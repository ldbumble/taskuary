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
    # the desktop hears the turn START (it shows the typing dots, as for its own turns) and END (it reads the
    # conversation at once instead of on its 30 s tick)
    from . import live
    live.emit(live.CHAT, thinking=True, channel=channel)
    try:
        with lock: respond(store, channel, chat, question, connector_id)
    finally: live.emit(live.CHAT, thinking=False, channel=channel)


_ASKING = threading.local()                  # the chat a turn came from, for the thread that answers it


def asking() -> dict | None:
    """The chat whose owner is speaking RIGHT NOW on this thread - {channel, chat, connector_id} - or None
    on the desktop. What a report run started here reports back to (server._rerun_report)."""
    return getattr(_ASKING, 'chat', None)


# ── the start of the walk: who wants what, the same grouping the desktop draws (walkSummary.js) ──
# KEEP IN STEP with website/src/walkSummary.js: the four groups, and which lanes land in each. A grouping
# of lanes the pile already carries - nothing is judged here (2026-09-23).
GROUPS = (('people', 'People want'), ('you', 'You wanted'), ('agents', 'Agents waiting'), ('read', 'Nothing to decide'),
          ('passed', 'You passed'))
_AGENT_LANES = {'blocked', 'stopped', 'queued', 'working', 'broken', 'unjudged'}
ROWS_PER_GROUP = 5


def group_of(i: dict) -> str:
    # walked past with Next: the rail's Passed band (funnelPile.levelOf) - never back under "Agents waiting" (2026-09-24)
    if i.get('surfaced') and i.get('order_band') == 2: return 'passed'
    if i.get('kind') in ('action', 'agent', 'agentdone') or i.get('lane') in _AGENT_LANES: return 'agents'
    if i.get('lane') in ('report', 'fyi') or i.get('kind') in ('fyis', 'report', 'idea', 'wrapup'): return 'read'
    if i.get('channel') in ('own', 'assistant'): return 'you'
    return 'people'


def who_of(i: dict) -> str:
    who, title = ' '.join(str(i.get('who') or i.get('agent') or '').split()), str(i.get('title') or '')
    if who and not title.lower().startswith(who.lower()[:16]): return who
    return 'Report' if i.get('kind') == 'report' or i.get('lane') == 'report' else who or 'someone'


def who_wants_what(items: list) -> str:
    """The desktop's opener, as a chat can print it: the count in a sentence, then each group's rows."""
    from . import funnel
    # meetings are the day's strip (meetings_line), never a row someone wants - as on the desktop
    live = [i for i in items or [] if i.get('lane') != 'working' and i.get('kind') != 'meeting']
    if not live: return 'Nothing is waiting on you.'
    ready = sum(1 for i in live if i.get('lane') == 'approve')
    skip = sum(1 for i in live if group_of(i) == 'read')
    yours = sum(1 for i in live if group_of(i) == 'you')
    passed = sum(1 for i in live if group_of(i) == 'passed')
    word = len(live) - ready - skip - yours - passed
    parts = [x for x in (ready and f"{ready} {'is' if ready == 1 else 'are'} ready - you only approve",
                         word and f"{word} {'needs' if word == 1 else 'need'} a word",
                         yours and f"{yours} {'is' if yours == 1 else 'are'} on your list",
                         skip and f"{skip} you can skip", passed and f"{passed} you passed") if x]
    lines = [f"{len(live)} thing{'' if len(live) == 1 else 's'}. " + ', '.join(parts)[:1].upper() + ', '.join(parts)[1:] + '.']
    for key, word_ in GROUPS:
        rows = [i for i in live if group_of(i) == key]
        if not rows: continue
        lines.append(f'\n{word_.upper()} · {len(rows)}')
        for i in rows[:ROWS_PER_GROUP]:
            state = ('draft ready' if i.get('kind') != 'action' else 'wants a yes') if i.get('lane') == 'approve' \
                else (funnel.LANE_WORDS.get(str(i.get('lane') or '')) or ('',))[0]
            lines.append(f"· {who_of(i)} - {_cut(i.get('title') or '', 70)}" + (f' ({state})' if state else ''))
        if len(rows) > ROWS_PER_GROUP: lines.append(f'  and {len(rows) - ROWS_PER_GROUP} more')
    return '\n'.join(lines)


