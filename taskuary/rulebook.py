"""THE FACTS THE APP KEEPS ABOUT AN ITEM (the Advisor design, phase A, 2026-10-23; a decider no more since 2026-11-02).

This was THE ONE RULEBOOK: each state lit its own button from a table, and 62% of the Advisor's rows said "left to the rule" - the model
never read the item, and an agent that finished and asked to go further lit nothing (7 of the owner's 9 dropped balls). The owner,
2026-11-02, for the hundredth time: "never ever use hard coded rules, let the ai see everything and all tools in progressive fashion and it
should work". So what is left here is FACTS: the item's state named from what the app keeps - a draft and whether it can send from here, the
agent's state, a failure, the calendar, the days waited, the lane - never the words of a mail, with the fact sentence for it (words.json
`advice_rule`: an age, a clash, a failure, a promise nothing backs).

And ONE move read off them (recommended, 2026-11-09: "the agents while running should recommend actions, no assistant"): the button a
task's row fills comes from its agent's own turn and these facts - no model, no Advisor. The Advisor judges only its own idea rows.

A sentence is only a checkable fact the card does not show, never one explaining a button ("buttons do the talking", the owner)."""
import json, re
from datetime import date, datetime, timedelta
from loguru import logger
from . import words

RULES = words.ADVICE_RULE
CHASE_DAYS = 3           # a wait past 3 working days is late (waiting_late): its agent is woken to chase (checkback.late), else Chase is lit
# a failure is the fact whatever is lit: its sentence stands on the strip where the model's own line is empty (advisor._out)
FAILED = frozenset({'failed', 'failed_cause', 'report_failed'})
EV = '_evidence'         # a fact's own ids (usual.py), carried beside the line's facts and handed on as the decision's evidence


def _dt(s):
    try: return datetime.fromisoformat(str(s or '').replace('T', ' ')[:19])
    except ValueError: return None


def working_days(since, now: datetime = None) -> int:
    """Working days from `since` to now - a Friday ask is one day old on Monday, not three."""
    a, b = (since.date() if isinstance(since, datetime) else since), (now or datetime.now()).date()
    if not a or a >= b: return 0
    return sum(1 for i in range(1, (b - a).days + 1) if (a + timedelta(days=i)).weekday() < 5)


