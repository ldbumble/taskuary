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
import collections, json, re, threading, time

from loguru import logger


CHANNELS = ('whatsapp', 'telegram')
LABELS = {'whatsapp': 'WhatsApp', 'telegram': 'Telegram'}
HANDOFF_KEY = 'assistant_handoff'      # {'channel','chat','connector_id','at'} while the walk is on the phone

_TASK_LINK = re.compile(r'\[([^\]]+)\]\(#task=\d+\)')
_locks, _locks_guard = {}, threading.Lock()
_turns: dict = {}                            # chat -> the Event that cancels its turn in flight

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
    return 'always' if store.get_setting('phone_assistant') == '1' else 'walk'


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
    # ...and only the one the owner picked (the owner, 2026-09-28: "setting to either be whatsapp or telegram")
    pick = str(store.get_setting('phone_walk_channel') or 'both').strip().lower()
    for ch in CHANNELS:
        if pick in CHANNELS and ch != pick: continue
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
    try: h = json.loads(store.get_setting(HANDOFF_KEY) or 'null')
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
        out = concierge.resume(store, actor)                  # the item on the table first, when there still is one
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
# A PUSH WAITS FOR A GAP IN THE CONVERSATION (2026-09-29): two "By the way"s and the day's opener landed in the middle
# of a walk, between a card and the owner's answer to it - the opener's numbered list replaced the card's, so the next
# number answered the push. Nothing unprompted is sent while a turn is being answered for that chat, or within QUIET
# seconds of the last word either way; the next look tries again.
QUIET = 90.0
_talked: dict = {}                     # (store, channel, chat) -> monotonic time of the last word, either way


def _sid(store) -> int: return id(getattr(store, '_store', store))      # a poll worker's writer proxy is the same store


def talked(store, channel: str, chat: str): _talked[(_sid(store), channel, str(chat))] = time.monotonic()


def quiet(store, channel: str, chat: str) -> bool:
    """True when nothing is being said in this chat just now - a push may go."""
    with _locks_guard: busy = any(k[0] == _sid(store) and k[1] == channel and str(k[3]) == str(chat) for k in _turns)
    return not busy and time.monotonic() - _talked.get((_sid(store), channel, str(chat)), 0.0) >= QUIET


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
    if not force and not quiet(store, h['channel'], h['chat']): return 0          # mid-conversation: the next look tries again
    from . import concierge, funnel, general
    try: p = funnel.pile(store)
    except Exception as e:
        logger.warning(f'could not look for interruptions to send to {h["channel"]}: {e}'); return 0
    task, _ = general.dock_task(store, 'owner')
    on_the_table = concierge.current_key(store, task['TaskId'])
    told = list(h.get('told') or [])
    refs = {i['key']: i.get('ref') or '' for i in p.get('items') or []}
    # ONLY WHAT OUTRANKS THE TABLE (funnel.more_urgent's rule): a reply "waiting for your yes" is what the walk itself
    # leads with - pushed as a By the way it arrived seconds before the walk showed that very card (2026-09-29). A
    # meeting about to start still interrupts: the walk would not reach it in time.
    items = p.get('items') or []
    cur = next((i for i in items if i['key'] == on_the_table), None)
    band = funnel._band(cur) if cur else 99
    fresh = [a for a in (p.get('alerts') or [])
             if a.get('key') not in told and a.get('item') != on_the_table
             and (a.get('kind') == 'meeting' or a.get('order_band', 3) < band)][:3]
    if not fresh: return 0
    named = [' '.join(x for x in (funnel.mark_for(a), f"{a['text']}"
                                  f"{' (' + refs[a['item']] + ')' if refs.get(a['item']) and refs[a['item']] not in a['text'] else ''}") if x)
             for a in fresh]
    lead = 'By the way — '            # the same words the desktop strip uses, in the place he is reading
    say = lead + named[0].rstrip('.') + '.' if len(named) == 1 else lead.rstrip() + '\n' + '\n'.join('· ' + n for n in named)
    handle = next((refs[a['item']] for a in fresh if refs.get(a['item'])), '')
    tail = (f'Say {handle} to take it now, or keep going.' if handle
            else 'Name it and I will take you to it, or keep going.')
    send(store, h['channel'], h['chat'], f'{say}\n\n{tail}', h.get('connector_id'))
    concierge.record(store, task['TaskId'], 'assistant', say)
    # ...onto the hand-off as it is NOW: a Take it back that landed while this was sending must stay taken back - writing
    # the record read a moment ago put the walk back in the chat and locked the desk again
    now = handoff(store)
    if now and now.get('at') == h.get('at'):
        store.set_setting(HANDOFF_KEY, json.dumps({**now, 'told': list(now.get('told') or []) + [a['key'] for a in fresh]}), 'owner')
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
              message_id=None, poll=False, arrived=None) -> bool:
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
                           message_id, bool(poll), arrived),
                     name=f'taskuary-{channel}-assistant', daemon=True).start()
    return True


def _locked_respond(store, channel: str, chat: str, question: str, connector_id: int, message_id=None, poll=False,
                    arrived=None):
    # the thumb goes up BEFORE the lock: it says "heard you", and it must not wait behind the turn
    # already answering (which is exactly when the owner most needs to know they were heard)
    if message_id:
        from . import messengers
        try: messengers.react(store, channel, chat, message_id, connector_id=connector_id)
        except Exception as e: logger.debug(f'no receipt in {channel}: {e}')
    key = (id(store), channel, connector_id, chat)
    talked(store, channel, chat)
    with _locks_guard: lock = _locks.setdefault(key, threading.Lock())
    # A PICK DOES NOT QUEUE BEHIND THE MODEL (2026-09-25: a poll tap got its thumb and then waited a minute - the
    # typed turn before it was still waiting on the model). A tap or a typed number is a button: it stops the turn
    # in flight, whose answer would only have buried it, and runs at once.
    if poll or question.strip().isdigit():
        with _locks_guard: busy = _turns.get(key)
        if busy: busy.set()
    # the desktop hears the turn START (it shows the typing dots, as for its own turns) and END (it reads the
    # conversation at once instead of on its 30 s tick)
    from . import live
    live.emit(live.CHAT, thinking=True, channel=channel)
    try:
        heard = time.time()
        with lock:
            ev = threading.Event()
            with _locks_guard: _turns[key] = ev
            try: respond(store, channel, chat, question, connector_id, poll=poll, cancel=ev)
            finally:
                with _locks_guard:
                    if _turns.get(key) is ev: _turns.pop(key, None)
        # WHERE A SLOW TURN SPENT ITS TIME (2026-09-25: a poll tap took a minute and the log could not say why):
        # from reaching the bridge to being heard here, and from heard to answered
        lag = f'{heard - float(arrived):.1f}s to be heard, ' if arrived else ''
        logger.info(f"{channel}: {'a poll tap' if poll else 'a message'} answered - {lag}{time.time() - heard:.1f}s to answer")
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
          ('passed', 'For later'))           # the rail's For later (the canvas redesign, 2026-09-29): walked past, or put away
_AGENT_LANES = {'blocked', 'stopped', 'saved', 'queued', 'working', 'broken', 'unjudged'}
AGENT_CARD_LANES = {'blocked', 'stopped', 'queued', 'working', 'saved'}     # the lanes whose card is an agent's
ROWS_PER_GROUP = 5


def group_of(i: dict) -> str:
    # walked past with Next: the rail's Passed band (funnelPile.levelOf) - never back under "Agents waiting" (2026-09-24)
    if (i.get('surfaced') or i.get('deferred')) and i.get('order_band') == 2: return 'passed'
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
                         skip and f"{skip} you can skip", passed and f"{passed} for later") if x]
    lines = [f"{len(live)} thing{'' if len(live) == 1 else 's'}. " + ', '.join(parts)[:1].upper() + ', '.join(parts)[1:] + '.']
    for key, word_ in GROUPS:
        rows = [i for i in live if group_of(i) == key]
        if not rows: continue
        lines.append(f'\n{word_.upper()} · {len(rows)}')
        for i in rows[:ROWS_PER_GROUP]:
            state = ('draft ready' if i.get('kind') != 'action' else 'wants a yes') if i.get('lane') == 'approve' \
                else (funnel.LANE_WORDS.get(str(i.get('lane') or '')) or ('',))[0]
            # FOR LATER says when it comes back, in the rail's own short form (funnelPile.railBack)
            if key == 'passed': state = f"back in {_back_in(i.get('back_at') or i.get('defer_until'))}" if _back_in(i.get('back_at') or i.get('defer_until')) else ''
            lines.append(f"· {who_of(i)} - {_cut(i.get('title') or '', 70)}" + (f' ({state})' if state else ''))
        if len(rows) > ROWS_PER_GROUP: lines.append(f'  and {len(rows) - ROWS_PER_GROUP} more')
    return '\n'.join(lines)


