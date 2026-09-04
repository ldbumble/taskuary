"""Real terminals, in the app: a CLI agent (or a plain shell) spawned under a pseudo-tty,
its bytes streamed to the browser over a WebSocket and rendered by xterm.js. This is the ONLY
way an agent works here: headless runs are gone (see the note at the foot of agents.py), so
every piece of work happens somewhere you can watch it, interrupt it and answer it - the
agent's own TUI, its approval prompts and your typing all go through this.

Windows uses ConPTY via pywinpty; POSIX uses the stdlib pty module.
"""
import json, os, re, shutil, subprocess, threading, time, uuid
from collections import deque
from datetime import datetime
from loguru import logger

SCROLLBACK = 200_000        # chars kept for late joiners / reconnects
SESSIONS = {}               # sid -> Term. Iterate a list(...) copy: readers run on FastAPI worker threads while
                            # close()/reap() pop from it - "dictionary changed size during iteration" mid-wrap-up
SEED_WAIT, SEED_QUIET = 25, 1.2     # seconds: how long to wait for a TUI, and what 'settled' means
# settle() waits for QUIET - and a TUI with an animated boot spinner is never quiet, so every
# settle in the seed path used to burn its full cap (codex took ~30s before the prompt showed).
# The toe probe makes long waits unnecessary: settle caps stay short, readiness is VERIFIED.
SEED_SETTLE = 3
SEED_ENTER = 1.0                    # how long to give the TUI to react to Enter before pressing again
SEED_RETRIES, SEED_BUDGET = 3, 180  # retype attempts after a boot dialog ate the prompt, and the total window
# One giant write loses characters: a TUI's input loop reads in frames, and a multi-KB burst
# arrives faster than it drains - ~150 chars of a 2.4KB seed's FRONT vanished mid-stream in
# live testing (Ink's long-paste dropping). Chunks with a breath between give it frames.
SEED_CHUNK, SEED_CHUNK_GAP = 160, .03
DOC_CHARS = 1800                    # how much of CODER.md rides along in the prompt
SOUL_CHARS = 1200                   # ...and of SOUL.md: context, not the operative ruleset,
                                    # and every char is another char to type into a TUI
# The fastest way to type a prompt is not to type it at all: these CLIs take the first prompt
# on the COMMAND LINE, so the session starts with it already submitted - instant, and immune
# to boot dialogs eating keystrokes (codex's update chooser once swallowed half a toe and the
# session opened on a beheaded ask). Typed seeding (Term.seed) stays for CLIs without one.
SEED_ARGV = {'claude': lambda s: [s], 'codex': lambda s: [s], 'gemini': lambda s: ['-i', s]}

def seed_argv(profile: dict, seed: str):
    """The argv tail that hands the CLI its first prompt directly - None when only typing can."""
    name = os.path.basename(str(profile.get('cmd') or 'claude')).lower()
    return next((f(seed) for k, f in SEED_ARGV.items() if k in name), None)


# A terminal must start a FRESH session. Taskuary can itself be launched from inside an
# agent CLI, and those processes export session markers that make the child resume /
# inherit the parent's conversation - strip anything that would carry that in.
_DIRTY = ('CLAUDE_CODE', 'CLAUDECODE', 'CLAUDE_SESSION', 'ANTHROPIC_SESSION', 'CODEX_SESSION', 'GEMINI_SESSION')

def clean_env(extra: dict = None) -> dict:
    # child_env, not os.environ: a CLI with no home directory refuses to start at all
    # ("Error finding codex home: Could not find home directory") and a Taskuary launched
    # from a service or a scrubbed shortcut does not always have one to pass down.
    from .agents import child_env
    env = {k: v for k, v in child_env().items() if not k.upper().startswith(_DIRTY)}
    # per-session additions: the browser session name that ties an agent's agent-browser to
    # its pane (browserview) - set after the strip, so it wins over an inherited one
    env.update(extra or {})
    # the pane IS a real terminal (xterm.js): say so. A service started with no TERM, or TERM=dumb,
    # made codex stop at "Codex's interactive TUI may not work in this terminal. Continue? [y/N]"
    # before a single prompt - the owner typed y into a box that was built for exactly this.
    if env.get('TERM', 'dumb').lower() in ('', 'dumb'): env['TERM'] = 'xterm-256color'
    env.setdefault('COLORTERM', 'truecolor')
    return env


def session_env(agent: str = '', task_id=None, cwd: str = '') -> dict:
    """What a CLI needs to know about ITSELF. `taskuary --note "..."` inside an agent's terminal
    should not have to be told which agent or which task it is - the session already knows, so
    it says so in the environment."""
    from . import config, guard
    srv = config.load()['server']
    host = '127.0.0.1' if srv.get('host') in ('0.0.0.0', '::', '', None) else srv.get('host')
    out = {k: str(v) for k, v in (('TASKUARY_AGENT', agent), ('TASKUARY_TASK', task_id or ''),
                                  ('TASKUARY_CWD', cwd),
                                  # A bare shell has no Taskuary job and should carry no ambient
                                  # app context. Task-backed agents need the exact running URL so
                                  # they reuse it instead of starting another port.
                                  ('TASKUARY_URL', f'http://{host}:{srv.get("port") or 7787}' if task_id else '')) if v}
    # ...and the token that says WHO IS ASKING. It is what --note, --learned and --done
    # authenticate with, and it is what the middleware reads to refuse this session the routes
    # that send (guard.DENIED). Less authority than the owner has, by construction rather than by
    # instruction: an untrusted message can argue with a paragraph, not with a header.
    tok = srv.get('agent_token')
    if tok: out[guard.AGENT_ENV] = tok
    return out


class _WinPty:
    def __init__(self, argv, cwd, rows, cols, env=None):
        try:
            from winpty import PtyProcess
        except ImportError:
            raise RuntimeError('the interactive terminal needs pywinpty on Windows - pip install pywinpty')
        self.p = PtyProcess.spawn(argv, cwd=cwd, dimensions=(rows, cols), env=clean_env(env))
    def read(self):
        try: return self.p.read(65536)
        except EOFError: return ''
    def write(self, s): self.p.write(s)
    def resize(self, rows, cols): self.p.setwinsize(rows, cols)
    def alive(self): return self.p.isalive()
    def kill(self):
        try: self.p.terminate(force=True)
        except Exception: pass


class _UnixPty:
    def __init__(self, argv, cwd, rows, cols, env=None):
        import fcntl, pty, struct, termios
        self.fd, slave = pty.openpty()
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        self.p = subprocess.Popen(argv, cwd=cwd, stdin=slave, stdout=slave, stderr=slave,
                                  close_fds=True, start_new_session=True, env=clean_env(env))
        os.close(slave)
        import codecs
        self.dec = codecs.getincrementaldecoder('utf-8')(errors='replace')
    def read(self):
        # decoded INCREMENTALLY: a multibyte glyph split across two reads used to decode as two
        # replacement chars, and a TUI draws in box glyphs all day
        try: return self.dec.decode(os.read(self.fd, 65536))
        except OSError: return ''
    def write(self, s): os.write(self.fd, s.encode())
    def resize(self, rows, cols):
        import fcntl, struct, termios
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
    def alive(self): return self.p.poll() is None
    def kill(self):
        try: self.p.kill()
        except Exception: pass


