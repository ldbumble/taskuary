"""Taskuary desktop: the same server + UI in a native window, shipped as one executable.

The FastAPI app runs on a free localhost port in a background thread; pywebview (Edge
WebView2 on Windows) hosts the UI. No pywebview -> graceful fallback to the default
browser, so `taskuary-desktop` is useful even from a bare pip install. Build the single
exe with `pyinstaller taskuary.spec` (see the spec at the repo root).
"""
import http.client, io, os, socket, sys, threading, time, urllib.parse, webbrowser
from pathlib import Path
# Every import serving() needs is HERE. It runs on a thread while uvicorn imports taskuary.server
# on another, and an import on both sides at once deadlocks on the import lock - which is how the
# app came to start and then never open its port at all (2026-09-09).

# Windowed (console=False) exe: std streams are None, but uvicorn's logging setup calls
# sys.stdout.isatty() and loguru writes to stderr - shim BEFORE importing uvicorn.
for _s in ('stdout', 'stderr'):
    if getattr(sys, _s) is None: setattr(sys, _s, io.StringIO())

import uvicorn
from loguru import logger
from taskuary import workerstate as _ws    # here, on the main thread: Server's flag reaches it from a signal or the quit road

SHUTDOWN_WAIT = 30.0        # the lifespan's cleanup: drain, sessions, CLI children - bounded, and loud when it is not enough
# uvicorn waits for open requests BEFORE the lifespan shutdown, and a stranger's permit is a request only that shutdown
# ends: unbounded, an orderly stop hung for good while one was held (R26, the task 10 live check)
GRACE = 5


def server_config(app, host, port) -> uvicorn.Config:
    return uvicorn.Config(app, host=host, port=port, log_level='warning', timeout_graceful_shutdown=GRACE)


