"""Channel connectors - the cards on the Connections tab: Outlook mail + Microsoft Teams
(Graph, app-only client credentials) and GitHub (fine-grained PAT). test_connector is a
live probe (token/chat-read/repo-discovery); poll_channels is the scheduled ingest that
funnels mail and chats through the same triage as everything else. Credentials left blank
fall back to AZURE_TENANT_ID / AZURE_CLIENT_ID / AZURE_CLIENT_SECRET env vars.
"""
import base64, contextlib, hashlib, json, math, os, queue, re, threading, time
from concurrent.futures import ThreadPoolExecutor
from html import unescape
from datetime import datetime, timedelta
import requests
from loguru import logger

from . import spawn
from .github import _h as gh_headers, list_accessible_repos
from .ingest import ingest_message, rev_id, seen_before
from .counsel import is_invite

GRAPH = 'https://graph.microsoft.com/v1.0'
MAIL_SELECT = ('id,subject,from,toRecipients,ccRecipients,receivedDateTime,sentDateTime,bodyPreview,body,'
               'conversationId,webLink,hasAttachments,isRead,inferenceClassification,flag')
# ...and the same thing without the one field that carries the weight. A folder page LISTS; the
# bodies come back afterwards (_mail_bodies) for the mail that survives the policy, so a flood
# sender's twenty thousand characters are never pulled across the wire for a row nobody opens.
MAIL_LIST_SELECT = ','.join(f for f in MAIL_SELECT.split(',') if f != 'body')
# ...and the field that says where the sender's own words END. uniqueBody is the part of the body
# unique to THIS message - the mailbox drawing the line that everything else has to guess at from
# text, which on a forwarded mail is what buried Ray's one-sentence ask (TQ-0665). It rides in the
# $select the bodies already come back on: no extra request, and never in a LISTING, where the whole
# point is to carry no weight.
MAIL_BODY_SELECT = 'id,body,uniqueBody'
MAIL_FULL_SELECT = MAIL_SELECT + ',uniqueBody'
BODY_BATCH = 20              # Graph's $batch ceiling


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
        elif c['Type'] == 'quickbooks':
            from .quickbooks import probe, connection
            detail = probe(connection(store, cid))
        elif c['Type'] == 'zoho_invoice':
            from .zoho import probe, connection
            detail = probe(connection(store, cid))
        elif c['Type'] == 'teller':
            from .teller import probe, connection
            detail = probe(connection(store, cid))
        elif c['Type'] == 'simplefin':
            from .simplefin import probe, connection
            detail = probe(connection(store, cid))
        elif c['Type'] == 'alchemy':
            from .alchemy import probe
            from .reports import _card
            detail = probe(_card(store, 'alchemy', 'api_key', cid))
        elif c['Type'] in ('coingecko', 'frankfurter', 'yahoo', 'sec_edgar', 'fred', 'screen',
                           'twelvedata', 'alphavantage', 'finnhub', 'polygon', 'tiingo', 'fmp'):
            # every market card probes the same way: one cheap real call, through markets.py's
            # probe_<type> - a keyless card (coingecko/frankfurter/yahoo/sec_edgar/fred/screen)
            # runs with whatever ConfigJson carries; a keyed one resolves its saved api_key first,
            # and a missing one surfaces _need's own "no <Card> API key saved" MarketError as-is
            from . import markets
            from .reports import _card
            detail = getattr(markets, f'probe_{c["Type"]}')(_card(store, c['Type'], 'api_key', cid))
        elif c['Type'] == 'alpaca':
            from . import markets
            from .reports import _card
            detail = markets.probe_alpaca(_card(store, 'alpaca', 'secret_key', cid))
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
            host = cfg.get('host')
            if not host: raise RuntimeError('no host set - enter the machine name (e.g. AZWEB01)')
            from .reports import winrm_argv
            argv, env = winrm_argv(host)
            p = spawn.run(argv, env=env, capture_output=True, text=True, encoding='utf-8',
                          errors='replace', timeout=60)
            if p.returncode != 0:
                raise RuntimeError((p.stderr or p.stdout or 'WinRM unreachable')[:400]
                                   + ' - if this is a box you RDP into, PS remoting may need enabling: '
                                     'run Enable-PSRemoting -Force on it once (elevated)')
            detail = f"remote run OK on {(p.stdout or '').strip() or host} (your Windows credentials)"
        elif c['Type'] == 'typesafe':
            # not llm.test_ai: that asks for a completion, and this model has no completions. One
            # real typed question is the only proof the key works.
            from . import jev
            got = jev.ask(c['Secret'] or '', 'A scheduled check ran and came back clean.',
                          {'ok': ('is this a clean result?', 'nothing is wrong in it')})
            detail = f"Jev answered: {got['ok'][1]:.2f} confident"
        elif c['Type'] in ('anthropic', 'openai', 'azure_openai', 'openrouter', 'ollama', 'meta'):
            from .llm import test_ai
            detail = test_ai(store, cid)
        elif c['Type'] == 'robinhood':
            from . import robinhood
            detail = robinhood.test(store, c)
        elif c['Type'] == 'sharepoint':
            from . import sharepoint
            detail = sharepoint.test(store, c)
        elif c['Type'] == 'google_sheets':
            from . import sheets
            detail = sheets.test(store, c)
        elif c['Type'] == 'knowledge':
            from . import knowledge
            detail = knowledge.test(store, c)
        elif c['Type'] in ('smb_file', 'sftp'):
            from . import files
            detail = files.test_smb(store, c) if c['Type'] == 'smb_file' else files.test_sftp(store, c)
        elif c['Type'] in ('gemini_stt', 'groq_stt', 'openai_stt', 'deepgram', 'elevenlabs_stt', 'stt_server', 'local_whisper'):
            from . import voice
            detail = voice.test(store, store.get_connector(cid, with_secret=True))   # a second of silence through the real endpoint
        elif c['Type'] in ('openai_image', 'azure_openai_image', 'xai_image', 'image_server',
                           'gemini_image', 'stability_image', 'openrouter_image', 'replicate_image'):
            from . import images
            detail = images.test(store, store.get_connector(cid, with_secret=True))  # one small square through the real endpoint
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
        # ...and a failure that is only a missing package carries the package, so the card offers
        # Install rather than a pip command the owner has to take somewhere else (deps.py)
        if getattr(e, 'package', None):
            from . import deps
            can, why = deps.can_install()
            out['install'] = {'package': e.package, 'name': deps.pip_name(e.package), 'can': can, 'why': why}
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

