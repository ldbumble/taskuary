"""Drive an agent over the Agent Client Protocol: JSON-RPC, newline-delimited, on its stdio.

One protocol instead of a dialect per CLI. `clis.py` is that dialect today - claude takes `-p`,
codex takes `exec`, devin spells its approval bypass as a mode - and the session half is worse:
gemini and cursor hand out no id at all, so `sessionfiles` hashes a project root and reads the
vendor's own temp directory to learn what conversation just happened. `session/new` returns it.

The shape is `mcp.py`'s - spawn, a pump thread reading NDJSON, requests matched by id - with one
real difference. MCP as we use it is one-way: we ask, the server answers, and every inbound
message is a reply. ACP is BIDIRECTIONAL. Mid-turn the agent sends requests to US, and an
unanswered one is not an error, it is a hang - the same deadlock `clis.py` documents for a
headless run with no approval flag, one layer up. So the pump dispatches three kinds:

    id + result/error   our reply          -> hand to the waiting caller
    method, no id       a notification     -> session/update, streamed into the run trace
    method + id         the agent asking   -> MUST be answered, here, immediately

Answering happens on the pump thread on purpose: the caller is blocked in `request()` waiting for
the turn to end, so anything that routed the answer back through it would deadlock on itself.

Scope: every headless CLI run of the general agent, on a CLI that speaks ACP natively or through an
adapter (claude, codex: clis.ADAPTERS), and a coding session on claude or codex (acpcoding.py - the pty
stays its fallback). See docs/acp-transport.md.
"""
import json, os, queue, subprocess, threading, time
from loguru import logger

from . import spawn

VERSION = 1
# what we tell the agent we can do. Omitted means UNSUPPORTED per the spec, and `fs` is omitted on
# purpose: declaring it would route the agent's file reads through Taskuary, which is a different
# project. Under `-p` today it uses its own hands, and this keeps that true.
CLIENT_CAPS = {'fs': {'readTextFile': False, 'writeTextFile': False}, 'terminal': False}
# ONCE, never always: an allow_always ("don't ask again for commands that start with git") would stop the next call reaching us
ALLOW_KINDS, REJECT_KINDS = ('allow_once', 'allow_always'), ('reject_once', 'reject_always')


class ACPAgentError(RuntimeError):
    """The agent answered with an error, or died holding a turn."""


class ACPStartError(ACPAgentError):
    """The agent never got as far as a session: it did not start, or failed initialize. Nothing of the turn ran, so the
    caller may take another road (agents.run_cli falls back to the argv one)."""


def pick(options: list, allow: bool) -> dict:
    "The outcome for a permission request: the first option of the wanted kind, in ALLOW_KINDS/REJECT_KINDS order."
    kinds = ALLOW_KINDS if allow else REJECT_KINDS
    o = next((o for k in kinds for o in options or [] if o.get('kind') == k), None)
    return {'outcome': 'selected', 'optionId': o['optionId']} if o else {'outcome': 'cancelled'}


