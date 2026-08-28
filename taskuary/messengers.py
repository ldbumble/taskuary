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
import base64, json
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
        if not text and not atts: continue
        who = ' '.join(x for x in (frm.get('first_name'), frm.get('last_name')) if x) or frm.get('username') or 'someone'
        out = ingest_message(store, file_only=file_only, msg={
            'external_id': f"telegram:{cid}:{m.get('message_id')}", 'channel': 'telegram',
            'subject': None, 'body': text or '(no text - see the attachment)',
            'from_name': who, 'from_email': f"@{frm['username']}" if frm.get('username') else None,
            'conversation_id': f'telegram:{cid}',
            'sent_at': datetime.fromtimestamp(m.get('date') or 0).strftime('%Y-%m-%d %H:%M:%S'),
            'source_name': chat.get('title') or who,
            'images': images_for_triage(store, atts)}, llm=llm)
        n += out['status'] != 'duplicate'
        if atts and out.get('message_id') and out['status'] != 'duplicate':
            try: save_attachments(store, out['message_id'], atts, f"telegram:{cid}:{m.get('message_id')}")
            except Exception as e: logger.warning(f'telegram attachments failed: {e}')
    if ups:
        store.set_connector_config(c['ConnectorId'], {**cfg, 'tg_offset': ups[-1]['update_id'] + 1})
    return n


def tg_send(store, chat_id: str, body: str) -> dict:
    c = store.get_connector_by_type('telegram', with_secret=True)
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
    if not any(s['Channel'] == 'whatsapp' for s in store.list_sources(active_only=False)):
        store.save_source({'Channel': 'whatsapp', 'Address': '*', 'ConnectorId': c['ConnectorId'], 'Active': 1}, 'connector-test')
    return f"paired as {st.get('me') or 'your account'} - chats flow in on the next sync"


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


def poll_whatsapp(store, c, sources: list, llm=None, file_only=False) -> int:
    """The bridge keeps a sequence number per message; ours is on the connector, so nothing is
    read twice and a bridge restart just resets both to live traffic."""
    from datetime import datetime
    from .ingest import ingest_message
    cfg = _cfg(c)
    want = {s['Address'] for s in sources
            if s.get('Channel', 'whatsapp') == 'whatsapp' and s['Address'] and s['Address'] != '*'}
    out = _wa(c, f"/messages?after={int(cfg.get('wa_seq') or 0)}")
    n, took = 0, []
    from . import phone
    for m in out.get('messages', []):
        jid = m.get('jid') or ''
        if not jid: continue
        # the WhatsApp bridge is the owner's OWN account, so a verdict they type in the
        # notify chat arrives as fromMe - intercept runs before that filter (phone.py also
        # recognizes and swallows our own pings echoing back through the bridge)
        if (m.get('text') or '').strip() and phone.intercept(store, 'whatsapp', jid, m['text']):
            continue
        if m.get('fromMe') or (want and jid not in want): continue
        if not (m.get('text') or '').strip(): continue
        r = ingest_message(store, file_only=file_only, msg={
            'external_id': f"whatsapp:{jid}:{m.get('id')}", 'channel': 'whatsapp',
            'subject': None, 'body': m['text'], 'from_name': m.get('name') or jid.split('@')[0],
            'conversation_id': f'whatsapp:{jid}',
            'sent_at': datetime.fromtimestamp(m.get('ts') or 0).strftime('%Y-%m-%d %H:%M:%S'),
            'source_name': ('group chat' if m.get('group') else m.get('name')) or 'WhatsApp'}, llm=llm)
        n += r['status'] != 'duplicate'
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


def wa_send(store, jid: str, body: str) -> dict:
    c = store.get_connector_by_type('whatsapp', with_secret=True)
    if not c: raise RuntimeError('the WhatsApp connection is not set up')
    _wa(c, '/send', {'jid': jid, 'text': body[:4000]})
    return {'channel': 'whatsapp', 'chat': jid}