class Server(uvicorn.Server):
    """uvicorn's server, whose exit flag also tells every held wait to let go (workerstate.STOP) - set by its own signal
    handler (Ctrl+C, CTRL_BREAK) and by stop_server alike, before uvicorn starts waiting on the requests those waits hold.
    The newest one is the one Quit stops (workerstate.SERVER)."""
    def __init__(self, config): super().__init__(config); _ws.SERVER[0] = self
    @property
    def should_exit(self): return self._should_exit
    @should_exit.setter
    def should_exit(self, v):
        self._should_exit = v
        (_ws.STOP.set if v else _ws.STOP.clear)()      # a new server in the same process (tests, a restart) starts unstopped
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
  .r { margin:18px auto 0; width:26px; height:26px; border-radius:50%; border:3px solid rgba(128,128,128,.22);
       border-top-color:#55697a; animation:spin .9s linear infinite }
  .e { margin-top:8px; font-size:12px; opacity:.5; font-variant-numeric:tabular-nums }
  @keyframes spin { to { transform:rotate(360deg) } }
</style>
<div class="b">
  <div class="t">Taskuary is starting up</div>
  <div class="s">Loading your work - the first start can take a minute.</div>
  <div class="r"></div><div class="e" id="e">0s</div>
</div>
<script>var t0=Date.now();setInterval(function(){var e=document.getElementById('e');if(e)e.textContent=Math.round((Date.now()-t0)/1000)+'s'},1000)</script>"""

STALLED = (SPLASH.replace('Taskuary is starting up', 'Taskuary could not start')
                 .replace('Loading your work - the first start can take a minute.',
                          'The window is here but the server never answered. See desktop-error.log next to your data.')
                 .replace('<div class="r"></div><div class="e" id="e">0s</div>', ''))


def splash(text: str = None):
    """The exe's own splash (taskuary.spec: Splash), up before the bundle unpacked: say what is happening on it, or close it once
    the window is up. Nothing at all when this is not the packaged exe."""
    try: import pyi_splash
    except ImportError: return
    try:
        if text: pyi_splash.update_text(text)
        else: pyi_splash.close()
    except Exception: pass


# CLOSING IS NOT QUITTING where there is a tray (the owner, 2026-10-25: "Close keeps Taskuary running. Quit is an explicit option"):
# the X hides the window, the server and the work it runs carry on, and the tray icon says so (welcome.tray_goodbye). Open Taskuary
# brings the window back; Quit is the only road that stops it, and it goes the way closing always went - asking first when work runs,
# then the goodbye that says what Taskuary cannot see while it is closed (welcome.goodbye). With no tray (not Windows, or no .NET),
# closing is still quitting, exactly as before.
GOODBYE_SECS = 3.0
BALLOON_MS = 6000


class Tray:
    """The Windows tray icon, with Open Taskuary and Quit. It has its own STA thread and message loop: pywebview's loop belongs to the
    window, and the icon has to keep answering while that window is hidden. A press runs on a thread of its own, so the icon's loop
    never waits on the window."""
    def __init__(self, on_open, on_quit): self.on_open, self.on_quit, self.icon, self.ctx, self._wf = on_open, on_quit, None, None, None
    def _go(self, f): threading.Thread(target=f, daemon=True).start()
    def start(self, wait: float = 5.0) -> bool:
        net = dotnet()
        if not net: return False
        WF, D, Thread, ThreadStart, ApartmentState = net
        ready = threading.Event()
        def run():
            try:
                ico = Path(__file__).parent / 'web' / 'favicon.ico'
                n, m = WF.NotifyIcon(), WF.ContextMenuStrip()
                n.Icon, n.Text = (D.Icon(str(ico)) if ico.is_file() else D.SystemIcons.Application), 'Taskuary'
                o, q = m.Items.Add('Open Taskuary'), m.Items.Add('Quit')
                o.Font = D.Font(o.Font, D.FontStyle.Bold)          # the default, as a double-click on the icon
                o.Click += lambda *_: self._go(self.on_open); q.Click += lambda *_: self._go(self.on_quit)
                n.DoubleClick += lambda *_: self._go(self.on_open)
                n.ContextMenuStrip, n.Visible = m, True
                self.icon, self.ctx, self._wf = n, WF.ApplicationContext(), WF
            except Exception as e: logger.warning(f'tray: the icon did not come up - {e}'); return
            finally: ready.set()
            WF.Application.Run(self.ctx)
        t = Thread(ThreadStart(run)); t.SetApartmentState(ApartmentState.STA); t.IsBackground = True; t.Start()
        ready.wait(wait)
        return self.icon is not None
    def say(self, text: str):
        """The goodbye, as the icon's balloon: the window it would have been shown in is already hidden."""
        if not (self.icon and text): return
        try: self.icon.ShowBalloonTip(BALLOON_MS, 'Taskuary', text[:250], getattr(self._wf.ToolTipIcon, 'None'))
        except Exception as e: logger.debug(f'tray: the goodbye was not shown - {e}')
    def stop(self):
        """Gone with the app - an icon left behind sits in the tray until the mouse passes over it."""
        n, self.icon = self.icon, None
        try:
            if n: n.Visible = False; n.Dispose()
            if self.ctx: self.ctx.ExitThread()
        except Exception as e: logger.debug(f'tray: not stopped cleanly - {e}')


_NET = []


def dotnet():
    """The .NET pieces the tray is made of, imported once, or None off Windows or without .NET. IMPORTED on the main thread before the
    window opens (the import-lock note at the top) - but the icon is CREATED only after pywebview has set its WinForms app up: that
    calls SetCompatibleTextRenderingDefault, which throws once any window exists, and a NotifyIcon is one (2026-10-25)."""
    if _NET: return _NET[0]
    net = None
    if sys.platform == 'win32':
        try:
            try: import clr
            except Exception: os.environ['PYTHONNET_RUNTIME'] = 'coreclr'; import clr     # the order pywebview's winforms tries them in
            clr.AddReference('System.Windows.Forms'); clr.AddReference('System.Drawing')
            import System.Windows.Forms as WF, System.Drawing as D
            from System.Threading import Thread, ThreadStart, ApartmentState
            net = (WF, D, Thread, ThreadStart, ApartmentState)
        except Exception as e: logger.info(f'tray: none on this machine, so closing quits - {e}')
    _NET.append(net)
    return net


def tray(on_open, on_quit):
    """A started Tray, or None where there is none - and then closing quits, as it always did."""
    t = Tray(on_open, on_quit)
    return t if t.start() else None


def goodbye_html(text: str) -> str:
    import html
    return (SPLASH.replace('Taskuary is starting up', 'Taskuary is closing')
                  .replace('Loading your work - the first start can take a minute.', html.escape(text))
                  .replace('<div class="r"></div><div class="e" id="e">0s</div>', ''))


def _server_store():
    """The running app's store - already imported by the boot, so nothing is imported here (see the note at the top)."""
    return getattr(sys.modules.get('taskuary.server'), 'store', None)


def farewell(store, tray: bool = False) -> str:
    """The goodbye, with the close written down; '' when it cannot be said - a goodbye never holds a window open."""
    if store is None: return ''
    try:
        from taskuary import welcome
        return welcome.closing(store, tray=tray)
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


def allow_downloads(webview) -> bool:
    """Every Download in the window SAVES. pywebview (5+) ships ALLOW_DOWNLOADS off, and its WebView2 handler then cancels each
    download as it starts - so Download on a file an agent made, a mail attachment or a published page was a click that did
    nothing at all, with no error anywhere (the owner, 2026-10-28: "this did not work - both preview and download?"). On, the
    window asks where to save it, as a browser does. An older pywebview has no switch and downloads already."""
    s = getattr(webview, 'settings', None)
    if not isinstance(s, dict): return False
    s['ALLOW_DOWNLOADS'] = True
    return True


def closing_handler(window, store_of=_server_store, secs: float = GOODBYE_SECS, shell: dict = None):
    """pywebview's `closing` event. With a tray (`shell['tray']`) a close that is not a Quit HIDES the window and the tray says the
    goodbye; nothing stops. A Quit (`shell['quit']`), or any close with no tray: with work running, the first close ASKS (Keep working /
    Close anyway) and holds the window; a second close while it asks is the answer. Then - or straight away when nothing runs - the
    goodbye goes in the window and it closes `secs` later; returning False holds it for that moment, and a close after that goes
    straight through. `shell['gone']`: the server has already stopped (a Quit from the browser), so the window simply goes. The work
    runs on its own thread: the event may arrive on the GUI thread, which load_html and hide also need."""
    st, shell = {'said': False, 'asking': None}, shell if shell is not None else {}
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
        back, st['asking'], shell['quit'] = st['asking'], None, False      # ...and the next X hides again
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
    def hide():
        try: window.hide()
        except Exception as e: logger.debug(f'closing: the window did not hide - {e}')
        shell['tray'].say(farewell(store_of(), tray=True))
    def on_closing():
        if st['said'] or shell.get('gone'): return True
        if shell.get('tray') and not shell.get('quit'):
            threading.Thread(target=hide, daemon=True).start(); return False
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


def held_elsewhere() -> str:
    """The Taskuary serving THIS data folder from another port, or '': one per folder (instance.py), and the configured
    port is only where it usually is - a start that found its port taken moved to a free one."""
    from taskuary import instance
    at = instance.holder().get('url') or ''
    return at if at and serving(at, secs=3) else ''


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
    server = Server(server_config(app, host, port))
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
    splash('Starting Taskuary...')
    from taskuary import __version__, config
    argv = sys.argv[1:]
    from taskuary.logs import setup as setup_logs
    setup_logs('--debug' in argv)
    from taskuary import unpack           # imported here, on the main thread (the import-lock note above)
    threading.Thread(target=unpack.sweep_stale, daemon=True, name='unpack-sweep').start()   # old _MEI folders a sweeper missed
    port =int(argv[argv.index('--port') + 1]) if '--port' in argv else None

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
        splash()
        server, _ = headless()
        wait_for_exit(server)
        return 0 if stop_server(server) != 'timeout' else 1
    # every window and browser this opens carries a one-time key: the page seeds the owner token only for one (R29)
    from taskuary import launchkey
    try:
        import webview
    except Exception:                # no pywebview at all -> the browser, as before
        filed(); splash()
        server, url = headless()
        webbrowser.open(launchkey.link(url)); wait_for_exit(server)
        return 0 if stop_server(server) != 'timeout' else 1

    # The window opens FIRST and says what is happening, then the app boots behind it. Importing
    # the app is ~8s cold before uvicorn exists at all, so the alternative is what the owner
    # actually saw: their own window telling them it could not connect, for 18 seconds.
    # ...and if one is already up, this window is a VIEW of it, not a second copy of the app.
    allow_downloads(webview)
    running = already_serving() or held_elsewhere()
    held, booted = {}, threading.Event()
    # a view of another process's server: that server mints the key, asked with the owner token this install keeps
    view = launchkey.remote_link(running, config.load()['server'].get('token') or '') if running else None
    # MAXIMIZED, on whatever screen it is: a fixed 1280x840 was taller than a laptop's work area, so every launch - an update's
    # relaunch included - opened hanging off the screen's edge (TQ-1251). Restore still gives the 1280x840 window.
    window = webview.create_window('Taskuary', url=view, html=None if running else SPLASH,
                                   width=1280, height=840, min_size=(900, 600), maximized=True)
    # the window is up: the exe's splash hands over to it (and its own spinner and seconds take the wait from here)
    try: window.events.shown += lambda: splash()
    except Exception: pass
    if running:
        print(f'Taskuary is already running at {running} - opening that one.')
        webview.start()
        return 0

    # this window owns the server: closing it hides it in the tray, and the tray's Quit quits - saying goodbye first (a view of another
    # one does neither). No tray, and closing is quitting.
    shell = {'tray': None, 'quit': False, 'gone': False}
    def show():
        try: window.show(); window.restore()
        except Exception as e: logger.debug(f'tray: the window did not come back - {e}')
    def quit_():
        shell['quit'] = True; show()      # in view: a Quit with work running asks in the window first
        try: window.destroy()
        except Exception as e: logger.debug(f'tray: the window was already gone - {e}')
    dotnet()                              # imported here, on the main thread; the icon comes up in opened(), once the window has
    try: window.events.closing += closing_handler(window, lambda: _server_store() if 'server' in held else None, shell=shell)
    except Exception as e: logger.debug(f'closing: no goodbye on this pywebview - {e}')

    def gone_with(server):
        """Quit pressed in the browser stops the server (POST /api/quit): the window it served goes too, with nothing left to ask."""
        wait_for_exit(server, poll=0.5)
        shell['gone'] = True
        try: window.destroy()
        except Exception as e: logger.debug(f'quitting: the window was already gone - {e}')

    def opened():
        splash()                     # in case `shown` never fired on this pywebview
        shell['tray'] = tray(show, quit_)
        try: held['server'], url = boot()
        except Exception:
            filed(); window.load_html(STALLED); return
        finally: booted.set()
        threading.Thread(target=gone_with, args=(held['server'],), daemon=True).start()
        if serving(url): window.load_url(launchkey.link(url))
        else: window.load_html(STALLED)

    try:
        webview.start(opened)
    except Exception:                # the window died mid-flight -> finish in the browser
        filed()
        if 'server' not in held:
            try: held['server'], url = boot()
            except Exception: filed(); raise
            webbrowser.open(launchkey.link(url)); wait_for_exit(held['server'])
    # A window CLOSED during the boot is new - there was no window to close before this. Give the
    # boot its moment to hand the server over, or its lifespan never gets told to stop and the
    # tasks it owns stay in_progress until the next launch repairs them.
    booted.wait(BOOT_WAIT)
    if shell['tray']: shell['tray'].stop()
    # the window is gone; the process is not - not until the server has stopped what it started
    server = held.get('server')
    return 0 if server is None or stop_server(server) != 'timeout' else 1


def leave(code) -> int:
    """The exe's last word: the lifespan has stopped what the server started, so the unpack folder is handed to a
    quiet sweeper rather than to the bootloader, whose answer to a straggler is a dialog (unpack.py)."""
    try:
        from taskuary import unpack
        unpack.handoff()
    except Exception as e: logger.debug(f'leaving: no handoff - {e}')
    return code or 0


if __name__ == '__main__':
    sys.exit(leave(main()))

