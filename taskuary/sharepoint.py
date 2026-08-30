"""SharePoint: lists and document-library files as report sources and agent tools, over Graph.

The connection is one app registration with Sites.Read.All (application permission) - and most
installs already HAVE one: the Outlook card's tenant app. So the SharePoint card's own fields are
optional; blank, it borrows Outlook's app exactly the way the Azure card does (sharepoint_connection
below). The borrow is only offered when Outlook actually runs on a tenant app: a personal
Sign-in-with-Microsoft token carries mail scopes, not Sites, and would fail at the first read.

Two report types: `sharepoint_list` (a list's items, one row each) and `sharepoint_file` (a csv or
xlsx in a library, parsed to rows; a folder path lists what is in it, newest first).
"""
import io, json
import requests
from loguru import logger

GRAPH = 'https://graph.microsoft.com/v1.0'


def sharepoint_connection(store, connector_id=None) -> dict:
    """The card's own app, else the Outlook card's TENANT app. A user sign-in on Outlook is not
    borrowable (its secret is a refresh token for mail scopes), so it is skipped on purpose."""
    from .reports import _card
    cfg = _card(store, 'sharepoint', 'client_secret', connector_id)
    if not (cfg.get('client_id') and cfg.get('client_secret')):
        o = _card(store, 'outlook', 'client_secret')
        if o.get('auth') != 'user' and o.get('client_id') and o.get('client_secret'):
            cfg = {**{k: o[k] for k in ('tenant_id', 'client_id', 'client_secret') if o.get(k)}, **cfg, 'borrowed': 'outlook'}
    return cfg


def can_borrow_outlook(store) -> bool:
    from .reports import _card
    o = _card(store, 'outlook', 'client_secret')
    return bool(o.get('auth') != 'user' and o.get('client_id') and o.get('client_secret'))


def _token(cfg) -> str:
    from .azure import token
    if not (cfg.get('client_id') and cfg.get('client_secret')):
        raise RuntimeError('SharePoint needs an app registration with Sites.Read.All: set tenant_id, client_id and a client secret on the '
                           'SharePoint card - or set up the Outlook card as a tenant app and leave these blank to reuse it')
    return token(cfg, 'https://graph.microsoft.com/.default')


def _get(tok, path, **params):
    r = requests.get(f'{GRAPH}{path}', headers={'Authorization': f'Bearer {tok}'}, params=params or None, timeout=30)
    if r.status_code == 403: raise RuntimeError('Graph refused (403) - grant the app the Sites.Read.All APPLICATION permission and admin-consent it')
    if r.status_code == 404: raise RuntimeError(f'not found on SharePoint: {path}')
    if r.status_code >= 300: raise RuntimeError(f'Graph {r.status_code}: {r.text[:200]}')
    return r.json()


def site_id(tok, site: str) -> str:
    """'contoso.sharepoint.com/sites/Ops' (or the https URL, or 'contoso.sharepoint.com:/sites/Ops') -> the site id."""
    s = (site or '').strip().replace('https://', '').replace('http://', '').rstrip('/')
    if not s: raise RuntimeError('no site given - e.g. contoso.sharepoint.com/sites/Ops')
    if ':' in s: host, path = s.split(':', 1)
    elif '/' in s: host, path = s.split('/', 1); path = '/' + path
    else: host, path = s, ''
    return _get(tok, f'/sites/{host}:{path}' if path else f'/sites/{host}')['id']


def run_sharepoint_list(cfg):
    """{"site": "contoso.sharepoint.com/sites/Ops", "list": "Requests", "top": 200} - the items of one
    SharePoint list, one row per item with its columns; the app comes from the SharePoint card (or
    the Outlook card's tenant app)."""
    from .reports import rows_out, row_limit
    tok, sid = _token(cfg), None
    sid = site_id(tok, cfg.get('site'))
    name = (cfg.get('list') or '').strip()
    if not name: raise RuntimeError('no list named - the list title as shown in SharePoint, e.g. Requests')
    lim, mine = row_limit(cfg)
    top = max(1, min(int(cfg.get('top') or 200), 999))
    j = _get(tok, f'/sites/{sid}/lists/{name}/items', **{'$expand': 'fields', '$top': top})
    rows = [{k: v for k, v in (it.get('fields') or {}).items() if not k.startswith('@odata') and k not in ('id', 'ContentType', 'Edit', 'LinkTitleNoMenu', 'LinkTitle', 'ItemChildCount', 'FolderChildCount', '_UIVersionString', 'Attachments', '_ComplianceFlags', '_ComplianceTag', '_ComplianceTagWrittenTime', '_ComplianceTagUserId', 'AppAuthorLookupId', 'AppEditorLookupId')}
            for it in j.get('value', [])]
    return rows_out(rows, lim, unit=f'items in {name}', mine=mine)


