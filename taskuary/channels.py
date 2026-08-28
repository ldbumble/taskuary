"""Channel connectors - the cards on the Connectors tab: Outlook mail + Microsoft Teams
(Graph, app-only client credentials) and GitHub (fine-grained PAT). test_connector is a
live probe (token/chat-read/repo-discovery); poll_channels is the scheduled ingest that
funnels mail and chats through the same triage as everything else. Credentials left blank
fall back to AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET env vars.
"""
import base64, hashlib, json, os, re, time
from html import unescape
from datetime import datetime, timedelta
import requests
from loguru import logger

from .github import _h as gh_headers, list_accessible_repos
from .ingest import ingest_message

GRAPH = 'https://graph.microsoft.com/v1.0'
MAIL_SELECT = 'id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,bodyPreview,body,conversationId,webLink,hasAttachments,isRead'


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


def _addrs(rows) -> list:
    """The addresses off a Graph recipient list. Triage needs to know whether the mailbox is
    on the To line or merely in Cc - being copied on other people's work is not an assignment."""
    return [a for a in ((r.get('emailAddress') or {}).get('address') or '' for r in rows or []) if a]


def graph_creds(store, c):
    """Effective Graph credentials for a connector: its own, else the Outlook connector's
    saved app (Teams shares it by design), else the AZURE_* env vars (in graph_token).
    Returns (cfg, secret, borrowed_from_outlook)."""
    cfg, sec = _cfg(c), c.get('Secret')
    if c['Type'] != 'outlook' and not (cfg.get('client_id') and sec):
        o = store.get_connector_by_type('outlook', with_secret=True)
        ocfg = _cfg(o) if o else {}
        if o and (ocfg.get('client_id') or o.get('Secret')):
            # _cid = whose secret this is, so a rotated refresh token is saved on the right card
            return {**ocfg, **{k: v for k, v in cfg.items() if v}, '_cid': o['ConnectorId']}, sec or o.get('Secret'), True
    return {**cfg, '_cid': c.get('ConnectorId')}, sec, False


def graph_token(cfg: dict, secret: str = None) -> str:
    """An access token for Graph. Two roads: the card's owner signed in with their own account
    (auth=user: the secret is a refresh token, msauth turns it into access tokens) or a tenant
    app registration (client credentials, app-only). The callers cannot tell them apart."""
    if (cfg or {}).get('auth') == 'user':
        from . import msauth
        return msauth.access_token(cfg, secret)
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
    # who the PAT is: kept on the card so About you can say it without another API call
    login = u.json().get('login')
    if login:
        try: cfg0 = json.loads(c.get('ConfigJson') or '{}')
        except ValueError: cfg0 = {}
        if cfg0.get('login') != login: store.set_connector_config(c['ConnectorId'], {**cfg0, 'login': login})
    repos = list_accessible_repos(tok)
    have = {s['Address']: s for s in store.list_sources(active_only=False) if s['Channel'] == 'github'}
    added = 0
    for rp in repos:
        s = have.get(rp['full_name'])
        if not s:
            store.save_source({'Channel': 'github', 'Address': rp['full_name'], 'ConnectorId': c['ConnectorId'],
                               'Active': 1, 'Owner': 'discovered', 'ConfigJson': json.dumps({'private': rp.get('private', False)})}, actor)
            added += 1
        else:
            # public or private is what the auto-dispatch picker warns on, so a repo discovered
            # before the flag existed learns it now - its pickers untouched
            try: gc = json.loads(s.get('ConfigJson') or '{}')
            except ValueError: gc = {}
            if gc.get('private') != rp.get('private', False):
                store.save_source({'SourceId': s['SourceId'], 'ConfigJson': json.dumps({**gc, 'private': rp.get('private', False)})}, actor)
    # a repo the CURRENT token cannot see is REMOVED: the list is what this token reaches, period
    # (owner's call - a fine-grained PAT scoped to one repo sat over 57 rows another token had
    # found). A repo the token covers again later is rediscovered with fresh pickers.
    seen = {rp['full_name'] for rp in repos}
    gone = 0
    for name, s in have.items():
        if name not in seen:
            store.delete_source(s['SourceId']); gone += 1
    from .docsync import sync_connections, update_repo_map
    from .llm import build_llm
    try: llm = build_llm(store)
    except Exception: llm = None
    update_repo_map(store, repos, actor, tok=tok, llm=llm)
    sync_connections(store, actor)
    return {'login': u.json().get('login'), 'repos': len(repos), 'added': added, 'unreachable': gone}


def _slack(tok, method, post=False, **params):
    url = f'https://slack.com/api/{method}'
    hdr = {'Authorization': f'Bearer {tok}'}
    # write methods (conversations.mark) are POST-only; the read ones are happy either way
    r = requests.post(url, data=params, timeout=20, headers=hdr) if post \
        else requests.get(url, params=params, timeout=20, headers=hdr)
    r.raise_for_status()
    j = r.json()
    if not j.get('ok'): raise RuntimeError(f"slack {method}: {j.get('error')}")
    return j


ACTOR_DISCOVER = 'connector-test'


