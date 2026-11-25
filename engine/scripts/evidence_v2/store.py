"""Append-only SQL evidence ledger. Replay picks the latest revision usable at a cutoff."""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from evidence_v2 import EXAMPLE_LABEL, LAST30DAYS_REVIEW, VERSION_ID, FORMULA_ID
from evidence_v2.adapters import ADAPTERS, adapter_for
from evidence_v2.identity import canonical, normalize_text, sha256_text
from evidence_v2.timebox import bucket_bounds, classify_timestamps, complete_utc_window, parse_aware, pit_decision

SQL_PATH = Path(__file__).resolve().parents[2] / "sql" / "migrate_v7_evidence_research.sql"


def connect(path: str) -> sqlite3.Connection:
    con = sqlite3.connect(path)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con


def migrate(con: sqlite3.Connection) -> None:
    con.executescript(SQL_PATH.read_text())
    for adapter in ADAPTERS:
        con.execute(
            """INSERT OR IGNORE INTO evidence_v2_adapter
               (adapter_id, platform, cadence, official_daily, availability, reason, version_id)
               VALUES (?,?,?,?,?,?,?)""",
            adapter.as_row(),
        )
    con.commit()


def load_fixture(path: str) -> dict:
    document = json.loads(Path(path).read_text())
    label = document.get("example_label")
    if label != EXAMPLE_LABEL:
        raise ValueError(
            f"example fixture must set example_label={EXAMPLE_LABEL}; refused to ingest unlabeled data"
        )
    return document


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _expand(document: dict) -> list[dict]:
    rows: list[dict] = []
    for series in document.get("series", []):
        for day in series["days"]:
            start, end = bucket_bounds(day["date"])
            row = {
                "platform": series["platform"],
                "metric_key": series["metric_key"],
                "entity_kind": series["entity_kind"],
                "entity_id": series.get("entity_id") or series["metric_key"],
                "unit": series.get("unit"),
                "requested_cadence": series.get("cadence"),
                "status": day.get("status", "observed"),
                "value": day["value"] if "value" in day else None,
                "observed_start": start,
                "observed_end": end,
                "published_at": day.get("published_at"),
                "collected_at": day.get("collected_at"),
                "available_at": day.get("available_at"),
                "source_url": day.get("source_url") or series.get("source_url"),
                "source_note": day.get("source_note") or series.get("source_note") or "",
                "text": day.get("text"),
                "is_partial": day.get("is_partial", 0),
                "engagement": day["engagement"] if "engagement" in day else None,
            }
            rows.append(row)
    rows.extend(document.get("extra_observations", []))
    return rows


def _normalize(raw: dict, example_label: str | None) -> dict:
    platform = raw["platform"]
    adapter = adapter_for(platform)
    requested = raw.get("requested_cadence") or raw.get("cadence") or (adapter.cadence if adapter else "unavailable")
    effective = adapter.cadence if adapter else "unavailable"
    start = raw.get("observed_start")
    end = raw.get("observed_end")
    if raw.get("date") and not start:
        start, end = bucket_bounds(raw["date"])
    collected = raw.get("collected_at")
    available = raw.get("available_at")
    published = raw.get("published_at")
    confidence = classify_timestamps(start, end, collected, available)
    status = raw.get("status") or "missing"
    is_partial = 1 if raw.get("is_partial") in (1, True, "1") or status == "partial" else 0
    entity_kind = raw["entity_kind"]
    metric = raw["metric_key"]
    entity_id = raw.get("entity_id") or metric
    text_norm = normalize_text(raw.get("text"))
    shared = metric if entity_kind == "category_proxy" else entity_id
    identity_parts = [platform, metric, entity_kind, entity_id, effective, start or "", end or "", raw.get("unit") or ""]
    if entity_kind == "item":
        identity_parts.append(sha256_text(text_norm)[:16])
    identity_key = "|".join(identity_parts)
    if "engagement" in raw and raw.get("engagement") is not None:
        engagement_json = canonical(raw["engagement"])
    else:
        engagement_json = None
    value = raw["value"] if "value" in raw else None
    provenance = sha256_text(canonical({
        "identity_key": identity_key,
        "value": value,
        "status": status,
        "is_partial": is_partial,
        "observed_start": start,
        "observed_end": end,
        "published_at": published,
        "collected_at": collected,
        "available_at": available,
        "source_url": raw.get("source_url"),
        "text_norm": text_norm,
        "engagement_json": engagement_json,
        "unit": raw.get("unit"),
    }))
    return {
        "identity_key": identity_key,
        "platform": platform,
        "metric_key": metric,
        "entity_kind": entity_kind,
        "entity_id": entity_id,
        "shared_group_id": shared,
        "value": value,
        "unit": raw.get("unit"),
        "status": status,
        "requested_cadence": requested,
        "effective_cadence": effective,
        "observed_start": start,
        "observed_end": end,
        "published_at": published,
        "collected_at": collected,
        "available_at": available,
        "date_confidence": confidence,
        "source_url": raw.get("source_url"),
        "source_note": raw.get("source_note") or "",
        "text_norm": text_norm or None,
        "engagement_json": engagement_json,
        "is_partial": is_partial,
        "provenance_hash": provenance,
        "example_label": example_label,
    }


