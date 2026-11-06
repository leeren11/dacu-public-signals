"""Public source adapters with human-like browser / TLS fingerprinting.
Raw evidence + explicit NULLs. Never invent volumes. Monthly Newsroom is context only.
"""
from __future__ import annotations
import json, re
from datetime import date, datetime, timedelta, timezone
from urllib.parse import urlencode
from bs4 import BeautifulSoup
from collectors.human_fetch import BrowserSession, fetch_cffi, MAC_CHROME_UA, _host_backoff_until

SH = timezone(timedelta(hours=8))
NEWS = 'https://newsroom.tiktok.com/whats-shaping-the-holiday-season-on-tiktok-shop?lang=en'
NEWS_PUBLICATION = '2026-10-19'


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
        # Common patterns in Ad Library JSON
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
    # Fallback: no invented number
    return None, 'No dated numeric trend field in Creative Center XHR/HTML'


def collect_google_trends(as_of, watch, yday):
    """Homepage NID warm-up via Playwright, then pytrends with cooldown batches."""
    out = []
    terms = list(watch.get('search_terms') or [])[:5]
    url = 'https://trends.google.com/trends/explore?' + urlencode({
        'geo': 'US',
        'q': ','.join(terms) if terms else 'gifts',
        'date': f'{(date.fromisoformat(yday) - timedelta(days=6)).isoformat()} {yday}',
    })
    # Warm cookies
    try:
        with BrowserSession(headless=True) as browser:
            warm = browser.open_and_capture('https://trends.google.com/trends/explore?geo=US', wait_ms=5000, referer='https://www.google.com/')
    except Exception as e:  # noqa: BLE001
        warm = {'error': str(e), 'fetched_at': datetime.now(SH).isoformat()}

    values_by_term = {}
    trends_err = None
    try:
        from pytrends.request import TrendReq
        # Longer timeout; pytrends still uses requests underneath but after browser NID warm-up
        # and with human pauses between batches — best-effort against 429.
        # urllib3 v2 dropped method_whitelist; avoid pytrends retries kwargs that break.
        pytrends = TrendReq(hl='en-US', tz=360, timeout=(10, 30))
        for i in range(0, len(terms), 1):
            batch = terms[i:i + 1]
            try:
                from collectors.human_fetch import human_pause
                human_pause(6.0, 12.0)
                pytrends.build_payload(batch, timeframe=f'{(date.fromisoformat(yday) - timedelta(days=6)).isoformat()} {yday}', geo='US')
                df = pytrends.interest_over_time()
                if df is not None and not df.empty and batch[0] in df.columns:
                    # Last complete day in frame matching yday if present, else last row
                    series = df[batch[0]]
                    if yday in [str(x.date()) for x in series.index]:
                        for idx, val in series.items():
                            if str(idx.date()) == yday:
                                values_by_term[batch[0]] = float(val)
                                break
                    else:
                        values_by_term[batch[0]] = float(series.iloc[-1])
            except Exception as e:  # noqa: BLE001
                trends_err = str(e)
                break
    except Exception as e:  # noqa: BLE001
        trends_err = str(e)

    for sku, profile in watch['profiles'].items():
        row = observation('GoogleTrends', 'explore', 'search_velocity', sku, url, yday)
        row['as_of_ts'] = warm.get('fetched_at') or datetime.now(SH).isoformat()
        # Match SKU query tokens to a search term loosely
        q = (profile.get('query') or '').lower()
        hit = None
        for term, val in values_by_term.items():
            if any(tok in term.lower() for tok in re.findall(r'[a-z]{4,}', q)[:3]) or any(tok in q for tok in re.findall(r'[a-z]{4,}', term.lower())[:3]):
                hit = (term, val)
                break
        if hit:
            row.update(
                value=hit[1], unit='interest_index', status='observed', available_at=as_of,
                source_note=f'pytrends interest_over_time for "{hit[0]}" after Playwright Trends warm-up; proxy index not search volume. NID warm err={warm.get("error")}',
            )
        else:
            row['source_note'] = (
                f'Google Trends unavailable after human-like attempt. warm={warm.get("error")}; '
                f'pytrends={trends_err or ("no term match; got " + str(list(values_by_term)))}. NULL, not zero.'
            )
            if trends_err and ('429' in trends_err or 'Sorry' in trends_err):
                row['source_note'] = 'HTTP 429 / pytrends blocked after backoff + cache miss. ' + row['source_note']
        out.append(row)
    return out


