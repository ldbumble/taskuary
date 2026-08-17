"""MCP connector for reports: call any MCP server's tool on a schedule and file the result
on the timeline. Config: {"cmd": "npx", "args": [...], "tool": "query", "tool_args": {...},
"env": {...}}. Minimal stdio JSON-RPC client (initialize -> initialized -> tools/call), no
SDK dependency - keeps the single-exe desktop build lean. Spec: modelcontextprotocol.io.
"""
import json, os, subprocess, threading, queue

PROTOCOL = '2025-06-18'


class MCPClient:
    """One short-lived stdio session with an MCP server."""

    def __init__(self, cmd, args=None, env=None, timeout=60):
        self.timeout, self._id = timeout, 0
        self.p = subprocess.Popen([cmd] + list(args or []), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
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


def _session(cfg):
    if not cfg.get('cmd'): raise ValueError('mcp connector needs "cmd" (the MCP server command)')
    return MCPClient(cfg['cmd'], cfg.get('args'), cfg.get('env'), int(cfg.get('timeout', 60))).start()


def list_tools(cfg) -> list:
    c = _session(cfg)
    try: return [{'name': t['name'], 'description': t.get('description', '')[:200]} for t in c.list_tools()]
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
