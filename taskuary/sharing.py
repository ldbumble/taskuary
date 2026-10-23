"""SHARE A RESULT (the owner, 2026-10-23: "put on sharing reports/new dashboards or agent result so you can email it out, maybe on
same network you can share results directly via shared link or post report in google drive, sharepoint ... button on report on
bottom named share"). One Share, four ways out, each offered only where it can work (ways):

- EMAIL IT: a draft on the same review road every send takes - the task's Close out when the result is a task's, else a task of
  its own like ＋ New's - with the result as its text and, at send, as clean HTML beside it (email_html). Nothing leaves here.
- SHARED LINK: a frozen, escaped snapshot of the one result at /share/<token> on this machine, for people on the same network.
  Off until the owner turns `share_links_lan` on, and useless while the server listens on loopback alone (lan_url says which).
  The token is shown once and only its hash is kept; a link expires (7 days by default) and is revoked from Settings.
- ONEDRIVE / GOOGLE DRIVE: the same HTML uploaded to a "Taskuary" folder, through a sign-in the owner already gave - only when
  that sign-in holds a file scope. Taskuary never widens a sign-in to get one (NEED_MS / NEED_G say what would be needed).

A SHAREABLE RESULT is {kind, title, text, html?, data?} - a report's message, an agent's or a workflow's task (snapshot reads
those from the store, so the page cannot hand in words the store does not hold), or anything a page registers itself with
(a dashboard: website/src/Share.jsx useShare). Client HTML is never trusted: clean_html keeps a short list of tags and no
attributes, and the share page's CSP sandboxes it besides.

Every share is a row of the audit chain (EntityType 'share'): what, how, to whom or where, when."""
import hashlib, html as H, json, re, secrets, socket, time
from datetime import datetime, timedelta
from html.parser import HTMLParser
import requests
from loguru import logger

SETTING = 'share_links_lan'
DAYS = 7
MAX_TEXT, MAX_HTML, MAX_ROWS = 200_000, 500_000, 2000
GRAPH = 'https://graph.microsoft.com/v1.0'
FOLDER = 'Taskuary'
MS_FILES = ('files.readwrite', 'files.readwrite.all', 'sites.readwrite.all')
G_FILES = ('https://www.googleapis.com/auth/drive.file', 'https://www.googleapis.com/auth/drive')
NEED_MS = ("the Microsoft sign-in has no file access - uploading to OneDrive or SharePoint needs Files.ReadWrite "
           "(a tenant app: Files.ReadWrite.All), which Taskuary does not ask for")
NEED_G = 'the Google sign-in has no Drive access - uploading needs the drive.file scope, which Taskuary does not ask for'
WAYS = ('email', 'link', 'onedrive', 'gdrive')
# the page a link opens: no script, nothing fetched, no frame, no form - the snapshot's own styles and nothing else
CSP = "default-src 'none'; style-src 'unsafe-inline'; img-src data:; base-uri 'none'; form-action 'none'; frame-ancestors 'none'; sandbox"
HEADERS = {'Cache-Control': 'no-store', 'Pragma': 'no-cache', 'X-Robots-Tag': 'noindex, nofollow, noarchive', 'Referrer-Policy': 'no-referrer',
           'X-Content-Type-Options': 'nosniff', 'X-Frame-Options': 'DENY', 'Content-Security-Policy': CSP}


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def _hash(tok: str) -> str: return hashlib.sha256(str(tok or '').encode('utf-8', 'surrogateescape')).hexdigest()


# ── the table: only the HASH of a token is kept, so a copy of the database opens no link ──────────────────────────────────
def _table(store):
    with store.lock:
        store.cx.execute('CREATE TABLE IF NOT EXISTS share_link (ShareId INTEGER PRIMARY KEY, TokenHash TEXT UNIQUE, Kind TEXT, Title TEXT, '
                         'Html TEXT, TaskId INTEGER, MessageId INTEGER, CreatedAt TEXT, ExpiresAt TEXT, RevokedAt TEXT, Views INTEGER DEFAULT 0, '
                         'LastViewAt TEXT)')
        store.cx.commit()


