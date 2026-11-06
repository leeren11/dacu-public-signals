#!/usr/bin/env python3
"""Director-readable walk-forward stamp.

Public X post counts and stored platform_signals only. Missing days stay null.
Growth is the eval-window daily mean versus the pre-freeze 7-day daily mean.
Shape labels describe that path. They are not accuracy percentages, and this
module does not write action_hit or timing_hit.
"""
import json
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from display_names import METRIC_LABELS, zh_name

CLIMB_PCT = 10.0
FADE_PCT = -10.0
LONG_DAYS = 5
FALSE_HEAT_MAX_RANK = 5
T0_FREEZE_ID = "T0_2026-11-02_top9"

PROXY = (
    "Complete non-partial X UTC post counts, plus platform_signals rows that "
    "were actually stored for the eval window. Growth = eval daily mean / "
    "pre-freeze 7-day daily mean - 1. Pending means a missing day or a "
    "non-positive baseline. Not GMV, not orders, not an accuracy percentage."
)
METHOD = {
    "growth": PROXY,
    "climb_threshold_pct": CLIMB_PCT,
    "fade_threshold_pct": FADE_PCT,
    "long_window_days": LONG_DAYS,
    "false_heat": (
        f"eval days>={LONG_DAYS}, predicted_rank<={FALSE_HEAT_MAX_RANK}, "
        "shape in flat/fade/spike_fade"
    ),
    "spike_fade": "eval days>=6, first-half index>=1.20, second-half index<=1.05 and at least 0.10 below the first half",
    "late_lift": "eval days>=6, first-half index<=1.05, second-half index>=1.15",
    "spearman": "correlation of predicted rank vs growth on the valid subset; null if n<3",
    "hits": "action_hit and timing_hit are not written by this export",
}
SHAPE_ZH = {
    "climb": "爬坡",
    "late_lift": "后段抬升",
    "flat": "走平",
    "fade": "走弱",
    "spike_fade": "脉冲回落",
    "incomplete": "日桶未齐",
    "zero_baseline": "基线无效",
}
BUCKET_HEADINGS = (
    ("aligned", "### 爬坡兑现"),
    ("aligned_hint", "### 初步同向"),
    ("hint_weak", "### 短窗未爬坡"),
    ("false_heat", "### 伪热嫌疑"),
    ("fade", "### 声量走弱"),
    ("flat", "### 声量走平"),
    ("pending", "### 未能对照（pending）"),
)


def now_shanghai():
    return datetime.now(ZoneInfo("Asia/Shanghai")).replace(microsecond=0).isoformat()


def rnum(v, digits):
    if v is None:
        return None
    return round(float(v), digits)


def cell(v):
    if v is None or v == "":
        return "—"
    return str(v).replace("|", "/").replace("\n", " ")


def fmt_growth(v):
    if v is None:
        return "—"
    return f"{float(v):+.1f}%"


def fmt_num(v, digits=1):
    if v is None:
        return "—"
    return f"{float(v):.{digits}f}"


def fmt_count(v):
    if v is None:
        return "—"
    fv = float(v)
    if abs(fv - round(fv)) < 1e-6:
        return str(int(round(fv)))
    return f"{fv:.2f}"


def md_table(headers, rows):
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append("| " + " | ".join(cell(c) for c in row) + " |")
    return "\n".join(lines)


def endpoint_growth(baseline_values, eval_values):
    """Window growth used by evaluate(). Incomplete windows and non-positive baselines return no growth.

    Returns (actual_sum, growth_pct). actual_sum is None when either window has a gap.
    """
    if not baseline_values or not eval_values:
        return None, None
    if any(v is None for v in baseline_values) or any(v is None for v in eval_values):
        return None, None
    actual = float(sum(eval_values))
    bmean = float(sum(baseline_values)) / len(baseline_values)
    if bmean <= 0:
        return actual, None
    growth = (actual / len(eval_values) / bmean - 1.0) * 100.0
    return actual, growth


def _curve(baseline_values, eval_values):
    def one(v):
        if v is None:
            return "—"
        return fmt_count(v)

    left = ", ".join(one(v) for v in baseline_values)
    right = ", ".join(one(v) for v in eval_values)
    return f"{left} → {right}"


