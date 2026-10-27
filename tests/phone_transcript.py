"""A fake phone in front of the doorway's real roads - what the phone SHOWS, bubble by bubble.

Telegram: only the Bot API (messengers.tg) is faked; a typed line or a button tap goes in through getUpdates and
messengers.poll_telegram, and each sendMessage is a bubble with its buttons. WhatsApp: only the bridge (messengers._wa)
is faked; poll_whatsapp reads /messages and wa_send posts /send with its poll. The rest - remote_assistant, concierge,
funnel - runs as it does for the owner. The brain is a scripted stand-in or None (no AI connected). Invented people only."""
import itertools, json, time
from unittest import mock

from taskuary import concierge, funnel, ingest, messengers, remote_assistant as ra, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory

TG_CHAT, JID = '900100', '15550100100@s.whatsapp.net'
ME = {'id': 4242, 'is_bot': False, 'first_name': 'Alex', 'last_name': 'Doyle'}
GAIL, RAY = ('Gail Moreno', 'gmoreno@northwind.example'), ('Ray Colton', 'rcolton@northwind.example')


class _Sync:
    """The doorway answers on a thread of its own; here it answers before the poll returns."""
    def __init__(self, target=None, args=(), kwargs=None, **k): self.t, self.a, self.k = target, args, kwargs or {}
    def start(self): self.t(*self.a, **self.k)
    def join(self, *a): pass


def call(_k, **params): return 'CALL: ' + json.dumps({'kind': _k, 'params': params})