def test_connector(store, cid: int) -> dict:
    """Live credential + access probe; the result (or failure) lands on the connector row."""
    c = store.get_connector(cid, with_secret=True)
    if not c: raise ValueError('connector not found')
    cfg, t0 = _cfg(c), time.time()
    try:
        if c['Type'] in ('outlook', 'teams'):
            gcfg, gsec, borrowed = graph_creds(store, c)
            if c['Type'] == 'teams' and gcfg.get('auth') == 'user':
                # Graph's chat delta (getAllMessages) is app-only; a person's sign-in cannot read it
                raise RuntimeError('Teams chat reading needs a tenant app registration (application permission '
                                   'Chat.Read.All) - the Outlook sign-in covers mail, sending and calendar only. '
                                   'Enter tenant_id + client_id + client secret on this card.')
            own = bool(cfg.get('client_id') and c.get('Secret'))
            tok = graph_token(gcfg, gsec)
            detail = (f"signed in as {gcfg.get('name') or gcfg.get('account')} ({gcfg.get('account')})" if gcfg.get('auth') == 'user'
                      else 'Graph token OK' + ('' if own else
                                               " (using the Outlook connector's credentials)" if borrowed
                                               else ' (using server env credentials)'))
            if c['Type'] == 'outlook':
                # the calendar rides the same app: one more permission, and the card says whether it is there
                try:
                    from . import calendar as cal
                    from datetime import datetime as _dt, timedelta as _td
                    boxes = [x['Address'] for x in store.list_sources() if x.get('Channel') == 'email' and x.get('Address')]
                    if boxes:
                        n = len(cal.outlook_events(gcfg, gsec, boxes[:1], _dt.now(), _dt.now() + _td(days=7), cal.tz_of(store)))
                        detail += f' · calendar read OK ({n} events in the next 7 days)'
                except Exception as e:
                    detail += f' · calendar: {str(e)[:160]}'
            if c['Type'] == 'teams':
                src = next((s for s in store.list_sources(active_only=False)
                            if s['Channel'] == 'teams' and '@' in (s['Address'] or '')), None)
                if src:
                    # probe the road the POLLER takes, or a green card means nothing
                    msgs = _teams_delta(tok, src['Address'], _utc(datetime.now() - timedelta(days=7)), cap=100)
                    people = {(((m.get('from') or {}).get('user') or {}).get('displayName'))
                              for m in msgs if ((m.get('from') or {}).get('user'))}
                    detail = (f"chat read OK for {src['Address']} - {len(msgs)} messages in the last 7 days across "
                              f"{len({m.get('chatId') for m in msgs})} chats, {len(people - {None})} people")
                else:
                    detail += ' - add a Teams source (user UPN) to probe chat access'
        elif c['Type'] == 'github':
            d = github_discover(store, c)
            detail = (f"authenticated as {d['login']} · {d['repos']} repos reachable · {d['added']} new sources"
                      + (f" · {d['unreachable']} removed (this token cannot see them)" if d.get('unreachable') else '')
                      + ' · repo map written to SOUL.md')
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
        elif c['Type'] in ('gmail', 'imap'):
            from .imapmail import test_imap
            detail = test_imap(store, store.get_connector(c['ConnectorId'], with_secret=True))
        elif c['Type'] == 'telegram':
            from .messengers import tg_test
            detail = tg_test(store, store.get_connector(c['ConnectorId'], with_secret=True))
        elif c['Type'] == 'whatsapp':
            from .messengers import wa_test
            detail = wa_test(store, store.get_connector(c['ConnectorId'], with_secret=True))
        elif c['Type'] == 'imessage':
            from .imessage import test as imessage_test
            detail = imessage_test(store, c)
        elif c['Type'] in ('exa', 'tavily', 'firecrawl', 'reader'):
            # a real call, not a key-shape check: these all fail the same way (401) and the
            # owner should find that out here rather than from an empty report on Monday
            from .reports import REGISTRY, resolve_cfg
            probe = ({'url': 'https://example.com'} if c['Type'] in ('firecrawl', 'reader')
                     else {'query': 'taskuary local-first ai task hub', 'num': 1})
            head, _body = REGISTRY[c['Type']](resolve_cfg(store, {**probe, 'type': c['Type'], 'max_rows': 1}))
            detail = f'{c["Type"]} answered: {head}'
        elif c['Type'] in ('jira', 'asana', 'monday', 'clickup', 'todoist'):
            from . import pm
            detail = pm.test(store, store.get_connector(c['ConnectorId'], with_secret=True))
        elif c['Type'] in ('gitlab', 'azdo', 'linear', 'trello', 'notion', 'discord', 'sentry', 'pagerduty'):
            from . import devtools
            detail = devtools.test(store, store.get_connector(c['ConnectorId'], with_secret=True))
        elif c['Type'] == 'mssql':
            from .mssql import test as mssql_test
            conn_cfg = _cfg(c)
            if c.get('Secret'): conn_cfg.setdefault('password', c['Secret'])
            r = mssql_test(conn_cfg)
            if not r['ok']: raise RuntimeError(r['error'])
            detail = f"connected · {r['version']} · db {r['database']}"
        elif c['Type'] == 'database':
            from .db import test as db_test
            from .reports import database_connection
            r = db_test(database_connection(store))
            if not r['ok']: raise RuntimeError(r['error'])
            detail = r['detail']
        elif c['Type'] in ('aws', 'azure'):
            # Test also DISCOVERS: the keys/app are asked what they can see, and every
            # bucket, log group, container and workspace lands under Sources with its own
            # mode picker (report by default - nothing is polled until you say so)
            from .reports import aws_connection, azure_connection
            mod = __import__(f'taskuary.{c["Type"]}', fromlist=['x'])
            conn_cfg = (aws_connection if c['Type'] == 'aws' else azure_connection)(store)
            r = mod.test(conn_cfg)
            if not r['ok']: raise RuntimeError(r['error'])
            detail = r['detail']
            # the same app registration usually reaches the DIRECTORY too, and that is a
            # whole family of reports (people, groups, licences, sign-ins) the card would
            # otherwise never mention - so Test says which of them this app can do
            if c['Type'] == 'azure':
                try:
                    from .azure import test_entra
                    e = test_entra(conn_cfg)
                    detail += ' · ' + (e['detail'] if e['ok'] else f"Entra: {e['error']}")
                except Exception as e:
                    detail += f' · Entra probe failed: {str(e)[:100]}'
            try:
                d = mod.discover(store, conn_cfg, c['ConnectorId'], ACTOR_DISCOVER)
                detail += f" · {d['found']} objects visible, {d['added']} new under Sources"
                # "0 objects visible" alone reads as a broken feature; the hint says which
                # permission is missing, because that is always what an empty result means
                if d.get('hint'): detail += f" — {d['hint']}"
            except Exception as e:
                detail += f' · discovery failed: {str(e)[:120]}'
        elif c['Type'] == 'intacct':
            from .intacct import probe
            from .reports import intacct_connection
            detail = probe(intacct_connection(store))
        elif c['Type'] == 'prometheus':
            from .reports import run_prometheus, prometheus_connection
            head, _ = run_prometheus({**prometheus_connection(store), 'query': 'vector(1)', 'max_rows': 1})
            detail = f'query OK ({head}) - build the reports on the Reports tab'
        elif c['Type'] == 'datadog':
            from .reports import datadog_connection
            dd = datadog_connection(store)
            site = (dd.get('site') or 'datadoghq.com').strip()
            r = requests.get(f'https://api.{site}/api/v1/validate', timeout=20,
                             headers={'DD-API-KEY': dd.get('api_key') or ''})
            if r.status_code != 200 or not r.json().get('valid'):
                raise RuntimeError(f'Datadog rejected the API key ({r.status_code})')
            detail = f'API key valid on {site}' + ('' if dd.get('app_key') else ' - add the application key for monitor reads')
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
        elif c['Type'] in ('anthropic', 'openai', 'azure_openai', 'openrouter', 'ollama'):
            from .llm import test_ai
            detail = test_ai(store, cid)
        elif c['Type'] == 'sharepoint':
            from . import sharepoint
            detail = sharepoint.test(store, c)
        elif c['Type'] == 'google_sheets':
            from . import sheets
            detail = sheets.test(store, c)
        elif c['Type'] in ('groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt', 'stt_server', 'local_whisper'):
            from . import voice
            detail = voice.test(store, store.get_connector(cid, with_secret=True))   # a second of silence through the real endpoint
        else:
            raise RuntimeError(f"no test for connector type '{c['Type']}'")
        store.touch_connector(cid)
        out = {'ok': True, 'ms': int((time.time() - t0) * 1000), 'detail': detail}
        if c['Type'] == 'imessage':
            # the read succeeded, but the send card still needs to name the host macOS will list
            from .imessage import setup_info
            out['setup'] = setup_info('ready', None)
        return out
    except Exception as e:
        store.touch_connector(cid, str(e))
        out = {'ok': False, 'ms': int((time.time() - t0) * 1000), 'detail': str(e)[:500]}
        # a failure the owner fixes in the OS (macOS privacy consent) carries the structured
        # half too - which pane, which host - so the card can offer the button, not a paragraph
        if getattr(e, 'setup', None): out['setup'] = e.setup
        return out


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

