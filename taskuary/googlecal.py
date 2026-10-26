"""Sign in with Google for the calendar, on the Gmail card (the owner, 2026-10-26: "yes" to "A Gmail card's calendar is only read
once its Google calendar fields are filled in by hand. Should the card offer a 'Sign in with Google' step for the calendar?").

A Gmail card is IMAP with an App Password, which carries no calendar, and Google Calendar takes OAuth only - so the refresh token
used to be minted outside Taskuary and pasted into the card. The card's step runs Google's installed-app flow from here instead:
the browser goes to Google asking for calendar.readonly, comes back to this server on 127.0.0.1 (a Desktop client takes any
loopback port - fileaccess's round rides the same road) with PKCE and a one-time state, and the refresh token is kept on the card,
sealed (store seals google_refresh_token inside ConfigJson, vault.py), where calendar.agenda reads it as it read a pasted one.

TASKUARY'S OWN GOOGLE CLIENT (the owner, 2026-10-26: "don't want to create my own google client, want to use their own"): nobody
creates or pastes an OAuth client. The sign-in rides ONE Desktop-app client Taskuary ships, as msauth rides Taskuary's Microsoft app
id (msauth.PUBLIC_CLIENT_ID) - BUILTIN_CLIENT_ID below, overridable per install with TASKUARY_GOOGLE_CLIENT_ID / _SECRET for
development, or per card with its own google_client_id / google_client_secret (the card's admin fold, where the Outlook card keeps
its client_id). A build with none says so in one line (UNAVAILABLE) instead of sending anyone to Google Cloud console."""
import base64, hashlib, json, os, secrets, threading, time
from urllib.parse import urlencode
from . import net as requests     # pooled Session + (connect, read) timeouts, same call shape

G_AUTH, G_TOKEN = 'https://accounts.google.com/o/oauth2/v2/auth', 'https://oauth2.googleapis.com/token'
SCOPE = 'https://www.googleapis.com/auth/calendar.readonly'
TTL = 900
# Taskuary's Desktop-app OAuth client goes HERE once it exists in Google Cloud - empty until then, and this build has no Google
# sign-in. Its secret is not one: Google documents an installed app's client secret as not confidential, and asks for it anyway.
BUILTIN_CLIENT_ID = ''
BUILTIN_CLIENT_SECRET = ''
UNAVAILABLE = "Google sign-in isn't available in this build yet."
LAPSED = 'the Google calendar sign-in has lapsed - press Sign in with Google for the calendar on the Gmail card'
_FLOWS: dict = {}          # state -> {cid, verifier, at, done: (ok, what to say) once Google has sent the browser back}
_TOK, _LOCK = {}, threading.Lock()     # refresh token -> (access token, expires at)


def redirect_uri(server: dict) -> str: return f"http://127.0.0.1:{server.get('port') or 7787}/api/google/calendar/callback"
def connected(cfg: dict) -> bool: return bool((cfg or {}).get('google_refresh_token'))
def builtin() -> tuple: return ((os.getenv('TASKUARY_GOOGLE_CLIENT_ID') or BUILTIN_CLIENT_ID).strip(),
                                (os.getenv('TASKUARY_GOOGLE_CLIENT_SECRET') or BUILTIN_CLIENT_SECRET).strip())


def client(cfg: dict) -> tuple:
    """(id, secret) the card's Google token was minted with - a token only renews with its own client. A sign-in here says which
    (google_signin); a token pasted beside the card's own client is that client's; anything else is Taskuary's."""
    return builtin() if (cfg or {}).get('google_signin') == 'builtin' else signin_client(cfg)


def signin_client(cfg: dict) -> tuple:
    """(id, secret) a NEW sign-in goes with: the card's own client when its admin fold holds one, else Taskuary's."""
    own = ((cfg or {}).get('google_client_id') or '', (cfg or {}).get('google_client_secret') or '')
    return own if all(own) else builtin()


def available(cfg: dict) -> bool: return all(signin_client(cfg))


def _gmail(store, cid):
    c = store.get_connector(int(cid), with_secret=True)
    if not c or c.get('Type') != 'gmail': raise LookupError('Sign in with Google for the calendar lives on the Gmail card')
    return c, json.loads(c.get('ConfigJson') or '{}')


