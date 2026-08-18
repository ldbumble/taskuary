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
MAIL_SELECT = 'id,subject,from,receivedDateTime,sentDateTime,bodyPreview,body,conversationId,webLink'


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


def graph_creds(store, c):
    """Effective Graph credentials for a connector: its own, else the Outlook connector's
    saved app (Teams shares it by design), else the AZURE_* env vars (in graph_token).
    Returns (cfg, secret, borrowed_from_outlook)."""
    cfg, sec = _cfg(c), c.get('Secret')
    if c['Type'] != 'outlook' and not (cfg.get('client_id') and sec):
        o = store.get_connector_by_type('outlook', with_secret=True)
        ocfg = _cfg(o) if o else {}
        if o and (ocfg.get('client_id') or o.get('Secret')):
            return {**ocfg, **{k: v for k, v in cfg.items() if v}}, sec or o.get('Secret'), True
    return cfg, sec, False


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
    (they become the Board's repo choices) and write the repo map into SOUL.md."""
    tok = c.get('Secret')
    if not tok: raise RuntimeError('no PAT saved yet - paste one under Credentials')
    u = requests.get('https://api.github.com/user', headers=gh_headers(tok), timeout=20)
    u.raise_for_status()
    repos = list_accessible_repos(tok)
    have = {s['Address'] for s in store.list_sources(active_only=False) if s['Channel'] == 'github'}
    added = 0
    for rp in repos:
        if rp['full_name'] not in have:
            store.save_source({'Channel': 'github', 'Address': rp['full_name'], 'ConnectorId': c['ConnectorId'],
                               'Active': 1, 'Owner': actor}, actor)
            added += 1
    from .docsync import sync_connections, update_repo_map
    from .llm import build_llm
    try: llm = build_llm(store)
    except Exception: llm = None
    update_repo_map(store, repos, actor, tok=tok, llm=llm)
    sync_connections(store, actor)
    return {'login': u.json().get('login'), 'repos': len(repos), 'added': added}


def _slack(tok, method, **params):
    r = requests.get(f'https://slack.com/api/{method}', params=params, timeout=20,
                     headers={'Authorization': f'Bearer {tok}'})
    r.raise_for_status()
    j = r.json()
    if not j.get('ok'): raise RuntimeError(f"slack {method}: {j.get('error')}")
    return j


def test_connector(store, cid: int) -> dict:
    """Live credential + access probe; the result (or failure) lands on the connector row."""
    c = store.get_connector(cid, with_secret=True)
    if not c: raise ValueError('connector not found')
    cfg, t0 = _cfg(c), time.time()
    try:
        if c['Type'] in ('outlook', 'teams'):
            gcfg, gsec, borrowed = graph_creds(store, c)
            own = bool(cfg.get('client_id') and c.get('Secret'))
            tok = graph_token(gcfg, gsec)
            detail = 'Graph token OK' + ('' if own else
                                         " (using the Outlook connector's credentials)" if borrowed
                                         else ' (using server env credentials)')
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
            detail = f"authenticated as {d['login']} · {d['repos']} repos discovered · {d['added']} new sources · repo map written to SOUL.md"
        elif c['Type'] == 'slack':
            if not c.get('Secret'): raise RuntimeError('no bot token saved - paste an xoxb- token under Credentials')
            a = _slack(c['Secret'], 'auth.test')
            detail = f"authenticated as {a.get('user')} in {a.get('team')}"
            src = next((s for s in store.list_sources(active_only=False) if s['Channel'] == 'slack'), None)
            if src:
                _slack(c['Secret'], 'conversations.history', channel=src['Address'], limit=1)
                detail += f" · channel read OK for {src['Address']}"
            else:
                detail += ' - add a channel ID under Sources to probe reads'
        elif c['Type'] == 'mssql':
            from .mssql import test as mssql_test
            conn_cfg = _cfg(c)
            if c.get('Secret'): conn_cfg.setdefault('password', c['Secret'])
            r = mssql_test(conn_cfg)
            if not r['ok']: raise RuntimeError(r['error'])
            detail = f"connected · {r['version']} · db {r['database']}"
        elif c['Type'] == 'winrm':
            import subprocess
            host = cfg.get('host')
            if not host: raise RuntimeError('no host set - enter the machine name (e.g. AZWEB01)')
            p = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                                f'Test-WSMan -ComputerName {host} -ErrorAction Stop | Out-Null; '
                                f'Invoke-Command -ComputerName {host} -ScriptBlock {{ $env:COMPUTERNAME }}'],
                               capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=60)
            if p.returncode != 0:
                raise RuntimeError((p.stderr or p.stdout or 'WinRM unreachable')[:400]
                                   + ' - if this is a box you RDP into, PS remoting may need enabling: '
                                     'run Enable-PSRemoting -Force on it once (elevated)')
            detail = f"remote run OK on {(p.stdout or '').strip() or host} (your Windows credentials)"
        elif c['Type'] in ('anthropic', 'openai', 'azure_openai'):
            from .llm import test_ai
            detail = test_ai(store, cid)
        else:
            raise RuntimeError(f"no test for connector type '{c['Type']}'")
        store.touch_connector(cid)
        return {'ok': True, 'ms': int((time.time() - t0) * 1000), 'detail': detail}
    except Exception as e:
        store.touch_connector(cid, str(e))
        return {'ok': False, 'ms': int((time.time() - t0) * 1000), 'detail': str(e)[:500]}


