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
from datetime import datetime, timedelta
from pathlib import Path
from loguru import logger
from . import spawn

DIR = Path(__file__).resolve().parent / 'whatsapp'
LOG = DIR / 'wa-bridge.log'
_STATE = {'phase': 'idle', 'detail': '', 'pid': None, 'at': 0.0}   # idle | installing | starting | running | failed
_LOCK = threading.Lock()


def state() -> dict: return dict(_STATE)


# Baileys logs every protocol frame it handles and the bridge appends all of it to one file. Nothing
# rotated it: on the owner's machine it reached 205 MB (2026-09-15). logs.py has given the app's own
# log rotation for a long time; loguru never sees this one, because a Node subprocess writes it.
LOG_KEEP_DAYS, LOG_MAX_BYTES = 3, 25 * 1024 * 1024
LOG_RAN_KEY = 'wa_log_trimmed_at'


def _stamp(value):
    try: return datetime.strptime(str(value)[:19], '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError): return None


def trim_log(store, now: datetime = None) -> dict | None:
    """Empty the bridge's log once it is big, or a few days old. Looked at once a day, like retention.

    TRUNCATED IN PLACE, never renamed or deleted: the running bridge holds this file open in append
    mode, and on Windows a held-open file cannot be moved. An append handle always writes at the end,
    so the bridge keeps logging across the truncation without noticing.
    """
    now = now or datetime.now()
    if not LOG.exists(): return None
    last = str(store.get_setting(LOG_RAN_KEY) or '')
    if last[:10] == now.strftime('%Y-%m-%d'): return None          # already looked today
    size = LOG.stat().st_size
    since = _stamp(last)
    aged = bool(last) and (since is None or since <= now - timedelta(days=LOG_KEEP_DAYS))
    trimmed = size > LOG_MAX_BYTES or aged
    if trimmed:
        try:
            with open(LOG, 'r+b') as f: f.truncate(0)
            logger.info(f'whatsapp bridge log: emptied {size / 1e6:.1f} MB')
        except OSError as e:
            logger.debug(f'could not empty the bridge log: {e}')
            trimmed = False
    store.set_setting(LOG_RAN_KEY, now.strftime('%Y-%m-%d %H:%M:%S'), 'wabridge')
    return {'trimmed': trimmed, 'bytes': size}


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


def _status() -> dict | None:
    """The running bridge's /status, or None when nothing answers. WITH the token: the bridge refuses /status
    without it, and a 401 read as "nothing running" launched a second copy that died on EADDRINUSE while the old
    one kept serving (2026-09-25 - the owner's poll never came, because the bridge answering was this morning's)."""
    import requests
    try: r = requests.get(f'http://127.0.0.1:{port()}/status', headers={'x-bridge-token': token()}, timeout=.75)
    except requests.RequestException: return None
    if r.status_code == 401: return {}                    # something answers on the port, just not to us
    try: return r.json() if r.status_code < 300 else None
    except ValueError: return {}


def _listening() -> bool:
    """Is Taskuary's managed local bridge already answering? The bridge is detached, so a
    Taskuary restart commonly finds the old process still healthy and must adopt it rather than
    launch a second copy that dies with EADDRINUSE."""
    return _status() is not None


def code() -> str:
    """The fingerprint of the bridge code on disk - the same bytes, the same order, the same hash the bridge reports
    as `code` in /status (bridge.mjs CODE)."""
    import hashlib
    files = sorted(p for p in DIR.glob('*.mjs') if not p.name.endswith('.test.mjs'))
    return hashlib.sha1(b''.join(p.read_bytes() for p in files)).hexdigest()[:12]


def stale() -> bool:
    """The bridge answering runs older code than is on disk (an update landed while it kept running)."""
    st = _status()
    return st is not None and st.get('code') != code()


def wait_listening(secs: float) -> bool:
    """Give a just-launched bridge a moment to answer before anyone polls it."""
    end = time.time() + secs
    while time.time() < end:
        if _listening(): return True
        time.sleep(0.5)
    return False


_GRACE_SPENT = False


def ready(secs: float = 8) -> bool:
    """Spend the launch grace for a just-started bridge - once per process, and never on the
    startup path.

    This wait used to sit in the FastAPI lifespan, which uvicorn will not accept a single
    connection until it yields: both launches on 2026-09-09 burned the full 8 seconds there, so
    the window was up in front of the owner saying "can't connect" for 18s. wait_listening has no
    side effect - it only delays whoever calls it - so the grace cannot move to a thread and
    still mean anything. It belongs to whichever POLL asks first, which is who it was always for:
    the point was that the first poll must not file a false "bridge not running".
    """
    global _GRACE_SPENT
    if _GRACE_SPENT: return True
    _GRACE_SPENT = True          # a LAUNCH grace, spent whether or not it answered in time
    return wait_listening(secs)


def filter_policy(store, connector_id: int) -> dict:
    """The same allow-list used by Python ingestion, ready before Baileys receives offline messages.
    Without this launch-time copy, a restarted bridge could acknowledge its pending queue before
    the first poll had time to call /filter and lose messages from chats the owner did authorize."""
    c = store.get_connector(int(connector_id)) or {}
    try: cfg = json.loads(c.get('ConfigJson') or '{}')
    except ValueError: cfg = {}
    srcs = [s for s in store.list_sources() if s.get('Channel') == 'whatsapp'
            and int(s.get('ConnectorId') or connector_id) == int(connector_id) and s.get('Address')]
    exact = {str(s['Address']).strip() for s in srcs if str(s['Address']).strip() != '*'}
    notify = str(cfg.get('notify_chat') or '').strip()
    assistant = str(cfg.get('assistant_chat') or '').strip()
    if notify: exact.add(notify)
    if assistant: exact.add(assistant)
    return {'allDirect': any(str(s['Address']).strip() == '*' for s in srcs), 'jids': sorted(exact)}


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
    if _listening() and stale():
        # an update landed while the detached bridge kept running: adopt it and the new code never runs
        logger.info('wa bridge startup: the running bridge is older than the code on disk - restarting it')
        out = restart(filter_policy=filter_policy(store, c['ConnectorId']))
    elif _listening():
        _set('running', f'already listening on http://127.0.0.1:{port()}', pid_on_port())
        out = state()
    else:
        out = start(filter_policy=filter_policy(store, c['ConnectorId']))
    logger.info(f'wa bridge startup: connector {c["ConnectorId"]}, {out.get("phase")}')
    return {**out, 'started': True, 'connectorId': c['ConnectorId']}


def start(force_install: bool = False, wait: bool = False, filter_policy: dict = None) -> dict:
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
            env = {**os.environ, 'WA_BRIDGE_TOKEN': token()}
            if filter_policy is not None: env['WA_BRIDGE_FILTER'] = json.dumps(filter_policy, separators=(',', ':'))
            p = subprocess.Popen([node(), 'bridge.mjs'], cwd=str(DIR), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL,
                                 env=env, **kw)
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
    if not p.exists():
        p.write_text(secrets.token_urlsafe(24), encoding='utf-8')
        if os.name != 'nt':
            try: p.chmod(0o600)
            except OSError: pass
    elif os.name != 'nt':
        try: p.chmod(0o600)
        except OSError: pass
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


def restart(wait: bool = False, filter_policy: dict = None) -> dict:
    """Stop whatever holds the port and start the bridge from the code on disk - the way a bridge
    picks up a newer bridge.mjs (an old one kept answering /status without the paired number)."""
    stop(); time.sleep(1.0)
    return start(wait=wait, filter_policy=filter_policy)
