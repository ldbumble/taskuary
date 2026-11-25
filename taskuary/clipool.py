"""Live CLI conversations: one Claude process per chat, kept open between turns.

A headless `claude -p` used to be started for EVERY model call and exited after it, the conversation carried
by `--resume <id>`. Each call paid the CLI's start-up again - measured on the owner's machine, 4.2 s a turn
that way against 1.0-1.2 s once the process is already running - and a turn with a look-up is two or three
calls (the owner, 2026-09-24: "of course it should keep open session ... instead of reopening each time").

Claude Code's stream-json INPUT keeps one process and takes each message as a JSON line on stdin; a `result`
event closes each turn. The conversation is the same one `--resume` names, so nothing about what the caller
sees changes: the same answer text, the same session id, the same trace events.

What a live process costs is looked after here: one turn at a time per conversation, closed when idle
(IDLE_SECONDS) or when the pool is full (MAX_LIVE: the oldest at rest - never one at work), killed on cancel or timeout and simply
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
REST = 60                    # ...a conversation used this recently is between the steps of one piece of work - never what makes room (_room)
INPUT = ['--input-format', 'stream-json']


class Ended(RuntimeError):
    """The process went away mid-turn: its stderr, for the caller's error message."""


class Gone(Ended):
    """...before the turn's message reached it: nothing of the turn ran, so sending it again repeats nothing."""


class Unfinished(RuntimeError):
    """A TURN THAT DID NOT FINISH, ON ANY ROAD (the one-shot run, the kept process, ACP): stopped, out of time, ended early. It carries the
    conversation it was on, which the caller keeps (general.send_prompt), so the next turn picks that conversation up instead of opening
    another - and it is never sent again, as part of it may have run."""
    def __init__(self, msg='', session_id=None): super().__init__(msg); self.session_id = session_id


class TimedOut(Unfinished):
    """A turn that ran past its limit and was killed there - not a CLI that broke: the work it did is picked up by Continue."""


class PartWay(Unfinished):
    "A turn its agent ended part-way: it died mid-turn (MID_TURN), or ended it early (a refusal, a limit), before a word or after some. Never sent again: part of it may have run."


class Cancelled(Unfinished):
    "A turn the owner stopped - the one way every road says it (str: 'cancelled')."
    def __init__(self, session_id=None): super().__init__('cancelled', session_id)


RESTART_FAILED = 'the AI tool stopped, and stopped again when it was restarted'
# ...a chat agent's CLI (this pool's only kind): typing carries it on, as no Continue button is there (general.CARRY_ON)
# ...said as what happened and why nothing ran it again ("nothing was sent again" read, on a mail task, as a word on the mail - the walk, 2026-11-11)
MID_TURN = 'the agent stopped in the middle of its turn. It may have done part of the work, so the turn was not run again - type to carry on'
# ...and one its agent ENDED EARLY (an ACP adapter's stopReason, a CLI's own result): the fewest sentences true of each reason - a refusal is
# the model's no, a limit one it reached (max_tokens, max_turn_requests; claude's error_max_turns), anything else said as no more than it is -
# in the same voice, with the same way on. A refusal or a limit may come after words, and any of them after tool calls ran: no words does not
# mean no work, and words do not mean it finished
ENDED_EARLY = {'refusal': 'the agent declined to finish this turn. It may have done part of the work, so the turn was not run again - '
                          'type to carry on, or say it another way',
               'limit': 'the agent reached its limit for one turn before it finished. It may have done part of the work, so the turn was not run '
                        'again - type to carry on',
               'other': 'the agent ended its turn before it answered. It may have done part of the work, so the turn was not run again - type to '
                        'carry on'}
LIMITS = ('max_tokens', 'max_turn_requests', 'error_max_turns')
def ended_early(stop: str) -> str: return ENDED_EARLY['refusal' if stop == 'refusal' else 'limit' if stop in LIMITS else 'other']


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
        spawn.end(self.p)                                # ...and what it runs: a command it started ended with it (walk 21)
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
                self.close(); raise Cancelled(self.sid)
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
            self.sid = self.sid or j.get('session_id')          # ...named from its init on: a turn stopped or cut before its result keeps it
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
            text = _look(said)
            if not text: return True
            try: self._send(text)
            except (OSError, ValueError) as e:
                logger.warning(f'clipool: {self.key} - words for the turn at work did not go in ({e})'); return False
            _took(said); return True


_POOL: dict[str, Live] = {}
_LOCK = threading.Lock()


