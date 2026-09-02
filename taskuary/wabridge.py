"""The WhatsApp bridge, managed by Taskuary: install its dependency if needed, start it detached,
know whether it is up.

The bridge is a Node server beside the app. Asking a person - or a coding agent - to run
`npm install && node bridge.mjs` in a shell went wrong in every way a long-running command can:
an agent ran it in the foreground and sat on it for five minutes (a server never returns),
`npm install` of Baileys took minutes with nothing on screen, and a closed terminal killed the
bridge. So the card has a button and the API has a verb: start() installs when node_modules is
missing, spawns `node bridge.mjs` detached with its output in a log, and state() says which phase
it is in. The bridge outlives the request and the browser tab; only the machine rebooting stops it.
"""
import json, os, secrets, shutil, subprocess, threading, time
from pathlib import Path
from loguru import logger
from . import spawn

DIR = Path(__file__).resolve().parent / 'whatsapp'
LOG = DIR / 'wa-bridge.log'
_STATE = {'phase': 'idle', 'detail': '', 'pid': None, 'at': 0.0}   # idle | installing | starting | running | failed
_LOCK = threading.Lock()


def state() -> dict: return dict(_STATE)


def _set(phase, detail='', pid=None): _STATE.update(phase=phase, detail=detail[:300], pid=pid, at=time.time())


def node() -> str:
    """The node binary, or ''. which() first; then the usual Windows homes, because a Taskuary
    started from a shortcut can have a PATH older than the Node install."""
    found = shutil.which('node')
    if found: return found
    for c in (Path(os.getenv('ProgramFiles', r'C:\Program Files')) / 'nodejs' / 'node.exe',
              Path(os.getenv('LOCALAPPDATA', '')) / 'Programs' / 'nodejs' / 'node.exe',
              Path(os.getenv('APPDATA', '')) / 'nvm' / 'current' / 'node.exe', Path('/usr/local/bin/node'), Path('/opt/homebrew/bin/node')):
        if str(c) not in ('node.exe', 'nodejs') and c.exists(): return str(c)
    return ''


def _listening() -> bool:
    """Is Taskuary's managed local bridge already answering? The bridge is detached, so a
    Taskuary restart commonly finds the old process still healthy and must adopt it rather than
    launch a second copy that dies with EADDRINUSE."""
    import requests
    try: return requests.get(f'http://127.0.0.1:{port()}/status', timeout=.75).status_code < 300
    except requests.RequestException: return False


def start_configured(store) -> dict:
    """Start the managed bridge on app startup when WhatsApp is enabled.

    Every install has a seeded, inactive WhatsApp card, so existence alone is not configuration:
    Active is the owner's explicit on/off switch. A non-default bridge URL is owner-managed and
    must not cause this machine to launch another local bridge.
    """
    c = next((x for x in store.connectors_by_type('whatsapp') if x.get('Active')), None)
    if not c: return {'started': False, 'reason': 'WhatsApp is off'}
    try: cfg = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    raw = str(cfg.get('bridge_url') or '').strip().rstrip('/')
    managed = {'', f'http://127.0.0.1:{port()}', f'http://localhost:{port()}'}
    if raw not in managed:
        return {'started': False, 'reason': 'external bridge URL', 'connectorId': c['ConnectorId']}
    if _listening():
        _set('running', f'already listening on http://127.0.0.1:{port()}', pid_on_port())
        out = state()
    else:
        out = start()
    logger.info(f'wa bridge startup: connector {c["ConnectorId"]}, {out.get("phase")}')
    return {**out, 'started': True, 'connectorId': c['ConnectorId']}


