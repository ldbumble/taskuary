"""`taskuary` - start the local server and open the app. Everything lives in ~/.taskuary."""
import argparse, socket, threading, time, webbrowser
import uvicorn
from . import __version__, config


def _busy(host, port):
    with socket.socket() as s: return s.connect_ex((host, port)) == 0

def _is_taskuary(url):
    try:
        import requests
        return requests.get(f'{url}/api/settings', timeout=2).status_code in (200, 401)
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(prog='taskuary', description='Automate your job - the local-first agent work hub.')
    ap.add_argument('--port', type=int, help='override [server].port')
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--debug', action='store_true', help='verbose console logging (requests, report runs, errors)')
    ap.add_argument('--version', action='version', version=f'taskuary {__version__}')
    args = ap.parse_args()
    from .logs import setup as setup_logs
    setup_logs(args.debug)
    cfg = config.load()
    host, port = cfg['server']['host'], args.port or cfg['server']['port']
    url = f'http://{host}:{port}'
    if _busy(host, port):
        if _is_taskuary(url):
            # don't crash into 'address already in use' - reuse the running instance
            print(f'Taskuary is already running at {url} - opening it.')
            if not args.no_browser: webbrowser.open(url)
            return
        from .desktop import free_port
        old, port = port, free_port(host)
        url = f'http://{host}:{port}'
        print(f'port {old} is in use by something else - using {port} instead')
    print(f'Taskuary {__version__} - {url}  (data: {config.db_path()})')
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    uvicorn.run('taskuary.server:app', host=host, port=port, log_level='warning')


if __name__ == '__main__':
    main()
