"""Collectors must not stamp a shared or sample observation as a daily per-SKU series."""
import html
import json
import sqlite3
import sys
import unittest
from pathlib import Path
from urllib.parse import unquote_plus

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / 'scripts'))

from collect_multi_platform import annotate_dod  # noqa: E402
from collectors.human_fetch import _host_backoff_until, mark_backoff  # noqa: E402
from collectors.public_sources import (  # noqa: E402
    SHARED_META_TOPIC,
    build_youtube_rows,
    choose_anchor,
    collect_google_trends,
    instagram_rows,
    load_reddit_sub,
    meta_shared_rows,
    parse_reddit_posts,
    reddit_gap_note,
    trend_payloads,
)
from export_daily_md import snapshot_definition, snapshot_section  # noqa: E402
from export_walkforward import fetch_platform_rows  # noqa: E402

WATCH = json.loads((ENGINE / 'config' / 'watch_topics.json').read_text())
YDAY = '2026-11-06'
AS_OF = '2026-11-07'
NAILS = 'holiday press-on nails'
PJS = 'matching family Christmas PJs flannel'


class TrendBatchTests(unittest.TestCase):
    def test_payloads_cap_at_five_and_keep_the_anchor(self):
        anchor = choose_anchor(WATCH)
        queries = [profile['query'] for profile in WATCH['profiles'].values()]
        payloads = trend_payloads(queries, anchor, 5)
        self.assertEqual(anchor, 'best gifts under 25')
        self.assertEqual([len(payload) for payload in payloads], [5, 5, 2])
        self.assertTrue(all(len(payload) <= 5 and payload.count(anchor) == 1 for payload in payloads))
        self.assertEqual([term for payload in payloads for term in payload if term != anchor], queries)

    def test_exact_query_mapping_does_not_reuse_unrelated_terms(self):
        library = {
            'best gifts under 25': [(YDAY, 50.0)],
            'press on nails christmas': [(YDAY, 80.0)],
        }

        def fetcher(payload, timeframe):
            self.assertLessEqual(len(payload), 5)
            self.assertIn('best gifts under 25', payload)
            self.assertTrue(timeframe.endswith(YDAY))
            return {term: library[term] for term in payload if term in library}

        rows = collect_google_trends(
            AS_OF, WATCH, YDAY, fetcher=fetcher, sleeper=lambda _delay: None,
            pause=lambda *_a, **_k: None, skip_browser=True,
        )
        by_sku = {row['sku_cluster_or_topic']: row for row in rows}
        self.assertEqual(len(rows), 9)
        nails = by_sku[NAILS]
        pjs = by_sku[PJS]
        self.assertEqual(nails['signal_date'], YDAY)
        self.assertEqual(nails['status'], 'observed')
        self.assertEqual(nails['unit'], 'interest_index_vs_anchor')
        self.assertAlmostEqual(nails['value'], 160.0)
        self.assertIn('press on nails christmas', unquote_plus(nails['source_url']))
        self.assertIn('configured query "press on nails christmas"', nails['source_note'])
        self.assertIsNone(pjs['value'])
        self.assertIn('no term match for configured query "christmaspajamas"', pjs['source_note'])
        self.assertIn('NULL', pjs['source_note'])
        self.assertNotEqual(pjs['value'], nails['value'])
        matched = [row for row in rows if row['value'] is not None]
        self.assertEqual([row['sku_cluster_or_topic'] for row in matched], [NAILS])

    def test_429_retries_with_backoff_and_other_errors_do_not(self):
        watch = {
            'search_terms': ['best gifts under 25'],
            'profiles': {
                'gold hoop': {'query': 'gold hoop earrings'},
                NAILS: {'query': 'press on nails christmas'},
            },
        }
        calls = {'n': 0}
        sleeps = []

        def fetcher(payload, _timeframe):
            calls['n'] += 1
            if calls['n'] < 3:
                raise RuntimeError('The request failed: Google returned a response with code 429')
            return {term: [(YDAY, 20.0 if term == 'best gifts under 25' else 10.0)] for term in payload}

        rows = collect_google_trends(
            AS_OF, watch, YDAY, fetcher=fetcher, sleeper=sleeps.append,
            pause=lambda *_a, **_k: None, skip_browser=True, max_attempts=4,
        )
        self.assertEqual(calls['n'], 3)
        self.assertEqual(sleeps, [8.0, 16.0])
        self.assertTrue(all(row['value'] == 50.0 and row['status'] == 'observed' for row in rows))

        calls['n'] = 0

        def broken(_payload, _timeframe):
            calls['n'] += 1
            raise RuntimeError('connection reset')

        missed = collect_google_trends(
            AS_OF, watch, YDAY, fetcher=broken, sleeper=sleeps.append,
            pause=lambda *_a, **_k: None, skip_browser=True, max_attempts=4,
        )
        self.assertEqual(calls['n'], 1)
        self.assertTrue(all(row['value'] is None for row in missed))
        self.assertEqual(len(sleeps), 2)
        self.assertIn('connection reset', missed[0]['source_note'])
        self.assertIn('NULL', missed[0]['source_note'])

    def test_missing_yday_stays_null(self):
        watch = {'search_terms': ['best gifts under 25'], 'profiles': {NAILS: {'query': 'press on nails christmas'}}}

        def fetcher(payload, _timeframe):
            return {term: [('2026-11-05', 10.0)] for term in payload}

        rows = collect_google_trends(
            AS_OF, watch, YDAY, fetcher=fetcher, sleeper=lambda _d: None,
            pause=lambda *_a, **_k: None, skip_browser=True,
        )
        self.assertIsNone(rows[0]['value'])
        self.assertIn('not in interest_over_time', rows[0]['source_note'])
        self.assertIn('NULL', rows[0]['source_note'])