_DROP = re.compile(r'(?is)<(script|style|head)[^>]*>.*?</\1>')
_BLOCK = re.compile(r'(?i)<br\s*/?>|</(p|div|tr|li|h[1-6]|blockquote|table)>')

def _clean(html):
    """HTML mail -> readable text. Block ends become NEWLINES: collapsing every whitespace
    run (the old behaviour) mashed the reply and the quoted 'From:/Sent:/To:' history into
    one wall of text, which no reader - human or model - could take apart."""
    from html import unescape
    txt = _BLOCK.sub('\n', _DROP.sub(' ', html or ''))
    txt = unescape(re.sub(r'<[^>]+>', ' ', txt))
    txt = re.sub(r'[^\S\n]+', ' ', txt.replace('\xa0', ' '))
    return re.sub(r'\n{3,}', '\n\n', re.sub(r' ?\n ?', '\n', txt)).strip()

# Graph's bodyPreview is capped at 255 chars - reading it FIRST truncated every stored mail,
# so the panel (and the agents) only ever saw the opening sentence. Full body wins.
def _body(m): return (_clean((m.get('body') or {}).get('content')) or m.get('bodyPreview') or '')[:20000]

def _local(iso):
    try: return datetime.fromisoformat(iso.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except ValueError: return iso


def _mail_msgs(tok, upn, since, folder='inbox'):
    # folder-scoped - a bare /messages spans every folder including Sent Items, which made
    # the owner's own replies come back through the funnel as inbound work
    r = requests.get(f'{GRAPH}/users/{upn}/mailFolders/{folder}/messages',
                     headers={'Authorization': f'Bearer {tok}'}, timeout=30,
                     params={'$top': 25, '$orderby': 'receivedDateTime desc', '$select': MAIL_SELECT,
                             '$filter': f'receivedDateTime gt {since}'})
    r.raise_for_status()
    return r.json().get('value', [])


def ingest_outbound_mail(store, mailbox: str, m: dict) -> int:
    """The owner's SENT mail never gets its own timeline row and never becomes work: when
    the conversation has a task, it rides along INSIDE the chain (a 'context' message on
    the task + a 'You replied' history entry, so the side panel shows it was answered).
    No matching chain -> nothing stored at all."""
    ext = f"graph:{m['id']}"
    if store.message_exists(ext): return 0
    conv = m.get('conversationId')
    tid = next((s['task_id'] for s in store.snapshots() if conv and conv in s['conversation_ids']), None)
    if not tid: return 0
    mid = store.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': conv, 'Channel': 'email',
                             'SourceName': mailbox, 'Subject': m.get('subject'), 'FromName': 'You',
                             'FromEmail': mailbox, 'SentAt': _local(m.get('receivedDateTime') or m.get('sentDateTime') or ''),
                             'BodyText': _body(m),
                             'SourceLink': m.get('webLink'), 'Status': 'context'})
    store.add_route(mid, tid, 'attach', None, 'your reply on this thread - kept for context', [], 'router')
    store.add_comment(tid, 'you', 'human', f"You replied: {(m.get('bodyPreview') or '')[:300]}")
    return 1


CH2SRC = {'outlook': 'email', 'teams': 'teams', 'slack': 'slack', 'github': 'github'}
TQ_ISSUE = re.compile(r'^\[TQ-\d{4}\]')      # issues the coder itself opened - never ingest those back