def _own(m):
    """What the sender typed THIS time, as the mailbox marks it (uniqueBody) - or '' when it is not
    worth believing. Graph sometimes hands back the whole conversation here instead of the new part
    (microsoftgraph/msgraph-sdk-php#1576), so it is kept only when it is genuinely SHORTER than the
    body it came from; anything else and triage.split_own finds the cut for itself, as it does for
    IMAP, chat and every channel that has no such field."""
    own = _clean((m.get('uniqueBody') or {}).get('content'))[:20000]
    return own if own and len(own) < len(_body(m)) else ''

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


def mail_folders(tok, upn) -> list:
    """The mailbox's folders, for the card's chooser: id + name, the well-known ones first. Only the
    Inbox was ever read; a rule that files vendor mail into 'Vendors' made that mail invisible here."""
    r = requests.get(f'{GRAPH}/users/{upn}/mailFolders', headers={'Authorization': f'Bearer {tok}'}, timeout=30,
                     params={'$top': 100, '$select': 'id,displayName,totalItemCount,wellKnownName'})
    r.raise_for_status()
    skip = {'sentitems', 'deleteditems', 'drafts', 'junkemail', 'outbox', 'conversationhistory', 'syncissues', 'recoverableitemsdeletions'}
    out = []
    for f in r.json().get('value', []):
        wk = (f.get('wellKnownName') or '').lower()
        if wk in skip: continue
        out.append({'id': 'inbox' if wk == 'inbox' else f['id'], 'name': f.get('displayName') or '', 'count': f.get('totalItemCount') or 0, 'well_known': wk})
    out.sort(key=lambda f: (f['id'] != 'inbox', f['name'].lower()))
    return out


def source_folders(s: dict) -> list:
    """Which folders a mailbox source reads - its ConfigJson `folders`, default the Inbox alone."""
    try: fs = json.loads(s.get('ConfigJson') or '{}').get('folders') or []
    except ValueError: fs = []
    return [f for f in fs if f] or ['inbox']


MAIL_BATCH = 500   # one _mail_msgs call; _mail_folder keeps asking until a short batch comes back


def _mail_msgs(tok, upn, since, folder='inbox', cap=MAIL_BATCH, inclusive=False,
               through=None, continuation=None, with_continuation=False):
    """One batch of a folder, OLDEST first: at most `cap` messages received after `since` - or from
    it, with inclusive=True, which is how a failed continuation safely replays its boundary second
    (dedupe drops the repeats). Graph continuation URLs are opaque and are followed verbatim."""
    # folder-scoped - a bare /messages spans every folder including Sent Items, which made
    # the owner's own replies come back through the funnel as inbound work.
    # ...and PAGED: one page of the 25 newest, then a watermark stamped 'now', meant the
    # 26th-newest mail in the window was never asked for again - a busy shared mailbox lost
    # mail every poll with nothing in any log (audit 2026-09-02). Newest-first with a cap had
    # the same hole one size up: the 501st-newest mail of a long absence was never fetched
    # once the watermark moved (PW-006) - so the batch is the OLDEST, and the caller continues.
    url = continuation or f'{GRAPH}/users/{upn}/mailFolders/{folder}/messages'
    bounds = f"receivedDateTime {'ge' if inclusive else 'gt'} {since}"
    if through: bounds += f' and receivedDateTime le {through}'
    params, out = (None if continuation else {
        '$top': 50, '$orderby': 'receivedDateTime asc', '$select': MAIL_LIST_SELECT, '$filter': bounds
    }), []
    seen_urls = set()
    while url and len(out) < cap:
        if url in seen_urls:
            raise RuntimeError(f'Graph repeated mail continuation for {folder}')
        seen_urls.add(url)
        r = requests.get(url, headers={'Authorization': f'Bearer {tok}'}, timeout=30, params=params)
        r.raise_for_status(); j = r.json()
        page = j.get('value') or []
        out += page
        url, params = j.get('@odata.nextLink'), None       # the nextLink carries the filter itself
    if url in seen_urls:
        raise RuntimeError(f'Graph repeated mail continuation for {folder}')
    # A provider page is indivisible: short pages can leave us just below cap before the next
    # full page. Durable callers keep that bounded one-page overshoot and its exact nextLink;
    # the historical list-only helper retains its advertised hard view cap.
    return (out, url) if with_continuation else out[:cap]


def _mail_bodies(tok: str, upn: str, ids: list) -> list:
    """The bodies for mail already listed, twenty at a time through Graph's $batch. A failed
    sub-request is simply a message with no body - _body falls back to the preview the listing
    already carried, which is what the old single-request page would have given a stripped mail."""
    out = []
    for i in range(0, len(ids), BODY_BATCH):
        chunk = ids[i:i + BODY_BATCH]
        r = requests.post(f'{GRAPH}/$batch', timeout=60, headers={'Authorization': f'Bearer {tok}'},
                          json={'requests': [{'id': str(k), 'method': 'GET',
                                              'url': f'/users/{upn}/messages/{x}?$select={MAIL_BODY_SELECT}'}
                                             for k, x in enumerate(chunk)]})
        r.raise_for_status()
        for resp in r.json().get('responses') or []:
            body = resp.get('body')
            if resp.get('status') == 200 and isinstance(body, dict) and body.get('id'): out.append(body)
            else: logger.debug(f"mail body {resp.get('id')} came back {resp.get('status')}")
    return out


def _hydrate(tok: str, upn: str, drop=None):
    """Fill a listed page back in - only what is actually MISSING, like chains completes a thread.
    `drop(m)` names the mail a policy throws away on its envelope alone: that mail keeps the
    255-char preview as its body and costs no request at all."""
    def go(batch):
        want = [m['id'] for m in batch if 'body' not in m and not (drop and drop(m))]
        if not want: return batch
        got = {b['id']: b for b in _mail_bodies(tok, upn, want)}
        return [{**m, **got.get(m['id'], {})} for m in batch]
    return go


def _envelope(m: dict) -> dict:
    """What a bodyless policy rule reads: who sent it, what it is called, and the preview Graph
    hands out free with the listing (a keyword found there is found in the full body too)."""
    frm = (m.get('from') or {}).get('emailAddress') or {}
    return {'from_email': frm.get('address'), 'subject': m.get('subject'), 'body': m.get('bodyPreview')}


_MAIL_MSGS_IMPLEMENTATION = _mail_msgs


def _mail_cursor(s: dict) -> dict:
    """Where each folder's last read stopped short: {folder: receivedDateTime} in the source's ConfigJson."""
    try: cur = json.loads(s.get('ConfigJson') or '{}').get('mail_cursor') or {}
    except ValueError: cur = {}
    return dict(cur) if isinstance(cur, dict) else {}


