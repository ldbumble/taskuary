"""A FAKE WHATSAPP BRIDGE for the live walks: the owner's phone in front of the REAL app and the REAL AI (not a test: nothing here runs in CI).

It speaks the protocol taskuary/whatsapp/bridge.mjs serves and messengers._wa reads - the shapes are bridge.mjs's, field for field:
  GET  /status            connected, me, jid, seq, kept, code, filter, reconnect, loggedOut, admitted, turnedAway, unreadable ...
  GET  /messages?after=N  {seq, boot, messages, blockedChats} - every message after N, a new `boot` (and seq from 0) after a restart
  GET  /chats             the roster: the owner's own chat, and the people and groups his account sees (never message bodies)
  POST /filter /read /react /logout
  POST /send              {jid, text, poll?: {name, values}, quote?: {id, text}} - and its echo comes back on /messages as `taskuary: true`,
                          as Baileys hands the bridge every message the account sends (bridge.mjs keep()); a poll of fewer than two goes unsent
  POST /send-document     {jid, data (base64), mimetype, fileName, caption?}
Every request carries X-Bridge-Token: checked against <home>/wa-bridge.token once the app has minted it; a browser's Origin is refused.

What the walker does, on the same port (phone.mjs drives these):
  POST /owner   {text, quote?}            a line the owner types in his own chat
  POST /vote    {option, poll?}           a tap on a poll: option is its number from 1 or its words; poll the poll's id (default the newest).
                                          Newest and unspent: the option's words, poll: true. Spent or older: stalePoll (bridge.mjs
                                          polls.spent / polls.stale). A poll from before a bridge restart: nothing at all, as the real one.
  POST /media   {path | data, name?, mime?, caption?, kind?}   a picture, a file or a voice note he sends (kind image|doc|audio, else by mime)
  POST /restart                          the bridge restarted: a new boot id, seq from 0, its messages and polls forgotten
  POST /connected {on}                   the link to WhatsApp dropped (sends answer 503) or came back
  GET  /bubbles?after=N[&all=1]          everything the app sent, in order: {n, at, kind, text, poll, quote, unasked}; all=1 with his lines too
`unasked` marks a bubble sent with no line of his in the 30 minutes before it (remote_assistant.SESSION_MINS) - the phone's silence rule.
Invented people only (CLAUDE.md): the owner is Alex Doyle, +1 555 0100 100.
"""
import argparse, base64, itertools, json, mimetypes, os, threading, time, uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

ME_NUM = '15550100100'
ME = f'{ME_NUM}@s.whatsapp.net'
ROSTER = [  # the owner's own chat first; a colleague and a group so the card's chat list has the shape of a real one
    {'jid': ME, 'group': False, 'name': 'Alex Doyle (You)', 'people': None},
    {'jid': '15550100142@s.whatsapp.net', 'group': False, 'name': 'Gail Moreno', 'people': None},
    {'jid': '120363000000000042@g.us', 'group': True, 'name': 'Northwind ops', 'people': 5}]
MAX_KEPT, SESSION = 500, 30 * 60


