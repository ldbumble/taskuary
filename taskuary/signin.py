"""SIGNING IN FOR THE BROWSER AGENT, without the agent ever holding the password (the owner, 2026-10-24: "build the password/computer
use thing with vault if they want").

Until now a browser agent at a sign-in page handed the owner the keyboard and stopped - which needs the owner AT the pane, so a
sign-in from the phone was a dead end. Now:

- THE AGENT SAYS SO. It opens the sign-in page in its own browser and ends its turn with `[[TASKUARY-SIGNIN: <domain>]]`
  (selfclose.signin_marker). That is the whole of its part: it is never handed a command, a tool or a file that returns a secret.
- THE TASK PAUSES on the ask it already has - one `input_needed` request, "Sign in to bank.example to continue", answered "Signed in"
  (workerstate). No new state. Its request id is `signin:<site>`, which is how the task page knows to offer the fill page beside it.
- THE SITE IS THE PAGE'S, never the agent's word or a mail's. What the request names, and what a fill may type into, is the
  registrable domain of the page the browser is ON (browserview.state), read when the agent asks and again before every keystroke.
  An email saying "sign in at bank-example.example" can make an agent go there and ask - and the owner then sees that name, big, on
  a page of its own; it cannot make a saved password go there, because a saved one is pinned to the site the owner saved it for.
- THE OWNER SIGNS IN one of two ways: takes over the pane as before (the cookies are kept), or opens the one-time fill page - a link
  minted from the task (owner only), good once and for 15 minutes, of which only the hash is kept. It shows the site, takes a user
  name and password, and "Save to vault for next time" - off unless ticked.
- THE SERVER TYPES IT, over the browser's own DevTools socket (`agent-browser get cdp-url`): into the TOP document only, after
  checking the page's origin is the pinned site, and checking again with the field focused, right before the text goes in. The
  secret travels in one CDP message to Chrome and nowhere else - no argv, no file, no env, no prompt, no log line, no audit text -
  and the pane's screencast is held for the length of the fill (browserview.FILLING), so no frame of it is relayed or snapshotted.
  agent-browser's own `auth save/login` was the obvious road and is not taken: it keeps the profile in a file under
  ~/.agent-browser, which the agent's shell can read.
- SAVED, IT IS SEALED (vault.seal: DPAPI on Windows, the keychain elsewhere; refused where neither exists), one row per site. The
  next time an agent asks to sign in on that site the server fills it by itself and tells the agent "Signed in - continue": no owner
  step. A saved sign-in the site asked for AGAIN within a few minutes is not tried twice (a changed password, a lockout) - the ask
  stays with the owner.
- EVERY FILL IS AUDITED: site, task, how, whether it went in. Never what was typed.

Not built yet (next phase): authenticator/TOTP keys, reading a code out of the mail, a fill link on the phone (the share port is
LAN-only), and a 1Password/Bitwarden provider.
"""
import hashlib, html as H, ipaddress, json, logging, re, secrets, shutil, subprocess, tempfile, threading, time
from pathlib import Path
from urllib.parse import urlsplit
from loguru import logger

