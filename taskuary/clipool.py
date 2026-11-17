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
GRACE = IDLE_SECONDS         # how long a process nobody touches stays open; an agent's TURN has no limit (the owner's ruling) - this is idle time only
MAX_LIVE = 6
INPUT = ['--input-format', 'stream-json']


class Ended(RuntimeError):
    """The process went away mid-turn: its stderr, for the caller's error message."""


class Gone(Ended):
    """...before the turn's message reached it: nothing of the turn ran, so sending it again repeats nothing."""


class TimedOut(RuntimeError):
    """A turn that ran past its limit and was killed there - not a CLI that broke. It carries the conversation it was on, so the
    work it did is picked up by Continue (general.send_prompt) instead of started again."""
    def __init__(self, msg='', session_id=None): super().__init__(msg); self.session_id = session_id


RESTART_FAILED = 'the AI tool stopped, and stopped again when it was restarted'
# ...a chat agent's CLI (this pool's only kind): typing carries it on, as no Continue button is there (general.CARRY_ON)
# ...said as what happened and why nothing ran it again ("nothing was sent again" read, on a mail task, as a word on the mail - the walk, 2026-11-11)
MID_TURN = 'the agent stopped in the middle of its turn. It may have done part of the work, so the turn was not run again - type to carry on'


class Live:
    def __init__(self, key: str, cmd: list, cwd: str, env: dict, sig: tuple):
        self.key, self.cmd, self.sig = key, cmd, sig
        self.p = spawn.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding='utf-8', errors='replace', cwd=cwd, env=env, shell=False)
        self.lines, self.err = queue.Queue(), []
        self.lock = threading.Lock()
        self.on, self.io = False, threading.Lock()       # a turn is reading (steer); `io` keeps a steer and the turn's end apart
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

    def _send(self, prompt: str):
        self.p.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': prompt}}) + '\n')
        self.p.stdin.flush()

    def turn(self, prompt: str, on_event, cancel=None, timeout: float = None) -> tuple:
        """Send one message and read until its `result`. Returns (result event, raw lines). `timeout` None: no limit - an agent's turn."""
        # a process that went away while idle - killed, or its CLI updated itself under it - never gets the message: Gone, not mid-turn
        if not self.alive(): raise Gone(f'the CLI was gone before the message reached it (exit {self.p.poll()})')
        # ...WHAT AN EARLIER TURN LEFT IN THE PIPE IS NOT THIS ONE'S (2026-11-17): words steered in just as that turn ended run as a turn nobody
        # read (and an older CLI that does not count its queue does the same) - read here, its result was this turn's answer, every later one behind
        while True:
            try: old = self.lines.get_nowait()
            except queue.Empty: break
            if old is None: self.lines.put(None); break
            logger.debug(f'clipool: {self.key} - a line left from an earlier turn dropped: {old[:200]}')
        try:
            with self.io: self._send(prompt); self.on = True
        except (OSError, ValueError) as e: raise Gone(f'the CLI was gone before the message reached it ({e})')
        try: return self._read(on_event, cancel, timeout)
        finally: self.on = False

    def _read(self, on_event, cancel, timeout) -> tuple:
        raw, end, said = [], time.time() + timeout if timeout else None, []
        while True:
            if cancel is not None and cancel.is_set():
                self.close(); raise RuntimeError('cancelled')
            left = end - time.time() if end else 0.5
            if left <= 0:
                self.close(); raise TimedOut(f'timed out after {int(timeout)}s', self.sid)
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
                if str(j.get('result') or '').strip(): said.append(str(j['result']).strip())
                # ...WORDS STEERED IN THAT THE CLI KEPT FOR A TURN OF THEIR OWN (claude's `queued_turn_count`: more results follow) are this turn's
                # too - read to the last result, its answer every one of theirs; ended at the first, the rest stood in the pipe as the next turn's
                with self.io:
                    if (j.get('queued_turn_count') or 0) > 0: continue
                    self.on = False
                return ({**j, 'result': '\n\n'.join(said)} if len(said) > 1 else j), raw
            on_event(j)

    def steer(self, said) -> bool:
        """Words INTO the turn at work (`said`: the text, or what makes it - made only once it can go in): claude's stream-json input takes a
        further user message while a turn runs and folds it into that turn, or keeps it for a turn of its own that this one reads to its end
        (_read). False, and nothing made or written, where no turn is reading."""
        with self.io:
            if not (self.on and self.alive()): return False
            text = said() if callable(said) else said
            if not text: return True
            try: self._send(text)
            except (OSError, ValueError) as e: logger.warning(f'clipool: {self.key} - words for the turn at work did not go in ({e})')
            return True


