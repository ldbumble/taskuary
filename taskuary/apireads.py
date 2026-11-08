"""A VENDOR'S REST API, READ WITH A KEY (the owner, 2026-11-08: "all the ones that say coming soon just add them now").

One road for every card whose whole integration is "GET this vendor's API with the owner's key": DigitalOcean, Terraform Cloud, Better
Stack, CircleCI, Buildkite, Coda, Intrinio, Benzinga, Tradier, Diffbot, and the self-hosted ones whose address is on the card (Jenkins,
SonarQube, Elasticsearch, Splunk, Dynatrace, Kubernetes) - plus Google Drive and OneDrive, read with the sign-ins the app already has.

THE TABLE IS apireads.json, read by this module and by the Connections page (one row: the base or the card's address, how the key rides,
the cheap GET its Test makes, the vendor's page it was read off). A new vendor is a row. Each card's report / agent type is `<type>_read`:
{"path": "/v2/droplets", "params": {...}} - a GET under that base and nothing else. THEY ARE ALL READS: no verb but GET is ever sent (a
Tradier key that could trade places no order here), the path cannot leave the base, and a redirect is not followed.
"""
import base64, json
from functools import lru_cache
from pathlib import Path
import requests

TIMEOUT, BODY_CHARS = 30, 20000
BORROWED = ('google_drive', 'onedrive', 'office365_files')     # no key of their own: the app's Google and Microsoft sign-ins


@lru_cache(maxsize=1)
def table() -> dict: return json.loads(Path(__file__).with_name('apireads.json').read_text(encoding='utf-8'))['services']
def types() -> tuple: return tuple(table())
def rtype(t: str) -> str: return f'{t}_read'
def card_of(rt: str) -> str | None: return rt[:-5] if rt.endswith('_read') and rt[:-5] in table() else None


def base_of(t: str, cfg: dict) -> str:
    s = table()[t]
    if s.get('base'): return s['base'].rstrip('/')
    host = str(cfg.get('host') or s.get('default_host') or '').strip().rstrip('/')
    if not host: raise RuntimeError(f"{s['title']} needs its address on the card ({s.get('host_hint') or 'https://...'})")
    if not host.startswith(('https://', 'http://')): host = f'https://{host}'
    return host


def _path(p) -> str:
    p = str(p or '').strip()
    if not p.startswith('/') or p.startswith('//') or '://' in p or '\\' in p or '@' in p or '..' in p: raise ValueError(f'a path under the API, starting with / - not {p[:80]!r}')
    return p


def _token(store, t: str, cfg: dict, key: str) -> str:
    "Google Drive and OneDrive borrow the app's own sign-ins: the Google Sheets card's token, the Outlook card's Microsoft one."
    s = table()[t]
    if s['auth'] == 'google':
        from . import sheets
        return sheets._token(sheets.google_sheets_connection(store))
    if s['auth'] == 'graph':
        from .outbound import _graph_token
        return _graph_token(store, 'outlook')
    return key


def request_parts(t: str, cfg: dict, key: str, store=None) -> tuple:
    "(url base, headers, params) for one card - how its key rides, read off the table."
    s, a = table()[t], table()[t]['auth']
    h, q = dict(s.get('headers') or {}), {}
    if a in ('google', 'graph'): h['Authorization'] = f'Bearer {_token(store, t, cfg, key)}'
    elif not key and not s.get('keyless'): raise RuntimeError(f"no {s['title']} key saved - paste it on the {s['title']} card")
    elif a == 'query': q[s['param']] = key
    elif a == 'basic': h['Authorization'] = 'Basic ' + base64.b64encode(f"{cfg.get('user') or ''}:{key}".encode()).decode()
    elif key: h[s.get('header') or 'Authorization'] = (s.get('format') or 'Bearer {key}').format(key=key)
    return base_of(t, cfg), h, q


def get(t: str, cfg: dict, key: str, path: str, params: dict | None = None, store=None):
    base, h, q = request_parts(t, cfg, key, store)
    r = requests.get(base + _path(path), headers={'Accept': 'application/json', **h}, params={**(params or {}), **q},
                     timeout=TIMEOUT, allow_redirects=False)
    if r.status_code >= 300:
        why = ' - the key was refused' if r.status_code in (401, 403) else ''
        raise RuntimeError(f"{table()[t]['title']} answered {r.status_code}{why}: {r.text[:200]}")
    try: return r.json()
    except ValueError: return r.text


def runner(t: str):
    "The `<type>_read` executor for one card: {path, params} -> (headline, the JSON it answered)."
    def run(cfg):
        j = get(t, cfg, cfg.get('api_key') or '', cfg.get('path') or table()[t]['probe'], cfg.get('params') if isinstance(cfg.get('params'), dict) else None,
                cfg.get('store'))
        n = len(j) if isinstance(j, list) else next((len(v) for v in (j.values() if isinstance(j, dict) else ()) if isinstance(v, list)), None)
        return (f"{table()[t]['title']}: {n} items" if n is not None else f"{table()[t]['title']} answered"), json.dumps(j, indent=1, default=str)[:BODY_CHARS]
    run.__doc__ = f'{{"path": "{table()[t]["probe"]}", "params": {{}}}} - a GET under {table()[t]["title"]}\'s API with the card\'s key. Reads only.'
    return run


def test(store, c) -> str:
    "The card's Test: its cheap GET."
    from .reports import _card
    t = c['Type']
    cfg = _card(store, t, 'api_key', c['ConnectorId'])
    head, _ = runner(t)({**cfg, 'store': store})
    return f'{head} - the key works ({table()[t]["probe"]})'
