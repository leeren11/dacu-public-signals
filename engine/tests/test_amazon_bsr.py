"""SYNTHETIC TEST ONLY. ASINs use the reserved B0EXAMPL prefix and are not production data."""

from __future__ import annotations

import io
import json
import math
import os
import sqlite3
import tempfile
import unittest
from contextlib import redirect_stdout
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
import sys

sys.path.insert(0, str(ROOT / "scripts"))

from amazon_bsr.cli import main
from amazon_bsr.db import backup_database, connect_rw, migrate_database
from amazon_bsr.derive import DERIVED_SERIES, derive_metrics
from amazon_bsr.errors import AmazonBsrError
from amazon_bsr.ingest import import_keepa_bytes
from amazon_bsr.keepa_decode import decode_product
from amazon_bsr.live import live_fetch
from amazon_bsr.local_hook import ingest_local_file
from amazon_bsr.mapping import import_mapping
from amazon_bsr.policies import TARGET_GROUPS
from amazon_bsr.timeutil import KEEPA_EPOCH_OFFSET_MINUTES, keepa_minutes_to_utc
from display_names import ZH_NAME

EXAMPLE = "SYNTHETIC TEST ONLY — not a real ASIN and not production data"
SECRET = "SUPERSECRETKEY99"
NOW = "2026-11-08T00:00:00Z"
CUTOFF = "2026-11-08T12:00:00Z"


