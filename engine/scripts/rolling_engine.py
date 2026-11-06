#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Dual-Track Rolling Forecast engine (Track B Live).

Track A (T0) stays immutable in prediction_*.
Track B recomputes Rolling_* from latest complete day-bucket DoD% + slope_7d
+ fulfill time-decay + external_catalysts.json.

Public-proxy only; never invent GMV; never UPDATE freeze prediction fields.
"""

from __future__ import annotations

import json
import math
import sqlite3
from dataclasses import dataclass, asdict
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Sequence, Tuple

from display_names import (
    APPAREL_SIZE_SENSITIVE,
    BLACK_FRIDAY,
    CATALYST_K,
    FORMULA_VERSION,
    FREEZE_ID,
    METRIC_LABELS,
    METRIC_ORDER,
    METRIC_TO_SKUS,
    SKU_PRIMARY_METRIC,
    zh_name,
)

ROOT = Path("/workspace/dacu-signal")
DB_PATH = ROOT / "db" / "dacu_signals.sqlite"
CATALYSTS_PATH = ROOT / "external_catalysts.json"
SH_TZ = timezone(timedelta(hours=8))


def shanghai_now_iso() -> str:
    return datetime.now(SH_TZ).replace(microsecond=0).isoformat()


def connect(db: Path = DB_PATH) -> sqlite3.Connection:
    con = sqlite3.connect(str(db))
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    return con


def apply_migrate_v4(con: sqlite3.Connection) -> None:
    sql = (ROOT / "sql" / "migrate_v4_rolling.sql").read_text(encoding="utf-8")
    con.executescript(sql)
    con.execute(
        "INSERT OR IGNORE INTO schema_migrations(version) VALUES ('4')"
    )
    con.commit()


def fix_black_friday_anchors(con: sqlite3.Connection) -> int:
    """Correct Black_Friday 2026-11-28 → 2026-11-27 and recompute days_to_anchor."""
    rows = con.execute(
        """
        SELECT a.rowid AS rid, a.run_id, a.anchor_date, r.as_of_date
        FROM calendar_anchors a
        JOIN runs r ON r.run_id = a.run_id
        WHERE a.anchor_name = 'Black_Friday'
        """
    ).fetchall()
    n = 0
    for r in rows:
        as_of = date.fromisoformat(r["as_of_date"])
        bf = date.fromisoformat(BLACK_FRIDAY)
        dto = (bf - as_of).days
        if r["anchor_date"] != BLACK_FRIDAY or r["as_of_date"] and True:
            con.execute(
                """
                UPDATE calendar_anchors
                SET anchor_date = ?, days_to_anchor = ?,
                    note = COALESCE(NULLIF(note, ''), '黑五')
                WHERE rowid = ?
                """,
                (BLACK_FRIDAY, dto, r["rid"]),
            )
            n += 1
    con.commit()
    return n


def clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def pct_change(curr: Optional[float], prev: Optional[float]) -> Optional[float]:
    if curr is None or prev is None or prev == 0:
        return None
    return (curr - prev) / prev * 100.0


def linreg_slope(ys: Sequence[float]) -> Optional[float]:
    """Ordinary least-squares slope vs index 0..n-1."""
    n = len(ys)
    if n < 2:
        return None
    xs = list(range(n))
    mx = sum(xs) / n
    my = sum(ys) / n
    denom = sum((x - mx) ** 2 for x in xs)
    if denom == 0:
        return None
    m = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / denom
    return m


@dataclass
class MetricSnap:
    metric_key: str
    label: str
    signal_date: str
    value: float
    dod_pct: Optional[float]
    slope_7d: Optional[float]
    is_partial: int
    consec_hot_days: int = 0  # DoD>+30% streak ending at this date


@dataclass
class RollingRow:
    sku_cluster: str
    zh_name: str
    t0_rank: int
    t0_urgency: float
    t0_demand: float
    t0_content: float
    t0_fulfill: float
    t0_total: float
    rolling_urgency: float
    rolling_demand: float
    rolling_content: float
    rolling_fulfill: float
    catalyst_adj: float
    rolling_total: float
    rolling_rank: int
    rank_delta: int
    demand_adj: float
    fulfill_adj: float
    primary_metric: str
    dod_pct: Optional[float]
    slope_7d: Optional[float]
    consec_hot_days: int
    action_note: str
    formula_note: str
    predicted_action: str = ""
    multi_platform_demand: float = 0.0
    content_ad_leverage: float = 0.0
    fulfillment_sla: float = 0.0
    margin_return_risk: float = 0.0
    white_label_viability: float = 0.0
    live_total: float = 0.0


def pick_run(
    con: sqlite3.Connection, as_of: str, run_id: Optional[str] = None
) -> sqlite3.Row:
    if run_id:
        row = con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,)).fetchone()
        if not row:
            raise SystemExit(f"run_id 不存在: {run_id}")
        return row
    row = con.execute(
        """
        SELECT * FROM runs
        WHERE as_of_date=?
        ORDER BY CASE run_type WHEN 'scheduled' THEN 0 ELSE 1 END, report_ts DESC
        LIMIT 1
        """,
        (as_of,),
    ).fetchone()
    if not row:
        raise SystemExit(f"as_of={as_of} 无对应 run")
    return row


def load_complete_series(
    con: sqlite3.Connection, run_id: str, metric_key: str
) -> List[Tuple[str, float]]:
    rows = con.execute(
        """
        SELECT signal_date, value
        FROM signals_daily
        WHERE run_id=? AND metric_key=? AND is_partial=0
        ORDER BY signal_date
        """,
        (run_id, metric_key),
    ).fetchall()
    return [(r["signal_date"], float(r["value"])) for r in rows]


def metric_features(
    series: List[Tuple[str, float]], complete_day: str
) -> Tuple[Optional[float], Optional[float], Optional[float], int]:
    """Return (value, dod_pct, slope_7d_recomputed, consec_hot_days) at complete_day."""
    by = {d: v for d, v in series}
    if complete_day not in by:
        return None, None, None, 0
    # previous complete day in series
    dates = [d for d, _ in series if d <= complete_day]
    if not dates:
        return None, None, None, 0
    # ensure complete_day is last considered
    if dates[-1] != complete_day:
        # complete_day missing
        return None, None, None, 0
    val = by[complete_day]
    prev = by.get((date.fromisoformat(complete_day) - timedelta(days=1)).isoformat())
    dod = pct_change(val, prev)
    window_dates = [d for d in dates if d >= (date.fromisoformat(complete_day)-timedelta(days=6)).isoformat()]
    window = [by[d] for d in window_dates]
    xs=[(date.fromisoformat(d)-date.fromisoformat(window_dates[0])).days for d in window_dates]
    mx=sum(xs)/len(xs); my=sum(window)/len(window)
    denom=sum((x-mx)**2 for x in xs)
    slope=sum((x-mx)*(y-my) for x,y in zip(xs,window))/denom if denom else None
    # consecutive DoD > +30% ending at complete_day
    consec = 0
    for i in range(len(dates) - 1, 0, -1):
        if (date.fromisoformat(dates[i])-date.fromisoformat(dates[i-1])).days != 1:
            break
        cur_v = by[dates[i]]
        prev_v = by[dates[i - 1]]
        dlt = pct_change(cur_v, prev_v)
        if dlt is not None and dlt > 30.0 and abs(cur_v - prev_v) >= 5:
            consec += 1
        else:
            break
    return val, dod, slope, consec


def build_yesterday_complete_table(
    con: sqlite3.Connection, run_id: str, as_of: str
) -> Tuple[List[Dict[str, Any]], str]:
    as_of_d = date.fromisoformat(as_of)
    yday = (as_of_d - timedelta(days=1)).isoformat()
    out: List[Dict[str, Any]] = []
    for mk in METRIC_ORDER:
        series = load_complete_series(con, run_id, mk)
        # Prefer yday; if missing, use latest complete <= as_of
        complete_day = yday
        dates = [d for d, _ in series if d < as_of]
        if yday not in {d for d, _ in series} and dates:
            complete_day = dates[-1]
        val, dod, slope, consec = metric_features(series, complete_day)
        if val is None:
            continue
        out.append(
            {
                "metric_key": mk,
                "label": METRIC_LABELS.get(mk, mk),
                "window_n": sum((date.fromisoformat(complete_day)-timedelta(days=6)).isoformat() <= d <= complete_day for d,_ in series),
                "value": val,
                "dod_pct": dod,
                "slope_7d": None if slope is None else round(slope, 4),
                "is_partial": 0,
                "signal_date": complete_day,
                "consec_hot_days": consec,
            }
        )
    complete_date = out[0]["signal_date"] if out else yday
    return out, complete_date


def build_partial_table(
    con: sqlite3.Connection, run_id: str, as_of: str
) -> List[Dict[str, Any]]:
    rows = con.execute(
        """
        SELECT metric_key, value, slope_7d, is_partial, signal_date
        FROM signals_daily
        WHERE run_id=? AND signal_date=?
        """,
        (run_id, as_of),
    ).fetchall()
    by = {r["metric_key"]: r for r in rows}
    out = []
    for mk in METRIC_ORDER:
        r = by.get(mk)
        if not r:
            continue
        out.append(
            {
                "metric_key": mk,
                "label": METRIC_LABELS.get(mk, mk),
                "value": r["value"],
                "slope_7d": r["slope_7d"],
                "is_partial": r["is_partial"],
                "signal_date": as_of,
            }
        )
    return out


def load_catalysts(
    path: Path = CATALYSTS_PATH, as_of: Optional[str] = None
) -> Dict[str, Any]:
    if not path.exists():
        return {
            "schema_version": 1,
            "catalysts": [],
            "as_of_date": as_of,
            "updated_at": None,
        }
    data = json.loads(path.read_text(encoding="utf-8"))
    return data


def catalyst_adj_for_sku(
    sku: str, catalysts: Dict[str, Any]
) -> Tuple[float, str]:
    """Sum matching catalyst weights * K, clamped to [-2, +2]."""
    items = catalysts.get("catalysts") or []
    matched = []
    total_w = 0.0
    for c in items:
        w = clamp(float(c.get("weight") or 0.0), -1.0, 1.0)
        if abs(w) < 1e-12:
            continue
        key = (c.get("sku_cluster_or_category") or "").strip()
        src = c.get("source") or "?"
        if not key or key in ("*", "all", "ALL"):
            total_w += w
            matched.append(f"{src}:{key or '*'}:{w:+.2f}")
            continue
        # match sku_cluster substring or category-ish tokens
        sku_l = sku.lower()
        key_l = key.lower()
        if key_l in sku_l or sku_l in key_l:
            total_w += w
            matched.append(f"{src}:{key}:{w:+.2f}")
            continue
        # category aliases
        aliases = {
            "jewelry": "jewelry_gift_posts",
            "珠宝": "jewelry_gift_posts",
            "nail": "nail_makeup_gift_posts",
            "美甲": "nail_makeup_gift_posts",
            "美妆": "nail_makeup_gift_posts",
            "squishy": "squishy_plush_gift_posts",
            "毛绒": "squishy_plush_gift_posts",
            "fashion": "fashion_gift_posts",
            "apparel": "fashion_gift_posts",
            "pjs": "matching family Christmas PJs flannel",
            "knit": "cream/oatmeal oversized chunky knit",
            "毛衣": "cream/oatmeal oversized chunky knit",
            "tts": "tts_us_gift_holiday_posts",
        }
        hit = False
        for alias, target in aliases.items():
            if alias in key_l:
                if target in METRIC_TO_SKUS:
                    if sku in METRIC_TO_SKUS[target]:
                        hit = True
                elif target == sku:
                    hit = True
                if hit:
                    break
        if hit:
            total_w += w
            matched.append(f"{src}:{key}:{w:+.2f}")
    adj = clamp(total_w * CATALYST_K, -2.0, 2.0)
    note = "; ".join(matched) if matched else "none"
    return adj, note


def demand_float(
    dod: Optional[float],
    slope: Optional[float],
    consec_hot: int,
    primary: str,
    metric_map: Dict[str, Dict[str, Any]],
) -> Tuple[float, str]:
    """Compute demand adjustment from primary + TTS channel rules."""
    bits: List[str] = []
    adj = 0.0

    def apply_dod(d: Optional[float], tag: str, scale: float = 1.0) -> None:
        nonlocal adj
        if d is None:
            return
        # value delta gate approximated via |DoD| magnitude; callers already used |Δ|>=5/8/10 in consec
        if d >= 80.0:
            delta = 1.0 * scale
        elif d >= 50.0:
            delta = 0.75 * scale
        elif d >= 30.0:
            delta = 0.5 * scale
        elif d <= -50.0:
            delta = -1.0 * scale
        elif d <= -30.0:
            delta = -0.5 * scale
        else:
            delta = 0.0
        if delta:
            adj += delta
            bits.append(f"{tag}_DoD{d:+.1f}%→{delta:+.2f}")

    apply_dod(dod, primary)

    if slope is not None:
        if slope >= 8.0:
            adj += 0.5
            bits.append(f"slope{slope:+.2f}→+0.50")
        elif slope >= 5.0:
            adj += 0.35
            bits.append(f"slope{slope:+.2f}→+0.35")
        elif slope < -2.0:
            adj -= 0.5
            bits.append(f"slope{slope:+.2f}→-0.50")
        elif slope < 0:
            adj -= 0.25
            bits.append(f"slope{slope:+.2f}→-0.25")

    # Consecutive hot days on primary (e.g. TTS-style multi-day surge)
    if consec_hot >= 4:
        adj += 1.0
        bits.append(f"consec_hot={consec_hot}→+1.00")
    elif consec_hot >= 3:
        adj += 0.75
        bits.append(f"consec_hot={consec_hot}→+0.75")
    elif consec_hot >= 2 and primary in (
        "tts_us_gift_holiday_posts",
        "squishy_plush_gift_posts",
    ):
        adj += 0.35
        bits.append(f"consec_hot={consec_hot}→+0.35")

    # Extra TTS channel bonus for TTS-sensitive SKUs
    tts = metric_map.get("tts_us_gift_holiday_posts")
    if tts and primary != "tts_us_gift_holiday_posts":
        # only if this SKU is in TTS map
        pass  # applied at SKU level below via separate call

    return adj, (", ".join(bits) if bits else "demand flat")


def fulfill_time_decay(sku: str, days_to_bf: int) -> Tuple[float, str]:
    if sku not in APPAREL_SIZE_SENSITIVE:
        return 0.0, "fulfill_decay=0 (non-apparel/low-return)"
    if days_to_bf <= 7:
        return -1.5, f"apparel decay days_to_BF={days_to_bf}≤7 → -1.5"
    if days_to_bf <= 10:
        return -1.0, f"apparel decay days_to_BF={days_to_bf}≤10 → -1.0"
    if days_to_bf <= 14:
        return -0.5, f"apparel decay days_to_BF={days_to_bf}≤14 → -0.5"
    if days_to_bf <= 21:
        return -0.25, f"apparel decay days_to_BF={days_to_bf}≤21 → -0.25"
    return 0.0, f"apparel decay days_to_BF={days_to_bf}>21 → 0"


def urgency_nudge(
    days_to_tts: Optional[int], dod: Optional[float], days_to_bf: int
) -> Tuple[float, str]:
    adj = 0.0
    bits = []
    if days_to_tts is not None and days_to_tts <= 5 and dod is not None and dod >= 20:
        adj += 0.25
        bits.append(f"near_TTS({days_to_tts}d)+DoD≥20 → +0.25")
    if days_to_bf <= 14 and dod is not None and dod >= 50:
        adj += 0.25
        bits.append("near_BF+surge → +0.25")
    return adj, (", ".join(bits) if bits else "urgency flat")


def load_t0_items(con: sqlite3.Connection) -> List[sqlite3.Row]:
    return con.execute(
        """
        SELECT rank_in_list, sku_cluster, predicted_action,
               predicted_urgency, predicted_demand, predicted_content,
               predicted_fulfill, predicted_total, snapshot_json, price_band
        FROM prediction_items
        WHERE freeze_id=?
        ORDER BY rank_in_list
        """,
        (FREEZE_ID,),
    ).fetchall()


def days_to_anchor(con: sqlite3.Connection, run_id: str, name: str) -> Optional[int]:
    row = con.execute(
        """
        SELECT days_to_anchor, anchor_date FROM calendar_anchors
        WHERE run_id=? AND anchor_name=?
        """,
        (run_id, name),
    ).fetchone()
    if not row:
        return None
    return int(row["days_to_anchor"]) if row["days_to_anchor"] is not None else None


def compute_rolling_for_as_of(con, as_of, run_id=None, catalysts_path=CATALYSTS_PATH, use_catalysts=False):
    from director_model import compute
    return compute(con, as_of, run_id, catalysts_path, use_catalysts)


def persist_rolling(
    con: sqlite3.Connection,
    rows: List[RollingRow],
    meta: Dict[str, Any],
) -> str:
    """Idempotent write into rolling_runs / rolling_sku_scoring."""
    from director_schema import migrate
    migrate(con)
    as_of = meta["as_of_date"]
    rolling_run_id = f"rolling_{as_of}"
    con.execute("DELETE FROM rolling_sku_scoring WHERE run_id=?", (rolling_run_id,))
    con.execute("DELETE FROM rolling_runs WHERE run_id=?", (rolling_run_id,))
    con.execute(
        """
        INSERT INTO rolling_runs(
          run_id, as_of_date, source_run_id, freeze_id, complete_day,
          black_friday, days_to_bf, catalysts_path, catalysts_as_of,
          formula_version, note
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?)
        """,
        (
            rolling_run_id,
            as_of,
            meta["source_run_id"],
            meta["freeze_id"],
            meta["complete_day"],
            meta["black_friday"],
            meta["days_to_bf"],
            meta["catalysts_path"],
            meta.get("catalysts_as_of"),
            meta["formula_version"],
            "Dual-Track Live rolling; T0 untouched",
        ),
    )
    for r in rows:
        con.execute(
            """
            INSERT INTO rolling_sku_scoring(
              run_id, as_of_date, sku_cluster, zh_name,
              t0_rank, t0_urgency, t0_demand, t0_content, t0_fulfill, t0_total,
              rolling_urgency, rolling_demand, rolling_content, rolling_fulfill,
              catalyst_adj, rolling_total, rolling_rank, rank_delta,
              demand_adj, fulfill_adj, primary_metric, dod_pct, slope_7d,
              consec_hot_days, action_note, formula_note
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                rolling_run_id,
                as_of,
                r.sku_cluster,
                r.zh_name,
                r.t0_rank,
                r.t0_urgency,
                r.t0_demand,
                r.t0_content,
                r.t0_fulfill,
                r.t0_total,
                r.rolling_urgency,
                r.rolling_demand,
                r.rolling_content,
                r.rolling_fulfill,
                r.catalyst_adj,
                r.rolling_total,
                r.rolling_rank,
                r.rank_delta,
                r.demand_adj,
                r.fulfill_adj,
                r.primary_metric,
                r.dod_pct,
                r.slope_7d,
                r.consec_hot_days,
                r.action_note,
                r.formula_note,
            ),
        )
    for r in rows:
        con.execute("""UPDATE rolling_sku_scoring SET multi_platform_demand=?,content_ad_leverage=?,fulfillment_sla=?,margin_return_risk=?,white_label_viability=?,live_total=? WHERE run_id=? AND sku_cluster=?""",(r.multi_platform_demand,r.content_ad_leverage,r.fulfillment_sla,r.margin_return_risk,r.white_label_viability,r.live_total,rolling_run_id,r.sku_cluster))
    con.commit()
    return rolling_run_id


