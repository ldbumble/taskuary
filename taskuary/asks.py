"""What the owner asked for, remembered as tasks and said back at the door they asked from
(docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

The assistant is deliberately light - it hands work to tasks and keeps nothing of its own - so it forgot: "where's the tab
check?" had no answer, and finished work was silent. An ask IS a task, marked with where it was asked (`AskedVia`); its
state is its rail lane in the rail's own words; a move into a lane that needs the owner, or its end, is said once. No
memory store, no model call.
"""
import hashlib, json, threading, time
from datetime import datetime, timedelta

from loguru import logger


def door() -> str:
    """Where the owner is asking from right now: the phone chat speaking this turn, else the desktop."""
    from . import remote_assistant
    at = remote_assistant.asking()
    return f"{at['channel']}:{at['chat']}" if at and at.get('channel') and at.get('chat') else 'desktop'


def mark(store, tid: int):
    """The owner started an agent on a task that was not theirs to begin with (mail, triage): from now on it is their
    ask, said back at the door they started it from. A task already asked keeps its door. Written quietly."""
    t = store.get_task(tid) or {}
    if t and not of(t): store._exec('UPDATE task SET AskedVia=? WHERE TaskId=?', (door(), tid))


def of(task) -> str | None:
    """The door a task was asked from, or None for work the owner did not ask for (triage, reports, ...)."""
    return (task or {}).get('AskedVia') or None


# ── where an ask stands: its task's rail lane, in the rail's own words ───────────────────
# ONE VOCABULARY: an ask has no statuses of its own. These are the lanes whose arrival is said at the ask's door - the
# owner is needed (blocked, approve), it is stuck (stopped, broken), or it ended (saved: the run finished and kept the
# task open; finished: closed). `working`, `queued`... are never said.
SAID = ('blocked', 'approve', 'stopped', 'broken', 'saved', 'finished')
AGENT_REFS = ('assistant:agent', 'assistant:handoff')      # a chat hand-off IS an agent's job from its first second
OWNER = ('owner', 'assistant-phone')                       # who closing it means the owner did: nothing to tell them


def _rail(store) -> list:
    """The rail as it stands, built if it has to be - for the background check, never for a chat turn (block())."""
    from . import funnel
    funnel.pile(store, quiet=True)
    return funnel.full_items(store) or (funnel.cached_pile(store) or {}).get('items') or []


def agent_touched(store, tid: int) -> bool:
    """Has an agent worked this? A to-do the owner does themselves has nothing to report."""
    t = store.get_task(tid) or {}
    if str(t.get('Assignee') or '').startswith('agent:') or t.get('SourceRef') in AGENT_REFS: return True
    return bool(store._one('SELECT 1 x FROM run WHERE TaskId=? UNION SELECT 1 FROM transcript WHERE TaskId=? '
                           'UNION SELECT 1 FROM worker_event WHERE TaskId=? LIMIT 1', (tid, tid, tid)))


def state(store, tid: int, rail: list = None) -> tuple:
    """(lane, sentence) - the rail's lane for this task and its own words; 'finished' when closed, 'quiet' when it is on
    no rail row. Where it has emails to send, how many are drafted rides along (slots.py). `rail`: rows already in hand."""
    from . import funnel, slots
    t = store.get_task(tid) or {}
    if t.get('Status') in ('done', 'dropped'):
        found = funnel.agent_found(store, tid)
        return 'finished', ('done' + (f': {found}' if found else '') if t.get('Status') == 'done' else 'dropped')
    row = next((i for i in (rail if rail is not None else _rail(store)) if i.get('tid') == tid), None)
    if not row: return 'quiet', ''
    lane, says = row.get('lane') or 'quiet', str(row.get('why') or '').strip()
    owed = slots.all_(store, tid)
    if owed and lane == 'approve':
        drafted = sum(1 for i in owed if i.get('rid'))
        says = f"{drafted} of {len(owed)} emails drafted, waiting on your yes"
    return lane, says


# ── saying it moved: once, at the door it was asked from ─────────────────────────────────
def _told(store, tid: int, lane: str):
    """The last lane said (or passed over) for this ask - written quietly: a poke here would queue the same task again."""
    store._exec('UPDATE task SET AskedTold=?, AskedToldAt=? WHERE TaskId=?', (lane, datetime.now().isoformat(' ', 'seconds'), tid))