def kt(iso: str) -> int:
    dt = datetime.strptime(iso, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return int(dt.timestamp() // 60) - KEEPA_EPOCH_OFFSET_MINUTES


def product(asin: str, **extra) -> dict:
    body = {
        "asin": asin,
        "domainId": 1,
        "productType": 0,
        "title": f"{EXAMPLE} {asin}",
        "lastUpdate": kt("2026-11-02T12:00:00Z"),
        "listedSince": 0,
    }
    body.update(extra)
    return body


def ranks(category: int, points: list[tuple[str, int]]) -> dict:
    history = []
    for iso, rank in points:
        history.extend([kt(iso), rank])
    return {str(category): history}


class AmazonBsrTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.db = Path(self.tmp.name) / "evidence.sqlite"
        migrate_database(self.db, now=NOW)

    def tearDown(self):
        self.tmp.cleanup()

    def connect(self):
        return connect_rw(self.db, create=False)

    def test_keepa_epoch_and_listed_since_sentinel(self):
        self.assertEqual(keepa_minutes_to_utc(0), "2011-01-01T00:00:00Z")
        self.assertIsNone(keepa_minutes_to_utc(-1))
        decoded = decode_product(product("B0EXAMPL01", salesRanks=ranks(1001, [("2026-11-02T12:00:00Z", 10)])), domain_id=1)
        self.assertIsNone(decoded.snapshot["listed_since_at"])
        self.assertEqual(decoded.snapshot["listed_since_raw"], 0)
        self.assertTrue(any("not available" in note for note in decoded.snapshot["decode_notes_json"]))

    def test_migration_preserves_existing_rows_and_is_idempotent(self):
        path = Path(self.tmp.name) / "legacy.sqlite"
        con = sqlite3.connect(path)
        con.execute("CREATE TABLE schema_migrations(version TEXT PRIMARY KEY, applied_at TEXT NOT NULL)")
        con.execute("INSERT INTO schema_migrations(version, applied_at) VALUES ('5', '2026-11-02T00:00:00Z')")
        con.execute(
            "CREATE TABLE prediction_items(id INTEGER PRIMARY KEY, freeze_id TEXT, sku_cluster TEXT, predicted_total REAL)"
        )
        con.execute(
            "INSERT INTO prediction_items(freeze_id, sku_cluster, predicted_total) VALUES ('T0_2026-11-02_top9', 'holiday press-on nails', 12.5)"
        )
        con.execute("CREATE TABLE walkforward_results(freeze_id TEXT, sku_cluster TEXT, actual_growth REAL)")
        con.execute("INSERT INTO walkforward_results VALUES ('T0_2026-11-02_top9', 'holiday press-on nails', 1.25)")
        con.commit()
        con.close()
        before = _dump(path)
        dry = migrate_database(path, dry_run=True, backup_dir=self.tmp.name)
        self.assertEqual(dry["status"], "dry_run")
        self.assertEqual(dry["drops"], [])
        self.assertTrue(dry["would_backup"])
        self.assertEqual(_dump(path), before)
        self.assertFalse(list(Path(self.tmp.name).glob("*.sqlite.bak-*")))
        backup_dir = Path(self.tmp.name) / "backups"
        applied = migrate_database(path, backup_dir=backup_dir, now="2026-11-08T03:00:00Z")
        self.assertEqual(applied["status"], "applied")
        self.assertFalse(applied["offsite"])
        self.assertEqual(applied["backup"]["integrity_check"], "ok")
        self.assertIn("不是异地备份", applied["backup"]["note_zh"])
        sidecar = Path(applied["backup"]["sha256_path"]).read_text(encoding="utf-8").split()[0]
        self.assertEqual(sidecar, applied["backup"]["sha256"])
        after = _dump(path)
        self.assertEqual(after["prediction_items"], before["prediction_items"])
        self.assertEqual(after["walkforward_results"], before["walkforward_results"])
        self.assertEqual(after["applied_at"], "2026-11-02T00:00:00Z")
        again = migrate_database(path)
        self.assertEqual(again["status"], "already_applied")
        self.assertFalse(again["wrote"])
        con = sqlite3.connect(path)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='5'").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='amazon_bsr_v1'").fetchone()[0], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM amazon_asin_map").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM amazon_observation").fetchone()[0], 0)
        statuses = [row[0] for row in con.execute("SELECT pool_status FROM amazon_target_group ORDER BY sku_cluster")]
        self.assertEqual(statuses, ["needs_input"] * 4)
        names = {row[0]: row[1] for row in con.execute("SELECT sku_cluster, display_zh FROM amazon_target_group")}
        for group in TARGET_GROUPS:
            self.assertEqual(names[group["sku_cluster"]], ZH_NAME[group["sku_cluster"]])
        con.close()
        backed = sqlite3.connect(applied["backup"]["backup_path"])
        self.assertEqual(backed.execute("SELECT predicted_total FROM prediction_items").fetchone()[0], 12.5)
        self.assertIsNone(
            backed.execute("SELECT name FROM sqlite_master WHERE name='amazon_target_group'").fetchone()
        )
        backed.close()
        sql = "\n".join(
            line.split("--", 1)[0]
            for line in (ROOT / "sql" / "migrate_v6_amazon_bsr.sql").read_text(encoding="utf-8").splitlines()
        )
        self.assertNotRegex(sql, r"(?i)\bDROP\b")
        self.assertNotRegex(sql, r"(?i)\bDELETE\s+FROM\b")

    def test_mapping_rules_and_empty_pool(self):
        con = self.connect()
        empty = _mapping("map.empty.1", [])
        imported = import_mapping(con, empty, allow_example=True, now=NOW)
        self.assertEqual(imported["item_count"], 0)
        self.assertTrue(all(row["pool_status"] == "needs_input" for row in imported["pools"]))
        with self.assertRaises(AmazonBsrError) as mixed:
            import_mapping(
                con,
                _mapping(
                    "map.opal.bad",
                    [
                        _item(
                            "opal/birthstone/initial pendant (ready-stock)",
                            "B0EXAMPL21",
                            {"pendant_facet": "opal", "additional_facets": ["birthstone"]},
                        )
                    ],
                ),
                allow_example=True,
                now=NOW,
            )
        self.assertEqual(mixed.exception.code, "reason_required")
        good = import_mapping(
            con,
            _mapping(
                "map.opal.1",
                [
                    _item(
                        "opal/birthstone/initial pendant (ready-stock)",
                        "B0EXAMPL21",
                        {"pendant_facet": "opal"},
                    )
                ],
            ),
            allow_example=True,
            now="2026-11-08T01:00:00Z",
        )
        self.assertEqual(_pool(con, "opal/birthstone/initial pendant (ready-stock)"), "below_recommended")
        with self.assertRaises(AmazonBsrError) as other:
            import_mapping(
                con,
                _mapping(
                    "map.opal.cross",
                    [_item("holiday press-on nails", "B0EXAMPL21", {"product_form": "press-on", "theme": "holiday"})],
                ),
                allow_example=True,
                now=NOW,
            )
        self.assertEqual(other.exception.code, "asin_in_other_group")
        self.assertIsNone(con.execute("SELECT 1 FROM amazon_mapping_version WHERE mapping_version='map.opal.cross'").fetchone())
        child = _item(
            "holiday press-on nails",
            "B0EXAMPL22",
            {"product_form": "press-on", "theme": "holiday"},
            role="child",
            parent_asin="B0EXAMPLP1",
            variation_attributes=[{"dimension": "Color", "value": "Red"}],
        )
        import_mapping(con, _mapping("map.nails.1", [child]), allow_example=True, now="2026-11-08T01:00:00Z")
        with self.assertRaises(AmazonBsrError):
            import_mapping(
                con,
                _mapping("map.nails.1", [child | {"inclusion_reason": "changed reason that is still long enough"}]),
                allow_example=True,
                now=NOW,
            )
        con.close()

    def test_keepa_import_metrics_revisions_and_secrets(self):
        secret_product = product(
            "B0EXAMPL12",
            key=SECRET,
            sourceUrl=f"https://api.keepa.com/product?key={SECRET}&domain=1",
            title="x" * 9000,
            salesRanks=ranks(1001, [("2026-10-26T12:00:00Z", 10), ("2026-11-02T12:00:00Z", 8)]),
        )
        payload = {
            "_example": True,
            "products": [
                product(
                    "B0EXAMPL01",
                    categoryTree=[{"catId": 1001, "name": "Example Nails"}],
                    salesRanks=ranks(1001, [("2026-10-26T12:00:00Z", 1000), ("2026-11-02T12:00:00Z", 250)]),
                ),
                product(
                    "B0EXAMPL02",
                    salesRanks=ranks(
                        1001,
                        [
                            ("2026-10-26T12:00:00Z", 200),
                            ("2026-11-02T10:00:00Z", 100),
                            ("2026-11-02T18:00:00Z", 300),
                        ],
                    ),
                ),
                product(
                    "B0EXAMPL03",
                    salesRanks=ranks(1001, [("2026-10-26T12:00:00Z", 200), ("2026-11-02T12:00:00Z", 100)]),
                ),
                product(
                    "B0EXAMPL04",
                    salesRanks={
                        **ranks(1001, [("2026-10-26T12:00:00Z", 1000), ("2026-11-02T12:00:00Z", 500)]),
                        **ranks(2002, [("2026-10-26T12:00:00Z", 500), ("2026-11-02T12:00:00Z", 1000)]),
                    },
                ),
                product(
                    "B0EXAMPL05",
                    salesRanks={
                        **ranks(3003, [("2026-10-26T12:00:00Z", 100), ("2026-10-30T12:00:00Z", -1), ("2026-11-02T12:00:00Z", 50)]),
                        **ranks(3004, [("2026-10-26T12:00:00Z", 80), ("2026-11-02T12:00:00Z", 40)]),
                    },
                ),
                product(
                    "B0EXAMPL06",
                    salesRankReferenceHistory=[
                        kt("2026-10-26T00:00:00Z"),
                        1001,
                        kt("2026-10-30T00:00:00Z"),
                        2002,
                        kt("2026-11-02T00:00:00Z"),
                        1001,
                    ],
                    csv=_csv({3: [kt("2026-10-26T12:00:00Z"), 100, kt("2026-11-02T12:00:00Z"), 80]}),
                ),
                product(
                    "B0EXAMPL16",
                    salesRankReferenceHistory=[kt("2026-10-01T00:00:00Z"), 1001],
                    csv=_csv({3: [kt("2026-10-26T12:00:00Z"), 1000, kt("2026-11-02T12:00:00Z"), 250]}),
                ),
                product("B0EXAMPL15", csv=_csv({3: [kt("2026-10-26T12:00:00Z"), 40, kt("2026-11-02T12:00:00Z"), 20]})),
                product("B0EXAMPL17", csv=_csv({3: [1, 2, 3], 1: [kt("2026-02-22T12:00:00Z"), 1000]})),
                product(
                    "B0EXAMPL14",
                    salesRanks=ranks(1001, [("2026-10-30T12:00:00Z", 90), ("2026-11-02T12:00:00Z", 70)]),
                ),
                product(
                    "B0EXAMPL13",
                    salesRanks=ranks(1001, [("2026-11-02T12:00:00Z", 0), ("2026-11-02T13:00:00Z", -1)]),
                ),
                _rating_product(),
                product(
                    "B0EXAMPL10",
                    parentAsin="B0EXAMPL10",
                    variations=[{"asin": "B0EXAMPLC1", "attributes": [{"dimension": "Color", "value": "Red"}]}],
                    salesRanks=ranks(1001, [("2026-10-26T12:00:00Z", 15), ("2026-11-02T12:00:00Z", 12)]),
                ),
                product(
                    "B0EXAMPL11",
                    csv=_price_csv(),
                    monthlySoldHistory=[kt("2026-11-02T12:00:00Z"), 100],
                    offers=[
                        {
                            "offerId": 7,
                            "sellerId": "A2EXAMPLESELL",
                            "condition": 1,
                            "lastSeen": kt("2026-11-02T12:00:00Z"),
                            "offerCSV": [kt("2026-11-02T12:00:00Z"), 2500, 0],
                            "stockCSV": [kt("2026-11-02T12:00:00Z"), 4],
                        }
                    ],
                ),
                secret_product,
                product(
                    "B0EXAMPL07",
                    salesRanks=ranks(1001, [("2026-11-02T12:00:00Z", 30)]),
                ),
            ],
        }
        raw = json.dumps(payload).encode()
        con = self.connect()
        dry = import_keepa_bytes(con, raw, source_kind="offline_file", domain_id=1, allow_example=True, dry_run=True, now=NOW)
        self.assertFalse(dry["wrote"])
        self.assertEqual(con.execute("SELECT COUNT(*) FROM amazon_observation").fetchone()[0], 0)
        con.execute(
            "CREATE TABLE prediction_items(id INTEGER PRIMARY KEY, freeze_id TEXT, predicted_total REAL)"
        )
        con.execute("INSERT INTO prediction_items(freeze_id, predicted_total) VALUES ('T0_2026-11-02_top9', 12.5)")
        first = import_keepa_bytes(con, raw, source_kind="offline_file", domain_id=1, allow_example=True, now=NOW)
        self.assertEqual(first["status"], "imported")
        self.assertGreater(first["inserted_observations"], 0)
        self.assertNotIn(SECRET.encode(), self.db.read_bytes())
        encoding = con.execute(
            "SELECT payload_encoding FROM amazon_raw_payload WHERE asin='B0EXAMPL12' AND payload_role='product'"
        ).fetchone()[0]
        self.assertEqual(encoding, "gzip_json")
        listed = con.execute(
            "SELECT listed_since_at FROM amazon_product_snapshot WHERE asin='B0EXAMPL01'"
        ).fetchone()[0]
        self.assertIsNone(listed)
        observed = con.execute(
            "SELECT observed_at, first_available_to_system FROM amazon_observation WHERE asin='B0EXAMPL01' LIMIT 1"
        ).fetchone()
        self.assertLess(observed["observed_at"], observed["first_available_to_system"])
        second = import_keepa_bytes(con, raw, source_kind="offline_file", domain_id=1, allow_example=True, now=NOW)
        self.assertEqual(second["status"], "duplicate")
        self.assertEqual(second["inserted_observations"], 0)
        revision = {
            "_example": True,
            "products": [
                product(
                    "B0EXAMPL03",
                    salesRanks=ranks(1001, [("2026-10-26T12:00:00Z", 200), ("2026-11-02T12:00:00Z", 400)]),
                )
            ],
        }
        revised = import_keepa_bytes(
            con,
            json.dumps(revision).encode(),
            source_kind="offline_file",
            domain_id=1,
            allow_example=True,
            now=NOW,
        )
        self.assertGreater(revised["revision_observations"], 0)
        original = con.execute(
            """
            SELECT value_num FROM amazon_observation
            WHERE asin='B0EXAMPL03' AND observed_at='2026-11-02T12:00:00Z' AND revision_seq=1
            """
        ).fetchone()[0]
        self.assertEqual(original, 100)
        self.assertEqual(
            con.execute(
                "SELECT value_num FROM amazon_observation WHERE asin='B0EXAMPL03' AND observed_at='2026-11-02T12:00:00Z' AND revision_seq=2"
            ).fetchone()[0],
            400,
        )
        import_keepa_bytes(
            con,
            json.dumps(
                {
                    "_example": True,
                    "products": [product("B0EXAMPL07", salesRanks=ranks(1001, [("2026-10-26T12:00:00Z", 90)]))],
                }
            ).encode(),
            source_kind="offline_file",
            domain_id=1,
            allow_example=True,
            now="2026-11-09T00:00:00Z",
        )
        import_mapping(
            con,
            _mapping(
                "map.nails.live",
                [_item("holiday press-on nails", "B0EXAMPL01", {"product_form": "press-on", "theme": "holiday"})],
                valid_from="2026-10-01",
            ),
            allow_example=True,
            now="2026-11-08T01:00:00Z",
        )
        derived = derive_metrics(
            con,
            selection_cutoff=CUTOFF,
            as_of="2026-11-02",
            eval_freeze_id="T1_label_only",
            eval_date="2026-11-02",
            allow_eval=True,
        )
        self.assertEqual(derived["conflicts"], 0)
        again = derive_metrics(
            con,
            selection_cutoff=CUTOFF,
            as_of="2026-11-02",
            eval_freeze_id="T1_label_only",
            eval_date="2026-11-02",
            allow_eval=True,
        )
        self.assertEqual(again["inserted"], 0)
        self.assertGreater(again["skipped"], 0)
        self.assertEqual(con.execute("SELECT predicted_total FROM prediction_items").fetchone()[0], 12.5)
        ln_row = _metric(con, "B0EXAMPL01", "bsr_ln_ratio_7d_v1", "1001")
        pct_row = _metric(con, "B0EXAMPL01", "bsr_rank_improvement_pct_7d_v1", "1001")
        self.assertEqual(ln_row["status"], "ok")
        self.assertAlmostEqual(ln_row["value"], math.log(1000 / 250))
        self.assertAlmostEqual(pct_row["value"], 75.0)
        self.assertEqual(ln_row["interpretation"], "ln_old_bsr_over_new_bsr_not_sales")
        self.assertEqual(pct_row["interpretation"], "rank_improvement_percent_not_sales_growth")
        self.assertEqual(ln_row["span_days"], 7.0)
        self.assertEqual(ln_row["policy_id"], "utc_day_latest_observed_at_lowest_revision_v1")
        link = con.execute(
            "SELECT sku_cluster, link_status, leak_excluded FROM amazon_eval_link WHERE asin='B0EXAMPL01' AND metric_id=?",
            (ln_row["metric_id"],),
        ).fetchone()
        self.assertEqual(link["sku_cluster"], "holiday press-on nails")
        self.assertEqual(link["link_status"], "linked")
        self.assertEqual(link["leak_excluded"], 0)
        median = _metric(con, "B0EXAMPL02", "bsr_ln_ratio_7d_v1", "1001")
        self.assertAlmostEqual(median["value"], math.log(200 / 300))
        self.assertNotAlmostEqual(median["value"], 0.0)
        revision_metric = _metric(con, "B0EXAMPL03", "bsr_ln_ratio_7d_v1", "1001")
        self.assertAlmostEqual(revision_metric["value"], math.log(200 / 100))
        cat_a = _metric(con, "B0EXAMPL04", "bsr_ln_ratio_7d_v1", "1001")
        cat_b = _metric(con, "B0EXAMPL04", "bsr_ln_ratio_7d_v1", "2002")
        self.assertAlmostEqual(cat_a["value"], math.log(2))
        self.assertAlmostEqual(cat_b["value"], math.log(0.5))
        self.assertEqual(cat_a["category_id"], "1001")
        self.assertEqual(cat_b["category_id"], "2002")
        hole = _metric(con, "B0EXAMPL05", "bsr_ln_ratio_7d_v1", "3003")
        other = _metric(con, "B0EXAMPL05", "bsr_ln_ratio_7d_v1", "3004")
        self.assertEqual(hole["status"], "discontinuity_gap")
        self.assertIsNone(hole["value"])
        self.assertEqual(other["status"], "ok")
        flipped = _metric(con, "B0EXAMPL06", "bsr_ln_ratio_7d_v1", "1001", series="bsr_csv_sales")
        self.assertEqual(flipped["status"], "discontinuity_reference_change")
        self.assertIsNone(flipped["value"])
        stable = _metric(con, "B0EXAMPL16", "bsr_ln_ratio_7d_v1", "1001", series="bsr_csv_sales")
        self.assertEqual(stable["status"], "ok")
        self.assertAlmostEqual(stable["value"], math.log(4))
        unresolved = con.execute(
            """
            SELECT is_valid_measurement, category_resolution FROM amazon_observation
            WHERE asin='B0EXAMPL15' AND series_kind='bsr_csv_sales' AND value_missing_reason IS NULL
            """
        ).fetchall()
        self.assertTrue(unresolved)
        self.assertTrue(all(row["is_valid_measurement"] == 0 and row["category_resolution"] == "unresolved_no_reference_history" for row in unresolved))
        self.assertIsNone(_metric(con, "B0EXAMPL15", "bsr_ln_ratio_7d_v1", "", series="bsr_csv_sales"))
        short = _metric(con, "B0EXAMPL14", "bsr_ln_ratio_7d_v1", "1001")
        self.assertEqual(short["status"], "no_snapshot_on_start_utc_date")
        self.assertIsNone(short["value"])
        self.assertIsNone(_metric(con, "B0EXAMPL13", "bsr_ln_ratio_7d_v1", "1001"))
        sentinels = con.execute(
            "SELECT sentinel_raw, is_valid_measurement FROM amazon_observation WHERE asin='B0EXAMPL13' ORDER BY sentinel_raw"
        ).fetchall()
        self.assertEqual([row["sentinel_raw"] for row in sentinels], [-1, 0])
        self.assertTrue(all(row["is_valid_measurement"] == 0 for row in sentinels))
        rating = _metric(
            con,
            "B0EXAMPL09",
            "rating_count_abs_delta_7d_v1",
            "",
            series="rating_count",
            variant="keepa_csv17_COUNT_REVIEWS_rating_count_v1",
        )
        written = _metric(
            con,
            "B0EXAMPL09",
            "written_review_count_abs_delta_7d_v1",
            "",
            series="written_review_count",
            variant="keepa_reviews_reviewCount_written_variation_v1",
        )
        self.assertEqual(rating["value"], 5)
        self.assertIn("rating count", rating["status_reason"])
        self.assertEqual(written["value"], 2)
        self.assertNotEqual(rating["definition_variant"], written["definition_variant"])
        stale = con.execute(
            """
            SELECT source_update_status, source_update_reason FROM amazon_observation
            WHERE asin='B0EXAMPL09' AND definition_variant='keepa_reviews_ratingCount_variation_v1' LIMIT 1
            """
        ).fetchone()
        self.assertEqual(stale["source_update_status"], "documented_stale")
        self.assertIn("April 9th 2025", stale["source_update_reason"])
        stars = con.execute(
            "SELECT value_num, value_text FROM amazon_observation WHERE asin='B0EXAMPL09' AND series_kind='rating' AND is_valid_measurement=1"
        ).fetchone()
        self.assertEqual(stars["value_num"], 4.5)
        self.assertIn("keepa_raw=45", stars["value_text"])
        leak = _metric(con, "B0EXAMPL07", "bsr_ln_ratio_7d_v1", "1001")
        self.assertEqual(leak["status"], "no_snapshot_on_start_utc_date")
        self.assertIsNone(leak["value"])
        self.assertEqual(json.loads(leak["guard_json"])["leak_excluded"], 1)
        leak_link = con.execute(
            "SELECT sku_cluster, link_status, leak_excluded FROM amazon_eval_link WHERE asin='B0EXAMPL07'"
        ).fetchone()
        self.assertEqual(leak_link["link_status"], "withheld_not_known")
        self.assertIsNone(leak_link["sku_cluster"])
        self.assertEqual(leak_link["leak_excluded"], 1)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM amazon_asin_map WHERE asin='B0EXAMPLC1'").fetchone()[0], 0)
        self.assertGreater(
            con.execute("SELECT COUNT(*) FROM amazon_variation_seen WHERE child_asin='B0EXAMPLC1'").fetchone()[0],
            0,
        )
        ship = con.execute(
            """
            SELECT price_cents, shipping_cents, value_num FROM amazon_observation
            WHERE asin='B0EXAMPL11' AND price_type='NEW_FBM_SHIPPING' AND is_valid_measurement=1
            """
        ).fetchone()
        self.assertEqual((ship["price_cents"], ship["shipping_cents"], ship["value_num"]), (1999, 250, 19.99))
        basis = {
            row["observed_at"]: row["price_basis"]
            for row in con.execute(
                "SELECT observed_at, price_basis FROM amazon_observation WHERE asin='B0EXAMPL11' AND price_type='NEW'"
            )
        }
        self.assertIn("listing", basis["2026-02-22T12:00:00Z"])
        self.assertIn("landing", basis["2026-02-23T12:00:00Z"])
        self.assertEqual(
            con.execute(
                "SELECT COUNT(*) FROM amazon_observation WHERE asin='B0EXAMPL11' AND source_field='csv[36]'"
            ).fetchone()[0],
            0,
        )
        self.assertIn(
            "Unknown csv index",
            con.execute(
                "SELECT note FROM amazon_series_presence WHERE source_field='csv[36]'"
            ).fetchone()[0],
        )
        shape_note = con.execute(
            """
            SELECT note FROM amazon_series_presence p
            JOIN amazon_raw_payload r ON r.raw_id = p.raw_id
            WHERE r.asin = 'B0EXAMPL17' AND p.source_field = 'csv[3]'
            """
        ).fetchone()[0]
        self.assertIn("shape", shape_note)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM amazon_derived_metric WHERE series_kind='price'").fetchone()[0], 0)
        self.assertEqual(con.execute("SELECT COUNT(*) FROM amazon_derived_metric WHERE series_kind='offer_stock'").fetchone()[0], 0)
        self.assertEqual(
            con.execute("SELECT stock_qty FROM amazon_observation WHERE asin='B0EXAMPL11' AND series_kind='offer_stock'").fetchone()[0],
            4,
        )
        columns = [row[1] for row in con.execute("PRAGMA table_info(amazon_derived_metric)")]
        self.assertNotIn("acceleration", columns)
        self.assertEqual(
            DERIVED_SERIES,
            ("bsr_sales_ranks", "bsr_csv_sales", "rating_count", "written_review_count"),
        )
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("UPDATE amazon_raw_payload SET license_note='mutated'")
        with self.assertRaises(sqlite3.DatabaseError):
            con.execute("DELETE FROM amazon_observation")
        con.close()

    def test_cli_refuses_examples_and_live_without_key_or_flag(self):
        raw_path = Path(self.tmp.name) / "example.json"
        raw_path.write_text(
            json.dumps({"_example": True, "products": [product("B0EXAMPL01", salesRanks=ranks(1001, [("2026-11-02T12:00:00Z", 5)]))] }),
            encoding="utf-8",
        )
        code, body = _cli(
            "import-raw",
            "--db",
            str(self.db),
            "--file",
            str(raw_path),
            "--domain",
            "1",
        )
        self.assertEqual(code, 2)
        self.assertEqual(body["error"], "example_refused")
        con = self.connect()
        self.assertEqual(con.execute("SELECT COUNT(*) FROM amazon_observation").fetchone()[0], 0)
        con.close()
        code, body = _cli("health", "--db", str(self.db))
        self.assertEqual(code, 0)
        self.assertEqual(body["integrity_check"], "ok")
        self.assertEqual(body["live_score_integration"], "not_validated")
        self.assertEqual(body["amazon_signal_score"], None)
        self.assertEqual(len(body["needs_input"]), 4)
        out = Path(self.tmp.name) / "summary.json"
        code, body = _cli("export", "--db", str(self.db), "--out", str(out))
        self.assertEqual(code, 0)
        self.assertFalse(body["raw_included"])
        self.assertNotIn("raw_payloads", json.loads(out.read_text(encoding="utf-8")))
        missing = Path(self.tmp.name) / "missing.sqlite"
        calls = []

        def boom(url, timeout=60):
            calls.append(url)
            raise AssertionError("network")

        import amazon_bsr.live as live_mod

        original = live_mod.default_fetch
        live_mod.default_fetch = boom
        try:
            os.environ.pop("KEEPA_API_KEY", None)
            code, body = _cli(
                "live-fetch",
                "--db",
                str(missing),
                "--live-fetch",
                "--domain",
                "1",
                "--asin",
                "B00REALAS1",
                "--token-budget",
                "1",
                "--batch-size",
                "1",
            )
            self.assertEqual(code, 0)
            self.assertEqual(body["status"], "unavailable")
            self.assertFalse(missing.exists())
            self.assertEqual(calls, [])
            code, body = _cli(
                "live-fetch",
                "--db",
                str(self.db),
                "--domain",
                "1",
                "--asin",
                "B00REALAS1",
                "--token-budget",
                "1",
                "--batch-size",
                "1",
            )
            self.assertEqual(code, 2)
            self.assertEqual(body["error"], "live_not_confirmed")
            self.assertEqual(calls, [])
        finally:
            live_mod.default_fetch = original
        with self.assertRaises(AmazonBsrError) as url_error:
            ingest_local_file(self.db, "https://api.keepa.com/product?key=SECRET")
        self.assertEqual(url_error.exception.code, "live_forbidden")
        self.assertNotIn("urlopen", (ROOT / "scripts" / "amazon_bsr" / "local_hook.py").read_text(encoding="utf-8"))
        pipeline = (ROOT / "scripts" / "run_daily_pipeline.py").read_text(encoding="utf-8")
        self.assertIn("if amazon_local_input:", pipeline)
        doc = (ROOT / "docs" / "amazon_bsr_zh.md").read_text(encoding="utf-8")
        for phrase in (
            "python3 scripts/amazon_bsr_cli.py migrate",
            "/workspace/dacu-signal/db/dacu_signals.sqlite",
            "不是异地备份",
            "needs_input",
            "2026-11-12",
            "2026-12-01",
            "--live-fetch",
            "COUNT_REVIEWS",
            "--selection-cutoff",
        ):
            self.assertIn(phrase, doc)

    def test_live_records_reported_tokens_and_stops_at_budget(self):
        calls = []

        def fetch(url, timeout=60):
            calls.append(url)
            asin = "B00REALAS1" if "B00REALAS1" in url else "B00REALAS2"
            body = {
                "tokensConsumed": 1,
                "tokensLeft": 4,
                "refillIn": 1000,
                "refillRate": 5,
                "timestamp": 1762617600000,
                "products": [product(asin, salesRanks=ranks(1001, [("2026-11-02T12:00:00Z", 11)]))],
            }
            return 200, json.dumps(body).encode()

        os.environ["KEEPA_API_KEY"] = SECRET
        try:
            result = live_fetch(
                self.db,
                live_confirmed=True,
                asins=["B00REALAS1", "B00REALAS2"],
                asin_file=None,
                domain_id=1,
                token_budget=1,
                batch_size=1,
                fetch=fetch,
                now=NOW,
            )
        finally:
            os.environ.pop("KEEPA_API_KEY", None)
        self.assertEqual(len(calls), 1)
        self.assertEqual(result["tokens_consumed_reported"], 1)
        self.assertIsNone(result["estimated_tokens"])
        self.assertEqual(result["stopped"], "budget_reached")
        self.assertNotIn(SECRET.encode(), self.db.read_bytes())
        con = self.connect()
        stored = con.execute("SELECT tokens_consumed FROM amazon_request").fetchone()[0]
        self.assertEqual(stored, 1)
        params = con.execute("SELECT sanitized_params_json FROM amazon_request").fetchone()[0]
        self.assertIn("[REDACTED]", params)
        self.assertNotIn(SECRET, params)
        con.close()
        with self.assertRaises(AmazonBsrError) as guessed:
            live_fetch(
                self.db,
                live_confirmed=True,
                asins=["B00REALAS1"],
                asin_file=None,
                domain_id=1,
                token_budget=5,
                batch_size=20,
                offers=20,
                fetch=fetch,
                key="present-but-unused",
            )
        self.assertEqual(guessed.exception.code, "refusing_to_guess_token_cost")
        self.assertEqual(len(calls), 1)


