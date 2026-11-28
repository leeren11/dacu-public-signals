import hashlib
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from contextlib import redirect_stdout
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from display_names import FORMULA_VERSION
from evidence_v2 import EXAMPLE_LABEL, FORMULA_ID, VERSION_ID
from evidence_v2.cli import main
from evidence_v2.identity import engagement_counters
from evidence_v2.legacy import assess_legacy_row
from evidence_v2.shadow import dod_pct, momentum_x, ols_slope, pairwise_order_agreement, run_fixture
from evidence_v2.store import connect, load_fixture, migrate

FIXTURE = ROOT / "examples" / "evidence_v2_min.json"
PRODUCTIONS = {
    "scripts/director_model.py": "3b8726adca11b4dcdd6e357c4c12ce21475a29e6d8f8b925a212e45f2ef3c805",
    "scripts/run_daily_pipeline.py": "d4923ef80a5066ef481ee73a4bfba00ba97c713dfd97d50e90693414b9a48d71",
    "scripts/backfill_actuals.py": "815dd7c4a71a7dac78c9583a8930d7c0aaf0e22bb22f171c19dcd951e95b7338",
}


def _components(con, manifest_id, entity_id):
    row = con.execute(
        "SELECT * FROM evidence_v2_shadow_score WHERE manifest_id=? AND entity_id=?",
        (manifest_id, entity_id),
    ).fetchone()
    return dict(row), json.loads(row["components_json"])


