"""Public source adapters with human-like browser / TLS fingerprinting.
Raw evidence + explicit NULLs. Never invent volumes. Monthly Newsroom is context only.

Sync Playwright always goes through collectors.playwright_worker (fresh thread),
because the sync API raises inside a running asyncio loop.
"""
from __future__ import annotations
import html, json, logging, os, re, time
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from collectors.human_fetch import fetch_cffi, host_blocked, mark_backoff

SH = timezone(timedelta(hours=8))
NEWS = 'https://newsroom.tiktok.com/whats-shaping-the-holiday-season-on-tiktok-shop?lang=en'
NEWS_PUBLICATION = '2026-10-19'
log = logging.getLogger('collectors.public_sources')

TREND_PAYLOAD_LIMIT = 5
TREND_ANCHOR_FALLBACK = 'christmas gifts'
YT_COUNT_METRIC = 'sampled_video_count_snapshot'
YT_COUNT_UNIT = 'search_sample_video_count'
YT_VIEWS_METRIC = 'sampled_video_views_snapshot'
YT_VIEWS_UNIT = 'sampled_lifetime_video_views'
SHARED_META_TOPIC = 'shared_category:christmas gifts'
SHARED_META_QUERY = 'christmas gifts'
META_METRIC = 'active_ads_shared_category_proxy'
META_UNIT = 'active_ads_shared_category_proxy'


def observation(platform, channel, metric, topic, url, day, **kw):
    return dict(
        platform=platform, channel=channel, metric_key=metric, sku_cluster_or_topic=topic,
        source_url=url, signal_date=day, value=None, unit='unavailable', slope_7d=None,
        dod_pct=None, is_partial=0, is_proxy=1, status='missing',
        source_note='No public dated measurement.', period_start=day, period_end=day,
        available_at=None, **kw,
    )


def _txt(node):
    if not isinstance(node, dict):
        return ''
    return node.get('simpleText', '') or ''.join(x.get('text', '') for x in node.get('runs', []))


def _view_count(text):
    match = re.fullmatch(r'([\d,.]+)\s*([KMB])? views?', text or '', re.I)
    if not match:
        return None
    return float(match[1].replace(',', '')) * {'K': 1000, 'M': 1_000_000, 'B': 1_000_000_000, None: 1}[match[2].upper() if match[2] else None]


def _parse_yt_initial(body: str):
    videos = []
    marker = re.search(r'(?:var )?ytInitialData\s*=\s*', body or '')
    if not marker:
        return videos
    try:
        payload, _ = json.JSONDecoder().raw_decode(body[marker.end():])
    except (ValueError, TypeError):
        return videos

    def visit(node):
        if isinstance(node, dict):
            if 'videoRenderer' in node:
                videos.append(node['videoRenderer'])
            if 'reelItemRenderer' in node:
                videos.append(node['reelItemRenderer'])
            for value in node.values():
                visit(value)
        elif isinstance(node, list):
            for value in node:
                visit(value)
    visit(payload)
    return videos


def _extract_active_ads_from_xhr(xhr_list):
    """Best-effort Active Ads count from Meta Ad Library XHR/GraphQL payloads."""
    for item in xhr_list or []:
        body = item.get('body') or ''
        if not body:
            continue
        for pat in (
            r'"ad_library_main"[^{]*\{[^}]*"count"\s*:\s*(\d+)',
            r'"count"\s*:\s*(\d+)[^}]*"edges"',
            r'"totalCount"\s*:\s*(\d+)',
            r'"ad_count"\s*:\s*(\d+)',
            r'About\s+([\d,]+)\s+results',
        ):
            m = re.search(pat, body, re.I)
            if m:
                try:
                    return float(str(m.group(1)).replace(',', ''))
                except ValueError:
                    continue
        try:
            data = json.loads(body)
        except (ValueError, TypeError):
            continue

        def walk(n):
            if isinstance(n, dict):
                for k, v in n.items():
                    if k in ('count', 'totalCount', 'ad_count', 'results_count') and isinstance(v, (int, float)):
                        return float(v)
                    got = walk(v)
                    if got is not None:
                        return got
            elif isinstance(n, list):
                for v in n:
                    got = walk(v)
                    if got is not None:
                        return got
            return None
        got = walk(data)
        if got is not None:
            return got
    return None


def _extract_tt_trend(xhr_list, body):
    """TikTok Creative Center: try XHR JSON then visible text for a numeric proxy."""
    for item in xhr_list or []:
        b = item.get('body') or ''
        if not b:
            continue
        for pat in (r'"video_views"\s*:\s*(\d+)', r'"publish_cnt"\s*:\s*(\d+)', r'"rank_change"\s*:\s*(-?\d+)', r'"popularity"\s*:\s*([0-9.]+)'):
            m = re.search(pat, b)
            if m:
                try:
                    return float(m.group(1)), f'TikTok CC XHR field via {pat}'
                except ValueError:
                    continue
    return None, 'No dated numeric trend field in Creative Center XHR/HTML'


def _pw_failure(url: str, reason: str) -> dict:
    return {
        'url': url,
        'fetched_at': datetime.now(SH).isoformat(),
        'http_status': None,
        'body': '',
        'xhr': [],
        'error': reason or 'playwright unavailable',
        'from_cache': False,
        'transport': 'playwright',
    }


def choose_anchor(watch) -> str:
    """Stable comparison term included in every Trends payload."""
    for term in (watch or {}).get('search_terms') or []:
        text = (term or '').strip()
        if text:
            return text
    return TREND_ANCHOR_FALLBACK


