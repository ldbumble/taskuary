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


# CLOSING IS QUITTING: the server stops with the window, and there is no tray to keep watching (the owner has not chosen
# one). So the window says what is true before it goes - what Taskuary cannot see while it is closed, and where the mail
# waits meanwhile (welcome.goodbye) - and the next open counts what came in from this moment.
GOODBYE_SECS = 3.0


def goodbye_html(text: str) -> str:
    import html
    return (SPLASH.replace('Taskuary is starting up', 'Taskuary is closing')
                  .replace('Reading your work - this takes a few seconds.', html.escape(text))
                  .replace('<div class="d"><i></i><i></i><i></i></div>', ''))


def _server_store():
    """The running app's store - already imported by the boot, so nothing is imported here (see the note at the top)."""
    return getattr(sys.modules.get('taskuary.server'), 'store', None)


def farewell(store) -> str:
    """The goodbye, with the close written down; '' when it cannot be said - a goodbye never holds a window open."""
    if store is None: return ''
    try:
        from taskuary import welcome
        return welcome.closing(store)
    except Exception as e:
        logger.warning(f'closing: no goodbye - {e}'); return ''


# CLOSING STOPS WORK THAT IS RUNNING, so it asks first. The X used to kill every live agent three seconds after a goodbye that
# never mentioned them (B3, 2026-10-11). The question is a page in the window rather than a native box: pywebview's own
# confirmation dialog only says OK / Cancel, and the owner should not have to work out which of those keeps the work going.
ASK = """<!doctype html>
<meta charset="utf-8">
<title>Taskuary</title>
<style>
  :root { color-scheme: light dark }
  body { margin:0; height:100vh; display:grid; place-items:center; background:#faf9f7; color:#3a3a38;
         font:14px/1.5 -apple-system,"Segoe UI",system-ui,sans-serif }
  @media (prefers-color-scheme: dark) { body { background:#1b1b1a; color:#e7e5e1 } button { background:#262624; color:inherit } }
  .b { text-align:center; max-width:440px; padding:0 16px }
  .t { font-size:15px; font-weight:600; letter-spacing:.01em }
  .s { margin-top:6px; opacity:.7 }
  .r { margin-top:20px; display:flex; gap:10px; justify-content:center }
  button { font:inherit; padding:7px 16px; border-radius:6px; border:1px solid #b9b5ad; background:#fff; color:#3a3a38; cursor:pointer }
  button.p { font-weight:600 }
</style>
<div class="b">
  <div class="t">Work is still running</div>
  <div class="s">{text}</div>
  <div class="r">
    <button class="p" autofocus onclick="window.pywebview && pywebview.api.keep_working()">Keep working</button>
    <button onclick="window.pywebview && pywebview.api.close_anyway()">Close anyway</button>
  </div>
</div>"""
ASK_NATIVE = '{text}\n\nOK closes Taskuary anyway. Cancel keeps it working.'


def ask_html(text: str) -> str:
    import html
    return ASK.replace('{text}', html.escape(text))


def busy(store) -> list:
    """The tasks the close would stop; [] when that cannot be said - a question never holds a window shut for good."""
    if store is None: return []
    try:
        from taskuary import welcome
        return welcome.working(store)
    except Exception as e:
        logger.warning(f'closing: could not count running work - {e}'); return []