def _mail_config(s: dict) -> dict:
    try: cfg = json.loads(s.get('ConfigJson') or '{}')
    except ValueError: return {}
    return cfg if isinstance(cfg, dict) else {}


def _mail_identity(s: dict) -> dict:
    cfg = _mail_config(s)
    return {key: s.get(key) for key in ('LastPolledAt', 'Address', 'ConnectorId', 'Active', 'Channel')} | {
        'folders': cfg.get('folders')}


def _mail_cutoff() -> str:
    return _utc(datetime.now().astimezone())


class _MailSourceChanged(RuntimeError):
    pass


def _mail_progress(s: dict, requested_since: str = None) -> tuple[dict, dict]:
    """Bound continuation state, or empty state when an owner/source edit made it stale."""
    cfg = _mail_config(s)
    cursor = cfg.get('mail_cursor') or {}
    basis = cfg.get('mail_cursor_basis') or {}
    try:
        saved_since = datetime.fromisoformat(str(basis.get('since') or '').replace('Z', '+00:00'))
        wanted_since = datetime.fromisoformat(str(requested_since or basis.get('since') or '').replace('Z', '+00:00'))
        saved_through = datetime.fromisoformat(str(basis.get('through') or '').replace('Z', '+00:00'))
        covers_requested_floor = saved_since <= wanted_since and saved_since <= saved_through
    except (TypeError, ValueError):
        covers_requested_floor = False
    valid = (isinstance(cursor, dict)
             and all(isinstance(k, str) and isinstance(v, str) for k, v in cursor.items())
             and isinstance(basis, dict)
             and all(basis.get(key) == value for key, value in _mail_identity(s).items())
             and covers_requested_floor
             and isinstance(basis.get('through'), str) and bool(basis['through']))
    if not valid: return {}, {}
    return dict(cursor), dict(basis)


def _mail_folder(tok, s: dict, folder: str, since_iso: str, through: str,
                 cursor: dict, handle, save, hydrate=None) -> int:
    """Drain one folder oldest-first, batch by batch, until a short batch says it is exhausted.

    handle(m) takes each message not yet seen this poll and returns what it added. Between
    batches the folder's half-way point is kept in cursor[folder] (and saved through `save`),
    so a fetch that dies resumes from there instead of re-downloading - and the source's
    watermark, which the caller moves only when every folder finished, never steps over mail
    nobody fetched. Within a run, batches follow Graph's opaque continuation URL. After a failed
    run, the saved timestamp is replayed inclusively; no returned-row count is treated as Graph's
    provider cursor."""
    since = cursor.get(folder) or since_iso
    inclusive = folder in cursor
    continuation, used_continuations, seen, n = None, set(), set(), 0
    while True:
        if continuation:
            if continuation in used_continuations:
                raise RuntimeError(f'Graph repeated mail continuation for {folder}')
            used_continuations.add(continuation)
        try:
            result = _mail_msgs(
                tok, s['Address'], since, folder=folder, cap=MAIL_BATCH, through=through,
                **({'inclusive': True} if inclusive else {}), continuation=continuation,
                with_continuation=True)
        except TypeError as exc:
            # Keep the small historical fake-store protocol used by embedders/tests. The real
            # implementation above accepts the frozen bounds and opaque continuation contract.
            if _mail_msgs is _MAIL_MSGS_IMPLEMENTATION or 'unexpected keyword argument' not in str(exc):
                raise
            result = (_mail_msgs(tok, s['Address'], since, folder=folder), None)
        batch, continuation = result if isinstance(result, tuple) else (result, None)
        fresh = [m for m in batch if m['id'] not in seen]
        # the page's bodies, fetched once for the whole batch - never one request per message
        if hydrate and fresh: fresh = hydrate(fresh)
        for m in fresh:
            seen.add(m['id']); n += handle(m)
        if not continuation: break
        if not batch:
            raise RuntimeError(f'Graph mail continuation made no progress for {folder}')
        # This is a safe replay boundary, not a reconstructed Graph cursor. The current run
        # follows `continuation`; a retry asks inclusively from this timestamp and dedupes.
        since, inclusive = batch[-1]['receivedDateTime'], True
        cursor[folder] = since
        save()
    cursor.pop(folder, None); save()
    return n


# where the owner actually typed it - the timeline entry says so, because "you replied" with no
# place is the one thing the owner cannot check against their own memory
SENT_FROM = {'email': 'from your mailbox', 'teams': 'in Teams', 'slack': 'in Slack',
             'whatsapp': 'in WhatsApp', 'telegram': 'in Telegram', 'imessage': 'in Messages'}


def _same_words(a: str, b: str, n: int = 160) -> bool:
    """Two renderings of the SAME reply. The copy that comes back from the Sent folder went out
    through the provider's HTML and back through our stripper, so it is never byte-identical to
    the text approved here - the opening words are what survive both, and the quoted thread the
    provider appends is what makes a prefix the only honest comparison."""
    x, y = (re.sub(r'\s+', ' ', a or '').strip().lower()[:n], re.sub(r'\s+', ' ', b or '').strip().lower()[:n])
    return bool(x) and x == y


def retire_draft_answered_elsewhere(store, tid: int | None, sent: dict) -> list:
    """Resolve reply drafts made obsolete by a reply the owner sent in the native app.

    A provider sync can land well after triage wrote its draft.  The draft belongs to the
    inbound message it was written against, so an owner line later on that same conversation
    is the missing verdict: the reply already went out.  Action approvals are deliberately
    excluded -- sending a chat line cannot approve an unrelated proposed action.
    """
    conv, sent_at = sent.get('ConversationId'), sent.get('SentAt')
    if not conv or not sent_at:
        return []
    stale = [rv for rv in store.list_reviews('pending')
             if rv.get('TaskId') == tid and rv.get('Kind') != 'action'
             and rv.get('ConversationId') == conv
             and (not rv.get('SentAt') or rv['SentAt'] <= sent_at)]
    if not stale:
        return []

    place = SENT_FROM.get(sent.get('Channel'), 'outside Taskuary')
    for rv in stale:
        store.decide_review(rv['ReviewId'], 'superseded', None, 'you',
                            f'The owner replied {place}; this draft was not sent.')

    # Treat this exactly like a successful send through Review.  Reply-only work closes, while
    # owner-controlled work and a task whose coding agent is still running keep their safeguards.
    if tid:
        from . import verdicts
        verdicts._settle_task_after_sent_reply(store, stale[0], 'you', True)

    task = store.get_task(tid) if tid else {}
    body = re.sub(r'\s+', ' ', sent.get('BodyText') or '').strip()
    excerpt = f': "{body[:180]}"' if body else ''
    if not tid:
        subject = (store.get_message(stale[0].get('MessageId')) or {}).get('Subject') or 'this thread'
        where = subject
        state = ''
    else:
        where = f'TQ-{tid:04d}'
        state = ' The task is still open because it has other work in progress.' \
            if task.get('Status') not in ('done', 'dropped') else ' I marked the task done.'
    from . import concierge, funnel, general
    concierge.record(store, general.dock_task(store)[0]['TaskId'], 'assistant',
                     f'You replied {place} on {where}{excerpt}. '
                     f'I removed the unused draft; the reply was taken care of.{state}')
    funnel.invalidate()
    # The review transition already wakes the UI, but this final wake happens after the durable
    # Assistant line was written, avoiding a race where an open chat fetched one write too early.
    store._poke('feed-changed', 'task-changed', task_id=tid)
    return stale


