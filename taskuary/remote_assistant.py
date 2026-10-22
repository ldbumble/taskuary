"""The owner's private doorway into the assistant from a phone chat - WhatsApp or Telegram.

This is deliberately not another bot and not another conversation. A message the owner types in the
one chat they named runs the SAME walk the Assistant tab runs, on the same dock task (general.dock_task),
through the same concierge: the pipe it takes items from, the verbs it decides with and the proposals it
waits on are the desk's. What the desktop draws as a card with action words under it, the phone carries
as words in the message - the choices are appended here, from the item, never invented by the model.

A HANDOFF is the explicit version, and the reason the button exists: the tab hands its walk to the chat
and LOCKS itself, because two screens answering the same item is how the same mail gets replied to twice.
Walk it here on the desktop and the chat is told the walk is over.

Only messages the owner themself sent in that named, private chat are accepted. Other people, other
chats and groups continue through the normal funnel.
"""
import collections, json, re, threading, time

from loguru import logger
from . import kinds as task_kinds
from .timewords import plural
from . import buttons, lanes
# the row's words (who, state, your move) and when a For later row comes back are worked out ONCE, in funnel_presentation
from .funnel_presentation import back_in as _back_in, is_own, move_of as move_title, shows, story_who


CHANNELS = ('whatsapp', 'telegram')
LABELS = {'whatsapp': 'WhatsApp', 'telegram': 'Telegram'}
HANDOFF_KEY = 'assistant_handoff'      # {'channel','chat','connector_id','at'} while the walk is on the phone

_TASK_LINK = re.compile(r'\[([^\]]+)\]\(#task=\d+\)')
_TASK_ID = re.compile(r'\]\(#task=(\d+)\)')
_locks, _locks_guard = {}, threading.Lock()
_turns: dict = {}                            # chat -> the Event that cancels its turn in flight

# the desk's button that brings the walk back is Walk it here (buttons.json walk_here) - "Take it back" named a button that is gone (verify, 2026-10-19)
# ...and the phone HAS its choices now (the poll, the bot's buttons): "when you want the buttons again" said it had none (F21)
OPENED = ('Walking you through it here. Reply in this chat and I keep going; '
          f"press {buttons.label('walk_here')} on the desktop to take the walk back.")
CLOSED = 'Walked back to the desktop - this walk is over here. Message me any time and I will pick it up again.'
HAND_BACK = 'Hand back to the desktop'
MORE_CHOICES, POLL_MAX = 'More choices', 12      # WhatsApp's poll and Telegram's buttons both stop at twelve
HANDED_BACK = 'Handed back - the walk is on the desktop again. Message me any time and I will pick it up again.'


def farewell(store, channel: str, note: str) -> str:
    """The hand-back's last line, with the way to pick the walk up again under it. "Message me any time" is true now in a chat that
    listens only during a walk too: a hand-back keeps that chat listening (A5, 2026-10-22 - it said so, then ignored the next message)."""
    return turn_text({'say': note, 'item': None}, store=store, extra=[(WALK, {'t': 'walk', 'opened': True})])


HANDED_KEY = 'assistant_handed_back'    # {'channel', 'chat', 'at', 'told'}: the chat a walk was handed back FROM - it keeps listening (A5)


def handed_back(store, channel: str = None, chat: str = None) -> dict | None:
    """The chat the last walk was handed back from, while its card still names it - a message there picks the walk up again."""
    try: h = json.loads(store.get_setting(HANDED_KEY) or 'null')
    except ValueError: h = None
    if not isinstance(h, dict) or h.get('channel') not in CHANNELS: return None
    if channel and (h['channel'] != channel or (chat is not None and str(h.get('chat')) != str(chat).strip())): return None
    return h if connector_for_chat(store, h['channel'], h.get('chat')) else None


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


PICKED = 'Connected - this is your Assistant chat now.'
GREET_EVERY = 6 * 3600                  # one fixed line per unchosen chat in this long, so a stranger cannot make the bot talk


def hello_chat(store, channel: str, chat: str) -> bool:
    """The chat the desktop just picked is told so, with the way in (A4, 2026-10-22): picking it sent nothing, and the owner's first message
    to a bot is often before that. Where the chat listens only during a walk, it says how a walk gets here instead of offering one."""
    c = doorway(store, channel)
    if not chat or not c or chat_of(c) != str(chat): return False
    if enabled(store, channel, chat, c):
        text = turn_text({'say': f'{PICKED} Tap below to walk through what is waiting, or type what you want.', 'item': None}, store=store,
                         extra=[(WALK, {'t': 'walk', 'opened': True}), (MENU, {'t': 'menu'})])
    else: text = f'{PICKED} To walk here, press "Walk me through them in {LABELS.get(channel, channel)}" on the desktop.'
    send(store, channel, str(chat), text, c['ConnectorId'])
    return True


def greet_unchosen(store, connector, chat: str) -> bool:
    """/start, "hello" - any first words - from a private Telegram chat the doorway does not answer get ONE fixed line, at most every
    GREET_EVERY (A4, 2026-10-22): first contact was total silence. A bot is public, so the line says nothing about the owner - only where
    a chat is chosen. The owner's own chosen chat, quiet between walks, is told how a walk gets there."""
    from . import messengers, words
    key = f'tg_greeted:{chat}'
    try: last = float(store.get_setting(key) or 0)
    except ValueError: last = 0.0
    if time.time() - last < GREET_EVERY: return False
    store.set_setting(key, str(time.time()), 'telegram-poll')
    mine = chat_of(connector) == str(chat)
    text = (f'This is your Assistant chat. To walk here, press "Walk me through them in Telegram" on the desktop, or let it listen any time '
            f'under {words.name("settings")} → Assistant on your phone.' if mine else
            f'To talk to Taskuary here, choose this chat on the desktop: {words.name("settings")} → Assistant on your phone.')
    try: messengers.tg_send(store, str(chat), text, connector_id=connector.get('ConnectorId'))
    except Exception as e:
        logger.warning(f'telegram: the first-contact line did not go - {e}'); return False
    return True


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
    # this channel's own standing permission, not one switch for every channel at once - and the chat a walk was handed back from (A5)
    return (listens(store, c) == 'always'
            or bool(h and h['channel'] == channel and h.get('chat') == str(chat).strip())
            or bool(handed_back(store, channel, chat)))


def polls(store, connector) -> bool:
    """True when this connector must be polled for the doorway alone - it carries the Assistant chat,
    so its messages have to be read even when nothing about it is set to become work."""
    ch = (connector or {}).get('Type')
    if ch not in CHANNELS or not chat_of(connector): return False
    h = handoff(store)
    return listens(store, connector) == 'always' or bool(h and h['channel'] == ch) or bool(handed_back(store, ch, chat_of(connector)))


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
        # the hello, then the card in a bubble of its own - its choices ride the card, not the greeting (F21)
        from . import chatformat
        text = OPENED + chatformat.BREAK + carry_out(store, out, None, actor)
    send(store, channel, chat, text, cid)
    store.set_setting(HANDOFF_KEY, json.dumps(live), actor)
    store.set_setting(HANDED_KEY, '', actor)                  # a new hand-over: whatever was handed back before is this walk now
    store.audit('task', task['TaskId'], 'assistant_handoff_start', actor, detail={'channel': channel, 'chat': chat})
    concierge.record(store, task['TaskId'], 'assistant',
                     f"Taking this to {LABELS[channel]} - I have said hello there. "
                     f"Answer me in the chat; press {buttons.label('walk_here')} here when you want the desk again.")
    return {**live, 'label': LABELS[channel], 'say': out.get('say') or ''}


def end_handoff(store, actor: str = 'owner', note: str = CLOSED) -> dict:
    """Take it back: the chat is told the walk is over there, and the desktop is its own again."""
    from . import concierge, general
    h = handoff(store)
    store.set_setting(HANDOFF_KEY, '', actor)
    if not h: return {'ended': False}
    # ...and that chat keeps listening: the next message there picks the walk up again (A5)
    store.set_setting(HANDED_KEY, json.dumps({'channel': h['channel'], 'chat': h['chat'], 'at': _now(), 'told': False}), actor)
    task, _ = general.dock_task(store, actor)
    store.audit('task', task['TaskId'], 'assistant_handoff_end', actor, detail={'channel': h['channel']})
    concierge.record(store, task['TaskId'], 'assistant',
                     f"Back at the desk - {LABELS[h['channel']]} has been told we are done there.")
    try: send(store, h['channel'], h['chat'], farewell(store, h['channel'], note), h.get('connector_id'))
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
    try: keep_promises(store, force=force)
    except Exception as e: logger.warning(f'could not follow up in the chat: {e}')
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
    # "or keep going" read as the Continue button, which this line does not offer
    tail = (f'Say {handle} to take it now, or carry on with this one.' if handle
            else 'Name it and I will take you to it, or carry on with this one.')
    send(store, h['channel'], h['chat'], f'{say}\n\n{tail}', h.get('connector_id'))
    concierge.record(store, task['TaskId'], 'assistant', say)
    # ...onto the hand-off as it is NOW: a Take it back that landed while this was sending must stay taken back - writing
    # the record read a moment ago put the walk back in the chat and locked the desk again
    now = handoff(store)
    if now and now.get('at') == h.get('at'):
        store.set_setting(HANDOFF_KEY, json.dumps({**now, 'told': list(now.get('told') or []) + [a['key'] for a in fresh]}), 'owner')
    return len(fresh)


# ── the phone never drops you ─────────────────────────────────────────────────────────────────────────────────────
# "Told <the agent>: ..." and "Continuing TQ-… - it comes back here when it stops or asks" were the last words the chat ever said: the
# by-the-way push runs only while the walk is HANDED to the phone, and an owner who simply talks to it never hands it over. The
# agent finished, wrote its draft, and the chat sat silent (the owner, 2026-10-08: "it never sends close out email draft to
# whatsapp?" - "make sure the assistant on the phone never just drops you"). So work handed to an agent FROM a chat is a promise
# kept in that chat: when the agent stops working - finished, asking, a draft for your yes - the card comes back there.
PROMISES_KEY = 'phone_promises'
WORKING = ('working', 'queued')
PROMISE_HOURS = 12
PROMISE_LINE = 'I will tell you here when it finishes or needs you.'


def _promises(store) -> list:
    try: return [p for p in json.loads(store.get_setting(PROMISES_KEY) or '[]') or [] if isinstance(p, dict) and p.get('tid')]
    except ValueError: return []


def _task_item(store, tid: int, items: list = None) -> dict | None:
    """The task's row in the pile - the first, which is the one the rail leads with."""
    if items is None:
        from . import funnel
        items = funnel.pile(store).get('items') or []
    return next((i for i in items if str(i.get('tid') or '') == str(tid)), None)


def _starts_agent(op: dict) -> bool:
    """An act that sets an agent working: a hand-off, a continue, an answer to one that asked."""
    k = op.get('kind')
    return k in ('agent.continue', 'agent.answer', 'dispatch.prepare') or \
        (k in ('task.create_from_text', 'task.create_from_message') and str((op.get('params') or {}).get('kind')) in task_kinds.AGENT)


def _run(store, op: dict, actor: str) -> dict:
    """A confirmed act, run from the phone - and a general hand-off STARTED here. On the desk Send to agent makes the general task
    and the page asks its question when the chat opens (server.chat_message's ask tag); a phone has no page, so the tap said "It's
    being worked on now" and nothing ever started (F3). It starts on the task page's own Start road (server.dispatch_task)."""
    from . import concierge
    done = concierge.run_proposal(store, op, actor)
    p, o = done.get('params') or op.get('params') or {}, done.get('outcome') or {}
    if done.get('status') != 'done' or (done.get('kind') or op.get('kind')) != 'task.create_from_message' or str(p.get('kind')) != 'general' \
            or not o.get('chat') or not str(o.get('taskId') or '').isdigit(): return done
    import asyncio
    from fastapi import BackgroundTasks, HTTPException
    from . import server
    tid, bg = int(o['taskId']), BackgroundTasks()
    try: out = server.dispatch_task(tid, server.DispatchBody(kind='general'), bg)
    except (HTTPException, ValueError, RuntimeError) as e:
        why = getattr(e, 'detail', None) or plain(e)
        logger.warning(f'the phone could not start the agent on TQ-{tid:04d}: {why}')
        return {**done, 'outcome': {**o, 'chat': False, 'started': False, 'start_error': str(why)}}
    if bg.tasks:
        try: asyncio.run(bg())
        except Exception as e: logger.warning(f'the first ask to the agent on TQ-{tid:04d} did not go: {e}')
    # the page's own ask is spent - opened later, the task would ask the agent the same thing again
    tags = [x.strip() for x in str((store.get_task(tid) or {}).get('Tags') or '').split(',') if x.strip()]
    if server.ASK_TAG in tags: store.update_task(tid, {'Tags': ','.join(x for x in tags if x != server.ASK_TAG)}, actor)
    return {**done, 'outcome': {**o, 'chat': False, **{k: out.get(k) for k in ('started', 'existing', 'dispatch') if k in out}}}


def promise(store, tid) -> bool:
    """Work on `tid` was just handed to an agent from the chat speaking now (asking()): follow it up there."""
    at = asking()
    if not at or not str(tid or '').isdigit(): return False
    try: lane = (_task_item(store, int(tid)) or {}).get('lane') or ''
    except Exception: lane = ''
    keep = [p for p in _promises(store) if int(p['tid']) != int(tid)]
    keep.append({'tid': int(tid), 'channel': at['channel'], 'chat': at['chat'], 'connector_id': at.get('connector_id'),
                 'at': time.time(), 'lane': lane, 'armed': lane in WORKING})
    store.set_setting(PROMISES_KEY, json.dumps(keep), 'assistant')
    return True