def meetings_line(store) -> str:
    """Today's meetings, one line each - the day strip the desktop draws over the same opener."""
    from . import calendar as cal
    try: t = cal.today(store)
    except Exception as e:
        logger.debug(f'the phone could not read today\'s meetings: {e}'); return ''
    evs = [e for e in t.get('events') or [] if not e.get('all_day')]
    if not evs: return ''
    return '\n'.join([f'TODAY\'S MEETINGS · {len(evs)}'] + [f"· {cal.span(e['start'], e.get('end') or '')} {e.get('subject') or ''}" for e in evs])


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
    # the desktop's opener: the day's meetings, then who wants what (2026-09-23)
    head = '\n\n'.join(x for x in ('Good morning.', meetings_line(store),
                                     who_wants_what(items) if items else 'The pipe is clear.') if x)
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
            from . import funnel
            # the day's summary opens the WALK; "next" inside it is the desktop's Next, which reprints nothing
            try: opener = who_wants_what(funnel.pile(store).get('items') or []) if q != 'next' else ''
            except Exception as e:
                logger.debug(f'the phone walk opened without its summary: {e}'); opener = ''
            out = concierge.surface(store, actor='owner')
            return carry_out(store, out, None, actor='owner', lead=opener)
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
            # A PICK IS THE BUTTON: what the desktop's click would run, run here in code - the model reads only
            # words (the owner, 2026-09-25: the phone matches the desktop exactly). A list answers ONE reply:
            # whatever comes next, the old numbers are gone, so a stale "2" can never fire.
            acts = acts_for(store, channel, chat)
            try: offered = json.loads(store.get_settings().get(f'{OFFERED_KEY}:{channel}:{chat}') or '[]') or []
            except ValueError: offered = []
            act = acts.get(question) if picked else None
            forget_offered(store, channel, chat); _ACTS.rows = None
            if act:
                send(store, channel, chat, run_act(store, act, item), connector_id)
                return
            # ...and on an fyi batch a number names one of the lines we printed: open that one - the item on
            # the table, its own text and its own options under it - as the desktop's "Talk about it" does
            key = next((k for k, line in member_lines(item) if picked and line == question), None)
            if key:
                nxt = concierge.surface(store, key, actor='owner')
                send(store, channel, chat, carry_out(store, nxt, nxt.get('item')), connector_id)
                return
            # MORE, picked: the rest of what the card folds, then the same choices again without it
            if picked and question == MORE:
                again = [w for w in offered if w != MORE]
                _offer([(w, acts[w]) for w in again if w in acts])
                folded = more_text(store, item) or 'Nothing more on this one.'
                opts = 'Reply with one of:\n' + '\n'.join(f'{i} · {w}' for i, w in enumerate(again, 1)) if again else ''
                send(store, channel, chat, '\n\n'.join(x for x in (folded, opts) if x), connector_id)
                return
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


def _settled_the_table(prop: dict, item: dict | None) -> bool:
    """The desktop's rule for walking on (proposalCard.afterConfirm): only a settling action on the item ON THE TABLE.
    The phone walked on after any settling action, so a hand-off started from plain words arrived with the next
    item stapled under its receipt - an email nobody asked about (the 2026-09-24 chat audit; the owner: the phone
    follows the desktop)."""
    return bool(prop.get('settles') and prop.get('key') and item and prop['key'] == item.get('key'))


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
    # whoever happened to be up - "reply to Erin" wrote to Dovid (2026-09-10 audit).
    on = decision.get('target') or item
    walk_on, prop = verb == 'next' or bool(out.get('settled')), out.get('proposal')
    # "Answer it" with nothing after it is not an answer. concierge fills an empty answer_agent with
    # the word "yes" - right for "shall I?", wrong and unrecoverable for "which branch?" - so the chip
    # asks for the words instead of running (the agent's OWN choices never come through here; they are
    # delivered verbatim by answer_the_agent).
    if picked and verb == 'answer_agent' and not (decision.get('text') or '').strip():
        return '\n\n'.join(said + [f"What should I tell {(on or {}).get('agent') or 'it'}? "
                                   'Say it here and I will pass it straight to the run that is waiting.'])
    if prop and picked and prop.get('status') == 'proposed' and not asks(prop):
        # the number WAS the yes: run it, and say what happened instead of asking again
        said[0] = turn_text({**out, 'proposal': None}, lead, store)
        done = concierge.run_proposal(store, prop, actor)
        said.append(concierge.receipt(store, done, actor))
        walk_on = done.get('status') == 'done' and _settled_the_table(prop, item)
    elif prop and prop.get('auto') and prop.get('status') == 'proposed':
        done = concierge.run_proposal(store, prop, actor)
        said.append(concierge.receipt(store, done, actor))
        walk_on = done.get('status') == 'done' and _settled_the_table(prop, item)
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
        said.append('I could not write that draft here - it is waiting on the task page.')
    if walk_on:
        nxt = concierge.surface(store, actor=actor)
        return '\n\n'.join(said + [turn_text(nxt, store=store)])
    return '\n\n'.join(x for x in said if x)


