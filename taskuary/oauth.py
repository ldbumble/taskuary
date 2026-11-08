"""ONE SIGN-IN ROAD for every vendor that hands out tokens through OAuth 2.0 (authorization code, PKCE where the vendor takes it) -
Basecamp, Box, DocuSign, HubSpot, Salesforce, Threads, Webex, Zoom, and whatever comes next (`register`).

BRING YOUR OWN APP, as Microsoft is (the owner, 2026-11-05): there is no shared Taskuary app at any vendor. The owner registers one in
the vendor's developer console, pastes its Client ID and Secret on the card (each saves itself), and adds the card's redirect URL there.

THE REDIRECT IS LOOPBACK - http://127.0.0.1:<port>/api/oauth/callback, Taskuary's own server on this computer, so nothing needs a public
address (the address, not "localhost": Zoom takes only that). A vendor that refuses an http address (Meta's Threads) takes the card's
`redirect_base`: an https address the owner already points at this computer (their own tunnel), and the same path under it. Either way
the code comes back to this machine only.

WHAT PROVES A RETURN is the one-time `state` start() issued (15 minutes, answered once) and, where the vendor takes it, the PKCE verifier
that never left this process. The tokens - access, refresh, expiry - are the card's Secret, one JSON sealed like every secret (vault.py);
`access` renews them a minute before they lapse and keeps whatever new refresh token the vendor rotates in (Box, Zoom). Starting a sign-in
is a POST under /api/connectors, refused to an agent (guard.DENIED) and to the demo (demo.REFUSALS): only the owner presses Sign in.

A VENDOR'S ROW is its `oauth` block in apireads.json (the same row that says how its API is read): `authorize`, `token`, `scopes`, `pkce`,
`client` ("basic" when the secret rides as HTTP Basic), `params` / `token_params` the vendor wants beside the standard ones, `keep`
(token-response keys the card keeps, and under which name: Salesforce's instance_url is its API host), `defaults` / `hosts` (a host
the card may change - a Salesforce My Domain - and the names it must end in), and for Threads `long_lived` / `renew`: Meta swaps the short token for a 60-day one and renews it by GET, not with a refresh token.
"""
import base64, hashlib, json, re, secrets, threading, time
from urllib.parse import urlencode
import requests

TTL, TIMEOUT, PATH = 15 * 60, 30, '/api/oauth/callback'
_FLOWS, _LOCKS, _EXTRA, _GUARD = {}, {}, {}, threading.Lock()


class OAuthError(RuntimeError): pass


def register(t: str, spec: dict): _EXTRA[t] = spec          # a card whose row is not in apireads.json (its own module's)
def spec(t: str) -> dict | None:
    if t in _EXTRA: return _EXTRA[t]
    from .apireads import table
    r = table().get(t) or {}
    return {'title': r.get('title', t), **r['oauth']} if r.get('oauth') else None
def types() -> tuple:
    from .apireads import table
    return (*_EXTRA, *(t for t, r in table().items() if r.get('oauth')))
def _conf(c) -> dict:
    try: return json.loads((c or {}).get('ConfigJson') or '{}') or {}
    except ValueError: return {}
def _challenge(v: str) -> str: return base64.urlsafe_b64encode(hashlib.sha256(v.encode()).digest()).rstrip(b'=').decode()


def _url(sp: dict, key: str, conf: dict) -> str:
    "A vendor URL with the card's own host filled in ({login_host}, {auth_host}) - a host the vendor's row allows, never a path."
    vals = {**sp.get('defaults', {}), **{k: str(conf.get(k) or '').strip().lower() for k in sp.get('defaults', {}) if conf.get(k)}}
    for k, v in vals.items():
        v = re.sub(r'^https://', '', v).rstrip('/')
        if not re.fullmatch(r'[a-z0-9.-]+', v) or not any(v == h.lstrip('.') or v.endswith(h) for h in sp.get('hosts') or [v]):
            raise OAuthError(f"{v!r} is not a {sp['title']} sign-in address")
        vals[k] = v
    return sp[key].format(**vals)