# A FULL POOL CLOSES ONLY WHAT IS AT REST, AND OTHERWISE WAITS (walk 9, 2026-11-23: three agents "died mid-turn" at once, 13 tasks open): it
# closed the oldest conversation with no turn LOCKED on it - and the only unlocked ones were those just opened, whose turns had not yet
# taken their lock. An agent at work is never killed (the owner: only finish or Stop): dead ones go first, then one at rest (no turn on it,
# untouched for REST), and with none a new start waits here - _LOCK held on the way in and out, let go while it waits
def _room(key: str):
    said = False
    while len(_POOL) >= MAX_LIVE:
        now = time.time()
        out = next((k for k, v in _POOL.items() if not v.alive()), None) or min(
            (k for k, v in _POOL.items() if k != key and not v.lock.locked() and now - v.used > REST), key=lambda k: _POOL[k].used, default=None)
        if out:
            _POOL.pop(out).close(); logger.info(f'clipool: closed {out}, at rest, to make room - {MAX_LIVE} processes were open'); continue
        if not said: logger.info(f'clipool: {key} waits for room - all {MAX_LIVE} open conversations are at work'); said = True
        _LOCK.release()
        try: time.sleep(0.5)
        finally: _LOCK.acquire()


def _sweep():
    now = time.time()
    with _LOCK:
        idle = [k for k, lv in _POOL.items() if not lv.lock.locked() and (now - lv.used > GRACE or not lv.alive())]
        for k in idle: _POOL.pop(k).close()
    for k in idle: logger.debug(f'clipool: closed {k} (idle or gone)')


def _reap():
    while True: time.sleep(60); _sweep()


# HIS LINE REACHES THE AGENT AT ITS NEXT STEP ON EVERY ROAD THAT CAN TAKE IT (design round 3, 2026-11-18: "sign up yourself" sat unheard 13
# minutes behind a 15-minute turn on Codex): claude's stream-json input (Live.steer), an ACP agent that steers (`_session/steering`: claude-agent-
# acp and codex-acp both say so at initialize), and an API card's own loop, which reads what was said to it between its tool calls (`ear`)
_EARS: dict[str, list] = {}


def _acp_turn(lv) -> bool:
    "A kept ACP conversation (acp.Conversation) with a turn on it, whose agent takes words mid-turn."
    c = getattr(lv, 'client', None)
    return c is not None and lv.lock.locked() and lv.alive() and bool(getattr(c, 'can_steer', lambda: False)())


def takes_words(key: str) -> bool:
    "Can this conversation's road take his words in the middle of a turn at all - a fact of the road, not of this instant (the waiting line says so)."
    with _LOCK: lv, ear = _POOL.get(key), key in _EARS
    return ear or isinstance(lv, Live) or bool(getattr(getattr(lv, 'client', None), 'can_steer', lambda: False)())


def steerable(key: str) -> bool:
    "Is a turn at work on this conversation that takes words written now (Live.steer, an ACP steer, an API loop's ear)?"
    with _LOCK: lv, ear = _POOL.get(key), key in _EARS
    return ear or (isinstance(lv, Live) and lv.on and lv.alive()) or _acp_turn(lv)


def steer(key: str, said) -> bool:
    """Words into the turn at work on this conversation: False where none is - they wait for the next turn. `said`: the text, or what makes it
    (it takes his kept lines) - made only once it can go in: an API loop makes it at its next step, so one it never reaches stays kept."""
    with _LOCK:
        lv = _POOL.get(key)
        if (ear := _EARS.get(key)) is not None: ear.append(said); return True
    if isinstance(lv, Live): return lv.steer(said)
    if not _acp_turn(lv): return False
    text = _look(said)
    if not text: return True
    # ...WORDS THAT DID NOT GO IN ARE NOT HEARD (the agent audit, 2026-11-22: a turn that ended between the look and the request answered
    # "promptRequired", and his line stood heard with nothing answering it): False, and they stay his waiting lines - the next turn's
    try: got = lv.client.steer(text)
    except Exception as e: got = str(e)
    if got != 'injected':
        logger.warning(f'clipool: {key} - words for the turn at work did not go in ({got or "no answer"}): {text[:200]}'); return False
    _took(said); return True


def _looks(said) -> bool:
    "Can this maker of words make them without taking what they are made of (its `take`)?"
    import inspect
    try: return callable(said) and 'take' in inspect.signature(said).parameters
    except (TypeError, ValueError): return False
def _look(said) -> str:
    "The words to steer, made from what waits without taking it (general.Session.steer's lines) - a maker with no look takes as it makes."
    return said(take=False) if _looks(said) else said() if callable(said) else said
def _took(said) -> None:
    "They went in: what they were made of is taken now, heard where they went in."
    if _looks(said): said(take=True)


def ear(key: str):
    "An API turn at work opens its ear (apiagent.turn): what is steered to its conversation waits here for its next step."
    with _LOCK: _EARS[key] = []


def heard(key: str, last: bool = False) -> str:
    """What was said to the turn since its last step, made now (his kept lines taken as it goes in). `last`: the turn is about to answer - with
    nothing waiting its ear closes in the same step, so a word steered after is the next turn's, never lost between."""
    with _LOCK:
        got = list(_EARS.get(key) or [])
        if key in _EARS: _EARS[key].clear()
        if last and not got: _EARS.pop(key, None)
    return '\n\n'.join(t for t in ((f() if callable(f) else f) for f in got) if t)


