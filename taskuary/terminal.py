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


def agent_argv(profile: dict, model: str = None) -> list:
    """Interactive invocation of a configured CLI: its command WITHOUT the headless flags
    (-p / --output-format json turn it into a one-shot pipe). `interactive_args` in the
    profile overrides, for CLIs that need a subcommand to open their TUI, and the model flag
    is the same one the headless runner uses (`model_arg`, e.g. codex wants -m)."""
    from .agents import _resolve_cmd
    argv = _resolve_cmd(profile.get('cmd') or 'claude') + list(profile.get('interactive_args') or [])
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


# ── wrapping up: "we're done" -> the agent's own closing summary ────────────────────
WRAP_MARKER = '===TASKUARY WRAP==='
WRAP_PROMPT = ("The owner is closing this Taskuary task. Stop working and write your wrap-up now, nothing "
               "else: first a line containing only " + WRAP_MARKER + " then 5-15 plain-text lines - what you "
               "determined, what you actually changed, and anything left for next time. No questions, no code "
               "blocks, no further tool calls.")
WRAP_WAIT, WRAP_QUIET = 420, 5      # seconds: give a thinking agent room, then take the answer

_ANSI = re.compile(r'\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b\][^\x07\x1b]*(?:\x07|\x1b\\)|\x1b[()][0-9A-B]|\x1b[=>]'
                   r'|[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]')

def plain(s: str) -> str:
    """A TUI's bytes as readable text: escape sequences gone, box gutters trimmed."""
    s = _ANSI.sub('', s or '').replace('\r\n', '\n').replace('\r', '\n')
    return '\n'.join(l.strip(' │┃┊▎|').rstrip() for l in s.split('\n'))


def wrap_up(t: Term, on_done, prompt: str = WRAP_PROMPT, timeout: int = WRAP_WAIT):
    """Ask a LIVE session for its closing summary and hand the text back. A pty is all we
    have here - no session id to resume, and no JSON contract that survives a TUI wrapping
    long lines - so we ask for a marker line and take the plain text after the last one.
    The marker also appears in the echo of our own prompt, which is exactly the fallback we
    want: a CLI that ignores the instruction still gives us everything it said afterwards."""
    got = []
    sink = got.append                     # one identity, so untap can find it again
    t.tap(sink)
    def go():
        try:
            t.write(prompt.replace('\n', ' ') + '\r')
            t0, last, quiet = time.time(), 0, 0
            while t.alive and time.time() - t0 < timeout:
                time.sleep(.5)
                n = sum(len(x) for x in got)
                quiet, last = (quiet + .5, last) if n == last else (0, n)
                if quiet >= WRAP_QUIET and WRAP_MARKER in plain(''.join(got)): break
            txt = plain(''.join(got))
            on_done(txt.rsplit(WRAP_MARKER, 1)[-1].strip()[:8000])
        finally:
            t.untap(sink)
    threading.Thread(target=go, daemon=True).start()


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
