"""One helper for sync Playwright.

Root cause: ``sync_playwright().start()`` raises
"It looks like you are using Playwright Sync API inside the asyncio loop"
when the calling thread already has a running event loop
(``playwright/sync_api/_context_manager.py``). Google Trends NID warm-up and
the Reddit RSS fallback both hit that after other work had started a loop.
A fresh worker thread has no running loop, so the sync API is legal there.
Each call gets its own thread: Playwright's dispatcher also marks the loop
running between calls, and a reused thread can trip the same error.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path

log = logging.getLogger('collectors.playwright')

_INSTALL_ARGV_TAIL = ('-m', 'playwright', 'install', 'chromium', 'chromium-headless-shell')
_state = {'attempted': False, 'ready': False, 'reason': ''}

# Relative executable paths from Playwright's driver registry (linux/mac/win).
_EXE_REL = {
    'linux-x64': {
        'chromium': ('chrome-linux64', 'chrome'),
        'chromium-headless-shell': ('chrome-headless-shell-linux64', 'chrome-headless-shell'),
    },
    'linux-arm64': {
        'chromium': ('chrome-linux-arm64', 'chrome'),
        'chromium-headless-shell': ('chrome-headless-shell-linux-arm64', 'chrome-headless-shell'),
    },
    'mac-x64': {
        'chromium': ('chrome-mac-x64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'),
        'chromium-headless-shell': ('chrome-headless-shell-mac-x64', 'chrome-headless-shell'),
    },
    'mac-arm64': {
        'chromium': ('chrome-mac-arm64', 'Google Chrome for Testing.app', 'Contents', 'MacOS', 'Google Chrome for Testing'),
        'chromium-headless-shell': ('chrome-headless-shell-mac-arm64', 'chrome-headless-shell'),
    },
    'win-x64': {
        'chromium': ('chrome-win64', 'chrome.exe'),
        'chromium-headless-shell': ('chrome-headless-shell-win64', 'chrome-headless-shell.exe'),
    },
}


def run_sync_playwright(fn, /, *args, **kwargs):
    """Run ``fn(*args, **kwargs)`` on a fresh thread with no asyncio loop.

    The callable may use Playwright's sync API. Playwright objects must not
    escape the callable; return plain data.
    """
    box: dict = {}

    def _target():
        try:
            try:
                asyncio.get_running_loop()
            except RuntimeError:
                pass
            else:
                raise RuntimeError('Playwright worker thread unexpectedly has a running asyncio loop')
            box['value'] = fn(*args, **kwargs)
        except BaseException as exc:  # noqa: BLE001 — re-raised on the caller thread
            box['error'] = exc

    thread = threading.Thread(target=_target, name='playwright-sync-worker', daemon=True)
    thread.start()
    thread.join()
    if 'error' in box:
        raise box['error']
    if 'value' not in box:
        raise RuntimeError('playwright worker returned no result')
    return box['value']


def run_browser(fn, *, headless: bool = True):
    """Open one persistent Chromium session on the worker thread and call ``fn(browser)``."""

    def _job():
        from collectors.human_fetch import BrowserSession
        with BrowserSession(headless=headless) as browser:
            return fn(browser)

    return run_sync_playwright(_job)


def host_platform_key() -> str:
    machine = platform.machine().lower()
    if sys.platform.startswith('linux'):
        return 'linux-arm64' if machine in ('aarch64', 'arm64') else 'linux-x64'
    if sys.platform == 'darwin':
        return 'mac-arm64' if machine in ('arm64', 'aarch64') else 'mac-x64'
    if sys.platform.startswith('win'):
        return 'win-x64'
    return 'linux-x64'


def registry_root() -> Path:
    override = os.environ.get('PLAYWRIGHT_BROWSERS_PATH', '').strip()
    if override and override != '0':
        return Path(override)
    if sys.platform.startswith('linux'):
        base = Path(os.environ['XDG_CACHE_HOME']) if os.environ.get('XDG_CACHE_HOME') else Path.home() / '.cache'
        return base / 'ms-playwright'
    if sys.platform == 'darwin':
        return Path.home() / 'Library' / 'Caches' / 'ms-playwright'
    if sys.platform.startswith('win'):
        local = os.environ.get('LOCALAPPDATA')
        base = Path(local) if local else Path.home() / 'AppData' / 'Local'
        return base / 'ms-playwright'
    return Path.home() / '.cache' / 'ms-playwright'


def packaged_browser_descriptors() -> list[dict]:
    try:
        import playwright
    except ImportError as exc:
        raise RuntimeError(f'playwright package not importable: {exc}') from exc
    path = Path(playwright.__file__).resolve().parent / 'driver' / 'package' / 'browsers.json'
    if not path.exists():
        raise RuntimeError(f'playwright browsers.json missing: {path}')
    data = json.loads(path.read_text())
    wanted = []
    for obj in data.get('browsers') or []:
        if obj.get('name') in ('chromium', 'chromium-headless-shell'):
            wanted.append({'name': obj['name'], 'revision': str(obj['revision'])})
    if {item['name'] for item in wanted} != {'chromium', 'chromium-headless-shell'}:
        raise RuntimeError(f'browsers.json has no chromium + chromium-headless-shell revisions: {path}')
    return wanted


def _executable_present(path: Path) -> bool:
    # Existence is the install check. os.access(X_OK) is always true for root
    # and would hide a missing mode bit; launch reports a bad binary itself.
    return path.is_file()


def missing_browser_executables(*, root: Path | None = None, descriptors: list | None = None, platform_key: str | None = None) -> list[str]:
    """Return human-readable gaps for chromium and chromium-headless-shell. Empty means both exist."""
    root = registry_root() if root is None else root
    platform_key = platform_key or host_platform_key()
    layout = _EXE_REL.get(platform_key)
    if layout is None:
        return [f'unsupported platform {platform_key}']
    if descriptors is None:
        descriptors = packaged_browser_descriptors()
    missing = []
    for item in descriptors:
        name = item['name']
        if name not in layout:
            continue
        folder = root / f"{name.replace('-', '_')}-{item['revision']}"
        exe = folder.joinpath(*layout[name])
        if not _executable_present(exe):
            missing.append(f'{name}:{exe}')
    return missing


def _run_playwright_install() -> tuple[bool, str]:
    argv = [sys.executable, *_INSTALL_ARGV_TAIL]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=600, check=False)
    except Exception as exc:  # noqa: BLE001 — install failure becomes a NULL reason
        return False, f'{" ".join(argv)} failed: {exc}'
    tail = ((proc.stderr or '') + '\n' + (proc.stdout or '')).strip()[-400:]
    if proc.returncode != 0:
        return False, f'exit={proc.returncode} {tail}'
    return True, tail or 'ok'


def ensure_chromium_installed(*, detect=None, install=None, state: dict | None = None) -> tuple[bool, str]:
    """Detect chromium and chromium-headless-shell. Install them once if missing.

    Never raises. Returns ``(ok, reason)``. ``reason`` is empty when browsers are present.
    A failed install is not retried in this process.
    """
    state = _state if state is None else state
    if state.get('ready'):
        return True, ''
    if state.get('attempted'):
        return False, state.get('reason') or 'playwright browser install already attempted'
    detect = detect or missing_browser_executables
    install = install or _run_playwright_install
    try:
        missing = list(detect() or [])
    except Exception as exc:  # noqa: BLE001
        missing = [f'detect failed: {exc}']
    if not missing:
        state['ready'] = True
        state['reason'] = ''
        return True, ''
    state['attempted'] = True
    argv = f'{sys.executable} -m playwright install chromium chromium-headless-shell'
    log.warning('[playwright] missing %s; running once: %s', missing, argv)
    try:
        ok, detail = install()
    except Exception as exc:  # noqa: BLE001
        ok, detail = False, str(exc)
    if not ok:
        state['ready'] = False
        state['reason'] = (
            f'Playwright browser install failed ({argv}): {detail}. '
            f'Missing: {missing}. Platform rows that need a browser are NULL, not zero.'
        )
        log.warning('[playwright] %s', state['reason'])
        return False, state['reason']
    try:
        still = list(detect() or [])
    except Exception as exc:  # noqa: BLE001
        still = [f'detect failed after install: {exc}']
    if still:
        state['ready'] = False
        state['reason'] = (
            f'Playwright browsers still missing after {argv}: {still}. '
            'Platform rows that need a browser are NULL, not zero.'
        )
        log.warning('[playwright] %s', state['reason'])
        return False, state['reason']
    state['ready'] = True
    state['reason'] = ''
    log.warning('[playwright] chromium and chromium-headless-shell present after %s', argv)
    return True, ''