# What rode along with the mail. Screenshots of the thing that is broken ARE the ask half the
# time ("see below"), and a text-only funnel threw them away.
ATT_MAX, ATT_BYTES = 12, 12 * 1024 * 1024      # per message: how many, and how big each may be
_SAFE = re.compile(r'[^A-Za-z0-9._-]+')

def save_attachments(store, mid: int, items: list, ext_prefix: str) -> int:
    """Write the bytes to disk and the metadata to the db. Items are Graph fileAttachments;
    anything without contentBytes (an attached mail, a OneDrive link) is recorded WITHOUT a
    path, so the panel can still say it was there and point at the original."""
    import base64
    from .artifacts import attachment_dir
    n = 0
    for i, a in enumerate(items[:ATT_MAX]):
        ext_id = f"{ext_prefix}:{a.get('id') or i}"
        if store.attachment_exists(ext_id): continue
        name = (a.get('name') or f'attachment-{i}')[:120]
        raw = a.get('contentBytes')
        path = None
        if raw:
            try: data = base64.b64decode(raw)
            except Exception: data = b''
            if data and len(data) <= ATT_BYTES:
                f = attachment_dir(mid) / f'{i}-{_SAFE.sub("_", name)}'
                f.write_bytes(data)
                path = str(f)
        store.add_attachment({'MessageId': mid, 'ExternalId': ext_id, 'Name': name,
                              'ContentType': a.get('contentType') or 'application/octet-stream',
                              'Size': int(a.get('size') or 0), 'ContentId': a.get('contentId'),
                              'Inline': 1 if a.get('isInline') else 0, 'Path': path})
        n += 1
    return n


def mail_attachments(tok: str, upn: str, graph_id: str) -> list:
    """One message's attachments from Graph, raw. Called only when the mail says it has some -
    an extra request per mail otherwise, for nothing."""
    r = requests.get(f'{GRAPH}/users/{upn}/messages/{graph_id}/attachments',
                     headers={'Authorization': f'Bearer {tok}'}, timeout=60)
    r.raise_for_status()
    return r.json().get('value', [])


def fetch_mail_attachments(store, mid: int, tok: str, upn: str, graph_id: str) -> int:
    return save_attachments(store, mid, mail_attachments(tok, upn, graph_id), f'graph:{graph_id}')