def load_persisted_rolling(
    con: sqlite3.Connection, as_of: str
) -> List[Dict[str, Any]]:
    rid = f"rolling_{as_of}"
    rows = con.execute(
        """
        SELECT * FROM rolling_sku_scoring
        WHERE run_id=?
        ORDER BY rolling_rank
        """,
        (rid,),
    ).fetchall()
    return [dict(r) for r in rows]


def formula_readme_block():
    from director_model import FORMULA_DOC
    return FORMULA_DOC


if __name__ == "__main__":
    import pprint

    con = connect()
    apply_migrate_v4(con)
    n = fix_black_friday_anchors(con)
    print(f"[bf] fixed anchors rows touched≈{n}, date={BLACK_FRIDAY}")
    rows, meta, complete, partial, rid = compute_rolling_for_as_of(con, "2026-11-06")
    rid2 = persist_rolling(con, rows, meta)
    print("meta", {k: meta[k] for k in meta if k != "run"})
    print("complete", complete)
    for r in rows:
        print(
            f"#{r.rolling_rank} Δ{r.rank_delta:+d} {r.zh_name} "
            f"T0={r.t0_total}/{r.t0_rank} → R={r.rolling_total} "
            f"dem_adj={r.demand_adj} ful_adj={r.fulfill_adj}"
        )
    con.close()
