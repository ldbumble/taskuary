"""SIGNING IN FOR THE BROWSER AGENT, without the agent ever holding the password (the owner, 2026-10-24: "build the password/computer
use thing with vault if they want").

Until now a browser agent at a sign-in page handed the owner the keyboard and stopped - which needs the owner AT the pane, so a
sign-in from the phone was a dead end. Now:

- THE AGENT SAYS SO. It opens the sign-in page in its own browser and calls hand_over with its site (browserview.hand_over), and goes on
  with the job. That is the whole of its part: it is never handed a command, a tool or a file that returns a secret.
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
  step, and no ask raised - so nothing is shown (2026-11-05); the ask is raised only when the saved one does not go in. A saved sign-in the site asked for AGAIN within a few minutes is not tried twice (a changed password, a lockout) - the ask
  stays with the owner.
- EVERY FILL IS AUDITED: site, task, how, whether it went in. Never what was typed.

- AN AUTHENTICATOR CODE (2026-10-25, totp.py): the owner may keep the site's authenticator key with its sign-in, sealed the same
  way. After the password, when the site's page asks for a one-time code, the server computes it (RFC 6238) and types it under the
  same checks - top document, the pinned site, the box focused - and the box is emptied after, like the password's. A page that
  is ONLY a code prompt (the agent was signed in, the site asks again) is filled with the code alone. The receipt says a code was
  typed, never which.

Not built yet (next phase): reading a code out of the mail, a code split over one box per digit, a fill link on the phone (the share
port is LAN-only), and a 1Password/Bitwarden provider.
"""
import hashlib, html as H, ipaddress, json, logging, re, secrets, shutil, subprocess, tempfile, threading, time
from datetime import datetime
from .say import said as _said            # a failure written to the chat is said in his words (say.py)
from pathlib import Path
from urllib.parse import urlsplit
from loguru import logger
from . import words

TTL = 15 * 60                   # a fill link lives this long, and opens once
AGAIN = 10 * 60                 # a saved sign-in the site asks for again inside this is not tried a second time
STEP_WAIT = 20.0                # a two-step sign-in: how long the password page is given to appear after the user name
CODE_WAIT = 15.0                # after the password: how long a site is given to show its code prompt before none is taken as asked
PREFIX = 'signin:'              # the request id of a sign-in ask: `signin:<site>`, `~N` after it when raised again (workerstate.fresh_id)
def ask_site(rid) -> str: return str(rid or '')[len(PREFIX):].split('~')[0]      # the site a sign-in ask is for, by its id
DONE = 'Signed in'
CODE_ASK = '{site} took the saved sign-in and asks for a code - type it on the page to continue'
# ...AND THE CODE PAGE IS MADE READY FOR HIM FIRST (the owner, 2026-11-15: "why can't you click save for 30 days when you sign in ... so you
# won't need it"): the agent, which reads the page, ticks whatever the page offers to remember this browser - so the next task, and one
# opened beside it, does not stop for a code - and hands the code step over. What such a box is, is its judgement: nothing here reads words
READY_CODE = ('TASKUARY: the saved sign-in for {site} went in, and the site now asks for a code only the owner has. Get that page ready for '
              'them: if it offers to remember this browser or device (so later sign-ins skip the code), tick that - type nothing in the code '
              'box and press nothing else - then call hand_over with site {site}, and Taskuary hands them the code step. Say nothing else to them.')
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
class NotAccepted(SignInError):
    """Typed, and the site kept its password box up: not a sign-in. Every surface said "Signed in", the vault kept a password that never
    worked and typed it again (the owner's computer-use walk, 2026-10-25). `again`: a fresh fill link's token, for the form shown again.
    `own`: the reason names what the form also needed (refused) - the password was not shown to be wrong."""
    again, own = '', False
def _now() -> float: return time.time()
def _hash(tok) -> str: return hashlib.sha256(str(tok or '').encode('utf-8', 'surrogateescape')).hexdigest()


# ── the site: what a page IS, by its own origin ──────────────────────────────────────────────────────────────────────────
def _loopback(h: str) -> bool:
    "This computer: localhost, or an address of the loopback range - all of 127.0.0.0/8 is, not only 127.0.0.1."
    if h in LOOPBACK: return True
    try: return ipaddress.ip_address(h.strip('[]')).is_loopback
    except ValueError: return False


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
    if u.scheme == 'https' or (u.scheme == 'http' and _loopback(h)): return registrable(h)
    return ''


# WHAT A SITE IS CALLED, ONE WAY (the roads audit, 2026-11-19: one payment step read www.toll.example on its card, toll.example on its
# hand-over and toll.example:8443 on the page). Every card, hand-over and line names a site by this: the name it is registered under
# (login.bank.example is bank.example), never a port or a www; a bare address by its page's own title where the session is named
def site_name(where, sid: str = '') -> str:
    "The site a URL or a host is on, as the owner reads it - '' for none."
    s = str(where or '').strip()
    try: h = host_of(urlsplit(s if '://' in s else '//' + s).hostname)
    except ValueError: return ''
    if not h: return ''
    if _ip(h) or '.' not in h: return page_name(sid, h) if sid else h
    return registrable(h) or h.removeprefix('www.')


def on_site(url, site) -> bool:
    """Is this page ON `site` - the site itself or a name under it, by its origin? A lookalike (bank.example.evil.example,
    bank-example.example, a homograph) has another registrable domain and is not."""
    s = site_of(url)
    return bool(s) and s == str(site or '').lower()


def site_from(typed) -> str:
    """The site an owner TYPED, to keep a sign-in for: an address or a bare name ("portal.example.com", "https://login.portal.example/x"),
    as its registrable domain - '' for anything else (plain http, a bare suffix, words)."""
    t = str(typed or '').strip()
    if not t or ' ' in t: return ''
    return site_of(t if re.match(r'^[a-z][a-z0-9+.-]*://', t, re.I) else f'https://{t}')


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
        # the authenticator key (2026-10-25) came a release after the table: a 0.3.9.34 home gains the column, its rows untouched
        if 'Totp' not in {r[1] for r in store.cx.execute('PRAGMA table_info(signin_vault)')}:
            store.cx.execute('ALTER TABLE signin_vault ADD COLUMN Totp TEXT')
        # ...and the other boxes a site's form asks for (2026-11-04: a "Customer ID" beside the email and password), sealed as one JSON
        if 'Extra' not in {r[1] for r in store.cx.execute('PRAGMA table_info(signin_vault)')}:
            store.cx.execute('ALTER TABLE signin_vault ADD COLUMN Extra TEXT')
        # ...and the task whose agent made the account (walk 9, 2026-11-23): an inbox one task signed up for, no later task knew of
        if 'Task' not in {r[1] for r in store.cx.execute('PRAGMA table_info(signin_vault)')}:
            store.cx.execute('ALTER TABLE signin_vault ADD COLUMN Task INTEGER')
        store.cx.commit()


def saved(store, site) -> dict | None:
    _tables(store)
    return store._one('SELECT Site, User, Secret, Totp, Extra, SavedAt, SavedBy, LastUsed, Task FROM signin_vault WHERE Site=?', (str(site or '').lower(),))


# ONE VAULT FOR EVERY LOGIN (the owner, 2026-11-23: "if the agent made a login it should save it in the agent vault same as login I give it"):
# an account an agent made is a row like one he typed, by the same save, shown the same way - the site, the user name, which task made it -
# and its password his to reveal. An account Taskuary has not yet signed in with is said so (confirmed): a sign-up the site seemed to take
# is not proof it was made (walk 9: a row read "signed in" for an account stopped at its phone step). Whether a site took it is the ledger's
# (ledger.account, written by the sign-in or sign-up the site let past) - the one record every task reads what exists from.
MADE_BY = ('taskuary', 'agent')
def confirmed(row, known: dict) -> bool:
    "The owner's own, or an account a site took since this row was saved (`known`: ledger.sites)."
    if (row.get('SavedBy') or 'owner') not in MADE_BY: return True
    k = known.get(str(row.get('Site') or '').lower())
    return bool(k) and str(k['At']) >= datetime.fromtimestamp(float(row.get('SavedAt') or 0)).isoformat(sep=' ', timespec='seconds')


def _user(row) -> str:
    from . import vault
    return vault.unseal(row['User']) if row.get('User') else ''


def listing(store) -> list:
    """Settings -> Saved sign-ins: the site, its user name, when it was saved and last used, whether a code key is kept, the task whose agent
    made it, and whether a sign-in with it has gone in yet. Never the secret or the key (reveal, on his press)."""
    from .store import task_ref
    from . import ledger
    _tables(store); known = ledger.sites(store)
    return [{'site': r['Site'], 'user': _user(r), 'saved': r['SavedAt'], 'used': r['LastUsed'], 'code': bool(r['Totp']), 'fields': sorted(extra_of(r)),
             'by': 'agent' if (r.get('SavedBy') or '') in MADE_BY else 'owner', 'confirmed': confirmed(r, known),
             **({'task': int(r['Task']), 'ref': task_ref(int(r['Task']))} if r.get('Task') else {})}
            for r in store._rows('SELECT Site, User, SavedAt, SavedBy, LastUsed, Totp, Extra, Task FROM signin_vault ORDER BY Site')]


def reveal(store, site) -> str | None:
    "The saved password for `site`, opened from its seal for the owner's own eyes (Settings -> Saved sign-ins, Show) - None when none is kept."
    from . import vault
    row = saved(store, site)
    if not row: return None
    store.audit('signin', 0, 'signin_revealed', 'owner', detail={'site': str(site).lower()})
    return vault.unseal(row['Secret'])


def extra_of(row) -> dict:
    "The other boxes a saved sign-in fills, {label: value}, opened from its seal - {} when it keeps none or it will not open here."
    from . import vault
    raw = vault.unseal((row or {}).get('Extra') or '') if (row or {}).get('Extra') else ''
    try: d = json.loads(raw) if raw else {}
    except ValueError: d = {}
    return {str(k): str(v) for k, v in d.items() if str(k).strip() and str(v)} if isinstance(d, dict) else {}


def _seal_key(key) -> str:
    "An authenticator key, checked and sealed - or ValueError. Never kept in the clear, as a password is not."
    from . import totp, vault
    k = vault.seal(totp.dumps(totp.parse(key)))
    if not vault.sealed(k): raise ValueError('this computer has no keychain to seal it in, so it was not saved')
    return k


def save(store, site, user, pw, by='owner', key=None, extra=None, keep_old=False, task=None):
    """Keep a sign-in for `site`, sealed. The site is the one the owner saw on the fill page - pinned there, at save time. `key`: an
    authenticator key to keep with it; None keeps the one already saved (a changed password is not a new authenticator). `extra`: the
    other boxes its form asks for, {label: value} (a "Customer ID"); None keeps the ones already saved."""
    from . import vault
    site = str(site or '').lower()
    if not site or registrable(site) != site: raise ValueError('that is not a site a sign-in can be kept for')
    if not pw: raise ValueError('there is no password to keep')
    k = _seal_key(key) if key else None
    ex = {str(a).strip()[:60]: str(b)[:256] for a, b in (extra or {}).items() if str(a).strip() and str(b)} if extra is not None else None
    x = vault.seal(json.dumps(ex)) if ex else None
    if x and not vault.sealed(x): raise ValueError('this computer has no keychain to seal it in, so it was not saved')
    u, p = vault.seal(user or '') if user else '', vault.seal(pw)
    # sealed or not at all: a password vault that falls back to plain text in the database is worse than none
    if not vault.sealed(p): raise ValueError('this computer has no keychain to seal it in, so it was not saved')
    _tables(store)
    old = saved(store, site) or {}
    store._exec('INSERT OR REPLACE INTO signin_vault (Site, User, Secret, Totp, Extra, SavedAt, SavedBy, LastUsed, Task) VALUES (?,?,?,?,?,?,?,?,?)',
                (site, u, p, k or old.get('Totp'), x if ex is not None else old.get('Extra'), _now(), by, None, int(task) if task else None))
    # ...`keep_old`: a row that may yet be put back (a sign-up the site has not answered) keeps the secrets it replaced until it is - on macOS
    # a sealed secret is a keychain entry, and forgetting it here left the put-back row pointing at nothing (CI, 2026-11-19)
    if not keep_old: forget_row(old, k, ex)
    store.audit('signin', 0, 'signin_saved', by, detail={'site': site, **({'code': True} if k else {})})
    if by not in MADE_BY:                    # ...his own sign-in is an account he has: on the record (an agent's waits for a site to take it)
        from . import ledger
        ledger.account(store, site, user or '', 'given', task, by='owner')


def set_key(store, site, key, by='owner') -> bool:
    """Settings -> Saved sign-ins: keep (or, with '', drop) the authenticator key of a sign-in already saved. False: none is saved
    for that site - a key alone would type a code into a sign-in the owner never kept."""
    from . import vault
    site = str(site or '').lower()
    row = saved(store, site)
    if not row: return False
    k = _seal_key(key) if key else None
    store._exec('UPDATE signin_vault SET Totp=? WHERE Site=?', (k, site))
    vault.forget(row.get('Totp'))
    store.audit('signin', 0, 'signin_code_saved' if k else 'signin_code_removed', by, detail={'site': site})
    return True


def remove(store, site, by='owner') -> dict | None:
    """Forget a saved sign-in AND what it left behind: the sealed row, and that site's cookies in the browser's kept state. One press,
    no question (the owner, 2026-11-14) - and taken back by the Undo line every Remove leaves (2026-11-15, recentlydeleted.remove_signin):
    the row is out of the vault at once and kept sealed for the line's minutes, its keychain entries forgotten only when they pass. The
    browser is signed out now either way - Undo brings the saved sign-in back, and the next visit types it. The Remove's answer
    ({deleted, title, kind}; no `deleted` where only cookies were left), or None when nothing was kept for the site."""
    from . import browserview, recentlydeleted
    site = str(site or '').lower()
    _tables(store)
    row = store._one('SELECT * FROM signin_vault WHERE Site=?', (site,))
    out = recentlydeleted.remove_signin(store, row) if row else None
    n = browserview.forget_site(site)
    _forget_live(site)
    store.audit('signin', 0, 'signin_removed', by, detail={'site': site, 'had_saved': bool(row), 'cookie_files': n})
    return out or ({'title': site, 'kind': 'signin'} if n else None)


