"""TEN STAND-IN SITES THAT TAKE A SIGN-UP, for a recorded walk (not a test: nothing here runs in CI). python fake_signup.py <port> [inbox.jsonl]
Each invented data vendor lives under /s/<slug>/: a home page, a sign-up, and - signed in - a data page with a table the agent is asked to
collect. They differ the ways real sign-ups do: a plain form, a password rule, a plan to choose, a two-step wizard, a sum to prove a person,
a code sent by email, a phone number only the owner has, a card payment for the data. All of it invented; nothing leaves loopback.
A code "sent by email" is written as a line to <inbox.jsonl> (the walk turns it into a mail in the owner's inbox), and to /s/<slug>/sent."""
import html, json, random, sys, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

PORT, INBOX = int(sys.argv[1]), (sys.argv[2] if len(sys.argv) > 2 else '')
r = random.Random(5)
CITIES = ['Harbor City', 'Millbrook', 'Oak Ridge', 'Lakeview', 'Riverside', 'Fairhaven']
# slug, name, what its data is, the extra step its sign-up asks
SITES = [('rentscope', 'RentScope', 'asking rent per sq ft', ''), ('vacancyiq', 'VacancyIQ', 'office vacancy %', 'password'),
         ('parcelpulse', 'ParcelPulse', 'tax-delinquent parcels', 'plan'), ('capratehub', 'CapRateHub', 'average cap rate %', 'wizard'),
         ('permitwatch', 'PermitWatch', 'building permits filed', 'sum'), ('lienlens', 'LienLens', 'new liens filed', 'emailcode'),
         ('footfall', 'Footfall', 'weekly foot traffic (k)', ''), ('zoningnow', 'ZoningNow', 'rezoning applications', 'phone'),
         ('dealflowpro', 'DealFlow Pro', 'off-market listings', 'payment'), ('tenantpulse', 'TenantPulse', 'lease renewals %', '')]
HOST = {s: f'127.0.0.{i + 2}' for i, (s, *_) in enumerate(SITES)}     # each vendor its own site, as real vendors are
DATA = {s: [(c, round(r.uniform(5, 95), 1)) for c in CITIES] for s, *_ in SITES}
USERS, SESS, CODES = {}, {}, {}     # (slug, email) -> {..}; cookie -> (slug, email); (slug, email) -> code


def page(site, title, body):
    name = next((n for s, n, *_ in SITES if s == site), 'Sites')
    return (f'<!doctype html><html><head><meta charset="utf-8"><title>{html.escape(title)} - {html.escape(name)}</title><style>body{{font:15px system-ui;margin:32px;'
            f'color:#223}}table{{border-collapse:collapse}}td,th{{border:1px solid #ccd;padding:4px 10px}}label{{display:block;margin:6px 0}}.err{{color:#b00}}</style></head>'
            f'<body><h1>{html.escape(name)}</h1><h2>{html.escape(title)}</h2>{body}</body></html>').encode()


def form(site, action, fields, button='Create account', err=''):
    rows = ''.join(f'<label>{html.escape(l)} <input name="{n}" type="{t}"></label>' if t != 'checkbox' else f'<label><input name="{n}" type="checkbox" value="yes"> {html.escape(l)}</label>'
                   for l, n, t in fields)
    return (f'<p class="err">{html.escape(err)}</p>' if err else '') + f'<form method="post" action="/s/{site}/{action}">{rows}<button>{button}</button></form>'


BASE = [('Full name', 'name', 'text'), ('Work email', 'email', 'email'), ('Password', 'password', 'password'), ('I agree to the terms of use', 'terms', 'checkbox')]