def ago(at, now: datetime = None) -> str:
    """'40 minutes ago', '3 hours ago', 'yesterday', '4 days ago' - '' for a time nothing can read."""
    t = _dt(at)
    if not t: return ''
    # ...said by timewords, as every other age is - only "yesterday" is the line's own word
    from .timewords import ago_m
    m = max(1, ((now or datetime.now()) - t).total_seconds() // 60)
    return 'yesterday' if 1440 <= m < 2880 else ago_m(m, long=True)


def when(at, now: datetime = None) -> str:
    """'at 10:02' today, else ago() - "your reply went at 10:02; nothing since" (the owner, 2026-10-28). '' for a time nothing can read."""
    t, now = _dt(at), now or datetime.now()
    if not t: return ''
    return f'at {t:%H:%M}' if t.date() == now.date() and t <= now else ago(t, now)


def finished_quiet(store, tid, at) -> str:
    """when() the agent's work ended at `at` - '' when nothing says when, or mail reached the task since: Mark done is lit only with
    its reason, and "nothing since" must be true."""
    if not at: return ''
    # ...by when it was written, as answered() reads it (a mail filed in later is still one written before)
    try: since = store._one("SELECT 1 x FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out' AND Status NOT IN ('context','history','skipped') "
                            "AND IFNULL(Channel,'')<>'report' AND IFNULL(SentAt,CreatedAt)>? LIMIT 1", (int(tid), str(at).replace('T', ' ')[:19]))
    except Exception: since = None
    return '' if since else when(at)


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


# ONE SURVIVOR PER PAIR, DECIDED ONCE (the Advisor audit's judge, 2026-10-26): both twins lit "Remove - not a task", each naming the other -
# following the Advisor twice dropped the ask. The pair is decided once and kept (advice_decision `pair:<a>:<b>`): the one asked first
# stays, with its own move; only the other is the duplicate, folded into it. A fact, never the words: when each was asked, then how much
# each holds, then the older task.
def survivor(store, a: int, b: int) -> int:
    lo, hi = sorted((int(a), int(b)))
    key = f'pair:{lo}:{hi}'
    r = store._one('SELECT Json FROM advice_decision WHERE Key=?', (key,))
    if r:
        try:
            got = int(json.loads(r['Json'])['survivor'])
            if got in (lo, hi): return got
        except (ValueError, KeyError, TypeError): pass
    def facts(t):
        m = store._one("SELECT MIN(IFNULL(SentAt,CreatedAt)) AS at, COUNT(*) AS n FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out'", (t,)) or {}
        return (str(m.get('at') or '9999'), -int(m.get('n') or 0), t)
    got = min((lo, hi), key=facts)
    store._exec('INSERT OR REPLACE INTO advice_decision (Key, Stamp, Json, At) VALUES (?,?,?,?)',
                (key, 'pair', json.dumps({'survivor': got, 'pair': [lo, hi]}), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
    return got


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


def left_result(store, tid) -> bool:
    """Whether the task's agent left its work finished before it stopped: a done note on the board (newer than any ready note), a
    finished event no later prompt took up, or a run that kept a result - facts the app keeps, never the words of the result."""
    try:
        n = store._one("SELECT Kind FROM boardnote WHERE TaskId=? AND Kind IN ('ready','done') ORDER BY NoteId DESC LIMIT 1", (int(tid),))
        if n and n.get('Kind') == 'done': return True
        fin = store.last_worker_event(int(tid), kinds=('finished',))
        work = fin and store.last_worker_event(int(tid), kinds=('working',))
        if fin and str(fin.get('Text') or '').strip() and (not work or work['Id'] < fin['Id']): return True
        r = store._one("SELECT Result, Status FROM run WHERE TaskId=? ORDER BY RunId DESC LIMIT 1", (int(tid),)) or {}
        return bool(str(r.get('Result') or '').strip()) and r.get('Status') not in ('failed', 'error', 'running')
    except Exception as e:
        logger.debug(f'rulebook: no result read for {tid} - {e}'); return False


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


def overdue(t: dict) -> int:
    """Calendar days past the task's due day - 0 with none, or not yet."""
    try: return max(0, (date.today() - date.fromisoformat(str((t or {}).get('DueAt') or '')[:10])).days)
    except ValueError: return 0


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


def state(store, item: dict, verbs: list) -> tuple:
    """(state, facts for its sentence) - the first that holds, in the order a careful assistant would read the item. A name for where the
    item stands, never a move: the model reads it beside everything else and decides."""
    from . import advisor, concierge
    it, offered = item or {}, {v['verb'] for v in verbs or []}
    kind, lane, tid = str(it.get('kind') or ''), str(it.get('lane') or ''), it.get('tid')
    t = (store.get_task(int(tid)) or {}) if tid else {}
    if t.get('Status') in ('done', 'dropped'): return 'closed', {}
    # AN ACTION WAITS FOR THE OWNER'S YES (proposals.held_pending - a `git push` the shell gate held): read before an agent asking or at work,
    # which lit nothing over the Approve it waited on (the 2026-11-02 audit) - its Approve is lit
    from . import proposals
    if tid and (h := proposals.held_pending(store, tid)): return 'action_held', {'what': h['what'], EV: [f"rv{h['rid']}"]}
    if lane == 'working' or (tid and advisor._at_work(store, 'task', tid)): return 'working', {}
    if kind == 'agent' and (it.get('asking') or lane == 'blocked'): return 'agent_asking', {}
    # ...and a run that ENDED on a question to the owner - a restart cut it off at "go ahead?" - is still asking, not stopped: the finish
    # check read it as stopped work and lit Reply to the sender over the agent's ask (the owner, 2026-11-03)
    if tid and (kind in ('agent', 'agentdone', 'wrapup') or lane in ('stopped', 'saved')):
        from . import workerstate
        if workerstate.left_asking(store, tid): return 'agent_asking', {}
    try: f = advisor.failure(store, it)
    except Exception: f = None
    if kind == 'report' and (it.get('bad') or f): return 'report_failed', {'why': _plain_why((f or {}).get('why'), it.get('why'), default='it did not run')}
    # ...a fix named after its place, or none named and the cause for the model to read (a mail too large is redrafted, a dead address
    # is fixed, a run that hit a wall is tried again)
    if f: return ('failed' if f.get('fix') else 'failed_cause'), {'why': _plain_why(f.get('why'), f.get('what'))}
    # A WATCH THAT CAME BACK (watch.py, the owner, 2026-11-01): Mark done only where triage read the new message as handled by somebody
    # else - never closed for the owner - and a quiet week lights Chase them / Let it go; a thread that merely moved is read as any task
    from . import watch
    if (wb := watch.back(t)) == 'handled': return 'watch_handled', {'who': _name((_inbound(store, it) or [{}])[-1])}
    if wb == 'quiet': return 'watch_quiet', {}
    # THE WRITER SAID WHAT IT NEEDS (store.set_review_draft_needs): no failure - the work is an agent's, so Continue the one that worked it,
    # else Send to agent. Its reason is on the card already, so nothing is said (walk 2026-10-29: it lit "New task to fix this")
    if advisor.draft_needs(store, it) or advisor.reply_unwritten(store, it): return 'needs_agent', {}
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
        if 'approve' not in offered: return 'unsendable', {}
        try: out = leaving(store, it, draft) if draft else ''
        except Exception as e: logger.debug(f"rulebook: no recipients read for {it.get('key')} - {e}"); out = ''
        return 'draft_ready', ({'leaving': out, EV: [f"rv{draft['ReviewId']}"]} if out else {})
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
        if tid and 'review_changes' in offered and changes_waiting(store, tid): return 'unpushed', {}
        # ...its reason the newest of what ended it - the agent's last word, or the owner's reply that went - with nothing come in since
        try: sent = store.sent_reply(task_id=int(tid)) if tid else None
        except Exception: sent = None
        # ...sent from here, or TYPED OUTSIDE TASKUARY (channels.ingest_own_message: the owner's own line, Direction out): a Teams answer is
        # as much the reply as a Send here, and with neither counted the wrap card of a task answered in Teams lit nothing
        try: own = (store._one("SELECT MAX(IFNULL(SentAt,CreatedAt)) AS at FROM message WHERE TaskId=? AND Direction='out'", (int(tid),)) or {}).get('at') if tid else None
        except Exception: own = None
        went = max(str((sent or {}).get('DecidedAt') or '')[:19], str(own or '').replace('T', ' ')[:19])
        work = str(last_word(store, tid) or '')[:19] if tid else ''
        if not tid or not (went or work): return 'agent_done', {'what': '', 'when': ''}
        if went > work: return 'agent_done', {'what': 'Your reply went', 'when': finished_quiet(store, tid, went)}
        return 'agent_done', {'what': 'Finished', 'when': finished_quiet(store, tid, work)}
    # an agent stopped, saved, or paused when Taskuary stopped - its card, or the task's own row in an agent's stopped lane: its work is kept
    if kind == 'agent' or (tid and lane in ('stopped', 'saved')):
        at = last_word(store, tid) if tid else None
        # ...A STOPPED RUN THAT FINISHED ITS WORK is put down, not picked up (the Advisor audit, 2026-10-28: on a stopped agent the owner
        # pressed Continue 3 of 16 times and Mark done 11) - and one stopped with its work unfinished is carried on: its Continue is lit
        # (rulebook.MOVES; the owner, 2026-11-10: "job of agent is to be helpful and do as much as possible")
        return ('stopped_done', {'when': finished_quiet(store, tid, at)}) if tid and left_result(store, tid) else ('stopped', {'ago': ago(at)})
    if lane == 'forgotten':
        who, days = slipped(store, it, t)
        return 'waiting_late', {'who': who, 'days': days}
    if kind.startswith('goal') or (t and advisor.is_goal(t)):
        late = late_step(store, t) if t else None
        return ('goal_late', {'step': late[0], 'days': late[1]}) if late else ('goal', {})
    if lane == 'theirs' and t:
        who, days = waited(store, it, t)
        # ONE CLOCK WITH THE HEADER (the Advisor audit's judge, 2026-10-26): "Due Oct 24, 2 days late" stood over a lit Remind me, and the
        # chase line said "this is 4 days" counted from the ask - a wait with a due day past is late by the days past it, as the header
        # counts them (taskLayout.waitingOn) and a goal's late step does (late_step), and Chase is lit
        if (late := overdue(t)) > 0: return 'waiting_overdue', {'who': who, 'days': late}
        # ...LEARNED PER PERSON (ruling 8): once three of their answers say how soon this person answers, a silence is late on THEIR day,
        # and the line says their usual beside this wait (usual.chase_usual) - before that, the three working days stand
        from . import usual
        held = next((str(x).split(':', 1)[-1].strip().lower() for x in (t.get('WaitingOn'), t.get('Assignee')) if '@' in str(x or '')), '')
        u = usual.chase_usual(store, held) if held else None
        if u: return ('waiting_late_usual', {'who': who, 'days': days, 'usual': usual.days(u['median'])}) if days >= u['days'] else ('waiting', {})
        return ('waiting_late', {'who': who, 'days': days}) if days >= CHASE_DAYS else ('waiting', {})
    if kind == 'idea': return 'idea', {}
    # A PHISH FILED FYI IS PUT DOWN, NEVER HANDED ON (the owner, 2026-10-30): its row lit Send to agent - the one press that feeds a scam to
    # an agent. Not ours is its move, at once and with no model read, and Send to agent waits in the ▾ (FyiCard's Foot `tuck`)
    if kind == 'fyi' and it.get('danger'): return 'fyi_danger', {}
    if kind == 'fyi': return 'fyi', {}
    ins = _inbound(store, it)
    if ins:
        from .remote_assistant import stranger_held
        if stranger_held(store, it):
            who = str(ins[-1].get('FromEmail') or '').lower()
            if '@' in who: return 'stranger', {'domain': who.rsplit('@', 1)[1]}
        dup = same_thread(store, it) if tid else None
        # ...the survivor of the pair keeps its own move; only the other is the duplicate, and its line names the one that stays
        if dup and offered & {'split', 'remove'} and (keep := survivor(store, tid, dup)) != int(tid):
            from .store import task_ref
            return 'duplicate', {'ref': task_ref(keep)}
        # LATE FOR THIS PERSON, BY THE OWNER'S OWN USUAL (the owner, 2026-10-25: "Reply: you usually answer Erin within the hour; this is
        # 3h") - one line, the reason beside the lit Reply, counted from the answers it cites (usual.late_reply)
        # THE OWNER ALREADY ANSWERED (trust audit A3, 2026-10-28): their own reply went after the sender's newest message, so nobody is
        # waiting - Mark done, as the model's prompt says ("someone is waiting only when they wrote again after it"); Reply lit there
        # offered to say twice what was said
        if (went := answered(store, it, ins[-1])): return 'answered', {'when': when(went)}
        from . import usual
        if (late := usual.late_reply(store, ins[-1])):
            return 'asked_late', {'who': late['who'], 'usual': late['usual'], 'age': late['age'], EV: late['evidence']}
        return 'asked', {'who': _name(ins[-1]), 'ago': ago(ins[-1].get('SentAt') or ins[-1].get('CreatedAt'))}
    if t and (cl := advisor._checklist(t)) and all(c.get('done') for c in cl): return 'done_list', {'n': len(cl)}
    if t and untouched(store, t): return 'untouched', {}
    return 'own', {}


# UNTOUCHED TOO LONG (the design rev 2: "an ask with no answer, a promise past its day" - the owner, 2026-10-28: "there to hold your hand
# when something was dropped"): an open task of the owner's own that nothing has moved for UNTOUCHED_DAYS working days. That it sat is a
# fact the app keeps; WHAT is still owed on it, to whom, and the move that gets it going are the model's to read (the UNTOUCHED line
# in its prompt) - never a word list.
UNTOUCHED_DAYS = 5


def untouched(store, t: dict) -> int:
    """Working days nothing has moved on an open task - its own change, a message on it, its agent's last word - or 0 under UNTOUCHED_DAYS."""
    if not t or t.get('Status') not in ('open', 'in_progress'): return 0
    m = store._one('SELECT MAX(IFNULL(SentAt,CreatedAt)) AS at FROM message WHERE TaskId=?', (int(t['TaskId']),)) or {}
    ats = [a for a in (_dt(t.get('UpdatedAt')), _dt(t.get('CreatedAt')), _dt(m.get('at')), _dt(last_word(store, t['TaskId']))) if a]
    n = working_days(max(ats)) if ats else 0
    return n if n >= UNTOUCHED_DAYS else 0


# WHAT LEAVES WITH A DRAFT (the design rev 2, data leaving; the owner, 2026-10-28: "a line on top ... it should recommend action", never a
# new dialog): before Send, an address the thread never had and the files the draft carries are said in one line beside the lit Send.
# Addresses and files are facts the draft's envelope keeps - read the way the send will read them (verdicts._deliver_review) - never words.
def recipients(store, rv: dict) -> list:
    """The addresses a draft will go to, lowercased: its own envelope's To and Cc when it is new mail or a reply with its people set, else
    whom a reply to its message goes to (outbound.reply_envelope)."""
    from . import outbound
    try: env = json.loads(rv.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): env = {}
    env = env if isinstance(env, dict) else {}
    if not env.get('to') and (env.get('kind') == 'reply' or not env.get('channel')):
        m = store.get_message(int(rv['MessageId'])) if rv.get('MessageId') else None
        env = {**(outbound.reply_envelope(store, m) or {}), **({'cc': env['cc']} if env.get('cc') is not None else {})}
    return [str(a).strip().lower() for a in [*(env.get('to') or []), *(env.get('cc') or [])] if '@' in str(a or '')]


def leaving(store, item: dict, rv: dict) -> str:
    """'' or the line: who on the draft is new to its thread, and the files it sends."""
    from . import advisor, learned_cut
    from .ingest import owner_addresses, own_addresses
    tk, ti = ('task', item['tid']) if item.get('tid') else ('message', rv.get('MessageId') or item.get('mid'))
    known = {a for m in advisor._msgs(store, item, tk, ti) for a in learned_cut.people_of(m)} | owner_addresses(store) | own_addresses(store)
    new = [a for a in dict.fromkeys(recipients(store, rv)) if a not in known]
    try: files = [f.get('name') for f in (json.loads(rv.get('Deliver') or '{}') or {}).get('attachments') or [] if isinstance(f, dict) and f.get('name')]
    except (TypeError, ValueError, AttributeError): files = []
    who = ', '.join(new[:2]) + (f' +{len(new) - 2}' if len(new) > 2 else '')
    sends = (f'{len(files)} files' if len(files) > 1 else f'the file {files[0]}') if files else ''
    if new and files: return f'Goes to {who}, new to this thread, with {sends}.'
    if new: return f'Goes to {who} - new to this thread.'
    return f"Sends {sends}{': ' + ', '.join(files[:3]) if len(files) > 1 else ''}." if files else ''


def last_word(store, tid):
    """When the task's agent last did anything: its newest event on the board, else its headless run's last update."""
    try: return (store._one('SELECT MAX(at) AS at FROM (SELECT MAX(CreatedAt) AS at FROM worker_event WHERE TaskId=? UNION ALL '
                            'SELECT MAX(IFNULL(FinishedAt, UpdatedAt)) FROM run WHERE TaskId=?)', (int(tid), int(tid))) or {}).get('at')
    except Exception: return None


def answered(store, item: dict, last_in: dict):
    """When the owner's own reply - one sent from here (its review) or typed anywhere (an outgoing message) - went after `last_in`, the
    newest such; None when none did."""
    from . import advisor
    tid, mid = item.get('tid'), item.get('mid')
    try: r = store.sent_reply(task_id=int(tid)) if tid else store.sent_reply(message_id=int(mid)) if mid else None
    except Exception: r = None
    try: outs = [m for m in advisor._msgs(store, item, 'task' if tid else 'message', tid or mid) if str(m.get('Direction') or 'in') == 'out']
    except Exception: outs = []
    last = _dt(last_in.get('SentAt') or last_in.get('CreatedAt'))
    ats = [_dt((r or {}).get('DecidedAt') or (r or {}).get('CreatedAt'))] + [_dt(m.get('SentAt') or m.get('CreatedAt')) for m in outs]
    went = [a for a in ats if a and last and a > last]
    return max(went) if went else None


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


def facts(store, item: dict, verbs: list) -> dict:
    """{state, line, evidence?} - where the item stands and the checkable fact said for it ('' when a fact it needs is not known),
    with the ids it rests on. Read by the Advisor's prompt; nothing here lights a button.
    Never raises: facts that cannot be read are the plain 'own'."""
    try: st, f = state(store, item, verbs)
    except Exception as e:
        logger.warning(f"rulebook: no facts read for {(item or {}).get('key')} - {e}"); st, f = 'own', {}
    ev = f.pop(EV, None) or []
    line = _cut(_say(st, **f), 64)
    return {'state': st, 'line': line, **({'evidence': ev} if ev and line else {})}


# ── THE TASK'S RECOMMENDED MOVE (the owner, 2026-11-09) ─────────────────────────────────────────────────────────────────────────────
# The Advisor read every task with a model and lit a button over the agent's own word (its finish check was right 7% of the time). Now the
# one filled button is read off what the task already says, the same for every kind and brain: a held action's Approve; a failed run's own
# way past it (the row's lead: the place that fixes it, or Try again); the Send of a draft that waits on the owner - whoever wrote it, an
# agent or triage - never one whose channel is not connected; Mark done where the agent's turn summary said nothing is left; and with no
# summary at all (a coding agent's terminal writes none, and a task no agent touched has none) Mark done where the facts say it is over.
# An agent at work or asking fills nothing: its own pane is the way on.
OVER = frozenset({'agent_done', 'stopped_done', 'answered', 'done_list', 'watch_handled'})
QUIET = frozenset({'closed', 'working', 'agent_asking'})
# an answer owed to the owner gone late: its agent is woken once to draft the chase (checkback.late), and where none was, Chase is lit
LATE = frozenset({'waiting_late', 'waiting_overdue', 'waiting_late_usual', 'goal_late', 'watch_quiet'})
NOTHING_LEFT = 'Its agent said nothing is left to do'
# THE MOVE A STATE'S OWN FACT NAMES (the owner, 2026-11-10: "job of agent is to be helpful and do as much as possible. it shoudl prompt you,
# should i deploy"): these lit nothing, and their line was hidden too - work left unpushed is looked at, an agent stopped with its work
# unfinished is carried on, and an ask no agent started on is handed to one, as needs_agent is
MOVES = {'unpushed': ('review_changes',), 'stopped': ('continue',), 'asked': ('regular_agent',), 'asked_late': ('regular_agent',)}


def landing_asks(store, tid) -> bool:
    """Whether the task's landing card asks its question - Push, or how its branch lands (landing.state) - whose own first button is filled
    there: the row lights nothing over it. Read only for work left unpushed."""
    from . import landing
    try: return bool(tid) and (landing.asked(store, tid) or bool((landing.state(store, int(tid)) or {}).get('ask')))
    except Exception as e: logger.debug(f'rulebook: no landing read for {tid} - {e}'); return False


def agent_word(store, tid) -> str | None:
    """What the agent's newest turn summary (general.SUMMARY_TYPE) leaves the owner: 'on_you' while a step of its list is theirs,
    'nothing_left' where it said so, '' where it said neither - and None with no summary (no agent ran, or one that writes none)."""
    from . import advisor, general
    try:
        last = next((c for c in reversed(store.list_comments(int(tid), internal=True)) if c.get('ActorType') == general.SUMMARY_TYPE), None)
        summ = json.loads(last['Body']) if last else None
    except (TypeError, ValueError, KeyError): summ = None
    if not isinstance(summ, dict): return None
    if any(c.get('on_you') and not c.get('done') and c.get('text') for c in advisor._checklist(store.get_task(int(tid)))): return 'on_you'
    return 'nothing_left' if summ.get('nothing_left') else ''


def _recommended(store, it: dict, verbs: list | None, f: dict | None) -> dict | None:
    from . import advisor, checkback
    if it.get('kind') == 'idea': return None                # an idea is the Advisor's own row, and its light the Advisor's
    verbs = advisor.offered(store, it) if verbs is None else verbs
    f = f or facts(store, it, verbs)
    st, tid, lead = f['state'], it.get('tid'), (verbs[0]['verb'] if verbs else '')
    pick = lambda *vs: next((v for v in vs if not advisor.pressable(store, it, v, verbs)), None)
    why = f.get('line') or ''
    if st in QUIET: v = None
    # ...a reply owed that nothing has written, on a task no agent started on by itself (the setting, a stranger held, no room): the
    # agent writes it now, so its start is the move - the one that worked it before, else Send to agent (the owner, 2026-11-10)
    elif st == 'needs_agent': v = pick('continue', 'regular_agent')
    elif st == 'action_held': v = None if advisor.unconnected(store, it) else pick('approve', 'send_close')
    # ...what failed is never sent again as it stood: its own fix or Try again where the row leads with one, else nothing
    elif lead == 'fix' or st in FAILED: v = pick(lead) if lead in ('fix', 'continue') else None
    elif st == 'draft_ready' or ((w := store.waiting_on_owner(int(tid)) if tid else None) and (w.get('FinalText') or w.get('DraftText'))):
        v = None if advisor.unconnected(store, it) else pick('send_close', 'approve')
    # ...a late answer no agent was woken for is chased from the row (the owner, 2026-11-10: "job of agent is to be helpful and do as much as
    # possible") - over an older turn's word too; one that was woken says itself what it did about it
    elif st in LATE and not (tid and checkback.woke(store, tid)): v = pick('chase')
    # ...the agent's own word decides wherever it wrote one: a turn that said neither fills nothing, whatever the facts read
    elif tid and (said := agent_word(store, tid)) is not None: v, why = (pick('close'), NOTHING_LEFT) if said == 'nothing_left' else (None, '')
    # ...and with no word of an agent's over it, the move the state's own fact names (MOVES)
    else: v = pick('close') if st in OVER else None if st == 'unpushed' and landing_asks(store, tid) else pick(*MOVES.get(st, ()))
    return {'verb': v, 'label': advisor._label(verbs, v, it), 'why': why, 'state': st} if v else None


def recommended(store, item: dict, verbs: list = None, f: dict = None) -> dict | None:
    """{verb, label, why, state} - the one move the item's row fills - or None for nothing filled. `verbs`: the row's buttons where the
    caller read them already (advisor.offered); `f`: its facts. Never raises: a row that cannot be read fills nothing."""
    from . import advisor
    try:
        with advisor.reading(): return _recommended(store, item or {}, verbs, f) if item else None
    except Exception as e:
        logger.warning(f"rulebook: no recommended move for {(item or {}).get('key')} - {e}"); return None


def recommended_task(store, tid, known: dict = None) -> dict | None:
    """The same for a task by its id (the task page's own payload): its card as the rail last stood, never a rail build. `known`: what
    the page's read holds of the task already (concierge._shows, and its `messages`) - that read is made on every live write while an
    agent works."""
    from . import advisor
    known = dict(known or {})
    with advisor.reading({int(tid): known.pop('messages')} if 'messages' in known else None):
        try:
            item = advisor._item(store, 'task', int(tid), build=False)
            verbs = advisor.offered(store, item, known) if item and item.get('kind') != 'idea' else None
        except Exception as e:
            logger.debug(f'rulebook: no card for task {tid} - {e}'); item = verbs = None
        return recommended(store, item, verbs)


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
    # ...from somebody who reads a reply (wrapup.reads_replies, the stress round 2026-11-10): a signing service's "viewed" or a list's digest
    # filed on the task since was the newest mail, and Chase named the machine
    from .wrapup import reads_replies
    m = next((x for x in store._rows("SELECT MessageId, FromEmail, Channel, SenderClass, Status FROM message WHERE TaskId=? AND IFNULL(Direction,'in')<>'out' "
                                     "AND Status!='context' AND IFNULL(FromEmail,'')<>'' AND lower(FromEmail)<>? AND (?='' OR lower(FromEmail)=?) "
                                     'ORDER BY IFNULL(SentAt,CreatedAt) DESC LIMIT 50', (tid, me, held, held)) if reads_replies(x)), None)
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


def quiet_watch(store, item: dict) -> bool:
    """A watched task back after a quiet week (watch.py 'quiet') - where Chase them and Let it go are its answers until the owner's move."""
    from . import watch
    try: return watch.back(store.get_task(int(item['tid'])) if item.get('tid') else None) == 'quiet'
    except Exception: return False


def adds(store, item: dict) -> list:
    """The verbs the row draws only when they are its lit move: Chase on every waiting lane and goal with somebody to write to (the
    design's "Chase (offered on every waiting lane)" and "(added to goals)") - lit once the wait is late (LATE) and no agent was woken to
    chase it; Let it go on a watch back after a quiet week. The task's row draws a lit Chase (TaskPage's `chase` verb); the phone already
    carries it on the slipped lane."""
    it = item or {}
    lane, kind = it.get('lane'), str(it.get('kind') or '')
    if it.get('tid') and quiet_watch(store, it): return (['chase'] if chase_thread(store, it) else []) + ['let_go']
    if lane not in ('theirs', 'forgotten') and not kind.startswith('goal'): return []
    try: return ['chase'] if lane == 'forgotten' or chase_thread(store, it) else []
    except Exception: return []