def _forget_live(site):
    from . import browserview, terminal as term
    for sid in list(term.SESSIONS):
        if not browserview.state(sid).get('open'): continue
        try:
            c = connect(sid)
            try: c.forget(site)
            finally: c.close()
        except Exception as e: logger.debug(f'signin: {site} cookies not cleared from the live browser of {sid} - {e}')


def _used(store, site, tid=None):
    "The site took the saved sign-in: kept on its row, and the account on the record (ledger.account)."
    from . import ledger
    store._exec('UPDATE signin_vault SET LastUsed=? WHERE Site=?', (_now(), site))
    row = saved(store, site) or {}
    ledger.account(store, site, _user(row), 'signed_in', tid or row.get('Task'), by='agent' if row.get('SavedBy') in MADE_BY else 'owner')


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


def row_of(store, tok) -> dict | None:
    "The link's row whatever its state - used, expired or good - so the page can say which (gone_html)."
    _tables(store)
    return store._one('SELECT * FROM signin_token WHERE TokenHash=?', (_hash(tok),)) if tok else None


def for_line(store, tid) -> str:
    """'for TQ-0001 · Pay the toll (Claude Code)' - the fill page opens outside the app, so it says which task and which agent the password
    goes to: with two tasks on one portal, or a tab left from earlier, the owner could not tell (2026-10-25)."""
    from .store import task_ref
    from . import workerstate as ws
    if not tid: return ''
    t, sess = store.get_task(tid) or {}, ws._live(tid)
    who = str(getattr(sess, 'provider', '') or getattr(sess, 'label', '') or '') if sess else ''
    # ...the agent's name after a dash: "(Claude Code (on this computer))" read as a typo on the one page about a password (2026-11-03)
    return f"for {task_ref(tid)} · {t.get('Title') or 'a task'}" + (f' - {who}' if who else '')


def gone_why(store, tok) -> tuple:
    "(why, tid) of a link that can no longer be used: used, and when - or expired, and how long one lasts."
    r = row_of(store, tok)
    if not r: return 'This sign-in page is not one Taskuary made, or it is long gone.', None
    if r.get('UsedAt'): return f"This sign-in page was used already, at {time.strftime('%H:%M', time.localtime(r['UsedAt']))}.", r['TaskId']
    return f'This sign-in page has expired - one lasts {TTL // 60} minutes.', r['TaskId']


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
    return {'site': ask_site(r['request_id']), 'sid': str(r.get('sid') or ''), 'request_id': r['request_id'], 'text': r.get('text')}


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


def on_signin_page(sid: str, conn=None) -> bool:
    """The agent's browser is open, on a page a password may be typed on (site_of), showing a password box - a sign-in nobody raised.
    `conn`: the DevTools connection (tests stand one in). False whenever the page cannot be read."""
    from . import browserview
    st = browserview.state(sid, fresh=True)
    if not st.get('open') or not site_of(st.get('url')): return False
    c = conn or connect(sid)
    try: f = c.fields('') or {}
    finally:
        if conn is None: c.close()
    return bool(f.get('top') and (f.get('password') or code_step(f)))      # ...or its code box: the second step of one is a sign-in page too


def shows_signin(sid: str, conn=None):
    "Does the page show a box a sign-in fills - a password, a user name, a code? None when it cannot be read."
    try:
        c = conn or connect(sid)
        try: f = c.fields('') or {}
        finally:
            if conn is None: c.close()
    except Exception: return None
    return bool(f.get('top') and (f.get('password') or f.get('user') or code_step(f)))


def set_aside(store, tid: int, sid: str) -> bool:
    """Did the owner's newest words to this agent overtake an open sign-in ask - he answered it in words, not on the page? Then a turn that
    ends with the page still on its sign-in does not put it back in front of him by itself (recorded on a real site, 2026-11-15: "leave
    it for today", the agent left it - and the page was shown him again, "sign in to continue"). The agent may still ask, in its own words."""
    from . import workerstate as ws
    evs = ws.events(store, tid, sid)
    spoke = max((i for i, e in enumerate(evs) if e['Kind'] == 'working' and e.get('Text') != ws.WAKE), default=-1)
    return spoke >= 0 and any(str(r.get('RequestId') or '').startswith(PREFIX) for r in ws.open_requests(evs[:spoke]))


def on_password_page(sid: str) -> bool:
    try:
        c = connect(sid)
        try: return bool((c.fields('') or {}).get('password'))
        finally: c.close()
    except Exception: return False


def holds_password(sid: str, conn=None) -> bool:
    """Does a password box of the page the browser is on hold one now - typed by Taskuary (a sign-in, a sign-up waiting for his press) or by
    him? True too when the page cannot be read: what a script would read there is then not known to be no secret."""
    try:
        c = conn or connect(sid)
        try: return bool(c.js("(() => { " + DEEP + " return deepAll('input[type=password]').some((e) => !!e.value); })()"))
        finally:
            if conn is None: c.close()
    except Exception: return True


def asks_code(sid: str, conn=None) -> bool:
    "Is the page the browser is on asking for a sign-in code? False whenever it cannot be read."
    try:
        c = conn or connect(sid)
        try: f = c.fields('') or {}
        finally:
            if conn is None: c.close()
    except Exception: return False
    return bool(f.get('top') and code_step(f))


# A CODE STEP, BY THE PAGE'S OWN SHAPE: the box it marks as a one-time code, or a code split over a row of small numeric boxes - one per
# digit, unnamed (FIELDS `digits`). The second was not seen at all: a real site's code page read as "no password box, no user box, no code
# box", so the sign-in was called through the moment its password page gave way to the code page (the owner's own sign-in, 2026-11-14).
CODE_ROW = 4
def code_step(f: dict) -> bool: return bool((f or {}).get('otp') or ((f or {}).get('digits') or 0) >= CODE_ROW)


def _ask(store, tid, sid, site, rid, text, watch):
    "The owner's step on the page: the ask in the task, and the page watched for what he sends there (watch) - sign-in and sign-up alike."
    from . import workerstate as ws
    ws.record(store, tid, sid, 'input_needed', request_id=rid, text=text, choices=None, source='api')
    if watch: threading.Thread(target=watch, args=(store, tid, sid, site, rid), daemon=True, name=f'signin-watch-{tid}').start()


# A HAND-OVER NAMES THE SITE AS HE KNOWS IT (design round 5, 2026-11-19: "Sign in to 127.0.0.6 to continue" over a vendor's sign-up page): a
# site reached by a bare address is called by its page's own title; a named one by its name. What a fill is pinned to stays the address
def page_name(sid: str, site: str) -> str:
    if not _ip(site): return site
    try:
        c = connect(sid)
        try: got = json.loads(c.js("JSON.stringify([document.title, document.querySelector('meta[property=\'og:site_name\']')?.content || '', "
                                   "location.href])") or '[]')
        finally: c.close()
    except Exception: got = []
    t, named, href = ([' '.join(str(x or '').split()) for x in got] + ['', '', ''])[:3]
    return (brand_of(t, href) or named or t)[:60] or site
# ...THE SITE'S NAME, NOT THE PAGE'S (round 2, 2026-11-22: "Sign in to Sign in - DealFlow Pro to continue"): a title is the page and the site
# around a separator, either way round ("PermitWatch — Create your account", "Payment | DealFlow Pro"). The site is the part its own address
# spells (/s/permitwatch/..., dealflow.local) - read off the structure, no words judged; '' where no part is
TITLE_PARTS = re.compile(r'\s+[-|·—–]\s+')
def brand_of(title: str, href: str = '') -> str:
    parts, at = [x.strip() for x in TITLE_PARTS.split(str(title or '')) if x.strip()], re.sub(r'[^a-z0-9]', '', str(href or '').lower())
    if len(parts) < 2: return ''
    return next((x for x in parts if len(k := re.sub(r'[^a-z0-9]', '', x.lower())) >= 3 and (k in at or any(w in at for w in re.findall(r'[a-z0-9]{4,}', x.lower()) if w == k[:len(w)]))), '')


HANDED_ON = 6
def needs(store, tid: int, sid: str, claimed: str = '', fill=None, watch=..., what: str = '', ended: bool = True) -> dict:
    """The agent ended its turn asking to be signed in. Record the ask on the existing road and, when the owner keeps a sign-in for
    the site the browser is actually on, fill it at once on its own thread. `fill`: the filler (tests stand one in). `what`: the step in the
    agent's own words, where it handed the page over as its turn (browserview.your_turn) - the ask says that, never "sign in". `ended`: the turn
    ended on the ask, so its answer only handed the sign-in over and is taken back as a step (conversation.take_back) - never a turn that goes on
    (walk 10: hand_over mid-turn, and that turn's closing words, all it had done and why it stopped, never reached the chat)."""
    from . import browserview, workerstate as ws
    if watch is ...: watch = globals()['watch']
    st = browserview.state(sid, fresh=True)
    site, said = (site_of(st.get('url')) if st.get('open') else ''), clean_claim(claimed)
    if not site:
        # no page to sign in on (or not one a password goes to): the owner reads the agent's words, and no fill is ever offered
        # ...said as what to DO (2026-10-25): "a sign-in page Taskuary can fill" explained the app, and plain-http portals are common
        # ...and a sign-up is asked as one: "Sign in to ... then say Signed in" stood over a sign-up form on plain http
        up = signing_up(claimed)
        do, then, page = ('Sign up on', 'Signed up', 'sign-up') if up else ('Sign in to', DONE, 'sign-in')
        text = (f"{do} {said or 'the site'} yourself in the browser pane, then say {then} - Taskuary only types passwords into "
                "secure (https) pages" if st.get('open') and st.get('url') and not str(st.get('url')).startswith('about:') else
                f"{do} {said or 'the site'} to continue - the agent has no {page} page open; ask it to open one")
        ws.record(store, tid, sid, 'input_needed', request_id=ws.request_id_for(text), text=text, choices=[then] if _chat(sid) else None,
                  source='api')
        return {'site': '', 'auto': False}
    # A SIGN-UP (the agent's own marker said so - signing_up): Taskuary makes the password, types it and keeps it - nobody is asked
    # ...A FRESH ID FOR A SIGN-IN ASKED AGAIN (round 3, 2026-11-22: a second hand-over on the same site was recorded under the answered one -
    # "nothing waits on you" on screen while the agent waited on him, a dead end)
    rid = ws.fresh_id(store, tid, f'{PREFIX}{site}')
    if signing_up(claimed): return new_account(store, tid, sid, site, rid, fill, watch)
    name = site_name(site, sid)
    what = ' '.join(str(what or '').split()).rstrip('.')
    text = f'{ws.NAMED_STEP} on {name}: {what}' if what else f'Sign in to {name} to continue'      # ...named: the page says these words (workerstate)
    # "Signed in" as a CHOICE only where an answer arrives as words (the chat's own agent): a pty's choices are a chooser, answered
    # by number (workerstate.answer). A pty's ask still has the press - the card draws it for every `signin:` ask, and its answer goes
    # through signed_in, never the chooser (2026-10-25)
    # NO PRESSES ON IT (the owner, 2026-11-03: "remove that stupid box again ... just have the question and link to fill it out securely"):
    # the ask is its words; Taskuary sees the sign-in happen on the page itself (watch), and "done" typed in the chat's box still tells it
    def ask(said=None): _ask(store, tid, sid, site, rid, said or text, watch)
    row, last = saved(store, site), _TRIED.get((tid, site), 0)
    # ...A PAGE THAT ASKS ONLY THE CODE is his step at once, however lately the saved sign-in was typed (its agent made it ready, READY_CODE):
    # not a sign-in "asked again within minutes"
    if row and last and _now() - last < AGAIN and not _code_of(row.get('Totp')) and asks_code(sid) and not on_password_page(sid):
        # ...and the turn that made it ready is a step, not an answer ("I need the site signed in to go on" stood in the chat, 2026-11-15)
        if ended and _chat(sid):
            from . import conversation
            conversation.take_back(store, tid, why=f'Made the code page of {site} ready for you.', since=_now(), ahead=True)
        return ask(CODE_ASK.format(site=site)) or {'site': site, 'auto': False}
    # A SAVED SIGN-IN GOES STRAIGHT IN, AND NOTHING IS ASKED (the owner, 2026-11-05: "once you have that saved it should save the login and
    # next time just go in and get the data"). The open `signin:` ask is what puts the browser on the owner's screen; raised before the
    # fill, it drew the pane for the seconds the server typed - for a step the owner had nothing to do in. It is raised only when the
    # fill fails, and then the owner is the way on.
    # ...or kept anew since it was last tried (the agent reset it, or signed up again): that one has not been tried
    if row and (_now() - last >= AGAIN or (row.get('SavedAt') or 0) > last):
        _TRIED[(tid, site)] = _now()
        # ...AND THE TASK IS AT WORK WHILE IT IS TYPED, as it is from a mail's hand-over to its pass (general.hand - the one mark): the agent's
        # turn had ended and nothing of its own ran, so for those seconds the header read "agent done" with Mark done lit (2026-11-14)
        from . import general
        def typed(*a):
            try: _auto(*a)
            finally:
                # ...UNTIL IT HAS HANDED ON (watched on the real CLI, 2026-11-15): the agent is told "signed in" and its turn begins a beat
                # later - for those 2-3 s the task read "agent waiting on you" over a turn with no words, the rail "Finished ...; nothing
                # since". Held until that turn is at work or the sign-in is the owner's to do (its ask is up), never past HANDED_ON seconds
                end = time.time() + HANDED_ON
                # ...which is exactly while "signed in" is the last thing its record holds (_continue's `answered`): the turn that hears it
                # writes the next line, and a turn that ran inside the telling has ended already - held past it, the task read "agent
                # waiting on you" for six seconds after the agent had finished (watched on the real CLI, 2026-11-15)
                # (...on a session that can say its own phase: a stand-in that cannot writes no line of its own, and would be waited out whole)
                from . import workerstate as ws
                told = lambda: (evs := ws.events(store, tid, sid)) and evs[-1]['Kind'] == 'answered'
                while time.time() < end and callable(getattr(general._live_of(tid), 'phase', None)) and told(): time.sleep(.1)
                general.hand(tid, -1)
        general.hand(tid)
        threading.Thread(target=typed, args=(store, tid, sid, site, rid, fill or type_in, ask, ended), daemon=True, name=f'signin-{tid}').start()
        return {'site': site, 'auto': True}
    ask()
    if row:
        store.add_comment(tid, 'taskuary', 'agent', f'{site} asked to sign in again within minutes of the saved sign-in - it may be out '
                                                    'of date, so it was not tried twice. Sign in yourself, or update it on the fill page.')
    return {'site': site, 'auto': False}