TITLE_SAID = 60


def _title(t: dict) -> str:
    s = ' '.join(str((t or {}).get('Title') or '').split())
    return s if len(s) <= TITLE_SAID else s[:TITLE_SAID - 1].rstrip() + '…'


def _sig(text) -> str: return hashlib.sha1(str(text or '').strip().encode()).hexdigest()[:10]


def phone_text(store, t: dict, lane: str, says: str) -> tuple:
    """What the phone is told: the line, and what it asks a yes FOR - every email in full (the owner, 2026-10-05: "this is
    useless if i don't know what i'm approving"), or the drafted reply - with numbered picks that run the desktop's own
    send and drop. (text, [(label, act)])."""
    from . import slots
    from .store import task_ref
    tid = t['TaskId']
    blocks, rows, ready = [f"{task_ref(tid)} {_title(t)} - {says or lane}."], [], []
    if lane == 'approve':
        emails = [(i, store.get_review(i['rid'])) for i in slots.open_(store, tid) if i.get('rid')]
        emails = [(i, rv) for i, rv in emails if rv and rv.get('Status') == 'pending']
        for n, (i, rv) in enumerate(emails, 1):
            o = i['out']; addr = o['to'] if '@' in str(o.get('to')) else ''
            who = o.get('name') or o['to']
            subject = (json.loads(rv.get('Deliver') or '{}') or {}).get('subject')
            blocks.append(f"{n}) To {who}" + (f" <{addr}>" if addr and o.get('name') else '')
                          + ('' if addr else ' - no address yet (reply with it, or drop it)') + (f' - "{subject}"' if subject else '')
                          + '\n' + str(rv.get('DraftText') or '').strip())
            if addr:
                rows.append((f'Send to {who}', {'t': 'send', 'rid': rv['ReviewId'], 'sig': _sig(rv.get('DraftText'))})); ready.append(rv)
            else: rows.append((f'Drop the one to {who}', {'t': 'drop', 'tid': tid, 'slot': i['id']}))
        if len(ready) > 1:
            rows.append((f"Send {'both' if len(ready) == 2 else f'all {len(ready)}'} ready ones",
                         {'t': 'sendall', 'sends': [[rv['ReviewId'], _sig(rv.get('DraftText'))] for rv in ready]}))
        reply = None if emails else store.pending_review(tid)
        if reply and str(reply.get('DraftText') or '').strip():
            blocks.append(str(reply['DraftText']).strip())
            rows.append(('Send the reply', {'t': 'send', 'rid': reply['ReviewId'], 'sig': _sig(reply.get('DraftText'))}))
    rows.append((f'Open {task_ref(tid)}', {'t': 'open', 'key': f'task:{tid}'}))
    return '\n\n'.join(blocks) + '\n\n' + '\n'.join(f'{n} · {label}' for n, (label, _) in enumerate(rows, 1)), rows


def send_picked(store, sends: list) -> str:
    """A phone pick's send: each email exactly as it was shown - one rewritten since is not sent, but said."""
    from . import verdicts
    said = []
    for rid, sig in sends:
        rv = store.get_review(int(rid)) or {}
        to = ', '.join((json.loads(rv.get('Deliver') or '{}') or {}).get('to') or []) or 'the sender'
        if rv.get('Status') != 'pending': said.append(f'the one to {to} was already {rv.get("Status") or "gone"}'); continue
        if sig and _sig(rv.get('DraftText')) != sig: said.append(f'the email to {to} changed since I showed it - not sent; open it to see it again'); continue
        out = verdicts.decide(store, rv, 'approve')
        said.append(f'Sent to {to}' if out.get('ok') and not out.get('send_error') else f"not sent to {to} - {out.get('send_error') or out.get('status')}")
    return '. '.join(s[:1].upper() + s[1:] for s in said) + '.'