def start(store, cid: int, server: dict) -> dict:
    """{flow, url}: where the browser goes to say yes, and the id the card polls with. ValueError (said as is) with no client."""
    _, cfg = _gmail(store, cid)
    if not available(cfg): raise ValueError(UNAVAILABLE)
    gid, gsec = signin_client(cfg)
    for k, v in list(_FLOWS.items()):
        if time.time() - v['at'] > TTL: _FLOWS.pop(k, None)
    state, verifier = secrets.token_urlsafe(24), secrets.token_urlsafe(48)
    _FLOWS[state] = {'cid': int(cid), 'verifier': verifier, 'at': time.time(), 'done': None, 'client': (gid, gsec)}
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b'=').decode()
    # include_granted_scopes: a card that already allowed saving files (drive.file) keeps it on the new token
    return {'flow': state, 'url': G_AUTH + '?' + urlencode({
        'client_id': gid, 'redirect_uri': redirect_uri(server), 'response_type': 'code', 'scope': SCOPE,
        'access_type': 'offline', 'prompt': 'consent', 'state': state, 'include_granted_scopes': 'true',
        'code_challenge': challenge, 'code_challenge_method': 'S256'})}


def callback(store, server: dict, code: str, state: str, error: str = None) -> tuple:
    """(ok, what to say). Exchanges the code with the round's own verifier and keeps the refresh token on the card. A state answers once."""
    f = _FLOWS.get(str(state or ''))
    if not f or f.get('claimed') or time.time() - f['at'] > TTL:
        return False, 'This sign-in was not started here, or it is too old - press Sign in with Google for the calendar on the Gmail card again.'
    f['claimed'] = True
    f['done'] = _exchange(store, server, f, code, error)
    return f['done']


def _exchange(store, server, f, code, error) -> tuple:
    if error: return False, f'Google said: {error}'
    if not code: return False, 'Google sent no code back.'
    try: _, cfg = _gmail(store, f['cid'])
    except LookupError as e: return False, str(e)
    gid, gsec = f['client']              # the code answers to the client it was asked with, whatever the card holds now
    r = requests.post(G_TOKEN, timeout=20, data={'client_id': gid, 'client_secret': gsec, 'code': code, 'code_verifier': f['verifier'],
                                                'grant_type': 'authorization_code', 'redirect_uri': redirect_uri(server)})
    if r.status_code != 200: return False, f'Google refused the sign-in ({r.status_code}).'
    j = r.json() or {}
    if not j.get('refresh_token'): return False, 'Google returned no refresh token - nothing was changed.'
    granted = str(j.get('scope') or '')
    # Google's consent page lets each permission be unticked: a token without the calendar is no calendar
    if SCOPE not in granted.split() and 'https://www.googleapis.com/auth/calendar' not in granted.split():
        return False, 'Google did not grant calendar access - the box for it was left unticked. Nothing was changed.'
    own = f['client'] == (cfg.get('google_client_id') or '', cfg.get('google_client_secret') or '')
    cfg.update({'google_refresh_token': j['refresh_token'], 'google_scope': granted, 'google_signin': 'own' if own else 'builtin'})
    store.save_connector({'ConnectorId': f['cid'], 'ConfigJson': json.dumps(cfg)}, 'owner')
    store.audit('connector', f['cid'], 'google_calendar', 'owner', detail={'scope': granted})
    with _LOCK: _TOK[j['refresh_token']] = (j.get('access_token') or '', time.time() + int(j.get('expires_in') or 3600))
    from . import calendar
    for c in (calendar._REPLY, calendar._UPCOMING, calendar._TODAY): c['data'] = None     # the next read sees the new calendar
    return True, f"Taskuary now reads the Google calendar of {cfg.get('address') or 'this account'} - read-only."


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


def access_token(cfg: dict) -> str:
    """A live access token off the card's refresh token - cached until a minute before it expires, minted again after.
    Google refusing the refresh token (revoked, or a test-mode client's week run out) is a lapse, said with its fix."""
    rt = cfg.get('google_refresh_token')
    if not rt: raise RuntimeError('not signed in - press Sign in with Google for the calendar on the Gmail card')
    with _LOCK:
        hit = _TOK.get(rt)
        if hit and hit[0] and hit[1] > time.time() + 60: return hit[0]
        gid, gsec = client(cfg)
        r = requests.post(G_TOKEN, timeout=20, data={'client_id': gid, 'client_secret': gsec, 'refresh_token': rt, 'grant_type': 'refresh_token'})
        if r.status_code in (400, 401) and 'invalid_grant' in r.text: raise RuntimeError(LAPSED)
        if r.status_code != 200: raise RuntimeError(f'Google token failed ({r.status_code}): {r.text[:200]}')
        j = r.json()
        _TOK[rt] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600))
        return j['access_token']