def _auto(store, tid, sid, site, rid, fill, ask=None, ended=True):
    """Type the saved sign-in. `ask`: raises the owner's ask - called only when the fill did not go in."""
    from . import conversation, vault
    row = saved(store, site) or {}
    # THE ANSWER THAT ONLY HANDED THE SIGN-IN OVER IS A STEP FROM NOW, not once the typing is done: for those seconds it stood in the chat as
    # the agent's answer - "I have no saved sign-in for it ... once the sign-in is done" - untrue, and gone a beat later (recorded 2026-11-14)
    back = lambda why: ended and _chat(sid) and conversation.take_back(store, tid, why=why, since=_TRIED.get((tid, site), 0), ahead=True)
    back(f'Signing in to {site} with the saved sign-in.')
    try:
        user, pw = vault.unseal(row.get('User') or '') or '', vault.unseal(row.get('Secret') or '')
        if not pw: raise SignInError('the saved password could not be opened on this computer')
        code = _code_of(row.get('Totp'))
        ex = extra_of(row)
        # ...A PAGE THAT ASKS ONLY THE CODE, and none is kept: nothing of the saved sign-in is typed - the code is his, said in one line
        # (the owner's own sign-in, 2026-11-14: the agent asked again on the code page, the saved sign-in was tried on it, "there is no
        # sign-in form", and the task read "the saved sign-in was not used")
        if ask and not code and asks_code(sid) and not on_password_page(sid): return _ready_code(store, tid, sid, site) or ask(CODE_ASK.format(site=site))
        typing(store, tid, site, sid)
        got = fill(sid, site, user, pw, **({'code': code} if code else {}), **({'extra': ex} if ex else {})) or {}
        _used(store, site, tid)
        # THE PASSWORD WENT IN AND THE SITE ASKS A CODE NOBODY KEEPS: that step is the owner's, on the page, and it is said in one line - the
        # agent is not told "signed in" over a code prompt (the recorded walk, 2026-11-11: it was, read the page, said so and ended; nothing
        # was asked of anyone)
        if ask and not got.get('code') and asks_code(sid):
            _audit(store, tid, site, 'vault', True, 'a code was asked')
            back(f'Typed the saved sign-in for {site} - it asks for a code next.')
            return _ready_code(store, tid, sid, site) or ask(CODE_ASK.format(site=site))
        _audit(store, tid, site, 'vault', True, code=bool(got.get('code')) if code else None)
        # ...and the answer that only handed the sign-in over ("once you have signed in...") is a step of the work: nobody was asked to
        back(f"Signed in to {site} with the saved sign-in{' and its authenticator code' if got.get('code') else ''}.")
        _continue(store, tid, rid, site, 'taskuary', bool(got.get('code')))
    except NotAccepted as e:
        # A SAVED SIGN-IN THE SITE REFUSED GOES BACK TO THE AGENT (design round 4, 2026-11-19): it was handed to him - "sign in on the page" - for
        # an account the agent itself had made a minute before, whose password he never had. The way past it is the agent's first: the site's
        # reset, a code it emails, a sign-up that never finished. It hands him the page only when only he can do the step
        _audit(store, tid, site, 'vault', False, str(e))
        back(f'The saved sign-in for {site} did not go in.')
        why = str(e) if e.own else f'{site} kept its sign-in form up - the saved password was refused'
        store.add_comment(tid, 'taskuary', 'agent', f'The saved sign-in for {site} did not go in: {why}.')
        _continue(store, tid, rid, site, 'taskuary', words=(f'The saved sign-in for {site} did not go in', f'The saved sign-in for {site} did not go '
                  f"in: {why}. Find the way past it yourself first - the site's own password reset "
                  f'(on its new-password form run `agent-browser '
                  'signup`), a code it emails (Taskuary types it), or a sign-up that never finished. Only a step nobody but the owner can do is '
                  'handed to them, with hand_over.'))
    except Exception as e:
        why = str(e) if isinstance(e, SignInError) else 'the browser could not be reached'
        _audit(store, tid, site, 'vault', False, why)
        back(f'The saved sign-in for {site} was not used.')
        store.add_comment(tid, 'taskuary', 'agent', f'The saved sign-in for {site} was not used: {why}. Sign in yourself to continue.')
        if ask: ask()


def _ready_code(store, tid, sid, site) -> bool:
    "The chat's agent makes the code page ready (READY_CODE) and hands it over (hand_over) - needs() then gives him the step. False: no chat to tell."
    from . import workerstate as ws
    sess = ws._live(tid)
    if not sess or not hasattr(sess, 'send_prompt') or getattr(sess, 'sid', sid) != sid: return False
    try: sess.send_prompt(READY_CODE.format(site=site), as_owner=False); return True
    except Exception as e: logger.info(f'task {tid}: the code page was not made ready by its agent - {e}'); return False


def _code_of(key):
    """What types the code: a function the filler calls at the moment it types, so the code is the one current THEN - and one in
    its last seconds is waited out, never typed to arrive stale. `key` is sealed (a saved row's) or as the owner typed it. None
    when there is none, or it will not open on this computer."""
    from . import totp, vault
    raw = vault.unseal(key) if key else ''
    if not raw: return None
    try: totp.loads(raw) if raw.lstrip().startswith('{') else totp.parse(raw)
    except (ValueError, KeyError, TypeError): return None
    return lambda: totp.current(raw)


def by_owner(store, tok, user, pw, keep: bool, fill=None, key: str = '') -> dict:
    """The fill page's Sign in: spend the link, type it into the task's browser, keep it sealed when asked, and tell the agent. `key`:
    an authenticator key typed on the page - its code goes in this time, and it is kept with the sign-in when that is."""
    from . import totp
    key = str(key or '').strip()
    if key: totp.parse(key)                                  # a mistyped key is said before the link is spent, not after
    r = take(store, tok)
    if not r: raise LookupError('this sign-in link was used already or has expired - open a new one from the task')
    tid, site = r['TaskId'], r['Site']
    if not pw: raise ValueError('type the password')
    code = _code_of(key or (saved(store, site) or {}).get('Totp'))
    ex = extra_of(saved(store, site))            # the other boxes the site's saved sign-in keeps, filled with what is typed here
    try: got = (fill or type_in)(r['Sid'], site, user, pw, **({'code': code} if code else {}), **({'extra': ex} if ex else {})) or {}
    except NotAccepted as e:
        # nothing saved, nobody told "signed in" - the ask stays, and the form comes back on a fresh link with the reason
        _audit(store, tid, site, 'typed', False, str(e))
        e.again = mint(store, tid, r['Sid'], site, r['RequestId']); raise
    except SignInError as e:
        _audit(store, tid, site, 'typed', False, str(e)); raise
    except Exception:
        _audit(store, tid, site, 'typed', False, 'the browser could not be reached')
        raise SignInError("the task's browser could not be reached - is the task still open?")
    kept = ''
    if keep:
        try: save(store, site, user, pw, key=key or None); kept = 'saved'
        except ValueError as e: kept = str(e)
    _audit(store, tid, site, 'typed', True, saved=kept == 'saved', code=bool(got.get('code')) if code else None)
    from . import workerstate as ws
    told = ws._live(tid) is not None            # what the done page may promise: "the agent goes on" only with an agent to tell
    threading.Thread(target=_continue, args=(store, tid, r['RequestId'], site, 'owner', bool(got.get('code'))), daemon=True).start()
    return {'site': site, 'task': tid, 'saved': kept == 'saved', 'kept': kept, 'told': told}


# WHO SIGNED IN IS SAID, to the agent and on the task alike (the browser round, 2026-11-15): told only "Signed in to <site> - continue." after
# the saved sign-in went in unseen, the agent wrote "which I read after you signed in" to an owner who had touched nothing
def signed_in_words(site: str, actor: str, code: bool = False) -> tuple[str, str]:
    "(the task's receipt, what the agent is told) for a sign-in that went in - by Taskuary from the saved sign-in, or by the owner on the page."
    if actor == 'owner': return f'Signed in to {site}', f'{DONE} to {site} - continue. The owner signed in on the page themselves.'
    how = f"the owner's saved sign-in{' and its authenticator code' if code else ''}"
    return (f'Signed in to {site} with the saved sign-in{" and its authenticator code" if code else ""}',
            f'{DONE} to {site} - continue. Taskuary signed in with {how}; the owner did nothing on the page.')


def _continue(store, tid, rid, site, actor, code=False, words=None):
    """Tell the agent - the words it was promised, nothing else - and close the ask. Not workerstate.answer: that answers a pty's
    question with choices by its NUMBER, and "1" typed into a CLI's prompt is not "you are signed in"."""
    from . import terminal as term, workerstate as ws
    # the receipt (2026-10-25): that a code went in too, so the owner knows the vault answered the site's second question
    sess, (did, said) = ws._live(tid), words or signed_in_words(site, actor, code)
    from . import browserview
    if sess and getattr(sess, 'sid', None): browserview.keep_soon(sess.sid)     # past the sign-in: what the site set is kept now (keep)
    if not sess:
        store.add_comment(tid, actor, 'agent', f'{did}, but no agent is running on this task to tell - open it to continue.')
        return False
    if term.stranger_now(store, tid, sess): return False             # the task says why nothing went in
    # ...and the chat shows what woke the agent's next answer (the owner, 2026-11-05: "why is there taskuary twice"): a short trigger line
    try:
        from .general import BRIEF_ACTOR, USER_TYPE
        if hasattr(sess, 'send_prompt'): store.add_comment(tid, BRIEF_ACTOR, USER_TYPE, f'{did}.')
    except Exception as e: logger.debug(f'signin: the trigger line for task {tid} was not filed - {e}')
    # THE ASK IS OVER THE MOMENT THE SIGN-IN IS PAST, not when the agent's next turn ends (the recorded walk, 2026-11-11: a chat agent's turn
    # runs inside this call, so all the while it worked the task still read "Sign in to ... to continue" and the page beside it "your turn")
    ws.record(store, tid, sess.sid, 'answered', request_id=rid, text=DONE, source='owner' if actor == 'owner' else 'api')
    try:
        # ...once: a turn that ends after this moment - his line's, begun while the sign-in went in - has worked the page signed in
        from .general import GeneralSession
        # ...and a turn still at work - it handed the sign-in over and went on with the job (browserview.hand_over) - hears it in that turn
        if isinstance(sess, GeneralSession) and getattr(sess, 'busy', False) and sess.steer(said): pass
        elif hasattr(sess, 'send_prompt'): sess.send_prompt(said, as_owner=False, **({'since': time.time()} if isinstance(sess, GeneralSession) else {}))
        else: term.type_into(sess, said, brief=True)      # Taskuary's, never the owner's line
    except Exception as e:
        logger.warning(f'signin: task {tid} signed in to {site}, but the agent was not told - {e}')
        store.add_comment(tid, actor, 'agent', f'{did}, but the agent could not be told - say "{said}" to it.')
        return False
    store.add_comment(tid, actor, 'agent', f'{did} - the agent goes on.')
    return True


SAID_DONE = frozenset(('signed in', 'done', "i'm signed in", 'i am signed in', 'i signed in', 'logged in', "i'm in", 'im in'))


def said_done(rid, text) -> bool:
    "Is this the owner saying they signed in - \"Signed in\", or \"done\" typed in the chat's box - to a sign-in ask?"
    return str(rid or '').startswith(PREFIX) and ' '.join(str(text or '').split()).rstrip('.!').lower() in SAID_DONE


def signed_in(store, tid: int, rid: str) -> dict:
    """The owner signed in by hand and said so (workerstate.answer). Told as a fill is (_continue), on every kind of agent: a terminal
    CLI's ask had no Signed in press, only a box to type it in, and the bare words reached its prompt with no site and no "continue"
    (the owner, 2026-10-25: both kinds of agent ask alike)."""
    told = _through(store, tid, rid, ask_site(rid), seen=False)
    return {'delivered': True, 'state': 'delivered'} if told else {'delivered': False, 'state': 'failed', 'why': 'the agent could not be told - see the task'}


def _audit(store, tid, site, how, ok, why='', saved=None, code=None, signup=False):
    d = {'site': site, 'how': how, 'ok': bool(ok), **({'why': why} if why else {}), **({'saved': saved} if saved is not None else {}),
         **({'code': code} if code is not None else {}), **({'signup': True} if signup else {})}
    store.audit('task', tid, 'signin_fill', 'taskuary' if how == 'vault' else 'owner', 'system' if how == 'vault' else 'human', d)


