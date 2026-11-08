"""A VENDOR'S REST API, READ WITH A KEY (the owner, 2026-11-08: "all the ones that say coming soon just add them now").

One road for every card whose whole integration is "read this vendor's API with what the owner pasted": DigitalOcean, Terraform Cloud,
Better Stack, CircleCI, Buildkite, Coda, Intrinio, Benzinga, Tradier, Diffbot, the self-hosted ones whose address is on the card (Jenkins,
SonarQube, Elasticsearch, Splunk, Dynatrace, Kubernetes), Google Drive and OneDrive on the sign-ins the app already has - and (the owner,
2026-11-08: "hurry finish it all") the ones whose key is not the whole story: a token swapped first (Docker Hub, Schwab, Workday, Dataverse,
SAP, ADP, PointClickCare), a key signed into each call (NetSuite's OAuth 1.0a, Google Cloud's service account, Epic and Cerner's SMART
backend-services JWT), credentials that ride in the body (Plaid), and the vendors whose reads are POSTs (UptimeRobot, Plaid, SuiteQL,
Cloud Logging, Browserbase / Oxylabs / Bright Data fetches). And the cards that sign in by OAuth (auth "oauth": Box, Zoom, HubSpot, Salesforce,
DocuSign...; the row's `oauth` block is oauth.py's), read with the tokens their own Sign in left.

THE TABLE IS apireads.json, read by this module and by the Connections page (one row: the base or the card's address, how the key rides,
the cheap read its Test makes, the vendor's page it was read off). A new vendor is a row. Each card's report / agent type is `<type>_read`:
{"path": "/v2/droplets", "params": {...}} - a GET under that base. THEY ARE ALL READS: a GET, or a POST only to a path the row lists as a
read (`post`: UptimeRobot's getMonitors, Plaid's /accounts/get, a scraper's fetch) - never PUT, PATCH or DELETE; the path cannot leave the
base, and a redirect is not followed. A Tradier key that could trade places no order here.
"""
import base64, hashlib, hmac, json, re, secrets, time
from functools import lru_cache
from pathlib import Path
from urllib.parse import quote, urlsplit, parse_qsl
import requests

TIMEOUT, BODY_CHARS = 30, 20000
BORROWED = ('google_drive', 'onedrive', 'office365_files')     # no key of their own: the app's Google and Microsoft sign-ins
_TOK = {}                                                       # (type, who) -> (access token, expires) - one swap per hour, not per read


@lru_cache(maxsize=1)
def table() -> dict: return json.loads(Path(__file__).with_name('apireads.json').read_text(encoding='utf-8'))['services']
def types() -> tuple: return tuple(table())
def rtype(t: str) -> str: return f'{t}_read'
def card_of(rt: str) -> str | None: return rt[:-5] if rt.endswith('_read') and rt[:-5] in table() else None
def write_only() -> dict: return {t: tuple(r['write_only']) for t, r in table().items() if r.get('write_only')}
def auth_of(s: dict, cfg: dict) -> str: return s['alt'][1] if s.get('alt') and cfg.get(s['alt'][0]) else s['auth']   # SAP: basic, or OAuth once a token URL is given


def _fill(tpl: str, cfg: dict, host=False) -> str:
    "A row's {placeholders} from the card - in a host only letters, digits, - and . (NetSuite's 1234567_SB1 is host 1234567-sb1)."
    def one(m):
        v = str(cfg.get(m.group(1)) or '').strip()
        if host: v = v.lower().replace('_', '-')
        if not v or not re.fullmatch(r'[A-Za-z0-9._-]+' if host else r'[A-Za-z0-9._~-]+', v): raise RuntimeError(f'the card needs its {m.group(1).replace("_", " ")}')
        return v
    return re.sub(r'\{(\w+)\}', one, tpl)


def base_of(t: str, cfg: dict) -> str:
    s = table()[t]
    if s.get('base'): return _fill(s['base'], cfg, host=True).rstrip('/')
    host = str(cfg.get('host') or s.get('default_host') or '').strip().rstrip('/')
    if not host: raise RuntimeError(f"{s['title']} needs its address on the card ({s.get('host_hint') or 'https://...'})")
    if not host.startswith(('https://', 'http://')): host = f'https://{host}'
    return host


def _path(p) -> str:
    p = str(p or '').strip()
    if not p.startswith('/') or p.startswith('//') or '://' in p or '\\' in p or '@' in p or '..' in p: raise ValueError(f'a path under the API, starting with / - not {p[:80]!r}')
    return p


def url_of(t: str, cfg: dict, path: str) -> str:
    "Google Cloud's row names no one host: the path's first part is the service - /run/v2/... is run.googleapis.com/v2/..."
    s, p = table()[t], _path(path)
    if not s.get('service_host'): return base_of(t, cfg) + p
    svc, _, rest = p[1:].partition('/')
    if not re.fullmatch(r'[a-z][a-z0-9-]*', svc): raise ValueError(f'start the path with a Google service name (/run/v2/...), not {p[:60]!r}')
    return f"https://{svc}.{s['service_host']}/{rest}"


