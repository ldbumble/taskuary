"""A VENDOR'S REST API, READ WITH A KEY (the owner, 2026-11-08: "all the ones that say coming soon just add them now").

One road for every card whose whole integration is "read this vendor's API with what the owner pasted": DigitalOcean, Terraform Cloud,
Better Stack, CircleCI, Buildkite, Coda, Intrinio, Benzinga, Tradier, Diffbot, the self-hosted ones whose address is on the card (Jenkins,
SonarQube, Elasticsearch, Splunk, Dynatrace, Kubernetes), Google Drive and OneDrive on the sign-ins the app already has - and (the owner,
2026-11-08: "hurry finish it all") the ones whose key is not the whole story: a token swapped first (Docker Hub, Schwab, Workday, Dataverse,
SAP, ADP, PointClickCare), a key signed into each call (NetSuite's OAuth 1.0a, Google Cloud's service account, Epic and Cerner's SMART
backend-services JWT), credentials that ride in the body (Plaid), and the vendors whose reads are POSTs (UptimeRobot, Plaid, SuiteQL,
Cloud Logging, Browserbase / Oxylabs / Bright Data fetches). And the cards that sign in by OAuth (auth "oauth": Box, Zoom, HubSpot,
Salesforce, DocuSign...; the row's `oauth` block is oauth.py's), read with the tokens their own Sign in left.

THE TABLE IS apireads.json, read by this module and by the Connections page (one row: the base or the card's address, how the key rides,
the cheap read its Test makes, the vendor's page it was read off). A new vendor is a row. Each card's report / agent type is `<type>_read`:
{"path": "/v2/droplets", "params": {...}} - a GET under that base. THEY ARE ALL READS: a GET, or a POST only to a path the row lists as a
read (`post`: UptimeRobot's getMonitors, Plaid's /accounts/get, a scraper's fetch) - never PUT, PATCH or DELETE; the path cannot leave the
base, and a redirect is not followed. A Tradier key that could trade places no order here. A `post` entry is the path itself or a pattern
it must match whole (Google Analytics' /properties/<id>:runReport).

The CRMs, analytics, BI, commerce, billing, shipping and time trackers ("yes do all of them") ride the same rows: a row's strings are
templates over the card's own fields ({user}, {store_hash}), the key ({key}, {key_tail}: Mailchimp's data centre after the dash) and the
row's `defaults`; a field the card lacks says its name. `token`: the vendor swaps the card's credentials for a short-lived bearer first
(OAuth client credentials, a Looker / Tableau / Veeva / Toast sign-in) - minted once, cached till it expires. Google Analytics, Search
Console and Ads read on the Google sign-in, Power BI on the Outlook card's Microsoft one; Ghost signs each call with its Admin key.
"""
import base64, hashlib, hmac, json, re, secrets, time
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlsplit, parse_qsl
import requests

TIMEOUT, BODY_CHARS = 30, 20000
BORROWED = ('google_drive', 'onedrive', 'office365_files')     # no key of their own: the app's Google and Microsoft sign-ins (STORE_BACKED)
SIGN_INS = {'google': "the Google Sheets card's Google sign-in", 'graph': "the Outlook card's Microsoft sign-in",
            'powerbi': "the Outlook card's Microsoft sign-in", 'oauth': "the card's own Sign in"}
SWAPS = ('jwt_swap', 'gcp_sa', 'smart', 'refresh', 'client_credentials')   # the key swapped for a bearer by _swap
POWERBI = 'https://analysis.windows.net/powerbi/api/.default'
FIELD = re.compile(r'[\w.-]+')                                 # a card field that lands inside a base or a path: a name, never a path of its own
_TOK = {}                                                       # (type, who) -> (access token, expires) - one swap per hour, not per read


@lru_cache(maxsize=1)
def table() -> dict: return json.loads(Path(__file__).with_name('apireads.json').read_text(encoding='utf-8'))['services']
def types() -> tuple: return tuple(table())
def rtype(t: str) -> str: return f'{t}_read'
def card_of(rt: str) -> str | None: return rt[:-5] if rt.endswith('_read') and rt[:-5] in table() else None
def write_only() -> dict: return {t: tuple(r['write_only']) for t, r in table().items() if r.get('write_only')}
def auth_of(s: dict, cfg: dict) -> str: return s['alt'][1] if s.get('alt') and cfg.get(s['alt'][0]) else s['auth']   # SAP: basic, or OAuth once a token URL is given


