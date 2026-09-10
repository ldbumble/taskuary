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

    class FakeWindow:                      # pywebview hands one back, and main() drives it
        def load_url(self, url): events.append(('load-url', url))
        def load_html(self, html): events.append(('load-html', True))

    fake_window = FakeWindow()
    fake_server = FakeServer()

    def fake_start(func=None, *a, **k):
        # real pywebview runs `func` on its own thread and returns when the window closes. The
        # window opens FIRST now and the app boots behind it, so the boot IS what func does.
        if func: func()
        events.append(('window-returned', True))

    fake_webview = SimpleNamespace(
        create_window=lambda *a, **k: (events.append(('window', a[0])), fake_window)[1],
        start=fake_start)

    with mock.patch.object(desktop, 'start_server', return_value=(fake_server, 'http://127.0.0.1:54321')), \
         mock.patch.object(desktop, 'serving', return_value=True), \
         mock.patch.dict(sys.modules, {'webview': fake_webview}), \
         mock.patch.object(sys, 'argv', ['taskuary-desktop']):
        desktop.main()

    assert ('load-url', 'http://127.0.0.1:54321') in events, events   # the splash gave way to the app
    assert events[-1] == ('server-exit', True)
    assert fake_server.should_exit is True