TTL = 15 * 60                   # a fill link lives this long, and opens once
AGAIN = 10 * 60                 # a saved sign-in the site asks for again inside this is not tried a second time
STEP_WAIT = 20.0                # a two-step sign-in: how long the password page is given to appear after the user name
PREFIX = 'signin:'              # the request id of a sign-in ask: `signin:<site>`
DONE = 'Signed in'
LOOPBACK = ('localhost', '127.0.0.1', '::1')
# TWO-LABEL PUBLIC SUFFIXES - where the registrable domain is THREE labels. Without them "bank.co.uk" would pin "co.uk", and a
# saved sign-in would fill on every site in the UK. Not the whole Public Suffix List (no dependency carries it here); the
# common country suffixes and the shared-hosting ones where strangers hold sibling names (one user's github.io is not another's).
SUFFIX2 = frozenset('''
co.uk org.uk ac.uk gov.uk ltd.uk plc.uk me.uk net.uk nhs.uk police.uk sch.uk
com.au net.au org.au edu.au gov.au asn.au id.au co.nz net.nz org.nz govt.nz ac.nz
co.jp ne.jp or.jp ac.jp go.jp co.kr or.kr ac.kr go.kr com.cn net.cn org.cn gov.cn edu.cn com.hk org.hk com.tw org.tw com.sg org.sg
gov.sg edu.sg com.my org.my co.in net.in org.in gov.in ac.in co.id or.id ac.id go.id co.th ac.th go.th com.ph com.vn com.pk
co.za org.za gov.za ac.za co.il org.il ac.il gov.il com.tr org.tr gov.tr com.br net.br org.br gov.br com.ar gob.ar com.mx gob.mx
org.mx com.co gov.co com.pe com.ve com.ec co.ke co.ug co.tz com.ng com.eg com.sa gov.sa com.qa ae.org com.ua co.at or.at gv.at
qc.ca on.ca bc.ca ab.ca
github.io gitlab.io herokuapp.com azurewebsites.net cloudapp.net blogspot.com appspot.com web.app firebaseapp.com
netlify.app vercel.app pages.dev workers.dev onrender.com fly.dev glitch.me repl.co ngrok.io ngrok.app s3.amazonaws.com
cloudfront.net amplifyapp.com elasticbeanstalk.com azurestaticapps.net sharepoint.com myshopify.com wordpress.com wixsite.com
squarespace.com webflow.io bubbleapps.io notion.site'''.split())


class SignInError(Exception): pass
def _now() -> float: return time.time()
def _hash(tok) -> str: return hashlib.sha256(str(tok or '').encode('utf-8', 'surrogateescape')).hexdigest()


# ── the site: what a page IS, by its own origin ──────────────────────────────────────────────────────────────────────────
def _ip(h: str) -> bool:
    try: ipaddress.ip_address(h.strip('[]')); return True
    except ValueError: return False


def host_of(host) -> str:
    """A host as the browser holds it: lower case, no trailing dot, an international name as its punycode - so a lookalike
    spelled in another alphabet is the different name it is, never folded onto the real one."""
    h = str(host or '').strip().strip('.').lower()
    if not h or _ip(h): return h.strip('[]')
    try: return h.encode('idna').decode('ascii')
    except UnicodeError: return ''


def registrable(host) -> str:
    """The name a sign-in belongs to: bank.example for login.bank.example, bank.co.uk for www.bank.co.uk. An IP or a one-label
    name (localhost) is itself; a bare public suffix ("co.uk", "github.io") belongs to nobody - ''."""
    h = host_of(host)
    if not h or _ip(h) or '.' not in h: return h
    p = h.split('.')
    n = 3 if '.'.join(p[-2:]) in SUFFIX2 else 2
    return '.'.join(p[-n:]) if len(p) >= n else ''


def site_of(url) -> str:
    """The registrable domain of a page a password may be typed on, or '' - https only (loopback is the one http, for a local
    app), no other scheme at all."""
    try: u = urlsplit(str(url or '').strip())
    except ValueError: return ''
    h = host_of(u.hostname)
    if u.scheme == 'https' or (u.scheme == 'http' and h in LOOPBACK): return registrable(h)
    return ''


def on_site(url, site) -> bool:
    """Is this page ON `site` - the site itself or a name under it, by its origin? A lookalike (bank.example.evil.example,
    bank-example.example, a homograph) has another registrable domain and is not."""
    s = site_of(url)
    return bool(s) and s == str(site or '').lower()


def clean_claim(text) -> str:
    """What the agent NAMED, as words to show and nothing more: a domain's own characters, or ''."""
    m = re.search(r'[a-z0-9](?:[a-z0-9.-]{0,251}[a-z0-9])?\.[a-z]{2,63}', str(text or '').lower())
    return m.group(0) if m else ''