class NotARead(PermissionError, ValueError):
    "A body sent where the row names no read by POST: refused before anything leaves."


class Fields(dict):
    "A row's template fields: its defaults, the card's own, the key; one the card lacks names itself."
    def __init__(self, t, cfg, key='', **extra):
        own = {k: str(v) for k, v in (cfg or {}).items() if isinstance(v, (str, int, float)) and str(v).strip() and k != 'store'}
        super().__init__({**(table()[t].get('defaults') or {}), **own, 'key': key or '', 'key_tail': (key or '').rsplit('-', 1)[-1], **extra})
        self.t = t
    def __missing__(self, k): raise RuntimeError(f"{table()[self.t]['title']} needs its {k.replace('_', ' ')} on the card")
def fill(v, f):
    "A template string, or a dict / list of them, filled from the fields."
    if isinstance(v, dict): return {k: fill(x, f) for k, x in v.items()}
    if isinstance(v, list): return [fill(x, f) for x in v]
    return v.format_map(f) if isinstance(v, str) else v
def _names(s: str, f) -> str:
    "Only {name} placeholders, each a plain name - what lands in a base or a path cannot climb out of it."
    def one(m):
        v = str(f[m.group(1)]).strip()
        if not FIELD.fullmatch(v): raise ValueError(f'{m.group(1)} must be a plain name, not {v[:60]!r}')
        return v
    return re.sub(r'\{([a-z_]+)\}', one, s)


def _fill(tpl: str, cfg: dict, host=False) -> str:
    "A row's {placeholders} from the card (or its Fields) - in a host only letters, digits, - and . (NetSuite's 1234567_SB1 is host 1234567-sb1)."
    def one(m):
        v = str(cfg.get(m.group(1)) or '').strip()
        if host: v = v.lower().replace('_', '-')
        if not v or not re.fullmatch(r'[A-Za-z0-9._-]+' if host else r'[A-Za-z0-9._~-]+', v): raise RuntimeError(f'the card needs its {m.group(1).replace("_", " ")}')
        return v
    return re.sub(r'\{(\w+)\}', one, tpl)


def base_of(t: str, cfg: dict, key: str = '') -> str:
    s = table()[t]
    if s.get('base'): return _fill(s['base'], Fields(t, cfg, key), host=True).rstrip('/')
    host = str(cfg.get('host') or s.get('default_host') or '').strip().rstrip('/')
    if not host: raise RuntimeError(f"{s['title']} needs its address on the card ({s.get('host_hint') or 'https://...'})")
    if not host.startswith(('https://', 'http://')): host = f'https://{host}'
    return host + _names(s.get('suffix') or '', Fields(t, cfg, key))


def _path(p) -> str:
    p = str(p or '').strip()
    if not p.startswith('/') or p.startswith('//') or '://' in p or '\\' in p or '@' in p or '..' in p: raise ValueError(f'a path under the API, starting with / - not {p[:80]!r}')
    return p


def url_of(t: str, cfg: dict, path: str, base: str | None = None) -> str:
    "Google Cloud's row names no one host: the path's first part is the service - /run/v2/... is run.googleapis.com/v2/..."
    s, p = table()[t], _path(path)
    if not s.get('service_host'): return (base if base is not None else base_of(t, cfg)) + p
    svc, _, rest = p[1:].partition('/')
    if not re.fullmatch(r'[a-z][a-z0-9-]*', svc): raise ValueError(f'start the path with a Google service name (/run/v2/...), not {p[:60]!r}')
    return f"https://{svc}.{s['service_host']}/{rest}"


def _dig(j, path: str):
    for k in path.split('.'): j = (j or {}).get(k) if isinstance(j, dict) else None
    return j


