"""Taskuary desktop: the same server + UI in a native window, shipped as one executable.

The FastAPI app runs on a free localhost port in a background thread; pywebview (Edge
WebView2 on Windows) hosts the UI. No pywebview -> graceful fallback to the default
browser, so `taskuary-desktop` is useful even from a bare pip install. Build the single
exe with `pyinstaller taskuary.spec` (see the spec at the repo root).
"""
import socket, sys, threading, time, webbrowser
import uvicorn


def free_port(host='127.0.0.1') -> int:
    with socket.socket() as s:
        s.bind((host, 0)); return s.getsockname()[1]


def start_server(host='127.0.0.1', port=None):
    """Run the app in a daemon thread; returns (server, url) once it accepts connections."""
    from taskuary.server import app  # absolute: PyInstaller runs this file as a script
    port = port or free_port(host)
    server = uvicorn.Server(uvicorn.Config(app, host=host, port=port, log_level='warning'))
    threading.Thread(target=server.run, daemon=True).start()
    for _ in range(200):
        if server.started: break
        time.sleep(0.05)
    return server, f'http://{host}:{port}'


def main():
    from taskuary import __version__, config
    argv = sys.argv[1:]
    port = int(argv[argv.index('--port') + 1]) if '--port' in argv else None
    server, url = start_server(port=port)
    print(f'Taskuary {__version__} desktop - {url}  (data: {config.db_path()})')
    if '--server-only' in argv:  # headless mode: CI smoke tests, or run as a service
        try:
            while not server.should_exit: time.sleep(1)
        except KeyboardInterrupt: pass
        return
    try:
        import webview
        webview.create_window('Taskuary', url, width=1280, height=840, min_size=(900, 600))
        webview.start()
    except ImportError:
        webbrowser.open(url)
        try:
            while True: time.sleep(3600)
        except KeyboardInterrupt: pass
    server.should_exit = True


if __name__ == '__main__':
    main()