def keep_promises(store, force: bool = False) -> int:
    """Each promised task whose agent has STOPPED working comes back to its chat as its card - once. It waits until the agent
    has been seen working (an answered question is still `blocked` for a moment), or until its row is something new."""
    ps = _promises(store)
    if not ps: return 0
    from . import concierge, funnel
    items = funnel.pile(store).get('items') or []
    keep, kept = [], 0
    for p in ps:
        tid, chat = int(p['tid']), p['chat']
        if time.time() - float(p.get('at') or 0) > PROMISE_HOURS * 3600: continue        # stale: the walk has long moved on
        it, t = _task_item(store, tid, items), store.get_task(tid) or {}
        lane = (it or {}).get('lane') or ''
        if lane in WORKING: keep.append({**p, 'armed': True}); continue
        # ...and a run that ENDED by its own word with no row left on the pile is over too: a failed or finished agent on a task still
        # open kept its promise unsaid for twelve hours (F5)
        from . import workerstate as ws
        end = None if it else ws.ended(store, tid)
        done = (t.get('Status') in ('done', 'dropped') or end in ('finished', 'failed')) and not it
        if not (p.get('armed') or done or (it and lane != p.get('lane'))): keep.append(p); continue
        if not force and not quiet(store, p['channel'], chat): keep.append(p); continue   # mid-conversation: the next look tries again
        ref = f'TQ-{tid:04d}'
        if it:
            with concierge.delivering(concierge.PHONE): nxt = concierge.surface(store, it['key'], actor='owner')
            text = turn_text(nxt, lead=f'{ref} is back:', store=store)
        else:
            state = agent_state({'kind': 'agentdone', 'tid': tid}, store) if t.get('Status') not in ('done', 'dropped') else ''
            said = (f'{ref} is back: the agent {state}.' if state.startswith('failed') else f'{ref} is finished - nothing on it waits on you.')
            # ...a failed one with its way on first, as its card offers it (R2 on the phone, A2)
            again = [(buttons.label('try_again'), {'t': 'continue', 'tid': tid})] if state.startswith('failed') else []
            text = turn_text({'say': said, 'item': None}, store=store,
                             extra=again + [(f'Open {ref}', {'t': 'open', 'key': f'task:{tid}'}), (concierge.CHIP_WORDS['next'], {'t': 'next'})])
        send(store, p['channel'], chat, text, p.get('connector_id'))
        kept += 1
    # ...plus any promise made WHILE this looked (a chat turn on another thread): rewriting the list read above would drop it
    seen = {(int(p['tid']), p.get('at')) for p in ps}
    store.set_setting(PROMISES_KEY, json.dumps(keep + [p for p in _promises(store) if (int(p['tid']), p.get('at')) not in seen]), 'assistant')
    return kept


CLOSING_SECS = 10.0         # the whole goodbye to the phones - the lifespan's cleanup is bounded, and these are network calls


def promises_closing(store, secs: float = CLOSING_SECS) -> int:
    """Taskuary is shutting down: each open promise gets ONE honest line, then the list is cleared. "I will tell you here when
    it finishes" was the last thing the chat heard - the close stopped the agent, nothing was sent, and the promise lapsed
    twelve hours later in silence (B3, 2026-10-11). Run after the sessions are closed, so the task says what the close did."""
    from .terminal import INTERRUPTED
    ps = [p for p in _promises(store) if time.time() - float(p.get('at') or 0) <= PROMISE_HOURS * 3600]
    end, told = time.time() + secs, 0
    for p in ps:
        if time.time() > end: logger.warning(f'closing: {len(ps) - told} phone promise(s) left unsaid - out of time'); break
        tid = int(p['tid']); ref, t = f'TQ-{tid:04d}', store.get_task(tid) or {}
        if t.get('Status') in ('done', 'dropped'): text = f'{ref} is finished. Taskuary is closing now - I will catch up when it opens again.'
        elif INTERRUPTED in str(t.get('Tags') or ''):
            text = (f'Taskuary is closing, so the work on {ref} stopped before it finished. It is back on your list, and nothing '
                    'starts again until you say so.')
        else: text = f'Taskuary is closing, so I cannot follow {ref} here any more. Look for it when Taskuary opens again.'
        try: send(store, p['channel'], p['chat'], text, p.get('connector_id')); told += 1
        except Exception as e: logger.warning(f'closing: the phone was not told about {ref} - {e}')
    store.set_setting(PROMISES_KEY, '[]', 'assistant')
    return told


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


STARTED = time.time()                  # this process came up: a message sent before it waited out a closed Taskuary
CLOSED_GRACE = 5.0                     # seconds of clock skew between the phone's stamp and ours


def queued_while_closed(rows) -> dict:
    """The doorway's messages that were sent while Taskuary was closed - [(chat, message id, sent at, words)] from one poll - as {chat:
    {'newest': id, 'skip': {ids}, 'older': [words, ...]}}. Only the newest is acted on (A10, 2026-10-22): each was answered and acted on
    in turn, an hour-old "next" included, and nothing said the app had been closed."""
    by = collections.defaultdict(list)
    for chat, mid, at, words in sorted(rows, key=lambda r: float(r[2] or 0)):
        if at and float(at) < STARTED - CLOSED_GRACE: by[str(chat)].append((mid, words))
    return {chat: {'newest': q[-1][0], 'skip': {m for m, _w in q[:-1]}, 'older': [w for _m, w in q[:-1]]} for chat, q in by.items()}


def closed_note(older: list) -> str:
    """What the answer to the newest queued message opens with."""
    said = 'Taskuary was closed - picking up from your last message.'
    if not older: return said
    named = '; '.join(f'"{_cut(w, 40)}"' for w in older[:3]) + (f' and {len(older) - 3} more' if len(older) > 3 else '')
    return f"{said} {plural(len(older), 'earlier message')} {'was' if len(older) == 1 else 'were'} not acted on: {named}."


def intercept(store, channel: str, chat: str, text: str, *, from_me=False, taskuary=False, connector=None,
              message_id=None, poll=False, arrived=None, heard=False, closed=None) -> bool:
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
                           message_id, bool(poll), arrived, bool(heard), closed),
                     name=f'taskuary-{channel}-assistant', daemon=True).start()
    return True


def _locked_respond(store, channel: str, chat: str, question: str, connector_id: int, message_id=None, poll=False,
                    arrived=None, spoken=False, closed=None):
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
            try: respond(store, channel, chat, question, connector_id, poll=poll, cancel=ev, heard=spoken, closed=closed)
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


# ── the start of the walk: THE RAIL, said in a chat (walkSummary.js) ──────────────────────────────────────────
# Its own who-wants-what grouping put a finished agent's task under "Agents waiting" while the rail had it On you (the
# owner, 2026-10-02: "it should just read from the rail no?"). The bands, their order and their names are the rail's:
# funnel.level_of, which mirrors lanes.js levelOf, and the order is lanes.json's `sections`.
from .lanes import LEVEL_ORDER
AGENT_CARD_LANES = {'blocked', 'stopped', 'queued', 'working', 'saved'}     # the lanes whose card is an agent's
_TASKISH = ('todo', 'message', 'asked', 'task')                            # a task's own card - an agent may have run on it
ROWS_PER_GROUP = 5


def group_of(i: dict) -> str:
    from . import funnel
    return funnel.level_of(i)


def groups():
    from . import funnel
    return [(k, funnel.SECTION_WORDS[k]) for k in LEVEL_ORDER]


def _shows(i: dict) -> dict:
    """How the row reads, as the server worked it out for every surface (funnel_presentation.shows) - a card that came
    some other road than the pile is worked out the same way here."""
    return i.get('shows') or shows(i)


def who_of(i: dict, store=None) -> str:
    """Who, as the summary names them: the SENDER's own display name where the mail has one - the shared reading took the address's
    domain ("example") or the agent's CLI ("claude", "kai") over the person (F15) - else the row's who, as every surface says it."""
    named = ' '.join(str(i.get('who') or '').split())
    tools = {str(i.get(k) or '').strip().lower() for k in ('agent', 'working')} - {''}
    who = _shows(i)['who']
    # ...an agent by what it IS, read off its task: with no store a general run (no session mode) was called "Coding agent" in the
    # opener while its own card said General agent (F6, the 2026-10-22 re-walk)
    if who.strip().lower() in tools: return agent_label(i, store=store)
    # a word of the ADDRESS stood for a sender whose mail names them in full - a person's or a team's own name, never a lone word
    host = re.split(r'[@.]', str(i.get('email') or '').lower())
    if ' ' in named and '@' not in named and who.strip().lower() in host and not is_own(i): return story_who(i)
    return who


# the count's noun, said right for one: "1 task", "1 report" - never "1 tasks" (F15)
_ONE = {'task': ('task', 'tasks'), 'reports': ('report', 'reports'), 'ideas': ('Advisor idea', 'Advisor ideas')}


def who_wants_what(items: list, store=None) -> str:
    """The desktop's opener, as a chat can print it: the count in a sentence, then each group's rows."""
    live = list(items or [])
    if not live: return 'Nothing is waiting on you.'
    have = [(k, w, [i for i in live if group_of(i) == k]) for k, w in groups()]
    have = [(k, w, rows) for k, w, rows in have if rows]
    lines = [f"{plural(len(live), 'thing')}: "
             + ', '.join(plural(len(rows), *_ONE[k]) if k in _ONE else f"{len(rows)} {w if k == 'fyi' else w.lower()}" for k, w, rows in have) + '.']
    for key, word_, rows in have:
        # For later is sorted soonest-back first, as the rail draws it (funnelPile.bandsOf)
        if key == 'later': rows = sorted(rows, key=lambda i: str(i.get('back_at') or i.get('defer_until') or '9999'))
        lines.append(f'\n{word_.upper()} · {len(rows)}')
        for i in rows[:ROWS_PER_GROUP]:
            # FOR LATER says when it comes back, in the rail's own short form (funnelPile.railBack)
            back = _back_in(i.get('back_at') or i.get('defer_until')) if key == 'later' else ''
            state = (f'back {back}' if back else '') if key == 'later' else _shows(i)['state']
            # ...and never the heading's own word again: "(fyi)" on every row under FYI (F15)
            if state.lower() in (key, word_.lower(), word_.lower().rstrip('s')): state = ''
            lines.append(f"· {who_of(i, store)} - {_cut(i.get('title') or '', 70)}" + (f' ({state})' if state else ''))
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
# (no "Set up Taskuary": setup is the desk's Setup button, never a chat script - the owner, 2026-10-19)
WALK = 'Walk me through my tasks'
SCRIPT_LINES = [(WALK, {'t': 'walk'}), ('Set up a report', {'t': 'script', 'script': 'set up a report'}),
                # the sidebar's browse buttons, as picks (doorway_browse): sections, then the list, then one
                ('Connections', {'t': 'browse', 'area': 'connections'}), ('Reports', {'t': 'browse', 'area': 'reports'}),
                ('Hub', {'t': 'browse', 'area': 'hub'}), ('Settings', {'t': 'browse', 'area': 'settings'})]


MENU = 'More…'                                 # the opener's way to everything it does not list (A7) - not the card's More
OPENER_SECTIONS = ('reports', 'fyi', 'ideas', 'later')   # the section walks the opener leads with, the walkers' most used first


def opener_lines(items: list) -> list:
    """The day's opener's picks: the walk, the two section walks the rail holds that walkers reached for most, and More… - about four
    clear options instead of nine (A7, 2026-10-22). "Walk me through my tasks" next to "Walk Tasks", "Reports" next to "Walk Reports"
    read as the same thing twice. The walk picked off the opener goes straight to the first card: the summary is right above it (F9)."""
    from . import doorway_browse
    walks = dict(doorway_browse.section_rows(items))
    lead = [w for s in OPENER_SECTIONS for w, a in walks.items() if a['section'] == s][:2]
    return [(WALK, {'t': 'walk', 'opened': True})] + [(w, walks[w]) for w in lead] + [(MENU, {'t': 'menu'})]


def menu_lines(store) -> list:
    """What More… opens: everything the opener does not list - set up a report, the other section walks, Connections, Reports, Hub and
    Settings - so nothing the nine options reached is lost; then the walk again, the way on."""
    from . import doorway_browse, funnel
    try: items = funnel.pile(store).get('items') or []
    except Exception as e:
        logger.debug(f'the phone menu has no pile: {e}'); items = []
    shown = {w for w, _a in opener_lines(items)}
    rest = [r for r in SCRIPT_LINES[1:2] + doorway_browse.section_rows(items) + SCRIPT_LINES[2:] if r[0] not in shown]
    return rest + [(WALK, {'t': 'walk', 'opened': True})]


def greeting(now=None) -> str:
    from datetime import datetime as _dt
    h = (now or _dt.now()).hour
    return 'Good morning.' if h < 12 else 'Good afternoon.' if h < 18 else 'Good evening.'


def day_opener(store, items: list, now=None) -> str:
    """THE DAY IN A BREATH - the greeting, today's meetings, then who wants what. ONE text for the morning line and for
    "Walk me through my tasks" (the owner, 2026-09-29: "when you hit walk me through on whatsapp that should trigger the
    morning summary"): the walk opened with who-wants-what alone, without the meetings the morning line carried."""
    return '\n\n'.join(x for x in (greeting(now), meetings_line(store), who_wants_what(items, store) if items else 'Nothing is waiting on you.') if x)


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
    it"). Quiet when the pipe is empty; never twice in a day; the two options are always the same."""
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
    lines = opener_lines(items)
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


def walk(store, actor: str = 'owner', opener: bool = True) -> str:
    """"Walk me through my tasks", picked: the day's summary, then the first card - the desktop's Start at the top.
    A table of typed words used to run this and set-up with no model ("next", "set up", "my tasks"); the owner,
    2026-09-25: "No hard coded anything... Only if you type 1 or hit poll that's clicking a pill". Typed, the words
    go to the model like any other. `opener=False`: picked off the day's opener itself, which was the summary - it goes
    straight to the first card (docs/phone-choices.md: "no summary reprinted"; F9)."""
    from . import concierge, funnel
    with concierge.delivering(concierge.PHONE):
        try: opener = day_opener(store, funnel.pile(store).get('items') or []) if opener else ''
        except Exception as e:
            logger.debug(f'the phone walk opened without its summary: {e}'); opener = ''
        spend_morning(store)                                  # the summary IS the day's opener - it is not said twice
        from . import welcome
        welcome.mark_greeted(store)                           # ...on the desk too: one good morning a day, wherever it was said
        out = concierge.resume(store, actor)                  # the item on the table first, when there still is one
        return carry_out(store, out, None, actor=actor, lead=opener)


