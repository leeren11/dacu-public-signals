"""Human-like fetch layer: Playwright persistent Chromium + curl_cffi chrome124.
Never use bare python-requests for target HTML pages. Honesty: leave NULL on hard blocks.

Sync Playwright must run on a thread with no running asyncio loop. Callers use
``collectors.playwright_worker.run_browser`` / ``run_sync_playwright``.
"""
from __future__ import annotations
import asyncio, hashlib, json, random, time
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import urlparse

ROOT = Path('/workspace/dacu-signal')
RAW = ROOT / 'data' / 'platform_raw'
CACHE = ROOT / 'data' / 'platform_cache'
PROFILE = ROOT / 'data' / 'browser_profile'
SH = timezone(timedelta(hours=8))

MAC_CHROME_UA = (
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
    'AppleWebKit/537.36 (KHTML, like Gecko) '
    'Chrome/124.0.0.0 Safari/537.36'
)
EXTRA_HEADERS = {
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8',
    'Accept-Language': 'en-US,en;q=0.9',
    'Sec-Ch-Ua': '"Chromium";v="124", "Google Chrome";v="124", "Not-A.Brand";v="99"',
    'Sec-Ch-Ua-Mobile': '?0',
    'Sec-Ch-Ua-Platform': '"macOS"',
    'Upgrade-Insecure-Requests': '1',
}

# Serialize cross-platform calls (no concurrent hammering of one host).
_last_call_mono = 0.0
_host_backoff_until: dict[str, float] = {}


def _now_iso() -> str:
    return datetime.now(SH).isoformat()


def human_pause(lo: float = 4.5, hi: float = 11.2) -> None:
    global _last_call_mono
    gap = random.uniform(lo, hi)
    elapsed = time.monotonic() - _last_call_mono
    if elapsed < gap:
        time.sleep(gap - elapsed)
    _last_call_mono = time.monotonic()


def _cache_key(url: str, tag: str = '') -> str:
    return hashlib.sha256((tag + '|' + url).encode()).hexdigest()[:24]


def read_good_cache(url: str, tag: str = '') -> dict | None:
    path = CACHE / f'{_cache_key(url, tag)}.json'
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
    except (ValueError, OSError):
        return None
    if data.get('http_status') in (200, 201) and data.get('body'):
        return data
    return None


def write_cache(url: str, data: dict, tag: str = '') -> Path:
    CACHE.mkdir(parents=True, exist_ok=True)
    RAW.mkdir(parents=True, exist_ok=True)
    key = _cache_key(url, tag)
    path = CACHE / f'{key}.json'
    path.write_text(json.dumps(data, ensure_ascii=False)[:2_000_000])
    # Evidence dump (truncated) for audit; not stamped to GitHub.
    raw = RAW / f'{datetime.now(SH).date().isoformat()}_{key[:20]}.json'
    slim = dict(data)
    body = slim.get('body') or ''
    if len(body) > 80_000:
        slim['body'] = body[:80_000] + '\n/* truncated */'
    raw.write_text(json.dumps(slim, ensure_ascii=False))
    return path


def assert_sync_playwright_thread() -> None:
    """Refuse the sync API when this thread already has a running asyncio loop.

    Playwright raises "It looks like you are using Playwright Sync API inside
    the asyncio loop" in that case. Google Trends warm-up and the Reddit
    fallback were hitting it on the pipeline thread.
    """
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return
    raise RuntimeError(
        'Playwright Sync API called inside the asyncio loop. '
        'Use collectors.playwright_worker.run_sync_playwright so sync Playwright '
        'runs on a fresh worker thread.'
    )


def host_blocked(url: str) -> bool:
    host = urlparse(url).netloc
    return time.monotonic() < _host_backoff_until.get(host, 0)


def mark_backoff(url: str, status: int | None, attempt: int) -> None:
    host = urlparse(url).netloc
    # Exponential: 30s, 90s, 270s ...
    wait = min(900.0, 30.0 * (3 ** max(0, attempt)))
    if status in (403, 429) or status is None:
        _host_backoff_until[host] = time.monotonic() + wait


def fetch_cffi(url: str, *, referer: str | None = None, accept: str | None = None, tag: str = 'cffi') -> dict:
    """curl_cffi chrome124 for JSON/RSS/simple HTML. Not bare requests."""
    if host_blocked(url):
        cached = read_good_cache(url, tag)
        if cached:
            out = dict(cached)
            out['from_cache'] = True
            out['error'] = (out.get('error') or '') + ' | host backoff; served last good cache'
            return out
        return {'url': url, 'fetched_at': _now_iso(), 'http_status': None, 'body': '', 'error': 'host in backoff; no good cache', 'from_cache': False}

    human_pause()
    try:
        from curl_cffi import requests as creq
    except ImportError as e:
        return {'url': url, 'fetched_at': _now_iso(), 'http_status': None, 'body': '', 'error': f'curl_cffi missing: {e}', 'from_cache': False}

    headers = dict(EXTRA_HEADERS)
    headers['User-Agent'] = MAC_CHROME_UA
    if referer:
        headers['Referer'] = referer
    if accept:
        headers['Accept'] = accept

    last_err = None
    for attempt in range(3):
        try:
            resp = creq.get(url, headers=headers, impersonate='chrome124', timeout=25, allow_redirects=True)
            data = {
                'url': url,
                'fetched_at': _now_iso(),
                'http_status': resp.status_code,
                'body': resp.text or '',
                'error': None if resp.ok else f'HTTP {resp.status_code}',
                'from_cache': False,
                'transport': 'curl_cffi/chrome124',
            }
            if resp.status_code in (403, 429):
                mark_backoff(url, resp.status_code, attempt)
                last_err = data
                time.sleep(min(60, 8 * (2 ** attempt)) + random.uniform(1, 4))
                continue
            write_cache(url, data, tag)
            return data
        except Exception as e:  # noqa: BLE001 — surface as NULL upstream
            last_err = {'url': url, 'fetched_at': _now_iso(), 'http_status': None, 'body': '', 'error': str(e), 'from_cache': False, 'transport': 'curl_cffi/chrome124'}
            mark_backoff(url, None, attempt)
            time.sleep(min(60, 8 * (2 ** attempt)) + random.uniform(1, 4))
    cached = read_good_cache(url, tag)
    if cached:
        out = dict(cached)
        out['from_cache'] = True
        out['error'] = f"after retries: {(last_err or {}).get('error')}; served last good cache"
        return out
    return last_err or {'url': url, 'fetched_at': _now_iso(), 'http_status': None, 'body': '', 'error': 'unknown cffi failure', 'from_cache': False}