class YouTubeMetaTests(unittest.TestCase):
    def test_youtube_rows_are_collection_date_snapshots(self):
        videos = [
            {'title': {'simpleText': 'press on nails christmas gift'}, 'viewCountText': {'simpleText': '1.2K views'}},
            {'title': {'simpleText': 'holiday press on nails'}, 'viewCountText': {'simpleText': '300 views'}},
        ]
        rows = build_youtube_rows(
            NAILS, {'query': 'press on nails christmas'},
            surl='https://www.youtube.com/results?search_query=press',
            fetched={'fetched_at': '2026-11-07T09:00:00+08:00', 'http_status': 200, 'error': None},
            videos=videos, as_of=AS_OF, today=AS_OF,
        )
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(row['signal_date'] == AS_OF and row['period_start'] == AS_OF for row in rows))
        self.assertTrue(all(row['status'] == 'snapshot' for row in rows))
        self.assertNotIn('video_view_velocity', {row['metric_key'] for row in rows})
        count = next(row for row in rows if row['metric_key'] == 'sampled_video_count_snapshot')
        views = next(row for row in rows if row['metric_key'] == 'sampled_video_views_snapshot')
        self.assertEqual(count['value'], 2.0)
        self.assertEqual(views['value'], 1500.0)
        self.assertTrue(all('cumulative/sample snapshot' in row['source_note'] for row in rows))
        self.assertTrue(all('Not daily views' in row['source_note'] for row in rows))
        past = build_youtube_rows(
            NAILS, {'query': 'press on nails christmas'},
            surl='https://www.youtube.com/results',
            fetched={'fetched_at': 't', 'http_status': 200, 'error': None},
            videos=videos, as_of='2026-11-05', today=AS_OF,
        )
        self.assertTrue(all(row['value'] is None and row['signal_date'] == '2026-11-05' for row in past))
        self.assertIn('no backdated', past[0]['source_note'])

    def test_snapshot_dod_ignores_other_definitions(self):
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        con.execute('create table runs (run_id text, as_of_date text, report_ts text)')
        con.execute('''create table platform_signals (
            run_id text, signal_date text, platform text, channel text, metric_key text,
            sku_cluster_or_topic text, value real, unit text, status text, is_partial integer)''')
        con.execute("insert into runs values ('old','2026-11-07','2026-11-07T09:00:00+08:00')")
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?)",
            ('old', '2026-11-06', 'YouTube', 'public_search', 'video_view_velocity', NAILS, 12, 'matched_video_count', 'observed', 0),
        )
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?)",
            ('old', '2026-11-06', 'YouTube', 'public_search', 'sampled_video_count_snapshot', NAILS, 10, 'search_sample_video_count', 'snapshot', 0),
        )
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?)",
            ('old', '2026-11-05', 'YouTube', 'public_search', 'sampled_video_views_snapshot', NAILS, 1000, 'sampled_lifetime_video_views', 'snapshot', 0),
        )
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?)",
            ('old', '2026-11-06', 'Meta', 'AdLibrary', 'active_ads', 'gold medium/chunky hoop earrings', 50000, 'active_ads_count', 'observed', 0),
        )
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?)",
            ('old', '2026-11-06', 'Meta', 'AdLibrary', 'active_ads_shared_category_proxy', SHARED_META_TOPIC, 40000, 'active_ads_shared_category_proxy', 'snapshot', 0),
        )
        rows = [
            dict(platform='YouTube', channel='public_search', metric_key='sampled_video_count_snapshot',
                 sku_cluster_or_topic=NAILS, unit='search_sample_video_count', status='snapshot',
                 signal_date=AS_OF, value=15, is_partial=0, dod_pct=None, slope_7d=99),
            dict(platform='YouTube', channel='public_search', metric_key='sampled_video_views_snapshot',
                 sku_cluster_or_topic=NAILS, unit='sampled_lifetime_video_views', status='snapshot',
                 signal_date=AS_OF, value=2000, is_partial=0, dod_pct=None, slope_7d=99),
            dict(platform='Meta', channel='AdLibrary', metric_key='active_ads_shared_category_proxy',
                 sku_cluster_or_topic=SHARED_META_TOPIC, unit='active_ads_shared_category_proxy', status='snapshot',
                 signal_date=AS_OF, value=50000, is_partial=0, dod_pct=None, slope_7d=99),
            dict(platform='GoogleTrends', channel='explore', metric_key='search_velocity',
                 sku_cluster_or_topic=NAILS, unit='interest_index_vs_anchor', status='observed',
                 signal_date=YDAY, value=150, is_partial=0, dod_pct=None, slope_7d=None),
        ]
        con.execute(
            "insert into platform_signals values (?,?,?,?,?,?,?,?,?,?)",
            ('old', '2026-11-05', 'GoogleTrends', 'explore', 'search_velocity', NAILS, 100, 'interest_index_vs_anchor', 'observed', 0),
        )
        annotate_dod(con, rows, AS_OF)
        self.assertAlmostEqual(rows[0]['dod_pct'], 50.0)
        self.assertIsNone(rows[0]['slope_7d'])
        self.assertIsNone(rows[1]['dod_pct'])
        self.assertIsNone(rows[1]['slope_7d'])
        self.assertAlmostEqual(rows[2]['dod_pct'], 25.0)
        self.assertAlmostEqual(rows[3]['dod_pct'], 50.0)
        self.assertIsNotNone(rows[3]['slope_7d'])
        con.close()

    def test_meta_is_one_shared_curve_and_instagram_stays_null(self):
        meta = meta_shared_rows(
            {'fetched_at': '2026-11-07T09:00:00+08:00', 'error': None, 'from_cache': False, 'http_status': 200, 'body': 'About 50,000 results'},
            'https://www.facebook.com/ads/library/?q=christmas+gifts', AS_OF, 50000,
        )
        self.assertEqual(len(meta), 1)
        self.assertEqual(meta[0]['value'], 50000.0)
        self.assertEqual(meta[0]['status'], 'snapshot')
        self.assertEqual(meta[0]['signal_date'], AS_OF)
        self.assertEqual(meta[0]['sku_cluster_or_topic'], SHARED_META_TOPIC)
        self.assertNotIn(meta[0]['sku_cluster_or_topic'], WATCH['profiles'])
        self.assertIn('shared category inventory proxy', meta[0]['source_note'])
        self.assertIn('not 9 independent', meta[0]['source_note'])
        ig = instagram_rows(
            WATCH,
            {'fetched_at': 't', 'http_status': 200, 'error': 'login wall', 'body': 'About 50000 results'},
            'https://www.instagram.com/explore/tags/stockingstuffers/',
            YDAY,
        )
        self.assertEqual(len(ig), 9)
        self.assertTrue(all(row['value'] is None for row in ig))
        self.assertTrue(all('NULL, not zero' in row['source_note'] and 'no public dated aggregate' in row['source_note'] for row in ig))

    def test_markdown_shows_snapshots_as_snapshots(self):
        signals = [
            {
                'platform': 'YouTube', 'channel': 'public_search', 'sku_cluster_or_topic': NAILS,
                'period_start': AS_OF, 'period_end': AS_OF, 'signal_date': AS_OF,
                'value': 1500, 'unit': 'sampled_lifetime_video_views', 'dod_pct': None, 'slope_7d': None,
                'status': 'snapshot', 'is_partial': 0, 'is_proxy': 1,
                'source_note': 'cumulative/sample snapshot',
            },
            {
                'platform': 'Meta', 'channel': 'AdLibrary', 'sku_cluster_or_topic': SHARED_META_TOPIC,
                'period_start': AS_OF, 'period_end': AS_OF, 'signal_date': AS_OF,
                'value': 50000, 'unit': 'active_ads_shared_category_proxy', 'dod_pct': None,
                'status': 'snapshot', 'is_partial': 0, 'is_proxy': 1,
                'source_note': 'shared category inventory proxy',
            },
        ]
        text = '\n'.join(snapshot_section(signals))
        self.assertIn('snapshot', text)
        self.assertIn(AS_OF, text)
        self.assertIn('cumulative/sample snapshot (not daily views)', text)
        self.assertIn('shared category inventory proxy (one curve, not independent SKU observations)', text)
        self.assertNotIn('video_view_velocity', text)
        self.assertEqual(snapshot_definition(signals[0]), 'cumulative/sample snapshot (not daily views)')
        self.assertIn('one curve', snapshot_definition(signals[1]))

    def test_walkforward_keeps_snapshot_status(self):
        con = sqlite3.connect(':memory:')
        con.row_factory = sqlite3.Row
        con.execute('create table runs (run_id text, as_of_date text, report_ts text)')
        con.execute('''create table platform_signals (
            run_id text, platform text, channel text, metric_key text,
            sku_cluster_or_topic text, signal_date text, value real, unit text,
            is_partial integer, status text, source_note text, period_start text,
            period_end text, available_at text)''')
        con.execute("insert into runs values ('b','2026-11-12','2026-11-12T02:00:00+08:00')")
        con.execute(
            'insert into platform_signals values (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
            ('b', 'YouTube', 'public_search', 'sampled_video_views_snapshot', 'gold medium/chunky hoop earrings',
             '2026-11-11', 8, 'sampled_lifetime_video_views', 0, 'snapshot', 'cumulative/sample snapshot',
             '2026-11-11', '2026-11-11', '2026-11-11'),
        )
        rows = fetch_platform_rows(con, 'gold medium/chunky hoop earrings', '2026-11-11', '2026-11-11', '2026-11-12')
        self.assertEqual(rows[0]['status'], 'snapshot')
        self.assertEqual(rows[0]['value'], 8)
        con.close()


