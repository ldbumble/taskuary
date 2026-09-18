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
    "whatsapp did not work, i said reply and nothing happened"). So a group jid is accepted only
    when it carries the paired account's number.

    THAT PREFIX IS NECESSARY, NOT SUFFICIENT - every group the owner CREATED wears it too. This is
    the shape check; `own_thread` is the one that counts the people in the room, and it is what the
    card offers from. Nothing reaches the assistant on a chat that was not configured there
    (connector_for_chat), so refusing to offer a real group is what keeps one out.
    """
    chat = str(chat or '').strip()
    if not chat: return False
    if not chat.endswith('@g.us'): return True
    if (connector or {}).get('Type') != 'whatsapp': return False
    from . import messengers
    me = messengers.wa_self_number(store, connector)
    return bool(me) and chat.split('-', 1)[0] == me


def own_thread(store, connector, row, configured: str = '') -> bool:
    """Is this roster row the owner's own thread - the one chat the assistant may live in?

    The number prefix is NECESSARY and not sufficient. WhatsApp gives the "Message yourself" thread
    a legacy group jid, `<their number>-<when it was made>@g.us`, and gives every group they created
    the same shape - so a real group called "Jogging", with people in it, was offered as the
    assistant's private chat, one click from answering questions about the owner's mail in front of
    everyone in it (the owner, 2026-09-17). What settles it is how many people are in the group,
    which the roster now carries.

    A bridge too old to say reports None. That reads as UNKNOWN, not as "nobody": the chat already
    configured keeps working, and nothing new is offered until the bridge can prove it.
    """
    jid = str((row or {}).get('jid') or '').strip()
    if not jid or not is_private(store, connector, jid): return False
    if not (row or {}).get('group'): return True
    people = (row or {}).get('people')
    if people is None: return jid == str(configured or '').strip()
    return int(people) <= 1


LISTEN = ('always', 'walk')      # any time you message it | only while a walk is handed over


def listens(store, connector) -> str:
    """When this channel may listen: 'always', or 'walk' - only while a walk is handed to it.

    PER CHANNEL, because the answer differs by channel: WhatsApp is the owner's own phone and they
    may want it always; a Telegram bot they may want only during a hand-over (the owner, 2026-09-17:
    "the listen any time should be per system?"). A global switch under two per-channel rows reads
    as though it belonged to both equally.

    `phone_assistant` remains the default for a channel that has never been asked, so nothing
    changes for a setup made before this: one switch, still meaning what it meant.
    """
    how = str(_config(connector).get('assistant_listen') or '').strip().lower()
    if how in LISTEN: return how
    return 'always' if store.get_settings().get('phone_assistant') == '1' else 'walk'


def set_listens(store, channel: str, how: str) -> dict:
    """Say when that channel may listen. Written on the card, so the two channels can differ."""
    how = str(how or '').strip().lower()
    if how not in LISTEN: raise ValueError(f'unknown listening rule {how!r} - one of {", ".join(LISTEN)}')
    c = next((x for x in (store.connectors_by_type(channel, with_secret=True) or []) if x and x.get('Active')), None)
    if not c: raise ValueError(f'no {channel} connection is switched on')
    store.set_connector_config(c['ConnectorId'], {**_config(c), 'assistant_listen': how})
    return {'channel': channel, 'listens': how}


def candidates(store, connector) -> list:
    """The chats on this connector that the assistant could be given, newest first.

    Only chats the owner is ALONE in. WhatsApp knows that by counting the room (own_thread, over the
    bridge's roster); Telegram cannot be asked - a bot never sees a fromMe - so the SHAPE of the id
    says it: Telegram gives groups, supergroups and channels a NEGATIVE id and a person a positive
    one, which is the only thing about a Telegram chat that cannot be faked by naming it.

    Returns [{'to', 'name', 'mine'}]. A bridge that will not answer yields nothing rather than
    raising: the panel still has to render, and the chat already chosen is shown whatever happens.
    """
    kind = (connector or {}).get('Type')
    if kind == 'whatsapp':
        from . import messengers
        try: rows = messengers.wa_chats(connector)
        except Exception as e:
            logger.debug(f'whatsapp roster unavailable for the doorway picker: {e}')
            return []
        guide = chat_of(connector)
        return [{'to': r['jid'], 'name': r.get('name') or r['jid'], 'mine': bool(r.get('self'))}
                for r in rows if own_thread(store, connector, r, guide)]
    if kind == 'telegram':
        seen = {}
        for src in store.list_sources(active_only=False):
            if (src.get('Channel') or '') != 'telegram': continue
            cid = str(src.get('Address') or '').strip()
            if not cid or cid == '*' or cid.startswith('-') or not cid.lstrip('-').isdigit(): continue
            # the poller writes "discovered: <the chat's title>" when it first sees one
            name = str(src.get('Owner') or '')
            seen[cid] = name.split(':', 1)[1].strip() if name.startswith('discovered:') else cid
        return [{'to': cid, 'name': name, 'mine': True} for cid, name in seen.items()]
    return []


def doorway_state(store) -> list:
    """Every channel the assistant can be reached on, whether it is set up, and what it could use.

    One answer for every channel, because "where can I talk to it" is one question - it was two
    screens and a text box asking for an id, one per connector card, with the standing permission
    kept somewhere else again (the owner, 2026-09-17).
    """
    out = []
    for channel in CHANNELS:
        for c in store.connectors_by_type(channel, with_secret=True) or []:
            if not c: continue
            out.append({'channel': channel, 'connectorId': c.get('ConnectorId'),
                        'name': c.get('Name') or channel, 'live': bool(c.get('Active')),
                        'chat': chat_of(c), 'listens': listens(store, c),
                        'options': candidates(store, c) if c.get('Active') else []})
    return out


def use_chat(store, channel: str, chat: str) -> dict:
    """Give the assistant a chat on this channel, or take it away with ''.

    Refuses anything the owner is not alone in, for the same reason the picker does not offer it: a
    group must never be able to command the assistant, and an answer about the owner's mail must
    never be posted where other people are reading.
    """
    c = next((x for x in (store.connectors_by_type(channel, with_secret=True) or []) if x and x.get('Active')), None)
    if not c: raise ValueError(f'no {channel} connection is switched on')
    chat = str(chat or '').strip()
    if chat and not any(o['to'] == chat for o in candidates(store, c)):
        raise ValueError(f'{chat} is not a chat you are alone in - the assistant can only live in one of those')
    cfg = _config(c)
    store.set_connector_config(c['ConnectorId'], {**cfg, 'assistant_chat': chat})
    return {'channel': channel, 'chat': chat}


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
    # this channel's own standing permission, not one switch for every channel at once
    return (listens(store, c) == 'always'
            or bool(h and h['channel'] == channel and h.get('chat') == str(chat).strip()))


def polls(store, connector) -> bool:
    """True when this connector must be polled for the doorway alone - it carries the Assistant chat,
    so its messages have to be read even when nothing about it is set to become work."""
    ch = (connector or {}).get('Type')
    if ch not in CHANNELS or not chat_of(connector): return False
    h = handoff(store)
    return listens(store, connector) == 'always' or bool(h and h['channel'] == ch)


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
    named = [' '.join(x for x in (funnel.mark_for(a), f"{a['text']}"
                                  f"{' (' + refs[a['item']] + ')' if refs.get(a['item']) and refs[a['item']] not in a['text'] else ''}") if x)
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
_ANSWERED = {}                         # (channel, id) -> when, so one message is answered once
_ANSWERED_GUARD = threading.Lock()


def _claim(channel: str, message_id) -> bool:
    """First sight of this message? Two readers deliver the same one - the fast doorway loop and the
    connector's own poll - and answering twice would reply twice."""
    if not message_id: return True
    key = (channel, str(message_id))
    with _ANSWERED_GUARD:
        if key in _ANSWERED: return False
        _ANSWERED[key] = time.time()
        if len(_ANSWERED) > 500:
            for k, _ in sorted(_ANSWERED.items(), key=lambda kv: kv[1])[:250]: _ANSWERED.pop(k, None)
    return True


def intercept(store, channel: str, chat: str, text: str, *, from_me=False, taskuary=False, connector=None,
              message_id=None) -> bool:
    """Claim an owner-authored question before it can be discarded or triaged.

    ``taskuary`` is stamped by the local bridge on every message Taskuary itself sends. Those echoes are
    always swallowed; otherwise a notification could become the assistant's next prompt. ``from_me`` is
    WhatsApp's own flag (the bridge is the owner's account); a Telegram bot only ever hears the other
    side of a private chat, so the named chat itself is what says the words are the owner's.
    """
    if taskuary: return True
    question = str(text or '').strip()
    if not from_me or not question or not enabled(store, channel, chat, connector): return False
    if not _claim(channel, message_id): return True         # already answered; swallow the second sighting
    c = connector_for_chat(store, channel, chat, connector)
    # The answer outlives the poll that heard the question, and a poll hands its workers a single
    # writer thread it CLOSES when the cycle ends (channels._Writer) - a store call after that waits
    # on a queue nobody reads again. The turn talks to the store underneath instead, like any request.
    threading.Thread(target=_locked_respond,
                     args=(getattr(store, '_store', store), channel, str(chat), question, c.get('ConnectorId'),
                           message_id),
                     name=f'taskuary-{channel}-assistant', daemon=True).start()
    return True


def _locked_respond(store, channel: str, chat: str, question: str, connector_id: int, message_id=None):
    # the thumb goes up BEFORE the lock: it says "heard you", and it must not wait behind the turn
    # already answering (which is exactly when the owner most needs to know they were heard)
    if message_id:
        from . import messengers
        try: messengers.react(store, channel, chat, message_id, connector_id=connector_id)
        except Exception as e: logger.debug(f'no receipt in {channel}: {e}')
    key = (id(store), channel, connector_id, chat)
    with _locks_guard: lock = _locks.setdefault(key, threading.Lock())
    with lock: respond(store, channel, chat, question, connector_id)


_ASKING = threading.local()                  # the chat a turn came from, for the thread that answers it


def asking() -> dict | None:
    """The chat whose owner is speaking RIGHT NOW on this thread - {channel, chat, connector_id} - or None
    on the desktop. What a report run started here reports back to (server._rerun_report)."""
    return getattr(_ASKING, 'chat', None)


MORNING_KEY, MORNING_AT = 'phone_morning_line', 'phone_morning_line_at'
SCRIPT_LINES = ['Walk me through my tasks', 'Set up Taskuary', 'Set up a report']


def morning_line(store, now=None, force: bool = False) -> int:
    """Once a day, to the assistant's own chat: what is waiting in a breath, and the scripts as numbered
    options, so one reply starts the walk there. The chat used to speak first only for a hand-off, a
    review ping or a report aimed at it - a doorway nobody opens stays shut (the owner, 2026-09-18:
    "does WhatsApp surface the option to click to get started once a day so you will interact with
    it"). Quiet when the pipe is empty; never twice in a day; the three options are always the same -
    set-up never drops off, "there always is more to set up"."""
    from datetime import datetime as _dt
    from . import funnel
    now = now or _dt.now()
    st = store.get_settings()
    if str(st.get(MORNING_KEY, '1')).strip() in ('0', 'false', 'off'): return 0
    today = now.strftime('%Y-%m-%d')
    if not force and (str(st.get(MORNING_AT) or '') == today or now.hour < 6): return 0
    doors = doorways(store)
    if not doors: return 0
    try: p = funnel.pile(store)
    except Exception as e:
        logger.debug(f'morning line: no pile - {e}'); return 0
    items = p.get('items') or []
    if not items and not force: return 0
    on_you = sum(1 for i in items if (funnel.LANE_WORDS.get(i.get('lane'), ('', ''))[1] == 'you'))
    head = (f"Good morning - {len(items)} in the pipe" + (f" · {on_you} on you" if on_you else '') + '.') if items else 'Good morning - the pipe is clear.'
    text = head + '\n\nReply with one of:\n' + '\n'.join(f'{i} · {w}' for i, w in enumerate(SCRIPT_LINES, 1))
    sent = 0
    for d in doors:
        try: send(store, d['channel'], d['chat'], text, d['connectorId']); sent += 1
        except Exception as e: logger.warning(f'the morning line did not reach {d["channel"]}: {e}')
    if sent: store.set_setting(MORNING_AT, today, 'assistant')
    return sent


def script_direct(store, question: str) -> str | None:
    """A script named in so many words needs no model: "walk me through my tasks" is Next, "set up
    Taskuary" opens on the connections, "set up a report" asks for the sentence. Returns the words to
    send, or None when the line is not a script (then the general road reads it)."""
    from . import concierge
    q = ' '.join(str(question or '').lower().replace('-', ' ').split())
    if not q: return None
    if q in ('walk me through my tasks', 'walk me through the tasks', 'walk me through tasks', 'my tasks', 'next'):
        with concierge.delivering(concierge.PHONE):
            out = concierge.surface(store, actor='owner')
            return carry_out(store, out, None, actor='owner')
    if q in ('set up taskuary', 'setup taskuary', 'set up', 'setup'): return script_words(store, 'set up Taskuary')
    if q in ('set up a report', 'setup a report', 'set up report', 'new report'): return script_words(store, 'set up a report')
    return None


def respond(store, channel: str, chat: str, question: str, connector_id: int):
    """Answer synchronously; the poller runs this on a serialized background worker."""
    from . import concierge, general
    _ASKING.chat = {'channel': channel, 'chat': chat, 'connector_id': connector_id}
    try:
        task, _ = general.dock_task(store, f'owner-{channel}')
        tid = task['TaskId']
        store.audit('task', tid, 'assistant_chat_question', f'owner-{channel}',
                    detail={'channel': channel, 'chat': chat, 'chars': len(question)})
        with concierge.delivering(concierge.PHONE):
            # the item on the table is the walk's own, persisted and validated here - a phone has no
            # client state to send, and the key is all say() needs to build the item afresh
            item = concierge.restore_current(store, tid)
            # "undo", alone: the newest undo a receipt offered, run once (the tiers - an instant write
            # says how to put it back, and on a phone the word is the button)
            if question.strip().lower() in ('undo', 'undo it', 'put it back'):
                send(store, channel, chat, concierge.undo_last(store, 'owner'), connector_id)
                return
            question, picked = resolve_index(store, channel, chat, question)   # "2" is the words we numbered
            # a script by name (the morning line's options, or the words themselves) runs with no model
            scripted = script_direct(store, question)
            if scripted:
                send(store, channel, chat, scripted, connector_id)
                return
            straight = answer_the_agent(store, item, question, picked)
            if straight:
                send(store, channel, chat, straight, connector_id)
                return
            out = concierge.say(store, question, key=concierge.current_key(store, tid) or None, actor='owner')
            text = carry_out(store, out, item, picked=picked)
        send(store, channel, chat, text, connector_id)
    except Exception as e:
        logger.warning(f'the {channel} assistant could not answer: {e}')
        try: send(store, channel, chat, f"I couldn't answer that: {e}", connector_id)
        except Exception as send_error: logger.warning(f'the {channel} assistant could not send its error: {send_error}')
    finally: _ASKING.chat = None


def answer_the_agent(store, item: dict | None, words: str, picked: bool, actor: str = 'owner') -> str:
    """The owner picked one of the answers THE AGENT offered: send it, as typed, to the run that asked.

    This is the desktop's choice button, in a chat. It deliberately goes nowhere near the model: the
    words are the agent's own, the request they answer is the one on the item, and interpreting them
    is how "Signed in" became the verb `answer_agent` with no text - which concierge sends to a
    blocked agent as the literal word "yes" (measured 2026-09-15). Returns what to say back, or ''
    when this was not one of those picks and the ordinary walk should take the turn.
    """
    from . import workerstate as ws
    if not picked or not item or item.get('kind') != 'agent': return ''
    if words not in agent_answers(item): return ''
    out = ws.answer_open(store, int(item['tid']), words, actor) if item.get('tid') else {'delivered': False, 'state': 'no_request'}
    who = item.get('agent') or 'the agent'
    if out.get('delivered'): return f'Told {who}: "{words}".'
    if out.get('state') == 'no_request': return f'{who} is not waiting on that any more - it is in its waiting room: "{words}".'
    return f'Could not get that to {who} ({out.get("state")}): {out.get("why") or ""}'.strip()


def carry_out(store, out: dict, item: dict | None, actor: str = 'owner', lead: str = '', picked: bool = False) -> str:
    """Everything the Assistant TAB does after a turn, done here - a chat has no page to do it.

    The desktop's own JavaScript is the missing half of the walk: it opens the draft a reply decision
    asks for, presses the button on a settle the assistant already decided (concierge.AUTO), and moves
    to the next item once something is off the table. Without this the phone would answer "Next." and
    then sit there, and "draft a reply" would be a promise nothing kept.

    `picked` says the owner answered by NUMBER, off a message that showed them the draft and quoted
    what arrived. That is the press of the button the desktop would have drawn, so the proposal it
    makes runs here instead of coming back as "1 · yes, go ahead" - the second question that made one
    decision cost two round trips on a slow chat (the owner, 2026-09-15).
    """
    from . import concierge
    decision = out.get('decision') or {}
    said, verb = [turn_text(out, lead, store)], decision.get('verb')
    # The words can name somebody OTHER than what is on the table. The interpreter resolves that into
    # `decision.target` and the desktop's decide() drafts THERE; drafting on `item` regardless answered
    # whoever happened to be up - "reply to Chana" wrote to Dovid (2026-09-10 audit).
    on = decision.get('target') or item
    walk_on, prop = verb == 'next' or bool(out.get('settled')), out.get('proposal')
    # "Answer it" with nothing after it is not an answer. concierge fills an empty answer_agent with
    # the word "yes" - right for "shall I?", wrong and unrecoverable for "which branch?" - so the chip
    # asks for the words instead of running (the agent's OWN choices never come through here; they are
    # delivered verbatim by answer_the_agent).
    if picked and verb == 'answer_agent' and not (decision.get('text') or '').strip():
        return '\n\n'.join(said + [f"What should I tell {(on or {}).get('agent') or 'it'}? "
                                   'Say it here and I will pass it straight to the run that is waiting.'])
    if prop and picked and prop.get('status') == 'proposed':
        # the number WAS the yes: run it, and say what happened instead of asking again
        said[0] = turn_text({**out, 'proposal': None}, lead, store)
        done = concierge.run_proposal(store, prop, actor)
        said.append(concierge.receipt(store, done, actor))
        walk_on = done.get('status') == 'done' and prop.get('settles')
    elif prop and prop.get('auto') and prop.get('status') == 'proposed':
        done = concierge.run_proposal(store, prop, actor)
        said.append(concierge.receipt(store, done, actor))
        walk_on = done.get('status') == 'done' and prop.get('settles')
        # a SCRIPT started by name from the phone: the tasks walk is Next; set-up opens on the connections
        # (the spec: "or at least see my connectors"); the composer wants a sentence
        script = str((done.get('outcome') or {}).get('script') or '')
        if script:
            if 'tasks' in script: walk_on = True
            else: said.append(script_words(store, script))
    elif verb in ('reply', 'redraft') and (on or {}).get('mid'):
        rid = _draft(store, on, verb, decision.get('text') or '')
        if rid:                                             # the draft is the next thing to read, so go to it
            nxt = concierge.surface(store, f'review:{rid}', actor=actor)
            return '\n\n'.join(said + [turn_text(nxt, store=store)])
        said.append('I could not write that draft here - it is waiting on the Review tab.')
    if walk_on:
        nxt = concierge.surface(store, actor=actor)
        return '\n\n'.join(said + [turn_text(nxt, store=store)])
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
def agent_answers(item: dict | None) -> list:
    """The answers the AGENT itself offered, when it is an agent that is waiting on one.

    These are the words that go back to the run - so they are what a chat must number. Without them a
    numbered pick could only mean the chip "Answer it", which carries no text, and concierge's
    answer_agent sends the literal word "yes" to an agent that asked "which branch?"."""
    it = item or {}
    return [str(c) for c in (it.get('choices') or [])] if it.get('kind') == 'agent' and it.get('asking') else []


def choices(out: dict) -> list:
    """The words the owner can answer with. The desktop draws these as the action words under the line;
    a chat has to say them. A proposal is waiting on a yes, so that is the choice - nothing else runs."""
    if out.get('proposal') and not (out['proposal'].get('auto') or out['proposal'].get('status') == 'done'):
        return ['yes, go ahead', 'no, leave it']
    # an agent's own answers come first: they are the reply it is blocked on, and the chips below
    # them ("Stop it", "Next") are what the owner does INSTEAD of answering
    said = agent_answers(out.get('item'))
    rest = [str(o) for o in (out.get('options') or [])] or [c['label'] for c in (out.get('chips') or [])]
    return said + [w for w in rest if w not in said] if said else rest


def source_line(item: dict | None) -> str:
    """Where it came from, on its own line - the chat's version of the sender and channel icon the
    desktop draws on the row. Nothing when the item has no human source (a report, an agent's own job)."""
    from . import funnel
    if not item: return ''
    who = ' '.join(str(item.get('who') or '').split())
    ch = str(item.get('channel') or '')
    bits = ' · '.join(x for x in (who, ch.replace('_', ' '), str(item.get('ref') or '')) if x)
    return ' '.join(x for x in (funnel.CHANNEL_MARKS.get(ch, ''), bits) if x) if bits else ''


def _cut(text: str, n: int) -> str:
    t = ' '.join(str(text or '').split())
    return t if len(t) <= n else t[:n].rstrip() + '…'


BOX, TICKED = '☐', '☑'
# the few sources whose own spelling title() would get wrong; everything else title-cases fine
_SOURCE_WORDS = {'github': 'GitHub', 'gitlab': 'GitLab', 'pagerduty': 'PagerDuty', 'imessage': 'iMessage'}


_CODE = re.compile(r'`+([^`\n]+?)`+')
_MD = (
    (re.compile(r'^\s{0,3}#{1,6}\s+', re.M), ''),                        # a heading keeps its words
    (re.compile(r'^(\s*)[-*+]\s+\[([ xX])\]\s+', re.M),
     lambda m: m.group(1) + (TICKED if m.group(2).lower() == 'x' else BOX) + ' '),
    (re.compile(r'^\s*```+[a-z]*\s*$', re.M), ''),                       # the fence, never the code
    (re.compile(r'!?\[([^\]]+)\]\([^)]*\)'), r'\1'),                   # the link's words, not its url
    (re.compile(r'(\*\*|__)(.+?)\1', re.S), r'\2'),                     # bold
    (re.compile(r'(?<![\w*])\*(?!\s)([^*\n]+?)(?<!\s)\*(?![\w*])'), r'\1'),   # *italic*
    (re.compile(r'(?<![\w_])_(?!\s)([^_\n]+?)(?<!\s)_(?![\w_])'), r'\1'),       # _italic_
)


def _plain(text) -> str:
    """Markdown as WORDS. Neither sender sets parse_mode - Telegram's sendMessage and the WhatsApp
    bridge both post plain text - so every ** and ` and [](...) arrived as its own punctuation once
    the body stopped being truncated. The desktop renders them; here they are simply removed.

    Code spans come out first and go back last, so `snake_case_name` is not read as an italic."""
    kept = []
    def _hold(m):
        kept.append(m.group(1))
        return f'\x00{len(kept) - 1}\x00'
    out = _CODE.sub(_hold, str(text or ''))
    for pat, rep in _MD: out = pat.sub(rep, out)
    for i, code in enumerate(kept): out = out.replace(f'\x00{i}\x00', code)
    return out


def _quote(text) -> str:
    """Every line marked, not just the first - a multi-paragraph body has to keep reading as theirs."""
    return '\n'.join('> ' + l.rstrip() if l.strip() else '>' for l in str(text or '').strip().splitlines())


def checklist_block(store, item: dict | None) -> str:
    """The desktop's TASK LIST, as boxes a chat can print - the job the card exists for, which the
    phone never showed at all (the owner, 2026-09-18: "where is the github logo, todo's sections").
    Read-only here, exactly as on the card: ticking stays on the task."""
    tid = (item or {}).get('tid')
    if store is None or not tid: return ''
    try: items = store.task_checklist(int(tid))
    except Exception as e:
        logger.debug(f'the phone could not read the task list: {e}')
        return ''
    if not items: return ''
    done = sum(1 for i in items if i.get('done'))
    boxes = [f'{TICKED if i.get("done") else BOX} {i["text"]}' for i in items]
    return '\n'.join([f'TASK LIST · {done} of {len(items)} done'] + boxes)


def thread_line(store, msg: dict) -> str:
    """"Email context · 2 messages combined by triage" - the card says how much of the thread is behind
    the one body it shows, and the chat showed one message as if it were the whole of it."""
    if store is None or not msg: return ''
    try: kin = store.thread_messages(msg.get('ConversationId'), msg.get('Subject'))
    except Exception as e:
        logger.debug(f'the phone could not count the thread: {e}')
        return ''
    n = len([m for m in kin if str(m.get('Status') or '') != 'context'])
    if n < 2: return ''
    key = str(msg.get('Channel') or '')
    ch = _SOURCE_WORDS.get(key) or key.replace('_', ' ').title() or 'Thread'
    return f'{ch} context · {n} messages combined by triage'


def status_line(item: dict | None) -> str:
    """The card's kicker and the one line under it, in the words lanes.json already holds - the chat
    must not grow a second copy of a vocabulary that took two tables to unify."""
    from . import funnel
    word = (funnel.LANE_WORDS.get(str((item or {}).get('lane') or '')) or ('',))[0]
    why = ' '.join(str((item or {}).get('why_idle') or (item or {}).get('why') or '').split())
    # the WHY only. A bare lane word repeats the mark the say line already wears ("fyi" under a 👀),
    # and the card's kicker earns its place with a header a chat does not have.
    return f'{word} - {why}' if word and why else ''


def decision_block(store, item: dict | None) -> str:
    """WHAT THE OWNER IS BEING ASKED TO APPROVE, in the message that asks them.

    The desktop draws the incoming line and the draft under the card, so concierge's own sentence says
    "approve the draft below" - and on a phone there was nothing below it (the owner, 2026-09-15: "you
    didn't show the message or the drafed reply? what am i approving?"). A yes is only a yes to
    something you were shown. The draft rides in FULL: it is the thing being sent in your name, and
    send() already splits a long message on paragraph boundaries.
    """
    if not item: return ''
    parts = []
    # an agent that is blocked asked something exact; the alert only ever said that a hand went up
    if item.get('kind') == 'agent' and item.get('asking'):
        asked = ' '.join(str((item.get('tail') or [''])[0]).split())
        if asked: parts.append('IT ASKED\n' + _cut(asked, 600))
    todos = checklist_block(store, item)
    if todos: parts.append(todos)
    try:
        if item.get('mid'):
            msg = store.get_message(int(item['mid'])) or {}
            kin = thread_line(store, msg)
            if kin: parts.append(kin)
            # WHOLE, not a teaser: _cut also flattened every paragraph, and the rest of it existed
            # only on the desktop. send() splits on paragraph boundaries, so length costs bubbles.
            body = str(msg.get('BodyText') or '').strip()
            # a REPORT is ours, not a letter: the card prints its sections, and "THEY WROTE" over a
            # quoted block credits a person with what Taskuary itself wrote
            if body and (item.get('kind') == 'report' or msg.get('Channel') == 'report'): parts.append(_plain(body))
            elif body: parts.append('THEY WROTE\n' + _quote(_plain(body)))
        if item.get('rid'):
            rv = store.get_review(int(item['rid'])) or {}
            # an `action` review's DraftText is the proposal's JSON, never prose to read out
            draft = str(rv.get('DraftText') or '').strip() if rv.get('Kind') == 'draft' else ''
            if draft: parts.append('YOUR DRAFT\n' + draft.strip())
    except Exception as e:
        logger.debug(f'the phone could not show what is on the table: {e}')
    return '\n\n'.join(parts)


def script_words(store, script: str) -> str:
    """A script, as a chat can hold it. Set-up from a phone opens on what is connected - each live
    connection with its state, then the stops still to do (the owner, 2026-09-18: "or at least see my
    connectors"); the composer asks for the sentence it builds from."""
    from . import appfacts, walk
    if 'report' in script.lower():
        return 'Tell me what to set up - a check that reads, or a workflow that writes - in a sentence, and I put it together.'
    conns = appfacts.connections(store); live = [c for c in conns if c['active']]
    lines = ['SET UP TASKUARY - what is connected:']
    lines += [f"· {c['name']} ({c['type']}{', no key yet' if not c['has_secret'] else ''}{' - ERROR ' + c['last_error'] if c['last_error'] else ''})" for c in live] or ['· nothing yet']
    lines.append(f"{len(conns) - len(live)} more in the catalogue, off - say \"connect <name>\" and I open the card.")
    try:
        stops = walk.state(store)['stops']
        todo = [s for s in stops[:5] if 'done' in s and not s.get('done')]
        if todo: lines.append('Still to do: ' + '; '.join(s.get('title') or s['key'] for s in todo) + ' - the desktop walk does each in a click.')
        else: lines.append('The five set-up steps are done; the desktop walk shows the rest of the app.')
    except Exception as e: logger.debug(f'the phone set-up walk could not read the stops: {e}')
    return '\n'.join(lines)


def turn_text(out: dict, lead: str = '', store=None) -> str:
    """One turn as one message: where it came from, what was said, then what can be said back.

    The options used to ride one line joined by dots, which read as a single run-on sentence on a
    phone (the owner, 2026-09-10: "reply with should make it more clear they are separate"). Each owns
    a line now, and carries the number that answers it - see resolve_index for why that number works.

    `store` is what lets the turn SHOW what it is asking about (decision_block). It is optional only
    so a caller with nothing to look up still gets its words.
    """
    from . import funnel
    item = out.get('item') or {}
    say = _TASK_LINK.sub(r'\1', str(out.get('say') or '')).strip()
    mark = funnel.mark_for(item)
    if say and mark: say = f'{mark} {say}'
    state = status_line(item)
    # the say line often already carries the cause; a card does not print the same sentence twice
    if state and state.split(' - ', 1)[-1].lower() in say.lower(): state = state.split(' - ', 1)[0]
    head = '\n'.join(x for x in (source_line(item), say, state) if x)
    words = choices(out)
    opts = 'Reply with one of:\n' + '\n'.join(f'{i} · {w}' for i, w in enumerate(words, 1)) if words else ''
    shown = decision_block(store, item) if store is not None else ''
    return '\n\n'.join(x for x in (lead.strip(), head, shown, opts) if x)


OFFERED_KEY = 'remote_offered'
_OFFERED = re.compile(r'^\s*(\d+) · (.+?)\s*$', re.M)


def remember_offered(store, channel: str, chat: str, text: str) -> list:
    """The options this message just numbered, kept against the chat that was sent them."""
    words = [m.group(2) for m in _OFFERED.finditer(str(text or ''))]
    if words: store.set_setting(f'{OFFERED_KEY}:{channel}:{chat}', json.dumps(words), 'assistant')
    return words


def resolve_index(store, channel: str, chat: str, text: str) -> tuple[str, bool]:
    """"2" as an answer - because WE numbered the options a moment ago. Returns (words, picked).

    The code indexes the list it offered; it reads no words and knows no verbs (the intent model still
    does that, on whatever this returns). Anything that is not one of the numbers we just wrote comes
    back untouched, as the owner's own words.

    `picked` is what makes the number a DECISION rather than a suggestion: the owner chose a line we
    wrote, off a message that showed them what it was about, so nothing is left to confirm (PW: the
    owner, 2026-09-15, having answered "1" to "Send the reply" and been asked "1 · yes, go ahead" -
    "this is confusing? I wrote 1 but it asked me again?"). Their own words stay a suggestion, because
    there we are reading intent and can be wrong.
    """
    t = str(text or '').strip().lstrip('#').rstrip('.').strip()
    if not t.isdigit(): return text, False
    try: words = json.loads(store.get_settings().get(f'{OFFERED_KEY}:{channel}:{chat}') or '[]')
    except ValueError: words = []
    i = int(t)
    return (words[i - 1], True) if 1 <= i <= len(words) else (text, False)


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
    # every road to this chat passes here, so this is where what we offered is written down
    try: remember_offered(store, channel, chat, text)
    except Exception as e: logger.debug(f'could not keep the offered options for {channel}: {e}')
    chunks = _chunks(text)
    for i, chunk in enumerate(chunks):
        prefix = 'Taskuary:\n' if i == 0 else f'Taskuary ({i + 1}/{len(chunks)}):\n'
        out(store, chat, prefix + chunk, connector_id=connector_id)
