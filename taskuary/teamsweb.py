"""PERSONAL TEAMS, READ THROUGH THE BROWSER (the owner, 2026-11-09: "add Teams for personal Microsoft accounts as an option").

Microsoft Graph's chat API answers only work and school accounts; Teams for a personal account (teams.live.com, "Teams free")
has no API at all. So a Teams card set to `account_type: personal` reads the owner's chats the way a person does - in a browser:

- SIGN IN ONCE, in the card's own browser view: the card starts a headless agent-browser session (`teamsweb-<card id>`, the same
  browserview road a task's browser takes - restored from the owner's own cookies) on teams.live.com, the owner takes over the
  view and signs in. Taskuary stores nothing of that sign-in; the browser profile keeps the cookies, as it does for every portal.
- THE POLL reads the page, not an API: the chat list from the DOM, and each chat whose preview moved (or that is marked unread)
  opened and its messages read. The fragments come back as HTML and are parsed HERE (parse_chats / parse_messages), so the part
  that breaks when Microsoft changes the page is in one place, and is tested against a recorded shape (tests/test_teamsweb.py).
- FILED LIKE THE GRAPH ROAD: one conversation per chat (`teams:live:<chat id>` - `live:` keeps a personal chat from ever
  meeting a work one), each message `teams:live:<chat>:<message id>` so a second read files nothing twice, the sender's name,
  the message's own time; the owner's own lines ride in as context (ingest_own_message), never as work.
- A REPLY is a draft on the task like any Teams reply; the owner's Send is the press, and only then is it typed into the chat by
  the browser (send) - outbound.send_teams routes a `live:` chat here.
- WHEN IT STOPS, the card says which: signed out (SIGNED_OUT - "Sign in again") or the page no longer looks like Teams (CHANGED).
  Never a guess at a half-read page: no chat list on a page that is not a sign-in page is CHANGED, and the poll stops there.
"""
import json, time
from datetime import datetime
from html.parser import HTMLParser
from urllib.parse import urlsplit
from loguru import logger
from .timewords import plural

HOME = 'https://teams.live.com/v2/'
SITE = 'teams.live.com'
SIGNIN_HOSTS = ('login.live.com', 'login.microsoftonline.com', 'login.microsoft.com', 'signup.live.com', 'account.live.com')
SIGNED_OUT = 'Signed out of Teams - press Sign in again on this card.'
CHANGED = "Teams' page changed; reading stopped. Taskuary needs an update before it can read your chats again."
NO_BROWSER = 'the browser is not installed - personal Teams is read through agent-browser (npm i -g agent-browser)'
LOAD_WAIT, OPEN_WAIT, SEND_WAIT = 25.0, 8.0, 10.0
MAX_CHATS = 30                  # chats looked at per read: the newest, the way the list is ordered


def _cfg(c): return json.loads((c or {}).get('ConfigJson') or '{}')
def personal(c) -> bool: return _cfg(c).get('account_type') == 'personal'
def sid_of(cid) -> str: return f'teamsweb-{int(cid)}'
def is_live(chat) -> bool: return str(chat or '').startswith('live:')


# ── the page, as HTML: a small tree, because the stdlib parser only streams ─────────────────────────────────────────────────
VOID = frozenset('area base br col embed hr img input link meta source track wbr'.split())

class Node:
    __slots__ = ('tag', 'attrs', 'kids', 'parent')
    def __init__(self, tag, attrs=None, parent=None): self.tag,self.attrs,self.kids,self.parent = tag,dict(attrs or {}),[],parent
    def get(self, k, d=''): return self.attrs.get(k) or d
    def walk(self):
        yield self
        for k in self.kids:
            if isinstance(k, Node): yield from k.walk()
    def find(self, f): return next((n for n in self.walk() if f(n)), None)
    def text(self, skip=()) -> str:
        out = []
        def go(n):
            for k in n.kids:
                if isinstance(k, str): out.append(k)
                elif not any(f(k) for f in skip): go(k)
        go(self)
        return ' '.join(' '.join(out).split())