class RedditFallbackTests(unittest.TestCase):
    def setUp(self):
        _host_backoff_until.clear()

    def tearDown(self):
        _host_backoff_until.clear()

    def test_403_then_old_reddit_rss_respects_backoff(self):
        calls = []
        xml = (
            '<?xml version="1.0"?><rss version="2.0"><channel><item>'
            '<title>late delivery squishy</title><description>refund please</description>'
            '<pubDate>Fri, 06 Nov 2026 01:00:00 GMT</pubDate>'
            '</item></channel></rss>'
        )
        wrapped = '<html><body><pre>' + html.escape(xml) + '</pre></body></html>'

        def fetch_json(url, sub):
            calls.append(('json', url, sub))
            mark_backoff(url, 403, 0)
            return {'url': url, 'http_status': 403, 'body': '', 'error': 'HTTP 403', 'fetched_at': 't'}

        def fetch_old(url, sub):
            calls.append(('pw', url, sub))
            self.assertNotIn('www.reddit.com', url)
            self.assertTrue(url.startswith('https://old.reddit.com/r/beauty/'))
            self.assertTrue(url.endswith('.rss'))
            return {'url': url, 'http_status': 200, 'body': wrapped, 'error': None, 'fetched_at': 't'}

        data = load_reddit_sub('beauty', fetch_json=fetch_json, fetch_old_rss=fetch_old, browsers_ok=True)
        posts = parse_reddit_posts(data)
        self.assertEqual(data['reddit_mode'], 'old_reddit_rss')
        self.assertEqual(len(posts), 1)
        self.assertIn('squishy', posts[0]['title'])
        self.assertGreater(posts[0]['created_utc'], 0)
        self.assertIn('www.reddit.com', _host_backoff_until)
        self.assertNotIn(('pw', 'https://www.reddit.com/r/beauty/new/.rss', 'beauty'), calls)
        self.assertTrue(all('old.reddit.com' in url for kind, url, _sub in calls if kind == 'pw'))

    def test_429_keeps_host_backoff_for_the_next_subreddit(self):
        calls = []

        def fetch_json(url, sub):
            calls.append(('json', url, sub))
            return {'url': url, 'http_status': 403, 'body': '', 'error': 'HTTP 403', 'fetched_at': 't'}

        def fetch_old(url, sub):
            calls.append(('pw', url, sub))
            return {'url': url, 'http_status': 429, 'body': '', 'error': 'HTTP 429', 'fetched_at': 't'}

        blocked = load_reddit_sub('beauty', fetch_json=fetch_json, fetch_old_rss=fetch_old, browsers_ok=True)
        note = reddit_gap_note(blocked)
        self.assertIn('HTTP 403', note)
        self.assertIn('HTTP 429', note)
        self.assertIn('old.reddit.com', note)
        self.assertIn('NULL', note)
        self.assertIn('www.reddit.com', _host_backoff_until)
        self.assertIn('old.reddit.com', _host_backoff_until)
        self.assertTrue(all('www.reddit.com' not in url or url.endswith('.json?limit=100') for _kind, url, _sub in calls))
        calls.clear()
        skipped = load_reddit_sub('TikTokShop', fetch_json=fetch_json, fetch_old_rss=fetch_old, browsers_ok=True)
        self.assertEqual(calls, [])
        skipped_note = reddit_gap_note(skipped)
        self.assertIn('backoff', skipped_note)
        self.assertIn('www.reddit.com', skipped_note)
        self.assertIn('old.reddit.com', skipped_note)
        self.assertIn('NULL', skipped_note)

    def test_success_json_does_not_call_playwright(self):
        def fetch_old(_url, _sub):
            raise AssertionError('playwright fallback should not run')

        data = load_reddit_sub(
            'beauty',
            fetch_json=lambda url, sub: {'url': url, 'http_status': 200, 'body': '{"data":{"children":[]}}', 'error': None, 'fetched_at': 't'},
            fetch_old_rss=fetch_old,
            browsers_ok=True,
        )
        self.assertEqual(data['reddit_mode'], 'json')
        self.assertFalse(data.get('source_extra'))

    def test_missing_browser_skips_playwright_with_reason(self):
        def fetch_old(_url, _sub):
            raise AssertionError('playwright should not run without a browser')

        data = load_reddit_sub(
            'beauty',
            fetch_json=lambda url, sub: {'url': url, 'http_status': 403, 'body': '', 'error': 'HTTP 403', 'fetched_at': 't'},
            fetch_old_rss=fetch_old,
            browsers_ok=False,
            browser_reason='Playwright browser install failed: exit=1',
        )
        note = reddit_gap_note(data)
        self.assertIn('HTTP 403', note)
        self.assertIn('not attempted', note)
        self.assertIn('install failed', note)
        self.assertIn('NULL', note)


if __name__ == '__main__':
    unittest.main()