def _ghost(key: str) -> str:
    "Ghost's Admin API key is id:secret; each call carries a five-minute JWT signed with the secret (HS256)."
    kid, _, sec = (key or '').partition(':')
    if not (kid and sec): raise RuntimeError('a Ghost Admin API key looks like <id>:<secret> - copy the whole key from the custom integration')
    b64 = lambda d: base64.urlsafe_b64encode(json.dumps(d, separators=(',', ':')).encode()).rstrip(b'=').decode()
    now = int(time.time())
    head = f"{b64({'alg': 'HS256', 'typ': 'JWT', 'kid': kid})}.{b64({'iat': now, 'exp': now + 300, 'aud': '/admin/'})}"
    try: sig = hmac.new(bytes.fromhex(sec), head.encode(), hashlib.sha256).digest()
    except ValueError: raise RuntimeError('the secret half of a Ghost Admin API key is hex - copy the whole key again') from None
    return f"{head}.{base64.urlsafe_b64encode(sig).rstrip(b'=').decode()}"


def _minted(t: str, cfg: dict, key: str, base: str) -> dict:
    "The row's `token`: the card's credentials swapped for a bearer (and any `vars` the answer carries), cached until a minute before expiry."
    from . import net
    s, f = table()[t]['token'], Fields(t, cfg, key)
    url = s['url'] if s['url'].startswith('https://') else base + _path(_names(s['url'], f))
    body, user = fill(s.get('body') or {}, f), fill(s.get('basic') or '', f)
    def mint():
        r = requests.post(url, timeout=TIMEOUT, allow_redirects=False, headers={'Accept': 'application/json', **fill(s.get('headers') or {}, f)},
                          auth=tuple(user.split(':', 1)) if user else None, **({'json': body} if s.get('style') == 'json' else {'data': body}))
        if r.status_code >= 300: raise RuntimeError(f"{table()[t]['title']} refused the sign-in ({r.status_code}) - check what is on the card: {r.text[:200]}")
        j = r.json()
        tok = _dig(j, s.get('take') or 'access_token')
        if not tok: raise RuntimeError(f"{table()[t]['title']} signed in but handed back no token")
        return json.dumps({'token': tok, **{k: _dig(j, p) for k, p in (s.get('vars') or {}).items()}}), _dig(j, s.get('ttl_at') or 'expires_in') or s.get('ttl') or 3600
    kid = hashlib.sha256(json.dumps([url, body, user, key], sort_keys=True).encode()).hexdigest()
    return json.loads(net.token(('apireads', t, kid), mint))


def _token(store, t: str, cfg: dict, key: str) -> str:
    "The app's own sign-ins: the Google Sheets card's token, the Outlook card's Microsoft one (Graph or Power BI), or the card's own OAuth."
    s = table()[t]
    if s['auth'] == 'google':
        from . import sheets
        return sheets._token(sheets.google_sheets_connection(store))
    if s['auth'] == 'graph':
        from .outbound import _graph_token
        return _graph_token(store, 'outlook')
    if s['auth'] == 'powerbi':
        from .outbound import Fixable, _graph_token
        try: return _graph_token(store, 'outlook', scope=POWERBI)
        except Fixable: raise                                 # no Outlook card yet: its own words say where to set it up
        except RuntimeError as e:                             # ...a refusal is this sign-in lacking Power BI, not a lapse
            raise RuntimeError(f"the Outlook card's Microsoft sign-in did not reach Power BI ({e}) - your company's Microsoft app needs the Power BI "
                               'Service permissions (Report.Read.All, Dataset.Read.All, Workspace.Read.All), then Sign in with Microsoft again') from e
    if s['auth'] == 'oauth':
        from . import oauth
        from .reports import _connector
        if not (c := _connector(store, t, cfg.get('connector_id'), with_secret=True)): raise RuntimeError(f"there is no {s['title']} card")
        return oauth.access(store, c)
    return key


def _need(cfg, *ks):
    if (miss := [k for k in ks if not cfg.get(k)]): raise RuntimeError(f"the card needs its {', '.join(k.replace('_', ' ') for k in miss)}")


def _pem(k: str) -> str:
    "A private key pasted into a one-line box arrives with its line breaks gone - put them back."
    k = k.strip().replace('\\n', '\n')
    m = re.match(r'(-----BEGIN [A-Z ]+-----)\s*(.+?)\s*(-----END [A-Z ]+-----)$', k, re.S)
    if not m: return k
    body = re.sub(r'\s+', '', m.group(2))
    return f'{m.group(1)}\n{body}\n{m.group(3)}\n'