def _say(store, task: dict, line: str, via: str = None, lane: str = None, says: str = '', desktop: bool = False) -> bool:
    """One line at the ask's door. The phone it was asked from - or, failing that, the phone the walk is handed to - only
    in a gap of the conversation (remote_assistant.quiet: never between a card and its answer); False = not now, try
    again. Everywhere else, the desktop Assistant chat. `via`: a door other than the ask's (a reminder's). `desktop`: a
    line nobody asked for at that moment - a due day, a nudge, a watch ending - which the phone never speaks first (the
    owner, 2026-10-02)."""
    from . import concierge, general, live, remote_assistant
    via, handed = via or of(task) or 'desktop', None if desktop else remote_assistant.handoff(store)
    doors = ([tuple(via.split(':', 1))] if ':' in via and not desktop else []) + ([(handed['channel'], handed['chat'])] if handed else [])
    for channel, chat in doors:
        c = remote_assistant.connector_for_chat(store, channel, chat)
        if not c: continue
        if not remote_assistant.quiet(store, channel, chat): return False
        if lane:                                    # the phone gets what it is asked a yes for, and the picks to give it
            line, rows = phone_text(store, task, lane, says)
            remote_assistant._offer(rows)
        remote_assistant.send(store, channel, chat, line, c['ConnectorId'])
        try: concierge.record(store, general.dock_task(store, 'owner')[0]['TaskId'], 'assistant', line, phone=True)
        except Exception as e: logger.warning(f'asks: said on the phone, not kept in the chat - {e}')   # never said twice
        return True
    # ON THE DESKTOP A LANE MOVE IS NOT A LINE: the rail row and the task's own card already say it, and the lines piled
    # under the task being worked - "asked you", "left without finishing", the same ask twice in two wordings (the owner,
    # 2026-10-06: "Task they are working on should be the main thing, nothing else"). What the owner ASKED to hear - a
    # reply on a watched task, a reminder coming due - still comes here; a phone, which has no card, still hears it all.
    if lane: return True
    concierge.record(store, general.dock_task(store, 'owner')[0]['TaskId'], 'assistant', line)
    live.emit(live.CHAT)                     # the open Assistant tab shows it now, not on its next tick
    return True


def check(store, tid: int) -> str | None:
    """Say this ask's move if it moved into a said lane since it was last told. The line said, or None."""
    from .store import task_ref
    t = store.get_task(tid) or {}
    watched, worked = t.get('AskedWatch'), agent_touched(store, tid)
    if not of(t) or not (worked or watched): return None
    if watched in ('reply', 'any'):
        said = _reply(store, t)
        if said: return said
    # which lane moves are said: all of them where an agent works it or the watch is on everything; only its end for a
    # "tell me when it's done"; none for "tell me when someone replies"
    lanes = SAID if worked or watched == 'any' else ('finished',) if watched == 'done' else ()
    lane, says = state(store, tid)
    # the same lane again is not news - unless it is a NEW close: reopened and closed again after it was told
    again = lane == 'finished' and str(t.get('ClosedAt') or '') > str(t.get('AskedToldAt') or '')
    if lane == 'quiet' or (lane == t.get('AskedTold') and not again): return None
    # not said: a lane that needs nobody, or a close the owner made themselves (they know - they pressed it)
    if lane not in lanes or (lane == 'finished' and t.get('UpdatedBy') in OWNER):
        _told(store, tid, lane); return None
    line = f"{task_ref(tid)} {_title(t)} - {says or lane}."
    if not _say(store, t, line, lane=lane, says=says): return None
    _told(store, tid, lane)
    return line


def _answer(store, tid: int) -> dict | None:
    """The newest word from the other side on this task's mail threads. A FILED one too: an answer that settles the
    question ("Thursday at 2 works") is exactly what triage files as needing nothing, and lands on no task at all. Never
    an auto-reply, never our own; a chat room is one task's lines only (a room is not a thread)."""
    from .autoreply import STATUS as AUTO
    from .ingest import is_ours
    me = str(store.get_setting('owner_email') or '').lower()
    rows = store._rows("SELECT * FROM message WHERE (TaskId=? OR ConversationId IN (SELECT ConversationId FROM message WHERE TaskId=? "
                       "AND Channel='email' AND ConversationId IS NOT NULL)) AND Status NOT IN ('context','history','skipped',?) "
                       "AND IFNULL(Direction,'in')<>'out' AND IFNULL(Channel,'')<>'report' ORDER BY SentAt DESC, MessageId DESC LIMIT 8",
                       (tid, tid, AUTO))
    return next((m for m in rows if not is_ours(m) and (not me or str(m.get('FromEmail') or '').lower() != me)), None)


