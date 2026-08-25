"""`taskuary` - start the local server and open the app. Everything lives in ~/.taskuary."""
import argparse, socket, threading, time, webbrowser
import uvicorn
from . import __version__, config


def public_url(host, port) -> str:
    """0.0.0.0 / :: are bind addresses, not a place a browser can go."""
    shown = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    return f'http://{shown}:{port}'

def _busy(host, port):
    probe = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    with socket.socket() as s: return s.connect_ex((probe, port)) == 0

def _is_taskuary(url):
    try:
        import requests
        r = requests.get(f'{url}/api/health', timeout=2)
        if r.status_code == 200 and (r.json() or {}).get('ok') is True: return True
        return requests.get(f'{url}/api/settings', timeout=2).status_code in (200, 401)
    except Exception:
        return False


def main():
    ap = argparse.ArgumentParser(prog='taskuary', description='Automate your job - the local-first agent work hub.')
    ap.add_argument('--host', help='override [server].host (0.0.0.0 to listen on all interfaces)')
    ap.add_argument('--port', type=int, help='override [server].port')
    ap.add_argument('--no-browser', action='store_true')
    ap.add_argument('--debug', action='store_true', help='verbose console logging (requests, report runs, errors)')
    ap.add_argument('--version', action='version', version=f'taskuary {__version__}')
    # "what is actually in the prompt?" had no answer short of reading the code that builds it,
    # which is not a reasonable thing to ask of the person whose judgement is being automated
    ap.add_argument('--prompts', nargs='?', const='', metavar='MESSAGE_ID',
                    help='print the triage, reply and coding-agent prompts for a real item on '
                         'this machine - every block labelled with the document or table it '
                         'came from - then exit. Optionally for one message id.')
    args = ap.parse_args()
    if args.prompts is not None:
        import sys
        from .promptmap import render
        from .store import SQLiteStore
        # the Windows console is cp1252 and the operator documents are full of em dashes, so this
        # would die on the owner's OWN text before it printed a line of it
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        mid = int(args.prompts) if str(args.prompts).strip().isdigit() else None
        print(render(SQLiteStore(config.db_path()), message_id=mid))
        return
    from .logs import setup as setup_logs
    setup_logs(args.debug)
    cfg = config.load()
    host, port = args.host or cfg['server']['host'], args.port or cfg['server']['port']
    url = public_url(host, port)
    if _busy(host, port):
        if _is_taskuary(url):
            # don't crash into 'address already in use' - reuse the running instance
            print(f'Taskuary is already running at {url} - opening it.')
            if not args.no_browser: webbrowser.open(url)
            return
        from .desktop import free_port
        old, port = port, free_port(host)
        url = public_url(host, port)
        print(f'port {old} is in use by something else - using {port} instead')
    print(f'Taskuary {__version__} - {url}  (data: {config.db_path()})')
    if not args.no_browser:
        threading.Thread(target=lambda: (time.sleep(1.2), webbrowser.open(url)), daemon=True).start()
    uvicorn.run('taskuary.server:app', host=host, port=port, log_level='warning')


if __name__ == '__main__':
    main()