class Term:
    """One live pty session. The reader thread fans output out to every attached socket
    and keeps a scrollback so reopening the tab shows the session as it stands."""

    def __init__(self, argv, cwd, label, task_id=None, agent=None, rows=32, cols=110, store=None):
        self.sid = uuid.uuid4().hex[:12]
        self.argv, self.cwd, self.label, self.task_id, self.agent = argv, cwd, label, task_id, agent
        self.rows, self.cols = rows, cols                 # replaying the stream needs the real geometry
        self.started = datetime.now().isoformat(sep=' ', timespec='seconds')
        self.started_ts = time.time()                     # the same instant a clock can subtract (selfclose's age gate)
        self.buf, self.n, self.ended, self.last = deque(), 0, None, time.time()
        self.calm_until = 0                               # output until then must not reset idle()
        self.seeded = ''                                  # the prompt we typed: echoed back, not said
        self.store = store                                # so the pty can file its own transcript when it ends
        self.keep_transcript = True                       # off for a session the owner types secrets into (aisetup)
        self.subs = []                                    # (loop, asyncio.Queue)
        self.taps = []                                    # plain callables, for server-side readers
        self.failover = None                              # availability-only replacement installed by start_on_task
        self._live_at = 0                                 # last run-tail emit; pty bursts fold into one
        # One published lifecycle state for every consumer (Timeline, Board, Studio, hand raise,
        # waiting room). A full-screen TUI redraws in pieces; sampling one piece used to publish
        # parked for a frame, then working again on the next. The raw observation may move that
        # quickly, but the state people see must hold before it changes.
        self._phase_stable, self._phase_candidate, self._phase_since = 'working', None, time.time()
        self._phase_screen = (0.0, [])                    # rendered-screen cache; one render per request burst
        # what was already unclean in the checkout is NOT this session's doing - the snapshot is
        # what lets files() attribute later dirt to this agent (see blackboard.py)
        from . import blackboard as _bb, witness as _w
        self.dirty0 = _bb.dirty(cwd) if task_id else set()
        self._files = ([], 0.0)
        self.witness, self.ext_id = _w.Witness(), ''     # what the agent said and did (hooks / rollout), and the CLI's own session id once a hook names it
        # the browser this session may open is named after it, so the pane can find it (browserview)
        from . import browserview as _bv
        # the pane's browser name, and who this session IS - so `taskuary --note` inside it needs
        # no arguments to know which agent, task and checkout it is speaking for
        self.pty = (_WinPty if os.name == 'nt' else _UnixPty)(
            argv, cwd, rows, cols, {**_bv.env(self.sid), **session_env(agent or label, task_id, cwd)})
        self.alive = True
        # started LAST, and store comes in through the constructor: a CLI that dies immediately
        # used to reach keep() before the caller had handed the session anywhere to file itself
        threading.Thread(target=self._pump, daemon=True).start()

    def _append(self, s):
        self.buf.append(s); self.n += len(s)
        while self.n > SCROLLBACK and len(self.buf) > 1: self.n -= len(self.buf.popleft())

    def _emit(self, data):
        for loop, q in list(self.subs):
            try: loop.call_soon_threadsafe(q.put_nowait, data)
            except RuntimeError: pass                     # socket's loop is gone; unsubscribe follows
    def _pump(self):
        while True:
            try: data = self.pty.read()
            except Exception as e: logger.debug(f'terminal {self.sid} read ended: {e}'); break
            if not data: break
            self._saw_output()
            self._append(data); self._emit(data)
            if self.task_id:
                now = time.time()
                if now - self._live_at >= 0.2:
                    self._live_at = now
                    try:
                        from . import live as live_bus
                        live_bus.emit('run-tail', task_id=self.task_id)
                    except Exception:
                        pass
            for f in list(self.taps):
                try: f(data)
                except Exception as e: logger.debug(f'terminal tap failed: {e}')
        self.alive, self.ended = False, time.time()       # exited: the tab stays readable for a while
        self.keep()                                       # the transcript must outlive the pty
        self._emit(None)
        from . import browserview as _bv
        _bv.close(self.sid)                               # its browser goes with it, not into an hour of idling
        # A plan/session limit is known only after an interactive CLI paints the refusal and
        # exits. start_on_task installs the replacement callback; ordinary agent/task errors
        # never take this road, because changing authors after work began would be unsafe.
        if self.failover and time.time() - self.started_ts < 180:
            from .agents import availability_failure
            reason = plain(self.scrollback())[-5000:]
            if availability_failure(RuntimeError(reason)):
                def replace():
                    try: self.failover(self, reason)
                    except Exception as e: logger.warning(f'agent fallback for {self.sid} failed: {e}')
                threading.Thread(target=replace, daemon=True).start()
        if self.store and self.task_id:                   # whoever queued behind this session gets its turn
            from . import blackboard, waitroom
            # A CLI can exit itself (quit, crash, rate-limit) without traveling through the HTTP
            # close button. It no longer owns the task at that point: release stale running rows
            # and put unfinished work back in the owner's pipe immediately.
            release_task(self.store, self.task_id)
            blackboard.drain_later(self.store)
            waitroom.later(self.store)                    # ...and notes left for THIS agent reopen it

    def keep(self):
        """File this session's readable transcript on its task. A pty is not storage: sessions are
        reaped, and once the last one was gone the task could no longer be wrapped up at all - the
        buttons had nothing to read and quietly disappeared. Written on exit AND on close, because
        either can come first."""
        if not (self.store and self.task_id and self.keep_transcript): return
        try: self.store.add_transcript(self.task_id, self.sid, harvest(self), self.agent, self.cwd)
        except Exception as e: logger.warning(f'could not file the transcript for {self.sid}: {e}')

    def settle(self, cap: float) -> bool:
        """Wait until the TUI stops painting - that gap IS 'ready'. A fixed delay either typed
        into the middle of a redraw (swallowed) or waited seconds longer than it needed."""
        start, quiet, last = time.time(), 0, self.n
        while self.alive and quiet < SEED_QUIET and time.time() - start < cap:
            time.sleep(.1)
            quiet, last = (quiet + .1, last) if self.n == last else (0, self.n)
        return self.alive

    def _sees(self, fragment: str) -> bool:
        """Did this piece of typed text land? Checked on the RENDERED screen first (where
        Claude Code's '[Pasted text #N]' chips stand in for the words), then in the RAW
        stream: a boot spinner that repaints with erase-line wipes the echo off the screen
        the instant it lands, and judging by the screen alone called a landed toe 'eaten',
        retyped it, and stalled the whole seed (the macOS CI flake). An echo in the raw
        bytes is proof enough - eaten input never echoes anywhere. All comparisons strip
        whitespace, because wrapping breaks phrases across lines."""
        want = ''.join(fragment.split())
        scr = ''.join(render(self.scrollback(), self.cols, self.rows).split())
        if '[Pastedtext' in scr or want in scr: return True
        return want in ''.join(self.scrollback().split())

    def _echoed(self) -> bool:
        """Did the WHOLE prompt land? Only the tail is checkable - a long seed scrolls the input
        box, so the head may legitimately be off-screen (checking the head here once read a
        fully-typed prompt as 'eaten' and retyped it on top of itself, three glued copies and no
        Enter). Tail-presence alone is safe ONLY because seed() proves the box is listening with
        a short toe BEFORE the payload goes in - without that proof, a booting TUI that ate the
        front of the prompt still shows the tail, and a beheaded ask gets submitted (it did)."""
        return len(self.seeded) > 10 and self._sees(self.seeded[-40:])

    def seed(self, text: str):
        """Type the first prompt in AND SEND IT. The owner asked for the work when they clicked
        the button, so leaving a filled-in box for them to come back and press Enter on is not
        starting - it is a session that looks busy and has done nothing.

        Everything here is verified, not assumed, in TWO steps. First a 20-char TOE: a booting
        TUI eats the earliest bytes (a trust dialog, an input box not yet listening) - and when
        it eats only the FRONT, the tail still lands, so typing everything at once submitted a
        beheaded prompt whose problem statement was gone. Not-echoed toe = a dialog is up (the
        owner answers those, never us) - wait for the screen to move, try the toe again. Echoed
        toe = the box is live and listening, so the payload after it cannot be eaten. Then press
        Enter until the session answers, because a CR arriving mid-redraw reads as part of the
        same edit and some TUIs submit on \\n not \\r."""
        def go():
            start = time.time()
            while self.alive and not self.n and time.time() - start < SEED_WAIT: time.sleep(.1)
            if not self.settle(3): return                 # a breath after first output - the toe probes the rest
            self.seeded = fit_typed(text)
            toe, rest = self.seeded[:20], self.seeded[20:]
            for attempt in range(SEED_RETRIES):
                self.write(toe)                           # attempt > 0 = retyped: the first toe was eaten
                end = time.time() + 12                    # generous: a loaded CI runner echoes LATE, and a
                while self.alive and not self._sees(toe) and time.time() < end:
                    time.sleep(.25)                       # fast poll, no quiet-wait - spinners are never quiet
                if not self.alive: return
                if not self._sees(toe):
                    # a dialog is up, or the echo is still coming: hold until the screen moves,
                    # and judge AGAIN before retyping - calling a late echo 'eaten' stalled the
                    # whole seed on slow macOS runners (dialog-wait outlived the test's patience)
                    was = self.n
                    while self.alive and self.n == was and time.time() - start < SEED_BUDGET:
                        time.sleep(.5)
                    if self._sees(toe):
                        pass                              # late echo: it landed - go type the payload
                    elif time.time() - start >= SEED_BUDGET:
                        logger.warning(f'terminal {self.sid}: the CLI is waiting on a prompt of its own '
                                       f'(trust/login?) - answer it and the seeded ask will need retyping')
                        return
                    else:
                        if not self.settle(SEED_SETTLE): return
                        continue
                # proven listening - and fed in frame-sized bites so nothing drops mid-stream
                for i in range(0, len(rest), SEED_CHUNK):
                    self.write(rest[i:i + SEED_CHUNK])
                    time.sleep(SEED_CHUNK_GAP)
                time.sleep(.5)                            # let the box finish laying the paste out
                if not self.alive: return
                # The toe proved the box was LISTENING. Nothing proved the PAYLOAD arrived - and
                # _echoed(), written for exactly this question, was never called. A TUI that
                # drops a bite mid-paste leaves a SPLICE, and a splice submits happily: TQ-0038's
                # "Fix employee id's" ran straight into the flattened CODER.md behind it and the
                # agent spent ten minutes working "fix emd for every coder run" - a sentence
                # nobody wrote, in a repo the eaten REPO: line never named. A prompt that did not
                # go in is recoverable; a garbled one that did is not.
                end = time.time() + 8
                while self.alive and not self._echoed() and time.time() < end: time.sleep(.25)
                if self.alive and not self._echoed():
                    # SAY HOW incomplete. 'landed incomplete' with no numbers is unactionable in
                    # production and unfixable from a CI log: macOS runners have failed here for
                    # a while and the line never said whether the tail was missing by forty
                    # characters or by four hundred, nor how much the child echoed back.
                    raw = ''.join(self.scrollback().split())
                    logger.warning(f'terminal {self.sid}: the prompt landed incomplete - clearing and retyping '
                                   f'(typed {len(self.seeded)} chars, {len(raw)} echoed back, '
                                   f'looking for {self.seeded[-40:]!r})')
                    self.write('\x15')                    # kill-line: a retype must not glue onto the wreckage
                    time.sleep(.4)
                    if not self.settle(SEED_SETTLE): return
                    continue
                for key in ('\r', '\r', '\n'):
                    was = self.n
                    self.write(key)
                    time.sleep(SEED_ENTER)
                    if self.n > was: return               # it answered: the prompt went in
                    if not self.settle(SEED_SETTLE): return
                return                                    # echoed but never submitted: stop typing
            logger.warning(f'terminal {self.sid}: prompt typed but nothing came back - press Enter')
        threading.Thread(target=go, daemon=True).start()

    def tap(self, fn): self.taps.append(fn)
    def untap(self, fn): self.taps = [f for f in self.taps if f is not fn]

    def subscribe(self, loop, q): self.subs.append((loop, q))
    def unsubscribe(self, q): self.subs = [(l, x) for l, x in self.subs if x is not q]
    def scrollback(self): return ''.join(self.buf)
    def write(self, s):
        if self.alive: self.pty.write(s)
    def _saw_output(self):
        """Silence is the signal (see idle()) - but not ALL output breaks it. The reattach
        wiggle forces a full REPAINT, which is output that says nothing about the agent:
        counting it reset idle(), so a session parked at its prompt flipped back to 'Agent
        working' on every tab switch and the board flapped between lanes."""
        if time.time() > self.calm_until: self.last = time.time()

    def quiet_for(self, secs: float):
        """The next `secs` of output are OURS - a repaint we asked for - and must not count as the
        agent working. Opening the card in the chat produced exactly that, idle() reset, and a coder
        sitting on a trust dialog flipped to "the agent is working again" (2026-09-03)."""
        self.calm_until = max(self.calm_until, time.time() + float(secs))

    def resize(self, rows, cols):
        if self.alive:
            try:
                self.pty.resize(int(rows), int(cols))
                self.rows, self.cols = int(rows), int(cols)
                self.quiet_for(3)                         # the repaint this triggers is not activity
            except Exception: pass
    def close(self):
        self.keep()                                       # before the bytes go, not after
        self.alive, self.ended = False, time.time()
        self.pty.kill()
        self._emit(None)
    def idle(self) -> float:
        """Seconds since this session last printed anything. An agent that has gone quiet is
        not working - it is waiting at its own prompt, which means it is waiting on YOU."""
        return round(time.time() - self.last, 1)

    def tail(self, n=3) -> list:
        """The last few readable lines - a card-sized peephole into what it is doing."""
        lines = [l for l in plain(''.join(self.buf)[-6000:]).splitlines() if l.strip()]
        return lines[-n:]

    def files(self) -> list:
        """What THIS session has modified so far: dirty now minus dirty at open. Cached a few
        seconds - the board polls, and a git status per poll per session adds up."""
        got, at = self._files
        if time.time() - at < 4 or not (self.task_id and self.alive): return got
        from . import blackboard as bb
        try: got = sorted(bb.dirty(self.cwd) - self.dirty0)[:20]
        except Exception: got = []
        self._files = (got, time.time())
        return got

    def status_tail(self, n=8) -> list:
        """The bottom of the screen the owner can actually see, not the raw repaint bytes.

        `tail()` deliberately reads the raw stream for transcript snippets. It is the wrong input
        for lifecycle: Claude's current "esc to interrupt" footer was visible on screen while the
        raw tail contained only fragments such as "Gallivanting…" and reported `unknown`.
        """
        at, lines = self._phase_screen
        now = time.time()
        if now - at >= .5:
            lines = render(self.scrollback(), self.cols, self.rows).splitlines()
            self._phase_screen = (now, lines)
        return lines[-max(1, n):]

    def phase(self) -> str: return stable_phase_of(self)
    def waiting(self) -> bool: return self.phase() == 'parked'

    def info(self, tail=0, details=True):
        # module functions, not methods: the tests' fakes (and any other stand-in) need only tail() and idle()
        # Keep this module-level for the deliberately small terminal stand-ins used by the API
        # and hook tests; production Terms and fakes must go through the same state machine.
        phase = stable_phase_of(self)          # compute once: every field in this payload tells one truth
        base = {'sid': self.sid, 'label': self.label, 'cwd': self.cwd, 'taskId': self.task_id,
                'agent': self.agent, 'cli': cli_of(self.argv), 'alive': self.alive, 'started': self.started,
                'idle': self.idle(), 'phase': phase, 'waiting': phase == 'parked',
                'cmd': ' '.join(self.argv), **({'tail': self.tail(tail)} if tail else {})}
        if not details:
            # Task lists need identity and lifecycle only. files() shells out to git and witness
            # reconciliation walks that result; doing either on every Tasks/Board refresh made a
            # two-session roster hold the entire API behind repository I/O.
            return base
        files, w = self.files(), getattr(self, 'witness', None)      # fakes in tests carry no witness
        from . import browserview as _bv
        return {**base, 'files': files, 'browser': _bv.state(self.sid),
                'work': w.snapshot(files, self.cwd, (self.tail(1) or [''])[-1]) if w else None}


