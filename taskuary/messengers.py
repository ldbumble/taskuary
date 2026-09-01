"""Telegram and WhatsApp as inbound channels - the personal-messenger half of the funnel.

Telegram is light: a bot token and plain HTTPS (getUpdates / sendMessage), so it is built in
entirely. WhatsApp has no sanctioned API for a personal account - the working road is Baileys,
a Node library speaking the WhatsApp Web protocol - so Taskuary does NOT embed it: a small
bridge script (taskuary/whatsapp/bridge.mjs) runs beside the app with its own npm install, and
this module just polls the bridge over localhost HTTP. Heavy dependency, separate install;
Taskuary's side is ~40 lines either way.

Both are CHAT: messages land with a conversation id per chat, replies go back into the same
chat, and the responder already knows not to sign chat messages.
"""
import base64, json, os
import requests
from loguru import logger

TG_API = 'https://api.telegram.org'
TG_LIMIT = 25                # messages per poll, like the other channels
WA_URL = 'http://127.0.0.1:8977'   # the bridge's default; override in the connector config


def _cfg(c): return json.loads(c.get('ConfigJson') or '{}')


# ── Telegram ─────────────────────────────────────────────────────────────────────────────
def tg(token: str, method: str, **params):
    r = requests.post(f'{TG_API}/bot{token}/{method}', json=params, timeout=30)
    j = r.json()
    if not j.get('ok'): raise RuntimeError(f"telegram {method}: {j.get('description') or r.status_code}")
    return j['result']