def respond(store, channel: str, chat: str, question: str, connector_id: int, poll: bool = False, cancel=None, heard: bool = False,
            closed: list = None):
    """Answer synchronously; the poller runs this on a serialized background worker. `cancel` is set when a pick
    arrives behind this turn: the model's answer is dropped, never sent after the pick's."""
    from . import concierge, general
    # `heard`: the words are a voice note's, as transcribed - the answer says them back first (A17)
    _ASKING.chat = {'channel': channel, 'chat': chat, 'connector_id': connector_id, **({'heard': question} if heard else {})}
    # the first word after a hand-back picks the walk up here again, and says so once (A5)
    hb = handed_back(store, channel, chat)
    if hb and not hb.get('told') and not handoff(store):
        store.set_setting(HANDED_KEY, json.dumps({**hb, 'told': True}), 'assistant')
        _ASKING.chat['again'] = True
    if closed is not None: _ASKING.chat['closed'] = closed_note(closed)       # it waited out a closed Taskuary (A10)
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
            # A NUMBER TELEGRAM NEVER SHOWED is not acted on silently (A18): it says what the choices are, under them. An agent asking on
            # the table may want a number for an answer - there it is words, as typed
            if channel == 'telegram' and not picked and bare_number(question) and offered and (item or {}).get('kind') != 'agent':
                send(store, channel, chat, f'"{question.strip()}" is not one of the choices here - the buttons have no numbers on Telegram. '
                                           f'Tap one: {", ".join(_tg_buttons(store, chat) or offered)}.', connector_id, choices=offered)
                return
            act = acts.get(question) if picked else None
            # a pick that IS words (Try again): the same line goes to the model again, as if typed
            if act and act.get('t') == 'ask': question, picked, act = str(act.get('text') or question), False, None
            # ...spent by a PICK now; words spend it only when their answer goes out - a tap made while the model is
            # still thinking about typed words must find its list (PickJumpsTheQueueTests)
            if picked: forget_offered(store, channel, chat)
            _ACTS.rows = None
            # HELP AND STOP ARE BUILT IN (A16, 2026-10-22): "/help" and "/stop" went to the model and came back "Ok." - the two words a
            # stranger to the chat reaches for first answer here, with no model, on both channels
            builtin = command(question) if not picked else ''
            if builtin:
                if builtin == 'stop':
                    for k in (NOTE_KEY, REDRAFT_KEY): store.set_setting(f'{k}:{channel}:{chat}', '', 'assistant')
                forget_offered(store, channel, chat)
                if builtin == 'stop' and (h := handoff(store)) and h['channel'] == channel and h.get('chat') == chat:
                    end_handoff(store, 'owner', HANDED_BACK)            # the walk was handed here: it goes back, and this chat is told
                    return
                send(store, channel, chat, (help_text if builtin == 'help' else stop_walk)(store, tid), connector_id)
                return
            redo = str(store.get_setting(f'{REDRAFT_KEY}:{channel}:{chat}') or '')
            if redo and not picked:
                forget_offered(store, channel, chat)
                send(store, channel, chat, run_act(store, {'t': 'redraft', 'key': redo, 'how': question}, item), connector_id)
                return
            if redo: store.set_setting(f'{REDRAFT_KEY}:{channel}:{chat}', '', 'assistant')
            pending = str(store.get_setting(f'{NOTE_KEY}:{channel}:{chat}') or '')
            if pending: store.set_setting(f'{NOTE_KEY}:{channel}:{chat}', '', 'assistant')
            if pending and not picked:
                # the line typed after "Continue" is what to tell the agent - a text field, not a word to read
                forget_offered(store, channel, chat)
                send(store, channel, chat, _continue(store, pending, question), connector_id)
                return
            if act and act.get('t') == 'page':
                # the same list, the next page - kept whole again (the pick spent it above) so a typed number still answers
                store.set_setting(f'{OFFERED_KEY}:{channel}:{chat}', json.dumps(offered), 'assistant')
                store.set_setting(f'{ACTS_KEY}:{channel}:{chat}', json.dumps(acts), 'assistant')
                send(store, channel, chat, 'More choices:', connector_id, page=int(act.get('at') or 0), choices=offered)
                return
            if act and act.get('t') == 'handback':
                end_handoff(store, 'owner', HANDED_BACK)            # tells this chat itself
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
                folded = more_text(store, item, page_chars(channel)) or 'Nothing more on this one.'
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
            if out.get('no_brain') and not picked:
                # NO AI TO READ THE WORDS (F10): "next" typed over a list holding Next is that choice's own label - the poll vote said
                # in words - and a number past the list is a slip of the thumb; with nobody to read either, the line answered "use
                # the buttons" and the walk stopped there
                said = ' '.join(str(question or '').split()).strip(' .!?').lower()
                hit = next((w for w in offered if str(w).strip().lower() == said and w in acts), None)
                if hit:
                    forget_offered(store, channel, chat)
                    send(store, channel, chat, run_act(store, acts[hit], item), connector_id)
                    return
                if said.lstrip('#').isdigit() and offered:
                    send(store, channel, chat, f'Pick 1 to {len(offered)} - the choices are below.', connector_id, choices=offered)
                    return
            if not picked: forget_offered(store, channel, chat)
            text = carry_out(store, out, item, picked=picked)
            if out.get('no_brain') and not _CHOICES_BLOCK.search(text): text = text.replace(concierge.NO_BRAIN, concierge.NO_BRAIN_BARE)
            # THE DAY'S OPENING rides on the answer to their first typed message of the day (or after a long gap): the phone
            # never speaks first, so this is where it goes - once, and never if the desk already said it (welcome.phone_lead)
            if not picked:
                from . import welcome
                try: lead = welcome.phone_lead(store)
                except Exception as e:
                    logger.debug(f'the phone answered without its opening: {e}'); lead = ''
                if lead: text = f'{lead}\n\n{text}'
        send(store, channel, chat, text, connector_id)
    except Exception as e:
        if cancel is not None and cancel.is_set():
            logger.info(f'{channel}: a turn gave way to a pick'); return
        logger.warning(f'the {channel} assistant could not answer: {e}')
        try: send(store, channel, chat, stuck(store, f"I couldn't answer that - {plain(e)}. Say it again, or go on to the next one."), connector_id)
        except Exception as send_error: logger.warning(f'the {channel} assistant could not send its error: {send_error}')
    finally: _ASKING.chat = None


_COMMANDS = {'help': 'help', 'start': 'help', '?': 'help', 'stop': 'stop'}


def command(text: str) -> str:
    """'help' or 'stop' when the whole line is one of the chat's built-in words - "help", "/help", Telegram's "/start" (its own first
    word, and "/help@TheBot" in a menu) - else ''. Only the bare word: "stop the agent on TQ-0003" is a request, the model's to read."""
    t = ' '.join(str(text or '').split()).lower().rstrip('.!')
    if t.startswith('/'): t = t[1:].split('@', 1)[0]
    elif t == 'start': return ''                                  # typed "start" is no command; Telegram's own is "/start"
    return _COMMANDS.get(t, '')


def help_text(store, tid=None) -> str:
    """What the phone can do, in a few lines, with the way on under it - the card on the table to go back to, the walk, everything else."""
    from . import concierge, general
    lines = ['What you can do here:',
             '· Tap a choice under a card - it is the same button as on the desktop.',
             '· Type what you want: "remind me Friday", "bring up TQ-0012", "reply that I am out until Monday".',
             '· "next" moves on, "stop" ends the walk, "help" shows this again.']
    try: brain = bool(general.provider_options(store))
    except Exception: brain = True
    if not brain: lines.append(f"Typed requests need an AI - connect one under {concierge.places.name('ai')} on the desktop. The choices work without one.")
    return turn_text({'say': '\n'.join(lines), 'item': None}, store=store, extra=_way_on(store, tid))


def _way_on(store, tid=None) -> list:
    """The picks that never dead-end: back to the card on the table (when there is one), the walk, and everything else."""
    from . import concierge
    try: table = concierge.restore_current(store, tid) if tid else None
    except Exception: table = None
    back = [(f"Back to {table.get('ref') or 'the card'}", {'t': 'open', 'key': table['key']})] if (table or {}).get('key') else []
    return back + [(WALK, {'t': 'walk', 'opened': True}), (MENU, {'t': 'menu'})]


def stop_walk(store, tid=None) -> str:
    """Stop, said in the chat: the walk ends here - nothing on the table, no section held, the next walk from the top - and nothing is
    changed on any task. The walk and everything else stay one tap away."""
    from . import concierge, doorway_browse, funnel
    if tid:
        try: concierge.set_current(store, tid, None, 'owner')
        except Exception as e: logger.debug(f'the phone stop left the table as it was: {e}')
    doorway_browse.hold(store, asking(), None)
    funnel.new_walk(store)
    return turn_text({'say': 'Stopped - the walk is over, and nothing on any task changed. Message me any time to start again.', 'item': None},
                     store=store, extra=[(WALK, {'t': 'walk', 'opened': True}), (MENU, {'t': 'menu'})])


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
    # TYPED words are the AI's to read, as on the desktop (the owner, 2026-10-08: "why is it different if you type next ... ai should
    # match to pill action"): typed "next" over an asking agent went to the agent as its answer. The AI matches them - an answer is
    # answer_agent, which runs at once (concierge.AUTO), so it still goes straight in (2026-10-02); Next is Next.
    if not picked or words not in agent_answers(item): return ''
    out = ws.answer_open(store, int(item['tid']), words, actor) if item.get('tid') else {'delivered': False, 'state': 'no_request'}
    who = item.get('agent') or 'the agent'
    if out.get('delivered'):
        # ...never the last word: it is followed up here when the agent is done with it, and the walk goes on meanwhile
        from . import concierge
        said = f'Told {who}: "{words}".' + (f' {PROMISE_LINE}' if promise(store, item['tid']) else '')
        return turn_text({'say': said, 'item': None}, store=store, extra=[(concierge.CHIP_WORDS['next'], {'t': 'next'})])
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
    if prop.get('settles') and prop.get('key') and item and prop['key'] == item.get('key'): return True
    # ...and a Remind me / snooze / later TYPED on the table's own task puts it away as the poll's Remind me does - the walk moves on
    # (F19): typed, it said "Away until ..." and sat on the card it had just put away
    p = prop.get('params') or {}
    if not item: return False
    if prop.get('kind') == 'task.defer':
        return str(prop.get('target') or '') == str(item.get('tid') or '-') and str(p.get('until') or '').strip().lower() not in ('', 'none')
    return prop.get('kind') == 'item.settle' and str(p.get('verb') or '') in ('later', 'skip') and p.get('key') in (None, item.get('key'))


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
    decision_verb = decision.get('verb')
    # a bare "Next." over the next card only echoes the press (F12): the card that follows is the answer
    if decision_verb == 'next' and str(out.get('say') or '').strip() == concierge.RECEIPTS['next'] and not lead: said = []
    else: said = [turn_text(out, lead, store, table=item)]
    verb = decision_verb
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
        # ...without "Nothing happens until you say yes." over the receipt that says it happened (F13)
        said = [turn_text({**out, 'proposal': None, 'say': _unasked(out.get('say'))}, lead, store, table=item)]
        done = _run(store, prop, actor)
        said = _said_once(said, done) + [receipt_text(store, done, actor)]
        walk_on = done.get('status') == 'done' and _settled_the_table(prop, item)
    elif prop and not picked and not prop.get('auto') and prop.get('status') == 'proposed' and not asks(prop) \
            and (lit := _bring_up(store, prop, actor)):
        return '\n\n'.join(x for x in (lead.strip(), lit) if x)
    elif prop and prop.get('auto') and prop.get('status') == 'proposed':
        done = _run(store, prop, actor)
        # the act run at once is said ONCE, by its receipt: its card line ("Answer it - general - ...", a button that is gone) said
        # it a second time above it (F13); only what it could not do (`say_card`, the note) stays
        said = [x for x in (lead.strip(), str(prop.get('say_card') or '').strip()) if x] + [receipt_text(store, done, actor)]
        walk_on = done.get('status') == 'done' and _settled_the_table(prop, item)
        # a SCRIPT started by name from the phone: the tasks walk is Next; set-up opens on the connections
        # (the spec: "or at least see my connectors"); the composer wants a sentence
        script = str((done.get('outcome') or {}).get('script') or '')
        # ...the tasks walk is the PILL's walk - the summary, then the card ON THE TABLE (concierge.resume): walking on from here
        # skipped the table, which the walk had already read, and stacked "Done - Start a script" over it (F9)
        if script and 'tasks' in script and done.get('status') == 'done': return walk(store, actor)
        # ...and set-up is its question alone: "Doing it now. Done - Start a script by its name: ... Starting: set up a report." over it
        # read the tool's own description back as a receipt (the 2026-10-22 re-walk)
        if script and done.get('status') == 'done': return '\n\n'.join(x for x in (lead.strip(), script_words(store, script)) if x)
        if script: said.append(script_words(store, script))
    elif verb in ('reply', 'redraft') and (on or {}).get('mid'):
        rid = _draft(store, on, verb, decision.get('text') or '')
        if rid:                                             # the draft is the next thing to read, so go to it
            nxt = _draft_card(store, rid, actor)
            return '\n\n'.join(said + [turn_text(nxt, store=store)])
        said.append('I could not write that draft here - it is waiting on the task page.')
    if walk_on:
        here = (item or {}).get('key') if verb == 'next' else None       # Next leaves the table as the desktop's does
        return _on(store, actor, said, leaving=here, exclude=here, done_with=(item or {}).get('key'))
    # AN ANSWER THAT NAMES A TASK BRINGS IT UP (the router rule): the desk opens a [TQ-…](#task=N) link the moment the answer lands;
    # the phone stripped it to its words, so "bring up TQ-0035" was answered and nothing came up (F18). Its card and its choices
    linked = _TASK_ID.search(str(out.get('say') or '')) if not out.get('item') and not prop and not verb else None
    if linked:
        nxt = concierge.surface(store, f'task:{int(linked.group(1))}', actor=actor)
        if nxt.get('item'):
            from . import chatformat
            words = turn_text({**out, 'chips': [], 'options': []}, lead, store)
            return chatformat.BREAK.join(x for x in (words, turn_text(nxt, store=store)) if x)
    return '\n\n'.join(x for x in said if x)