def ingest_own_message(store, msg: dict, why: str, keep_unmatched: bool = True) -> int:
    """Anything YOU sent - a mail reply, a line in a chat - never gets its own timeline row and
    never becomes work: it rides INSIDE the thread as a 'context' message, which is what the
    Timeline reads to say "you answered this yourself" (store.ANSWERED_AT, timelineState).

    It is kept whether or not a task claims it, and that is the fix for the commonest ending
    there is: you answer a mail in Outlook that Taskuary filed, or one whose task closed
    yesterday. The router only ever matched OPEN tasks, so both of those replies were dropped on
    the floor - the row kept saying nothing had happened, forever (owner, 2026-09-02)."""
    if store.message_exists(msg['external_id']): return 0
    conv = msg.get('conversation_id')
    tid = (next((s['task_id'] for s in store.snapshots() if conv and conv in s['conversation_ids']), None)
           or store.task_for_conversation(conv, msg.get('subject')))
    if not tid and not keep_unmatched: return 0
    mid = store.add_message({'TaskId': tid, 'ExternalId': msg['external_id'], 'ConversationId': conv,
                             'Channel': msg['channel'], 'SourceName': msg.get('source_name'),
                             'Subject': msg.get('subject'), 'FromName': 'You', 'FromEmail': msg.get('from_email'),
                             'SentAt': msg.get('sent_at'), 'BodyText': msg.get('body'),
                             'OwnText': msg.get('own_text') or None,
                             'SourceLink': msg.get('source_link'), 'Status': 'context',
                             'MailMetaJson': json.dumps(msg.get('mail_meta')) if msg.get('mail_meta') else None})
    sent = store.get_message(mid) or {}
    retire_draft_answered_elsewhere(store, tid, sent)
    if not tid: return 1
    store.add_route(mid, tid, 'attach', None, why, [], 'router')
    # ...unless Taskuary is reading back its OWN send. That reply already has its line on the
    # timeline ("Sent by email to ..."), and a second entry under it saying "You replied" read as
    # the owner having answered twice.
    rv = store.sent_reply(task_id=tid) or {}
    body = (msg.get('body') or '').strip()
    if not _same_words(body, rv.get('FinalText') or rv.get('DraftText') or ''):
        store.add_comment(tid, 'you', 'human',
                          f"You replied {SENT_FROM.get(msg['channel'], 'outside Taskuary')}: {body[:300]}")
    return 1


def ingest_outbound_mail(store, mailbox: str, m: dict) -> int:
    return ingest_own_message(store, {
        'external_id': f"graph:{m['id']}", 'channel': 'email', 'source_name': mailbox,
        'subject': m.get('subject'), 'from_email': mailbox, 'body': _body(m), 'own_text': _own(m),
        'conversation_id': m.get('conversationId'), 'source_link': m.get('webLink'),
        'sent_at': _local(m.get('receivedDateTime') or m.get('sentDateTime') or ''),
        'mail_meta': {'folder': 'sentitems', 'focus': m.get('inferenceClassification'),
                      'flag': (m.get('flag') or {}).get('flagStatus'), 'invite': is_invite(m)}},
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
    from urllib.parse import urlparse
    for i, url in enumerate(dict.fromkeys(_HOSTED.findall(html or '')).keys()):
        if i >= cap: break
        # the token goes to Graph and nowhere else: any chat participant can put an <img> with
        # their own host in a message body, and the fetch used to hand them the bearer (audit 2026-09-02)
        if (urlparse(unescape(url)).hostname or '').lower() != 'graph.microsoft.com': continue
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
        # Deleted at the source. Teams' delta reports it (mail's plain $top list does not, so
        # the mailbox side of this needs a delta migration before it can say the same). If we
        # already carry the row, say so on it rather than leaving a message on the Timeline that
        # no longer exists in the chat - and never remove it: work may hang off it.
        if m.get('deletedDateTime'):
            cid_d = m.get('chatId') or ''
            if cid_d: store.withdraw_message(f'teams:{cid_d}:{m["id"]}')
            continue
        if m.get('messageType') != 'message' or not user.get('id') or not body: continue
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
                                    'your message in this chat - kept for context', keep_unmatched=True)
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
# what the cap is for). The Connections card warns before switching a PUBLIC repo on.
GH_TEAM = ('OWNER', 'MEMBER', 'COLLABORATOR')
GH_AUTO = {'off': (), 'team': GH_TEAM, 'contributors': GH_TEAM + ('CONTRIBUTOR',), 'anyone': None}


def gh_auto_ok(src: dict, association: str) -> bool:
    try: mode = json.loads((src or {}).get('ConfigJson') or '{}').get('auto') or 'off'
    except ValueError: mode = 'off'
    allowed = GH_AUTO.get(mode, ())
    return allowed is None or (association or 'NONE').upper() in allowed


def file_as_context(store, msg: dict, why: str) -> int:
    """A tracker line nobody has to act on, kept as thread history under its OWN name.

    ingest_own_message is for what YOU sent and stamps the row 'You' - which would put the
    owner's name on a coverage bot's comment. A robot is not the owner; it is just not work."""
    if store.message_exists(msg['external_id']): return 0
    conv = msg.get('conversation_id')
    tid = store.task_for_conversation(conv, msg.get('subject'))
    mid = store.add_message({'TaskId': tid, 'ExternalId': msg['external_id'], 'ConversationId': conv,
                             'Channel': msg['channel'], 'SourceName': msg.get('source_name'),
                             'Subject': msg.get('subject'), 'FromName': msg.get('from_name'),
                             'FromEmail': msg.get('from_email'), 'SentAt': msg.get('sent_at'),
                             'BodyText': msg.get('body'), 'SourceLink': msg.get('source_link'),
                             'Status': 'context'})
    if tid: store.add_route(mid, tid, 'attach', None, why, [], 'router')
    return 1


