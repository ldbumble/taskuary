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
import base64, json, os, time
from loguru import logger
from . import net as requests     # pooled Session + (connect, read) timeouts, same call shape

TG_API = 'https://api.telegram.org'
TG_LIMIT = 25                # messages per poll, like the other channels
WA_URL = 'http://127.0.0.1:8977'   # the bridge's default; override in the connector config
def wa_url(raw='') -> str:
    "The card's bridge URL - the managed bridge's current port when it names none, or names it where it was (wabridge.bridge_url)."
    from .wabridge import bridge_url
    return bridge_url(raw)
WA_FILTER_EVERY = 60          # seconds a sent /filter is trusted before poll_whatsapp re-states it
_WA_FILTERED = {}             # bridge url -> (policy json, monotonic time it was sent)


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
        # the token never reaches a log: requests names the whole URL, /file/bot<token>/..., in its exception
        logger.warning(f"telegram file fetch failed: {str(e).replace(token, '<token>') if token else e}"); return None


def poll_telegram(store, c, sources: list, llm=None, file_only=False) -> int:
    """getUpdates with the offset watermark kept on the connector - Telegram's own cursor, so a
    restart never re-ingests.

    Only chats the owner switched ON become work. A bot is PUBLIC - anyone who finds it can
    message it, and 'blank takes every chat' was an open door for spam-as-tasks. An unknown
    chat is registered instead: it shows up under Sources with its chat id, off, and flipping
    it on admits it from the next message onward. That registration is also how you FIND a
    chat id - message the bot once and read it off the card."""
    from datetime import datetime
    from .channels import files_for_triage, images_for_triage, save_attachments
    from .ingest import ingest_message
    tok, cfg = c['Secret'], _cfg(c)
    if not tok: return 0
    # every telegram source ever seen, on or off - a report source in the same list (the
    # seeded Morning digest) must never become a chat-id nothing can match
    known = {s['Address']: s for s in store.list_sources(active_only=False)
             if s.get('Channel') == 'telegram' and s.get('Address')}
    want = {a for a, s in known.items() if a != '*' and s.get('Active')}
    ups = tg(tok, 'getUpdates', offset=int(cfg.get('tg_offset') or 0), limit=TG_LIMIT,
             allowed_updates=['message', 'callback_query'])
    n = 0
    from . import remote_assistant
    # WHAT WAITED OUT A CLOSED TASKUARY in the Assistant chat: only the newest is acted on, the rest get their thumb and are named (A10)
    mine = lambda x: (((x.get('chat') or {}).get('type') or 'private') == 'private' and not (x.get('from') or {}).get('is_bot')
                      and ((x.get('text') or '').strip() or x.get('voice') or x.get('audio'))
                      and remote_assistant.enabled(store, 'telegram', str((x.get('chat') or {}).get('id') or ''), c))
    late = remote_assistant.queued_while_closed([(str(x['chat']['id']), x.get('message_id'), x.get('date'), (x.get('text') or '').strip() or 'a voice note')
                                                 for u in ups if (x := u.get('message')) and x.get('chat') and mine(x)])
    for u in ups:
        if u.get('callback_query'):                     # a button under one of the Assistant's messages
            try: tg_tap(store, c, u['callback_query'])
            except Exception as e: logger.warning(f'telegram: a tapped button was not handled - {e}')
            continue
        m = u.get('message') or {}
        chat, frm = m.get('chat') or {}, m.get('from') or {}
        cid = str(chat.get('id') or '')
        if not cid or frm.get('is_bot'): continue
        q = late.get(cid)
        if q and m.get('message_id') in q['skip']:
            react(store, 'telegram', cid, m.get('message_id'), connector_id=c.get('ConnectorId')); continue
        closed = q['older'] if q and m.get('message_id') == q['newest'] else None
        # A VOICE NOTE TO THE ASSISTANT is the owner talking, as on WhatsApp (_hear): heard first, then its words take the
        # text road below. Telegram dropped it - the interceptor reads text only (the owner, 2026-10-02: "yes fix the
        # transcribe thing for telegram"). Only in the chat that would answer typed words, so a stranger's note to a
        # public bot is never sent to a transcription service.
        v = m.get('voice') or m.get('audio')
        heard = False
        if (v and not (m.get('text') or '').strip() and (chat.get('type') or 'private') == 'private'
                and remote_assistant.enabled(store, 'telegram', cid, c)):
            m, heard = {**m, 'text': _tg_hear(store, c, cid, v, m.get('message_id'))}, True
            if not m['text']: continue
        # the owner's own words in the ONE private chat their card names as the Assistant chat go to
        # the same walk the desktop is on. A bot only ever hears the other side of a chat, so that
        # named private chat is what says the words are the owner's - there is no fromMe to read.
        if ((m.get('text') or '').strip() and (chat.get('type') or 'private') == 'private'
                and remote_assistant.intercept(store, 'telegram', cid, m['text'], from_me=True, connector=c,
                                               message_id=m.get('message_id'), heard=heard, closed=closed)):
            continue
        if cid not in want:
            # ...and a private chat nobody chose is not met with silence: one fixed line, with nothing about the owner in it (A4)
            if (m.get('text') or '').strip() and (chat.get('type') or 'private') == 'private':
                try: remote_assistant.greet_unchosen(store, c, cid)
                except Exception as e: logger.debug(f'telegram: no first-contact line - {e}')
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
            # a display name anyone can copy is not who they are: no username, the numeric id is the key (senders.chat_key)
            'from_name': who, 'from_email': f"@{frm['username']}" if frm.get('username') else f"tg:{frm['id']}" if frm.get('id') else None,
            'conversation_id': f'telegram:{cid}',
            'sent_at': datetime.fromtimestamp(m.get('date') or 0).strftime('%Y-%m-%d %H:%M:%S'),
            'source_name': chat.get('title') or who,
            # the platform's word that this chat is one-to-one: what senders.known needs, never guessed from who has spoken
            **({'mail_meta': {'dm': True}} if chat.get('type') == 'private' else {}),
            'images': images_for_triage(store, atts), **files_for_triage(atts),
            **({'file_reason': f'voice note - not transcribed: {why[:160]}'} if not transcribed else {})}, llm=llm)
        n += out['status'] != 'duplicate'
        if atts and out.get('message_id') and out['status'] != 'duplicate':
            try: save_attachments(store, out['message_id'], atts, f"telegram:{cid}:{m.get('message_id')}")
            except Exception as e: logger.warning(f'telegram attachments failed: {e}')
    if ups:
        store.set_connector_config(c['ConnectorId'], {**cfg, 'tg_offset': ups[-1]['update_id'] + 1})
    return n