def _insert_observation(con: sqlite3.Connection, plan_id: str, row: dict) -> str:
    found = con.execute(
        "SELECT observation_id FROM evidence_v2_observation WHERE identity_key=? AND provenance_hash=?",
        (row["identity_key"], row["provenance_hash"]),
    ).fetchone()
    if found:
        return found["observation_id"]
    revision = con.execute(
        "SELECT COALESCE(MAX(revision), 0) + 1 FROM evidence_v2_observation WHERE identity_key=?",
        (row["identity_key"],),
    ).fetchone()[0]
    observation_id = sha256_text(row["identity_key"] + "|" + row["provenance_hash"])
    con.execute(
        """INSERT INTO evidence_v2_observation (
            observation_id, plan_id, identity_key, revision, platform, metric_key, entity_kind,
            entity_id, shared_group_id, value, unit, status, requested_cadence, effective_cadence,
            observed_start, observed_end, published_at, collected_at, available_at, date_confidence,
            source_url, source_note, text_norm, engagement_json, is_partial, provenance_hash,
            example_label, inserted_at
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
        (
            observation_id, plan_id, row["identity_key"], revision, row["platform"], row["metric_key"],
            row["entity_kind"], row["entity_id"], row["shared_group_id"], row["value"], row["unit"],
            row["status"], row["requested_cadence"], row["effective_cadence"], row["observed_start"],
            row["observed_end"], row["published_at"], row["collected_at"], row["available_at"],
            row["date_confidence"], row["source_url"], row["source_note"], row["text_norm"],
            row["engagement_json"], row["is_partial"], row["provenance_hash"], row["example_label"], _now(),
        ),
    )
    return observation_id


def _record_conflicts(con: sqlite3.Connection, plan_id: str) -> None:
    rows = [dict(row) for row in con.execute(
        "SELECT * FROM evidence_v2_observation WHERE plan_id=? ORDER BY identity_key, revision",
        (plan_id,),
    )]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["identity_key"], []).append(row)
    for identity_key, group in grouped.items():
        for earlier, later in zip(group, group[1:]):
            reasons = []
            if earlier["value"] != later["value"]:
                reasons.append("value_disagreement")
            if earlier["status"] != later["status"]:
                reasons.append("status_disagreement")
            if not reasons:
                continue
            reason = "+".join(reasons)
            conflict_id = sha256_text(earlier["observation_id"] + "|" + later["observation_id"] + "|" + reason)
            con.execute(
                """INSERT OR IGNORE INTO evidence_v2_conflict
                   (conflict_id, plan_id, identity_key, earlier_observation_id, later_observation_id, reason)
                   VALUES (?,?,?,?,?,?)""",
                (conflict_id, plan_id, identity_key, earlier["observation_id"], later["observation_id"], reason),
            )


def _link_near_duplicates(con: sqlite3.Connection, plan_id: str) -> None:
    from evidence_v2.identity import hybrid_similarity

    items = [dict(row) for row in con.execute(
        """SELECT * FROM evidence_v2_observation
           WHERE plan_id=? AND entity_kind='item' AND text_norm IS NOT NULL
           ORDER BY observation_id""",
        (plan_id,),
    )]
    for index, left in enumerate(items):
        for right in items[index + 1:]:
            if left["identity_key"] == right["identity_key"]:
                continue
            similarity = hybrid_similarity(left["text_norm"], right["text_norm"])
            if similarity < 0.7:
                continue
            link_id = sha256_text(plan_id + "|" + left["observation_id"] + "|" + right["observation_id"])
            con.execute(
                """INSERT OR IGNORE INTO evidence_v2_dedupe_link
                   (link_id, plan_id, left_observation_id, right_observation_id, method, similarity, action, note)
                   VALUES (?,?,?,?,?,?,?,?)""",
                (
                    link_id, plan_id, left["observation_id"], right["observation_id"],
                    "text_jaccard", similarity, "cross_post_kept_both",
                    "近重复只记录链接，不合并数值，也不把两条计成两个独立验证。",
                ),
            )


def ensure_plan(con: sqlite3.Connection, document: dict) -> str:
    as_of = parse_aware(document["as_of"])
    if as_of is None:
        raise ValueError("as_of must be an aware timestamp")
    lookback = int(document.get("lookback_days") or 7)
    start, end_exclusive = complete_utc_window(as_of, lookback)
    label = document.get("example_label")
    plan_id = sha256_text(canonical({
        "version": VERSION_ID,
        "formula": FORMULA_ID,
        "as_of": as_of.isoformat(),
        "window_start": start.isoformat(),
        "window_end_exclusive": end_exclusive.isoformat(),
        "lookback_days": lookback,
        "example_label": label,
    }))
    con.execute(
        """INSERT OR IGNORE INTO evidence_v2_plan
           (plan_id, version_id, formula_id, as_of, window_start, window_end_exclusive,
            lookback_days, example_label, review_commit, created_at)
           VALUES (?,?,?,?,?,?,?,?,?,?)""",
        (
            plan_id, VERSION_ID, FORMULA_ID, as_of.isoformat(), start.isoformat(),
            end_exclusive.isoformat(), lookback, label, LAST30DAYS_REVIEW["commit"], _now(),
        ),
    )
    for adapter in ADAPTERS:
        con.execute(
            """INSERT OR IGNORE INTO evidence_v2_plan_adapter
               (plan_id, adapter_id, included_in_daily_score, reason)
               VALUES (?,?,?,?)""",
            (
                plan_id,
                adapter.adapter_id,
                1 if adapter.official_daily and adapter.availability == "available" else 0,
                adapter.reason,
            ),
        )
    for item in document.get("v1_readonly", []):
        formula = item.get("v1_formula") or "director_v1"
        if formula != "director_v1":
            raise ValueError("v1 snapshot only accepts director_v1")
        con.execute(
            """INSERT OR IGNORE INTO evidence_v2_v1_snapshot
               (plan_id, entity_id, v1_score, v1_rank, v1_formula, note)
               VALUES (?,?,?,?,?,?)""",
            (
                plan_id, item["entity_id"], item.get("v1_score"), item.get("v1_rank"), formula,
                item.get("note") or "readonly layout copy; not a new freeze",
            ),
        )
    return plan_id


def ingest_document(con: sqlite3.Connection, document: dict) -> str:
    plan_id = ensure_plan(con, document)
    label = document.get("example_label")
    for raw in _expand(document):
        _insert_observation(con, plan_id, _normalize(raw, label))
    _record_conflicts(con, plan_id)
    _link_near_duplicates(con, plan_id)
    con.commit()
    return plan_id


def select_at_cutoff(con: sqlite3.Connection, plan_id: str, cutoff: datetime) -> tuple[list[dict], list[tuple[dict, str]]]:
    rows = [dict(row) for row in con.execute(
        "SELECT * FROM evidence_v2_observation WHERE plan_id=? ORDER BY identity_key, revision",
        (plan_id,),
    )]
    grouped: dict[str, list[dict]] = {}
    for row in rows:
        grouped.setdefault(row["identity_key"], []).append(row)
    selected: list[dict] = []
    withheld: list[tuple[dict, str]] = []
    for group in grouped.values():
        visible = []
        for row in group:
            ok, reason = pit_decision(row, cutoff)
            if ok:
                visible.append(row)
            else:
                withheld.append((row, reason))
        if not visible:
            continue
        visible.sort(key=lambda row: (row["collected_at"] or "", row["revision"]))
        selected.append(visible[-1])
    return selected, withheld