class ACPClient:
    """One connection to one agent process: one session, one task's. A kept conversation holds it between turns (clipool)."""

    def __init__(self, cmd, args=None, cwd=None, env=None, timeout=1200, on_update=None, permit=None):
        self.timeout, self.on_update, self.session_id, self.permit = timeout, on_update, None, permit
        # ...a reply goes to ITS caller by id: a steer (steer) waits beside the turn's own session/prompt, and one shared queue handed
        # each caller the other's reply to drop
        self._id, self._waiters, self._idlock, self._alive = 0, {}, threading.Lock(), True
        self._caps, self._meta, self._write_lock, self.options, self.last_turn = {}, {}, threading.Lock(), [], {}
        try:
            self.p = spawn.popen([cmd] + list(args or []), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                 stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                                 cwd=cwd, env=env, shell=False)
        except PermissionError: raise
        except OSError as e: raise ACPStartError(f'{cmd} did not start: {e}') from e
        self._err = []
        threading.Thread(target=self._pump, daemon=True).start()
        threading.Thread(target=lambda: self._err.append(self.p.stderr.read()), daemon=True).start()

    # ── wire ────────────────────────────────────────────────────────────────────────────────
    def _send(self, msg):
        with self._write_lock:
            self.p.stdin.write(json.dumps(msg) + '\n'); self.p.stdin.flush()

    def _pump(self):
        try:
            for line in self.p.stdout:
                line = line.strip()
                if not line: continue
                try: m = json.loads(line)
                except ValueError:
                    logger.debug(f'acp: not JSON, ignored: {line[:200]}'); continue
                method, mid = m.get('method'), m.get('id')
                if method is None:                                      # a reply to us - to whoever is still waiting on it
                    if (q := self._waiters.get(m.get('id'))): q.put(m)
                elif mid is None: self._notified(m)                     # a notification
                else: self._asked(m)                                    # a request TO us
        except Exception as e:
            logger.debug(f'acp: pump ended - {e}')
        finally:
            self._alive = False
            for q in list(self._waiters.values()): q.put(None)      # wake anyone waiting rather than let them hang

    def _notified(self, m):
        if m.get('method') != 'session/update' or not self.on_update: return
        try: self.on_update((m.get('params') or {}).get('update') or {})
        except Exception as e: logger.debug(f'acp: update handler raised - {e}')

    def _asked(self, m):
        """Answer the agent's own request. Silence here is a hang, so every branch replies."""
        method, mid = m.get('method'), m.get('id')
        if method == 'session/request_permission':
            self._send({'jsonrpc': '2.0', 'id': mid, 'result': {'outcome': self._permit(m.get('params') or {})}})
        else:
            # fs/* and anything else we never advertised. Refusing explicitly beats a hang, and
            # names the capability in the log rather than leaving a silent stall to diagnose.
            logger.debug(f'acp: refused {method} - not a capability we advertise')
            self._send({'jsonrpc': '2.0', 'id': mid,
                        'error': {'code': -32601, 'message': f'{method} is not supported by this client'}})

    def _permit(self, params):
        """The answer to one permission request. `permit` (acpgate.answerer: Taskuary's own rules) decides when it is set; a
        bare client allows once, which is what a headless argv run does with its bypass flag. A rule that raises refuses -
        an error is no yes."""
        if not self.permit: return pick(params.get('options'), True)
        try: return self.permit(params)
        except Exception as e:
            logger.warning(f'acp: the permission rule raised, so the call is refused - {e}')
            return pick(params.get('options'), False)

    def request(self, method, params=None, timeout=None, sent=None):
        with self._idlock: self._id += 1; mine = self._id; q = self._waiters[mine] = queue.Queue()
        try:
            if not self._alive: q.put(None)
            else:
                self._send({'jsonrpc': '2.0', 'id': mine, 'method': method, **({'params': params} if params else {})})
                if sent: sent()                           # ...once it is on its way: a cancel then is this request's (prompt)
            m = q.get(timeout=timeout or self.timeout)
            if m is None:
                err = ''.join(self._err).strip()[:300]
                # ...a turn it died holding is said as a chat CLI's that died mid-turn (clipool.MID_TURN): one sentence for one fact, whatever the agent
                from .clipool import MID_TURN
                # ...and nothing of the process after it, which the chat drew as "(the agent exited)" - that detail is the log's
                if method == 'session/prompt': logger.warning(f"acp: died mid-turn - {err or 'the agent exited'}"); raise ACPAgentError(MID_TURN)
                raise ACPAgentError(f'the agent stopped during {method}' + (f': {err}' if err else ''))
            if 'error' in m: raise ACPAgentError(f"{method}: {m['error'].get('message', m['error'])}")
            return m.get('result')
        finally: self._waiters.pop(mine, None)            # a reply to a request we gave up on is dropped by the pump

    # ── protocol ────────────────────────────────────────────────────────────────────────────
    def connect(self) -> dict:
        "initialize. Any failure here is a start failure (ACPStartError): no session exists yet, so nothing has run."
        try:
            r = self.request('initialize', {'protocolVersion': VERSION, 'clientCapabilities': CLIENT_CAPS,
                                            'clientInfo': {'name': 'taskuary', 'version': '1'}}, timeout=90) or {}
        except queue.Empty: raise ACPStartError(f'no answer to initialize in 90s{self._said()}')
        except ACPStartError: raise
        except ACPAgentError as e: raise ACPStartError(str(e)) from e
        self._caps, self._meta = r.get('agentCapabilities') or {}, r.get('_meta') or {}
        return self._caps

    def _said(self) -> str: return f': {"".join(self._err)[:300]}' if self._err else ''
    def can(self, capability) -> bool: return bool(self._caps.get(capability))
    def can_resume(self) -> bool: return 'resume' in (self._caps.get('sessionCapabilities') or {})
    def can_steer(self) -> bool: return bool(((self._meta or {}).get('steering') or {}).get('supported'))

    # MID-TURN INPUT (the steering extension both coding adapters advertise at initialize as _meta.steering.supported - claude-agent-acp
    # 0.101.0 and codex-acp 2.5.0, read from their code 2026-11-06): `_session/steering` puts words INTO the running turn instead of
    # queueing a session/prompt behind it. With idleBehavior promptRequired an idle session takes nothing and says so - the words stay ours
    # to send as the next session/prompt, never a turn the adapter starts on its own that nobody is waiting on.
    STEER = '_session/steering'
    def steer(self, text, timeout: float = 60) -> str:
        "'injected' when the words joined the running turn; else what the adapter said ('promptRequired': no turn runs; 'failed'), or ''."
        r = self.request(self.STEER, {'sessionId': self.session_id, 'prompt': [{'type': 'text', 'text': str(text or '')}],
                                      '_meta': {'steering': {'idleBehavior': 'promptRequired'}}}, timeout=timeout) or {}
        return str(r.get('outcome') or '')

    def _opened(self, r, session_id=None) -> str:
        r = r or {}
        self.session_id, self.options = r.get('sessionId') or session_id, r.get('configOptions') or self.options
        return self.session_id

    def new_session(self, cwd, mcp=None, meta=None) -> str:
        r = self.request('session/new', {'cwd': str(cwd or os.getcwd()), 'mcpServers': list(mcp or []),
                                         **({'_meta': meta} if meta else {})}, timeout=120)
        return self._opened(r)

    def load_session(self, session_id, cwd, mcp=None, meta=None) -> str:
        """Continue the agent's OWN conversation. session/resume where it is offered: the same conversation, nothing replayed.
        Else session/load, which replays the whole thread as session/update first - muted here, or every step of every earlier
        turn would be traced again as this turn's work."""
        p = {'sessionId': session_id, 'cwd': str(cwd or os.getcwd()), 'mcpServers': list(mcp or []), **({'_meta': meta} if meta else {})}
        if self.can_resume(): return self._opened(self.request('session/resume', p, timeout=120), session_id)
        outer, self.on_update = self.on_update, None
        try: return self._opened(self.request('session/load', p), session_id)
        finally: self.on_update = outer

    def option(self, want) -> dict:
        "A session config option by its id or its category ('model', 'thought_level', 'mode'); {} when the agent offers none."
        return next((o for o in self.options if want in (o.get('id'), o.get('category'))), {})

    def values(self, want) -> list:
        "The values option `want` offers - a select's options, flat or in the protocol's groups ({group, options})."
        return [x.get('value') for g in self.option(want).get('options') or [] if isinstance(g, dict)
                for x in (g.get('options') if isinstance(g.get('options'), list) else [g]) if isinstance(x, dict) and x.get('value')]

    def set_option(self, want, value) -> bool:
        """session/set_config_option. False, and nothing sent, when the agent has no such option or not that value - a model
        it does not list is said, never sent to fail the session. Both adapters list their models and efforts here."""
        o = self.option(want)
        if not o or value in (None, '') or (o.get('options') and value not in self.values(want)): return False
        if o.get('currentValue') == value: return True
        r = self.request('session/set_config_option', {'sessionId': self.session_id, 'configId': o['id'], 'value': value}, timeout=60)
        self.options = (r or {}).get('configOptions') or self.options
        return True

    def prompt(self, text, sent=None) -> tuple:
        """(stopReason, what the agent answered). Text is collected from the same agent_message_chunk updates that stream to the
        trace - one pass, two consumers.

        THE ANSWER IS WHAT IT SAID LAST, after its last tool call - what claude's `result` and codex's last agent_message are on the
        argv road. Its words before are steps in the trace (agents.ACPSteps); joined into the answer they read "I'll list the
        files... There are 3 files" as one reply. All of it when it said nothing after its last call."""
        said, cut, of = [], [0], [None]
        self.last_turn = {}
        outer = self.on_update
        def collect(u):
            kind = u.get('sessionUpdate')
            # a message resumed after a tool call is a new paragraph: copilot and devin both stream
            # "Hello!" / tool_call / "What would you like..." and the result read "Hello!What would you"
            if kind == 'agent_message_chunk':
                if said and said[-1] is None: said[-1] = chr(10); cut[0] = len(said)
                # ...and so is a new message said straight after another (the adapter names each chunk's message): they ran together
                elif said and u.get('messageId') != of[0]: said.append(chr(10) * 2)
                of[0] = u.get('messageId')
                said.append(_text_of(u.get('content')))
            elif kind in ('tool_call', 'tool_call_update', 'plan') and said and said[-1] is not None: said.append(None)
            if outer: outer(u)
        self.on_update = collect
        try:
            r = self.request('session/prompt', {'sessionId': self.session_id,
                                                'prompt': [{'type': 'text', 'text': str(text or '')}]}, sent=sent) or {}
        finally:
            self.on_update = outer
        self.last_turn = r              # ...the whole PromptResponse: its `usage` and _meta are what the turn used (aiusage.acp)
        last = ''.join(x for x in said[cut[0]:] if x).strip()
        return r.get('stopReason'), last or ''.join(x for x in said if x).strip()

    def cancel(self):
        if not (self._alive and self.session_id): return
        try: self._send({'jsonrpc': '2.0', 'method': 'session/cancel', 'params': {'sessionId': self.session_id}})
        except Exception as e: logger.debug(f'acp: could not cancel - {e}')

    def alive(self) -> bool: return self._alive and self.p.poll() is None

    def close(self):
        self._alive = False
        try:
            if self.p.poll() is not None: return
            # an adapter is node under npx under cmd.exe: kill() ends the cmd and leaves node driving the CLI on its own
            # ...and a tree-kill that could not run still ends the process we hold: skipped with it, the agent went on working a task
            # its owner had closed and filed its answer there
            if os.name == 'nt':
                try: spawn.run(['taskkill', '/PID', str(self.p.pid), '/T', '/F'], capture_output=True, timeout=15)
                except Exception as e: logger.debug(f'acp: the tree-kill did not run - {e}')
            if self.p.poll() is None: self.p.kill()
        except Exception: pass