def images_for_triage(store, items: list) -> list:
    """[(media_type, base64)] for the pictures on a mail, straight from the Graph payload - so
    triage can SEE them. They have to be read before the message row exists: the attachments used
    to be saved after ingest, which meant the one classifying "See below." never saw what was
    below it, and filed a screenshot of a stack trace as informational."""
    from .llm import VISION_BYTES, VISION_MAX, VISION_TYPES
    if str(store.get_settings().get('vision_enabled') or '1') != '1': return []
    out = []
    for a in items:
        if len(out) >= VISION_MAX: break
        ct = str(a.get('contentType') or '').split(';')[0].lower()
        raw = a.get('contentBytes')
        if ct not in VISION_TYPES or not raw or int(a.get('size') or 0) > VISION_BYTES: continue
        out.append((ct, raw))                    # Graph already hands it over base64-encoded
    return out


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


def ingest_own_message(store, msg: dict, why: str) -> int:
    """Anything YOU sent - a mail reply, a line in a chat - never gets its own timeline row
    and never becomes work: when the conversation already has a task it rides along INSIDE
    the chain (a 'context' message + a history entry, so the panel shows it was answered).
    No matching chain -> nothing stored at all."""
    if store.message_exists(msg['external_id']): return 0
    conv = msg.get('conversation_id')
    tid = next((s['task_id'] for s in store.snapshots() if conv and conv in s['conversation_ids']), None)
    if not tid: return 0
    mid = store.add_message({'TaskId': tid, 'ExternalId': msg['external_id'], 'ConversationId': conv,
                             'Channel': msg['channel'], 'SourceName': msg.get('source_name'),
                             'Subject': msg.get('subject'), 'FromName': 'You', 'FromEmail': msg.get('from_email'),
                             'SentAt': msg.get('sent_at'), 'BodyText': msg.get('body'),
                             'SourceLink': msg.get('source_link'), 'Status': 'context'})
    store.add_route(mid, tid, 'attach', None, why, [], 'router')
    store.add_comment(tid, 'you', 'human', f"You replied: {(msg.get('body') or '')[:300]}")
    return 1


def ingest_outbound_mail(store, mailbox: str, m: dict) -> int:
    return ingest_own_message(store, {
        'external_id': f"graph:{m['id']}", 'channel': 'email', 'source_name': mailbox,
        'subject': m.get('subject'), 'from_email': mailbox, 'body': _body(m),
        'conversation_id': m.get('conversationId'), 'source_link': m.get('webLink'),
        'sent_at': _local(m.get('receivedDateTime') or m.get('sentDateTime') or '')},
        'your reply on this thread - kept for context')


# ── Teams chats ─────────────────────────────────────────────────────────────────────
# Three roads out of Graph, and only one works:
#   /chats/{id}/messages   - refuses (403) every chat HOSTED IN ANOTHER ORG'S TENANT, which
#                            is exactly where the external-vendor threads live;
#   /chats/getAllMessages  - rejects every lastModifiedDateTime filter we can form and pages
#                            OLDEST first, so it hands back years of bot attachment posts;
#   .../getAllMessages/delta - takes the filter, pages NEWEST first, and includes those
#                            externally-hosted chats. That is the one.
def _utc(dt) -> str:
    from datetime import timezone
    return dt.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%S.000Z')


def _teams_delta(tok, upn, since_iso, cap=200):
    """Every chat message this user can see since a timestamp, newest first."""
    url = f'{GRAPH}/users/{upn}/chats/getAllMessages/delta'
    params, out = {'$top': 50, '$filter': f'lastModifiedDateTime gt {since_iso}'}, []
    while url and len(out) < cap:
        r = requests.get(url, headers={'Authorization': f'Bearer {tok}'}, params=params, timeout=45)
        if r.status_code == 403:
            raise RuntimeError('token OK but chat read DENIED (403) - app-only Chat.Read.All is a Microsoft '
                               'protected API: submit the approval form for this app registration')
        r.raise_for_status()
        j = r.json()
        out += j.get('value', [])
        url, params = j.get('@odata.nextLink'), None       # the nextLink carries the filter itself
    return out[:cap]


def _chat_meta(tok, chat_id, cache):
    """(topic, kind) for a chat. Readable even for chats whose MESSAGES are refused, so a
    group thread keeps its real name on the timeline."""
    if chat_id in cache: return cache[chat_id]
    meta = ('', 'chat')
    try:
        r = requests.get(f'{GRAPH}/chats/{chat_id}', headers={'Authorization': f'Bearer {tok}'}, timeout=20)
        if r.status_code == 200:
            j = r.json()
            meta = (j.get('topic') or '', j.get('chatType') or 'chat')
    except requests.RequestException as e:
        logger.debug(f'teams chat lookup failed for {chat_id[:24]}: {e}')
    cache[chat_id] = meta
    return meta


def _graph_user(tok, oid, cache):
    """AAD object id -> (name, address). Cached per poll: the sender's address is what memory
    notes, skip-sender rules and the whole triage funnel key on."""
    if oid in cache: return cache[oid]
    who = ('Teams user', '')
    try:
        r = requests.get(f'{GRAPH}/users/{oid}', headers={'Authorization': f'Bearer {tok}'}, timeout=20,
                         params={'$select': 'displayName,mail,userPrincipalName'})
        if r.status_code == 200:
            j = r.json()
            who = (j.get('displayName') or 'Teams user', j.get('mail') or j.get('userPrincipalName') or '')
    except requests.RequestException as e:
        logger.debug(f'teams user lookup failed for {oid}: {e}')
    cache[oid] = who
    return who


# A picture in a Teams message is not an attachment. Graph reports attachments: [] and puts
# the image in the BODY as <img src=".../hostedContents/{id}/$value">, which _clean strips
# along with every other tag - so "the screenshot IS the ask" worked for mail and silently
# lost the picture on chat. Same shape as a Graph fileAttachment coming out, so the existing
# pipeline (images_for_triage before the row exists, save_attachments after) is reused whole.
_HOSTED = re.compile(r'<img[^>]+src="([^"]*?/hostedContents/[^"]*?)"', re.I)