# ── the tables: a sealed row per saved site, and the hash of each fill link ─────────────────────────────────────────────
def _tables(store):
    with store.lock:
        store.cx.execute('CREATE TABLE IF NOT EXISTS signin_vault (Site TEXT PRIMARY KEY, User TEXT, Secret TEXT, SavedAt REAL, '
                         'SavedBy TEXT, LastUsed REAL)')
        store.cx.execute('CREATE TABLE IF NOT EXISTS signin_token (TokenHash TEXT PRIMARY KEY, TaskId INTEGER, Sid TEXT, Site TEXT, '
                         'RequestId TEXT, CreatedAt REAL, ExpiresAt REAL, UsedAt REAL)')
        store.cx.commit()


def saved(store, site) -> dict | None:
    _tables(store)
    return store._one('SELECT Site, User, Secret, SavedAt, LastUsed FROM signin_vault WHERE Site=?', (str(site or '').lower(),))


def listing(store) -> list:
    """Settings -> Saved sign-ins: the site, when it was saved, when it was last used. Never the user name or the secret."""
    _tables(store)
    return [{'site': r['Site'], 'saved': r['SavedAt'], 'used': r['LastUsed']}
            for r in store._rows('SELECT Site, SavedAt, LastUsed FROM signin_vault ORDER BY Site')]


def save(store, site, user, pw, by='owner'):
    """Keep a sign-in for `site`, sealed. The site is the one the owner saw on the fill page - pinned there, at save time."""
    from . import vault
    site = str(site or '').lower()
    if not site or registrable(site) != site: raise ValueError('that is not a site a sign-in can be kept for')
    if not pw: raise ValueError('there is no password to keep')
    u, p = vault.seal(user or '') if user else '', vault.seal(pw)
    # sealed or not at all: a password vault that falls back to plain text in the database is worse than none
    if not vault.sealed(p): raise ValueError('this computer has no keychain to seal it in, so it was not saved')
    _tables(store)
    old = saved(store, site)
    store._exec('INSERT OR REPLACE INTO signin_vault (Site, User, Secret, SavedAt, SavedBy, LastUsed) VALUES (?,?,?,?,?,?)',
                (site, u, p, _now(), by, None))
    for v in (old or {}).get('User'), (old or {}).get('Secret'): vault.forget(v)
    store.audit('signin', 0, 'signin_saved', by, detail={'site': site})


def remove(store, site, by='owner') -> bool:
    """Forget a saved sign-in AND what it left behind: the sealed row, and that site's cookies in the browser's kept state."""
    from . import browserview, vault
    site = str(site or '').lower()
    row = saved(store, site)
    if row:
        store._exec('DELETE FROM signin_vault WHERE Site=?', (site,))
        for v in row.get('User'), row.get('Secret'): vault.forget(v)
    n = browserview.forget_site(site)
    _forget_live(site)
    store.audit('signin', 0, 'signin_removed', by, detail={'site': site, 'had_saved': bool(row), 'cookie_files': n})
    return bool(row) or bool(n)


def _forget_live(site):
    from . import browserview, terminal as term
    for sid in list(term.SESSIONS):
        if not browserview.state(sid).get('open'): continue
        try:
            c = connect(sid)
            try: c.forget(site)
            finally: c.close()
        except Exception as e: logger.debug(f'signin: {site} cookies not cleared from the live browser of {sid} - {e}')


def _used(store, site): store._exec('UPDATE signin_vault SET LastUsed=? WHERE Site=?', (_now(), site))


# ── the one-time fill link ───────────────────────────────────────────────────────────────────────────────────────────────
def mint(store, tid: int, sid: str, site: str, request_id: str) -> str:
    """A fill link's token: shown once (in the link), kept only as its hash."""
    _tables(store)
    tok, now = secrets.token_urlsafe(32), _now()
    store._exec('INSERT INTO signin_token (TokenHash, TaskId, Sid, Site, RequestId, CreatedAt, ExpiresAt) VALUES (?,?,?,?,?,?,?)',
                (_hash(tok), tid, str(sid), site, request_id, now, now + TTL))
    store._exec('DELETE FROM signin_token WHERE ExpiresAt<?', (now - 86400,))      # yesterday's dead links are not kept
    return tok


