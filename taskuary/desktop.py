"""Taskuary desktop: the same server + UI in a native window, shipped as one executable.

The FastAPI app runs on a free localhost port in a background thread; pywebview (Edge
WebView2 on Windows) hosts the UI. No pywebview -> graceful fallback to the default
browser, so `taskuary-desktop` is useful even from a bare pip install. Build the single
exe with `pyinstaller taskuary.spec` (see the spec at the repo root).
"""
import io, socket, sys, threading, time, webbrowser

# Windowed (console=False) exe: std streams are None, but uvicorn's logging setup calls
# sys.stdout.isatty() and loguru writes to stderr - shim BEFORE importing uvicorn.
for _s in ('stdout', 'stderr'):
    if getattr(sys, _s) is None: setattr(sys, _s, io.StringIO())

import uvicorn
from loguru import logger

SHUTDOWN_WAIT = 30.0        # the lifespan's cleanup: drain, sessions, CLI children - bounded, and loud when it is not enough


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
    try:
        server, url = start_server(port=port)
    except Exception:
        import traceback
        try: (config.home() / 'desktop-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        except OSError: pass
        raise
    print(f'Taskuary {__version__} desktop - {url}  (data: {config.db_path()})')
    if '--server-only' in argv:  # headless mode: CI smoke tests, or run as a service
        wait_for_exit(server)
        return 0 if stop_server(server) != 'timeout' else 1
    try:
        import webview
        webview.create_window('Taskuary', url, width=1280, height=840, min_size=(900, 600))
        webview.start()
    except Exception:
        # no native window (pywebview missing or its runtime broke) -> browser fallback,
        # never an error dialog; the traceback lands next to the data for diagnosis
        import traceback
        try: (config.home() / 'desktop-error.log').write_text(traceback.format_exc(), encoding='utf-8')
        except OSError: pass
        webbrowser.open(url)
        wait_for_exit(server)
    # the window is gone; the process is not - not until the server has stopped what it started (PW-261/263)
    return 0 if stop_server(server) != 'timeout' else 1


if __name__ == '__main__':
    sys.exit(main() or 0)