ALT_QUESTION = {'not_ours': 'How far?', 'agent': 'Which agent?'}


def _picking_repo(prop: dict) -> bool:
    """proposalCard.pickingRepo: a coding hand-off whose checkout nobody named asks for one before it starts."""
    p = prop.get('params') or {}
    return (prop.get('kind') == 'task.create_from_text' and p.get('kind') == 'coding' and prop.get('clear') is False
            and bool(prop.get('repo_choices')))


def asks(prop: dict) -> bool:
    """The card has a question of its own - a pick does not run it until that is answered."""
    return bool(prop and (prop.get('alts') or _picking_repo(prop)))


def proposal_choices(prop: dict) -> tuple[str, list]:
    """The desktop card as numbered rows: its question, then (label, act) for each answer. The current answer IS the
    confirm button; another answer is a new proposal from the same road; Cancel leaves everything where it is."""
    from . import concierge
    pid, rows, q = prop['id'], [], ''
    ok = {'id': pid, 'key': prop.get('key'), 'settles': bool(prop.get('settles'))}      # what the run settles, for walking on
    if _picking_repo(prop):
        guess = (prop.get('params') or {}).get('repo') or ''
        q = 'Which repository should the coding agent use?'
        rows += [(f'{r} (best guess)' if r == guess else r, {'t': 'repo', **ok, 'repo': r})
                 for r in sorted(prop['repo_choices'], key=lambda r: r != guess)]
    alts = prop.get('alts') or []
    if alts:
        q = q or ALT_QUESTION.get(concierge.ALT_OF.get(prop.get('verb')), '')
        cur = [a for a in alts if a.get('current')]
        rows += [(a['label'], {'t': 'confirm', **ok}) for a in cur if not _picking_repo(prop)]
        rows += [(a['label'], {'t': 'alt', 'verb': a['verb'], 'key': prop.get('key'), 'table': bool(prop.get('settles'))})
                 for a in alts if not a.get('current')]
    if not rows: rows = [('yes, go ahead', {'t': 'confirm', **ok})]
    return q, rows + [('no, leave it' if not q else 'Cancel', {'t': 'cancel', 'id': pid})]


def _item_for(store, key: str, item: dict | None) -> dict | None:
    from . import funnel
    if item and item.get('key') == key: return item
    return funnel.next_item(store, key, include_surfaced=True) or funnel.item_for_key(store, key)


def _ran(store, prop: dict, done: dict, item: dict | None, actor: str) -> str:
    """After the run: the receipt, an Undo when it offered one, and the next item when the table was settled."""
    from . import concierge
    said = concierge.receipt(store, done, actor)
    undo = [('Undo', {'t': 'undo'})] if ' Undo: ' in said else []
    if done.get('status') == 'done' and _settled_the_table(prop, item):
        return '\n\n'.join([said, turn_text(concierge.surface(store, actor=actor), store=store, extra=undo)])
    if undo: return '\n\n'.join([said, turn_text({}, store=store, extra=undo)])
    return said


def _settle(store, prop: dict, item: dict | None, actor: str) -> str:
    """A proposal a pick made: run it, unless its card asks something first - then ask that, numbered."""
    from . import concierge
    if asks(prop):
        said = f"{prop['label']}: {prop['summary']}." if prop.get('label') and prop.get('summary') else prop.get('say')
        return turn_text({'say': said, 'proposal': prop}, store=store)
    return _ran(store, prop, concierge.run_proposal(store, prop, actor), item, actor)


