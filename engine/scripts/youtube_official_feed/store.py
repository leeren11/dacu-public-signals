"""Isolated SQLite ledger for youtube_official_feed_v1. No score tables are written."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from collectors.archive import atomic_write_text, sha256_text

from youtube_official_feed import (
    DELTA_DISCLOSURE,
    LICENSE_BASIS,
    RETENTION_DAYS,
    RULE_VERSION,
    SOURCE,
)
from youtube_official_feed.http import fetch_channel
from youtube_official_feed.parse import FeedEntry, official_url, parse_feed

SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "migrate_v8_youtube_official_feed.sql"

DISABLED = (
    ("youtube_data_api", "disabled", "HTTP 403 ACCESS_DENIED without an authorized project. Not treated as a missing key only."),
    ("reddit", "disabled", "JSON 403 and RSS HTTP 200 HTML login wall. No commercial API agreement and no refetch."),
    ("meta_ad_library", "disabled", "HTTP 403. Official docs were not verified this round. No connector installed."),
    ("google_trends_official", "disabled", "Official Trends API is still an alpha application. Existing relative index is unchanged."),
    ("tiktok_research", "disabled", "Research approval and commercial eligibility are unknown. Monthly background is not a daily series."),
    ("keepa", "disabled", "No API key. Formal ASIN map and BSR observations are still zero."),
)


def connect(path: str) -> sqlite3.Connection:
    connection = sqlite3.connect(path)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    return connection


def migrate(connection: sqlite3.Connection) -> None:
    connection.executescript(SQL_PATH.read_text())
    connection.execute(
        """INSERT OR IGNORE INTO youtube_feed_policy
           (policy_id, retention_days, license_basis, delta_disclosure, statistics_are_score)
           VALUES ('default', ?, ?, ?, 0)""",
        (RETENTION_DAYS, LICENSE_BASIS, DELTA_DISCLOSURE),
    )
    for source_id, state, reason in DISABLED:
        connection.execute(
            "INSERT OR IGNORE INTO youtube_feed_disabled_source (source_id, state, reason) VALUES (?,?,?)",
            (source_id, state, reason),
        )
    connection.commit()


def approve_watchlist(connection: sqlite3.Connection, document: dict) -> str:
    label = document.get("example_label")
    if label not in ("SYNTHETIC_EXAMPLE_NOT_PRODUCTION", "PUBLIC_FEED_EXCERPT_NOT_PRODUCTION", "operator_approved"):
        raise ValueError("watchlist example_label is missing or not an allowed marker")
    version = document["watchlist_version"]
    channels = document.get("channels") or []
    if not channels:
        raise ValueError("watchlist has no channels")
    for item in channels:
        if int(item.get("maps_to_sku") or 0) != 0:
            raise ValueError("this adapter cannot grant SKU coverage")
        if item.get("status") not in ("approved_shadow_only", "connectivity_control"):
            raise ValueError("channel status is not approved for shadow fetch")
        official_url(item["channel_id"])
        connection.execute(
            """INSERT OR IGNORE INTO youtube_feed_watchlist
               (source, channel_id, watchlist_version, handle, scope, business_role, maps_to_sku,
                provenance_url, approved_at, included_from, status, example_label)
               VALUES (?,?,?,?,?,?,0,?,?,?,?,?)""",
            (
                SOURCE, item["channel_id"], version, item.get("handle") or item["channel_id"],
                item["scope"], item["business_role"], item.get("provenance_url"),
                item.get("approved_at"), item["included_from"], item["status"], label,
            ),
        )
    connection.commit()
    return version


def _watch(connection: sqlite3.Connection, channel_id: str, version: str) -> sqlite3.Row:
    row = connection.execute(
        """SELECT * FROM youtube_feed_watchlist
           WHERE source=? AND channel_id=? AND watchlist_version=?""",
        (SOURCE, channel_id, version),
    ).fetchone()
    if row is None:
        raise ValueError("channel is not on the approved watchlist")
    return row


def _seen(connection: sqlite3.Connection, object_id: str, now: str) -> str:
    row = connection.execute(
        "SELECT first_available_at FROM youtube_feed_object_seen WHERE source_object_id=?",
        (object_id,),
    ).fetchone()
    if row is not None:
        return row["first_available_at"]
    connection.execute(
        "INSERT INTO youtube_feed_object_seen (source_object_id, first_available_at) VALUES (?,?)",
        (object_id, now),
    )
    return now


def _hours(earlier: str, later: str) -> float | None:
    try:
        left = datetime.fromisoformat(earlier.replace("Z", "+00:00"))
        right = datetime.fromisoformat(later.replace("Z", "+00:00"))
    except ValueError:
        return None
    if left.tzinfo is None or right.tzinfo is None:
        return None
    return (right - left).total_seconds() / 3600.0


def _boundary_matched(earlier: str, later: str) -> bool:
    gap = _hours(earlier, later)
    if gap is None or abs(gap - 24.0) > 1e-9:
        return False
    try:
        left = datetime.fromisoformat(earlier.replace("Z", "+00:00")).astimezone(timezone.utc)
        right = datetime.fromisoformat(later.replace("Z", "+00:00")).astimezone(timezone.utc)
    except ValueError:
        return False
    midnight = left.hour == left.minute == left.second == left.microsecond == 0
    return midnight and right.hour == right.minute == right.second == right.microsecond == 0


def _insert_delta(connection: sqlite3.Connection, channel_id: str, later_evidence: str, later_retrieved: str, video_id: str, later_value):
    previous = connection.execute(
        """SELECT s.evidence_id, s.retrieved_at, s.value, s.status
           FROM youtube_feed_snapshot s
           JOIN youtube_feed_evidence e ON e.evidence_id = s.evidence_id
           WHERE s.source_object_id=? AND s.metric_key='views_cumulative_snapshot'
             AND s.evidence_id<>? AND e.channel_id=? AND e.status='stored'
           ORDER BY s.retrieved_at DESC LIMIT 1""",
        (video_id, later_evidence, channel_id),
    ).fetchone()
    if previous is None:
        return
    hours = _hours(previous["retrieved_at"], later_retrieved)
    if previous["value"] is None or later_value is None or previous["status"] != "observed":
        connection.execute(
            """INSERT OR IGNORE INTO youtube_feed_cohort_delta
               (earlier_evidence_id, later_evidence_id, source_object_id, earlier_value, later_value,
                delta_value, hours_between, status, missing_reason, disclosure, not_for_scoring)
               VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
            (
                previous["evidence_id"], later_evidence, video_id, previous["value"], later_value,
                None, hours, "missing", "endpoint_missing", DELTA_DISCLOSURE,
            ),
        )
        return
    matched = hours is not None and _boundary_matched(previous["retrieved_at"], later_retrieved)
    connection.execute(
        """INSERT OR IGNORE INTO youtube_feed_cohort_delta
           (earlier_evidence_id, later_evidence_id, source_object_id, earlier_value, later_value,
            delta_value, hours_between, status, missing_reason, disclosure, not_for_scoring)
           VALUES (?,?,?,?,?,?,?,?,?,?,1)""",
        (
            previous["evidence_id"], later_evidence, video_id, previous["value"], later_value,
            float(later_value) - float(previous["value"]), hours,
            "interval_matched" if matched else "partial",
            None if matched else "interval_is_not_an_exact_utc_day",
            DELTA_DISCLOSURE,
        ),
    )


