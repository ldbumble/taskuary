"""Google Sheets as a report source and an agent tool.

One OAuth client (id + secret) and a refresh token minted with the Sheets scope. The client can be
the one already on the Gmail card (its optional calendar fields), so the Sheets card's id/secret
are blank-to-reuse; the refresh token cannot be shared - a token carries the scopes it was consented
with, and the calendar one does not cover spreadsheets - so each card holds its own. The borrow is
only offered when the Gmail card actually carries a Google OAuth client.

Report type `google_sheets`: {"spreadsheet": id or URL, "range": "Sheet1!A:Z"} -> rows, first row
as headers.
"""
import json, re, time
import requests

SHEETS = 'https://sheets.googleapis.com/v4/spreadsheets'
_TOK = {}   # refresh token -> (access token, expiry)


def google_sheets_connection(store, connector_id=None) -> dict:
    from .reports import _card
    cfg = _card(store, 'google_sheets', 'google_refresh_token', connector_id)
    if not (cfg.get('google_client_id') and cfg.get('google_client_secret')):
        g = _card(store, 'gmail', 'password')
        if g.get('google_client_id') and g.get('google_client_secret'):
            cfg = {'google_client_id': g['google_client_id'], 'google_client_secret': g['google_client_secret'], **cfg, 'borrowed': 'gmail'}
    return cfg


def can_borrow_gmail(store) -> bool:
    from .reports import _card
    g = _card(store, 'gmail', 'password')
    return bool(g.get('google_client_id') and g.get('google_client_secret'))


def _token(cfg) -> str:
    cid, sec, rt = cfg.get('google_client_id'), cfg.get('google_client_secret'), cfg.get('google_refresh_token')
    if not (cid and sec): raise RuntimeError('Google Sheets needs an OAuth client id + secret - on the Sheets card, or on the Gmail card to reuse')
    if not rt: raise RuntimeError('no refresh token saved on the Sheets card - mint one with the spreadsheets.readonly scope (see the Guide)')
    hit = _TOK.get(rt)
    if hit and hit[1] > time.time() + 60: return hit[0]
    r = requests.post('https://oauth2.googleapis.com/token', timeout=20,
                      data={'client_id': cid, 'client_secret': sec, 'refresh_token': rt, 'grant_type': 'refresh_token'})
    if r.status_code != 200: raise RuntimeError(f'Google refused the refresh token ({r.status_code}): {r.text[:200]}')
    j = r.json(); _TOK[rt] = (j['access_token'], time.time() + int(j.get('expires_in') or 3600))
    return j['access_token']


def spreadsheet_id(s: str) -> str:
    """An id, or the sheet's URL - people paste the URL."""
    s = (s or '').strip()
    m = re.search(r'/spreadsheets/d/([A-Za-z0-9_-]+)', s)
    return m.group(1) if m else s


def _get(tok, url, **params):
    r = requests.get(url, headers={'Authorization': f'Bearer {tok}'}, params=params or None, timeout=30)
    if r.status_code == 403: raise RuntimeError('Google refused (403): the refresh token lacks the spreadsheets.readonly scope, or the sheet is not shared with that account')
    if r.status_code == 404: raise RuntimeError('spreadsheet not found - check the id/URL and that the account can open it')
    if r.status_code >= 300: raise RuntimeError(f'Google {r.status_code}: {r.text[:200]}')
    return r.json()


def run_google_sheets(cfg):
    """{"spreadsheet": "<id or URL>", "range": "Sheet1!A:Z"} - a Google Sheet's cells as rows, the
    first row as the column names. Blank range = the first sheet. The OAuth client comes from the
    Sheets card (or the Gmail card's Google fields)."""
    from .reports import rows_out, row_limit
    tok = _token(cfg)
    sid = spreadsheet_id(cfg.get('spreadsheet'))
    if not sid: raise RuntimeError('no spreadsheet given - paste its URL or id')
    rng = (cfg.get('range') or '').strip()
    if not rng:
        meta = _get(tok, f'{SHEETS}/{sid}', fields='sheets.properties.title')
        rng = (meta.get('sheets') or [{}])[0].get('properties', {}).get('title') or 'Sheet1'
    j = _get(tok, f'{SHEETS}/{sid}/values/{requests.utils.quote(rng, safe="!:")}', valueRenderOption='UNFORMATTED_VALUE', dateTimeRenderOption='FORMATTED_STRING')
    vals = j.get('values') or []
    if not vals: return f'{rng}: empty', ''
    head = [str(h) if str(h).strip() else f'col{i}' for i, h in enumerate(vals[0])]
    rows = [dict(zip(head, r + [''] * (len(head) - len(r)))) for r in vals[1:]]
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit=f'rows from {rng}', mine=mine)


def test(store, c) -> str:
    cfg = google_sheets_connection(store)
    tok = _token(cfg)
    who = " (using the Gmail card's client)" if cfg.get('borrowed') else ''
    info = requests.get('https://www.googleapis.com/oauth2/v3/tokeninfo', params={'access_token': tok}, timeout=20).json()
    scopes = info.get('scope', '')
    if 'spreadsheets' not in scopes and 'drive' not in scopes:
        raise RuntimeError(f'the token works but has no Sheets scope ({scopes[:120]}) - mint the refresh token with spreadsheets.readonly')
    out = f'Google accepted the token{who}; scopes: ' + ', '.join(s.rsplit('/', 1)[-1] for s in scopes.split())
    if 'drive' in scopes:
        j = _get(tok, 'https://www.googleapis.com/drive/v3/files', q="mimeType='application/vnd.google-apps.spreadsheet' and trashed=false", pageSize=10, fields='files(name)')
        names = [f['name'] for f in j.get('files', [])]
        out += f"; {len(names)} spreadsheet{'s' if len(names) != 1 else ''} visible" + (f" ({', '.join(names[:5])}{'…' if len(names) > 5 else ''})" if names else '')
    sheet = json.loads(c.get('ConfigJson') or '{}').get('spreadsheet')
    if sheet:
        meta = _get(tok, f'{SHEETS}/{spreadsheet_id(sheet)}', fields='properties.title,sheets.properties.title')
        out += f"; opened {meta.get('properties', {}).get('title')} ({len(meta.get('sheets') or [])} tabs)"
    return out