def _token(store, t: str, cfg: dict, key: str) -> str:
    "Google Drive and OneDrive borrow the app's own sign-ins: the Google Sheets card's token, the Outlook card's Microsoft one."
    s = table()[t]
    if s['auth'] == 'google':
        from . import sheets
        return sheets._token(sheets.google_sheets_connection(store))
    if s['auth'] == 'graph':
        from .outbound import _graph_token
        return _graph_token(store, 'outlook')
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
    "(url base, headers, params) for one card - how its key rides, read off the table."
    s = table()[t]; a = auth_of(s, cfg)
    h, q = dict(s.get('headers') or {}), {}
    if a in ('google', 'graph', 'oauth'): h['Authorization'] = f'Bearer {_token(store, t, cfg, key)}'
    elif not key and not s.get('keyless'): raise RuntimeError(f"no {s['title']} key saved - paste it on the {s['title']} card")
    elif a == 'query': q[s['param']] = key
    elif a == 'basic':
        h['Authorization'] = 'Basic ' + base64.b64encode((s.get('basic') or '{user}:{key}').format(user=cfg.get('user') or s.get('user') or '', key=key).encode()).decode()
    elif a in ('jwt_swap', 'gcp_sa', 'smart', 'refresh', 'client_credentials'): h['Authorization'] = f'Bearer {_swap(t, s, cfg, key)}'
    elif a in ('oauth1', 'form', 'plaid'): pass                    # signed per call / riding in the body: send() puts it there
    elif key: h[s.get('header') or 'Authorization'] = (s.get('format') or 'Bearer {key}').format(key=key)
    return (base_of(t, cfg) if not s.get('service_host') else ''), h, q


def call(t: str, cfg: dict, key: str, path: str, params: dict | None = None, body=None, store=None):
    """One read. A body goes only to a path the row lists as a read (`post`) - every other call is a GET; nothing else is ever sent."""
    s = table()[t]; a = auth_of(s, cfg)
    _b, h, q = request_parts(t, cfg, key, store)
    url, params = url_of(t, cfg, path), {**(params or {}), **q}
    bare = _path(path).split('?')[0]
    post = bare in (s.get('post') or ()) and (body is not None or s.get('post_only'))
    if body is not None and not post: raise PermissionError(f"{s['title']}: {bare} is not one of the reads this card may POST to ({', '.join(s.get('post') or ()) or 'none'})")
    if s.get('post_only') and not post: raise PermissionError(f"{s['title']} reads by POST to {', '.join(s['post'])} - not {bare}")
    body = dict(body or {}) if post else None
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
        why = ' - the key was refused' if r.status_code in (401, 403) else ''
        raise RuntimeError(f"{s['title']} answered {r.status_code}{why}: {r.text[:200]}")
    try: return r.json()
    except ValueError: return feed(r.text) if '<rss' in r.text[:500] or '<feed' in r.text[:500] else r.text


def feed(xml: str) -> list:
    "An RSS/Atom page as its posts - title, link, date - rather than markup (Substack has no API, only its feed)."
    tag = lambda b, n: (m.group(1).strip() if (m := re.search(rf'<{n}[^>]*>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</{n}>', b, re.S)) else '')
    link = lambda b: tag(b, 'link') or (m.group(1) if (m := re.search(r'<link[^>]*href="([^"]+)"', b)) else '')
    return [{'title': tag(b, 'title'), 'link': link(b), 'date': tag(b, 'pubDate') or tag(b, 'updated'), 'summary': tag(b, 'description')[:500]}
            for b in re.findall(r'<(?:item|entry)[\s>].*?</(?:item|entry)>', xml, re.S)][:50]


def get(t: str, cfg: dict, key: str, path: str, params: dict | None = None, store=None): return call(t, cfg, key, path, params, None, store)


def runner(t: str):
    "The `<type>_read` executor for one card: {path, params, body} -> (headline, the JSON it answered)."
    s = table()[t]
    def run(cfg):
        probe = not cfg.get('path')
        p = _fill(cfg.get('path') or s['probe'], cfg) if probe else cfg['path']
        body = cfg.get('body') if not probe else s.get('probe_body')
        j = call(t, cfg, cfg.get('api_key') or '', p, cfg.get('params') if isinstance(cfg.get('params'), dict) else None, body, cfg.get('store'))
        n = len(j) if isinstance(j, list) else next((len(v) for v in (j.values() if isinstance(j, dict) else ()) if isinstance(v, list)), None)
        return (f"{s['title']}: {n} items" if n is not None else f"{s['title']} answered"), json.dumps(j, indent=1, default=str)[:BODY_CHARS]
    verb = f" (POST {', '.join(s['post'])} with \"body\")" if s.get('post') else ''
    run.__doc__ = f'{{"path": "{s["probe"]}", "params": {{}}}} - a read under {s["title"]}\'s API with the card\'s key{verb}. Reads only.'
    return run


def test(store, c) -> str:
    "The card's Test: its cheap read."
    from .reports import _card
    t = c['Type']
    cfg = {**_card(store, t, 'api_key', c['ConnectorId']), 'connector_id': c['ConnectorId']}
    head, _ = runner(t)({**cfg, 'store': store})
    return f'{head} - the key works ({table()[t]["probe"]})'