def _who(m: dict, first: bool = True) -> str:
    """A person as the owner calls them: 'Erin' from "Blake, Erin" - or the address when there is no name."""
    from .triage import person_name
    n = person_name((m or {}).get('FromName'))
    return (n.split()[0] if first else n) if n else str((m or {}).get('FromEmail') or 'them')


def _reply(store, t: dict) -> str | None:
    """A watched task's new message, said once: who answered and the start of what they said. A reply watch ends with
    the answer - it was waiting for exactly that; a watch on everything goes on."""
    from .store import task_ref
    m = _answer(store, t['TaskId']) or {}
    if not m.get('MessageId') or str(m['MessageId']) == str(t.get('AskedSeenMid') or ''): return None
    words = ' '.join(str(m.get('OwnText') or m.get('BodyText') or '').split())[:140]
    line = f"{task_ref(t['TaskId'])} {str(t.get('Title') or '').strip()} - {_who(m, first=False)} answered: {words}"
    if not _say(store, t, line): return None
    store._exec('UPDATE task SET AskedSeenMid=? WHERE TaskId=?', (m['MessageId'], t['TaskId']))
    if t.get('AskedWatch') == 'reply': store._exec('UPDATE task SET AskedWatch=NULL WHERE TaskId=?', (t['TaskId'],))
    return line


# ── "I'll keep an eye out" that keeps it: a sent reply that asks something watches for the answer ──
# Sending closes the task, so an ordinary reply had no "waiting on them" at all, and the sweep forgot any watch on a task
# over 30 days old however recently it began (2026-10-06). Now the watch starts at the send and counts its own 30 days;
# their answer ends it; a quiet stretch offers one nudge - held while they are out of office; at 30 days it stops, and
# says so. The lines nobody asked for at that moment (the nudge, the end) stay in the app.
NUDGE_DAYS = 2                     # assistant.CHASE_STEPS' first step: silence worth a word


def watch_reply(store, rv: dict, body: str, now: datetime = None) -> str | None:
    """After a reply really left: when it ASKED them something (assistant._ASKS, the Advisor's own test for a follow-up
    owed), watch for their answer - on the task the send just closed too. The line to say, or None."""
    from .assistant import _ASKS
    from .triage import own_words
    tid, msg = rv.get('TaskId'), store.get_message(rv['MessageId']) if rv.get('MessageId') else None
    if not tid or not msg or msg.get('Channel') != 'email' or not _ASKS.search(own_words(str(body or ''))): return None
    t = store.get_task(tid) or {}
    seen, at = (_answer(store, tid) or msg).get('MessageId'), (now or datetime.now()).isoformat(' ', 'seconds')
    store._exec('UPDATE task SET AskedVia=COALESCE(AskedVia,?), AskedWatch=?, AskedSeenMid=?, AskedWatchAt=?, AskedNudgedAt=NULL '
                'WHERE TaskId=?', (door(), 'any' if t.get('AskedWatch') == 'any' else 'reply', seen, at, tid))
    line = f"Sent. I'll watch for {_who(msg)}'s answer."
    store.add_comment(tid, 'assistant', 'agent', line)
    return line


def _waiting_on(store, t: dict) -> dict:
    """Whose answer a watch waits for: the message the owner answered (what was seen when it began)."""
    return (store.get_message(t['AskedSeenMid']) if t.get('AskedSeenMid') else None) or {}


def nudge(store, t: dict, now: datetime = None) -> str | None:
    """Two days of silence on a reply watch: offered once - never to someone whose auto-reply says they are away."""
    from . import assistant
    from .store import task_ref
    now = now or datetime.now()
    if t.get('AskedWatch') not in ('reply', 'any') or t.get('AskedNudgedAt') or not t.get('AskedWatchAt'): return None
    try: quiet = now - datetime.fromisoformat(str(t['AskedWatchAt'])[:19])
    except ValueError: return None
    if quiet < timedelta(days=NUDGE_DAYS): return None
    m = _waiting_on(store, t)
    if str(m.get('FromEmail') or '').lower() in assistant.ooo(store): return None     # held while they are away
    line = f"{task_ref(t['TaskId'])} {_title(t)} - still nothing from {_who(m)}. Want a short nudge ready?"
    if not _say(store, t, line, desktop=True): return None
    store._exec('UPDATE task SET AskedNudgedAt=? WHERE TaskId=?', (now.isoformat(' ', 'seconds'), t['TaskId']))
    return line


