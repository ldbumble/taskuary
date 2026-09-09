"""Taskuary desktop: the same server + UI in a native window, shipped as one executable.

The FastAPI app runs on a free localhost port in a background thread; pywebview (Edge
WebView2 on Windows) hosts the UI. No pywebview -> graceful fallback to the default
browser, so `taskuary-desktop` is useful even from a bare pip install. Build the single
exe with `pyinstaller taskuary.spec` (see the spec at the repo root).
"""
import http.client, io, socket, sys, threading, time, urllib.parse, webbrowser
# Every import serving() needs is HERE. It runs on a thread while uvicorn imports taskuary.server
# on another, and an import on both sides at once deadlocks on the import lock - which is how the
# app came to start and then never open its port at all (2026-09-09).

# Windowed (console=False) exe: std streams are None, but uvicorn's logging setup calls
# sys.stdout.isatty() and loguru writes to stderr - shim BEFORE importing uvicorn.
for _s in ('stdout', 'stderr'):
    if getattr(sys, _s) is None: setattr(sys, _s, io.StringIO())

import uvicorn
from loguru import logger

SHUTDOWN_WAIT = 30.0        # the lifespan's cleanup: drain, sessions, CLI children - bounded, and loud when it is not enough
BOOT_WAIT = 120.0           # how long the splash will wait for the server before it says so

# Shown in the window from the moment it opens until the server answers. Importing the app is
# ~8s cold on its own (fastapi/pydantic, ~600 modules) and the lifespan runs after it, so the
# owner sat in front of a connection error for 18 seconds and had no way to know the app was
# working (2026-09-09). Quiet, and it says the one thing worth knowing.
SPLASH = """<!doctype html>
<meta charset="utf-8">
<title>Taskuary</title>
<style>
  :root { color-scheme: light dark }
  body { margin:0; height:100vh; display:grid; place-items:center; background:#faf9f7; color:#3a3a38;
         font:14px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif }
  @media (prefers-color-scheme: dark) { body { background:#1b1b1a; color:#e7e5e1 } }
  .b { text-align:center }
  .t { font-size:15px; font-weight:600; letter-spacing:.01em }
  .s { margin-top:6px; opacity:.6 }
  .d { margin-top:18px; display:flex; gap:5px; justify-content:center }
  .d i { width:5px; height:5px; border-radius:50%; background:currentColor; opacity:.25;
         animation:p 1.4s ease-in-out infinite }
  .d i:nth-child(2){animation-delay:.2s} .d i:nth-child(3){animation-delay:.4s}
  @keyframes p { 0%,80%,100%{opacity:.2} 40%{opacity:.7} }
</style>
<div class="b">
  <div class="t">Taskuary is starting up</div>
  <div class="s">Reading your work - this takes a few seconds.</div>
  <div class="d"><i></i><i></i><i></i></div>
</div>"""

STALLED = (SPLASH.replace('Taskuary is starting up', 'Taskuary could not start')
                 .replace('Reading your work - this takes a few seconds.',
                          'The window is here but the server never answered. See desktop-error.log next to your data.'))


def serving(url: str, secs: float = BOOT_WAIT) -> bool:
    """Is the server ANSWERING yet - not merely started.

    Any HTTP reply counts, a 401 included: the question is whether the port is alive, and the
    owner token makes some paths refuse. Only a dead socket means "not yet".

    http.client rather than urlopen, because urlopen reads the proxy configuration on every call
    and on Windows that is a lazy `import winreg` - an import on this thread, which is the one
    thing this function may not do."""
    host, _, port = urllib.parse.urlsplit(url).netloc.partition(':')
    end = time.time() + secs
    while time.time() < end:
        c = http.client.HTTPConnection(host, int(port or 80), timeout=2)
        try:
            c.request('GET', '/api/health'); c.getresponse(); return True   # a 401 answered too
        except Exception:
            time.sleep(0.25)
        finally: c.close()
    return False


def free_port(host='127.0.0.1') -> int:
    with socket.socket() as s:
        s.bind((host, 0)); return s.getsockname()[1]


