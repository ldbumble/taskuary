"""THE ONE RULEBOOK (the Advisor design, phase A; the owner's rulings 2026-10-23).

Four pieces of code chose the item's move - the Advisor's model, the row's own fallbacks, the Tasks tab's always-dark Mark done and the
phone's primary() - and they disagreed on 6 of 21 states; on the phone Send led on a draft the desk said not to send. Here each state is
decided once, from FACTS THE APP KEEPS - a draft and whether it can send from here, the agent's state, a failure, the calendar, the days
waited, the lane - never the words of a mail (the owner: no hardcoded keyword lists; the model reads intent). A rule answers at once, with
no "Thinking...", and costs nothing against the hourly model cap. Where intent must be read (an ask that is really work or someone else's,
a draft promising what nothing shows, a duplicate by subject, a buried ask, an idea) the rule's button is lit at once and the state says
`ask`: the model may change it (advisor.decide).

What each state says and lights is words.json `advice_rule` - the same on every surface. "Obvious move -> the strip is EMPTY and one
button is lit" (the owner, 2026-10-23): a line is only a checkable fact the card does not show - an age, a clash, a failure, a promise
nothing backs - and never a sentence explaining the button ("buttons do the talking", "I hate free text")."""
import json, re
from datetime import date, datetime, timedelta
from loguru import logger
from . import words

RULES = words.ADVICE_RULE
CHASE_DAYS = 3           # the owner, 2026-10-23: "Chase lights after 3 working days, then learned per person" (the per person is phase E)
# states no habit may change (the owner, 2026-10-23: "a habit only lights a button ... never a safety rule"): what failed is fixed before
# anything else, an agent asking is answered in its pane, a closed or working item has no move of the owner's
SAFE = frozenset({'closed', 'working', 'agent_asking', 'failed', 'failed_cause', 'report_failed', 'unsendable'})
FAILED = frozenset({'failed', 'failed_cause', 'report_failed'})
# where the lit move needs an AI to work: with none connected the strip asks for one there, and only there
NEEDS_AI = frozenset({'asked', 'stranger'})


def asks(state: str) -> bool: return bool((RULES.get(state) or {}).get('ask'))


def _dt(s):
    try: return datetime.fromisoformat(str(s or '').replace('T', ' ')[:19])
    except ValueError: return None