TG_BUTTONS = 'tg_buttons'              # tg_buttons:<chat> -> {"msg": id, "labels": [...]} - the one message whose buttons answer


def tg_send(store, chat_id: str, body: str, connector_id=None, buttons: list = None) -> dict:
    """`buttons`: the choices numbered in `body`, as tappable buttons under it - Telegram's own, so no poll is needed (the
    owner, 2026-09-29: "if buttons work in telegram no need for polls"). A tap comes back as a callback_query
    (poll_telegram) carrying the button's index. Only the NEWEST message's buttons answer; the ones before are taken off,
    so a list that is gone cannot be tapped - and one tapped anyway is told so, never run."""
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else \
        store.get_connector_by_type('telegram', with_secret=True)
    if c and c.get('Type') != 'telegram': c = None
    if not (c and c.get('Secret')): raise RuntimeError('the Telegram connection is not set up')
    labels = [str(b) for b in (buttons or []) if str(b).strip()][:12]      # whole: a tap is matched by its words
    markup = {'reply_markup': {'inline_keyboard': [[{'text': t, 'callback_data': f'p{i}'}] for i, t in enumerate(labels)]}} if labels else {}
    sent = tg(c['Secret'], 'sendMessage', chat_id=int(chat_id), text=body[:4000], **markup)
    # ...and ANY newer message takes the older buttons off, one with none of its own too: a typed answer under a card left the card's
    # buttons drawn and looking live above it, while the list they named had been spent (F2)
    key = f'{TG_BUTTONS}:{chat_id}'
    try: before = json.loads(store.get_setting(key) or '{}') or {}
    except ValueError: before = {}
    if before.get('msg'):
        try: tg(c['Secret'], 'editMessageReplyMarkup', chat_id=int(chat_id), message_id=int(before['msg']),
                reply_markup={'inline_keyboard': []})
        except Exception as e: logger.debug(f'telegram: the older buttons stay drawn - {e}')
    if labels or before.get('msg'):
        store.set_setting(key, json.dumps({'msg': (sent or {}).get('message_id'), 'labels': labels} if labels else {}), 'assistant')
    return {'channel': 'telegram', 'chat': chat_id}


