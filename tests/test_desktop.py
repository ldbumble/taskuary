"""Desktop shell tests - the embedded server really boots and serves the UI + API."""
import builtins, threading, time, unittest, urllib.request
from taskuary import config, desktop


def _get(url: str) -> str:
    """The owner token is mandatory now. A browser gets it from the page the server hands out
    (server._seed_token); a plain client sends the header, as the CLI and the hooks do."""
    req = urllib.request.Request(url, headers={'X-Taskuary-Token': config.load()['server'].get('token') or ''})
    return urllib.request.urlopen(req, timeout=10).read().decode()


class DesktopTests(unittest.TestCase):
    def test_free_port(self):
        a, b = desktop.free_port(), desktop.free_port()
        self.assertTrue(1024 < a < 65536 and 1024 < b < 65536)

    def test_embedded_server_serves_ui_and_api(self):
        server, url = desktop.start_server()
        try:
            self.assertTrue(server.started)
            html = _get(f'{url}/')
            self.assertIn('Taskuary', html)
            self.assertIn('localStorage.setItem("taskuary_token"', html)   # ...and the page carries it
            api = _get(f'{url}/api/report-types')
            self.assertIn('mssql', api)
            conns = _get(f'{url}/api/connectors')
            self.assertIn('github', conns)
        finally:
            self.assertEqual(desktop.stop_server(server), 'clean')
            self.assertFalse(server.thread.is_alive())

    # Quitting used to flip should_exit and return; the daemon thread died with the process before the
    # lifespan's cleanup (sessions, CLI children, the drain) ran - an orphaned Claude/Codex was the result (PW-261).
    def test_stop_server_is_bounded_when_cleanup_hangs_and_says_so(self):
        release = threading.Event()
        class Hung: should_exit = False
        hung = Hung(); hung.thread = threading.Thread(target=release.wait, daemon=True); hung.thread.start()
        t0 = time.monotonic()
        try:
            self.assertEqual(desktop.stop_server(hung, timeout=0.3), 'timeout')
            self.assertLess(time.monotonic() - t0, 2.0)
            self.assertTrue(hung.should_exit)
        finally: release.set()

    def test_stop_server_reports_a_server_that_already_ended(self):
        class Gone: should_exit = True
        gone = Gone(); gone.thread = threading.Thread(target=lambda: None); gone.thread.start(); gone.thread.join()
        self.assertEqual(desktop.stop_server(gone), 'not_running')

    def test_the_browser_fallback_waits_until_the_server_is_told_to_exit(self):
        class Srv: should_exit = False
        srv = Srv()
        threading.Timer(0.2, lambda: setattr(srv, 'should_exit', True)).start()
        t0 = time.monotonic(); desktop.wait_for_exit(srv, poll=0.05)
        self.assertLess(time.monotonic() - t0, 2.0)



class StartingUpTests(unittest.TestCase):
    """The window used to open on whatever was there while the app was still booting - and for
    18 seconds on 2026-09-09 that was a connection error, because `from taskuary.server import
    app` alone is ~8s cold and the lifespan follows it. The owner should be told it is starting."""

    def test_serving_is_true_once_the_port_answers_at_all(self):
        server, url = desktop.start_server()
        try:
            # any HTTP reply means the server is up - even a 401. Only a dead socket is "not yet".
            self.assertTrue(desktop.serving(url, 10))
        finally:
            desktop.stop_server(server)

    def test_serving_gives_up_on_a_port_with_nothing_behind_it(self):
        dead = f'http://127.0.0.1:{desktop.free_port()}'
        started = time.time()
        self.assertFalse(desktop.serving(dead, 0.6))
        self.assertLess(time.time() - started, 5, 'the probe must respect its own deadline')

    def test_the_splash_says_what_is_happening(self):
        self.assertIn('starting up', desktop.SPLASH.lower())


class BrowserWaitsForThePortTests(unittest.TestCase):
    """`taskuary` (the CLI entry point, which is what a plain install runs) opened the browser on
    a fixed 1.2s timer while uvicorn was still importing the app - ~8s cold before the lifespan
    even starts. The owner got their BROWSER's "site can't be reached", which no splash of ours
    can replace: the only fix is not to open it until the port answers (2026-09-09)."""

    def test_the_browser_is_opened_only_after_the_probe_says_yes(self):
        from taskuary import cli
        order = []
        cli.open_when_ready('http://127.0.0.1:9',
                            open_it=lambda u: order.append(f'open {u}'),
                            wait=lambda u: order.append('probe') or True)
        self.assertEqual(order, ['probe', 'open http://127.0.0.1:9'])

    def test_the_opener_thread_imports_nothing_at_all(self):
        """The whole point of passing `serving` in. uvicorn imports taskuary.server on the main
        thread while this thread runs, and the first cut imported urllib here: the two took each
        other's import lock and the port never opened - the app hung, silently (2026-09-09)."""
        from taskuary import cli
        real, worker, imported, opened = builtins.__import__, {}, [], []
        def guarded(name, *a, **kw):
            if threading.get_ident() == worker.get('id'): imported.append(name)
            return real(name, *a, **kw)
        dead = f'http://127.0.0.1:{desktop.free_port()}'
        def body():
            worker['id'] = threading.get_ident()
            cli.open_when_ready(dead, lambda u: desktop.serving(u, 0.3), open_it=opened.append)
        builtins.__import__ = guarded
        try:
            t = threading.Thread(target=body); t.start(); t.join(10)
        finally: builtins.__import__ = real
        self.assertFalse(t.is_alive())
        self.assertEqual(opened, [dead])
        self.assertEqual(imported, [], 'an import on the opener thread is the deadlock')

    def test_a_server_that_never_answers_still_gets_the_browser_opened(self):
        """Degrade to the old behaviour rather than to nothing: the owner should see their
        browser's error, not a window that never appears."""
        from taskuary import cli
        opened = []
        cli.open_when_ready('http://127.0.0.1:9', open_it=opened.append, wait=lambda u: False)
        self.assertEqual(opened, ['http://127.0.0.1:9'])


if __name__ == '__main__':
    unittest.main()