def build_climb(baseline_days, baseline_values, eval_days, eval_values):
    if len(baseline_days) != len(baseline_values) or len(eval_days) != len(eval_values):
        raise ValueError("climb days and values must align")
    actual, growth = endpoint_growth(baseline_values, eval_values)
    base_complete = bool(baseline_values) and all(v is not None for v in baseline_values)
    eval_complete = bool(eval_values) and all(v is not None for v in eval_values)
    bmean = sum(baseline_values) / len(baseline_values) if base_complete else None
    emean = sum(eval_values) / len(eval_values) if eval_complete else None
    index_base = bmean if bmean is not None and bmean > 0 else None
    series = []
    prev_day = None
    prev_value = None
    for phase, days, values in (
        ("baseline", baseline_days, baseline_values),
        ("eval", eval_days, eval_values),
    ):
        for day, value in zip(days, values):
            adjacent = False
            if prev_day:
                adjacent = (datetime.fromisoformat(prev_day) + timedelta(days=1)).date().isoformat() == day
            dod = None
            if value is not None and prev_value is not None and adjacent and prev_value > 0:
                dod = (value - prev_value) / prev_value * 100.0
            idx = value / index_base if value is not None and index_base else None
            series.append(
                {
                    "date": day,
                    "phase": phase,
                    "value": None if value is None else rnum(value, 4),
                    "index_vs_baseline": None if idx is None else rnum(idx, 4),
                    "dod_pct": None if dod is None else rnum(dod, 4),
                    "status": "observed" if value is not None else "pending",
                }
            )
            prev_day = day
            prev_value = value if value is not None else None
    half = None
    first_index = second_index = None
    if eval_complete and len(eval_values) >= 6 and index_base:
        cut = len(eval_values) // 2
        first_index = (sum(eval_values[:cut]) / cut) / index_base
        second_index = (sum(eval_values[cut:]) / (len(eval_values) - cut)) / index_base
        half = {
            "cut": cut,
            "first_index": rnum(first_index, 4),
            "second_index": rnum(second_index, 4),
        }
    if not base_complete or not eval_complete:
        shape = "incomplete"
    elif index_base is None:
        shape = "zero_baseline"
    elif (
        first_index is not None
        and first_index >= 1.20
        and second_index <= 1.05
        and second_index < first_index - 0.10
    ):
        shape = "spike_fade"
    elif first_index is not None and first_index <= 1.05 and second_index >= 1.15:
        shape = "late_lift"
    elif growth is not None and growth >= CLIMB_PCT:
        shape = "climb"
    elif growth is not None and growth <= FADE_PCT:
        shape = "fade"
    else:
        shape = "flat"
    note = _shape_note(shape, growth, first_index, second_index)
    return {
        "baseline_start": baseline_days[0] if baseline_days else None,
        "baseline_end": baseline_days[-1] if baseline_days else None,
        "eval_start": eval_days[0] if eval_days else None,
        "eval_end": eval_days[-1] if eval_days else None,
        "baseline_days": len(baseline_days),
        "eval_days": len(eval_days),
        "baseline_observed": sum(v is not None for v in baseline_values),
        "eval_observed": sum(v is not None for v in eval_values),
        "baseline_mean": None if bmean is None else rnum(bmean, 4),
        "eval_mean": None if emean is None else rnum(emean, 4),
        "actual_sum": None if actual is None else rnum(actual, 4),
        "growth_pct": None if growth is None else rnum(growth, 4),
        "shape": shape,
        "shape_zh": SHAPE_ZH[shape],
        "shape_note": note,
        "half": half,
        "curve": _curve(baseline_values, eval_values),
        "series": series,
    }


def _shape_note(shape, growth, first_index, second_index):
    g = "相对增长无法计算" if growth is None else f"相对增长 {growth:+.1f}%"
    if shape == "spike_fade":
        return (
            f"{g}。前半段指数 {first_index:.2f}，后半段 {second_index:.2f}。"
            "前段冲高、后段回到基线附近，窗口均值不能当成持续爬坡。"
        )
    if shape == "late_lift":
        return (
            f"{g}。前半段指数 {first_index:.2f}，后半段 {second_index:.2f}。"
            "抬升出现在评估窗后段。"
        )
    if shape == "climb":
        return f"{g}。评估窗日均高于冻结前 7 日日均，路径不是冲高回落。"
    if shape == "fade":
        return f"{g}。评估窗日均低于基线 10% 以上。"
    if shape == "flat":
        return f"{g}。变化落在 ±10% 以内。"
    if shape == "zero_baseline":
        return "基线日均≤0，不能算相对增长。已有的帖量仍列出，不补缺失日。"
    return "基线或评估窗有缺失日。缺失保持 pending，不写成 0。"


def action_family(action, t0_reference):
    text = (action or "").strip()
    note = ""
    used = text
    if text == "Live hard freeze":
        ref = (t0_reference or {}).get("predicted_action")
        if ref:
            used = ref
            note = (
                f"本行 predicted_action 是 Live hard freeze。"
                f"回看对照采用 T0 原动作「{ref}」。两列都留在预测情况里。"
            )
        else:
            note = "本行 predicted_action 是 Live hard freeze，没有找到同 SKU 的 T0 原动作。"
    if "轻测" in used:
        family = "light"
    elif "内容" in used and "测款" not in used:
        family = "content"
    elif "测款" in used or "预热" in used:
        family = "test"
    elif "观望" in used:
        family = "watch"
    else:
        family = "other"
    return family, used, note


def review_bucket(shape, eval_days, predicted_rank):
    if shape in ("incomplete", "zero_baseline"):
        return "pending"
    long = eval_days >= LONG_DAYS
    hot = predicted_rank is not None and predicted_rank <= FALSE_HEAT_MAX_RANK
    if shape in ("climb", "late_lift"):
        return "aligned" if long else "aligned_hint"
    if shape in ("flat", "fade", "spike_fade"):
        if long and hot:
            return "false_heat"
        if long and shape == "flat":
            return "flat"
        if long:
            return "fade"
        return "hint_weak"
    return "pending"


