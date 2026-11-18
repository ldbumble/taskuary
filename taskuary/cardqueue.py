"""ONE CARD AT A TIME (the owner, 2026-11-16: "where there are 2 action cards, like approve push then email, it should wait on each approval
step or action card, so the agent should wait on it and then go to next steps ... action cards should hold up the agent until it's completed.
In chat flow it makes more sense"). Every card on a task - a reply or an email to Send, an act to Approve (a push, a PR, a post, a SQL write,
a held step), a calendar answer, the landing question - stands in ONE line, in the order it was raised. Only its front is live; the rest are
held: drawn nowhere, named on the front as what comes next. One comes forward once the owner has pressed (or turned down) the one before it
AND the agent has heard what came of it - the turn that press woke has ended - so the agent goes on from each outcome: it lets the next stand,
changes it, or takes it back. A press never sends or closes another card; nothing goes without its own press.

Plain code, read wherever a card is drawn, listed or told: the chat's list (conversation.items), the page's detail (server.task_detail), what
waits on the owner (store.waiting_reviews), and what its agent hears (agenttools, general.latest_block, general.approved/failed)."""
import json, time, weakref

LAND = 'land'                   # the landing question (landing.record): a card with no review row
FRESH = 1.0                     # seconds one read of a task's line serves the reads beside it, while nothing was written


# ...ONE READ OF A PAGE ASKS IT ONCE (tests/test_big_task_opens_fast: the task's open, its state, what waits on him and its pill each asked
# the line again): kept for a second, and only while this store has written nothing since
_SEEN: dict = {}
def fresh(store, key, fn):
    w = getattr(store, '_writes', None)
    if w is None: return fn()
    k, now = (id(store), key), time.monotonic()
    # ...and only for this very store: a store gone and a new one at its address (a test's) is another store
    if (got := _SEEN.get(k)) and got[3]() is store and got[0] == w and now - got[1] < FRESH: return got[2]
    if len(_SEEN) > 512: _SEEN.clear()
    v = fn(); _SEEN[k] = (w, now, v, weakref.ref(store)); return v
WAKING = 20                     # seconds a woken agent has to begin its turn before the next card stands without it


def _p(r) -> dict:
    try: d = json.loads(r.get('DraftText') or '{}') or {}
    except (TypeError, ValueError): d = {}
    return d if isinstance(d, dict) else {}


def in_line(r: dict) -> bool:
    """A card of the line: one the owner presses, and the agent's or triage's to raise - never a close-out, a playbook or a workflow's own step
    (Taskuary's, beside the reply - proposals._older's rule), an email he wrote himself, nor one nobody has written (a reply owed, a to-do's email)."""
    from .conversation import unwritten
    from .proposals import CLOSEOUT, PLAYBOOKS, passed
    if passed(r) or unwritten(r): return False
    if r['Kind'] == 'slot': return bool(str(r.get('DraftText') or '').strip()) and not str(r.get('Reason') or '').startswith('your email')
    if r['Kind'] == 'action':
        p = _p(r)
        return not (p.get('closeout') or p.get('action') in CLOSEOUT or p.get('action') in PLAYBOOKS or p.get('block')
                    or str(r.get('Reason') or '').startswith('the workflow'))
    return True


def _turn(r) -> str:
    """A turn's held steps are one card (heldGroups on the page), and so are the rows of a bulk card (bulkcard.py, its Batch): the key they
    share - a review's own id for any other card."""
    if r.get('Batch'): return f"b:{r['Batch']}"
    p = _p(r) if r['Kind'] == 'action' else {}
    return f"{p.get('sid') or ''}|{p['turn']}|{p.get('where') or p.get('cwd') or ''}" if p.get('action') == 'shell_act' and p.get('turn') is not None else f"rv{r['ReviewId']}"


