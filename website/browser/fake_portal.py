"""A STAND-IN WEB PORTAL behind a sign-in, for a recorded walk (not a test: nothing here runs in CI). python fake_portal.py <port>
Payworth, an invented payroll portal: a sign-in (alex / northwind-pass), then a code step (424242), then a list of payroll runs over four pages
that the agent must page through, and a run's own page with its lines. Read-only: nothing here can be changed. All of it invented."""
import html, random, sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT, USER, PW, CODE = int(sys.argv[1]), 'alex', 'northwind-pass', '424242'
r = random.Random(11)
RUNS = [{'id': 1000 + i, 'date': f'2026-{(i // 4) % 12 + 1:02d}-{(i % 4) * 7 + 3:02d}', 'people': r.randint(38, 44),
         'gross': r.randint(180_000, 240_000), 'status': 'paid' if i < 30 else 'scheduled'} for i in range(32)]
SESS = {}                                       # cookie -> 'password' | 'ok'
PAGE = 8


def page(title, body, nav=''):
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)} - Payworth</title><style>body{{font:15px system-ui;margin:32px;color:#223}}'
            f'table{{border-collapse:collapse}}td,th{{border:1px solid #ccd;padding:4px 10px}}nav a{{margin-right:12px}}</style></head><body>'
            f'<h1>Payworth</h1><nav>{nav}</nav><h2>{html.escape(title)}</h2>{body}</body></html>').encode()


class H(BaseHTTPRequestHandler):
    def _who(self):
        c = self.headers.get('Cookie') or ''
        return next((v for k, v in (p.strip().split('=', 1) for p in c.split(';') if '=' in p) if k == 'pw'), '')
    def _send(self, code, body, extra=()):
        self.send_response(code); self.send_header('Content-Type', 'text/html; charset=utf-8')
        for k, v in extra: self.send_header(k, v)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def _go(self, where, extra=()): self._send(303, b'', [('Location', where), *extra])
    def do_GET(self):
        u, q = urlparse(self.path), parse_qs(urlparse(self.path).query)
        state = SESS.get(self._who())
        if u.path == '/login': return self._send(200, page('Sign in', '<form method="post" action="/login"><label>User <input name="user"></label><br><label>Password '
                                                           '<input name="password" type="password"></label><br><button>Sign in</button></form>'))
        if u.path == '/code': return self._send(200, page('Enter your code', '<p>We sent a 6-digit code to your phone.</p><form method="post" action="/code">'
                                                          '<label>Code <input name="code" inputmode="numeric"></label><button>Continue</button></form>'))
        if state != 'ok': return self._go('/login')
        nav = '<a href="/">Home</a><a href="/runs?page=1">Payroll runs</a><a href="/account">Account</a>'
        if u.path == '/': return self._send(200, page('Home', '<p>Signed in as Alex Doyle, Northwind.</p><p><a href="/runs?page=1">See your payroll runs</a></p>', nav))
        if u.path == '/account': return self._send(200, page('Account', '<p>Northwind - account reference NW-48213</p>', nav))
        if u.path == '/runs':
            n = max(1, int((q.get('page') or ['1'])[0])); last = (len(RUNS) + PAGE - 1) // PAGE
            rows = ''.join(f'<tr><td><a href="/runs/{x["id"]}">{x["id"]}</a></td><td>{x["date"]}</td><td>{x["people"]}</td><td>${x["gross"]:,}</td><td>{x["status"]}</td></tr>'
                           for x in RUNS[(n - 1) * PAGE:n * PAGE])
            pager = (f'<a href="/runs?page={n - 1}">Previous</a> ' if n > 1 else '') + f'Page {n} of {last}' + (f' <a href="/runs?page={n + 1}">Next</a>' if n < last else '')
            return self._send(200, page('Payroll runs', f'<table><tr><th>Run</th><th>Date</th><th>People</th><th>Gross</th><th>Status</th></tr>{rows}</table><p>{pager}</p>', nav))
        if u.path.startswith('/runs/'):
            x = next((x for x in RUNS if str(x['id']) == u.path.rsplit('/', 1)[1]), None)
            if not x: return self._send(404, page('Not found', '<p>No such run.</p>', nav))
            return self._send(200, page(f'Run {x["id"]}', f'<p>{x["date"]} - {x["people"]} people - gross ${x["gross"]:,} - taxes ${int(x["gross"] * .21):,} - {x["status"]}</p>', nav))
        return self._send(404, page('Not found', '<p>Nothing here.</p>', nav))
    def do_POST(self):
        f = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode()).items()}
        if self.path == '/login':
            if f.get('user') == USER and f.get('password') == PW:
                c = f'{r.random():.12f}'; SESS[c] = 'password'; return self._go('/code', [('Set-Cookie', f'pw={c}; Path=/')])
            return self._send(401, page('Sign in', '<p>That user and password do not match.</p><p><a href="/login">Try again</a></p>'))
        if self.path == '/code':
            if SESS.get(self._who()) == 'password' and f.get('code') == CODE: SESS[self._who()] = 'ok'; return self._go('/')
            return self._send(401, page('Enter your code', '<p>That code is not right.</p><p><a href="/code">Try again</a></p>'))
        return self._send(405, page('Not allowed', '<p>This portal is read-only.</p>'))
    def log_message(self, *a): pass


ThreadingHTTPServer(('127.0.0.1', PORT), H).serve_forever()
