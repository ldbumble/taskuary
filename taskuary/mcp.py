"""MCP connector for reports: call any MCP server's tool on a schedule and file the result
on the timeline. Config: {"cmd": "npx", "args": [...], "tool": "query", "tool_args": {...},
"env": {...}}. Minimal stdio JSON-RPC client (initialize -> initialized -> tools/call), no
SDK dependency - keeps the single-exe desktop build lean. Spec: modelcontextprotocol.io.
"""
import json, os, subprocess, threading, queue
from . import spawn

PROTOCOL = '2025-06-18'


class MCPClient:
    """One short-lived stdio session with an MCP server."""

    def __init__(self, cmd, args=None, env=None, timeout=60):
        self.timeout, self._id = timeout, 0
        self.p = spawn.popen([cmd] + list(args or []), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                  stderr=subprocess.DEVNULL, text=True, encoding='utf-8',
                                  env={**os.environ, **(env or {})}, shell=False)
        self.q = queue.Queue()
        threading.Thread(target=self._pump, daemon=True).start()

    def _pump(self):
        for line in self.p.stdout:
            line = line.strip()
            if line:
                try: self.q.put(json.loads(line))
                except ValueError: pass

    def _send(self, msg):
        self.p.stdin.write(json.dumps(msg) + '\n'); self.p.stdin.flush()

    def request(self, method, params=None):
        self._id += 1
        self._send({'jsonrpc': '2.0', 'id': self._id, 'method': method, **({'params': params} if params else {})})
        while True:
            m = self.q.get(timeout=self.timeout)
            if m.get('id') == self._id:
                if 'error' in m: raise RuntimeError(f"{method}: {m['error'].get('message', m['error'])}")
                return m.get('result', {})

    def start(self):
        self.request('initialize', {'protocolVersion': PROTOCOL, 'capabilities': {},
                                    'clientInfo': {'name': 'taskuary', 'version': '0.1'}})
        self._send({'jsonrpc': '2.0', 'method': 'notifications/initialized'})
        return self

    def list_tools(self): return self.request('tools/list').get('tools', [])
    def call_tool(self, name, args=None): return self.request('tools/call', {'name': name, 'arguments': args or {}})

    def close(self):
        try: self.p.stdin.close(); self.p.terminate()
        except Exception: pass


class HTTPMCPClient:
    """One session with a REMOTE MCP server over Streamable HTTP.

    The hosted servers (Robinhood's agent.robinhood.com/mcp/trading is the first one we speak
    to) are not programs we can spawn - there is no `cmd`. Same JSON-RPC, different pipe: POST
    the request, and the reply comes back either as one JSON object or as an SSE stream that
    has to be read until the frame carrying our id arrives. Both shapes are legal in the spec
    and servers choose per response, so both are handled here rather than guessed at.

    Auth is a bearer token, which is where an OAuth access token lands once the owner has one.
    """

    def __init__(self, url, token=None, headers=None, timeout=60):
        self.url, self.timeout, self._id, self.session = url, timeout, 0, None
        self.h = {'Content-Type': 'application/json',
                  # both, on purpose: the server picks the shape and we must accept either
                  'Accept': 'application/json, text/event-stream', **(headers or {})}
        if token: self.h['Authorization'] = f'Bearer {token}'

    def _post(self, msg, want_reply=True):
        import requests
        h = dict(self.h)
        if self.session: h['Mcp-Session-Id'] = self.session
        r = requests.post(self.url, headers=h, json=msg, timeout=self.timeout,
                          stream=True if want_reply else False)
        # the id the server assigns on initialize identifies every later call in this session
        self.session = r.headers.get('mcp-session-id') or r.headers.get('Mcp-Session-Id') or self.session
        if r.status_code == 401:
            raise RuntimeError('the MCP server rejected the token (401) - sign in again and paste a fresh one')
        if r.status_code >= 400:
            raise RuntimeError(f'MCP HTTP {r.status_code}: {(r.text or "")[:300]}')
        if not want_reply: return None
        if 'text/event-stream' in (r.headers.get('content-type') or ''):
            for line in r.iter_lines(decode_unicode=True):
                if not line or not line.startswith('data:'): continue
                try: m = json.loads(line[5:].strip())
                except ValueError: continue
                if m.get('id') == msg.get('id'): return m
            raise RuntimeError('the MCP stream ended before answering')
        return r.json()

    def request(self, method, params=None):
        self._id += 1
        m = self._post({'jsonrpc': '2.0', 'id': self._id, 'method': method, **({'params': params} if params else {})})
        if 'error' in (m or {}): raise RuntimeError(f"{method}: {m['error'].get('message', m['error'])}")
        return (m or {}).get('result', {})

    def start(self):
        self.request('initialize', {'protocolVersion': PROTOCOL, 'capabilities': {},
                                    'clientInfo': {'name': 'taskuary', 'version': '0.1'}})
        self._post({'jsonrpc': '2.0', 'method': 'notifications/initialized'}, want_reply=False)
        return self

    def list_tools(self): return self.request('tools/list').get('tools', [])
    def call_tool(self, name, args=None): return self.request('tools/call', {'name': name, 'arguments': args or {}})
    def close(self): pass                       # nothing to reap: no child process


def _session(cfg):
    """stdio when the config names a command, HTTP when it names a url. A card may carry both
    (a `cmd` bridge in front of a remote server); the url wins, since it needs no local install."""
    if cfg.get('url'):
        return HTTPMCPClient(cfg['url'], cfg.get('token'), cfg.get('headers'), int(cfg.get('timeout', 60))).start()
    if not cfg.get('cmd'): raise ValueError('mcp connector needs "cmd" (a local server) or "url" (a hosted one)')
    return MCPClient(cfg['cmd'], cfg.get('args'), cfg.get('env'), int(cfg.get('timeout', 60))).start()


def read_only(tool: dict) -> bool:
    """Does the SERVER declare this tool harmless? `readOnlyHint` is the MCP spec's own answer,
    which beats us pattern-matching names we have never seen. FAIL CLOSED: a tool that says
    nothing about itself is treated as a write, so an unannotated `place_order` can never slip
    through a read-scoped call."""
    return bool((tool.get('annotations') or {}).get('readOnlyHint') is True)


def list_tools(cfg) -> list:
    c = _session(cfg)
    try:
        return [{'name': t['name'], 'description': (t.get('description') or '')[:200],
                 'read_only': read_only(t), 'schema': t.get('inputSchema') or {}}
                for t in c.list_tools()]
    finally: c.close()


def run_report(cfg):
    """Report executor: call cfg['tool'] and return (headline, text content)."""
    c = _session(cfg)
    try:
        args = cfg.get('tool_args') or {}
        if isinstance(args, str): args = json.loads(args or '{}')
        res = c.call_tool(cfg['tool'], args)
        if res.get('isError'): raise RuntimeError(str(res.get('content'))[:500])
        texts = [b.get('text', '') for b in res.get('content', []) if b.get('type') == 'text']
        body = '\n'.join(t for t in texts if t) or json.dumps(res, default=str)
        return f"{cfg['tool']} ok", body[:4000]
    finally:
        c.close()