def _dump(path: Path) -> dict:
    con = sqlite3.connect(path)
    try:
        return {
            "prediction_items": con.execute("SELECT freeze_id, sku_cluster, predicted_total FROM prediction_items").fetchall(),
            "walkforward_results": con.execute("SELECT * FROM walkforward_results").fetchall(),
            "applied_at": con.execute("SELECT applied_at FROM schema_migrations WHERE version='5'").fetchone()[0],
        }
    finally:
        con.close()


def _mapping(version: str, items_by_call: list[dict], valid_from: str = "2026-11-08") -> dict:
    groups = {group["sku_cluster"]: [] for group in TARGET_GROUPS}
    for item in items_by_call:
        groups[item["sku_cluster"]].append({key: value for key, value in item.items() if key != "sku_cluster"})
    return {
        "_example": True,
        "mapping_version": version,
        "domain_id": 1,
        "valid_from": valid_from,
        "provenance": {
            "source": "unit-test",
            "recorded_by": "test-fixture",
            "note": EXAMPLE,
            "license_note": "test only",
        },
        "groups": [{"sku_cluster": sku, "items": items} for sku, items in groups.items()],
    }


def _item(sku: str, asin: str, attributes: dict, **extra) -> dict:
    body = {
        "sku_cluster": sku,
        "asin": asin,
        "role": "standalone",
        "inclusion_reason": f"operator checked this example listing for {sku}",
        "category_ids": [1001],
        "product_attributes": attributes,
        "variation_attributes": [],
    }
    body.update(extra)
    return body