def stop_watching(store, t: dict, quiet: bool = False) -> str | None:
    """A watch at its 30 days ends, and says so with the way back (watch_task again). One with no start of its own -
    from before watches kept one - ends quietly."""
    from .store import task_ref
    line = None if quiet else f"I've stopped watching for {_who(_waiting_on(store, t))}'s answer on {task_ref(t['TaskId'])} {_title(t)}. Keep going?"
    if line and not _say(store, t, line, desktop=True): return None
    store._exec('UPDATE task SET AskedWatch=NULL WHERE TaskId=?', (t['TaskId'],))
    return line


def say_due(store, tid: int, line: str) -> bool:
    """A due day's line (remind.deadlines), in the desktop chat only."""
    from .store import task_ref
    t = store.get_task(tid) or {}
    return bool(t) and _say(store, t, f"{task_ref(tid)} {_title(t)} - {line}", via='desktop', desktop=True)


WATCHES = ('done', 'reply', 'any', 'off')


def watch_task(store, tid: int, what: str = 'any') -> dict:
    """"Tell me when it's done / when Paula replies" about any task - here, at the door it was said on. What is already
    on the task is not news: only a reply after the watch is said. `off` stops the watch (the task stays an ask)."""
    what = str(what or 'any').strip().lower()
    if what not in WATCHES: raise ValueError('what: done | reply | any | off')
    if not store.get_task(tid): raise ValueError('task not found')
    if what == 'off':
        store._exec('UPDATE task SET AskedWatch=NULL WHERE TaskId=?', (tid,)); return {'taskId': tid, 'watch': 'off'}
    seen = (_answer(store, tid) or {}).get('MessageId')
    # ...and its 30 days count from NOW: "keep going" after a watch ended starts a fresh one
    store._exec('UPDATE task SET AskedVia=?, AskedWatch=?, AskedSeenMid=?, AskedWatchAt=?, AskedNudgedAt=NULL WHERE TaskId=?',
                (door(), what, seen, datetime.now().isoformat(' ', 'seconds'), tid))
    return {'taskId': tid, 'watch': what, 'via': door()}


# ── a reminder reaches you: said at the door it was set from when it comes due (remind.due) ──
def reminder_set(store, tid: int):
    store._exec('UPDATE task SET RemindVia=? WHERE TaskId=?', (door(), tid))


def remind_due(store, tid: int):
    store._exec("UPDATE task SET RemindOwed='1' WHERE TaskId=?", (tid,))
    _remind(store, tid)


def _remind(store, tid: int) -> bool:
    """The due reminder, said once; a busy phone chat keeps it owed for the next look (sweep)."""
    from .store import task_ref
    t = store.get_task(tid) or {}
    if not t: return False
    line = f"Reminder: {task_ref(tid)} {str(t.get('Title') or '').strip()} - you asked to be reminded about it today."
    if not _say(store, t, line, via=t.get('RemindVia') or 'desktop'): return False
    store._exec('UPDATE task SET RemindOwed=NULL WHERE TaskId=?', (tid,))
    return True


# Event-driven: a task write (store._poke 'task-changed') queues its id; one worker drains the queue a moment later, so a
# 150-row catch-up is one pass over the few asks it touched. A slow sweep catches what no write announces (an agent going
# quiet). Off until watch() starts it - tests and scripts never get a background thread.
WAIT, SWEEP, DAYS = 2.0, 300.0, 30
_Q = {'on': False, 'pending': {}, 'lock': threading.Lock(), 'wake': threading.Event()}


def notice(store, tid):
    if not _Q['on'] or not tid: return
    with _Q['lock']: _Q['pending'][int(tid)] = store
    _Q['wake'].set()


def drain():
    with _Q['lock']: due, _Q['pending'] = _Q['pending'], {}
    for tid, store in due.items():
        try: check(store, tid)
        except Exception as e: logger.warning(f'asks: could not check {tid} - {e}')