def hosted_images(tok: str, html: str, cap: int = 4, where: str = '') -> list:
    out = []
    for i, url in enumerate(dict.fromkeys(_HOSTED.findall(html or '')).keys()):
        if i >= cap: break
        try:
            r = requests.get(unescape(url), headers={'Authorization': f'Bearer {tok}'}, timeout=30)
            r.raise_for_status()
        except Exception as e:
            # one readable line, not the signed hostedContents URL twice over: it is 900
            # characters of query string, it says nothing the status code does not, and two
            # of them per message buried the rest of the sync log. 403 here is the membership
            # check described below - expected, not a fault to hunt.
            code = getattr(getattr(e, 'response', None), 'status_code', None)
            why = ('Microsoft refused it for this chat (403 - the app is not a member)' if code == 403
                   else f'HTTP {code}' if code else str(e)[:120])
            logger.warning(f'teams image {i + 1} not readable{f" in {where}" if where else ""}: {why}')
            continue
        ct = (r.headers.get('Content-Type') or 'image/png').split(';')[0].strip()
        out.append({'id': hashlib.sha1(url.encode()).hexdigest()[:16],
                    'name': f"image-{i + 1}.{(ct.split('/')[-1] or 'png').replace('jpeg', 'jpg')}",
                    'contentType': ct, 'size': len(r.content), 'isInline': True,
                    'contentBytes': base64.b64encode(r.content).decode()})
    return out


def ingest_teams_chats(store, upn: str, tok: str, since, llm=None, file_only=False, read_it=False) -> int:
    """Teams as an inbound channel: each chat is a conversation (so a thread keeps building
    ONE task, like a mail thread), each human message an item on the timeline. Bot posts,
    call-started events, deletions and empty bodies are not messages anybody has to act on."""
    since_iso, users, chats, n = _utc(since), {}, {}, 0
    touched = set()                                # chats to mark read once, not per message
    me = ''
    try:
        r = requests.get(f'{GRAPH}/users/{upn}', headers={'Authorization': f'Bearer {tok}'},
                         params={'$select': 'id'}, timeout=20)
        me = r.json().get('id', '') if r.status_code == 200 else ''
    except requests.RequestException:
        pass
    for m in reversed(_teams_delta(tok, upn, since_iso)):          # oldest first, so threads read in order
        user = (m.get('from') or {}).get('user') or {}
        body = _clean((m.get('body') or {}).get('content'))
        if m.get('messageType') != 'message' or m.get('deletedDateTime') or not user.get('id') or not body: continue
        cid = m.get('chatId') or ''
        topic, kind = _chat_meta(tok, cid, chats) if cid else ('', 'chat')
        name, addr = _graph_user(tok, user['id'], users)
        name = user.get('displayName') or name
        # fetched BEFORE triage, like the mail path: the classifier has to see the screenshot
        # to judge it, and afterwards is too late
        raw_html = (m.get('body') or {}).get('content') or ''
        atts = hosted_images(tok, raw_html, where=topic or f'chat with {name}')
        # a picture we could not FETCH must not vanish silently the way it used to. Graph
        # refuses hostedContents unless the app registration carries ChatMessage.Read.All, and
        # "the screenshot was the whole ask" is exactly the message you cannot afford to read
        # as a sentence with a hole in it, so the row says what is missing.
        #
        # And it is NOT a missing consent, which is what this comment used to claim: the token
        # carries ChatMessage.Read.All and hostedContents still answers 403 AclCheckFailed -
        # a MEMBERSHIP check on the chat, not a scope check. An app-only connection is not in
        # the chat, so no permission grant fixes it; that would take delegated auth.
        missed = len(set(_HOSTED.findall(raw_html))) - len(atts)
        if missed > 0:
            body += ('\n\n[' + f"{missed} image{'s' if missed > 1 else ''} in this message could not be read: "
                     'Microsoft refused the download for THIS chat (403) - it happens on group '
                     'threads with external participants, whatever the app is consented for. '
                     'Images in your other chats come through normally. Open it in Teams to see it.]')
        common = {'external_id': f'teams:{cid}:{m["id"]}', 'channel': 'teams',
                  'subject': topic or (f'Teams chat with {name}' if kind == 'oneOnOne' else f'Teams {kind}'),
                  'body': body[:20000], 'conversation_id': f'teams:{cid}',
                  'sent_at': _local(m.get('createdDateTime') or ''), 'source_link': m.get('webUrl'),
                  'source_name': upn, 'images': images_for_triage(store, atts)}
        if user['id'] == me:                       # your own chat lines are context, never work
            n += ingest_own_message(store, {**common, 'from_name': 'You', 'from_email': upn},
                                    'your message in this chat - kept for context')
            continue
        out = ingest_message(store, {**common, 'from_name': name, 'from_email': addr}, llm=llm, file_only=file_only)
        n += out['status'] != 'duplicate'
        if atts and out.get('message_id') and out['status'] != 'duplicate':
            try: save_attachments(store, out['message_id'], atts, f'teams:{m["id"]}')
            except Exception as e: logger.warning(f'saving teams images for {m["id"]} failed: {e}')
        if cid: touched.add(cid)
    for cid in touched if read_it else ():
        mark_chat_read(tok, upn, cid, me)
    return n


