"""Allowlisted GET for one official feed URL. No proxy, no cookie, no other host."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

from youtube_official_feed import USER_AGENT
from youtube_official_feed.parse import official_url, same_official_url


@dataclass
class Exchange:
    status: int | None
    body: str = ""
    content_type: str = ""
    headers: dict | None = None
    error: str | None = None
    final_url: str = ""
    etag: str | None = None


@dataclass
class FetchOutcome:
    requested: bool
    status: str
    http_status: int | None = None
    body: str = ""
    content_type: str = ""
    etag: str | None = None
    reason: str = ""
    stop_state: str | None = None
    retry_after: str | None = None


def _retry_after_seconds(headers: dict | None, now: datetime) -> float | None:
    if not headers:
        return None
    raw = None
    for key, value in headers.items():
        if key.lower() == "retry-after":
            raw = value
            break
    if raw is None:
        return None
    text = str(raw).strip()
    if text.isdigit():
        return float(text)
    try:
        when = parsedate_to_datetime(text)
    except (TypeError, ValueError, IndexError):
        return None
    if when.tzinfo is None:
        when = when.replace(tzinfo=timezone.utc)
    return (when - now).total_seconds()


def fetch_channel(channel_id: str, transport, state: dict | None, sleep, now: datetime) -> FetchOutcome:
    """Call transport only for the official URL. 401/403 stop the channel."""
    url = official_url(channel_id)
    current = state or {}
    if current.get("state") == "stopped_auth":
        return FetchOutcome(False, "stopped_auth", reason=current.get("reason") or "authorization previously failed")
    headers = {"User-Agent": USER_AGENT, "Accept": "application/atom+xml, application/xml;q=0.9"}
    if current.get("etag"):
        headers["If-None-Match"] = current["etag"]
    attempts = 0
    while attempts < 3:
        attempts += 1
        try:
            result = transport(url, headers)
        except TimeoutError:
            if attempts >= 3:
                return FetchOutcome(True, "timeout", reason="timeout")
            sleep(min(0.5, 0.2 * attempts))
            continue
        if not isinstance(result, Exchange):
            raise TypeError("transport must return Exchange")
        final_url = result.final_url or url
        if not same_official_url(final_url, channel_id):
            return FetchOutcome(True, "refused", reason="redirect_off_allowlist")
        code = result.status
        if code in (401, 403):
            return FetchOutcome(
                True, "stopped_auth", http_status=code, reason=f"HTTP {code}", stop_state="stopped_auth",
            )
        if code == 429:
            wait = _retry_after_seconds(result.headers, now)
            if attempts == 1 and wait is not None and 0 <= wait <= 5:
                sleep(wait)
                continue
            retry_at = None
            if wait is not None and wait > 0:
                retry_at = (now + timedelta(seconds=wait)).isoformat()
            return FetchOutcome(
                True, "rate_limited", http_status=429, reason="HTTP 429",
                stop_state="rate_limited", retry_after=retry_at,
            )
        if code == 304:
            return FetchOutcome(True, "not_modified", http_status=304, etag=result.etag, reason="not_modified")
        if code == 200:
            return FetchOutcome(
                True, "ok", http_status=200, body=result.body or "",
                content_type=result.content_type or "", etag=result.etag,
            )
        if code is None or code >= 500:
            if attempts < 3:
                sleep(min(0.5, 0.2 * attempts))
                continue
            return FetchOutcome(True, "unavailable", http_status=code, reason=result.error or f"HTTP {code}")
        return FetchOutcome(True, "refused", http_status=code, reason=f"HTTP {code}")
    return FetchOutcome(True, "unavailable", reason="retries_exhausted")