class Bridge:
    def __init__(self, home=None, media=None):
        self.home, self.media = Path(home) if home else None, Path(media or Path.cwd() / 'fake-wa-media')
        self.lock, self.ids = threading.RLock(), itertools.count(1)
        self.bubbles, self.owner_at, self.filter, self.connected, self.reacts = [], 0.0, {'allDirect': False, 'jids': []}, True, []
        self.restart()

    def restart(self):
        with self.lock: self.boot, self.seq, self.msgs, self.polls = str(uuid.uuid4()), 0, [], {}   # polls: jid -> [{id, values, used}], newest first

    def mid(self): return f'3EB0FA{next(self.ids):010X}'

    def push(self, **m):
        with self.lock:
            self.seq += 1
            m = {'seq': self.seq, 'id': m.pop('id', None) or self.mid(), 'jid': ME, 'sender': ME, 'senderAlt': '', 'group': False, 'name': 'Alex Doyle',
                 'text': '', 'ts': int(time.time()), 'fromMe': True, 'quoted': '', 'key': {}, 'audio': '', 'mime': '', 'seconds': 0, 'voice': False,
                 'image': '', 'imageMime': '', 'doc': '', 'docMime': '', 'docName': '', 'taskuary': False, **m}
            m['key'] = {'remoteJid': m['jid'], 'id': m['id'], 'fromMe': m['fromMe']}
            self.msgs.append(m); del self.msgs[:-MAX_KEPT]
            return m

    def bubble(self, **b):
        with self.lock:
            now = time.time()
            b = {'n': len(self.bubbles) + 1, 'at': now, 'from': 'app', 'unasked': now - self.owner_at > SESSION, **b}
            self.bubbles.append(b); return b

    # ── the protocol ──
    def status(self):
        with self.lock:
            return {'connected': self.connected, 'me': 'Alex Doyle', 'jid': f'{ME_NUM}:7@s.whatsapp.net', 'qr': '', 'pairingCode': '', 'seq': self.seq,
                    'kept': len(self.msgs), 'code': 'fake', 'filter': self.filter, 'reconnect': {'paused': False, 'attempt': 0, 'at': 0},
                    'loggedOut': False, 'admitted': len(self.filter.get('jids') or []), 'turnedAway': 0, 'lidMapped': 0,
                    'lastInboundAt': int(self.owner_at * 1000) or None, 'lastFailure': None, 'contactSync': {}, 'unreadable': {}}

    def messages(self, after):
        with self.lock: return {'seq': self.seq, 'boot': self.boot, 'messages': [m for m in self.msgs if m['seq'] > after], 'blockedChats': []}

    def chats(self):
        last = {m['jid']: m['ts'] for m in self.msgs}
        return {'chats': [{**r, 'last': last.get(r['jid'], 0), 'n': sum(m['jid'] == r['jid'] for m in self.msgs), 'snippet': ''} for r in ROSTER]}

    def send(self, b):
        jid, text, poll, quote = b.get('jid'), b.get('text'), b.get('poll') or {}, b.get('quote')
        if not self.connected: return 503, {'error': 'not connected to WhatsApp'}
        if not jid or not text: return 400, {'error': 'jid and text are required'}
        m = self.push(jid=jid, text=text, taskuary=True)                    # the echo Baileys hands back for what the account sent
        seen, values = set(), []
        for v in poll.get('values') or []:                                  # poll.mjs pollValues: distinct, non-empty, 100 chars, 12 at most
            s = str(v or '').strip()[:100]
            if s and s not in seen: seen.add(s); values.append(s)
        values, pid = values[:12], ''
        self.bubble(kind='text', jid=jid, text=text, id=m['id'], quote=quote, poll=None)
        if len(values) > 1:
            p = self.push(jid=jid, taskuary=True)
            pid = p['id']
            with self.lock: self.polls[jid] = [{'id': pid, 'values': values, 'used': False}, *self.polls.get(jid, [])][:9]
            self.bubble(kind='poll', jid=jid, text=str(poll.get('name') or 'Pick one')[:255], id=pid, poll=values)
        elif values: self.bubble(kind='note', jid=jid, text=f'(a poll of one choice was not sent: {values[0]!r})', poll=None)
        return 200, {'ok': True, 'id': m['id'], 'poll': pid}

    def send_document(self, b):
        if not self.connected: return 503, {'error': 'not connected to WhatsApp'}
        if not b.get('jid') or not b.get('data') or not b.get('fileName'): return 400, {'error': 'jid, data and fileName are required'}
        data = base64.b64decode(b['data'])
        if not data: return 400, {'error': 'the file is empty'}
        self.media.mkdir(parents=True, exist_ok=True)
        f = self.media / f"out-{next(self.ids)}-{os.path.basename(b['fileName'])}"; f.write_bytes(data)
        m = self.push(jid=b['jid'], taskuary=True)
        self.bubble(kind='doc', jid=b['jid'], text=b.get('caption') or '', id=m['id'], file=str(f), name=b['fileName'], mime=b.get('mimetype'), bytes=len(data), poll=None)
        return 200, {'ok': True, 'id': m['id'], 'bytes': len(data)}

    def react(self, b):
        if not self.connected: return 503, {'error': 'not connected to WhatsApp'}
        if not b.get('id'): return 400, {'error': 'id is required'}
        hit = any(m['id'] == b['id'] for m in self.msgs)
        if hit: self.reacts.append({'id': b['id'], 'emoji': b.get('emoji') or '\U0001F44D', 'at': time.time()})
        return 200, {'ok': True, 'reacted': int(hit)}

    # ── the walker ──
    def owner(self, b):
        self.owner_at = time.time()
        q = b.get('quote')
        m = self.push(text=str(b.get('text') or ''), quoted=str(q or ''))
        self.bubbles.append({'n': len(self.bubbles) + 1, 'at': time.time(), 'from': 'owner', 'kind': 'text', 'text': m['text'], 'id': m['id']})
        return 200, {'ok': True, 'id': m['id'], 'seq': m['seq']}

    def vote(self, b):
        with self.lock:
            ps = self.polls.get(ME) or []
            p = next((x for x in ps if x['id'] == b['poll']), None) if b.get('poll') else (ps[0] if ps else None)
            if not p: return 404, {'error': 'no poll of this bridge run to tap - one sent before a restart answers nothing, as on the real bridge'}
            o = b.get('option')
            word = p['values'][int(o) - 1] if str(o).isdigit() and 0 < int(o) <= len(p['values']) else next((v for v in p['values'] if v == o), None) \
                or next((v for v in p['values'] if str(o).lower() and v.lower().startswith(str(o).lower())), None)
            if word is None: return 400, {'error': f'no option {o!r} among {p["values"]}'}
            newest = p is ps[0]
            self.owner_at = time.time()
            if newest and not p['used']:
                p['used'] = True; m = self.push(text=word, poll=True)
            else: m = self.push(text='', poll=True, stalePoll=True, **({'spentPoll': True} if newest else {}))
        self.bubbles.append({'n': len(self.bubbles) + 1, 'at': time.time(), 'from': 'owner', 'kind': 'vote', 'text': word, 'poll': p['id'],
                             'stale': not newest, 'spent': newest and m.get('stalePoll', False)})
        return 200, {'ok': True, 'id': m['id'], 'picked': word, 'stale': bool(m.get('stalePoll'))}

    def media_in(self, b):
        src = b.get('path')
        data = Path(src).read_bytes() if src else base64.b64decode(b.get('data') or '')
        if not data: return 400, {'error': 'path or data is required'}
        name = b.get('name') or (os.path.basename(src) if src else 'file.bin')
        mime = b.get('mime') or mimetypes.guess_type(name)[0] or 'application/octet-stream'
        kind = b.get('kind') or ('image' if mime.startswith('image/') else 'audio' if mime.startswith('audio/') else 'doc')
        self.media.mkdir(parents=True, exist_ok=True)
        mid = self.mid(); f = self.media / f'{mid}{Path(name).suffix or ".bin"}'; f.write_bytes(data)
        self.owner_at = time.time()
        fields = {'image': {'image': str(f), 'imageMime': mime}, 'audio': {'audio': str(f), 'mime': mime, 'seconds': 4, 'voice': True},
                  'doc': {'doc': str(f), 'docMime': mime, 'docName': name}}[kind]
        m = self.push(id=mid, text=str(b.get('caption') or ''), **fields)
        self.bubbles.append({'n': len(self.bubbles) + 1, 'at': time.time(), 'from': 'owner', 'kind': kind, 'text': m['text'], 'name': name, 'id': mid})
        return 200, {'ok': True, 'id': mid, 'file': str(f)}

    def token_ok(self, got):
        p = self.home / 'wa-bridge.token' if self.home else None
        if not p or not p.exists(): return bool(got)            # the app mints its token on its first call; until then any is taken
        return got == p.read_text(encoding='utf-8').strip()