def peek(store, tok) -> dict | None:
    """The link's sign-in while it is still good - unused and in date - else None. Reading does not spend it."""
    _tables(store)
    r = store._one('SELECT * FROM signin_token WHERE TokenHash=?', (_hash(tok),)) if tok else None
    return r if r and not r['UsedAt'] and r['ExpiresAt'] > _now() else None


def take(store, tok) -> dict | None:
    """Spend the link: the first caller gets its sign-in, every later one None - checked and marked in one statement."""
    r = peek(store, tok)
    if not r: return None
    with store.lock:
        cur = store.cx.execute('UPDATE signin_token SET UsedAt=? WHERE TokenHash=? AND UsedAt IS NULL AND ExpiresAt>?',
                               (_now(), r['TokenHash'], _now()))
        store.cx.commit()
    return r if cur.rowcount == 1 else None


def pending(store, tid: int) -> dict | None:
    """The sign-in this task is waiting on now - {site, sid, request_id} - from its open requests; None when it waits on none."""
    from . import workerstate as ws
    reqs = [r for r in ws.status(store, tid)['requests'] if str(r.get('request_id') or '').startswith(PREFIX)]
    if not reqs: return None
    r = reqs[-1]
    return {'site': r['request_id'][len(PREFIX):], 'sid': str(r.get('sid') or ''), 'request_id': r['request_id'], 'text': r.get('text')}


