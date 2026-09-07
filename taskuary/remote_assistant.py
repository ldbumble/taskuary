"""The owner's private doorway into the assistant from a phone chat - WhatsApp or Telegram.

This is deliberately not another bot and not another conversation. A message the owner types in the
one chat they named runs the SAME walk the Assistant tab runs, on the same dock task (general.dock_task),
through the same concierge: the pipe it takes items from, the verbs it decides with and the proposals it
waits on are the desk's. What the desktop draws as a card with action words under it, the phone carries
as words in the message - the choices are appended here, from the item, never invented by the model.

A HANDOFF is the explicit version, and the reason the button exists: the tab hands its walk to the chat
and LOCKS itself, because two screens answering the same item is how the same mail gets replied to twice.
Take it back on the desktop and the chat is told the walk is over.

Only messages the owner themself sent in that named, private chat are accepted. Other people, other
chats and groups continue through the normal funnel.
"""
import json, re, threading, time

from loguru import logger


CHANNELS = ('whatsapp', 'telegram')
LABELS = {'whatsapp': 'WhatsApp', 'telegram': 'Telegram'}
HANDOFF_KEY = 'assistant_handoff'      # {'channel','chat','connector_id','at'} while the walk is on the phone

_TASK_LINK = re.compile(r'\[([^\]]+)\]\(#task=\d+\)')
_locks, _locks_guard = {}, threading.Lock()

OPENED = ('Walking you through it here. Reply in this chat and I keep going; '
          'take it back on the desktop when you want the buttons again.')
CLOSED = 'Taken back on the desktop - this walk is over here. Message me any time and I will pick it up again.'


def _config(connector) -> dict:
    try: return json.loads((connector or {}).get('ConfigJson') or '{}')
    except (TypeError, ValueError): return {}


def chat_of(connector) -> str:
    """The private guide chat. ``notify_chat`` is WhatsApp's backward-compatible old location."""
    cfg = _config(connector)
    return str(cfg.get('assistant_chat')
               or (cfg.get('notify_chat') if (connector or {}).get('Type') == 'whatsapp' else '') or '').strip()


def is_private(store, connector, chat: str) -> bool:
    """Whether this chat is the owner ALONE. A group must never be able to command the assistant,
    and an answer about the owner's mail must never be posted where other people are reading.

    The exception, and the reason this is not one line: WhatsApp gives the owner's own "Message
    yourself" thread a LEGACY GROUP jid - `<their number>-<when it was made>@g.us` - so refusing
    everything that ends in @g.us refused the very chat the pairing box tells people to use. Sending
    hid it, because a DM to your own address lands in that same thread; only the inbound half was
    wrong, and the walk Taskuary had just sent there could not be answered (the owner, 2026-09-07:
    "whatsapp did not work, i said reply and nothing happened"). So: a group jid is accepted only
    when it is the paired account's own self-chat, which its number-prefix is what proves.
    """
    chat = str(chat or '').strip()
    if not chat: return False
    if not chat.endswith('@g.us'): return True
    if (connector or {}).get('Type') != 'whatsapp': return False
    from . import messengers
    me = messengers.wa_self_number(store, connector)
    return bool(me) and chat.split('-', 1)[0] == me


def doorway(store, channel: str):
    """The active connector of that channel whose card names an Assistant chat, if there is one."""
    return next((c for c in store.connectors_by_type(channel, with_secret=True)
                 if c and c.get('Active') and chat_of(c) and is_private(store, c, chat_of(c))), None)


def doorways(store) -> list:
    """The channels the walk can actually be handed to, for the button that offers it. A channel with
    no connector, no pairing or no Assistant chat named is not offered at all - the point is to TALK to
    the assistant through it, and a button that opens a setup page instead is a different thing."""
    out = []
    for ch in CHANNELS:
        c = doorway(store, ch)
        if c: out.append({'channel': ch, 'label': LABELS[ch], 'chat': chat_of(c),
                          'connectorId': c['ConnectorId'], 'name': c.get('Name') or LABELS[ch]})
    return out


def connector_for_chat(store, channel: str, chat: str, connector=None):
    """The active connector that owns this private Assistant chat, if any."""
    rows = [connector] if connector else store.connectors_by_type(channel, with_secret=True)
    return next((c for c in rows if c and c.get('Active')
                 and chat_of(c) == str(chat or '').strip()), None)