def _pool(con, sku: str) -> str:
    return con.execute("SELECT pool_status FROM amazon_target_group WHERE sku_cluster=?", (sku,)).fetchone()[0]


def _csv(slots: dict[int, list]) -> list:
    size = max(slots) + 1
    csv = [None] * size
    for index, history in slots.items():
        csv[index] = history
    return csv


def _price_csv() -> list:
    unknown = [kt("2026-11-02T12:00:00Z"), 999]
    csv = _csv(
        {
            1: [kt("2026-02-22T12:00:00Z"), 1000, kt("2026-02-23T12:00:00Z"), 1100],
            7: [kt("2026-11-02T12:00:00Z"), 1999, 250],
        }
    )
    while len(csv) < 36:
        csv.append(None)
    csv.append(unknown)
    return csv


def _rating_product() -> dict:
    start = "2026-10-26T12:00:00Z"
    end = "2026-11-02T12:00:00Z"
    csv = _csv(
        {
            16: [kt(end), 45],
            17: [kt(start), 10, kt(end), 15],
        }
    )
    return product(
        "B0EXAMPL09",
        csv=csv,
        lastRatingUpdate=kt(end),
        reviews={
            "lastUpdate": kt(end),
            "ratingCount": [kt(start), 10, kt(end), 12],
            "reviewCount": [kt(start), 2, kt(end), 4],
        },
    )


def _metric(con, asin, version, category, series="bsr_sales_ranks", variant=None):
    sql = """
        SELECT * FROM amazon_derived_metric
        WHERE asin=? AND metric_version=? AND category_key=? AND series_kind=?
    """
    args = [asin, version, category, series]
    if variant:
        sql += " AND definition_variant=?"
        args.append(variant)
    return con.execute(sql, args).fetchone()


def _cli(*args):
    buf = io.StringIO()
    with redirect_stdout(buf):
        code = main(list(args))
    return code, json.loads(buf.getvalue())


if __name__ == "__main__":
    unittest.main()