def cli_of(argv) -> str:
    """'claude' for C:\\...\\claude.exe or claude.cmd - the CLI a session runs, whatever the profile is
    called. A profile named codex that runs claude showed 'codex' on the card next to a 'claude' badge."""
    return re.split(r'[\\/]', str((argv or [''])[0]))[-1].lower().rsplit('.', 1)[0] if argv else ''


_LIGHT_INFO = {'sid', 'label', 'cwd', 'taskId', 'agent', 'cli', 'mode', 'alive', 'busy',
               'started', 'idle', 'phase', 'waiting', 'cmd', 'provider', 'pick',
               'connector_id', 'model', 'tail'}

def _info(t, tail=0, details=True) -> dict:
    """Call real sessions' lightweight path while remaining compatible with small adapters.

    Session stand-ins and third-party session types predate the `details` keyword. Rich callers
    keep the old exact call; a lightweight caller filters their old payload only when necessary.
    """
    if details: return t.info(tail)
    try: return t.info(tail, details=False)
    except TypeError as e:
        if "unexpected keyword argument 'details'" not in str(e): raise
        return {k: v for k, v in t.info(tail).items() if k in _LIGHT_INFO}


def default_shell():
    if os.name == 'nt': return ['powershell', '-NoLogo']
    return [os.environ.get('SHELL') or '/bin/bash', '-i']


# Flags that turn a CLI into a one-shot pipe. Everything ELSE in the profile's args belongs
# in an interactive session too - dropping them all took --dangerously-skip-permissions with
# them, so an unattended session stopped at the first approval prompt instead of working.
PIPE_FLAGS = {'-p', '--print'}
PIPE_OPTS = {'--output-format', '--input-format'}
# codex spells its pipe mode as a SUBCOMMAND, not a flag: `codex exec` is one prompt in, one
# result out, and a session launched with it just runs headless and exits. Bare `codex` is
# the TUI, so a leading exec is dropped the same way claude's -p is - and exec-only flags are
# TRANSLATED: `--full-auto` becomes the TUI's own spelling of the same intent - workspace-write
# sandbox, never ask (failures go straight back to the model). Translating it to sandbox-only
# looked safer, but it turned "auto" sessions into approval-click marathons the owner never
# asked for. 'never' and not 'on-failure' because current codex builds dropped on-failure
# (verified against the CLI: possible values are untrusted, on-request, never) - and the truly
# dangerous modes still only ever come from the profile the owner wrote.
PIPE_SUBCOMMANDS = {'exec', 'e'}
PIPE_TRANSLATE = {'--full-auto': ['--sandbox', 'workspace-write', '--ask-for-approval', 'never']}

def interactive_args(args) -> list:
    out, skip = [], False
    piped = bool(args) and args[0] in PIPE_SUBCOMMANDS
    for i, a in enumerate(args or []):
        if skip: skip = False; continue
        if i == 0 and piped: continue
        if piped and a in PIPE_TRANSLATE: out += PIPE_TRANSLATE[a]; continue
        # -p is claude's pipe flag but codex's --profile, which takes a value: only strip it
        # for a command that was not already marked headless some other way
        if a in PIPE_FLAGS and not piped: continue
        if a in PIPE_OPTS: skip = True; continue
        out.append(a)
    return out


def _codex_windows_auto(argv: list) -> list:
    """codex's workspace-write sandbox needs a helper exe most Windows installs lack
    (codex-windows-sandbox-setup.exe) - without it EVERY command dies before running ('the
    Windows sandbox helper executable is missing'), so an auto session can read but never act.
    When the helper is absent, full-auto degrades to codex's own bypass flag: the exact trust
    the claude preset already ships (--dangerously-skip-permissions) - a watched session, no
    sandbox. Only the TRANSLATED quad is touched; flags the owner typed are theirs."""
    AUTO = ['--sandbox', 'workspace-write', '--ask-for-approval', 'never']
    if os.name != 'nt': return argv
    exe = next((a for a in argv if 'codex' in os.path.basename(str(a)).lower()), None)
    if not exe: return argv
    i = next((j for j in range(len(argv) - 3) if argv[j:j + 4] == AUTO), None)
    if i is None: return argv
    if os.path.exists(os.path.join(os.path.dirname(str(exe)), 'codex-windows-sandbox-setup.exe')): return argv
    return argv[:i] + ['--dangerously-bypass-approvals-and-sandbox'] + argv[i + 4:]


def _codex_browser_tui(argv: list) -> list:
    """Keep Codex's composer responsive inside xterm.js.

    Codex's default alternate-screen TUI redraws the whole screen around its composer. Over
    ConPTY -> websocket -> xterm that makes each typed character wait behind repaint work;
    Claude does not exercise that path in the same way. Codex officially exposes both knobs,
    so browser-hosted sessions use inline mode and disable decorative animations without
    changing the owner's global config.toml. An explicit profile value still wins.
    """
    if not any('codex' in os.path.basename(str(a)).lower() for a in argv): return argv
    out = list(argv)
    if '--no-alt-screen' not in out: out.append('--no-alt-screen')
    configured = any(
        (a in ('-c', '--config') and i + 1 < len(out) and str(out[i + 1]).split('=', 1)[0] == 'tui.animations')
        or (str(a).startswith('--config=') and str(a).split('=', 1)[1].split('=', 1)[0] == 'tui.animations')
        for i, a in enumerate(out)
    )
    if not configured: out += ['-c', 'tui.animations=false']
    return out


def agent_argv(profile: dict, model: str = None) -> list:
    """Interactive invocation of a configured CLI: its command, its own flags minus the pipe
    ones, and the model flag the headless runner uses (`model_arg`, e.g. codex wants -m).
    `interactive_args` in the profile replaces the lot, for CLIs that need a subcommand."""
    from .agents import _resolve_cmd
    from .clis import preset_args
    argv = _resolve_cmd(profile.get('cmd') or 'claude')
    argv += list(profile['interactive_args']) if profile.get('interactive_args') else interactive_args(profile.get('args') or preset_args(profile.get('cmd') or 'claude'))
    model = model or profile.get('model')
    argv += [profile.get('model_arg') or '--model', str(model)] if model else []
    return _codex_windows_auto(_codex_browser_tui(argv))


# Claude Code asks two questions the FIRST time it opens a folder: "Do you trust the files in this
# directory?" and "Allow external CLAUDE.md imports?". An agent Taskuary started answers neither -
# it sits on the dialog, the pipe says "waiting on you", and the card shows the theme toolbar
# instead of a question (the 2026-09-03 break test: three auto-started coders parked like that).
# The owner already answered by dispatching the work, and the folder is one Taskuary chose. So the
# answers are written where the CLI reads them, before it starts.
TRUSTED = {'hasTrustDialogAccepted': True, 'hasCompletedProjectOnboarding': True,
           'hasClaudeMdExternalIncludesApproved': True, 'hasClaudeMdExternalIncludesWarningShown': True}

def pretrust(cwd: str, agent: str = '', home: str = None) -> bool:
    """Answer the first-run dialogs for `cwd` in ~/.claude.json. True when something was written.
    Only claude asks these, and only about a directory: nothing else in the file is touched, and a
    file we cannot read or parse is left exactly as it is."""
    if not cwd or 'claude' not in str(agent or 'claude').lower(): return False
    path = os.path.join(home or os.path.expanduser('~'), '.claude.json')
    try:
        cfg = json.loads(open(path, encoding='utf-8').read()) if os.path.exists(path) else {}
        if not isinstance(cfg, dict): return False
    except (OSError, ValueError) as e:
        logger.debug(f'pretrust: {path} could not be read ({e}) - the CLI will ask its own questions')
        return False
    projects = cfg.setdefault('projects', {})
    if not isinstance(projects, dict): return False
    entry = projects.get(cwd) if isinstance(projects.get(cwd), dict) else {}
    if all(entry.get(k) for k in TRUSTED): return False                  # already answered - nothing to write
    projects[cwd] = {**entry, **TRUSTED}
    try:
        tmp = path + '.tq'
        with open(tmp, 'w', encoding='utf-8') as f: json.dump(cfg, f, indent=2)
        os.replace(tmp, path)
    except OSError as e:
        logger.warning(f'pretrust: could not write {path} ({e}) - the CLI may ask about {cwd}')
        return False
    logger.info(f'pretrust: {cwd} is trusted for claude - no first-run dialog for this session')
    return True