def handler(br: Bridge):
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a): pass

        def reply(self, code, obj):
            body = json.dumps(obj).encode()
            self.send_response(code); self.send_header('content-type', 'application/json'); self.send_header('content-length', str(len(body)))
            self.end_headers(); self.wfile.write(body)

        def body(self):
            n = int(self.headers.get('content-length') or 0)
            return json.loads(self.rfile.read(n) or b'{}') if n else {}

        def go(self, method):
            u = urlparse(self.path); p, q = u.path, parse_qs(u.query)
            walker = p in ('/owner', '/vote', '/media', '/restart', '/connected', '/bubbles', '/reacts')
            if self.headers.get('origin') is not None: return self.reply(403, {'error': 'browsers may not call the bridge'})
            if not walker and not br.token_ok(self.headers.get('x-bridge-token')): return self.reply(401, {'error': 'bridge token missing or wrong'})
            try:
                if method == 'GET':
                    if p == '/status': return self.reply(200, br.status())
                    if p == '/messages': return self.reply(200, br.messages(int((q.get('after') or ['0'])[0] or 0)))
                    if p == '/chats': return self.reply(200, br.chats())
                    if p == '/bubbles':
                        after, every = int((q.get('after') or ['0'])[0] or 0), (q.get('all') or ['0'])[0] == '1'
                        return self.reply(200, {'bubbles': [b for b in br.bubbles if b['n'] > after and (every or b['from'] == 'app')], 'n': len(br.bubbles)})
                    if p == '/reacts': return self.reply(200, {'reacts': br.reacts})
                    return self.reply(404, {'error': 'unknown path'})
                b = self.body()
                if p == '/filter': br.filter = {'allDirect': bool(b.get('allDirect')), 'jids': list(b.get('jids') or [])}; return self.reply(200, {'ok': True, 'filter': br.filter})
                if p == '/logout': return self.reply(200, {'ok': True, 'unlinked': False})
                if p == '/read':
                    if not br.connected: return self.reply(503, {'error': 'not connected to WhatsApp'})
                    return self.reply(200, {'ok': True, 'marked': sum(m['id'] in set(b.get('ids') or []) for m in br.msgs)})
                route = {'/send': br.send, '/send-document': br.send_document, '/react': br.react, '/owner': br.owner, '/vote': br.vote, '/media': br.media_in}
                if p in route: return self.reply(*route[p](b))
                if p == '/restart': br.restart(); return self.reply(200, {'ok': True, 'boot': br.boot})
                if p == '/connected': br.connected = bool(b.get('on', True)); return self.reply(200, {'ok': True, 'connected': br.connected})
                self.reply(404, {'error': 'unknown path'})
            except Exception as e: self.reply(500, {'error': str(e)})

        def do_GET(self): self.go('GET')
        def do_POST(self): self.go('POST')
    return H


def serve(port=0, home=None, media=None):
    "Start it on a thread; returns (server, bridge) - server.server_address[1] is the port."
    br = Bridge(home, media)
    srv = ThreadingHTTPServer(('127.0.0.1', port), handler(br)); srv.daemon_threads = True
    threading.Thread(target=srv.serve_forever, daemon=True, name='fake-wa-bridge').start()
    return srv, br


if __name__ == '__main__':
    a = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    a.add_argument('--port', type=int, default=0); a.add_argument('--home'); a.add_argument('--media')
    o = a.parse_args()
    srv, _ = serve(o.port, o.home, o.media)
    print(f'FAKE_WA_READY http://127.0.0.1:{srv.server_address[1]}', flush=True)
    try: threading.Event().wait()
    except KeyboardInterrupt: pass
