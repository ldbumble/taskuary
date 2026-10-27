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


class Gone(Ended):
    """...before the turn's message reached it: nothing of the turn ran, so sending it again repeats nothing."""


RESTART_FAILED = 'the AI tool stopped, and stopped again when it was restarted'
MID_TURN = 'the agent stopped in the middle of its turn - nothing was sent again, as it may have done part of the work; Continue picks it up'


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
        # a process that went away while idle - killed, or its CLI updated itself under it - never gets the message: Gone, not mid-turn
        if not self.alive(): raise Gone(f'the CLI was gone before the message reached it (exit {self.p.poll()})')
        try:
            self.p.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': prompt}}) + '\n')
            self.p.stdin.flush()
        except (OSError, ValueError) as e: raise Gone(f'the CLI was gone before the message reached it ({e})')
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


def _take(key: str, cmd: list, cwd, env, resume, sig: tuple, swap: bool = False) -> Live | None:
    """The live process for this conversation, opened (or reopened) as the caller's resume id requires. `swap`: only one that is
    live and idle is replaced - None, and nothing started, when there is none or a turn is under way on it."""
    with _LOCK:
        lv = _POOL.get(key)
        if swap and (lv is None or lv.lock.locked()): return None
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


def _sig(cmd, cwd, env) -> tuple:
    # ...and the environment's NAMES: a session whose token changed kind (a task that became a stranger's: no task proof,
    # its own token - terminal.stranger_env) must not carry on in a process started with the other one
    return (tuple(cmd), str(cwd or ''), hash(tuple(sorted(env or {}))))


def warm(key: str, cmd: list, *, cwd=None, env=None, resume=None, swap: bool = False) -> bool:
    """Start the conversation's process BEFORE its first message, so the CLI's start-up (2.5-4 s of node, settings and auth)
    is paid while the owner is still reading, not after they type. The same process `run` would take for this key, command
    and resume id - so the first turn finds it ready. True when one was started; one already live is left as it is.
    `swap`: after a turn - only a live, idle process launched otherwise is replaced; none is ever started where none was (a chat
    closed meanwhile stays closed), and a turn under way is never cut."""
    with _LOCK: had = _POOL.get(key)
    lv = _take(key, cmd, cwd, env, resume, _sig(cmd, cwd, env), swap=swap)
    return lv is not None and lv is not had


def run(key: str, cmd: list, prompt: str, on_event, *, cwd=None, env=None, resume=None, cancel=None,
        timeout: float = 1200, resend: bool = False) -> tuple:
    """One turn on the conversation's live process: (result event, raw lines). A process that died between
    turns is started again once, resumed by its id, before the turn fails. `resend`: a turn with no side effects (a CLI
    with its tools off - the Assistant deciding) is sent again after ANY end, mid-turn included; one that may have done
    work mid-turn never is (MID_TURN)."""
    sig = _sig(cmd, cwd, env)
    for attempt in (1, 2):
        lv = _take(key, cmd, cwd, env, resume, sig)
        with lv.lock:
            try: return lv.turn(prompt, on_event, cancel=cancel, timeout=timeout)
            except Ended as e:
                with _LOCK:
                    if _POOL.get(key) is lv: _POOL.pop(key)
                lv.close()
                resume = lv.sid or resume
                # ONCE MORE, ON A NEW PROCESS, first turn or not: the CLI updating itself mid-session left every later turn "Broken pipe"
                # (the real-CLI walk, 2026-10-21) - and a warmed process killed before its first turn is the same case. Only a second end
                # is the caller's, said plainly (RESTART_FAILED).
                if attempt == 2: raise Ended(f'{RESTART_FAILED} ({e})') from e
                # ...but a turn that may have DONE something - an agent with tools, part-way through - is never sent twice
                if not resend and not isinstance(e, Gone): raise Ended(f'{MID_TURN} ({e})') from e
                logger.info(f'clipool: {key} ended - reopening it{" on " + resume if resume else ""} and sending the turn again')
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