def store_parsed(
    connection: sqlite3.Connection,
    *,
    parsed: dict,
    channel_id: str,
    watchlist_version: str,
    retrieved_at: str,
    now: str,
    http_status: int | None,
    content_type: str,
    body: str,
    archive_dir: Path,
    example_label: str,
    etag: str | None = None,
    evidence_status: str = "stored",
    missing_reason: str | None = None,
) -> str:
    watch = _watch(connection, channel_id, watchlist_version)
    if datetime.fromisoformat(now.replace("Z", "+00:00")) < datetime.fromisoformat(retrieved_at.replace("Z", "+00:00")):
        raise ValueError("first_available clock cannot be earlier than retrieved_at")
    digest = sha256_text(body)
    raw_bytes = len(body.encode("utf-8"))
    evidence_id = sha256_text("|".join([SOURCE, official_url(channel_id), retrieved_at, digest]))
    existing = connection.execute(
        "SELECT evidence_id, first_available_at FROM youtube_feed_evidence WHERE evidence_id=?",
        (evidence_id,),
    ).fetchone()
    if existing is not None:
        return existing["evidence_id"]
    destination = Path(archive_dir) / digest[:2] / digest
    if not destination.exists():
        atomic_write_text(destination, body)
    saved = destination.stat().st_size
    truncated = 0 if saved == raw_bytes else 1
    if truncated:
        evidence_status = "truncated"
        missing_reason = "archive_truncated"
        parsed = {"kind": "truncated", "entries": [], "rejected": [], "uploads": None}
    connection.execute(
        """INSERT INTO youtube_feed_evidence
           (evidence_id, source, channel_id, request_url, retrieved_at, first_available_at,
            http_status, content_type, response_path, response_sha256, response_bytes, saved_bytes,
            truncated, status, missing_reason, license_basis, watchlist_version, etag, not_modified_of, example_label)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            evidence_id, SOURCE, channel_id, official_url(channel_id), retrieved_at, now,
            http_status, content_type, str(destination), digest, raw_bytes, saved, truncated,
            evidence_status, missing_reason, LICENSE_BASIS, watchlist_version, etag, None, example_label,
        ),
    )
    _seen(connection, channel_id, now)
    if evidence_status != "stored" or parsed.get("kind") != "atom":
        connection.commit()
        return evidence_id
    uploads = parsed["uploads"]
    _snapshot(
        connection, evidence_id, channel_id, channel_id, None, None, retrieved_at,
        uploads["metric_key"], uploads["value"], "recent_entries", official_url(channel_id),
        None, None, uploads["status"], uploads["reason"],
    )
    for entry in parsed["entries"]:
        _seen(connection, entry.video_id, now)
        _snapshot(
            connection, evidence_id, entry.video_id, channel_id, entry.published_at, entry.feed_updated_at,
            retrieved_at, "views_cumulative_snapshot", entry.views, "views_cumulative_snapshot",
            entry.source_url, entry.title, entry.content_tag, entry.view_status, entry.view_reason,
        )
        _insert_delta(connection, channel_id, evidence_id, retrieved_at, entry.video_id, entry.views if entry.view_status == "observed" else None)
    if watch["status"] == "connectivity_control":
        connection.execute(
            "UPDATE youtube_feed_snapshot SET content_tag=NULL WHERE evidence_id=?",
            (evidence_id,),
        )
    connection.commit()
    return evidence_id


def _snapshot(connection, evidence_id, object_id, channel_id, published, updated, retrieved, metric, value, unit, url, title, tag, status, reason):
    if status == "observed" and value is None:
        status = "missing"
        reason = reason or "null_is_not_zero"
    connection.execute(
        """INSERT OR IGNORE INTO youtube_feed_snapshot
           (evidence_id, source_object_id, channel_id, published_at, feed_updated_at, retrieved_at,
            metric_key, value, unit, source_url, title, content_tag, category_rule_version,
            is_proxy, maps_to_sku, not_for_scoring, status, missing_reason)
           VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,1,0,1,?,?)""",
        (
            evidence_id, object_id, channel_id, published, updated, retrieved, metric, value, unit,
            url, title, tag, RULE_VERSION, status, reason,
        ),
    )


def import_xml(
    connection: sqlite3.Connection,
    *,
    xml_text: str,
    channel_id: str,
    watchlist_version: str,
    retrieved_at: str,
    now: str,
    archive_dir: Path,
    example_label: str,
    content_type: str = "text/xml",
) -> str:
    parsed = parse_feed(xml_text, channel_id)
    status = "stored" if parsed.get("kind") == "atom" else "missing"
    reason = None if status == "stored" else parsed.get("kind")
    return store_parsed(
        connection, parsed=parsed, channel_id=channel_id, watchlist_version=watchlist_version,
        retrieved_at=retrieved_at, now=now, http_status=200 if status == "stored" else None,
        content_type=content_type, body=xml_text, archive_dir=archive_dir, example_label=example_label,
        evidence_status=status, missing_reason=reason,
    )


def record_fetch(
    connection: sqlite3.Connection,
    *,
    channel_id: str,
    watchlist_version: str,
    transport,
    now: str,
    archive_dir: Path,
    example_label: str,
    sleep=lambda _seconds: None,
) -> dict:
    _watch(connection, channel_id, watchlist_version)
    state_row = connection.execute(
        "SELECT * FROM youtube_feed_source_state WHERE channel_id=?",
        (channel_id,),
    ).fetchone()
    state = dict(state_row) if state_row else {}
    previous_etag = connection.execute(
        """SELECT etag FROM youtube_feed_evidence
           WHERE channel_id=? AND etag IS NOT NULL AND status='stored'
           ORDER BY retrieved_at DESC LIMIT 1""",
        (channel_id,),
    ).fetchone()
    if previous_etag is not None:
        state["etag"] = previous_etag["etag"]
    outcome = fetch_channel(channel_id, transport, state, sleep, datetime.fromisoformat(now.replace("Z", "+00:00")))
    if outcome.stop_state:
        connection.execute(
            """INSERT INTO youtube_feed_source_state (channel_id, state, http_status, reason, stopped_at, retry_after)
               VALUES (?,?,?,?,?,?)
               ON CONFLICT(channel_id) DO UPDATE SET
                 state=excluded.state, http_status=excluded.http_status, reason=excluded.reason,
                 stopped_at=excluded.stopped_at, retry_after=excluded.retry_after""",
            (channel_id, outcome.stop_state, outcome.http_status, outcome.reason, now, outcome.retry_after),
        )
        connection.commit()
    if outcome.status == "stopped_auth" and not outcome.requested:
        return {"status": "stopped_auth", "requested": False, "evidence_id": None}
    if outcome.status == "not_modified":
        previous = connection.execute(
            """SELECT evidence_id FROM youtube_feed_evidence
               WHERE channel_id=? AND status='stored' ORDER BY retrieved_at DESC LIMIT 1""",
            (channel_id,),
        ).fetchone()
        marker = sha256_text("|".join(["304", outcome.etag or "", now]))
        evidence_id = sha256_text("|".join([SOURCE, official_url(channel_id), now, marker]))
        connection.execute(
            """INSERT OR IGNORE INTO youtube_feed_evidence
               (evidence_id, source, channel_id, request_url, retrieved_at, first_available_at,
                http_status, content_type, response_path, response_sha256, response_bytes, saved_bytes,
                truncated, status, missing_reason, license_basis, watchlist_version, etag, not_modified_of, example_label)
               VALUES (?,?,?,?,?,?,304,'',NULL,?,0,0,0,'not_modified',NULL,?,?,?,?,?)""",
            (
                evidence_id, SOURCE, channel_id, official_url(channel_id), now, now, marker,
                LICENSE_BASIS, watchlist_version, outcome.etag, None if previous is None else previous["evidence_id"],
                example_label,
            ),
        )
        connection.commit()
        return {"status": "not_modified", "requested": True, "evidence_id": evidence_id, "snapshots_added": 0}
    if outcome.status != "ok":
        return {"status": outcome.status, "requested": outcome.requested, "evidence_id": None, "reason": outcome.reason}
    parsed = parse_feed(outcome.body, channel_id)
    status = "stored" if parsed.get("kind") == "atom" else "missing"
    evidence_id = store_parsed(
        connection, parsed=parsed, channel_id=channel_id, watchlist_version=watchlist_version,
        retrieved_at=now, now=now, http_status=200, content_type=outcome.content_type or "text/xml",
        body=outcome.body, archive_dir=archive_dir, example_label=example_label, etag=outcome.etag,
        evidence_status=status, missing_reason=None if status == "stored" else parsed.get("kind"),
    )
    return {"status": status, "requested": True, "evidence_id": evidence_id}


def purge_expired(connection: sqlite3.Connection, now: str) -> int:
    policy = connection.execute("SELECT retention_days FROM youtube_feed_policy WHERE policy_id='default'").fetchone()
    days = int(policy["retention_days"])
    cutoff = datetime.fromisoformat(now.replace("Z", "+00:00")) - timedelta(days=days)
    rows = connection.execute("SELECT evidence_id, retrieved_at, response_path FROM youtube_feed_evidence").fetchall()
    removed = 0
    for row in rows:
        retrieved = datetime.fromisoformat(row["retrieved_at"].replace("Z", "+00:00"))
        if retrieved >= cutoff:
            continue
        connection.execute("DELETE FROM youtube_feed_cohort_delta WHERE earlier_evidence_id=? OR later_evidence_id=?", (row["evidence_id"], row["evidence_id"]))
        connection.execute("DELETE FROM youtube_feed_snapshot WHERE evidence_id=?", (row["evidence_id"],))
        connection.execute("DELETE FROM youtube_feed_evidence WHERE evidence_id=?", (row["evidence_id"],))
        if row["response_path"]:
            path = Path(row["response_path"])
            if path.exists():
                path.unlink()
        removed += 1
    connection.commit()
    return removed


def rollback(connection: sqlite3.Connection) -> None:
    for name in (
        "youtube_feed_cohort_delta",
        "youtube_feed_snapshot",
        "youtube_feed_evidence",
        "youtube_feed_object_seen",
        "youtube_feed_source_state",
        "youtube_feed_watchlist",
        "youtube_feed_disabled_source",
        "youtube_feed_policy",
    ):
        connection.execute(f"DROP TABLE IF EXISTS {name}")
    connection.execute("DELETE FROM schema_migrations WHERE version='8'")
    connection.commit()


def load_json(path: str) -> dict:
    return json.loads(Path(path).read_text())