CH2SRC = {'outlook': 'email', 'teams': 'teams', 'slack': 'slack', 'github': 'github',
          'telegram': 'telegram', 'whatsapp': 'whatsapp', 'imessage': 'imessage',
          'gmail': 'email', 'imap': 'email',
          'jira': 'jira', 'asana': 'asana', 'monday': 'monday',
          'clickup': 'clickup', 'todoist': 'todoist',
          'gitlab': 'gitlab', 'azdo': 'azdo', 'linear': 'linear', 'trello': 'trello',
          'notion': 'notion', 'discord': 'discord', 'sentry': 'sentry', 'pagerduty': 'pagerduty',
          # cloud objects are DISCOVERED sources: each carries its own mode (report/feed/tasks/off)
          'aws': 'aws', 'azure': 'azure'}
# A cloud object's mode lives on the SOURCE, not the connector - one bucket can feed the
# Timeline while the next is only a report. 'report' (the default) polls nothing at all.
CLOUD = ('aws', 'azure')
# Connections polled ONCE per connector: their cursor lives on the connector (telegram's
# getUpdates offset, whatsapp's bridge seq) or their API is 'assigned to me' with no
# per-source dimension at all. Their source row is a label, so the poll must not depend
# on one existing - see poll_channels.
PER_CONNECTOR = ('telegram', 'whatsapp', 'imessage', 'jira', 'asana', 'monday', 'clickup', 'todoist',
                 'gitlab', 'azdo', 'linear', 'trello', 'notion', 'sentry', 'pagerduty')

def _cloud_explicit(store, channel) -> bool:
    """Any discovered object set to feed or tasks? Then the connector is polled even
    without a trigger/feed role - the per-object picker carries the intent, the same deal
    github's per-repo pickers get."""
    return any(json.loads(s.get('ConfigJson') or '{}').get('mode') in ('feed', 'tasks')
               for s in store.list_sources() if s['Channel'] == channel)
TQ_ISSUE = re.compile(r'^\[TQ-\d{4}\]')      # issues the coder itself opened - never ingest those back


def gh_modes(src: dict, file_only: bool) -> tuple:
    """(issues_mode, prs_mode) for a repo. An EXPLICIT picker beats the connector's role -
    'issues: tasks' means tasks even on a tool-only card; unconfigured kinds follow the role,
    and PRs default off. One place, because the poller needs the same answer as the ingest
    to know whether this source was even looked at."""
    try: modes = json.loads(src.get('ConfigJson') or '{}')
    except ValueError: modes = {}
    default_mode = 'feed' if file_only else 'tasks'
    return (modes.get('issues') or default_mode, modes.get('prs') or 'off')


# Who may start a coding agent by themselves, per repo - the source's 'auto' picker, keyed on
# GitHub's own author_association. Everyone else's items still become tasks (in 'tasks' mode)
# and wait for the owner to promote them. Default off: a public repo would otherwise start an
# agent per drive-by PR (the session cap still holds, but a queue full of strangers is not
# what the cap is for). The Connectors card warns before switching a PUBLIC repo on.
GH_TEAM = ('OWNER', 'MEMBER', 'COLLABORATOR')
GH_AUTO = {'off': (), 'team': GH_TEAM, 'contributors': GH_TEAM + ('CONTRIBUTOR',), 'anyone': None}


def gh_auto_ok(src: dict, association: str) -> bool:
    try: mode = json.loads((src or {}).get('ConfigJson') or '{}').get('auto') or 'off'
    except ValueError: mode = 'off'
    allowed = GH_AUTO.get(mode, ())
    return allowed is None or (association or 'NONE').upper() in allowed


def ingest_github_issues(store, src: dict, tok: str, since, llm=None, file_only=False) -> int:
    """GitHub as an INBOUND channel: new issues - and, per repo, pull requests - land on the
    Timeline and go through the same triage as mail. What each KIND does is the source's own
    call (ConfigJson {"issues": "tasks|feed|off", "prs": ...}), because an open-source repo
    usually wants PRs SEEN but not auto-worked. Every item leads with who wrote it and
    GitHub's own author_association, so triage can weigh a stranger's PR on a public repo
    for what it is. Whether an item may start a coding agent by itself is the repo's 'auto'
    picker (gh_auto_ok): off by default, or the team / contributors / anyone. Issues Taskuary
    opened for its own tasks are skipped, otherwise the coder would file work against itself."""
    repo = src['Address']
    issues_mode, prs_mode = gh_modes(src, file_only)
    if issues_mode == 'off' and prs_mode == 'off': return 0
    n = 0
    from .github import list_items
    for i in reversed(list_items(tok, repo, since=since.astimezone().isoformat())):
        if TQ_ISSUE.match(i.get('title') or ''): continue
        is_pr = 'pull_request' in i
        mode = prs_mode if is_pr else issues_mode
        if mode == 'off': continue
        who = (i.get('user') or {}).get('login') or 'github'
        # WHO is asking is part of the ask on a public repo - triage reads this line first
        head = f"[{'pull request' if is_pr else 'issue'} by {who} - association: {i.get('author_association') or 'NONE'}]"
        out = ingest_message(store, {
            'external_id': f"gh:{repo}#{i['number']}", 'channel': 'github',
            'subject': f"{repo}#{i['number']} {i.get('title') or ''}".strip(),
            'body': f"{head}\n{(i.get('body') or '(no description)')[:20000]}",
            'from_name': who, 'from_email': f'{who}@users.noreply.github.com',
            'conversation_id': f"gh:{repo}#{i['number']}", 'sent_at': _local(i.get('updated_at') or ''),
            'source_link': i.get('html_url'), 'source_name': repo,
            'no_auto': not gh_auto_ok(src, i.get('author_association'))},
            llm=llm, file_only=mode == 'feed')
        n += out['status'] != 'duplicate'
    return n