def _swap(t: str, s: dict, cfg: dict, key: str) -> str:
    "The access token a key is swapped for, kept until a minute before it expires."
    mode = auth_of(s, cfg)
    who = hashlib.sha256(f"{mode}|{cfg.get('client_id')}|{cfg.get('user')}|{cfg.get('host')}|{cfg.get('token_url')}|{key}".encode()).hexdigest()
    tok, exp = _TOK.get((t, who), ('', 0))
    if tok and exp > time.time() + 60: return tok
    here = lambda tpl: _fill(str(tpl or '').replace('{host}', base_of(t, cfg) if '{host}' in str(tpl or '') else ''), cfg)
    url = here(cfg.get('token_url') or s.get('token_url'))           # Workday's is under the tenant's own host, Dataverse's under its tenant
    if mode != 'gcp_sa' and not url: raise RuntimeError(f"{s['title']} needs its token URL on the card")
    if mode == 'jwt_swap':
        _need(cfg, 'user')
        j = _post_token(t, url, json={'identifier': cfg['user'], 'secret': key})
        tok, ttl = j.get('access_token') or j.get('token'), 600
    elif mode == 'gcp_sa':
        try:
            from google.oauth2 import service_account
            from google.auth.transport.requests import Request
        except ImportError:
            from .deps import Missing
            raise Missing('google.auth', 'the Google Cloud card needs google-auth - install it from the card, or run: pip install taskuary[gcp]') from None
        try: info = json.loads(key)
        except ValueError: raise RuntimeError('paste the whole service-account key file (the JSON) as the key') from None
        c = service_account.Credentials.from_service_account_info(info, scopes=[s['scope']])
        c.refresh(Request())
        tok, ttl = c.token, 3000
    else:
        if mode == 'smart':
            _need(cfg, 'client_id')
            try: import jwt
            except ImportError:
                from .deps import Missing
                raise Missing('jwt', f"the {s['title']} card signs with PyJWT - install it from the card, or run: pip install taskuary[fhir]") from None
            now = int(time.time())
            a = jwt.encode({'iss': cfg['client_id'], 'sub': cfg['client_id'], 'aud': url, 'jti': secrets.token_hex(16), 'iat': now, 'exp': now + 290},
                           _pem(key), algorithm='RS384', headers={'kid': cfg['kid']} if cfg.get('kid') else None)
            data = {'grant_type': 'client_credentials', 'client_assertion_type': 'urn:ietf:params:oauth:client-assertion-type:jwt-bearer',
                    'client_assertion': a, 'scope': cfg.get('scope') or s.get('scope') or ''}
            cred = None
        else:
            _need(cfg, 'client_id')
            sec = cfg.get('client_secret') if mode == 'refresh' else key
            data = {'grant_type': 'refresh_token', 'refresh_token': key} if mode == 'refresh' else {'grant_type': 'client_credentials'}
            if cfg.get('scope') or s.get('scope'): data['scope'] = here(cfg.get('scope') or s['scope'])     # Dataverse's: {host}/.default
            cred = (cfg['client_id'], sec or '') if s.get('client_auth', 'basic') == 'basic' else None
            if not cred: data.update(client_id=cfg['client_id'], client_secret=sec or '')
        j = _post_token(t, url, data=data, auth=cred, cert=_cert(s, cfg))
        tok, ttl = j.get('access_token'), int(j.get('expires_in') or 1800)
    if not tok: raise RuntimeError(f"{s['title']} gave no access token back")
    _TOK[(t, who)] = (tok, time.time() + ttl)
    return tok


def _post_token(t, url, **kw) -> dict:
    if not url.startswith('https://'): raise RuntimeError(f"{table()[t]['title']}: the token URL must be https://")
    r = requests.post(url, timeout=TIMEOUT, allow_redirects=False, headers={'Accept': 'application/json'}, **{k: v for k, v in kw.items() if v is not None})
    if r.status_code >= 300:
        raise RuntimeError(f"{table()[t]['title']} refused the sign-in ({r.status_code}) - check what is on the card: {r.text[:200]}")
    return r.json()


def _cert(s, cfg):
    "ADP's partner certificate: the TLS client certificate and its key, as files on this computer."
    if not s.get('client_cert'): return None
    _need(cfg, 'cert_file', 'key_file')
    return (cfg['cert_file'], cfg['key_file'])