def trend_payloads(queries, anchor: str, limit: int = TREND_PAYLOAD_LIMIT) -> list[list[str]]:
    """Batches of at most ``limit`` terms. Every batch includes ``anchor`` once."""
    if limit < 1:
        raise ValueError('trend payload limit must be >= 1')
    uniq: list[str] = []
    for query in queries:
        text = (query or '').strip()
        if text and text not in uniq:
            uniq.append(text)
    anchor = (anchor or '').strip()
    others = [query for query in uniq if query != anchor]
    if not anchor:
        return [others[i:i + limit] for i in range(0, len(others), limit)]
    if not others or limit == 1:
        return [[anchor]]
    room = limit - 1
    return [[anchor, *others[i:i + room]] for i in range(0, len(others), room)]


def _on_day(series, yday: str):
    if not series:
        return None
    for day, val in series:
        if str(day)[:10] == yday:
            try:
                return float(val)
            except (TypeError, ValueError):
                return None
    return None


def _trend_retryable(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return '429' in msg or 'too many requests' in msg


def _fetch_trend_payload(fetcher, payload, timeframe, sleeper, max_attempts: int):
    last = 'unknown'
    for attempt in range(max_attempts):
        try:
            frame = fetcher(list(payload), timeframe)
            return frame or {}, None
        except Exception as exc:  # noqa: BLE001 — pytrends surfaces blocks as exceptions
            last = str(exc)
            if not _trend_retryable(exc) or attempt >= max_attempts - 1:
                if _trend_retryable(exc):
                    return {}, f'HTTP 429 / pytrends blocked after backoff ({max_attempts} attempts): {last}'
                return {}, f'pytrends error: {last}'
            delay = min(60.0, 8.0 * (2 ** attempt))
            log.warning('[google-trends] HTTP 429 payload=%s; backoff %.0fs attempt %s/%s', payload, delay, attempt + 1, max_attempts)
            sleeper(delay)
    return {}, f'HTTP 429 / pytrends blocked after backoff: {last}'


def _default_trend_fetcher():
    def fetch(payload, timeframe):
        from pytrends.request import TrendReq
        pytrends = TrendReq(hl='en-US', tz=360, timeout=(10, 30))
        pytrends.build_payload(list(payload), timeframe=timeframe, geo='US')
        df = pytrends.interest_over_time()
        if df is None or getattr(df, 'empty', True):
            return {}
        out = {}
        for term in payload:
            if term not in getattr(df, 'columns', []):
                continue
            series = []
            for idx, val in df[term].items():
                day = idx.date().isoformat() if hasattr(idx, 'date') else str(idx)[:10]
                series.append((day, float(val)))
            out[term] = series
        return out
    return fetch


def _trend_pause(*_args, **_kwargs):
    from collectors.human_fetch import human_pause
    human_pause(6.0, 12.0)


def trends_explore_url(query: str, anchor: str, yday: str) -> str:
    start = (date.fromisoformat(yday) - timedelta(days=6)).isoformat()
    terms = []
    for term in (query, anchor):
        text = (term or '').strip()
        if text and text not in terms:
            terms.append(text)
    return 'https://trends.google.com/trends/explore?' + urlencode({
        'geo': 'US',
        'q': ','.join(terms) if terms else anchor,
        'date': f'{start} {yday}',
    })


def _with_null(text: str) -> str:
    text = (text or '').strip()
    if 'NULL' not in text:
        text += ' NULL, not zero.'
    return text


def collect_google_trends(as_of, watch, yday, *, browsers_ok=True, browser_reason='', fetcher=None, sleeper=None, pause=None, skip_browser=False, max_attempts=4):
    """One comparable index per SKU configured query.

    Each pytrends payload has at most 5 terms and always includes the anchor,
    so batches can be rescaled as query/anchor*100. Results map by exact query
    string. 429 is retried with backoff; other failures stay NULL.
    """
    anchor = choose_anchor(watch)
    pairs = [(sku, ((profile or {}).get('query') or '').strip()) for sku, profile in (watch.get('profiles') or {}).items()]
    queries = [query for _, query in pairs if query]
    payloads = trend_payloads(queries, anchor, TREND_PAYLOAD_LIMIT)
    start = (date.fromisoformat(yday) - timedelta(days=6)).isoformat()
    timeframe = f'{start} {yday}'
    warm = {'error': None, 'fetched_at': datetime.now(SH).isoformat()}
    if not skip_browser:
        if not browsers_ok:
            warm['error'] = browser_reason or 'playwright browser unavailable'
        else:
            try:
                from collectors.playwright_worker import run_browser

                def _warm(browser):
                    return browser.open_and_capture(
                        'https://trends.google.com/trends/explore?geo=US',
                        wait_ms=5000,
                        referer='https://www.google.com/',
                    )
                captured = run_browser(_warm) or {}
                warm = {'error': captured.get('error'), 'fetched_at': captured.get('fetched_at') or warm['fetched_at']}
            except Exception as exc:  # noqa: BLE001
                warm['error'] = str(exc)
    fetcher = fetcher or _default_trend_fetcher()
    sleeper = sleeper or time.sleep
    pause = pause or _trend_pause
    values: dict[str, tuple[float, float, float]] = {}
    errors: dict[str, str] = {}
    sku_queries = set(queries)
    for payload in payloads:
        pause()
        frame, err = _fetch_trend_payload(fetcher, payload, timeframe, sleeper, max_attempts)
        targets = [term for term in payload if term in sku_queries]
        if err:
            for term in targets:
                errors.setdefault(term, err)
            continue
        if anchor not in frame:
            msg = f'anchor term "{anchor}" missing from payload response; columns={sorted(frame)}. NULL, not zero.'
            for term in targets:
                errors.setdefault(term, msg)
            continue
        anchor_raw = _on_day(frame.get(anchor), yday)
        if anchor_raw is None:
            msg = f'yday {yday} not in interest_over_time for anchor "{anchor}". NULL, not zero.'
            for term in targets:
                errors.setdefault(term, msg)
            continue
        if anchor_raw == 0:
            msg = f'anchor "{anchor}" interest is 0 on {yday}; batch not comparable. NULL, not zero.'
            for term in targets:
                errors.setdefault(term, msg)
            continue
        for term in targets:
            series = frame.get(term)
            if series is None:
                errors[term] = (
                    f'no term match for configured query "{term}"; '
                    f'response terms were {sorted(frame)}. NULL, not zero.'
                )
                continue
            raw = _on_day(series, yday)
            if raw is None:
                errors[term] = f'yday {yday} not in interest_over_time for configured query "{term}". NULL, not zero.'
                continue
            values[term] = (raw / anchor_raw * 100.0, raw, anchor_raw)
            errors.pop(term, None)

    warm_err = warm.get('error')
    out = []
    for sku, query in pairs:
        url = trends_explore_url(query, anchor, yday)
        row = observation('GoogleTrends', 'explore', 'search_velocity', sku, url, yday)
        row['as_of_ts'] = warm.get('fetched_at') or datetime.now(SH).isoformat()
        if not query:
            row['source_note'] = 'SKU has no configured query. NULL, not zero.'
            out.append(row)
            continue
        if query in values:
            scaled, raw, anchor_raw = values[query]
            note = (
                f'pytrends interest_over_time for configured query "{query}" relative to anchor "{anchor}" '
                f'(definition=query/anchor*100; raw_query={raw}; raw_anchor={anchor_raw}; scaled={scaled}). '
                f'Timeframe {timeframe} geo=US. Not search volume.'
            )
            if warm_err:
                note += f' NID warm={warm_err}.'
            row.update(
                value=scaled, unit='interest_index_vs_anchor', status='observed',
                available_at=as_of, is_proxy=1, source_note=note,
            )
        else:
            reason = errors.get(query) or f'no term match for configured query "{query}". NULL, not zero.'
            if warm_err:
                reason = f'warm={warm_err}; {reason}'
            row['source_note'] = _with_null(reason)
        out.append(row)
    return out


def build_youtube_rows(sku, profile, *, surl, fetched, videos, as_of, today):
    """Search-sample count and cumulative views on the collection date.

    These are snapshots, not daily view velocity. ``signal_date`` is ``as_of``.
    """
    fetched = fetched or {}
    videos = videos or []
    count_row = observation('YouTube', 'public_search', YT_COUNT_METRIC, sku, surl, as_of)
    views_row = observation('YouTube', 'public_search', YT_VIEWS_METRIC, sku, surl, as_of)
    fetched_at = fetched.get('fetched_at') or datetime.now(SH).isoformat()
    for row in (count_row, views_row):
        row['as_of_ts'] = fetched_at
        row['period_start'] = as_of
        row['period_end'] = as_of
        row['is_proxy'] = 1
    if as_of != today:
        note = (
            'Historical as_of — no backdated search sample. '
            'cumulative/sample snapshot not collected for a past day. NULL, not zero.'
        )
        count_row['source_note'] = note
        views_row['source_note'] = note
        return [count_row, views_row]
    tokens = [
        t for t in re.findall('[a-z]+', ((profile or {}).get('query') or '').lower())
        if len(t) > 3 and t not in ('gifts', 'christmas', 'family', 'holiday', 'ready', 'stock')
    ]
    matched = [video for video in videos if any(token in _txt(video.get('title', {})).lower() for token in tokens)]
    relevant = matched or videos[:12]
    counts = [count for count in (_view_count(_txt(video.get('viewCountText', {}))) for video in relevant) if count is not None]
    err = fetched.get('error')
    if counts and not err:
        n = len(counts)
        total = float(sum(counts))
        count_row.update(
            value=float(n), unit=YT_COUNT_UNIT, status='snapshot', is_partial=0, available_at=as_of,
            source_note=(
                'cumulative/sample snapshot: search-sample video count for this SKU query on the collection date. '
                f'n={n}. Not daily views. Window={as_of}. '
                'DoD only versus the previous calendar-day snapshot of this same metric definition.'
            ),
        )
        views_row.update(
            value=total, unit=YT_VIEWS_UNIT, status='snapshot', is_partial=0, available_at=as_of,
            source_note=(
                'cumulative/sample snapshot: sum of lifetime view counts on the collected search sample. '
                f'n={n}. Not daily views. Window={as_of} (collection date, not the previous UTC day). '
                'DoD only versus the previous calendar-day snapshot of this same metric definition.'
            ),
        )
    else:
        note = (
            'YouTube search sample NULL, not zero. '
            f'status={fetched.get("http_status")} err={err} '
            f'videos_parsed={len(videos)} countable={len(counts)}. '
            'cumulative/sample snapshot was not observed.'
        )
        count_row['source_note'] = note
        views_row['source_note'] = note
    return [count_row, views_row]


def meta_shared_rows(meta_data, meta_url, as_of, ads_count):
    """One shared category inventory curve, not one copy per SKU."""
    meta_data = meta_data or {}
    row = observation('Meta', 'AdLibrary', META_METRIC, SHARED_META_TOPIC, meta_url, as_of)
    row['as_of_ts'] = meta_data.get('fetched_at')
    row['period_start'] = as_of
    row['period_end'] = as_of
    base = (
        'shared category inventory proxy: one Ad Library curve for keyword '
        f'"{SHARED_META_QUERY}", not 9 independent SKU observations. '
        f'Window={as_of} (collection date). '
        'DoD only versus the previous calendar-day snapshot of this same definition. '
        f'transport={meta_data.get("transport") or "playwright"} cache={meta_data.get("from_cache")}'
    )
    if ads_count is not None and not meta_data.get('error'):
        note = base
        if meta_data.get('archive_note'):
            note = f"{meta_data['archive_note']}. {base}"
        row.update(
            value=float(ads_count), unit=META_UNIT, status='snapshot', is_partial=0,
            is_proxy=1, available_at=as_of, source_note=note,
        )
    else:
        block = ''
        transport = meta_data.get('transport') or 'playwright'
        if meta_data.get('http_status') == 403 and transport == 'playwright':
            block = (
                'Web UI HTTP 403 is the Ad Library page refusing this client. It is not retried. '
                'Graph ads_archive does not return US commercial ads that never reached the EU '
                '(political/issue ads, or ads that reached the EU, are what that API returns), '
                'so META_AD_LIBRARY_TOKEN cannot fill this US christmas-gifts inventory curve. '
            )
        archive = meta_data.get('archive_note') or ''
        row['source_note'] = (
            'Meta Ad Library shared category inventory proxy NULL, not zero, and not per-SKU. '
            f'status={meta_data.get("http_status")} err={meta_data.get("error")}. {block}{archive} {base}'
        )
    return [row]


def parse_ads_archive_total(payload):
    """Return an explicit archive total, never the length of one page."""
    if not isinstance(payload, dict):
        return None, 'ads_archive body was not a JSON object. NULL, not zero.'
    err = payload.get('error')
    if isinstance(err, dict):
        return None, f"ads_archive error {err.get('code')}: {err.get('message') or 'error'}. NULL, not zero."
    summary = payload.get('summary')
    if isinstance(summary, dict):
        total = summary.get('total_count')
        if isinstance(total, (int, float)) and not isinstance(total, bool):
            return float(total), 'summary.total_count'
    total = payload.get('total_count')
    if isinstance(total, (int, float)) and not isinstance(total, bool):
        return float(total), 'total_count'
    page = payload.get('data')
    n = len(page) if isinstance(page, list) else 0
    return None, (
        f'ads_archive returned {n} ads on this page and no total field. '
        'Page length is not the category inventory. '
        'US commercial ads that never reached the EU are outside this API. NULL, not zero.'
    )


def fetch_meta_ads_archive(query, token, *, get):
    """One Graph ads_archive call. The token stays in the Authorization header, not the URL."""
    url = 'https://graph.facebook.com/v21.0/ads_archive?' + urlencode({
        'search_terms': query,
        'ad_reached_countries': '["US"]',
        'ad_active_status': 'ACTIVE',
        'ad_type': 'ALL',
        'fields': 'id',
        'limit': '1',
    })
    fetched_at = datetime.now(SH).isoformat()
    status, text = get(url, {'Authorization': 'Bearer ' + token})
    base = {
        'url': url, 'http_status': status, 'xhr': [], 'from_cache': False,
        'transport': 'graph_ads_archive', 'fetched_at': fetched_at,
    }
    if status not in (200, 201):
        note = f'HTTP {status}'
        try:
            err = json.loads(text or '').get('error')
        except (ValueError, AttributeError):
            err = None
        if isinstance(err, dict) and err.get('message'):
            note = f"HTTP {status}: {err.get('message')}"
        base.update(body='', error=note, archive_note='')
        return base, None
    try:
        payload = json.loads(text or '')
    except ValueError:
        base.update(body='', error='ads_archive body was not JSON', archive_note='')
        return base, None
    total, note = parse_ads_archive_total(payload)
    base.update(body=text or '', error=None, archive_note=note)
    return base, total


def instagram_rows(watch, ig_data, ig_url, day):
    """Instagram has no public dated aggregate. Always NULL, even if the page shows a number."""
    ig_data = ig_data or {}
    note = (
        'Instagram explore has no public dated aggregate (login wall or no time series). '
        'NULL, not zero. '
        f'http_status={ig_data.get("http_status")} err={ig_data.get("error") or "no dated public aggregate"}.'
    )
    rows = []
    for sku in (watch.get('profiles') or {}):
        row = observation('Meta', 'Instagram', 'reels_keyword_velocity', sku, ig_url, day)
        row['as_of_ts'] = ig_data.get('fetched_at')
        row['source_note'] = note
        rows.append(row)
    return rows


def _reddit_listing_ok(data) -> bool:
    if not data or data.get('error'):
        return False
    if data.get('http_status') not in (200, 201):
        return False
    return bool(data.get('body'))


def _status_reason(label: str, data) -> str:
    data = data or {}
    status = data.get('http_status')
    err = data.get('error')
    if status in (403, 429):
        return f'{label} HTTP {status}'
    if status:
        return f'{label} HTTP {status}' + (f' ({err})' if err else '')
    return f'{label} error: {err or "no response"}'


def unwrap_playwright_rss(body: str) -> str:
    """Chromium sometimes wraps RSS XML in an HTML <pre> with escaped markup."""
    if not body:
        return ''
    head = body[:800].lower()
    if '<entry' in body or '<item' in body or '<feed' in head or '<rss' in head:
        return body
    match = re.search(r'<pre[^>]*>([\s\S]*?)</pre>', body, re.I)
    if not match:
        return body
    unescaped = html.unescape(match.group(1))
    lowered = unescaped[:800].lower()
    if '<entry' in unescaped or '<item' in unescaped or '<feed' in lowered or '<rss' in lowered:
        return unescaped
    return body


def reddit_gap_note(data) -> str:
    data = data or {}
    extra = data.get('source_extra')
    err = data.get('error')
    if extra:
        text = str(extra)
    elif err:
        text = str(err)
    else:
        text = 'Public listing cannot fully cover the target UTC day or no relevant sample.'
        if data.get('fetch_note'):
            text += ' Fetch path: ' + str(data['fetch_note'])
    return _with_null(text)


ANON_JSON_SKIPPED = (
    'Unauthenticated www.reddit.com .json is not requested. '
    'Reddit answers logged-out JSON with HTTP 403, and repeating that call is what exhausted the IP budget and returned HTTP 429 on RSS.'
)


def _reddit_gap(url, reasons, now):
    return {
        'url': url, 'fetched_at': now, 'http_status': None, 'body': '',
        'error': None, 'from_cache': False, 'listing_url': url,
        'source_extra': '; '.join(reasons),
    }


def reddit_app_credentials():
    """Already-approved script app. Missing any one of the three means no OAuth call."""
    client_id = os.environ.get('REDDIT_CLIENT_ID', '').strip()
    client_secret = os.environ.get('REDDIT_CLIENT_SECRET', '').strip()
    user_agent = os.environ.get('REDDIT_USER_AGENT', '').strip()
    if client_id and client_secret and user_agent:
        return client_id, client_secret, user_agent
    return None


def fetch_reddit_oauth_listing(sub, client_id, client_secret, user_agent, *, post, get, cache, pause=None):
    """Application-only OAuth. The secret and bearer token are not written into the result."""
    if cache.get('dead'):
        return dict(cache['dead'])
    token = cache.get('token')
    if not token or time.monotonic() >= (cache.get('exp') or 0):
        status, text = post(
            'https://www.reddit.com/api/v1/access_token',
            {'grant_type': 'client_credentials'},
            {'User-Agent': user_agent},
            (client_id, client_secret),
        )
        if status != 200:
            dead = {
                'url': 'https://www.reddit.com/api/v1/access_token',
                'http_status': status, 'body': '', 'error': f'HTTP {status}',
                'fetched_at': datetime.now(SH).isoformat(), 'transport': 'reddit_oauth',
            }
            cache['dead'] = dead
            return dict(dead)
        try:
            payload = json.loads(text or '')
        except ValueError:
            dead = {
                'url': 'https://www.reddit.com/api/v1/access_token',
                'http_status': status, 'body': '', 'error': 'token response was not JSON',
                'fetched_at': datetime.now(SH).isoformat(), 'transport': 'reddit_oauth',
            }
            cache['dead'] = dead
            return dict(dead)
        token = payload.get('access_token')
        if not token:
            dead = {
                'url': 'https://www.reddit.com/api/v1/access_token',
                'http_status': status, 'body': '', 'error': 'token response had no access_token',
                'fetched_at': datetime.now(SH).isoformat(), 'transport': 'reddit_oauth',
            }
            cache['dead'] = dead
            return dict(dead)
        try:
            ttl = float(payload.get('expires_in') or 3600)
        except (TypeError, ValueError):
            ttl = 3600.0
        cache['token'] = token
        cache['exp'] = time.monotonic() + max(0.0, ttl - 60.0)
    if pause:
        pause()
    listing_url = f'https://oauth.reddit.com/r/{sub}/new?limit=100&raw_json=1'
    status, text = get(listing_url, {'Authorization': 'bearer ' + token, 'User-Agent': user_agent})
    return {
        'url': listing_url,
        'http_status': status,
        'body': text or '' if status in (200, 201) else '',
        'error': None if status in (200, 201) else f'HTTP {status}',
        'fetched_at': datetime.now(SH).isoformat(),
        'transport': 'reddit_oauth',
    }


def load_reddit_sub(sub, *, fetch_json=None, fetch_old_rss=None, fetch_oauth=None, browsers_ok=True, browser_reason=''):
    """One polite listing. OAuth when an approved app is configured; otherwise one RSS.

    Logged-out .json is not called. A 403 there is Reddit's shutdown of that
    endpoint, and the retries were the request burst behind the RSS 429.
    An OAuth failure does not fall through to a page fetch. Host backoff is kept.
    ``fetch_json`` is accepted so older callers still import, and is not used.
    """
    del fetch_json  # anonymous JSON is a permanent 403; calling it spends the RSS budget
    old_url = f'https://old.reddit.com/r/{sub}/new/.rss'
    now = datetime.now(SH).isoformat()
    if fetch_oauth is not None:
        oauth_probe = 'https://oauth.reddit.com/r/' + sub + '/new'
        if host_blocked(oauth_probe):
            return _reddit_gap(oauth_probe, [
                'oauth.reddit.com host backoff in effect; no further Reddit request. NULL, not zero.',
            ], now)
        try:
            data = fetch_oauth(sub) or {}
        except Exception as exc:  # noqa: BLE001
            return _reddit_gap(oauth_probe, [
                f'oauth.reddit.com failed: {exc}. Anonymous JSON and RSS were not used.',
            ], now)
        data = data or {}
        data.setdefault('url', oauth_probe)
        data.setdefault('fetched_at', now)
        if _reddit_listing_ok(data):
            data['reddit_mode'] = 'oauth'
            data['listing_url'] = data.get('url')
            data['error'] = None
            return data
        status = data.get('http_status')
        if status in (403, 429):
            mark_backoff(data.get('url') or oauth_probe, status, 0)
        data['source_extra'] = (
            'oauth.reddit.com failed; anonymous JSON and RSS were not used. '
            + _status_reason('oauth.reddit.com', data)
        )
        data['listing_url'] = data.get('url') or oauth_probe
        return data

    reasons = [ANON_JSON_SKIPPED]
    if host_blocked(old_url):
        reasons.append('old.reddit.com host backoff in effect; skipped Playwright RSS')
        return _reddit_gap(old_url, reasons, now)
    if not browsers_ok:
        reasons.append('old.reddit.com RSS via Playwright not attempted: ' + (browser_reason or 'browser unavailable'))
        return _reddit_gap(old_url, reasons, now)
    if fetch_old_rss is None:
        reasons.append('old.reddit.com RSS fetcher missing')
        return _reddit_gap(old_url, reasons, now)
    try:
        pw = fetch_old_rss(old_url, sub) or {}
    except Exception as exc:  # noqa: BLE001
        reasons.append(f'old.reddit.com RSS via Playwright failed: {exc}')
        return _reddit_gap(old_url, reasons, now)
    pw.setdefault('url', old_url)
    pw.setdefault('fetched_at', now)
    body = unwrap_playwright_rss(pw.get('body') or '')
    pw_status = pw.get('http_status')
    if pw_status in (403, 429):
        mark_backoff(old_url, pw_status, 0)
    usable = bool(body) and ('<entry' in body or '<item' in body) and not pw.get('error') and pw_status in (200, 201)
    if usable:
        out = dict(pw)
        out['body'] = body
        out['reddit_mode'] = 'old_reddit_rss'
        out['error'] = None
        out['listing_url'] = old_url
        return out
    reasons.append(_status_reason('old.reddit.com RSS via Playwright', pw))
    pw['source_extra'] = '; '.join(reasons)
    pw['listing_url'] = old_url
    return pw


def parse_reddit_posts(data) -> list:
    if not _body_usable(data):
        return []
    body = unwrap_playwright_rss(data.get('body') or '')
    mode = data.get('reddit_mode') or ''
    posts = []
    if mode in ('rss', 'old_reddit_rss') or body.lstrip().startswith('<?xml') or '<feed' in body[:240] or '<rss' in body[:240]:
        chunks = re.findall(r'<entry[\s\S]*?</entry>', body) or re.findall(r'<item[\s\S]*?</item>', body)
        for block in chunks:
            title_m = re.search(r'<title[^>]*>([\s\S]*?)</title>', block)
            content_m = re.search(r'<(?:content|description|summary)[^>]*>([\s\S]*?)</(?:content|description|summary)>', block)
            updated_m = re.search(r'<(?:updated|published|pubDate)[^>]*>([^<]+)</', block)
            ts = 0.0
            if updated_m:
                raw_ts = updated_m.group(1).strip()
                try:
                    from email.utils import parsedate_to_datetime
                    ts = parsedate_to_datetime(raw_ts).timestamp()
                except Exception:
                    try:
                        ts = datetime.fromisoformat(raw_ts.replace('Z', '+00:00')).timestamp()
                    except Exception:
                        ts = 0.0
            posts.append({
                'title': html.unescape(re.sub(r'<[^>]+>', '', title_m.group(1) if title_m else '')),
                'selftext': html.unescape(re.sub(r'<[^>]+>', '', content_m.group(1) if content_m else '')),
                'created_utc': ts,
                'num_comments': 0,
            })
        return posts
    try:
        raw = body
        if '<html' in raw[:200].lower():
            match = re.search(r'(\{\s*"kind"\s*:\s*"Listing"[\s\S]+)', raw)
            raw = match.group(1) if match else raw
        return [post['data'] for post in json.loads(raw)['data']['children']]
    except (ValueError, KeyError, TypeError):
        return []


def _body_usable(data) -> bool:
    if not data or not data.get('body'):
        return False
    if data.get('reddit_mode') in ('rss', 'old_reddit_rss', 'playwright_json'):
        return True
    return not data.get('error')


def _reddit_rows(sub, data, posts, watch, as_of, yday):
    rurl = data.get('listing_url') or f'https://www.reddit.com/r/{sub}/new.json?limit=100'
    start = datetime.fromisoformat(yday).replace(tzinfo=timezone.utc).timestamp()
    end = start + 86400
    coverage = bool(posts) and min((p.get('created_utc') or end) for p in posts) <= start
    week_start = start - 6 * 86400
    rows = []
    for sku, profile in watch['profiles'].items():
        row = observation('Reddit', sub, 'complaint_share', sku, rurl, yday)
        row.update(as_of_ts=data.get('fetched_at'), unit='fraction')
        tokens = [t for t in re.findall('[a-z]+', (profile.get('query') or '').lower()) if len(t) > 3]
        if coverage and not data.get('error'):
            selected = [
                p for p in posts
                if start <= (p.get('created_utc') or 0) < end
                and any(t in ((p.get('title') or '') + ' ' + (p.get('selftext') or '')).lower() for t in tokens)
            ]
            if selected:
                negative = sum(
                    any(k in ((p.get('title') or '') + ' ' + (p.get('selftext') or '')).lower() for k in watch['risk_keywords'])
                    for p in selected
                )
                mode = data.get('reddit_mode') or 'json'
                note = (
                    f'{mode} public listing; UTC day covered; keyword-matched n={len(selected)}, '
                    f'complaint-keyword n={negative}. Lexical proxy, not return rate.'
                )
                if data.get('fetch_note'):
                    note += f' Fallback: {data["fetch_note"]}.'
                row.update(value=negative / len(selected), status='observed', available_at=as_of, source_note=note)
        if row['value'] is None:
            row['source_note'] = reddit_gap_note(data)
        rows.append(row)

        heat = observation('Reddit', sub, 'post_heat_7d', sku, rurl, yday)
        heat.update(as_of_ts=data.get('fetched_at'), unit='posts')
        week_posts = [
            p for p in posts
            if week_start <= (p.get('created_utc') or 0) < end
            and any(t in ((p.get('title') or '') + ' ' + (p.get('selftext') or '')).lower() for t in tokens)
        ]
        if week_posts and not data.get('error'):
            comments = sum(int(p.get('num_comments') or 0) for p in week_posts)
            mode = data.get('reddit_mode') or 'json'
            heat.update(
                value=float(len(week_posts)), status='observed', available_at=as_of,
                source_note=(
                    f'{mode} last-7d matched posts n={len(week_posts)}, comments_sum={comments}. '
                    'Sample of /new, not full subreddit volume.'
                ),
            )
        else:
            if data.get('error') or data.get('source_extra'):
                heat['source_note'] = reddit_gap_note(data)
            else:
                heat['source_note'] = 'No 7d keyword-matched Reddit posts in sample. NULL, not zero.'
        rows.append(heat)
    return rows


def _graph_get(url, headers):
    from curl_cffi import requests as creq
    resp = creq.get(url, headers=headers, timeout=25)
    return resp.status_code, resp.text or ''


def _reddit_post(url, data, headers, auth):
    from curl_cffi import requests as creq
    resp = creq.post(url, data=data, headers=headers, auth=auth, timeout=25)
    return resp.status_code, resp.text or ''


def _reddit_get(url, headers):
    from curl_cffi import requests as creq
    resp = creq.get(url, headers=headers, timeout=25)
    return resp.status_code, resp.text or ''


def collect(as_of, watch):
    yday = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
    today = date.today().isoformat()
    out = []
    try:
        from collectors.playwright_worker import ensure_chromium_installed
        browsers_ok, browser_reason = ensure_chromium_installed()
    except Exception as exc:  # noqa: BLE001 — a self-check must not kill the daily run
        browsers_ok, browser_reason = False, f'playwright self-check failed: {exc}'

    news = fetch_cffi(NEWS, referer='https://www.google.com/', tag='news')
    text = BeautifulSoup(news.get('body') or '', 'html.parser').get_text(' ', strip=True)
    context = [
        ('matching family Christmas PJs flannel', 'christmaspajamas', 297),
        ('holiday press-on nails', 'fall nails', 333),
        ('soft squishy multipack', 'squishy toys', 149),
        ('gold medium/chunky hoop earrings', 'gold jewelry', 1134),
        ('opal/birthstone/initial pendant (ready-stock)', 'opal rings', 825),
        ('friendship/beaded charm bracelet', 'friendshipbracelet', 120),
    ]
    for sku, term, expected in context:
        row = observation('TikTok', 'Newsroom', 'reported_monthly_growth', sku, NEWS, '2026-09-30')
        row.update(period_start='2026-08-01', period_end='2026-09-30', available_at=NEWS_PUBLICATION,
                   as_of_ts=news.get('fetched_at'), unit='percent_month_over_month')
        match = re.search(re.escape(term) + r'.{0,130}?' + re.escape(f'{expected:,}') + r'%', text, re.I)
        if not news.get('error') and match and as_of >= NEWS_PUBLICATION:
            row.update(
                value=float(expected), status='context',
                source_note=f'Official reported August→September 2026 monthly growth for {term}; not November growth, not daily DoD. Dated release syndicated 2026-10-19. Context excluded from daily resonance. transport={news.get("transport")}',
            )
        else:
            row['source_note'] = news.get('error') or f'Could not verify literal {term} / {expected}% in fetched public page.'
        out.append(row)

    creative_url = 'https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en'
    meta_url = 'https://www.facebook.com/ads/library/?' + urlencode({
        'active_status': 'active', 'ad_type': 'all', 'country': 'US',
        'q': SHARED_META_QUERY, 'search_type': 'keyword_unordered',
    })
    yt_url = 'https://www.youtube.com/results?' + urlencode({'search_query': 'shorts best gifts under 25 christmas 2026'})
    ig_url = 'https://www.instagram.com/explore/tags/stockingstuffers/'
    meta_token = os.environ.get('META_AD_LIBRARY_TOKEN', '').strip()
    ads_count = None
    meta_data = None
    if meta_token:
        try:
            meta_data, ads_count = fetch_meta_ads_archive(
                SHARED_META_QUERY, meta_token, get=_graph_get,
            )
        except Exception as exc:  # noqa: BLE001
            meta_data = _pw_failure(meta_url, f'ads_archive request failed: {exc}')
            meta_data['transport'] = 'graph_ads_archive'
            ads_count = None
    if not browsers_ok:
        reason = browser_reason or 'playwright browser unavailable'
        if meta_data is None:
            meta_data = _pw_failure(meta_url, reason)
        tt_data = _pw_failure(creative_url, reason)
        yt_data = _pw_failure(yt_url, reason)
        ig_data = _pw_failure(ig_url, reason)
    else:
        box: dict = {}
        try:
            from collectors.playwright_worker import run_browser

            def _grab(browser):
                if not meta_token:
                    box['meta'] = browser.open_and_capture(
                        meta_url, wait_ms=10000,
                        capture_substrings=['graphql', 'ads/library', 'api/v', 'ad_library'],
                        referer='https://www.facebook.com/',
                    )
                box['tt'] = browser.open_and_capture(
                    creative_url, wait_ms=10000,
                    capture_substrings=['api/', 'creative', 'hashtag', 'graphql', 'aweme'],
                    referer='https://ads.tiktok.com/',
                )
                box['yt'] = browser.open_and_capture(
                    yt_url, wait_ms=8000,
                    capture_substrings=['youtubei', 'results'],
                    referer='https://www.youtube.com/',
                )
                box['ig'] = browser.open_and_capture(
                    ig_url, wait_ms=6000,
                    capture_substrings=['graphql', 'api/v1'],
                    referer='https://www.instagram.com/',
                )
                return box
            run_browser(_grab)
            grab_err = None
        except Exception as exc:  # noqa: BLE001
            grab_err = str(exc)
        if meta_data is None:
            meta_data = box.get('meta') or _pw_failure(meta_url, grab_err or 'playwright returned no Meta capture')
        tt_data = box.get('tt') or _pw_failure(creative_url, grab_err or 'playwright returned no TikTok capture')
        yt_data = box.get('yt') or _pw_failure(yt_url, grab_err or 'playwright returned no YouTube capture')
        ig_data = box.get('ig') or _pw_failure(ig_url, grab_err or 'playwright returned no Instagram capture')

    if not meta_token:
        ads_count = _extract_active_ads_from_xhr((meta_data or {}).get('xhr'))
    if ads_count is None and meta_data and meta_data.get('body') and not meta_token:
        matched = re.search(r'(?:About\s+)?([\d,]+)\s+result', meta_data['body'], re.I)
        if matched:
            try:
                ads_count = float(matched.group(1).replace(',', ''))
            except ValueError:
                ads_count = None
    out.extend(meta_shared_rows(meta_data, meta_url, as_of, ads_count))

    tt_val, tt_note = _extract_tt_trend((tt_data or {}).get('xhr'), (tt_data or {}).get('body'))
    for sku in watch['profiles']:
        for metric in ('content_velocity', 'engagement_rate'):
            row = observation('TikTok', 'CreativeCenter', metric, sku, creative_url, yday)
            row['as_of_ts'] = (tt_data or {}).get('fetched_at')
            if tt_val is not None and metric == 'content_velocity' and not (tt_data or {}).get('error'):
                row.update(
                    value=tt_val, unit='cc_proxy', status='observed', available_at=as_of,
                    source_note=f'{tt_note}; shared Creative Center proxy, not SKU-daily post volume.',
                )
            else:
                row['source_note'] = (
                    f'TikTok Creative Center no dated series after Playwright. '
                    f'status={(tt_data or {}).get("http_status")} err={(tt_data or {}).get("error")}; {tt_note}'
                )
            out.append(row)
    for tag in watch['hashtags']:
        row = observation('TikTok', 'CreativeCenter', 'hashtag_daily_growth', tag, creative_url, yday)
        row.update(as_of_ts=(tt_data or {}).get('fetched_at'),
                   source_note=(tt_data or {}).get('error') or 'No timestamped daily hashtag series; NULL, not Newsroom monthly substitution.')
        out.append(row)

    out.extend(instagram_rows(watch, ig_data, ig_url, yday))

    sku_capture: dict = {}
    if as_of == today and browsers_ok:
        try:
            from collectors.playwright_worker import run_browser

            def _skus(browser):
                for sku, profile in watch['profiles'].items():
                    query = (profile.get('query') or sku) + ' christmas gift'
                    surl = 'https://www.youtube.com/results?' + urlencode({'search_query': query})
                    fetched = browser.open_and_capture(
                        surl, wait_ms=7000, referer='https://www.youtube.com/',
                        capture_substrings=['youtubei'],
                    )
                    sku_capture[sku] = (surl, fetched, _parse_yt_initial((fetched or {}).get('body') or ''))
                return sku_capture
            run_browser(_skus)
        except Exception as exc:  # noqa: BLE001
            for sku in watch['profiles']:
                sku_capture.setdefault(sku, (yt_url, _pw_failure(yt_url, str(exc)), []))
    elif as_of == today:
        for sku in watch['profiles']:
            sku_capture[sku] = (yt_url, _pw_failure(yt_url, browser_reason or 'playwright browser unavailable'), [])

    for sku, profile in watch['profiles'].items():
        if sku in sku_capture:
            surl, fetched, videos = sku_capture[sku]
        else:
            surl, fetched, videos = yt_url, {'error': None, 'fetched_at': datetime.now(SH).isoformat(), 'http_status': None}, []
        out.extend(build_youtube_rows(
            sku, profile, surl=surl, fetched=fetched, videos=videos, as_of=as_of, today=today,
        ))

    creds = reddit_app_credentials()
    oauth_cache: dict = {}

    def _fetch_oauth(sub):
        from collectors.human_fetch import human_pause
        return fetch_reddit_oauth_listing(
            sub, *creds, post=_reddit_post, get=_reddit_get, cache=oauth_cache, pause=human_pause,
        )

    def _fetch_old(url, _sub):
        from collectors.playwright_worker import run_browser

        def _go(browser):
            return browser.open_and_capture(
                url, wait_ms=8000, referer='https://old.reddit.com/',
                capture_substrings=['.rss', 'reddit.com'],
            )
        return run_browser(_go)

    for sub in watch['subreddits']:
        data = load_reddit_sub(
            sub, fetch_old_rss=_fetch_old,
            fetch_oauth=_fetch_oauth if creds else None,
            browsers_ok=browsers_ok, browser_reason=browser_reason,
        )
        posts = parse_reddit_posts(data)
        out.extend(_reddit_rows(sub, data, posts, watch, as_of, yday))

    out.extend(collect_google_trends(
        as_of, watch, yday, browsers_ok=browsers_ok, browser_reason=browser_reason,
    ))

    for row in out:
        row.setdefault('as_of_ts', datetime.now(SH).isoformat())
    return out