class EvidenceV2Tests(unittest.TestCase):
    def setUp(self):
        self.con = connect(":memory:")
        self.con.execute("CREATE TABLE prediction_items (sku TEXT PRIMARY KEY, score REAL)")
        self.con.execute("INSERT INTO prediction_items VALUES ('holiday press-on nails', 17.2)")
        self.con.execute("CREATE TABLE walkforward_metrics (freeze_id TEXT, spearman REAL)")
        self.con.execute("INSERT INTO walkforward_metrics VALUES ('T1', -0.2635231383)")
        self.con.execute("CREATE TABLE rolling_sku_scoring (sku TEXT, live_total REAL)")
        self.con.execute("INSERT INTO rolling_sku_scoring VALUES ('holiday press-on nails', 17.8)")
        migrate(self.con)
        self.document = load_fixture(FIXTURE)
        self.result = run_fixture(self.con, self.document)

    def tearDown(self):
        self.con.close()

    def test_version_and_fixture_label(self):
        self.assertEqual(VERSION_ID, "evidence_research_v2.1.0")
        self.assertEqual(FORMULA_ID, "shadow_demand_v2")
        self.assertNotEqual(FORMULA_ID, FORMULA_VERSION)
        self.assertEqual(FORMULA_VERSION, "director_v1")
        self.assertEqual(self.document["example_label"], EXAMPLE_LABEL)
        self.assertIn("不是生产观测", self.document["notice"])
        self.assertIsNone(self.result["accuracy_claim"])

    def test_legacy_scores_and_hashes_unchanged(self):
        self.assertEqual(self.con.execute("SELECT score FROM prediction_items").fetchone()[0], 17.2)
        self.assertEqual(self.con.execute("SELECT spearman FROM walkforward_metrics").fetchone()[0], -0.2635231383)
        self.assertEqual(self.con.execute("SELECT live_total FROM rolling_sku_scoring").fetchone()[0], 17.8)
        for relative, digest in PRODUCTIONS.items():
            actual = hashlib.sha256((ROOT / relative).read_bytes()).hexdigest()
            self.assertEqual(actual, digest, relative)
        sql = (ROOT / "sql" / "migrate_v7_evidence_research.sql").read_text()
        executable = "\n".join(line for line in sql.splitlines() if not line.strip().startswith("--"))
        for banned in ("prediction_", "walkforward", "rolling_sku", "signals_daily", "platform_signals", "live_freeze"):
            self.assertNotIn(banned, executable)

    def test_migration_and_ingest_are_idempotent(self):
        before = self.con.execute("SELECT COUNT(*) FROM evidence_v2_observation").fetchone()[0]
        migrate(self.con)
        again = run_fixture(self.con, self.document)
        after = self.con.execute("SELECT COUNT(*) FROM evidence_v2_observation").fetchone()[0]
        shadows = self.con.execute(
            "SELECT COUNT(*) FROM evidence_v2_shadow_score WHERE manifest_id=?",
            (self.result["manifest_id"],),
        ).fetchone()[0]
        self.assertEqual(before, after)
        self.assertEqual(again["manifest_id"], self.result["manifest_id"])
        self.assertEqual(shadows, 9)
        self.assertEqual(self.con.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='7'").fetchone()[0], 1)
        with self.assertRaises(sqlite3.IntegrityError):
            self.con.execute("UPDATE evidence_v2_observation SET value=0")

    def test_scored_momentum_pending_and_shared_groups(self):
        nails, nail_parts = _components(self.con, self.result["manifest_id"], "holiday press-on nails")
        lip, _ = _components(self.con, self.result["manifest_id"], "lip butter gift set")
        squishy, squish_parts = _components(self.con, self.result["manifest_id"], "soft squishy multipack")
        jewelry, jewelry_parts = _components(self.con, self.result["manifest_id"], "friendship/beaded charm bracelet")
        fashion, fashion_parts = _components(self.con, self.result["manifest_id"], "matching family Christmas PJs flannel")
        self.assertEqual(nails["score_status"], "scored")
        self.assertEqual(lip["score"], nails["score"])
        self.assertEqual(nails["independent_group"] + lip["independent_group"], 1)
        self.assertEqual(nails["n_skus_sharing"], 2)
        self.assertEqual(nail_parts["uncertainty"], "single-source")
        self.assertFalse(nail_parts["neutral_imputation"])
        self.assertTrue(nail_parts["source_coverage_is_not_a_probability"])
        self.assertNotEqual(nails["score"], nails["source_coverage"])
        self.assertNotEqual(nails["score"], nails["v1_score"])
        self.assertEqual(nail_parts["values"], [10, 12, 11, 13, 14, 15, 18])
        expected = momentum_x(dod_pct(15, 18), ols_slope([10, 12, 11, 13, 14, 15, 18], list(range(7))))
        self.assertAlmostEqual(nails["score"], expected)
        self.assertEqual(squishy["score_status"], "scored")
        self.assertEqual(squishy["score"], 0)
        self.assertIsNone(squishy["pending_reason"])
        self.assertEqual(squish_parts["values"], [10, 10, 10, 10, 10, 10, 10])
        self.assertEqual(jewelry["score_status"], "pending")
        self.assertIsNone(jewelry["score"])
        self.assertIn("unproven_time", jewelry["pending_reason"])
        self.assertNotIn(8888, jewelry_parts["values"])
        self.assertNotEqual(jewelry["score"], 2.5)
        self.assertIn("partial_day", fashion["pending_reason"])
        self.assertNotIn(9999, fashion_parts["values"])
        self.assertEqual(self.result["n_entities"], 9)
        self.assertEqual(self.result["n_scored_entities"], 3)
        self.assertEqual(self.result["n_pending_entities"], 6)
        self.assertEqual(self.result["n_independent_groups"], 4)
        self.assertEqual(self.result["n_scored_groups"], 2)
        self.assertEqual(self.result["descriptive_rank_agreement"], 1.0)
        self.assertIn("不是准确率", self.result["comparison_note"])
        columns = {row[1] for row in self.con.execute("PRAGMA table_info(evidence_v2_shadow_score)")}
        self.assertNotIn("probability", columns)
        self.assertNotIn("accuracy", columns)

    def test_late_revision_and_open_bucket_stay_isolated(self):
        early, early_parts = _components(self.con, self.result["manifest_id"], "holiday press-on nails")
        later = run_fixture(self.con, self.document, self.document["later_replay_cutoff"])
        self.assertNotEqual(later["manifest_id"], self.result["manifest_id"])
        late_row, late_parts = _components(self.con, later["manifest_id"], "holiday press-on nails")
        self.assertEqual(early_parts["values"][-1], 18)
        self.assertEqual(late_parts["values"][-1], 16)
        self.assertNotAlmostEqual(early["score"], late_row["score"])
        still, still_parts = _components(self.con, self.result["manifest_id"], "holiday press-on nails")
        self.assertEqual(still_parts["values"][-1], 18)
        self.assertEqual(still["score"], early["score"])
        for parts in (early_parts, late_parts):
            self.assertNotIn(999, parts["values"])
            self.assertNotIn(500, parts["values"])
            self.assertNotIn(3, parts["values"])
        conflicts = self.con.execute(
            "SELECT reason FROM evidence_v2_conflict WHERE plan_id=?",
            (self.result["plan_id"],),
        ).fetchall()
        self.assertTrue(any("value_disagreement" in row["reason"] for row in conflicts))

    def test_non_daily_sources_null_and_dedupe(self):
        youtube = self.con.execute(
            "SELECT * FROM evidence_v2_observation WHERE platform='YouTube' AND entity_kind='category_proxy'"
        ).fetchone()
        self.assertEqual(youtube["requested_cadence"], "daily")
        self.assertEqual(youtube["effective_cadence"], "snapshot")
        self.assertEqual(youtube["value"], 500)
        tiktok = self.con.execute("SELECT effective_cadence, value FROM evidence_v2_observation WHERE platform='TikTok'").fetchone()
        self.assertEqual(tiktok["effective_cadence"], "monthly")
        self.assertEqual(tiktok["value"], 3)
        meta_null = self.con.execute(
            "SELECT value, status FROM evidence_v2_observation WHERE platform='Meta' AND value IS NULL"
        ).fetchone()
        self.assertIsNone(meta_null["value"])
        self.assertEqual(meta_null["status"], "missing")
        meta_zero = self.con.execute(
            "SELECT value FROM evidence_v2_observation WHERE platform='Meta' AND metric_key='jewelry_gift_posts'"
        ).fetchone()
        self.assertEqual(meta_zero["value"], 0)
        trends = self.con.execute(
            "SELECT effective_cadence FROM evidence_v2_observation WHERE platform='GoogleTrends'"
        ).fetchone()
        self.assertEqual(trends["effective_cadence"], "relative_index")
        date_only = self.con.execute(
            "SELECT date_confidence FROM evidence_v2_observation WHERE metric_key='bfcm_posts'"
        ).fetchone()
        self.assertEqual(date_only["date_confidence"], "medium")
        links = self.con.execute("SELECT action, similarity FROM evidence_v2_dedupe_link").fetchall()
        self.assertEqual(len(links), 1)
        self.assertEqual(links[0]["action"], "cross_post_kept_both")
        self.assertGreaterEqual(links[0]["similarity"], 0.7)
        item_values = sorted(
            row["value"] for row in self.con.execute("SELECT value FROM evidence_v2_observation WHERE entity_kind='item'")
        )
        self.assertEqual(item_values, [3, 9])
        engagement = json.loads(self.con.execute(
            "SELECT engagement_json FROM evidence_v2_observation WHERE entity_id='example-item-x'"
        ).fetchone()["engagement_json"])
        counters = engagement_counters(engagement)
        self.assertIsNone(counters["likes"])
        self.assertEqual(counters["reposts"], 2)
        self.assertNotIn("rank", counters)
        self.assertIsNone(self.con.execute(
            "SELECT engagement_json FROM evidence_v2_observation WHERE platform='Reddit'"
        ).fetchone()["engagement_json"])

    def test_null_partial_baseline_and_legacy_rows(self):
        self.assertIsNone(dod_pct(0, 5))
        tiny = {
            "example_label": EXAMPLE_LABEL,
            "as_of": "2026-11-12T02:00:00+00:00",
            "replay_cutoff": "2026-11-12T02:00:00+00:00",
            "lookback_days": 2,
            "series": [{
                "platform": "X",
                "metric_key": "squishy_plush_gift_posts",
                "entity_kind": "category_proxy",
                "unit": "posts",
                "cadence": "daily",
                "source_note": "SYNTHETIC_EXAMPLE_NOT_PRODUCTION",
                "days": [
                    {"date": "2026-11-11", "value": 4, "status": "observed",
                     "collected_at": "2026-11-13T01:30:00+00:00", "available_at": "2026-11-13T01:30:00+00:00"},
                    {"date": "2026-11-12", "value": None, "status": "missing",
                     "collected_at": "2026-11-13T01:30:00+00:00", "available_at": "2026-11-13T01:30:00+00:00"},
                ],
            }],
        }
        # A second plan would collide with the fixture plan if as_of and label match.
        tiny["as_of"] = "2026-11-13T02:00:00+00:00"
        tiny["replay_cutoff"] = tiny["as_of"]
        scored = run_fixture(self.con, tiny)
        row = self.con.execute(
            "SELECT score, pending_reason FROM evidence_v2_shadow_score WHERE manifest_id=? AND entity_id=?",
            (scored["manifest_id"], "soft squishy multipack"),
        ).fetchone()
        self.assertIsNone(row["score"])
        self.assertIn("null_value", row["pending_reason"])
        zero = json.loads(json.dumps(tiny))
        zero["as_of"] = "2026-11-14T02:00:00+00:00"
        zero["replay_cutoff"] = zero["as_of"]
        zero["series"][0]["days"] = [
            {"date": "2026-11-12", "value": 0, "status": "observed",
             "collected_at": "2026-11-14T01:00:00+00:00", "available_at": "2026-11-14T01:00:00+00:00"},
            {"date": "2026-11-13", "value": 5, "status": "observed",
             "collected_at": "2026-11-14T01:00:00+00:00", "available_at": "2026-11-14T01:00:00+00:00"},
        ]
        zero_result = run_fixture(self.con, zero)
        zero_row = self.con.execute(
            "SELECT score, pending_reason FROM evidence_v2_shadow_score WHERE manifest_id=? AND entity_id=?",
            (zero_result["manifest_id"], "soft squishy multipack"),
        ).fetchone()
        self.assertIsNone(zero_row["score"])
        self.assertIn("non_positive_baseline", zero_row["pending_reason"])
        proven_zero = assess_legacy_row({
            "platform": "X", "value": 0, "status": "observed", "is_partial": 0,
            "observed_start": "2026-11-11T00:00:00+00:00", "observed_end": "2026-11-12T00:00:00+00:00",
            "collected_at": "2026-11-12T01:40:00+00:00", "available_at": "2026-11-12T01:40:00+00:00",
        })
        self.assertTrue(proven_zero["eligible_for_daily_score"])
        self.assertTrue(proven_zero["treated_as_zero"])
        self.assertIn("not_a_forecast", proven_zero["reason"])
        missing = assess_legacy_row({"platform": "X", "value": None, "status": "missing"})
        self.assertFalse(missing["eligible_for_daily_score"])
        self.assertEqual(missing["reason"], "null_is_not_zero")
        self.assertFalse(missing["treated_as_zero"])
        partial = assess_legacy_row({"platform": "X", "value": 10, "status": "partial", "is_partial": 1})
        self.assertEqual(partial["reason"], "partial_day")
        unproven = assess_legacy_row({
            "platform": "X", "value": 10, "status": "observed",
            "observed_start": "2026-11-11T00:00:00+00:00", "observed_end": "2026-11-12T00:00:00+00:00",
            "collected_at": "2026-11-12T01:40:00+00:00", "available_at": "2026-11-12",
        })
        self.assertEqual(unproven["reason"], "unproven_time")
        for platform in ("YouTube", "TikTok", "Meta", "Reddit", "GoogleTrends"):
            decision = assess_legacy_row({"platform": platform, "value": 0, "status": "observed"})
            self.assertFalse(decision["eligible_for_daily_score"], platform)
            self.assertFalse(decision["treated_as_zero"], platform)

    def test_order_agreement_is_not_defined_for_one_group(self):
        self.assertIsNone(pairwise_order_agreement([(1, 0.2)]))
        self.assertEqual(pairwise_order_agreement([(1, 0.2), (2, -0.1)]), 1)
        self.assertEqual(pairwise_order_agreement([(1, -0.1), (2, 0.2)]), 0)

    def test_package_does_not_call_collectors(self):
        text = "\n".join(path.read_text() for path in (ROOT / "scripts" / "evidence_v2").glob("*.py"))
        for banned in ("run_daily_pipeline", "backfill_actuals", "freeze_T1", "persist_rolling", "playwright", "requests"):
            self.assertNotIn(banned, text)

    def test_cli_example_and_replay(self):
        with tempfile.TemporaryDirectory() as directory:
            database = str(Path(directory) / "example.sqlite")
            buffer = io.StringIO()
            with redirect_stdout(buffer):
                code = main(["run", "--db", database, "--fixture", str(FIXTURE)])
            self.assertEqual(code, 0)
            payload = json.loads(buffer.getvalue())
            self.assertEqual(payload["example_label"], EXAMPLE_LABEL)
            self.assertEqual(payload["n_scored_groups"], 2)
            self.assertIsNone(payload["accuracy_claim"])
            replay = io.StringIO()
            with redirect_stdout(replay):
                code = main([
                    "replay", "--db", database, "--plan-id", payload["plan_id"],
                    "--cutoff", self.document["later_replay_cutoff"],
                ])
            self.assertEqual(code, 0)
            later = json.loads(replay.getvalue())
            self.assertNotEqual(later["manifest_id"], payload["manifest_id"])
            with self.assertRaises(ValueError):
                load_fixture_text = dict(self.document)
                load_fixture_text["example_label"] = "production"
                path = Path(directory) / "bad.json"
                path.write_text(json.dumps(load_fixture_text))
                load_fixture(path)


if __name__ == "__main__":
    unittest.main()