def deaf(key: str):
    "The turn is over, however it ended: its ear closes; what never went in is still kept, the next turn's."
    with _LOCK: _EARS.pop(key, None)


def is_live(key: str) -> bool:
    with _LOCK: lv = _POOL.get(key)
    return lv is not None and lv.alive()


def touch(prefix: str) -> int:
    """The conversation is on screen: its idle clock starts again, so a task the owner is looking at never has its process reaped
    from under them. Returns how many live processes it kept."""
    n, now = 0, time.time()
    with _LOCK:
        for k, lv in _POOL.items():
            if _under(k, prefix) and lv.alive(): lv.used = now; n += 1
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
            _room(key)
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
                if not resend and not isinstance(e, Gone): raise PartWay(f'{MID_TURN} ({e})', resume) from e
                logger.info(f'clipool: {key} ended - reopening it{" on " + resume if resume else ""} and sending the turn again')
            except Exception:
                with _LOCK:
                    if _POOL.get(key) is lv: _POOL.pop(key)
                lv.close(); raise


# ── A SPARE FOR A ONE-SHOT ANSWER (the speed round, 2026-11-20): triage started a fresh `claude -p` for every arrival and paid its start-up
# each time - 3-7 s of a 10-13 s verdict, measured on the real CLI. A one-shot call with no tools (a judgement: nothing it can do, so asking
# again repeats nothing) now takes a process started ahead for its exact command, waiting for its one message, and starts the next one
# for the call after. Taken whole, never shared: each answer is a conversation of its own. Kept apart from the pool's conversations, so a
# spare never pushes an agent's out, and few: the oldest goes when there are more than SPARES.
_SPARES: dict[str, Live] = {}
SPARES = 2


def spare_turn(key: str, cmd: list, prompt: str, on_event, *, cwd=None, env=None, cancel=None, timeout: float = None) -> tuple:
    """One answer on a fresh process for `cmd` - the spare started ahead when there is one - then the next spare started. (result, raw).
    A process that ended before or during the answer is replaced once and asked again, as nothing it was asked can have run."""
    cmd = list(cmd) + INPUT
    with _LOCK: lv = _SPARES.pop(key, None)
    if lv is not None and (not lv.alive() or time.time() - lv.used > GRACE): lv.close(); lv = None
    try:
        for attempt in (1, 2):
            if lv is None: lv = Live(key, cmd, cwd, env, ())
            try: return lv.turn(prompt, on_event, cancel=cancel, timeout=timeout)
            except Ended as e:
                lv.close(); lv = None
                if attempt == 2: raise Ended(f'{RESTART_FAILED} ({e})') from e
    finally:
        if lv is not None: lv.close()
        if cancel is None or not cancel.is_set(): _ready(key, cmd, cwd, env)


def _ready(key: str, cmd: list, cwd, env):
    "The next spare for this command, started now so its CLI is up by the next call."
    try: nxt = Live(key, cmd, cwd, env, ())
    except Exception as e: logger.debug(f'clipool: no spare started for {key} - {e}'); return
    with _LOCK:
        old = [x for x in [_SPARES.pop(key, None)] if x]
        _SPARES[key] = nxt
        while len(_SPARES) > SPARES: old.append(_SPARES.pop(next(iter(_SPARES))))
    for x in old: x.close()


def spares() -> int:
    with _LOCK: return sum(1 for lv in _SPARES.values() if lv.alive())


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
        _room(key)
        _POOL[key] = lv


def take(key: str, sig: tuple, open_conn, resume=None):
    "The live ACP conversation for `key`: the open one when it still fits (same launch, same conversation), else `open_conn()`."
    with _LOCK:
        lv, why = _POOL.get(key), 'none was open'
        if lv is not None and (why := _stale(lv, sig, resume) or 'none was open') != 'none was open' and not lv.lock.locked(): _POOL.pop(key).close(); lv = None
    if lv is not None: return lv
    logger.info(f'clipool: opening {key}{" on " + resume if resume else ""} - {why}')
    t0 = time.time(); lv = open_conn(); _put(key, lv)
    logger.info(f'clipool: {key} open in {time.time() - t0:.1f}s')          # ...the start-up a first turn waits on, said beside its reason
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


def _under(k: str, prefix: str) -> bool:
    """`k` is `prefix`'s conversation or one under it ('general:1', 'general:1:x'; 'concierge:' takes every concierge one; '' takes all) - by
    whole parts: as a bare string prefix, task 1's agent idling out closed task 10's (walk 14, 2026-11-24: 'general:1' took 'general:10',
    1.3 s into its first turn)."""
    return not prefix or k == prefix or k.startswith(prefix.rstrip(':') + ':')


def close(prefix: str) -> int:
    """Close every live conversation that is `prefix`'s or under it (_under) - New chat, a finished general task."""
    with _LOCK:
        keys = [k for k in _POOL if _under(k, prefix)]
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
    with _LOCK: gone = list(_SPARES.values()); _SPARES.clear()
    for lv in gone: lv.close()