def parse_table(name: str, data: bytes, cfg: dict) -> list:
    """csv / tsv / xlsx bytes -> rows as dicts (first row = headers)."""
    from .reports import _rows_from_text
    low = (name or '').lower()
    if low.endswith('.xlsx'):
        try: from openpyxl import load_workbook
        except ImportError: raise RuntimeError('reading .xlsx needs openpyxl - run: pip install openpyxl')
        wb = load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        ws = wb[cfg['sheet']] if cfg.get('sheet') else wb.active
        it = ws.iter_rows(values_only=True)
        head = [str(h) if h is not None else f'col{i}' for i, h in enumerate(next(it, []) or [])]
        rows = [dict(zip(head, [('' if v is None else v) for v in r])) for r in it]
        wb.close(); return rows
    text = data.decode('utf-8', errors='replace')
    return _rows_from_text(text, '\t' if low.endswith('.tsv') else cfg.get('delimiter'))


def run_sharepoint_file(cfg):
    """{"site": "contoso.sharepoint.com/sites/Ops", "path": "Shared Documents/Reports/latest.xlsx", "sheet": "Data"} -
    a csv/tsv/xlsx in a document library as rows; a path ending in / lists the folder, newest first.
    The app comes from the SharePoint card (or the Outlook card's tenant app)."""
    from .reports import rows_out, row_limit, BODY_CHARS
    tok = _token(cfg)
    sid = site_id(tok, cfg.get('site'))
    path = (cfg.get('path') or '').strip().strip('/')
    if not path: raise RuntimeError('no path given - e.g. Shared Documents/Reports/latest.xlsx')
    lim, mine = row_limit(cfg)
    if str(cfg.get('path') or '').endswith('/'):
        j = _get(tok, f'/sites/{sid}/drive/root:/{path}:/children', **{'$top': 200})
        rows = sorted(({'name': f.get('name'), 'bytes': f.get('size'), 'modified': (f.get('lastModifiedDateTime') or '')[:16].replace('T', ' '),
                        'kind': 'folder' if f.get('folder') else 'file'} for f in j.get('value', [])), key=lambda r: r['modified'], reverse=True)
        return rows_out(rows, lim, unit=f'items in {path.rsplit("/", 1)[-1]}', mine=mine)
    r = requests.get(f'{GRAPH}/sites/{sid}/drive/root:/{path}:/content', headers={'Authorization': f'Bearer {tok}'}, timeout=60, allow_redirects=True)
    if r.status_code == 404: raise RuntimeError(f'no such file on the site: {path}')
    if r.status_code >= 300: raise RuntimeError(f'Graph {r.status_code}: {r.text[:200]}')
    name = path.rsplit('/', 1)[-1]
    low = name.lower()
    if low.endswith(('.csv', '.tsv', '.xlsx')): return rows_out(parse_table(name, r.content, cfg), lim, unit=f'rows from {name}', mine=mine)
    text = r.content.decode('utf-8', errors='replace')
    lines = text.splitlines()
    try: tail = max(1, int(cfg.get('tail') or 50))
    except (TypeError, ValueError): tail = 50
    return f'{name} - last {min(tail, len(lines))} of {len(lines)} lines', '\n'.join(lines[-tail:])[:BODY_CHARS]


def test(store, c) -> str:
    cfg = sharepoint_connection(store)
    tok = _token(cfg)
    root = _get(tok, '/sites/root')
    who = f" (using the Outlook card's app)" if cfg.get('borrowed') else ''
    out = f"reaches SharePoint{who} - root site: {root.get('displayName') or root.get('webUrl')}"
    site = (json.loads(c.get('ConfigJson') or '{}')).get('site')
    if site:
        sid = site_id(tok, site)
        lists = _get(tok, f'/sites/{sid}/lists', **{'$select': 'displayName', '$top': 50}).get('value', [])
        out += f"; {site}: {len(lists)} lists" + (f" ({', '.join(l.get('displayName') for l in lists[:6])}{'…' if len(lists) > 6 else ''})" if lists else '')
    return out