def sweep(store, now: datetime = None):
    from . import remind
    try: remind.tick(store, now)             # a reminder for later today comes due on this clock too, not only on a sync
    except Exception as e: logger.warning(f'asks: reminders not looked at - {e}')
    for r in store._rows("SELECT TaskId FROM task WHERE RemindOwed='1'"):
        try: _remind(store, r['TaskId'])
        except Exception as e: logger.warning(f"asks: could not say the reminder on {r['TaskId']} - {e}")
    now = now or datetime.now()
    since = (now - timedelta(days=DAYS)).isoformat(' ', 'seconds')
    # a watch's 30 days are its own, counted from when it began - not the task's age
    for t in store._rows("SELECT * FROM task WHERE AskedWatch IN ('reply','any') AND COALESCE(AskedWatchAt, CreatedAt)<?", (since,)):
        try: stop_watching(store, t, quiet=not t.get('AskedWatchAt'))
        except Exception as e: logger.warning(f"asks: could not end the watch on {t['TaskId']} - {e}")
    for r in store._rows("SELECT TaskId FROM task WHERE AskedVia IS NOT NULL AND COALESCE(AskedWatchAt, CreatedAt)>=? AND "
                         "(Status NOT IN ('done','dropped') OR IFNULL(AskedTold,'')<>'finished' OR AskedWatch IN ('reply','any')) "
                         "ORDER BY TaskId", (since,)):
        try: check(store, r['TaskId']); nudge(store, store.get_task(r['TaskId']) or {}, now)
        except Exception as e: logger.warning(f"asks: could not check {r['TaskId']} - {e}")


def watch(store):
    """Start the one worker (the server's lifespan does; conftest replaces this)."""
    if _Q['on']: return
    _Q['on'] = True
    def loop():
        last = 0.0
        while True:
            woke = _Q['wake'].wait(timeout=SWEEP); _Q['wake'].clear()
            try:
                if woke: time.sleep(WAIT); drain()
                if time.monotonic() - last >= SWEEP: sweep(store); last = time.monotonic()
            except Exception as e: logger.warning(f'asks watcher: {e}')
    threading.Thread(target=loop, daemon=True, name='asks').start()


# ── the assistant knows your asks: a short block every turn, the rest on request ─────────
BLOCK_CAP, TITLE, SAYS = 6, 50, 60


