"""Atom parser for the official channel feed. Rejects DOCTYPE and entity declarations."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from xml.etree import ElementTree

from collectors.feed_honesty import classify_document

from youtube_official_feed import FEED_CAP, RULE_VERSION

ATOM = "http://www.w3.org/2005/Atom"
YT = "http://www.youtube.com/xml/schemas/2015"
MEDIA = "http://search.yahoo.com/mrss/"
NS = {"atom": ATOM, "yt": YT, "media": MEDIA}
_CHANNEL_RE = re.compile(r"^UC[0-9A-Za-z_-]{22}$")


@dataclass
class FeedEntry:
    video_id: str
    channel_id: str
    title: str
    published_at: str | None
    feed_updated_at: str | None
    views: int | None
    view_status: str
    view_reason: str | None
    source_url: str
    content_tag: str | None


def official_url(channel_id: str) -> str:
    if not _CHANNEL_RE.fullmatch(channel_id or ""):
        raise ValueError("channel_id is not an allowlisted YouTube channel id")
    return f"https://www.youtube.com/feeds/videos.xml?channel_id={channel_id}"


def same_official_url(url: str, channel_id: str) -> bool:
    try:
        expected = official_url(channel_id)
    except ValueError:
        return False
    return (url or "").split("#", 1)[0] == expected


def content_tag(title: str) -> str | None:
    """Content screen only. A tag is not demand, sales, or SKU coverage."""
    lowered = title.lower()
    compact = lowered.replace(" ", "").replace("-", "")
    has_press = "pressonnail" in compact or "press-on" in lowered
    has_christmas = "christmas" in lowered
    has_gel = "gelnails" in compact or "semicured" in compact or "gelnail" in compact
    if has_press and has_christmas:
        return "press_on_christmas_candidate"
    if has_gel and not has_press:
        return "gel_or_strip_not_press_on"
    return None


def _local(element: ElementTree.Element, name: str) -> str | None:
    child = element.find(f"atom:{name}", NS)
    if child is None or child.text is None:
        return None
    text = child.text.strip()
    return text or None


def _aware(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _views(entry: ElementTree.Element) -> tuple[int | None, str, str | None]:
    node = entry.find("media:group/media:community/media:statistics", NS)
    if node is None or node.get("views") is None:
        return None, "missing", "views_attribute_absent"
    raw = node.get("views")
    if raw is None or not re.fullmatch(r"[0-9]+", raw):
        return None, "missing", "views_not_an_integer"
    return int(raw), "observed", None


def _reject_declarations(xml_text: str) -> None:
    lowered = xml_text.lower()
    if "<!doctype" in lowered or "<!entity" in lowered:
        raise ValueError("doctype_or_entity_refused")


def parse_feed(xml_text: str, expected_channel_id: str) -> dict:
    kind = classify_document(xml_text, None)
    if kind in ("auth_wall", "html_not_feed"):
        return {"kind": kind, "entries": [], "rejected": [], "title": None}
    if kind not in ("atom", "xml_not_feed"):
        return {"kind": kind, "entries": [], "rejected": [], "title": None}
    try:
        _reject_declarations(xml_text)
        root = ElementTree.fromstring(xml_text)
    except ValueError as exc:
        return {"kind": "invalid_xml", "entries": [], "rejected": [], "title": None, "error": str(exc)}
    except ElementTree.ParseError as exc:
        return {"kind": "invalid_xml", "entries": [], "rejected": [], "title": None, "error": str(exc)}
    if root.tag != f"{{{ATOM}}}feed":
        return {"kind": "xml_not_feed", "entries": [], "rejected": [], "title": None}
    title = _local(root, "title")
    chosen: dict[str, FeedEntry] = {}
    rejected = []
    for node in root.findall("atom:entry", NS):
        video_id = None
        video_node = node.find("yt:videoId", NS)
        if video_node is not None and video_node.text:
            video_id = video_node.text.strip()
        channel_node = node.find("yt:channelId", NS)
        channel_id = channel_node.text.strip() if channel_node is not None and channel_node.text else ""
        if not video_id or not _CHANNEL_RE.fullmatch(channel_id):
            rejected.append({"video_id": video_id, "reason": "missing_identity"})
            continue
        if channel_id != expected_channel_id:
            rejected.append({"video_id": video_id, "reason": "channel_mismatch"})
            continue
        views, view_status, view_reason = _views(node)
        link = None
        for item in node.findall("atom:link", NS):
            if item.get("rel") == "alternate" and item.get("href"):
                link = item.get("href")
                break
        if not link:
            link = f"https://www.youtube.com/watch?v={video_id}"
        entry_title = _local(node, "title") or ""
        entry = FeedEntry(
            video_id=video_id,
            channel_id=channel_id,
            title=entry_title,
            published_at=_local(node, "published"),
            feed_updated_at=_local(node, "updated"),
            views=views,
            view_status=view_status,
            view_reason=view_reason,
            source_url=link,
            content_tag=content_tag(entry_title),
        )
        previous = chosen.get(video_id)
        if previous is None:
            chosen[video_id] = entry
            continue
        if previous.views is None and entry.views is not None:
            chosen[video_id] = entry
            continue
        if entry.views is None or previous.views == entry.views:
            continue
        entry.views = None
        entry.view_status = "conflict"
        entry.view_reason = "duplicate_video_views_disagree"
        chosen[video_id] = entry
    entries = list(chosen.values())
    return {
        "kind": "atom",
        "title": title,
        "entries": entries,
        "rejected": rejected,
        "uploads": _uploads(entries),
        "rule_version": RULE_VERSION,
    }


def _uploads(entries: list[FeedEntry]) -> dict:
    published = [item for item in (_aware(entry.published_at) for entry in entries) if item is not None]
    value = float(len(entries))
    if len(entries) >= FEED_CAP and published and max(published) - min(published) < timedelta(hours=24):
        return {
            "value": value,
            "status": "partial",
            "reason": "feed_cap_shorter_than_24h",
            "metric_key": "observed_recent_uploads",
        }
    if len(entries) >= FEED_CAP:
        return {
            "value": value,
            "status": "partial",
            "reason": "feed_capped_eviction_possible",
            "metric_key": "observed_recent_uploads",
        }
    return {
        "value": value,
        "status": "partial",
        "reason": "no_pagination_proof",
        "metric_key": "observed_recent_uploads",
    }


def bucket_anchor_present(entries: list[FeedEntry], bucket_start: datetime) -> bool:
    """True when the oldest published entry is at or before the UTC bucket start.

    This is an audit note. The stored upload row stays partial because a capped
    feed can still lose videos to deletion.
    """
    published = [item for item in (_aware(entry.published_at) for entry in entries) if item is not None]
    if not published:
        return False
    return min(published) <= bucket_start.astimezone(timezone.utc)