class Conversation:
    """A connected session kept between turns - clipool's entry for the ACP road, in the shape its claude processes have (one turn at a
    time, an idle clock, the session id), so New chat, the idle reaper and shutdown close it like any other."""
    def __init__(self, client: ACPClient, sig: tuple):
        self.client, self.sig, self.lock, self.turns, self.used = client, sig, threading.Lock(), 0, time.time()
    @property
    def sid(self): return self.client.session_id
    def alive(self) -> bool: return self.client.alive()
    def close(self): self.client.close()


def _text_of(content) -> str:
    if isinstance(content, dict): return str(content.get('text') or '')
    if isinstance(content, list): return ''.join(_text_of(c) for c in content)
    return str(content or '')


def trace_line(u: dict) -> str:
    """One readable line for the Board, or '' for an update with nothing to show. Mirrors what
    agents._live_line does for claude's stream-json, so the run looks the same on either road."""
    kind = u.get('sessionUpdate')
    if kind == 'agent_message_chunk': return ' '.join(_text_of(u.get('content')).split())[:400]
    if kind in ('tool_call', 'tool_call_update'):
        title = u.get('title') or u.get('toolCallId') or 'tool'
        status = u.get('status') or ''
        return f'{title}{f" ({status})" if status else ""}'[:400]
    if kind == 'plan':
        entries = [str((e or {}).get('content') or '') for e in (u.get('entries') or [])]
        return ('plan: ' + '; '.join(x for x in entries if x))[:400] if entries else ''
    return ''