def ingest_github_issues(store, repo: str, tok: str, since, llm=None, file_only=False) -> int:
    """GitHub as an INBOUND channel: new issues land on the Timeline and go through the
    same triage as mail. Issues Taskuary opened for its own tasks are skipped, otherwise
    the coder would file work against itself forever."""
    n = 0
    from .github import list_issues
    for i in reversed(list_issues(tok, repo, since=since.astimezone().isoformat())):
        if TQ_ISSUE.match(i.get('title') or ''): continue
        who = (i.get('user') or {}).get('login') or 'github'
        out = ingest_message(store, {
            'external_id': f"gh:{repo}#{i['number']}", 'channel': 'github',
            'subject': f"{repo}#{i['number']} {i.get('title') or ''}".strip(),
            'body': (i.get('body') or '(no description)')[:20000],
            'from_name': who, 'from_email': f'{who}@users.noreply.github.com',
            'conversation_id': f"gh:{repo}#{i['number']}", 'sent_at': _local(i.get('updated_at') or ''),
            'source_link': i.get('html_url'), 'source_name': repo}, llm=llm, file_only=file_only)
        n += out['status'] != 'duplicate'
    return n


def _since(s):
    if not s.get('LastPolledAt'): return datetime.now() - timedelta(days=1)
    return datetime.fromisoformat(s['LastPolledAt'].replace(' ', 'T'))


def poll_channels(store) -> int:
    """Ingest new items for every connection the owner marked as a TRIGGER, through the
    same triage funnel (incl. the configured AI, if any). A connection without the trigger
    role is still usable by agents and reports - it just never creates work on its own.
    Failures land on the card."""
    from .llm import build_llm
    from .store import roles_of
    try: llm = build_llm(store)
    except Exception: llm = None
    n = 0
    for c in store.list_connectors():
        if not c['Active'] or c['Type'] not in CH2SRC: continue
        roles = roles_of(c)
        # trigger = becomes work; feed = shows on the timeline and stops there; neither = never polled
        if not roles & {'trigger', 'feed'}: continue
        file_only = 'trigger' not in roles
        full = store.get_connector(c['ConnectorId'], with_secret=True)
        try:
            if c['Type'] in ('outlook', 'teams'):
                gcfg, gsec, _ = graph_creds(store, full)
                tok = graph_token(gcfg, gsec)
            else:
                tok = full.get('Secret')
            for s in store.list_sources():
                if s['Channel'] != CH2SRC[c['Type']]: continue
                since = _since(s)
                if c['Type'] == 'outlook':
                    since_iso = since.astimezone().isoformat()
                    # your replies ride along as CONTEXT: attached to the thread's task,
                    # visible on the timeline, never triaged into work
                    for m in reversed(_mail_msgs(tok, s['Address'], since_iso, folder='sentitems')):
                        n += ingest_outbound_mail(store, s['Address'], m)
                    for m in reversed(_mail_msgs(tok, s['Address'], since_iso)):
                        frm = (m.get('from') or {}).get('emailAddress') or {}
                        if (frm.get('address') or '').lower() == s['Address'].lower():
                            continue   # the mailbox's own mail (moved copies, self-sends) is never inbound work
                        out = ingest_message(store, file_only=file_only, msg={
                            'external_id': f"graph:{m['id']}", 'channel': 'email',
                            'subject': m.get('subject'), 'body': _body(m),
                            'from_name': frm.get('name'), 'from_email': frm.get('address'),
                            'conversation_id': m.get('conversationId'), 'sent_at': _local(m.get('receivedDateTime') or ''),
                            'source_link': m.get('webLink'), 'source_name': s['Address']}, llm=llm)
                        n += out['status'] != 'duplicate'
                elif c['Type'] == 'github':
                    n += ingest_github_issues(store, s['Address'], tok, since, llm, file_only)
                elif c['Type'] == 'slack':
                    hist = _slack(tok, 'conversations.history', channel=s['Address'],
                                  oldest=since.timestamp(), limit=25)
                    for m in reversed(hist.get('messages', [])):
                        if m.get('subtype'): continue   # joins/leaves/bots noise
                        out = ingest_message(store, file_only=file_only, msg={
                            'external_id': f"slack:{s['Address']}:{m.get('ts')}", 'channel': 'slack',
                            'subject': None, 'body': m.get('text'), 'from_name': m.get('user'),
                            'conversation_id': f"slack:{s['Address']}",
                            'sent_at': datetime.fromtimestamp(float(m.get('ts', 0))).strftime('%Y-%m-%d %H:%M:%S'),
                            'source_name': s['Address']}, llm=llm)
                        n += out['status'] != 'duplicate'
                store.touch_source(s['SourceId'])
            store.touch_connector(c['ConnectorId'])
        except Exception as e:
            logger.warning(f"channel poll failed ({c['Type']}): {e}")
            store.touch_connector(c['ConnectorId'], str(e))
    return n