class Phone:
    """`brain`: f(said) -> the model's answer, or None for no AI. `channel`: 'telegram' or 'whatsapp'."""
    def __init__(self, channel='telegram', brain=None, store=None):
        funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
        ra._ANSWERED.clear(); ra._talked.clear()
        self.ch, self.brain_fn = channel, brain
        self.s = s = store or MemoryStore()
        for k in ('calendar_enabled', 'coding_auto_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
        if brain: s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude'}))
        cid = s.get_connector_by_type(channel)['ConnectorId']
        self.chat = TG_CHAT if channel == 'telegram' else JID
        s.save_connector({'ConnectorId': cid, 'Active': 1, 'Roles': 'trigger,tool', 'Secret': 'tok',
                          'ConfigJson': json.dumps({'assistant_chat': self.chat, 'me_number': '15550100100'})}, 'test')
        s.set_setting('phone_assistant', '1', 'test')
        ra.owner_spoke(s, channel, self.chat)          # a transcript is a conversation the owner has open (in_session)
        self.cid, self.f = cid, Factory(s)
        self.f.actor = 'triage'
        self.ids, self.queue, self.bubbles, self.msgs, self.seq = itertools.count(500), [], [], {}, 0
        # files that reached the phone as documents: (chat, file name, bytes, mime, caption); `doc_fails` makes the next upload fail
        self.docs, self.doc_fails = [], None
        from taskuary import server, wabridge
        self._p = [mock.patch.object(messengers, 'tg', side_effect=self._tg), mock.patch.object(messengers, '_wa', side_effect=self._wa),
                   mock.patch.object(messengers, 'tg_upload', side_effect=self._tg_upload),
                   mock.patch.object(ra.threading, 'Thread', _Sync), mock.patch.object(ingest, '_spawn'),
                   mock.patch.object(concierge, 'brain', side_effect=lambda *a, **k: self._brain() if self.brain_fn else None),
                   mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(server, 'store', s),
                   mock.patch.object(wabridge, 'ready', lambda *a, **k: None)]
        for p in self._p: p.start()

    def close(self):
        for p in reversed(self._p): p.stop()

    def ready(self):
        """The rail as the running app keeps it: membership reconciled, canonical reads on."""
        from datetime import datetime
        now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        self.s.reconcile_processing_membership(fixed_now=now); funnel.invalidate()
        self.s.activate_processing_reads(fixed_now=now, live_state=[])
        self.s.reconcile_processing_membership(fixed_now=now); funnel.invalidate()

    def _brain(self):
        def llm(system, user, **kw):
            asked = [l[len(concierge.OWNER_SAYS):].strip() for l in str(user or '').splitlines() if l.startswith(concierge.OWNER_SAYS)]
            return self.brain_fn(asked[-1] if asked else str(user or '')[-300:])
        return llm

    # ── the transports ──
    def _tg(self, tok, method, **p):
        if method == 'sendMessage':
            mid = next(self.ids)
            btns = [r[0]['text'] for r in (p.get('reply_markup') or {}).get('inline_keyboard') or []]
            self.msgs[mid] = btns; self.bubbles.append((p['text'], btns)); return {'message_id': mid}
        if method == 'getUpdates': q, self.queue = self.queue, []; return q
        if method == 'getFile': return {'file_path': 'voice/file_1.oga'}
        if method == 'setMessageReaction': self.reacted = getattr(self, 'reacted', 0) + 1
        return True

    def _tg_upload(self, tok, method, files, **p):
        assert method == 'sendDocument', method
        if self.doc_fails: raise RuntimeError(f'telegram sendDocument: {self.doc_fails}')
        name, data, mime = files['document']
        self.docs.append((str(p['chat_id']), name, data, mime, p.get('caption'))); return {'message_id': next(self.ids)}

    def _wa(self, c, path, body=None, *a, **k):
        if path.startswith('/messages'):
            q, self.queue = self.queue, []; self.seq += len(q); return {'seq': self.seq, 'messages': q}
        if path == '/send-document':
            if self.doc_fails: raise RuntimeError(f'bridge /send-document failed (503): {self.doc_fails}')
            import base64
            self.docs.append((body['jid'], body['fileName'], base64.b64decode(body['data']), body['mimetype'], body.get('caption')))
            return {'ok': True, 'id': f'o{next(self.ids)}'}
        if path == '/send':
            self.bubbles.append((body['text'], list((body.get('poll') or {}).get('values') or []))); return {'ok': True, 'id': f'o{next(self.ids)}'}
        return {'ok': True}

    def _poll(self):
        c = self.s.get_connector(self.cid, with_secret=True)
        (messengers.poll_telegram if self.ch == 'telegram' else messengers.poll_whatsapp)(self.s, c, [], llm=None)

    # ── what the owner does; each returns the bubbles it brought ──
    def _took(self, go):
        n = len(self.bubbles); go(); return self.bubbles[n:]

    def type(self, text):
        mid = next(self.ids)
        if self.ch == 'telegram':
            self.queue.append({'update_id': mid, 'message': {'message_id': mid, 'text': text, 'date': int(time.time()),
                               'chat': {'id': int(self.chat), 'type': 'private'}, 'from': ME}})
        else: self.queue.append({'id': f'in{mid}', 'jid': self.chat, 'text': text, 'fromMe': True, 'poll': False, 'ts': time.time()})
        return self._took(self._poll)

    def voice(self):
        """A Telegram voice note: the file comes down (faked), and voice.transcribe hears it - or says why it cannot."""
        mid = next(self.ids)
        self.queue.append({'update_id': mid, 'message': {'message_id': mid, 'date': int(time.time()), 'from': ME,
                           'voice': {'file_id': 'VOICE1', 'duration': 4, 'mime_type': 'audio/ogg'}, 'chat': {'id': int(self.chat), 'type': 'private'}}})
        with mock.patch.object(messengers.requests, 'get', return_value=mock.Mock(content=b'OggS fake')): return self._took(self._poll)

    def choices(self):
        return next((b for _t, b in reversed(self.bubbles) if b), [])

    def tap(self, label):
        """The choice under the newest message whose words start with `label`."""
        if self.ch == 'telegram':
            mid = max(m for m, b in self.msgs.items() if b) if any(self.msgs.values()) else None
            btns = self.msgs.get(mid) or []
        else: btns = self.choices()
        hit = next((i for i, b in enumerate(btns) if b == label), None)
        if hit is None: hit = next((i for i, b in enumerate(btns) if b.lower().startswith(label.lower())), None)
        assert hit is not None, f'no choice {label!r} among {btns}'
        mid2 = next(self.ids)
        if self.ch == 'telegram':
            self.queue.append({'update_id': mid2, 'callback_query': {'id': f'q{mid2}', 'data': f'p{hit}', 'from': ME,
                               'message': {'message_id': mid, 'chat': {'id': int(self.chat), 'type': 'private'}}}})
        else: self.queue.append({'id': f'in{mid2}', 'jid': self.chat, 'text': btns[hit], 'fromMe': True, 'poll': True, 'ts': time.time()})
        return self._took(self._poll)

    def push(self, fn):
        """Something Taskuary sends on its own - the morning line, a promise kept."""
        return self._took(fn)

    def opener(self):
        """The day's opener, switched on and sent - the walk's front door."""
        self.s.set_setting(ra.MORNING_KEY, '1', 't'); self.s.set_setting(ra.MORNING_AT, '', 't'); ra._talked.clear()
        return self.push(lambda: ra.morning_line(self.s, force=True))

    def walk(self):
        """The opener, then Walk me through my tasks tapped under it: the first card."""
        self.opener(); return self.tap('Walk me through my tasks')


def text_of(bubbles) -> str: return '\n\n'.join(t for t, _b in bubbles)