def link(store, tid: int) -> dict:
    """A fresh fill link for the sign-in this task waits on (the owner's press on the task)."""
    p = pending(store, tid)
    if not p: raise LookupError('this task is not waiting on a sign-in')
    return {'url': f"/signin/{mint(store, tid, p['sid'], p['site'], p['request_id'])}", 'site': p['site'], 'minutes': TTL // 60}


def phone_line(store, tid: int) -> str:
    """What the phone says of a task waiting on a sign-in: where to do it. No fill link goes to the phone - the fill page is this
    computer's, and the phone is not on its network."""
    p = pending(store, tid)
    return f"Sign in to {p['site']} on your PC to continue" if p else ''


# ── the agent asked ──────────────────────────────────────────────────────────────────────────────────────────────────────
_TRIED = {}                     # (tid, site) -> when a saved sign-in was last typed for it


def _chat(sid) -> bool:
    from . import terminal as term
    return hasattr(term.SESSIONS.get(str(sid)), 'send_prompt')


def needs(store, tid: int, sid: str, claimed: str = '', fill=None) -> dict:
    """The agent ended its turn asking to be signed in. Record the ask on the existing road and, when the owner keeps a sign-in for
    the site the browser is actually on, fill it at once on its own thread. `fill`: the filler (tests stand one in)."""
    from . import browserview, workerstate as ws
    st = browserview.state(sid, fresh=True)
    site, said = (site_of(st.get('url')) if st.get('open') else ''), clean_claim(claimed)
    if not site:
        # no page to sign in on (or not one a password goes to): the owner reads the agent's words, and no fill is ever offered
        text = f"Sign in to {said or 'the site'} to continue - the agent's browser is not on a sign-in page Taskuary can fill"
        ws.record(store, tid, sid, 'input_needed', request_id=ws.request_id_for(text), text=text, choices=[DONE] if _chat(sid) else None,
                  source='api')
        return {'site': '', 'auto': False}
    rid, text = f'{PREFIX}{site}', f'Sign in to {site} to continue'
    # "Signed in" as a press only where an answer arrives as words (the chat's own agent): a pty's choices are a chooser, answered
    # by number (workerstate.answer) - there the owner types it
    ws.record(store, tid, sid, 'input_needed', request_id=rid, text=text, choices=[DONE] if _chat(sid) else None, source='api')
    row, last = saved(store, site), _TRIED.get((tid, site), 0)
    if row and _now() - last < AGAIN:
        store.add_comment(tid, 'taskuary', 'agent', f'{site} asked to sign in again within minutes of the saved sign-in - it may be out '
                                                    'of date, so it was not tried twice. Sign in yourself, or update it on the fill page.')
        return {'site': site, 'auto': False}
    if not row: return {'site': site, 'auto': False}
    _TRIED[(tid, site)] = _now()
    threading.Thread(target=_auto, args=(store, tid, sid, site, rid, fill or type_in), daemon=True, name=f'signin-{tid}').start()
    return {'site': site, 'auto': True}


def _auto(store, tid, sid, site, rid, fill):
    from . import vault
    row = saved(store, site) or {}
    try:
        user, pw = vault.unseal(row.get('User') or '') or '', vault.unseal(row.get('Secret') or '')
        if not pw: raise SignInError('the saved password could not be opened on this computer')
        fill(sid, site, user, pw)
        _used(store, site)
        _audit(store, tid, site, 'vault', True)
        _continue(store, tid, rid, site, 'taskuary')
    except Exception as e:
        why = str(e) if isinstance(e, SignInError) else 'the browser could not be reached'
        _audit(store, tid, site, 'vault', False, why)
        store.add_comment(tid, 'taskuary', 'agent', f'The saved sign-in for {site} was not used: {why}. Sign in yourself to continue.')


def by_owner(store, tok, user, pw, keep: bool, fill=None) -> dict:
    """The fill page's Sign in: spend the link, type it into the task's browser, keep it sealed when asked, and tell the agent."""
    r = take(store, tok)
    if not r: raise LookupError('this sign-in link was used already or has expired - open a new one from the task')
    tid, site = r['TaskId'], r['Site']
    if not pw: raise ValueError('type the password')
    try: (fill or type_in)(r['Sid'], site, user, pw)
    except SignInError as e:
        _audit(store, tid, site, 'typed', False, str(e)); raise
    except Exception:
        _audit(store, tid, site, 'typed', False, 'the browser could not be reached')
        raise SignInError("the task's browser could not be reached - is the task still open?")
    kept = ''
    if keep:
        try: save(store, site, user, pw); kept = 'saved'
        except ValueError as e: kept = str(e)
    _audit(store, tid, site, 'typed', True, saved=kept == 'saved')
    threading.Thread(target=_continue, args=(store, tid, r['RequestId'], site, 'owner'), daemon=True).start()
    return {'site': site, 'task': tid, 'saved': kept == 'saved', 'kept': kept}


def _continue(store, tid, rid, site, actor):
    """Tell the agent - the words it was promised, nothing else - and close the ask. Not workerstate.answer: that answers a pty's
    question with choices by its NUMBER, and "1" typed into a CLI's prompt is not "you are signed in"."""
    from . import terminal as term, workerstate as ws
    sess, said = ws._live(tid), f'{DONE} to {site} - continue.'
    if not sess:
        store.add_comment(tid, actor, 'agent', f'Signed in to {site}, but no agent is running on this task to tell - open it to continue.')
        return
    try:
        if hasattr(sess, 'send_prompt'): sess.send_prompt(said, as_owner=False)
        else: term.type_into(sess, said)
    except Exception as e:
        logger.warning(f'signin: task {tid} signed in to {site}, but the agent was not told - {e}')
        store.add_comment(tid, actor, 'agent', f'Signed in to {site}, but the agent could not be told - say "{said}" to it.')
        return
    ws.record(store, tid, sess.sid, 'answered', request_id=rid, text=DONE, source='owner' if actor == 'owner' else 'api')
    store.add_comment(tid, actor, 'agent', f"Signed in to {site}{' with the saved sign-in' if actor != 'owner' else ''} - the agent goes on.")


def _audit(store, tid, site, how, ok, why='', saved=None):
    d = {'site': site, 'how': how, 'ok': bool(ok), **({'why': why} if why else {}), **({'saved': saved} if saved is not None else {})}
    store.audit('task', tid, 'signin_fill', 'taskuary' if how == 'vault' else 'owner', 'system' if how == 'vault' else 'human', d)


# ── typing it: the browser's own DevTools socket, top document only ─────────────────────────────────────────────────────────
_QUIET = logging.getLogger('taskuary.signin.cdp')      # websockets logs frames at DEBUG: never to anything, whatever the root says
_QUIET.addHandler(logging.NullHandler()); _QUIET.propagate = False; _QUIET.disabled = True

# Every field is looked for in THIS document - never a frame's, so a sign-in box another site framed into the page is not one
# Taskuary types into. Visible, enabled and writable only; the user-name box is the text field before the password box.
FIELDS = r'''(want) => {
  const vis = (e) => { const s = getComputedStyle(e), r = e.getBoundingClientRect();
    return !e.disabled && !e.readOnly && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05 && r.width > 4 && r.height > 4; };
  const ins = [...document.querySelectorAll('input')].filter(vis);
  const pw = ins.find((e) => e.type === 'password');
  const texty = (e) => ['text', 'email', 'tel', ''].includes(e.type);
  const named = (e) => /user|mail|login|account|ident|member|customer/i
    .test([e.name, e.id, e.autocomplete, e.getAttribute('aria-label'), e.placeholder].join(' '));
  const before = pw ? ins.slice(0, ins.indexOf(pw)).filter(texty) : [];
  const user = before.reverse().find(named) || before[0] || (!pw && (ins.find((e) => texty(e) && named(e)) || null));
  const frames = [...document.querySelectorAll('iframe')].filter(vis).map((e) => e.src || '');
  const el = want === 'password' ? pw : want === 'user' ? user : null;
  if (el) { el.focus(); try { el.select(); } catch (_) { el.value = ''; } }
  return { origin: location.origin, href: location.href, top: window === window.top, password: !!pw, user: !!user, frames,
           focused: !!el && document.activeElement === el };
}'''
CLEAR = "document.querySelectorAll('input[type=password]').forEach((e) => { e.value = ''; })"
SETTLE = 2.0                    # after the submit, before the boxes are emptied and the agent hears: the page's own post goes first
STILL = "(() => ({ href: location.href, password: !!document.activeElement && document.activeElement.type === 'password' }))()"


class Cdp:
    """One DevTools connection to a session's Chrome, attached to the tab the agent is on. A refusal is said by WHICH call, never
    with the call's parameters - one of them is the password."""
    def __init__(self, ws_url: str, target: str):
        from websockets.sync.client import connect
        kw = dict(open_timeout=5, max_size=8 * 1024 * 1024, logger=_QUIET)   # no Origin: Chrome refuses a browser-looking client
        try: self.ws = connect(ws_url, proxy=None, **kw)
        except TypeError: self.ws = connect(ws_url, **kw)              # websockets before 15 has no proxy setting
        self.n, self.session = 0, None
        self.session = self.call('Target.attachToTarget', {'targetId': target, 'flatten': True}, top=True)['sessionId']

    def call(self, method, params=None, top=False, timeout=10.0) -> dict:
        self.n += 1; i = self.n
        m = {'id': i, 'method': method, 'params': params or {}}
        if self.session and not top: m['sessionId'] = self.session
        self.ws.send(json.dumps(m))
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0: raise SignInError('the browser did not answer in time')
            r = json.loads(self.ws.recv(timeout=left))
            if r.get('id') == i:
                if 'error' in r: raise SignInError(f'the browser refused {method.split(".")[0]}')
                return r.get('result') or {}

    def js(self, expr: str):
        r = self.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
        if r.get('exceptionDetails'): raise SignInError('the page did not let Taskuary look at it')
        return (r.get('result') or {}).get('value')

    def fields(self, want=''): return self.js(f'({FIELDS})({json.dumps(want)})') or {}
    def type(self, text: str): self.call('Input.insertText', {'text': text})
    def forget(self, site: str) -> int:
        """Delete the site's cookies from this LIVE browser - its kept file is cleaned on disk, but a running browser writes its own
        jar back when it closes."""
        mine = [k for k in self.call('Storage.getCookies', top=True).get('cookies') or []
                if (h := host_of(k.get('domain'))) and (h == site or h.endswith('.' + site))]
        for k in mine: self.call('Network.deleteCookies', {'name': k['name'], 'domain': k['domain'], 'path': k.get('path') or '/'})
        return len(mine)
    def enter(self):
        for t in ('keyDown', 'keyUp'):
            self.call('Input.dispatchKeyEvent', {'type': t, 'key': 'Enter', 'code': 'Enter', 'windowsVirtualKeyCode': 13,
                                                 'nativeVirtualKeyCode': 13, **({'text': '\r'} if t == 'keyDown' else {})})
    def close(self):
        try: self.ws.close()
        except Exception: pass


def _cdp_url(sid: str) -> str:
    """The session's Chrome DevTools address, from agent-browser itself. Output to a FILE, not a pipe: see browserview.navigate."""
    from . import browserview, spawn
    exe = shutil.which('agent-browser')
    if not exe: raise SignInError('agent-browser is not installed')
    log = Path(tempfile.gettempdir()) / f'{browserview.session_name(sid)}-cdp.log'
    with open(log, 'wb') as f:
        p = spawn.popen([exe, '--session', browserview.session_name(sid), 'get', 'cdp-url'], env=browserview._cli_env(sid),
                        stdout=f, stderr=f, stdin=subprocess.DEVNULL)
        try: rc = p.wait(timeout=20)
        except subprocess.TimeoutExpired: p.kill(); raise SignInError('the browser did not answer in time')
    m = re.search(r'ws://127\.0\.0\.1:\d+/devtools/browser/[\w-]+', log.read_text(encoding='utf-8', errors='replace'))
    if rc != 0 or not m: raise SignInError("the task's browser is not open")
    return m.group(0)


def connect(sid: str) -> Cdp:
    from . import browserview
    if not browserview.state(sid, fresh=True)['open']: raise SignInError("the task's browser is not open")
    try: target = (json.loads(browserview._read(browserview.session_name(sid), 'target') or '{}') or {}).get('targetId')
    except ValueError: target = None
    if not target: raise SignInError("the task's browser has no page open")
    return Cdp(_cdp_url(sid), target)


def _guard(c: Cdp, site: str, want: str) -> dict:
    """Focus the `want` field - and refuse unless the TOP page is on the pinned site and the field is in it."""
    f = c.fields(want)
    if not f.get('top') or not on_site(f.get('href'), site):
        raise SignInError(f'the page is no longer on {site} - nothing was typed')
    if want and not f.get('focused'): raise SignInError(f'the {"password" if want == "password" else "user name"} box on {site} could not be found')
    return f


def fill_page(c: Cdp, site: str, user: str, pw: str, wait: float = STEP_WAIT):
    """Type a sign-in into the page `c` is on - the whole of the checking lives here, so a test drives it with a stand-in page."""
    f = _guard(c, site, '')
    if not f.get('password') and not f.get('user'):
        # what tells "the form is in another site's frame" from "no form": the page's own frames, by their address. Not the
        # DevTools frame tree - a cross-site frame runs in a process of its own and is not in it (measured, Chrome 2026-10)
        other = [o for o in f.get('frames') or [] if str(o).startswith(('http://', 'https://')) and not on_site(o, site)]
        raise SignInError(f'the sign-in form is inside a frame from another site ({registrable(urlsplit(other[0]).hostname) or "unknown"}) - '
                          'sign in yourself in the pane' if other else f'there is no sign-in form on the {site} page')
    if f.get('user') and user:
        _guard(c, site, 'user'); c.type(user)
        if not f.get('password'):                            # a two-step sign-in: the user name first, then its own password page
            c.enter()
            end = time.time() + wait
            while not f.get('password'):
                if time.time() > end: raise SignInError(f'{site} did not ask for the password after the user name')
                time.sleep(.5)
                try: f = _guard(c, site, '')
                except SignInError as e:     # mid-navigation the page cannot be read for a moment; off the site, it has gone elsewhere
                    if 'no longer on' in str(e): raise SignInError(f'{site} sent the sign-in to another site - sign in yourself in the pane')
                    f = {}
    elif not f.get('password'): raise SignInError(f'the {site} page asks for a user name and none is saved')
    _guard(c, site, 'password')
    s = c.js(STILL) or {}                                    # the last look, with the box focused: still this site, still a password box
    if not s.get('password') or not on_site(s.get('href'), site): raise SignInError('the page changed under the sign-in - nothing was typed')
    c.type(pw)
    c.enter()


def type_in(sid: str, site: str, user: str, pw: str):
    """Sign the session's browser in on `site`: the screencast held while it types, the socket closed after."""
    from . import browserview
    with browserview.filling(sid):
        c = connect(sid)
        try:
            fill_page(c, site, user, pw)
            # THE PASSWORD DOES NOT STAY IN THE PAGE for the agent to read back (`agent-browser eval` on the box) when the site keeps
            # the form up - a wrong password, a captcha, a page that submits by script. Whatever box still holds it is emptied.
            time.sleep(SETTLE)
            try: c.js(CLEAR)
            except SignInError: pass                          # the page moved on: nothing of it is left to clear
        finally: c.close()


# ── the fill page: one site, two boxes, one press - served by the app itself on 127.0.0.1, never on the share port ───────────
CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'Referrer-Policy': 'no-referrer', 'X-Content-Type-Options': 'nosniff',
           'X-Frame-Options': 'DENY', 'Content-Security-Policy': CSP, 'X-Robots-Tag': 'noindex, nofollow'}