def _oauth1(s, cfg, key, method, url, params) -> str:
    """NetSuite token-based auth: OAuth 1.0a, HMAC-SHA256, the account id as realm (netsuite.com: "the authorization header").
    The card's secret is the TOKEN secret; the consumer secret is a write-only field beside it."""
    _need(cfg, 'account', 'consumer_key', 'token_id', 'consumer_secret')
    e = lambda x: quote(str(x), safe='~')
    o = {'oauth_consumer_key': cfg['consumer_key'], 'oauth_token': cfg['token_id'], 'oauth_signature_method': 'HMAC-SHA256',
         'oauth_timestamp': str(int(time.time())), 'oauth_nonce': secrets.token_hex(12), 'oauth_version': '1.0'}
    u = urlsplit(url)
    ps = sorted((e(k), e(v)) for k, v in [*parse_qsl(u.query), *(params or {}).items(), *o.items()])
    base = '&'.join([method.upper(), e(f'{u.scheme}://{u.netloc}{u.path}'), e('&'.join(f'{k}={v}' for k, v in ps))])
    sig = base64.b64encode(hmac.new(f"{e(cfg['consumer_secret'])}&{e(key)}".encode(), base.encode(), hashlib.sha256).digest()).decode()
    realm = str(cfg['account']).upper().replace('-', '_')
    return 'OAuth ' + ', '.join([f'realm="{realm}"', *(f'{k}="{e(v)}"' for k, v in {**o, 'oauth_signature': sig}.items())])


def request_parts(t: str, cfg: dict, key: str, store=None) -> tuple:
    "(url base, headers, params, template fields) for one card - how its key rides, read off the table."
    s = table()[t]; a = auth_of(s, cfg)
    if not key and not s.get('keyless') and not (a in SIGN_INS and not s.get('key')): raise RuntimeError(f"no {s['title']} key saved - paste it on the {s['title']} card")
    base, tok, extra = (base_of(t, cfg, key) if not s.get('service_host') else ''), key, {}
    if s.get('token'): got = _minted(t, cfg, key, base); tok, extra = got.pop('token'), got
    f = Fields(t, cfg, key, token=tok, **{k: str(v) for k, v in extra.items() if v is not None})
    h, q = fill(dict(s.get('headers') or {}), f), {}
    if a in SIGN_INS: h['Authorization'] = f'Bearer {_token(store, t, cfg, key)}'
    elif a == 'query': q[s['param']] = tok
    elif a == 'basic':
        fb = Fields(t, cfg, key, token=tok, **{k: str(v) for k, v in extra.items() if v is not None})
        if 'user' not in fb: fb['user'] = s.get('user') or ''     # Mailgun's user is always "api"; Jenkins' is the card's
        h['Authorization'] = 'Basic ' + base64.b64encode(fill(s.get('basic') or '{user}:{key}', fb).encode()).decode()
    elif a == 'ghost': h['Authorization'] = f'Ghost {_ghost(key)}'
    elif a in SWAPS: h['Authorization'] = f'Bearer {_swap(t, s, cfg, key)}'
    elif a in ('oauth1', 'form', 'plaid'): pass                    # signed per call / riding in the body: call() puts it there
    elif tok: h[s.get('header') or 'Authorization'] = (s.get('format') or 'Bearer {key}').format(key=tok)
    return base, {k: v for k, v in h.items() if v}, q, f


def _posts(s: dict, bare: str) -> bool:
    "A path the row names as a read by POST: the path itself, or a pattern it matches whole."
    return any(p == bare or re.fullmatch(p, bare) for p in s.get('post') or ())