def _units(store, tid: int, past: set) -> list:
    "Every card of the line on task `tid`, waiting or settled, oldest first: [{'rids', 'at', 'done', 'rows'}] - the landing question among them."
    from . import landing
    from .conversation import ep
    from .proposals import moved_on
    out, by = [], {}
    for r in store._rows("SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId", (int(tid),)):
        if r['ReviewId'] in past: continue        # ...one the chat moved past is greyed where it stood (proposals._older): no card of the line
        # ...a settled one by what it was while it waited: its run tells how many came together ("2 of 3")
        if r['Status'] != 'pending' and not r.get('DecidedAt'): continue
        if not in_line(r if r['Status'] == 'pending' else {**r, 'Status': 'pending', 'DecideNote': None}): continue
        if (k := _turn(r)) in by: u = by[k]
        else: u = by[k] = {'rids': [], 'rows': [], 'at': ep(r['CreatedAt'])}; out.append(u)
        u['rids'].append(r['ReviewId']); u['rows'].append(r)
    for u in out: u['done'] = None if any(r['Status'] == 'pending' for r in u['rows']) else max(ep(r.get('DecidedAt')) for r in u['rows'])
    rec = landing.record(store, int(tid)); q = rec.get('proposal') or {}
    if q.get('at') and not q.get('passed') and max(float(rec.get('moved') or 0), moved_on(store, int(tid))) <= ep(q['at']):
        went = str((rec.get('landed') or {}).get('at') or '')
        out.append({'rids': [LAND], 'rows': [], 'at': ep(q.get('first') or q['at']), 'done': ep(went) if went >= q['at'] else None, 'how': q.get('how')})
        out.sort(key=lambda u: u['at'])
    return out


def _going_on(store, tid: int, since: float, own=()) -> bool:
    """Is the agent still going on from a press made after `since` on ANOTHER card - at work on it, or woken a moment ago and not yet begun?
    A press on the front itself (`own`: a Send that did not go, which still waits on its card) holds nothing back: it never left its place."""
    from . import general
    from .conversation import ep
    # ...a PRESS: the agent taking back its own card is none - nothing wakes it, and the front stood held for WAKING seconds over it (a CI
    # flake twice, 2026-11-17: whenever the take-back fell in the second after its last answer)
    pressed = max([ep(r['at']) for r in store._rows("SELECT ReviewId, DecidedAt AS at FROM review WHERE TaskId=? AND DecidedAt IS NOT NULL "
                                                    "AND COALESCE(DecidedBy, '') NOT LIKE 'agent%'", (int(tid),))
                   if r['ReviewId'] not in own] or [0.])
    from . import landing
    if LAND not in own: pressed = max(pressed, ep((landing.record(store, int(tid)).get('landed') or {}).get('at')))
    if pressed < since: return False
    last = ep(general._last_answer(store, int(tid)))
    if not last or last >= pressed: return False
    return general.working(store, int(tid)) or time.time() - pressed < WAKING


def state(store, tid: int) -> dict: return fresh(store, ('state', int(tid)), lambda: _state(store, tid))


def _state(store, tid: int) -> dict:
    """The line on task `tid`: {'live': the front's ids or [], 'held': ids that wait behind it, 'n': the front's place in the run it is one
    of, 'of': that run's length, 'next': what comes next in words, 'units', 'past': the cards the chat moved past (proposals.written_past)}. The front itself is held while its agent goes on from the press
    that brought it forward."""
    from .proposals import written_past
    us = _units(store, tid, past := written_past(store, int(tid)))
    waiting = [u for u in us if u['done'] is None]
    if not waiting: return {'live': [], 'held': [], 'n': 0, 'of': 0, 'next': '', 'units': [], 'past': past}
    front = waiting[0]
    # ...the run it is one of: the cards before it that were raised while the one before them still waited
    i = us.index(front); n = 1
    while i - n >= 0 and us[i - n + 1]['at'] <= (us[i - n]['done'] or float('inf')) + 1: n += 1
    held = [x for u in waiting[1:] for x in u['rids']]
    live = [] if _going_on(store, tid, front['at'], set(front['rids'])) else front['rids']
    if not live: held = front['rids'] + held
    return {'live': live, 'held': held, 'n': n, 'of': n + len(waiting) - 1, 'next': what(store, waiting[1]) if len(waiting) > 1 else '', 'units': waiting, 'past': past}


def mark(store, tid: int, s: dict) -> None:
    """Each card that waits marked as it is first seen waiting, in the chat's ledger: one taken back before its turn came never stands
    (conversation.items). Written where the chat is read and where the agent is told its line - never by a read of what waits on him."""
    if (ids := [x for x in s['held'] if x != LAND]):
        with store.lock: store.cx.executemany("INSERT OR IGNORE INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,'held')", [(int(tid), f'q:r:{x}') for x in ids]); store.cx.commit()


def held(store, tid: int) -> set:
    "The ids of task `tid`'s cards that wait their turn - drawn nowhere until it comes."
    return set(state(store, tid)['held']) if tid else set()