def redirect_uri(server: dict, conf: dict | None = None) -> str:
    "What the vendor's app must list, exactly: loopback, or the owner's own https address in front of this computer."
    base = str((conf or {}).get('redirect_base') or '').strip().rstrip('/')
    if base and not re.fullmatch(r'https://[A-Za-z0-9.-]+(:\d+)?', base): raise OAuthError('the redirect address must be https://your.host, nothing after it')
    return (base or f"http://127.0.0.1:{(server or {}).get('port') or 7787}") + PATH


def bundle(c) -> dict:
    "The tokens a sign-in left on the card; a token pasted by hand is a bundle of one."
    s = str((c or {}).get('Secret') or '').strip()
    if not s: return {}
    try: b = json.loads(s)
    except ValueError: b = None
    return b if isinstance(b, dict) else {'access_token': s}


def _app(sp, conf):
    cid, sec = str(conf.get('client_id') or '').strip(), str(conf.get('client_secret') or '').strip()
    if not cid or (sp.get('secret', True) and not sec):
        raise OAuthError(f"paste the {sp['title']} app's Client ID and Client Secret on the card first - {sp.get('console') or 'from its developer console'}")
    return cid, sec


def start(store, cid: int, server: dict) -> str:
    "The vendor's consent page for this card, with a fresh one-time state (and PKCE challenge)."
    c = store.get_connector(cid, with_secret=True)
    sp = spec((c or {}).get('Type'))
    if not sp: raise OAuthError('this card does not sign in with OAuth')
    conf = _conf(c); client, _ = _app(sp, conf)
    st, ver, ru = secrets.token_urlsafe(24), secrets.token_urlsafe(48) if sp.get('pkce') else '', redirect_uri(server, conf)
    with _GUARD:
        for k in [k for k, f in _FLOWS.items() if time.time() - f['at'] > TTL]: del _FLOWS[k]
        _FLOWS[st] = {'cid': cid, 'ver': ver, 'at': time.time(), 'redirect': ru}
    q = {'response_type': 'code', 'client_id': client, 'redirect_uri': ru, 'state': st, **({'scope': sp['scopes']} if sp.get('scopes') else {}),
         **sp.get('params', {}), **({'code_challenge': _challenge(ver), 'code_challenge_method': 'S256'} if ver else {})}
    return _url(sp, 'authorize', conf) + '?' + urlencode(q)


def _said(r) -> dict:
    try: j = r.json()
    except ValueError: j = None
    return j if isinstance(j, dict) else {}


def _grant(sp, conf, data: dict) -> dict:
    "One token request: the code or a refresh token for tokens. A 200 carrying `error` is a refusal too."
    client, sec = _app(sp, conf)
    d, auth = {**sp.get('token_params', {}), **data}, None
    if sp.get('client') == 'basic': auth = (client, sec)
    else: d.update(client_id=client, **({'client_secret': sec} if sec else {}))
    r = requests.post(_url(sp, 'token', conf), data=d, auth=auth, headers={'Accept': 'application/json'}, timeout=TIMEOUT)
    j = _said(r)
    if r.status_code >= 400 or j.get('error') or not j.get('access_token'):
        why = j.get('error_description') or j.get('error') or j.get('error_message') or (r.text or '')[:200]
        raise OAuthError(f"{sp['title']} refused the sign-in ({r.status_code}): {why}")
    return j


def _swap(sp, conf, url_key: str, params: dict) -> dict:
    "Meta's GET swaps: the short token for a 60-day one, and a 60-day one for the next."
    r = requests.get(sp[url_key]['url'], params={**sp[url_key].get('params', {}), **params}, timeout=TIMEOUT)
    j = _said(r)
    if r.status_code >= 400 or not j.get('access_token'):
        why = j.get('error')
        raise OAuthError(f"{sp['title']} refused the token ({r.status_code}): {why.get('message') if isinstance(why, dict) else why or r.text[:200]}")
    return j


