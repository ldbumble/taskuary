"""`taskhub` - start the local server and open the app. Everything lives in ~/.taskhub."""
import argparse, threading, time, webbrowser
import uvicorn
from . import __version__, config


def main():
    ap = argparse.ArgumentParser(prog='taskhub', description='Automate Your Work - local task-driven agent hub.')
    ap.add_argument('--port', type=int, help='override [server].port')
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--version', action='version', version=f'taskhub {__version__}')
    args = ap.parse_args()
    cfg = config.load()
    host, port = cfg['server']['host'], args.port or cfg['server']['port']
    url = f'http://{host}:{port}'
    print(f'TaskHub {__version__} - {url}  (data: {config.db_path()})')
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    uvicorn.run('taskhub.server:app', host=host, port=port, log_level='warning')


if __name__ == '__main__':
    main()