def _bring_up(store, prop: dict, actor: str = 'owner') -> str:
    """A TYPED ACT BRINGS UP THE REAL CHOICE (A6, 2026-10-22; the router rule - no confirm cards, light the real button): "remind me Friday"
    came back as "Remind me: Fri 23 Oct: TQ-0001. Nothing happens until you say yes." with a yes/no under it. A Remind me is the card's own
    day picker, the typed day first; an act that is one of a card's buttons brings that card up with the button first. The proposal is
    withdrawn - the pick is the decision. '' for anything else (a set of items, a setting, a new task): those keep their yes or no."""
    from . import concierge, operations
    kind, p, target = prop.get('kind'), prop.get('params') or {}, prop.get('target')
    # a sender rule is more than the card's Not ours (just this once, on the phone): what was asked keeps its own yes or no
    if kind in ('preference.exclude_sender', 'preference.sender_rule'): return ''
    tid = int(target) if str(target or '').isdigit() and prop.get('targetKind') in ('task', 'item') else None
    if kind == 'item.settle': b, key = concierge.canon_verb(str(p.get('verb') or 'close')), p.get('key') or (f'task:{tid}' if tid else '')
    else:
        b = concierge.KIND_BUTTON.get(kind) or ('regular_agent' if kind == 'task.create_from_message' and str(p.get('kind')) in task_kinds.AGENT else '')
        key = f'task:{tid}' if tid and prop.get('targetKind') == 'task' else str(p.get('key') or '')
        if not key and prop.get('targetKind') == 'message' and str(target or '').isdigit():   # a mail's act: the card that holds it
            from . import funnel
            key = next((i['key'] for i in funnel.pile(store).get('items') or [] if str(i.get('mid') or '') == str(target)), '')
    if not b or not key or b == 'next': return ''
    card = concierge.surface(store, key, actor=actor)
    on = card.get('item')
    if not on: return ''
    ref = on.get('ref') or _cut(on.get('title') or 'it', 60)
    def withdraw():
        try: operations.cancel(store, prop['id'], actor)
        except Exception as e: logger.debug(f'the phone left proposal {prop.get("id")} as it was: {e}')
    if b == 'defer' and on.get('tid'):
        until = str(p.get('until') or '').strip()
        day = concierge._day_said(until) if until else ''
        rows = ([(day, {'t': 'remind', 'tid': on['tid'], 'until': until})] if day and until.lower() not in {u for _l, u in REMIND_DAYS} else [])
        rows += [(label, {'t': 'remind', 'tid': on['tid'], 'until': u}) for label, u in REMIND_DAYS]
        rows = sorted(rows, key=lambda r: r[1]['until'] != until) + [('Cancel', {'t': 'stay', 'key': on.get('key') or key})]
        withdraw()
        return turn_text({'say': f"Remind you about {ref} when? Or say another day.", 'item': None}, store=store, extra=rows)
    label = next((c['label'] for c in card.get('chips') or [] if isinstance(c, dict) and c.get('verb') == b), '')
    if not label: return ''                    # not one of this card's buttons: the yes or no stands
    withdraw()
    return turn_text({**card, 'first': b}, f'{label} is first under {ref} - tap it to do it.', store=store)


def _unasked(say) -> str:
    """The proposal's line without its invitation to say yes - the number WAS the yes."""
    from . import concierge
    return re.sub(r'\s*' + re.escape(concierge.WAITS) + r'\s*$', '', str(say or '')).strip()


def _said_once(said: list, done: dict) -> list:
    """What was said before the run, minus a bare acknowledgement over an act that did not happen: "Ok." then "Not done - ..."."""
    if done.get('status') == 'done': return said
    return [x for x in said if len(re.sub(r'[^\w\s]', '', str(x or '')).split()) > 2]


ALT_QUESTION = {'not_ours': 'How far?', 'agent': 'Which agent?'}


def _pinned(store, item: dict | None, verb: str) -> dict:
    """What a pick must still find when it lands: the draft this message showed (verdicts.draft_revision). The yes is
    pressed off THIS message, and an agent's `taskuary --reply` can rewrite the draft before the owner answers."""
    if verb != 'approve' or store is None or not (item or {}).get('rid'): return {}
    from . import verdicts
    try: return {'shown': verdicts.draft_revision(store, int(item['rid']))}
    except Exception as e:
        logger.debug(f'the phone could not pin the draft it showed: {e}'); return {}


def _drawn_at(item: dict | None) -> dict:
    """The revision each card in this message was drawn at, for the pick to carry: Done and Next put down what THIS message
    showed (funnel.showing), never a mail that landed on the item before the owner answered."""
    cards = (item or {}).get('items') if (item or {}).get('kind') == 'fyis' else [item or {}]
    rev = {c['key']: c['view_revision'] for c in cards or () if c.get('key') and c.get('view_revision')}
    return {'rev': rev} if rev else {}


def _draft_moved(store, act: dict, on: dict) -> str:
    """The draft changed after the phone showed it: nothing is sent, and the new one is shown for its own yes."""
    if not act.get('shown') or act.get('verb') != 'approve' or not on.get('rid'): return ''
    from . import concierge, verdicts
    if verdicts.draft_revision(store, int(on['rid'])) == act['shown']: return ''
    nxt = concierge.surface(store, act.get('key'), actor='owner')
    return turn_text(nxt, 'The draft changed after I showed it - nothing was sent. This is the one waiting now:', store=store)


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


def stale_tap(store, channel: str, chat: str, connector_id=None, spent: bool = False):
    """A tap on a poll that is no longer the newest: its choices went with the card it was under, so nothing runs (a stale
    pick must never fire) - but a tap that got no answer read as the assistant freezing (2026-09-29). The current choices
    are the ones under the last message; say so, once, in words. `spent`: a second pick on the newest poll, which answers
    once (the owner, 2026-10-02: "once a poll is answered it should never be allowed to be used again")."""
    said = ('That list was already used - nothing ran. The choices under my last message are the current ones.' if spent
            else 'That was an older list, so nothing ran - the choices under my last message are the current ones.')
    # ...and this line is now the last message - on Telegram it takes the older buttons off (tg_send) - so the current choices come
    # with it, on both channels: an answer with nothing to tap under it is a dead end (F19)
    try: live = json.loads(store.get_setting(f'{OFFERED_KEY}:{channel}:{chat}') or '[]') or []
    except ValueError: live = []
    try: send(store, channel, chat, said, connector_id, choices=live or None)
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
        elif v == 'go': continue        # a place in the desktop app (Connections, Settings): a phone cannot open it, the line says where
        elif v:
            if table is None:
                from . import general
                task, _ = general.dock_task(store, actor)          # the ONE dock the desk and the phone share
                table = (concierge.restore_current(store, task['TaskId']) or {}).get('key') or ''
            if table: yield c['label'], {'t': 'verb', 'verb': v, 'key': table}


def sent_rows(store, done: dict) -> list:
    """A send keeps its task (concierge.sent_chips): the item stays, and Mark done or Next is the owner's next pick, numbered."""
    from . import concierge
    return [(c['label'], {'t': 'close', 'tid': c['tid']} if c['verb'] == 'close' else {'t': 'next'}) for c in concierge.sent_chips(store, done)]


def receipt_text(store, done: dict, actor: str = 'owner') -> str:
    """The receipt - and when the act did NOT happen, its way on, numbered (2026-09-29: a failed Close out on the phone
    said "Not done - 403 ..." and offered nothing to pick, and the list it was picked from was already spent)."""
    from . import concierge
    if done.get('status') == 'done':
        line = concierge.receipt(store, done, actor)
        if (sent := sent_rows(store, done)): return turn_text({'say': line, 'item': None}, store=store, extra=sent)
        # ...and the task it made or moved is a pick: "open it from here or from Tasks" with nothing to tap (2026-10-06),
        # where the desktop draws Open TQ-… under the same line
        o = done.get('outcome') or {}
        tid = o.get('taskId') or o.get('task_id') or (done.get('target') if done.get('targetKind') == 'task' else None)
        if not str(tid or '').isdigit(): return line
        from .store import task_ref
        ref = o.get('ref') or task_ref(int(tid))
        extra = [(f'Open {ref}', {'t': 'open', 'key': f'task:{int(tid)}'})]
        # ...and an agent that never started is not walked past: its task to open again, or the walk's way on - never the same card back
        if o.get('start_error'): return turn_text({'say': line, 'item': None}, store=store, extra=extra + [(concierge.CHIP_WORDS['next'], {'t': 'next'})])
        # ...and an agent set to work from here is followed up HERE (keep_promises), with the walk's way on meanwhile
        if _starts_agent(done) and o.get('started') is not False and promise(store, tid):
            line, extra = f'{line} {PROMISE_LINE}', extra + [(concierge.CHIP_WORDS['next'], {'t': 'next'})]
        return turn_text({'say': line, 'item': None}, store=store, extra=extra)
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
    # THE RECEIPT IS ITS OWN BUBBLE, and the choices are the next card's alone (F14): a receipt's own picks (Open TQ-…, Mark done on
    # the task it just sent for) rode the same poll as the card under it - two Nexts, and a Mark done for a different task
    from . import chatformat
    said = [_CHOICES_BLOCK.sub('', x).strip() for x in said if x]
    card = turn_text(nxt, lead=lead, store=store, extra=extra)
    return chatformat.BREAK.join(['\n\n'.join(x for x in said if x), card] if any(said) else [card])


def _ran(store, prop: dict, done: dict, item: dict | None, actor: str) -> str:
    """After the run: the receipt, and the next item when the table was settled."""
    from . import concierge
    if done.get('draft_changed') and prop.get('key'):           # operations.execute refused it: show what waits now
        return turn_text(concierge.surface(store, prop['key'], actor=actor), concierge.receipt_turn(store, done, actor)['say'], store=store)
    if done.get('status') != 'done' or (done.get('outcome') or {}).get('start_error'): return receipt_text(store, done, actor)
    said = concierge.receipt(store, done, actor)
    # an agent set to work from here is followed up HERE (keep_promises) - the tap's road made no promise, only a typed number's did
    tid = (done.get('outcome') or {}).get('taskId')
    if _starts_agent(done) and (done.get('outcome') or {}).get('started') is not False and promise(store, tid): said = f'{said} {PROMISE_LINE}'
    if done.get('status') == 'done' and _settled_the_table(prop, item):
        return _on(store, actor, [said], done_with=prop.get('key') or (item or {}).get('key'))
    if (sent := sent_rows(store, done)): return turn_text({'say': said, 'item': None}, store=store, extra=sent)
    return said


def _settle(store, prop: dict, item: dict | None, actor: str) -> str:
    """A proposal a pick made: run it, unless its card asks something first - then ask that, numbered."""
    from . import concierge
    if prop.get('failed'):              # refused at propose time: the reason, and what the item CAN do instead
        return turn_text({'say': prop['say'], 'item': None}, store=store, extra=list(recovery_rows(store, prop.get('chips') or [], actor)))
    # ...but a card that ACTS AT ONCE (concierge.AUTO - Not ours on the table, as just this once: the owner, 2026-10-21, "no 'are you
    # sure'") runs on the press as the desktop's does: its question drawn here un-numbered was a card nothing could answer, so the tap
    # showed "File it: ..." and nothing ever ran
    if asks(prop) and not prop.get('auto'):
        said = f"{prop['label']}: {prop['summary']}." if prop.get('label') and prop.get('summary') else prop.get('say')
        return turn_text({'say': said, 'proposal': prop}, store=store)
    return _ran(store, prop, _run(store, prop, actor), item, actor)


def run_act(store, act: dict, item: dict | None, actor: str = 'owner') -> str:
    """One numbered pick, run the way the desktop's button runs it - never through the model."""
    from . import funnel
    with funnel.showing(act.get('rev')): return _run_act(store, act, item, actor)


def _run_act(store, act: dict, item: dict | None, actor: str = 'owner') -> str:
    from . import asks, concierge, funnel, operations
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
        if t == 'menu': return turn_text({'say': 'Everything else, from here:', 'item': None}, store=store, extra=menu_lines(store))
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
        if t == 'stay':
            # Cancel under a question about a card goes back to THAT card, its choices under it: "Left it - nothing moved." with
            # nothing to tap was a dead end (the 2026-10-22 re-walk). A section being walked stays walked
            here = asking() or {}
            if here.get('chat'):                                     # no Continue note waits, and no Redraft instruction
                for k in (NOTE_KEY, REDRAFT_KEY): store.set_setting(f"{k}:{here['channel']}:{here['chat']}", '', 'assistant')
            if not act.get('key'): return 'Left it - nothing moved.'
            back = concierge.surface(store, act['key'], actor=actor)
            return carry_out(store, back, back.get('item'), actor) if back.get('item') else stuck(store, 'Left it - nothing moved.')
        if t == 'close' and act.get('tid'):             # Mark done under a send's receipt: the one close, then the walk goes on
            tid_ = int(act['tid'])
            from .store import task_ref
            said = f'{task_ref(tid_)} closed.' if concierge.close_task(store, tid_, actor) else f'{task_ref(tid_)} was already closed.'
            here = (item or {}).get('key')
            return _on(store, actor, [said], leaving=here, exclude=here, done_with=here)
        if t == 'redraft':
            here = asking() or {}
            if here.get('chat'): store.set_setting(f"{REDRAFT_KEY}:{here['channel']}:{here['chat']}", '', 'assistant')
            on = _item_for(store, act.get('key') or '', item)
            if not (on or {}).get('mid'): return stuck(store, 'That draft is not in front of you any more - nothing changed.')
            rid = _draft(store, on, 'redraft', act.get('how') or '')
            if not rid: return stuck(store, 'I could not rewrite that draft here - the one you had is still waiting.')
            return turn_text(_draft_card(store, rid, actor), store=store)
        if t == 'trust': return _trust(store, int(act['tid']), act.get('key') or f"task:{int(act['tid'])}", actor)
        if t == 'walk': return walk(store, actor, opener=not act.get('opened'))
        if t == 'script': return script_words(store, act.get('script') or '')
        if t == 'remind': return _remind(store, act, actor)
        if t == 'continue': return _continue(store, act.get('tid'), act.get('note') or '')
        if t == 'retry':
            # the same confirmation again, once more - an act that failed stays `error` and may run again (claim_operation)
            op = operations.get(store, act.get('id') or '')
            if not op or op.get('status') != 'error': return 'That one is not waiting to be tried again - nothing moved.'
            # ...and a retry that lands settles the table the way the first press would have
            prop = {**op, 'settles': bool(act.get('settles')), 'key': (item or {}).get('key')}
            return _ran(store, prop, _run(store, op, actor), item, actor)
        # a report-back's picks (asks.phone_text): send exactly what was shown, or let one email go
        if t == 'send': return asks.send_picked(store, [[act.get('rid'), act.get('sig')]])
        if t == 'sendall': return asks.send_picked(store, act.get('sends') or [])
        if t == 'drop':
            from . import slots
            slots.drop(store, int(act['tid']), str(act.get('slot') or ''), actor)
            return 'Dropped - that email will not go.'
        if t == 'closeout':
            from fastapi import HTTPException
            from .server import closeout_act
            try: return f"{closeout_act(int(act['rid']), str(act['act']))['said']}. Press {buttons.label('approve', 'action')} again once the checks pass."
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
            return _ran(store, prop, _run(store, op, actor), item, actor)
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
            # the desktop's box says the same one word (buttons.json) - "Continue as is" was a second name for Continue
            go = buttons.label('continue')
            rows = [(go, {'t': 'continue', 'tid': on.get('tid')}), ('Cancel', {'t': 'stay', 'key': key})]
            return turn_text({'say': f"{go} on {on.get('ref') or 'it'}? Type what to tell it as it picks up, or tap {go}.",
                              'item': None}, store=store, extra=rows)
        if verb == 'defer':
            # Remind me asks for the day, as the desktop's picker does; a day typed instead goes to the model's task.defer
            # ...an Advisor idea's own day, the desktop's picker on the idea (C5, 2026-09-27)
            aim = {'idea': on['idea']} if on.get('kind') == 'idea' and on.get('idea') else {'tid': on.get('tid')}
            rows = [(label, {'t': 'remind', **aim, 'until': until}) for label, until in REMIND_DAYS]
            return turn_text({'say': f"Remind you about {on.get('ref') or on.get('title') or 'this'} when? Or say a day.", 'item': None},
                             store=store, extra=rows + [('Cancel', {'t': 'stay', 'key': key})])
        if verb == 'answer_agent':
            return f"What should I tell {on.get('agent') or 'it'}? Say it here and I will pass it straight to the run that is waiting."
        if verb == 'redraft' and on.get('mid') and (on.get('rid') or _draft_text(store, on)):
            # REDRAFT ASKS WHAT TO CHANGE (A18, 2026-10-22): it rewrote at once with no instruction. The next typed line is the instruction
            here = asking() or {}
            if here.get('chat'): store.set_setting(f"{REDRAFT_KEY}:{here['channel']}:{here['chat']}", key, 'assistant')
            rows = [('Shorter', {'t': 'redraft', 'key': key, 'how': 'Make it shorter.'}), ('Just rewrite', {'t': 'redraft', 'key': key, 'how': ''}),
                    ('Cancel', {'t': 'stay', 'key': key})]
            return turn_text({'say': 'What should change? Type it - "warmer", "say we pay on Friday" - or pick one.', 'item': None},
                             store=store, extra=rows)
        if verb in ('reply', 'redraft') and on.get('mid'):
            rid = _draft(store, on, verb, '')
            if not rid: return stuck(store, 'I could not write that draft here - it is waiting on the task page.')
            return turn_text(_draft_card(store, rid, actor), store=store)
        moved = _draft_moved(store, act, on)
        if moved: return moved
        prop = concierge.propose_direct(store, verb, key, actor=actor, table=bool(item and item.get('key') == key))
        return _settle(store, prop, item, actor)
    except ValueError as e: return stuck(store, f'Not done - {e}. Nothing moved.')
    except Exception as e:
        # anything else a pick can hit (a remind, a continue, the funnel under a surface) - said plainly, with the way on,
        # never the raw exception (it went out as "I couldn't answer that: <traceback line>")
        logger.warning(f'phone pick {t or act.get("verb")} failed: {e}')
        return stuck(store, f'Not done - {plain(e)}. Nothing moved.')


