"""Azure connector - client-credentials tokens over plain requests, the same app-registration
road Outlook/Teams already ride (leave the card blank and it borrows the Outlook app; one
registration can hold Graph permissions AND Azure RBAC roles). Three report/tool types:
'azure' GETs ANY Azure Resource Manager path, 'azure_blob' reads or lists a storage
container, 'azure_logs' runs KQL against a Log Analytics workspace. The app needs a role
on the target: Reader for ARM, Storage Blob Data Reader, Log Analytics Reader.
"""
import json, os, re, requests
from datetime import datetime
from loguru import logger

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


def discover(store, cfg: dict, connector_id: int, actor: str = 'owner') -> dict:
    """What can this app SEE? ARM enumerates the storage accounts (then their containers,
    with the storage token) and Log Analytics workspaces across every visible subscription;
    each is registered as a source with the same mode picker as AWS - report (default,
    nothing polled), feed, tasks, or off. RBAC decides what enumerates; partial failures
    register what did."""
    known = {s['Address'] for s in store.list_sources(active_only=False) if s['Channel'] == 'azure'}
    found, cfgs = [], {}
    tok = token(cfg, f'{ARM}/.default')
    subs = _get(f'{ARM}/subscriptions', tok, params={'api-version': '2022-12-01'}).json().get('value') or []
    stok = None
    for sub in subs[:5]:
        sid = sub['subscriptionId']
        try:
            for sa in _get(f'{ARM}/subscriptions/{sid}/providers/Microsoft.Storage/storageAccounts',
                           tok, params={'api-version': '2023-01-01'}).json().get('value') or []:
                acct = sa['name']
                try:
                    stok = stok or token(cfg, 'https://storage.azure.com/.default')
                    xml = _get(f'https://{acct}.blob.core.windows.net/', stok, params={'comp': 'list'}).text
                    for cont in re.findall(r'<Name>(.*?)</Name>', xml)[:20]:
                        found.append(f'blob://{acct}/{cont}')
                except Exception as e:
                    logger.warning(f'azure discovery: containers of {acct} failed: {e}')
                    found.append(f'blob://{acct}')          # the account still shows; add /container by hand
        except Exception as e:
            logger.warning(f'azure discovery: storage accounts in {sid} failed: {e}')
        try:
            for ws in _get(f'{ARM}/subscriptions/{sid}/providers/Microsoft.OperationalInsights/workspaces',
                           tok, params={'api-version': '2022-10-01'}).json().get('value') or []:
                wid = (ws.get('properties') or {}).get('customerId')
                if not wid: continue
                addr = f"law://{ws['name']}"
                found.append(addr)
                cfgs[addr] = {'workspace_id': wid}
        except Exception as e:
            logger.warning(f'azure discovery: workspaces in {sid} failed: {e}')
    added = 0
    for addr in found:
        if addr in known: continue
        store.save_source({'Channel': 'azure', 'Address': addr, 'ConnectorId': connector_id, 'Active': 1,
                           'Owner': 'discovered',
                           'ConfigJson': json.dumps({'mode': 'report', **cfgs.get(addr, {})})}, actor)
        added += 1
    out = {'found': len(found), 'added': added}
    if not found: out['hint'] = _why_empty(cfg, tok, subs)
    return out


def _why_empty(cfg, tok, subs) -> str:
    """Nothing found is almost never 'nothing exists' - it is RBAC, and the shape of the
    emptiness says WHICH gap. Azure hands out container reads and resource reads
    separately, so an app can list 86 resource groups and still read nothing inside them."""
    if not subs:
        return ('the app has no role on any subscription - assign it Reader: Azure Portal → '
                'Subscriptions → your subscription → Access control (IAM) → Add role assignment')
    sid = subs[0]['subscriptionId']
    try:
        rgs = len(_get(f'{ARM}/subscriptions/{sid}/resourcegroups', tok,
                       params={'api-version': '2021-04-01'}).json().get('value') or [])
        res = len(_get(f'{ARM}/subscriptions/{sid}/resources', tok,
                       params={'api-version': '2021-04-01', '$top': 1}).json().get('value') or [])
    except Exception as e:
        return f'could not tell why: {str(e)[:120]}'
    if rgs and not res:
        return (f'the app sees the subscription and its {rgs} resource groups but CANNOT READ THE '
                'RESOURCES inside them - those are separate rights in Azure. Assign it Reader on '
                'the subscription (or on the resource groups holding your storage accounts and '
                'Log Analytics workspaces): Access control (IAM) → Add role assignment → Reader')
    if not rgs:
        return 'the app can see the subscription but none of its resource groups - it needs Reader on the subscription'
    return ('the app can read resources, but this subscription holds no storage accounts and no Log '
            'Analytics workspaces (a VM estate with no diagnostics storage looks exactly like this)')


