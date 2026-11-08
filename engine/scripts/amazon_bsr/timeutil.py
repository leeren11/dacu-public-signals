from __future__ import annotations

from datetime import datetime, timezone

from amazon_bsr.errors import AmazonBsrError

UTC_FMT = "%Y-%m-%dT%H:%M:%SZ"
# Minutes from Unix epoch (1970-01-01) to Keepa epoch (2011-01-01), both UTC.
# https://keepa.com/api-docs/product-object.html
KEEPA_EPOCH_OFFSET_MINUTES = 21_564_000


def format_utc(dt: datetime) -> str:
    if dt.tzinfo is None:
        raise AmazonBsrError("timezone_required", "refusing a naive datetime")
    return dt.astimezone(timezone.utc).strftime(UTC_FMT)


def now_utc() -> str:
    return format_utc(datetime.now(timezone.utc))


def parse_utc(value: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise AmazonBsrError(
            "timezone_required",
            "timestamps must be UTC and end with Z, for example 2026-11-08T00:00:00Z",
        )
    try:
        return datetime.strptime(value, UTC_FMT).replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise AmazonBsrError("bad_timestamp", f"unusable timestamp: {value}") from exc


def parse_date(value: str) -> str:
    if not isinstance(value, str):
        raise AmazonBsrError("bad_date", "date must be YYYY-MM-DD")
    try:
        datetime.strptime(value, "%Y-%m-%d")
    except ValueError as exc:
        raise AmazonBsrError("bad_date", f"date must be YYYY-MM-DD, got {value}") from exc
    return value


def keepa_minutes_to_utc(minutes: int) -> str | None:
    """Convert Keepa Time minutes to UTC.

    Keepa Time 0 is 2011-01-01T00:00:00Z. Negative values are not converted:
    Keepa uses them as sentinels on some fields (for example listedSince -1,
    or a negative lastEbayUpdate). listedSince also uses 0 as "not available";
    callers that read listedSince must not send 0 through this function.
    """
    if isinstance(minutes, bool) or not isinstance(minutes, int):
        return None
    if minutes < 0:
        return None
    unix = (minutes + KEEPA_EPOCH_OFFSET_MINUTES) * 60
    return format_utc(datetime.fromtimestamp(unix, timezone.utc))


def add_utc_days(day: str, days: int) -> str:
    base = datetime.strptime(parse_date(day), "%Y-%m-%d")
    from datetime import timedelta

    return (base + timedelta(days=days)).date().isoformat()
