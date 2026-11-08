"""Status, health, and export. Raw payloads stay out of the export unless asked."""

from __future__ import annotations

import json
import os

from amazon_bsr import SCHEMA_VERSION
from amazon_bsr.db import require_migrated, unpack_payload
from amazon_bsr.errors import AmazonBsrError


def live_api_state() -> str:
    value = os.environ.get("KEEPA_API_KEY", "")
    if not isinstance(value, str) or not value.strip():
        return "unavailable_no_key"
    return "key_present_not_used"


def status_report(con) -> dict:
    require_migrated(con)
    groups = [dict(row) for row in con.execute("SELECT * FROM amazon_v_pool ORDER BY sku_cluster")]
    counts = {
        "raw_payloads": con.execute("SELECT COUNT(*) FROM amazon_raw_payload").fetchone()[0],
        "observations": con.execute("SELECT COUNT(*) FROM amazon_observation").fetchone()[0],
        "revisions": con.execute("SELECT COUNT(*) FROM amazon_observation WHERE revision_seq > 1").fetchone()[0],
        "current_asins": con.execute("SELECT COUNT(*) FROM amazon_asin_map WHERE is_current = 1").fetchone()[0],
        "derived_metrics": con.execute("SELECT COUNT(*) FROM amazon_derived_metric").fetchone()[0],
        "derived_ok": con.execute("SELECT COUNT(*) FROM amazon_derived_metric WHERE status = 'ok'").fetchone()[0],
        "eval_links": con.execute("SELECT COUNT(*) FROM amazon_eval_link").fetchone()[0],
        "variations_seen": con.execute("SELECT COUNT(*) FROM amazon_variation_seen").fetchone()[0],
    }
    freshness = [dict(row) for row in con.execute("SELECT * FROM amazon_v_freshness")]
    gaps = [
        dict(row)
        for row in con.execute(
            """
            SELECT source_field, SUM(present) AS present_rows, SUM(1 - present) AS absent_rows
            FROM amazon_series_presence
            WHERE source_field IN ('csv[16]', 'csv[17]', 'salesRanks', 'reviews', 'reviews.reviewCount', 'offers.stockCSV')
            GROUP BY source_field
            ORDER BY source_field
            """
        )
    ]
    return {
        "ok": True,
        "schema_version": SCHEMA_VERSION,
        "groups": groups,
        "counts": counts,
        "freshness": freshness,
        "series_presence": gaps,
        "live_api": live_api_state(),
        "live_score_integration": "not_validated",
        "amazon_signal_score": None,
        "backup_is_offsite": False,
        "rating_count_is_not_written_reviews": True,
        "rank_improvement_is_not_sales": True,
    }


def health_report(con) -> dict:
    report = status_report(con)
    integrity = con.execute("PRAGMA integrity_check").fetchone()
    report["integrity_check"] = integrity[0] if integrity else "missing"
    report["ok"] = report["integrity_check"] == "ok"
    needs = [row["sku_cluster"] for row in report["groups"] if row["pool_status"] == "needs_input"]
    report["needs_input"] = needs
    report["summary_zh"] = (
        "完整性检查 "
        + report["integrity_check"]
        + "。实时接口 "
        + report["live_api"]
        + "。尚未接入 Live 分数。needs_input 组："
        + ("、".join(needs) if needs else "无")
        + "。本机备份不是异地备份。"
    )
    return report


def export_summary(con, *, include_raw: bool = False) -> dict:
    if include_raw not in {True, False}:
        raise AmazonBsrError("export", "include_raw must be boolean")
    body = status_report(con)
    body["raw_included"] = bool(include_raw)
    body["limitations_zh"] = [
        "BSR 对数比和名次改善百分比不是销量，也不是 GMV。",
        "csv[17] 的官方名称是 COUNT_REVIEWS，文档定义是评分人数，不是文字评论数。",
        "reviews.ratingCount 自 2025-04-09 起 Keepa 文档写明不再更新。",
        "缺货或未返回的库存不会被补成 0。",
        "ASIN 池为空是 needs_input，不是样本数据。",
        "未验证前不要把任何 Amazon 指标写进 Live 权重。",
    ]
    if not include_raw:
        return body
    payloads = []
    for row in con.execute(
        "SELECT raw_id, payload_role, asin, content_hash, payload_encoding, payload_blob FROM amazon_raw_payload ORDER BY raw_id"
    ):
        logical = unpack_payload(row["payload_encoding"], row["payload_blob"])
        payloads.append(
            {
                "raw_id": row["raw_id"],
                "payload_role": row["payload_role"],
                "asin": row["asin"],
                "content_hash": row["content_hash"],
                "json": json.loads(logical.decode("utf-8")),
            }
        )
    body["raw_payloads"] = payloads
    return body
