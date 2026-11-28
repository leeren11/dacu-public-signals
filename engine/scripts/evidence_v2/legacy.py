"""Classify an already stored public signal without reading a production database.

A missing official source, a monthly background row, or a snapshot stays
ineligible. NULL is not rewritten to 0. A proven zero on the official daily
source remains a real zero, and one bucket is still not a forecast.
"""

from __future__ import annotations

from evidence_v2.adapters import adapter_for
from evidence_v2.timebox import classify_timestamps, parse_aware


def assess_legacy_row(row: dict) -> dict:
    platform = row.get("platform")
    adapter = adapter_for(platform)
    value = row.get("value") if "value" in row else None
    result = {
        "platform": platform,
        "eligible_for_daily_score": False,
        "reason": "",
        "value_is_null": value is None,
        "treated_as_zero": False,
        "official_daily": bool(adapter and adapter.official_daily),
    }
    if adapter is None or not adapter.official_daily:
        result["reason"] = adapter.reason if adapter else "no_official_adapter"
        return result
    if row.get("is_partial") in (1, True, "1") or row.get("status") == "partial":
        result["reason"] = "partial_day"
        return result
    if value is None or row.get("status") == "missing":
        result["reason"] = "null_is_not_zero"
        return result
    if row.get("status") not in (None, "observed"):
        result["reason"] = "status_" + str(row.get("status"))
        return result
    start = row.get("observed_start") or row.get("period_start")
    end = row.get("observed_end") or row.get("period_end")
    collected = row.get("collected_at") or row.get("as_of_ts")
    available = row.get("available_at")
    if classify_timestamps(start, end, collected, available) != "high":
        result["reason"] = "unproven_time"
        return result
    parsed_end = parse_aware(end)
    parsed_collected = parse_aware(collected)
    parsed_available = parse_aware(available)
    if None in (parsed_end, parsed_collected, parsed_available):
        result["reason"] = "unproven_time"
        return result
    if parsed_collected < parsed_end or parsed_available < parsed_end:
        result["reason"] = "collected_before_window_close"
        return result
    result["eligible_for_daily_score"] = True
    result["reason"] = "single_bucket_only_not_a_forecast"
    result["treated_as_zero"] = value == 0
    return result
