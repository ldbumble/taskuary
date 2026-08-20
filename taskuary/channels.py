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
MAIL_SELECT = 'id,subject,from,receivedDateTime,sentDateTime,bodyPreview,body,conversationId,webLink,hasAttachments'


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
        elif c['Type'] == 'telegram':
            from .messengers import tg_test
            detail = tg_test(store, store.get_connector(c['ConnectorId'], with_secret=True))
        elif c['Type'] == 'whatsapp':
            from .messengers import wa_test
            detail = wa_test(store, store.get_connector(c['ConnectorId'], with_secret=True))
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


def ingest_teams_chats(store, upn: str, tok: str, since, llm=None, file_only=False) -> int:
    """Teams as an inbound channel: each chat is a conversation (so a thread keeps building
    ONE task, like a mail thread), each human message an item on the timeline. Bot posts,
    call-started events, deletions and empty bodies are not messages anybody has to act on."""
    since_iso, users, chats, n = _utc(since), {}, {}, 0
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
        common = {'external_id': f'teams:{cid}:{m["id"]}', 'channel': 'teams',
                  'subject': topic or (f'Teams chat with {name}' if kind == 'oneOnOne' else f'Teams {kind}'),
                  'body': body[:20000], 'conversation_id': f'teams:{cid}',
                  'sent_at': _local(m.get('createdDateTime') or ''), 'source_link': m.get('webUrl'),
                  'source_name': upn}
        if user['id'] == me:                       # your own chat lines are context, never work
            n += ingest_own_message(store, {**common, 'from_name': 'You', 'from_email': upn},
                                    'your message in this chat - kept for context')
            continue
        out = ingest_message(store, {**common, 'from_name': name, 'from_email': addr}, llm=llm, file_only=file_only)
        n += out['status'] != 'duplicate'
    return n


CH2SRC = {'outlook': 'email', 'teams': 'teams', 'slack': 'slack', 'github': 'github',
          'telegram': 'telegram', 'whatsapp': 'whatsapp'}
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


def _since(s, backfill_days: int = 0):
    """How far back to ask this source for. `backfill_days` WIDENS the window without moving the
    watermark - what the app does on startup, because whatever arrived while it was shut down was
    never polled by anyone, and 'since I last ran' is the wrong question after a weekend off."""
    last = (datetime.fromisoformat(s['LastPolledAt'].replace(' ', 'T')) if s.get('LastPolledAt')
            else datetime.now() - timedelta(days=1))
    return min(last, datetime.now() - timedelta(days=backfill_days)) if backfill_days else last


def poll_channels(store, backfill_days: int = 0) -> int:
    """Ingest new items for every connection the owner marked as a TRIGGER, through the
    same triage funnel (incl. the configured AI, if any). A connection without the trigger
    role is still usable by agents and reports - it just never creates work on its own.
    Failures land on the card. `backfill_days` reaches further back than the watermark - see
    _since; it is how startup catches up on mail that arrived while the app was closed."""
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
                            'conversation_id': m.get('conversationId'), 'sent_at': _local(m.get('receivedDateTime') or ''),
                            'source_link': m.get('webLink'), 'source_name': s['Address'],
                            'images': images_for_triage(store, atts)}, llm=llm)
                        n += out['status'] != 'duplicate'
                        if atts and out.get('message_id') and out['status'] != 'duplicate':
                            try: save_attachments(store, out['message_id'], atts, f"graph:{m['id']}")
                            except Exception as e: logger.warning(f"saving attachments for {m['id']} failed: {e}")
                elif c['Type'] == 'teams':
                    n += ingest_teams_chats(store, s['Address'], tok, since, llm, file_only)
                elif c['Type'] == 'github':
                    n += ingest_github_issues(store, s['Address'], tok, since, llm, file_only)
                elif c['Type'] in ('telegram', 'whatsapp'):
                    # one poll per CONNECTOR, not per source: both keep a cursor on the connector,
                    # and the sources are just filters over what arrives (see messengers)
                    from . import messengers
                    mine = [x for x in store.list_sources() if x['Channel'] == CH2SRC[c['Type']]]
                    if s['SourceId'] != mine[0]['SourceId']: continue
                    poll = messengers.poll_telegram if c['Type'] == 'telegram' else messengers.poll_whatsapp
                    n += poll(store, full, mine, llm, file_only)
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