def _keep(store, c, sp, j: dict, old: dict | None = None) -> str:
    n = int(j.get('expires_in') or 0)
    b = {'access_token': j['access_token'], 'refresh_token': j.get('refresh_token') or (old or {}).get('refresh_token') or '',
         'expires_at': time.time() + n if n else 0}
    store.save_connector({'ConnectorId': c['ConnectorId'], 'Secret': json.dumps(b)}, 'owner')
    if keep := {to: j[k] for k, to in sp.get('keep', {}).items() if j.get(k)}: store.merge_connector_config(c['ConnectorId'], keep)
    return b['access_token']


def finish(store, code: str, state: str, error: str = '', said: str = '') -> tuple:
    "The vendor's redirect back: (ok, the words for the tab). Never a token in either."
    with _GUARD: f = _FLOWS.pop(str(state or ''), None)
    if not f or time.time() - f['at'] > TTL:
        return False, 'This sign-in was not started here, was already used, or is too old - press Sign in on the card again.'
    c = store.get_connector(f['cid'], with_secret=True)
    sp = spec((c or {}).get('Type'))
    if not sp: return False, 'that card is gone'
    if error: return False, f"{sp['title']} said: {said or error}"
    if not code: return False, f"{sp['title']} came back without a code"
    conf = _conf(c)
    try:
        j = _grant(sp, conf, {'grant_type': 'authorization_code', 'code': code, 'redirect_uri': f['redirect'], **({'code_verifier': f['ver']} if f['ver'] else {})})
        if sp.get('long_lived'): j = _swap(sp, conf, 'long_lived', {'client_secret': _app(sp, conf)[1], 'access_token': j['access_token']})
    except (OAuthError, requests.RequestException) as e: return False, str(e)[:300]
    _keep(store, c, sp, j)
    store.save_connector({'ConnectorId': c['ConnectorId'], 'Active': True}, 'owner')
    store.audit('connector', c['ConnectorId'], 'oauth_connected', 'owner', detail={'type': c['Type']})
    return True, f"{sp['title']} is signed in. Press Test on the card - it says which account and starts the sync."


def access(store, c) -> str:
    "A bearer for this card, renewed a minute before it lapses - one renewal at a time per card."
    sp = spec(c['Type']) or {'title': c['Type']}
    b = bundle(c)
    if not b.get('access_token'): raise OAuthError(f"{sp['title']} is not signed in yet - press Sign in with {sp['title']} on its card")
    if not b.get('expires_at') or b['expires_at'] > time.time() + 60: return b['access_token']
    with _GUARD: lock = _LOCKS.setdefault(c['ConnectorId'], threading.Lock())
    with lock:
        c = store.get_connector(c['ConnectorId'], with_secret=True) or c        # another thread may have renewed it already
        b, conf = bundle(c), _conf(c)
        if b.get('expires_at', 0) > time.time() + 60: return b['access_token']
        try:
            if sp.get('renew'): j = _swap(sp, conf, 'renew', {'access_token': b['access_token']})
            elif b.get('refresh_token'): j = _grant(sp, conf, {'grant_type': 'refresh_token', 'refresh_token': b['refresh_token'], **sp.get('refresh_params', {})})
            else: raise OAuthError('no refresh token was given')
        except (OAuthError, requests.RequestException) as e:
            raise OAuthError(f"{sp['title']} would not renew the sign-in - press Sign in on the card again ({str(e)[:200]})") from e
        return _keep(store, c, sp, j, b)


def status(store, cid: int, server: dict) -> dict:
    "What the card's Sign in box says (ConnectorsView OAuthConnect): the redirect URL to register, keys saved, signed in, days left."
    c = store.get_connector(cid, with_secret=True)
    sp, conf, b = spec(c['Type']) or {}, _conf(c), bundle(c)
    try: ru = redirect_uri(server, conf)
    except OAuthError as e: ru = str(e)
    lapse = 0 if b.get('refresh_token') else b.get('expires_at') or 0       # a token that renews itself has no days to count
    return {'redirect_uri': ru, 'connected': bool(b.get('access_token')), 'member': conf.get('me_name') or '',
            'has_app': bool(conf.get('client_id') and (conf.get('client_secret') or not sp.get('secret', True))),
            'days_left': max(0, int((lapse - time.time()) // 86400)) if lapse else None}