def _trust(store, tid: int, key: str, actor: str) -> str:
    """Trust them, from the phone: the task page's own vouch (server.task_trust - origin.raise_to), which lifts the hold. The card comes
    back with its ordinary choices - Send to agent among them now - and nothing has started."""
    from fastapi import HTTPException
    from . import concierge, server
    from .ingest import HOLD_TAG
    try: server.task_trust(tid)
    except HTTPException as e: return stuck(store, f'Not done - {e.detail}. Nothing moved.')
    if store.task_has_tag(tid, HOLD_TAG): store.tag_task(tid, HOLD_TAG, on=False, actor=actor)     # the vouch is the release (release_task)
    from .store import task_ref
    back = concierge.surface(store, key, actor=actor)
    said = f'Trusted - {task_ref(tid)} is no longer held, and nothing has started on it.'
    return turn_text(back, said, store=store) if back.get('item') else stuck(store, said)


NOTE_KEY = 'remote_continue_note'         # a Continue pick waiting for its note: the next typed line is it
REDRAFT_KEY = 'remote_redraft'            # a Redraft pick waiting for what to change: the next typed line is it (A18)


def _continue(store, tid, note: str) -> str:
    """Continue, from the phone: the same road as the desktop's pill (server.continue_work)."""
    from .server import ContinueBody, continue_work
    from fastapi import HTTPException
    try: continue_work(int(tid), ContinueBody(note=note or None))
    except HTTPException as e: return stuck(store, f'Could not continue it - {e.detail}.')
    ref = f'TQ-{int(tid):04d}'
    from . import concierge
    said = f'Continuing {ref}' + (' with your note' if note else '') + ' - it picks up where it left off.'
    said += f' {PROMISE_LINE}' if promise(store, tid) else ''
    return turn_text({'say': said, 'item': None}, store=store, extra=[(concierge.CHIP_WORDS['next'], {'t': 'next'})])


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
    said = concierge.away_line(out)
    if not out.get('remindAt'):
        # "It is back on your rail now." - and the card in front of you keeps its choices under it, never a dead end (F19)
        from . import general
        try: table = concierge.restore_current(store, general.dock_task(store, actor)[0]['TaskId'])
        except Exception: table = None
        if not table: return stuck(store, said)
        return turn_text({'say': said, 'chips': concierge.chips_for(store, table)}, store=store, table=table)
    # ...in plain past tense, the task by name: "TQ-0001 is away until Thu 22 Oct." (F13)
    from .store import task_ref
    said = f"{task_ref(int(act['tid']))} is away until {out['when']}." + (f" {out['warn']}" if out.get('warn') else '')
    # ...and no "Bring it back now" under the NEXT task's card: an undo for a different task, which the owner does not want (A15, 2026-10-22)
    return _on(store, actor, [said], done_with=(asking_key(store) or None))


def _draft_card(store, rid, actor: str = 'owner') -> dict:
    """The draft just written, brought up. Under canonical processing reads a review is found only once membership has been
    reconciled, which the background does a moment later: the phone answered "I can't find that one" over the draft it had
    just written (F4). The row is reconciled first when it is not there yet - the same recovery funnel.settle uses."""
    from . import concierge, funnel
    key = f'review:{rid}'
    if getattr(store, 'processing_reads_active', lambda: False)() and not funnel.next_item(store, key, include_surfaced=True):
        try:
            from . import processing_all
            processing_all.wait_settled(store)
            store.reconcile_processing_membership(); funnel.invalidate()
        except Exception as e: logger.debug(f'the phone could not reconcile the new draft: {e}')
    return concierge.surface(store, key, actor=actor)


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
    # ...and told apart by WHO sent it where the lines alike can be (F26): "(2)" said nothing about which one it was
    from . import concierge
    lines = [line for _k, line in rows]
    # ...and where neither the sender nor the age tells them apart - the same notice from the same sender in the same minute - which of
    # how many it is: "(just now)" and "(just now) (2)" said nothing about either (the 2026-10-22 re-walk)
    members = list(item.get('items') or [])
    by = lambda m: ' '.join(str(m.get('email') or m.get('from') or '').split())
    tellers = (by, concierge.funnel_age)
    def tell(i, m, line):
        alike = [j for j, x in enumerate(lines) if x == line]
        if len(alike) < 2: return line
        for f in tellers:
            v = f(m)
            if v and sum(1 for j in alike if f(members[j]) == v) == 1: return f'{line} ({v})'
        return f'{line} ({alike.index(i) + 1} of {len(alike)})'
    told = [(k, tell(i, m, line)) for i, ((k, line), m) in enumerate(zip(rows, members))]
    seen = collections.Counter()
    def _nth(line): seen[line] += 1; return line if seen[line] == 1 else f'{line} ({seen[line]})'
    return [(k, _nth(line)) for k, line in told]