def run_act(store, act: dict, item: dict | None, actor: str = 'owner') -> str:
    """One numbered pick, run the way the desktop's button runs it - never through the model."""
    from . import concierge, operations
    t = act.get('t')
    try:
        if t == 'next': return carry_out(store, concierge.surface(store, actor=actor), None, actor)
        if t == 'undo': return concierge.undo_last(store, actor)
        if t in ('confirm', 'cancel', 'repo'):
            op = operations.get(store, act.get('id') or '')
            if not op or op.get('status') != 'proposed': return 'That one is not waiting on you any more - nothing moved.'
            if t == 'cancel':
                operations.cancel(store, op['id'], actor)
                return 'Left it - nothing moved.'
            if t == 'repo': op = {**op, **operations.revise(store, op['id'], {**(op.get('params') or {}), 'repo': act['repo']}, actor)}
            prop = {**op, 'settles': bool(act.get('settles')), 'key': act.get('key')}
            return _ran(store, prop, concierge.run_proposal(store, op, actor), item, actor)
        key, verb = act.get('key') or '', act.get('verb') or ''
        on = _item_for(store, key, item)
        if not on: return 'That one is not in front of you any more - say next and I show what is.'
        if t == 'alt':
            prop = concierge.propose_direct(store, verb, key, actor=actor, table=bool(act.get('table')), exact=True)
            # the pick answered the card's question; only a checkout still to choose is left to ask
            return _settle(store, {**prop, 'alts': []}, item, actor)
        if verb == 'answer_agent':
            return f"What should I tell {on.get('agent') or 'it'}? Say it here and I will pass it straight to the run that is waiting."
        if verb in ('reply', 'redraft') and on.get('mid'):
            rid = _draft(store, on, verb, '')
            if not rid: return 'I could not write that draft here - it is waiting on the task page.'
            return turn_text(concierge.surface(store, f'review:{rid}', actor=actor), store=store)
        prop = concierge.propose_direct(store, verb, key, actor=actor, table=bool(item and item.get('key') == key))
        return _settle(store, prop, item, actor)
    except ValueError as e: return f'Not done - {e}. Nothing moved.'


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


def member_lines(item: dict | None) -> list:
    """An fyi batch's members as (key, line): the line the phone prints, numbered, and what a number
    answers. The desktop opens one member with "Talk about it"; a chat had the four lines and no door
    into any of them (the owner, 2026-09-20: "how do you dig into one specific one?")."""
    from . import funnel
    if not item or item.get('kind') != 'fyis': return []
    return [(m.get('key'), ' '.join(x for x in (funnel.CHANNEL_MARKS.get(str(m.get('channel') or ''), ''),
                                                 f"{' '.join(str(m.get('who') or 'someone').split())} - {m.get('title') or ''}") if x))
            for m in item.get('items') or []]


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


def _body(store, item: dict | None) -> tuple[dict, str, bool]:
    """(the message, its body, whether it is a report) - what arrived, or what Taskuary itself wrote."""
    if store is None or not (item or {}).get('mid'): return {}, '', False
    try: msg = store.get_message(int(item['mid'])) or {}
    except Exception as e:
        logger.debug(f'the phone could not read the message: {e}')
        return {}, '', False
    from .triage import strip_banner
    return msg, strip_banner(str(msg.get('BodyText') or '')).strip(), item.get('kind') == 'report' or msg.get('Channel') == 'report'


def _draft_text(store, item: dict | None) -> str:
    """The reply waiting on a yes - never an `action` review, whose DraftText is the proposal's JSON."""
    if store is None or not (item or {}).get('rid'): return ''
    try: rv = store.get_review(int(item['rid'])) or {}
    except Exception as e:
        logger.debug(f'the phone could not read the draft: {e}')
        return ''
    return str(rv.get('DraftText') or '').strip() if rv.get('Kind') == 'draft' else ''


# the one word the phone adds to what the walk offers: the rest of what is folded, as the card's More
MORE = 'More'
EXCERPT = 400                                  # a message longer than this shows its opening; More has the rest