def call(t: str, cfg: dict, key: str, path: str, params: dict | None = None, body=None, store=None):
    """One read. A body goes only to a path the row lists as a read (`post`) - every other call is a GET; nothing else is ever sent."""
    s = table()[t]; a = auth_of(s, cfg)
    base, h, q, f = request_parts(t, cfg, key, store)
    path = _path(_names(_path(path), f))
    url, params = url_of(t, cfg, path, base), {**(params or {}), **q}
    bare = path.split('?')[0]
    post = _posts(s, bare) and (body is not None or s.get('post_only'))
    if body is not None and not post:
        raise NotARead(f"{s['title']}{' is read by GET only -' if not s.get('post') else ':'} {bare} is not one of the reads this card may POST to "
                       f"({', '.join(s.get('post') or ()) or 'none'})")
    if s.get('post_only') and not post: raise NotARead(f"{s['title']} reads by POST to {', '.join(s['post'])} - not {bare}")
    if post: body = {} if body is None else dict(body) if isinstance(body, dict) else body
    else: body = None
    if a == 'form': body[s['param']] = key
    if a == 'plaid':
        _need(cfg, 'client_id')
        body.update(client_id=cfg['client_id'], secret=key, **({'access_token': cfg['access_token']} if cfg.get('access_token') else {}))
    if a == 'oauth1': h['Authorization'] = _oauth1(s, cfg, key, 'POST' if post else 'GET', url, params)
    kw = dict(headers={'Accept': 'application/json', **h}, params=params, timeout=TIMEOUT, allow_redirects=False, cert=_cert(s, cfg))
    # IBKR's gateway runs on this computer with a certificate it made itself: trusted only there, never for an address off the machine
    if s.get('local_tls') and urlsplit(url).hostname in ('localhost', '127.0.0.1', '::1'): kw['verify'] = False
    r = requests.post(url, **({'data': body} if s.get('body_as') == 'form' else {'json': body}), **kw) if post else requests.get(url, **kw)
    if r.status_code >= 300:
        why = (f" - the key was refused{'; ' + s['scope_hint'] if s.get('scope_hint') else ''}" if r.status_code in (401, 403) else '')
        raise RuntimeError(f"{s['title']} answered {r.status_code}{why}: {r.text[:200]}")
    try: return r.json()
    except ValueError: return feed(r.text) if '<rss' in r.text[:500] or '<feed' in r.text[:500] else r.text


def feed(xml: str) -> list:
    "An RSS/Atom page as its posts - title, link, date - rather than markup (Substack has no API, only its feed)."
    tag = lambda b, n: (m.group(1).strip() if (m := re.search(rf'<{n}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{n}>', b, re.S)) else '')
    link = lambda b: tag(b, 'link') or (m.group(1) if (m := re.search(r'<link[^>]*href="([^"]+)"', b)) else '')
    return [{'title': tag(b, 'title'), 'link': link(b), 'date': tag(b, 'pubDate') or tag(b, 'updated'), 'summary': tag(b, 'description')[:500]}
            for b in re.findall(r'<(?:item|entry)[\s>].*?</(?:item|entry)>', xml, re.S)][:50]


def get(t: str, cfg: dict, key: str, path: str, params: dict | None = None, store=None, body=None): return call(t, cfg, key, path, params, body, store)


def runner(t: str):
    "The `<type>_read` executor for one card: {path, params, body} -> (headline, the JSON it answered)."
    s = table()[t]
    def run(cfg):
        probe = not cfg.get('path')
        if probe and not s['probe']: raise RuntimeError(f"{s['title']} needs a path to read - e.g. {s['example']}")
        p = cfg.get('path') or s['probe']
        body = (cfg.get('body') if isinstance(cfg.get('body'), (dict, list)) else None) if not probe else s.get('probe_body')
        j = call(t, cfg, cfg.get('api_key') or '', p, cfg.get('params') if isinstance(cfg.get('params'), dict) else None, body, cfg.get('store'))
        n = len(j) if isinstance(j, list) else next((len(v) for v in (j.values() if isinstance(j, dict) else ()) if isinstance(v, list)), None)
        return (f"{s['title']}: {n} items" if n is not None else f"{s['title']} answered"), json.dumps(j, indent=1, default=str)[:BODY_CHARS]
    verb = f" (POST {', '.join(s['post'])} with \"body\")" if s.get('post') else ''
    run.__doc__ = f'{{"path": "{s.get("example") or s["probe"]}", "params": {{}}}} - a read under {s["title"]}\'s API with the card\'s key{verb}. Reads only.'
    return run


def test(store, c) -> str:
    "The card's Test: its cheap read - or, where the vendor has no cheap one (a tracking lookup needs a number), its sign-in."
    from .reports import _card
    t, s = c['Type'], table()[c['Type']]
    cfg = {**_card(store, t, 'api_key', c['ConnectorId']), 'connector_id': c['ConnectorId'], 'store': store}
    if not s['probe']:
        request_parts(t, cfg, cfg.get('api_key') or '', store)
        return f"{s['title']} signed you in - the key works (a read names its path, e.g. {s['example']})"
    head, _ = runner(t)(cfg)
    return f'{head} - the key works ({table()[t]["probe"]})'