def fyi_total(store, item: dict | None) -> int:
    """Every FYI the rail holds with this batch counted in - its members are read by being shown, so the pile alone has dropped them."""
    if store is None or (item or {}).get('kind') != 'fyis': return 0
    from . import funnel
    try: rows = funnel.pile(store).get('items') or []
    except Exception as e:
        logger.debug(f'the phone could not count the FYI: {e}'); return 0
    keys = {i['key'] for i in rows if i.get('key') and not i.get('settling') and group_of(i) == 'fyi' and i.get('kind') != 'fyis'}
    return len(keys | {m.get('key') for m in item.get('items') or [] if m.get('key')})


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
    """"Email context · 2 messages in this thread" - the card says how much of the thread is behind
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
    return f'{ch} context · {n} messages in this thread'


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
    # ...and one of the task's emails (slots.py) says who it goes to - a yes on the phone must show what it sends, and where
    if rv.get('Kind') == 'slot':
        try: to = ', '.join((json.loads(rv.get('Deliver') or '{}') or {}).get('to') or [])
        except (TypeError, ValueError): to = ''
        return (f'To {to}:\n' if to else '') + str(rv.get('DraftText') or '').strip()
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


def more_text(store, item: dict | None, limit: int = None) -> str:
    """What the card folds - the phone's More. Under a draft, what they wrote; under a report, every
    section after the first; under a long message, the whole of it. '' when nothing is folded.
    `limit`: one bubble on the channel it goes to (page_chars)."""
    if not item: return ''
    if item.get('kind') == 'agentdone' and item.get('tid'):
        # what the agent FOUND, in full - the card's line is its summary, and it asks "want to see the final report?"
        rep = next((c['Body'] for c in reversed(store.list_comments(int(item['tid'])) or [])
                    if str(c.get('Body') or '').startswith(('AGENT REPORT', 'CODER REPORT', 'The agent closed this itself'))), '')
        return rep.split('\n', 1)[-1].strip() if rep.startswith(('AGENT REPORT', 'CODER REPORT')) else rep
    msg, body, is_report = _body(store, item)
    if not body: return ''
    if is_report:
        from . import chatformat
        rest = chatformat.blocks(body)[1:]
        return chatformat.BREAK + chatformat.BREAK.join(rest) if rest else ''
    if _draft_text(store, item) or len(_plain(body)) > EXCERPT:
        from . import chatformat
        head = '\n'.join(x for x in (thread_line(store, msg), 'THEY WROTE') if x)
        # ...a long one in bubbles of a few paragraphs each, never one wall cut wherever the chat's limit fell (F17)
        return head + '\n' + chatformat.BREAK.join(_quote(p) for p in pages(_plain(body), limit or PAGE_CHARS, head=len(head) + 1))
    return ''


PAGE_CHARS = 1200                              # one More bubble on WhatsApp, whose client folds a long one behind Read more


def page_chars(channel: str) -> int:
    """One More bubble: on Telegram as much as one message holds - six bubbles of 1,200 there were five breaks too many."""
    from . import chatformat
    return chatformat.HARD if channel == 'telegram' else PAGE_CHARS


_SENTENCE = re.compile(r'(?<=[.!?])\s+(?=\S)')


def pages(text: str, limit: int = PAGE_CHARS, head: int = 0) -> list:
    """A long message as as few bubbles as fit `limit` once quoted, broken between paragraphs, else between sentences - a word
    break only inside one sentence longer than a bubble. Each bubble is filled before the next starts: the first was a lone
    "Hi Alex," and the rest were cut every 1,200 characters mid-sentence (the 2026-10-22 re-walk). `head`: what the first
    bubble already carries above the quote."""
    from . import chatformat
    fits = lambda t: len(_quote(t)) <= limit - head
    bits = []                                    # (what goes before it, its words)
    for para in [p.strip() for p in re.split(r'\n\s*\n', str(text or '')) if p.strip()]:
        for j, sent in enumerate([para] if fits(para) else _SENTENCE.split(para)):
            for k, piece in enumerate([sent] if fits(sent) else chatformat.split(sent, max(1, limit - head - 40))):
                bits.append(('\n\n' if j == k == 0 else ' ', piece))
    out, cur, room = [], '', limit - head
    for sep, piece in bits:
        if cur and len(_quote(cur + sep + piece)) > room: out.append(cur); cur, room = piece, limit
        else: cur = cur + sep + piece if cur else piece
    if cur: out.append(cur)
    return out


# what the first word does, said before it is pressed - the desktop card's "then" line. Keyed on the
# vocabulary's verbs (concierge.CHIPS), so a word the table does not name simply says nothing.
THEN = {'approve': f"sends the draft above, in your name - the task stays open until you {buttons.label('close')}.",
        'answer_agent': 'goes straight to the agent; it picks up where it stopped.',
        'reply': 'writes a draft for you to approve here - nothing is sent.',
        'regular_agent': 'hands it to an agent - you can change which one before it starts.',
        'coding_agent': 'starts a coding agent on it; it comes back here when it stops.',
        'mine': 'puts it on your own list - no agent starts.',
        'stop_agent': 'saves what the agent did and stops it; the task stays open.',
        'close': 'ends the task - it stops coming back.'}
# an action card's Send is "Run it": it runs what the card shows, it sends no mail
THEN_KIND = {('approve', 'action'): 'runs what the card above shows, and only that.'}


# words that put a thing DOWN rather than do it: never the card's verb while a real one is offered
_DOWN = ('close', 'not_ours', 'not_ours_sender', 'block_sender', 'done')


# the words that answer "who should take it?" - the move of a task nobody is on (move_title)
_HAND = ('regular_agent', 'coding_agent')


HOLD_LINE = 'New sender - not on your domain, and you have never written to them. Nothing starts until you choose.'
TRUST = 'Trust them'                          # the task page's own word for vouching for a stranger (strangerLine.js -> task.trust)
TRUST_QUESTION = 'do you know this sender?'


def stranger_held(store, item: dict | None) -> bool:
    """A first message from an address nobody here knows: its task wears ingest.HOLD_TAG and nothing starts on it by itself."""
    it = item or {}
    if it.get('hold') is not None: return bool(it['hold'])
    if store is None or not str(it.get('tid') or '').isdigit(): return False
    from .ingest import HOLD_TAG
    try: return store.task_has_tag(int(it['tid']), HOLD_TAG)
    except Exception: return False


def primary(out: dict) -> dict | None:
    """The card's verb: the first word that DOES the thing - a reply with no draft yet leads with
    drafting it, not with closing the task (the vocabulary lists close first for a waiting draft).
    ...and the move's own verb where the card names one: "who should take it?" is answered by handing it over,
    never by a reply (the desktop's button there is Hand to agent, 2026-09-28)."""
    chips = [c for c in (out.get('chips') or []) if isinstance(c, dict) and c.get('verb') and c.get('verb') != 'next']
    it = out.get('item') or {}
    # ...but never on a stranger's held mail: handing a prompt from an unknown address to an agent is not the first thing to do (F8)
    if it.get('hold'):
        mine = [c for c in chips if c['verb'] not in _HAND]
        return next((c for c in mine if c['verb'] not in _DOWN), (mine or chips or [None])[0])
    if it.get('kind') in STORY_KINDS and move_title(it) in ('who should take it?', buttons.label('regular_agent')):
        hand = next((c for c in chips if c['verb'] in _HAND), None)
        if hand: return hand
    return next((c for c in chips if c['verb'] not in _DOWN), chips[0] if chips else None)


def then_line(out: dict, store=None) -> str:
    """"Send the reply: sends the draft above, in your name." - only on a card that shows what it is about."""
    c = next((x for x in out.get('chips') or [] if isinstance(x, dict) and out.get('first') and x.get('verb') == out['first']), None) or primary(out)
    # ...and only under a CARD: under the model's own answer ("Yes to what?") it read as a hint about nothing on screen (F12)
    if store is None or not c or not out.get('item') or agent_answers(out.get('item')) or out.get('proposal'): return ''
    if out['item'].get('kind') in _LEADS_WITH_NEXT: return ''        # nothing to decide: no verb leads, so none is explained (A8, A9)
    if out.get('lead_verb') == 'try_again': return f"{buttons.label('try_again')}: starts the agent again from where it stopped."
    if out.get('lead_verb') == 'close': return f"{buttons.label('close')}: {THEN['close']}"
    if out['item'].get('hold') and out['item'].get('kind') not in ('review', 'action', 'agent'):
        return f"{TRUST}: you vouch for this sender - then {buttons.label('regular_agent')} is offered. Nothing starts by itself."
    it = out.get('item') or {}
    if c['verb'] == 'approve' and str(it.get('channel') or '').lower() == 'teams' and not it.get('closeout'): return ''   # it does not send (F20)
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
    if summary_rows(summary): return ''                    # rows are no sentence: story_block lays them out as a table
    first = _sentences(summary)[0] if summary else ''
    return first if first and first.lower() not in (say or '').lower() else ''


_SALUTE = re.compile(r'^(?:hi|hello|hey|dear|good (?:morning|afternoon|evening))\b[^,.!?\n]{0,40}[,!]\s*', re.I)
_NUMBER = re.compile(r'^(?:\d{1,2}|[a-z])[.)]$|^[-*•]$', re.I)


def _sentences(text: str) -> list:
    """A summary's sentences, without what only LOOKS like one: a salutation ("Hi Alex,") or a list's own number ("1.") led the card
    as its whole summary line (F17)."""
    out = []
    for p in re.split(r'(?<=[.!?])\s+|\n+', str(text or '')):
        p = _SALUTE.sub('', p.strip()).strip()
        if p and not _NUMBER.match(p): out.append(p)
    return out or ['']


# THE CARD'S STORY, ON THE PHONE (the owner, 2026-09-28: the desktop's "the story is quiet, your move is loud", and "same
# for whatsapp"): who asked and what the agent did as plain lines, then one bold YOUR MOVE with the thing to decide under
# it. WhatsApp has no frame and no colour - a rule and the one bold header are the only loud things it allows. The words
# match assistantCards.jsx Story / YourMove, so the two surfaces say the same card.
STORY_KINDS = {'review', 'action', 'agent', 'agentdone', 'todo', 'message', 'asked', 'fyi', 'wrapup', 'task'}
_CHANNEL_WORDS = {'email': 'Email', 'github': 'GitHub', 'whatsapp': 'WhatsApp', 'teams': 'Teams', 'slack': 'Slack', 'telegram': 'Telegram',
                  'sms': 'Text', 'discord': 'Discord', 'google_chat': 'Google Chat', 'assistant': 'Advisor', 'gitlab': 'GitLab'}
_VIA = {'whatsapp': 'on WhatsApp', 'teams': 'in Teams', 'slack': 'in Slack', 'telegram': 'on Telegram', 'sms': 'by text',
        'github': 'on GitHub', 'discord': 'on Discord', 'google_chat': 'in Google Chat'}
# a profile whose name only repeats the kind, the CLI or the word agent says nothing the label does not already say
_PLAIN_PROFILE = {'coding', 'claude', 'codex', 'agent', 'assistant', 'general', 'regular', 'the agent', ''}
RULE = '──────────'
# THE TASK PAGE'S THREE COLOURS, as a chat can wear them (the owner, 2026-09-28: "make sure whatsapp/telegram matches
# this new color scheme"): 1 the task in slate, 2 the agent in sage, 3 you in tan - the card's avatars, as dots
DOT_TASK, DOT_AGENT, DOT_YOU = '🔵', '🟢', '🟤'


def _advisor(store, item: dict | None) -> bool:
    """A task made from an Advisor idea: the Advisor asked, never the owner."""
    it = item or {}
    if store is None or not it.get('tid'): return str(it.get('channel') or '') == 'assistant'
    try: t = store.get_task(int(it['tid'])) or {}
    except Exception: return False
    # ...never one the OWNER asked for: a job started from the chat carries the Assistant's Source too, and read "Advisor
    # raised an idea" over what the owner had just asked for on WhatsApp (2026-10-06)
    if t.get('AskedVia') or str(t.get('CreatedBy') or '') == 'owner': return False
    return str(it.get('channel') or '') == 'assistant' or str(t.get('Source') or '') == 'assistant' or str(t.get('SourceRef') or '').startswith('assistant:')


def channel_word(ch) -> str:
    k = str(ch or '').lower()
    return _CHANNEL_WORDS.get(k) or k.replace('_', ' ').title()


def _general(store, it: dict) -> bool:
    """A general agent's task - read off the task, because a headless or saved general run carries no session `mode` (F6)."""
    if store is None or not it.get('tid'): return False
    try: return str((store.get_task(int(it['tid'])) or {}).get('Kind') or '').lower() == 'general'
    except Exception: return False


def agent_label(item: dict | None, name: str = None, store=None) -> str:
    """What an agent IS - never the profile's bare name ("coding"); the profile only when it says more."""
    it = item or {}
    p = str(name or it.get('working') or it.get('agent') or '').strip()
    kind = 'General agent' if str(it.get('mode') or '') in ('chat', 'assistant') or p.lower() == 'assistant' or _general(store, it) else 'Coding agent'
    return f'{kind} · {p}' if p.lower() not in _PLAIN_PROFILE else kind


def asker(store, it: dict) -> str:
    """Who asked for the work behind an agent's card - the person on the task's mail - '' when nobody did (own work, a report).
    The card's `who` is the AGENT there, and the move read "Reply to claude with what it found" (F6)."""
    if store is None or is_own(it): return ''
    try:
        msg = store.get_message(int(it['mid'])) if it.get('mid') else None
        if not msg and it.get('tid'): msg = next((m for m in store.list_messages(int(it['tid'])) or [] if m.get('Status') != 'context'), None)
    except Exception: msg = None
    if not msg or str(msg.get('Channel') or '') in ('report', 'assistant', 'own'): return ''
    return story_who({'who': msg.get('FromName') or msg.get('FromEmail') or ''}) if (msg.get('FromName') or msg.get('FromEmail')) else ''


def last_result(store, tid, n: int = 600) -> str:
    """A regular agent's answer: its newest finished turn (worker_event turn_end), plain and cut - '' when it has none."""
    if store is None or not tid: return ''
    try:
        row = store._one("SELECT Text FROM worker_event WHERE TaskId=? AND Kind='turn_end' AND IFNULL(Text,'')<>'' ORDER BY Id DESC LIMIT 1", (int(tid),))
    except Exception as e:
        logger.debug(f'the phone could not read the agent result: {e}'); return ''
    return _cut(_plain(str((row or {}).get('Text') or '')), n)


def agent_report(store, tid) -> dict:
    """The report an agent files (wrapup.py): Summary = what it found, Actions = what it did, Determination = its verdict."""
    if store is None or not tid: return {}
    try: rep = next((str(c.get('Body') or '') for c in reversed(store.list_comments(int(tid)) or [])
                     if str(c.get('Body') or '').startswith(('AGENT REPORT', 'CODER REPORT', 'HANDOVER NOTE'))), '')
    except Exception as e:
        logger.debug(f'the phone could not read the agent report: {e}')
        return {}
    body = re.split(r'\n\s*LAST MESSAGE\s*\n', rep)[0]
    field = lambda k: ((re.search(rf'(?im)^\s*{k}:\s*(.+)$', body) or [None, ''])[1] or '').strip()
    return {'summary': field('Summary'), 'actions': field('Actions'), 'verdict': field('Determination')} if rep else {}


def _says(sub: str) -> str:
    """lanes.json's sentence for a blocked agent's sub-state (workerstate.says), without the agent: the card's line names it."""
    from . import workerstate as ws
    return ws.says(sub, '\x00').replace('\x00', '').strip()


def agent_state(item: dict | None, store=None) -> str:
    """The agent's state in the rail's own words. A run that ended by its OWN word says so - "failed - <why>" (owner-approved R2,
    2026-10-21) or finished - and "is waiting on you" is said only of a run that is: a failed run read "is waiting on you" (F5)."""
    it = item or {}
    kind, lane = it.get('kind'), it.get('lane')
    # ...and a task whose agent ENDED, whatever its row became: a finished run on a task the rail shows as yours read "No agent yet" (A2)
    if store is not None and it.get('tid') and lane != 'working' and (kind in ('agent', 'agentdone') or lane in AGENT_CARD_LANES or kind in _TASKISH):
        from . import funnel, workerstate as ws
        # ...FAILED whatever the session does, as the desk's R2 reads it: a run that failed with its session still open read "is waiting
        # on you" (the 2026-10-22 re-walk) - finished stays a reading of a run that is over
        try: end = 'failed' if ws.ended(store, int(it['tid']), live_too=True) == 'failed' else ws.ended(store, int(it['tid']))
        except Exception as e:
            logger.debug(f'the phone could not read how the run ended: {e}'); end = None
        if end == 'failed':
            f = funnel.run_failed(store, int(it['tid']), live_too=True) or {}
            why = str(f.get('sentence') or '').rstrip('.')
            return f'failed - {why[:1].lower()}{why[1:]}' if why else 'failed'
        if end == 'finished' and not it.get('asking'): return 'finished'
    if kind == 'agent':
        if lane == 'working': return 'working'
        if it.get('paused'): return 'stopped - its work is saved'
        sub = it.get('state') if it.get('state') in ('asking', 'approval', 'stalled', 'parked') else 'asking' if it.get('asking') else 'parked'
        return _says(sub)
    if kind == 'agentdone': return 'finished'
    # an agent at work on a task whose card is not an agent's: the header said "agent working" over "No agent yet" (F7)
    if held(it): return 'working'
    return {'queued': 'handed over, not started', 'stopped': 'stopped', 'saved': lanes.word('saved')}.get(lane) or ('finished' if it.get('summary') else '')


def held(item: dict | None) -> bool:
    """An agent holds this task right now: its row is in the working lane, or a live session is on it."""
    it = item or {}
    if it.get('lane') == 'working': return True
    if not str(it.get('tid') or '').isdigit(): return False
    from . import terminal
    try: s = terminal.session_for(int(it['tid']))
    except Exception: return False
    return bool(s and getattr(s, 'alive', False))


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
    return '' if summary_rows(summary) else ' '.join(_sentences(summary)[1:]).strip()


ROWS_SHOWN = 12


def summary_rows(text: str) -> str:
    """A summary that is a report's ROWS - one flat JSON object a line, as a report put on the list is summarised - as those lines,
    else ''. Read as sentences, its first row led the card and the rest ran on as one line of braces and quotes (F16, the re-walk)."""
    from . import chatformat
    lines = [l.strip() for l in str(text or '').splitlines() if l.strip()]
    return '\n'.join(lines) if lines and all(chatformat._flat_rows(l) for l in lines) else ''


def _rows_block(store, item: dict | None) -> list:
    """The task's rows as lines the send lays out as a table (chatformat.json_blocks), the first few and how many more."""
    if store is None or not (item or {}).get('tid'): return []
    try: rows = summary_rows((store.get_task(int(item['tid'])) or {}).get('Summary')).splitlines()
    except Exception: return []
    if not rows: return []
    more = len(rows) - ROWS_SHOWN
    return rows[:ROWS_SHOWN] + ([f'…and {more} more {"row" if more == 1 else "rows"} on the task'] if more > 0 else [])


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


def todo_lines(store, tid, cap: int = 6) -> list:
    """A task's to-dos for a chat: "To do · 2 of 5 done", then each open one by its checklist number, with its note under it."""
    if not tid: return []
    try: boxes = store.task_checklist(int(tid))
    except Exception: return []
    todo = [(n, b) for n, b in enumerate(boxes, 1) if not isinstance(b.get('out'), dict)]          # an email a task owes is Close out's
    if not todo: return []
    left = [(n, b) for n, b in todo if not b.get('done')]
    out = [f"**To do** · {sum(1 for _, b in todo if b.get('done'))} of {len(todo)} done"]
    out += [f"{n}. {_cut(b['text'], 140)}" + (f"  _({_cut(b['note'], 140)})_" if b.get('note') else '') for n, b in left[:cap]]
    if len(left) > cap: out.append(f'... and {len(left) - cap} more')
    if left: out.append('Say "tick 2", "note on 2: ..." or "add a to-do: ...".')
    return out


def story_block(store, item: dict | None, draft: str = '', say: str = '', full: bool = False) -> str:
    """The quiet part: a header (state · ref), who asked and what they want, then the agent and its evidence.
    `full`: the owner opened this one to READ it - the whole message, not its opening (full_body)."""
    from . import concierge, funnel
    it = item or {}
    kind, ch = it.get('kind'), str(it.get('channel') or '')
    word = ({'agentdone': lanes.word('agentdone'), 'wrapup': 'reply sent · task still open'}.get(kind)
            or ('your task' if is_own(it) and kind not in ('agent', 'review', 'action') else '')
            or (funnel.LANE_WORDS.get(str(it.get('lane') or '')) or ('',))[0])
    # ...and the header reads the run the body reads: "agent waiting on you" sat over "failed - <why>" (F5)
    state = agent_state(it, store)
    if state.startswith('failed') and kind not in ('agentdone', 'wrapup'): word = funnel.LANE_WORDS['stopped'][0]
    elif state == 'finished' and kind == 'agent': word = lanes.word('agentdone')
    elif state == 'working' and kind != 'agent': word = funnel.LANE_WORDS['working'][0]
    # A STRANGER'S HELD MAIL says it is held, once (F8): it read "waiting to start" and "handed over, not started" over a task
    # nothing will start until the owner chooses - the rail's own `held` state and its word
    hold = stranger_held(store, it) and state != 'working'
    if hold: word, state = lanes.word('held'), ''
    head = ' · '.join(x for x in (word, str(it.get('ref') or '')) if x)
    mark = funnel.mark_for({**it, 'lane': 'stopped'} if state.startswith('failed') and kind == 'agent' else it)
    if head and mark: head = f'{mark} {head}'
    age = concierge.funnel_age(it)
    said = lead_line(store, it, '') or _cut(it.get('title') or '', 160)
    lines = [head] if head else []
    # the asker - the TASK where the card's `who` is not the asker (an agent-finished card carries the agent there)
    agent_is_who = kind == 'agent' and str(it.get('who') or '').strip().lower() in {str(it.get(k) or '').strip().lower() for k in ('agent', 'working')} - {''}
    if _advisor(store, it):
        lines.append(' · '.join(x for x in (f'{DOT_TASK} **Advisor** raised', 'an idea', age) if x))
    elif kind in ('agentdone', 'wrapup') or agent_is_who:
        # the PERSON who asked, when the work has one - "🔵 The task · just now" said nothing the header had not (F6)
        who = asker(store, it)
        if who: lines.append(' · '.join(x for x in (f'{DOT_TASK} **{who}** asked', channel_word(ch) if ch and ch not in ('own', 'report') else '', age) if x))
    elif is_own(it):
        lines.append(' · '.join(x for x in (f'{DOT_TASK} **You**', 'your task', age) if x))
    else:
        verb = 'wrote' if kind == 'fyi' or it.get('lane') in ('fyi', 'report') else 'asked'
        lines.append(' · '.join(x for x in (f'{DOT_TASK} **{story_who(it)}** {verb}', channel_word(ch), age) if x))
    if hold: lines.append(HOLD_LINE)
    if said: lines.append(said[:1].upper() + said[1:])
    # what the thing IS, in its own words - a pull request's title and number, an email's subject - and the rest of the
    # summary: the first sentence says who wants what, never what it is (the owner, 2026-09-28: "at least the title")
    subj = subject_of(store, it)
    if subj and re.sub(r'^(PR |Issue )?#\d+( ·)?\s*', '', subj).lower() not in (said or '').lower() and not _repeats(subj, [said]):
        lines.append(_cut(subj, 280))
    rest = summary_rest(store, it)
    if rest and not _repeats(rest, [said, subj]): lines.append(_cut(rest, 280))
    lines += _rows_block(store, it)
    if not it.get('tid') and say and kind != 'agentdone' and (not said or said.lower() not in say.lower()): lines.append(say)
    # their own words, when nothing of yours answers them yet (a draft puts them behind More)
    whole = full_body(store, it) if full else ''
    if whole: lines += ['', whole]
    elif not draft and kind in ('message', 'asked', 'todo', 'fyi') and not is_own(it):
        msg, body, is_report = _body(store, it)
        opening = _plain(body) if body and not is_report else ''
        # ...ONCE: a short mail is often its own title and summary as well, and the card printed it again under them (F8)
        norm = lambda s: ' '.join(str(s or '').split()).lower().rstrip('.…')
        # ...and a summary that IS the mail, split into its first sentence and the rest, is the mail too: each line alone held only
        # half of it, so a held stranger's two sentences were printed and then quoted whole under them (the 2026-10-22 re-walk)
        shown = [x for x in (said, subj, rest, ' '.join(x for x in (said, rest) if x)) if x]
        if opening and not any(norm(opening) and norm(opening) in norm(x) for x in shown):
            lines.append(_quote(_cut(opening, EXCERPT) if len(opening) > EXCERPT else opening))
    # THE TASK'S TO-DOS (the owner, 2026-10-20: "anything you can do, you can do via the Assistant" - the phone never showed them): the open
    # ones, numbered as task.check takes them, each with its note, and how far the list got; "tick 2" / "note on 2: ..." answer them
    todo = todo_lines(store, it.get('tid'))
    if todo: lines += [''] + todo
    # the agent: its state and what it found, did and concluded - the evidence the move is decided on
    rep = agent_report(store, it.get('tid'))
    found = rep.get('summary') or ' '.join(str(it.get('summary') or '').split())
    # ...and a regular agent files no report: what it RETURNED is its last finished turn. The phone showed only its
    # follow-up question, never the answer above it (2026-10-06: "in whatsapp you just see the question")
    if not found and (kind == 'agent' or state == 'finished'): found = last_result(store, it.get('tid'))
    # ...a finished agent with no summary on the card: the assistant's own line says what it found
    if not found and kind == 'agentdone' and say: found = say
    if found or state:
        lines.append('')
        lines.append(f"{DOT_AGENT} **{agent_label(it, it.get('who') if kind == 'agentdone' else None, store)}**" + (f' · {state}' if state else ''))
        if found: lines.append(_cut(found, 400))
        if rep.get('actions'): lines.append(f"did: {_cut(rep['actions'], 300)}")
        if rep.get('verdict'): lines.append(f"verdict: {_cut(rep['verdict'], 300)}")
        # what the AGENT asks is the agent's line, not the owner's: it sat under "You · answer the agent" (2026-10-06)
        asked = ' '.join(str((it.get('tail') or [''])[0]).split()) if kind == 'agent' and it.get('asking') and len(it.get('questions') or []) <= 1 else ''
        if asked: lines.append(f'asks: **{_cut(asked, 600)}**')
    elif it.get('tid') and kind in ('todo', 'message', 'asked') and (kind == 'todo' or is_own(it)) and not hold:
        lines += ['', f'{DOT_AGENT} No agent yet - nobody is working on this.']
    return '\n'.join(lines).strip()


TEAMS_DRAFT = f"Teams replies can't be sent from here - copy it into Teams, then {buttons.label('close')}:"


def move_block(store, item: dict | None, draft: str = '') -> str:
    """The loud part: a rule, **YOUR MOVE · <what>**, and what to decide on - your reply, its question, why it waits."""
    it = item or {}
    title = move_title({**it, 'who': asker(store, it) or it.get('who')} if it.get('kind') == 'agentdone' else it, draft)
    # ...a stranger's held work asks the one thing that comes first: is the sender real (A3) - "who should take it?" over no hand-off
    if title in (buttons.label('regular_agent'), 'who should take it?') and stranger_held(store, it): title = TRUST_QUESTION
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
        # the question itself is on the agent's own line (story_block): here only what the owner does about it
        # "goes straight in" only where it does: an agent ASKING takes typed words as its answer (answer_the_agent)
        body.append(('Pick an answer below, or type your own - it goes straight in.' if it.get('choices')
                     else 'Type your answer - it goes straight in.') if it.get('asking')
                    else 'Pick below, or tell me what to do with it.')
    elif draft:
        ch = str(it.get('channel') or '').lower()
        via = _VIA.get(ch, 'by email')
        # a Teams reply cannot go from here - Microsoft lets only the owner's own sign-in post one (outbound) - so it does not say it goes (F20)
        if ch == 'teams' and not is_own(it): body.append(f"Your reply to {story_who(it)} - {TEAMS_DRAFT}")
        else: body.append('Your draft - it goes when you send it:' if is_own(it) else f'Your reply to {story_who(it)} {via} - it goes when you send it:')
        body.append(_quote(draft))
    elif it.get('lane') == 'queued' and (it.get('why_idle') or it.get('why')) and not stranger_held(store, it):
        body.append(f"Why it has not started: {' '.join(str(it.get('why_idle') or it['why']).split())}")
    elif it.get('kind') == 'wrapup' and it.get('sent'):
        body.append(f"You sent: {_cut(it['sent'], 300)}")
    # "👉 You · start it" - the thread's last step, in the words every step uses; the rule is the one loud thing
    return '\n'.join([RULE, f'{DOT_YOU} **You** · {title}'] + body)


def script_words(store, script: str) -> str:
    """A script, as a chat can hold it: the composer asks for the sentence it builds from. Setting Taskuary up is the desk's Setup
    button, never a script here (the owner, 2026-10-19) - an old pick of it says where it is."""
    if 'report' in str(script or '').lower():
        # ...with one sentence to copy the shape of: the bare ask left the owner guessing what a sentence like that is (F25)
        return ('Tell me what to set up - a check that reads, or a workflow that writes - in a sentence, and I put it together. '
                'For example: "Every weekday at 8, list the invoices more than 30 days overdue and send them to me here."')
    return 'Setting Taskuary up is the Setup button at the top of Taskuary on your computer.'


_ROAMING = ('next', 'open')                   # chips that run with no item behind them
GOT_IT = 'Got it'                             # an FYI's Next: read, and on to the next (A8)
_LEADS_WITH_NEXT = ('fyi', 'fyis', 'report')   # cards with nothing to decide: the way on comes first, and no "then" line


def _fix_pick(fix: dict | None) -> tuple | None:
    """A failure's fix as a phone pick: a Connections section it names opens as the phone's own browse of it (doorway_browse) - the
    page's link, which a chat cannot follow. None where the fix is a place the phone has no list of."""
    from urllib.parse import unquote
    m = re.match(r'^#connections=(.+)$', str((fix or {}).get('href') or ''))
    return (fix['label'], {'t': 'browse', 'area': 'connections', 'section': unquote(m.group(1))}) if m and fix.get('label') else None


def _after_the_run(store, out: dict, item: dict) -> tuple[dict, list]:
    """R2 ON THE PHONE (A2, 2026-10-22), as the desk reads a run that is over: a FAILED agent leads with Try again - the same road as
    Continue - and with Connect an AI when no AI is why; a FINISHED one leads with Mark done. The phone offered Stop and save, Next and
    Remind me under both. Returns (the turn, the labels that lead)."""
    from . import concierge
    tid = item.get('tid')
    if store is None or not str(tid or '').isdigit() or item.get('kind') not in ('agent', *_TASKISH): return out, []
    if held(item) and item.get('kind') != 'agent': return out, []
    state = agent_state(item, store)
    have = {c.get('verb'): c['label'] for c in out.get('chips') or [] if isinstance(c, dict) and c.get('verb')}
    if state.startswith('failed'):
        go = buttons.label('try_again')
        out = _recast(out, drop={'continue'})          # the desk's Continue, which asks for a note first: one tap here runs it
        _offer([(go, {'t': 'continue', 'tid': int(tid)})])
        from . import funnel
        fix = _fix_pick((funnel.run_failed(store, int(tid), live_too=True) or {}).get('fix'))
        if fix: _offer([fix])
        return {**out, 'lead_verb': 'try_again'}, [go] + ([fix[0]] if fix else [])
    if state == 'finished':
        done = have.get('close') or concierge.CHIP_WORDS['close']
        if 'close' not in have: _offer([(done, {'t': 'close', 'tid': int(tid)})])
        return {**out, 'lead_verb': 'close'}, [done]
    return out, []


def _recast(out: dict, drop=(), relabel: dict = None) -> dict:
    """The turn with the chips of `drop` (verbs) gone and `relabel` ({verb: label}) said in the phone's own words - its options too."""
    from . import concierge
    relabel = relabel or {}
    gone = {concierge.CHIP_WORDS[v] for v in drop if v in concierge.CHIP_WORDS}
    words = {concierge.CHIP_WORDS[v]: w for v, w in relabel.items() if v in concierge.CHIP_WORDS}
    chips = [({**c, 'label': relabel[c['verb']]} if isinstance(c, dict) and c.get('verb') in relabel else c)
             for c in out.get('chips') or [] if not (isinstance(c, dict) and c.get('verb') in drop)]
    return {**out, 'chips': chips, 'options': [words.get(str(o), o) for o in out.get('options') or [] if str(o) not in gone]}


def _chips_on(store, out: dict, item: dict, table: dict | None) -> tuple[dict, str]:
    """(the turn, the key its verb chips act on). A typed answer carries no item, and its chips - the table's own, drawn under the
    words - were numbered with nothing to run them on: the tap fell through to the model as words (F2). They act on the TABLE when
    they are the table's chips; a verb chip that has nothing to act on is not drawn at all."""
    key = item.get('key') or ''
    if item: return out, key
    verbs = [c['verb'] for c in out.get('chips') or [] if isinstance(c, dict) and c.get('verb') and c['verb'] not in _ROAMING]
    if verbs and (table or {}).get('key') and store is not None:
        from . import concierge
        try: own = {c.get('verb') for c in concierge.chips_for(store, table) or []}
        except Exception as e:
            logger.debug(f'the phone could not read the table chips: {e}'); own = set()
        if all(v in own for v in verbs): key = table['key']
    if key or not verbs: return out, key
    return {**out, 'chips': [c for c in out['chips'] if not (isinstance(c, dict) and c.get('verb') and c['verb'] not in _ROAMING)]}, key


def turn_text(out: dict, lead: str = '', store=None, extra: list = None, full: bool = False, table: dict = None) -> str:
    """One turn as one message: where it came from, what was said, then what can be said back.

    The options used to ride one line joined by dots, which read as a single run-on sentence on a
    phone (the owner, 2026-09-10: "reply with should make it more clear they are separate"). Each owns
    a line now, and carries the number that answers it - see resolve_index for why that number works.

    `store` is what lets the turn SHOW what it is asking about (decision_block). It is optional only
    so a caller with nothing to look up still gets its words.
    """
    from . import funnel
    item = out.get('item') or {}
    # A RUN THAT FAILED ASKS NOTHING, though its session is still up and its last question still on the row: the card read "answer the
    # agent" and offered its old answers over "failed - <why>" (R2)
    if item.get('kind') == 'agent' and item.get('asking') and agent_state(item, store).startswith('failed'):
        item = {**item, 'asking': False, 'choices': [], 'questions': [], 'state': 'parked'}; out = {**out, 'item': item}
    out, key = _chips_on(store, out, item, table)
    if item and 'hold' not in item and stranger_held(store, item): item = {**item, 'hold': True}; out = {**out, 'item': item}
    # A STRANGER'S HELD WORK IS NOT HANDED TO AN AGENT until the owner says the sender is real (A3, 2026-10-22): one tap started work on a
    # new sender's branch. Its choices lead with Trust them - the task page's own vouch - and Not ours
    trusting = bool(item.get('hold') and str(item.get('tid') or '').isdigit() and item.get('kind') not in ('review', 'action', 'agent'))
    if item.get('hold'): out = _recast(out, drop=set(_HAND))
    out, leads = _after_the_run(store, out, item)
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
        # ...and how many of how many: "4 fyi" over a rail holding fourteen read as all of them (F26)
        total = fyi_total(store, item)
        head = '\n'.join([f"{mark} {len(members)}{f' of {total}' if total > len(members) else ''} fyi · nothing to do"]
                         + [f'{i} · {line}' for i, (_k, line) in enumerate(members, 1)])
    if item: head = _placed(head, position(store, item))
    if item and len(item.get('questions') or []) > 1:
        from . import concierge
        out = {**out, 'chips': [c for c in out.get('chips') or [] if not (isinstance(c, dict) and c.get('verb') == 'answer_agent')],
               'options': [o for o in out.get('options') or [] if str(o) != concierge.CHIP_WORDS['answer_agent']]}
    # A NOTICE IS READ AND PASSED (A8, 2026-10-22): an FYI led with Put it on my list, and one tap sent a newsletter to an agent - it leads
    # with Got it (its read-and-next, the batch's All read) and offers no Send to agent. A REPORT needs nothing (A9): it led with Put it on
    # my list, which made it a to-do offering Reply to a report - it leads with Next, and Put it on my list goes
    if item.get('kind') in ('fyi', 'fyis'): out = _recast(out, drop=set(_HAND), relabel={'next': GOT_IT})
    elif item.get('kind') == 'report': out = _recast(out, drop={'mine'})
    if item and is_own(item) and item.get('kind') in STORY_KINDS:
        # work you started has nobody behind it to answer or to file away (the desktop hides the same two)
        from . import concierge
        gone = {concierge.CHIP_WORDS['reply'], concierge.CHIP_WORDS['not_ours']}
        out = {**out, 'chips': [c for c in out.get('chips') or [] if not (isinstance(c, dict) and c.get('verb') in ('reply', 'not_ours'))],
               'options': [o for o in out.get('options') or [] if str(o) not in gone]}
    if item and item.get('kind') != 'agent' and held(item):
        # ...and a task an agent already holds is not handed to another: the server refuses a second start (Continue that session)
        from . import concierge
        hand = {concierge.CHIP_WORDS[v] for v in _HAND}
        out = {**out, 'chips': [c for c in out.get('chips') or [] if not (isinstance(c, dict) and c.get('verb') in _HAND)],
               'options': [o for o in out.get('options') or [] if str(o) not in hand]}
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
                 else {'t': 'next', **_drawn_at(item)} if c.get('verb') == 'next' else {'t': 'open', 'key': c['key']} if c.get('verb') == 'open'
                 else {'t': 'verb', 'verb': c['verb'], 'key': key, **_drawn_at(item or table), **_pinned(store, item or table, c['verb'])})
                for c in out.get('chips') or [] if isinstance(c, dict) and c.get('label')
                and ((c.get('ask') and not c.get('verb')) or (c.get('verb') and (key or c.get('verb') in ('next', 'open'))))])
    # THE CARD'S ORDER: the verb, then Next, then More, then the rest - the desktop's two buttons and its
    # Also line, as one numbered list (2026-09-23). A proposal's yes/no and an agent's own answers keep
    # theirs: those are the answer itself, not a choice of what to do.
    # WHICH WORD IS NEXT is the chip's verb, or the vocabulary's own word - never a label that happens to contain "next"
    # (the owner, 2026-10-11: no word matching decides what a word does)
    from . import concierge as _c
    next_words = {c['label'] for c in out.get('chips') or [] if isinstance(c, dict) and c.get('verb') == 'next'} | {_c.CHIP_WORDS['next'], GOT_IT}
    if not out.get('proposal') and not agent_answers(item):
        nxt = [w for w in words if w in next_words]
        rest = [w for w in words if w not in nxt]
        # ...the button a typed act asked for, when one was brought up for it (A6), else the card's own verb
        lead_word = next((c['label'] for c in out.get('chips') or [] if isinstance(c, dict) and out.get('first') and c.get('verb') == out['first']), None) \
            or (primary(out) or {}).get('label')
        first_ = [] if item.get('kind') in _LEADS_WITH_NEXT else [w for w in rest if w == lead_word][:1] or rest[:1]
        # ...and the draft's own other word rides with it, ahead of Next - the screen draws Redraft beside the send, under the draft
        # (the owner, 2026-10-06: "on whatsapp" the same order)
        redo = {c['label'] for c in out.get('chips') or [] if isinstance(c, dict) and c.get('verb') == 'redraft'}   # Redraft, or Draft with AI
        first_ += [w for w in rest if w in redo and w not in first_]
        more = [MORE] if store is not None and not (full and story) and more_text(store, item) else []
        words = first_ + nxt + more + [w for w in rest if w not in first_]
        if leads: words = leads + [w for w in words if w not in leads]
        if trusting:
            nope = [w for w in words if w == _c.CHIP_WORDS['not_ours']]
            words = [TRUST] + nope + [w for w in words if w not in nope]
            _offer([(TRUST, {'t': 'trust', 'tid': int(item['tid']), 'key': key})])
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
        if not any(w in next_words for w in words):
            words = words + [GOT_IT]                  # after the members: they are the card, numbered as the text numbers them
            _offer([(GOT_IT, {'t': 'next', **_drawn_at(item)})])
    # ...and what a NUMBER does, said plainly. "Open one" describes a door on a screen that is not
    # here; on a phone the number is the only way to see what the line is actually about.
    # A plain answer with nothing on the table offered "Reply with one of: 1 · Next" under every reply - three
    # lines of menu for the one word the owner can always type (2026-09-24 audit). The desktop's lone Next is
    # one small button; on a phone it is noise.
    # ...but a lone Next is never dropped any more: "walk me through my tasks" answered with three fyi and "Shall we begin
    # with the rejected refund form?" and nothing to tap - stuck (the owner, 2026-10-06: "where are the buttons?? we should
    # never get stuck"). The way on is a pick whenever the pipe still holds something.
    # THE WALK RAN OUT, ON THE PHONE: hand it back from here (the owner, 2026-10-02: "hand back choice at the end of the walk
    # though asking question of assistant will always work") - a pick, the desktop's Take it back; typed words still talk
    if out.get('over') and store is not None and handoff(store): extra = list(extra or []) + [(HAND_BACK, {'t': 'handback'})]
    # ...and the way to start again, first: the end offered only its Opens, and outside a hand-off nothing began a new walk - which shows
    # every open task again from the top (A1, 2026-10-22; next-is-seen-in-this-walk). The summary is the line above it: straight to card 1
    if out.get('over') and store is not None:
        words = [WALK] + [w for w in words if w != WALK]
        _offer([(WALK, {'t': 'walk', 'opened': True})])
    if extra:
        words = words + [label for label, _ in extra]
        _offer(extra)
    words = list(dict.fromkeys(words))         # one Next, never "2 · Next" and "4 · Next" (F14)
    lead_in = ('Reply with a number to read that message in full, or:' if item.get('kind') == 'fyis'
               else 'Reply with a number to open one, or:') if first > 1 else 'Reply with one of:'
    opts = (lead_in + '\n'
            + '\n'.join(f'{i} · {w}' for i, w in enumerate(words, first))) if words else ''
    shown = move_block(store, item, draft) if story else decision_block(store, item) if store is not None else ''
    return _once('\n\n'.join(x for x in (lead.strip(), head, shown, then_line(out, store), opts) if x))


