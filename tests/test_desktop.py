"""Desktop shell tests - the embedded server really boots and serves the UI + API."""
import unittest, urllib.request
from taskuary import desktop


class DesktopTests(unittest.TestCase):
    def test_free_port(self):
        a, b = desktop.free_port(), desktop.free_port()
        self.assertTrue(1024 < a < 65536 and 1024 < b < 65536)

    def test_embedded_server_serves_ui_and_api(self):
        server, url = desktop.start_server()
        try:
            self.assertTrue(server.started)
            html = urllib.request.urlopen(f'{url}/', timeout=10).read().decode()
            self.assertIn('Taskuary', html)
            api = urllib.request.urlopen(f'{url}/api/connectors', timeout=10).read().decode()
            self.assertIn('mssql', api)
        finally:
            server.should_exit = True


if __name__ == '__main__':
    unittest.main()
