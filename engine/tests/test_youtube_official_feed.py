import hashlib
import json
import sqlite3
import sys
import tempfile
import threading
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from collectors.archive import build_cache_payload, classify_cache_file, write_json_atomic
from collectors.feed_honesty import classify_document
from collectors.human_fetch import _host_backoff_until, read_good_cache, write_cache
from collectors.public_sources import load_reddit_sub, parse_reddit_posts
from display_names import FORMULA_VERSION
from youtube_official_feed import DELTA_DISCLOSURE, SOURCE
from youtube_official_feed.http import Exchange
from youtube_official_feed.parse import bucket_anchor_present, official_url, parse_feed
from youtube_official_feed.store import (
    approve_watchlist,
    connect,
    import_xml,
    migrate,
    purge_expired,
    record_fetch,
    rollback,
)

CHANNEL = "UCp7db2pxQKGH1mI7D_Jxedg"
VERSION = "2026-11-25-shadow-review"
EXCERPT = ROOT / "examples" / "youtube_official_feed_excerpt.xml"
WATCHLIST = json.loads((ROOT / "examples" / "youtube_official_feed_watchlist.json").read_text())
REAL = Path("/home/ubuntu/.cursor/projects/agent-repos-dacu-public-signals/uploads/youtube_ebanku_candidate_2175.xml")
NOW = "2026-11-26T00:10:00+00:00"
RETRIEVED = "2026-11-25T15:59:23+00:00"
LABEL = "PUBLIC_FEED_EXCERPT_NOT_PRODUCTION"


def _watch(connection):
    approve_watchlist(connection, WATCHLIST)


def _entry(video, channel, published, views=None, title="Christmas press-on nails"):
    stats = "" if views is None else f'<media:statistics views="{views}"/>'
    return f"""
    <entry>
      <yt:videoId>{video}</yt:videoId>
      <yt:channelId>{channel}</yt:channelId>
      <title>{title}</title>
      <link rel="alternate" href="https://www.youtube.com/watch?v={video}"/>
      <published>{published}</published>
      <updated>{published}</updated>
      <media:group><media:community>{stats}</media:community></media:group>
    </entry>
    """


def _feed(entries: str) -> str:
    return (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<feed xmlns:yt="http://www.youtube.com/xml/schemas/2015" '
        'xmlns:media="http://search.yahoo.com/mrss/" xmlns="http://www.w3.org/2005/Atom">'
        f"<title>SYNTHETIC_EXAMPLE_NOT_PRODUCTION</title>{entries}</feed>"
    )