def open_session(store, agent: str = None, task_id: int = None, repo: str = None, cwd: str = None,
                 rows: int = 32, cols: int = 110, actor: str = 'owner', model: str = None,
                 seed_fn=None) -> Term:
    """Start a terminal: a configured agent CLI, or a plain shell when agent is None.

    `seed_fn(cwd) -> str` builds the first prompt once the working directory is known. CLIs
    that take a prompt on the command line (claude, codex, gemini) get it THERE - the session
    starts with it already submitted; the rest get it typed in (Term.seed)."""
    import json
    profile = {}
    if agent:
        row = store.get_agent(agent)
        if not row: raise ValueError(f'unknown agent: {agent}')
        profile = json.loads(row.get('Config') or '{}')
        label = agent
    else:
        label = 'shell'
    # A named repo with no path used to fall through to the agent's default folder, so a task about
    # one system opened a session in another and the agent edited the wrong tree in good faith.
    # Refuse instead: not starting is recoverable, working the wrong checkout is not.
    if not cwd and repo:
        paths = profile.get('cwd_map') or {}
        cwd = paths.get(repo)
        if not cwd:
            # before refusing, LOOK - the checkout usually exists, just unconfigured
            found = find_checkout(repo, profile)
            if found:
                cwd = found
                if agent: remember_path(store, agent, repo, found)
                logger.info(f'found {repo} at {found} - remembered on {agent or label}')
        if not cwd and paths:
            raise ValueError(f'no local path for {repo}, and a search of your code folders found no '
                             f'checkout with that git remote. Open the task menu (...) > Pick the '
                             f'repository, choose {repo} and give it the path - otherwise the session '
                             f'would open in {profile.get("cwd") or os.getcwd()} and work the wrong tree')
    # ...and NO repo decided must not mean "the agent's default folder" either. That default is one
    # particular checkout (FanApp, on this box), so a task nothing matched opened there and an agent
    # worked a tree it had no business in - the same failure the refusal above exists to prevent, one
    # branch further along (the owner, 2026-09-03: "sent the coding agent the wrong repo again").
    if not cwd and not repo and task_id and agent:
        paths = profile.get('cwd_map') or {}
        if len(paths) > 1:
            raise ValueError('I could not tell which checkout this belongs in, and guessing would put an '
                             f"agent in {profile.get('cwd') or os.getcwd()}. Open the task menu (...) > Pick "
                             'the repository and say which one - or tag it, and every later session goes there.')
        if len(paths) == 1: cwd = next(iter(paths.values()))
    cwd = cwd or profile.get('cwd') or os.getcwd()
    if not os.path.isdir(cwd): raise ValueError(f'working directory does not exist: {cwd}')
    # WHICH CHECKOUT comes first, and only then which binary: resolving the CLI up here meant a box
    # without it answered "'claude' not found on PATH" to a task whose real problem was that nothing
    # said where it belonged - the wrong sentence, and the one the owner cannot act on.
    argv = agent_argv(profile, model) if agent else default_shell()
    if agent:
        try: pretrust(cwd, ' '.join(str(a) for a in argv))     # no first-run dialog to park on
        except Exception as e: logger.debug(f'pretrust skipped: {e}')
    seed = ' '.join(seed_fn(cwd).split()) if (seed_fn and agent) else None
    extra = seed_argv(profile, seed) if seed else None
    # pywinpty joins argv with list2cmdline - correct for a direct .exe - but an npm .CMD shim
    # runs through `cmd /c`, and cmd.exe parses & | < > and stray quotes as ITS OWN syntax:
    # the seed's `subject "T&E System"` was cut AT THE AMPERSAND and half a prompt was
    # delivered as if it were whole. Shims take the verified typed road instead.
    if extra and any(str(a).lower().endswith(('.cmd', '.bat')) or
                     os.path.basename(str(a)).lower() in ('cmd', 'cmd.exe') for a in argv):
        extra = None
    if extra: argv = list(argv) + extra
    # the agent tells the Board what it is doing: Claude through its own hooks in this checkout
    # (hooks.py), Codex through the rollout it writes as it works (witness.RolloutTail)
    if agent and task_id:
        from . import hooks as _hooks
        try:
            # with the agent token: once [server].token is set the gate refuses a bare hook POST, and
            # the Board went dark the moment the owner did the recommended thing (audit 2026-09-02)
            if _hooks.wanted(store, profile): _hooks.install(cwd, token=session_env(agent, task_id, cwd).get('TASKUARY_TOKEN', ''))
        except Exception as e: logger.debug(f'claude hooks not installed in {cwd}: {e}')
    t = Term(argv, cwd, label, task_id, agent, rows, cols, store)
    SESSIONS[t.sid] = t
    # The configured profile name is the worker's identity, not just a launch option. Keep it on
    # the task after this terminal closes so an inbound auto-start and an owner-started session
    # both have a named owner, and the next session can return to the same worker deliberately.
    if agent and task_id:
        task = store.get_task(task_id) or {}
        assigned = f'agent:{agent}'
        if task.get('Assignee') != assigned: store.update_task(task_id, {'Assignee': assigned}, actor)
    # A task the owner marked "needs a browser" gets one WITH its session - bound to it by name,
    # restored from the owner's own saved cookies, closed with it (Term._pump). Until now a
    # browser existed only if the agent thought to run agent-browser, so a task that plainly
    # needs one started with nothing on screen. On its own thread: Chrome takes a few seconds
    # and the session must not wait for it.
    if task_id and store:
        from . import browserview as _bv
        if _bv.wanted(store.get_task(task_id)):
            threading.Thread(target=_bv.start, args=(t.sid,), daemon=True).start()
    if agent and task_id and 'codex' in os.path.basename(str(argv[0])).lower():
        from .witness import RolloutTail
        RolloutTail(t).start()
    if seed:
        if extra: t.seeded = seed        # the CLI submits it itself; kept so harvest drops the echo
        else: t.seed(seed)               # no prompt argument on this CLI: type it in, verified
    # A reply drafted from the mail alone promises what this session has not worked out yet, so
    # it stops waiting in Review and comes back rewritten from the report - see coder.raise_reply.
    if task_id and store.hold_reviews(task_id, 'held while an agent works the task - the reply is written from what it finds'):
        logger.debug(f'held the pending reply on task {task_id} while {agent or "a session"} works it')
    store.audit('terminal', 0, 'open', actor, detail={'sid': t.sid, 'agent': agent, 'cwd': cwd, 'task': task_id})
    return t


# A replayed scrollback must not ASK QUESTIONS. The raw stream contains the TUI's terminal
# queries (device attributes ESC[c, cursor position ESC[6n, color probes) - replaying them
# on reattach made xterm ANSWER each one again, and the answers arrived at the CLI as
# keystrokes: '[?1;2c' typed into codex's input box, stray cursor reports nudging its view.
# Scrubbed from the REPLAY only; the live stream keeps them so real queries get real answers.
_TERM_QUERIES = re.compile(
    r'\x1b\[[0>=]?c'                                 # DA1/DA2/DA3 - who are you?
    r'|\x1b\[[56]n'                                  # DSR status / CPR - where is the cursor?
    r'|\x1b\[\?\d+\$p'                               # DECRQM - is mode N on?
    r'|\x1b\]1[01];\?(?:\x07|\x1b\\)'                # OSC 10/11 - what are your colors?
    r'|\x1b\[\?u'                                    # kitty keyboard protocol probe
    r'|\x1bP\+q[0-9A-Fa-f;]*(?:\x07|\x1b\\)')        # XTGETTCAP

def scrub_queries(s: str) -> str:
    return _TERM_QUERIES.sub('', s or '')


# ── wrapping up: "we're done" -> the transcript IS the report ───────────────────────
_ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-B]|\x1b[=>]'
                   r'|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')
_FORWARD = re.compile(r'\x1b\[(\d*)C')          # cursor-forward: a GAP, not nothing
_ERASE = re.compile(r'\x1b\[0?K')             # erase-to-end: the old paint is GONE


def _overlay(line: str) -> str:
    """A bare carriage return rewrites the line in place - that is how a TUI animates. Splitting
    on it (what we used to do) turned one spinner into a hundred lines of debris; joining the
    segments blind glued words together. Paint them over each other, like the terminal does."""
    out = ''
    for seg in line.split('\r'):
        out = seg + out[len(seg):] if len(seg) < len(out) else seg
    return out


def plain(s: str) -> str:
    """A TUI's bytes as readable text: repaints resolved, escape sequences gone, box gutters
    trimmed. Cursor-forward becomes spaces - deleting it is what ran "112 active" together
    into "112active" in the first wrap-ups.

    Kept as the FALLBACK for `render` (and for streams with no positioning in them). It cannot
    be made correct: see render() for why."""
    s = (s or '').replace('\r\n', '\n')
    s = _FORWARD.sub(lambda m: ' ' * max(1, int(m.group(1) or 1)), s)
    lines = [_overlay(l) for l in s.split('\n')]
    return '\n'.join(_ANSI.sub('', l).strip(' │┃┊▎|').rstrip() for l in lines)


HISTORY_LINES = 6000        # scrollback pyte keeps while replaying a session

def render(raw: str, cols: int = 110, rows: int = 32) -> str:
    """The pty stream as a terminal would SHOW it, which is the only faithful way to read one.

    Hand-rolling this was the mistake. Claude Code lays its output out with ABSOLUTE moves -
    ESC[54G to a column, ESC[1B down a line - and a regex that deletes those instead of obeying
    them glues every word together ("Run/inittocreateaCLAUDE.mdfile") and collapses a whole
    session into a couple of hundred characters of debris. That is exactly what the wrap-up was
    handing the AI, which is why reports came back saying the transcript was unreadable: it was.

    pyte is a real VT emulator, pure Python, so the one-file exe is unaffected. Its history is
    the scrollback. Anything it cannot parse falls back to plain() rather than losing the run."""
    if not (raw or '').strip(): return ''
    try:
        import pyte
    except ImportError:
        logger.warning('pyte is not installed - transcripts will be rendered with the fallback')
        return plain(raw)
    try:
        sc = pyte.HistoryScreen(max(40, int(cols or 110)), max(4, int(rows or 32)),
                                history=HISTORY_LINES, ratio=1.0)
        pyte.Stream(sc).feed(raw)
        # history rows are sparse Char maps; display rows are already strings
        def line(r):
            return r.rstrip() if isinstance(r, str) else ''.join(r[x].data for x in range(sc.columns)).rstrip()
        return '\n'.join(line(r) for r in list(sc.history.top) + list(sc.display))
    except Exception as e:
        logger.warning(f'terminal render failed ({e}) - falling back to plain()')
        return plain(raw)


REPLAY_LINES = 400          # what a reopened pane is seeded with, in lines
ESC = chr(27)
# leave the alternate screen, home the cursor, clear: a known state to seed into
REPLAY_RESET = f'{ESC}[?1049l{ESC}[H{ESC}[2J'
CRLF = chr(13) + chr(10)

def replay_text(t, lines: int = REPLAY_LINES) -> str:
    """What a reopened pane is seeded with: the session as a terminal WOULD SHOW it, never the
    bytes that got it there.

    A full-screen TUI paints with ABSOLUTE cursor moves, so replaying its raw scrollback into a
    fresh xterm - which starts at row one with none of that history - smears it into the debris
    the owner photographed on 2026-09-02, and the live repaint then lands ON TOP of the debris
    instead of replacing it, which is the scrolling. pyte already resolves those moves for the
    wrap-up (render); the same render is the honest seed here, and it costs the replay its colour
    to buy a pane that is legible every single time.

    The reset prefix leaves the alternate screen and clears, so the pane starts from a known
    state whatever the old bytes left behind - and a terminal QUERY cannot survive a render, so
    the replay can no longer make xterm answer one into the CLI as typed junk."""
    text = render(t.scrollback(), getattr(t, 'cols', 110), getattr(t, 'rows', 32))
    tail = text.splitlines()[-max(1, lines):]
    while tail and not tail[0].strip(): tail.pop(0)
    return (REPLAY_RESET + CRLF.join(tail)) if tail else ''


# What a TUI paints over and over and none of it is what the agent SAID: spinner frames, the
# hint bar, the token counter, rules, the statusline tip. It all landed in the wrap-up - and in
# the transcript we hand the AI to write from.
_CHROME = re.compile(r'esc to interrupt|\? for shortcuts|for agents|to manage|\bTip:\s|^\s*\d[\d,]*\s+tokens?\b|\(\d+s\)\s*$|\b\d[\d,]*\s+tokens\)\s*$|still r?unning\s*$', re.I)
_WORDLESS = re.compile(r'^[^A-Za-z]*$')
_HINT = re.compile(r'\bTip:\s+Use /')      # a slash-command hint, any length
_SPIN = re.compile('[·✢✳✻✽✶✷✸✹✺⏺◐◓◑◒✦❯›]')       # the frames themselves
# a spinner frame painted over a longer line leaves the OLD line's tail fused on (the macOS CI
# runner is slow enough to catch one mid-animation): any line that OPENS as spinner chrome is
# debris however long the residue makes it - the real text repeats on its own lines
_SPINLINE = re.compile(r'^\s*[✢✳✻✽✶✷✸✹✺◐◓◑◒✦]\s.{0,80}\besc to interrupt\b', re.I)
# A row of a drawn BOX - the welcome banner, the input frame - once a real emulator renders the
# layout instead of deleting it. Only when the inside is mostly padding: a boxed line of actual
# prose is content, a line of gutters and gaps is furniture.
_FRAMED = re.compile(r'^[\s]*[│┃](?P<in>.*)[│┃][\s]*$')