def working_days(since, now: datetime = None) -> int:
    """Working days from `since` to now - a Friday ask is one day old on Monday, not three."""
    a, b = (since.date() if isinstance(since, datetime) else since), (now or datetime.now()).date()
    if not a or a >= b: return 0
    return sum(1 for i in range(1, (b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)


def ago(at, now: datetime = None) -> str:
    """'40 min ago', '3 hours ago', 'yesterday', '4 days ago' - '' for a time nothing can read."""
    t = _dt(at)
    if not t: return ''
    s = max(0, int(((now or datetime.now()) - t).total_seconds()))
    if s < 3600: return f'{max(1, s // 60)} min ago'
    if s < 86400: return f"{s // 3600} hour{'s' if s >= 7200 else ''} ago"
    d = s // 86400
    return 'yesterday' if d == 1 else f'{d} days ago'


def _say(state: str, **facts) -> str:
    """The state's line with its facts - '' when a fact it needs is not known: a line is a fact, never "Stopped partway"."""
    t = (RULES.get(state) or {}).get('line') or ''
    if not t or any(v in (None, '') for v in facts.values()): return ''
    try: return t.format(**facts)
    except (KeyError, IndexError): return ''


def _cut(s, n: int) -> str:
    s = ' '.join(str(s or '').split())
    return s if len(s) <= n else s[:n - 1].rstrip() + '…'


def _inbound(store, item) -> list:
    from . import advisor
    tk = 'task' if item.get('tid') else 'message'
    try: ms = advisor._msgs(store, item, tk, item.get('tid') or item.get('mid'))
    except Exception: ms = []
    return [m for m in ms if m and str(m.get('Direction') or 'in') != 'out' and m.get('Status') not in ('context',)]


def _name(m: dict) -> str: return ' '.join(str(m.get('FromName') or m.get('FromEmail') or 'Someone').split())


def same_thread(store, item) -> int | None:
    """Another open task on this item's own conversation - the one duplicate a FACT shows. The same sender alone no longer counts
    (the design, 2026-10-23): one person asks for many things, and "TQ-0006 may already cover it" stood over unrelated asks."""
    ms = _inbound(store, item)
    cids = {m['ConversationId'] for m in ms if m.get('ConversationId')}
    if not cids: return None
    own = item.get('tid')
    r = store._one(f"SELECT m.TaskId FROM message m JOIN task t ON t.TaskId=m.TaskId WHERE t.Status NOT IN ('done','dropped') AND m.ConversationId IN "
                   f"({','.join('?' * len(cids))}) AND m.TaskId<>? ORDER BY m.TaskId LIMIT 1", (*cids, int(own or 0)))
    return int(r['TaskId']) if r else None


def changes_waiting(store, tid) -> bool:
    """Work an agent left that is not pushed, as the app knows it without asking git: the agent's own note on the board saying it is
    ready to push and nothing after it saying done, or a run that finished with a diff."""
    try:
        n = store._one("SELECT Kind FROM boardnote WHERE TaskId=? AND Kind IN ('ready','done') ORDER BY NoteId DESC LIMIT 1", (int(tid),))
        if n and n.get('Kind') == 'ready': return True
        r = store._one("SELECT 1 x FROM run WHERE TaskId=? AND IFNULL(DiffText,'')<>'' AND Status IN ('done','finished','succeeded') LIMIT 1", (int(tid),))
        return bool(r)
    except Exception as e:
        logger.debug(f'rulebook: no changes read for {tid} - {e}'); return False


def calendar_on(store) -> bool:
    from . import demo, calendar
    try: return demo.enabled() or calendar.reachable(store)
    except Exception: return False


def waited(store, item, t: dict) -> tuple:
    """(who, working days) a task waiting on someone else has waited: since the owner last wrote on it, else since it was set waiting."""
    from . import waiton
    from .processing_unread import holder_name
    who = (waiton.name_of(t['WaitingOn']) if t.get('WaitingOn') else holder_name(t.get('Assignee'))) or ''
    out = store._one("SELECT SentAt, CreatedAt FROM message WHERE TaskId=? AND Direction='out' ORDER BY IFNULL(SentAt,CreatedAt) DESC LIMIT 1",
                     (int(t['TaskId']),)) or {}
    since = _dt(out.get('SentAt') or out.get('CreatedAt')) or _dt(t.get('WaitingSince')) or _dt(t.get('UpdatedAt')) or _dt(t.get('CreatedAt'))
    return who or 'They', working_days(since) if since else 0


def late_step(store, t: dict) -> tuple | None:
    """(the step said with whose it is, days late) - the latest step of a goal past its day, or None."""
    from .processing_unread import holder_name
    today, best = date.today(), None
    for x in store.goal_steps(int(t['TaskId'])):
        c = x.get('child') or {}
        if x['done'] or not str(c.get('DueAt') or '')[:10]: continue
        try: due = date.fromisoformat(str(c['DueAt'])[:10])
        except ValueError: continue
        late = (today - due).days
        if late <= 0 or (best and best[1] >= late): continue
        who, step = holder_name(c.get('Assignee')), _cut(x['text'], 40)
        # "Ray Colton's schema sign-off" - unless the step already names them ("Ray: schema sign-off")
        best = (f"{who}'s {step}" if who and not step.lower().startswith(who.split()[0].lower()) else step, late)
    return best


def _lit(state: str, offered: set) -> str | None:
    """The first of the state's verbs the row draws; Next when none is; None where the state lights nothing."""
    want = (RULES.get(state) or {}).get('lit') or []
    if not want: return None
    return next((v for v in want if v in offered or v == 'next'), 'next')


def state(store, item: dict, verbs: list) -> tuple:
    """(state, facts for its line) - the first rule that holds, in the order a careful assistant would read the item."""
    from . import advisor, concierge
    it, offered = item or {}, {v['verb'] for v in verbs or []}
    kind, lane, tid = str(it.get('kind') or ''), str(it.get('lane') or ''), it.get('tid')
    t = (store.get_task(int(tid)) or {}) if tid else {}
    if t.get('Status') in ('done', 'dropped'): return 'closed', {}
    if lane == 'working' or (tid and advisor._at_work(store, 'task', tid)): return 'working', {}
    if kind == 'agent' and (it.get('asking') or lane == 'blocked'): return 'agent_asking', {}
    try: f = advisor.failure(store, it)
    except Exception: f = None
    if kind == 'report' and (it.get('bad') or f): return 'report_failed', {'why': _plain_why((f or {}).get('why'), it.get('why'), default='it did not run')}
    # ...the fix named after its place is the way past it, at once; with none named, the model reads the cause (a mail too large is
    # redrafted, a dead address is fixed, a run that hit a wall is tried again) while the rule's Try again / New task stands lit
    if f: return ('failed' if f.get('fix') else 'failed_cause'), {'why': _plain_why(f.get('why'), f.get('what'))}
    # A DASHBOARD's refresh lands under Reports like a report run and Next walks past it (the owner, 2026-10-23): looked at, never acted
    # on - so silent, Next lit. Its Share (and a report's) is on the row for the Advisor to SEE, never the move a rule lights: sending a
    # result somewhere is the owner's own idea, not the obvious next step
    if kind == 'report': return ('dashboard' if it.get('dashboard') else 'report_ok'), {}
    if kind == 'fyis': return 'fyi_batch', {}
    if kind == 'meeting': return 'meeting', {}
    if kind == 'connection': return 'connection', {}
    if lane == 'unjudged': return 'unsorted', {}
    tk = 'task' if tid else 'message'
    try: draft = advisor._draft(store, it, tk, tid or it.get('mid')) if (tid or it.get('mid')) else None
    except Exception: draft = None
    if draft or it.get('closeout') or kind == 'action':
        return ('draft_ready', {}) if 'approve' in offered else ('unsendable', {})
    inv, _meet = concierge.calendar_asks(store, it)
    if inv:
        if not calendar_on(store): return 'invite_no_cal', {}
        from . import calwrite
        try:
            c = calwrite.invite_of(store.get_message(int(it['mid'])) or {}) or {}
            clash = calwrite.clash_line(store, c['start'], c['end'], skip=c.get('subject') or '') if c.get('start') and not c.get('all_day') else ''
        except Exception as e: logger.debug(f'rulebook: no clash read - {e}'); clash = ''
        return ('invite_clash', {'clash': _cut(clash[:1].upper() + clash[1:], 58)}) if clash else ('invite_free', {})
    if kind in ('agentdone', 'wrapup'):
        return ('unpushed', {}) if tid and 'review_changes' in offered and changes_waiting(store, tid) else ('agent_done', {})
    # an agent stopped, saved, or paused when Taskuary stopped - its card, or the task's own row in an agent's stopped lane: its work is kept
    if kind == 'agent' or (tid and lane in ('stopped', 'saved')):
        # when it stopped: its last word on the board of events, else its headless run's last update
        try: at = (store._one('SELECT MAX(at) AS at FROM (SELECT MAX(CreatedAt) AS at FROM worker_event WHERE TaskId=? UNION ALL '
                              'SELECT MAX(IFNULL(FinishedAt, UpdatedAt)) FROM run WHERE TaskId=?)', (int(tid), int(tid))) or {}).get('at') if tid else None
        except Exception: at = None
        return 'stopped', {'ago': ago(at)}
    if lane == 'forgotten':
        who, days = slipped(store, it, t)
        return 'waiting_late', {'who': who, 'days': days}
    if kind.startswith('goal') or (t and advisor.is_goal(t)):
        late = late_step(store, t) if t else None
        return ('goal_late', {'step': late[0], 'days': late[1]}) if late else ('goal', {})
    if lane == 'theirs' and t:
        who, days = waited(store, it, t)
        return ('waiting_late', {'who': who, 'days': days}) if days >= CHASE_DAYS else ('waiting', {})
    if kind == 'idea': return 'idea', {}
    if kind == 'fyi': return 'fyi', {}
    ins = _inbound(store, it)
    if ins:
        from .remote_assistant import stranger_held
        if stranger_held(store, it):
            who = str(ins[-1].get('FromEmail') or '').lower()
            if '@' in who: return 'stranger', {'domain': who.rsplit('@', 1)[1]}
        dup = same_thread(store, it) if tid else None
        if dup and 'remove' in offered:
            from .store import task_ref
            return 'duplicate', {'ref': task_ref(dup)}
        return 'asked', {'who': _name(ins[-1]), 'ago': ago(ins[-1].get('SentAt') or ins[-1].get('CreatedAt'))}
    if t and (cl := advisor._checklist(t)) and all(c.get('done') for c in cl): return 'done_list', {}
    return 'own', {}


def slipped(store, item: dict, t: dict) -> tuple:
    """(who, days quiet) of a slipped follow-up or a step a person owes past its day."""
    from . import funnel
    from .processing_unread import holder_name
    iid = re.match(r'^idea:(\d+)$', str(item.get('key') or ''))
    if item.get('kind') == 'idea' and iid:
        i = store.get_idea(int(iid.group(1))) or {}
        try: a = json.loads(i.get('ActionJson') or '{}') or {}
        except ValueError: a = {}
        try: _l, _late, quiet, _day = funnel.slipped_followup(store, a)
        except Exception: quiet = 0
        return holder_name('person:' + str(a.get('who_email') or '')) or 'They', quiet
    # ...the processing rail's card for a slipped thread names whom it waits on (who_email); a step a person owes, its holder
    who = holder_name('person:' + item['who_email']) if item.get('who_email') else holder_name(t.get('Assignee')) if t else ''
    due = _dt(str(t.get('DueAt') or '')[:10] + ' 00:00') if t and str(t.get('DueAt') or '')[:10] else None
    if not due and t:                                             # ...else quiet since the owner last wrote on it
        o = store._one("SELECT IFNULL(SentAt,CreatedAt) AS at FROM message WHERE TaskId=? AND Direction='out' ORDER BY 1 DESC LIMIT 1", (int(t['TaskId']),)) or {}
        due = _dt(o.get('at'))
        if not due:
            m = store._one("SELECT MIN(IFNULL(SentAt,CreatedAt)) AS at FROM message WHERE TaskId=?", (int(t['TaskId']),)) or {}
            due = _dt(m.get('at'))
    return who or 'They', working_days(due) if due else int(item.get('late_days') or 0)


def decide(store, item: dict, verbs: list) -> dict:
    """{state, verb, line, ask} - the rule's move for the item: the verb lit, the line the strip says ('' is silent) and whether the
    model may change it. Never raises: a rule that cannot read its facts lights Next and says nothing."""
    try: st, facts = state(store, item, verbs)
    except Exception as e:
        logger.warning(f"rulebook: {(item or {}).get('key')} not decided - {e}"); st, facts = 'own', {}
    offered = {v['verb'] for v in verbs or []}
    verb = _lit(st, offered)
    # a line only over the move it is the fact for: "Erin Blake asked yesterday" over a lit Next would be a reason for another button
    # ...save what failed: the failure is the fact whatever is lit - the demo's refused Send leaves only Next, and "Failed: ..." over it
    line = _say(st, **facts) if verb and (verb != 'next' or st in FAILED) else ''
    # ...and an age under a day is on the card already ("2h"): the line speaks from yesterday on
    if st == 'asked' and not re.search(r'yesterday|days ago', line): line = ''
    return {'state': st, 'verb': verb, 'line': _cut(line, 64), 'ask': asks(st)}


def chase_thread(store, item: dict) -> dict | None:
    """WHERE A CHASE GOES for a wait the rule calls late but no follow-up ledger slipped (the 'theirs' lane past CHASE_DAYS working
    days, a goal step past its day): {tid, who, mid} - the task the wait is on (the goal's late step, not the goal), the address it
    waits on, and their newest mail on it to answer (mid None: the chase is a new message to them from the task). None when nobody's
    address is known: a Chase with nobody to write to is a button that can only be refused (the dead-end sweep, 2026-10-23), so it is
    not lit. The slipped lane keeps its own road (server task.chase)."""
    it = item or {}
    tid = it.get('tid')
    t = store.get_task(int(tid)) if tid else None
    if not t: return None
    if str(it.get('kind') or '').startswith('goal') or advisor_goal(t):
        today, best = date.today(), None
        for x in store.goal_steps(int(t['TaskId'])):
            c = x.get('child') or {}
            try: late = (today - date.fromisoformat(str(c.get('DueAt') or '')[:10])).days
            except ValueError: continue
            if not x['done'] and c.get('TaskId') and late > 0 and (not best or late > best[1]): best = (c, late)
        if not best: return None
        t = best[0]
    tid = int(t['TaskId'])
    held = next((str(x).split(':', 1)[-1] for x in (t.get('WaitingOn'), t.get('Assignee')) if '@' in str(x or '')), '').strip().lower()
    me = str(store.get_setting('owner_email') or '').strip().lower()
    m = store._one("SELECT MessageId, FromEmail FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out' AND Status!='context' "
                   "AND IFNULL(FromEmail,'')<>'' AND lower(FromEmail)<>? AND (?='' OR lower(FromEmail)=?) ORDER BY IFNULL(SentAt,CreatedAt) DESC LIMIT 1",
                   (tid, me, held, held))
    who = str((m or {}).get('FromEmail') or held or '').lower()
    return {'tid': tid, 'who': who, 'mid': int(m['MessageId']) if m else None} if '@' in who else None


def advisor_goal(t: dict) -> bool:
    from . import advisor
    try: return bool(advisor.is_goal(t))
    except Exception: return False


def _plain_why(*said, default: str = 'it stopped without saying why') -> str:
    """The first reason that is the owner's words: a raw refusal ("needs a repository first - working directory ...") is ours, said
    on the card's own failure box where its fix is - the line says what failed in plain words, or nothing it cannot say plainly."""
    return next((_cut(w, 60) for w in said if w and not words.jargon_in(w)), default)


def adds(store, item: dict) -> list:
    """The verbs a state lights that the row draws only when the Advisor names them: Chase on a waiting item past its day and on a late
    goal step - the design's "Chase (offered on every waiting lane)" and "(added to goals)". The row draws the advised move in its type
    (ActionRow.AdvisorNext); the phone already carries it on the slipped lane."""
    it = item or {}
    lane, kind = it.get('lane'), str(it.get('kind') or '')
    if lane not in ('theirs', 'forgotten') and not kind.startswith('goal'): return []
    try: st, _f = state(store, it, [{'verb': 'chase'}])
    except Exception: return []
    if st not in ('waiting_late', 'goal_late'): return []
    return ['chase'] if lane == 'forgotten' or chase_thread(store, it) else []