# ── rendering: everything escaped first, then a small markdown subset given its tags back ─────────────────────────────────
_INLINE = ((re.compile(r'`([^`]+)`'), r'<code>\1</code>'), (re.compile(r'\*\*(.+?)\*\*'), r'<b>\1</b>'),
           (re.compile(r'(?<![\w*])\*(?!\s)(.+?)(?<!\s)\*(?![\w*])'), r'<i>\1</i>'),
           (re.compile(r'\[([^\]]+)\]\((https?://[^\s)"<>]+)\)'), r'<a href="\2">\1</a>'))


def _inline(s: str) -> str:
    s = H.escape(s, quote=True)
    for rx, to in _INLINE: s = rx.sub(to, s)
    return s


def _cells(line: str) -> list: return [c.strip() for c in line.strip().strip('|').split('|')]


def md_html(text: str) -> str:
    """Markdown as the reports and agents write it - headings, lists, tables, code, bold - as HTML. Every character of the text
    is escaped before any tag is given back, so nothing in a result (a mail it quoted, a cell from a query) can become markup."""
    out, para, lines, i = [], [], str(text or '').replace('\r\n', '\n').split('\n'), 0
    flush = lambda: (out.append(f"<p>{'<br>'.join(_inline(p) for p in para)}</p>"), para.clear()) if para else None
    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith('```'):
            flush(); j = i + 1
            while j < len(lines) and not lines[j].strip().startswith('```'): j += 1
            out.append(f"<pre>{H.escape(chr(10).join(lines[i + 1:j]))}</pre>"); i = j + 1; continue
        if m := re.match(r'^(#{1,6})\s+(.*)$', ln):
            flush(); n = min(len(m.group(1)) + 1, 6); out.append(f'<h{n}>{_inline(m.group(2))}</h{n}>'); i += 1; continue
        if ln.strip().startswith('|') and i + 1 < len(lines) and re.match(r'^\s*\|?\s*:?-{2,}', lines[i + 1]):
            flush(); head, j, body = _cells(ln), i + 2, []
            while j < len(lines) and lines[j].strip().startswith('|'): body.append(_cells(lines[j])); j += 1
            out.append('<table><thead><tr>' + ''.join(f'<th>{_inline(c)}</th>' for c in head) + '</tr></thead><tbody>'
                       + ''.join('<tr>' + ''.join(f'<td>{_inline(c)}</td>' for c in r) + '</tr>' for r in body) + '</tbody></table>')
            i = j; continue
        if m := re.match(r'^\s*([-*•]|\d+[.)])\s+(.*)$', ln):
            flush(); tag, items = ('ol' if m.group(1)[0].isdigit() else 'ul'), []
            while i < len(lines) and (m := re.match(r'^\s*([-*•]|\d+[.)])\s+(.*)$', lines[i])): items.append(m.group(2)); i += 1
            out.append(f'<{tag}>' + ''.join(f'<li>{_inline(x)}</li>' for x in items) + f'</{tag}>'); continue
        if not ln.strip(): flush()
        else: para.append(ln)
        i += 1
    flush()
    return '\n'.join(out)


def rows_html(rows) -> str:
    """A list of records (a report's rows, a dashboard's data) as one table - the columns every row has, in first-seen order."""
    rows = [r for r in (rows or [])[:MAX_ROWS] if isinstance(r, dict)]
    if not rows: return ''
    cols = list(dict.fromkeys(k for r in rows for k in r))
    cell = lambda v: '' if v is None else f'{v:,}' if isinstance(v, (int, float)) and not isinstance(v, bool) else str(v)
    return ('<table><thead><tr>' + ''.join(f'<th>{H.escape(str(c).replace("_", " "))}</th>' for c in cols) + '</tr></thead><tbody>'
            + ''.join('<tr>' + ''.join(f'<td>{H.escape(cell(r.get(c)))}</td>' for c in cols) + '</tr>' for r in rows) + '</tbody></table>')


