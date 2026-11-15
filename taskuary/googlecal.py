"""Sign in with Google, on the Gmail card: one sign-in for the mail, the calendar and the contacts (the owner, 2026-11-15: "any way to
connect to gmail through the api so you can use the calendar item? add that option as well not just app password").

The card's App Password carries mail only, and Google Calendar takes OAuth only. The card's step runs Google's installed-app flow from
here: the browser goes to Google asking for the mail (MAIL - imapmail signs in to the same IMAP and SMTP with it, XOAUTH2, when the card
holds no App Password), the calendar (SCOPE: calendar.events, which reads it and answers invites - calwrite) and the contacts (PEOPLE),
comes back to this server on 127.0.0.1 (a Desktop client takes any loopback port - fileaccess's round rides the same road) with PKCE
and a one-time state, and the refresh token is kept on the card, sealed (store seals google_refresh_token inside ConfigJson, vault.py).

EACH INSTALL BRINGS ITS OWN GOOGLE CLIENT (the owner, 2026-11-15, as Microsoft since 2026-11-05 - msauth.py): Taskuary ships none. The
card holds a Desktop-app client's ID and secret (google_client_id / google_client_secret) and lists the steps to make one; a card
without one says so (NO_CLIENT) on the card, never at Google. TASKUARY_GOOGLE_CLIENT_ID / _SECRET stand in for a card that holds none.

ONE ROAD TO A TOKEN: token() - the calendar's reads and writes, the people search, the mail's sign-in and Allow saving files all ask it."""
import base64, hashlib, json, os, secrets, threading, time
from urllib.parse import urlencode
from . import net as requests     # pooled Session + (connect, read) timeouts, same call shape

G_AUTH, G_TOKEN = 'https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token'
MAIL = 'https://mail.google.com/'                                    # IMAP and SMTP by XOAUTH2: the one scope Google gives those
SCOPE = 'https://www.googleapis.com/auth/calendar.events'            # reads the calendar AND answers invites
CAL_WRITE = (SCOPE, 'https://www.googleapis.com/auth/calendar')
CAL_READ = (*CAL_WRITE, 'https://www.googleapis.com/auth/calendar.readonly')     # ...readonly: all a sign-in before 2026-11-15 asked for
# PEOPLE SEARCH (the owner, 2026-10-27: "and Gmail if it supports it"): the same sign-in asks for the account's contacts, the ones Gmail
# saved by itself (otherContacts) and, on a Workspace account, its organisation's directory - all read-only, each a box Google lets the
# owner untick (peoplesearch.google_people skips what was not granted).
G_CONTACTS, G_OTHER, G_DIRECTORY = (f'https://www.googleapis.com/auth/{s}' for s in ('contacts.readonly', 'contacts.other.readonly', 'directory.readonly'))
PEOPLE = (G_CONTACTS, G_OTHER, G_DIRECTORY)
SCOPES = ' '.join((MAIL, SCOPE, *PEOPLE))
TTL = 900
G_SIGNIN = 'Sign in with Google'
NO_CLIENT = f"{G_SIGNIN} needs this install's own Google client - add its client ID and secret on the Gmail card, which lists the steps."
LAPSED = 'the Google sign-in has lapsed'
READ_ONLY = (f'This Google sign-in only reads the calendar. Press {G_SIGNIN} on the Gmail card again - it then asks for the calendar '
             'itself, so invites are answered and meetings set up from here.')
_FLOWS: dict = {}          # state -> {cid, verifier, at, done: (ok, what to say) once Google has sent the browser back}
_TOK, _LOCK = {}, threading.Lock()     # refresh token -> (access token, expires at, the scopes it holds)
_GONE: set = set()         # refresh tokens Google has refused: the card says so without asking Google again


def redirect_uri(server: dict) -> str: return f"http://127.0.0.1:{server.get('port') or 7787}/api/google/calendar/callback"
def connected(cfg: dict) -> bool: return bool((cfg or {}).get('google_refresh_token'))
def lapsed(err) -> bool: return LAPSED in str(err or '')
def granted(cfg: dict) -> list: return str((cfg or {}).get('google_scope') or '').split()


def client(cfg: dict) -> tuple:
    """(id, secret) of the install's own Google client: the card's, else the environment's."""
    own = tuple(str((cfg or {}).get(k) or '').strip() for k in ('google_client_id', 'google_client_secret'))
    return own if all(own) else tuple((os.getenv(k) or '').strip() for k in ('TASKUARY_GOOGLE_CLIENT_ID', 'TASKUARY_GOOGLE_CLIENT_SECRET'))


