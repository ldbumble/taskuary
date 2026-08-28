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
import os, shutil, subprocess, threading, time
from pathlib import Path
from loguru import logger

DIR = Path(__file__).resolve().parent / 'whatsapp'
LOG = DIR / 'wa-bridge.log'
_STATE = {'phase': 'idle', 'detail': '', 'pid': None, 'at': 0.0}   # idle | installing | starting | running | failed
_LOCK = threading.Lock()


def state() -> dict: return dict(_STATE)


def _set(phase, detail='', pid=None): _STATE.update(phase=phase, detail=detail[:300], pid=pid, at=time.time())


def node() -> str:
    """The node binary, or ''. Windows keeps npm's node next to the CLI shims; a plain which() finds it."""
    return shutil.which('node') or ''


def start(force_install: bool = False, wait: bool = False) -> dict:
    """Kick off install (if needed) + start on a worker thread and return at once; state() tells
    the rest. A second call while one runs is a no-op that reports the current phase. `wait` runs
    the work inline (tests, scripts) instead of on the thread."""
    if not _LOCK.acquire(blocking=False): return {**state(), 'note': 'already in progress'}
    def work():
        try:
            if not node():
                _set('failed', 'node is not installed - install Node 18+ from nodejs.org, then try again'); return
            if not DIR.exists():
                _set('failed', f'the bridge folder is missing ({DIR})'); return
            if force_install or not (DIR / 'node_modules' / '@whiskeysockets').exists():
                _set('installing', 'npm install - the bridge\'s dependency (Baileys) is a few minutes on a slow line')
                npm = shutil.which('npm') or shutil.which('npm.cmd') or 'npm'
                r = subprocess.run([npm, 'install', '--no-audit', '--no-fund'], cwd=str(DIR), capture_output=True, text=True, timeout=900, shell=False)
                if r.returncode != 0:
                    _set('failed', f'npm install failed: {(r.stderr or r.stdout)[-300:]}'); return
            _set('starting', 'node bridge.mjs')
            log = open(LOG, 'ab')
            kw = {'creationflags': subprocess.CREATE_NEW_PROCESS_GROUP | getattr(subprocess, 'DETACHED_PROCESS', 0)} if os.name == 'nt' else {'start_new_session': True}
            p = subprocess.Popen([node(), 'bridge.mjs'], cwd=str(DIR), stdout=log, stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, **kw)
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


def stop() -> dict:
    pid = _STATE.get('pid')
    if pid:
        try:
            if os.name == 'nt': subprocess.run(['taskkill', '/PID', str(pid), '/T', '/F'], capture_output=True)
            else: os.kill(pid, 15)
        except Exception as e: logger.warning(f'wa bridge stop: {e}')
    _set('idle', 'stopped')
    return state()