def decision_block(store, item: dict | None) -> str:
    """WHAT IS READY - the card's box, in the message that asks (the owner, 2026-09-15: "what am i
    approving?"). A yes is only a yes to something you were shown, so the draft rides in FULL.

    Since 2026-09-23 it is the desktop card's box and nothing more: the draft when there is one, the
    agent's question, a report's first section, or a message's opening lines. What they wrote under a
    draft, the rest of a report and the rest of a long message are behind More (more_text), and the task
    list stays on the task - on the phone as on the desktop ("keep the detail task list on the actual
    task tab").
    """
    if not item: return ''
    parts = []
    # an agent that is blocked asked something exact; the alert only ever said that a hand went up
    if item.get('kind') == 'agent' and item.get('asking'):
        asked = ' '.join(str((item.get('tail') or [''])[0]).split())
        if asked: parts.append('IT ASKED\n' + _cut(asked, 600))
    draft = _draft_text(store, item)
    msg, body, is_report = _body(store, item)
    if draft:
        parts.append('YOUR DRAFT\n' + draft)
    elif body and is_report:
        # a report is OURS, not a letter: its first section here, each further one a bubble of its own
        # under More, and the `--- raw data ---` dump cut where the desktop cuts it (2026-09-19)
        from . import chatformat
        said = chatformat.blocks(body)
        if said: parts.append(said[0])
    elif body:
        # "THEY WROTE" over their own words; a report credits nobody, a draft puts them behind More
        kin = thread_line(store, msg)
        opening = _plain(body)
        if len(opening) > EXCERPT: opening = _cut(opening, EXCERPT)
        parts.append('\n'.join(x for x in (kin, 'THEY WROTE', _quote(opening)) if x))
    return '\n\n'.join(parts)


def more_text(store, item: dict | None) -> str:
    """What the card folds - the phone's More. Under a draft, what they wrote; under a report, every
    section after the first; under a long message, the whole of it. '' when nothing is folded."""
    if not item: return ''
    msg, body, is_report = _body(store, item)
    if not body: return ''
    if is_report:
        from . import chatformat
        rest = chatformat.blocks(body)[1:]
        return chatformat.BREAK + chatformat.BREAK.join(rest) if rest else ''
    if _draft_text(store, item) or len(_plain(body)) > EXCERPT:
        kin = thread_line(store, msg)
        return '\n'.join(x for x in (kin, 'THEY WROTE', _quote(_plain(body))) if x)
    return ''


# what the first word does, said before it is pressed - the desktop card's "then" line. Keyed on the
# vocabulary's verbs (concierge.CHIPS), so a word the table does not name simply says nothing.
THEN = {'approve': 'sends the draft above, in your name.',
        'answer_agent': 'goes straight to the agent; it picks up where it stopped.',
        'reply': 'writes a draft for you to approve here - nothing is sent.',
        'regular_agent': 'hands it to an agent - triage picks a coding or a non-coding one, and you can switch before it starts.',
        'coder': 'starts a coding agent on it; it comes back here when it stops.',
        'mine': 'puts it on your own list - no agent starts.',
        'stop_agent': 'saves what the agent did and ends its session; the task stays open.',
        'close': 'ends the task - it stops coming back.'}
# an action card's Send is "Run it": it runs what the card shows, it sends no mail
THEN_KIND = {('approve', 'action'): 'runs what the card above shows.'}


# words that put a thing DOWN rather than do it: never the card's verb while a real one is offered
_DOWN = ('close', 'not_ours', 'not_ours_sender', 'block_sender', 'done')


def primary(out: dict) -> dict | None:
    """The card's verb: the first word that DOES the thing - a reply with no draft yet leads with
    drafting it, not with closing the task (the vocabulary lists close first for a waiting draft)."""
    chips = [c for c in (out.get('chips') or []) if isinstance(c, dict) and c.get('verb') and c.get('verb') != 'next']
    return next((c for c in chips if c['verb'] not in _DOWN), chips[0] if chips else None)


def then_line(out: dict, store=None) -> str:
    """"Send the reply: sends the draft above, in your name." - only on a card that shows what it is about."""
    c = primary(out)
    if store is None or not c or agent_answers(out.get('item')) or out.get('proposal'): return ''
    said = THEN_KIND.get((c['verb'], (out.get('item') or {}).get('kind'))) or THEN.get(c['verb'])
    return f"{c.get('label')}: {said}" if said else ''


def lead_line(store, item: dict | None, say: str) -> str:
    """Who wants what: the first sentence of the task's summary, which triage now writes as exactly that
    (triage.TASK_FIELDS). Nothing when there is no task, or the assistant's own line already said it."""
    tid = (item or {}).get('tid')
    if store is None or not tid or item.get('kind') == 'fyis': return ''
    try: summary = str((store.get_task(int(tid)) or {}).get('Summary') or '').strip()
    except Exception as e:
        logger.debug(f'the phone could not read the task summary: {e}')
        return ''
    first = re.split(r'(?<=[.!?])\s+', summary)[0].strip() if summary else ''
    return first if first and first.lower() not in (say or '').lower() else ''


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