class _Clean(HTMLParser):
    KEEP = {'p', 'br', 'b', 'strong', 'i', 'em', 'u', 'code', 'pre', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'ul', 'ol', 'li', 'table', 'thead',
            'tbody', 'tr', 'th', 'td', 'div', 'span', 'section', 'blockquote', 'hr', 'small', 'sub', 'sup', 'caption'}
    DROP = {'script', 'style', 'iframe', 'object', 'embed', 'template', 'noscript', 'svg', 'math', 'head', 'title', 'form', 'select', 'textarea'}
    VOID = {'br', 'hr'}
    def __init__(self): super().__init__(convert_charrefs=True); self.out, self.skip = [], 0
    def handle_starttag(self, tag, attrs):
        if tag in self.DROP: self.skip += 1
        elif not self.skip and tag in self.KEEP:
            span = ''.join(f' {k}="{int(v)}"' for k, v in attrs if k in ('colspan', 'rowspan') and str(v or '').isdigit() and int(v) < 100)
            self.out.append(f'<{tag}{span}>')
    def handle_startendtag(self, tag, attrs):
        if not self.skip and tag in self.VOID: self.out.append(f'<{tag}>')
    def handle_endtag(self, tag):
        if tag in self.DROP: self.skip = max(0, self.skip - 1)
        elif not self.skip and tag in self.KEEP and tag not in self.VOID: self.out.append(f'</{tag}>')
    def handle_data(self, d):
        if not self.skip: self.out.append(H.escape(d, quote=True))


def clean_html(html: str) -> str:
    """HTML a page handed in (a dashboard's own render) with nothing left that runs, loads or links: a short list of tags, no
    attribute but colspan/rowspan, every text node escaped again. The share page's CSP would stop a script anyway; an email
    client and a Drive preview have no CSP, so this is what keeps them clean."""
    p = _Clean(); p.feed(str(html or '')[:MAX_HTML]); p.close()
    return ''.join(p.out)


CSS = ('body{font:15px/1.55 -apple-system,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;color:#22262b;background:#faf8f5;margin:0}'
       'main{max-width:860px;margin:0 auto;padding:28px 20px 48px}h1{font-size:22px;margin:0 0 4px}.meta{color:#77736c;font-size:12.5px;'
       'margin-bottom:22px}table{border-collapse:collapse;margin:10px 0;font-size:13.5px;display:block;overflow-x:auto}th,td{border:1px solid '
       '#e3ded6;padding:5px 9px;text-align:left;vertical-align:top}th{background:#f1ede6}pre{background:#f1ede6;padding:10px;overflow-x:auto;'
       'white-space:pre-wrap}code{background:#f1ede6;padding:0 3px}a{color:#3e6a8a}')


def body_of(snap: dict) -> str:
    """The result's own content as HTML: its text, its rows, the page's cleaned HTML - whichever it has, in that order."""
    return '\n'.join(x for x in (md_html(snap.get('text') or ''), rows_html(snap.get('data')), clean_html(snap.get('html') or '')) if x)


def document(snap: dict, meta: str = None) -> str:
    """The whole page - one result, its title and when it was taken; no app around it, nothing it loads."""
    t = H.escape(str(snap.get('title') or 'Shared result'))
    meta = H.escape(meta if meta is not None else ' · '.join(x for x in (str(snap.get('kind') or '').capitalize(), f"taken {snap.get('at') or _now()}") if x))
    return (f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<meta name="robots" content="noindex,nofollow,noarchive"><meta name="referrer" content="no-referrer"><title>{t}</title>'
            f'<style>{CSS}</style></head><body><main><h1>{t}</h1><div class="meta">{meta}</div>{body_of(snap)}</main></body></html>')


def email_html(subject: str, text: str) -> str:
    """The HTML part of a shared result's email, rendered from the text AS SENT - the owner's edits to the draft are in both."""
    return document({'title': subject, 'text': text}, meta='Shared from Taskuary')


# ── what is shared: read from the store where the result lives there ──────────────────────────────────────────────────────
def _rows_of(text: str):
    try: v = json.loads(text)
    except (TypeError, ValueError): return None
    return v if isinstance(v, list) and v and all(isinstance(r, dict) for r in v) else None


def as_text(snap: dict) -> str:
    """The plain-text form - the email's editable draft and its fallback part: the text, else the rows as a markdown table."""
    if snap.get('text'): return snap['text']
    rows = [r for r in (snap.get('data') or [])[:MAX_ROWS] if isinstance(r, dict)]
    if rows:
        cols = list(dict.fromkeys(k for r in rows for k in r)); esc = lambda v: str('' if v is None else v).replace('|', '/').replace('\n', ' ')
        return '\n'.join(['| ' + ' | '.join(map(esc, cols)) + ' |', '|' + '---|' * len(cols)] + ['| ' + ' | '.join(esc(r.get(c)) for c in cols) + ' |' for r in rows])
    return re.sub(r'\n{3,}', '\n\n', re.sub(r'<[^>]+>', '\n', clean_html(snap.get('html') or ''))).strip()