def tg_tap(store, c, q: dict) -> bool:
    """One button tapped in the Assistant chat: the chosen label goes on as that choice's own words - a pick, exactly as a
    typed number or a WhatsApp poll vote. A tap on an older message's buttons runs nothing and is answered."""
    from . import remote_assistant
    tok = c.get('Secret')
    try: tg(tok, 'answerCallbackQuery', callback_query_id=q.get('id'))      # the button stops spinning at once
    except Exception as e: logger.debug(f'telegram: tap not acknowledged - {e}')
    msg, frm = q.get('message') or {}, q.get('from') or {}
    cid = str((msg.get('chat') or {}).get('id') or '')
    if not cid or frm.get('is_bot') or ((msg.get('chat') or {}).get('type') or 'private') != 'private': return False
    if not remote_assistant.enabled(store, 'telegram', cid, c): return False
    try: shown = json.loads(store.get_setting(f'{TG_BUTTONS}:{cid}') or '{}') or {}
    except ValueError: shown = {}
    data, labels = str(q.get('data') or ''), shown.get('labels') or []
    i = int(data[1:]) if data[:1] == 'p' and data[1:].isdigit() else -1
    if shown.get('msg') != msg.get('message_id') or not 0 <= i < len(labels):
        remote_assistant.stale_tap(store, 'telegram', cid, c.get('ConnectorId')); return True
    return remote_assistant.intercept(store, 'telegram', cid, labels[i], from_me=True, connector=c, poll=True)


# ── WhatsApp (via the Baileys bridge) ────────────────────────────────────────────────────
class BridgeDown(RuntimeError):
    """Nothing answers at the bridge's address - the poll hands it to wabridge.supervise instead of logging it every time."""


def _wa(c, path, body=None, timeout=20):
    from .wabridge import token
    url, hdr = wa_url(_cfg(c).get('bridge_url')), {'X-Bridge-Token': token()}
    try:
        r = requests.post(f'{url}{path}', json=body, timeout=timeout, headers=hdr) if body is not None \
            else requests.get(f'{url}{path}', timeout=timeout, headers=hdr)
    except requests.ConnectionError:
        # a button, not a shell line: the card's Restart bridge installs what is missing and starts it detached (wabridge.py)
        from .wabridge import managed
        raise BridgeDown(f'the WhatsApp bridge is not running at {url}'
                           + (' - Restart bridge starts it' if managed(c) else ' - start it where it runs'))
    if r.status_code >= 300: raise RuntimeError(f'bridge {path} failed ({r.status_code}): {r.text[:200]}')
    return r.json()


def _wa_sender_id(jid: str) -> str:
    """Stable stored identity without making a provider JID look like an email address."""
    return 'whatsapp:' + str(jid or '').partition('@')[0].split(':', 1)[0]

def _wa_alias(m: dict) -> str:
    "The sender's other WhatsApp id (bridge senderAlt: phone beside LID), stored like from_email - '' when it is the same one."
    alt = _wa_sender_id(m['senderAlt']) if m.get('senderAlt') else ''
    return alt if alt != 'whatsapp:' and alt != _wa_sender_id(m.get('sender') or m.get('jid')) else ''


def wa_test(store, c) -> str:
    st = _wa(c, '/status')
    if not st.get('connected'):
        raise RuntimeError('bridge is running but WhatsApp is not paired yet - '
                           + (f"enter code {st['pairingCode']} on your phone (Linked devices)" if st.get('pairingCode')
                              else 'scan the QR the bridge printed in its own terminal'))
    # no catch-all is created here: only the chats the owner (or the setup agent) adds come in.
    # '*' - every direct chat - is a row they add themselves. A '*' that appeared by itself was a
    # timeline full of chats nobody asked for (the owner, 2026-08-30).
    return f"paired as {st.get('me') or 'your account'} - switch on the chats you want under Chats; they flow in on the next sync"


def wa_status(c) -> dict:
    """The bridge's state, with the pairing QR drawn as an SVG the card can show. Pairing used to
    mean reading a QR off the bridge's own terminal or typing a phone number into a chat; WhatsApp
    rotates the QR every ~20s, so the card polls this and redraws - nobody relays anything."""
    st = _wa(c, '/status')
    jid = str(st.get('jid') or '')
    out = {'connected': bool(st.get('connected')), 'me': st.get('me') or '', 'jid': jid,
           'phone': ('+' + jid.split('@')[0].split(':')[0]) if jid and jid.split(':')[0].split('@')[0].isdigit() else '',   # the paired number, from the account jid
           'pairing_code': st.get('pairingCode') or '', 'qr_svg': '',
           'reconnect': st.get('reconnect') or {}, 'filter': st.get('filter') or {},
           # what the card's status line says beyond "the socket is open" (bridge.mjs /status, health.mjs) - None from an older bridge
           'admitted': st.get('admitted'), 'turned_away': st.get('turnedAway'), 'last_inbound_at': st.get('lastInboundAt') or 0,
           'last_failure': st.get('lastFailure'), 'contact_sync': st.get('contactSync') or {}, 'logged_out': bool(st.get('loggedOut'))}
    if st.get('qr') and not out['connected']:
        import segno
        out['qr_svg'] = segno.make(st['qr'], error='m').svg_data_uri(scale=5, border=2, dark='#1e1e2e', light='#ffffff')
    out.update(wa_status_line(out))
    return out


