"""NOTHING FALLS THROUGH: the daily check, and the person nobody answered. No model - every fact here is already in the store.

The point of the app is that nothing is lost between the contexts it holds, and two holes stayed open:

- A PERSON'S ASK NOBODY ANSWERED (aged_asks). Their mail asked something (triage's own verdict), no task came of it, nothing of the
  owner's went back, and nobody ruled on it - and once it aged off the rail (unread for funnel_hours, history for feed_days) it
  was simply gone.
  Past AGED_DAYS it comes back as an ordinary row under On you, the way the Advisor's finds land: an idea whose verdict is the
  mail's own, so no model reads it again. A sender that is not a person (automated, bulk, a notice) is never raised.
- AN OPEN ITEM IN NO STATE AT ALL (loose_tasks). Every open task is meant to be in exactly one of five states: the owner's move,
  waiting on a named person with a date, an agent working (or stopped, with Continue), put away with Remind me until a day, or
  closed. One in none of them - waiting on nobody, or on somebody with no date that brings it back - sits where nothing will
  ever move it. The check says so on the task's OWN row (an idea joined to the task, processing_unread lifts it under On you)
  until the state is fixed; the row reads the task live, so fixing it takes the line off at once.

Both are said once per set of facts (the idea's Sig): not again tomorrow for the same item unless it changed, and never again
after the owner put it down, until it changes.
"""
import json
from datetime import datetime
from loguru import logger

from . import lanes, words
from .store import task_ref

SWEPT_KEY = 'loose_ends_swept'
AGED_DAYS = 5              # a person's ask unanswered this long, with nothing deciding it, is raised (fixed - the owner, 2026-10-20)
SILENT_DAYS = 5            # how long someone with no answering history may be quiet before a wait on them is late
LOOKBACK_DAYS = 120        # how far back the aged asks are read - past the rail's own window on purpose
ASK, LOOSE = 'unanswered', 'loose'
# the states an open task may be in, by lane: the owner's move (lanes.json on_you), or an agent's
AGENT_LANES = ('working', 'blocked', 'stopped', 'saved')
OWED = ('agentdone', 'wrapup')          # an agent finished / the reply went out: "read it" and "close it?" are next steps
SAY = words.LOOSE


def _ts(s): return str(s or '')[:19].replace('T', ' ')
def _action(i):
    try: return json.loads(i.get('ActionJson') or '{}') or {}
    except (TypeError, ValueError): return {}


# ── the aged ask ──────────────────────────────────────────────────────────────────────────────

def _ruled(store, mid: int, states: dict) -> bool:
    """Did the owner decide anything about this mail? A draft decided (sent, no reply, rejected), a Done / Remind me on its row,
    or an Advisor line about it put down - each is a ruling, and a ruled ask is not one that slipped."""
    if store._one("SELECT 1 x FROM review WHERE MessageId=? LIMIT 1", (mid,)): return True       # a draft at all: waiting or decided
    keys = [f'msg:{mid}']
    row = store._one("SELECT ItemId FROM processing_member WHERE EntityKind='message' AND LocalId=? AND RetiredAt IS NULL", (str(mid),))
    if row: keys.append(f"processing:{row['ItemId']}")
    if any((states.get(k) or {}).get('Status') in ('done', 'later', 'skip') for k in keys): return True
    return any(_action(i).get('mid') == mid and i.get('Status') in ('dismissed', 'done') for i in store.list_ideas())