# ── the owner signs in on the page itself: seen, and what they typed kept ─────────────────────────────────────────────────────
# THE OWNER SIGNS IN IN THE LIVE VIEW, and nothing needs pressing after (the owner, 2026-11-03: "when we have browser it should just save
# what i type in"). While a sign-in ask is open Taskuary holds its own DevTools connection to the task's tab:
# - A SCRIPT IN THE TOP PAGE hears the form being sent (the submit, Enter in a box, a press on a button) and hands Taskuary - over that
#   connection, never the agent's - the user name and, when the form has one, the password. A two-step sign-in sends the user name on its
#   own page first: that is kept in memory (it is not the secret) until the password page is sent.
# - SIGNED IN is the page past the sign-in: on the site, no password box and no user box, at another address than the ask's. Then the
#   agent is told as a fill tells it, and a password typed on the way is SEALED to the vault for that site (save) - the one store - with
#   one line on the task saying so and where to remove it. A password the site refused is never kept: it is only kept once past.
# Nothing typed is logged, put in an event, a comment or the audit; captures while Taskuary itself types a sign-in (FILLING) are ignored.
# A BOX THE PAGE NAMES AS THE USER'S, by its own words: the vault's look at the page (FIELDS) and the owner's typing heard (CAPTURE) read it alike
NAMED = r'/user|mail|login|account|ident|member|customer/i'
CAPTURE = r'''(() => {
  if (window !== window.top || window.__tqSigninHooked) return;
  window.__tqSigninHooked = true;
  const vis = (e) => { const r = e.getBoundingClientRect(); return !e.disabled && r.width > 2 && r.height > 2; };
  const texty = (e) => ['text', 'email', 'tel', ''].includes(e.type);
  const deepAll = (sel) => { const out = []; const walk = (r) => { r.querySelectorAll('*').forEach((e) => {
    if (e.matches(sel)) out.push(e); if (e.shadowRoot) walk(e.shadowRoot); }); }; walk(document); return out; };
  const grab = () => {
    const ins = deepAll('input').filter(vis);
    const pw = ins.find((e) => e.type === 'password' && e.value);
    const before = pw ? ins.slice(0, ins.indexOf(pw)) : ins;
    // ...never a code box: the code typed on the page after the password was heard as the user name, and kept as it
    const coded = (e) => e.autocomplete === 'one-time-code' || /otp|one.?time|totp|2fa|mfa|passcode|verif|auth.*code|security.?code|^code$|^pin$/i
      .test([e.name, e.id, e.getAttribute('aria-label'), e.placeholder].join(' ').trim());
    const user = before.filter((e) => texty(e) && e.value && !coded(e)).pop();
    const h = user && user.getRootNode().host;
    const named = !!user && (''' + NAMED + r'''.test([user.name, user.id, user.autocomplete, user.getAttribute('aria-label'), user.placeholder,
      h && h.id, h && h.getAttribute('name'), h && h.getAttribute('label'), h && h.getAttribute('aria-label')].join(' ')));
    if ((!pw && !user) || typeof __tqSignin !== 'function') return;
    // ...and the form's other boxes the owner filled (a "Customer ID"), by their label - kept with the sign-in, filled by it next time
    const labelOf = (e) => { const r = e.getRootNode(), h = r && r.host, l = e.labels && e.labels[0];
      return String((l && l.textContent) || e.getAttribute('aria-label') || e.placeholder || (h && (h.getAttribute('label') || h.getAttribute('aria-label'))) || e.name || '').trim().slice(0, 40); };
    const o = {}; for (const e of before) if (texty(e) && e !== user && e.value && labelOf(e)) o[labelOf(e)] = e.value;
    try { __tqSignin(JSON.stringify({ u: user ? user.value : '', n: named, p: pw ? pw.value : '', o, href: location.href })); } catch (_) {}
  };
  document.addEventListener('submit', grab, true);
  // ...AND AS IT IS TYPED, not only as the form is sent (the owner's own sign-ins, 2026-11: seen through, and nothing kept). A page sends
  // its form many ways this cannot hear - a control that is no button calling form.submit(), which fires no submit event; a script on a
  // timer; a box that sends itself when it is full - so what stands in the boxes is handed over on every change to one, and as the page goes
  document.addEventListener('input', (e) => { if (e.composedPath().some((x) => x.tagName === 'INPUT')) grab(); }, true);
  document.addEventListener('change', (e) => { if (e.composedPath().some((x) => x.tagName === 'INPUT')) grab(); }, true);
  window.addEventListener('pagehide', grab, true);
  // composedPath: a key or a press inside a component's shadow root reaches the document retargeted to its host
  document.addEventListener('keydown', (e) => { if (e.key === 'Enter' && e.composedPath().some((x) => x.tagName === 'INPUT')) grab(); }, true);
  document.addEventListener('pointerdown', (e) => { if (e.composedPath().some((x) => x.matches && x.matches('button, [type=submit], [role=button], a'))) grab(); }, true);
})()'''
WATCH_FOR = 30 * 60             # a sign-in ask is watched this long, then left to the owner's word
WATCH_EVERY = 1.0
# ...and PAST ONLY ONCE IT STAYS PAST (the owner, 2026-11-05, a site that asks for the user name, then the password on a page of its own: the
# password page, still loading, read as no user box and no password box at another address - "signed in", the agent was woken on the
# password page, and when the owner did sign in nothing was watching any more). This many readings in a row, ~4.5 s at WATCH_EVERY
PAST_STEADY = 3
_TYPED = {}                     # tid -> {'user', 'pw', 'site'}: what the owner sent on the page, until the sign-in is past - memory only
SAVED_LINE = 'Saved your {site} sign-in to the vault - remove it under {where}.'
MADE_LINE = 'Kept the {site} account{who} the agent made in {where} - its password is there for you.'
def made_line(store, tid, site: str, user: str = '') -> None:
    "The task says, once, that an account its agent made is kept and where he reads its password (one vault - listing)."
    from . import words
    store.add_comment_once(int(tid), 'taskuary', 'agent', MADE_LINE.format(site=site, who=f' ({user})' if user else '', where=words.name('signins')))


def heard(tid, site: str, raw) -> bool:
    """One capture from the page: kept for the task when it came from the pinned site's top page. Never logged."""
    from . import browserview
    try: d = json.loads(raw) if isinstance(raw, str) else dict(raw or {})
    except (ValueError, TypeError): return False
    if not on_site(d.get('href'), site): return False
    cur = _TYPED.setdefault(tid, {'site': site, 'user': '', 'pw': ''})
    if cur.get('site') != site: cur.update(site=site, user='', pw='')
    # ...and once the password is held, a box typed into WITHOUT one is no user name: the page after the password asks a code, a search
    if d.get('u') and (d.get('p') or not cur.get('pw')): cur['user'], cur['named'] = str(d['u'])[:256], bool(d.get('n'))
    if d.get('p'): cur['pw'] = str(d['p'])[:512]
    if isinstance(d.get('o'), dict) and d['o']:
        cur['extra'] = {str(k)[:60]: str(v)[:256] for k, v in list(d['o'].items())[:5] if str(k).strip() and str(v)}
    return True


def past(f: dict, site: str, start: str) -> bool:
    "Is the page past the sign-in: on the site, no password or user box, and not the page the ask was made on?"
    if not f or not f.get('top') or not on_site(f.get('href'), site): return False
    # ...THROUGH IS EVERY STEP LEFT BEHIND, never one step giving way to the next (the owner, 2026-11-14: "it took it back when it started
    # 2fa, then quickly reopened it ... then I got through and it did not automatically take it back"): no password box, no code step
    # (code_step), no box the page itself names as the user's. A lone unnamed box is no step once the page has moved - the page behind a
    # sign-in has a search box, and read as "a user box" it kept the sign-in open for good. And a page that moves by its fragment has moved.
    return not f.get('password') and not code_step(f) and not f.get('named') and str(f.get('href') or '') != str(start or '')


def keep_typed(store, tid, site) -> bool:
    "The sign-in is past: seal what the owner typed for the site, and say so in one line. False when no password was typed."
    t = _TYPED.pop(tid, None) or {}
    if t.get('site') != site or not t.get('pw'): return False
    try: save(store, site, t.get('user') or '', t['pw'], by='owner', extra=t.get('extra') or None)
    except ValueError as e:
        store.add_comment(tid, 'taskuary', 'agent', f'Your {site} sign-in was not saved: {_said(e)}.'); return False
    store.add_comment(tid, 'taskuary', 'agent', SAVED_LINE.format(site=site, where=words.name('signins')))
    return True


def _asked(store, tid, rid) -> bool: return (pending(store, tid) or {}).get('request_id') == rid


# A CODE THE SITE EMAILED (the real-CLI walk, 2026-11-16): signed up, the site sent "Your code is 383972" to his inbox and asked for it on
# its page. Triage filed the mail, the task kept saying "press its button" over a code page, and nobody knew the code was in the inbox. While
# the ask is watched, a mail from the page's own site that came in since holds the code: typed on the pinned page like an authenticator's
# (the agent never sees it), the mail named on the task by its subject. A mail with no single code is his to read, said in one line. The
# mail stays where triage filed it: put on the task, a site's no-reply mail made his own task a stranger's, held until he trusted the site.
CODE_RE = re.compile(r'(?<![\w-])\d{4,8}(?![\w-])')
CODE_SYSTEM = ('A site sent this email while the owner was signing in or signing up there. Which of the numbers listed is the one-time code '
               '(verification, sign-in or security code) the site asks to be typed? Answer JSON {"code": "<that number exactly as listed>"}, '
               'or {"code": ""} when none of them is one.')
CODE_WANT = {'type': 'object', 'properties': {'code': {'type': 'string'}}, 'required': ['code']}


def _pick_code(store, text: str, found: set, brain=None) -> str:
    """WHICH NUMBER IS THE CODE, when the mail holds several - the footer's year, a street address, a zip (real code mails all do): the model's
    to read, and only one of the numbers the mail holds may come back. '' - no AI, or no clear answer: his to read."""
    from .llm import build_llm, ask_json
    from .terminal import fence
    try:
        b = brain or build_llm(store, job='judge')
        if not b: return ''
        v = ask_json(b, CODE_SYSTEM, f"THE EMAIL:\n{fence(text[:4000])}\nTHE NUMBERS IN IT: {', '.join(sorted(found))}", want=CODE_WANT, need=('code',)).data
    except Exception as e: logger.debug(f'signin: no reading of which number a code mail holds - {e}'); return ''
    c = str((v or {}).get('code') or '').strip() if isinstance(v, dict) else ''
    return c if c in found else ''


def mailed_code(store, site: str, after: int, brain=None):
    """(message id, code) of the newest mail from `site` - its sender's registrable domain the page's pinned site - since message `after`,
    and the one code it holds (one code-shaped number, or the one the model reads as the code among several); (message id, '') for one with
    none, or none clear; None for no such mail."""
    for r in store._rows('SELECT MessageId, FromEmail, Subject, BodyText FROM message WHERE MessageId>? ORDER BY MessageId DESC', (int(after or 0),)):
        dom = str(r.get('FromEmail') or '').rsplit('@', 1)[-1]
        if '@' not in str(r.get('FromEmail') or '') or registrable(dom) != site: continue
        text = f"{r.get('Subject') or ''}\n{r.get('BodyText') or ''}"
        found = set(CODE_RE.findall(text))
        return r['MessageId'], (found.pop() if len(found) == 1 else _pick_code(store, text, found, brain) if found else '')
    return None


_TYPING = {}                    # (task, site) -> (the newest mail, when, session) as an act of its agent's went to that site: a code it mails comes after
CODE_FRESH = 10 * 60            # ...and is looked for from there this long; past it, from when the ask's watch begins
CODE_EVERY = 2.0                # the agent's own sign-up: how often its page is looked at for the code step (code_watch)


def _newest_mail(store) -> int: return (store._one('SELECT MAX(MessageId) AS m FROM message') or {}).get('m') or 0


def typing(store, tid, site, sid: str = ''): _TYPING[(int(tid), site)] = (_newest_mail(store), _now(), str(sid or ''))


def mail_since(store, tid, site) -> int:
    """The mail a code for this sign-in can be in: from just before Taskuary typed its password - the site mails the code as the password goes,
    and the code step is raised a turn later (its agent makes the page ready), when the code was in the inbox already - else from now."""
    mid, at, _ = _TYPING.get((int(tid), site), (None, 0, ''))
    return mid if mid is not None and _now() - at < CODE_FRESH else _newest_mail(store)


# THE AGENT'S OWN SIGN-UP COMES BACK AS MAIL (the vendor walks, 2026-11-18): it pressed Create account itself, the site emailed its code, and the
# code landed on his rail as four "unverified sender" FYI rows while the agent asked for it again. An act of the agent's that went to a site
# (browsergate lets it run) is marked here; a mail from that site, holding a code, while it is fresh, is that act returning - kept off the
# inbox (ingest, ahead of triage, as an auto-reply is: triage itself is unchanged) and typed into that site's page only, never shown to the agent.
def acting(store, tid, sid: str, site: str) -> None:
    "An act of this agent's went to `site`: a code it mails from now is the agent's own (take_code). Kept from its first act while fresh."
    if not site or not str(tid or '').isdigit(): return
    k = (int(tid), site)
    if k in _TYPING and _now() - _TYPING[k][1] < CODE_FRESH: _TYPING[k] = (*_TYPING[k][:2], str(sid))
    else: typing(store, tid, site, sid)