def start_server(host='127.0.0.1', port=None):
    """Run the app in a daemon thread; returns (server, url) once it accepts connections."""
    from taskuary.server import app  # absolute: PyInstaller runs this file as a script
    port = port or free_port(host)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level='warning'))
    server.thread = threading.Thread(target=server.run, daemon=True); server.thread.start()   # kept: quitting joins it
    for _ in range(200):
        if server.started: break
        time.sleep(0.05)
    return server, f'http://{host}:{port}'


def stop_server(server, timeout: float = SHUTDOWN_WAIT) -> str:
    """Quit means: tell the server to exit, then WAIT for its lifespan to finish - workers stopped, CLI children
    killed, task/run state written. A daemon thread abandoned at process exit did none of that (PW-261). Bounded:
    past `timeout` the process still exits, but the log says the cleanup is unverified rather than done (PW-263)."""
    thread = getattr(server, 'thread', None)
    if thread is None or not thread.is_alive(): server.should_exit = True; return 'not_running'
    server.should_exit = True
    logger.info('quitting: waiting for the server to finish its cleanup')
    t0 = time.monotonic()
    while thread.is_alive() and time.monotonic() - t0 < timeout:
        thread.join(0.25)
        if thread.is_alive() and int(time.monotonic() - t0) % 5 == 0 and (time.monotonic() - t0) % 5 < 0.25:
            logger.info(f'quitting: still stopping workers ({int(time.monotonic() - t0)}s)')
    if thread.is_alive():
        logger.error(f'quitting: cleanup did not finish within {timeout:.0f}s - a worker or CLI child may still be running; exiting anyway')
        return 'timeout'
    logger.info('quitting: cleanup finished')
    return 'clean'


def wait_for_exit(server, poll: float = 1.0):
    """The no-window fallback used to sleep for ever; now it ends the moment the server is told to exit."""
    try:
        while not server.should_exit: time.sleep(poll)
    except KeyboardInterrupt: pass


def main():
    from taskuary import __version__, config
    argv = sys.argv[1:]
    from taskuary.logs import setup as setup_logs
    setup_logs('--debug' in argv)
    port = int(argv[argv.index('--port') + 1]) if '--port' in argv else None

    def filed():
        """Whatever just failed, next to the data - never an error dialog."""
        import traceback
        try: (config.home() / 'desktop-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        except OSError: pass

    def boot():
        """Import the app and start serving. The ~8s import lives in here, behind the splash."""
        server, url = start_server(port=port)
        print(f'Taskuary {__version__} desktop - {url}  (data: {config.db_path()})')
        return server, url

    def headless():
        try: server, url = boot()
        except Exception: filed(); raise
        return server, url

    if '--server-only' in argv:      # CI smoke tests, or run as a service
        server, _ = headless()
        wait_for_exit(server)
        return 0 if stop_server(server) != 'timeout' else 1
    try:
        import webview
    except Exception:                # no pywebview at all -> the browser, as before
        filed()
        server, url = headless()
        webbrowser.open(url); wait_for_exit(server)
        return 0 if stop_server(server) != 'timeout' else 1

    # The window opens FIRST and says what is happening, then the app boots behind it. Importing
    # the app is ~8s cold before uvicorn exists at all, so the alternative is what the owner
    # actually saw: their own window telling them it could not connect, for 18 seconds.
    held, booted = {}, threading.Event()
    window = webview.create_window('Taskuary', html=SPLASH, width=1280, height=840, min_size=(900, 600))

    def opened():
        try: held['server'], url = boot()
        except Exception:
            filed(); window.load_html(STALLED); return
        finally: booted.set()
        if serving(url): window.load_url(url)
        else: window.load_html(STALLED)

    try:
        webview.start(opened)
    except Exception:                # the window died mid-flight -> finish in the browser
        filed()
        if 'server' not in held:
            try: held['server'], url = boot()
            except Exception: filed(); raise
            webbrowser.open(url); wait_for_exit(held['server'])
    # A window CLOSED during the boot is new - there was no window to close before this. Give the
    # boot its moment to hand the server over, or its lifespan never gets told to stop and the
    # tasks it owns stay in_progress until the next launch repairs them.
    booted.wait(BOOT_WAIT)
    # the window is gone; the process is not - not until the server has stopped what it started
    server = held.get('server')
    return 0 if server is None or stop_server(server) != 'timeout' else 1


if __name__ == '__main__':
    sys.exit(main() or 0)