def poll_source(store, cfg: dict, src: dict, since, llm=None, file_only=False) -> int:
    """One discovered object in tasks/feed mode. blob://account/container -> a Timeline
    item per NEW blob; law://workspace -> ONE batched item of new exception rows (the
    source's own 'query' overrides the default KQL)."""
    from .ingest import ingest_message
    scfg = json.loads(src.get('ConfigJson') or '{}')
    addr, floor, n = src['Address'], since.strftime('%Y-%m-%d %H:%M:%S'), 0
    if addr.startswith('blob://') and '/' in addr[7:]:
        acct, cont = addr[7:].split('/', 1)
        tok = token(cfg, 'https://storage.azure.com/.default')
        xml = _get(f'https://{acct}.blob.core.windows.net/{cont}', tok,
                   params={'restype': 'container', 'comp': 'list'}).text
        for name, mod in re.findall(r'<Name>(.*?)</Name>.*?<Last-Modified>(.*?)</Last-Modified>', xml, re.S)[:200]:
            try: stamp = datetime.strptime(mod, '%a, %d %b %Y %H:%M:%S GMT').astimezone().strftime('%Y-%m-%d %H:%M:%S')
            except ValueError: continue
            if stamp < floor: continue
            out = ingest_message(store, file_only=file_only, msg={
                'external_id': f'azblob:{acct}/{cont}/{name}:{stamp[:16]}', 'channel': 'azure',
                'subject': f'New in {addr}: {name}',
                'body': f'[blob landed]\nhttps://{acct}.blob.core.windows.net/{cont}/{name}',
                'from_name': addr, 'conversation_id': f'azure:{addr}', 'sent_at': stamp,
                'source_name': addr}, llm=llm)
            n += out['status'] != 'duplicate'
    elif addr.startswith('law://') and scfg.get('workspace_id'):
        hours = max(0.2, (datetime.now() - since.replace(tzinfo=None)).total_seconds() / 3600)
        q = scfg.get('query') or 'AppExceptions | project TimeGenerated, ProblemId, OuterMessage | take 50'
        try:
            head, body = run_azure_logs({**cfg, 'workspace_id': scfg['workspace_id'], 'query': q,
                                         'hours': hours, 'max_rows': 50})
        except Exception as e:
            raise RuntimeError(f'{addr}: {e}') from e
        if body.strip() and not head.startswith('0 '):
            stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            out = ingest_message(store, file_only=file_only, msg={
                'external_id': f'azlaw:{addr}:{stamp[:16]}', 'channel': 'azure',
                'subject': f'{head} from {addr}',
                'body': f'[Log Analytics - {q[:100]}]\n{body[:8000]}',
                'from_name': addr, 'conversation_id': f'azure:{addr}', 'sent_at': stamp,
                'source_name': addr}, llm=llm)
            n += out['status'] != 'duplicate'
    return n


# ── Entra ID (the directory, over Graph) ────────────────────────────────────────────────
# The SAME app registration - one client-credentials token, a different scope. An app that
# reads mail for the Outlook card can read the directory too once it has the Graph
# APPLICATION permissions (User.Read.All, Group.Read.All, AuditLog.Read.All,
# Organization.Read.All); admin consent is what turns each one on.
GRAPH = 'https://graph.microsoft.com/v1.0'
GRAPH_PAGES = 12                      # $top=999 a page; a 10k-user tenant stops being a report

def graph_get(cfg: dict, path: str, **params) -> list:
    """Every page of a Graph collection, following @odata.nextLink. Advanced queries
    ($filter on any(), $count) need the eventual-consistency header, so it always rides."""
    tok = token(cfg, 'https://graph.microsoft.com/.default')
    url, out, pages = f'{GRAPH}{path}', [], 0
    while url and pages < GRAPH_PAGES:
        r = requests.get(url, headers={'Authorization': f'Bearer {tok}', 'ConsistencyLevel': 'eventual'},
                         params=params or None, timeout=45)
        if r.status_code >= 400: raise RuntimeError(f'graph {path} said {r.status_code}: {r.text[:300]}')
        j = r.json()
        out += j.get('value') or []
        url, params, pages = j.get('@odata.nextLink'), None, pages + 1
    return out


def run_entra_users(cfg: dict):
    """{"filter": "...", "select": "..."} - the directory's people. accountEnabled is NOT in
    Graph's default user payload, so it is selected explicitly: without it every disabled
    account reads as active, which is the one thing an access review must not get wrong."""
    from .reports import row_limit, rows_out
    sel = cfg.get('select') or 'displayName,userPrincipalName,accountEnabled,jobTitle,department,createdDateTime'
    rows = graph_get(cfg, '/users', **{'$select': sel, '$top': 999,
                                       **({'$filter': cfg['filter']} if cfg.get('filter') else {})})
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit='users', mine=mine)