def _is_frame_row(l: str) -> bool:
    mt = _FRAMED.match(l)
    if not mt: return False
    inner = mt.group('in')
    return bool(re.search(r'\s{6,}', inner)) or inner.count(' ') > len(inner) * .4


# The gutter a TUI paints down the left of its own output. render() keeps it, because a terminal
# really does show it; the report reads better without it.
_GUTTER_L = re.compile(r'^\s*[│┃┊▎|]\s?')
_GUTTER_R = re.compile(r'\s*[│┃┊▎|]\s*$')

def degutter(text: str) -> str:
    return '\n'.join(_GUTTER_R.sub('', _GUTTER_L.sub('', l)).rstrip() for l in (text or '').splitlines())


def declutter(text: str) -> str:
    """Keep the lines that carry words. Chrome only matches short lines, so a sentence that
    happens to say "esc to interrupt" survives."""
    out = []
    for l in (text or '').splitlines():
        l = l.rstrip()
        if _is_frame_row(l): continue                     # the banner and the input frame
        l = _GUTTER_R.sub('', _GUTTER_L.sub('', l)).rstrip()   # see degutter
        if not l.strip():
            if out and out[-1]: out.append('')            # keep paragraph breaks, never runs
            continue
        if _WORDLESS.match(l): continue                   # glyphs, rules, box art
        if _HINT.search(l) or (len(l) < 90 and _CHROME.search(l)): continue
        if _SPINLINE.match(l): continue                   # spinner frame fused with repaint residue
        # a frame painted mid-line leaves fused debris ('✻an8', 'e69'): short, and barely letters
        if len(l) <= 12 and (_SPIN.search(l) or sum(c.isalpha() for c in l) <= 3): continue
        if out and out[-1] == l: continue                 # repaints of the same line
        out.append(l)
    return '\n'.join(out).strip()


def letters(s: str) -> int:
    """How much of this is words - the measure of whether there is anything to report FROM."""
    return sum(1 for c in (s or '') if c.isalpha())


_GUTTER = ' \t│┃┊▎|╭╮╰╯─━>❯›'

def _drop_echo(text: str, seed: str) -> str:
    """A pty ECHOES what was typed into it, so the seeded prompt - the ask, the mail, all of
    CODER.md - comes back as if the agent had said it. It is the one thing in the transcript we
    know the agent did not write, and the AI writing the report should not read it twice.

    Matched by CONTAINMENT, not by a fixed head: a real terminal wraps an 8000-character prompt
    across dozens of lines inside a box, so no single line ever started with the same 60 chars."""
    s = ' '.join((seed or '').split())
    if len(s) < 40: return text
    out = []
    for l in text.splitlines():
        n = ' '.join(l.strip(_GUTTER).split())
        if len(n) > 24 and n in s: continue     # this line is literally a slice of what we typed
        out.append(l)
    return '\n'.join(out)


def harvest(t: Term, chars: int = 12000) -> str:
    """What the session actually said, as readable text. Closing a task asks the agent nothing:
    everything needed is already on screen.

    Two lessons are baked in here. The tail used to be taken off the RAW stream, which in a busy
    TUI is almost all escape codes - so render the whole scrollback FIRST and keep the tail of the
    readable text. And the rendering has to be a real terminal (see render): a regex that strips
    absolute cursor moves instead of obeying them turned a 27-minute session into 216 characters
    of glued-together debris, which is what the AI was being asked to write a report from."""
    raw = _drop_echo(render(t.scrollback(), getattr(t, 'cols', 110), getattr(t, 'rows', 32)),
                     getattr(t, 'seeded', '')).strip()
    tidy = declutter(raw)
    # noise an AI can discount; emptiness it cannot. If decluttering took the words out with the
    # chrome, hand over the rendered text instead of nothing - minus the gutter either way.
    return (tidy if letters(tidy) >= 160 else degutter(raw).strip())[-chars:]


def rules_text(store, chars: int = DOC_CHARS) -> str:
    """CODER.md, flattened. The doc says it is 'stacked on top of SOUL.md for every coder run'
    - it never was: these docs live in Taskuary's own database, nowhere the agent can read, so
    the rules only reach a session if the prompt carries them."""
    doc = str(store.doc('coder') or '')
    keep = [l.strip(' #*-').strip() if l.lstrip().startswith('#') else l.strip()
            for l in doc.splitlines() if l.strip()]
    return ' '.join(' '.join(keep).split())[:chars]


# The ask travels as ONE command-line argument now (see agents._shim_target), so the old
# 3000-char squeeze on the message body has no delivery reason left - and it was never
# harmless: a 12,000-character mail reached the agent as its first quarter, unmarked, under an
# instruction that says "work it from THIS message alone". It read a fragment and believed it
# had the whole thing. Windows takes 32767 characters of command line; ASK_CHARS spends a
# useful slice of that on the thing the task is actually about.
ASK_CHARS = 12000
SEED_CEILING = 24000        # the whole prompt, leaving room for the exe path and its flags


# What a canonical-mode tty holds on ONE LINE before it discards the rest - without an error,
# without a signal, without anything. MAX_CANON is 4096 on Linux but 1024 on macOS/BSD, and a TUI
# that has not yet switched the terminal to raw mode is still canonical, so the limit is real for
# exactly the moment we type the first prompt into one. Over it the TAIL is what is lost - and the
# tail is what _echoed() looks for, so seed() reads a fully-typed prompt as eaten and retypes it
# until it gives up, leaving a full input box and no Enter. Typed seeds stay under the SMALLEST
# limit, because we do not know whose tty this is. (SEED_ARGV CLIs never come through here: their
# prompt goes on the command line, where the budget is SEED_CEILING.)
TTY_CANON = 1000


def fit_typed(text: str, ceiling: int = TTY_CANON) -> str:
    """A seed trimmed to what a tty will actually take. The MESSAGE gives, never the rules that
    keep an agent inside its checkout - the same order seed_text uses against SEED_CEILING - and
    it gives out loud, because an agent cannot ask for the rest of something it was not told was
    cut."""
    out = ' '.join((text or '').split())
    if len(out) <= ceiling: return out
    over = len(out) - ceiling
    head, sep, tail = out.partition('FROM ')
    if sep and len(tail) > over + 300:
        return head + sep + _cut(tail, len(tail) - over - 160, 'message')
    return _cut(out, max(40, ceiling - 160), 'prompt')


def _cut(text: str, n: int, what: str = 'message') -> str:
    """Truncate, and SAY SO. Silence here is the expensive kind: an agent cannot ask for the
    rest of something it does not know was cut."""
    text = text or ''
    if len(text) <= n: return text
    return (text[:n] + f' …[{what} truncated here: {n:,} of {len(text):,} characters. '
            'Ask the owner for the rest before assuming anything past this point.]')


# An agent working a repository has no use for anybody's email address, and every prompt is
# a copy handed to a third-party CLI, written into its transcript and its own logs. So the
# addresses come out of everything we inject: SOUL.md carries the owner's, the coder rules and
# handover notes quote correspondents, and none of it changes a line of code. The NAME stays -
# a "sign as <the owner's name>" instruction still means something without the mailbox next to it.
_EMAIL = re.compile(r'\b[\w.+-]+@[\w-]+\.[\w.-]+')


def no_emails(text: str) -> str:
    return _EMAIL.sub('[email removed]', text or '')