class ArchiveTests(unittest.TestCase):
    def test_complete_roundtrip_and_legacy_slice_is_not_a_source(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            path = write_cache(
                "https://example.test/item",
                {"url": "https://example.test/item", "http_status": 200, "body": "complete-body"},
                cache_dir=root / "cache",
                raw_dir=root / "raw",
            )
            loaded = read_good_cache("https://example.test/item", cache_dir=root / "cache")
            self.assertEqual(loaded["body"], "complete-body")
            self.assertEqual(loaded["truncated"], 0)
            self.assertEqual(hashlib.sha256(b"complete-body").hexdigest(), loaded["body_sha256"])
            raw = next((root / "raw").iterdir())
            self.assertNotIn("/* truncated */", raw.read_text())
            broken = root / "cache" / "legacy.json"
            broken.write_text('{"body": "unterminated', encoding="utf-8")
            self.assertEqual(classify_cache_file(broken)["status"], "legacy_truncated_invalid")
            self.assertFalse(classify_cache_file(broken)["valid_source"])
            marked = root / "cache" / "marked.json"
            write_json_atomic(marked, {"http_status": 200, "body": "hello\n/* truncated */"})
            self.assertEqual(classify_cache_file(marked)["status"], "legacy_body_marker")
            huge = "x" * 500
            payload = build_cache_payload({"http_status": 200, "body": huge}, char_cap=120)
            self.assertEqual(payload["truncated"], 1)
            self.assertNotIn("body", payload)
            self.assertEqual(payload["body_sha256"], hashlib.sha256(huge.encode()).hexdigest())
            saved = root / "cache" / "huge.json"
            write_json_atomic(saved, payload)
            json.loads(saved.read_text())
            self.assertFalse(classify_cache_file(saved)["valid_source"])
            self.assertTrue(path.exists())

    def test_concurrent_atomic_writes_stay_parseable(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            errors = []

            def worker(index: int):
                try:
                    write_cache(
                        f"https://example.test/{index}",
                        {"url": f"https://example.test/{index}", "http_status": 200, "body": f"body-{index}"},
                        cache_dir=root,
                        raw_dir=root / "raw",
                    )
                except Exception as exc:  # noqa: BLE001
                    errors.append(exc)

            threads = [threading.Thread(target=worker, args=(index,)) for index in range(8)]
            for thread in threads:
                thread.start()
            for thread in threads:
                thread.join()
            self.assertEqual(errors, [])
            files = list(root.glob("*.json"))
            self.assertEqual(len(files), 8)
            for item in files:
                json.loads(item.read_text())


class FeedHonestyTests(unittest.TestCase):
    def test_login_wall_is_missing_not_zero(self):
        html = (ROOT / "examples" / "reddit_login_wall_min.html").read_text()
        self.assertEqual(classify_document(html, "text/html"), "auth_wall")
        self.assertEqual(parse_reddit_posts({"body": html, "content_type": "text/html", "http_status": 200}), [])

        def fetch_json(url, sub):
            return {"url": url, "http_status": 403, "body": "", "error": "HTTP 403", "fetched_at": "t"}

        def fetch_old(url, sub):
            return {"url": url, "http_status": 200, "body": html, "content_type": "text/html", "error": None, "fetched_at": "t"}

        _host_backoff_until.clear()
        data = load_reddit_sub("beauty", fetch_json=fetch_json, fetch_old_rss=fetch_old, browsers_ok=True)
        self.assertEqual(data["error"], "auth_wall")
        self.assertIn("not zero", data["source_extra"])
        _host_backoff_until.clear()
        empty = '<?xml version="1.0"?><rss version="2.0"><channel></channel></rss>'
        empty_data = load_reddit_sub(
            "beauty",
            fetch_json=fetch_json,
            fetch_old_rss=lambda url, sub: {"url": url, "http_status": 200, "body": empty, "error": None, "fetched_at": "t"},
            browsers_ok=True,
        )
        self.assertEqual(empty_data["error"], "empty_feed")


class YoutubeFeedTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.connection = connect(":memory:")
        self.connection.execute("CREATE TABLE prediction_items (sku TEXT PRIMARY KEY, score REAL)")
        self.connection.execute("INSERT INTO prediction_items VALUES ('holiday press-on nails', 17.2)")
        migrate(self.connection)
        _watch(self.connection)

    def tearDown(self):
        self.connection.close()
        self.directory.cleanup()

    def _import(self, xml, retrieved=RETRIEVED, now=NOW, channel=CHANNEL, label=LABEL):
        return import_xml(
            self.connection, xml_text=xml, channel_id=channel, watchlist_version=VERSION,
            retrieved_at=retrieved, now=now, archive_dir=Path(self.directory.name), example_label=label,
        )

    def test_excerpt_is_idempotent_and_does_not_touch_freeze_scores(self):
        xml = EXCERPT.read_text()
        first = self._import(xml)
        second = self._import(xml)
        self.assertEqual(first, second)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM youtube_feed_evidence").fetchone()[0], 1)
        views = {
            row["source_object_id"]: row["value"]
            for row in self.connection.execute(
                "SELECT source_object_id, value, status, published_at, feed_updated_at, retrieved_at FROM youtube_feed_snapshot WHERE metric_key='views_cumulative_snapshot'"
            )
        }
        self.assertEqual(views["d23RxaInO1g"], 8)
        self.assertEqual(views["xHWHamkgG-g"], 113)
        row = self.connection.execute(
            "SELECT published_at, feed_updated_at, retrieved_at, content_tag, maps_to_sku, not_for_scoring FROM youtube_feed_snapshot WHERE source_object_id='d23RxaInO1g'"
        ).fetchone()
        self.assertEqual(row["published_at"], "2026-11-25T14:40:02+00:00")
        self.assertEqual(row["feed_updated_at"], "2026-11-25T15:53:37+00:00")
        self.assertEqual(row["retrieved_at"], RETRIEVED)
        self.assertNotEqual(row["feed_updated_at"], row["retrieved_at"])
        self.assertEqual(row["content_tag"], "press_on_christmas_candidate")
        self.assertEqual(row["maps_to_sku"], 0)
        self.assertEqual(row["not_for_scoring"], 1)
        uploads = self.connection.execute(
            "SELECT status, missing_reason, metric_key FROM youtube_feed_snapshot WHERE metric_key='observed_recent_uploads'"
        ).fetchone()
        self.assertEqual(uploads["status"], "partial")
        self.assertEqual(uploads["metric_key"], "observed_recent_uploads")
        self.assertEqual(self.connection.execute("SELECT score FROM prediction_items").fetchone()[0], 17.2)
        self.assertEqual(FORMULA_VERSION, "director_v1")
        self.assertEqual(self.connection.execute("PRAGMA integrity_check").fetchone()[0], "ok")
        seen = self.connection.execute(
            "SELECT first_available_at FROM youtube_feed_object_seen WHERE source_object_id='d23RxaInO1g'"
        ).fetchone()[0]
        self.assertEqual(seen, NOW)
        later_xml = xml.replace('views="8"', 'views="7"')
        self._import(later_xml, retrieved="2026-11-20T00:00:00+00:00", now="2026-11-26T01:00:00+00:00")
        self.assertEqual(
            self.connection.execute(
                "SELECT first_available_at FROM youtube_feed_object_seen WHERE source_object_id='d23RxaInO1g'"
            ).fetchone()[0],
            NOW,
        )

    def test_cap_missing_conflict_zero_and_channel_guard(self):
        start = datetime(2026, 11, 25, 1, 0, tzinfo=timezone.utc)
        pieces = []
        for index in range(15):
            stamp = (start + timedelta(minutes=20 * index)).isoformat()
            pieces.append(_entry(f"vid{index:02d}aaaaaaaaaaaa", CHANNEL, stamp, views=index))
        parsed = parse_feed(_feed("".join(pieces)), CHANNEL)
        self.assertEqual(parsed["uploads"]["reason"], "feed_cap_shorter_than_24h")
        self.assertEqual(parsed["uploads"]["status"], "partial")
        self.assertFalse(bucket_anchor_present(parsed["entries"], datetime(2026, 11, 25, tzinfo=timezone.utc)))
        missing = _feed(_entry("vidmiss" + "a" * 15, CHANNEL, "2026-11-25T01:00:00+00:00", views=None, title="plain title"))
        evidence = self._import(missing)
        row = self.connection.execute(
            "SELECT value, status FROM youtube_feed_snapshot WHERE evidence_id=? AND metric_key='views_cumulative_snapshot'",
            (evidence,),
        ).fetchone()
        self.assertIsNone(row["value"])
        self.assertEqual(row["status"], "missing")
        zero = _feed(_entry("vidzero" + "b" * 15, CHANNEL, "2026-11-25T01:00:00+00:00", views=0, title="plain title"))
        zero_id = self._import(zero, retrieved="2026-11-25T16:00:00+00:00", now="2026-11-26T00:20:00+00:00")
        zero_row = self.connection.execute(
            "SELECT value, status FROM youtube_feed_snapshot WHERE evidence_id=? AND metric_key='views_cumulative_snapshot'",
            (zero_id,),
        ).fetchone()
        self.assertEqual(zero_row["value"], 0)
        self.assertEqual(zero_row["status"], "observed")
        conflict = _feed(
            _entry("vidsame" + "c" * 15, CHANNEL, "2026-11-25T01:00:00+00:00", views=3, title="plain")
            + _entry("vidsame" + "c" * 15, CHANNEL, "2026-11-25T01:00:00+00:00", views=4, title="plain")
        )
        conflict_id = self._import(conflict, retrieved="2026-11-25T16:10:00+00:00", now="2026-11-26T00:30:00+00:00")
        conflict_row = self.connection.execute(
            "SELECT value, status, missing_reason FROM youtube_feed_snapshot WHERE evidence_id=? AND metric_key='views_cumulative_snapshot'",
            (conflict_id,),
        ).fetchone()
        self.assertIsNone(conflict_row["value"])
        self.assertEqual(conflict_row["status"], "conflict")
        other = "UCBR8-60-B28hp2BmDPdntcQ"
        mismatched = _feed(_entry("vidother" + "d" * 14, other, "2026-11-25T01:00:00+00:00", views=9))
        parsed_mismatch = parse_feed(mismatched, CHANNEL)
        self.assertEqual(parsed_mismatch["entries"], [])
        self.assertEqual(parsed_mismatch["rejected"][0]["reason"], "channel_mismatch")
        gel = _feed(_entry(
            "vidgel" + "e" * 16, CHANNEL, "2026-11-25T01:00:00+00:00", views=1,
            title="Christmas gel nails semicured strips",
        ))
        gel_id = self._import(gel, retrieved="2026-11-25T16:20:00+00:00", now="2026-11-26T00:40:00+00:00")
        self.assertEqual(
            self.connection.execute("SELECT content_tag FROM youtube_feed_snapshot WHERE evidence_id=? AND metric_key='views_cumulative_snapshot'", (gel_id,)).fetchone()[0],
            "gel_or_strip_not_press_on",
        )

    def test_delta_keeps_decrease_and_real_interval(self):
        first = _feed(_entry("viddelta" + "f" * 14, CHANNEL, "2026-11-24T00:00:00+00:00", views=113, title="plain"))
        second = _feed(_entry("viddelta" + "f" * 14, CHANNEL, "2026-11-24T00:00:00+00:00", views=100, title="plain"))
        self._import(first, retrieved="2026-11-25T00:00:00+00:00", now="2026-11-25T00:05:00+00:00")
        self._import(second, retrieved="2026-11-25T06:30:00+00:00", now="2026-11-25T06:35:00+00:00")
        delta = self.connection.execute(
            "SELECT * FROM youtube_feed_cohort_delta WHERE source_object_id=?",
            ("viddelta" + "f" * 14,),
        ).fetchone()
        self.assertEqual(delta["delta_value"], -13)
        self.assertEqual(delta["status"], "partial")
        self.assertAlmostEqual(delta["hours_between"], 6.5)
        self.assertIn("not daily views", delta["disclosure"])
        self.assertIn("not a YouTube", DELTA_DISCLOSURE)
        matched_early = _feed(_entry("vidday" + "g" * 15, CHANNEL, "2026-11-01T00:00:00+00:00", views=10, title="plain"))
        matched_late = _feed(_entry("vidday" + "g" * 15, CHANNEL, "2026-11-01T00:00:00+00:00", views=12, title="plain"))
        self._import(matched_early, retrieved="2026-11-02T00:00:00+00:00", now="2026-11-02T00:00:00+00:00")
        self._import(matched_late, retrieved="2026-11-03T00:00:00+00:00", now="2026-11-03T00:00:00+00:00")
        matched = self.connection.execute(
            "SELECT status, delta_value FROM youtube_feed_cohort_delta WHERE source_object_id=?",
            ("vidday" + "g" * 15,),
        ).fetchone()
        self.assertEqual(matched["status"], "interval_matched")
        self.assertEqual(matched["delta_value"], 2)

    def test_bad_documents_do_not_become_zero_and_http_policy_stops(self):
        wall = (ROOT / "examples" / "reddit_login_wall_min.html").read_text()
        wall_id = self._import(wall)
        self.assertEqual(self.connection.execute("SELECT status, missing_reason FROM youtube_feed_evidence WHERE evidence_id=?", (wall_id,)).fetchone()["missing_reason"], "auth_wall")
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM youtube_feed_snapshot WHERE evidence_id=?", (wall_id,)).fetchone()[0], 0)
        xxe = '<!DOCTYPE foo [<!ENTITY xxe SYSTEM "file:///etc/passwd">]><feed xmlns="http://www.w3.org/2005/Atom">&xxe;</feed>'
        parsed = parse_feed(xxe, CHANNEL)
        self.assertEqual(parsed["kind"], "invalid_xml")
        self.assertEqual(parsed["entries"], [])
        self.assertNotIn("root:", json.dumps(parsed))
        calls = {"n": 0}

        def boom(url, headers):
            calls["n"] += 1
            raise AssertionError("unapproved channel was requested")

        with self.assertRaises(ValueError):
            record_fetch(
                self.connection, channel_id="UCBR8-60-B28hp2BmDPdntcQ", watchlist_version=VERSION,
                transport=boom, now=NOW, archive_dir=Path(self.directory.name), example_label=LABEL,
            )
        self.assertEqual(calls["n"], 0)

        def scripted(responses):
            def transport(url, headers):
                self.assertEqual(url, official_url(CHANNEL))
                item = responses.pop(0)
                item.final_url = item.final_url or url
                return item
            return transport

        stopped = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION,
            transport=scripted([Exchange(status=403, error="HTTP 403")]),
            now="2026-11-26T02:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
        )
        self.assertEqual(stopped["status"], "stopped_auth")
        again = {"n": 0}

        def blocked(url, headers):
            again["n"] += 1
            return Exchange(status=200, body="<feed/>", final_url=url)

        held = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION,
            transport=blocked, now="2026-11-26T03:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
        )
        self.assertEqual(held["status"], "stopped_auth")
        self.assertFalse(held["requested"])
        self.assertEqual(again["n"], 0)
        self.connection.execute("DELETE FROM youtube_feed_source_state")
        waits = []
        limited = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION,
            transport=scripted([
                Exchange(status=429, headers={"Retry-After": "1"}),
                Exchange(status=200, body=_feed(_entry("vidhttp" + "h" * 14, CHANNEL, "2026-11-25T01:00:00+00:00", views=5, title="plain")), content_type="text/xml", etag="abc"),
            ]),
            now="2026-11-26T04:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
            sleep=waits.append,
        )
        self.assertEqual(limited["status"], "stored")
        self.assertEqual(waits, [1.0])
        long_wait = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION,
            transport=scripted([Exchange(status=429, headers={"Retry-After": "60"})]),
            now="2026-11-26T05:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
            sleep=lambda seconds: self.fail(seconds),
        )
        self.assertEqual(long_wait["status"], "rate_limited")
        self.connection.execute("DELETE FROM youtube_feed_source_state")
        failures = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION,
            transport=scripted([Exchange(status=503), Exchange(status=503), Exchange(status=503)]),
            now="2026-11-26T06:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
            sleep=lambda _seconds: None,
        )
        self.assertEqual(failures["status"], "unavailable")
        off = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION,
            transport=scripted([Exchange(status=200, final_url="https://evil.example/feeds/videos.xml")]),
            now="2026-11-26T07:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
        )
        self.assertEqual(off["reason"], "redirect_off_allowlist")

    def test_not_modified_does_not_copy_views_and_retention_rollback(self):
        body = _feed(_entry("vid304" + "i" * 15, CHANNEL, "2026-11-25T01:00:00+00:00", views=4, title="plain"))
        calls = {"n": 0}

        def transport(url, headers):
            calls["n"] += 1
            if calls["n"] == 1:
                self.assertNotIn("If-None-Match", headers)
                return Exchange(status=200, body=body, content_type="text/xml", etag='"v1"', final_url=url)
            self.assertEqual(headers.get("If-None-Match"), '"v1"')
            return Exchange(status=304, etag='"v1"', final_url=url)

        first = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION, transport=transport,
            now="2026-11-26T08:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
        )
        before = self.connection.execute("SELECT COUNT(*) FROM youtube_feed_snapshot WHERE metric_key='views_cumulative_snapshot'").fetchone()[0]
        second = record_fetch(
            self.connection, channel_id=CHANNEL, watchlist_version=VERSION, transport=transport,
            now="2026-11-26T09:00:00+00:00", archive_dir=Path(self.directory.name), example_label=LABEL,
        )
        after = self.connection.execute("SELECT COUNT(*) FROM youtube_feed_snapshot WHERE metric_key='views_cumulative_snapshot'").fetchone()[0]
        self.assertEqual(second["status"], "not_modified")
        self.assertEqual(before, after)
        self.assertEqual(self.connection.execute("SELECT not_modified_of FROM youtube_feed_evidence WHERE evidence_id=?", (second["evidence_id"],)).fetchone()[0], first["evidence_id"])
        removed = purge_expired(self.connection, "2026-12-27T00:00:00+00:00")
        self.assertGreaterEqual(removed, 1)
        self.assertEqual(self.connection.execute("SELECT score FROM prediction_items").fetchone()[0], 17.2)
        rollback(self.connection)
        names = {row[0] for row in self.connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
        self.assertNotIn("youtube_feed_snapshot", names)
        self.assertEqual(self.connection.execute("SELECT score FROM prediction_items").fetchone()[0], 17.2)
        disabled = self.connection.execute("SELECT COUNT(*) FROM schema_migrations WHERE version='8'").fetchone()[0]
        self.assertEqual(disabled, 0)

    def test_real_sample_when_present_and_package_boundary(self):
        if not REAL.exists():
            self.skipTest("local real sample is not in this checkout")
        xml = REAL.read_text(encoding="utf-8")
        parsed = parse_feed(xml, CHANNEL)
        self.assertEqual(len(parsed["entries"]), 15)
        by_id = {entry.video_id: entry for entry in parsed["entries"]}
        self.assertEqual(by_id["d23RxaInO1g"].views, 8)
        self.assertEqual(by_id["xHWHamkgG-g"].views, 113)
        self.assertEqual(parsed["uploads"]["status"], "partial")
        self.assertTrue(bucket_anchor_present(parsed["entries"], datetime(2026, 11, 25, tzinfo=timezone.utc)))
        evidence = self._import(xml, label="PUBLIC_FEED_EXCERPT_NOT_PRODUCTION")
        stored = self.connection.execute(
            "SELECT COUNT(*) FROM youtube_feed_snapshot WHERE evidence_id=? AND metric_key='views_cumulative_snapshot' AND maps_to_sku=0",
            (evidence,),
        ).fetchone()[0]
        self.assertEqual(stored, 15)
        text = "\n".join(path.read_text() for path in (ROOT / "scripts" / "youtube_official_feed").glob("*.py"))
        for banned in ("run_daily_pipeline", "director_model", "backfill_actuals", "freeze_T1"):
            self.assertNotIn(banned, text)
        self.assertEqual(SOURCE, "youtube_official_feed_v1")

    def test_hashes_of_scoring_files_and_watchlist_cannot_grant_coverage(self):
        for relative, digest in {
            "scripts/director_model.py": "3b8726adca11b4dcdd6e357c4c12ce21475a29e6d8f8b925a212e45f2ef3c805",
            "scripts/run_daily_pipeline.py": "d4923ef80a5066ef481ee73a4bfba00ba97c713dfd97d50e90693414b9a48d71",
            "scripts/backfill_actuals.py": "815dd7c4a71a7dac78c9583a8930d7c0aaf0e22bb22f171c19dcd951e95b7338",
        }.items():
            self.assertEqual(hashlib.sha256((ROOT / relative).read_bytes()).hexdigest(), digest)
        bad = json.loads(json.dumps(WATCHLIST))
        bad["channels"][0]["maps_to_sku"] = 1
        with self.assertRaises(ValueError):
            approve_watchlist(self.connection, bad)
        self.assertEqual(self.connection.execute("SELECT COUNT(*) FROM youtube_feed_disabled_source").fetchone()[0], 6)


if __name__ == "__main__":
    unittest.main()
