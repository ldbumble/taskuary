"""Real terminals, in the app: a CLI agent (or a plain shell) spawned under a pseudo-tty,
its bytes streamed to the browser over a WebSocket and rendered by xterm.js. Unlike the
headless runs (agents.run_cli - pipes, one prompt in, one result out) this is INTERACTIVE:
the agent's own TUI, its approval prompts, and your typing all go through it.

Windows uses ConPTY via pywinpty; POSIX uses the stdlib pty module.
"""
import os, re, subprocess, threading, time, uuid
from collections import deque
from datetime import datetime
from loguru import logger

SCROLLBACK = 200_000        # chars kept for late joiners / reconnects
SESSIONS = {}               # sid -> Term
SEED_WAIT, SEED_QUIET = 25, 1.2     # seconds: how long to wait for a TUI, and what 'settled' means
SEED_SETTLE = 8                     # cap on waiting for the input box to finish laying out a long paste
SEED_ENTER = 1.0                    # how long to give the TUI to react to Enter before pressing again
SEED_RETRIES, SEED_BUDGET = 3, 180  # retype attempts after a boot dialog ate the prompt, and the total window
DOC_CHARS = 1800                    # how much of CODER.md rides along in the prompt


# A terminal must start a FRESH session. Taskuary can itself be launched from inside an
# agent CLI, and those processes export session markers that make the child resume /
# inherit the parent's conversation - strip anything that would carry that in.
_DIRTY = ('CLAUDE_CODE', 'CLAUDECODE', 'CLAUDE_SESSION', 'ANTHROPIC_SESSION', 'CODEX_SESSION', 'GEMINI_SESSION')

def clean_env() -> dict:
    return {k: v for k, v in os.environ.items() if not k.upper().startswith(_DIRTY)}