def seed_text(store, tid: int, instruction: str = None, repo: str = None, cwd: str = None) -> str:
    """What gets typed into a fresh session, and the ONLY context it should need: the ask, the
    mail behind it, which checkout to work in, and the coder rules. One line - a newline
    submits in a TUI.

    It says so explicitly, because an agent that goes back to Taskuary for the message spends
    a minute of tool calls re-fetching what it was already handed."""
    from .store import task_ref
    t = store.get_task(tid) or {}
    msgs = [m for m in store.list_messages(tid) if m.get('Status') != 'context']
    m = msgs[-1] if msgs else None
    parts = [f"TASK {task_ref(tid)} - {t.get('Title') or ''}."]
    # A general question is told so out loud. Without this the folder the CLI happens to have
    # started in was announced as "REPO: ... work only here", and an agent asked to prepare for a
    # meeting went reading that codebase for the answer.
    if repo_tag(t) == NO_REPO:
        parts.append('NO REPOSITORY - this is a general question, not a change to a codebase. '
                     'Answer it from what you are given and what you can look up; do not go '
                     'hunting for code to edit.')
    elif repo or cwd: parts.append(f"REPO: {repo or cwd} - you are already in it; work only here.")
    # the blackboard: agents sharing THIS checkout, told to a newcomer once, up front. Another
    # repo's agents are deliberately absent - awareness costs prompt tokens, so it is spent
    # only where a collision is physically possible.
    from . import browserview as _bv
    if _bv.wanted(t) and shutil.which('agent-browser'): parts.append(_bv.brief())
    from . import blackboard as bb
    aware = bb.briefing(store, cwd, exclude_tid=tid) if cwd else ''
    if aware: parts.append(aware)
    # ...and what those agents SAID, which is the half no amount of reading git can reconstruct.
    # It rides even when nobody else is running: the last session's "ready to push, tests green"
    # is exactly what the next one needs, and by then that session is gone.
    if cwd:
        said = bb.wall_text(store, cwd)
        if said: parts.append(said)
    if instruction and instruction.strip(): parts.append(f'ASK: {instruction.strip()}')
    # A finished session can be continued with a new ask. Its PTY is gone, but its result is
    # durable task context: hand that result to the next terminal so "now make the changes" does
    # not send the same coder back through the investigation it just completed.
    previous = next((str(c.get('Body') or '')[len('CODER REPORT'):].strip()
                     for c in reversed(store.list_comments(tid))
                     if str(c.get('Body') or '').startswith('CODER REPORT')), '')
    if previous:
        parts.append('PREVIOUS SESSION RESULT: continue from this saved result; verify the current checkout '
                     f'before changing it and do not repeat finished work: {no_emails(_cut(previous, 3000, "previous result"))}')
    from .triage import strip_boilerplate
    if m: parts.append(f"FROM {m.get('FromName') or m.get('FromEmail')} on {m.get('Channel')}, "
                       f"subject \"{m.get('Subject') or ''}\": "
                       f"{_cut(strip_boilerplate(m.get('BodyText') or ''), ASK_CHARS)}")
    elif t.get('Summary'): parts.append(f"ASK: {_cut(strip_boilerplate(str(t['Summary'])), ASK_CHARS)}")
    # the source's standing instruction: a PR is judged before it is worked, a Jira item may
    # have its own house rules - configured per connector card, defaulted for GitHub
    from .ingest import source_rules
    sr = source_rules(store, m) if m else ''
    if sr: parts.append(f'RULES FOR THIS SOURCE: {sr}')
    # the screenshot is often the whole ask ("see below"), and the file paths are local - the
    # session can open them itself instead of being told an image existed
    atts = [a for msg in msgs for a in store.list_attachments(msg['MessageId']) if a.get('Path')]
    if atts: parts.append('FILES that came with it, already on this machine - open them: '
                          + '; '.join(f"{a['Name']} ({a['Path']})" for a in atts[:8]))
    # a paused session left a handover note: carry it in, or the next agent redoes the digging
    from .coder import PAUSE_MARKER
    note = next((c['Body'] for c in reversed(store.list_comments(tid))
                 if str(c.get('Body') or '').startswith(PAUSE_MARKER)), None)
    if note: parts.append('HANDOVER: an earlier session on this task was paused and left this - '
                          f'continue from it, do not start over: {no_emails(_cut(note, 3000, "handover note"))}')
    # SOUL.md rides in WITH the coder rules, because the coder rules refer to it: CODER.md says
    # "work only in the repository the task names (see the repository map in SOUL.md)" and
    # claims it is "stacked on top of SOUL.md for every coder run" - and for a live session it
    # never was. A coder found this itself, went looking for SOUL.md on disk, found three
    # unrelated copies in Downloads and concluded it had been told to consult a document it is
    # structurally incapable of seeing. It was right. These docs live in Taskuary's database;
    # if the prompt does not carry them, nothing does.
    # what is CERTIFIED about the company's own systems - a coder asked a finance question on a
    # general task would otherwise write its own ERP query and be plausibly wrong
    from . import semantic
    layer = ' '.join(semantic.block(store).split())
    if layer: parts.append(layer)
    soul = ' '.join(str(store.doc('soul') or '').split())[:SOUL_CHARS]
    if soul: parts.append(f'OPERATOR RULES (SOUL.md - authoritative): {no_emails(soul)}')
    rules = rules_text(store)
    if rules: parts.append(f'RULES: {no_emails(rules)}')
    # the playbook for THIS kind of job (playbooks.py): triage tagged the task with it, and it is the
    # operative rule set here - CODER.md's "work only in the repository" is the wrong first rule for a
    # bill, so the playbook says so out loud; the closing-out and wall rules still stand
    from . import playbooks as _pbk
    pbk = _pbk.seed_block(t)
    if pbk: parts.append(no_emails(pbk))
    # ...and the owner's own standing notes about THIS thread. agents.memory_block has built
    # this block since it was written and nothing ever called it, so every verdict the owner
    # gave - who to defer to, what is not ours, what never gets touched - reached the triage
    # brain and the reply writer, and never the agent that does the work.
    from .agents import memory_block
    mem = memory_block(store, msgs)
    if mem: parts.append(no_emails(' '.join(mem.split())[:DOC_CHARS]))
    # Everything else the hub knows goes in a FILE, not the command line: the sender's history,
    # the topic elsewhere, the calendar, the learned profile, the whole thread - and PAST WORK, the
    # reports of closed tasks on this sender/subject/repo, which no agent ever saw before. Under
    # Taskuary's own home, never in the checkout (a stray file there gets staged - 8abb175).
    from . import context as ctx
    cpath = ctx.write(store, tid, msgs, repo)
    # short on purpose: this line rides on the command line with a full path in it, and a canonical
    # tty caps a line at 1024 bytes (CI's fake TUI; macOS temp paths are long) - a wordy sentence here
    # pushed the seed over and the prompt arrived clipped
    if cpath: parts.append(f'CONTEXT FILE: {cpath} - read it FIRST: this sender, this topic, past tasks and how they ended.')
    # a browser the owner can WATCH exists only if the agent is told so - and told who types passwords
    from . import browserview as _bv
    if _bv.hint(): parts.append(_bv.hint())
    # The job, spelled out. An agent handed a bare task description went looking for the ticket
    # it came from - Taskuary's own API, its database, the mailbox - and spent its first minute
    # re-fetching what is already in this paragraph.
    issues_ok, push_ok = store.github_permissions()
    parts.append('WHAT TO DO: work it from THIS message alone - diagnose, fix it if it is fixable, else say plainly '
                 'what the problem is and what it would take. Do NOT call the Taskuary API, read its database or '
                 'hunt for this task elsewhere - everything known about it is above' + (' and in the context file. ' if cpath else '. ')
                 + ('GitHub is the issue tracker here: open and update issues for the work as the team expects. '
                    if issues_ok else
                    'Do NOT create GitHub issues, PRs or other tracker items unless this message asks for one - '
                    'Taskuary IS the tracker and this task is the record. ')
                 + ('You may push and deploy as the work needs. ' if push_ok else
                    'Do NOT push, deploy, publish or release - commit locally and stop; the owner reviews and pushes. ')
                 + 'Missing required detail? Change nothing: ask one concrete question here, say if the sender must '
                   'answer, and wait.')
    # how this session ENDS. Without it the only ending is a person clicking Done, so a task
    # finished overnight produced no report and the sender got no answer (selfclose.py).
    from . import selfclose
    if selfclose.stays_open(store, tid): parts.append(selfclose.STAY_LINE)
    elif selfclose.mode(store) != 'off': parts.append(selfclose.SEED_LINE)
    # what earlier agents worked out about this ground, and how to add to it (handbook.py). The
    # wall says what is happening in this checkout this hour; the handbook says what is still
    # true next month, and no agent could see it before.
    # HOW to write one is not here: it is a standing rule, and standing rules ride in CODER.md,
    # which is already in this prompt and already capped (DOC_CHARS). An unconditional line here
    # is paid for by every session forever - and it pushed the seed past its budget the day the
    # handbook was switched on, which is how we found out it was ever off.
    from . import handbook
    if handbook.enabled(store):
        known = handbook.block(store, task_blob(store, tid))
        if known: parts.append(no_emails(' '.join(known.split())))
    out = ' '.join(' '.join(parts).split())
    # A command line has a hard limit (32767 on Windows) and the OS does not warn - it refuses
    # or clips. If we are over, the ASK is what gives, never the rules that keep an agent
    # inside its checkout, and it gives out loud.
    if len(out) > SEED_CEILING:
        over = len(out) - SEED_CEILING
        head, sep, tail = out.partition('FROM ')
        if sep and len(tail) > over + 400:
            out = head + sep + _cut(tail, len(tail) - over - 200, 'message')
        else:
            out = _cut(out, SEED_CEILING, 'prompt')
        logger.warning(f'seed for task {tid} trimmed to fit the command line ({len(out)} chars)')
    return out


_REPO_LINE = re.compile(r'^-\s+\*\*([^*]+)\*\*:\s*(.*)$', re.M)

def repo_map(store) -> dict:
    """{repo: what it is} out of SOUL.md's repo map - the routing table the operator doc already
    keeps. It is the answer to "which repo is this about", written down once."""
    return {mt.group(1).strip(): mt.group(2).strip() for mt in _REPO_LINE.finditer(str(store.doc('soul') or ''))}


def task_blob(store, tid: int) -> str:
    t = store.get_task(tid) or {}
    return ' '.join([t.get('Title') or '', str(t.get('Summary') or '')[:2000]]
                    + [str(m.get('BodyText') or '')[:2000] for m in store.list_messages(tid)])


def rank_repos(store, tid: int, profile: dict) -> list:
    """Every repo Taskuary knows about, best match for this task first: [(repo, score, has_path)].

    Scored over the WHOLE SOUL.md map, not just the repos this agent has a path for. Scoring only
    the mapped ones is how a reimbursement task landed in the integrations repo: with one path
    configured, "the only repo this agent has a path for" won without the ask ever being read."""
    from .routing import cosine, tokens
    paths, desc = (profile.get('cwd_map') or {}), repo_map(store)
    known = list(dict.fromkeys(list(desc) + list(paths)))
    text = task_blob(store, tid)
    xs, blob = tokens(text), text.lower()
    def score(r):
        dt = set(tokens(f"{r.replace('/', ' ')} {desc.get(r, '')}"))
        named = 1.0 if r.split('/')[-1].lower() in blob else 0.0
        # how much of what this repo IS turns up in the ask. Cosine alone dilutes a decisive word
        # ("reimbursement") to 0.07 against a long mail, which is how a real routing signal ended
        # up under the floor and lost to a repo that matched nothing at all.
        hit = len(dt & set(xs)) / max(4, len(dt))
        return round(named + 2 * hit + cosine(xs, list(dt)), 4)
    return sorted(((r, score(r), bool(paths.get(r))) for r in known), key=lambda x: -x[1])


_SKIP_DIRS = {'node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build', 'bin', 'obj',
              'appdata', 'site-packages', 'windows', 'program files', 'program files (x86)'}

def find_checkout(repo: str, profile: dict, budget: int = 4000, seconds: float = 3.0):
    """Where IS this repo on disk? "No local path configured" reads as "cannot find it" to the
    owner - who knows perfectly well the checkout exists - so before asking for a path, LOOK:
    walk the folders around the checkouts we already know (plus the usual homes for code), and
    match on the git remote, because the folder is not always named after the repo (this very
    project is ldbumble/taskuary checked out in a folder called taskhub)."""
    from pathlib import Path
    want = repo.lower().rstrip('/')
    roots = [Path(v).parent for v in list((profile.get('cwd_map') or {}).values())
             + [profile.get('cwd') or ''] if v]
    home = Path.home()
    roots += [home / 'Documents', home / 'source' / 'repos', home / 'repos', home / 'code', home / 'projects']
    # '/' (or 'C:\\') as a search root walks the whole machine. A checkout at /workspace
    # used to do that, then Path.is_file() on an unreadable /etc/.../.git/config 500'd
    # GET /api/tasks/:id/repos instead of listing the repos we already know about.
    queue, seen, deadline = [], set(), time.time() + seconds
    for r in roots:
        try:
            if not r.is_dir() or r == r.parent: continue
        except OSError:
            continue
        queue.append((r, 0))
    while queue and budget > 0 and time.time() < deadline:
        d, depth = queue.pop(0)
        key = str(d).lower()
        if key in seen or d.name.lower() in _SKIP_DIRS or d.name.startswith('.'): continue
        seen.add(key); budget -= 1
        cfg = d / '.git' / 'config'
        try:
            is_repo = cfg.is_file()
        except OSError:
            continue                        # locked folder: neither a hit nor a place to descend
        if is_repo:
            try:
                if want in cfg.read_text(encoding='utf-8', errors='ignore').lower(): return str(d)
            except OSError: pass
            continue                        # a repo dir either way: never descend into one
        if depth >= 3: continue
        try: queue += [(c, depth + 1) for c in d.iterdir() if c.is_dir()]
        except OSError: continue
    return None


def path_for_repo(store, repo: str):
    """Where a repo lives, WITHOUT opening a session on it - the read-only half of what
    open_session does before it starts anything. Any agent that has been there knows the
    way, so the maps are asked in turn before the disk is searched."""
    import json
    if not repo: return None
    for a in store.list_agents():
        p = (json.loads(a.get('Config') or '{}').get('cwd_map') or {}).get(repo)
        if p and os.path.isdir(p): return p
    found = find_checkout(repo, {'cwd_map': {}})
    return found if found and os.path.isdir(found) else None