_NOTHING = re.compile(r'(?:\s*[;,]|\s+-)?\s*nothing has to happen\b[.;]?', re.I)


def position(store, item: dict | None) -> str:
    """Where this card is in its rail section - "4 of 19" - so a long walk says how far it has come (A11, 2026-10-22). '' for a card
    the rail does not hold, a section of one, and an FYI batch (it counts itself)."""
    key = (item or {}).get('key')
    if store is None or not key or item.get('kind') == 'fyis': return ''
    from . import funnel
    try: items = [i for i in funnel.pile(store).get('items') or [] if not i.get('settling')]
    except Exception as e:
        logger.debug(f'the phone could not place the card: {e}'); return ''
    me = next((i for i in items if key == i.get('key') or key in (i.get('aliases') or ())), None)
    if not me: return ''
    rows = [i for i in items if group_of(i) == group_of(me)]
    if group_of(me) == 'later': rows = sorted(rows, key=lambda i: str(i.get('back_at') or i.get('defer_until') or '9999'))
    return f'{rows.index(me) + 1} of {len(rows)}' if len(rows) > 1 else ''


def _placed(head: str, pos: str) -> str:
    """The card's first line with its place on the end: "📋 on you · TQ-0004 · 4 of 19"."""
    if not pos or not head: return head
    first, _, rest = head.partition('\n')
    return f'{first} · {pos}' + (f'\n{rest}' if rest else '')