_CODE_WATCHED = set()           # (task, site) whose code watch runs
def take_code(store, msg: dict, watch=..., brain=None) -> int | None:
    """The task whose agent's own act this mail answers - its sender the site that agent acted on lately, a code-shaped number in it - with its
    code watch started (code_watch); else None."""
    frm, text = str(msg.get('from_email') or ''), f"{msg.get('subject') or ''}\n{msg.get('body') or ''}"
    if '@' not in frm or not (found := set(CODE_RE.findall(text))): return None
    site = registrable(frm.rsplit('@', 1)[-1])
    tid, sid = next(((t, x) for (t, s), (_, at, x) in list(_TYPING.items()) if s == site and _now() - at < CODE_FRESH), (None, ''))
    if tid is None:
        logger.info(f'signin: a mail from {site} holds a code-shaped number, and no agent acted on {site} lately - it is his mail'); return None
    # ...and only a mail the model reads as a one-time code: an invoice from a site the agent just used holds numbers too, and is his
    if not _pick_code(store, text, found, brain):
        logger.info(f'signin: a mail from {site} came while task {tid} acted there, and was not read as a one-time code - it is his mail'); return None
    if watch is ...: watch = code_watch
    if watch and (tid, site) not in _CODE_WATCHED:
        _CODE_WATCHED.add((tid, site))
        def run():
            try: watch(store, tid, sid, site)
            finally: _CODE_WATCHED.discard((tid, site))
        threading.Thread(target=run, daemon=True, name=f'code-watch-{tid}').start()
    return tid


def code_watch(store, tid: int, sid: str, site: str, every: float = CODE_EVERY, until: float = CODE_FRESH, conn=None, url: str = '') -> bool:
    """While the agent's act on `site` is fresh: when its page there asks for a code and a mail from the site holds one, type it on the pinned
    page (as the sign-in ask's watch does) and tell the agent to look. A sign-in ask open on the site watches for itself (watch). `url`: the code
    page the sign-up left - where the agent has gone on to another site, the code is typed there, in a tab of Taskuary's own (tab_at)."""
    end, after = time.time() + until, mail_since(store, tid, site)
    while time.time() < end:
        time.sleep(every)
        if ask_site((pending(store, tid) or {}).get('request_id')) == site: return False
        got = None
        try:
            c = conn or connect(sid)
            try:
                f = c.fields('')
                here = f.get('top') and on_site(f.get('href'), site) and code_step(f)
                if not here and not (url and conn is None): continue
                if not (got := mailed_code(store, site, after)): continue
                if here: _code_from_mail(store, tid, site, c, *got)
                else:
                    with tab_at(sid, url) as (t, _):
                        if not code_step(t.fields('')): return False          # ...that page asks no code any more: nothing to type
                        _code_from_mail(store, tid, site, t, *got)
            finally:
                if conn is None: c.close()
        except SignInError: continue
        if got[1]:
            from .browsergate import _tell
            _tell(store, tid, f'Taskuary typed the code {site} emailed for your sign-up into its page and sent it. Look at the page and continue.', wake=True)
        return True
    return False


def _code_from_mail(store, tid, site, c, mid, code) -> bool:
    mail = f'"{str((store.get_message(mid) or {}).get("Subject") or "").strip()[:120]}"'
    if not code:
        store.add_comment(tid, 'taskuary', 'agent', f'{site} emailed you {mail} - type its code on the page to continue.')
        return True
    try: _type_code(c, site, lambda: code)
    except SignInError as e:
        store.add_comment(tid, 'taskuary', 'agent', f'{site} emailed you {mail}, and its code could not be typed ({_said(e)}) - type it on the page.')
        return True
    _audit(store, tid, site, 'vault', True, 'the code it emailed', code=True)
    store.add_comment(tid, 'taskuary', 'agent', f'Typed the code {site} emailed you ({mail}).')
    return True


def _through(store, tid, rid, site, seen=True):
    """The sign-in is past - seen on the page (watch), or the owner said so (`seen` False, signed_in): keep what was typed for it, and tell the
    agent once, in words that say who did it."""
    kept = keep_typed(store, tid, site)
    if seen: _audit(store, tid, site, 'page', True, saved=kept)
    # ...AND HIS PRESS IS SAID AS A PRESS (round 3, 2026-11-22: "I'm done" on a sign-up page, nothing typed, told the agent "the owner signed in
    # on the page themselves"): seen on the page, he signed in; only pressed, the agent looks at the page before it goes on
    if not seen: return _continue(store, tid, rid, site, 'owner', words=(f'You pressed {DONE} on {site}', f"The owner pressed {DONE} on the {site} "
                                  "page. Look at the page before you go on - nothing says what, if anything, was done on it."))
    return _continue(store, tid, rid, site, 'owner')


def watch(store, tid: int, sid: str, site: str, rid: str, conn=None, every: float = WATCH_EVERY, until: float = WATCH_FOR):
    """While the ask is open: hear what the owner sends on the page, and when the page is past the sign-in, keep it and tell the agent.
    `conn`: the DevTools connection (tests stand one in)."""
    from . import browserview
    try: c = conn or connect(sid)
    except Exception as e: logger.debug(f'signin: task {tid} is not watched for its {site} sign-in - {e}'); return False
    try:
        try:
            c.call('Runtime.enable'); c.call('Page.enable'); c.call('Runtime.addBinding', {'name': '__tqSignin'})
            c.call('Page.addScriptToEvaluateOnNewDocument', {'source': CAPTURE})
            c.js(CAPTURE)
        except SignInError as e: logger.debug(f'signin: the {site} page of task {tid} could not be listened to - {e}')
        start, end, steady = (c.fields('') or {}).get('href') or '', time.time() + until, 0
        after, coded = mail_since(store, tid, site), False      # mail from here on (mailed_code)
        while time.time() < end and _asked(store, tid, rid):
            time.sleep(every)
            for ev in c.drain():
                if ev.get('method') == 'Runtime.bindingCalled' and (ev.get('params') or {}).get('name') == '__tqSignin' and sid not in browserview.FILLING:
                    heard(tid, site, (ev.get('params') or {}).get('payload'))
            if sid in browserview.FILLING: continue
            try: f = c.fields('')
            except SignInError: continue                         # mid-navigation: the page cannot be read for a moment
            if not coded and code_step(f) and (got := mailed_code(store, site, after)): coded = _code_from_mail(store, tid, site, c, *got)
            steady = steady + 1 if past(f, site, start) else 0
            if steady >= PAST_STEADY and _asked(store, tid, rid): _through(store, tid, rid, site); return True
        return False
    finally:
        _TYPED.pop(tid, None)
        if conn is None: c.close()


# ── typing it: the browser's own DevTools socket, top document only ─────────────────────────────────────────────────────────
_QUIET = logging.getLogger('taskuary.signin.cdp')      # websockets logs frames at DEBUG: never to anything, whatever the root says
_QUIET.addHandler(logging.NullHandler()); _QUIET.propagate = False; _QUIET.disabled = True

# Every field is looked for in THIS document - never a frame's, so a sign-in box another site framed into the page is not one
# Taskuary types into. Visible, enabled and writable only; the user-name box is the text field before the password box.
# ...AND INSIDE ITS COMPONENTS' OPEN SHADOW ROOTS (the browser-agent walk, 2026-11-03): a portal built of web components keeps its User
# ID box in one, querySelectorAll never saw it, and the page read as "no sign-in form" - so the fill page could not type into it.
# A box in a shadow root is named by its host's words too, and the focused box is the one at the bottom of the shadow roots' focus.
DEEP = r'''const deepAll = (sel) => { const out = []; const walk = (r) => { r.querySelectorAll('*').forEach((e) => {
    if (e.matches(sel)) out.push(e); if (e.shadowRoot) walk(e.shadowRoot); }); }; walk(document); return out; };
  const deepActive = () => { let a = document.activeElement; while (a && a.shadowRoot && a.shadowRoot.activeElement) a = a.shadowRoot.activeElement; return a; };
  const hostOf = (e) => { const r = e.getRootNode(); return r && r.host ? r.host : null; };'''
FIELDS = r'''(want) => {
  ''' + DEEP + r'''
  const vis = (e) => { const s = getComputedStyle(e), r = e.getBoundingClientRect();
    return !e.disabled && !e.readOnly && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05 && r.width > 4 && r.height > 4; };
  const ins = deepAll('input').filter(vis);
  const pw = ins.find((e) => e.type === 'password');
  const texty = (e) => ['text', 'email', 'tel', ''].includes(e.type);
  const words = (e) => { const h = hostOf(e); return [e.name, e.id, e.autocomplete, e.getAttribute('aria-label'), e.placeholder,
    h && h.id, h && h.getAttribute('name'), h && h.getAttribute('label'), h && h.getAttribute('aria-label')].join(' '); };
  const named = (e) => ''' + NAMED + r'''.test(words(e));
  const before = pw ? ins.slice(0, ins.indexOf(pw)).filter(texty) : [];
  // ...A BOX THE PAGE MARKS AS A CODE IS NEVER THE USER-NAME BOX (recorded 2026-11-14: a code page's one box, alone on it, read as "a user
  // box" - so the saved sign-in's code prompt was not seen, the agent was told "signed in" over it, and the ask that followed read "sign in")
  const isCode = (e) => e.autocomplete === 'one-time-code' || /otp|one.?time|totp|2fa|mfa|passcode|verif|auth.*code|security.?code|^code$/i.test(words(e).trim());
  const alone = ins.filter((e) => texty(e) && !isCode(e));
  const user = before.reverse().find(named) || before[0] || (!pw && (ins.find((e) => texty(e) && named(e) && !isCode(e)) || (alone.length === 1 ? alone[0] : null)));
  const frames = [...document.querySelectorAll('iframe')].filter(vis).map((e) => e.src || '');
  // A CODE SPLIT OVER ONE BOX PER DIGIT: the longest row of small numeric boxes side by side (digits), told by shape - the page names none
  const small = ins.filter((e) => e !== pw && ['text', 'tel', 'number', ''].includes(e.type) && e.getBoundingClientRect().width <= 90
    && (e.inputMode === 'numeric' || e.inputMode === 'decimal' || e.type === 'tel' || e.type === 'number' || e.maxLength === 1));
  const rows = {}; small.forEach((e) => { const k = Math.round(e.getBoundingClientRect().top / 4); rows[k] = (rows[k] || 0) + 1; });
  const digits = Math.max(0, ...Object.values(rows));
  // THE CODE BOX (2026-10-25): the one the page itself marks as a one-time code, else a short numeric-looking box that names a
  // code - never the user name or password box. A page of six one-digit boxes is not one this types into (not built).
  const coded = (e) => /otp|one.?time|totp|2fa|mfa|passcode|verif|auth.*code|security.?code|^code$/i
    .test(words(e).trim());
  const otp = ins.find((e) => e.autocomplete === 'one-time-code') || (!pw && ins.find((e) => e !== user
    && ['text', 'tel', 'number', ''].includes(e.type) && !(e.maxLength > 0 && e.maxLength < 4) && coded(e))) || null;
  // ...AND WHAT ELSE THE FORM ASKS: a box beside the user name and password - a "Customer ID", a company code - named by its label. The
  // vault fills the ones it keeps (`other:<label>`); one left empty is named when the form stays up, never the password blamed (2026-11-04)
  const labelOf = (e) => { const h = hostOf(e), l = e.labels && e.labels[0];
    return String((l && l.textContent) || e.getAttribute('aria-label') || e.placeholder || (h && (h.getAttribute('label') || h.getAttribute('aria-label'))) || e.name || '').trim().slice(0, 40); };
  const otherEl = String(want).startsWith('other:') ? ins.find((e) => texty(e) && e !== user && labelOf(e).toLowerCase() === String(want).slice(6).toLowerCase()) : null;
  const el = want === 'password' ? pw : want === 'user' ? user : want === 'otp' ? otp : otherEl;
  if (el) { el.focus(); try { el.select(); } catch (_) { el.value = ''; } }
  if (el && want === 'otp') el.setAttribute('data-tq-code', '');
  const others = pw ? ins.filter((e) => texty(e) && e !== user && e !== otp && !e.value).map(labelOf).filter(Boolean) : [];
  return { origin: location.origin, href: location.href, top: window === window.top, password: !!pw, user: !!user, otp: !!otp, frames, others, digits,
           named: !!user && (named(user) || /username|email/.test(user.autocomplete || '')),
           focused: !!el && deepActive() === el };
}'''
CLEAR = "(() => { " + DEEP + " deepAll('input[type=password], input[data-tq-code]').forEach((e) => { e.value = ''; }); })()"
SETTLE = 2.0                    # after the submit, before the boxes are emptied and the agent hears: the page's own post goes first
STILL = "(() => { " + DEEP + " const a = deepActive(); return { href: location.href, password: !!a && a.type === 'password' }; })()"


