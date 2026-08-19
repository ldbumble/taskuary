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
SEED_WAIT, SEED_QUIET = 25, 1.4     # seconds: how long to wait for a TUI, and what 'settled' means


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
    def read(self):
        try: return os.read(self.fd, 65536).decode('utf-8', 'replace')
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

    def __init__(self, argv, cwd, label, task_id=None, agent=None, rows=32, cols=110):
        self.sid = uuid.uuid4().hex[:12]
        self.argv, self.cwd, self.label, self.task_id, self.agent = argv, cwd, label, task_id, agent
        self.started = datetime.now().isoformat(sep=' ', timespec='seconds')
        self.buf, self.n, self.ended, self.last = deque(), 0, None, time.time()
        self.subs = []                                    # (loop, asyncio.Queue)
        self.taps = []                                    # plain callables, for server-side readers
        self.pty = (_WinPty if os.name == 'nt' else _UnixPty)(argv, cwd, rows, cols)
        self.alive = True
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
        self._emit(None)

    def seed(self, text: str):
        """Type the first prompt in for the user - but only once the CLI is actually ready
        for it. Agent TUIs take a few seconds to boot and redraw, and anything typed while
        they are still painting is swallowed, so wait for output to start and then go quiet
        (that gap IS 'ready'), rather than guessing a delay."""
        def go():
            start = time.time()
            while self.alive and not self.n and time.time() - start < SEED_WAIT: time.sleep(.1)
            quiet, last = 0, self.n
            while self.alive and quiet < SEED_QUIET and time.time() - start < SEED_WAIT:
                time.sleep(.2)
                quiet, last = (quiet + .2, last) if self.n == last else (0, self.n)
            if self.alive: self.write(text.replace('\n', ' ') + '\r')
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
            try: self.pty.resize(int(rows), int(cols))
            except Exception: pass
    def close(self):
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

def interactive_args(args) -> list:
    out, skip = [], False
    for a in (args or []):
        if skip: skip = False; continue
        if a in PIPE_FLAGS: continue
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
    if not cwd and repo: cwd = (profile.get('cwd_map') or {}).get(repo)
    cwd = cwd or profile.get('cwd') or os.getcwd()
    if not os.path.isdir(cwd): raise ValueError(f'working directory does not exist: {cwd}')
    t = Term(argv, cwd, label, task_id, agent, rows, cols)
    SESSIONS[t.sid] = t
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
    into "112active" in the first wrap-ups."""
    s = (s or '').replace('\r\n', '\n')
    s = _FORWARD.sub(lambda m: ' ' * max(1, int(m.group(1) or 1)), s)
    lines = [_overlay(l) for l in s.split('\n')]
    return '\n'.join(_ANSI.sub('', l).strip(' │┃┊▎|').rstrip() for l in lines)


# What a TUI paints over and over and none of it is what the agent SAID: spinner frames, the
# hint bar, the token counter, rules, the statusline tip. It all landed in the wrap-up - and in
# the transcript we hand the AI to write from.
_CHROME = re.compile(r'esc to interrupt|\? for shortcuts|for agents|to manage|\bTip:\s|^\s*\d[\d,]*\s+tokens?\b|\(\d+s\)\s*$|\b\d[\d,]*\s+tokens\)\s*$|still r?unning\s*$', re.I)
_WORDLESS = re.compile(r'^[^A-Za-z]*$')
_HINT = re.compile(r'\bTip:\s+Use /')      # a slash-command hint, any length
_SPIN = re.compile('[·✢✳✻✽✶✷✸✹✺⏺◐◓◑◒✦❯›]')       # the frames themselves


def declutter(text: str) -> str:
    """Keep the lines that carry words. Chrome only matches short lines, so a sentence that
    happens to say "esc to interrupt" survives."""
    out = []
    for l in (text or '').splitlines():
        l = l.rstrip()
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


def harvest(t: Term, chars: int = 12000) -> str:
    """What the session actually said, as readable text. Closing a task used to TYPE a request
    for a summary into the pty and wait: another prompt to read, minutes of waiting, and one
    more chance for an agent you just told to stop to go and do more work. Everything needed
    is already on screen - take it and let the main AI write the report."""
    return declutter(plain(t.scrollback()[-chars * 4:]))[-chars:]


def seed_text(store, tid: int, instruction: str = None) -> str:
    """What gets typed into a fresh session: the ask, the owner's own prompt, and the message
    that started it. One line - a newline submits in a TUI."""
    from .store import task_ref
    t = store.get_task(tid) or {}
    msgs = [m for m in store.list_messages(tid) if m.get('Status') != 'context']
    m = msgs[-1] if msgs else None
    parts = [f"Work Taskuary task {task_ref(tid)} - {t.get('Title') or ''}."]
    if instruction and instruction.strip(): parts.append(instruction.strip())
    if m: parts.append(f"It came in on {m.get('Channel')} from {m.get('FromName') or m.get('FromEmail')}: "
                       f"{(m.get('BodyText') or '')[:3000]}")
    elif t.get('Summary'): parts.append(str(t['Summary'])[:3000])
    # a paused session left a handover note: carry it in, or the next agent redoes the digging
    from .coder import PAUSE_MARKER
    note = next((c['Body'] for c in reversed(store.list_comments(tid))
                 if str(c.get('Body') or '').startswith(PAUSE_MARKER)), None)
    if note: parts.append(f"An earlier session on this task was paused and left this handover - "
                          f"continue from it, do not start over: {note[:3000]}")
    return ' '.join(' '.join(parts).split())


def start_on_task(store, tid: int, agent: str = 'coder', model: str = None, instruction: str = None,
                  actor: str = 'owner') -> dict:
    """Put a CLI on a task, in a REAL terminal - the only way an agent starts work here. An
    agent you cannot watch, interrupt or answer is the thing this app exists to replace."""
    import re
    live = for_task(tid)
    if live: return {**live, 'existing': True}
    t = store.get_task(tid)
    if not t: raise ValueError(f'no task {tid}')
    if not store.get_agent(agent or ''): raise ValueError(f'unknown agent: {agent}')
    repo = (re.search(r'repo:([^\s,]+)', str(t.get('Tags') or '')) or [None, None])[1]
    term = open_session(store, agent, tid, repo, None, 32, 110, actor, model)
    term.seed(seed_text(store, tid, instruction))
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


def live_sessions(tail=3):
    return [t.info(tail) for t in SESSIONS.values() if t.alive]


def close(sid):
    t = SESSIONS.pop(sid, None)
    if t: t.close()
    return bool(t)


KEEP_DEAD = 600     # an exited session stays listed this long so you can still read it


def reap():
    """Drop long-finished sessions nobody is watching (a fresh exit stays readable)."""
    for sid in [s for s, t in SESSIONS.items()
                if not t.alive and not t.subs and time.time() - (t.ended or 0) > KEEP_DEAD]:
        SESSIONS.pop(sid, None)


def listing():
    reap()
    return [t.info() for t in SESSIONS.values()]