def snapshot(store, req: dict) -> dict:
    """{kind, title, text, data, html, tid, mid, at} - FROZEN now. A report's message and a task's result are read here; only a
    result the store does not hold (a dashboard drawn on the page) brings its own words, and its HTML is cleaned like any."""
    from . import outbox, workflows
    req = req or {}
    kind, mid, tid = str(req.get('kind') or 'result')[:40], req.get('message'), req.get('task')
    title, text, data, html = str(req.get('title') or '').strip(), str(req.get('text') or ''), req.get('data'), str(req.get('html') or '')
    if mid:
        m = store.get_message(int(mid))
        if not m: raise LookupError('that result is not here any more')
        body = str(m.get('BodyText') or '')
        cut = body.find('\n--- raw data ---')
        text = body[:cut] if cut >= 0 else body
        title, tid = title or m.get('Subject') or m.get('TriageTitle') or 'Report', tid or m.get('TaskId')
        if rows := _rows_of(text.strip()): data, text = rows, ''           # a report that is only rows reads as its table
    elif tid:
        t = store.get_task(int(tid))
        if not t: raise LookupError('that task is not here any more')
        run = (workflows.of_task(store, t) or {})
        steps = '\n'.join('- ' + ' - '.join(str(x) for x in (s.get('label') or s.get('kind') or 'step', s.get('status'), s.get('head') or s.get('why')) if x)
                          for s in run.get('steps') or [] if isinstance(s, dict))
        text = outbox.work_of(store, int(tid)) or '\n\n'.join(x for x in (run.get('summary'), steps) if x) or str(t.get('Summary') or '')
        title = title or t.get('Title') or 'Result'
    text, html = text[:MAX_TEXT], html[:MAX_HTML]
    data = [r for r in data[:MAX_ROWS] if isinstance(r, dict)] if isinstance(data, list) else None
    if not (text.strip() or data or clean_html(html).strip()): raise ValueError('there is nothing in this result to share yet')
    return {'kind': kind, 'title': title[:200] or 'Result', 'text': text, 'data': data, 'html': html,
            'tid': int(tid) if tid else None, 'mid': int(mid) if mid else None, 'at': _now()[:16]}


# ── where it can go, each with the sentence why not ───────────────────────────────────────────────────────────────────────
LOOPBACK = ('127.0.0.1', 'localhost', '::1', '')


def lan_address() -> str:
    """This machine's address on its network: the interface a route out would leave by (a UDP connect sends nothing)."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
            s.connect(('10.255.255.255', 1)); ip = s.getsockname()[0]
            if not ip.startswith('127.'): return ip
    except Exception: pass          # no route out (offline): the machine's own name is the next best thing
    try: return socket.gethostname()
    except OSError: return ''


def base_url(server: dict) -> str:
    """Where someone else on the network reaches this server - '' when it listens on this computer alone."""
    host, port = str(server.get('host') or '').strip(), server.get('port') or 7787
    if host.lower() in LOOPBACK: return ''
    if host in ('0.0.0.0', '::'): host = lan_address()
    if not host: return ''
    return f"http://{f'[{host}]' if ':' in host else host}:{port}"


def link_block(store, server: dict) -> str:
    if store.get_setting(SETTING, '0') != '1':
        return 'share links are off - turn on "Share links on my network" in Settings first'
    if not base_url(server):
        return (f"Taskuary listens only on this computer ({server.get('host') or '127.0.0.1'}), so nobody else on your network could open a "
                'link - it needs to listen on your network (host under [server] in config.toml) first')
    return ''


_CACHE: dict = {}


def _cached(key, f, ttl=300):
    hit = _CACHE.get(key)
    if hit and time.time() - hit[0] < ttl: return hit[1]
    v = f(); _CACHE[key] = (time.time(), v); return v


def _ms_card(store):
    return next((c for c in store.connectors_by_type('outlook', with_secret=True) if c.get('Active')), None)


def _ms_token(store, c):
    from .channels import graph_creds, graph_token
    cfg, sec, _ = graph_creds(store, c)
    return cfg, graph_token(cfg, sec)


def onedrive_block(store) -> str:
    """'' when the Outlook card's sign-in can write files. A signed-in card says what Microsoft granted (granted_scope); a tenant
    app's token carries its roles. Neither is ever widened from here."""
    c = _ms_card(store)
    if not c: return 'no Microsoft account is connected - OneDrive and SharePoint go through the Outlook card'
    cfg = json.loads(c.get('ConfigJson') or '{}')
    if cfg.get('auth') == 'user':
        return '' if any(s in str(cfg.get('granted_scope') or '').lower().split() for s in MS_FILES) else NEED_MS
    def check():
        from .calwrite import _claims
        try: _, tok = _ms_token(store, c)
        except Exception as e: return f'the Microsoft account could not be reached ({str(e)[:120]})'
        held = [str(x).lower() for x in (_claims(tok).get('roles') or [])] + str(_claims(tok).get('scp') or '').lower().split()
        return '' if any(h in MS_FILES for h in held) else NEED_MS
    return _cached(('ms', c['ConnectorId']), check)


