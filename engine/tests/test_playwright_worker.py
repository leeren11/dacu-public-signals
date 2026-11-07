"""Sync Playwright must not run on a thread that already has an asyncio loop."""
import asyncio
import sys
import tempfile
import threading
import unittest
from pathlib import Path
from unittest import mock

ENGINE = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ENGINE / 'scripts'))

from collectors.human_fetch import BrowserSession, assert_sync_playwright_thread  # noqa: E402
from collectors.playwright_worker import (  # noqa: E402
    ensure_chromium_installed,
    missing_browser_executables,
    run_sync_playwright,
)


class PlaywrightWorkerTests(unittest.TestCase):
    def test_sync_api_guard_rejects_running_loop(self):
        async def main():
            with self.assertRaises(RuntimeError) as caught:
                assert_sync_playwright_thread()
            self.assertIn('asyncio loop', str(caught.exception))
            session = BrowserSession()
            with self.assertRaises(RuntimeError) as caught:
                session.__enter__()
            self.assertIn('asyncio loop', str(caught.exception))

        asyncio.run(main())
        self.assertFalse(Path('/workspace/dacu-signal/data/browser_profile').exists())

    def test_worker_thread_has_no_loop_even_if_caller_does(self):
        seen = []

        def probe():
            # Thread idents can be recycled after join; the Thread object is the session.
            seen.append(threading.current_thread())
            assert_sync_playwright_thread()
            try:
                asyncio.get_running_loop()
            except RuntimeError as exc:
                return str(exc)
            raise AssertionError('worker thread has a running loop')

        async def main():
            first = run_sync_playwright(probe)
            second = run_sync_playwright(probe)
            self.assertIn('no running event loop', first)
            self.assertIn('no running event loop', second)

        caller = threading.current_thread()
        asyncio.run(main())
        self.assertEqual(len(seen), 2)
        self.assertIsNot(seen[0], seen[1])
        self.assertIsNot(seen[0], caller)
        self.assertIsNot(seen[1], caller)

    def test_worker_propagates_exceptions(self):
        def boom():
            raise RuntimeError('worker-boom')

        with self.assertRaises(RuntimeError) as caught:
            run_sync_playwright(boom)
        self.assertIn('worker-boom', str(caught.exception))

    def test_missing_executables_follow_playwright_layout(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            revision = '1248'
            chrome = root / 'chromium-1248' / 'chrome-linux64' / 'chrome'
            shell = root / 'chromium_headless_shell-1248' / 'chrome-headless-shell-linux64' / 'chrome-headless-shell'
            chrome.parent.mkdir(parents=True)
            shell.parent.mkdir(parents=True)
            chrome.write_text('chrome')
            shell.write_text('shell')
            descriptors = [
                {'name': 'chromium', 'revision': revision},
                {'name': 'chromium-headless-shell', 'revision': revision},
            ]
            self.assertEqual(
                missing_browser_executables(root=root, descriptors=descriptors, platform_key='linux-x64'),
                [],
            )
            shell.unlink()
            missing = missing_browser_executables(root=root, descriptors=descriptors, platform_key='linux-x64')
            self.assertEqual(len(missing), 1)
            self.assertIn('chromium-headless-shell', missing[0])
            chrome.unlink()
            missing = missing_browser_executables(root=root, descriptors=descriptors, platform_key='linux-x64')
            self.assertEqual(len(missing), 2)

    def test_install_runs_once_with_the_chromium_command(self):
        state = {}
        calls = []

        def detect():
            calls.append('detect')
            if calls.count('detect') == 1:
                return ['chromium:/cache/chromium-1248/chrome-linux64/chrome']
            return []

        def install():
            calls.append('install')
            return True, 'ok'

        with self.assertLogs('collectors.playwright', level='WARNING') as logs:
            ok, reason = ensure_chromium_installed(detect=detect, install=install, state=state)
        self.assertTrue(ok)
        self.assertEqual(reason, '')
        self.assertEqual(calls, ['detect', 'install', 'detect'])
        self.assertTrue(any('playwright install chromium chromium-headless-shell' in line for line in logs.output))
        ok_again, _ = ensure_chromium_installed(detect=detect, install=install, state=state)
        self.assertTrue(ok_again)
        self.assertEqual(calls.count('install'), 1)

    def test_failed_install_is_not_retried_and_does_not_raise(self):
        state = {}
        installs = []

        def detect():
            return ['chromium-headless-shell:/cache/missing/chrome-headless-shell']

        def install():
            installs.append(1)
            return False, 'exit=1 disk full'

        ok, reason = ensure_chromium_installed(detect=detect, install=install, state=state)
        ok2, reason2 = ensure_chromium_installed(detect=detect, install=install, state=state)
        self.assertFalse(ok)
        self.assertFalse(ok2)
        self.assertEqual(installs, [1])
        self.assertEqual(reason, reason2)
        self.assertIn('playwright install chromium chromium-headless-shell', reason)
        self.assertIn('chromium-headless-shell', reason)
        self.assertIn('disk full', reason)
        self.assertIn('NULL', reason)

    def test_install_argv(self):
        import collectors.playwright_worker as worker

        completed = mock.Mock(returncode=0, stdout='installed', stderr='')
        with mock.patch.object(worker.subprocess, 'run', return_value=completed) as run:
            ok, _detail = worker._run_playwright_install()
        self.assertTrue(ok)
        argv = run.call_args.args[0]
        self.assertEqual(argv[1:], ['-m', 'playwright', 'install', 'chromium', 'chromium-headless-shell'])

    def test_present_browsers_do_not_install(self):
        state = {}

        def install():
            raise AssertionError('install should not run')

        ok, reason = ensure_chromium_installed(detect=lambda: [], install=install, state=state)
        self.assertTrue(ok)
        self.assertEqual(reason, '')


if __name__ == '__main__':
    unittest.main()