def gh_login(store, tok: str) -> str:
    """The login this token acts as, cached. Needed to tell Taskuary's OWN comments from a
    person's: the hub posts on issues itself (outbound.comment_issue), so without this it reads
    its own reply on the next poll, triages it, and can answer itself."""
    me = str(store.get_settings().get('github_login') or '')
    if me: return me
    from . import github
    try: me = github.whoami(tok)
    except Exception as e:
        logger.warning(f'github: could not read our own login ({e}) - own comments may read as a stranger')
        return ''
    if me: store.set_setting('github_login', me, 'github')
    return me


def close_upstream_ended(store, tid: int, said: str, final: str):
    """Close a task whose upstream item is over - through the NORMAL ending, not a status flip.

    wrap() is the same call the Done button makes: the report is written, the transcript becomes
    an artifact, proposals become reviews and the sender gets their drafted reply. The cause
    rides in as the LAST MESSAGE, so the task says what ended it in the place every other ending
    is recorded. A task that never had a session has nothing to wrap ('nothing to wrap up') -
    that refusal is expected, and must not leave the dead task sitting in the work list."""
    from . import coder
    store.add_comment(tid, 'router', 'agent', said)
    try:
        coder.wrap(store, tid, close=True, actor='router', final_message=final)
    except ValueError as e:
        logger.info(f'TQ-{tid:04d}: nothing to wrap up ({e}) - closing it plainly')
        store.update_task(tid, {'Status': 'done'}, 'router')
    except Exception as e:
        logger.warning(f'TQ-{tid:04d}: the ending failed ({e}) - closing it plainly')
        store.update_task(tid, {'Status': 'done'}, 'router')


def _gh_ended(store, item: dict, base: str, repo: str) -> int:
    """The item this task came from is over - it was closed or merged upstream.

    The work is moot whatever state the task is in, so it leaves the work list rather than
    waiting for somebody to notice (the owner: the work tab holds only LIVE work). The cause is
    said on the task, because a task that closes itself and does not say why is worse than one
    that stayed open. Deliberately deterministic: no model is asked to infer an ending from a
    fact GitHub stated outright."""
    tid = store.task_for_conversation(base)
    if not tid: return 0
    t = store.get_task(tid) or {}
    if t.get('Status') in ('done', 'dropped'): return 0
    what = 'merged' if item.get('merged_at') else 'closed'
    kind = 'pull request' if 'pull_request' in item else 'issue'
    said = (f"The {kind} this task came from was {what} on GitHub "
            f"({repo}#{item['number']}), so there is nothing left to do here.")
    close_upstream_ended(store, tid, said, f'{repo}#{item["number"]} was {what} on GitHub - {said}')
    logger.info(f'github: {base} was {what} - closed TQ-{tid:04d}')
    return 0


def _gh_comments(store, src: dict, tok: str, repo: str, item: dict, base: str, llm, file_only: bool) -> int:
    """Comments on one issue or PR, as messages on the ITEM's conversation - which is what makes
    identity_route attach them to its task, re-judge them and rewrite a draft that is now behind.

    Ours and a bot's ride along as history and never become work: CI, Dependabot and coverage
    bots are the loudest commenters on any active repo and none of it is a person asking."""
    from . import github
    try: comments = github.issue_comments(tok, repo, item['number'])
    except Exception as e:
        logger.warning(f"github: comments on {base} could not be read ({e})")
        return 0
    me, n = gh_login(store, tok), 0
    for c in comments:
        u = c.get('user') or {}
        who, ext = u.get('login') or 'github', f"{base}:c{c.get('id')}"
        if store.message_exists(ext): continue
        msg = {'external_id': ext, 'channel': 'github', 'subject': f"Re: {item.get('title') or base}",
               'body': (c.get('body') or '')[:20000], 'from_name': who,
               'from_email': f'{who}@users.noreply.github.com', 'conversation_id': base,
               'sent_at': _local(c.get('created_at') or ''), 'source_link': c.get('html_url'),
               'source_name': repo, 'no_auto': not gh_auto_ok(src, c.get('author_association'))}
        if me and who == me:
            n += ingest_own_message(store, msg, f'our own comment on {base} - history, not work')
            continue
        if (u.get('type') or '') == 'Bot':
            n += file_as_context(store, msg, f'{who} is a bot - history, not work')
            continue
        n += ingest_message(store, msg, llm=llm, file_only=file_only)['status'] != 'duplicate'
    return n


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
    from . import github
    body_images, list_items = github.body_images, github.list_items
    # state='all', because a CLOSURE IS SILENCE. With state='open' an item that closes simply
    # stops being returned - there is no event, and the task it opened sat in the work list for
    # good (the owner, 2026-09-15, on the closed PR behind TQ-0550). Asking for all of them is
    # what makes the ending arrive; _gh_ended below is what acts on it.
    for i in reversed(list_items(tok, repo, since=since.astimezone().isoformat(), state='all')):
        if TQ_ISSUE.match(i.get('title') or ''): continue
        is_pr = 'pull_request' in i
        mode = prs_mode if is_pr else issues_mode
        if mode == 'off': continue
        who = (i.get('user') or {}).get('login') or 'github'
        # WHO is asking is part of the ask on a public repo - triage reads this line first
        head = f"[{'pull request' if is_pr else 'issue'} by {who} - association: {i.get('author_association') or 'NONE'}]"
        base = f"gh:{repo}#{i['number']}"
        subject = f"{repo}#{i['number']} {i.get('title') or ''}".strip()
        body = f"{head}\n{(i.get('body') or '(no description)')[:20000]}"
        known = store.message_by_external(base) or store.task_for_conversation(base)
        if (i.get('state') or 'open') != 'open':
            # an ending we never saw begin is history: a backfill reaches items closed long
            # before Taskuary existed, and none of those is a job for anybody
            if known: n += _gh_ended(store, i, base, repo)
            continue
        # a robot filing its own chore (a downloads chart, a dependency bump) is not somebody
        # asking the owner for something - the same rule its comments get
        if ((i.get('user') or {}).get('type') or '') == 'Bot':
            n += file_as_context(store, {
                'external_id': base, 'channel': 'github', 'conversation_id': base, 'subject': subject,
                'body': body, 'from_name': who, 'from_email': f'{who}@users.noreply.github.com',
                'sent_at': _local(i.get('updated_at') or ''), 'source_link': i.get('html_url'),
                'source_name': repo}, f'{who} is a bot - history, not work')
            continue
        # the conversation on the item is where "what changed" usually lives; the body is only
        # what somebody meant to say the day they filed it
        n += _gh_comments(store, src, tok, repo, i, base, llm, mode == 'feed')
        if seen_before(store, base, subject, body): continue
        out = ingest_message(store, {
            'external_id': rev_id(base, subject, body), 'channel': 'github',
            'subject': subject, 'body': body,
            'from_name': who, 'from_email': f'{who}@users.noreply.github.com',
            'conversation_id': base, 'sent_at': _local(i.get('updated_at') or ''),
            'source_link': i.get('html_url'), 'source_name': repo,
            # the screenshot IS the report: read it before the row exists, or the classifier
            # judges an issue template whose headings are empty (see images_for_triage above)
            'images': (body_images(tok, i.get('body') or '')
                       if str(store.get_settings().get('vision_enabled') or '1') == '1' else []),
            'no_auto': not gh_auto_ok(src, i.get('author_association'))},
            llm=llm, file_only=mode == 'feed')
        n += out['status'] != 'duplicate'
    return n


