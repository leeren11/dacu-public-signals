"""Shadow demand from PIT-valid daily X buckets only.

The score is the existing X momentum transform. It is not on the director_v1
0–5 scale, it does not impute 2.5, and it is not a probability. A missing,
partial, unproven, or non-daily input leaves the entity pending.
"""

from __future__ import annotations

import json
import math
import sqlite3
from datetime import date, datetime, timezone

from display_names import METRIC_TO_SKUS, SKU_PRIMARY_METRIC

from evidence_v2 import (
    COVERAGE_NOTE,
    COMPARE_NOTE,
    DISCLAIMER,
    FORMULA_ID,
    VERSION_ID,
)
from evidence_v2.identity import canonical, sha256_text
from evidence_v2.store import ingest_document, select_at_cutoff
from evidence_v2.timebox import bucket_date, parse_aware, window_dates


def ols_slope(values: list[float], day_index: list[int]) -> float | None:
    count = len(values)
    if count < 2 or len(day_index) != count:
        return None
    xs = [float(item) for item in day_index]
    ys = [float(item) for item in values]
    mean_x = sum(xs) / count
    mean_y = sum(ys) / count
    denominator = sum((item - mean_x) ** 2 for item in xs)
    if denominator == 0:
        return None
    numerator = sum((x - mean_x) * (y - mean_y) for x, y in zip(xs, ys))
    return numerator / denominator


def dod_pct(previous: float, current: float) -> float | None:
    if previous is None or current is None or previous <= 0:
        return None
    return (float(current) / float(previous) - 1.0) * 100.0


def momentum_x(day_over_day: float, slope: float) -> float:
    return 0.6 * math.tanh(day_over_day / 50.0) + 0.4 * math.tanh(slope / 8.0)


def pairwise_order_agreement(pairs: list[tuple[float, float]]) -> float | None:
    """Agreement of (v1 rank, v2 score). Higher score should have the smaller rank.

    Returns None when fewer than two comparable points exist. This is not an
    accuracy statistic.
    """
    comparable = [(rank, score) for rank, score in pairs if rank is not None and score is not None]
    if len(comparable) < 2:
        return None
    decided = 0
    concordant = 0
    for index, (rank_a, score_a) in enumerate(comparable):
        for rank_b, score_b in comparable[index + 1:]:
            score_delta = score_a - score_b
            rank_delta = rank_b - rank_a
            if score_delta == 0 or rank_delta == 0:
                continue
            decided += 1
            if (score_delta > 0 and rank_delta > 0) or (score_delta < 0 and rank_delta < 0):
                concordant += 1
    if decided == 0:
        return None
    return concordant / decided


def _primary_metrics() -> list[str]:
    seen = []
    for metric in SKU_PRIMARY_METRIC.values():
        if metric not in seen:
            seen.append(metric)
    return seen


def _matching_row(rows: list[dict], metric: str, day: date) -> dict | None:
    matches = []
    for row in rows:
        if row["platform"] != "X" or row["effective_cadence"] != "daily":
            continue
        if row["entity_kind"] != "category_proxy" or row["metric_key"] != metric:
            continue
        if bucket_date(row.get("observed_start")) != day:
            continue
        matches.append(row)
    if not matches:
        return None
    matches.sort(key=lambda row: (row["collected_at"] or "", row["revision"]))
    return matches[-1]