# ── the handoff: which screen the walk is on ────────────────────────────────────────────────────
def handoff(store) -> dict | None:
    """The live handoff, or None. Validated against the connectors: a card that was turned off or had
    its chat cleared must never leave the desktop locked out of its own assistant."""
    try: h = json.loads(store.get_settings().get(HANDOFF_KEY) or 'null')
    except ValueError: h = None
    if not isinstance(h, dict) or h.get('channel') not in CHANNELS: return None
    return h if connector_for_chat(store, h['channel'], h.get('chat')) else None


def enabled(store, channel: str, chat: str, connector=None) -> bool:
    """Whether a message in this chat is the owner talking to the assistant. The setting is the standing
    permission; a live handoff to this chat is the owner asking for it right now."""
    c = connector_for_chat(store, channel, chat, connector)
    if c is None or not is_private(store, c, chat): return False
    h = handoff(store)
    return (store.get_settings().get('phone_assistant') == '1'
            or bool(h and h['channel'] == channel and h.get('chat') == str(chat).strip()))


def polls(store, connector) -> bool:
    """True when this connector must be polled for the doorway alone - it carries the Assistant chat,
    so its messages have to be read even when nothing about it is set to become work."""
    ch = (connector or {}).get('Type')
    if ch not in CHANNELS or not chat_of(connector): return False
    h = handoff(store)
    return store.get_settings().get('phone_assistant') == '1' or bool(h and h['channel'] == ch)


def start_handoff(store, channel: str, actor: str = 'owner') -> dict:
    """Send the walk to the phone: the opening turn goes to the chat, and the desktop locks behind it."""
    from . import concierge, general
    if channel not in CHANNELS: raise ValueError(f'{channel} is not a chat the assistant can be handed to')
    c = doorway(store, channel)
    if not c: raise ValueError(f'no {LABELS[channel]} card names an Assistant chat to walk you through it in')
    chat, cid = chat_of(c), c['ConnectorId']
    live = {'channel': channel, 'chat': chat, 'connector_id': cid, 'at': _now()}
    task, _ = general.dock_task(store, actor)
    # the hello goes first: a bridge that is not running or a bot that will not send must never leave
    # the tab locked behind a walk that never arrived anywhere
    with concierge.delivering(concierge.PHONE):
        out = concierge.surface(store, actor=actor)
        text = carry_out(store, out, None, actor, lead=OPENED)
    send(store, channel, chat, text, cid)
    store.set_setting(HANDOFF_KEY, json.dumps(live), actor)
    store.audit('task', task['TaskId'], 'assistant_handoff_start', actor, detail={'channel': channel, 'chat': chat})
    concierge.record(store, task['TaskId'], 'assistant',
                     f"Taking this to {LABELS[channel]} - I have said hello there. "
                     f'Answer me in the chat; press Take it back here when you want the desk again.')
    return {**live, 'label': LABELS[channel], 'say': out.get('say') or ''}


def end_handoff(store, actor: str = 'owner', note: str = CLOSED) -> dict:
    """Take it back: the chat is told the walk is over there, and the desktop is its own again."""
    from . import concierge, general
    h = handoff(store)
    store.set_setting(HANDOFF_KEY, '', actor)
    if not h: return {'ended': False}
    task, _ = general.dock_task(store, actor)
    store.audit('task', task['TaskId'], 'assistant_handoff_end', actor, detail={'channel': h['channel']})
    concierge.record(store, task['TaskId'], 'assistant',
                     f"Back at the desk - {LABELS[h['channel']]} has been told we are done there.")
    try: send(store, h['channel'], h['chat'], note, h.get('connector_id'))
    except Exception as e: logger.warning(f"could not close the {h['channel']} walk: {e}")
    return {'ended': True, **h}


ALERT_EVERY = 20.0                     # seconds between looks; the walk is on the phone, not on a screen
_looked = [0.0]


