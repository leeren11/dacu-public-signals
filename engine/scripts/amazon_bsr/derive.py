"""Derived BSR and count metrics.

Daily selection is one snapshot: the latest observed_at that was already in
this database at the cutoff, then the lowest revision, then the lowest id.
It is not a daily median and it does not forward-fill a missing day.

The 7-day metrics require a snapshot on the UTC end date and on the UTC date
seven days earlier. Rank changes in another category are a different series.
csv[3] also refuses a window whose salesRankReference changed inside the span.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict

from amazon_bsr import (
    INTERPRET_COUNT,
    INTERPRET_LN,
    INTERPRET_PCT,
    METRIC_LN,
    METRIC_PCT,
    METRIC_RATING_COUNT,
    METRIC_WRITTEN_REVIEWS,
    POLICY_ID,
)
from amazon_bsr.db import require_migrated, transaction
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.redact import canonical_hash
from amazon_bsr.timeutil import add_utc_days, parse_date, parse_utc

BSR_SERIES = ("bsr_sales_ranks", "bsr_csv_sales")
COUNT_SERIES = ("rating_count", "written_review_count")
DERIVED_SERIES = BSR_SERIES + COUNT_SERIES
SPAN_MIN_DAYS = 6.0
SPAN_MAX_DAYS = 8.0
SELECTION_RULE = (
    "one snapshot per UTC day: latest observed_at, then lowest revision_seq, "
    "then lowest observation_id; not a median and not a forward-fill"
)
EVAL_NOTE = (
    "Independent evidence link. This row does not read or write prediction freezes, "
    "Live scores, or walk-forward weights. Rank metrics are not sales."
)


def _better(candidate: dict, current: dict) -> bool:
    if candidate["observed_at"] != current["observed_at"]:
        return candidate["observed_at"] > current["observed_at"]
    if candidate["revision_seq"] != current["revision_seq"]:
        return candidate["revision_seq"] < current["revision_seq"]
    return candidate["observation_id"] < current["observation_id"]


def select_daily(rows: list[dict], cutoff: str, *, respect_cutoff: bool) -> dict[str, dict]:
    chosen: dict[str, dict] = {}
    for row in rows:
        if row["is_valid_measurement"] != 1:
            continue
        if respect_cutoff and row["first_available_to_system"] > cutoff:
            continue
        day = row["observed_at"][:10]
        current = chosen.get(day)
        if current is None or _better(row, current):
            chosen[day] = row
    return chosen


def _value_token(value: float | None) -> str | None:
    if value is None:
        return None
    return format(float(value), ".12g")


def _metric_specs(series_kind: str, count_kind: str | None) -> list[tuple[str, str, str]]:
    if series_kind in BSR_SERIES:
        return [
            (METRIC_LN, INTERPRET_LN, "ln_ratio"),
            (METRIC_PCT, INTERPRET_PCT, "percent_rank_not_sales"),
        ]
    if series_kind == "rating_count" and count_kind == "rating_count":
        return [(METRIC_RATING_COUNT, INTERPRET_COUNT, "count")]
    if series_kind == "written_review_count" and count_kind == "written_review_count":
        return [(METRIC_WRITTEN_REVIEWS, INTERPRET_COUNT, "count")]
    return []


def _compute_value(metric_version: str, start: dict, end: dict) -> float:
    old = float(start["value_num"])
    new = float(end["value_num"])
    if metric_version == METRIC_LN:
        if old <= 0 or new <= 0:
            raise AmazonBsrError("nonpositive_rank", "refusing log of a non-positive rank")
        return math.log(old / new)
    if metric_version == METRIC_PCT:
        if old <= 0:
            raise AmazonBsrError("nonpositive_rank", "refusing percent change with a non-positive old rank")
        return (old - new) / old * 100.0
    return new - old


def _lookup_mapping(con, asin: str, as_of: str, cutoff: str) -> dict | None:
    return con.execute(
        """
        SELECT sku_cluster, mapping_version
        FROM amazon_asin_map
        WHERE asin = ? AND domain_id = 1
          AND recorded_at <= ?
          AND valid_from <= ?
          AND (valid_to IS NULL OR valid_to > ?)
        ORDER BY recorded_at DESC, map_id DESC
        LIMIT 1
        """,
        (asin, cutoff, as_of, as_of),
    ).fetchone()


def derive_metrics(
    con,
    *,
    selection_cutoff: str,
    as_of: str | None = None,
    eval_freeze_id: str | None = None,
    eval_date: str | None = None,
    allow_eval: bool = False,
    dry_run: bool = False,
) -> dict:
    require_migrated(con)
    parse_utc(selection_cutoff)
    if as_of is not None:
        parse_date(as_of)
    if eval_freeze_id:
        if not allow_eval:
            raise AmazonBsrError(
                "cutoff_required",
                "an evaluation link needs an explicit --selection-cutoff; the default now is not a freeze replay",
            )
        if not as_of or eval_date != as_of:
            raise AmazonBsrError("eval_date", "--eval-date must equal --as-of when linking a freeze label")
    rows = [
        dict(row)
        for row in con.execute(
            f"""
            SELECT * FROM amazon_observation
            WHERE domain_id = 1
              AND series_kind IN ({",".join("?" for _ in DERIVED_SERIES + ("sales_rank_reference",))})
            """,
            DERIVED_SERIES + ("sales_rank_reference",),
        )
    ]
    grouped: dict[tuple, list[dict]] = defaultdict(list)
    references: dict[str, list[dict]] = defaultdict(list)
    for row in rows:
        if row["series_kind"] == "sales_rank_reference":
            references[row["asin"]].append(row)
            continue
        if row["series_kind"] not in DERIVED_SERIES:
            continue
        key = (
            row["asin"],
            row["series_kind"],
            row["category_id"] or "",
            row["definition_variant"],
            row["count_kind"] or "",
        )
        grouped[key].append(row)
    planned = []
    for key, group_rows in grouped.items():
        asin, series_kind, category_key, variant, count_kind = key
        specs = _metric_specs(series_kind, count_kind or None)
        if not specs:
            continue
        known = select_daily(group_rows, selection_cutoff, respect_cutoff=True)
        any_time = select_daily(group_rows, selection_cutoff, respect_cutoff=False)
        days = [as_of] if as_of else sorted(known)
        for end_day in days:
            end = known.get(end_day)
            if end is None:
                continue
            start_day = add_utc_days(end_day, -7)
            start = known.get(start_day)
            late_start = start is None and any_time.get(start_day) is not None
            late_end = any_time.get(end_day) is not None and any_time[end_day]["observation_id"] != end["observation_id"]
            leak = 1 if late_start or late_end else 0
            status, reason, value_by_metric = _judge(
                series_kind,
                category_key,
                group_rows,
                references.get(asin, []),
                start,
                end,
                start_day,
                selection_cutoff,
                specs,
            )
            for metric_version, interpretation, unit in specs:
                value = value_by_metric.get(metric_version)
                guard = {
                    "selection_rule": SELECTION_RULE,
                    "span_days": _span_days(start, end) if start is not None else None,
                    "raw_point_count": _raw_count(group_rows, start, end, selection_cutoff) if start is not None else None,
                    "daily_snapshot_count": sum(1 for day in known if start_day <= day <= end_day),
                    "revisions_after_cutoff": sum(
                        1
                        for row in group_rows
                        if row["observed_at"][:10] in {start_day, end_day} and row["first_available_to_system"] > selection_cutoff
                    ),
                    "leak_excluded": leak,
                    "start_observation_id": None if start is None else start["observation_id"],
                    "end_observation_id": end["observation_id"],
                }
                payload = {
                    "metric_version": metric_version,
                    "policy_id": POLICY_ID,
                    "asin": asin,
                    "domain_id": 1,
                    "series_kind": series_kind,
                    "category_id": category_key or None,
                    "category_key": category_key,
                    "definition_variant": variant,
                    "count_kind": count_kind or None,
                    "as_of_utc_date": end_day,
                    "selection_cutoff": selection_cutoff,
                    "start_observation_id": None if start is None else start["observation_id"],
                    "end_observation_id": end["observation_id"],
                    "start_observed_at": None if start is None else start["observed_at"],
                    "end_observed_at": end["observed_at"],
                    "start_first_available": None if start is None else start["first_available_to_system"],
                    "end_first_available": end["first_available_to_system"],
                    "span_days": guard["span_days"] if status == "ok" else guard["span_days"],
                    "raw_point_count": guard["raw_point_count"],
                    "daily_snapshot_count": guard["daily_snapshot_count"],
                    "value": value if status == "ok" else None,
                    "unit": unit,
                    "interpretation": interpretation,
                    "status": status,
                    "status_reason": reason,
                    "guard_json": json.dumps(guard, ensure_ascii=False, sort_keys=True),
                    "leak_excluded": leak,
                }
                payload["input_hash"] = canonical_hash(
                    {
                        "metric_version": metric_version,
                        "policy_id": POLICY_ID,
                        "asin": asin,
                        "series_kind": series_kind,
                        "category_key": category_key,
                        "definition_variant": variant,
                        "as_of": end_day,
                        "cutoff": selection_cutoff,
                        "status": status,
                        "value": _value_token(payload["value"]),
                        "start_id": payload["start_observation_id"],
                        "end_id": payload["end_observation_id"],
                        "start_known": payload["start_first_available"],
                        "end_known": payload["end_first_available"],
                    }
                )
                planned.append(payload)
    if dry_run:
        return {
            "ok": True,
            "status": "dry_run",
            "wrote": False,
            "planned": len(planned),
            "ok_values": sum(1 for row in planned if row["status"] == "ok"),
            "policy_id": POLICY_ID,
        }
    with transaction(con):
        written = _insert_metrics(con, planned, eval_freeze_id=eval_freeze_id, eval_date=eval_date, cutoff=selection_cutoff)
    return {"ok": True, "status": "derived", "wrote": True, "policy_id": POLICY_ID, **written}


def _span_days(start: dict | None, end: dict) -> float | None:
    if start is None:
        return None
    return (parse_utc(end["observed_at"]) - parse_utc(start["observed_at"])).total_seconds() / 86400.0


def _raw_count(rows: list[dict], start: dict | None, end: dict, cutoff: str) -> int | None:
    if start is None:
        return None
    return sum(
        1
        for row in rows
        if row["is_valid_measurement"] == 1
        and row["first_available_to_system"] <= cutoff
        and start["observed_at"] <= row["observed_at"] <= end["observed_at"]
    )


def _judge(series_kind, category_key, rows, refs, start, end, start_day, cutoff, specs):
    if start is None:
        return "no_snapshot_on_start_utc_date", f"no valid snapshot on UTC {start_day} was known at the cutoff", {}
    if start["definition_variant"] != end["definition_variant"] or (start["count_kind"] or "") != (end["count_kind"] or ""):
        return "definition_mismatch", "endpoints do not share a count definition", {}
    between = [
        row
        for row in rows
        if start["observed_at"] < row["observed_at"] < end["observed_at"] and row["first_available_to_system"] <= cutoff
    ]
    if any(row["is_valid_measurement"] == 0 and row["value_missing_reason"] in {"keepa_missing_sentinel", "nonpositive"} for row in between):
        return (
            "discontinuity_gap",
            "a missing or non-positive sentinel sits inside the span; that is not continuous rank movement",
            {},
        )
    if series_kind == "bsr_csv_sales":
        for ref in refs:
            if ref["first_available_to_system"] > cutoff:
                continue
            if start["observed_at"] < ref["observed_at"] < end["observed_at"] and ref["value_text"] != category_key:
                return (
                    "discontinuity_reference_change",
                    "salesRankReference changed inside the window; csv[3] movement across that change is not used",
                    {},
                )
    span = _span_days(start, end)
    if span is None or span < SPAN_MIN_DAYS or span > SPAN_MAX_DAYS:
        return "span_guard", f"actual span {span} days is outside [{SPAN_MIN_DAYS}, {SPAN_MAX_DAYS}]", {}
    values = {}
    for metric_version, _interpretation, _unit in specs:
        values[metric_version] = _compute_value(metric_version, start, end)
    reason = "actual UTC snapshots seven calendar days apart in the same series"
    if "ratingCount_variation" in end["definition_variant"]:
        reason += (
            "; this variant is Keepa's variation ratingCount, documented as not updated since April 9th 2025"
        )
    if end["definition_variant"].startswith("keepa_csv17"):
        reason += "; csv[17] is rating count, not written review count"
    if end["count_kind"] == "written_review_count":
        reason += "; written review count only, not rating count"
    return "ok", reason, values


def _insert_metrics(con, planned: list[dict], *, eval_freeze_id: str | None, eval_date: str | None, cutoff: str) -> dict:
    inserted = 0
    skipped = 0
    conflicts = 0
    links = 0
    for row in planned:
        existing = con.execute(
            """
            SELECT metric_id, input_hash FROM amazon_derived_metric
            WHERE metric_version = ? AND policy_id = ? AND asin = ? AND domain_id = 1
              AND series_kind = ? AND category_key = ? AND definition_variant = ?
              AND as_of_utc_date = ? AND selection_cutoff = ?
            """,
            (
                row["metric_version"],
                row["policy_id"],
                row["asin"],
                row["series_kind"],
                row["category_key"],
                row["definition_variant"],
                row["as_of_utc_date"],
                row["selection_cutoff"],
            ),
        ).fetchone()
        if existing is None:
            cur = con.execute(
                """
                INSERT INTO amazon_derived_metric(
                  metric_version, policy_id, asin, domain_id, series_kind, category_id, category_key,
                  definition_variant, count_kind, as_of_utc_date, selection_cutoff,
                  start_observation_id, end_observation_id, start_observed_at, end_observed_at,
                  start_first_available, end_first_available, span_days, raw_point_count,
                  daily_snapshot_count, value, unit, interpretation, status, status_reason,
                  guard_json, input_hash
                ) VALUES (?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    row["metric_version"],
                    row["policy_id"],
                    row["asin"],
                    row["series_kind"],
                    row["category_id"],
                    row["category_key"],
                    row["definition_variant"],
                    row["count_kind"],
                    row["as_of_utc_date"],
                    row["selection_cutoff"],
                    row["start_observation_id"],
                    row["end_observation_id"],
                    row["start_observed_at"],
                    row["end_observed_at"],
                    row["start_first_available"],
                    row["end_first_available"],
                    row["span_days"],
                    row["raw_point_count"],
                    row["daily_snapshot_count"],
                    row["value"],
                    row["unit"],
                    row["interpretation"],
                    row["status"],
                    row["status_reason"],
                    row["guard_json"],
                    row["input_hash"],
                ),
            )
            metric_id = cur.lastrowid
            inserted += 1
        elif existing["input_hash"] == row["input_hash"]:
            metric_id = existing["metric_id"]
            skipped += 1
        else:
            conflicts += 1
            continue
        if eval_freeze_id and metric_id is not None:
            links += _link(con, metric_id, row, eval_freeze_id, eval_date, cutoff)
    return {"inserted": inserted, "skipped": skipped, "conflicts": conflicts, "eval_links": links, "considered": len(planned)}