def _repo_error(e) -> str:
    """A poll failure in words the owner can act on. A 404 is not a hiccup to retry: the repo was
    renamed, deleted, or the token stopped being able to see it, and only a person can fix that."""
    text = str(e)
    if '404' in text or 'Not Found' in text:
        return 'no such repository - it was renamed or deleted, or this token cannot see it'
    if '403' in text or 'rate limit' in text.lower(): return 'GitHub refused the read (permissions or rate limit)'
    return text[:160]


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
# The same hedge at startup scale. A watermark that jumped to `now` while the mail behind it was
# still eventually-consistent hides that mail for good (the Richard Lowe case above), and a
# shutdown is exactly when nobody is polling to catch it. So the catch-up reaches back PAST the
# watermark - but by this, not by a rounded-up day: asking for 24h after 8.75h closed pulled 272
# messages the database already had, to keep 93 (the owner's mailbox, 2026-09-17).
STARTUP_OVERLAP = timedelta(hours=1)


def _since(s, backfill_hours: float = 0):
    """How far back to ask this source for. `backfill_hours` WIDENS the window without moving the
    watermark - what the app does on startup, because whatever arrived while it was shut down was
    never polled by anyone, and 'since I last ran' is the wrong question after a weekend off."""
    last = (datetime.fromisoformat(s['LastPolledAt'].replace(' ', 'T')) - POLL_OVERLAP
            if s.get('LastPolledAt') else datetime.now() - timedelta(days=1))
    return min(last, datetime.now() - timedelta(hours=backfill_hours)) if backfill_hours else last


class _Writer:
    """One thread talks to SQLite; connector polls wait on HTTP in others.

    WAL still wants a single writer. Outlook vs Slack vs GitHub waits do not share a
    conversation, so they overlap. Every store call from a worker hops onto this thread
    and waits. Drain stays on the poll thread, after this closes, and is still sequential.
    """
    def __init__(self, store):
        self._store = store
        self._q = queue.Queue()
        self._t = threading.Thread(target=self._loop, daemon=True, name='taskuary-sqlite')
        self._t.start()
        self.ident = self._t.ident

    def _loop(self):
        while True:
            item = self._q.get()
            if item is None: return
            name, args, kwargs, box, ev = item
            try:
                box['r'] = args[0]() if name == '__fn__' else getattr(self._store, name)(*args, **kwargs)
            except Exception as e:
                box['e'] = e
            finally:
                ev.set()

    def do(self, fn):
        box, ev = {}, threading.Event()
        self._q.put(('__fn__', (fn,), {}, box, ev))
        ev.wait()
        if 'e' in box: raise box['e']
        return box.get('r')

    def __getattr__(self, name):
        attr = getattr(self._store, name)
        if not callable(attr): return attr
        def call(*a, **k):
            box, ev = {}, threading.Event()
            self._q.put((name, a, k, box, ev))
            ev.wait()
            if 'e' in box: raise box['e']
            return box.get('r')
        return call

    def close(self):
        self._q.put(None)
        self._t.join(timeout=30)


def _poll_jobs(store, only=None):
    from .store import roles_of
    jobs = []
    for c in store.list_connectors():
        if not c['Active'] or c['Type'] not in CH2SRC: continue
        if only is not None and c['Type'] not in only: continue
        roles = roles_of(c)
        # trigger = becomes work; feed = shows on the timeline and stops there; neither = never
        # polled - EXCEPT github, where the per-repo issue/PR pickers carry the intent: two
        # switches where one reads as enough was a trap (a repo set to "PRs: tasks" on a
        # tool-only card, a Sync that pulled nothing, and no error anywhere).
        from . import remote_assistant
        phone_guide = remote_assistant.polls(store, c)      # the card carries the Assistant chat: read it regardless
        if (not roles & {'trigger', 'feed'} and not phone_guide
                and not (c['Type'] == 'github' and _gh_explicit(store))
                and not (c['Type'] in CLOUD and _cloud_explicit(store, CH2SRC[c['Type']]))): continue
        jobs.append((c, 'trigger' not in roles))
    return jobs