class _WinPty:
    def __init__(self, argv, cwd, rows, cols):
        try:
            from winpty import PtyProcess
        except ImportError:
            raise RuntimeError('the interactive terminal needs pywinpty on Windows - pip install pywinpty')
        self.p = PtyProcess.spawn(argv, cwd=cwd, dimensions=(rows, cols), env=clean_env())
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
    def __init__(self, argv, cwd, rows, cols):
        import fcntl, pty, struct, termios
        self.fd, slave = pty.openpty()
        fcntl.ioctl(self.fd, termios.TIOCSWINSZ, struct.pack('HHHH', rows, cols, 0, 0))
        self.p = subprocess.Popen(argv, cwd=cwd, stdin=slave, stdout=slave, stderr=slave,
                                  close_fds=True, start_new_session=True, env=clean_env())
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
        self.buf, self.n, self.ended, self.last = deque(), 0, None, time.time()
        self.seeded = ''                                  # the prompt we typed: echoed back, not said
        self.store = store                                # so the pty can file its own transcript when it ends
        self.subs = []                                    # (loop, asyncio.Queue)
        self.taps = []                                    # plain callables, for server-side readers
        self.pty = (_WinPty if os.name == 'nt' else _UnixPty)(argv, cwd, rows, cols)
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
            self.last = time.time()                       # silence is the signal: see idle()
            self._append(data); self._emit(data)
            for f in list(self.taps):
                try: f(data)
                except Exception as e: logger.debug(f'terminal tap failed: {e}')
        self.alive, self.ended = False, time.time()       # exited: the tab stays readable for a while
        self.keep()                                       # the transcript must outlive the pty
        self._emit(None)

    def keep(self):
        """File this session's readable transcript on its task. A pty is not storage: sessions are
        reaped, and once the last one was gone the task could no longer be wrapped up at all - the
        buttons had nothing to read and quietly disappeared. Written on exit AND on close, because
        either can come first."""
        if not (self.store and self.task_id): return
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

    def _echoed(self) -> bool:
        """Is the typed prompt actually ON the screen? A CLI that boots into a dialog - codex's
        first-run "do you trust this directory?" is the live example - silently eats whatever is
        typed at it, and pressing Enter blind would ANSWER that dialog, which is the owner's
        security decision to make, not ours.

        Claude Code (v2+) folds a burst-typed prompt into '[Pasted text #N]' chips - the words
        themselves never render. The chip IS the echo: before it was recognized here, the seeder
        read the missing words as "a dialog ate it", retyped once per retry (chips piling up on
        screen) and never dared press Enter - a session that looked busy and started nothing.

        And the words that DO render may be either end of the prompt: a long seed scrolls the
        input box, so only its TAIL stays visible - the head check alone read a fully-typed
        prompt as 'eaten' and retyped it on top of itself, three glued copies and no Enter.
        All checks compare with ALL whitespace stripped, because the box wraps at the terminal
        width and a chip or phrase broken across two lines is still the echo."""
        scr = ''.join(render(self.scrollback(), self.cols, self.rows).split())
        if '[Pastedtext' in scr: return True
        flat = ''.join(self.seeded.split())
        return len(flat) > 10 and (flat[:40] in scr or flat[-40:] in scr)

    def seed(self, text: str):
        """Type the first prompt in AND SEND IT. The owner asked for the work when they clicked
        the button, so leaving a filled-in box for them to come back and press Enter on is not
        starting - it is a session that looks busy and has done nothing.

        Everything here is verified, not assumed: wait for the boot to go quiet, type, then check
        the text ECHOED before any Enter goes in. Not echoed means a boot dialog ate it (a trust
        prompt, a login) - those are answered by the owner in the terminal, never by us - so wait
        for the screen to move past it and type the prompt again. Echoed means press Enter until
        the session answers, because a CR arriving mid-redraw reads as part of the same edit and
        some TUIs submit on \\n not \\r."""
        def go():
            start = time.time()
            while self.alive and not self.n and time.time() - start < SEED_WAIT: time.sleep(.1)
            if not self.settle(max(1.0, SEED_WAIT - (time.time() - start))): return
            self.seeded = ' '.join(text.split())
            for attempt in range(SEED_RETRIES):
                self.write(self.seeded)                   # attempt > 0 = retyped: the first copy was eaten
                if not self.settle(SEED_SETTLE): return
                if not self._echoed():
                    # a dialog is up: hold until the screen changes (the owner answered it),
                    # inside the overall budget, then try the prompt again
                    was = self.n
                    while self.alive and self.n == was and time.time() - start < SEED_BUDGET:
                        time.sleep(.5)
                    if time.time() - start >= SEED_BUDGET:
                        logger.warning(f'terminal {self.sid}: the CLI is waiting on a prompt of its own '
                                       f'(trust/login?) - answer it and the seeded ask will need retyping')
                        return
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
    def resize(self, rows, cols):
        if self.alive:
            try:
                self.pty.resize(int(rows), int(cols))
                self.rows, self.cols = int(rows), int(cols)
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

    def info(self, tail=0):
        return {'sid': self.sid, 'label': self.label, 'cwd': self.cwd, 'taskId': self.task_id,
                'agent': self.agent, 'alive': self.alive, 'started': self.started,
                'idle': self.idle(), 'cmd': ' '.join(self.argv),
                **({'tail': self.tail(tail)} if tail else {})}


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
# TRANSLATED, because the TUI rejects them outright: `--full-auto` exists only under exec, and
# its interactive equivalent is the workspace-write sandbox (approvals then happen IN the
# session, where a person is watching - which is the whole point of running one).
PIPE_SUBCOMMANDS = {'exec', 'e'}
PIPE_TRANSLATE = {'--full-auto': ['--sandbox', 'workspace-write']}

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


def agent_argv(profile: dict, model: str = None) -> list:
    """Interactive invocation of a configured CLI: its command, its own flags minus the pipe
    ones, and the model flag the headless runner uses (`model_arg`, e.g. codex wants -m).
    `interactive_args` in the profile replaces the lot, for CLIs that need a subcommand."""
    from .agents import _resolve_cmd
    argv = _resolve_cmd(profile.get('cmd') or 'claude')
    argv += list(profile['interactive_args']) if profile.get('interactive_args') else interactive_args(profile.get('args'))
    model = model or profile.get('model')
    return argv + ([profile.get('model_arg') or '--model', str(model)] if model else [])