def turn_text(out: dict, lead: str = '', store=None, extra: list = None) -> str:
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
    head = '\n'.join(x for x in (source_line(item), say, state, lead_line(store, item, say)) if x)
    if item.get('kind') == 'fyis':
        # THE ITEMS, one per line, and nothing else: the say line restated them as one run-on sentence and
        # the status line added "fyi - people told you things" under it, and on a phone that read as
        # nothing at all (the owner, 2026-09-18: "don't need random summary, just show the items")
        # ...each NUMBERED, so a number opens that one (respond): the desktop's "Talk about it" door
        members = member_lines(item)
        head = '\n'.join([f"{mark} {len(members)} fyi · nothing to do"] + [f'{i} · {line}' for i, (_k, line) in enumerate(members, 1)])
    words, first = choices(out), len(member_lines(item)) + 1
    prop = out.get('proposal') if (out.get('proposal') or {}).get('status', 'proposed') == 'proposed' else None
    if prop and prop.get('id') and not prop.get('auto'):
        # THE CARD'S QUESTION, numbered: how far a Not ours goes, which agent, which checkout - each answer runs
        q, rows = proposal_choices(prop)
        if q: head = '\n'.join(x for x in (head, q) if x)
        words = [label for label, _ in rows]
        _offer(rows)
    else:
        _offer([(c['label'], {'t': 'next'} if c.get('verb') == 'next' else {'t': 'verb', 'verb': c['verb'], 'key': item.get('key')})
                for c in out.get('chips') or [] if isinstance(c, dict) and c.get('verb') and c.get('label') and item.get('key')])
    # THE CARD'S ORDER: the verb, then Next, then More, then the rest - the desktop's two buttons and its
    # Also line, as one numbered list (2026-09-23). A proposal's yes/no and an agent's own answers keep
    # theirs: those are the answer itself, not a choice of what to do.
    if not out.get('proposal') and not agent_answers(item):
        nxt = [w for w in words if str(w).strip().lower() == 'next']
        rest = [w for w in words if w not in nxt]
        lead_word = (primary(out) or {}).get('label')
        first_ = [w for w in rest if w == lead_word][:1] or rest[:1]
        more = [MORE] if store is not None and more_text(store, item) else []
        words = first_ + nxt + more + [w for w in rest if w not in first_]
    if item.get('kind') == 'fyis':
        # THE WAY ON, which only this channel has to say. The desktop card carries its own "All read,
        # next" button, so concierge.CHIPS leaves `next` off the batch on purpose - and a chat has no
        # buttons, so the phone listed four things and offered no way past them (the owner, 2026-09-22:
        # "next to go to next group"). The word is the vocabulary's own, so the number answers it
        # exactly as it does on every other card.
        from . import concierge
        # ...unless the walk already offered one under its own name ("All read, next" is the batch
        # card's button, and on the phone it arrives as a word like any other): two ways to say the
        # same move, numbered separately, is the thing that made the desktop drop a button in the
        # first place.
        if not any('next' in str(w).lower() for w in words):
            words = words + [concierge.CHIP_WORDS['next']]
            _offer([(concierge.CHIP_WORDS['next'], {'t': 'next'})])
    # ...and what a NUMBER does, said plainly. "Open one" describes a door on a screen that is not
    # here; on a phone the number is the only way to see what the line is actually about.
    # A plain answer with nothing on the table offered "Reply with one of: 1 · Next" under every reply - three
    # lines of menu for the one word the owner can always type (2026-09-24 audit). The desktop's lone Next is
    # one small button; on a phone it is noise.
    if not item and [str(w).strip().lower() for w in words] == ['next']: words = []
    if extra:
        words = words + [label for label, _ in extra]
        _offer(extra)
    lead_in = ('Reply with a number to read that message in full, or:' if item.get('kind') == 'fyis'
               else 'Reply with a number to open one, or:') if first > 1 else 'Reply with one of:'
    opts = (lead_in + '\n'
            + '\n'.join(f'{i} · {w}' for i, w in enumerate(words, first))) if words else ''
    shown = decision_block(store, item) if store is not None else ''
    return '\n\n'.join(x for x in (lead.strip(), head, shown, then_line(out, store), opts) if x)


OFFERED_KEY = 'remote_offered'
_OFFERED = re.compile(r'^\s*(\d+) · (.+?)\s*$', re.M)


ACTS_KEY = 'remote_acts'
_ACTS = threading.local()                    # label -> act, gathered while a turn is written, kept when it is sent


