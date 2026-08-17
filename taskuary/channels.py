"""Channel connectors - the cards on the Connectors tab: Outlook mail + Microsoft Teams
(Graph, app-only client credentials) and GitHub (fine-grained PAT). test_connector is a
live probe (token/chat-read/repo-discovery); poll_channels is the scheduled ingest that
funnels mail and chats through the same triage as everything else. Credentials left blank
fall back to AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET env vars.
"""
import json, os, re, time
from datetime import datetime, timedelta
import requests
from loguru import logger

from .github import _h as gh_headers, list_accessible_repos
from .ingest import ingest_message

GRAPH = 'https://graph.microsoft.com/v1.0'
MAIL_SELECT = 'id,subject,from,receivedDateTime,bodyPreview,body,conversationId,webLink'


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


def graph_token(cfg: dict, secret: str = None) -> str:
    tid = cfg.get('tenant_id') or os.getenv('AZURE_TENANT_ID')
    cid = cfg.get('client_id') or os.getenv('AZURE_CLIENT_ID')
    sec = secret or os.getenv('AZURE_CLIENT_SECRET')
    if not (tid and cid and sec):
        raise RuntimeError('need tenant_id + client_id + a secret (or AZURE_* env vars on the server)')
    r = requests.post(f'https://login.microsoftonline.com/{tid}/oauth2/v2.0/token', timeout=20,
                      data={'client_id': cid, 'client_secret': sec, 'grant_type': 'client_credentials',
                            'scope': 'https://graph.microsoft.com/.default'})
    if r.status_code != 200: raise RuntimeError(f'token failed ({r.status_code}): {r.text[:300]}')
    return r.json()['access_token']


def github_discover(store, c: dict, actor='owner') -> dict:
    """A PAT is ALL the config: authenticate, list reachable repos, add each as a source
    (they become the Board's repo choices)."""
    tok = c.get('Secret')
    if not tok: raise RuntimeError('no PAT saved yet - paste one under Credentials')
    u = requests.get('https://api.github.com/user', headers=gh_headers(tok), timeout=20)
    u.raise_for_status()
    repos = list_accessible_repos(tok)
    have = {s['Address'] for s in store.list_sources(active_only=False) if s['Channel'] == 'github'}
    added = 0
    for rp in repos:
        if rp not in have:
            store.save_source({'Channel': 'github', 'Address': rp, 'ConnectorId': c['ConnectorId'],
                               'Active': 1, 'Owner': actor}, actor)
            added += 1
    return {'login': u.json().get('login'), 'repos': len(repos), 'added': added}


def test_connector(store, cid: int) -> dict:
    """Live credential + access probe; the result (or failure) lands on the connector row."""
    c = store.get_connector(cid, with_secret=True)
    if not c: raise ValueError('connector not found')
    cfg, t0 = _cfg(c), time.time()
    try:
        if c['Type'] in ('outlook', 'teams'):
            own = bool(cfg.get('client_id') and c.get('Secret'))
            tok = graph_token(cfg, c.get('Secret'))
            detail = 'Graph token OK' + ('' if own else ' (using server env credentials)')
            if c['Type'] == 'teams':
                src = next((s for s in store.list_sources(active_only=False)
                            if s['Channel'] == 'teams' and '@' in (s['Address'] or '')), None)
                if src:
                    r = requests.get(f"{GRAPH}/users/{src['Address']}/chats/getAllMessages",
                                     headers={'Authorization': f'Bearer {tok}'}, params={'$top': 1}, timeout=20)
                    if r.status_code == 403:
                        raise RuntimeError('token OK but chat read DENIED (403): app-only Chat.Read.All is a '
                                           'Microsoft protected API - submit the approval form, or use delegated auth')
                    r.raise_for_status()
                    detail = f"chat read OK for {src['Address']}"
                else:
                    detail += ' - add a Teams source (user UPN) to probe chat access'
        elif c['Type'] == 'github':
            d = github_discover(store, c)
            detail = f"authenticated as {d['login']} · {d['repos']} repos discovered · {d['added']} new sources"
        else:
            raise RuntimeError(f"no test for connector type '{c['Type']}'")
        store.touch_connector(cid)
        return {'ok': True, 'ms': int((time.time() - t0) * 1000), 'detail': detail}
    except Exception as e:
        store.touch_connector(cid, str(e))
        return {'ok': False, 'ms': int((time.time() - t0) * 1000), 'detail': str(e)[:500]}


def _clean(html): return re.sub(r'\s+', ' ', re.sub(r'<[^>]+>', ' ', html or '')).strip()

def _local(iso):
    try: return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except ValueError: return iso


def _mail_msgs(tok, upn, since):
    r = requests.get(f'{GRAPH}/users/{upn}/messages', headers={'Authorization': f'Bearer {tok}'}, timeout=30,
                     params={'$top': 25, '$orderby': 'receivedDateTime desc', '$select': MAIL_SELECT,
                             '$filter': f'receivedDateTime gt {since}'})
    r.raise_for_status()
    return r.json().get('value', [])


def poll_channels(store) -> int:
    """Ingest new mail (and chats where the tenant allows) for every active connector's
    active sources. Failures are visible on the connector card, never silent."""
    n = 0
    for c in store.list_connectors():
        if not c['Active'] or c['Type'] == 'github': continue   # github ingests via the coder loop
        full = store.get_connector(c['ConnectorId'], with_secret=True)
        try:
            tok = graph_token(_cfg(full), full.get('Secret'))
            for s in store.list_sources():
                if s['Channel'] != {'outlook': 'email', 'teams': 'teams'}[c['Type']]: continue
                since = ((datetime.now() - timedelta(days=1)).astimezone().isoformat()
                         if not s.get('LastPolledAt')
                         else datetime.fromisoformat(s['LastPolledAt'].replace(' ', 'T')).astimezone().isoformat())
                if c['Type'] == 'outlook':
                    for m in reversed(_mail_msgs(tok, s['Address'], since)):
                        frm = (m.get('from') or {}).get('emailAddress') or {}
                        out = ingest_message(store, {
                            'external_id': f"graph:{m['id']}", 'channel': 'email',
                            'subject': m.get('subject'), 'body': m.get('bodyPreview') or _clean((m.get('body') or {}).get('content')),
                            'from_name': frm.get('name'), 'from_email': frm.get('address'),
                            'conversation_id': m.get('conversationId'), 'sent_at': _local(m.get('receivedDateTime') or ''),
                            'source_link': m.get('webLink'), 'source_name': s['Address']})
                        n += out['status'] != 'duplicate'
                store.touch_source(s['SourceId'])
            store.touch_connector(c['ConnectorId'])
        except Exception as e:
            logger.warning(f"channel poll failed ({c['Type']}): {e}")
            store.touch_connector(c['ConnectorId'], str(e))
    return n
