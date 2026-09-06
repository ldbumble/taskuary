"""P0-ISOLATION shutdown characterization; awaited cleanup remains a later release gate."""
import sys
from types import SimpleNamespace
from unittest import mock

from taskuary import desktop


def test_desktop_window_exit_signals_the_embedded_server_to_shutdown():
    events = []

    class FakeServer:
        started = True
        _should_exit = False

        @property
        def should_exit(self):
            return self._should_exit

        @should_exit.setter
        def should_exit(self, value):
            self._should_exit = value
            events.append(('server-exit', value))

    fake_server = FakeServer()
    fake_webview = SimpleNamespace(
        create_window=lambda *a, **k: events.append(('window', a[0])),
        start=lambda: events.append(('window-returned', True)))

    with mock.patch.object(desktop, 'start_server', return_value=(fake_server, 'http://127.0.0.1:54321')), \
         mock.patch.dict(sys.modules, {'webview': fake_webview}), \
         mock.patch.object(sys, 'argv', ['taskuary-desktop']):
        desktop.main()

    assert events[-1] == ('server-exit', True)
    assert fake_server.should_exit is True