def review_text(bucket, zh, action, rank, shape_zh, growth, eval_days, family):
    g = fmt_growth(growth)
    rank_txt = "—" if rank is None else str(rank)
    if bucket == "pending":
        return (
            f"{zh} 的冻结动作是「{action}」（预测秩 {rank_txt}）。"
            "基线或评估窗的完整日桶不齐，或基线不能做比。"
            "这次不复核这条建议，也不把缺口写成没有需求。"
        )
    if bucket == "aligned_hint":
        return (
            f"{zh} 在 {eval_days} 个评估日上，公开主指标相对冻结前 7 日日均 {g}，形态{shape_zh}。"
            f"与冻结动作「{action}」同向，只记初步迹象。"
            "窗口太短，不能说这条测款或预热已经站得住。"
        )
    if bucket == "aligned":
        if family == "content":
            hold = "内容预热要的是讨论起来。公开声量同向，回看上这条预热站得住。"
        elif family == "light":
            hold = "轻测与公开声量同向，回看上维持轻测就够了。"
        elif family == "test":
            hold = "测款/预热与公开声量同向，回看上站得住。范围仍是轻测，帖量抬升本身不是加仓依据。"
        else:
            hold = "公开声量路径与冻结时的动作同向，回看上站得住。"
        return (
            f"{zh} 预测秩 {rank_txt}，动作「{action}」。"
            f"评估窗 {eval_days} 日，相对增长 {g}，形态{shape_zh}。{hold}"
        )
    if bucket == "false_heat":
        return (
            f"{zh} 预测秩 {rank_txt}，动作「{action}」。"
            f"评估窗 {eval_days} 日，相对增长 {g}，形态{shape_zh}。"
            "优先排序没有持续爬坡托住。"
            "回看意见：这条建议站不住，操作上回看降为观望。冻结原文不改。"
        )
    if bucket == "hint_weak":
        return (
            f"{zh} 只有 {eval_days} 个评估日，公开主指标 {g}，形态{shape_zh}。"
            f"短窗走弱或走平只记录方向，不把预测秩 {rank_txt} 的「{action}」升格成伪热结论。"
        )
    if bucket == "fade":
        return (
            f"{zh} 动作「{action}」（预测秩 {rank_txt}）。"
            f"评估窗相对增长 {g}，形态{shape_zh}。"
            "公开声量没有沿冻结方向爬坡。"
            "它不在优先秩 1–5，回看上把力度收到更保守，冻结原文不改。"
        )
    if bucket == "flat":
        return (
            f"{zh} 动作「{action}」（预测秩 {rank_txt}）。"
            f"评估窗相对增长 {g}，落在走平区间。"
            "公开声量没有爬坡，也没有明显走弱。维持原轻测强度，不追加。"
        )
    return f"{zh} 动作「{action}」。"


def fulfillment_note(zh, priors, shape_zh):
    if not priors:
        return ""
    try:
        lead = float(priors["lead_days"]) if priors.get("lead_days") is not None else 0.0
        size = float(priors["size_risk"]) if priors.get("size_risk") is not None else 0.0
    except (TypeError, ValueError):
        return ""
    if lead < 12 and size < 0.5:
        return ""
    bits = []
    if lead >= 12:
        bits.append(f"lead_days={lead:g}，冻结时按长链路情景")
    if size >= 0.5:
        bits.append(f"size_risk={size:g}，冻结时按尺码敏感情景")
    us = "us_ready_stock 为真" if priors.get("us_ready_stock") else "us_ready_stock=false，没有美仓核验"
    return (
        f"{zh}：" + "；".join(bits) + f"。{us}。"
        "这些是分析师先验，不是履约、退货或在途的实测。"
        f"本窗公开声量形态是{shape_zh}。"
        "声量不能证实履约拖累，也不能证实履约已经没问题。假说保持未验证。"
    )


def _five_dim(snapshot):
    if not isinstance(snapshot, dict):
        return None
    keys = (
        "multi_platform_demand",
        "content_ad_leverage",
        "fulfillment_sla",
        "margin_return_risk",
        "white_label_viability",
        "live_total",
    )
    if not any(isinstance(snapshot.get(k), (int, float)) and not isinstance(snapshot.get(k), bool) for k in keys):
        return None
    out = {}
    for k in keys:
        v = snapshot.get(k)
        out[k] = rnum(v, 1) if isinstance(v, (int, float)) and not isinstance(v, bool) else None
    return out


def _clip_note(text, limit):
    if text is None:
        return ""
    text = str(text).replace("\n", " ").strip()
    if len(text) <= limit:
        return text
    return text[: limit - 1] + "…"


def sku_record(
    *,
    sku_cluster,
    predicted_rank,
    predicted_action,
    metric,
    shared_with,
    baseline_days,
    baseline_values,
    eval_days,
    eval_values,
    actual_rank,
    rank_error,
    source_note,
    scores=None,
    snapshot=None,
    timing=None,
    checkpoints=None,
    t0_reference=None,
    platforms=None,
    priors=None,
):
    scores = scores or {}
    climb = build_climb(baseline_days, baseline_values, eval_days, eval_values)
    growth = climb["growth_pct"]
    status = "observed" if growth is not None else "pending"
    if status == "pending":
        actual_rank = None
        rank_error = None
    family, compare_action, action_note = action_family(predicted_action, t0_reference)
    bucket = review_bucket(climb["shape"], climb["eval_days"], predicted_rank)
    peers = [zh_name(s) for s in (shared_with or []) if s != sku_cluster]
    note = fulfillment_note(zh_name(sku_cluster), priors, climb["shape_zh"])
    five = _five_dim(snapshot if isinstance(snapshot, dict) else _parse_snapshot(snapshot))
    review = review_text(
        bucket,
        zh_name(sku_cluster),
        compare_action or predicted_action or "—",
        predicted_rank,
        climb["shape_zh"],
        growth,
        climb["eval_days"],
        family,
    )
    if peers and bucket != "pending":
        review += f" 主指标与 {'、'.join(peers)} 共用，这个判断不是该 SKU 的独立订单证据。"
    return {
        "sku_cluster": sku_cluster,
        "zh_name": zh_name(sku_cluster),
        "proxy_metric": metric,
        "proxy_metric_label": METRIC_LABELS.get(metric, metric),
        "shared_with": peers,
        "predicted_rank": predicted_rank,
        "predicted_action": predicted_action,
        "actual_value": climb["actual_sum"],
        "actual_growth": growth,
        "actual_rank": None if actual_rank is None else rnum(actual_rank, 4),
        "rank_error": None if rank_error is None else rnum(rank_error, 4),
        "status": status,
        "source_note": source_note,
        "review_bucket": bucket,
        "review": review,
        "fulfillment_note": note,
        "prediction": {
            "predicted_rank": predicted_rank,
            "predicted_action": predicted_action,
            "compare_action": compare_action,
            "action_family": family,
            "action_note": action_note,
            "predicted_urgency": rnum(scores.get("urgency"), 1),
            "predicted_demand": rnum(scores.get("demand"), 1),
            "predicted_content": rnum(scores.get("content"), 1),
            "predicted_fulfill": rnum(scores.get("fulfill"), 1),
            "predicted_total": rnum(scores.get("total"), 1),
            "price_band": scores.get("price_band"),
            "score_scale": "live/25" if five else "t0/20",
            "five_dim": five,
            "timing": timing,
            "checkpoints": checkpoints or [],
            "t0_reference": t0_reference,
        },
        "priors": _public_priors(priors),
        "climb": climb,
        "platforms": platforms or [],
    }