def available(cfg: dict) -> bool: return all(client(cfg))


def state(c: dict, cfg: dict) -> dict:
    """What the card's Google box says: can it sign in, is it signed in, should it sign in again - and the one line (`said`) for it.
    A token pasted before sign-ins wrote down their scopes (no google_scope) is not called read-only: nothing here knows."""
    on, g = connected(cfg), granted(cfg)
    rt = cfg.get('google_refresh_token')
    # ...a lapse the last poll wrote on the card stands until a poll is clean again, or a new sign-in minted a token (_TOK)
    gone = on and (rt in _GONE or (lapsed((c or {}).get('LastError')) and rt not in _TOK))
    mail, write = MAIL in g, any(s in g for s in CAL_WRITE)
    narrow = on and bool(g) and not write
    has = [w for w, ok in (('mail', mail), ('the calendar' if write else 'the calendar, read-only', any(s in g for s in CAL_READ)),
                           ('contacts', G_CONTACTS in g)) if ok]
    by = ('through this sign-in' if mail and not (c or {}).get('Secret') else 'by the App Password' if (c or {}).get('Secret')
          else f'once an App Password is saved, or after {G_SIGNIN} again with the Gmail box ticked')
    said = (NO_CLIENT if not available(cfg) and (gone or not on) else
            'Google ended this sign-in - sign in again. If that happens every week, the client is still in Testing: publish it in '
            'Google Cloud (Google Auth Platform > Audience > Publish app).' if gone else
            '' if not on else READ_ONLY.replace(' on the Gmail card', '') if narrow else
            f"Signed in with Google: {', '.join(has) or 'the calendar'}. Mail comes in {by}.")
    return {'available': available(cfg), 'connected': on, 'lapsed': bool(gone), 'again': bool(gone or narrow), 'said': said}


def _gmail(store, cid):
    c = store.get_connector(int(cid), with_secret=True)
    if not c or c.get('Type') != 'gmail': raise LookupError(f'{G_SIGNIN} lives on the Gmail card')
    return c, json.loads(c.get('ConfigJson') or '{}')


def start(store, cid: int, server: dict) -> dict:
    """{flow, url}: where the browser goes to say yes, and the id the card polls with. ValueError (said as is) with no client."""
    _, cfg = _gmail(store, cid)
    if not available(cfg): raise ValueError(NO_CLIENT)
    gid, gsec = client(cfg)
    for k, v in list(_FLOWS.items()):
        if time.time() - v['at'] > TTL: _FLOWS.pop(k, None)
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    _FLOWS[state] = {'cid': int(cid), 'verifier': verifier, 'at': time.time(), 'done': None, 'client': (gid, gsec)}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    # include_granted_scopes: a card that already allowed saving files (drive.file) keeps it on the new token
    # login_hint: Google opens on the card's own account - a token of another account is refused by that mailbox's IMAP
    return {'flow': state, 'url': G_AUTH + '?' + urlencode({
        'client_id': gid, 'redirect_uri': redirect_uri(server), 'response_type': 'code', 'scope': SCOPES,
        'access_type': 'offline', 'prompt': 'consent', 'state': state, 'include_granted_scopes': 'true',
        'code_challenge': challenge, 'code_challenge_method': 'S256', **({'login_hint': cfg['address']} if cfg.get('address') else {})})}


def callback(store, server: dict, code: str, state: str, error: str = None) -> tuple:
    """(ok, what to say). Exchanges the code with the round's own verifier and keeps the refresh token on the card. A state answers once."""
    f = _FLOWS.get(str(state or ''))
    if not f or f.get('claimed') or time.time() - f['at'] > TTL:
        return False, f'This sign-in was not started here, or it is too old - press {G_SIGNIN} on the Gmail card again.'
    f['claimed'] = True
    f['done'] = _exchange(store, server, f, code, error)
    return f['done']