def remember_path(store, agent: str, repo: str, path: str):
    """A found checkout is worth keeping: onto the agent row AND config.toml, so the search
    runs once per repo, not once per session."""
    import json
    from . import config as cfg_mod
    row = store.get_agent(agent)
    if not row: return
    prof = json.loads(row.get('Config') or '{}')
    prof.setdefault('cwd_map', {})[repo] = path
    store.upsert_agent(agent, row.get('Kind') or 'coding', 'cli', json.dumps(prof))
    try:
        conf = cfg_mod.load()
        # only when the agent has a real profile there - a partial {cwd_map} entry would be
        # upserted at next boot as an agent with no cmd
        if (conf.get('agents') or {}).get(agent):
            conf['agents'][agent].setdefault('cwd_map', {})[repo] = path
            cfg_mod.save(conf)
    except Exception as e:
        logger.warning(f'could not persist the found path to config: {e}')


# The tag a task carries when the owner said "this one is not about a codebase".
NO_REPO = 'none'


def repo_tag(task: dict) -> str | None:
    """The `repo:` tag on a task, if it has one - the override that always wins over the guess."""
    return (re.search(r'repo:([^\s,]+)', str((task or {}).get('Tags') or '')) or [None, None])[1]


APP = (__package__ or 'taskuary').split('.')[0]

def our_own_repo(store, tid: int, known) -> str:
    """A task about Taskuary's own machinery belongs in Taskuary's own checkout. A scheduled report
    that failed is the plain case: it is our scheduler, our prompt, our code - and it was sent to a
    coder in a completely unrelated repository (the owner, 2026-09-03: "It was issue with the github
    trending report but it says fannapp???")."""
    t = store.get_task(tid) or {}
    ours = (str(t.get('Source') or '') == 'report'
            or any(str(m.get('Channel') or '') == 'report' for m in store.list_messages(tid))
            or str(t.get('SourceRef') or '').startswith('assistant:'))
    if not ours: return ''
    return next((r for r in known if APP in r.split('/')[-1].lower()), '')


def guess_repo(store, tid: int, profile: dict) -> tuple:
    """Which checkout does this task belong in? The tag on the task wins - that is the override,
    and the only thing that always does what it says.

    Otherwise the ask is matched against the SOUL.md repo map. A repo the ask clearly names is
    returned even when this agent has no path for it, because open_session must then REFUSE
    rather than quietly open the default folder - an agent editing the wrong checkout is far
    worse than one that will not start. Only when the ask points nowhere at all does a single
    configured repo become the default.

    Taskuary deciding this is the point: an agent left to work it out reads SOUL.md over the API,
    or guesses from the folder it happens to have started in."""
    t = store.get_task(tid) or {}
    tag = repo_tag(t)
    # "no repository" is an ANSWER, not a missing one: a general question ("what does this mean",
    # "prepare me for this meeting") has no checkout, and leaving the field blank used to hand it
    # to the guess below - which then opened the highest-scoring repo and set an agent looking for
    # code to change. Only the explicit tag stops that.
    if tag == NO_REPO: return None, 'a general question - no repository'
    if tag: return tag, 'tagged on the task'
    paths = profile.get('cwd_map') or {}
    # no repo paths at all = this agent does not do repo routing. Naming one anyway would put a
    # REPO line in the prompt for a folder the session is not in.
    if not paths: return (None, None)
    ranked = rank_repos(store, tid, profile)
    if not ranked: return (None, None)
    own = our_own_repo(store, tid, [r for r, _s, _h in ranked])
    if own: return own, "Taskuary's own work - our own checkout"

    # A relationship learned from repeated OWNER repo choices outranks word overlap. It does not
    # learn from this answer, so a bad automatic route cannot reinforce itself. When one project
    # spans several repositories, the task's words still have to distinguish which checkout.
    from .projects import repositories_for_task
    related, relation_why = repositories_for_task(store, tid)
    known = {r for r, _score, _has in ranked}
    related = [r for r in related if r in known]
    if len(related) == 1: return related[0], relation_why
    if len(related) > 1:
        choices = [row for row in ranked if row[0] in related]
        if choices:
            best, sc, _has = choices[0]
            runner = choices[1][1] if len(choices) > 1 else 0.0
            if sc >= .05 and sc >= max(runner * 1.4, runner + .04):
                return best, relation_why + '; message content selected this repository'
        return None, relation_why + '; the project has several repositories, so choose one'

    best, sc, _has = ranked[0]
    runner = ranked[1][1] if len(ranked) > 1 else 0.0
    # "clearly the one" is a RELATIVE test: it beats the alternatives. A fixed floor is the wrong
    # question on a long mail, and the old fallback - take the only repo we have a path for - is
    # what put a reimbursement task in the integrations checkout, against the evidence.
    if sc >= .05 and sc >= max(runner * 1.4, runner + .04):
        return best, ('named in the ask' if best.split('/')[-1].lower() in task_blob(store, tid).lower()
                      else 'closest match in the SOUL.md repo map')
    # the ask points nowhere in particular: one configured repo is a fair default, several is a guess
    return (list(paths)[0], 'the only repo this agent has a path for') if len(paths) == 1 else (None, None)


def start_on_task(store, tid: int, agent: str = 'coder', model: str = None, instruction: str = None,
                  actor: str = 'owner', cwd: str = None, _chain: list = None) -> dict:
    """Put a CLI on a task, in a REAL terminal - the only way an agent starts work here. An
    agent you cannot watch, interrupt or answer is the thing this app exists to replace."""
    import json
    t = store.get_task(tid)
    if not t: raise ValueError(f'no task {tid}')
    # the owner opening a session makes the task theirs to end (selfclose.claim) - before the seed
    # is built, so the prompt says "stay at the prompt" instead of "run --done"
    from . import selfclose as _sc
    _sc.claim(store, tid, actor)
    live = for_task(tid)
    if live:
        if t.get('Status') != 'in_progress': store.update_task(tid, {'Status': 'in_progress'}, actor)
        return {**live, 'existing': True}
    from . import agents as hub_agents
    chain = list(_chain or hub_agents.agent_chain(store, agent))
    if not chain: chain = [agent]
    term = repo = why = None
    chosen = None
    last_error = None
    for i, candidate in enumerate(chain):
        row = store.get_agent(candidate or '')
        if not row:
            last_error = ValueError(f'unknown agent: {candidate}')
            if i + 1 < len(chain): continue
            raise last_error
        repo, why = guess_repo(store, tid, json.loads(row.get('Config') or '{}'))
        # A continuation names the exact checkout from the saved transcript. Use it when it still
        # exists; a moved/deleted checkout falls back through the normal guarded repo resolution.
        continued_cwd = cwd if cwd and os.path.isdir(cwd) else None
        try:
            term = open_session(store, candidate, tid, repo, continued_cwd, 32, 110, actor,
                                model if i == 0 else None,
                                seed_fn=lambda here, r=repo: seed_text(store, tid, instruction, r, here))
            chosen = candidate
            chain = chain[i:]
            break
        except Exception as e:
            last_error = e
            if i + 1 >= len(chain) or not hub_agents.availability_failure(e): raise
            store.add_comment(tid, 'router', 'agent',
                              f'{candidate} was unavailable before the session opened; trying {chain[i + 1]}.')
    if not term: raise last_error or RuntimeError('no coding agent could start')
    remaining = chain[1:]
    if remaining:
        def replace(dead, reason):
            # Drop only this dead pane. The task, held review, source mail and attachments remain
            # untouched; start_on_task rebuilds the same seed for the replacement CLI.
            SESSIONS.pop(dead.sid, None)
            nxt = remaining[0]
            store.add_comment(tid, 'router', 'agent',
                              f'{chosen} became unavailable; continuing with backup {nxt}.')
            start_on_task(store, tid, nxt, None, instruction, actor, cwd, _chain=remaining)
        term.failover = replace
    store.clear_dispatch(tid)          # started (by whatever road): it is no longer waiting
    if repo and why != 'tagged on the task':
        store.add_comment(tid, actor, 'human', f'Session opened in {repo} - {why}.')
    store.add_comment(tid, actor, 'human' if actor == 'owner' else 'agent',
                      f'{chosen} started on this task in a live session ({term.cwd}).')
    if t.get('Status') != 'in_progress': store.update_task(tid, {'Status': 'in_progress'}, actor)
    # A task started from the Board or the Tasks tab has no message behind it, so it had no
    # Timeline row - and an agent could work it for forty minutes while the page that is
    # supposed to be the record of the day said nothing. Stamped at the session's own start.
    from . import ownwork
    ownwork.ensure(store, tid, term.started, f'{chosen} started here', actor)
    # Starting a PTY is live state, not merely a database write. If the task was already marked
    # in_progress there may be no update_task() below to wake the Assistant, and its three-second
    # pile cache can still contain the old "nobody on it" row. Publish and invalidate at the point
    # where the session unquestionably exists, whichever screen started it.
    try:
        from . import funnel as _funnel, live as _live
        _funnel.invalidate()
        _live.emit('task-changed', task_id=tid)
    except Exception:
        pass
    return {**term.info(), 'existing': False}


def get(sid): return SESSIONS.get(sid)


# A session that has printed nothing for this long is parked at a prompt (or finished) -
# either way the next move is the owner's, not the agent's. The FALLBACK: the CLIs we know
# say it on screen, and that is read first (phase_of).
IDLE_WAITING = 45
# A state observed in the terminal must survive this long before the rest of Taskuary sees it.
# This is deliberately shorter than the UI polls: a genuine question is visible on the next
# poll, while the clear/draw/clear frames of one TUI repaint can never become a hand raise.
PHASE_DWELL = 3.0

# What the last lines of the screen say. Claude Code shows "esc to interrupt" (and a spinner)
# while it works and "? for shortcuts" / "shift+tab to cycle" / "auto mode on" at its prompt;
# codex shows "esc to interrupt" too and a bare "›" prompt; gemini "Type your message". The
# LAST line wins where both appear - a status line redrawn in place leaves old frames in the
# scrollback, so an "esc to interrupt" three lines up is history, not now.
_WORKING = re.compile(r'esc to interrupt|esc to cancel|\(thinking\)|[⠋⠙⠹⠸⠼⠴⠦⠧⠇⠏]|\b(thinking|working|running)…', re.I)
_PARKED = re.compile(r'shift\+tab to cycle|\? for shortcuts|bypass permissions on|auto mode on|type your message|'
                     r'\?\s*$|\b(y/n|yes/no|do you want|would you like|should i|which (one|of these)|press enter|'
                     r'choose an option|select an option|enter to (confirm|select))\b|^\s*[›>❯](?:\s*\d+\.)?', re.I)

def _observed_phase(t) -> str:
    """One raw observation from the rendered screen, with a fallback for small test doubles."""
    try: lines = t.status_tail(8)
    except (AttributeError, TypeError): lines = t.tail(4)
    return phase_of(lines)