def _series_decision(selected: list[dict], withheld: list[tuple[dict, str]], metric: str, days: list[date]) -> dict:
    used = []
    reasons = []
    for day in days:
        chosen = _matching_row(selected, metric, day)
        if chosen is None:
            held = [
                (row, reason)
                for row, reason in withheld
                if row["platform"] == "X"
                and row["metric_key"] == metric
                and row["entity_kind"] == "category_proxy"
                and bucket_date(row.get("observed_start")) == day
            ]
            if held:
                reasons.append(f"{day.isoformat()}:{held[-1][1]}")
            else:
                reasons.append(f"{day.isoformat()}:missing_day")
            continue
        if chosen["is_partial"] or chosen["status"] == "partial":
            reasons.append(f"{day.isoformat()}:partial_day")
            continue
        if chosen["value"] is None or chosen["status"] != "observed":
            reasons.append(f"{day.isoformat()}:null_value")
            continue
        used.append(chosen)
    coverage = len(used) / len(days) if days else 0.0
    components = {
        "formula": "0.6*tanh(dod/50)+0.4*tanh(slope/8)",
        "scale": "[-1,1] momentum, not director_v1 and not a probability",
        "neutral_imputation": False,
        "source_coverage_is_not_a_probability": True,
        "window_dates": [day.isoformat() for day in days],
        "values": [row["value"] for row in used],
        "selected_observation_ids": [row["observation_id"] for row in used],
        "reasons": reasons,
    }
    if reasons:
        components["uncertainty"] = "insufficient-evidence"
        return {"score": None, "score_status": "pending", "pending_reason": ";".join(reasons),
                "source_coverage": coverage, "uncertainty": "insufficient-evidence", "components": components}
    values = [float(row["value"]) for row in used]
    indexes = list(range(len(values)))
    change = dod_pct(values[-2], values[-1])
    slope = ols_slope(values, indexes)
    components["dod_pct"] = change
    components["slope_per_day"] = slope
    if change is None:
        components["uncertainty"] = "insufficient-evidence"
        return {"score": None, "score_status": "pending", "pending_reason": "non_positive_baseline",
                "source_coverage": coverage, "uncertainty": "insufficient-evidence", "components": components}
    if slope is None:
        components["uncertainty"] = "insufficient-evidence"
        return {"score": None, "score_status": "pending", "pending_reason": "slope_undefined",
                "source_coverage": coverage, "uncertainty": "insufficient-evidence", "components": components}
    score = momentum_x(change, slope)
    components["momentum_x"] = score
    components["uncertainty"] = "single-source"
    return {"score": score, "score_status": "scored", "pending_reason": None,
            "source_coverage": coverage, "uncertainty": "single-source", "components": components}