def _parse_snapshot(raw):
    if isinstance(raw, dict):
        return raw
    if not raw:
        return {}
    try:
        data = json.loads(raw)
    except (TypeError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _public_priors(priors):
    if not priors:
        return None
    return {
        "lead_days": priors.get("lead_days"),
        "size_risk": priors.get("size_risk"),
        "us_ready_stock": priors.get("us_ready_stock"),
        "source": "watch_topics.profiles analyst prior",
    }


def freeze_block(freeze, skus, spearman, rank_mae, metrics_note, baseline_start, baseline_end):
    return {
        "freeze_id": freeze["freeze_id"],
        "freeze_as_of": freeze.get("as_of_date"),
        "freeze_label": freeze.get("freeze_label"),
        "freeze_note": freeze.get("note"),
        "freeze_status": freeze.get("status"),
        "baseline": {"start": baseline_start, "end": baseline_end},
        "n": sum(s["status"] == "observed" for s in skus),
        "pending_n": sum(s["status"] == "pending" for s in skus),
        "sku_n": len(skus),
        "spearman": rnum(spearman, 6),
        "rank_mae": rnum(rank_mae, 4),
        "note": metrics_note,
        "skus": skus,
    }


def _ref(freeze_id, sku):
    return {
        "freeze_id": freeze_id,
        "sku_cluster": sku["sku_cluster"],
        "zh_name": sku["zh_name"],
        "predicted_rank": sku["predicted_rank"],
        "predicted_action": sku["predicted_action"],
        "shape": sku["climb"]["shape"],
        "actual_growth": sku["actual_growth"],
        "status": sku["status"],
    }


def evaluation_document(evaluation_date, window, freezes, black_friday=None, written_at=None):
    verdict = {key: [] for key, _heading in BUCKET_HEADINGS}
    verdict["fulfillment_unverified"] = []
    for fr in freezes:
        for sku in fr["skus"]:
            verdict[sku["review_bucket"]].append(_ref(fr["freeze_id"], sku))
            if sku.get("fulfillment_note"):
                verdict["fulfillment_unverified"].append(_ref(fr["freeze_id"], sku))
    return {
        "evaluation_date": evaluation_date,
        "window": {"start": window.get("start"), "end": window.get("end")},
        "black_friday": black_friday,
        "proxy": PROXY,
        "method": METHOD,
        "written_at": written_at or now_shanghai(),
        "summary": [
            {
                "freeze_id": fr["freeze_id"],
                "n": fr["n"],
                "pending_n": fr["pending_n"],
                "spearman": fr["spearman"],
                "rank_mae": fr["rank_mae"],
            }
            for fr in freezes
        ],
        "verdict": verdict,
        "freezes": freezes,
    }


def _score_cell(sku):
    total = sku["prediction"].get("predicted_total")
    if total is None:
        return "—"
    suffix = "/25" if sku["prediction"].get("score_scale") == "live/25" else "/20"
    return f"{float(total):.1f}{suffix}"


def _window_days(doc):
    window = doc.get("window") or {}
    start, end = window.get("start"), window.get("end")
    if not start or not end:
        return None
    return (datetime.fromisoformat(start) - datetime.fromisoformat(end)).days * -1 + 1


def _shared_line(doc):
    seen = set()
    bits = []
    for fr in doc["freezes"]:
        for sku in fr["skus"]:
            metric = sku.get("proxy_metric")
            peers = sku.get("shared_with") or []
            if not peers or metric in seen:
                continue
            seen.add(metric)
            names = "、".join([sku["zh_name"], *peers])
            bits.append(f"{sku.get('proxy_metric_label') or metric}（`{metric}`）由 {names} 共用")
    if not bits:
        return ""
    return "共用曲线：" + "；".join(bits) + "。这些 SKU 的爬坡不是各自的订单。"


def _comparison_rows(doc):
    rows = []
    for fr in doc["freezes"]:
        for sku in fr["skus"]:
            rows.append(
                (
                    sku["zh_name"],
                    fr["freeze_id"],
                    sku["predicted_rank"],
                    sku["prediction"].get("compare_action") or sku["predicted_action"],
                    _score_cell(sku),
                    sku["climb"]["shape_zh"],
                    fmt_growth(sku["actual_growth"]),
                    fmt_num(sku["actual_rank"], 2),
                    fmt_num(sku["rank_error"], 2),
                    sku["status"],
                )
            )
    return rows


def _bucket_blocks(doc):
    lines = []
    by_key = {}
    for fr in doc["freezes"]:
        for sku in fr["skus"]:
            by_key.setdefault(sku["review_bucket"], []).append(sku)
    for key, heading in BUCKET_HEADINGS:
        group = by_key.get(key) or []
        if not group:
            continue
        lines.append(heading)
        lines.append("")
        for sku in group:
            lines.append(f"- {sku['review']}")
        lines.append("")
    fulfill = [sku for fr in doc["freezes"] for sku in fr["skus"] if sku.get("fulfillment_note")]
    if fulfill:
        lines.append("### 履约拖累假说")
        lines.append("")
        for sku in fulfill:
            lines.append(f"- {sku['fulfillment_note']}")
        lines.append("")
    return lines


def _limitations(doc):
    bf = doc.get("black_friday") or "见 config/retail_calendar.json"
    return [
        "### 边界",
        "",
        "- 对照的是 X 完整 UTC 帖量，以及评估窗里真实写进 platform_signals 的其他公开行。",
        "- 本次数源没有 GMV、订单、退货或美仓实测。",
        "- 同一主指标上的多个 SKU 共用一条曲线，排名会并列，不能当成各自的订单。",
        "- Spearman 与 rank MAE 只在增长率可算的 SKU 子集上计算；有效样本少于 3 时 Spearman 为空。",
        "- 形态阈值 ±10% 只用来描述帖量路径。评估窗少于 5 日时只记方向。",
        "- action_hit、timing_hit、checkpoint_actuals 本导出不写入；到点的检查点保持 pending。",
        f"- 配置中的 Black_Friday = {bf}。本导出不改这个锚点，也不改 T0/T1 冻结原文。",
        "",
    ]


def render_brief(doc):
    ev = doc["evaluation_date"]
    window = doc["window"]
    lines = [
        f"## Walk-forward 回看 · {ev}",
        "",
        (
            f"评估窗 {window.get('start')} .. {window.get('end')}。"
            "公开帖量代理。"
            f"逐日数据爬坡、冻结动作与其他平台对照在 `walk-forward/walkforward_{ev}.md`。"
        ),
        "",
    ]
    if doc["summary"]:
        lines.append(
            md_table(
                ["freeze_id", "n", "pending", "Spearman", "rank MAE"],
                [
                    (s["freeze_id"], s["n"], s["pending_n"], fmt_num(s["spearman"], 4), fmt_num(s["rank_mae"], 3))
                    for s in doc["summary"]
                ],
            )
        )
        lines.append("")
    days = _window_days(doc)
    if days is not None and days < LONG_DAYS:
        lines.append(f"这个评估窗只有 {days} 日。同向或走弱只记方向，不升格成站得住或伪热。")
        lines.append("")
    shared = _shared_line(doc)
    if shared:
        lines.append(shared)
        lines.append("")
    rows = _comparison_rows(doc)
    if rows:
        lines.append(
            md_table(
                ["中文名", "冻结", "预测秩", "动作", "冻结分", "形态", "相对增长", "实际秩", "rank_error", "状态"],
                rows,
            )
        )
        lines.append("")
    for key, heading in BUCKET_HEADINGS:
        refs = (doc.get("verdict") or {}).get(key) or []
        if not refs:
            continue
        names = "、".join(r["zh_name"] for r in refs)
        lines.append(f"- {heading[4:]}：{names}")
    if any((doc.get("verdict") or {}).get("fulfillment_unverified")):
        names = "、".join(r["zh_name"] for r in doc["verdict"]["fulfillment_unverified"])
        lines.append(f"- 履约假说未验证：{names}")
    lines.append("")
    lines.append("形态阈值 ±10% 只描述帖量路径。action_hit 与 timing_hit 不在这里填写。")
    return "\n".join(lines)


def render_markdown(doc):
    ev = doc["evaluation_date"]
    window = doc["window"]
    lines = [
        f"# Walk-forward 回看 · {ev}",
        "",
        f"- 评估日：{ev}。评估窗：{window.get('start')} .. {window.get('end')}（完整 UTC 日，不含评估日当天）。",
        "- 读法：先看一页结论和运营结论，再下翻到每个 SKU 的预测情况、数据爬坡、公开实际对照。",
        "- 相对增长 = 评估窗日均帖量 / 冻结前 7 个完整日的日均帖量 − 1。指数 1.00 表示等于该基线。",
        f"- 生成时间（Asia/Shanghai）：{doc.get('written_at') or '—'}",
        "",
        "## 一页结论",
        "",
    ]
    if not doc["freezes"]:
        lines.append("没有早于评估窗起点的 prediction_freeze，本次没有 SKU 对照。")
        lines.append("")
    else:
        lines.append(
            md_table(
                ["freeze_id", "冻结日", "n", "pending", "Spearman", "rank MAE"],
                [
                    (
                        fr["freeze_id"],
                        fr.get("freeze_as_of"),
                        fr["n"],
                        fr["pending_n"],
                        fmt_num(fr["spearman"], 4),
                        fmt_num(fr["rank_mae"], 3),
                    )
                    for fr in doc["freezes"]
                ],
            )
        )
        lines.append("")
        days = _window_days(doc)
        if days is not None and days < LONG_DAYS:
            lines.append(f"这个评估窗只有 {days} 日。同向或走弱只记方向，不升格成站得住或伪热。")
            lines.append("")
        shared = _shared_line(doc)
        if shared:
            lines.append(shared)
            lines.append("")
        lines.append(
            md_table(
                ["中文名", "冻结", "预测秩", "动作", "冻结分", "形态", "相对增长", "实际秩", "rank_error", "状态"],
                _comparison_rows(doc),
            )
        )
        lines.append("")
    lines.append("## 运营结论")
    lines.append("")
    lines.extend(_bucket_blocks(doc))
    lines.extend(_limitations(doc))
    for fr in doc["freezes"]:
        lines.extend(_render_freeze(fr))
    return "\n".join(lines).rstrip() + "\n"


def _render_freeze(fr):
    lines = [
        f"## {fr['freeze_id']}",
        "",
        f"- 冻结日：{fr.get('freeze_as_of') or '—'}；状态：{fr.get('freeze_status') or '—'}",
        f"- 标签：{fr.get('freeze_label') or '—'}",
        f"- 冻结备注：{fr.get('freeze_note') or '—'}",
        f"- 基线窗：{(fr.get('baseline') or {}).get('start')} .. {(fr.get('baseline') or {}).get('end')}（冻结日当天不计入）",
        f"- 有效样本 n={fr['n']}，pending={fr['pending_n']}，Spearman={fmt_num(fr['spearman'], 4)}，rank MAE={fmt_num(fr['rank_mae'], 3)}",
        f"- 汇总说明：{fr.get('note') or '—'}",
        "",
    ]
    for sku in fr["skus"]:
        lines.extend(_render_sku(sku))
    return lines


def _render_sku(sku):
    pred = sku["prediction"]
    climb = sku["climb"]
    lines = [
        f"### {sku['zh_name']}",
        "",
        f"English SKU：`{sku['sku_cluster']}`。主指标：{sku['proxy_metric_label']}（`{sku['proxy_metric']}`）。",
        "",
        "#### 预测情况",
        "",
    ]
    if pred.get("action_note"):
        lines.append(pred["action_note"])
        lines.append("")
    rows = [
        ("预测秩 predicted_rank", pred.get("predicted_rank")),
        ("冻结动作 predicted_action", pred.get("predicted_action")),
        ("对照用动作", pred.get("compare_action")),
        ("urgency", fmt_num(pred.get("predicted_urgency"), 1)),
        ("demand", fmt_num(pred.get("predicted_demand"), 1)),
        ("content", fmt_num(pred.get("predicted_content"), 1)),
        ("fulfill", fmt_num(pred.get("predicted_fulfill"), 1)),
        ("总分", _score_cell(sku)),
        ("price_band", pred.get("price_band") or "—"),
    ]
    lines.append(md_table(["字段", "冻结时写下的值"], rows))
    lines.append("")
    if pred.get("score_scale") == "live/25":
        lines.append("这一行的总分按 Live 五维 /25 读。它和 T0 四维 /20 不是同一个尺子，两边的分不能相减。")
        lines.append("")
    five = pred.get("five_dim")
    if five:
        lines.append(
            md_table(
                ["D", "C", "F", "M", "W", "Live"],
                [[
                    fmt_num(five.get("multi_platform_demand"), 1),
                    fmt_num(five.get("content_ad_leverage"), 1),
                    fmt_num(five.get("fulfillment_sla"), 1),
                    fmt_num(five.get("margin_return_risk"), 1),
                    fmt_num(five.get("white_label_viability"), 1),
                    fmt_num(five.get("live_total"), 1),
                ]],
            )
        )
        lines.append("")
    ref = pred.get("t0_reference")
    if ref:
        lines.append(
            f"参照另一条冻结 {ref.get('freeze_id')}：预测秩 {ref.get('predicted_rank')}，"
            f"动作「{ref.get('predicted_action')}」，总分 {fmt_num(ref.get('predicted_total'), 1)}。"
            "这不是本条 freeze 行上的字段。"
        )
        lines.append("")
    timing = pred.get("timing")
    if timing:
        peak = "—"
        if timing.get("peak_window_start"):
            peak = f"{timing.get('peak_window_start')} .. {timing.get('peak_window_end')}"
        lines.append(
            f"- 发酵窗：{timing.get('ferment_window_start')} .. {timing.get('ferment_window_end')}"
        )
        lines.append(f"- 高峰窗：{peak}")
        lines.append(f"- verify_by：{timing.get('verify_by_date') or '—'}")
        lines.append(f"- 冻结时的窗假设：{timing.get('rationale') or '—'}")
        lines.append("")
    else:
        lines.append("无 prediction_timing 记录。")
        lines.append("")
    checkpoints = pred.get("checkpoints") or []
    if checkpoints:
        lines.append(
            md_table(
                ["日期", "标签", "是否已到", "预期公开信号", "本导出的对照"],
                [
                    (
                        c.get("checkpoint_date"),
                        c.get("checkpoint_label"),
                        "已到" if c.get("due") else "未到期",
                        _clip_note(c.get("expected_signal"), 80),
                        _checkpoint_status(c),
                    )
                    for c in checkpoints
                ],
            )
        )
        lines.append("")
    else:
        lines.append("无 prediction_checkpoints。")
        lines.append("")
    lines.extend(_render_climb(sku))
    lines.extend(_render_platforms(sku))
    lines.append("#### 对照解读")
    lines.append("")
    lines.append(sku["review"])
    lines.append("")
    if sku.get("fulfillment_note"):
        lines.append(sku["fulfillment_note"])
        lines.append("")
    if sku["status"] == "pending":
        lines.append(f"pending 备注：{sku.get('source_note') or '缺失日或基线无效，不编 actual。'}")
        lines.append("")
    return lines


def _checkpoint_status(c):
    if not c.get("due"):
        return "未到期，不提前填 actual"
    if c.get("stored_hit") is not None:
        return f"库内已有 hit={c.get('stored_hit')}，本导出不重算"
    return "pending，本导出不写 hit"


def _render_climb(sku):
    climb = sku["climb"]
    lines = [
        "#### 数据爬坡",
        "",
        (
            f"基线 {climb.get('baseline_start')} .. {climb.get('baseline_end')} "
            f"日均 {fmt_count(climb.get('baseline_mean'))}"
            f"（{climb.get('baseline_observed')}/{climb.get('baseline_days')} 日有数）。"
            f"评估窗 {climb.get('eval_start')} .. {climb.get('eval_end')} "
            f"日均 {fmt_count(climb.get('eval_mean'))}"
            f"（{climb.get('eval_observed')}/{climb.get('eval_days')} 日有数）。"
            f"窗口帖量合计 {fmt_count(climb.get('actual_sum'))}。"
            f"形态：{climb.get('shape_zh')}。{climb.get('shape_note')}"
        ),
        "",
        f"帖量曲线（基线 → 评估窗）：{climb.get('curve')}",
        "",
    ]
    if sku.get("shared_with"):
        names = "、".join(sku["shared_with"])
        lines.append(
            f"主指标与 {names} 共用（`{sku['proxy_metric']}`）。曲线相同，不是各自的订单。"
        )
        lines.append("")
    phase = {"baseline": "基线", "eval": "评估窗"}
    lines.append(
        md_table(
            ["日期", "阶段", "帖量", "相对基线指数", "日环比%", "状态"],
            [
                (
                    p["date"],
                    phase.get(p["phase"], p["phase"]),
                    fmt_count(p["value"]),
                    fmt_num(p["index_vs_baseline"], 3),
                    "—" if p["dod_pct"] is None else f"{p['dod_pct']:+.1f}",
                    p["status"],
                )
                for p in climb["series"]
            ],
        )
    )
    lines.append("")
    lines.append("指数只在基线日均 > 0 且当日有数时计算。日环比只连相邻自然日；缺日或基线与评估窗之间隔开的日期不连着算。")
    lines.append("")
    return lines


def _render_platforms(sku):
    lines = ["#### 公开实际对照", ""]
    rows = sku.get("platforms") or []
    if not rows:
        lines.append(
            "评估窗内没有匹配到该 SKU 或话题 * 的 platform_signals。缺测不是 0 声量。"
        )
        lines.append("")
        lines.append(
            "X 主指标的逐日帖量只出现在上面的数据爬坡里，不把其他平台的空行加进帖量合计。"
        )
        lines.append("")
        return lines
    shown = []
    pending = []
    for row in rows:
        if row.get("status") == "pending":
            pending.append(row)
        else:
            shown.append(row)
    lines.append(
        "下表是评估窗内、评估日之前已经入库的其他公开行。partial 不进爬坡合计；月度 context 只作背景。"
    )
    lines.append("")
    cap = 40
    view = shown[:cap]
    if view:
        lines.append(
            md_table(
                ["日期", "平台", "渠道", "指标", "归属", "数值", "状态"],
                [
                    (
                        r.get("signal_date"),
                        r.get("platform"),
                        r.get("channel"),
                        r.get("metric_key"),
                        "*" if r.get("scope") == "platform" else "SKU",
                        fmt_count(r.get("value")),
                        r.get("status"),
                    )
                    for r in view
                ],
            )
        )
        lines.append("")
    if len(shown) > cap:
        lines.append(f"另有 {len(shown) - cap} 行有数值或背景记录，写在同日 JSON 里。")
        lines.append("")
    if pending:
        keys = sorted({f"{r.get('platform')}/{r.get('metric_key')}" for r in pending})
        preview = "、".join(keys[:8])
        extra = f" 等 {len(keys)} 个指标" if len(keys) > 8 else ""
        lines.append(f"数值为空的行：{len(pending)}。这些行不是 0 帖。涉及 {preview}{extra}。")
        lines.append("")
    return lines


def _has_table(con, name):
    return (
        con.execute(
            "select 1 from sqlite_master where type='table' and name=?",
            (name,),
        ).fetchone()
        is not None
    )


def _date_prefix(value):
    if not value:
        return None
    text = str(value)[:10]
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        return text
    return None


def fetch_platform_rows(con, sku, start, end, evaluation_date):
    """Latest stored platform row per key, eval window only. Later availability is dropped."""
    if not _has_table(con, "platform_signals") or not _has_table(con, "runs"):
        return []
    try:
        rows = con.execute(
            """
            select s.platform, s.channel, s.metric_key, s.sku_cluster_or_topic,
                   s.signal_date, s.value, s.unit, s.is_partial, s.status,
                   s.source_note, s.period_start, s.period_end, s.available_at,
                   r.report_ts, r.as_of_date as run_as_of
            from platform_signals s
            join runs r on r.run_id = s.run_id
            where (s.sku_cluster_or_topic = ? or s.sku_cluster_or_topic = '*')
              and s.signal_date >= ? and s.signal_date <= ?
              and s.signal_date < ?
              and r.as_of_date <= ?
            order by r.report_ts
            """,
            (sku, start, end, evaluation_date, evaluation_date),
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    kept = {}
    for row in rows:
        avail = _date_prefix(row["available_at"])
        if avail and avail > evaluation_date:
            continue
        key = (
            row["signal_date"],
            row["platform"],
            row["channel"],
            row["metric_key"],
            row["sku_cluster_or_topic"],
        )
        kept[key] = row
    out = []
    for row in kept.values():
        status_raw = row["status"] or ""
        if row["is_partial"]:
            status = "partial"
        elif row["value"] is None:
            status = "pending"
        elif status_raw == "context":
            status = "context"
        else:
            status = "observed"
        out.append(
            {
                "signal_date": row["signal_date"],
                "platform": row["platform"],
                "channel": row["channel"],
                "metric_key": row["metric_key"],
                "scope": "platform" if row["sku_cluster_or_topic"] == "*" else "sku",
                "value": None if row["value"] is None else rnum(row["value"], 4),
                "unit": row["unit"],
                "status": status,
                "source_note": _clip_note(row["source_note"], 400),
                "period_start": row["period_start"],
                "period_end": row["period_end"],
                "available_at": row["available_at"],
                "run_as_of": row["run_as_of"],
            }
        )
    out.sort(key=lambda r: (r["signal_date"], r["platform"], r["metric_key"], r["scope"]))
    return out


def fetch_prediction_context(con, freeze_id, sku, evaluation_date, t0_freeze_id=T0_FREEZE_ID):
    timing = None
    if _has_table(con, "prediction_timing"):
        row = con.execute(
            "select * from prediction_timing where freeze_id=? and sku_cluster=?",
            (freeze_id, sku),
        ).fetchone()
        if row:
            timing = {
                "ferment_window_start": row["ferment_window_start"],
                "ferment_window_end": row["ferment_window_end"],
                "peak_window_start": row["peak_window_start"],
                "peak_window_end": row["peak_window_end"],
                "verify_by_date": row["verify_by_date"],
                "rationale": row["rationale"],
            }
    checkpoints = []
    if _has_table(con, "prediction_checkpoints"):
        actuals = {}
        if _has_table(con, "checkpoint_actuals"):
            for act in con.execute(
                "select * from checkpoint_actuals where freeze_id=? and sku_cluster=?",
                (freeze_id, sku),
            ):
                actuals[act["checkpoint_date"]] = act
        for row in con.execute(
            """
            select * from prediction_checkpoints
            where freeze_id=? and sku_cluster=?
            order by checkpoint_date, sort_order
            """,
            (freeze_id, sku),
        ):
            act = actuals.get(row["checkpoint_date"])
            checkpoints.append(
                {
                    "checkpoint_date": row["checkpoint_date"],
                    "checkpoint_label": row["checkpoint_label"],
                    "expected_signal": row["expected_signal"],
                    "metric_key": row["metric_key"],
                    "pass_rule": row["pass_rule"],
                    "due": row["checkpoint_date"] <= evaluation_date,
                    "stored_hit": None if act is None else act["hit"],
                }
            )
    t0_reference = None
    if freeze_id != t0_freeze_id and _has_table(con, "prediction_items"):
        row = con.execute(
            """
            select rank_in_list, predicted_action, predicted_total
            from prediction_items where freeze_id=? and sku_cluster=?
            """,
            (t0_freeze_id, sku),
        ).fetchone()
        if row:
            t0_reference = {
                "freeze_id": t0_freeze_id,
                "predicted_rank": row["rank_in_list"],
                "predicted_action": row["predicted_action"],
                "predicted_total": rnum(row["predicted_total"], 1),
            }
    return {"timing": timing, "checkpoints": checkpoints, "t0_reference": t0_reference}


def load_documents(stamp_dir, as_of):
    stamp_dir = Path(stamp_dir)
    if not stamp_dir.is_dir():
        return []
    docs = []
    for path in sorted(stamp_dir.glob("walkforward_*.json")):
        try:
            doc = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        ev = doc.get("evaluation_date")
        if ev and ev <= as_of:
            docs.append(doc)
    docs.sort(key=lambda d: d["evaluation_date"])
    return docs


def metrics_fallback(con, as_of):
    try:
        rows = list(
            con.execute(
                """
                select freeze_id, evaluation_date, n, spearman, rank_mae
                from walkforward_metrics
                where evaluation_date<=?
                order by evaluation_date, freeze_id
                """,
                (as_of,),
            )
        )
    except sqlite3.OperationalError:
        return ""
    if not rows:
        return ""
    lines = ["## Walk-forward 回看", ""]
    lines.append("库内只有汇总。逐日爬坡文件还不在 `walk-forward/`。n 为 0 或 Spearman 为空时，该冻结仍是 pending。")
    lines.append("")
    lines.append(
        md_table(
            ["评估日", "freeze_id", "n", "Spearman", "rank MAE"],
            [
                (r["evaluation_date"], r["freeze_id"], r["n"], fmt_num(r["spearman"], 4), fmt_num(r["rank_mae"], 3))
                for r in rows
            ],
        )
    )
    return "\n".join(lines)


def daily_section(as_of, stamp_dir, con=None):
    docs = load_documents(stamp_dir, as_of)
    if docs:
        return "\n\n".join(render_brief(d) for d in docs)
    if con is not None:
        return metrics_fallback(con, as_of)
    return ""


def publish(document, stamp_dir, reports_dir):
    body = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
    md = render_markdown(document)
    day = document["evaluation_date"]
    reports_dir = Path(reports_dir)
    reports_dir.mkdir(parents=True, exist_ok=True)
    reports_json = reports_dir / f"walkforward_{day}.json"
    reports_md = reports_dir / f"walkforward_{day}.md"
    reports_json.write_text(body, encoding="utf-8")
    reports_md.write_text(md, encoding="utf-8")
    stamp_dir = Path(stamp_dir)
    if not stamp_dir.parent.is_dir():
        raise FileNotFoundError(f"stamp checkout missing: {stamp_dir.parent}")
    stamp_dir.mkdir(exist_ok=True)
    stamp_json = stamp_dir / f"walkforward_{day}.json"
    stamp_md = stamp_dir / f"walkforward_{day}.md"
    stamp_json.write_text(body, encoding="utf-8")
    stamp_md.write_text(md, encoding="utf-8")
    print(f"[walkforward] {stamp_md}")
    return {
        "json": str(stamp_json),
        "md": str(stamp_md),
        "reports_json": str(reports_json),
        "reports_md": str(reports_md),
    }