def _link(con, metric_id: int, row: dict, freeze_id: str, eval_date: str, cutoff: str) -> int:
    existing = con.execute(
        """
        SELECT 1 FROM amazon_eval_link
        WHERE freeze_id = ? AND evaluation_date = ? AND cutoff_at = ? AND metric_id = ?
        """,
        (freeze_id, eval_date, cutoff, metric_id),
    ).fetchone()
    if existing is not None:
        return 0
    mapping = _lookup_mapping(con, row["asin"], row["as_of_utc_date"], cutoff)
    if row["status"] != "ok" and row["leak_excluded"]:
        link_status = "withheld_not_known"
    elif row["status"] != "ok":
        link_status = "withheld_no_metric"
    elif mapping is not None:
        link_status = "linked"
    else:
        link_status = "linked_asin_only"
    con.execute(
        """
        INSERT INTO amazon_eval_link(
          freeze_id, evaluation_date, cutoff_at, metric_id, sku_cluster, mapping_version,
          asin, domain_id, link_status, leak_excluded, note
        ) VALUES (?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?)
        """,
        (
            freeze_id,
            eval_date,
            cutoff,
            metric_id,
            None if mapping is None else mapping["sku_cluster"],
            None if mapping is None else mapping["mapping_version"],
            row["asin"],
            link_status,
            row["leak_excluded"],
            EVAL_NOTE,
        ),
    )
    return 1