def open_session(store, agent: str = None, task_id: int = None, repo: str = None, cwd: str = None,
                 rows: int = 32, cols: int = 110, actor: str = 'owner', model: str = None) -> Term:
    """Start a terminal: a configured agent CLI, or a plain shell when agent is None."""
    import json
    profile = {}
    if agent:
        row = store.get_agent(agent)
        if not row: raise ValueError(f'unknown agent: {agent}')
        profile = json.loads(row.get('Config') or '{}')
        argv, label = agent_argv(profile, model), agent
    else:
        argv, label = default_shell(), 'shell'
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
    cwd = cwd or profile.get('cwd') or os.getcwd()
    if not os.path.isdir(cwd): raise ValueError(f'working directory does not exist: {cwd}')
    t = Term(argv, cwd, label, task_id, agent, rows, cols, store)
    SESSIONS[t.sid] = t
    # A reply drafted from the mail alone promises what this session has not worked out yet, so
    # it stops waiting in Review and comes back rewritten from the report - see coder.raise_reply.
    if task_id and store.hold_reviews(task_id, 'held while an agent works the task - the reply is written from what it finds'):
        logger.debug(f'held the pending reply on task {task_id} while {agent or "a session"} works it')
    store.audit('terminal', 0, 'open', actor, detail={'sid': t.sid, 'agent': agent, 'cwd': cwd, 'task': task_id})
    return t


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


# What a TUI paints over and over and none of it is what the agent SAID: spinner frames, the
# hint bar, the token counter, rules, the statusline tip. It all landed in the wrap-up - and in
# the transcript we hand the AI to write from.
_CHROME = re.compile(r'esc to interrupt|\? for shortcuts|for agents|to manage|\bTip:\s|^\s*\d[\d,]*\s+tokens?\b|\(\d+s\)\s*$|\b\d[\d,]*\s+tokens\)\s*$|still r?unning\s*$', re.I)
_WORDLESS = re.compile(r'^[^A-Za-z]*$')
_HINT = re.compile(r'\bTip:\s+Use /')      # a slash-command hint, any length
_SPIN = re.compile('[·✢✳✻✽✶✷✸✹✺⏺◐◓◑◒✦❯›]')       # the frames themselves
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
    if repo or cwd: parts.append(f"REPO: {repo or cwd} - you are already in it; work only here.")
    if instruction and instruction.strip(): parts.append(f'ASK: {instruction.strip()}')
    from .triage import strip_boilerplate
    if m: parts.append(f"FROM {m.get('FromName') or m.get('FromEmail')} on {m.get('Channel')}, "
                       f"subject \"{m.get('Subject') or ''}\": "
                       f"{strip_boilerplate(m.get('BodyText') or '')[:3000]}")
    elif t.get('Summary'): parts.append(f"ASK: {strip_boilerplate(str(t['Summary']))[:3000]}")
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
                          f'continue from it, do not start over: {note[:3000]}')
    rules = rules_text(store)
    if rules: parts.append(f'RULES: {rules}')
    # The job, spelled out. An agent handed a bare task description went looking for the ticket
    # it came from - Taskuary's own API, its database, the mailbox - and spent its first minute
    # re-fetching what is already in this paragraph.
    issues_ok, push_ok = store.github_permissions()
    parts.append('WHAT TO DO: work it from THIS message alone. Diagnose the problem, fix it if it '
                 'is fixable, and if it is not, say plainly what the problem is and what it would '
                 'take. Do NOT call the Taskuary API, read its database or go looking for this task '
                 'anywhere - everything known about it is above. '
                 + ('GitHub is the issue tracker here: open and update issues for the work as '
                    'the team expects. '
                    if issues_ok else
                    'Do NOT create GitHub issues, PRs or any other tracker items for this work '
                    'unless this message explicitly asks for one - Taskuary IS the tracker, and '
                    'this task is the record. ')
                 + ('You may push and deploy as the work needs. ' if push_ok else
                    'Do NOT push, deploy, publish or release anything - commit locally and stop; '
                    'the owner reviews and pushes. Only when this message explicitly says to. ')
                 + 'Ask the owner here in the session if something is genuinely missing.')
    return ' '.join(' '.join(parts).split())


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
    seen, queue, deadline = set(), [(r, 0) for r in roots if r.is_dir()], time.time() + seconds
    while queue and budget > 0 and time.time() < deadline:
        d, depth = queue.pop(0)
        key = str(d).lower()
        if key in seen or d.name.lower() in _SKIP_DIRS or d.name.startswith('.'): continue
        seen.add(key); budget -= 1
        cfg = d / '.git' / 'config'
        if cfg.is_file():
            try:
                if want in cfg.read_text(encoding='utf-8', errors='ignore').lower(): return str(d)
            except OSError: pass
            continue                        # a repo dir either way: never descend into one
        if depth >= 3: continue
        try: queue += [(c, depth + 1) for c in d.iterdir() if c.is_dir()]
        except OSError: continue
    return None


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
    tag = (re.search(r'repo:([^\s,]+)', str(t.get('Tags') or '')) or [None, None])[1]
    if tag: return tag, 'tagged on the task'
    paths = profile.get('cwd_map') or {}
    # no repo paths at all = this agent does not do repo routing. Naming one anyway would put a
    # REPO line in the prompt for a folder the session is not in.
    if not paths: return (None, None)
    ranked = rank_repos(store, tid, profile)
    if not ranked: return (None, None)
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
                  actor: str = 'owner') -> dict:
    """Put a CLI on a task, in a REAL terminal - the only way an agent starts work here. An
    agent you cannot watch, interrupt or answer is the thing this app exists to replace."""
    import json
    live = for_task(tid)
    if live: return {**live, 'existing': True}
    t = store.get_task(tid)
    if not t: raise ValueError(f'no task {tid}')
    row = store.get_agent(agent or '')
    if not row: raise ValueError(f'unknown agent: {agent}')
    repo, why = guess_repo(store, tid, json.loads(row.get('Config') or '{}'))
    term = open_session(store, agent, tid, repo, None, 32, 110, actor, model)
    if repo and why != 'tagged on the task':
        store.add_comment(tid, actor, 'human', f'Session opened in {repo} - {why}.')
    term.seed(seed_text(store, tid, instruction, repo, term.cwd))
    store.add_comment(tid, actor, 'human' if actor == 'owner' else 'agent',
                      f'{agent} started on this task in a live session ({term.cwd}).')
    if t.get('Status') == 'open': store.update_task(tid, {'Status': 'in_progress'}, actor)
    return {**term.info(), 'existing': False}