class BrowserSession:
    """Persistent Chromium context; human micro-moves; XHR/GraphQL interception."""

    def __init__(self, headless: bool = True):
        self.headless = headless
        self._pw = None
        self._ctx = None
        self._browser = None

    def __enter__(self):
        assert_sync_playwright_thread()
        from playwright.sync_api import sync_playwright
        PROFILE.mkdir(parents=True, exist_ok=True)
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            user_data_dir=str(PROFILE),
            headless=self.headless,
            channel=None,
            viewport={'width': 1440, 'height': 900},
            user_agent=MAC_CHROME_UA,
            locale='en-US',
            timezone_id='America/Los_Angeles',
            extra_http_headers={
                'Accept-Language': 'en-US,en;q=0.9',
                'Sec-Ch-Ua': EXTRA_HEADERS['Sec-Ch-Ua'],
                'Sec-Ch-Ua-Mobile': '?0',
                'Sec-Ch-Ua-Platform': '"macOS"',
            },
            args=['--disable-blink-features=AutomationControlled'],
        )
        self._ctx.add_init_script(
            "Object.defineProperty(navigator,'webdriver',{get:()=>undefined});"
        )
        return self

    def __exit__(self, *exc):
        try:
            if self._ctx:
                self._ctx.close()
        finally:
            if self._pw:
                self._pw.stop()

    def open_and_capture(self, url: str, *, wait_ms: int = 8000, capture_substrings: list[str] | None = None, referer: str | None = None) -> dict:
        if host_blocked(url):
            cached = read_good_cache(url, 'pw')
            if cached:
                out = dict(cached)
                out['from_cache'] = True
                out['error'] = (out.get('error') or '') + ' | host backoff; served last good cache'
                return out
            return {'url': url, 'fetched_at': _now_iso(), 'http_status': None, 'body': '', 'xhr': [], 'error': 'host in backoff; no good cache', 'from_cache': False, 'transport': 'playwright'}

        human_pause()
        xhr: list[dict] = []
        capture_substrings = capture_substrings or []

        def on_response(resp):
            try:
                u = resp.url
                if any(s in u for s in capture_substrings):
                    ctype = (resp.headers or {}).get('content-type', '')
                    body = ''
                    if 'json' in ctype or 'javascript' in ctype or u.endswith('.json'):
                        try:
                            body = resp.text()
                        except Exception:
                            body = ''
                    xhr.append({'url': u, 'status': resp.status, 'content_type': ctype, 'body': body[:500_000]})
            except Exception:
                pass

        page = self._ctx.new_page()
        page.on('response', on_response)
        status = None
        body = ''
        err = None
        try:
            if referer:
                page.set_extra_http_headers({'Referer': referer})
            resp = page.goto(url, wait_until='domcontentloaded', timeout=45_000)
            status = resp.status if resp else None
            try:
                page.wait_for_load_state('networkidle', timeout=wait_ms)
            except Exception:
                page.wait_for_timeout(1500)
            # Human-like micro interaction
            try:
                page.mouse.move(random.randint(80, 400), random.randint(120, 500))
                page.mouse.wheel(0, random.randint(400, 1400))
                page.wait_for_timeout(random.randint(600, 1600))
                page.mouse.wheel(0, random.randint(200, 800))
            except Exception:
                pass
            body = page.content() or ''
            if status in (403, 429):
                mark_backoff(url, status, 0)
                err = f'HTTP {status}'
            elif status and status >= 400:
                err = f'HTTP {status}'
        except Exception as e:  # noqa: BLE001
            err = str(e)
            mark_backoff(url, None, 0)
        finally:
            page.close()

        data = {
            'url': url,
            'fetched_at': _now_iso(),
            'http_status': status,
            'body': body,
            'xhr': xhr,
            'error': err,
            'from_cache': False,
            'transport': 'playwright',
        }
        if not err and body:
            write_cache(url, {k: v for k, v in data.items() if k != 'xhr'}, 'pw')
        if err and status in (403, 429):
            cached = read_good_cache(url, 'pw')
            if cached:
                out = dict(cached)
                out['from_cache'] = True
                out['xhr'] = xhr
                out['error'] = f'{err}; served last good cache'
                return out
        return data