class _Tree(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.root = self.cur = Node('#root')
    def handle_starttag(self, tag, attrs):
        n = Node(tag, [(k, v or '') for k, v in attrs], self.cur); self.cur.kids.append(n)
        if tag not in VOID: self.cur = n
    def handle_startendtag(self, tag, attrs): self.cur.kids.append(Node(tag, [(k, v or '') for k, v in attrs], self.cur))
    def handle_endtag(self, tag):
        n = self.cur
        while n is not self.root and n.tag != tag: n = n.parent
        if n is not self.root: self.cur = n.parent
    def handle_data(self, d): self.cur.kids.append(d)

def dom(html: str) -> Node:
    t = _Tree(); t.feed(html or ''); t.close()
    return t.root

def _tid(*want): return lambda n: n.get('data-tid') in want
def _idp(*pre): return lambda n: n.get('id').startswith(pre)
def _cls(word): return lambda n: word.lower() in n.get('class').lower()


# ── what the page says ──────────────────────────────────────────────────────────────────────────────────────────────────
# The selectors are Teams' own markers (data-tid, the ids it derives from a chat's id), each with the fallback seen in other
# builds of the page. Every one of them is a guess at a page Microsoft owns - this is the part a page change breaks.
_ITEM = lambda n: n.get('id').startswith('chat-list-item_') or n.get('data-tid') == 'chat-list-item'
_TITLE = lambda n: n.get('data-tid') in ('chat-list-item-title', 'chat-title') or n.get('id').startswith('title-chat-list-item_')
_PREVIEW = lambda n: n.get('data-tid') in ('chat-list-item-preview', 'chat-list-item-last-message') or n.get('id').startswith('last-message-')
_UNREAD = lambda n: 'unread' in f"{n.get('class')} {n.get('data-tid')} {n.get('aria-label')}".lower()

def parse_chats(frags) -> list:
    """[{id, title, preview, when, unread, dm}] off the chat list's items, newest first as the page orders them."""
    out, seen = [], set()
    for f in frags or ():
        el = dom(f).find(_ITEM)
        if not el: continue
        cid = (el.get('data-item-id') or el.get('data-chat-id') or el.get('id').removeprefix('chat-list-item_')).strip()
        if not cid or cid in seen or cid == 'chat-list-item': continue
        seen.add(cid)
        t, p, w = el.find(_TITLE), el.find(_PREVIEW), el.find(lambda n: n.tag == 'time')
        title = (t.text() if t else '') or el.get('aria-label').split(',')[0].strip()
        out.append({'id': cid, 'title': title or 'Teams chat', 'preview': p.text() if p else '',
                    'when': (w.get('datetime') or w.text()) if w else '', 'unread': any(_UNREAD(n) for n in el.walk()),
                    # a 1:1 chat's id names the two people (@unq.gbl.spaces); a group's is a thread
                    'dm': '@unq.gbl.spaces' in cid or el.get('data-chat-type') == 'oneOnOne'})
    return out


_MSG = lambda n: n.get('data-tid') in ('chat-pane-message', 'chat-pane-message-mine') or bool(n.get('data-mid'))
_AUTHOR = _tid('message-author-name')
_BODY = lambda n: n.get('id').startswith('content-') or n.get('data-tid') in ('message-body-content', 'message-body')
_SYSTEM = lambda n: n.get('data-tid') in ('control-message', 'chat-pane-control-message', 'system-message')
_MINE = lambda n: 'chatmymessage' in n.get('class').lower().replace('-', '') or n.get('data-tid') == 'chat-pane-message-mine'

def parse_messages(frags) -> list:
    """[{id, author, when, text, mine}] off the open chat's items, oldest first. Teams draws a sender's name only on the first of a
    run of their messages, so a message without one is the last named sender's."""
    out, last = [], ''
    for f in frags or ():
        root = dom(f)
        if root.find(_SYSTEM) and not root.find(_MSG): continue          # "Erin added Ray", a call ended: nobody's words
        m = root.find(_MSG)
        if not m: continue
        b = m.find(_BODY) or root.find(_BODY)
        mid = (m.get('data-mid') or (b.get('id').removeprefix('content-') if b and b.get('id').startswith('content-') else '')).strip()
        a, w = root.find(_AUTHOR), root.find(lambda n: n.tag == 'time')
        mine = any(_MINE(n) for n in root.walk())
        author = (a.text() if a else '') or last
        text = b.text() if b else m.text(skip=(_AUTHOR, lambda n: n.tag == 'time'))
        if not mid or not text: continue
        last = author
        out.append({'id': mid, 'author': 'You' if mine else author or 'Teams user', 'when': w.get('datetime') if w else '',
                    'text': text, 'mine': mine})
    return out


def state_of(snap: dict) -> str:
    """'ok' | 'signed_out' | 'changed' for a read of the page. A sign-in host, or Teams' own signed-out landing, is signed out;
    a Teams page with neither its app shell nor a chat list is a page this code no longer knows."""
    host = (urlsplit(str(snap.get('url') or '')).hostname or '').lower()
    if host in SIGNIN_HOSTS or snap.get('signin'): return 'signed_out'
    if host != SITE and not host.endswith('.' + SITE): return 'changed'
    return 'ok' if snap.get('shell') or snap.get('list') else 'changed'


# ── the browser: agent-browser's session, driven over its DevTools socket (signin.Cdp) ──────────────────────────────────────
LIST_JS = r"""(() => {
  const q = s => [...document.querySelectorAll(s)];
  const list = q('[id^="chat-list-item_"],[data-tid="chat-list-item"]').slice(0, %d).map(e => e.outerHTML);
  const shell = !!document.querySelector('[data-tid="app-bar"],#app-bar,[data-tid="app-layout-area--nav"],[data-tid="chat-list"]');
  const signin = !!document.querySelector('[data-tid="signin-button"],a[href*="login.live.com"],button[data-tid="sign-in"]') && !shell;
  return {url: location.href, list, shell, signin};
})()"""

OPEN_JS = r"""(async (cid) => {
  const pick = () => document.getElementById('chat-list-item_' + cid) || document.querySelector(`[data-item-id="${CSS.escape(cid)}"]`);
  const el = pick(); if (!el) return {gone: true};
  el.click();
  const items = () => [...document.querySelectorAll('[data-tid="chat-pane-item"]')];
  const t0 = Date.now(); let seen = -1;
  while (Date.now() - t0 < %d) {
    await new Promise(r => setTimeout(r, 400));
    const n = items().length;
    if (n && n === seen && (location.href.includes(encodeURIComponent(cid)) || location.href.includes(cid) || el.getAttribute('aria-selected') === 'true')) break;
    seen = n;
  }
  const got = items();
  return {items: (got.length ? got : [...document.querySelectorAll('[data-tid="chat-pane-message"]')]).slice(-40).map(e => e.outerHTML)};
})(%s)"""

SEND_JS = r"""(async (text) => {
  const box = document.querySelector('[data-tid="ckeditor"] [contenteditable="true"],[data-tid="ckeditor"][contenteditable="true"],div[role="textbox"][contenteditable="true"]');
  if (!box) return {ok: false, why: 'no message box'};
  box.focus();
  text.split('\n').forEach((l, i) => { if (i) document.execCommand('insertLineBreak'); if (l) document.execCommand('insertText', false, l); });
  await new Promise(r => setTimeout(r, 300));
  const btn = document.querySelector('[data-tid="newMessageCommands-send"],button[name="send"],button[aria-label^="Send"]');
  if (!btn || btn.disabled) return {ok: false, why: 'no Send button'};
  const before = document.querySelectorAll('[data-tid="chat-pane-message"]').length;
  btn.click();
  const t0 = Date.now();
  while (Date.now() - t0 < %d) {
    await new Promise(r => setTimeout(r, 400));
    if (document.querySelectorAll('[data-tid="chat-pane-message"]').length > before && !box.textContent.trim()) return {ok: true};
  }
  return {ok: false, why: 'Teams did not show the message as sent'};
})(%s)"""


class Page:
    """The card's browser. One session per card; started on Teams' home with the owner's own restored cookies, and left up between
    reads like a WhatsApp bridge - a cold Chrome every few minutes costs more than one idle tab."""
    def __init__(self, cid): self.sid = sid_of(cid)

    def _conn(self):
        from . import browserview, signin
        if not browserview.installed(): raise RuntimeError(NO_BROWSER)
        if not browserview.state(self.sid, fresh=True).get('open') and not browserview.start(self.sid, HOME):
            raise RuntimeError('the browser for personal Teams did not start - press Sync now to try again')
        return signin.connect(self.sid)

    def chats(self) -> dict:
        c = self._conn()
        try:
            snap = c.js(LIST_JS % MAX_CHATS) or {}
            if state_of(snap) == 'changed' and not (urlsplit(str(snap.get('url') or '')).hostname or '').endswith(SITE):
                c.js(f'location.href = {json.dumps(HOME)}')           # it wandered (about:blank, a link the owner opened): home
            end = time.time() + LOAD_WAIT
            while state_of(snap) == 'changed' and time.time() < end:  # Teams is a heavy app: its shell paints seconds after load
                time.sleep(1); snap = c.js(LIST_JS % MAX_CHATS) or {}
            return snap
        finally: c.close()

    def open(self, chat: str) -> list:
        c = self._conn()
        try: return (c.js(OPEN_JS % (int(OPEN_WAIT * 1000), json.dumps(chat))) or {}).get('items') or []
        finally: c.close()

    def send(self, chat: str, text: str) -> dict:
        c = self._conn()
        try:
            got = c.js(OPEN_JS % (int(OPEN_WAIT * 1000), json.dumps(chat))) or {}
            if got.get('gone'): return {'ok': False, 'why': 'that chat is not in your Teams chat list'}
            return c.js(SEND_JS % (int(SEND_WAIT * 1000), json.dumps(text))) or {'ok': False, 'why': 'the page did not answer'}
        finally: c.close()


class SignedOut(RuntimeError): pass
class Changed(RuntimeError): pass

def _check(snap):
    st = state_of(snap)
    if st == 'signed_out': raise SignedOut(SIGNED_OUT)
    if st == 'changed': raise Changed(CHANGED)


def _after(when, since) -> bool:
    if not (when and since): return True
    try: return datetime.fromisoformat(when.replace('Z', '+00:00')).astimezone().replace(tzinfo=None) >= since
    except ValueError: return True


def poll(store, c, since=None, llm=None, file_only=False, page=None) -> int:
    """New messages of the card's personal Teams, filed. A chat is opened only when its list row moved since the last read (its
    preview or time) or says unread; within it, what follows the last message read - or, on a chat never read, what is newer
    than `since`. The external id is the dedupe that holds whatever this bookkeeping misses."""
    from .channels import _local, ingest_own_message
    from .ingest import ingest_message
    page = page or Page(c['ConnectorId'])
    snap = page.chats(); _check(snap)
    chats, seen, n = parse_chats(snap.get('list')), dict(_cfg(c).get('web_seen') or {}), 0
    for ch in chats:
        sig, was = f"{ch['when']}|{ch['preview']}", seen.get(ch['id']) or {}
        if not ch['unread'] and was.get('sig') == sig: continue
        msgs = parse_messages(page.open(ch['id']))
        ids = [m['id'] for m in msgs]
        new = msgs[ids.index(was['mid']) + 1:] if was.get('mid') in ids else [m for m in msgs if _after(m['when'], since)]
        conv = f"teams:live:{ch['id']}"
        for m in new:
            common = {'external_id': f"{conv}:{m['id']}", 'channel': 'teams', 'body': m['text'][:20000], 'conversation_id': conv,
                      'subject': f"Teams chat with {ch['title']}" if ch['dm'] else ch['title'], 'sent_at': _local(m['when']) if m['when'] else '',
                      'source_link': HOME, 'source_name': SITE, **({'mail_meta': {'dm': True}} if ch['dm'] else {})}
            if m['mine']:
                n += ingest_own_message(store, {**common, 'from_name': 'You', 'from_email': SITE}, 'your message in this chat - kept for context')
                continue
            # no address on a personal account's chat: the name is all Teams shows, so it is the sender's key
            out = ingest_message(store, {**common, 'from_name': m['author'], 'from_email': f"teams-live:{m['author'].lower()}"},
                                 llm=llm, file_only=file_only)
            n += out.get('status') != 'duplicate'
        seen[ch['id']] = {'sig': sig, **({'mid': ids[-1]} if ids else {k: v for k, v in was.items() if k == 'mid'})}
    store.merge_connector_config(c['ConnectorId'], {'web_seen': seen})
    return n


def probe(c, page=None) -> str:
    "The card's Test: the page read once, said in words. Raises SignedOut / Changed like the poll."
    snap = (page or Page(c['ConnectorId'])).chats(); _check(snap)
    k = len(parse_chats(snap.get('list')))
    return f"signed in to Teams (personal) - {plural(k, 'chat')} in the list"


def send(store, chat: str, body: str, connector_id=None, page=None) -> dict:
    """Type a reply into a personal chat and press Send - called only from the owner's own Send on the draft (outbound.send_teams)."""
    chat = str(chat).removeprefix('live:')
    if not page:
        cards = [x for x in store.connectors_by_type('teams') if x.get('Active') and personal(x)]
        c = next((x for x in cards if connector_id and x['ConnectorId'] == int(connector_id)), None) or next(iter(cards), None)
        if not c: raise RuntimeError('no personal Teams card is on - switch it on under Connections to answer this chat')
        page = Page(c['ConnectorId'])
    got = page.send(chat, body)
    if not got.get('ok'): raise RuntimeError(f"Teams (personal) did not take the reply: {got.get('why') or 'unknown'} - answer it in Teams")
    logger.info('teams personal: reply typed and sent through the browser')
    return {'channel': 'teams', 'chat': f'live:{chat}'}