# said the way every other age is (timewords.ago_m) - its own "40 min ago" sat beside the rail's "40m ago"
def _ago(ts: float, now: float) -> str:
    from .timewords import ago_m
    return ago_m(max(0, now - ts) // 60)


CONTACT_SYNC_REPAIR = 3         # failed contact syncs in a row (one per ~10 min) before the card offers Pair again


def wa_status_line(st: dict, now: float = None) -> dict:
    """THE CARD TELLS THE TRUTH (2026-10-23): it said "On - polling on schedule" from its switch while the bridge turned chats
    away, never heard a 1:1 addressed by LID and failed its contact sync every ten minutes. One short line, the same on the desk
    card and the phone: `parts` (the desk draws the turned-away count beside them, as a link into the chat picker), `line` (all of
    it, for the phone), and `fix` - the one button that is the next step: 'restart', 'pair' or ''."""
    now = time.time() if now is None else now
    if not st.get('connected'):
        if st.get('logged_out'): parts, fix = ['Logged out'], 'pair'
        elif st.get('qr_svg') or st.get('pairing_code'): parts, fix = ['Waiting for the phone to pair'], ''
        else: parts, fix = ['Not connected'], 'restart'
    else:
        parts, fix, n = ['Connected'], '', st.get('admitted')
        if n is not None:
            from .timewords import plural
            parts.append(plural(n, 'chat'))
        if st.get('last_inbound_at'): parts.append(f"last message {_ago(st['last_inbound_at'], now)}")
        elif n is not None: parts.append('no message yet')
        if int((st.get('contact_sync') or {}).get('failures') or 0) >= CONTACT_SYNC_REPAIR:
            parts.append('contact names not syncing'); fix = 'pair'
    away = int(st.get('turned_away') or 0) if st.get('connected') else 0
    return {'parts': parts, 'fix': fix, 'line': ' · '.join(parts + ([f'{away} turned away'] if away else []))}


WA_ALL = '*'        # the catch-all WhatsApp no longer honours; Telegram's '*' is a different thing


def wa_self_number(store, c) -> str:
    """The paired account's own number, cached on the card.

    It is what tells the owner's private "Message yourself" chat from any other group: WhatsApp
    gives that thread a LEGACY GROUP jid, `<your number>-<when it was made>@g.us`, and Taskuary
    refused it as a group - so the walk it had just sent there could not be answered (the owner,
    2026-09-07: "i said reply and nothing happened"). Sending is what hid it: a DM to your own
    `@s.whatsapp.net` address lands in that same thread, so only the INBOUND half was ever wrong.
    """
    cfg = _cfg(c)
    known = str(cfg.get('me_number') or '').strip()
    if known: return known
    try: jid = str(_wa(c, '/status').get('jid') or '')
    except Exception as e:
        logger.debug(f'whatsapp: the bridge did not say who is paired - {e}'); return ''
    number = jid.partition('@')[0].split(':', 1)[0]
    if not number.isdigit(): return ''
    try: store.patch_connector_poll_state(c['ConnectorId'], config_set={'me_number': number})
    except Exception as e: logger.debug(f'whatsapp: could not remember the paired number - {e}')
    return number


def wa_chats(c, store=None) -> list:
    """Chats reachable through the paired account, newest first.

    With a `store`, every row is named and given its `phone` (wanames.fill) and the names the roster gave are kept, so a
    picker can find a chat by its name or number - never only by its JID - even while the bridge is restarting.

    New bridges expose a metadata-only roster (including every group the account still belongs
    to). The legacy message roll-up remains as a compatibility path until an already-running
    bridge is restarted onto the new endpoint.
    """
    from datetime import datetime
    try:
        out = _wa(c, '/chats')
    except RuntimeError as e:
        if 'bridge /chats failed (404)' not in str(e): raise
        out = _wa(c, '/messages?after=0')
    if 'chats' in out:
        rows = []
        for item in out.get('chats', []):
            jid = item.get('jid') or ''
            if not jid or jid.endswith('@broadcast'): continue
            last = item.get('last') or 0
            rows.append({'jid': jid, 'group': bool(item.get('group')), 'name': item.get('name') or '',
                         'n': int(item.get('n') or 0), 'last': last,
                         # the bridge writes "not opened - chat is not authorized" against every
                         # chat that is not a source; on a real account that is most of them, the
                         # same sentence over and over, and it says nothing the row does not
                         'snippet': '' if 'not authorized' in str(item.get('snippet') or '') else (item.get('snippet') or ''),
                         # how many people are in it - None when this bridge is too old to say
                         'people': item.get('people')})
        rows.sort(key=lambda r: (-r['last'], (r['name'] or r['jid']).lower()))
        for r in rows:
            r['last'] = datetime.fromtimestamp(r['last']).strftime('%Y-%m-%d %H:%M') if r['last'] else ''
        return _named(store, rows)
    by = {}
    for m in out.get('messages', []):
        jid = m.get('jid') or ''
        if not jid or jid.endswith('@broadcast'): continue
        r = by.setdefault(jid, {'jid': jid, 'group': bool(m.get('group')), 'name': '', 'n': 0, 'last': 0, 'snippet': '', 'people': None})
        r['n'] += 1
        if not m.get('fromMe') and m.get('name'): r['name'] = m['name']     # the other side's push name, never ours
        if (m.get('ts') or 0) >= r['last']: r['last'], r['snippet'] = m.get('ts') or 0, (m.get('text') or '')[:80]
    # The bridge sees the routing JID before deciding whether to decrypt. That lets the source
    # picker show a newly active chat without retaining its sender, text, or media first.
    for m in out.get('blockedChats', []):
        jid = m.get('jid') or ''
        if not jid or jid.endswith('@broadcast') or jid in by: continue
        # NO SNIPPET. "not opened - chat is not authorized" is the bridge explaining itself, and it
        # was printed against most rows on a real account - a wall of the same sentence next to every
        # chat the owner has not listed (2026-09-17: "the words ... is not needed"). It is not
        # information: the row being here at all already says the chat exists and is not a source.
        by[jid] = {'jid': jid, 'group': bool(m.get('group')), 'name': '', 'n': 0,
                   'last': m.get('last') or 0, 'snippet': '', 'people': m.get('people')}
    rows = sorted(by.values(), key=lambda r: -r['last'])
    for r in rows: r['last'] = datetime.fromtimestamp(r['last']).strftime('%Y-%m-%d %H:%M') if r['last'] else ''
    return _named(store, rows)


def _named(store, rows) -> list:
    from . import wanames
    if store is None:
        for r in rows: r['phone'] = wanames.phone(r['jid'])
        return rows
    wanames.remember(store, rows)
    return wanames.fill(store, rows)


def _read_media(path: str):
    """The bridge wrote a voice note or a photo to disk beside itself; same machine, so it is
    read straight off. Missing or oversized (over 25 MB - every transcription and vision API's
    ceiling) is a warning, not a failed poll."""
    try:
        if os.path.getsize(path) > 25 * 1024 * 1024: logger.warning(f'media too large to read: {path}'); return None
        with open(path, 'rb') as f: return f.read()
    except OSError as e:
        logger.warning(f'could not read the media the bridge saved ({path}): {e}'); return None


def _unheard(store, channel: str, chat: str, c, e, message_id=None):
    """Say in the chat that a voice note could not be heard - instead of the note simply never arriving. The note gets its thumb like
    any message the doorway took, the place that fixes it is named once (the reason already names it when no connector is set up),
    and the choices under the last card come with the line - the note answered nothing, so they still stand (F22)."""
    from . import remote_assistant, words
    logger.warning(f'{channel}: a voice note to Taskuary was not transcribed - {e}')
    if message_id:
        try: react(store, channel, chat, message_id, connector_id=c.get('ConnectorId'))
        except Exception as e3: logger.debug(f'{channel}: no thumb on the voice note - {e3}')
    why, place = str(e)[:200].strip().rstrip('.'), words.name('voice')
    # ...the place named ONCE, however the reason spells it: "add one under Connections > Voice" got "under Connections → AI — voice" again
    told = place in why or place.split(' → ')[0] in why
    said = f"I could not hear that voice note - {why}." + (' Type it instead.' if told else f" Type it, or add a voice connector under {place}.")
    try: live = json.loads(store.get_setting(f'{remote_assistant.OFFERED_KEY}:{channel}:{chat}') or '[]') or []
    except ValueError: live = []
    remote_assistant.owner_spoke(store, channel, chat)          # the owner sent it: this is their conversation, and it is answered
    try: remote_assistant.send(store, channel, chat, said, c.get('ConnectorId'), **({'choices': live} if live else {}))
    except Exception as e2: logger.warning(f'{channel}: could not say so either - {e2}')


def _tg_hear(store, c, chat: str, v: dict, mid=None) -> str:
    """The words of a Telegram voice note (or audio file) the owner sent the Assistant chat, or ''."""
    from . import voice
    got = _tg_file(c.get('Secret') or '', v, 'voice.ogg')
    if not got:
        _unheard(store, 'telegram', chat, c, 'it could not be downloaded from Telegram', mid); return ''
    data, name, mime = got
    try: return str(voice.transcribe(store, data, mime, name)['text'] or '').strip()
    except Exception as e:
        _unheard(store, 'telegram', chat, c, e, mid); return ''


def _hear(store, c, jid: str, m: dict) -> str:
    """The words of a voice note the owner sent to a control chat, or '' - and when it cannot be heard, the
    owner is told so in that same chat, instead of the note simply never arriving."""
    import os
    from . import voice
    data = _read_media(m.get('audio'))
    if data is None: return ''
    mime = (m.get('mime') or 'audio/ogg').split(';')[0]
    try: return str(voice.transcribe(store, data, mime, os.path.basename(m['audio']))['text'] or '').strip()
    except Exception as e:
        _unheard(store, 'whatsapp', jid, c, e, m.get('id')); return ''


def poll_whatsapp(store, c, sources: list, llm=None, file_only=False) -> int:
    """The bridge keeps a sequence number per message; ours is on the connector, so nothing is
    read twice and a bridge restart just resets both to live traffic."""
    import os
    from datetime import datetime
    from .ingest import ingest_message
    from .channels import files_for_triage, images_for_triage, ingest_own_message, save_attachments
    from . import voice, wabridge
    # the launch grace lives HERE, in front of the one call that files "bridge not running": the catch-up, the chat clock,
    # the doorway and Sync now all come through, and none of them - nor the mail beside them - waits when no bridge was started
    try: wabridge.ready(8)
    except Exception as e: logger.debug(f'wa bridge grace skipped: {e}')
    cfg = _cfg(c)
    # NAMED CHATS ONLY. Every chat that comes in is one somebody listed: a person by their number,
    # a group by its JID. There is no catch-all - a paired account sees everything its owner does,
    # and on a real phone that is forty groups and every DM (the owner, 2026-09-17: "we should not
    # allow * all as incoming. it will be too big. it should be specific channels only").
    #
    # A '*' row left over from before is inert: it is skipped here and `allDirect` goes to the
    # bridge as False, so Baileys stops decrypting and downloading media for chats nobody asked for.
    # Telegram keeps its own '*' - a bot only ever hears the chats it has been added to, so there
    # the catch-all is the whole roster, not the world.
    srcs = [s for s in sources if s.get('Channel', 'whatsapp') == 'whatsapp'
            and s.get('Address') and s['Address'] != WA_ALL]
    want = {s['Address'] for s in srcs}
    notify_chat = str(cfg.get('notify_chat') or '').strip()
    assistant_chat = str(cfg.get('assistant_chat') or '').strip()
    # Control chats do not have to be inbound sources. Notification replies and Assistant
    # questions are different opt-ins, but both must reach the bridge's pre-decryption gate.
    bridge_want = want | ({notify_chat} if notify_chat else set()) | ({assistant_chat} if assistant_chat else set())
    # Filtering here alone was too late: Baileys had already decrypted and downloaded media from
    # every chat. Give the same policy to its pre-decryption hook before asking for messages.
    # Sent when the list CHANGES, not on every read: the doorway reads once a second, and a /filter
    # beside every /messages doubled an idle phone chat's bridge traffic (P13). A restarted bridge comes
    # up closed unless it was launched with WA_BRIDGE_FILTER, so a seq that went backwards forgets what
    # was sent, and WA_FILTER_EVERY re-states it anyway in case a restart slipped past both.
    url, policy, now = wa_url(cfg.get('bridge_url')), json.dumps({'allDirect': False, 'jids': sorted(bridge_want)}), time.monotonic()
    sent, at = _WA_FILTERED.get(url, (None, 0))
    if sent != policy or now - at > WA_FILTER_EVERY:
        try: _wa(c, '/filter', json.loads(policy))
        except RuntimeError as e:
            if '(404)' not in str(e): raise                 # an older detached bridge: keep polling until its next restart
        _WA_FILTERED[url] = (policy, now)
    seq = int(cfg.get('wa_seq') or 0)
    out = _wa(c, f"/messages?after={seq}")
    if out.get('seq') is not None and int(out['seq']) < seq: _WA_FILTERED.pop(url, None)    # the bridge restarted
    n, took = 0, []
    from . import remote_assistant
    # WHAT WAITED OUT A CLOSED TASKUARY in the Assistant chat: only the newest is acted on, the rest get their thumb and are named (A10)
    late = remote_assistant.queued_while_closed([
        (assistant_chat, x.get('id'), x.get('ts'), (x.get('text') or '').strip() or 'a voice note') for x in out.get('messages', [])
        if assistant_chat and x.get('jid') == assistant_chat and x.get('fromMe') and not x.get('taskuary') and not x.get('stalePoll')
        and ((x.get('text') or '').strip() or x.get('audio')) and remote_assistant.enabled(store, 'whatsapp', assistant_chat, c)])
    for m in out.get('messages', []):
        jid = m.get('jid') or ''
        if not jid: continue
        # This id was sent through the bridge's localhost /send endpoint. It is Taskuary's
        # output, never an owner verdict or question; discard it before either interceptor.
        if m.get('taskuary'): continue
        q = late.get(jid)
        if q and m.get('id') in q['skip']:
            react(store, 'whatsapp', jid, m.get('id'), connector_id=c.get('ConnectorId')); took.append(m.get('id')); continue
        closed = q['older'] if q and m.get('id') == q['newest'] else None
        # A TAP ON AN OLDER LIST of the Assistant's (poll.mjs stale): nothing runs - its choices are gone - but it is answered
        if m.get('stalePoll'):
            if jid == assistant_chat: remote_assistant.stale_tap(store, 'whatsapp', jid, c['ConnectorId'], spent=bool(m.get('spentPoll')))
            took.append(m.get('id')); continue
        text, heard = (m.get('text') or '').strip(), False
        # A VOICE NOTE IN A CONTROL CHAT is the owner talking to Taskuary, so it is heard BEFORE the interceptors,
        # which only ever read text. It used to fall past both - no text - and then past the source filter, since
        # the Assistant's own chat is not an inbound source: dropped without a trace, while the same note in a
        # group was transcribed and filed (the owner, 2026-09-24: "i sent whatsapp voice note to taskuary ...
        # nothing came through to the assistant").
        if not text and m.get('audio') and jid in {x for x in (assistant_chat, notify_chat) if x}:
            text, heard = _hear(store, c, jid, m), True
            if not text:
                took.append(m.get('id')); continue
        # A natural message the owner types in their designated private chat goes to the SAME
        # guide conversation as the desktop bubble. Bridge-stamped Taskuary output is swallowed
        # here too, so a notification or answer can never loop back as a fresh question.
        if text and remote_assistant.intercept(
                store, 'whatsapp', jid, text, from_me=bool(m.get('fromMe')),
                connector=c, message_id=m.get('id'), poll=bool(m.get('poll')), arrived=m.get('ts'), heard=heard, closed=closed):
            continue
        if m.get('group') or jid.endswith('@g.us'):
            if jid not in want: continue                      # groups are opt-in, always
        elif jid not in want: continue                        # a direct chat is listed too, or it does not come in
        if m.get('fromMe'):
            # the owner's OWN line in a chat the funnel reads - typed on their phone, not here. It
            # used to be dropped, so a WhatsApp thread the owner had answered still read as waiting
            # on them, and the reader that splits a room into asks never saw our half of it
            # (channels.ingest_own_message: context on the thread, never work, never counted)
            if (m.get('text') or '').strip():
                ingest_own_message(store, {
                    'external_id': f"whatsapp:{jid}:{m.get('id')}", 'channel': 'whatsapp', 'subject': None,
                    'body': m['text'].strip(), 'from_email': None, 'conversation_id': f'whatsapp:{jid}',
                    'sent_at': datetime.fromtimestamp(m.get('ts') or 0).strftime('%Y-%m-%d %H:%M:%S'),
                    'source_name': ('group chat' if m.get('group') else m.get('name')) or 'WhatsApp'},
                    'your line in this chat - kept for context')
            took.append(m.get('id'))
            continue
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
        # a person's JID, not a group's, is the one-to-one mark; `alias` is the same person's other id (phone vs LID), so
        # the group member the owner answers is the one they talk with directly (senders.chat_aliases)
        meta = {**({} if m.get('group') or jid.endswith('@g.us') else {'dm': True}), **({'alias': a} if (a := _wa_alias(m)) else {})}
        r = ingest_message(store, file_only=file_only or not transcribed, msg={
            'external_id': ext_id, 'channel': 'whatsapp',
            'subject': None, 'body': body or '(no text - see the attachment)',
            'from_name': m.get('name') or jid.split('@')[0],
            # Direct chats use the chat JID; groups carry the participant JID from the bridge.
            # This is the stable cross-message identity project learning needs - a display name
            # alone is not safe enough to merge two people.
            'from_email': _wa_sender_id(m.get('sender') or jid),
            'conversation_id': f'whatsapp:{jid}',
            'sent_at': datetime.fromtimestamp(m.get('ts') or 0).strftime('%Y-%m-%d %H:%M:%S'),
            'source_name': ('group chat' if m.get('group') else m.get('name')) or 'WhatsApp',
            **({'mail_meta': meta} if meta else {}),
            'images': images_for_triage(store, atts), **files_for_triage(atts),
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
    # only a sequence that moved: an idle check-in rewrote the same number ~2/s, and every write moved the rail (2026-10-12)
    if out.get('seq') is not None and out['seq'] != cfg.get('wa_seq'):
        store.set_connector_config(c['ConnectorId'], {**cfg, 'wa_seq': out['seq']})
    return n


GOT_IT = '👍'      # the hub heard you - see react()


def react(store, channel: str, chat: str, message_id: str, emoji: str = GOT_IT, connector_id=None) -> bool:
    """Mark the owner's own message as TAKEN, in their chat, the moment the doorway claims it.

    A chat that goes quiet while a model thinks is indistinguishable from one nobody is listening to
    (the owner, 2026-09-15: "can we also automatically do thumbs up to know the ai agent got the
    whatsapp"). Best effort by design: a reaction that will not send must never cost the answer that
    is already on its way - every road out of here returns False rather than raising.
    """
    if not message_id: return False
    try:
        c = store.get_connector(int(connector_id), with_secret=True) if connector_id else             store.get_connector_by_type(channel, with_secret=True)
        if not c or c.get('Type') != channel: return False
        if channel == 'whatsapp':
            # the bridge knows which chat the message was in: it kept the key it reacts with
            return bool((_wa(c, '/react', {'id': str(message_id), 'emoji': emoji}) or {}).get('reacted'))
        if channel == 'telegram' and c.get('Secret'):
            tg(c['Secret'], 'setMessageReaction', chat_id=int(chat), message_id=int(message_id),
               reaction=json.dumps([{'type': 'emoji', 'emoji': emoji}]))
            return True
    except Exception as e:
        logger.debug(f'could not react in {channel}: {e}')
    return False


# ── a file to the owner's phone, as a document (A14) ─────────────────────────────────────
# Telegram's Bot API takes a bot's upload up to 50 MB; the bridge holds a document in memory as base64, so it stops at 64 MB
# (bridge.mjs DOC_MAX) - and a tap on a phone on mobile data should not pull more than that anyway.
FILE_MAX = {'telegram': 50 * 2**20, 'whatsapp': 64 * 2**20}
FILE_SECS = 180               # an upload is not a text line: 50 MB over a slow uplink takes minutes, not the 20 s a message gets


class TooBig(ValueError):
    "A file over the channel's ceiling - said to the owner with the desktop instead, never tried."


def _connector(store, channel: str, connector_id=None):
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else store.get_connector_by_type(channel, with_secret=True)
    return c if c and c.get('Type') == channel else None


def tg_upload(token: str, method: str, files: dict, **params):
    """A multipart Bot API call (sendDocument). The token never reaches a log: requests names the whole URL in its exception."""
    try: r = requests.post(f'{TG_API}/bot{token}/{method}', data=params, files=files, timeout=FILE_SECS)
    except Exception as e: raise RuntimeError(str(e).replace(token, '<token>') if token else str(e)) from None
    try: j = r.json()
    except ValueError: j = {}
    if not j.get('ok'): raise RuntimeError(f"telegram {method}: {j.get('description') or r.status_code}")
    return j['result']


def send_document(store, channel: str, chat: str, data: bytes, name: str, mime: str, caption: str = '', connector_id=None) -> dict:
    """The bytes of one file into one chat as a document. The CALLER chose the file and the chat (remote_assistant.send_files: only
    a file inside the task's own outputs folder, only the owner's Assistant chat); this only carries it, and refuses one too big."""
    if len(data) > FILE_MAX[channel]: raise TooBig(f'{len(data)} bytes is over {FILE_MAX[channel] // 2**20} MB')
    c = _connector(store, channel, connector_id)
    if channel == 'telegram':
        if not (c and c.get('Secret')): raise RuntimeError('the Telegram connection is not set up')
        tg_upload(c['Secret'], 'sendDocument', {'document': (name, data, mime)}, chat_id=str(chat), **({'caption': caption[:1000]} if caption else {}))
    else:
        if not c: raise RuntimeError('the WhatsApp connection is not set up')
        _wa(c, '/send-document', {'jid': chat, 'data': base64.b64encode(data).decode(), 'mimetype': mime, 'fileName': name,
                                  **({'caption': caption[:1000]} if caption else {})}, timeout=FILE_SECS)
    return {'channel': channel, 'chat': chat, 'name': name, 'bytes': len(data)}


def wa_send(store, jid: str, body: str, connector_id=None, poll: list = None) -> dict:
    """`poll`: the choices numbered in `body`, sent again under it as a WhatsApp poll - one tap picks (the bridge
    turns the vote back into the option's words)."""
    c = store.get_connector(int(connector_id), with_secret=True) if connector_id else \
        store.get_connector_by_type('whatsapp', with_secret=True)
    if c and c.get('Type') != 'whatsapp': c = None
    if not c: raise RuntimeError('the WhatsApp connection is not set up')
    _wa(c, '/send', {'jid': jid, 'text': body[:4000], **({'poll': {'name': 'Pick one', 'values': list(poll)}} if poll else {})})
    return {'channel': 'whatsapp', 'chat': jid}