def closing_handler(window, store_of=_server_store, secs: float = GOODBYE_SECS):
    """pywebview's `closing` event. With work running, the first close ASKS (Keep working / Close anyway) and holds the window;
    a second close while it asks is the answer. Then - or straight away when nothing runs - the goodbye goes in the window and
    it closes `secs` later; returning False holds it for that moment, and a close after that goes straight through. The work
    runs on its own thread: the event may arrive on the GUI thread, which load_html also needs."""
    st = {'said': False, 'asking': None}
    def bye():
        """Say goodbye and close - False when there is nothing to say and the window may simply go."""
        st['said'], st['asking'] = True, None
        text = farewell(store_of())
        if not text: return False
        def show():
            try:
                window.load_html(goodbye_html(text)); time.sleep(secs)
            except Exception as e: logger.debug(f'closing: the goodbye was not shown - {e}')
            finally:
                try: window.destroy()
                except Exception as e: logger.debug(f'closing: the window was already gone - {e}')
        threading.Thread(target=show, daemon=True).start()
        return True
    def keep_working():
        back, st['asking'] = st['asking'], None
        if back:
            try: window.load_url(back)
            except Exception as e: logger.debug(f'closing: could not go back to the app - {e}')
    def close_anyway():
        if st['asking'] is None or st['said']: return
        if not bye():
            try: window.destroy()
            except Exception as e: logger.debug(f'closing: the window was already gone - {e}')
    try: window.expose(keep_working, close_anyway)
    except Exception as e: logger.debug(f'closing: this pywebview cannot take the answer from the page - {e}')
    def ask(text):
        try: back = window.get_current_url()
        except Exception: back = None
        if back:                                  # the page asks, and Keep working goes back to where they were
            st['asking'] = back
            try: window.load_html(ask_html(text)); return
            except Exception as e: logger.debug(f'closing: the question was not shown - {e}')
        st['asking'] = ''                         # ...else the toolkit's own box: OK / Cancel, said in words beside it
        try: ok = window.create_confirmation_dialog('Work is still running', ASK_NATIVE.format(text=text))
        except Exception as e:
            logger.debug(f'closing: no question could be asked - {e}'); ok = True
        if ok: close_anyway()
        else: st['asking'] = None
    def on_closing():
        if st['said']: return True
        if st['asking'] is not None: return not bye()      # closed again while asked: that is the answer
        work = busy(store_of())
        if work:
            from taskuary import welcome          # busy() has imported it already - nothing is imported on this thread
            st['asking'] = ''
            threading.Thread(target=ask, args=(welcome.still_working(work),), daemon=True).start()
            return False
        return not bye()
    return on_closing


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


def already_serving(host='127.0.0.1', port=None):
    """The Taskuary ALREADY RUNNING on this machine, or ''. 

    The desktop bound a fresh random port on every launch and never asked, so a second launch was a
    second SERVER - two pollers, two schedulers and two writers on one SQLite file, each with its own
    window (the owner, 2026-09-22: "taskuary desktop is opening twice always"). It is also why a
    running app could never be found by its configured port."""
    from taskuary import config
    cfg = config.load()
    host = host or cfg['server'].get('host') or '127.0.0.1'
    port = port or cfg['server'].get('port') or 7787
    probe = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    with socket.socket() as s:
        if s.connect_ex((probe, int(port))) != 0: return ''
    url = f'http://{probe}:{int(port)}'
    return url if serving(url, secs=3) else ''      # something else on that port is not ours to open


def start_server(host='127.0.0.1', port=None):
    """Run the app in a daemon thread; returns (server, url) once it accepts connections.

    The configured port first, so the app a person starts is the app they can find; a random one
    only when that port is taken by something that is not us."""
    from taskuary import config, __version__ as _v   # noqa: F401 - config is the port's source
    from taskuary.server import app  # absolute: PyInstaller runs this file as a script
    if port is None:
        want = config.load()['server'].get('port') or 7787
        probe = '127.0.0.1' if host in ('0.0.0.0', '::') else host
        with socket.socket() as s: port = want if s.connect_ex((probe, int(want))) != 0 else free_port(host)
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
    # ...and if one is already up, this window is a VIEW of it, not a second copy of the app.
    running = already_serving()
    held, booted = {}, threading.Event()
    window = webview.create_window('Taskuary', url=running or None, html=None if running else SPLASH,
                                   width=1280, height=840, min_size=(900, 600))
    if running:
        print(f'Taskuary is already running at {running} - opening that one.')
        webview.start()
        return 0

    # this window owns the server, so closing it is quitting - it says goodbye first (a view of another one does not)
    try: window.events.closing += closing_handler(window, lambda: _server_store() if 'server' in held else None)
    except Exception as e: logger.debug(f'closing: no goodbye on this pywebview - {e}')

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

