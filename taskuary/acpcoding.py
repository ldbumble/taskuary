"""A CODING SESSION OVER ACP (step 2 of docs/acp-transport.md, the owner 2026-11-06: "see the ACP CLI in action").

A coding task on claude or codex, with the owner's 'Run CLI agents over ACP' on, runs as one ACP connection in the task's checkout instead
of the CLI's TUI in a pty: the adapter (clis.ADAPTERS) launched by the general road's own code (agents.acp_launch, agents._acp_open), with
the pane's argv carried over - Taskuary's MCP tools, the owner's send tools left out, the theme/hook settings - and the router's model
and effort set as session options. The seed the pane would have had typed in is the first session/prompt.

ONE REGISTRY ENTRY, THE PTY'S SHAPE. Everything that reads a coding session - the Board and the Wall (terminal.listing), peers and the
blackboard, the waiting room, landing, the hand raise, devphone's tell_agent, agent channels, the hooks - finds it in terminal.SESSIONS
with a Term's fields (sid, task_id, agent, cli, argv, cwd, alive, started, files(), info(), phase(), write(), close()...). What a pty
does with the screen, this does with typed updates:

  - every session/update goes to codingchat.record_update, so the coding chat draws it live (codingChat.stepsFromAcp);
  - a prompt is a session/prompt, queued while a turn runs and sent as one at its end (the general road's batching); Stop is session/cancel;
  - a permission is acpgate's: Taskuary's rules first, what they hold put to the owner as buttons (permissions.ask);
  - its "screen" (the Terminal toggle, a Wall cell) is the live output of its commands - Codex streams it, Claude's comes with the
    call's result - and the agent's own words between them; nothing to show is no toggle, never a blank terminal;
  - the files it touches (a call's locations, an edit's diff) are on its card and on the blackboard while it works.

An adapter that does not start puts today's pty in its place, said once (FELL_BACK). A turn that fails part-way is said, never retried."""
import os, re, threading, time, uuid
from collections import deque
from datetime import datetime
from loguru import logger

from . import acp as acp_mod, codingchat

FELL_BACK: set = set()            # the CLIs that did not start over ACP this process: said once in the log
SCROLLBACK = 200_000
HOT_S = 30                        # a file touched this recently is "under its hands" (touching)
_SHELL = re.compile(r'^(bash|powershell|pwsh|shell|execute|terminal|local_shell|exec_command|cmd)$', re.I)


def wanted(store, profile: dict, mode: str, task_id) -> bool:
    """Does this coding session run over ACP: a task's session, the owner's own (a stranger's runs on argv's floor), the switch on, and a
    CLI whose adapter we ship (claude, codex). A native-ACP CLI keeps its pty here until its coding road is checked; any other CLI has none."""
    from . import agents, clis
    if not str(task_id or '').isdigit() or mode != 'full' or not agents.acp_on(store): return False
    return bool(clis.acp_adapter(str(profile.get('cmd') or '')))


def carried(args) -> list:
    "The pane's own flags, as the ACP session takes them over (agents.acp_launch): the model and effort are session options instead."
    out, it = [], iter(map(str, args or []))
    for a in it:
        if a in ('--model', '-m', '--effort'): next(it, None); continue
        out.append(a)
    return out


def _rel(p: str, cwd: str) -> str:
    from .witness import _rel as rel
    return rel(p, cwd)


def _crlf(s: str) -> str: return re.sub(r'(?<!\r)\n', '\r\n', str(s or ''))


def _unfence(s: str) -> str:
    "Claude's adapter hands a command's output back as a fenced block: the terminal shows the output, not the markdown around it."
    m = re.fullmatch(r'\s*```[\w-]*\n(.*?)\n?```\s*', str(s or ''), re.S)
    return m.group(1) if m else str(s or '')