class Cdp:
    """One DevTools connection to a session's Chrome, attached to the tab the agent is on. A refusal is said by WHICH call, never
    with the call's parameters - one of them is the password."""
    def __init__(self, ws_url: str, target: str, exact: bool = False):
        from websockets.sync.client import connect
        kw = dict(open_timeout=5, max_size=8 * 1024 * 1024, logger=_QUIET)   # no Origin: Chrome refuses a browser-looking client
        try: self.ws = connect(ws_url, proxy=None, **kw)
        except TypeError: self.ws = connect(ws_url, **kw)              # websockets before 15 has no proxy setting
        self.n, self.session, self.events, self.url = 0, None, [], ws_url
        # the tab it is on: a held step names it (browsergate.held_tab) - and attaches to that tab only, `exact`, never a stand-in for it
        self.target = target if exact else self.tab(target)
        self.session = self.call('Target.attachToTarget', {'targetId': self.target, 'flatten': True}, top=True)['sessionId']

    def tab(self, target: str) -> str:
        """The tab to attach to: agent-browser's own word for it when that tab is still there - its .target file is not rewritten every
        time the tab is, and a stale id attached to nothing, so neither a fill nor a watch reached the page (the browser-agent walk,
        2026-11-03) - else the one web page the browser holds, else the first."""
        try: pages = [t for t in self.call('Target.getTargets', top=True).get('targetInfos') or [] if t.get('type') == 'page']
        except SignInError: return target
        if not pages or any(t.get('targetId') == target for t in pages): return target
        web = [t for t in pages if str(t.get('url') or '').startswith(('http://', 'https://'))]
        return (web or pages)[0]['targetId']

    def call(self, method, params=None, top=False, timeout=10.0) -> dict:
        self.n += 1; i = self.n
        m = {'id': i, 'method': method, 'params': params or {}}
        if self.session and not top: m['sessionId'] = self.session
        # ...A SOCKET THAT FAILS IS A BROWSER THAT DID NOT ANSWER, said as one (the vendor walk, 2026-11-19): a page hung on a site that never
        # answered raised the socket's own TimeoutError, which no caller expects - the code watch died on it, and a code the site emailed sat unread
        try: self.ws.send(json.dumps(m))
        except Exception: raise SignInError('the browser did not answer') from None
        end = time.time() + timeout
        while True:
            left = end - time.time()
            if left <= 0: raise SignInError('the browser did not answer in time')
            try: r = json.loads(self.ws.recv(timeout=left))
            except Exception: raise SignInError('the browser did not answer in time') from None
            if r.get('method') == 'Runtime.bindingCalled' and len(self.events) < 200: self.events.append(r)   # the page's own events are not kept
            if r.get('id') == i:
                if 'error' in r: raise SignInError(f'the browser refused {method.split(".")[0]}')
                return r.get('result') or {}

    def js(self, expr: str):
        r = self.call('Runtime.evaluate', {'expression': expr, 'returnByValue': True, 'awaitPromise': True})
        if r.get('exceptionDetails'): raise SignInError('the page did not let Taskuary look at it')
        return (r.get('result') or {}).get('value')

    def fields(self, want=''): return self.js(f'({FIELDS})({json.dumps(want)})') or {}
    def drain(self) -> list:
        "The page's events read so far (a binding's call among them) - and the ones waiting on the socket - each once."
        while True:
            try: r = json.loads(self.ws.recv(timeout=0))
            except Exception: break
            if r.get('method') == 'Runtime.bindingCalled' and len(self.events) < 200: self.events.append(r)
        out, self.events = self.events, []
        return out
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
    # ...read off the Chrome Taskuary started for the session first: asking agent-browser hung while a page it was loading never answered
    if (own := browserview.devtools_url(sid)): return own
    exe = browserview.program()
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
    if want and not f.get('focused'):
        what = want[6:] if want.startswith('other:') else ({"password": "password", "otp": "code"}).get(want, "user name")
        raise SignInError(f'the {what} box on {site} could not be found')
    return f


def _type_code(c: Cdp, site: str, code) -> bool:
    "The code box focused on the pinned site, looked at once more, then the code - made now, not when the sign-in began."
    _guard(c, site, 'otp'); _guard(c, site, 'otp')        # the second is the last look, with the box already focused
    c.type(code()); c.enter()
    return True


def _await_code(c: Cdp, site: str, code, wait: float) -> bool:
    """After the password: type the code when the site's next page asks for one. No prompt within `wait`, the password box back (a
    wrong password), or the page gone to another site - no code is typed, and that is no failure: most sign-ins ask none."""
    end = time.time() + wait
    while time.time() < end:
        time.sleep(.5)
        try: f = _guard(c, site, '')
        except SignInError as e:
            if 'no longer on' in str(e): return False
            continue                                         # mid-navigation: the page cannot be read for a moment
        if f.get('otp'): return _type_code(c, site, code)
        if f.get('password'): return False
    return False


def _fill_others(c: Cdp, site: str, f: dict, extra: dict) -> list:
    "Type the saved other boxes the page shows (by label, case aside); the labels of the ones it shows that none was saved for."
    keep = {str(k).strip().lower(): v for k, v in (extra or {}).items()}
    left = []
    for label in f.get('others') or []:
        v = keep.get(str(label).strip().lower())
        if v is None: left.append(label); continue
        _guard(c, site, f'other:{label}'); c.type(v)
    return left


def fill_page(c: Cdp, site: str, user: str, pw: str, wait: float = STEP_WAIT, code=None, code_wait: float = CODE_WAIT, extra=None) -> dict:
    """Type a sign-in into the page `c` is on - the whole of the checking lives here, so a test drives it with a stand-in page.
    `code`: makes the authenticator code, when one is kept. `extra`: the other boxes the site's form asks for, {label: value}.
    {'code': whether one was typed, 'others': the boxes it asked for that were left empty}."""
    f = _guard(c, site, '')
    # ONLY A CODE PROMPT: the session was signed in and the site asks for its second factor again - the code alone goes in
    if code and f.get('otp') and not f.get('password'): return {'code': _type_code(c, site, code)}
    if not f.get('password') and not f.get('user'):
        # what tells "the form is in another site's frame" from "no form": the page's own frames, by their address. Not the
        # DevTools frame tree - a cross-site frame runs in a process of its own and is not in it (measured, Chrome 2026-10)
        other = [o for o in f.get('frames') or [] if str(o).startswith(('http://', 'https://')) and not on_site(o, site)]
        raise SignInError(f'the sign-in form is inside a frame from another site ({registrable(urlsplit(other[0]).hostname) or "unknown"}) - '
                          'sign in yourself in the pane' if other else f'there is no sign-in form on the {site} page')
    left = _fill_others(c, site, f, extra)
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
    pf = _guard(c, site, 'password')
    if pf.get('others') and set(map(str.lower, pf['others'])) - set(map(str.lower, left)):
        left = left + _fill_others(c, site, {'others': [o for o in pf['others'] if o not in left]}, extra)   # a password page's own
        _guard(c, site, 'password')                          # ...and the password box focused again before its last look
    s = c.js(STILL) or {}                                    # the last look, with the box focused: still this site, still a password box
    if not s.get('password') or not on_site(s.get('href'), site): raise SignInError('the page changed under the sign-in - nothing was typed')
    c.type(pw)
    c.enter()
    # ...and a user box left empty is said (refused): a sign-up whose user name no box named keeps its password alone (send_new)
    return {'code': bool(code) and _await_code(c, site, code, code_wait), 'others': left, **({'nouser': True} if f.get('user') and not user else {})}


REJECT_WAIT = 4.0               # after SETTLE: how long a site is given to take its password box away before the password is called refused


def accepted(c, site: str, wait: float = REJECT_WAIT) -> bool:
    """Did the site take the sign-in? Its password box gone, a code asked, or the page off to another site (an SSO hop) - yes. The
    password box still up on the same site after `wait` - no: a wrong password, a captcha, a form that would not submit."""
    end = time.time() + wait
    while True:
        try: f = c.fields('')
        except SignInError: f = None                          # mid-navigation: the page cannot be read for a moment
        if f is not None:
            if not f.get('top') or not on_site(f.get('href'), site) or not f.get('password') or code_step(f): return True
        if time.time() >= end: return f is None
        time.sleep(.5)


def refused(site: str, others=None, nouser=False) -> str:
    "Why a typed sign-in stayed on its form - the box the form also needed, when it showed one empty, before blaming the password."
    o = [str(x) for x in (others or []) if str(x).strip()]
    if nouser: return (f'{site} also asks for the user name, and none was given - type it on the page, then sign in there; the password '
                       'was not shown to be wrong')
    if o: return (f'{site} also asks for {o[0]!r}, which Taskuary does not keep - type it on the page, then sign in there; the saved '
                  'password was not shown to be wrong')
    return f'{site} did not accept that password'


def type_in(sid: str, site: str, user: str, pw: str, code=None, extra=None) -> dict:
    """Sign the session's browser in on `site`: the screencast held while it types, the socket closed after."""
    from . import browserview
    with browserview.filling(sid):
        c = connect(sid)
        try:
            out = fill_page(c, site, user, pw, code=code, extra=extra)
            # THE PASSWORD DOES NOT STAY IN THE PAGE for the agent to read back (`agent-browser eval` on the box) when the site keeps
            # the form up - a wrong password, a captcha, a page that submits by script. Whatever box still holds it is emptied.
            time.sleep(SETTLE)
            ok = out.get('code') or accepted(c, site)
            try: c.js(CLEAR)
            except SignInError: pass                          # the page moved on: nothing of it is left to clear
            if not ok:
                e = NotAccepted(refused(site, out.get('others'), out.get('nouser'))); e.own = bool(out.get('others') or out.get('nouser'))
                raise e
            return out
        finally: c.close()


# ── A SIGN-UP: one command in the agent's turn - Taskuary makes the password, types it, keeps it and sends the form (design round 4, 2026-11-19) ──
# The marker road (end the turn with [[TASKUARY-SIGNUP]], be woken a turn later) cost a turn a site - thirteen vendors took 25-35 minutes - and it
# lost what it made: a form the agent pressed itself, or a held card pressed after the agent had moved on, made an account whose password nobody
# kept ("already exists" on five sites, of its own making). Now:
# - `agent-browser signup` (gatecmd's own verb; the API agent's browser_signup) on the page whose boxes the agent filled: Taskuary types a strong
#   new password into every password box, SEALS it to the vault before the form goes, sends it, and prints what the site answered - the command's
#   own result. An account counts as made only where that result says the site let it in (on the site, no password box, no error).
# - A CODE the site emails is waited for inside the command and typed from the mail; past the wait, the code watch keeps going on that page.
# - ANY PRESS of the agent's that sends a password box's value (it typed one, or pressed the form itself) seals what the box held first (pressing),
#   kept once the site takes it (settled) - so nothing a site was sent is lost.
# - HELD (a sign-up he did not ask for, or one that costs) it is one card, tied to the job: the form's boxes are kept with it, and his press fills
#   the page again in a tab of Taskuary's own when the agent has moved on, then sends it (send_held). Nothing he presses fails on a page gone.
NEW = 'new:'                    # signin_marker's claim for a sign-up: this, then the site the agent named
def signing_up(claimed) -> bool: return str(claimed or '').startswith(NEW)
ENDED_WAIT = 30                 # the marker's answer waits this long for the turn that asked to end
CODE_INLINE = 60.0              # inside the command: how long a code the site emails is waited for
_USERS = {}                     # (task, site) -> the user name a box of the site named on a page the agent pressed on (a wizard's first step)
_PRESSED = {}                   # session -> (task, site, the row it replaced): a press that sent a password, until the site answered it


def new_password(n: int = 20) -> str:
    "A password no site's rule turns down: n characters, upper and lower case, a digit and a symbol, from the OS's own randomness."
    import string
    a, sym = string.ascii_letters + string.digits, '!#%+-=?@_'
    while True:
        pw = ''.join(secrets.choice(a + sym) for _ in range(n))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw) and any(c in sym for c in pw): return pw


PASSBOX = r"""(i) => { """ + DEEP + r"""
  const vis = (e) => { const s = getComputedStyle(e), r = e.getBoundingClientRect();
    return !e.disabled && !e.readOnly && s.visibility !== 'hidden' && s.display !== 'none' && +s.opacity > 0.05 && r.width > 4 && r.height > 4; };
  const ps = deepAll('input[type=password]').filter(vis), el = ps[i];
  if (el) { el.focus(); try { el.select(); } catch (_) { el.value = ''; } }
  return { n: ps.length, top: window === window.top, href: location.href, focused: !!el && deepActive() === el }; }"""
# ...and which of those boxes hold the password now, in their order - read on the page, the password never leaves it
KEPT = PASSBOX.split('const ps =')[0] + r"""return deepAll('input[type=password]').filter(vis).map((e) => e.value === i); }"""
# THE FORM AS IT STANDS: the user name a box names as the user's, whether a password box holds one, and the boxes the agent filled - by name, never a
# password or a card's - so a held card can fill the page again. FORM_PW, the password itself, is read only to seal it (pressing), never kept elsewhere
FORM = "(() => { " + DEEP + r"""
  const vis = (e) => { const r = e.getBoundingClientRect(); return !e.disabled && r.width > 2 && r.height > 2; };
  const ins = deepAll('input, select, textarea').filter(vis), texty = (e) => ['text', 'email', 'tel', ''].includes(e.type);
  const user = ins.find((e) => texty(e) && e.value && """ + NAMED + r""".test([e.name, e.id, e.autocomplete, e.getAttribute('aria-label'), e.placeholder].join(' ')));
  const keep = ins.filter((e) => (e.name || e.id) && e.type !== 'password' && e.type !== 'hidden' && !/^cc-/.test(e.autocomplete || '')
    && (e.type === 'checkbox' || e.type === 'radio' ? e.checked : e.value));
  return { href: location.href, top: window === window.top, title: document.title, user: user ? String(user.value).slice(0, 200) : '',
           pw: deepAll('input[type=password]').some((e) => !!e.value), password: ins.some((e) => e.type === 'password'),
           fields: keep.slice(0, 30).map((e) => ({ k: e.name || e.id, t: e.type,
             v: e.type === 'checkbox' || e.type === 'radio' ? (e.value || 'on') : String(e.value).slice(0, 300) })) }; })()"""
FORM_PW = "(() => { " + DEEP + " const e = deepAll('input[type=password]').find((x) => !!x.value); return e ? e.value : ''; })()"
REFILL = "((fs) => { " + DEEP + r"""
  let n = 0; for (const f of fs) { const e = deepAll('input, select, textarea').find((x) => (x.name || x.id) === f.k && (f.t !== 'radio' || x.value === f.v));
    if (!e) continue; if (f.t === 'checkbox' || f.t === 'radio') e.checked = true; else e.value = f.v;
    e.dispatchEvent(new Event('input', { bubbles: true })); e.dispatchEvent(new Event('change', { bubbles: true })); n++; } return n; })"""