def _once(text: str) -> str:
    """A card says a thing once: a line that repeats one above it goes, and "nothing has to happen" is said the first time only (F16)."""
    seen, out = set(), []
    for line in text.split('\n'):
        k = ' '.join(line.split()).lower()
        if len(k.split()) >= 3 and k in seen and not _OFFERED.match(line): continue
        seen.add(k); out.append(line)
    text = '\n'.join(out)
    m = _NOTHING.search(text)
    return text[:m.end()] + _NOTHING.sub('', text[m.end():]) if m else text


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
    # ...but on TELEGRAM a number picks only a line the message SHOWED numbered: the buttons carry their choices without numbers (F27),
    # and a bare "2" silently ran button 2 (A18, 2026-10-22). A line past the buttons' page is still printed with its number
    if channel == 'telegram' and 1 <= i <= len(words) and words[i - 1] in _tg_buttons(store, chat): return text, False
    return (words[i - 1], True) if 1 <= i <= len(words) else (text, False)


def _tg_buttons(store, chat: str) -> list:
    from . import messengers
    try: return (json.loads(store.get_setting(f'{messengers.TG_BUTTONS}:{chat}') or '{}') or {}).get('labels') or []
    except ValueError: return []


def bare_number(text: str) -> bool: return str(text or '').strip().lstrip('#').rstrip('.').strip().isdigit()


def _chunks(text: str, limit=3900) -> list[str]:
    """Split a long walkthrough where a reader would split it (chatformat.split).

    This used to take max() of the paragraph, line and space positions - and the space is
    always the latest of the three, so it won every time and the break landed mid-sentence:
    '...asked Fri 18 Sep 10:34 re "Northwind and' (the owner, 2026-09-19, with a screenshot)."""
    from . import chatformat
    return chatformat.split(str(text or '').strip(), limit)


def send(store, channel: str, chat: str, text: str, connector_id: int = None, page: int = 0, choices: list = None):
    """Everything we say to the owner leaves through here, so this is where it is SPELLED.

    WhatsApp formats client-side, so its own emphasis reaches it; Telegram renders nothing
    without a parse mode and neither sender sets one, so it gets the words bare. A producer
    writes one markup and puts chatformat.BREAK wherever a new bubble should start.

    Only the opening bubble wears the name. Four of them labelled "Taskuary (2/4):" over a
    heading that already says what it is read as machinery rather than somebody talking."""
    from . import chatformat, messengers
    out = messengers.tg_send if channel == 'telegram' else messengers.wa_send
    talked(store, channel, chat)
    # A VOICE NOTE IS SAID BACK before it is acted on (A17, 2026-10-22): the owner could not tell what was transcribed - once, on the turn's
    # first message
    a = asking()
    if a and a.get('again') and a.get('channel') == channel and str(a.get('chat')) == str(chat):
        text, a['again'] = f'Picking the walk up here again.\n\n{text}', False
    if a and a.get('closed') and a.get('channel') == channel and str(a.get('chat')) == str(chat):
        text, a['closed'] = f"{a['closed']}\n\n{text}", ''
    if a and a.get('heard') and a.get('channel') == channel and str(a.get('chat')) == str(chat):
        text, a['heard'] = f'🎤 Heard: "{_cut(a["heard"], 300)}"\n\n{text}', ''
    # every road to this chat passes here, so this is where what we offered is written down -
    # off the text AS WRITTEN, before any of it is respelled for the channel
    # `choices`: a further PAGE of a list already kept (More choices) - its words are not numbered in this text
    try: offered = list(choices) if choices else remember_offered(store, channel, chat, text)
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
    # ...and past TWELVE, a page and "More choices" (the owner, 2026-10-02: "the 12 choice should always be click to see more"):
    # a poll and Telegram's buttons both stop at 12, and the rest were reachable only by a typed number. The list kept for
    # typed numbers stays whole; the tap shows the next eleven, and the last page comes round to the first.
    tapped = offered
    if channel in ('whatsapp', 'telegram') and len(offered) > POLL_MAX:
        rest = [w for w in offered if w != MORE_CHOICES]
        at = page if 0 < page < len(rest) else 0
        nxt = at + POLL_MAX - 1 if at + POLL_MAX - 1 < len(rest) else 0
        kept = rest + [MORE_CHOICES]
        store.set_setting(f'{OFFERED_KEY}:{channel}:{chat}', json.dumps(kept), 'assistant')
        store.set_setting(f'{ACTS_KEY}:{channel}:{chat}', json.dumps({**acts_for(store, channel, chat), MORE_CHOICES: {'t': 'page', 'at': nxt}}), 'assistant')
        tapped = rest[at:at + POLL_MAX - 1] + [MORE_CHOICES]
        labels = dict(zip(kept, poll_labels(kept)))         # cut and told apart over the WHOLE list, as resolve_index reads it
    else: labels = dict(zip(offered, poll_labels(offered)))
    # ...and on Telegram a numbered line the buttons carry word for word is not printed above them too - the FYI batch read twice,
    # as text and as buttons (the owner, 2026-10-21: "skip the text, show the card"; F27). WhatsApp's poll cuts long lines, so it keeps them
    if channel == 'telegram' and tapped:
        on = set(tapped)
        text = '\n'.join(l for l in str(text or '').split('\n') if not ((m := _OFFERED.match(l)) and m.group(2) in on))
    msgs = []
    for part in str(text or '').split(chatformat.BREAK):
        shown = chatformat.render(chatformat.json_blocks(part), channel)        # rows as tables, never braces and quotes (F16)
        if shown.strip(): msgs.extend(chatformat.split(shown, chatformat.HARD))
    for i, msg in enumerate(msgs):
        # the LAST bubble carries the choices as a poll: WhatsApp's one tappable thing (the owner, 2026-09-25)
        last = i == len(msgs) - 1 and tapped
        # ...and on Telegram, its own buttons under the same last bubble (messengers.tg_send)
        kw = {'poll': [labels[w] for w in tapped]} if last and channel == 'whatsapp' else {'buttons': tapped} if last and channel == 'telegram' else {}
        # the name only where the chat does not already say who is talking: a Telegram bot's own name heads every message (F27)
        out(store, chat, ('Taskuary:\n' + msg) if i == 0 and channel != 'telegram' else msg, connector_id=connector_id, **kw)
    # a SENT line, not only a failed one: "never responds" left nothing to tell a reply that went from one
    # that never did (2026-09-24)
    logger.info(f'{channel}: sent {len(msgs)} message(s), {sum(len(m) for m in msgs)} chars, to the assistant chat'
                if msgs else f'{channel}: nothing to send - the answer was empty')
