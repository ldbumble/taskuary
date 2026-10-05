"""What the owner asked for, remembered as tasks and said back at the door they asked from
(docs/superpowers/specs/2026-10-05-assistant-remembers-asks-design.md).

The assistant is deliberately light - it hands work to tasks and keeps nothing of its own - so it forgot: "where's the tab
check?" had no answer, and finished work was silent. An ask IS a task, marked with where it was asked (`AskedVia`); its
state is its rail lane in the rail's own words; a move into a lane that needs the owner, or its end, is said once. No
memory store, no model call.
"""
import json, threading, time
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


def _say(store, task: dict, line: str, via: str = None) -> bool:
    """One line at the ask's door. The phone it was asked from - or, failing that, the phone the walk is handed to - only
    in a gap of the conversation (remote_assistant.quiet: never between a card and its answer); False = not now, try
    again. Everywhere else, the desktop Assistant chat. `via`: a door other than the ask's (a reminder's)."""
    from . import concierge, general, live, remote_assistant
    via, handed = via or of(task) or 'desktop', remote_assistant.handoff(store)
    doors = ([tuple(via.split(':', 1))] if ':' in via else []) + ([(handed['channel'], handed['chat'])] if handed else [])
    for channel, chat in doors:
        c = remote_assistant.connector_for_chat(store, channel, chat)
        if not c: continue
        if not remote_assistant.quiet(store, channel, chat): return False
        remote_assistant.send(store, channel, chat, line, c['ConnectorId'])
        try: concierge.record(store, general.dock_task(store, 'owner')[0]['TaskId'], 'assistant', line, phone=True)
        except Exception as e: logger.warning(f'asks: said on the phone, not kept in the chat - {e}')   # never said twice
        return True
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
    if lane == 'quiet' or lane == t.get('AskedTold'): return None
    # not said: a lane that needs nobody, or a close the owner made themselves (they know - they pressed it)
    if lane not in lanes or (lane == 'finished' and t.get('UpdatedBy') in OWNER):
        _told(store, tid, lane); return None
    line = f"{task_ref(tid)} {str(t.get('Title') or '').strip()} - {says or lane}."
    if not _say(store, t, line): return None
    _told(store, tid, lane)
    return line


def _reply(store, t: dict) -> str | None:
    """A watched task's new message, said once: who wrote and the start of what they said."""
    from .store import task_ref
    m = store.last_material_inbound_on_task(t['TaskId']) or {}
    if not m.get('MessageId') or m['MessageId'] == t.get('AskedSeenMid'): return None
    words = ' '.join(str(m.get('OwnText') or m.get('BodyText') or '').split())[:140]
    line = f"{task_ref(t['TaskId'])} {str(t.get('Title') or '').strip()} - {m.get('FromName') or m.get('FromEmail') or 'someone'} wrote: {words}"
    if not _say(store, t, line): return None
    store._exec('UPDATE task SET AskedSeenMid=? WHERE TaskId=?', (m['MessageId'], t['TaskId']))
    return line


WATCHES = ('done', 'reply', 'any', 'off')


def watch_task(store, tid: int, what: str = 'any') -> dict:
    """"Tell me when it's done / when Paula replies" about any task - here, at the door it was said on. What is already
    on the task is not news: only a reply after the watch is said. `off` stops the watch (the task stays an ask)."""
    what = str(what or 'any').strip().lower()
    if what not in WATCHES: raise ValueError('what: done | reply | any | off')
    if not store.get_task(tid): raise ValueError('task not found')
    if what == 'off':
        store._exec('UPDATE task SET AskedWatch=NULL WHERE TaskId=?', (tid,)); return {'taskId': tid, 'watch': 'off'}
    seen = (store.last_material_inbound_on_task(tid) or {}).get('MessageId')
    store._exec('UPDATE task SET AskedVia=?, AskedWatch=?, AskedSeenMid=? WHERE TaskId=?', (door(), what, seen, tid))
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


def sweep(store):
    for r in store._rows("SELECT TaskId FROM task WHERE RemindOwed='1'"):
        try: _remind(store, r['TaskId'])
        except Exception as e: logger.warning(f"asks: could not say the reminder on {r['TaskId']} - {e}")
    since = (datetime.now() - timedelta(days=DAYS)).isoformat(' ', 'seconds')
    for r in store._rows("SELECT TaskId FROM task WHERE AskedVia IS NOT NULL AND CreatedAt>=? AND "
                         "(Status NOT IN ('done','dropped') OR IFNULL(AskedTold,'')<>'finished') ORDER BY TaskId", (since,)):
        try: check(store, r['TaskId'])
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
        "SELECT TaskId FROM task WHERE (AskedVia IS NOT NULL AND Status NOT IN ('done','dropped')) OR ClosedAt>=? "
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