def push_alerts(store, force: bool = False) -> int:
    """While the walk is in a chat, an interruption goes THERE.

    The desktop's "By the way" strip lives on the tab this handoff has locked - which is precisely
    where the owner is not looking, so a coding agent raising its hand mid-walk reached nobody (the
    owner, 2026-09-07). Each one is said once per handoff: what has been told rides in the handoff
    record, so it is forgotten when the walk comes home and the strip can still raise anything the
    owner never acted on.

    It is also RECORDED in the conversation, which is what makes it answerable: the next turn's
    history carries the line, so "answer it - use the staging db" has a TQ number to land on.
    """
    if not force and time.monotonic() - _looked[0] < ALERT_EVERY: return 0
    _looked[0] = time.monotonic()
    h = handoff(store)
    if not h: return 0
    from . import concierge, funnel, general
    try: p = funnel.pile(store)
    except Exception as e:
        logger.warning(f'could not look for interruptions to send to {h["channel"]}: {e}'); return 0
    task, _ = general.dock_task(store, 'owner')
    on_the_table = concierge.current_key(store, task['TaskId'])
    told = list(h.get('told') or [])
    refs = {i['key']: i.get('ref') or '' for i in p.get('items') or []}
    fresh = [a for a in (p.get('alerts') or [])
             if a.get('key') not in told and a.get('item') != on_the_table][:3]
    if not fresh: return 0
    named = [f"{a['text']}{' (' + refs[a['item']] + ')' if refs.get(a['item']) and refs[a['item']] not in a['text'] else ''}"
             for a in fresh]
    lead = 'By the way — '            # the same words the desktop strip uses, in the place he is reading
    say = lead + named[0] + '.' if len(named) == 1 else lead.rstrip() + '\n' + '\n'.join('· ' + n for n in named)
    handle = next((refs[a['item']] for a in fresh if refs.get(a['item'])), '')
    tail = (f'Say {handle} to take it now, or keep going.' if handle
            else 'Name it and I will take you to it, or keep going.')
    send(store, h['channel'], h['chat'], f'{say}\n\n{tail}', h.get('connector_id'))
    concierge.record(store, task['TaskId'], 'assistant', say)
    store.set_setting(HANDOFF_KEY, json.dumps({**h, 'told': told + [a['key'] for a in fresh]}), 'owner')
    return len(fresh)


def _now() -> str:
    from datetime import datetime
    return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


# ── inbound: the owner's words, in their chat ───────────────────────────────────────────────────
def intercept(store, channel: str, chat: str, text: str, *, from_me=False, taskuary=False, connector=None) -> bool:
    """Claim an owner-authored question before it can be discarded or triaged.

    ``taskuary`` is stamped by the local bridge on every message Taskuary itself sends. Those echoes are
    always swallowed; otherwise a notification could become the assistant's next prompt. ``from_me`` is
    WhatsApp's own flag (the bridge is the owner's account); a Telegram bot only ever hears the other
    side of a private chat, so the named chat itself is what says the words are the owner's.
    """
    if taskuary: return True
    question = str(text or '').strip()
    if not from_me or not question or not enabled(store, channel, chat, connector): return False
    c = connector_for_chat(store, channel, chat, connector)
    # The answer outlives the poll that heard the question, and a poll hands its workers a single
    # writer thread it CLOSES when the cycle ends (channels._Writer) - a store call after that waits
    # on a queue nobody reads again. The turn talks to the store underneath instead, like any request.
    threading.Thread(target=_locked_respond,
                     args=(getattr(store, '_store', store), channel, str(chat), question, c.get('ConnectorId')),
                     name=f'taskuary-{channel}-assistant', daemon=True).start()
    return True


def _locked_respond(store, channel: str, chat: str, question: str, connector_id: int):
    key = (id(store), channel, connector_id, chat)
    with _locks_guard: lock = _locks.setdefault(key, threading.Lock())
    with lock: respond(store, channel, chat, question, connector_id)


def respond(store, channel: str, chat: str, question: str, connector_id: int):
    """Answer synchronously; the poller runs this on a serialized background worker."""
    from . import concierge, general
    try:
        task, _ = general.dock_task(store, f'owner-{channel}')
        tid = task['TaskId']
        store.audit('task', tid, 'assistant_chat_question', f'owner-{channel}',
                    detail={'channel': channel, 'chat': chat, 'chars': len(question)})
        with concierge.delivering(concierge.PHONE):
            # the item on the table is the walk's own, persisted and validated here - a phone has no
            # client state to send, and the key is all say() needs to build the item afresh
            item = concierge.restore_current(store, tid)
            out = concierge.say(store, question, key=concierge.current_key(store, tid) or None, actor='owner')
            text = carry_out(store, out, item)
        send(store, channel, chat, text, connector_id)
    except Exception as e:
        logger.warning(f'the {channel} assistant could not answer: {e}')
        try: send(store, channel, chat, f"I couldn't answer that: {e}", connector_id)
        except Exception as send_error: logger.warning(f'the {channel} assistant could not send its error: {send_error}')