def start(force_install: bool = False, wait: bool = False) -> dict:
    """Kick off install (if needed) + start on a worker thread and return at once; state() tells
    the rest. A second call while one runs is a no-op that reports the current phase. `wait` runs
    the work inline (tests, scripts) instead of on the thread."""
    if not _LOCK.acquire(blocking=False): return {**state(), 'note': 'already in progress'}
    def work():
        try:
            if not node():
                _set('failed', 'node is not installed - install Node 18+ (Windows: winget install OpenJS.NodeJS.LTS, or nodejs.org), '
                               'restart Taskuary so it sees the new PATH, then Try again'); return
            if not DIR.exists():
                _set('failed', f'the bridge folder is missing ({DIR})'); return
            if force_install or not (DIR / 'node_modules' / '@whiskeysockets').exists():
                _set('installing', 'npm install - the bridge\'s dependency (Baileys) is a few minutes on a slow line')
                npm = shutil.which('npm') or shutil.which('npm.cmd') or 'npm'
                r = spawn.run([npm, 'install', '--no-audit', '--no-fund'], cwd=str(DIR), capture_output=True, text=True, timeout=900, shell=False)
                if r.returncode != 0:
                    _set('failed', f'npm install failed: {(r.stderr or r.stdout)[-300:]}'); return
            _set('starting', 'node bridge.mjs')
            log = open(LOG, 'ab')
            kw = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, 'DETACHED_PROCESS', 0)} if os.name == 'nt' else {'start_new_session': True}
            p = subprocess.Popen([node(), 'bridge.mjs'], cwd=str(DIR), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 env={**os.environ, 'WA_BRIDGE_TOKEN': token()}, **kw)
            time.sleep(2.5)
            if p.poll() is not None:
                tail = LOG.read_bytes()[-400:].decode('utf-8', 'replace') if LOG.exists() else ''
                _set('failed', f'the bridge exited at once (code {p.returncode}): {tail}'); return
            _set('running', f'listening on http://127.0.0.1:{os.getenv("WA_BRIDGE_PORT") or 8977} - log: {LOG}', pid=p.pid)
        except Exception as e:
            logger.warning(f'wa bridge start failed: {e}')
            _set('failed', str(e))
        finally:
            _LOCK.release()
    if wait: work(); return state()
    threading.Thread(target=work, daemon=True).start()
    return {**state(), 'phase': _STATE['phase'] if _STATE['phase'] != 'idle' else 'starting'}


def port() -> int: return int(os.getenv('WA_BRIDGE_PORT') or 8977)


def token() -> str:
    """The shared secret between Taskuary and its bridge: minted once into the home, handed to the
    bridge in its environment and sent in a header on every request (bridge.mjs refuses without
    it). Before this, any local process - or any web page, via a cross-site POST to 127.0.0.1 -
    could send WhatsApp as the owner (audit 2026-09-02)."""
    from . import config
    p = config.home() / 'wa-bridge.token'
    if not p.exists(): p.write_text(secrets.token_urlsafe(24), encoding='utf-8')
    return p.read_text(encoding='utf-8').strip()


def pid_on_port(p: int = None) -> int:
    """Who is listening on the bridge port - a bridge the owner started by hand, or one from before
    a restart of Taskuary, is not in _STATE but is still the process to stop."""
    p = p or port()
    try:
        if os.name == 'nt':
            out = spawn.run(['netstat', '-ano', '-p', 'tcp'], capture_output=True, text=True, timeout=10).stdout
            for l in out.splitlines():
                cols = l.split()
                if len(cols) >= 5 and cols[0] == 'TCP' and cols[1].endswith(f':{p}') and cols[3] == 'LISTENING': return int(cols[4])
        else:
            out = subprocess.run(['lsof', '-ti', f'tcp:{p}', '-sTCP:LISTEN'], capture_output=True, text=True, timeout=10).stdout
            return int(out.split()[0]) if out.split() else 0
    except Exception as e: logger.debug(f'pid_on_port: {e}')
    return 0


def stop() -> dict:
    pid = _STATE.get('pid') or pid_on_port()
    if pid:
        try:
            if os.name == 'nt': spawn.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
            else: os.kill(pid, 15)
        except Exception as e: logger.warning(f'wa bridge stop: {e}')
    _set('idle', 'stopped')
    return state()


def restart(wait: bool = False) -> dict:
    """Stop whatever holds the port and start the bridge from the code on disk - the way a bridge
    picks up a newer bridge.mjs (an old one kept answering /status without the paired number)."""
    stop(); time.sleep(1.0)
    return start(wait=wait)