def type_new(sid: str, site: str, pw: str, c=None) -> int:
    """Type a new password into every password box of the sign-up page (its confirm box too), each focused and looked at on the pinned site
    first - and send nothing. -> how many boxes. `c`: the page's connection (a tab of Taskuary's own); else the agent's tab."""
    from . import browserview
    with browserview.filling(sid):
        own = c is None; c = c or connect(sid)
        try:
            _guard(c, site, '')
            n = (c.js(f'({PASSBOX})(-1)') or {}).get('n') or 0
            if not n: raise SignInError(f'there is no password box on the {site} page')
            def one(i):
                b = c.js(f'({PASSBOX})({i})') or {}
                if not b.get('top') or not on_site(b.get('href'), site) or not b.get('focused'): raise SignInError('the page changed under the sign-up - nothing was typed')
                c.type(pw)
            for i in range(n): one(i)
            # ...EVERY BOX HOLDS THE ONE PASSWORD, read back on the page (walk 7, 2026-11-23: a sign-up form re-drew its first box as the second was
            # typed - only the confirm box held it, "Passwords do not match", and the command said only that the form stayed up): a box that lost
            # it is typed again once, and one that still has not is said in plain words
            for again in (True, False):
                kept = c.js(f'({KEPT})({json.dumps(pw)})') or []
                if kept and all(kept): return n
                if not again: break
                for i, k in enumerate(kept):
                    if not k: one(i)
            raise SignInError(f'the {site} page kept the new password in {sum(map(bool, kept))} of its {len(kept)} password boxes, so they would '
                              'not match - nothing was sent')
        finally:
            if own: c.close()


USER = "(() => { " + DEEP + " const a = deepActive(); return a && a.type !== 'password' ? String(a.value || '').slice(0, 200) : ''; })()"
SAYS = (r"(() => [...document.querySelectorAll('[role=alert], [aria-live=assertive], [aria-invalid=true], .error, .err, .errors, "
        r".invalid-feedback, .field-error, [class*=error i], [id*=error i]')]"
        r".map((e) => e.innerText.trim()).filter(Boolean).join(' ').replace(/\s+/g, ' ').slice(0, 240))()")


def send_new(sid: str, site: str, c=None) -> dict:
    """Send the sign-up form the password was typed into: Enter in its password box on the pinned site. {'ok', 'user', 'why'} - `why` the
    page's own error marks when the form stayed up; the password boxes emptied after either way."""
    from . import browserview
    with browserview.filling(sid):
        own = c is None; c = c or connect(sid)
        try:
            f, user = _guard(c, site, ''), ''
            # ...the user box only where the page NAMES it so (FIELDS `named`): a wizard's last step shows a Company box over the password, and
            # read as the user box the account was kept as the company - and the next sign-in typed it into the email box
            if f.get('user') and f.get('named'): _guard(c, site, 'user'); user = str(c.js(USER) or '')
            _guard(c, site, 'password')
            try: c.js(LEAVING)
            except SignInError: pass
            c.enter()
            time.sleep(SETTLE)
            # ...AND WHAT THE SITE ANSWERED, by its status (the vendor walk, 2026-11-18): a 500 page has no password box either, and a site
            # crashing on its form was kept as an account nobody could sign in to; one that never answered was "the browser could not be reached"
            try: ok, why, status = accepted(c, site), '', answered(c)
            except Exception: ok, why, status = False, '', None
            if status is None:
                browserview.unstick(sid, every=True)
                return {'ok': False, 'user': user, 'why': f'the site did not answer in {SETTLE + REJECT_WAIT + ANSWER_WAIT:.0f} s, so the load was stopped'}
            if status >= 400: ok, why = False, f'the site answered with an error (HTTP {status})'
            elif not ok:
                try: why = str(c.js(SAYS) or '')
                except SignInError: pass
            try: c.js(CLEAR)
            except SignInError: pass
            return {'ok': ok, 'user': user, 'why': why}
        finally:
            if own: c.close()


ANSWER_WAIT = 8.0
# the document marks that it began to leave: still here after the wait, the site never answered the form (a form posted to its own address
# reads as the same page with the same status - only the old document knowing it was leaving tells the two apart)
LEAVING = "window.__tqLeaving = false; addEventListener('beforeunload', () => { window.__tqLeaving = true; }); true"
def answered(c, wait: float = ANSWER_WAIT) -> int | None:
    """The HTTP status of the document the page shows once it answers (0 when it does not say) - None when none answered within `wait`:
    the old document still there and leaving, or nothing readable."""
    from .browsergate import STATUS_JS
    end = time.time() + wait
    while time.time() < end:
        try:
            f = c.js(STATUS_JS) or {}
            if c.js('document.readyState') == 'complete' and c.js('window.__tqLeaving === true') is not True: return int(f.get('status') or 0)
        except Exception: pass
        time.sleep(.5)
    return None


def forget_row(old, key=True, extra=True):
    "A replaced row's own secrets out of the keychain: its user and password, and its code key and extras where they were replaced."
    from . import vault
    for v in (old or {}).get('User'), (old or {}).get('Secret'), ((old or {}).get('Totp') if key else None), ((old or {}).get('Extra') if extra is not None else None):
        vault.forget(v)


def _kept(prev, now):
    "The site took the new row: the secrets of the one it replaced go now - never before, while it might still come back."
    forget_row({k: v for k, v in (prev or {}).items() if v and v != (now or {}).get(k)})


# ── the vault row a sign-up replaced comes back when the site turns the form down ───────────────────────────────────────────────────
def _raw(store, site) -> dict | None:
    _tables(store)
    return store._one('SELECT * FROM signin_vault WHERE Site=?', (str(site or '').lower(),))


def _restore(store, site, prev):
    "The site kept its form up: the row kept ahead of the send goes, and the one it replaced (a sign-in that works) comes back as it was."
    from . import vault
    now = _raw(store, site)
    if prev: store._exec('INSERT OR REPLACE INTO signin_vault (Site, User, Secret, Totp, Extra, SavedAt, SavedBy, LastUsed) VALUES (?,?,?,?,?,?,?,?)',
                         tuple(prev.get(k) for k in ('Site', 'User', 'Secret', 'Totp', 'Extra', 'SavedAt', 'SavedBy', 'LastUsed')))
    else: store._exec('DELETE FROM signin_vault WHERE Site=?', (str(site).lower(),))
    for k in ('User', 'Secret', 'Extra'):
        if now and now.get(k) and now.get(k) != (prev or {}).get(k): vault.forget(now[k])


# ── the page a step belongs to: the agent's own tab while it is there, else a tab of Taskuary's own at it ──────────────────────────────
def _same(a, b) -> bool: return str(a or '').split('#', 1)[0].rstrip('/') == str(b or '').split('#', 1)[0].rstrip('/')


class tab_at:
    """with tab_at(sid, url) as (c, opened): a DevTools connection to the page at `url` - the agent's tab while it is on it, else a tab Taskuary
    opens at it in the same browser (its cookies, so a wizard's next step or a code page opens as it was left; `opened` True), closed after. A
    press held for the owner is tied to the job, not to the agent's tab: the agent moves on, and the press still lands (the vendor walk, 2026-11-19)."""
    def __init__(self, sid, url, wait: float = 15.0): self.sid, self.url, self.wait, self.c, self.tab = sid, url, wait, None, None
    def __enter__(self):
        c = connect(self.sid)
        try:
            if _same(c.js('location.href'), self.url): self.c = c; return c, False
            self.tab = c.call('Target.createTarget', {'url': self.url, 'background': True}, top=True)['targetId']
            self.c = Cdp(c.url, self.tab)
        finally:
            if self.c is not c: c.close()
        end = time.time() + self.wait
        while time.time() < end:
            try:
                if self.c.js('document.readyState') == 'complete' and _same(self.c.js('location.href'), self.url): break
            except SignInError: pass
            time.sleep(.3)
        return self.c, True
    def __exit__(self, *a):
        if self.tab:
            try: self.c.call('Target.closeTarget', {'targetId': self.tab}, top=True)
            except SignInError: pass
        if self.c: self.c.close()


# ── the command ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
# A CODE IS NEVER MAILED WHERE NOBODY READS IT (walk 9, CLI 2-6): an inbox an agent made on a web mail site was then put on five sign-ups - each
# site emailed its code there, Taskuary reads no such inbox, he cannot open it, and every code was handed to him to type. An address on the form
# that is an inbox an agent made (the vault knows it) and no mailbox Taskuary reads is refused before anything goes: with the ones it reads named,
# or - reading none - his one question on the task, which address to use
EMAIL_RE = re.compile(r'^[^@\s]+@[^@\s]+\.[^@\s]+$')
def unread_inbox(store, f: dict) -> str:
    "The email on the sign-up form `f` that is an inbox an agent made and Taskuary does not read - or ''."
    from .ingest import own_addresses, owner_addresses
    reads = {_bare(a) for a in owner_addresses(store) | own_addresses(store)}
    made = {(r['site'], str(r['user'] or '').lower()) for r in listing(store) if r['by'] == 'agent'}
    for v in [f.get('user'), *(x.get('v') for x in f.get('fields') or [])]:
        a = str(v or '').strip().lower()
        if not EMAIL_RE.match(a) or _bare(a) in reads: continue
        local, dom = a.split('@', 1)
        # ...the mailbox itself, kept as the account on its own mail site (its address, there) or by the bare name its form took - never an
        # account on another site that merely uses the address
        if any((u == a and s == registrable(dom)) or u == local for s, u in made): return a
    return ''


def _bare(a) -> str:
    "An address without its +tag: alex+rentscope@ reaches alex@'s inbox."
    local, _, dom = str(a or '').strip().lower().partition('@')
    return f"{local.split('+', 1)[0]}@{dom}"


def _dead_inbox(store, tid, site: str, addr: str) -> str:
    from .ingest import owner_addresses
    from . import selfclose
    boxes = sorted(owner_addresses(store))
    head = f'Nothing was sent: {addr} is an inbox an agent made that Taskuary does not read, so a code {site} emails there would reach nobody. '
    if boxes: return head + f"The mailboxes Taskuary reads: {', '.join(boxes)} - put one in the form and run `agent-browser signup` again."
    q = selfclose.ask_mark('Which email address should the accounts I make use? Taskuary reads none of your mailboxes yet, so a code a site emails '
                           'could not come back by itself - connect your mailbox under Connections, or name an address you read.')
    if q not in [l for _k, l in selfclose._MARKS.get(int(tid), [])]: selfclose.keep_mark(tid, 'ask', q)
    return head + 'Taskuary reads no mailbox, so the owner is asked once on this task which address to use; go on with what does not hang on it.'


def signup(store, tid, sid) -> tuple[bool, str]:
    """`agent-browser signup`: the agent filled a sign-up form but its password. -> (made or held, what the command prints)."""
    from . import browsergate, browserview, proposals
    st = browserview.state(sid, fresh=True)
    url = str(st.get('url') or '') if st.get('open') else ''
    site = site_of(url)
    if not site: return False, ('Nothing was typed: no page a password may go on is open in this browser (https, or this computer). Open the '
                                "site's sign-up page, fill every box but the password, and run `agent-browser signup` again.")
    try: c = connect(sid)
    except SignInError as e: return False, f'Nothing was typed: {e}.'
    try:
        # ...THE FORM IS THE ONE ON THE TAB THE COMMAND WORKS, by that tab's own address (walk 5, 2026-11-19: the card named one site's form while
        # the address read was another tab's) - the card names that tab, and his press runs there only (browsergate.held_tab)
        here = str(c.js('location.href') or '')
        if site_of(here) and site_of(here) != site: url, site = here, site_of(here)
        if dead := unread_inbox(store, c.js(FORM) or {}): return False, _dead_inbox(store, tid, site, dead)
        pg = browsergate.page(sid)
        name = site_name(url, sid) or site
        v = browsergate.judge(store, [{'verb': 'press', 'args': [], 'raw': f'send the filled sign-up form on {name}, creating an account there'}], pg,
                              said=browsergate.asked(store, tid))[0]
        if not v['hold']: return _make(store, tid, sid, site, c)
        f = c.js(FORM) or {}
        if not f.get('password'): return False, _no_box(site)
        proposals.queue(store, tid, {'action': 'browser_act', 'sid': str(sid), 'args': ['signup'], 'signup': site, 'url': here or url, 'site': site,
                                     'name': name, **({'tab': t} if (t := getattr(c, 'target', '')) else {}), 'fields': f.get('fields') or [], 'command': f'send the sign-up form on {name}',
                                     'what': v['what'], 'why': v['why']}, 'agent')
        return True, (f'HELD for the owner: {v["what"]} ({v["why"]}). It stands as one card in the chat; their press fills this form again as you '
                      'left it, makes and keeps the password and sends it - even after you have moved on - and you are told what the site '
                      'answered. Do not ask them in words; go on with the rest of the work.' + browsergate.stands(store, tid))
    finally: c.close()


def _no_box(site) -> str:
    return (f'Nothing was typed: this {site} page has no password box. Press its own button for the step before (a Next), then run '
            '`agent-browser signup` on the page that asks for the password.')