class ACPCoding:
    """One coding session on one ACP connection, registered in terminal.SESSIONS in a Term's shape (see the module's docstring)."""
    acp = True
    transport = 'acp'
    quick = False

    def __init__(self, store, profile: dict, argv: list, args: list, cwd: str, label: str, task_id: int, agent: str, cli: str, model: str = None,
                 resume: str = '', rows: int = 32, cols: int = 110, mode: str = 'full', fallback=None):
        from . import blackboard as bb, proof, witness
        self.sid, self.store, self.profile, self.model, self.mode = uuid.uuid4().hex[:12], store, dict(profile), model, mode
        self.args = [str(a) for a in args]
        self.argv, self.cwd, self.opened_in, self.label, self.task_id, self.agent, self.cli = list(argv), cwd, cwd, label, task_id, agent, cli
        self.rows, self.cols = rows, cols
        self.started, self.started_ts = datetime.now().isoformat(sep=' ', timespec='seconds'), time.time()
        self.buf, self.n, self.writes, self.ended, self.last, self.wrote_at, self.calm_until = deque(), 0, 0, None, time.time(), 0., 0
        self.seeded, self.accepted, self.seeding, self.draft, self.keyed_at, self.keep_transcript = '', None, True, '', 0., True
        self.subs, self.taps, self.geom_owner, self.failover, self.signed_out, self.relogin = [], [], None, None, False, False
        self.witness, self.ext_id, self.resumed_from, self.fallback = witness.Witness(), '', resume or '', fallback
        self.dirty0, self._files = bb.dirty(cwd), ([], 0.)
        try: proof.mark_start(store, task_id, cwd)
        except Exception as e: logger.debug(f'acp coding {self.sid}: no proof start - {e}')
        self.alive, self.busy, self.client, self.stop_reason = True, True, None, None     # busy from the start: opening is working
        self._q, self._qlock, self._wake = [], threading.Lock(), threading.Event()
        self.touched, self.calls, self.history, self.has_output, self._live_at = {}, {}, [], False, 0.
        self.held, self.steps, self.gate, self.turns = {}, None, None, 0

    # ── the terminal a Wall cell and the Terminal toggle show ──────────────────────────────────────────────────────────────
    def _out(self, s: str, output: bool = False):
        if not s: return
        self.buf.append(s); self.n += len(s); self.writes += 1; self.wrote_at = self.last = time.time()
        while self.n > SCROLLBACK and len(self.buf) > 1: self.n -= len(self.buf.popleft())
        if output: self.has_output = True
        for loop, q in list(self.subs):
            try: loop.call_soon_threadsafe(q.put_nowait, s)
            except RuntimeError: pass
        for f in list(self.taps):
            try: f(s)
            except Exception as e: logger.debug(f'acp coding tap failed: {e}')

    def subscribe(self, loop, q): self.subs.append((loop, q))
    def unsubscribe(self, q): self.subs = [(l, x) for l, x in self.subs if x is not q]
    def tap(self, fn): self.taps.append(fn)
    def untap(self, fn): self.taps = [f for f in self.taps if f is not fn]
    def scrollback(self): return ''.join(self.buf)
    def tail_chars(self, n): return self.scrollback()[-n:]
    def resize(self, rows, cols): self.rows, self.cols = int(rows), int(cols)
    def quiet_for(self, _secs: float): return None             # no TUI repaints on attach: nothing to mute
    def keyed(self, _s: str): return None                      # the box is the chat's: no half-typed line lives in a screen here

    def write(self, data):
        "Keys from a Terminal pane: a line typed there and Enter is the next prompt, as the chat's box sends it."
        line = getattr(self, '_line', '')
        for ch in str(data or ''):
            if ch in '\r\n':
                if line.strip(): self._out('\r\n'); self.prompt(line.strip())
                line = ''
            elif ch in '\x08\x7f':
                if line: line = line[:-1]; self._out('\b \b')
            elif ch == '\x03': self.cancel(); line = ''
            elif ch >= ' ': line += ch; self._out(ch)
        self._line = line

    # ── what the rest of Taskuary reads off a session ──────────────────────────────────────────────────────────────────────
    def idle(self) -> float: return round(time.time() - self.last, 1)
    def phase(self) -> str: return 'working' if self.alive and self.busy else 'parked'
    def waiting(self) -> bool: return self.alive and not self.busy
    def status_tail(self, n=8) -> list: return []              # no chooser can be drawn: a question comes as a typed request
    def tail(self, n=3) -> list:
        from .terminal import plain
        return [l for l in plain(self.scrollback()[-6000:]).splitlines() if l.strip()][-n:]
    def screen_lines(self, n: int = 32) -> list:
        "What a read-only snapshot shows (terminal.screen): the agent's last words, then what it is doing."
        lines = [l for kind, text in self.history[-12:] for l in str(text).splitlines() if kind != 'you' and l.strip()]
        return lines[-n:]
    def release_asks(self):
        from . import workerstate as ws
        ws.release(self.task_id)

    def files(self) -> list:
        """What THIS session changed: dirty now minus dirty at open (git, as a pty's), and every file a call of its edited - by the call's
        own word, so a peer sees it the moment it lands. Cached a few seconds: the Board polls."""
        got, at = self._files
        if time.time() - at < 4 or not self.alive: return got
        from . import blackboard as bb
        try: dirty = bb.dirty(self.cwd) - self.dirty0
        except Exception: dirty = set()
        edited = {_rel(p, self.cwd) for p, v in self.touched.items() if v.get('edit')}
        got = sorted(set(map(str, dirty)) | edited)[:20]
        self._files = (got, time.time())
        return got

    def touching(self) -> list:
        "The files under its hands NOW - 'path:line' where the call named one - from its calls' locations, newest first."
        now = time.time()
        rows = sorted(((p, v) for p, v in self.touched.items() if now - v['at'] < HOT_S), key=lambda x: -x[1]['at'])
        return [_rel(p, self.cwd) + (f":{v['l']}" if v.get('l') else '') for p, v in rows][:8]

    def info(self, tail=0, details=True):
        from . import terminal as term
        word = term.worker_fields(self.store, self)
        base = {'sid': self.sid, 'label': self.label, 'cwd': self.cwd, 'taskId': self.task_id, 'agent': self.agent, 'cli': self.cli,
                'mode': self.mode, 'transport': 'acp', 'alive': self.alive, 'busy': self.busy, 'started': self.started, 'idle': self.idle(),
                'phase': self.phase(), 'waiting': word['waiting'], 'request': word['request'], 'state': word.get('state'),
                'line': word.get('line'), 'questions': word.get('questions') or [], 'held': bool(word.get('held')), 'accepted': self.accepted,
                'promptPending': False, 'cmd': ' '.join(map(str, self.argv)), **({'tail': self.tail(tail)} if tail else {})}
        if not details: return base
        from . import browserview as bv
        files = self.files()
        return {**base, 'files': files, 'touching': self.touching(), 'browser': bv.state(self.sid),
                'work': self.witness.snapshot(files, self.cwd, (self.tail(1) or [''])[-1])}

    def transcript_text(self, chars: int = 12000) -> str:
        "What the session said, as readable text (terminal.harvest reads a pty's screen; this has the turns themselves)."
        who = {'you': 'You', 'brief': 'Taskuary', 'said': 'Agent', 'step': '-'}
        return '\n'.join(f'{who.get(k, k)}: {t}' if k != 'step' else f'  {t}' for k, t in self.history)[-chars:]

    # ── the connection ─────────────────────────────────────────────────────────────────────────────────────────────────────
    def start(self, seed: str = '', brief: bool = True):
        "Open the connection on its own thread - a start pays the adapter's few seconds there, not in the request that asked for it."
        if seed: self.prompt(seed, brief=brief)
        threading.Thread(target=self._run, daemon=True, name=f'acp-coding-{self.task_id}').start()

    def _launch(self) -> tuple:
        from . import agents, browserview as bv, terminal as term
        prof = {**self.profile, 'args': self.args, 'model': self.model or self.profile.get('model')}
        launch = agents.acp_launch(prof)
        env = {**agents.spawn_env(prof, {**term.session_env(self.agent or self.label, self.task_id, self.cwd, sid=self.sid), **bv.env(self.sid)}),
               **launch['env']}
        return prof, launch, env

    def _say(self, kind, name, detail=None):
        "acp_open's progress lines: on the task, where the owner reads what happened to the start."
        if kind == 'progress' and isinstance(detail, str) and detail: self.history.append(('step', detail)); self._out(f'\x1b[2m{_crlf(detail)}\x1b[0m\r\n')

    def _run(self):
        from . import agents
        name = str(self.profile.get('cmd') or self.cli)
        try:
            prof, launch, env = self._launch()
            self._out(f"\x1b[1;36m{self.cli} over ACP\x1b[0m \x1b[2m{launch['adapter'] or launch['cmd'][0]} - {self.cwd}\x1b[0m\r\n")
            self.client = agents._acp_open(name, launch, agents._long(self.cwd), env, self.resumed_from or None, None, self._say)
            if launch['adapter']: agents._acp_gears(self.client, prof, name, self._say)
        except Exception as e:
            return self._fell_back(e)
        from . import terminal as term
        term.bind_ext(self, self.client.session_id)
        self.client.on_update, self.client.permit = self._update, self._permit
        threading.Thread(target=self._watch, daemon=True).start()
        while self.alive:
            self._wake.wait(1.0); self._wake.clear()
            with self._qlock: items, self._q = self._q, []
            if items: self._turn(items)
            elif self.busy and self.client: self._idle(turn=False)      # reopened with nothing to say: back at its prompt

    def _fell_back(self, e):
        """The adapter did not get as far as a session: nothing ran, so today's pty takes its place - said once in the log per CLI and
        on the task. No pty to fall back to (the start failed for a reason it shares) ends this one, said."""
        from . import terminal as term
        self.alive, self.ended, self.busy = False, time.time(), False
        if self.client: self.client.close()
        term.SESSIONS.pop(self.sid, None)
        if self.cli not in FELL_BACK:
            FELL_BACK.add(self.cli); logger.warning(f'acp: {self.cli} coding session did not start over ACP ({e}) - running it in its terminal')
        if not self.fallback:
            self.store.add_comment(self.task_id, 'router', 'agent', f'{self.cli} did not start over ACP ({str(e)[:200]}).'); return self._emit_end()
        self.store.add_comment(self.task_id, 'router', 'agent', f'{self.cli} did not start over ACP ({str(e)[:200]}) - it runs in its terminal instead.')
        try: self.fallback()
        except Exception as x:
            logger.warning(f'acp coding {self.sid}: the terminal fallback did not start either - {x}')
            self.store.add_comment(self.task_id, 'router', 'agent', f'The terminal did not start either: {str(x)[:300]}')
            term.release_task(self.store, self.task_id, 'terminal')
        self._emit_end()

    def _watch(self):
        "The adapter ended by itself (it crashed, the CLI quit): the session ends as a pty's does when its process exits."
        try: self.client.p.wait()
        except Exception: pass
        if self.alive and not getattr(self, 'closing', False): self._gone()

    # ── turns ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def prompt(self, text: str, brief: bool = False, shown: list = None, done=None) -> bool:
        """The next prompt. While a turn runs it waits, and everything that waited goes in as ONE prompt when the turn ends (the general
        road's batching). `brief`: Taskuary's words (the seed, a relay), drawn as its brief; `shown`: the owner's own lines it carries,
        drawn as theirs. `done(ok)` hears whether the agent took it."""
        text = str(text or '').strip()
        if not text or not self.alive: return False
        with self._qlock: self._q.append((text, brief, list(shown or []), done))
        self._wake.set()
        return True

    def say(self, text: str, done=None):
        "terminal.type_into / tell for this session: a prompt, never keystrokes. `done(True)` once it is sent."
        return self.prompt(text, done=done)

    def _record(self, u: dict):
        codingchat.record_update(self.task_id, self.sid, u)

    def _turn(self, items: list):
        from . import agents, acpgate
        text = '\n\n'.join(t for t, *_ in items)
        for t, brief, shown, _d in items:
            for s in shown: self._record({'sessionUpdate': 'user_message_chunk', 'content': {'type': 'text', 'text': s}}); self.history.append(('you', s))
            self._record({'sessionUpdate': 'user_message_chunk', 'content': {'type': 'text', 'text': t},
                          **({'_meta': {'taskuary': 'brief'}} if brief or shown else {})})
            self.history.append(('brief' if brief or shown else 'you', t))
            self._out(f"\r\n\x1b[1;34m{'taskuary' if brief or shown else 'you'}>\x1b[0m {_crlf(t if len(t) < 400 else t[:400] + ' …')}\r\n")
        self.busy, self.seeding, self.accepted, self.stop_reason = True, False, True, None
        self.seeded = self.seeded or text
        self.witness.note({'k': 'turn'})
        self._event('UserPromptSubmit', prompt=text)
        self.steps = agents.ACPSteps(self._trace, self.cli, self.held)
        self.gate = acpgate.answerer({'store': self.store, 'task_id': self.task_id, 'cli': self.cli, 'cwd': self.cwd, 'sid': self.sid},
                                     self._trace, self.held)
        for *_x, d in items:
            if d:
                try: d(True)
                except Exception as e: logger.debug(f'acp coding: a done callback raised - {e}')
        stop, said, ok = None, '', False
        try: stop, said = self.client.prompt(text); ok = True
        except acp_mod.ACPAgentError as e:
            logger.warning(f'acp coding {self.sid}: the turn failed - {e}')
            self._say('progress', 'acp', f'The turn failed: {str(e)[:300]}')
        finally:
            try: self.steps.flush(stop if ok else 'error')
            except Exception as e: logger.debug(f'acp coding: steps not flushed - {e}')
        self.stop_reason, self.turns = stop, self.turns + 1
        if not self.client.alive(): return self._gone()
        self._idle(said)

    def _idle(self, said: str = '', turn: bool = True):
        "A turn ended: the agent waits on the owner, the Board hears it, and what waited in the waiting room goes in now."
        self.busy, self.seeding, self.last = False, False, time.time()
        if said: self.witness.note({'k': 'done', 'text': said})
        if turn: self._event('Stop', last_assistant_message=said)
        from . import handraise, waitroom, live
        try: live.emit('task-changed', task_id=self.task_id)
        except Exception: pass
        handraise.moved(self.task_id)
        waitroom.later(self.store, 0.3)

    def _event(self, ev: str, **p):
        """The turn's start and end as the worker record a hook would write (hooks._events): Codex's hooks do not run over ACP, and Claude's
        may not reach this session - one that did this turn (its notes are the witness's) has said it already."""
        from . import hooks
        if self.cli == 'claude' and self.witness.source == 'hook': return
        try: hooks._events(self, {'hook_event_name': ev, **p})
        except Exception as e: logger.debug(f'acp coding {self.sid}: worker event {ev} not written - {e}')

    def cancel(self) -> bool:
        "Stop: session/cancel - the turn ends, the conversation stays, and what is typed next carries on."
        if not (self.alive and self.busy and self.client): return False
        self.client.cancel(); return True

    # ── updates, steps, permissions ────────────────────────────────────────────────────────────────────────────────────────
    def _update(self, u: dict):
        self._record(u)
        kind = u.get('sessionUpdate')
        if kind in ('tool_call', 'tool_call_update'):
            iid = str(u.get('toolCallId') or '')
            c = self.calls.setdefault(iid, {'streamed': False, 'shown': False})
            edit = u.get('kind') == 'edit' or any(isinstance(b, dict) and b.get('type') == 'diff' for b in u.get('content') or [])
            if u.get('kind'): c['kind'] = u['kind']
            for l in u.get('locations') or []:
                if isinstance(l, dict) and l.get('path'):
                    v = self.touched.setdefault(str(l['path']), {})
                    v.update(at=time.time(), **({'l': l['line']} if l.get('line') else {}), **({'edit': True} if edit or c.get('kind') == 'edit' else {}))
            for b in u.get('content') or []:
                if isinstance(b, dict) and b.get('type') == 'diff' and b.get('path'):
                    self.touched.setdefault(str(b['path']), {}).update(at=time.time(), edit=True)
                    self.witness.note({'k': 'file', 'path': str(b['path']), **self._src()}); self._files = ([], 0.)
            if (d := ((u.get('_meta') or {}).get('terminal_output_delta') or {}).get('data')):
                if not c['shown']: self._show_cmd(c, (u.get('rawInput') or {}).get('command') or u.get('title') or '')
                c['streamed'] = True; self._out(_crlf(d), output=True)
        elif kind == 'plan':
            items = [{'text': str((e or {}).get('content') or ''), 'status': str((e or {}).get('status') or 'pending')} for e in u.get('entries') or []]
            self.witness.note({'k': 'todos', 'items': items, **self._src()})
        try: self.steps and self.steps(u)
        except Exception as e: logger.debug(f'acp coding: a step was not read - {e}')
        if time.time() - self._live_at >= 0.2:
            self._live_at = time.time()
            try:
                from . import live as live_bus
                live_bus.emit('run-tail', task_id=self.task_id)
            except Exception: pass

    def _src(self) -> dict: return {} if self.witness.source == 'hook' else {'source': 'acp'}

    def _show_cmd(self, c: dict, cmd):
        if isinstance(cmd, list): cmd = ' '.join(map(str, cmd))
        if cmd and not c['shown']: c['shown'] = True; self._out(f'\r\n\x1b[1;33m$\x1b[0m {_crlf(cmd)}\r\n', output=True)

    def _trace(self, kind, name, detail=None):
        "ACPSteps' settled steps: the witness (the Board card), the history (the transcript) and the terminal a Wall cell shows."
        d = detail if isinstance(detail, dict) else {}
        if kind == 'tool_call':
            args = d.get('args') or {}
            cmd = args.get('command') or args.get('cmd') or ''
            target = cmd or args.get('file_path') or args.get('path') or args.get('pattern') or args.get('query') or args.get('url') or ''
            self.witness.note({'k': 'tool', 'name': str(name), 'target': str(target if not isinstance(target, list) else ' '.join(map(str, target))), **self._src()})
            self.history.append(('step', f"{name} {str(target)[:200]}".strip()))
            c = self.calls.setdefault(str(d.get('tool_call_id') or ''), {'streamed': False, 'shown': False})
            if cmd and (_SHELL.match(str(name)) or c.get('kind') == 'execute'): self._show_cmd(c, cmd)
        elif kind == 'tool_result':
            c = self.calls.get(str(name)) or {}
            if c.get('shown') and not c.get('streamed') and (out := _unfence(d.get('result') or '').strip()):
                self._out(_crlf(out[-20000:]) + '\r\n', output=True)
        elif kind == 'progress' and name == 'text' and isinstance(detail, str) and detail.strip():
            self.history.append(('said', detail.strip())); self.witness.note({'k': 'say', 'text': detail.strip(), **self._src()})
            self._out(f'\r\n{_crlf(detail.strip())}\r\n')
        elif kind == 'permission': self.history.append(('step', f"{d.get('answer')}: {name} {d.get('why') or ''}".strip()))

    def _permit(self, params: dict):
        try: self.steps.asked(params.get('toolCall'))
        except Exception as e: logger.debug(f'acp coding: an asked step was not read - {e}')
        return self.gate(params)

    # ── ending ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
    def keep(self):
        "File the transcript on the task, as a pty does on exit and on close - the conversation itself is already kept (record_update)."
        if not (self.store and self.task_id and self.keep_transcript) or getattr(self, '_kept', False): return
        try: self.store.add_transcript(self.task_id, self.sid, self.transcript_text(), self.agent, self.cwd, self.ext_id, brain=self.cli); self._kept = True
        except Exception as e: logger.warning(f'could not file the transcript for {self.sid}: {e}')

    def _emit_end(self):
        for loop, q in list(self.subs):
            try: loop.call_soon_threadsafe(q.put_nowait, None)
            except RuntimeError: pass

    def close(self):
        self.closing = True
        self.keep()
        self.alive, self.ended, self.busy = False, time.time(), False
        self._wake.set()
        if self.client: self.client.close()
        self.release_asks()
        self._emit_end()

    def _gone(self):
        "Its process ended by itself: filed, and the task released as a pty's exit releases it (Term._pump's ending)."
        if not self.alive: return
        self.alive, self.ended, self.busy = False, time.time(), False
        self._wake.set()
        self.keep(); self.release_asks(); self._emit_end()
        from . import blackboard, browserview as bv, handraise, terminal as term, waitroom
        bv.close(self.sid, self.task_id)
        if self.store and self.task_id:
            if not getattr(self, 'on_purpose', False): term.release_task(self.store, self.task_id)
            blackboard.drain_later(self.store); waitroom.later(self.store)
        handraise.moved(self.task_id)