def get(sid): return SESSIONS.get(sid)


# A session that has printed nothing for this long is parked at a prompt (or finished) -
# either way the next move is the owner's, not the agent's.
IDLE_WAITING = 45

def for_task(task_id, tail=0):
    """The live session working a task, if any - what makes a task 'agent working' even
    though no headless run exists."""
    t = next((x for x in SESSIONS.values() if x.task_id == task_id and x.alive), None)
    return t.info(tail) if t else None


def session_for(task_id):
    """This task's session OBJECT - the live one if there is one, else the most recent that has
    not been reaped yet. Unlike for_task, an exited session counts: its scrollback is exactly
    what wrapping up needs to read."""
    mine = [x for x in SESSIONS.values() if x.task_id == task_id]
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


def live_sessions(tail=3):
    return [t.info(tail) for t in SESSIONS.values() if t.alive]


def close(sid):
    t = SESSIONS.pop(sid, None)
    if t: t.close()
    return bool(t)


KEEP_DEAD = 600     # an exited session stays listed this long so you can still read it


def reap():
    """Drop long-finished sessions nobody is watching (a fresh exit stays readable). The
    transcript was filed when the pty ended, so what is dropped here is only the bytes."""
    for sid in [s for s, t in SESSIONS.items()
                if not t.alive and not t.subs and time.time() - (t.ended or 0) > KEEP_DEAD]:
        SESSIONS.pop(sid, None)


def listing():
    reap()
    return [t.info() for t in SESSIONS.values()]