def _poll_one(store, c, file_only, backfill_hours, llm, read_it) -> int:
    """One connector. HTTP lives here; store writes go through whatever store was handed
    (the writer thread when polls overlap). Messages of one conversation still land in
    arrival order because a connector is one worker."""
    n, errors = 0, []      # errors: folders a mailbox could not finish - the card shows them, the poll goes on
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
            since = _since(mine[0] if mine else {}, backfill_hours)
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
            return n
        for s in store.list_sources():
            if s['Channel'] != CH2SRC[c['Type']]: continue
            # a source belongs to ONE connector: outlook and an IMAP mailbox are both
            # channel 'email', and without this the Graph poller tried the Gmail address.
            # (Orphans are adopted at startup, so ownership is always present now.)
            if s.get('ConnectorId') and s['ConnectorId'] != c['ConnectorId']: continue
            since = _since(s, backfill_hours)
            if c['Type'] == 'outlook':
                since_iso = since.astimezone().isoformat()
                identity = _mail_identity(s)
                cursor, basis = _mail_progress(s, since_iso)
                if basis:
                    cycle_since, through = basis['since'], basis['through']
                else:
                    cycle_since, through = since_iso, _mail_cutoff()
                    basis = {**identity, 'since': cycle_since, 'through': through}
                expect_fields = {key: identity[key]
                                 for key in ('LastPolledAt', 'Address', 'ConnectorId', 'Active', 'Channel')}
                expect_config = {'folders': identity['folders']}
                def save():
                    config_set = {'mail_cursor_basis': dict(basis)}
                    config_remove = ['mail_cursor_skip', 'mail_cursor_marker']
                    if cursor: config_set['mail_cursor'] = dict(cursor)
                    else: config_remove.append('mail_cursor')
                    if not store.patch_source_poll_state(
                            s['SourceId'], config_set=config_set, config_remove=tuple(config_remove),
                            expect_fields=expect_fields, expect_config=expect_config):
                        raise _MailSourceChanged('source changed while Outlook catch-up was running')
                history_pending = {}
                def inbound(folder):
                    def take(m) -> int:
                        frm = (m.get('from') or {}).get('emailAddress') or {}
                        if (frm.get('address') or '').lower() == s['Address'].lower():
                            return 0   # the mailbox's own mail (moved copies, self-sends) is never inbound work
                        # a thread whose history was never completed here (new, stored before this feature, or a failed
                        # attempt) is completed from the provider after the new mail lands - listed first, only the
                        # missing bodies fetched, and never again once complete (chains.py, PW-009/010)
                        from . import chains   # chains imports this module; the loop stays one-way at import time
                        conv = m.get('conversationId')
                        fresh_thread = bool(conv) and chains.needs_history(store, conv, s['Address'])
                        # the screenshot IS the ask in a "see below" mail, so it is fetched BEFORE
                        # triage and handed to it - then saved once the message row exists.
                        # ...but only for mail we do not already have. The overlap window is re-read on
                        # purpose and ingest_message drops a repeat on its first line - with this fetch
                        # sitting ABOVE that line, every re-read mail pulled its attachments over the wire
                        # again to discard them: 32.7 MB of P&L spreadsheets on one startup, base64'd to
                        # ~43 MB, which WAS the catch-up (the owner's mailbox, 2026-09-17). message_exists
                        # is the same indexed question ingest asks, and costs nothing to ask here first.
                        atts = []
                        if m.get('hasAttachments') and not store.message_exists(f"graph:{m['id']}"):
                            try: atts = mail_attachments(tok, s['Address'], m['id'])
                            except Exception as e: logger.warning(f"attachments for {m['id']} failed: {e}")
                        out = ingest_message(store, file_only=file_only, msg={
                            'external_id': f"graph:{m['id']}", 'channel': 'email',
                            'subject': m.get('subject'), 'body': _body(m), 'own_text': _own(m),
                            'from_name': frm.get('name'), 'from_email': frm.get('address'),
                            'to': _addrs(m.get('toRecipients')), 'cc': _addrs(m.get('ccRecipients')),
                            'conversation_id': m.get('conversationId'), 'sent_at': _local(m.get('receivedDateTime') or ''),
                            'source_link': m.get('webLink'), 'source_name': s['Address'],
                            'images': images_for_triage(store, atts), 'invite': is_invite(m),
                            'mail_meta': {'folder': folder, 'focus': m.get('inferenceClassification'),
                                          'flag': (m.get('flag') or {}).get('flagStatus'),
                                          'invite': is_invite(m)}}, llm=llm)
                        if atts and out.get('message_id') and out['status'] != 'duplicate':
                            try: save_attachments(store, out['message_id'], atts, f"graph:{m['id']}")
                            except Exception as e: logger.warning(f"saving attachments for {m['id']} failed: {e}")
                        # a duplicate is still mail the hub has read - the flag may just be
                        # older than the switch, and skipping it would strand those bold rows
                        if read_it and not m.get('isRead'): mark_mail_read(tok, s['Address'], m['id'])
                        # ...but only for mail that STAYED. A skip policy's mail is never shown, so the
                        # chain behind it is never read either - and a shared log mailbox is one dead
                        # conversation per message: a 3-day catch-up bought 634 history calls that each
                        # listed the one message we already had and added nothing (3.5 of its 13 minutes).
                        if fresh_thread and out['status'] not in ('skipped', 'ignored', 'duplicate'):
                            # Another configured folder may still own older messages in this
                            # conversation. History must wait for every intake folder to finish.
                            before = _local(m.get('receivedDateTime') or '')
                            history_pending[conv] = max(history_pending.get(conv, ''), before)
                        return int(out['status'] != 'duplicate')
                    return take
                # your replies ride along as CONTEXT: attached to the thread's task, visible on the
                # timeline, never triaged into work - then every folder the source asks for (the Inbox
                # alone unless the card says otherwise), each oldest first and read to the end
                folders = [('sentitems', lambda m: ingest_outbound_mail(store, s['Address'], m))] + [(f, inbound(f)) for f in source_folders(s)]
                # your own replies are always read in full; inbound mail pays for its body only if a
                # bodyless rule has not already thrown it away (policy.dropped_unseen)
                from . import policy as policy_engine
                pols = store.list_policies()
                sent_fill = _hydrate(tok, s['Address'])
                in_fill = _hydrate(tok, s['Address'], drop=lambda m: policy_engine.dropped_unseen(_envelope(m), pols))
                broken = []
                for folder, handle in folders:
                    try:
                        n += _mail_folder(tok, s, folder, cycle_since, through, cursor, handle, save,
                                          hydrate=sent_fill if folder == 'sentitems' else in_fill)
                    except _MailSourceChanged as e:
                        logger.warning(f"outlook {s['Address']} {folder}: {e}")
                        broken.append(f'{folder}: {e}')
                        break                           # disabled/retargeted source: make no more provider calls
                    except Exception as e:
                        logger.warning(f"outlook {s['Address']} {folder}: {e}"); broken.append(f'{folder}: {e}')
                if broken:
                    errors += broken; continue     # the watermark waits for the folders that did not finish
                if not store.patch_source_poll_state(
                        s['SourceId'], config_remove=('mail_cursor', 'mail_cursor_skip',
                                                      'mail_cursor_marker', 'mail_cursor_basis'),
                        last_polled_at=_local(through), expect_fields=expect_fields,
                        expect_config=expect_config):
                    errors.append(f"{s['Address']}: source changed while Outlook catch-up was finishing")
                else:
                    # Only a completed, still-owned intake cycle may fetch missing history.
                    # Replay duplicates participate when completed folders are read again after
                    # another folder failed; their arrivals have already landed.
                    from . import chains
                    for conv, before in history_pending.items():
                        try: chains.refresh_outlook(store, tok, s['Address'], conv, before=before)
                        except Exception as e: logger.warning(f'chain history for {conv} skipped: {e}')
                continue                            # exact cutoff above replaces generic touch_source(now)
            elif c['Type'] == 'teams':
                n += ingest_teams_chats(store, s['Address'], tok, since, llm, file_only, read_it)
            elif c['Type'] == 'github':
                # a repo with BOTH kinds off was not read, so its watermark must not
                # move: advancing it would step over the issues sitting there, and
                # switching the repo on later would only ever see what came next
                if set(gh_modes(s, file_only)) == {'off'}: continue
                # ONE dead repo must not blind the others. A renamed or deleted repo answers 404 for
                # ever, and with no guard of its own that error escaped the whole source loop: every
                # repo listed after it went unpolled, on every cycle, saying nothing. The mail branch
                # above has had this guard for as long as it has had folders that can fail.
                try: n += ingest_github_issues(store, s, tok, since, llm, file_only)
                except Exception as e:
                    errors.append(f"{s['Address']}: {_repo_error(e)}")
                    logger.warning(f"github: {s['Address']} could not be read ({e})")
                    # ...and the watermark stays PUT. Stamping a repo we failed to read would step
                    # over whatever arrived in the window we never saw.
                    continue
            elif c['Type'] in ('gmail', 'imap'):
                # one poll per connector (the UID watermark lives there); its own source only
                from . import imapmail
                if s['ConnectorId'] != c['ConnectorId']: continue
                n += imapmail.poll_imap(store, full, [s], llm, file_only, math.ceil(backfill_hours / 24))
            elif c['Type'] in CLOUD:
                # per SOURCE: each discovered object carries its own mode, and 'report'
                # (the default) means the Reports tab may use it but nothing is polled.
                # The picker OUTRANKS the card's role, like github's per-repo pickers:
                # 'tasks' on a tool-only card means tasks, not a filed feed row.
                mode = json.loads(s.get('ConfigJson') or '{}').get('mode') or 'report'
                if mode not in ('feed', 'tasks'): continue
                from .reports import aws_connection, azure_connection
                mod = __import__(f'taskuary.{c["Type"]}', fromlist=['x'])
                conn_cfg = (aws_connection if c['Type'] == 'aws' else azure_connection)(store, c['ConnectorId'])
                # per source, like github's repos: a throttle on page 40 of one bucket must not
                # skip the log groups after it, and the failed bucket keeps its watermark
                try: n += mod.poll_source(store, conn_cfg, s, since, llm, mode == 'feed')
                except Exception as e:
                    logger.warning(f"cloud poll failed ({s['Address']}): {e}"); errors.append(f"{s['Address']}: {e}")
                    continue
            elif c['Type'] == 'discord':
                # per SOURCE, like slack: each watched channel id is its own source
                from . import devtools
                n += devtools.poll_discord(store, full, s, since, llm, file_only)
            elif c['Type'] == 'slack':
                # paged like mail: one page of 25 and a watermark at 'now' lost the rest (audit 2026-09-02)
                hist_all, cursor = [], None
                while len(hist_all) < 500:
                    hist = _slack(tok, 'conversations.history', channel=s['Address'], oldest=since.timestamp(),
                                  limit=100, **({'cursor': cursor} if cursor else {}))
                    hist_all += hist.get('messages', [])
                    cursor = (hist.get('response_metadata') or {}).get('next_cursor')
                    if not cursor: break
                msgs = [m for m in reversed(hist_all) if not m.get('subtype')]
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
        store.touch_connector(c['ConnectorId'], '; '.join(errors) if errors else None)
    except Exception as e:
        logger.warning(f"channel poll failed ({c['Type']}): {e}")
        store.touch_connector(c['ConnectorId'], str(e))
    return n