def aged_asks(store, now: datetime = None, shown: set = frozenset()) -> list:
    """The asks past their day: [{key, kind, text, sig, action}] - the Advisor's candidate shape. `shown` is the mail already on
    the rail as the owner's move: raising it again would be the same ask twice."""
    from .assistant import their_asks
    days = max(1, int(store.get_setting('aged_ask_days', AGED_DAYS) or AGED_DAYS))
    asks, _ = their_asks(store, days=LOOKBACK_DAYS, hours=days * 24)
    states, out = store.funnel_states(), []
    said = {i['Key']: i for i in store.list_ideas()}
    for a in asks:
        act, cid = a.get('action') or {}, a['key'].split(':', 1)[1]
        mid = act.get('mid')
        m = store.get_message(mid) if mid else None
        # no task (theirs_asks reads the thread's), no draft, nothing decided, not on the rail already, not the Advisor's line already
        if not m or act.get('tid') or m.get('TaskId') or mid in shown or _ruled(store, mid, states): continue
        if (said.get(f'asked:{cid}') or {}).get('Status') == 'open': continue
        v = store.message_verdict(mid) or {}
        out.append({'key': f'{ASK}:{cid}', 'kind': ASK, 'sig': _ts(m.get('SentAt')),
                    'text': SAY['unanswered'].format(who=a['who'], gist=a['gist'], ago=a['ago']),
                    'action': {'type': 'message', 'mid': mid, 'tid': None, 'who': a['who'], 'by': 'sweep',
                               'why': SAY['unanswered_why'].format(days=days),
                               # its verdict is the MAIL's own, already reached: no model reads it again, and the rail draws it
                               # as an ask (processing_all.idea_lane) under On you
                               'triage': {'intent': v.get('intent'), 'kind': v.get('kind'), 'why': str(v.get('why') or '')[:200],
                                          'sig': _ts(m.get('SentAt')), 'at': (now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S'),
                                          'linked_task': None, 'error': None, 'by': 'sweep'}}})
    return out


# ── the open task in no state ─────────────────────────────────────────────────────────────────

def _chased(ideas, tid, mids) -> bool:
    """An open follow-up the Advisor raised on it: a person (who_email) and a day it slips (asked_at + their usual day)."""
    for i in ideas or []:
        a = _action(i)
        if (i.get('Status') == 'open' and i.get('Kind') == 'followup' and a.get('who_email') and a.get('asked_at')
                and (a.get('tid') == tid or a.get('mid') in mids)): return True
    return False


def waited_on(store, task: dict, now=None) -> tuple:
    """(who, days quiet, their day): the person a waiting task waits on - its holder, else the last person who wrote on it - how
    long since the last word on it, and the day a silence is late for them: their own answer time (outcomes.late_after, the
    ledger the reply watch reads), SILENT_DAYS when they have no history."""
    from . import outcomes
    msgs = store.list_messages(task['TaskId'])
    from .waiton import waiting
    who = str(task.get('Assignee') or '')
    # the person an agent SAID it waits on (waiton.py) first: the last one to write may be the asker, not who holds the answer
    who = waiting(task) or (who[7:] if who.startswith('person:') else '') or next((str(m['FromEmail']).lower() for m in reversed(msgs) if m.get('FromEmail')
                                                         and m.get('Direction') != 'out' and m.get('Status') != 'context'), '')
    last = max((_ts(m.get('SentAt')) for m in msgs if m.get('SentAt')), default='') or _ts(task.get('UpdatedAt') or task.get('CreatedAt'))
    try: quiet = ((now or datetime.now()) - datetime.fromisoformat(last)).days if last else 0
    except ValueError: quiet = 0
    return who, quiet, (outcomes.late_after(store, who, SILENT_DAYS) if who else SILENT_DAYS)


def state_of(task: dict, card: dict | None, *, deferred: bool = False, chased: bool = False, folded: bool = False, now=None,
             waits=None):
    """Which state an open task is in: None when it is in one of them, else (code, who) - why it is in none. `card` is its rail
    row as drawn (before any loose-end lift: `lane_was`), `deferred` Remind me with a day, `chased` an Advisor follow-up, `waits`
    the waited_on reading, asked for only when it matters."""
    if task.get('Status') not in ('open', 'in_progress', 'waiting'): return None             # closed or dropped: ruled
    now = now or datetime.now()
    if str(task.get('RemindAt') or '') > now.strftime('%Y-%m-%d %H:%M:%S') or deferred: return None
    if folded: return None                                    # a goal's step told by the goal's own row
    if card is None: return ('no_step', '')
    lane = card.get('lane_was') or card.get('lane')
    if lane in AGENT_LANES or card.get('kind') in OWED: return None
    who = str(task.get('Assignee') or '')
    person = who[7:] if who.startswith('person:') else ''
    # WAITING ON THEM is the rail's word, not the status's: a waiting task they have since written on is the owner's move again
    if lane == 'theirs':
        if chased or (person and str(task.get('DueAt') or '')[:10]): return None
        who, quiet, day = waits() if waits else (person, SILENT_DAYS, SILENT_DAYS)
        if not who: return ('waiting_nobody', '')               # nobody to hear from: nothing will ever bring it back
        # ...and somebody with no date is only LATE once they have been quiet past their own usual answer time (the owner,
        # 2026-10-20): a wait that is still inside it is a wait, not a loose end
        return ('waiting_no_date', who) if quiet >= day else None
    if (lanes.LANE.get(lane) or {}).get('on_you') and lanes.lane_section(lane) == 'task': return None
    return ('no_step', '')


def _say(task, code, who) -> str:
    from .processing_unread import holder_name
    return SAY[code].format(ref=task_ref(task['TaskId']), who=holder_name('person:' + who) if who else '')


def _sig(task, code, who='') -> str:
    return '|'.join(str(x or '') for x in (code, task.get('Status'), task.get('Assignee') or who, str(task.get('DueAt') or '')[:10]))


def loose_tasks(store, cards: list, now: datetime = None) -> list:
    """Every open task in no state, as the candidate its own row will say. `cards`: the rail read whole (read rows included)."""
    by_tid = {}
    for c in cards:
        if c.get('tid'): by_tid.setdefault(c['tid'], c)
    ideas, out = store.list_ideas('open'), []
    for t in store.list_tasks(active_only=True):
        tid = t['TaskId']
        parent = store.get_task(t['ParentId']) if t.get('ParentId') else None
        folded = bool(parent and parent.get('Status') not in ('done', 'dropped') and tid not in by_tid)
        mids = {m['MessageId'] for m in store.list_messages(tid)}
        c = by_tid.get(tid)
        st = state_of(t, c, deferred=bool(c and c.get('deferred') and c.get('defer_until')), chased=_chased(ideas, tid, mids),
                      folded=folded, now=now, waits=lambda t=t: waited_on(store, t, now))
        if not st: continue
        code, who = st
        # a task with NO row at all (its only mail is your own, which the rail does not draw) cannot carry the line on its row:
        # the line is a row of its own, naming it (`task`, not `tid`, which would fold it into the task nobody sees)
        on = {'tid': tid} if c else {'task': tid}
        out.append({'key': f'{LOOSE}:{tid}', 'kind': LOOSE, 'sig': _sig(t, code, who), 'text': _say(t, code, who),
                    'action': {'type': 'task', **on, 'loose': code, 'by': 'sweep', 'why': SAY[code + '_why'],
                               'triage': {'intent': 'task', 'kind': t.get('Kind'), 'why': SAY[code + '_why'], 'sig': _sig(t, code, who),
                                          'at': (now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S'), 'linked_task': tid,
                                          'error': None, 'by': 'sweep'}}})
    return out


def loose_on(store, view_ideas, task: dict, card: dict, *, deferred: bool, mids=(), now=None) -> dict | None:
    """The loose end the check raised on this task's row, while the task is STILL in no state and the same one - read live, so
    a date or a name put on it takes the line off before the next check runs. None otherwise."""
    tid = task.get('TaskId')
    mine = [i for i in view_ideas or [] if i.get('Kind') == LOOSE and i.get('Status') == 'open' and _action(i).get('tid') == tid]
    if not mine: return None
    st = state_of(task, card, deferred=deferred, chased=_chased(view_ideas, tid, set(mids)), now=now, waits=lambda: waited_on(store, task, now))
    return next((i for i in mine if st and i.get('Sig') == _sig(task, *st)), None)


# ── the check ─────────────────────────────────────────────────────────────────────────────────

def _say_once(store, cands: list, stamp: str) -> list:
    """Upsert each candidate whose facts are new: never said, or said with another Sig. The same facts are not said again - not
    tomorrow, and not after the owner put the line down."""
    old, said = {i['Key']: i for i in store.list_ideas()}, []
    for c in cands:
        i = old.get(c['key'])
        if i and (i.get('Sig') or '') == c['sig']: continue
        said.append(store.upsert_idea(c, stamp))
    return said


def run(store, now: datetime = None) -> dict:
    """The check, now: raise what fell through, put down what has since found its state. Returns {'asks', 'loose', 'cleared'}."""
    now = now or datetime.now()
    stamp = now.strftime('%Y-%m-%d %H:%M:%S')
    from . import processing_unread
    canonical = store.processing_reads_active()
    if canonical: store.reconcile_processing_membership()      # the rail as it stands now, not as the last settle left it
    # the rail as the owner has it, read rows too: what is already on it as their move is not raised twice
    cards = processing_unread.build(store, now=now, include_read=True)['items'] if canonical else []
    shown = set()
    for c in cards:
        # ...the mail's own row, never this check's line about it: that one is the ask said, not the ask seen
        if c.get('unread') and lanes.on_you(c) and c.get('mid') and c.get('idea_kind') not in (ASK, LOOSE): shown.add(c['mid'])
    asks = aged_asks(store, now, shown)
    loose = loose_tasks(store, cards, now) if canonical else []
    said = _say_once(store, asks + loose, stamp)
    # ...and a line whose task has found a state since, or whose ask was answered, tasked or ruled, is put down
    want, cleared = {c['key'] for c in asks + loose}, 0
    for i in store.list_ideas('open'):
        if i.get('Kind') in (ASK, LOOSE) and i['Key'] not in want:
            store.set_idea_status(i['IdeaId'], 'done', 'sweep'); cleared += 1
    if said or cleared:
        from . import funnel
        funnel.invalidate()
    logger.info(f'sweep: {len(asks)} aged ask(s), {len(loose)} loose end(s); {len(said)} said, {cleared} put down')
    return {'asks': len(asks), 'loose': len(loose), 'said': len(said), 'cleared': cleared}


def run_if_due(store, now: datetime = None):
    """Once a day, from the poll's housekeeping beside the outcome sweep: None when today's check already ran."""
    now = now or datetime.now(); today = now.strftime('%Y-%m-%d')
    if store.get_setting(SWEPT_KEY, '') == today: return None
    out = run(store, now)
    store.set_setting(SWEPT_KEY, today, 'sweep')
    return out
