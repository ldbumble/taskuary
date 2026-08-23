"""Azure connector - client-credentials tokens over plain requests, the same app-registration
road Outlook/Teams already ride (leave the card blank and it borrows the Outlook app; one
registration can hold Graph permissions AND Azure RBAC roles). Three report/tool types:
'azure' GETs ANY Azure Resource Manager path, 'azure_blob' reads or lists a storage
container, 'azure_logs' runs KQL against a Log Analytics workspace. The app needs a role
on the target: Reader for ARM, Storage Blob Data Reader, Log Analytics Reader.
"""
import json, os, re, requests

ARM = 'https://management.azure.com'
STORAGE_VER = '2021-08-06'


def token(cfg: dict, scope: str) -> str:
    tid = cfg.get('tenant_id') or os.getenv('AZURE_TENANT_ID')
    cid = cfg.get('client_id') or os.getenv('AZURE_CLIENT_ID')
    sec = cfg.get('client_secret') or os.getenv('AZURE_CLIENT_SECRET')
    if not (tid and cid and sec):
        raise RuntimeError('need tenant_id + client_id + a client secret - set them on the Azure card, '
                           'or set up the Outlook connector (its app is borrowed automatically)')
    r = requests.post(f'https://login.microsoftonline.com/{tid}/oauth2/v2.0/token', timeout=20,
                      data={'client_id': cid, 'client_secret': sec,
                            'grant_type': 'client_credentials', 'scope': scope})
    if r.status_code != 200: raise RuntimeError(f'token failed ({r.status_code}): {r.text[:300]}')
    return r.json()['access_token']


def _get(url, tok, **kw):
    r = requests.get(url, headers={'Authorization': f'Bearer {tok}', 'x-ms-version': STORAGE_VER},
                     timeout=60, **kw)
    if r.status_code >= 400: raise RuntimeError(f'{r.status_code}: {r.text[:300]}')
    return r


def test(cfg: dict) -> dict:
    """Mint a management token, then list what the app can actually SEE - a token with no
    role assignments is a setup half-done, and a bare green would hide that."""
    try:
        tok = token(cfg, f'{ARM}/.default')
        subs = _get(f'{ARM}/subscriptions', tok, params={'api-version': '2022-12-01'}).json().get('value') or []
        if not subs:
            return {'ok': True, 'detail': 'token OK, but the app sees no subscriptions - grant it a role '
                                          '(e.g. Reader) on a subscription or resource group for ARM reads. '
                                          'Blob and Log Analytics reads use their own roles and may work already.'}
        names = ', '.join(s.get('displayName') or s['subscriptionId'] for s in subs[:5])
        return {'ok': True, 'detail': f'authenticated · {len(subs)} subscription(s): {names}'}
    except Exception as e:
        return {'ok': False, 'error': str(e)[:500]}


def run_azure(cfg: dict):
    """{"path": "/subscriptions/<id>/..." (or a full https URL), "api_version",
    "path_expr": "a.b"} - GET any ARM object with the app's token. An ARM list (a 'value'
    array) comes back row-capped and honest; a single object comes back as JSON."""
    from .reports import row_limit, rows_out, BODY_CHARS
    from .aws import dot_path
    url = cfg['path'] if str(cfg.get('path') or '').startswith('http') else ARM + cfg['path']
    params = dict(cfg.get('params') or {})
    params.setdefault('api-version', cfg.get('api_version') or '2022-12-01')
    data = _get(url, token(cfg, f'{ARM}/.default'), params=params).json()
    if cfg.get('path_expr'): data = dot_path(data, cfg['path_expr'])
    if isinstance(data, dict) and isinstance(data.get('value'), list): data = data['value']
    if isinstance(data, list):
        lim, mine = row_limit(cfg)
        return rows_out(data, lim, unit='items', mine=mine)
    return 'ok', json.dumps(data, indent=1, default=str)[:BODY_CHARS]


def run_azure_blob(cfg: dict):
    """{"account", "container", "blob"} reads the blob (text head); {"account", "container",
    "prefix"} lists. Role: 'Storage Blob Data Reader' on the account (or container)."""
    from .reports import row_limit, rows_out, BODY_CHARS
    tok = token(cfg, 'https://storage.azure.com/.default')
    base = f"https://{cfg['account']}.blob.core.windows.net/{cfg['container']}"
    if cfg.get('blob'):
        r = _get(f"{base}/{cfg['blob']}", tok)
        head = (f"{cfg['container']}/{cfg['blob']} · {len(r.content)} bytes"
                + (' (shown truncated)' if len(r.content) > BODY_CHARS else ''))
        return head, r.content[:BODY_CHARS].decode('utf-8', errors='replace')
    xml = _get(base, tok, params={'restype': 'container', 'comp': 'list', 'prefix': cfg.get('prefix') or ''}).text
    rows = [{'name': n, 'modified': m, 'size': int(s)} for n, m, s in
            re.findall(r'<Name>(.*?)</Name>.*?<Last-Modified>(.*?)</Last-Modified>.*?<Content-Length>(\d+)</Content-Length>',
                       xml, re.S)]
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit='blobs', mine=mine)


def run_azure_logs(cfg: dict):
    """{"workspace_id", "query" (KQL), "hours": 24} - Log Analytics: app exceptions,
    sign-ins, anything the workspace collects. Role: 'Log Analytics Reader'."""
    from .reports import row_limit, rows_out
    tok = token(cfg, 'https://api.loganalytics.io/.default')
    r = requests.post(f"https://api.loganalytics.io/v1/workspaces/{cfg['workspace_id']}/query",
                      headers={'Authorization': f'Bearer {tok}'}, timeout=60,
                      json={'query': cfg['query'], 'timespan': f"PT{float(cfg.get('hours') or 24):g}H"})
    if r.status_code >= 400: raise RuntimeError(f'{r.status_code}: {r.text[:300]}')
    t = (r.json().get('tables') or [{}])[0]
    cols = [c['name'] for c in t.get('columns') or []]
    rows = [dict(zip(cols, row)) for row in t.get('rows') or []]
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, mine=mine)