def run_entra_groups(cfg: dict):
    """{"group": "<name or id>"} lists that group's TRANSITIVE members (nested groups
    included - what a login actually inherits); blank lists the groups themselves."""
    from .reports import row_limit, rows_out
    lim, mine = row_limit(cfg)
    g = (cfg.get('group') or '').strip()
    if not g:
        rows = graph_get(cfg, '/groups', **{'$select': 'displayName,id,mail,description', '$top': 999})
        return rows_out(rows, lim, unit='groups', mine=mine)
    gid = g
    if not re.fullmatch(r'[0-9a-fA-F-]{36}', g):
        hit = graph_get(cfg, '/groups', **{'$filter': f"displayName eq '{g}'", '$select': 'id,displayName'})
        if not hit: raise RuntimeError(f'no group named {g!r}')
        gid = hit[0]['id']
    rows = graph_get(cfg, f'/groups/{gid}/transitiveMembers',
                     **{'$select': 'displayName,userPrincipalName,accountEnabled', '$top': 999})
    # $select drops @odata.type, so a user is 'the thing with a UPN' - nested groups and
    # devices come back through the same collection
    rows = [r for r in rows if r.get('userPrincipalName')]
    return rows_out(rows, lim, unit='members', mine=mine)


def run_entra_signins(cfg: dict):
    """{"hours": 24, "failed_only": true} - sign-in activity. Needs AuditLog.Read.All AND
    an Entra ID P1/P2 tenant; without the licence Graph answers 403 and says so."""
    from .reports import row_limit, rows_out
    from datetime import timedelta
    since = (datetime.utcnow() - timedelta(hours=float(cfg.get('hours') or 24))).strftime('%Y-%m-%dT%H:%M:%SZ')
    flt = f'createdDateTime ge {since}'
    if cfg.get('failed_only'): flt += ' and status/errorCode ne 0'
    rows = graph_get(cfg, '/auditLogs/signIns', **{'$filter': flt, '$top': 999})
    out = [{'at': r.get('createdDateTime'), 'user': r.get('userPrincipalName'), 'app': r.get('appDisplayName'),
            'ip': r.get('ipAddress'), 'city': ((r.get('location') or {}).get('city')),
            'error': ((r.get('status') or {}).get('errorCode')),
            'reason': ((r.get('status') or {}).get('failureReason') or '')[:120]} for r in rows]
    lim, mine = row_limit(cfg)
    return rows_out(out, lim, unit='sign-ins', mine=mine)


def run_entra_licenses(cfg: dict):
    """The tenant's licence SKUs and how many seats are actually consumed - the report that
    finds the seats nobody is using. Needs Organization.Read.All."""
    from .reports import row_limit, rows_out
    rows = graph_get(cfg, '/subscribedSkus')
    out = []
    for s in rows:
        p = s.get('prepaidUnits') or {}
        enabled, used = int(p.get('enabled') or 0), int(s.get('consumedUnits') or 0)
        out.append({'sku': s.get('skuPartNumber'), 'enabled': enabled, 'consumed': used,
                    'spare': enabled - used, 'warning': int(p.get('warning') or 0),
                    'suspended': int(p.get('suspended') or 0)})
    out.sort(key=lambda x: -x['spare'])
    lim, mine = row_limit(cfg)
    return rows_out(out, lim, unit='SKUs', mine=mine)


def test_entra(cfg: dict) -> dict:
    """Which directory reads this app actually has - each permission probed separately, so
    the answer names the ones missing instead of failing on the first."""
    out, ok = {}, []
    for label, path, params in (('users', '/users', {'$top': 1, '$select': 'displayName'}),
                                ('groups', '/groups', {'$top': 1, '$select': 'displayName'}),
                                ('licences', '/subscribedSkus', {}),
                                ('sign-in logs', '/auditLogs/signIns', {'$top': 1})):
        try:
            graph_get(cfg, path, **params)
            out[label] = 'ok'; ok.append(label)
        except Exception as e:
            out[label] = 'no' if '403' in str(e) or '401' in str(e) else str(e)[:80]
    if not ok:
        return {'ok': False, 'error': 'the app has no directory permissions - grant Graph APPLICATION '
                                      'permissions (User.Read.All, Group.Read.All, Organization.Read.All, '
                                      'AuditLog.Read.All) and click Grant admin consent'}
    missing = [k for k, v in out.items() if v != 'ok']
    return {'ok': True, 'detail': 'Entra reads available: ' + ', '.join(ok)
                                  + (f" · not permitted: {', '.join(missing)}" if missing else '')}


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