def tg_test(store, c) -> str:
    """getMe proves the token; a '*' source is added so the poller has something to walk -
    it is a LISTENING marker only, never an admit-everything: a bot is public, and anyone
    who finds it can message it. Chats announce themselves in getUpdates and are registered
    OFF under Sources with their chat id; only the ones the owner flips on become work."""
    if not c.get('Secret'): raise RuntimeError('no bot token saved - paste the token @BotFather gave you under Credentials')
    me = tg(c['Secret'], 'getMe')
    # the bot's handle is part of who the owner is on Telegram (About you reads it back)
    if me.get('username'): store.set_connector_config(c['ConnectorId'], {**_cfg(c), 'bot_username': me['username']})
    if not any(s['Channel'] == 'telegram' for s in store.list_sources(active_only=False)):
        store.save_source({'Channel': 'telegram', 'Address': '*', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'connector-test')
    return (f"authenticated as @{me.get('username')} - message the bot (or add it to a group), Sync, "
            f"and the chat appears under Sources with its chat id, OFF. Flip on the chats that are "
            f"yours; every other chat stays out (a public bot can be messaged by anyone)")


def _tg_photo(token: str, m: dict) -> list:
    """The largest rendition of an attached photo/document, shaped like a Graph fileAttachment
    so channels.save_attachments and vision reuse the one pipeline."""
    out = []
    for kind, meta in (('photo', (m.get('photo') or [])[-1:]), ('document', [m['document']] if m.get('document') else [])):
        for f in meta:
            try:
                path = tg(token, 'getFile', file_id=f['file_id']).get('file_path') or ''
                data = requests.get(f'{TG_API}/file/bot{token}/{path}', timeout=60).content
                name = f.get('file_name') or (path.rsplit('/', 1)[-1] or f'{kind}.jpg')
                ct = f.get('mime_type') or ('image/jpeg' if kind == 'photo' else 'application/octet-stream')
                out.append({'id': f['file_id'][:60], 'name': name, 'contentType': ct,
                            'size': len(data), 'contentBytes': base64.b64encode(data).decode(),
                            'isInline': kind == 'photo'})
            except Exception as e:
                logger.warning(f'telegram file fetch failed: {e}')
    return out


def _tg_file(token: str, f: dict, fallback_name: str):
    """One Telegram file by file_id -> (bytes, name, mime), or None with a warning."""
    try:
        path = tg(token, 'getFile', file_id=f['file_id']).get('file_path') or ''
        data = requests.get(f'{TG_API}/file/bot{token}/{path}', timeout=60).content
        name = f.get('file_name') or (path.rsplit('/', 1)[-1] or fallback_name)
        return data, name, (f.get('mime_type') or 'audio/ogg').split(';')[0]
    except Exception as e:
        logger.warning(f'telegram file fetch failed: {e}'); return None


def poll_telegram(store, c, sources: list, llm=None, file_only=False) -> int:
    """getUpdates with the offset watermark kept on the connector - Telegram's own cursor, so a
    restart never re-ingests.

    Only chats the owner switched ON become work. A bot is PUBLIC - anyone who finds it can
    message it, and 'blank takes every chat' was an open door for spam-as-tasks. An unknown
    chat is registered instead: it shows up under Sources with its chat id, off, and flipping
    it on admits it from the next message onward. That registration is also how you FIND a
    chat id - message the bot once and read it off the card."""
    from datetime import datetime
    from .channels import images_for_triage, save_attachments
    from .ingest import ingest_message
    tok, cfg = c['Secret'], _cfg(c)
    if not tok: return 0
    # every telegram source ever seen, on or off - a report source in the same list (the
    # seeded Morning digest) must never become a chat-id nothing can match
    known = {s['Address']: s for s in store.list_sources(active_only=False)
             if s.get('Channel') == 'telegram' and s.get('Address')}
    want = {a for a, s in known.items() if a != '*' and s.get('Active')}
    ups = tg(tok, 'getUpdates', offset=int(cfg.get('tg_offset') or 0), limit=TG_LIMIT,
             allowed_updates=['message'])
    n = 0
    for u in ups:
        m = u.get('message') or {}
        chat, frm = m.get('chat') or {}, m.get('from') or {}
        cid = str(chat.get('id') or '')
        if not cid or frm.get('is_bot'): continue
        # a reply in the NOTIFY chat may be a verdict on a pinged review ("approve") - it is
        # handled before the approve-first filter, so the notify chat never needs a source
        # row and the owner's verdicts never become work (see phone.py)
        from . import phone
        if phone.intercept(store, 'telegram', cid, m.get('text') or m.get('caption') or '',
                           (m.get('reply_to_message') or {}).get('text')):
            continue
        if cid not in want:
            if cid not in known:      # first sight of this chat: register it OFF, ingest nothing
                title = chat.get('title') or ' '.join(x for x in (frm.get('first_name'), frm.get('last_name')) if x) \
                        or frm.get('username') or 'chat'
                store.save_source({'Channel': 'telegram', 'Address': cid, 'ConnectorId': c['ConnectorId'],
                                   'Active': 0, 'Owner': f'discovered: {title}'[:80]}, 'telegram-poll')
                known[cid] = {'Address': cid, 'Active': 0}
                logger.info(f'telegram: chat {cid} ({title}) discovered - registered OFF under Sources')
            continue
        text = m.get('text') or m.get('caption') or ''
        atts = _tg_photo(tok, m) if (m.get('photo') or m.get('document')) else []
        # a voice message (or an audio file with no caption): fetched, transcribed if a voice
        # connector exists, filed with the reason if not - and attached either way (voice.py)
        transcribed, why = True, ''
        v = m.get('voice') or (m.get('audio') if not text else None)
        if v and not text:
            from . import voice
            got = _tg_file(tok, v, 'voice.ogg')
            if got:
                data, name, mime = got
                text, transcribed, why = voice.note_body(store, data, mime, name, v.get('duration') or 0, 'Telegram')
                atts.append({'id': v['file_id'][:60], 'name': name, 'contentType': mime, 'size': len(data),
                             'contentBytes': base64.b64encode(data).decode()})
        if not text and not atts: continue
        who = ' '.join(x for x in (frm.get('first_name'), frm.get('last_name')) if x) or frm.get('username') or 'someone'
        out = ingest_message(store, file_only=file_only or not transcribed, msg={
            'external_id': f"telegram:{cid}:{m.get('message_id')}", 'channel': 'telegram',
            'subject': None, 'body': text or '(no text - see the attachment)',
            'from_name': who, 'from_email': f"@{frm['username']}" if frm.get('username') else None,
            'conversation_id': f'telegram:{cid}',
            'sent_at': datetime.fromtimestamp(m.get('date') or 0).strftime('%Y-%m-%d %H:%M:%S'),
            'source_name': chat.get('title') or who,
            'images': images_for_triage(store, atts),
            **({'file_reason': f'voice note - not transcribed: {why[:160]}'} if not transcribed else {})}, llm=llm)
        n += out['status'] != 'duplicate'
        if atts and out.get('message_id') and out['status'] != 'duplicate':
            try: save_attachments(store, out['message_id'], atts, f"telegram:{cid}:{m.get('message_id')}")
            except Exception as e: logger.warning(f'telegram attachments failed: {e}')
    if ups:
        store.set_connector_config(c['ConnectorId'], {**cfg, 'tg_offset': ups[-1]['update_id'] + 1})
    return n


def tg_send(store, chat_id: str, body: str, connector_id=None) -> dict:
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else \
        store.get_connector_by_type('telegram', with_secret=True)
    if c and c.get('Type') != 'telegram': c = None
    if not (c and c.get('Secret')): raise RuntimeError('the Telegram connection is not set up')
    tg(c['Secret'], 'sendMessage', chat_id=int(chat_id), text=body[:4000])
    return {'channel': 'telegram', 'chat': chat_id}


# ── WhatsApp (via the Baileys bridge) ────────────────────────────────────────────────────
def _wa(c, path, body=None):
    url = (_cfg(c).get('bridge_url') or WA_URL).rstrip('/')
    try:
        r = requests.post(f'{url}{path}', json=body, timeout=20) if body is not None \
            else requests.get(f'{url}{path}', timeout=20)
    except requests.ConnectionError:
        raise RuntimeError(f'the WhatsApp bridge is not running at {url} - start it: '
                           f'cd taskuary/whatsapp && npm install && node bridge.mjs')
    if r.status_code >= 300: raise RuntimeError(f'bridge {path} failed ({r.status_code}): {r.text[:200]}')
    return r.json()


def wa_test(store, c) -> str:
    st = _wa(c, '/status')
    if not st.get('connected'):
        raise RuntimeError('bridge is running but WhatsApp is not paired yet - '
                           + (f"enter code {st['pairingCode']} on your phone (Linked devices)" if st.get('pairingCode')
                              else 'scan the QR the bridge printed in its own terminal'))
    # no catch-all is created here: only the chats the owner (or the setup agent) adds come in.
    # '*' - every direct chat - is a row they add themselves. A '*' that appeared by itself was a
    # timeline full of chats nobody asked for (the owner, 2026-08-30).
    return f"paired as {st.get('me') or 'your account'} - add the chats you want under Chat JIDs; they flow in on the next sync"


def wa_status(c) -> dict:
    """The bridge's state, with the pairing QR drawn as an SVG the card can show. Pairing used to
    mean reading a QR off the bridge's own terminal or typing a phone number into a chat; WhatsApp
    rotates the QR every ~20s, so the card polls this and redraws - nobody relays anything."""
    st = _wa(c, '/status')
    jid = str(st.get('jid') or '')
    out = {'connected': bool(st.get('connected')), 'me': st.get('me') or '', 'jid': jid,
           'phone': ('+' + jid.split('@')[0].split(':')[0]) if jid and jid.split(':')[0].split('@')[0].isdigit() else '',   # the paired number, from the account jid
           'pairing_code': st.get('pairingCode') or '', 'qr_svg': ''}
    if st.get('qr') and not out['connected']:
        import segno
        out['qr_svg'] = segno.make(st['qr'], error='m').svg_data_uri(scale=5, border=2, dark='#1e1e2e', light='#ffffff')
    return out


def wa_chats(c) -> list:
    """The chats the bridge has seen since it started - one row per JID, newest first. This is
    how the owner finds the JID of "only this group": there is no directory to browse, the JID
    shows up the moment someone writes in the chat, and the card offers it as a source."""
    from datetime import datetime
    out = _wa(c, '/messages?after=0')
    by = {}
    for m in out.get('messages', []):
        jid = m.get('jid') or ''
        if not jid or jid.endswith('@broadcast'): continue
        r = by.setdefault(jid, {'jid': jid, 'group': bool(m.get('group')), 'name': '', 'n': 0, 'last': 0, 'snippet': ''})
        r['n'] += 1
        if not m.get('fromMe') and m.get('name'): r['name'] = m['name']     # the other side's push name, never ours
        if (m.get('ts') or 0) >= r['last']: r['last'], r['snippet'] = m.get('ts') or 0, (m.get('text') or '')[:80]
    rows = sorted(by.values(), key=lambda r: -r['last'])
    for r in rows: r['last'] = datetime.fromtimestamp(r['last']).strftime('%Y-%m-%d %H:%M') if r['last'] else ''
    return rows


def _read_media(path: str):
    """The bridge wrote a voice note or a photo to disk beside itself; same machine, so it is
    read straight off. Missing or oversized (over 25 MB - every transcription and vision API's
    ceiling) is a warning, not a failed poll."""
    try:
        if os.path.getsize(path) > 25 * 1024 * 1024: logger.warning(f'media too large to read: {path}'); return None
        with open(path, 'rb') as f: return f.read()
    except OSError as e:
        logger.warning(f'could not read the media the bridge saved ({path}): {e}'); return None


def poll_whatsapp(store, c, sources: list, llm=None, file_only=False) -> int:
    """The bridge keeps a sequence number per message; ours is on the connector, so nothing is
    read twice and a bridge restart just resets both to live traffic."""
    import os
    from datetime import datetime
    from .ingest import ingest_message
    from .channels import images_for_triage, save_attachments
    from . import voice
    cfg = _cfg(c)
    # '*' means every DIRECT chat and is itself opt-in (never created by default); a GROUP comes in
    # only when its JID is added as a source. Both earlier readings were wrong ways: '*' silently
    # dropped meant a listed group muted every DM, and '*' as admit-everything flooded the timeline
    # with every group the owner is in.
    srcs = [s for s in sources if s.get('Channel', 'whatsapp') == 'whatsapp' and s.get('Address')]
    star = any(s['Address'] == '*' for s in srcs)
    want = {s['Address'] for s in srcs if s['Address'] != '*'}
    out = _wa(c, f"/messages?after={int(cfg.get('wa_seq') or 0)}")
    n, took = 0, []
    from . import phone
    for m in out.get('messages', []):
        jid = m.get('jid') or ''
        if not jid: continue
        # the WhatsApp bridge is the owner's OWN account, so a verdict they type in the
        # notify chat arrives as fromMe - intercept runs before that filter (phone.py also
        # recognizes and swallows our own pings echoing back through the bridge)
        if (m.get('text') or '').strip() and phone.intercept(store, 'whatsapp', jid, m['text'], m.get('quoted')):
            continue
        if m.get('fromMe'): continue
        if m.get('group') or jid.endswith('@g.us'):
            if jid not in want: continue                      # groups are opt-in, always
        elif not (star or jid in want): continue              # direct chats ride on '*'
        body, audio, image = (m.get('text') or '').strip(), m.get('audio'), m.get('image')
        doc = m.get('doc')
        # a DOCUMENT counts. Without it in this list a .docx with no caption was dropped whole -
        # the owner watched a file they had just been sent never reach the Timeline (2026-09-01).
        if not body and not audio and not image and not doc: continue
        # a voice note lands like any message: transcribed when a voice connector exists, and
        # otherwise filed with the reason and the audio attached (voice.py) - it never vanishes
        atts, transcribed, why = [], True, ''
        if audio and not body:
            data = _read_media(audio)
            if data is None: continue
            mime, name = (m.get('mime') or 'audio/ogg').split(';')[0], os.path.basename(audio)
            body, transcribed, why = voice.note_body(store, data, mime, name, m.get('seconds') or 0, 'WhatsApp')
            atts.append({'id': f"voice:{m.get('id')}", 'name': name, 'contentType': mime, 'size': len(data),
                         'contentBytes': base64.b64encode(data).decode()})
        # ...and a PHOTO is evidence, not decoration: it rides into triage as an image the model
        # can see, the same way a Telegram photo already does. Without it "words look weird" is a
        # sentence about nothing and gets filed as nothing (the owner, 2026-08-31).
        if image:
            data = _read_media(image)
            if data is not None:
                mime, name = (m.get('imageMime') or 'image/jpeg').split(';')[0], os.path.basename(image)
                atts.append({'id': f"image:{m.get('id')}", 'name': name, 'contentType': mime, 'size': len(data),
                             'contentBytes': base64.b64encode(data).decode(), 'isInline': True})
        # a file is the message when nothing was typed with it
        if doc:
            data = _read_media(doc)
            if data is not None:
                mime = (m.get('docMime') or 'application/octet-stream').split(';')[0]
                name = m.get('docName') or os.path.basename(doc)
                atts.append({'id': f"doc:{m.get('id')}", 'name': name, 'contentType': mime,
                             'size': len(data), 'contentBytes': base64.b64encode(data).decode()})
        ext_id = f"whatsapp:{jid}:{m.get('id')}"
        r = ingest_message(store, file_only=file_only or not transcribed, msg={
            'external_id': ext_id, 'channel': 'whatsapp',
            'subject': None, 'body': body or '(no text - see the attachment)',
            'from_name': m.get('name') or jid.split('@')[0],
            'conversation_id': f'whatsapp:{jid}',
            'sent_at': datetime.fromtimestamp(m.get('ts') or 0).strftime('%Y-%m-%d %H:%M:%S'),
            'source_name': ('group chat' if m.get('group') else m.get('name')) or 'WhatsApp',
            'images': images_for_triage(store, atts),
            **({'file_reason': f'voice note - not transcribed: {why[:160]}'} if not transcribed else {})}, llm=llm)
        n += r['status'] != 'duplicate'
        if atts and r.get('message_id') and r['status'] != 'duplicate':
            try: save_attachments(store, r['message_id'], atts, ext_id)
            except Exception as e: logger.warning(f'whatsapp attachment failed: {e}')
        took.append(m.get('id'))
    # blue ticks on what the funnel took, when the owner asked for it - best effort, and
    # never at the cost of the poll: an unpaired or restarted bridge just does not mark
    from .channels import wants_read
    if took and wants_read(store):
        try: _wa(c, '/read', {'ids': [i for i in took if i]})
        except Exception as e: logger.warning(f'marking whatsapp read failed: {e}')
    if out.get('seq') is not None:
        store.set_connector_config(c['ConnectorId'], {**cfg, 'wa_seq': out['seq']})
    return n


def wa_send(store, jid: str, body: str, connector_id=None) -> dict:
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else \
        store.get_connector_by_type('whatsapp', with_secret=True)
    if c and c.get('Type') != 'whatsapp': c = None
    if not c: raise RuntimeError('the WhatsApp connection is not set up')
    _wa(c, '/send', {'jid': jid, 'text': body[:4000]})
    return {'channel': 'whatsapp', 'chat': jid}