def _ago(stamp) -> str:
    try: d = datetime.now() - datetime.fromisoformat(str(stamp)[:19])
    except (TypeError, ValueError): return ''
    h = int(d.total_seconds() // 3600)
    return 'just now' if h < 1 else f'{h}h ago' if h < 24 else 'yesterday' if h < 48 else f'{h // 24}d ago'


def _where(via) -> str:
    return '' if not via or via == 'desktop' else via.split(':', 1)[0].capitalize().replace('Whatsapp', 'WhatsApp')


def _line(store, t: dict, says: str) -> str:
    from .store import task_ref
    when = ', '.join(x for x in (_ago(t.get('CreatedAt')), _where(of(t))) if x)
    return (f"- {task_ref(t['TaskId'])} {str(t.get('Title') or '').strip()[:TITLE]}" + (f' ({when})' if when else '')
            + (f' - {says[:SAYS]}' if says else ''))


def _asked(store, open_only: bool, limit: int) -> list:
    q = 'SELECT * FROM task WHERE AskedVia IS NOT NULL' + (" AND Status NOT IN ('done','dropped')" if open_only else '')
    return store._rows(q + ' ORDER BY TaskId DESC LIMIT ?', (int(limit),))


def block(store, items: list = None) -> str:
    """YOUR OPEN ASKS - what the owner handed over and where each stands, newest first: enough for "where's the tab
    check?" and "add Omar to that" to land on the right task. Called on every chat turn, so it never builds the rail: it
    reads the turn's own pile (`items`, the unread rail) and the cached full build. A finished ask stays only while it is
    still unread on the rail."""
    rows = _asked(store, False, 40)
    if not rows: return ''
    from . import funnel
    unread = items if items is not None else ((funnel.cached_pile(store) or {}).get('items') or [])
    full, on_rail = funnel.full_items(store) or unread, {i.get('tid') for i in unread}
    lines = []
    for t in rows:
        if t.get('Status') in ('done', 'dropped') and t['TaskId'] not in on_rail: continue
        if not agent_touched(store, t['TaskId']): continue
        lines.append(_line(store, t, state(store, t['TaskId'], full)[1]))
        if len(lines) >= BLOCK_CAP: break
    return '\n'.join(['YOUR OPEN ASKS'] + lines) if lines else ''


def listing(store, p: dict) -> str:
    """The look-up (asks.list): every ask, any age - "what did I ask you last week?". `status`: open (default) | all."""
    open_only = str(p.get('status') or 'open').strip().lower() != 'all'
    rows = _asked(store, open_only, max(1, min(int(p.get('limit') or 20), 60)))
    return '\n'.join(_line(store, t, state(store, t['TaskId'])[1] or t.get('Status') or '') for t in rows) or 'No asks yet.'


# ── the Advisor never repeats what a task just said ──────────────────────────────────────
def _since(hours: float) -> str: return (datetime.now() - timedelta(hours=hours)).isoformat(' ', 'seconds')


def touched(store, hours: float) -> dict:
    """What the owner's tasks already cover: every OPEN ask (its thread is being worked), and in the window every task
    that said something at its door, sent something, or closed - their threads, and the people a task's email or reply
    reached. The Advisor's follow-ups on any of these are not news yet."""
    cut = _since(hours)
    tids = {r['TaskId'] for r in store._rows(
        # ...and a reply being watched: the watch offers its own nudge, so the Advisor's chase would be the same line twice
        "SELECT TaskId FROM task WHERE (AskedVia IS NOT NULL AND Status NOT IN ('done','dropped')) OR AskedWatch IN ('reply','any') OR ClosedAt>=? "
        f"OR (AskedToldAt>=? AND AskedTold IN ({','.join('?' * len(SAID))}))", (cut, cut, *SAID))}
    people = set()
    for r in store._rows("SELECT TaskId, Deliver FROM review WHERE DeliveryState='sent' AND DecidedAt>=?", (cut,)):
        if r.get('TaskId'): tids.add(r['TaskId'])
        try: people |= {str(a).lower() for a in (json.loads(r.get('Deliver') or '{}') or {}).get('to') or []}
        except (TypeError, ValueError): pass
    ids = sorted(tids)
    convs = {r['ConversationId'] for r in store._rows(
        f"SELECT DISTINCT ConversationId FROM message WHERE ConversationId IS NOT NULL AND TaskId IN ({','.join('?' * len(ids))})", ids)} if ids else set()
    return {'tids': tids, 'convs': convs, 'people': people}


def not_just_said(store, cands: list, hours: float) -> list:
    """Drop the Advisor candidates a task already covers - before the model sees them. Past the window, with the other
    side still quiet and no open ask on it, they come back: that chase is what the Advisor is for."""
    t = touched(store, hours)
    def covered(c):
        a = c.get('action') or {}
        if a.get('tid') in t['tids'] or str(c.get('key') or '').split(':', 1)[-1] in t['convs']: return True
        m = store.get_message(a['mid']) if a.get('mid') else None
        return bool(m and (m.get('TaskId') in t['tids'] or m.get('ConversationId') in t['convs'] or str(m.get('FromEmail') or '').lower() in t['people']))
    return [c for c in cands if not covered(c)]


def told_lines(store, days: float = 7) -> str:
    """What tasks already told the owner this week, with what the agent found - the Advisor reads it beside its own lines,
    and does not say it again."""
    from . import funnel
    from .store import task_ref
    rows = store._rows("SELECT TaskId, Title, AskedTold, AskedToldAt FROM task WHERE AskedToldAt>=? AND AskedTold IN "
                       f"({','.join('?' * len(SAID))}) ORDER BY AskedToldAt DESC LIMIT 20", (_since(days * 24), *SAID))
    def line(r):
        found = funnel.agent_found(store, r['TaskId']) if r['AskedTold'] in ('finished', 'saved') else ''
        return (f"- {task_ref(r['TaskId'])} {str(r.get('Title') or '')[:70]} - {r['AskedTold']} ({_ago(r['AskedToldAt'])})"
                + (f': {found}' if found else ''))
    return '\n'.join(line(r) for r in rows)
