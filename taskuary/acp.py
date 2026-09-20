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

Scope: the general agent's tool-using runs, on the CLIs that speak ACP natively. Coding sessions
keep the real CLI in a real pty - a developer wants the tool, not a rendering of it. See
docs/acp-transport.md.
"""
import json, os, queue, subprocess, threading
from loguru import logger

from . import spawn

VERSION = 1
# what we tell the agent we can do. Omitted means UNSUPPORTED per the spec, and `fs` is omitted on
# purpose: declaring it would route the agent's file reads through Taskuary, which is a different
# project. Under `-p` today it uses its own hands, and this keeps that true.
CLIENT_CAPS = {'fs': {'readTextFile': False, 'writeTextFile': False}, 'terminal': False}
ALLOW_KINDS = ('allow_always', 'allow_once')


class ACPAgentError(RuntimeError):
    """The agent answered with an error, or died holding a turn."""


class ACPClient:
    """One connection to one agent process. Not shared between runs: a session is a task's."""

    def __init__(self, cmd, args=None, cwd=None, env=None, timeout=1200, on_update=None):
        self.timeout, self.on_update, self.session_id = timeout, on_update, None
        self._id, self._replies, self._alive = 0, queue.Queue(), True
        self._caps, self._write_lock = {}, threading.Lock()
        self.p = spawn.popen([cmd] + list(args or []), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                             stderr=subprocess.PIPE, text=True, encoding='utf-8', errors='replace',
                             cwd=cwd, env=env, shell=False)
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
                if method is None: self._replies.put(m)                 # a reply to us
                elif mid is None: self._notified(m)                     # a notification
                else: self._asked(m)                                    # a request TO us
        except Exception as e:
            logger.debug(f'acp: pump ended - {e}')
        finally:
            self._alive = False
            self._replies.put(None)          # wake anyone waiting rather than let them hang

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
        """Auto-approve, which is what a headless run already does - every one of them carries
        --dangerously-skip-permissions, --yolo or --permission-mode dangerous, because there is
        nobody to click Approve. Surfacing this to the owner is the next version's job, and it is
        a change HERE rather than a new road."""
        opts = params.get('options') or []
        pick = next((o for o in opts if o.get('kind') in ALLOW_KINDS), None) or (opts[0] if opts else None)
        if not pick: return {'outcome': 'cancelled'}
        return {'outcome': 'selected', 'optionId': pick.get('optionId')}

    def request(self, method, params=None, timeout=None):
        self._id += 1
        mine = self._id
        self._send({'jsonrpc': '2.0', 'id': mine, 'method': method, **({'params': params} if params else {})})
        while True:
            m = self._replies.get(timeout=timeout or self.timeout)
            if m is None:
                raise ACPAgentError(f'the agent stopped during {method}' + (f': {"".join(self._err)[:300]}' if self._err else ''))
            if m.get('id') != mine: continue              # a reply to a request we gave up on
            if 'error' in m: raise ACPAgentError(f"{method}: {m['error'].get('message', m['error'])}")
            return m.get('result')

    # ── protocol ────────────────────────────────────────────────────────────────────────────
    def connect(self) -> dict:
        r = self.request('initialize', {'protocolVersion': VERSION, 'clientCapabilities': CLIENT_CAPS,
                                        'clientInfo': {'name': 'taskuary', 'version': '1'}}, timeout=60) or {}
        self._caps = r.get('agentCapabilities') or {}
        return self._caps

    def can(self, capability) -> bool: return bool(self._caps.get(capability))

    def new_session(self, cwd) -> str:
        r = self.request('session/new', {'cwd': str(cwd or os.getcwd()), 'mcpServers': []}, timeout=120) or {}
        self.session_id = r.get('sessionId')
        return self.session_id

    def load_session(self, session_id, cwd) -> str:
        """Continue the agent's OWN conversation. It replays the thread as session/update first,
        which is why this can take as long as a turn."""
        self.request('session/load', {'sessionId': session_id, 'cwd': str(cwd or os.getcwd()), 'mcpServers': []})
        self.session_id = session_id
        return session_id

    def prompt(self, text) -> tuple:
        """(stopReason, everything the agent said). Text is collected from the same
        agent_message_chunk updates that stream to the trace - one pass, two consumers."""
        said = []
        outer = self.on_update
        def collect(u):
            kind = u.get('sessionUpdate')
            # a message resumed after a tool call is a new paragraph: copilot and devin both stream
            # "Hello!" / tool_call / "What would you like..." and the result read "Hello!What would you"
            if kind == 'agent_message_chunk':
                if said and said[-1] is None: said[-1] = chr(10)
                said.append(_text_of(u.get('content')))
            elif kind in ('tool_call', 'tool_call_update', 'plan') and said and said[-1] is not None: said.append(None)
            if outer: outer(u)
        self.on_update = collect
        try:
            r = self.request('session/prompt', {'sessionId': self.session_id,
                                                'prompt': [{'type': 'text', 'text': str(text or '')}]}) or {}
        finally:
            self.on_update = outer
        return r.get('stopReason'), ''.join(x for x in said if x).strip()

    def cancel(self):
        if not (self._alive and self.session_id): return
        try: self._send({'jsonrpc': '2.0', 'method': 'session/cancel', 'params': {'sessionId': self.session_id}})
        except Exception as e: logger.debug(f'acp: could not cancel - {e}')

    def close(self):
        self._alive = False
        try:
            if self.p.poll() is None: self.p.kill()
        except Exception: pass


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