def _gh_explicit(store) -> bool:
    """Any repo whose issues/PRs picker is set to something live - that IS the trigger intent,
    whatever the connector card's role says."""
    for s in store.list_sources():
        if s['Channel'] != 'github': continue
        try: m = json.loads(s.get('ConfigJson') or '{}')
        except ValueError: m = {}
        if {'tasks', 'feed'} & {m.get('issues'), m.get('prs')}: return True
    return False


# ── "the hub has read this" ─────────────────────────────────────────────────────────────
# One switch (Settings > Sync & startup) decides whether reading an item here also marks it
# read THERE, so the mailbox and the chat list stop showing work the funnel already took.
# Every marker is best-effort by design: a missing consent (Graph wants Mail.ReadWrite,
# Slack conversations.mark) must never cost the ingest that already succeeded, so failures
# are logged once and swallowed. Protocols with no read state for a bot - Telegram, Discord,
# the trackers - simply have no marker, and the switch is a no-op for them.
def wants_read(store) -> bool:
    try: return str(store.get_settings().get('mark_read_enabled') or '0') == '1'
    except Exception: return False


def mark_mail_read(tok: str, upn: str, graph_id: str):
    try:
        requests.patch(f'{GRAPH}/users/{upn}/messages/{graph_id}', timeout=20,
                       headers={'Authorization': f'Bearer {tok}'}, json={'isRead': True}).raise_for_status()
    except Exception as e: logger.warning(f'marking mail {graph_id} read failed: {e}')


def mark_chat_read(tok: str, upn: str, chat_id: str, user_id: str = ''):
    """Teams reads a CHAT, not a message - Graph offers no per-message read state. The body
    wants the directory OBJECT ID, which the poller already looked up for 'is this me'."""
    try:
        requests.post(f'{GRAPH}/users/{upn}/chats/{chat_id}/markChatReadForUser', timeout=20,
                      headers={'Authorization': f'Bearer {tok}'},
                      json={'user': {'id': user_id or upn}}).raise_for_status()
    except Exception as e: logger.warning(f'marking chat {chat_id} read failed: {e}')


def mark_slack_read(tok: str, channel: str, ts: str):
    try: _slack(tok, 'conversations.mark', post=True, channel=channel, ts=ts)
    except Exception as e: logger.warning(f'marking slack {channel} read failed: {e}')


# Every poll reaches back a little PAST its own watermark, and this is not belt-and-braces -
# without it a message that arrives moments before a poll is lost for good. Graph's
# getAllMessages/delta is eventually consistent: a Teams message sent at 15:29:11 was not yet
# in the delta when the 15:29:19 poll asked for it, so that poll saw nothing and moved the
# watermark to 15:29:19 anyway - eight seconds PAST the message. Every later poll asked for
# "newer than 15:29:19" and the message was permanently on the wrong side of the line. Nobody
# would ever have found it by re-syncing, because re-syncing is what buried it.
#
# Every channel here works the same way (a watermark that jumps to now), so every channel had
# the same hole. Re-reading a few minutes is free: ingest_message dedupes on external_id in its
# FIRST line, before policies and before any AI call.
POLL_OVERLAP = timedelta(minutes=5)


def _since(s, backfill_days: int = 0):
    """How far back to ask this source for. `backfill_days` WIDENS the window without moving the
    watermark - what the app does on startup, because whatever arrived while it was shut down was
    never polled by anyone, and 'since I last ran' is the wrong question after a weekend off."""
    last = (datetime.fromisoformat(s['LastPolledAt'].replace(' ', 'T')) - POLL_OVERLAP
            if s.get('LastPolledAt') else datetime.now() - timedelta(days=1))
    return min(last, datetime.now() - timedelta(days=backfill_days)) if backfill_days else last