_STYLE = ('body{margin:0;background:#f6f3ee;color:#2b2722;font:15px/1.5 system-ui,-apple-system,"Segoe UI",sans-serif}'
          'main{max-width:420px;margin:8vh auto;padding:28px 24px;background:#fff;border:1px solid #e3ddd3;border-radius:10px}'
          '.k{color:#867f74;font-size:13px;margin:0}.site{font-size:30px;font-weight:700;margin:2px 0 14px;word-break:break-all}'
          'label{display:block;font-size:13px;color:#5b554c;margin:12px 0 4px}input[type=text],input[type=password]{width:100%;'
          'box-sizing:border-box;padding:9px 10px;font-size:15px;border:1px solid #d6cec1;border-radius:6px}'
          '.keep{display:flex;gap:8px;align-items:center;margin:14px 0 4px;font-size:14px;color:#2b2722}'
          'button{margin-top:16px;width:100%;padding:10px;font-size:15px;font-weight:600;border:0;border-radius:6px;background:#2b2722;'
          'color:#fff;cursor:pointer}.note{color:#867f74;font-size:12.5px;margin-top:14px}.err{color:#a33b3b}.ok{color:#2e6b3a}')


def _page(body: str) -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="referrer" content="no-referrer"><title>Sign in - Taskuary</title><style>{_STYLE}</style></head>'
            f'<body><main>{body}</main></body></html>')


