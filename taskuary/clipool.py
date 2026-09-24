"""Live CLI conversations: one Claude process per chat, kept open between turns.

A headless `claude -p` used to be started for EVERY model call and exited after it, the conversation carried
by `--resume <id>`. Each call paid the CLI's start-up again - measured on the owner's machine, 4.2 s a turn
that way against 1.0-1.2 s once the process is already running - and a turn with a look-up is two or three
calls (the owner, 2026-09-24: "of course it should keep open session ... instead of reopening each time").

Claude Code's stream-json INPUT keeps one process and takes each message as a JSON line on stdin; a `result`
event closes each turn. The conversation is the same one `--resume` names, so nothing about what the caller
sees changes: the same answer text, the same session id, the same trace events.

What a live process costs is looked after here: one turn at a time per conversation, closed when idle
(IDLE_SECONDS) or when the pool is full (MAX_LIVE, oldest first), killed on cancel or timeout and simply
started again - resumed by its id - on the next message, and all of them closed when the app exits. New chat
closes its conversation's process (close()); a caller that asks to resume a different conversation, or none,
gets a fresh one. Started through spawn.py, so Windows never opens a console window for it.
"""
import atexit, json, queue, subprocess, threading, time
from loguru import logger

from . import spawn

IDLE_SECONDS = 30 * 60
MAX_LIVE = 6
INPUT = ['--input-format', 'stream-json']


class Ended(RuntimeError):
    """The process went away mid-turn: its stderr, for the caller's error message."""


class Live:
    def __init__(self, key: str, cmd: list, cwd: str, env: dict, sig: tuple):
        self.key, self.cmd, self.sig = key, cmd, sig
        self.p = spawn.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding='utf-8', errors='replace', cwd=cwd, env=env, shell=False)
        self.lines, self.err = queue.Queue(), []
        self.lock = threading.Lock()
        self.sid, self.turns, self.used = None, 0, time.time()
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=lambda: self.err.append(self.p.stderr.read() or ''), daemon=True).start()

    def _pump(self):
        try:
            for line in self.p.stdout: self.lines.put(line)
        finally: self.lines.put(None)

    def alive(self) -> bool: return self.p.poll() is None

    def close(self):
        try: self.p.stdin.close()
        except Exception: pass
        try: self.p.kill()
        except Exception: pass

    def turn(self, prompt: str, on_event, cancel=None, timeout: float = 1200) -> tuple:
        """Send one message and read until its `result`. Returns (result event, raw lines)."""
        self.p.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': prompt}}) + '\n')
        self.p.stdin.flush()
        raw, end = [], time.time() + timeout
        while True:
            if cancel is not None and cancel.is_set():
                self.close(); raise RuntimeError('cancelled')
            left = end - time.time()
            if left <= 0:
                self.close(); raise RuntimeError(f'timed out after {int(timeout)}s')
            try: line = self.lines.get(timeout=min(left, 0.5))
            except queue.Empty: continue
            if line is None:
                time.sleep(0.2)
                raise Ended(''.join(self.err).strip() or f'the CLI exited ({self.p.poll()})')
            line = line.rstrip('\n')
            if not line.strip(): continue
            raw.append(line)
            try: j = json.loads(line)
            except ValueError: continue
            if not isinstance(j, dict): continue
            if j.get('type') == 'result':
                self.turns += 1; self.used = time.time()
                self.sid = j.get('session_id') or self.sid
                return j, raw
            on_event(j)


_POOL: dict[str, Live] = {}
_LOCK = threading.Lock()


def _reap():
    while True:
        time.sleep(60)
        now = time.time()
        with _LOCK:
            idle = [k for k, lv in _POOL.items() if not lv.lock.locked() and (now - lv.used > IDLE_SECONDS or not lv.alive())]
            for k in idle: _POOL.pop(k).close()
        for k in idle: logger.debug(f'clipool: closed {k} (idle or gone)')


threading.Thread(target=_reap, daemon=True, name='clipool-reaper').start()


def _take(key: str, cmd: list, cwd, env, resume, sig: tuple) -> Live:
    """The live process for this conversation, opened (or reopened) as the caller's resume id requires."""
    with _LOCK:
        lv = _POOL.get(key)
        # a fresh conversation where one was going (New chat), another conversation named, different launch
        # settings (a model or brain changed), or a process that died: close it and start again
        stale = lv is not None and (not lv.alive() or lv.sig != sig
                                     or (not resume and lv.turns > 0)
                                     or (resume and lv.sid and resume != lv.sid))
        if stale:
            _POOL.pop(key).close(); lv = None
        if lv is None:
            if len(_POOL) >= MAX_LIVE:
                old = min((k for k, v in _POOL.items() if not v.lock.locked()), key=lambda k: _POOL[k].used, default=None)
                if old: _POOL.pop(old).close()
            lv = Live(key, cmd + INPUT + (['--resume', resume] if resume else []), cwd, env, sig)
            if resume: lv.sid = resume
            _POOL[key] = lv
        return lv


def run(key: str, cmd: list, prompt: str, on_event, *, cwd=None, env=None, resume=None, cancel=None,
        timeout: float = 1200) -> tuple:
    """One turn on the conversation's live process: (result event, raw lines). A process that died between
    turns is started again once, resumed by its id, before the turn fails."""
    sig = (tuple(cmd), str(cwd or ''))
    for attempt in (1, 2):
        lv = _take(key, cmd, cwd, env, resume, sig)
        with lv.lock:
            try: return lv.turn(prompt, on_event, cancel=cancel, timeout=timeout)
            except Ended:
                with _LOCK:
                    if _POOL.get(key) is lv: _POOL.pop(key)
                lv.close()
                resume = lv.sid or resume
                if attempt == 2 or lv.turns == 0: raise
                logger.info(f'clipool: {key} ended between turns - reopening it on {resume}')
            except Exception:
                with _LOCK:
                    if _POOL.get(key) is lv: _POOL.pop(key)
                lv.close(); raise


def close(prefix: str) -> int:
    """Close every live conversation whose key starts with `prefix` - New chat, a finished general task."""
    with _LOCK:
        keys = [k for k in _POOL if k.startswith(prefix)]
        gone = [_POOL.pop(k) for k in keys]
    for lv in gone: lv.close()
    return len(gone)


def live() -> list:
    """What is open right now: [{'key', 'sid', 'turns', 'idle'}] - for a status line or a test."""
    now = time.time()
    with _LOCK: return [{'key': k, 'sid': v.sid, 'turns': v.turns, 'idle': round(now - v.used)} for k, v in _POOL.items() if v.alive()]


@atexit.register
def shutdown():
    close('')
