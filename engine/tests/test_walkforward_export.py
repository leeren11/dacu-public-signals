import json
import sqlite3
import sys
import unittest
from pathlib import Path

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / "scripts"))

from export_walkforward import (  # noqa: E402
    build_climb,
    daily_section,
    endpoint_growth,
    evaluation_document,
    fetch_platform_rows,
    fetch_prediction_context,
    publish,
    render_brief,
    render_markdown,
    sku_record,
)

HOOP = "gold medium/chunky hoop earrings"
NECK = "layering/paperclip necklace set"
NAILS = "holiday press-on nails"
PJS = "matching family Christmas PJs flannel"
KNIT = "cream/oatmeal oversized chunky knit"


def _days(start, n):
    from datetime import date, timedelta

    d = date.fromisoformat(start)
    return [(d + timedelta(days=i)).isoformat() for i in range(n)]


def _sku(**kw):
    base = dict(
        sku_cluster=HOOP,
        predicted_rank=1,
        predicted_action="测款",
        metric="jewelry_gift_posts",
        shared_with=[HOOP, NECK],
        baseline_days=_days("2026-10-26", 7),
        baseline_values=[100] * 7,
        eval_days=_days("2026-11-11", 6),
        eval_values=[150] * 6,
        actual_rank=1,
        rank_error=0,
        source_note="complete",
        scores={"urgency": 4, "demand": 5, "content": 5, "fulfill": 4, "total": 18, "price_band": "15-25"},
        timing={
            "ferment_window_start": "2026-11-08",
            "ferment_window_end": "2026-11-15",
            "peak_window_start": "2026-11-11",
            "peak_window_end": "2026-11-30",
            "verify_by_date": "2026-12-01",
            "rationale": "开窗前后种草抬升（预测，非事实）",
        },
        checkpoints=[
            {
                "checkpoint_date": "2026-11-09",
                "checkpoint_label": "预热核",
                "expected_signal": "讨论相对基线启动",
                "metric_key": "X:jewelry_gift_posts_slope_7d",
                "pass_rule": "公开代理 only",
                "due": True,
                "stored_hit": None,
            }
        ],
        priors={"lead_days": 7, "size_risk": 0.0, "us_ready_stock": False},
    )
    base.update(kw)
    return sku_record(**base)


def _doc(skus, evaluation_date="2026-12-01", window=None):
    window = window or {"start": "2026-11-11", "end": "2026-11-30"}
    freeze = {
        "freeze_id": "T0_2026-11-02_top9",
        "freeze_as_of": "2026-11-02",
        "freeze_label": "今日优先 Top9 软冻结基线（可回测）",
        "freeze_note": "公开代理、不编 GMV",
        "freeze_status": "soft",
        "baseline": {"start": "2026-10-26", "end": "2026-11-01"},
        "n": sum(s["status"] == "observed" for s in skus),
        "pending_n": sum(s["status"] == "pending" for s in skus),
        "sku_n": len(skus),
        "spearman": 0.5,
        "rank_mae": 1.25,
        "note": "public proxy",
        "skus": skus,
    }
    return evaluation_document(evaluation_date, window, [freeze], black_friday="2026-11-27", written_at="2026-12-01T09:30:00+08:00")


