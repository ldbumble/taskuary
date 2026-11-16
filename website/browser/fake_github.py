"""A STAND-IN GITHUB for a recorded walk (not a test: nothing here runs in CI). python fake_github.py <port> <log file>
One invented repository, northwind/ledger, with 40 open issues - stale questions, duplicates, things already fixed, and live bugs. A close or a
comment is a line in the log and changes the issue; nothing here reaches github.com. Point Taskuary at it with TASKUARY_GITHUB_API."""
import json, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT, LOG = int(sys.argv[1]), sys.argv[2]
KINDS = [('Question: how do I export totals to CSV?', 'question', '2022-03-04', 0),
         ('Duplicate of #3 - totals off by tax', 'duplicate', '2022-07-11', 1),
         ('Fixed in v2.1? Rounding on invoices', 'bug', '2023-01-09', 2),
         ('Ledger crashes on an empty month', 'bug', '2026-11-10', 5),
         ('Feature idea: dark mode for reports', 'enhancement', '2021-12-01', 0)]
ISSUES = {n: {'number': n, 'title': f'{KINDS[n % 5][0]} ({n})', 'labels': [{'name': KINDS[n % 5][1]}], 'updated_at': f'{KINDS[n % 5][2]}T10:00:00Z',
              'comments': KINDS[n % 5][3], 'state': 'open', 'user': {'login': f'user{n % 7}'}, 'html_url': f'https://github.example/northwind/ledger/issues/{n}',
              'body': 'Invented issue for a walk.'} for n in range(1, 41)}


class H(BaseHTTPRequestHandler):
    def _send(self, code, obj):
        b = json.dumps(obj).encode(); self.send_response(code); self.send_header('Content-Type', 'application/json'); self.send_header('Content-Length', str(len(b)))
        self.end_headers(); self.wfile.write(b)
    def _log(self, what):
        with open(LOG, 'a', encoding='utf-8') as f: f.write(json.dumps(what) + '\n')
    def do_GET(self):
        path = self.path.split('?')[0]
        if path == '/repos/northwind/ledger/issues':
            page = int((dict(p.split('=') for p in self.path.split('?')[1].split('&')) if '?' in self.path else {}).get('page', 1))
            return self._send(200, [i for i in ISSUES.values() if i['state'] == 'open'] if page == 1 else [])
        if path == '/repos/northwind/ledger': return self._send(200, {'full_name': 'northwind/ledger', 'default_branch': 'main', 'permissions': {'push': True}})
        if path == '/user': return self._send(200, {'login': 'alexdoyle'})
        return self._send(200, [])
    def do_PATCH(self):
        n = int(self.path.rstrip('/').split('/')[-1]); body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
        self._log({'close': n, **body})
        if n % 13 == 0: return self._send(410, {'message': 'This issue was deleted'})          # ...a few refuse, as GitHub does
        ISSUES[n]['state'] = body.get('state', 'open'); return self._send(200, ISSUES[n])
    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}'); self._log({'post': self.path, **body})
        return self._send(201, {'html_url': 'https://github.example/c/1'})
    def log_message(self, *a): pass


ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