def poll_channels(store, backfill_days: int = 0, progress=None, only=None) -> int:
    """Ingest new items for every connection the owner marked as a TRIGGER, through the
    same triage funnel (incl. the configured AI, if any). A connection without the trigger
    role is still usable by agents and reports - it just never creates work on its own.
    Failures land on the card. `backfill_days` reaches further back than the watermark - see
    _since; it is how startup catches up on mail that arrived while the app was closed."""
    from .llm import build_llm
    from .store import roles_of
    try: llm = build_llm(store)
    except Exception: llm = None
    read_it = wants_read(store)   # asked once per run, not once per message
    n = 0
    for c in store.list_connectors():
        if not c['Active'] or c['Type'] not in CH2SRC: continue
        if only is not None and c['Type'] not in only: continue     # a quick poll of the chatty ones
        roles = roles_of(c)
        # trigger = becomes work; feed = shows on the timeline and stops there; neither = never
        # polled - EXCEPT github, where the per-repo issue/PR pickers carry the intent: two
        # switches where one reads as enough was a trap (a repo set to "PRs: tasks" on a
        # tool-only card, a Sync that pulled nothing, and no error anywhere).
        if (not roles & {'trigger', 'feed'} and not (c['Type'] == 'github' and _gh_explicit(store))
                and not (c['Type'] in CLOUD and _cloud_explicit(store, CH2SRC[c['Type']]))): continue
        file_only = 'trigger' not in roles
        # said as it happens, not at the end: the timeline is refreshing while this runs, so
        # "reading Outlook" beside rows that are already arriving beats a spinner and a wait
        if progress:
            try: progress(c['Type'], n)
            except Exception: pass
        full = store.get_connector(c['ConnectorId'], with_secret=True)
        try:
            if c['Type'] in ('outlook', 'teams'):
                gcfg, gsec, _ = graph_creds(store, full)
                tok = graph_token(gcfg, gsec)
            else:
                tok = full.get('Secret')
            # ── connections whose SOURCE ROW IS ONLY A MARKER poll once per connector, and
            # they must poll even with NO source row at all. This used to live inside the
            # per-source loop, so a Telegram card whose '*' marker was never created (Test
            # skipped) or was deleted polled NOTHING: getUpdates never ran, so no chat could
            # ever announce itself, and Sync now looked broken with no error anywhere.
            if c['Type'] in PER_CONNECTOR:
                mine = [x for x in store.list_sources()
                        if x['Channel'] == CH2SRC[c['Type']]
                        and (not x.get('ConnectorId') or x['ConnectorId'] == c['ConnectorId'])]
                since = _since(mine[0] if mine else {}, backfill_days)
                if c['Type'] in ('telegram', 'whatsapp'):
                    from . import messengers
                    poll = messengers.poll_telegram if c['Type'] == 'telegram' else messengers.poll_whatsapp
                    n += poll(store, full, mine, llm, file_only)
                elif c['Type'] == 'imessage':
                    from . import imessage
                    n += imessage.poll(store, full, mine, llm, file_only)
                elif c['Type'] in ('jira', 'asana', 'monday', 'clickup', 'todoist'):
                    from . import pm
                    n += pm.poll(store, full, since, llm, file_only)
                else:
                    from . import devtools
                    n += devtools.poll(store, full, since, llm, file_only)
                for s in mine: store.touch_source(s['SourceId'])
                store.touch_connector(c['ConnectorId'])
                continue
            for s in store.list_sources():
                if s['Channel'] != CH2SRC[c['Type']]: continue
                # a source belongs to ONE connector: outlook and an IMAP mailbox are both
                # channel 'email', and without this the Graph poller tried the Gmail address.
                # (Orphans are adopted at startup, so ownership is always present now.)
                if s.get('ConnectorId') and s['ConnectorId'] != c['ConnectorId']: continue
                since = _since(s, backfill_days)
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
                        # the screenshot IS the ask in a "see below" mail, so it is fetched BEFORE
                        # triage and handed to it - then saved once the message row exists
                        atts = []
                        if m.get('hasAttachments'):
                            try: atts = mail_attachments(tok, s['Address'], m['id'])
                            except Exception as e: logger.warning(f"attachments for {m['id']} failed: {e}")
                        out = ingest_message(store, file_only=file_only, msg={
                            'external_id': f"graph:{m['id']}", 'channel': 'email',
                            'subject': m.get('subject'), 'body': _body(m),
                            'from_name': frm.get('name'), 'from_email': frm.get('address'),
                            'to': _addrs(m.get('toRecipients')), 'cc': _addrs(m.get('ccRecipients')),
                            'conversation_id': m.get('conversationId'), 'sent_at': _local(m.get('receivedDateTime') or ''),
                            'source_link': m.get('webLink'), 'source_name': s['Address'],
                            'images': images_for_triage(store, atts)}, llm=llm)
                        n += out['status'] != 'duplicate'
                        if atts and out.get('message_id') and out['status'] != 'duplicate':
                            try: save_attachments(store, out['message_id'], atts, f"graph:{m['id']}")
                            except Exception as e: logger.warning(f"saving attachments for {m['id']} failed: {e}")
                        # a duplicate is still mail the hub has read - the flag may just be
                        # older than the switch, and skipping it would strand those bold rows
                        if read_it and not m.get('isRead'): mark_mail_read(tok, s['Address'], m['id'])
                elif c['Type'] == 'teams':
                    n += ingest_teams_chats(store, s['Address'], tok, since, llm, file_only, read_it)
                elif c['Type'] == 'github':
                    # a repo with BOTH kinds off was not read, so its watermark must not
                    # move: advancing it would step over the issues sitting there, and
                    # switching the repo on later would only ever see what came next
                    if set(gh_modes(s, file_only)) == {'off'}: continue
                    n += ingest_github_issues(store, s, tok, since, llm, file_only)
                elif c['Type'] in ('gmail', 'imap'):
                    # one poll per connector (the UID watermark lives there); its own source only
                    from . import imapmail
                    if s['ConnectorId'] != c['ConnectorId']: continue
                    n += imapmail.poll_imap(store, full, [s], llm, file_only, backfill_days)
                elif c['Type'] in CLOUD:
                    # per SOURCE: each discovered object carries its own mode, and 'report'
                    # (the default) means the Reports tab may use it but nothing is polled.
                    # The picker OUTRANKS the card's role, like github's per-repo pickers:
                    # 'tasks' on a tool-only card means tasks, not a filed feed row.
                    mode = json.loads(s.get('ConfigJson') or '{}').get('mode') or 'report'
                    if mode not in ('feed', 'tasks'): continue
                    from .reports import aws_connection, azure_connection
                    mod = __import__(f'taskuary.{c["Type"]}', fromlist=['x'])
                    conn_cfg = (aws_connection if c['Type'] == 'aws' else azure_connection)(store)
                    n += mod.poll_source(store, conn_cfg, s, since, llm, mode == 'feed')
                elif c['Type'] == 'discord':
                    # per SOURCE, like slack: each watched channel id is its own source
                    from . import devtools
                    n += devtools.poll_discord(store, full, s, since, llm, file_only)
                elif c['Type'] == 'slack':
                    hist = _slack(tok, 'conversations.history', channel=s['Address'],
                                  oldest=since.timestamp(), limit=25)
                    msgs = [m for m in reversed(hist.get('messages', [])) if not m.get('subtype')]
                    # the channel's read cursor is ONE timestamp - the newest line we took
                    if read_it and msgs: mark_slack_read(tok, s['Address'], msgs[-1].get('ts'))
                    for m in msgs:
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