def _back_in(iso) -> str:
    """'< 30m', '< 1h', '3h', '2d' until a For later row comes back - the rail's gutter, said on the phone. '' once due."""
    from datetime import datetime as _dt
    try: at = _dt.strptime(str(iso or '')[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
    except ValueError: return ''
    m = round((at - _dt.now()).total_seconds() / 60)
    return '' if m <= 0 else '< 30m' if m < 30 else '< 1h' if m < 60 else f'{m // 60}h' if m < 1440 else f'{m // 1440}d'


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
SCRIPT_LINES = [('Walk me through my tasks', {'t': 'walk'}), ('Set up Taskuary', {'t': 'script', 'script': 'set up Taskuary'}),
                ('Set up a report', {'t': 'script', 'script': 'set up a report'}),
                # the sidebar's browse buttons, as picks (doorway_browse): sections, then the list, then one
                ('Connections', {'t': 'browse', 'area': 'connections'}), ('Reports', {'t': 'browse', 'area': 'reports'}),
                ('Hub', {'t': 'browse', 'area': 'hub'}), ('Settings', {'t': 'browse', 'area': 'settings'})]


def greeting(now=None) -> str:
    from datetime import datetime as _dt
    h = (now or _dt.now()).hour
    return 'Good morning.' if h < 12 else 'Good afternoon.' if h < 18 else 'Good evening.'


def day_opener(store, items: list, now=None) -> str:
    """THE DAY IN A BREATH - the greeting, today's meetings, then who wants what. ONE text for the morning line and for
    "Walk me through my tasks" (the owner, 2026-09-29: "when you hit walk me through on whatsapp that should trigger the
    morning summary"): the walk opened with who-wants-what alone, without the meetings the morning line carried."""
    return '\n\n'.join(x for x in (greeting(now), meetings_line(store), who_wants_what(items) if items else 'The pipe is clear.') if x)


def spend_morning(store, now=None):
    """The day's opener is spent - it went out, or the owner is already talking to the chat (a walk, a question): a second
    greeting mid-conversation replaced the card's numbered list with its own (2026-09-29)."""
    from datetime import datetime as _dt
    store.set_setting(MORNING_AT, (now or _dt.now()).strftime('%Y-%m-%d'), 'assistant')


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
    # OFF UNLESS TURNED ON (the owner, 2026-10-02: "it should not be sending to whatsapp anything unless the user asks the
    # assistant a question"): the day's opener comes with "Walk me through my tasks", never on its own
    if str(st.get(MORNING_KEY, '0')).strip() not in ('1', 'true', 'on'): return 0
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
    head = day_opener(store, items, now)
    from . import doorway_browse
    # the three scripts keep the numbers the owner knows; then each section the rail holds; then the browse picks
    lines = SCRIPT_LINES[:3] + doorway_browse.section_rows(items) + SCRIPT_LINES[3:]
    text = head + '\n\nReply with one of:\n' + '\n'.join(f'{i} · {w}' for i, (w, _) in enumerate(lines, 1))
    # ...never into a conversation: a walk handed to a chat is its own opener, and a door with a turn in flight or a word in
    # the last minutes is left for the next pass (this runs after every report pass)
    if handoff(store) and not force:
        spend_morning(store, now); return 0
    doors = [d for d in doors if force or quiet(store, d['channel'], d['chat'])]
    if not doors: return 0
    sent = 0
    for d in doors:
        _offer(lines)                           # per send: remember_offered spends what was offered
        try: send(store, d['channel'], d['chat'], text, d['connectorId']); sent += 1
        except Exception as e: logger.warning(f'the morning line did not reach {d["channel"]}: {e}')
    if sent:
        store.set_setting(MORNING_AT, today, 'assistant')
        # ...and it is IN the conversation: the desk and the model never knew it had been said
        from . import concierge, general
        concierge.record(store, general.dock_task(store, 'assistant')[0]['TaskId'], 'assistant', head, phone=True)
    return sent


def walk(store, actor: str = 'owner') -> str:
    """"Walk me through my tasks", picked: the day's summary, then the first card - the desktop's Start at the top.
    A table of typed words used to run this and set-up with no model ("next", "set up", "my tasks"); the owner,
    2026-09-25: "No hard coded anything... Only if you type 1 or hit poll that's clicking a pill". Typed, the words
    go to the model like any other."""
    from . import concierge, funnel
    with concierge.delivering(concierge.PHONE):
        try: opener = day_opener(store, funnel.pile(store).get('items') or [])
        except Exception as e:
            logger.debug(f'the phone walk opened without its summary: {e}'); opener = ''
        spend_morning(store)                                  # the summary IS the day's opener - it is not said twice
        out = concierge.resume(store, actor)                  # the item on the table first, when there still is one
        return carry_out(store, out, None, actor=actor, lead=opener)


def respond(store, channel: str, chat: str, question: str, connector_id: int, poll: bool = False, cancel=None):
    """Answer synchronously; the poller runs this on a serialized background worker. `cancel` is set when a pick
    arrives behind this turn: the model's answer is dropped, never sent after the pick's."""
    from . import concierge, general
    _ASKING.chat = {'channel': channel, 'chat': chat, 'connector_id': connector_id}
    try:
        task, _ = general.dock_task(store, f'owner-{channel}')
        tid = task['TaskId']
        spend_morning(store)                  # already talking: the day's opener would land mid-conversation
        store.audit('task', tid, 'assistant_chat_question', f'owner-{channel}',
                    detail={'channel': channel, 'chat': chat, 'chars': len(question)})
        with concierge.delivering(concierge.PHONE):
            # the item on the table is the walk's own, persisted and validated here - a phone has no
            # client state to send, and the key is all say() needs to build the item afresh
            item = concierge.restore_current(store, tid)
            question, picked = resolve_index(store, channel, chat, question, poll=poll)   # "2" is the words we numbered
            # A PICK IS THE BUTTON: what the desktop's click would run, run here in code - the model reads only
            # words (the owner, 2026-09-25: the phone matches the desktop exactly). A list answers ONE reply:
            # whatever comes next, the old numbers are gone, so a stale "2" can never fire.
            acts = acts_for(store, channel, chat)
            try: offered = json.loads(store.get_setting(f'{OFFERED_KEY}:{channel}:{chat}') or '[]') or []
            except ValueError: offered = []
            act = acts.get(question) if picked else None
            # a pick that IS words (Try again): the same line goes to the model again, as if typed
            if act and act.get('t') == 'ask': question, picked, act = str(act.get('text') or question), False, None
            # ...spent by a PICK now; words spend it only when their answer goes out - a tap made while the model is
            # still thinking about typed words must find its list (PickJumpsTheQueueTests)
            if picked: forget_offered(store, channel, chat)
            _ACTS.rows = None
            pending = str(store.get_setting(f'{NOTE_KEY}:{channel}:{chat}') or '')
            if pending: store.set_setting(f'{NOTE_KEY}:{channel}:{chat}', '', 'assistant')
            if pending and not picked:
                # the line typed after "Continue session" is what to tell the agent - a text field, not a word to read
                forget_offered(store, channel, chat)
                send(store, channel, chat, _continue(store, pending, question), connector_id)
                return
            if act and act.get('t') == 'prompt':
                send(store, channel, chat, 'Go ahead - type your question.', connector_id)
                return
            if act:
                send(store, channel, chat, run_act(store, act, item), connector_id)
                return
            # ...and on an fyi batch a number names one of the lines we printed: open that one - the item on
            # the table, its own text and its own options under it - as the desktop's "Talk about it" does
            key = next((k for k, line in member_lines(item) if picked and line == question), None)
            if key:
                nxt = concierge.surface(store, key, actor='owner')
                send(store, channel, chat, turn_text(nxt, store=store, full=True), connector_id)
                return
            # MORE, picked: the rest of what the card folds, then the same choices again without it
            if picked and question == MORE:
                again = [w for w in offered if w != MORE]
                _offer([(w, acts[w]) for w in again if w in acts])
                folded = more_text(store, item) or 'Nothing more on this one.'
                opts = 'Reply with one of:\n' + '\n'.join(f'{i} · {w}' for i, w in enumerate(again, 1)) if again else ''
                send(store, channel, chat, '\n\n'.join(x for x in (folded, opts) if x), connector_id)
                return
            straight = answer_the_agent(store, item, question, picked)
            if straight:
                if not picked: forget_offered(store, channel, chat)
                send(store, channel, chat, straight, connector_id)
                return
            out = concierge.say(store, question, key=concierge.current_key(store, tid) or None, actor='owner', cancel=cancel)
            if cancel is not None and cancel.is_set(): return          # a pick came in behind it and answers instead
            if not picked: forget_offered(store, channel, chat)
            text = carry_out(store, out, item, picked=picked)
        send(store, channel, chat, text, connector_id)
    except Exception as e:
        if cancel is not None and cancel.is_set():
            logger.info(f'{channel}: a turn gave way to a pick'); return
        logger.warning(f'the {channel} assistant could not answer: {e}')
        try: send(store, channel, chat, stuck(store, f"I couldn't answer that - {plain(e)}. Say it again, or go on to the next one."), connector_id)
        except Exception as send_error: logger.warning(f'the {channel} assistant could not send its error: {send_error}')
    finally: _ASKING.chat = None


def answer_the_agent(store, item: dict | None, words: str, picked: bool, actor: str = 'owner') -> str:
    """The owner picked one of the answers THE AGENT offered, or typed one while it asks: send it, as written, to the run.

    This is the desktop's choice button, in a chat. It deliberately goes nowhere near the model: the
    words are the agent's own, the request they answer is the one on the item, and interpreting them
    is how "Signed in" became the verb `answer_agent` with no text - which concierge sends to a
    blocked agent as the literal word "yes" (measured 2026-09-15). Returns what to say back, or ''
    when this was not one of those picks and the ordinary walk should take the turn.
    """
    from . import workerstate as ws
    if not item or item.get('kind') != 'agent': return ''
    # ...and TYPED words too, while the agent on the table is asking (the owner, 2026-10-02: "if agent asks you a question
    # in whatsapp and you respond it should go directly to the agent") - the card says it goes straight in, so it does;
    # several questions are one typed line, split by workerstate.answer_open
    if picked and words not in agent_answers(item): return ''
    if not picked and not item.get('asking'): return ''
    out = ws.answer_open(store, int(item['tid']), words, actor) if item.get('tid') else {'delivered': False, 'state': 'no_request'}
    who = item.get('agent') or 'the agent'
    if out.get('delivered'): return f'Told {who}: "{words}".'
    if out.get('state') == 'no_request':
        # ...and SAVED, as the desktop saves it (server agent.answer -> waitroom_add): the phone said "it is in its
        # waiting room" and kept nothing (A12, 2026-09-25). It reaches the agent when it next stops.
        from . import waitroom
        try: waitroom.add(store, int(item['tid']), words, actor)
        except ValueError as e: return f'Could not save that for {who}: {e}'
        return f'{who} is not asking any more - your answer "{words}" is saved and reaches it when it next stops.'
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
        said.append(receipt_text(store, done, actor))
        walk_on = done.get('status') == 'done' and _settled_the_table(prop, item)
    elif prop and prop.get('auto') and prop.get('status') == 'proposed':
        done = concierge.run_proposal(store, prop, actor)
        said.append(receipt_text(store, done, actor))
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
        here = (item or {}).get('key') if verb == 'next' else None       # Next leaves the table as the desktop's does
        return _on(store, actor, said, leaving=here, exclude=here, done_with=(item or {}).get('key'))
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


def stale_tap(store, channel: str, chat: str, connector_id=None):
    """A tap on a poll that is no longer the newest: its choices went with the card it was under, so nothing runs (a stale
    pick must never fire) - but a tap that got no answer read as the assistant freezing (2026-09-29). The current choices
    are the ones under the last message; say so, once, in words."""
    try: send(store, channel, chat, 'That was an older list, so nothing ran - the choices under my last message are the current ones.',
              connector_id)
    except Exception as e: logger.warning(f'{channel}: could not answer a tap on an older list - {e}')


def recovery_rows(store, chips: list, actor: str = 'owner') -> list:
    """A failed act's way on (concierge.recover) as numbered rows: each chip the button it stands for on the desktop."""
    from . import concierge
    table = None
    for c in chips:
        v = c.get('verb')
        if v == 'next': yield c['label'], {'t': 'next'}
        elif v == 'open' and c.get('key'): yield c['label'], {'t': 'open', 'key': c['key']}
        elif v == 'retry': yield c['label'], {'t': 'retry', 'id': c['op'], 'settles': bool(c.get('settles'))}
        elif v == 'closeout': yield c['label'], {'t': 'closeout', 'rid': c['rid'], 'act': c['act']}
        elif v == 'repo': yield c['label'], {'t': 'repo', 'id': c['op'], 'repo': c['repo'], 'settles': bool(c.get('settles'))}
        elif v:
            if table is None:
                from . import general
                task, _ = general.dock_task(store, actor)          # the ONE dock the desk and the phone share
                table = (concierge.restore_current(store, task['TaskId']) or {}).get('key') or ''
            if table: yield c['label'], {'t': 'verb', 'verb': v, 'key': table}


def receipt_text(store, done: dict, actor: str = 'owner') -> str:
    """The receipt - and when the act did NOT happen, its way on, numbered (2026-09-29: a failed Close out on the phone
    said "Not done - 403 ..." and offered nothing to pick, and the list it was picked from was already spent)."""
    from . import concierge
    if done.get('status') == 'done': return concierge.receipt(store, done, actor)
    turn = concierge.receipt_turn(store, done, actor)
    if not turn['chips']: return turn['say']
    return turn_text({'say': turn['say'], 'item': None}, store=store, extra=list(recovery_rows(store, turn['chips'], actor)))


def _move_on(store, actor: str, leaving: str = None, exclude: str = None, done_with: str = None) -> tuple[dict, str]:
    """What comes after the table - (the next surface, a lead line). WHILE A SECTION IS BEING WALKED the next row of that
    section, whatever put the last one down: Next did, but an act (Make a task, Send to agent, Remind me) fell back to the
    whole walk and put TQ-0001 up in the middle of Walk Reports (2026-09-30 phone test). `done_with` is the key the act settled."""
    from . import concierge, doorway_browse, funnel
    walking = doorway_browse.held(store, asking())
    if walking:
        seen = [*walking.get('seen', []), *[k for k in (leaving, done_with) if k]]
        nxt = doorway_browse.next_in(store, walking['section'], seen)
        if nxt:
            doorway_browse.hold(store, asking(), walking['section'], [*seen, nxt['key']])
            return concierge.surface(store, nxt['key'], actor=actor, leaving=leaving), ''
        doorway_browse.hold(store, asking(), None)          # the section ran out: say so, and the walk goes on as normal
        return concierge.surface(store, actor=actor, leaving=leaving, exclude=exclude), funnel.section_done(walking['section'])
    return concierge.surface(store, actor=actor, leaving=leaving, exclude=exclude), ''


def _on(store, actor: str, said: list, extra=None, **kw) -> str:
    """The receipt lines, then what comes next (_move_on) - with the section's own end said when it ran out."""
    nxt, lead = _move_on(store, actor, **kw)
    return '\n\n'.join([x for x in said if x] + [turn_text(nxt, lead=lead, store=store, extra=extra)])


def _ran(store, prop: dict, done: dict, item: dict | None, actor: str) -> str:
    """After the run: the receipt, an Undo when it offered one, and the next item when the table was settled."""
    from . import concierge
    if done.get('status') != 'done': return receipt_text(store, done, actor)
    said = concierge.receipt(store, done, actor)
    undo = [('Undo', {'t': 'undo'})] if ' Undo: ' in said else []
    if done.get('status') == 'done' and _settled_the_table(prop, item):
        return _on(store, actor, [said], extra=undo, done_with=prop.get('key') or (item or {}).get('key'))
    if undo: return '\n\n'.join([said, turn_text({}, store=store, extra=undo)])
    return said


def _settle(store, prop: dict, item: dict | None, actor: str) -> str:
    """A proposal a pick made: run it, unless its card asks something first - then ask that, numbered."""
    from . import concierge
    if prop.get('failed'):              # refused at propose time: the reason, and what the item CAN do instead
        return turn_text({'say': prop['say'], 'item': None}, store=store, extra=list(recovery_rows(store, prop.get('chips') or [], actor)))
    if asks(prop):
        said = f"{prop['label']}: {prop['summary']}." if prop.get('label') and prop.get('summary') else prop.get('say')
        return turn_text({'say': said, 'proposal': prop}, store=store)
    return _ran(store, prop, concierge.run_proposal(store, prop, actor), item, actor)


def run_act(store, act: dict, item: dict | None, actor: str = 'owner') -> str:
    """One numbered pick, run the way the desktop's button runs it - never through the model."""
    from . import concierge, funnel, operations
    t = act.get('t')
    from . import doorway_browse
    try:
        if t == 'section':
            # a section, walked (the desktop's heading click): its first row, and Next stays in it until it is empty
            sec = act.get('section') or ''
            first = doorway_browse.next_in(store, sec, ())
            if not first: return f"Nothing in {funnel.SECTION_WORDS.get(sec, sec)} right now."
            doorway_browse.hold(store, asking(), sec, [first['key']])
            nxt = concierge.surface(store, first['key'], actor=actor)
            return carry_out(store, nxt, nxt.get('item'), actor)
        # a new walk, or one item by name, is not the section being walked
        if t in ('walk', 'open'): doorway_browse.hold(store, asking(), None)
        if t == 'browse':
            text, rows = doorway_browse.browse(store, act.get('area') or '', act.get('section'), act.get('open'), act.get('page') or 0)
            return turn_text({'say': text, 'item': None}, store=store, extra=rows)
        if t == 'next' and doorway_browse.held(store, asking()):
            here, walking = (item or {}).get('key'), doorway_browse.held(store, asking())
            seen = [*walking.get('seen', []), *([here] if here else [])]
            nxt = doorway_browse.next_in(store, walking['section'], seen)
            if nxt:
                doorway_browse.hold(store, asking(), walking['section'], [*seen, nxt['key']])
                out = concierge.surface(store, nxt['key'], actor=actor, leaving=here)
                return carry_out(store, out, out.get('item'), actor)
            doorway_browse.hold(store, asking(), None)          # the section ran out: say so, and the walk goes on as normal
            return carry_out(store, concierge.surface(store, actor=actor, leaving=here, exclude=here), None, actor,
                             lead=funnel.section_done(walking['section']))
        if t == 'next':
            # the desktop's Next: what is on the table is put down on the way out (read - Passed when it is yours) and not
            # the next pick; the phone surfaced afresh, so a failed item could be handed straight back or left unread
            here = (item or {}).get('key')
            return carry_out(store, concierge.surface(store, actor=actor, leaving=here, exclude=here), None, actor)
        if t == 'open':                 # one item by name - one the walk already showed and would not repeat yet
            nxt = concierge.surface(store, act.get('key'), actor=actor)
            return carry_out(store, nxt, nxt.get('item'), actor)
        if t == 'stay': return 'Left it - nothing moved.'
        if t == 'walk': return walk(store, actor)
        if t == 'script': return script_words(store, act.get('script') or '')
        if t == 'undo': return concierge.undo_last(store, actor)
        if t == 'remind': return _remind(store, act, actor)
        if t == 'continue': return _continue(store, act.get('tid'), act.get('note') or '')
        if t == 'retry':
            # the same confirmation again, once more - an act that failed stays `error` and may run again (claim_operation)
            op = operations.get(store, act.get('id') or '')
            if not op or op.get('status') != 'error': return 'That one is not waiting to be tried again - nothing moved.'
            # ...and a retry that lands settles the table the way the first press would have
            prop = {**op, 'settles': bool(act.get('settles')), 'key': (item or {}).get('key')}
            return _ran(store, prop, concierge.run_proposal(store, op, actor), item, actor)
        if t == 'closeout':
            from fastapi import HTTPException
            from .server import closeout_act
            try: return f"{closeout_act(int(act['rid']), str(act['act']))['said']}. Close out again once the checks pass."
            except HTTPException as e: return f'Not done - {e.detail}.'
        if t in ('confirm', 'cancel', 'repo'):
            op = operations.get(store, act.get('id') or '')
            # ...a hand-off that stopped for a repository is `error` and waits for exactly this pick (concierge.recover)
            if not op or not (op.get('status') == 'proposed' or (t == 'repo' and op.get('status') == 'error')):
                return 'That one is not waiting on you any more - nothing moved.'
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
        if verb == 'continue':
            here = asking() or {}
            if here.get('chat'): store.set_setting(f"{NOTE_KEY}:{here['channel']}:{here['chat']}", str(on.get('tid') or ''), 'assistant')
            rows = [('Continue as is', {'t': 'continue', 'tid': on.get('tid')}), ('Cancel', {'t': 'stay'})]
            return turn_text({'say': f"Continue {on.get('ref') or 'it'}? Type what to tell it as it picks up, or tap Continue as is.",
                              'item': None}, store=store, extra=rows)
        if verb == 'defer':
            # Remind me asks for the day, as the desktop's picker does; a day typed instead goes to the model's task.defer
            # ...an Advisor idea's own day, the desktop's picker on the idea (C5, 2026-09-27)
            aim = {'idea': on['idea']} if on.get('kind') == 'idea' and on.get('idea') else {'tid': on.get('tid')}
            rows = [(label, {'t': 'remind', **aim, 'until': until}) for label, until in REMIND_DAYS]
            return turn_text({'say': f"Remind you about {on.get('ref') or on.get('title') or 'this'} when? Or say a day.", 'item': None},
                             store=store, extra=rows + [('Cancel', {'t': 'stay'})])
        if verb == 'answer_agent':
            return f"What should I tell {on.get('agent') or 'it'}? Say it here and I will pass it straight to the run that is waiting."
        if verb in ('reply', 'redraft') and on.get('mid'):
            rid = _draft(store, on, verb, '')
            if not rid: return 'I could not write that draft here - it is waiting on the task page.'
            return turn_text(concierge.surface(store, f'review:{rid}', actor=actor), store=store)
        prop = concierge.propose_direct(store, verb, key, actor=actor, table=bool(item and item.get('key') == key))
        return _settle(store, prop, item, actor)
    except ValueError as e: return stuck(store, f'Not done - {e}. Nothing moved.')
    except Exception as e:
        # anything else a pick can hit (a remind, a continue, the funnel under a surface) - said plainly, with the way on,
        # never the raw exception (it went out as "I couldn't answer that: <traceback line>")
        logger.warning(f'phone pick {t or act.get("verb")} failed: {e}')
        return stuck(store, f'Not done - {plain(e)}. Nothing moved.')


NOTE_KEY = 'remote_continue_note'         # a Continue pick waiting for its note: the next typed line is it


def _continue(store, tid, note: str) -> str:
    """Continue session, from the phone: the same road as the desktop's pill (server.continue_work)."""
    from .server import ContinueBody, continue_work
    from fastapi import HTTPException
    try: continue_work(int(tid), ContinueBody(note=note or None))
    except HTTPException as e: return stuck(store, f'Could not continue it - {e.detail}.')
    ref = f'TQ-{int(tid):04d}'
    return f'Continuing {ref}' + (' with your note' if note else '') + ' - it picks up where it left off, and comes back here when it stops or asks.'


def plain(e) -> str:
    from .operations import plain as _p
    return _p(e)


def stuck(store, text: str) -> str:
    """A line that did not go as asked, with the way on numbered under it - never a bare sentence the owner has to answer
    by guessing (2026-09-29 audit: four phone error paths sent text with nothing to pick)."""
    from . import concierge
    return turn_text({'say': text, 'item': None}, store=store, extra=[(concierge.CHIP_WORDS['next'], {'t': 'next'})])


def asking_key(store) -> str:
    """The key on the table for this chat's walk - what a Remind me just put away."""
    from . import concierge, general
    try: return (concierge.restore_current(store, general.dock_task(store, 'owner')[0]['TaskId']) or {}).get('key') or ''
    except Exception: return ''


REMIND_DAYS = (('Tomorrow', 'tomorrow'), ('Next week', '1 week'), ('In 2 weeks', '2 weeks'), ('In a month', '1 month'))   # RemindMe.jsx's QUICK


def _remind(store, act: dict, actor: str) -> str:
    """The day picked: the task page's own road (remind.set_reminder), then the walk moves on - it is off the rail."""
    from . import concierge, operations, remind
    if act.get('idea'):
        from . import assistant
        out = assistant.act(store, int(act['idea']), 'snooze', actor, until=act['until'])
        return _on(store, actor, [f"Put away until {out['when']} - it comes back that morning."], done_with=(asking_key(store) or None))
    try: out = remind.set_reminder(store, int(act['tid']), act['until'], actor)
    except remind.AgentOpen as e: return str(e)
    operations.record_direct(store, 'task.defer', int(act['tid']), {'until': act['until']}, actor, out)
    if not out.get('remindAt'): return 'It is back on your rail now.'
    said = f"Away until {out['when']} - it is under Upcoming in Tasks, and back on your rail that morning."
    back = [('Bring it back now', {'t': 'remind', 'tid': act['tid'], 'until': 'none'})]
    return _on(store, actor, [said], extra=back, done_with=(asking_key(store) or None))


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
    # several questions are answered in one line of the owner's own ("1 main, 2 blue") - a poll holds one question's
    # answers, and offering the first question's as if they were the only one answered the wrong thing (2026-09-28)
    if len(it.get('questions') or []) > 1: return []
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
    rows = [(m.get('key'), ' '.join(x for x in (funnel.CHANNEL_MARKS.get(str(m.get('channel') or ''), ''),
                                                 f"{' '.join(str(m.get('who') or 'someone').split())} - {m.get('title') or ''}") if x))
            for m in item.get('items') or []]
    # the same notification twice is two lines that read alike - a line is what a number or a tap answers, so a repeat
    # wears its count or the second one could never be opened (and a WhatsApp poll dropped it: 2026-09-29, 3 of 4)
    seen = collections.Counter()
    def _nth(line): seen[line] += 1; return line if seen[line] == 1 else f'{line} ({seen[line]})'
    return [(k, _nth(line)) for k, line in rows]


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


# the line Taskuary writes over a GitHub/Asana/monday item for TRIAGE (who wrote it, their standing) - evidence for the
# judge, never what they said; ui.jsx PROVENANCE is the same rule for the desktop
PROVENANCE = re.compile(r'^\s*\[(?:pull request|issue) by [^\]\n]*\]\s*|^\s*\[(?:Asana task|Monday item)[^\]\n]*\]\s*', re.I)


def _plain(text) -> str:
    """Markdown as WORDS. Neither sender sets parse_mode - Telegram's sendMessage and the WhatsApp
    bridge both post plain text - so every ** and ` and [](...) arrived as its own punctuation once
    the body stopped being truncated. The desktop renders them; here they are simply removed.

    Code spans come out first and go back last, so `snake_case_name` is not read as an italic."""
    kept = []
    def _hold(m):
        kept.append(m.group(1))
        return f'\x00{len(kept) - 1}\x00'
    out = _CODE.sub(_hold, PROVENANCE.sub('', str(text or ''), count=1))
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
    # a close-out card's words are the reply riding with it - the yes posts THAT (verdicts reply_text)
    if rv.get('Kind') == 'action' and item.get('closeout') and rv.get('TaskId'):
        rv = store._one("SELECT * FROM review WHERE TaskId=? AND Status='pending' AND Kind IN ('draft','draft_reply') "
                        "ORDER BY ReviewId DESC LIMIT 1", (rv['TaskId'],)) or {}
    # 'draft_reply' is the one an agent writes when it finishes - only 'draft' was read, so the reply a finished
    # agent's card asked you to approve never appeared on the phone (2026-09-28)
    return str(rv.get('DraftText') or '').strip() if rv.get('Kind') in ('draft', 'draft_reply') else ''


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


FULL = 6000                                    # an opened message in full - past this it is a document, not a message
EARLIER = 4                                    # a chat line reads with the few said before it


def full_body(store, item: dict | None) -> str:
    """The message itself, whole - what "read that message in full" promises (the owner, 2026-09-29: "for email, the
    full email, chat full chat and last few, if github issue/comment on pr let me see it not just a few words"). A chat
    line brings the few lines before it: one line of a conversation is rarely the whole of what was said."""
    from .ingest import CHAT_CHANNELS
    msg, body, is_report = _body(store, item)
    if not body or is_report: return ''
    parts = [thread_line(store, msg)]
    if str(msg.get('Channel') or '').lower() in CHAT_CHANNELS:
        try: kin = store.thread_messages(msg.get('ConversationId'), msg.get('Subject'))
        except Exception as e:
            logger.debug(f'the phone could not read the chat around it: {e}'); kin = []
        before = [m for m in kin if m.get('MessageId') != msg.get('MessageId') and str(m.get('Status') or '') != 'context'
                  and str(m.get('SentAt') or '') <= str(msg.get('SentAt') or '')][-EARLIER:]
        if before: parts.append('EARLIER\n' + '\n'.join(
            f"{' '.join(str(m.get('FromName') or m.get('FromEmail') or 'someone').split())}: {_cut(_plain(m.get('BodyText')), 300)}" for m in before))
    text = re.sub(r'\n{3,}', '\n\n', _plain(body)).strip()
    if len(text) > FULL: text = text[:FULL].rstrip() + '\n…(the rest is on the task page)'
    parts.append('THEY WROTE\n' + _quote(text))
    return '\n\n'.join(x for x in parts if x)


def more_text(store, item: dict | None) -> str:
    """What the card folds - the phone's More. Under a draft, what they wrote; under a report, every
    section after the first; under a long message, the whole of it. '' when nothing is folded."""
    if not item: return ''
    if item.get('kind') == 'agentdone' and item.get('tid'):
        # what the agent FOUND, in full - the card's line is its summary, and it asks "want to see the final report?"
        rep = next((c['Body'] for c in reversed(store.list_comments(int(item['tid'])) or [])
                    if str(c.get('Body') or '').startswith(('CODER REPORT', 'The agent closed this itself'))), '')
        return rep.split('\n', 1)[-1].strip() if rep.startswith('CODER REPORT') else rep
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


# the words that answer "who should take it?" - the move of a task nobody is on (move_title)
_HAND = ('regular_agent', 'coder')


def primary(out: dict) -> dict | None:
    """The card's verb: the first word that DOES the thing - a reply with no draft yet leads with
    drafting it, not with closing the task (the vocabulary lists close first for a waiting draft).
    ...and the move's own verb where the card names one: "who should take it?" is answered by handing it over,
    never by a reply (the desktop's button there is Hand to agent, 2026-09-28)."""
    chips = [c for c in (out.get('chips') or []) if isinstance(c, dict) and c.get('verb') and c.get('verb') != 'next']
    it = out.get('item') or {}
    if it.get('kind') in STORY_KINDS and move_title(it) in ('who should take it?', 'start it'):
        hand = next((c for c in chips if c['verb'] in _HAND), None)
        if hand: return hand
    return next((c for c in chips if c['verb'] not in _DOWN), chips[0] if chips else None)


def then_line(out: dict, store=None) -> str:
    """"Send the reply: sends the draft above, in your name." - only on a card that shows what it is about."""
    c = primary(out)
    if store is None or not c or agent_answers(out.get('item')) or out.get('proposal'): return ''
    it = out.get('item') or {}
    said = ((it['closeout'] + (', then posts the reply above as its comment.' if it.get('rides') else '.'))
            if c['verb'] == 'approve' and it.get('closeout')
            else THEN_KIND.get((c['verb'], it.get('kind'))) or THEN.get(c['verb']))
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


# THE CARD'S STORY, ON THE PHONE (the owner, 2026-09-28: the desktop's "the story is quiet, your move is loud", and "same
# for whatsapp"): who asked and what the agent did as plain lines, then one bold YOUR MOVE with the thing to decide under
# it. WhatsApp has no frame and no colour - a rule and the one bold header are the only loud things it allows. The words
# match assistantCards.jsx Story / YourMove, so the two surfaces say the same card.
STORY_KINDS = {'review', 'action', 'agent', 'agentdone', 'todo', 'message', 'asked', 'fyi', 'wrapup', 'task'}
_CHANNEL_WORDS = {'email': 'Email', 'github': 'GitHub', 'whatsapp': 'WhatsApp', 'teams': 'Teams', 'slack': 'Slack', 'telegram': 'Telegram',
                  'sms': 'Text', 'discord': 'Discord', 'google_chat': 'Google Chat', 'assistant': 'Advisor', 'gitlab': 'GitLab'}
_VIA = {'whatsapp': 'on WhatsApp', 'teams': 'in Teams', 'slack': 'in Slack', 'telegram': 'on Telegram', 'sms': 'by text',
        'github': 'on GitHub', 'discord': 'on Discord', 'google_chat': 'in Google Chat'}
_PLAIN_PROFILE = {'coder', 'coding', 'claude', 'codex', 'agent', 'assistant', 'general', 'regular', 'the agent', ''}
RULE = '──────────'
# THE TASK PAGE'S THREE COLOURS, as a chat can wear them (the owner, 2026-09-28: "make sure whatsapp/telegram matches
# this new color scheme"): 1 the task in slate, 2 the agent in sage, 3 you in tan - the card's avatars, as dots
DOT_TASK, DOT_AGENT, DOT_YOU = '🔵', '🟢', '🟤'


def _advisor(store, item: dict | None) -> bool:
    """A task made from an Advisor idea: the Advisor asked, never the owner."""
    it = item or {}
    if str(it.get('channel') or '') == 'assistant': return True
    if store is None or not it.get('tid'): return False
    try: t = store.get_task(int(it['tid'])) or {}
    except Exception: return False
    return str(t.get('Source') or '') == 'assistant' or str(t.get('SourceRef') or '').startswith('assistant:')


def channel_word(ch) -> str:
    k = str(ch or '').lower()
    return _CHANNEL_WORDS.get(k) or k.replace('_', ' ').title()


def is_own(item: dict | None) -> bool:
    """Work the owner started: its "sender" is the owner ("owner" from CreatedBy, "You" from ownwork)."""
    it = item or {}
    return str(it.get('channel') or '') == 'own' or str(it.get('who') or '').strip().lower() in ('owner', 'you', 'me')


def agent_label(item: dict | None, name: str = None) -> str:
    """What an agent IS - never the profile's bare name ("coder"); the profile only when it says more."""
    it = item or {}
    p = str(name or it.get('working') or it.get('agent') or '').strip()
    kind = 'General agent' if str(it.get('mode') or '') in ('chat', 'assistant') or p.lower() == 'assistant' else 'Coding agent'
    return f'{kind} · {p}' if p.lower() not in _PLAIN_PROFILE else kind


def agent_report(store, tid) -> dict:
    """The report an agent files (coder.py): Summary = what it found, Actions = what it did, Determination = its verdict."""
    if store is None or not tid: return {}
    try: rep = next((str(c.get('Body') or '') for c in reversed(store.list_comments(int(tid)) or [])
                     if str(c.get('Body') or '').startswith(('CODER REPORT', 'HANDOVER NOTE'))), '')
    except Exception as e:
        logger.debug(f'the phone could not read the agent report: {e}')
        return {}
    body = re.split(r'\n\s*LAST MESSAGE\s*\n', rep)[0]
    field = lambda k: ((re.search(rf'(?im)^\s*{k}:\s*(.+)$', body) or [None, ''])[1] or '').strip()
    return {'summary': field('Summary'), 'actions': field('Actions'), 'verdict': field('Determination')} if rep else {}


def agent_state(item: dict | None) -> str:
    it = item or {}
    kind, lane = it.get('kind'), it.get('lane')
    if kind == 'agent':
        return ('working' if lane == 'working' else 'stopped - its session is saved' if it.get('paused')
                else 'asks you' if it.get('asking') else 'is waiting on you')
    if kind == 'agentdone': return 'finished'
    return {'queued': 'handed over, not started', 'stopped': 'stopped', 'saved': 'session saved'}.get(lane) or ('finished' if it.get('summary') else '')


def move_title(item: dict | None, draft: str = '') -> str:
    """What the move decides, in the desktop's words - '' where nothing waits on the owner."""
    it = item or {}
    kind, lane, who = it.get('kind'), it.get('lane'), story_who(it)
    if kind == 'agent':
        if len(it.get('questions') or []) > 1: return f"{len(it['questions'])} questions from the agent"
        return '' if lane == 'working' else 'pick it up again' if it.get('paused') else 'answer the agent' if it.get('asking') else "tell the agent what's next"
    if kind == 'agentdone': return 'answer them from what it found' if it.get('mid') else ''
    if kind == 'wrapup': return 'close it'
    if lane == 'queued': return 'start it'
    if lane in ('stopped', 'saved'): return 'pick it up again'
    if kind == 'action': return 'close out' if it.get('closeout') else 'do what you asked for' if is_own(it) else 'run what the agent proposed'
    if kind == 'review':
        return ('send your draft' if is_own(it) else f'reply to {who}') if draft or it.get('draft') else 'no reply drafted yet'
    if kind == 'fyi' or lane == 'fyi': return ''
    if kind == 'todo' or is_own(it): return 'who should take it?'
    return f'reply to {who}' if it.get('mid') else ''


def story_who(item: dict | None) -> str:
    it = item or {}
    if is_own(it): return 'You'
    from .triage import person_name        # "Doyle, Alex at Northwind" reads "Alex Doyle", as on the card
    raw = re.sub(r'\s*<[^>]*>', '', ' '.join(str(it.get('who') or '').split()))
    return person_name(raw) or raw or 'them'


def subject_of(store, item: dict | None) -> str:
    """The source's own subject: "owner/repo#113 fix: ..." as "#113 · fix: ...", an email's without its Re:/Fwd:."""
    if store is None or not (item or {}).get('tid'): return ''
    try: msg = next((m for m in store.list_messages(int(item['tid'])) or [] if m.get('Status') != 'context'), None)
    except Exception: return ''
    s = ' '.join(str((msg or {}).get('Subject') or '').split())
    m = re.match(r'^[\w.-]+/[\w.-]+#(\d+)\s+(.*)$', s)
    body = str((msg or {}).get('BodyText') or '').lstrip().lower()
    kind = 'PR ' if body.startswith('[pull request') else 'Issue ' if body.startswith('[issue') else ''
    return f'{kind}#{m.group(1)} · {m.group(2)}' if m else re.sub(r'^((re|fw|fwd):\s*)+', '', s, flags=re.I)


def summary_rest(store, item: dict | None) -> str:
    """The task summary after its first sentence - what it changes, what it needs."""
    if store is None or not (item or {}).get('tid'): return ''
    try: summary = str((store.get_task(int(item['tid'])) or {}).get('Summary') or '').strip()
    except Exception: return ''
    return ' '.join(re.split(r'(?<=[.!?])\s+', summary)[1:]).strip()


def _repeats(line: str, shown: list) -> bool:
    """A line that only says again what is already on the card: its opening is in a shown line, or a shown line's opening is
    in it. A task written from one pasted paragraph has that paragraph as its title, its message's subject AND its summary,
    and the card printed it three times (the owner, 2026-09-30, TQ-0887) - the desktop row keeps one (fyiRow.gistFor)."""
    norm = lambda s: ' '.join(str(s or '').split()).lower().rstrip('…').strip()
    a = norm(line)
    if not a: return True
    for s in shown:
        b = norm(s)
        if b and (a[:48] in b or b[:48] in a): return True
    return False


def story_block(store, item: dict | None, draft: str = '', say: str = '', full: bool = False) -> str:
    """The quiet part: a header (state · ref), who asked and what they want, then the agent and its evidence.
    `full`: the owner opened this one to READ it - the whole message, not its opening (full_body)."""
    from . import concierge, funnel
    it = item or {}
    kind, ch = it.get('kind'), str(it.get('channel') or '')
    word = ({'agentdone': 'agent finished', 'wrapup': 'reply sent · task still open'}.get(kind)
            or ('your task' if is_own(it) and kind not in ('agent', 'review', 'action') else '')
            or (funnel.LANE_WORDS.get(str(it.get('lane') or '')) or ('',))[0])
    head = ' · '.join(x for x in (word, str(it.get('ref') or '')) if x)
    if head and funnel.mark_for(it): head = f'{funnel.mark_for(it)} {head}'
    age = concierge.funnel_age(it)
    said = lead_line(store, it, '') or _cut(it.get('title') or '', 160)
    lines = [head] if head else []
    # the asker - the TASK where the card's `who` is not the asker (an agent-finished card carries the agent there)
    agent_is_who = kind == 'agent' and str(it.get('who') or '').strip().lower() in {str(it.get(k) or '').strip().lower() for k in ('agent', 'working')} - {''}
    if _advisor(store, it):
        lines.append(' · '.join(x for x in (f'{DOT_TASK} **Advisor** raised', 'an idea', age) if x))
    elif kind in ('agentdone', 'wrapup') or agent_is_who:
        lines.append(' · '.join(x for x in (f'{DOT_TASK} **The task**', channel_word(ch) if ch and ch not in ('own', 'report') else '', age) if x))
    elif is_own(it):
        lines.append(' · '.join(x for x in (f'{DOT_TASK} **You**', 'your task', age) if x))
    else:
        verb = 'wrote' if kind == 'fyi' or it.get('lane') in ('fyi', 'report') else 'asked'
        lines.append(' · '.join(x for x in (f'{DOT_TASK} **{story_who(it)}** {verb}', channel_word(ch), age) if x))
    if said: lines.append(said[:1].upper() + said[1:])
    # what the thing IS, in its own words - a pull request's title and number, an email's subject - and the rest of the
    # summary: the first sentence says who wants what, never what it is (the owner, 2026-09-28: "at least the title")
    subj = subject_of(store, it)
    if subj and re.sub(r'^(PR |Issue )?#\d+( ·)?\s*', '', subj).lower() not in (said or '').lower() and not _repeats(subj, [said]):
        lines.append(_cut(subj, 280))
    rest = summary_rest(store, it)
    if rest and not _repeats(rest, [said, subj]): lines.append(_cut(rest, 280))
    if not it.get('tid') and say and kind != 'agentdone' and (not said or said.lower() not in say.lower()): lines.append(say)
    # their own words, when nothing of yours answers them yet (a draft puts them behind More)
    whole = full_body(store, it) if full else ''
    if whole: lines += ['', whole]
    elif not draft and kind in ('message', 'asked', 'todo', 'fyi') and not is_own(it):
        msg, body, is_report = _body(store, it)
        if body and not is_report:
            opening = _plain(body)
            lines.append(_quote(_cut(opening, EXCERPT) if len(opening) > EXCERPT else opening))
    # the agent: its state and what it found, did and concluded - the evidence the move is decided on
    rep = agent_report(store, it.get('tid'))
    found = rep.get('summary') or ' '.join(str(it.get('summary') or '').split())
    # ...a finished agent with no summary on the card: the assistant's own line says what it found
    if not found and kind == 'agentdone' and say: found = say
    state = agent_state(it)
    if found or state:
        lines.append('')
        lines.append(f"{DOT_AGENT} **{agent_label(it, it.get('who') if kind == 'agentdone' else None)}**" + (f' · {state}' if state else ''))
        if found: lines.append(_cut(found, 400))
        if rep.get('actions'): lines.append(f"did: {_cut(rep['actions'], 300)}")
        if rep.get('verdict'): lines.append(f"verdict: {_cut(rep['verdict'], 300)}")
    elif it.get('tid') and kind in ('todo', 'message', 'asked') and (kind == 'todo' or is_own(it)):
        lines += ['', f'{DOT_AGENT} No agent yet - nobody is working on this.']
    return '\n'.join(lines).strip()


def move_block(store, item: dict | None, draft: str = '') -> str:
    """The loud part: a rule, **YOUR MOVE · <what>**, and what to decide on - your reply, its question, why it waits."""
    it = item or {}
    title = move_title(it, draft)
    if not title: return ''
    body = []
    qs = it.get('questions') or []
    if it.get('kind') == 'agent' and len(qs) > 1:
        # EVERY question, numbered - the numbers the owner answers with (workerstate.split_answers)
        for i, q in enumerate(qs, 1):
            opts = ' / '.join(str(c) for c in q.get('choices') or [])
            body.append(f"**{i}. {_cut(q.get('text') or '', 300)}**" + (f' ({opts})' if opts else ''))
        body.append(f"Answer all {len(qs)} in one line - \"1 {((qs[0].get('choices') or ['yes'])[0])}, 2 ...\" - or in your own words. They go back to the agent together.")
    elif it.get('kind') == 'agent' and not it.get('paused') and it.get('lane') != 'working':
        asked = ' '.join(str((it.get('tail') or [''])[0]).split()) if it.get('asking') else ''
        if asked: body.append(f'**{_cut(asked, 600)}**')
        # "goes straight in" only where it does: an agent ASKING takes typed words as its answer (answer_the_agent)
        body.append(('Pick an answer below, or type your own - it goes straight in.' if it.get('choices')
                     else 'Type your answer - it goes straight in.') if it.get('asking')
                    else 'Pick below, or tell me what to do with it.')
    elif draft:
        via = _VIA.get(str(it.get('channel') or '').lower(), 'by email')
        body.append('Your draft - it goes when you pick Close out:' if is_own(it) else f'Your reply to {story_who(it)} {via} - it goes when you pick Close out:')
        body.append(_quote(draft))
    elif it.get('lane') == 'queued' and (it.get('why_idle') or it.get('why')):
        body.append(f"Why it has not started: {' '.join(str(it.get('why_idle') or it['why']).split())}")
    elif it.get('kind') == 'wrapup' and it.get('sent'):
        body.append(f"You sent: {_cut(it['sent'], 300)}")
    # "👉 You · start it" - the thread's last step, in the words every step uses; the rule is the one loud thing
    return '\n'.join([RULE, f'{DOT_YOU} **You** · {title}'] + body)


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


def turn_text(out: dict, lead: str = '', store=None, extra: list = None, full: bool = False) -> str:
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
    if item.get('kind') in ('agent', 'agentdone') or item.get('lane') in AGENT_CARD_LANES:
        # AN AGENT'S CARD is the task, then the agent's mark and what it did or needs (the owner, 2026-09-25: "show the
        # task and then emoji for agent and what it did"). It stacked a source line, the say line, the lane's
        # sentence and the task summary - four lines for one fact, two of them the same sentence.
        task = ' · '.join(x for x in (str(item.get('ref') or ''), _cut(item.get('title') or '', 90)) if x)
        # ...and WHY, where the why is the news: not started, stopped, or the session you saved (a waiting agent's
        # sentence already says what it needs)
        why = state if item.get('lane') in ('queued', 'stopped', 'saved') else ''
        head = '\n'.join(x for x in (task, say, why) if x)
    story = bool(item) and item.get('kind') in STORY_KINDS
    draft = _draft_text(store, item) if story and store is not None else ''
    if story: head = story_block(store, item, draft, _TASK_LINK.sub(r'\1', str(out.get('say') or '')).strip(), full=full)
    if item.get('kind') == 'fyis':
        # THE ITEMS, one per line, and nothing else: the say line restated them as one run-on sentence and
        # the status line added "fyi - people told you things" under it, and on a phone that read as
        # nothing at all (the owner, 2026-09-18: "don't need random summary, just show the items")
        # ...each NUMBERED, so a number opens that one (respond): the desktop's "Talk about it" door
        members = member_lines(item)
        head = '\n'.join([f"{mark} {len(members)} fyi · nothing to do"] + [f'{i} · {line}' for i, (_k, line) in enumerate(members, 1)])
    if item and len(item.get('questions') or []) > 1:
        from . import concierge
        out = {**out, 'chips': [c for c in out.get('chips') or [] if not (isinstance(c, dict) and c.get('verb') == 'answer_agent')],
               'options': [o for o in out.get('options') or [] if str(o) != concierge.CHIP_WORDS['answer_agent']]}
    if item and is_own(item) and item.get('kind') in STORY_KINDS:
        # work you started has nobody behind it to answer or to file away (the desktop hides the same two)
        from . import concierge
        gone = {concierge.CHIP_WORDS['reply'], concierge.CHIP_WORDS['not_ours']}
        out = {**out, 'chips': [c for c in out.get('chips') or [] if not (isinstance(c, dict) and c.get('verb') in ('reply', 'not_ours'))],
               'options': [o for o in out.get('options') or [] if str(o) not in gone]}
    words, first = choices(out), len(member_lines(item)) + 1
    prop = out.get('proposal') if (out.get('proposal') or {}).get('status', 'proposed') == 'proposed' else None
    if prop and prop.get('id') and not prop.get('auto'):
        # THE CARD'S QUESTION, numbered: how far a Not ours goes, which agent, which checkout - each answer runs
        q, rows = proposal_choices(prop)
        if q: head = '\n'.join(x for x in (head, q) if x)
        words = [label for label, _ in rows]
        _offer(rows)
    else:
        # ...and a chip that is WORDS (Try again after the AI failed: the owner's own line, sent again) is a pick too - it was
        # dropped for having no verb, and the phone offered nothing where the desktop offered Try again (2026-09-30)
        _offer([(c['label'], {'t': 'ask', 'text': c['ask']} if c.get('ask') and not c.get('verb')
                 else {'t': 'next'} if c.get('verb') == 'next' else {'t': 'open', 'key': c['key']} if c.get('verb') == 'open'
                 else {'t': 'verb', 'verb': c['verb'], 'key': item.get('key')})
                for c in out.get('chips') or [] if isinstance(c, dict) and c.get('label')
                and ((c.get('ask') and not c.get('verb')) or (c.get('verb') and (item.get('key') or c.get('verb') in ('next', 'open'))))])
    # THE CARD'S ORDER: the verb, then Next, then More, then the rest - the desktop's two buttons and its
    # Also line, as one numbered list (2026-09-23). A proposal's yes/no and an agent's own answers keep
    # theirs: those are the answer itself, not a choice of what to do.
    if not out.get('proposal') and not agent_answers(item):
        nxt = [w for w in words if str(w).strip().lower() == 'next']
        rest = [w for w in words if w not in nxt]
        lead_word = (primary(out) or {}).get('label')
        first_ = [w for w in rest if w == lead_word][:1] or rest[:1]
        more = [MORE] if store is not None and not (full and story) and more_text(store, item) else []
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
    shown = move_block(store, item, draft) if story else decision_block(store, item) if store is not None else ''
    return '\n\n'.join(x for x in (lead.strip(), head, shown, then_line(out, store), opts) if x)


OFFERED_KEY = 'remote_offered'
_CHOICES_BLOCK = re.compile(r'\n*Reply with (?:one of|a number[^\n]*?):\n(?:\d+ · [^\n]*(?:\n|$))+')
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
    try: return json.loads(store.get_setting(f'{ACTS_KEY}:{channel}:{chat}') or '{}') or {}
    except ValueError: return {}


ASK_SOMETHING = 'Ask the assistant something'
POLL_LABEL = 100                               # WhatsApp's option length, in UTF-16 units (whatsapp/poll.mjs)


def _poll_cut(w: str) -> str:
    return str(w or '').strip().encode('utf-16-le')[:POLL_LABEL * 2].decode('utf-16-le', 'ignore').strip()


def poll_labels(words: list) -> list:
    """The options as the poll carries them: cut where the bridge cuts (JavaScript counts an emoji as TWO, so a long
    line with its channel mark came back one short and never matched - 2026-09-29), and distinct, since a poll drops
    a repeat - two lines alike in their first 100 wear their number."""
    cut = [_poll_cut(w) for w in words]
    return [_poll_cut(f'{i} · {w}') if cut.count(c) > 1 else c for i, (w, c) in enumerate(zip(words, cut), 1)]


def resolve_index(store, channel: str, chat: str, text: str, poll: bool = False) -> tuple[str, bool]:
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
    try: words = json.loads(store.get_setting(f'{OFFERED_KEY}:{channel}:{chat}') or '[]') or []
    except ValueError: words = []
    # a WhatsApp poll's vote arrives as the option's own words (cut to the poll's 100 characters): the TAP is a pick.
    # Only a vote the bridge marked as one - the same words TYPED are words, and go to the model (the owner,
    # 2026-09-25: "Only if you type 1 or hit poll that's clicking a pill")
    said = str(text or '').strip()
    labels = poll_labels(words) if poll and said else []
    if said in labels: return words[labels.index(said)], True
    if poll and said in words: return said, True
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
    talked(store, channel, chat)
    # every road to this chat passes here, so this is where what we offered is written down -
    # off the text AS WRITTEN, before any of it is respelled for the channel
    try: offered = remember_offered(store, channel, chat, text)
    except Exception as e:
        logger.debug(f'could not keep the offered options for {channel}: {e}'); offered = []
    # ONE CHOICE IS STILL A POLL (the owner, 2026-09-25: "even if only next we should have poll to go next no?") - a card
    # that offered only Next printed "Reply with one of: 1 · Next" and nothing to tap
    if channel in ('whatsapp', 'telegram') and offered:
        # the POLL is the choices (the owner, 2026-09-25: "don't need this choices if you have pick"). A number typed
        # still answers - the list is remembered above - it is only not printed twice. Numbered lines that are the
        # CONTENT (an fyi batch's members, above the lead-in) stay.
        text = _CHOICES_BLOCK.sub('', str(text or '')).rstrip()
    # ...and WhatsApp will not send a poll of ONE (the bridge needs two), so a lone choice - Next on a closed task, one
    # "Open TQ-…", one Undo - showed nothing to tap. The second option is the other thing the owner can always do
    # (the owner, 2026-10-02: "just ask assistant question option")
    if channel == 'whatsapp' and len(offered) == 1:
        offered = offered + [ASK_SOMETHING]
        store.set_setting(f'{OFFERED_KEY}:{channel}:{chat}', json.dumps(offered), 'assistant')
        store.set_setting(f'{ACTS_KEY}:{channel}:{chat}', json.dumps({**acts_for(store, channel, chat), ASK_SOMETHING: {'t': 'prompt'}}), 'assistant')
    msgs = []
    for part in str(text or '').split(chatformat.BREAK):
        shown = chatformat.render(part, channel)
        if shown.strip(): msgs.extend(chatformat.split(shown, chatformat.HARD))
    for i, msg in enumerate(msgs):
        # the LAST bubble carries the choices as a poll: WhatsApp's one tappable thing (the owner, 2026-09-25)
        last = i == len(msgs) - 1 and offered
        # ...and on Telegram, its own buttons under the same last bubble (messengers.tg_send)
        kw = {'poll': poll_labels(offered)} if last and channel == 'whatsapp' else {'buttons': offered} if last and channel == 'telegram' else {}
        out(store, chat, ('Taskuary:\n' + msg) if i == 0 else msg, connector_id=connector_id, **kw)
    # a SENT line, not only a failed one: "never responds" left nothing to tell a reply that went from one
    # that never did (2026-09-24)
    logger.info(f'{channel}: sent {len(msgs)} message(s), {sum(len(m) for m in msgs)} chars, to the assistant chat'
                if msgs else f'{channel}: nothing to send - the answer was empty')
