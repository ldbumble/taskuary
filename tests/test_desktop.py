"""Desktop shell tests - the embedded server really boots and serves the UI + API."""
import threading, time, unittest, urllib.request
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


if __name__ == '__main__':
    unittest.main()