class WalkforwardExportTests(unittest.TestCase):
    def test_endpoint_growth_matches_complete_window_and_refuses_gaps(self):
        actual, growth = endpoint_growth([10, 10], [15, 15])
        self.assertEqual(actual, 30)
        self.assertAlmostEqual(growth, 50)
        self.assertEqual(endpoint_growth([10, None], [15, 15]), (None, None))
        actual0, growth0 = endpoint_growth([0, 0], [5, 5])
        self.assertEqual(actual0, 10)
        self.assertIsNone(growth0)

    def test_climb_keeps_missing_days_null_and_labels_shapes(self):
        gap = build_climb(_days("2026-10-26", 7), [10] * 6 + [None], _days("2026-11-11", 3), [12, 12, 12])
        self.assertEqual(gap["shape"], "incomplete")
        self.assertIsNone(gap["series"][6]["value"])
        self.assertNotEqual(gap["series"][6]["value"], 0)
        self.assertIn("—", gap["curve"])
        spike_eval = [150, 150, 150, 100, 100, 100]
        spike = build_climb(_days("2026-10-26", 7), [100] * 7, _days("2026-11-11", 6), spike_eval)
        self.assertEqual(spike["shape"], "spike_fade")
        self.assertGreater(spike["growth_pct"], 0)
        late = build_climb(_days("2026-10-26", 7), [100] * 7, _days("2026-11-11", 6), [100, 100, 100, 130, 140, 150])
        self.assertEqual(late["shape"], "late_lift")
        dod = build_climb(["2026-11-01", "2026-11-02"], [10, None], ["2026-11-03"], [20])
        self.assertIsNone(dod["series"][2]["dod_pct"])
        jump = build_climb(["2026-11-01"], [100], ["2026-11-11"], [150])
        self.assertIsNone(jump["series"][1]["dod_pct"])
        self.assertEqual(jump["series"][1]["index_vs_baseline"], 1.5)

    def test_director_markdown_has_climb_call_and_public_actuals(self):
        hoop = _sku()
        neck = _sku(
            sku_cluster=NECK,
            predicted_rank=2,
            predicted_action="测款+预热",
            eval_values=[70] * 6,
            actual_rank=2,
            rank_error=0,
            shared_with=[HOOP, NECK],
        )
        pjs = _sku(
            sku_cluster=PJS,
            predicted_rank=8,
            predicted_action="轻测+内容",
            metric="fashion_gift_posts",
            shared_with=[PJS],
            priors={"lead_days": 16, "size_risk": 0.9, "us_ready_stock": False},
            platforms=[
                {
                    "signal_date": "2026-11-12",
                    "platform": "TikTok",
                    "channel": "shop",
                    "metric_key": "content_velocity",
                    "scope": "sku",
                    "value": 12,
                    "unit": "posts",
                    "status": "observed",
                    "source_note": "stored",
                },
                {
                    "signal_date": "2026-11-13",
                    "platform": "YouTube",
                    "channel": "video",
                    "metric_key": "video_view_velocity",
                    "scope": "platform",
                    "value": None,
                    "unit": "views",
                    "status": "pending",
                    "source_note": "empty",
                },
            ],
        )
        knit = _sku(
            sku_cluster=KNIT,
            predicted_rank=9,
            predicted_action="内容预热",
            metric="fashion_gift_posts",
            shared_with=[PJS, KNIT],
            baseline_values=[100] * 6 + [None],
            source_note="Pending: missing full evaluation/baseline days or zero baseline; never impute actual.",
        )
        doc = _doc([hoop, neck, pjs, knit])
        md = render_markdown(doc)
        for heading in ("## 一页结论", "## 运营结论", "### 爬坡兑现", "### 伪热嫌疑", "### 履约拖累假说", "#### 预测情况", "#### 数据爬坡", "#### 公开实际对照", "#### 对照解读"):
            self.assertIn(heading, md)
        self.assertIn("镀金中粗圈耳环", md[md.find("### 爬坡兑现"):md.find("### 伪热嫌疑")])
        self.assertIn("站得住", md)
        self.assertIn("叠戴细链套装", md[md.find("### 伪热嫌疑"):md.find("### 履约拖累假说")])
        self.assertIn("观望", md)
        self.assertIn("未验证", md)
        self.assertIn("2026-10-26", md)
        self.assertIn("2026-11-11", md)
        self.assertIn("共用", md)
        self.assertIn("TikTok", md)
        self.assertIn("数值为空的行", md)
        self.assertIn("pending", md)
        self.assertIn("Black_Friday = 2026-11-27", md)
        self.assertIn("开窗前后种草抬升", md)
        self.assertNotIn("准确率", md)
        self.assertNotIn("命中率", md)
        series = doc["freezes"][0]["skus"][0]["climb"]["series"]
        self.assertEqual(len(series), 13)
        self.assertIn("baseline", {p["phase"] for p in series})
        self.assertIn("eval", {p["phase"] for p in series})
        self.assertEqual(doc["summary"][0]["n"], 3)
        self.assertEqual(knit["status"], "pending")
        self.assertIsNone(knit["actual_growth"])
        self.assertIsNone(knit["climb"]["series"][6]["value"])

    def test_short_window_does_not_call_false_heat(self):
        sku = _sku(eval_days=["2026-11-11"], eval_values=[50], predicted_rank=1, predicted_action="测款")
        self.assertEqual(sku["review_bucket"], "hint_weak")
        doc = _doc([sku], evaluation_date="2026-11-12", window={"start": "2026-11-11", "end": "2026-11-11"})
        md = render_markdown(doc)
        self.assertIn("### 短窗未爬坡", md)
        self.assertNotIn("### 伪热嫌疑", md)
        self.assertIn("不把预测秩", md)

    def test_live_freeze_uses_t0_action_as_reference_only(self):
        sku = _sku(
            predicted_action="Live hard freeze",
            t0_reference={"freeze_id": "T0_2026-11-02_top9", "predicted_rank": 1, "predicted_action": "测款", "predicted_total": 18},
            snapshot={"multi_platform_demand": 3.2, "content_ad_leverage": 2.8, "fulfillment_sla": 4.0, "margin_return_risk": 3.1, "white_label_viability": 3.4, "live_total": 16.5},
        )
        self.assertEqual(sku["prediction"]["compare_action"], "测款")
        self.assertEqual(sku["prediction"]["score_scale"], "live/25")
        md = render_markdown(_doc([sku]))
        self.assertIn("Live hard freeze", md)
        self.assertIn("不是本条 freeze 行上的字段", md)
        self.assertIn("不能相减", md)

    def test_publish_and_daily_brief_follow_the_stamp(self):
        sku = _sku()
        doc = _doc([sku])
        import tempfile

        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            stamp = root / "stamp"
            stamp.mkdir()
            reports = root / "reports"
            paths = publish(doc, stamp / "walk-forward", reports)
            stored = json.loads(Path(paths["json"]).read_text(encoding="utf-8"))
            self.assertIn("climb", stored["freezes"][0]["skus"][0])
            self.assertEqual(len(stored["freezes"][0]["skus"][0]["climb"]["series"]), 13)
            self.assertTrue(Path(paths["md"]).read_text(encoding="utf-8").startswith("# Walk-forward 回看"))
            brief = daily_section("2026-12-01", stamp / "walk-forward")
            self.assertIn("Spearman", brief)
            self.assertIn("walk-forward/walkforward_2026-12-01.md", brief)
            self.assertNotIn("2026-10-26", brief)
            self.assertEqual(daily_section("2026-11-06", stamp / "walk-forward"), "")

    def test_platform_rows_keep_nulls_and_drop_future_availability(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute("create table runs (run_id text, as_of_date text, report_ts text)")
        con.execute(
            """
            create table platform_signals (
              run_id text, platform text, channel text, metric_key text,
              sku_cluster_or_topic text, signal_date text, value real, unit text,
              is_partial integer, status text, source_note text, period_start text,
              period_end text, available_at text
            )
            """
        )
        con.execute("insert into runs values ('a','2026-11-12','2026-11-12T01:00:00+08:00')")
        con.execute("insert into runs values ('b','2026-11-12','2026-11-12T02:00:00+08:00')")
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("a", "TikTok", "shop", "content_velocity", HOOP, "2026-11-11", 1, "idx", 0, "observed", "old", None, None, "2026-11-11"),
        )
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("b", "TikTok", "shop", "content_velocity", HOOP, "2026-11-11", 9, "idx", 0, "observed", "new", None, None, "2026-11-11"),
        )
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("b", "YouTube", "v", "video_view_velocity", "*", "2026-11-11", None, "idx", 0, "missing", "gap", None, None, None),
        )
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            ("b", "Meta", "ads", "active_ads", HOOP, "2026-11-11", 4, "ads", 0, "observed", "late", None, None, "2026-11-13"),
        )
        rows = fetch_platform_rows(con, HOOP, "2026-11-11", "2026-11-11", "2026-11-12")
        by_key = {(r["platform"], r["metric_key"]): r for r in rows}
        self.assertEqual(by_key[("TikTok", "content_velocity")]["value"], 9)
        self.assertIsNone(by_key[("YouTube", "video_view_velocity")]["value"])
        self.assertEqual(by_key[("YouTube", "video_view_velocity")]["status"], "pending")
        self.assertNotIn(("Meta", "active_ads"), by_key)
        con.close()

    def test_prediction_context_does_not_invent_hits(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute(
            """
            create table prediction_timing (
              freeze_id text, sku_cluster text, ferment_window_start text, ferment_window_end text,
              peak_window_start text, peak_window_end text, verify_by_date text, rationale text
            )
            """
        )
        con.execute(
            """
            create table prediction_checkpoints (
              freeze_id text, sku_cluster text, checkpoint_date text, checkpoint_label text,
              expected_signal text, metric_key text, pass_rule text, sort_order integer
            )
            """
        )
        con.execute(
            """
            create table prediction_items (
              freeze_id text, sku_cluster text, rank_in_list integer, predicted_action text, predicted_total real
            )
            """
        )
        con.execute(
            "insert into prediction_timing values (?,?,?,?,?,?,?,?)",
            ("T1_2026-11-08_top9", HOOP, "2026-11-08", "2026-11-15", None, None, "2026-12-01", "窗假设"),
        )
        con.execute(
            "insert into prediction_checkpoints values (?,?,?,?,?,?,?,?)",
            ("T1_2026-11-08_top9", HOOP, "2026-11-09", "预热核", "讨论启动", "X:jewelry", "up", 1),
        )
        con.execute(
            "insert into prediction_items values (?,?,?,?,?)",
            ("T0_2026-11-02_top9", HOOP, 1, "测款", 18),
        )
        ctx = fetch_prediction_context(con, "T1_2026-11-08_top9", HOOP, "2026-11-12")
        self.assertEqual(ctx["timing"]["rationale"], "窗假设")
        self.assertTrue(ctx["checkpoints"][0]["due"])
        self.assertIsNone(ctx["checkpoints"][0]["stored_hit"])
        self.assertEqual(ctx["t0_reference"]["predicted_action"], "测款")
        con.close()

    def test_metrics_fallback_and_repo_guards(self):
        con = sqlite3.connect(":memory:")
        con.row_factory = sqlite3.Row
        con.execute(
            """
            create table walkforward_metrics (
              freeze_id text, evaluation_date text, n integer, spearman real, rank_mae real, note text
            )
            """
        )
        con.execute(
            "insert into walkforward_metrics values (?,?,?,?,?,?)",
            ("T0_2026-11-02_top9", "2026-11-12", 0, None, None, "pending"),
        )
        text = daily_section("2026-11-12", "/tmp/does-not-exist-walkforward", con)
        self.assertIn("Spearman", text)
        self.assertIn("pending", text.lower())
        self.assertEqual(daily_section("2026-11-06", "/tmp/does-not-exist-walkforward", con), "")
        con.close()
        pipeline = (ENGINE / "scripts" / "run_daily_pipeline.py").read_text(encoding="utf-8")
        body = pipeline[pipeline.index("def run("):]
        self.assertLess(body.index("evaluate(as_of)"), body.index("export_one("))
        backfill = (ENGINE / "scripts" / "backfill_actuals.py").read_text(encoding="utf-8")
        self.assertIn("endpoint_growth", backfill)
        self.assertIn("STAMP/'walk-forward'", backfill)
        self.assertNotIn("UPDATE prediction", backfill)
        calendar = json.loads((ENGINE / "config" / "retail_calendar.json").read_text(encoding="utf-8"))
        self.assertEqual(calendar["anchors"]["Black_Friday"], "2026-11-27")
        self.assertEqual(set(calendar["evaluations"]), {"2026-11-12", "2026-12-01"})


if __name__ == "__main__":
    unittest.main()