def _exchange(store, server, f, code, error) -> tuple:
    if error: return False, f'Google said: {error}'
    if not code: return False, 'Google sent no code back.'
    try: c, cfg = _gmail(store, f['cid'])
    except LookupError as e: return False, str(e)
    gid, gsec = f['client']              # the code answers to the client it was asked with, whatever the card holds now
    r = requests.post(G_TOKEN, timeout=20, data={'client_id': gid, 'client_secret': gsec, 'code': code, 'code_verifier': f['verifier'],
                                                'grant_type': 'authorization_code', 'redirect_uri': redirect_uri(server)})
    if r.status_code != 200: return False, f'Google refused the sign-in ({r.status_code}).'
    j = r.json() or {}
    if not j.get('refresh_token'): return False, 'Google returned no refresh token - nothing was changed.'
    scope = str(j.get('scope') or '')
    g = scope.split()
    # Google's consent page lets each permission be unticked: a token with neither the mail nor the calendar does nothing here
    mail, cal, write = MAIL in g, any(s in g for s in CAL_READ), any(s in g for s in CAL_WRITE)
    if not (mail or cal): return False, 'Google granted neither the mail nor the calendar - their boxes were left unticked. Nothing was changed.'
    old = cfg.get('google_refresh_token')
    # the sign-in's own keys merged over the card as it is NOW: the card read before Google answered is not written back (merge_config)
    store.merge_connector_config(f['cid'], {'google_refresh_token': j['refresh_token'], 'google_scope': scope})
    store.audit('connector', f['cid'], 'google_signin', 'owner', detail={'scope': scope})
    with _LOCK:
        _TOK.pop(old, None); _GONE.discard(old)
        _TOK[j['refresh_token']] = (j.get('access_token') or '', time.time() + int(j.get('expires_in') or 3600), scope)
    from . import calendar
    for x in (calendar._REPLY, calendar._UPCOMING, calendar._TODAY): x['data'] = None     # the next read sees the new calendar
    from . import peoplesearch
    peoplesearch.forget()                                                                   # the next search asks the new contacts
    does = [w for w, ok in (('reads and sends its mail' if not c.get('Secret') else 'may read and send its mail (the App Password is used while one is saved)', mail),
                            ('reads its calendar and answers invites' if write else 'reads its calendar', cal),
                            ('searches its contacts when you pick someone to write to', G_CONTACTS in g)) if ok]
    return True, f"Signed in with Google as {cfg.get('address') or 'this account'}: Taskuary now {', '.join(does)}."


def poll(state: str) -> dict:
    """{status: pending | ok | error, detail} - the card finishes by itself once the browser is back."""
    f = _FLOWS.get(str(state or ''))
    if not f: return {'status': 'error', 'detail': 'no such sign-in in progress - start it again'}
    if not f['done']:
        if time.time() - f['at'] > TTL: _FLOWS.pop(state, None); return {'status': 'error', 'detail': 'the sign-in took too long - start it again'}
        return {'status': 'pending'}
    _FLOWS.pop(state, None)
    ok, said = f['done']
    return {'status': 'ok' if ok else 'error', 'detail': said}


def cancel(state: str): _FLOWS.pop(str(state or ''), None)


def token(cfg: dict) -> tuple:
    """(a live access token, the scopes it holds) off the card's refresh token - cached until a minute before it expires, minted again
    after. Google refusing the refresh token (revoked, or a Testing client's week run out) is a lapse, said with its fix."""
    rt = (cfg or {}).get('google_refresh_token')
    if not rt: raise RuntimeError(f'not signed in with Google - press {G_SIGNIN} on the Gmail card')
    with _LOCK:
        hit = _TOK.get(rt)
        if hit and hit[0] and hit[1] > time.time() + 60: return hit[0], hit[2]
        gid, gsec = client(cfg)
        if not (gid and gsec): raise RuntimeError(NO_CLIENT)
        r = requests.post(G_TOKEN, timeout=20, data={'client_id': gid, 'client_secret': gsec, 'refresh_token': rt, 'grant_type': 'refresh_token'})
        # only Google REFUSING the token is a lapse: a 5xx is its service having a bad minute, and nothing to sign in again for
        if r.status_code in (400, 401) and 'invalid_grant' in r.text:
            _GONE.add(rt)
            raise RuntimeError(f'{LAPSED} - press {G_SIGNIN} on the Gmail card')
        if r.status_code != 200: raise RuntimeError(f'Google token failed ({r.status_code}): {r.text[:200]}')
        j = r.json() or {}
        _GONE.discard(rt)
        _TOK[rt] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600), str(j.get('scope') or cfg.get('google_scope') or ''))
        return _TOK[rt][0], _TOK[rt][2]


def access_token(cfg: dict) -> str: return token(cfg)[0]