_POOL: dict[str, Live] = {}
_LOCK = threading.Lock()


def _sweep():
    now = time.time()
    with _LOCK:
        idle = [k for k, lv in _POOL.items() if not lv.lock.locked() and (now - lv.used > GRACE or not lv.alive())]
        for k in idle: _POOL.pop(k).close()
    for k in idle: logger.debug(f'clipool: closed {k} (idle or gone)')


def _reap():
    while True: time.sleep(60); _sweep()


def steerable(key: str) -> bool:
    "Is a turn at work on this conversation's live process, so words written now go into it (Live.steer)?"
    with _LOCK: lv = _POOL.get(key)
    return isinstance(lv, Live) and lv.on and lv.alive()


def steer(key: str, said) -> bool:
    "Words into the turn at work on this conversation (Live.steer): False where none is - they wait for the next turn."
    with _LOCK: lv = _POOL.get(key)
    return isinstance(lv, Live) and lv.steer(said)


def is_live(key: str) -> bool:
    with _LOCK: lv = _POOL.get(key)
    return lv is not None and lv.alive()


def touch(prefix: str) -> int:
    """The conversation is on screen: its idle clock starts again, so a task the owner is looking at never has its process reaped
    from under them. Returns how many live processes it kept."""
    n, now = 0, time.time()
    with _LOCK:
        for k, lv in _POOL.items():
            if (k == prefix or k.startswith(prefix + ':')) and lv.alive(): lv.used = now; n += 1
    return n


threading.Thread(target=_reap, daemon=True, name='clipool-reaper').start()


def _take(key: str, cmd: list, cwd, env, resume, sig: tuple, swap: bool = False) -> Live | None:
    """The live process for this conversation, opened (or reopened) as the caller's resume id requires. `swap`: only one that is
    live and idle is replaced - None, and nothing started, when there is none or a turn is under way on it."""
    with _LOCK:
        lv = _POOL.get(key)
        if swap and (lv is None or lv.lock.locked()): return None
        # a fresh conversation where one was going (New chat), another conversation named, different launch
        # settings (a model or brain changed), or a process that died: close it and start again
        why = '' if lv is None else ('its process ended' if not lv.alive() else 'its launch settings changed' if lv.sig != sig
                                     else 'a fresh conversation' if not resume and lv.turns > 0
                                     else 'another conversation' if resume and lv.sid and resume != lv.sid else '')
        if why:
            _POOL.pop(key).close(); lv = None
        if lv is None:
            if len(_POOL) >= MAX_LIVE:
                old = min((k for k, v in _POOL.items() if not v.lock.locked()), key=lambda k: _POOL[k].used, default=None)
                if old: _POOL.pop(old).close(); logger.info(f'clipool: closed {old} to make room - {MAX_LIVE} processes were open')
            # ...WHY A PROCESS STARTS, said once (a follow-up a few minutes after an answer read as a cold start, 2026-11-16): new, or what made the
            # warm one unusable - the one line that tells a slow follow-up from a warm one
            logger.info(f'clipool: starting {key}{" on " + resume if resume else ""} - {why or "none was open"}')
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
        timeout: float = None, resend: bool = False) -> tuple:
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