def _make(store, tid, sid, site, c, fill=None, send=None, said: dict = None) -> tuple[bool, str]:
    """Type a new password into the page `c` is on, keep it, send the form, and say what the site answered. Kept BEFORE it is sent: a restart
    in those seconds left an account nobody could sign in to (2026-11-18). The row it replaced comes back if the site turns the form down."""
    f = c.js(FORM) or {}
    if not f.get('password'): return False, _no_box(site)
    pw, prev = new_password(), _raw(store, site)
    user = f.get('user') or _USERS.get((int(tid), site), '')
    typing(store, tid, site, sid)
    try: (fill or type_new)(sid, site, pw, c)
    except Exception as e:
        why = str(e) if isinstance(e, SignInError) else 'the browser could not be reached'
        _audit(store, tid, site, 'vault', False, why)
        return False, f'Nothing was sent: the password could not be typed - {why}. Look at the page and go on from what it shows.'
    try: save(store, site, user, pw, by='taskuary', keep_old=True, task=tid); kept = ''
    except ValueError as e: kept = f' The password could not be kept: {e}.'
    try: got = (send or send_new)(sid, site, c)
    except Exception as e: got = {'ok': False, 'why': str(e) if isinstance(e, SignInError) else 'the browser could not be reached'}
    if not got.get('ok'):
        # ...A PASSWORD THE SITE WAS SENT IS KEPT unless the site said no or a working sign-in comes back (walk 9, 2026-11-23: a site whose next
        # step stood on the same page read as "kept its form up", the row went, and the account the agent then finished had no password anywhere)
        drop = bool(got.get('why')) or bool(prev)
        if not kept and drop: _restore(store, site, prev)
        elif not kept: made_line(store, tid, site, user)
        _audit(store, tid, site, 'vault', False, got.get('why') or 'the form stayed up', signup=True)
        if said is not None: said['why'] = got.get('why') or ''
        return False, (f'No account yet: {site} kept its sign-up form up' + (f' - it says "{got["why"]}"' if got.get('why') else
                       ' and shows no error Taskuary could read - look at the page for what it asks') + '. ' +
                       ('Nothing was kept. ' if drop or kept else "The password it was sent is kept with the owner's saved sign-ins, marked "
                        'not signed in with yet. ') + 'Fix what it asks for and run `agent-browser signup` again; a box only the owner can fill is theirs.')
    if (u := got.get('user')) and u != user and not kept: user = u; save(store, site, user, pw, by='taskuary', keep_old=True, task=tid)
    if not kept: _kept(prev, _raw(store, site)); made_line(store, tid, site, user)
    from .browsergate import overcome
    overcome(store, tid, site, f'Done on a later try: the account on {site} was made', signup=True)
    return True, _answered(store, tid, sid, site, c, user, kept)


def _answered(store, tid, sid, site, c, user, kept) -> str:
    "After the form went: a code it emailed typed from the mail, and the page read - an account only where the site let it in."
    who = f' as {user}' if user else ''
    end, after, coded = time.time() + CODE_INLINE, mail_since(store, tid, site), ''
    _CODE_WATCHED.add((int(tid), site))               # ...the mail is this command's to type while it waits (take_code starts no watch)
    try:
        while True:
            try: f = c.fields('')
            except SignInError: f = {}
            if not (f.get('top') and on_site(f.get('href'), site) and code_step(f)) or time.time() > end: break
            if (got := mailed_code(store, site, after)) and got[1]:
                try: _type_code(c, site, lambda: got[1]); coded = ' The code it emailed was typed from the mail.'
                except SignInError: pass
                time.sleep(SETTLE); after = got[0]
            else: time.sleep(1)
    finally: _CODE_WATCHED.discard((int(tid), site))
    try: f, look, status = c.fields(''), c.js(FORM) or {}, answered(c, 3)
    except SignInError: f, look, status = {}, {}, None
    if f.get('top') and on_site(f.get('href'), site) and code_step(f):
        threading.Thread(target=code_watch, args=(store, tid, sid, site), kwargs={'url': str(f.get('href') or '')}, daemon=True,
                         name=f'code-watch-{tid}').start()
        _audit(store, tid, site, 'vault', True, 'a code was asked', saved=not kept, signup=True)
        return (f'Not an account yet: {site} took the form{who} and asks for a code it emailed. Taskuary types it from the mail when it comes and tells '
                f"you; never ask for it. The password is kept with the owner's saved sign-ins.{kept} Go on with the next one meanwhile.")
    there = f'"{look.get("title") or ""}" ({look.get("href") or f.get("href") or ""})'
    if f.get('top') and on_site(f.get('href'), site) and not f.get('password') and (status or 200) < 400:
        _audit(store, tid, site, 'vault', True, 'signed up', saved=not kept, signup=True)
        from . import ledger
        ledger.account(store, site, user, 'signed_up', tid)          # ...the site let it past: the account is on the record
        return (f"{site} took the sign-up{who}: the page shows {there} - look at it for whether the account is made or asks for more.{coded} "
                f"Its password is kept with the owner's saved sign-ins - you never need it; to sign in again later, open its sign-in page and "
                f'hand_over with site {site}.{kept}')
    _audit(store, tid, site, 'vault', True, 'sent', saved=not kept)
    return (f'Sent{who}; the page now shows {there}, not signed in. Not an account yet: open its sign-in page and hand_over with site '
            f'{site} - an account counts once that sign-in goes in.{coded}{kept}')


# ── the marker, for an agent that still ends its turn with [[TASKUARY-SIGNUP]]: the same command, answered once that turn has ended ──
def new_account(store, tid, sid, site, rid, fill=None, watch=...) -> dict:
    from . import general, workerstate as ws
    general.hand(tid)
    def run():
        try:
            end = time.time() + ENDED_WAIT
            while time.time() < end and getattr(ws._live(tid), 'busy', False): time.sleep(.1)
            ok, line = signup(store, tid, sid)
            _continue(store, tid, rid, site, 'taskuary', words=(line.split(':')[0].split(',')[0] if ok else f'The sign-up on {site} did not go through', line))
        finally: general.hand(tid, -1)
    threading.Thread(target=run, daemon=True, name=f'signup-{tid}').start()
    return {'site': site, 'auto': False}


def send_held(store, tid, sid, p) -> dict:
    """His press on a held sign-up's card (browsergate.perform): the form filled again where the agent has moved on, sent, and the agent told."""
    from .browsergate import _tell, held_on
    site, url = str(p.get('signup') or ''), str(p.get('url') or '')
    got = {}
    try:
        # ...ON THE TAB IT WAS HELD ON while that tab is on its form - never the tab shown now, never another page of the site (walk 5, 2026-11-19:
        # his yes to one site's sign-up ran on another site's page)
        if p.get('tab') and held_on(sid, p):
            c = Cdp(_cdp_url(sid), str(p['tab']), exact=True)
            try: ok, line = _make(store, tid, sid, site, c, said=got)
            finally: c.close()
        # ...ELSE ITS FORM OPENED AGAIN at its own address in a tab of Taskuary's own, its kept boxes filled back (walk 8, 2026-11-20: the agent
        # took its tab on to the next vendor, as it was told it could, and three held sign-ups went off their cards before he pressed)
        else:
            with tab_at(sid, url) as (c, _):
                if not _same(c.js('location.href'), url): raise SignInError(f'its sign-up page at {url} did not open again')
                c.js(f'{REFILL}({json.dumps(p.get("fields") or [])})')
                ok, line = _make(store, tid, sid, site, c, said=got)
    except SignInError as e: ok, line, got = False, f'Nothing was sent: {e}.', {'why': str(e)}
    _tell(store, tid, f'The owner approved the sign-up on {site}. {line}', wake=True)
    # ...his card says what became of it in his words (say.owner) - the agent's own next step ("run `agent-browser signup` again") is the agent's
    from . import say
    if not ok: raise RuntimeError(say.owner({'kind': 'signup_failed', 'site': site_name(url or site, sid), 'why': (got or {}).get('why')}))
    return {'performed': p.get('what') or f'the sign-up on {site}', 'site': site}


# ── the agent's own press that sends a password: sealed before it goes, kept once the site takes it ─────────────────────────────────
# THE SIGN-UP IS THE ONE WAY A NEW ACCOUNT'S PASSWORD IS TYPED (walk 10, 2026-11-23: told ten times "next time run `agent-browser signup`",
# an agent typed the same made-up password into every trial form): a press that would send a password the agent typed itself, on a site with
# no saved sign-in, is not sent - the gate runs the sign-up on that form instead (browsergate), which makes, types and keeps the password
UNSAVED = 'no saved sign-in'
TYPED_REFUSED = "Not pressed: a new account's password is made and typed by Taskuary, never by an agent, so it ran `agent-browser signup` on this form -"


def pressing(store, tid, sid, site, conn=None) -> str | None:
    """An act of the agent's is about to press on `site`: remember a user name a box there names (a wizard's later step shows none), and seal a
    password a box holds - the site is sent it now, and nothing else would ever keep it. -> UNSAVED where that password is one the agent typed for
    an account the owner has no sign-in for: nothing is kept, and the press is the sign-up's to make."""
    if not site or not str(tid or '').isdigit(): return
    try:
        c = conn or connect(sid)
        try: f = c.js(FORM) or {}; pw = c.js(FORM_PW) if f.get('pw') else ''
        finally:
            if conn is None: c.close()
    except Exception: return
    if not (f.get('top') and on_site(f.get('href'), site)): return
    if f.get('user'): _USERS[(int(tid), site)] = f['user']
    if not pw: return
    prev = _raw(store, site)
    if not prev: return UNSAVED
    from . import vault
    if prev.get('Secret') and vault.unseal(prev['Secret']) == pw: return     # ...the saved sign-in itself, typed by Taskuary: his row stays his
    try: save(store, site, f.get('user') or _USERS.get((int(tid), site), ''), pw, by='agent', keep_old=True, task=tid)
    except ValueError as e: return logger.info(f'signin: task {tid} pressed with a password on {site}, not kept - {e}')
    _PRESSED[str(sid)] = (int(tid), site, prev)


def form_fields(sid) -> list:
    "The boxes the agent filled on the page its browser is on (FORM) - kept with a card held there, so his press can fill it again. [] unread."
    return form_state(sid).get('fields') or []
def form_state(sid) -> dict:
    "The form on the page its browser is on, as FORM reads it ({fields, pw, ...}) - {} unread."
    try:
        c = connect(sid)
        try: return c.js(FORM) or {}
        finally: c.close()
    except Exception: return {}


def settled(store, sid, conn=None) -> str:
    "After that press: the site took it - kept, and said in one line; it kept its form up - the row put back as it was. '' when none was pressed."
    t = _PRESSED.pop(str(sid), None)
    if not t: return ''
    tid, site, prev = t
    try:
        c = conn or connect(sid)
        try: ok = accepted(c, site)
        finally:
            if conn is None: c.close()
    except Exception: ok = True                          # ...unreadable: what the site was sent stays kept - a password lost is the worse
    if not ok and prev: _restore(store, site, prev); return ''
    _kept(prev, _raw(store, site)); made_line(store, tid, site, _user(_raw(store, site) or {}))
    _audit(store, tid, site, 'vault', True, 'kept from a press', saved=True)
    return f"TASKUARY: the password that form sent to {site} is kept with the owner's saved sign-ins."


# ── the fill page: one site, two boxes, one press - served by the app itself on 127.0.0.1, never on the share port ───────────
CSP = "default-src 'none'; style-src 'unsafe-inline'; form-action 'self'; base-uri 'none'; frame-ancestors 'none'"
# SAME-ORIGIN, not no-referrer: a POST from a no-referrer page carries `Origin: null`, which guard.origin_ok refuses - so Chrome and Edge
# answered every fill with "This sign-in came from another page" (2026-10-25). same-origin still sends nothing to another site.
HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'Referrer-Policy': 'same-origin', 'X-Content-Type-Options': 'nosniff',
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
            f'<meta name="referrer" content="same-origin"><title>Sign in - Taskuary</title><style>{_STYLE}</style></head>'
            f'<body><main>{body}</main></body></html>')


def _for(line: str) -> str: return f'<p class="k" data-tq-for="">{H.escape(line)}</p>' if line else ''


def form_html(site: str, minutes: int, err: str = '', task: str = '', action: str = '') -> str:
    """The fill page. The SITE leads, big - it is the one thing to check before typing a password into anything. `task`: which task and
    agent it is for (for_line); `action`: where the form posts, when it is shown again on a fresh link (NotAccepted)."""
    from .timewords import plural
    s, act = H.escape(site), (f' action="{H.escape(action)}"' if action else '')
    return _page(f'<p class="k">Sign in to</p><p class="site">{s}</p>' + _for(task)
                 + (f'<p class="err" role="alert">{H.escape(err)}</p>' if err else '')
                 + f'<form method="post" autocomplete="off"{act}>'
                 '<label for="u">Username</label><input id="u" name="username" type="text" autocomplete="username" autofocus>'
                 '<label for="p">Password</label><input id="p" name="password" type="password" autocomplete="current-password" required>'
                 # the site's authenticator key, when it asks a code after the password (2026-10-25): optional, and typed as a secret
                 '<label for="k">Authenticator setup key <span class="k">(optional - the code the site shows under "Can\'t scan the QR code?")</span></label>'
                 '<input id="k" name="key" type="password" autocomplete="off" spellcheck="false">'
                 '<label class="keep"><input type="checkbox" name="save" value="1"> Save to vault for next time</label>'
                 '<button type="submit">Sign in</button></form>'
                 f'<p class="note">Taskuary types this into the {s} page open in the task\'s browser - only if that page is still on {s}. '
                 f'The agent never sees it. This page works once, for {plural(minutes, "more minute", "more minutes")}.</p>')


def done_html(site: str, saved: bool, kept: str = '', told: bool = True, task: str = '', ref: str = '') -> str:
    """`told`: an agent was running to hear it - with none, the page said "the agent goes on" over a task that stayed stuck (2026-10-25)."""
    s = H.escape(site)
    keep = ('<p class="note">Saved for next time - Settings &gt; Agent permissions &gt; Saved sign-ins, to remove it.</p>' if saved else
            f'<p class="note err">Not saved: {H.escape(kept)}.</p>' if kept else '')
    went = ("Typed into the task's browser - the agent goes on. You can close this page." if told else
            f"Typed in. No agent is running on {H.escape(ref or 'the task')} - open it to continue.")
    return _page(f'<p class="k">Signed in to</p><p class="site">{s}</p>' + _for(task) + f'<p class="ok">{went}</p>' + keep)


def gone_html(why: str, task: str = '', ref: str = '') -> str:
    "`ref`: the task to go back to - this tab was opened outside the app, and the page named no way back (2026-10-25)."
    back = f'Open {H.escape(ref)} in Taskuary and press Sign in here again.' if ref else 'Open a new sign-in page from the task.'
    return _page(f'<p class="k">Sign in</p>{_for(task)}<p class="err" role="alert">{H.escape(why)}</p><p class="note">{back}</p>')