def _g_card(store):
    return next((c for c in store.connectors_by_type('gmail', with_secret=True)
                 if c.get('Active') and json.loads(c.get('ConfigJson') or '{}').get('google_refresh_token')), None)


def gdrive_block(store) -> str:
    c = _g_card(store)
    if not c: return 'no Google account is signed in - the Gmail card holds the Google sign-in'
    def check():
        from .calwrite import _google_token
        try: _, granted = _google_token(json.loads(c.get('ConfigJson') or '{}'))
        except Exception as e: return f'the Google account could not be reached ({str(e)[:120]})'
        return '' if any(s in granted.split() for s in G_FILES) else NEED_G
    return _cached(('g', c['ConnectorId']), check)


def ways(store, server: dict) -> dict:
    """{way: {ok, why}} - what the Share menu offers, greyed with its reason where it cannot work."""
    from . import capabilities, demo
    def one(f):
        try: why = f()
        except Exception as e: why = f'could not tell ({str(e)[:120]})'
        return {'ok': not why, 'why': why}
    out = {'email': one(lambda: capabilities.send_refusal(store, 'email')), 'link': one(lambda: link_block(store, server)),
           'onedrive': one(lambda: onedrive_block(store)), 'gdrive': one(lambda: gdrive_block(store))}
    if demo.enabled():          # the demo's doors to the outside are shut - say so here rather than on the press
        out = {k: {'ok': False, 'why': 'the demo shares nothing'} for k in out}
    out['setting'] = store.get_setting(SETTING, '0') == '1'
    return out


# ── the four ways ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def _audit(store, eid, how, actor, snap, **where):
    store.audit('share', int(eid or 0), how, actor, detail={'kind': snap['kind'], 'title': snap['title'], 'task': snap.get('tid'),
                                                            'message': snap.get('mid'), **where})


def email(store, snap: dict, to: list, actor: str = 'owner') -> dict:
    """A draft, never a send: on the result's own task when it is open (its Close out, like Send out results), else on a task of
    its own the way ＋ New starts one. The envelope says `format: html`, so the send renders the approved text as HTML too."""
    from . import capabilities, outbound, slots
    from .store import task_ref
    if no := capabilities.send_refusal(store, 'email'): raise ValueError(no)
    raw = [p.strip() for v in (to if isinstance(to, (list, tuple)) else [to]) for p in str(v or '').replace(';', ',').split(',') if p.strip()]
    bad = [a for a in raw if not outbound.addrs([a])]
    if bad: raise ValueError(f"not a valid email address: {', '.join(bad)}")
    who = outbound.addrs(raw)
    if not who: raise ValueError('pick who it goes to')
    text, subject, tid = as_text(snap), snap['title'], snap.get('tid')
    task = store.get_task(tid) if tid else None
    if task and task.get('Status') not in ('done', 'dropped'):
        out = slots.draft(store, tid, text, to=who[0], subject=subject, agent='owner', channel='email')
        if not out.get('ok'): raise ValueError(out.get('why') or 'the email could not be saved on the task')
        rid = out['review_id']
    else:
        tid = store.create_task({'Title': subject[:300], 'Summary': f'Share "{subject}" with {", ".join(who)}', 'Kind': 'reply', 'Status': 'open',
                                 'Priority': 'normal', 'Source': 'outbox'}, actor)
        mid = store.add_message({'TaskId': tid, 'ExternalId': f'outbox:{tid}', 'ConversationId': f'outbox:{tid}', 'Channel': 'email',
                                 'SourceName': ', '.join(who), 'Subject': subject, 'FromName': 'You', 'Direction': 'out', 'BodyText': text,
                                 'Status': 'routed', 'SentAt': _now()})
        store.add_route(mid, tid, 'outbox', None, 'you shared a result from Taskuary - drafted for you to approve, then it sends', [], actor)
        rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': text,
                                'Deliver': json.dumps({'channel': 'email', 'to': who[:1], 'cc': [], 'subject': subject}),
                                'Reason': f'a result you are sharing with {", ".join(who)} - approve to send it'})
    rv = store.get_review(rid) or {}
    env = json.loads(rv.get('Deliver') or '{}') or {}
    env.update({'cc': [a for a in who[1:] if a.lower() != who[0].lower()], 'format': 'html', 'by': 'owner', 'shared': snap['kind']})
    store.set_review_deliver(rid, json.dumps(env))
    _audit(store, tid, 'email', actor, snap, to=who, review=rid)
    return {'ok': True, 'how': 'email', 'review_id': rid, 'task_id': tid, 'ref': task_ref(tid), 'to': who}


