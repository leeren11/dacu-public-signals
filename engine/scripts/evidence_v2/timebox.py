"""Point-in-time windows.

The date-window idea is adapted from last30days-skill dates.py at the pinned
review commit. This module is stricter: a date-only or missing available/collected
time is not usable, and a future bucket is withheld. Unknown is not low, and
unknown is not zero.
"""

from __future__ import annotations

from datetime import date, datetime, timedelta, timezone


def parse_aware(value: str | None) -> datetime | None:
    """Return a UTC datetime, or None when the value is not an aware timestamp."""
    if value is None:
        return None
    text = str(value).strip()
    if not text or _is_date_only(text):
        return None
    text = text.replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed.astimezone(timezone.utc)


def _is_date_only(text: str) -> bool:
    return len(text) == 10 and text[4] == "-" and text[7] == "-"


def classify_timestamps(*values: str | None) -> str:
    """high = every field is an aware timestamp; medium = a bare date exists; else unknown."""
    present = [value for value in values if value is not None and str(value).strip()]
    if len(present) != len(values):
        if any(_is_date_only(str(value).strip()) for value in present):
            return "medium"
        return "unknown"
    if all(parse_aware(str(value)) is not None for value in present):
        return "high"
    if any(_is_date_only(str(value).strip()) for value in present):
        return "medium"
    return "unknown"


def complete_utc_window(as_of: datetime, lookback_days: int) -> tuple[date, date]:
    """Closed UTC days ending before the open UTC day that contains as_of.

    Returns (window_start, window_end_exclusive). A bucket [D, D+1) is inside
    the window only when its end is at or before as_of.
    """
    if as_of.tzinfo is None:
        raise ValueError("as_of must be timezone-aware")
    if lookback_days < 2:
        raise ValueError("lookback_days must be at least 2")
    end_exclusive = as_of.astimezone(timezone.utc).date()
    start = end_exclusive - timedelta(days=lookback_days)
    return start, end_exclusive


def window_dates(start: date, end_exclusive: date) -> list[date]:
    days = []
    cursor = start
    while cursor < end_exclusive:
        days.append(cursor)
        cursor += timedelta(days=1)
    return days


def bucket_bounds(day: str) -> tuple[str, str]:
    start_day = date.fromisoformat(day)
    start = datetime(start_day.year, start_day.month, start_day.day, tzinfo=timezone.utc)
    end = start + timedelta(days=1)
    return start.isoformat(), end.isoformat()


def bucket_date(observed_start: str | None) -> date | None:
    parsed = parse_aware(observed_start)
    if parsed is None:
        return None
    return parsed.date()


def pit_decision(row: dict, cutoff: datetime) -> tuple[bool, str]:
    """Whether this exact revision was provably usable at cutoff."""
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    start = parse_aware(row.get("observed_start"))
    end = parse_aware(row.get("observed_end"))
    collected = parse_aware(row.get("collected_at"))
    available = parse_aware(row.get("available_at"))
    if row.get("date_confidence") != "high" or None in (start, end, collected, available):
        return False, "unproven_time"
    if end <= start:
        return False, "bad_window"
    if end > cutoff:
        return False, "future_or_open_bucket"
    if collected > cutoff or available > cutoff:
        return False, "not_yet_available"
    if collected < end or available < end:
        return False, "collected_before_window_close"
    return True, "visible"