# ── an ACP conversation: a connection, not a process we write lines to (agents.run_acp) ─────────────────────────────────────────
# The same pool, so the idle clock, MAX_LIVE, New chat (close) and shutdown treat it as they treat a claude process. Opening one
# takes seconds (an adapter's start, initialize, session/new), so it happens OUTSIDE the lock.
def _differs(a, b) -> str:
    "Where two launch signatures differ - down to the changed leaf of a JSON part - for the line that says why a conversation was reopened."
    def leaf(x, y, at=''):
        if isinstance(x, dict) and isinstance(y, dict):
            return [p for k in sorted(set(x) | set(y)) for p in leaf(x.get(k), y.get(k), f'{at}.{k}')]
        if x == y: return []
        if isinstance(x, str) and isinstance(y, str):
            i = next((i for i, (c, d) in enumerate(zip(x, y)) if c != d), min(len(x), len(y)))
            return [f'{at} at {i}: {x[max(0, i - 40):i + 40]!r} -> {y[max(0, i - 40):i + 40]!r}']
        return [at or '.']
    out = []
    for i, (x, y) in enumerate(zip(a or (), b or ())):
        if x == y: continue
        try: out += [f'part {i}{p}' for p in leaf(json.loads(x), json.loads(y))]
        except (TypeError, ValueError): out.append(f'part {i}')
    return '; '.join(out)[:600] or 'its length'


def _stale(lv, sig, resume) -> str:
    "Why the open conversation no longer fits ('' when it does): the same four reasons _take reads for a process."
    return ('its process ended' if not lv.alive() else f'its launch settings changed ({_differs(lv.sig, sig)})' if lv.sig != sig
            else 'a fresh conversation' if not resume and lv.turns > 0
            # ...a warmed one opened fresh because `resume` was gone (agents._acp_open fresh_if_gone) is what that resume now opens
            else f'another conversation ({lv.sid} open)' if resume and lv.sid and resume != lv.sid and getattr(getattr(lv, 'client', None), 'fresh_from', None) != resume
            else '')


def _put(key: str, lv):
    with _LOCK:
        old = _POOL.get(key)
        if old is not None and old is not lv: _POOL.pop(key).close()
        if len(_POOL) >= MAX_LIVE:
            out = min((k for k, v in _POOL.items() if not v.lock.locked()), key=lambda k: _POOL[k].used, default=None)
            if out: _POOL.pop(out).close(); logger.info(f'clipool: closed {out} to make room - {MAX_LIVE} processes were open')
        _POOL[key] = lv


def take(key: str, sig: tuple, open_conn, resume=None):
    "The live ACP conversation for `key`: the open one when it still fits (same launch, same conversation), else `open_conn()`."
    with _LOCK:
        lv, why = _POOL.get(key), 'none was open'
        if lv is not None and (why := _stale(lv, sig, resume) or 'none was open') != 'none was open' and not lv.lock.locked(): _POOL.pop(key).close(); lv = None
    if lv is not None: return lv
    logger.info(f'clipool: opening {key}{" on " + resume if resume else ""} - {why}')
    lv = open_conn(); _put(key, lv)
    return lv


def warm_with(key: str, sig: tuple, open_conn, resume=None, swap: bool = False) -> bool:
    "warm() for an ACP conversation: True when one was opened. `swap`: only a live, idle one opened otherwise is replaced."
    with _LOCK: lv = _POOL.get(key)
    if swap and (lv is None or lv.lock.locked()): return False
    if lv is not None and not _stale(lv, sig, resume): return False
    take(key, sig, open_conn, resume)
    return True


def drop(key: str, lv) -> None:
    "Close a conversation that failed or was cancelled - only if it is still the one under `key`."
    with _LOCK:
        if _POOL.get(key) is lv: _POOL.pop(key)
    lv.close()


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