def carry_out(store, out: dict, item: dict | None, actor: str = 'owner', lead: str = '') -> str:
    """Everything the Assistant TAB does after a turn, done here - a chat has no page to do it.

    The desktop's own JavaScript is the missing half of the walk: it opens the draft a reply decision
    asks for, presses the button on a settle the assistant already decided (concierge.AUTO), and moves
    to the next item once something is off the table. Without this the phone would answer "Next." and
    then sit there, and "draft a reply" would be a promise nothing kept.
    """
    from . import concierge
    said, verb = [turn_text(out, lead)], (out.get('decision') or {}).get('verb')
    walk_on, prop = verb == 'next' or bool(out.get('settled')), out.get('proposal')
    if prop and prop.get('auto') and prop.get('status') == 'proposed':
        done = concierge.run_proposal(store, prop, actor)
        said.append(concierge.receipt(store, done, actor))
        walk_on = done.get('status') == 'done' and prop.get('settles')
    elif verb in ('reply', 'redraft') and (item or {}).get('mid'):
        rid = _draft(store, item, verb, (out.get('decision') or {}).get('text') or '')
        if rid:                                             # the draft is the next thing to read, so go to it
            nxt = concierge.surface(store, f'review:{rid}', actor=actor)
            return '\n\n'.join(said + [turn_text(nxt)])
        said.append('I could not write that draft here - it is waiting on the Review tab.')
    if walk_on:
        nxt = concierge.surface(store, actor=actor)
        return '\n\n'.join(said + [turn_text(nxt)])
    return '\n\n'.join(x for x in said if x)


def _draft(store, item: dict, verb: str, instruction: str):
    """Write (or rewrite) the reply the owner just asked for - the same endpoint the page's word calls."""
    from .server import OpenReplyBody, open_reply
    try:
        data = open_reply(int(item['mid']), OpenReplyBody(draft=True, redraft=verb == 'redraft',
                                                          instruction=instruction or None))
    except Exception as e:
        logger.warning(f'the phone could not open a reply on message {item.get("mid")}: {e}')
        return None
    return (data or {}).get('reviewId')


# ── outbound: a turn, as words a chat can carry ─────────────────────────────────────────────────
def choices(out: dict) -> list:
    """The words the owner can answer with. The desktop draws these as the action words under the line;
    a chat has to say them. A proposal is waiting on a yes, so that is the choice - nothing else runs."""
    if out.get('proposal') and not (out['proposal'].get('auto') or out['proposal'].get('status') == 'done'):
        return ['yes, go ahead', 'no, leave it']
    return [str(o) for o in (out.get('options') or [])] or [c['label'] for c in (out.get('chips') or [])]


def turn_text(out: dict, lead: str = '') -> str:
    """One turn as one message: what was said, then what can be said back."""
    say = _TASK_LINK.sub(r'\1', str(out.get('say') or '')).strip()
    words = choices(out)
    return '\n\n'.join(x for x in (lead.strip(), say, ('Reply with: ' + ' · '.join(words)) if words else '') if x)


def _chunks(text: str, limit=3900) -> list[str]:
    """Split a long walkthrough on paragraph boundaries instead of silently truncating it."""
    text = str(text or '').strip()
    if not text: return []
    out = []
    while len(text) > limit:
        cut = max(text.rfind('\n\n', 0, limit), text.rfind('\n', 0, limit), text.rfind(' ', 0, limit))
        if cut < limit // 2: cut = limit
        out.append(text[:cut].rstrip()); text = text[cut:].lstrip()
    if text: out.append(text)
    return out


def send(store, channel: str, chat: str, text: str, connector_id: int = None):
    from . import messengers
    out = messengers.tg_send if channel == 'telegram' else messengers.wa_send
    chunks = _chunks(text)
    for i, chunk in enumerate(chunks):
        prefix = 'Taskuary:\n' if i == 0 else f'Taskuary ({i + 1}/{len(chunks)}):\n'
        out(store, chat, prefix + chunk, connector_id=connector_id)