def _offer(rows):
    """Say what a numbered word DOES, as data: the desktop button it stands for. Kept by send() beside the words."""
    got = getattr(_ACTS, 'rows', None)
    if got is None: got = _ACTS.rows = {}
    for label, act in rows or []:
        if label and act: got[str(label)] = act


def remember_offered(store, channel: str, chat: str, text: str) -> list:
    """The options this message just numbered, kept against the chat that was sent them - and, for each one
    this turn knew the button of, the act it runs."""
    words = [m.group(2) for m in _OFFERED.finditer(str(text or ''))]
    acts = getattr(_ACTS, 'rows', None) or {}
    if words:
        store.set_setting(f'{OFFERED_KEY}:{channel}:{chat}', json.dumps(words), 'assistant')
        store.set_setting(f'{ACTS_KEY}:{channel}:{chat}', json.dumps({w: acts[w] for w in words if w in acts}), 'assistant')
    _ACTS.rows = None
    return words


def forget_offered(store, channel: str, chat: str):
    for k in (OFFERED_KEY, ACTS_KEY): store.set_setting(f'{k}:{channel}:{chat}', '', 'assistant')


def acts_for(store, channel: str, chat: str) -> dict:
    try: return json.loads(store.get_settings().get(f'{ACTS_KEY}:{channel}:{chat}') or '{}') or {}
    except ValueError: return {}


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
    try: words = json.loads(store.get_settings().get(f'{OFFERED_KEY}:{channel}:{chat}') or '[]') or []
    except ValueError: words = []
    # a WhatsApp poll's vote arrives as the option's own words (cut to the poll's 100 characters): the tap is a pick
    said = str(text or '').strip()
    hit = next((w for w in words if said and (said == w or (len(said) >= 100 and w.startswith(said)))), None)
    if hit: return hit, True
    t = said.lstrip('#').rstrip('.').strip()
    if not t.isdigit(): return text, False
    i = int(t)
    return (words[i - 1], True) if 1 <= i <= len(words) else (text, False)


def _chunks(text: str, limit=3900) -> list[str]:
    """Split a long walkthrough where a reader would split it (chatformat.split).

    This used to take max() of the paragraph, line and space positions - and the space is
    always the latest of the three, so it won every time and the break landed mid-sentence:
    '...asked Fri 18 Sep 10:34 re "Northwind and' (the owner, 2026-09-19, with a screenshot)."""
    from . import chatformat
    return chatformat.split(str(text or '').strip(), limit)


def send(store, channel: str, chat: str, text: str, connector_id: int = None):
    """Everything we say to the owner leaves through here, so this is where it is SPELLED.

    WhatsApp formats client-side, so its own emphasis reaches it; Telegram renders nothing
    without a parse mode and neither sender sets one, so it gets the words bare. A producer
    writes one markup and puts chatformat.BREAK wherever a new bubble should start.

    Only the opening bubble wears the name. Four of them labelled "Taskuary (2/4):" over a
    heading that already says what it is read as machinery rather than somebody talking."""
    from . import chatformat, messengers
    out = messengers.tg_send if channel == 'telegram' else messengers.wa_send
    # every road to this chat passes here, so this is where what we offered is written down -
    # off the text AS WRITTEN, before any of it is respelled for the channel
    try: offered = remember_offered(store, channel, chat, text)
    except Exception as e:
        logger.debug(f'could not keep the offered options for {channel}: {e}'); offered = []
    msgs = []
    for part in str(text or '').split(chatformat.BREAK):
        shown = chatformat.render(part, channel)
        if shown.strip(): msgs.extend(chatformat.split(shown, chatformat.HARD))
    for i, msg in enumerate(msgs):
        # the LAST bubble carries the choices as a poll: WhatsApp's one tappable thing (the owner, 2026-09-25)
        poll = offered if channel == 'whatsapp' and i == len(msgs) - 1 and len(offered) > 1 else None
        kw = {'poll': poll} if poll else {}
        out(store, chat, ('Taskuary:\n' + msg) if i == 0 else msg, connector_id=connector_id, **kw)
    # a SENT line, not only a failed one: "never responds" left nothing to tell a reply that went from one
    # that never did (2026-09-24)
    logger.info(f'{channel}: sent {len(msgs)} message(s), {sum(len(m) for m in msgs)} chars, to the assistant chat'
                if msgs else f'{channel}: nothing to send - the answer was empty')