def stable_phase_of(t, now: float = None) -> str:
    """Return the session's latched `working` or `parked` phase.

    Full-screen CLIs repaint a screen in several writes. During a working turn, one intermediate
    frame can contain the bare input prompt and the next contains the spinner again. Publishing
    each observation made every consumer disagree in public: the Timeline waved, the Assistant
    alerted, then both took it back. A transition is now accepted only after the same target has
    held for PHASE_DWELL seconds. Process exit is separate (`alive=False`) and remains immediate.
    """
    at = time.time() if now is None else float(now)
    raw = _observed_phase(t)
    stable = getattr(t, '_phase_stable', 'working')
    # Known screen chrome is authoritative. Silence is only a fallback for third-party CLIs whose
    # prompt Taskuary does not recognise. Fresh real output can wake such a parked CLI again.
    target = raw if raw in ('working', 'parked') else None
    if target is None and t.idle() >= IDLE_WAITING: target = 'parked'
    elif target is None and stable == 'parked' and t.idle() < 2: target = 'working'

    if target is None or target == stable:
        t._phase_candidate = None
        t._phase_since = at
        return stable
    if getattr(t, '_phase_candidate', None) != target:
        t._phase_candidate, t._phase_since = target, at
        return stable
    if at - float(getattr(t, '_phase_since', at)) >= PHASE_DWELL:
        t._phase_stable, t._phase_candidate, t._phase_since = target, None, at
        return target
    return stable


def waiting_of(t) -> bool:
    """Compatibility helper for light test doubles; real Terms publish their latched phase."""
    if isinstance(t, Term): return stable_phase_of(t) == 'parked'
    p = _observed_phase(t)
    return p == 'parked' or (p != 'working' and t.idle() >= IDLE_WAITING)


def phase_of(lines) -> str:
    """'working' | 'parked' | 'unknown' from the tail of a screen.

    WORKING WINS, anywhere in the tail. Claude Code draws ONE footer carrying both readings at
    once - "bypass permissions on (shift+tab to cycle) - esc to interrupt - for agents" - and the
    parked half was tested first, so a working agent read as parked whenever that footer was the
    last line drawn, and as working again on the next frame. That flap is what said "stopped and is
    waiting on you" and then "is working, nothing for you there" seconds apart (the owner,
    2026-09-03: "it's stopped for a second that changed it's mind... very buggy").

    "esc to interrupt" is only ever on screen while a turn is in flight, so it is the strongest
    thing the screen says: one sighting of it in the last few lines means the agent is busy."""
    ls = [str(l) for l in (lines or []) if str(l).strip()]
    for l in reversed(ls):                      # newest first: the first line that says anything decides
        if _WORKING.search(l): return 'working'   # ...and WITHIN a line, working wins: one footer, both halves
        if _PARKED.search(l): return 'parked'
    return 'unknown'

def for_task(task_id, tail=0, details=True):
    """The live session working a task, if any - what makes a task 'agent working' even
    though no headless run exists."""
    t = next((x for x in list(SESSIONS.values()) if x.task_id == task_id and x.alive), None)
    return _info(t, tail, details) if t else None


def screen(sid: str, lines: int = 32) -> dict | None:
    """A read-only snapshot of exactly what the PTY screen currently renders.

    A second xterm cannot ask a full-screen TUI to repaint at a preview size without resizing
    the real working session. Replay the same byte stream through the server's VT emulator at
    the PTY's actual geometry instead, then return the visible tail for compact viewers.
    """
    t = get(sid)
    if not t: return None
    n = max(1, min(int(lines or 32), 120))
    shown = render(t.scrollback(), t.cols, t.rows).splitlines()
    return {'sid': t.sid, 'alive': bool(t.alive), 'rows': t.rows, 'cols': t.cols,
            'lines': shown[-n:]}


# What a TUI paints at the bottom of its screen is not what it is asking: a status bar, a theme
# name, a hint about shortcuts. The pipe's card showed "Catppuccin Mocha Dracula..." where the
# agent's question should have been (the 2026-09-03 break test), because the raw buffer's last
# lines are whatever was drawn last. These are the lines to leave out.
_TUI_FURNITURE = re.compile(r'^[\s─-╿▀-▟\-=_~*.·•]+$'                # rules, borders, spinners
                            r'|^\s*(\?|/)\s*for\b|shift\s*\+\s*tab|ctrl\s*\+|esc to |press enter to '
                            r'|^\s*(catppuccin|dracula|solarized|nord|gruvbox|monokai|tokyo ?night)\b'
                            r'|^\s*(auto-?accept|bypassing permissions|plan mode|accepting edits)\b'
                            r'|^\s*\d+%?\s*(context|tokens?) (left|used)\b|^\s*(tokens?|context):', re.I)


def asking_lines(sid: str, n: int = 4) -> list:
    """The last lines of the agent's RENDERED screen that could be a question - the same pyte
    render the reopened pane seeds from, with the chrome dropped. [] when there is no session."""
    snap = screen(sid, 40)
    if not snap: return []
    lines = [l.rstrip() for l in snap['lines'] if l.strip() and not _TUI_FURNITURE.search(l) and not _CHROME.search(l)]
    return lines[-max(1, n):]


def say_to_task(store, task_id: int, msg: dict, actor: str = 'router') -> bool:
    """Type an inbound answer INTO the task's live session. The agent asked a question, the
    hub asked the person, the person answered - the answer belongs in front of the agent,
    not on a timeline it cannot read. Fed in seed()-sized bites (a one-shot paste drops
    bytes mid-stream), then Enter until it lands. False = no live session to tell.
    Accepts a message as a DB row (BodyText/FromName) or an ingest dict (body/from_name)."""
    t = next((x for x in list(SESSIONS.values()) if x.task_id == task_id and x.alive), None)
    if not t: return False
    who = msg.get('FromName') or msg.get('from_name') or msg.get('FromEmail') or msg.get('from_email') or 'the sender'
    body = str(msg.get('BodyText') or msg.get('body') or '').strip()
    if not body: return False
    type_into(t, f'{who} answered (by {msg.get("Channel") or msg.get("channel") or "mail"}): {body}'[:4000])
    store.add_comment(task_id, actor, 'agent', f"{who}'s answer was typed into the live session.")
    store.audit('task', task_id, 'answer_forwarded', actor, detail={'from': who})
    return True


def clean_typed(text: str) -> str:
    """One printable line. Control bytes go too, not just whitespace: ESC interrupts a TUI and ^C
    kills it, and this text came from a message or a PR comment, not from the owner (audit 2026-09-02)."""
    return ' '.join(re.sub(r'[\x00-\x1f\x7f]', ' ', str(text or '')).split())


def type_into(t, text: str):
    """Type `text` into a live session the way seed() proved works: flattened to one line (a
    newline is Enter in a TUI), fed in frame-sized bites (a one-shot paste drops bytes
    mid-stream), then Enter until the box answers. Runs on its own thread; returns at once.
    Shared by say_to_task (an inbound answer) and waitroom.deliver (the owner's queued notes)."""
    text = clean_typed(text)
    def go():
        for i in range(0, len(text), SEED_CHUNK):
            t.write(text[i:i + SEED_CHUNK])
            time.sleep(SEED_CHUNK_GAP)
        time.sleep(.5)
        for key in ('\r', '\r', '\n'):
            was = t.n
            t.write(key)
            time.sleep(SEED_ENTER)
            if t.n > was: return
    threading.Thread(target=go, daemon=True).start()


def session_for(task_id):
    """This task's session OBJECT - the live one if there is one, else the most recent that has
    not been reaped yet. Unlike for_task, an exited session counts: its scrollback is exactly
    what wrapping up needs to read."""
    mine = [x for x in list(SESSIONS.values()) if x.task_id == task_id]
    return next((x for x in mine if x.alive), None) or (max(mine, key=lambda x: x.started) if mine else None)


def transcript_for(store, task_id) -> tuple:
    """(text, agent, sid) to wrap a task up from. A session still in memory is read live;
    otherwise the one the last session filed when it ended. Wrapping up must not depend on a
    pty still being around - the work happened either way, and a task you cannot close out is
    the worst of the two failures."""
    t = session_for(task_id)
    if t:
        text = harvest(t)
        # a session that has printed nothing yet (just opened, or spawn failed) must not shadow
        # the FILED transcript of the session that actually did the work
        if text.strip(): return text, (t.agent or 'coder'), t.sid
    row = store.last_transcript(task_id) or {}
    return (row.get('Text') or ''), (row.get('Agent') or 'coder'), row.get('Sid')


def live_sessions(tail=3, details=True):
    return [_info(t, tail, details) for t in list(SESSIONS.values()) if t.alive]


def close(sid):
    t = SESSIONS.pop(sid, None)
    if t: t.close()
    return bool(t)


def release_task(store, task_id, actor='terminal', note=None) -> bool:
    """Release unfinished work when its worker has really gone away.

    Idempotence matters: an HTTP close and the PTY's EOF can observe the same ending. Only the
    first caller that still sees ``in_progress`` changes state or writes the handoff comment.
    """
    task = store.get_task(task_id) or {}
    if task.get('Status') != 'in_progress': return False
    for run in store.list_runs(task_id):
        if run.get('Status') == 'running':
            store.update_run(run['RunId'], {'Status': 'stopped'}, finished=True)
    store.update_task(task_id, {'Status': 'open'}, actor)
    store.add_comment(task_id, actor, 'agent', note or
                      'The agent session ended. The task is open again - nobody is working it.')
    return True


def recover_after_restart(store) -> int:
    """Clear persisted worker state that cannot survive a Taskuary process restart."""
    # Sessions and headless-run threads are process-owned; none can be live before the new process
    # has started one. Repair both halves so the Board never invents a worker from yesterday.
    for run in store.running_runs():
        store.update_run(run['RunId'], {'Status': 'stopped'}, finished=True)
    released = 0
    for task in store.list_tasks(status='in_progress'):
        released += int(release_task(store, task['TaskId'], 'startup',
                                    'Taskuary restarted after the agent session ended. '
                                    'The task is open again - nobody is working it.'))
    return released


def shutdown_sessions():
    """Close every in-memory agent session during an orderly application shutdown."""
    sessions = list(SESSIONS.items())
    for sid, session in sessions:
        SESSIONS.pop(sid, None)
        try:
            # Do this synchronously before process teardown. Waiting for a dying PTY's pump thread
            # can lose the state transition when the interpreter exits immediately afterward.
            if getattr(session, 'store', None) and getattr(session, 'task_id', None):
                release_task(session.store, session.task_id, 'shutdown',
                             'Taskuary closed the agent session. The task is open again - nobody is working it.')
            # Shutdown is cleanup, not a new AI job. General task close normally mines useful
            # learning, but launching a headless model while the process is exiting can only
            # become an orphan itself.
            if getattr(session, 'mode', '') == 'assistant': session.close(learn=False)
            else: session.close()
        except Exception as e:
            logger.debug(f'could not close session {sid} during shutdown: {e}')
    return len(sessions)


KEEP_DEAD = 600     # an exited session stays listed this long so you can still read it


def reap():
    """Drop long-finished sessions nobody is watching (a fresh exit stays readable). The
    transcript was filed when the pty ended, so what is dropped here is only the bytes."""
    for sid in [s for s, t in list(SESSIONS.items())
                if not t.alive and not t.subs and time.time() - (t.ended or 0) > KEEP_DEAD]:
        SESSIONS.pop(sid, None)


def listing(details=True):
    reap()
    return [_info(t, 0, details) for t in list(SESSIONS.values())]
