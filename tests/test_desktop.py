"""Desktop shell tests - the embedded server really boots and serves the UI + API."""
import unittest, urllib.request
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
            server.should_exit = True


if __name__ == '__main__':
    unittest.main()