def form_html(site: str, minutes: int, err: str = '') -> str:
    """The fill page. The SITE leads, big - it is the one thing to check before typing a password into anything."""
    s = H.escape(site)
    return _page(f'<p class="k">Sign in to</p><p class="site">{s}</p>'
                 + (f'<p class="err" role="alert">{H.escape(err)}</p>' if err else '')
                 + '<form method="post" autocomplete="off">'
                 '<label for="u">Username</label><input id="u" name="username" type="text" autocomplete="username" autofocus>'
                 '<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>'
                 '<label class="keep"><input type="checkbox" name="save" value="1"> Save to vault for next time</label>'
                 '<button type="submit">Sign in</button></form>'
                 f'<p class="note">Taskuary types this into the {s} page open in the task\'s browser - only if that page is still on {s}. '
                 f'The agent never sees it. This page works once, for {minutes} more minute{"s" if minutes != 1 else ""}.</p>')


def done_html(site: str, saved: bool, kept: str = '') -> str:
    s = H.escape(site)
    keep = ('<p class="note">Saved for next time - Settings, Saved sign-ins, to remove it.</p>' if saved else
            f'<p class="note err">Not saved: {H.escape(kept)}.</p>' if kept else '')
    return _page(f'<p class="k">Signed in to</p><p class="site">{s}</p><p class="ok">Typed into the task\'s browser - the agent goes on. '
                 'You can close this page.</p>' + keep)


def gone_html(why: str) -> str:
    return _page(f'<p class="k">Sign in</p><p class="err" role="alert">{H.escape(why)}</p><p class="note">Open a new sign-in page from the task.</p>')