def collect(as_of, watch):
    yday = (date.fromisoformat(as_of) - timedelta(days=1)).isoformat()
    out = []

    # --- TikTok Newsroom monthly context (curl_cffi; static OK) ---
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

    # Single Playwright session for Meta / TikTok CC / YouTube / Trends warm pages
    creative_url = 'https://ads.tiktok.com/business/creativecenter/inspiration/popular/hashtag/pc/en'
    meta_url = 'https://www.facebook.com/ads/library/?' + urlencode({
        'active_status': 'active', 'ad_type': 'all', 'country': 'US',
        'q': 'christmas gifts', 'search_type': 'keyword_unordered',
    })
    yt_url = 'https://www.youtube.com/results?' + urlencode({'search_query': 'shorts best gifts under 25 christmas 2026'})
    ig_url = 'https://www.instagram.com/explore/tags/stockingstuffers/'

    meta_data = tt_data = yt_data = ig_data = None
    try:
        with BrowserSession(headless=True) as browser:
            meta_data = browser.open_and_capture(
                meta_url, wait_ms=10000,
                capture_substrings=['graphql', 'ads/library', 'api/v', 'ad_library'],
                referer='https://www.facebook.com/',
            )
            tt_data = browser.open_and_capture(
                creative_url, wait_ms=10000,
                capture_substrings=['api/', 'creative', 'hashtag', 'graphql', 'aweme'],
                referer='https://ads.tiktok.com/',
            )
            yt_data = browser.open_and_capture(
                yt_url, wait_ms=8000,
                capture_substrings=['youtubei', 'results'],
                referer='https://www.youtube.com/',
            )
            ig_data = browser.open_and_capture(
                ig_url, wait_ms=6000,
                capture_substrings=['graphql', 'api/v1'],
                referer='https://www.instagram.com/',
            )
    except Exception as e:  # noqa: BLE001
        err = {'url': '', 'fetched_at': datetime.now(SH).isoformat(), 'http_status': None, 'body': '', 'xhr': [], 'error': str(e), 'transport': 'playwright'}
        meta_data = meta_data or dict(err, url=meta_url)
        tt_data = tt_data or dict(err, url=creative_url)
        yt_data = yt_data or dict(err, url=yt_url)
        ig_data = ig_data or dict(err, url=ig_url)

    # Meta Ad Library → active_ads
    ads_count = _extract_active_ads_from_xhr((meta_data or {}).get('xhr'))
    if ads_count is None and meta_data and meta_data.get('body'):
        m = re.search(r'(?:About\s+)?([\d,]+)\s+result', meta_data['body'], re.I)
        if m:
            try:
                ads_count = float(m.group(1).replace(',', ''))
            except ValueError:
                ads_count = None
    for sku in watch['profiles']:
        row = observation('Meta', 'AdLibrary', 'active_ads', sku, meta_url, yday)
        row['as_of_ts'] = (meta_data or {}).get('fetched_at')
        if ads_count is not None and not (meta_data or {}).get('error'):
            row.update(
                value=ads_count, unit='active_ads_count', status='observed', available_at=as_of, is_proxy=1,
                source_note=f'Playwright XHR/HTML Active Ads proxy for keyword "christmas gifts" (shared across SKUs, not SKU-specific auction). transport=playwright. cache={(meta_data or {}).get("from_cache")}',
            )
        else:
            row['source_note'] = (
                f'Meta Ad Library blocked or empty after Playwright+backoff. '
                f'status={(meta_data or {}).get("http_status")} err={(meta_data or {}).get("error")}. NULL, not zero.'
            )
        out.append(row)

    # TikTok Creative Center
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

    # Instagram explore — usually login wall; keep honest NULL
    for sku in watch['profiles']:
        row = observation('Meta', 'Instagram', 'reels_keyword_velocity', sku, ig_url, yday)
        row['as_of_ts'] = (ig_data or {}).get('fetched_at')
        row['source_note'] = (
            f'IG explore after Playwright: status={(ig_data or {}).get("http_status")} '
            f'err={(ig_data or {}).get("error") or "no dated public aggregate"}. NULL.'
        )
        out.append(row)

    # YouTube: shared holiday search first, then per-SKU ytInitialData (today only; never backdate).
    shared_videos = _parse_yt_initial((yt_data or {}).get('body') or '')
    sku_yt = {}
    if as_of == date.today().isoformat():
        try:
            with BrowserSession(headless=True) as yb:
                for sku, profile in watch['profiles'].items():
                    q = (profile.get('query') or sku) + ' christmas gift'
                    surl = 'https://www.youtube.com/results?' + urlencode({'search_query': q})
                    yd = yb.open_and_capture(surl, wait_ms=7000, referer='https://www.youtube.com/', capture_substrings=['youtubei'])
                    sku_yt[sku] = (surl, yd, _parse_yt_initial((yd or {}).get('body') or ''))
        except Exception as e:  # noqa: BLE001
            for sku in watch['profiles']:
                sku_yt.setdefault(sku, (yt_url, {'error': str(e), 'fetched_at': datetime.now(SH).isoformat(), 'http_status': None, 'body': ''}, []))

    for sku, profile in watch['profiles'].items():
        surl, yd, videos = sku_yt.get(sku, (yt_url, yt_data or {}, shared_videos))
        row = observation('YouTube', 'public_search', 'video_view_velocity', sku, surl, yday)
        row['as_of_ts'] = (yd or {}).get('fetched_at') or (yt_data or {}).get('fetched_at')
        tokens = [t for t in re.findall('[a-z]+', (profile.get('query') or '').lower()) if len(t) > 3 and t not in ('gifts', 'christmas', 'family', 'holiday', 'ready', 'stock')]
        # Prefer title token match; if per-SKU search, accept top rendered videos as sample.
        relevant = [v for v in videos if any(t in _txt(v.get('title', {})).lower() for t in tokens)] or (videos[:12] if sku in sku_yt else [])
        counts = [c for c in (_view_count(_txt(v.get('viewCountText', {}))) for v in relevant) if c is not None]
        if counts and as_of == date.today().isoformat():
            snap = observation('YouTube', 'public_search', 'sampled_video_views_snapshot', sku, surl, as_of)
            snap.update(
                value=sum(counts), unit='sampled_lifetime_video_views', is_partial=1, status='snapshot',
                as_of_ts=row['as_of_ts'], available_at=as_of,
                source_note=f'Playwright ytInitialData per-SKU sample n={len(counts)}; lifetime views, selection-biased, not Shorts-only, not daily volume. Never backdated.',
            )
            out.append(snap)
            row.update(
                value=float(len(counts)), unit='matched_video_count', status='observed', available_at=as_of,
                source_note=f'Playwright ytInitialData matched/sample video count n={len(counts)}; proxy for content presence, NOT platform-wide daily views.',
            )
        else:
            row['source_note'] = (
                f'YouTube after Playwright: status={(yd or {}).get("http_status")} '
                f'err={(yd or {}).get("error")} videos_parsed={len(videos)}. '
                f'{"Historical as_of — no backdated lifetime snapshot." if as_of != date.today().isoformat() else "No countable views in sample."} NULL velocity.'
            )
        out.append(row)

    # Reddit: try JSON then RSS with curl_cffi; Playwright fallback once per sub.
    for sub in watch['subreddits']:
        rurl = f'https://www.reddit.com/r/{sub}/new.json?limit=100'
        data = fetch_cffi(
            rurl,
            referer=f'https://www.reddit.com/r/{sub}/',
            accept='application/json,text/plain,*/*',
            tag=f'reddit_{sub}',
        )
        if data.get('http_status') in (403, 429) or data.get('error'):
            # Alternate path on same host: clear short backoff so RSS gets one real try.
            _host_backoff_until.pop('www.reddit.com', None)
            rss_url = f'https://www.reddit.com/r/{sub}/new/.rss'
            rss = fetch_cffi(rss_url, referer=f'https://www.reddit.com/r/{sub}/', accept='application/atom+xml,application/rss+xml,text/xml,*/*', tag=f'reddit_rss_{sub}')
            if not rss.get('error') and rss.get('body') and '<entry' in (rss.get('body') or ''):
                data = dict(rss)
                data['reddit_mode'] = 'rss'
                rurl = rss_url
            else:
                try:
                    with BrowserSession(headless=True) as rb:
                        pw = rb.open_and_capture(rurl, wait_ms=8000, referer=f'https://www.reddit.com/r/{sub}/', capture_substrings=['.json'])
                    if pw.get('http_status') == 200 and 'children' in (pw.get('body') or ''):
                        data = pw; data['reddit_mode'] = 'playwright_json'
                    else:
                        data = data  # keep first error
                        data['source_extra'] = f'rss={(rss.get("http_status"), rss.get("error"))}; pw={(pw.get("http_status"), pw.get("error"))}'
                except Exception as e:  # noqa: BLE001
                    data['source_extra'] = f'rss/pw fallback failed: {e}'

        posts = []
        if data.get('body') and (not data.get('error') or data.get('reddit_mode') in ('rss', 'playwright_json')):
            body = data['body']
            if data.get('reddit_mode') == 'rss' or body.lstrip().startswith('<?xml') or '<feed' in body[:240] or '<rss' in body[:240]:
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
                        'title': re.sub(r'<[^>]+>', '', title_m.group(1) if title_m else ''),
                        'selftext': re.sub(r'<[^>]+>', '', content_m.group(1) if content_m else ''),
                        'created_utc': ts,
                        'num_comments': 0,
                    })
            else:
                try:
                    raw = body
                    if '<html' in raw[:200].lower():
                        m = re.search(r'(\{\s*"kind"\s*:\s*"Listing"[\s\S]+)', raw)
                        raw = m.group(1) if m else raw
                    posts = [p['data'] for p in json.loads(raw)['data']['children']]
                except (ValueError, KeyError, TypeError):
                    posts = []
        start = datetime.fromisoformat(yday).replace(tzinfo=timezone.utc).timestamp()
        end = start + 86400
        coverage = bool(posts) and min((p.get('created_utc') or end) for p in posts) <= start
        # Also emit a 7d heat metric when we have posts in last 7 days
        week_start = start - 6 * 86400
        for sku, profile in watch['profiles'].items():
            row = observation('Reddit', sub, 'complaint_share', sku, rurl, yday)
            row.update(as_of_ts=data.get('fetched_at'), unit='fraction')
            tokens = [t for t in re.findall('[a-z]+', (profile.get('query') or '').lower()) if len(t) > 3]
            if coverage:
                selected = [p for p in posts if start <= (p.get('created_utc') or 0) < end and any(t in ((p.get('title') or '') + ' ' + (p.get('selftext') or '')).lower() for t in tokens)]
                if selected:
                    negative = sum(any(k in ((p.get('title') or '') + ' ' + (p.get('selftext') or '')).lower() for k in watch['risk_keywords']) for p in selected)
                    row.update(
                        value=negative / len(selected), status='observed', available_at=as_of,
                        source_note=f'curl_cffi chrome124 Reddit JSON; UTC day covered; keyword-matched n={len(selected)}, complaint-keyword n={negative}. Lexical proxy, not return rate.',
                    )
            if row['value'] is None:
                row['source_note'] = (data.get('error') or 'Public listing cannot fully cover target UTC day or no relevant sample; NULL, never zero sentiment.') + ((' | ' + data['source_extra']) if data.get('source_extra') else '')
            out.append(row)

            heat = observation('Reddit', sub, 'post_heat_7d', sku, rurl, yday)
            heat.update(as_of_ts=data.get('fetched_at'), unit='posts')
            week_posts = [p for p in posts if week_start <= (p.get('created_utc') or 0) < end and any(t in ((p.get('title') or '') + ' ' + (p.get('selftext') or '')).lower() for t in tokens)]
            if week_posts and not data.get('error'):
                comments = sum(int(p.get('num_comments') or 0) for p in week_posts)
                heat.update(
                    value=float(len(week_posts)), status='observed', available_at=as_of,
                    source_note=f'curl_cffi Reddit JSON last-7d matched posts n={len(week_posts)}, comments_sum={comments}. Sample of /new, not full subreddit volume.',
                )
            else:
                heat['source_note'] = data.get('error') or 'No 7d keyword-matched Reddit posts in sample; NULL.'
            out.append(heat)

    # Google Trends (Playwright warm + pytrends batches)
    out.extend(collect_google_trends(as_of, watch, yday))

    for row in out:
        row.setdefault('as_of_ts', datetime.now(SH).isoformat())
    return out