def what(store, u: dict) -> str:
    "A card in the owner's words: 'the email to erin@northwind.example', 'the reply to Gail Moreno', 'the push', 'delete the old export'."
    from . import landing
    if u['rids'] == [LAND]: return f"the {landing.HOW.get(u.get('how'), 'push').lower()}"
    rows = _waits(u) or u['rows']; r = rows[0]
    if r.get('Batch') and len(u['rows']) > 1:
        from .timewords import plural
        # ...as the card heads itself (bulkCard.countOf): "24 emails", "40 issues" - the noun of the act's own press words, else "steps"
        if r.get('Kind') == 'slot': return plural(len(rows), 'email')
        if r.get('Kind') != 'action': return f"{len(rows)} like {what(store, {'rids': [r['ReviewId']], 'rows': [{**r, 'Batch': None}]})}"
        from .connectorcatalog import action_for
        press = str((action_for(_p(r).get('type')) or {}).get('press') or '').split()
        return plural(len(rows), press[1] if len(press) == 2 else 'step')
    if r.get('Kind') == 'action':
        if (p := _p(r)).get('repo') and p.get('number') is not None: return f"{p['repo']}#{p['number']}"       # ...an issue by its own name
        why = ' '.join(str(r.get('Reason') or '').split())
        for lead in ('the agent proposes to ', 'the workflow asks to '): why = why[len(lead):] if why.lower().startswith(lead) else why
        why = why.split(': ', 1)[1] if why.startswith('held before it ran') and ': ' in why else why
        return why.split(' - ')[0][:90] or 'the next step'
    try: env = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): env = {}
    if isinstance(env, dict) and env.get('kind') == 'calendar': return 'the calendar answer'
    to = env.get('to') if isinstance(env, dict) else None
    to = ', '.join(to) if isinstance(to, list) else str(to or '')
    if not to and r.get('MessageId'): m = store.get_message(r.get('AnswersMid') or r['MessageId']) or {}; to = m.get('FromName') or m.get('FromEmail') or ''
    return f"the {'email' if r.get('Kind') == 'slot' else 'reply'}" + (f' to {to}' if to else '')


def _waits(u: dict) -> list:
    "The rows of a card that still wait - a bulk card part-run (a send that did not go, a stop) is what is left on it, not what it once held."
    return [r for r in u.get('rows') or [] if r['Status'] == 'pending']


def line(s: dict) -> str:
    "What the live card says of the line, plain: '1 of 2 · next: the email to Erin' - '' when nothing waits behind it."
    return f"{s['n']} of {s['of']} · next: {s['next']}" if s['live'] and s['of'] > s['n'] else ''


def says(store, tid: int, pressed: bool = False) -> str:
    """What the agent is told of the line: as it raises a card, while another waits too; after a press (`pressed`), whatever still waits -
    '' when nothing does."""
    us = (st := state(store, tid))['units']
    mark(store, tid, st)
    if len(us) < (1 if pressed else 2): return ''
    name = lambda u: ' + '.join(f"rv{x['ReviewId']}" for x in _waits(u)) + f" ({what(store, u)})" if u['rows'] else f"the landing question ({what(store, u)})"
    return (f"YOUR CARDS STILL WAITING, IN ORDER: {name(us[0])} {'stands in front of the owner' if st['live'] else 'is shown to the owner once this turn ends'}"
            + (f"; then {', then '.join(map(name, us[1:]))}" if len(us) > 1 else '')
            + '. Each is shown once the one before it is pressed and you have heard how it went; take back or replace one that an outcome changes.')


def said_no(store, rv: dict, verb: str, actor: str = 'owner') -> str:
    """A NO DOES NOT CARRY THE LINE ON BY ITSELF (the owner, 2026-11-16): his no to a card with others behind it wakes its agent, told whose no
    it was, to decide what of the rest still stands - what it leaves is shown once its turn ends. 'told', 'woke' or '' (nothing waits)."""
    from . import general
    from .proposals import HELD_ACTS
    tid = rv.get('TaskId')
    # ...(a held step turned down tells its agent by its own road, the gate's; and Close without sending a reply closes the task)
    if _p(rv).get('action') in HELD_ACTS or verb == 'close_unsent' and rv.get('Kind') != 'slot': return ''
    if not tid or not (rest := says(store, tid, pressed=True)): return ''
    no = {'reject': 'turned down', 'no_reply': 'said no reply is needed for', 'close_unsent': 'closed without sending', 'close_pr': 'turned down'}.get(verb, 'turned down')
    return general.tell(store, tid, f"The owner {no} rv{rv['ReviewId']} ({what(store, {'rids': [rv['ReviewId']], 'rows': [rv]})}) - their own no. {rest}", actor,
                        heard=lambda how: store.audit('review', int(rv['ReviewId']), general.TOLD, actor, 'system', {'task': int(tid), 'how': how, 'no': verb}))