def poll_channels(store, backfill_hours: float = 0, progress=None, only=None) -> int:
    """Ingest new items for every connection the owner marked as a TRIGGER, through the
    same triage funnel (incl. the configured AI, if any). A connection without the trigger
    role is still usable by agents and reports - it just never creates work on its own.
    Failures land on the card. `backfill_hours` reaches further back than the watermark - see
    _since; it is how startup catches up on mail that arrived while the app was closed.

    Independent HTTP waits overlap. SQLite writes hop onto one writer thread. Drain of
    the same conversation stays sequential - that is a later pass, not this one."""
    from .llm import build_llm
    try: llm = build_llm(store)
    except Exception: llm = None
    read_it = wants_read(store)   # asked once per run, not once per message
    # a mailbox card whose source row was never created polls nothing at all, and looks connected
    # the whole time it is doing so - so it heals itself here, before the source list is read
    for c in store.list_connectors():
        if c['Type'] in ('imap', 'gmail') and c['Active']:
            try:
                from . import imapmail
                imapmail.ensure_source(store, store.get_connector(c['ConnectorId']))
            except Exception as e:
                logger.debug(f"imap: could not heal the source row for {c.get('Name')} - {e}")
    jobs = _poll_jobs(store, only)
    if not jobs: return 0

    def _say(kind, so_far, st):
        if not progress: return
        try:
            st.do(lambda: progress(kind, so_far)) if hasattr(st, 'do') else progress(kind, so_far)
        except Exception:
            pass

    if len(jobs) == 1:
        c, file_only = jobs[0]
        _say(c['Type'], 0, store)
        return _poll_one(store, c, file_only, backfill_hours, llm, read_it)

    # said as it happens, not at the end: the timeline is refreshing while this runs, so
    # "reading Outlook" beside rows that are already arriving beats a spinner and a wait
    writer = _Writer(store)
    tally, tally_lock = [0], threading.Lock()
    try:
        def run(c, file_only):
            from . import ingest as ingest_mod
            with tally_lock: so_far = tally[0]
            _say(c['Type'], so_far, writer)
            # inherit the poll thread's deferred(): our threading.local is off, and without
            # this wrap we would triage in parallel - the thing drain exists to prevent
            with ingest_mod.deferred() if ingest_mod._parent_deferring() else contextlib.nullcontext():
                added = _poll_one(writer, c, file_only, backfill_hours, llm, read_it)
            with tally_lock: tally[0] += added
            return added
        with ThreadPoolExecutor(max_workers=min(8, len(jobs)), thread_name_prefix='poll') as pool:
            futs = [pool.submit(run, c, fo) for c, fo in jobs]
            n = 0
            for f in futs:
                try: n += f.result()
                except Exception as e: logger.warning(f'channel poll worker failed: {e}')
            return n
    finally:
        writer.close()