def score_manifest(con: sqlite3.Connection, plan_id: str, cutoff: datetime) -> dict:
    if cutoff.tzinfo is None:
        raise ValueError("cutoff must be timezone-aware")
    plan = con.execute("SELECT * FROM evidence_v2_plan WHERE plan_id=?", (plan_id,)).fetchone()
    if plan is None:
        raise ValueError(f"unknown plan {plan_id}")
    selected, withheld = select_at_cutoff(con, plan_id, cutoff)
    selected_ids = sorted(row["observation_id"] for row in selected)
    hashed_inputs = sorted(
        ({"id": row["observation_id"], "provenance": row["provenance_hash"]} for row in selected),
        key=lambda item: item["id"],
    )
    input_hash = sha256_text(canonical({
        "cutoff": cutoff.isoformat(),
        "formula": FORMULA_ID,
        "version": VERSION_ID,
        "observations": hashed_inputs,
    }))
    manifest_id = sha256_text(plan_id + "|" + input_hash)
    existing = con.execute(
        "SELECT manifest_id FROM evidence_v2_manifest WHERE manifest_id=?",
        (manifest_id,),
    ).fetchone()
    if existing:
        return _public_result(con, manifest_id)
    start = date.fromisoformat(plan["window_start"])
    end_exclusive = date.fromisoformat(plan["window_end_exclusive"])
    days = window_dates(start, end_exclusive)
    v1_rows = {
        row["entity_id"]: dict(row)
        for row in con.execute("SELECT * FROM evidence_v2_v1_snapshot WHERE plan_id=?", (plan_id,))
    }
    decisions = {metric: _series_decision(selected, withheld, metric, days) for metric in _primary_metrics()}
    any_pending = any(item["score_status"] != "scored" for item in decisions.values())
    con.execute(
        """INSERT INTO evidence_v2_manifest
           (manifest_id, plan_id, version_id, formula_id, as_of, replay_cutoff,
            input_observation_ids, input_hash, status, disclaimer, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?,?)""",
        (
            manifest_id, plan_id, VERSION_ID, FORMULA_ID, plan["as_of"], cutoff.isoformat(),
            json.dumps(selected_ids), input_hash,
            "partial_pending" if any_pending else "complete",
            DISCLAIMER, datetime.now(timezone.utc).isoformat(),
        ),
    )
    for metric, decision in decisions.items():
        skus = list(METRIC_TO_SKUS[metric])
        representative = min(skus)
        for sku in skus:
            v1 = v1_rows.get(sku, {})
            con.execute(
                """INSERT INTO evidence_v2_shadow_score (
                    manifest_id, entity_id, shared_group_id, score, score_status, pending_reason,
                    source_coverage, coverage_note, uncertainty, independent_group, n_skus_sharing,
                    v1_score, v1_rank, v1_formula, components_json
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    manifest_id, sku, metric, decision["score"], decision["score_status"],
                    decision["pending_reason"], decision["source_coverage"], COVERAGE_NOTE,
                    decision["uncertainty"], 1 if sku == representative else 0, len(skus),
                    v1.get("v1_score"), v1.get("v1_rank"), v1.get("v1_formula"),
                    json.dumps(decision["components"], ensure_ascii=False),
                ),
            )
    compare = _compare_rows(con, manifest_id)
    con.execute(
        """INSERT INTO evidence_v2_shadow_compare
           (manifest_id, n_entities, n_scored, n_pending, n_independent_groups, n_scored_groups,
            descriptive_rank_agreement, note)
           VALUES (?,?,?,?,?,?,?,?)""",
        (
            manifest_id, compare["n_entities"], compare["n_scored"], compare["n_pending"],
            compare["n_independent_groups"], compare["n_scored_groups"],
            compare["descriptive_rank_agreement"], COMPARE_NOTE,
        ),
    )
    con.commit()
    return _public_result(con, manifest_id)


def _compare_rows(con: sqlite3.Connection, manifest_id: str) -> dict:
    rows = [dict(row) for row in con.execute(
        "SELECT * FROM evidence_v2_shadow_score WHERE manifest_id=?",
        (manifest_id,),
    )]
    groups: dict[str, dict] = {}
    for row in rows:
        group = groups.setdefault(row["shared_group_id"], {"status": row["score_status"], "score": row["score"], "ranks": []})
        if row["v1_rank"] is not None:
            group["ranks"].append(row["v1_rank"])
    scored = []
    for group in groups.values():
        if group["status"] == "scored" and group["score"] is not None and group["ranks"]:
            scored.append((min(group["ranks"]), group["score"]))
    return {
        "n_entities": len(rows),
        "n_scored": sum(1 for row in rows if row["score_status"] == "scored"),
        "n_pending": sum(1 for row in rows if row["score_status"] == "pending"),
        "n_independent_groups": len(groups),
        "n_scored_groups": sum(1 for group in groups.values() if group["status"] == "scored"),
        "descriptive_rank_agreement": pairwise_order_agreement(scored),
    }


def _public_result(con: sqlite3.Connection, manifest_id: str) -> dict:
    manifest = dict(con.execute("SELECT * FROM evidence_v2_manifest WHERE manifest_id=?", (manifest_id,)).fetchone())
    compare = dict(con.execute("SELECT * FROM evidence_v2_shadow_compare WHERE manifest_id=?", (manifest_id,)).fetchone())
    return {
        "version_id": VERSION_ID,
        "formula_id": FORMULA_ID,
        "director_v1_untouched": True,
        "accuracy_claim": None,
        "plan_id": manifest["plan_id"],
        "manifest_id": manifest_id,
        "replay_cutoff": manifest["replay_cutoff"],
        "manifest_status": manifest["status"],
        "disclaimer": manifest["disclaimer"],
        "n_entities": compare["n_entities"],
        "n_scored_entities": compare["n_scored"],
        "n_pending_entities": compare["n_pending"],
        "n_independent_groups": compare["n_independent_groups"],
        "n_scored_groups": compare["n_scored_groups"],
        "descriptive_rank_agreement": compare["descriptive_rank_agreement"],
        "comparison_note": compare["note"],
    }


def run_fixture(con: sqlite3.Connection, document: dict, cutoff: str | None = None) -> dict:
    plan_id = ingest_document(con, document)
    cutoff_text = cutoff or document.get("replay_cutoff") or document["as_of"]
    parsed = parse_aware(cutoff_text)
    if parsed is None:
        raise ValueError("replay cutoff must be an aware timestamp")
    result = score_manifest(con, plan_id, parsed)
    result["example_label"] = document.get("example_label")
    return result