class H(BaseHTTPRequestHandler):
    def _who(self):
        c = self.headers.get('Cookie') or ''
        return SESS.get(next((v for k, v in (p.strip().split('=', 1) for p in c.split(';') if '=' in p) if k == 'sid'), ''))
    def _send(self, code, body, extra=()):
        self.send_response(code); self.send_header('Content-Type', 'text/html; charset=utf-8')
        for k, v in extra: self.send_header(k, v)
        self.send_header('Content-Length', str(len(body))); self.end_headers(); self.wfile.write(body)
    def _go(self, where, extra=()): self._send(303, b'', [('Location', where), *extra])
    def _in(self, site, email):
        c = f'{r.random():.12f}'; SESS[c] = (site, email); return [('Set-Cookie', f'sid={c}; Path=/s/{site}')]

    def do_GET(self):
        u = urlparse(self.path); parts = [p for p in u.path.split('/') if p]
        if not parts or parts[0] != 's':
            return self._send(200, page('', 'Data vendors', '<ul>' + ''.join(f'<li><a href="http://{HOST[s]}:{PORT}/s/{s}/">{n}</a> - {d}</li>' for s, n, d, _ in SITES) + '</ul>'))
        site = parts[1] if len(parts) > 1 else ''
        meta = next((x for x in SITES if x[0] == site), None)
        if not meta: return self._send(404, page('', 'Not found', '<p>No such site.</p>'))
        _, name, what, extra = meta; act = parts[2] if len(parts) > 2 else ''
        who = self._who(); mine = who and who[0] == site and USERS.get(who, {}).get('ok')
        if act == '': return self._send(200, page(site, 'Welcome', f'<p>{name} publishes {what} by city. Free accounts see the table.</p>'
                                                  f'<p><a href="/s/{site}/signup">Sign up</a> · <a href="/s/{site}/login">Sign in</a> · <a href="/s/{site}/data">Data</a></p>'))
        if act == 'signup':
            fields = BASE + ([('Plan (free or pro)', 'plan', 'text')] if extra == 'plan' else []) + ([('What is 7 plus 5?', 'sum', 'text')] if extra == 'sum' else []) \
                + ([('Mobile phone (we text you a login code)', 'phone', 'tel')] if extra == 'phone' else [])
            if extra == 'wizard': fields = [('Full name', 'name', 'text'), ('Work email', 'email', 'email')]
            note = '<p>Passwords need 12 characters, a number and a symbol.</p>' if extra == 'password' else ''
            note += '<p>Access to the data is $49 a month, paid by card after sign-up.</p>' if extra == 'payment' else ''
            return self._send(200, page(site, 'Create your account', note + form(site, 'signup', fields, 'Next' if extra == 'wizard' else 'Create account')))
        if act == 'login': return self._send(200, page(site, 'Sign in', form(site, 'login', [('Email', 'email', 'email'), ('Password', 'password', 'password')], 'Sign in')))
        if act == 'step2' and who and who[0] == site:
            return self._send(200, page(site, 'Step 2 of 2 - your company', form(site, 'step2', [('Company', 'company', 'text'), ('Password', 'password', 'password'),
                                                                                                 ('I agree to the terms of use', 'terms', 'checkbox')], 'Finish')))
        if act == 'verify' and who and who[0] == site:
            return self._send(200, page(site, 'Check your email', f'<p>We emailed a 6-digit code to {html.escape(who[1])}.</p>' + form(site, 'verify', [('Code', 'code', 'text')], 'Verify')))
        if act == 'pay' and who and who[0] == site:
            return self._send(200, page(site, 'Payment', '<p>$49.00 a month, billed today.</p>' + form(site, 'pay', [('Card number', 'card', 'text'), ('Expiry (MM/YY)', 'exp', 'text'),
                                                                                                                  ('CVC', 'cvc', 'text')], 'Pay $49.00')))
        if act == 'sent': return self._send(200, page(site, 'Sent', '<pre>' + html.escape(json.dumps({e: c for (s, e), c in CODES.items() if s == site})) + '</pre>'))
        if act == 'data':
            if not mine: return self._go(f'/s/{site}/login')
            if extra == 'payment' and not USERS[who].get('paid'): return self._go(f'/s/{site}/pay')
            rows = ''.join(f'<tr><td>{c}</td><td>{v}</td></tr>' for c, v in DATA[site])
            return self._send(200, page(site, f'{what.capitalize()} by city', f'<table><tr><th>City</th><th>{html.escape(what)}</th></tr>{rows}</table>'))
        return self._send(404, page(site, 'Not found', '<p>Nothing here.</p>'))

    def do_POST(self):
        f = {k: v[0] for k, v in parse_qs(self.rfile.read(int(self.headers.get('Content-Length') or 0)).decode()).items()}
        parts = [p for p in urlparse(self.path).path.split('/') if p]
        site = parts[1] if len(parts) > 1 else ''; act = parts[2] if len(parts) > 2 else ''
        meta = next((x for x in SITES if x[0] == site), None)
        if not meta: return self._send(404, page('', 'Not found', ''))
        extra, who = meta[3], self._who()
        def again(err, fields=BASE): return self._send(400, page(site, 'Create your account', form(site, 'signup', fields, err=err)))
        if act == 'signup':
            email = (f.get('email') or '').strip().lower()
            if '@' not in email or not f.get('name'): return again('Name and a valid email are needed.')
            if extra == 'wizard': USERS[(site, email)] = {'name': f['name']}; return self._go(f'/s/{site}/step2', self._in(site, email))
            if not f.get('terms'): return again('You need to agree to the terms of use.')
            pw = f.get('password') or ''
            if extra == 'password' and not (len(pw) >= 12 and any(c.isdigit() for c in pw) and any(not c.isalnum() for c in pw)):
                return again('That password is too weak: 12 characters, a number and a symbol.')
            if len(pw) < 6: return again('Choose a password of at least 6 characters.')
            if extra == 'plan' and (f.get('plan') or '').strip().lower() not in ('free', 'pro'): return again('Choose a plan: free or pro.')
            if extra == 'sum' and (f.get('sum') or '').strip() != '12': return again('That answer is not right.')
            if extra == 'phone' and sum(c.isdigit() for c in f.get('phone') or '') < 10: return again('A mobile number is needed.')
            if (site, email) in USERS and USERS[(site, email)].get('ok'): return again('An account with that email already exists - sign in instead.')
            USERS[(site, email)] = {'pw': pw, 'ok': extra != 'emailcode'}
            if extra == 'emailcode':
                code = f'{r.randint(0, 999999):06d}'; CODES[(site, email)] = code
                if INBOX:
                    with open(INBOX, 'a', encoding='utf-8') as o: o.write(json.dumps({'to': email, 'from': f'no-reply@{site}.example', 'subject': f'Your {meta[1]} code',
                                                                                     'body': f'Your {meta[1]} verification code is {code}. It expires in 30 minutes.', 't': time.time()}) + '\n')
                return self._go(f'/s/{site}/verify', self._in(site, email))
            return self._go(f'/s/{site}/data', self._in(site, email))
        if act == 'step2' and who and who[0] == site:
            if not f.get('terms') or len(f.get('password') or '') < 6 or not f.get('company'): return self._send(400, page(site, 'Step 2 of 2', form(site, 'step2', [
                ('Company', 'company', 'text'), ('Password', 'password', 'password'), ('I agree to the terms of use', 'terms', 'checkbox')], 'Finish', 'Fill every field and agree.')))
            USERS[who].update(pw=f['password'], ok=True); return self._go(f'/s/{site}/data')
        if act == 'verify' and who and who[0] == site:
            if (f.get('code') or '').strip() != CODES.get(who): return self._send(400, page(site, 'Check your email', form(site, 'verify', [('Code', 'code', 'text')], 'Verify', 'That code is not right.')))
            USERS[who]['ok'] = True; return self._go(f'/s/{site}/data')
        if act == 'login':
            k = (site, (f.get('email') or '').strip().lower())
            if USERS.get(k, {}).get('ok') and USERS[k].get('pw') == f.get('password'): return self._go(f'/s/{site}/data', self._in(*k))
            return self._send(401, page(site, 'Sign in', form(site, 'login', [('Email', 'email', 'email'), ('Password', 'password', 'password')], 'Sign in', 'Wrong email or password.')))
        if act == 'pay' and who and who[0] == site:
            if sum(c.isdigit() for c in f.get('card') or '') < 15: return self._send(400, page(site, 'Payment', '<p class="err">Card declined.</p>'))
            USERS[who]['paid'] = True; return self._go(f'/s/{site}/data')
        return self._send(405, page(site, 'Not allowed', ''))

    def log_message(self, *a):
        with open(INBOX + '.log' if INBOX else 'signup.log', 'a', encoding='utf-8') as o: o.write(f'{time.strftime("%H:%M:%S")} {a[0] % a[1:] if len(a) > 1 else a}\n')


import threading
for h in ['127.0.0.1', *HOST.values()]: threading.Thread(target=ThreadingHTTPServer((h, PORT), H).serve_forever, daemon=True).start()
threading.Event().wait()