def link(store, snap: dict, server: dict, days: int = DAYS, actor: str = 'owner') -> dict:
    """A link for this one result. The token is returned ONCE - the table keeps its hash - and the page is frozen now."""
    if why := link_block(store, server): raise PermissionError(why)
    _table(store)
    days = max(1, min(int(days or DAYS), 90))
    tok = secrets.token_urlsafe(32)
    exp = (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    sid = store._exec('INSERT INTO share_link (TokenHash,Kind,Title,Html,TaskId,MessageId,CreatedAt,ExpiresAt,Views) VALUES (?,?,?,?,?,?,?,?,0)',
                      (_hash(tok), snap['kind'], snap['title'], document(snap), snap.get('tid'), snap.get('mid'), _now(), exp))
    url = f'{base_url(server)}/share/{tok}'
    _audit(store, sid, 'link', actor, snap, expires=exp)
    return {'ok': True, 'how': 'link', 'id': sid, 'url': url, 'expires': exp}


def page(store, tok: str) -> str | None:
    """The snapshot behind a live token, or None - a token that is unknown, revoked or expired, or links switched off, are all
    the same nothing to whoever asks (no oracle for which)."""
    if store.get_setting(SETTING, '0') != '1' or not re.fullmatch(r'[A-Za-z0-9_-]{20,100}', str(tok or '')): return None
    _table(store)
    r = store._one('SELECT ShareId, Html, ExpiresAt, RevokedAt FROM share_link WHERE TokenHash=?', (_hash(tok),))
    if not r or r.get('RevokedAt') or str(r.get('ExpiresAt') or '') <= _now(): return None
    store._exec('UPDATE share_link SET Views=COALESCE(Views,0)+1, LastViewAt=? WHERE ShareId=?', (_now(), r['ShareId']))
    return r['Html']


def active(store) -> list:
    """The links still open, newest first - for Settings, where each is revoked. Never the token: it was shown once."""
    _table(store)
    return store._rows('SELECT ShareId id, Kind kind, Title title, TaskId task, MessageId message, CreatedAt created, ExpiresAt expires, '
                       'Views views, LastViewAt viewed FROM share_link WHERE RevokedAt IS NULL AND ExpiresAt > ? ORDER BY ShareId DESC', (_now(),))


def revoke(store, sid: int, actor: str = 'owner') -> bool:
    _table(store)
    r = store._one('SELECT ShareId, Title, Kind FROM share_link WHERE ShareId=? AND RevokedAt IS NULL', (int(sid),))
    if not r: return False
    store._exec('UPDATE share_link SET RevokedAt=? WHERE ShareId=?', (_now(), int(sid)))
    store.audit('share', int(sid), 'revoke', actor, detail={'title': r['Title'], 'kind': r['Kind']})
    return True


def _fname(snap) -> str:
    name = re.sub(r'[^\w .-]+', ' ', snap['title']).strip()[:80] or 'Result'
    return f"{name} {snap['at'][:10]}.html"


def onedrive(store, snap: dict, actor: str = 'owner') -> dict:
    """The page as a file in Taskuary/ on the owner's OneDrive (a tenant app: the mailbox's own drive). Returns its link."""
    if why := onedrive_block(store): raise PermissionError(why)
    c = _ms_card(store)
    cfg, tok = _ms_token(store, c)
    from urllib.parse import quote
    if cfg.get('auth') == 'user': root = f'{GRAPH}/me/drive'
    else:
        box = next((s['Address'] for s in store.list_sources() if s.get('Channel') == 'email' and s.get('Address')
                    and (not s.get('ConnectorId') or s['ConnectorId'] == c['ConnectorId'])), '')
        if not box: raise PermissionError('the Outlook card names no mailbox whose OneDrive to put it in')
        root = f'{GRAPH}/users/{quote(box)}/drive'
    r = requests.put(f'{root}/root:/{FOLDER}/{quote(_fname(snap))}:/content', params={'@microsoft.graph.conflictBehavior': 'rename'},
                     headers={'Authorization': f'Bearer {tok}', 'Content-Type': 'text/html; charset=utf-8'},
                     data=document(snap).encode('utf-8'), timeout=60)
    if r.status_code >= 300: raise RuntimeError(f'OneDrive refused the upload ({r.status_code}): {r.text[:200]}')
    url = (r.json() or {}).get('webUrl') or ''
    _audit(store, 0, 'onedrive', actor, snap, where=url)
    return {'ok': True, 'how': 'onedrive', 'url': url}


def gdrive(store, snap: dict, actor: str = 'owner') -> dict:
    """The page as a file in a Taskuary folder on the owner's Google Drive. drive.file sees only what this app made, so the
    folder is found (or made) among those."""
    if why := gdrive_block(store): raise PermissionError(why)
    from .calwrite import _google_token
    tok, _ = _google_token(json.loads(_g_card(store).get('ConfigJson') or '{}'))
    hdr = {'Authorization': f'Bearer {tok}'}
    q = f"name='{FOLDER}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    r = requests.get('https://www.googleapis.com/drive/v3/files', headers=hdr, params={'q': q, 'fields': 'files(id)', 'pageSize': 1}, timeout=30)
    if r.status_code >= 300: raise RuntimeError(f'Google Drive refused ({r.status_code}): {r.text[:200]}')
    fid = ((r.json() or {}).get('files') or [{}])[0].get('id')
    if not fid:
        r = requests.post('https://www.googleapis.com/drive/v3/files', headers={**hdr, 'Content-Type': 'application/json'}, timeout=30,
                          params={'fields': 'id'}, data=json.dumps({'name': FOLDER, 'mimeType': 'application/vnd.google-apps.folder'}))
        if r.status_code >= 300: raise RuntimeError(f'Google Drive could not make the {FOLDER} folder ({r.status_code}): {r.text[:200]}')
        fid = (r.json() or {}).get('id')
    bound = 'taskuary' + secrets.token_hex(8)
    meta = json.dumps({'name': _fname(snap), 'parents': [fid], 'mimeType': 'text/html'})
    body = (f'--{bound}\r\nContent-Type: application/json; charset=UTF-8\r\n\r\n{meta}\r\n--{bound}\r\nContent-Type: text/html; charset=UTF-8\r\n\r\n'
            f'{document(snap)}\r\n--{bound}--').encode('utf-8')
    r = requests.post('https://www.googleapis.com/upload/drive/v3/files', params={'uploadType': 'multipart', 'fields': 'id,webViewLink'},
                      headers={**hdr, 'Content-Type': f'multipart/related; boundary={bound}'}, data=body, timeout=60)
    if r.status_code >= 300: raise RuntimeError(f'Google Drive refused the upload ({r.status_code}): {r.text[:200]}')
    url = (r.json() or {}).get('webViewLink') or ''
    _audit(store, 0, 'gdrive', actor, snap, where=url)
    return {'ok': True, 'how': 'gdrive', 'url': url}


def share(store, server: dict, req: dict, actor: str = 'owner') -> dict:
    """One press of one way. ValueError/LookupError/PermissionError say why it did not go; nothing half-happens."""
    how = str((req or {}).get('how') or '')
    if how not in WAYS: raise ValueError(f"share how? one of {', '.join(WAYS)}")
    snap = snapshot(store, req)
    if how == 'email': return email(store, snap, req.get('to') or [], actor)
    if how == 'link': return link(store, snap, server, req.get('days') or DAYS, actor)
    return (onedrive if how == 'onedrive' else gdrive)(store, snap, actor)
