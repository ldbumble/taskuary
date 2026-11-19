"""THE FACTS THE APP KEEPS ABOUT AN ITEM (the Advisor design, phase A, 2026-10-23; a decider no more since 2026-11-02).

This was THE ONE RULEBOOK: each state lit its own button from a table, and 62% of the Advisor's rows said "left to the rule" - the model
never read the item, and an agent that finished and asked to go further lit nothing (7 of the owner's 9 dropped balls). The owner,
2026-11-02, for the hundredth time: "never ever use hard coded rules, let the ai see everything and all tools in progressive fashion and it
should work". So what is left here is FACTS: the item's state named from what the app keeps - a draft and whether it can send from here, the
agent's state, a failure, the calendar, the days waited, the lane - never the words of a mail, with the fact sentence for it (words.json
`advice_rule`: an age, a clash, a failure, a promise nothing backs).

And ONE move read off them (recommended, 2026-11-09: "the agents while running should recommend actions, no assistant"): the button a
task's row fills comes from its agent's own turn and these facts - no model, no Advisor; an idea row fills none (the owner, 2026-11-15:
"remove the entire advisor from buttons thing"). The row's real buttons (offered), what failed on it (failure) and the one decision every
surface reads (decide) live here too, at the end.

A sentence is only a checkable fact the card does not show, never one explaining a button ("buttons do the talking", the owner)."""
import contextlib, contextvars, hashlib, json, re
from datetime import date, datetime, timedelta
from loguru import logger
from . import buttons, concierge, words

RULES = words.ADVICE_RULE
CHASE_DAYS = 3           # a wait past 3 working days is late (waiting_late): its agent is woken to chase (checkback.late), else Chase is lit
# a failure is the fact whatever is lit: its sentence stands on the strip beside it (decide)
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
    tk = 'task' if item.get('tid') else 'message'
    try: ms = _msgs(store, item, tk, item.get('tid') or item.get('mid'))
    except Exception: ms = []
    return [m for m in ms if m and str(m.get('Direction') or 'in') != 'out' and m.get('Status') not in ('context',)]


def _name(m: dict) -> str: return ' '.join(str(m.get('FromName') or m.get('FromEmail') or 'Someone').split())


def same_thread(store, item) -> int | None:
    """Another open task on this item's own conversation - the one duplicate a FACT shows. The same sender alone no longer counts
    (the design, 2026-10-23): one person asks for many things, and "TQ-0006 may already cover it" stood over unrelated asks."""
    ms = _inbound(store, item)
    # ...A CHAT'S ID NAMES ITS ROOM, NOT A TOPIC (routing.CHAT_CHANNELS; design round 4, H4: a colleague's sign-up list read "Same ask as TQ-0003 -
    # fold it into that one" of a code fix, because her earlier line in the same chat had joined it) - everything said there shares one id
    from .routing import CHAT_CHANNELS
    cids = {m['ConversationId'] for m in ms if m.get('ConversationId') and str(m.get('Channel') or '').lower() not in CHAT_CHANNELS}
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
    from . import concierge
    it, offered = item or {}, {v['verb'] for v in verbs or []}
    kind, lane, tid = str(it.get('kind') or ''), str(it.get('lane') or ''), it.get('tid')
    t = (store.get_task(int(tid)) or {}) if tid else {}
    if t.get('Status') in ('done', 'dropped'): return 'closed', {}
    # AN ACTION WAITS FOR THE OWNER'S YES (proposals.held_pending - a `git push` the shell gate held): read before an agent asking or at work,
    # which lit nothing over the Approve it waited on (the 2026-11-02 audit) - its Approve is lit
    from . import proposals
    if tid and (h := proposals.held_pending(store, tid)): return 'action_held', {'what': h['what'], EV: [f"rv{h['rid']}"]}
    if lane == 'working' or (tid and _at_work(store, 'task', tid)): return 'working', {}
    if kind == 'agent' and (it.get('asking') or lane == 'blocked'): return 'agent_asking', {}
    # ...and a run that ENDED on a question to the owner - a restart cut it off at "go ahead?" - is still asking, not stopped: the finish
    # check read it as stopped work and lit Reply to the sender over the agent's ask (the owner, 2026-11-03)
    if tid and (kind in ('agent', 'agentdone', 'wrapup') or lane in ('stopped', 'saved')):
        from . import workerstate
        if workerstate.left_asking(store, tid): return 'agent_asking', {}
    try: f = failure(store, it)
    except Exception: f = None
    # ...WHAT THE DEMO REFUSED DID NOT FAIL (the walk, 2026-11-15): its tour says "press Send - nothing leaves the demo", and the row then
    # read "Failed: This is the demo - nothing is sent" in the words of a real fault. The item is as it was; the press's own line said why
    if f and f.get('cause') == 'demo': f = None
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
    if draft_needs(store, it) or reply_unwritten(store, it): return 'needs_agent', {}
    # A DASHBOARD's refresh lands under Reports like a report run and Next walks past it (the owner, 2026-10-23): looked at, never acted
    # on - so silent, Next lit. Its Share (and a report's) is on the row for the Advisor to SEE, never the move a rule lights: sending a
    # result somewhere is the owner's own idea, not the obvious next step
    if kind == 'report': return ('dashboard' if it.get('dashboard') else 'report_ok'), {}
    if kind == 'fyis': return 'fyi_batch', {}
    if kind == 'meeting': return 'meeting', {}
    if kind == 'connection': return 'connection', {}
    if lane == 'unjudged': return 'unsorted', {}
    tk = 'task' if tid else 'message'
    try: draft = _draft(store, it, tk, tid or it.get('mid')) if (tid or it.get('mid')) else None
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
    if kind.startswith('goal') or (t and is_goal(t)):
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
    # an agent. Not ours is its move, lit (MOVES), and Send to agent waits in the ▾ (FyiCard's Foot `tuck`)
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
        # (no "you usually answer Erin within the hour; this is 3h" any more - the owner, 2026-11-13: how soon they answer is evidence of
        # who matters, which the memory says in words, never a number shown)
        # THE OWNER ALREADY ANSWERED (trust audit A3, 2026-10-28): their own reply went after the sender's newest message, so nobody is
        # waiting - Mark done, as the model's prompt says ("someone is waiting only when they wrote again after it"); Reply lit there
        # offered to say twice what was said
        if (went := answered(store, it, ins[-1])): return 'answered', {'when': when(went)}
        return 'asked', {'who': _name(ins[-1]), 'ago': ago(ins[-1].get('SentAt') or ins[-1].get('CreatedAt'))}
    if t and (cl := _checklist(t)) and all(c.get('done') for c in cl): return 'done_list', {'n': len(cl)}
    return 'own', {}


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
    from . import learned_cut
    from .ingest import owner_addresses, own_addresses
    tk, ti = ('task', item['tid']) if item.get('tid') else ('message', rv.get('MessageId') or item.get('mid'))
    known = {a for m in _msgs(store, item, tk, ti) for a in learned_cut.people_of(m)} | owner_addresses(store) | own_addresses(store)
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
    tid, mid = item.get('tid'), item.get('mid')
    try: r = store.sent_reply(task_id=int(tid)) if tid else store.sent_reply(message_id=int(mid)) if mid else None
    except Exception: r = None
    try: outs = [m for m in _msgs(store, item, 'task' if tid else 'message', tid or mid) if str(m.get('Direction') or 'in') == 'out']
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


# ── THE TASK'S RECOMMENDED MOVE (the owner, 2026-11-09; 2026-11-15: "nothing for now. the agent should suggest what to do") ──────────────
# The row fills a button only where the move is already settled: the Send of what waits for the owner's yes - a draft, whoever wrote it,
# or a held action - never one whose channel is not connected or that just failed; and Mark done where the agent's own turn said nothing
# is left (or, for an agent that writes no summary, where its own last word ended the work). Everything else - a late wait, work unpushed, a stopped agent, an ask nobody took, a duplicate - fills nothing: what to do
# next is the task's agent's to suggest, on its own card.
QUIET = frozenset({'closed', 'working', 'agent_asking'})
# an answer owed to the owner gone late: its agent is woken once to draft the chase (checkback.late)
LATE = frozenset({'waiting_late', 'waiting_overdue', 'waiting_late_usual', 'goal_late', 'watch_quiet'})
NOTHING_LEFT = 'Its agent said nothing is left to do'


def agent_word(store, tid) -> str | None:
    """What the agent's newest turn summary (general.SUMMARY_TYPE) leaves the owner: 'on_you' while a step of its list is theirs,
    'nothing_left' where it said so, '' where it said neither - and None with no summary (no agent ran, or one that writes none)."""
    from . import general
    try:
        last = next((c for c in reversed(store.list_comments(int(tid), internal=True)) if c.get('ActorType') == general.SUMMARY_TYPE), None)
        summ = json.loads(last['Body']) if last else None
    except (TypeError, ValueError, KeyError): summ = None
    if not isinstance(summ, dict): return None
    if any(c.get('on_you') and not c.get('done') and c.get('text') for c in _checklist(store.get_task(int(tid)))): return 'on_you'
    return 'nothing_left' if summ.get('nothing_left') else ''


def _recommended(store, it: dict, verbs: list | None, f: dict | None, unlit: bool = False) -> dict | None:
    if it.get('kind') == 'idea': return None                # an Advisor idea's row fills nothing (the owner, 2026-11-15)
    verbs = offered(store, it) if verbs is None else verbs
    f = f or facts(store, it, verbs)
    st, tid, why, on = f['state'], it.get('tid'), f.get('line') or '', {v['verb'] for v in verbs}
    pick = lambda *vs: next((v for v in vs if v in on), None)
    if st in QUIET or st in FAILED: v = None              # ...what failed is never sent again as it stood
    elif st == 'action_held': v = None if unconnected(store, it) else pick('approve', 'send_close')
    elif st == 'draft_ready' or ((w := store.waiting_on_owner(int(tid)) if tid else None) and (w.get('FinalText') or w.get('DraftText'))):
        v = None if unconnected(store, it) else pick('send_close', 'approve')
    elif tid and (said := agent_word(store, tid)) is not None: v, why = (pick('close'), NOTHING_LEFT) if said == 'nothing_left' else (None, why)
    # ...an agent that writes no summary (a coding agent's terminal) says it by ending its work: its own last word, never the owner's reply
    else: v = pick('close') if st == 'agent_done' and why.startswith('Finished') else None
    if v: return {'verb': v, 'label': _label(verbs, v, it), 'why': why, 'state': st}
    # ...and A ROW WITH NOTHING LIT SAYS WHY, on the desk as on the phone (the owner, 2026-11-10): `unlit` asks for the state's own sentence
    return {'verb': None, 'label': '', 'why': f['line'], 'state': st} if unlit and f.get('line') else None


def recommended(store, item: dict, verbs: list = None, f: dict = None, unlit: bool = False) -> dict | None:
    """{verb, label, why, state} - the one move the item's row fills - or None for nothing filled. `verbs`: the row's buttons where the
    caller read them already (offered); `f`: its facts; `unlit`: a row with nothing filled still comes back with its state's line
    (verb None) where it has one - what a row draws. Never raises: a row that cannot be read fills nothing."""
    try:
        with reading(): return _recommended(store, item or {}, verbs, f, unlit) if item else None
    except Exception as e:
        logger.warning(f"rulebook: no recommended move for {(item or {}).get('key')} - {e}"); return None


def recommended_task(store, tid, known: dict = None) -> dict | None:
    """The same for a task by its id (the task page's own payload): its card as the rail last stood, never a rail build. `known`: what
    the page's read holds of the task already (concierge._shows, and its `messages`) - that read is made on every live write while an
    agent works."""
    known = dict(known or {})
    with reading({int(tid): known.pop('messages')} if 'messages' in known else None):
        try:
            item = _item(store, 'task', int(tid), build=False)
            verbs = offered(store, item, known) if item and item.get('kind') != 'idea' else None
        except Exception as e:
            logger.debug(f'rulebook: no card for task {tid} - {e}'); item = verbs = None
        return recommended(store, item, verbs, unlit=True)


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
    if str(it.get('kind') or '').startswith('goal') or is_goal(t):
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


# ── THE ROW'S REAL BUTTONS AND THE ONE DECISION EVERY SURFACE READS (moved from advisor.py, 2026-11-15) ──────────────────────────────────
def key_of(target_kind: str, target_id) -> str:
    return f"{'task' if target_kind == 'task' else 'idea' if target_kind == 'idea' else 'msg'}:{int(target_id)}"
def target_of(store, key: str):
    """A rail key -> (target kind, id), or None for a key with nothing to advise on (a connection, a meeting, a batch). An idea - the
    Advisor's own line, a slipped follow-up - is a target of its own: it was None, so no idea ever had a line (the deep dive, 2026-10-20)."""
    m = re.match(r'^(task|agent|wrap|msg|report|idea):(\d+)$', str(key or ''))
    if m: return ('task' if m.group(1) in ('task', 'agent', 'wrap') else 'idea' if m.group(1) == 'idea' else 'message', int(m.group(2)))
    # a draft waiting for your yes is keyed by its review (funnel's review:N, in a bare store and the demo): advised as the
    # task it answers for, else the message - read as "nothing to advise on", every draft on the demo's rail had an empty bar
    m = re.match(r'^review:(\d+)$', str(key or ''))
    if m:
        r = store.get_review(int(m.group(1))) or {}
        return ('task', int(r['TaskId'])) if r.get('TaskId') else ('message', int(r['MessageId'])) if r.get('MessageId') else None
    if str(key or '').startswith('processing:'):
        # the inventory's key names an ITEM; its members say what it is made of (a task outranks its mail rows)
        try:
            with store._processing_read() as cur:
                hit = store._processing_read_target(cur, key)
                rows = cur.execute("SELECT EntityKind, LocalId FROM processing_member WHERE ItemId=? AND RetiredAt IS NULL", (hit[0],)).fetchall() if hit else []
        except Exception: rows = []
        for kind in ('task', 'message', 'idea'):
            m = next((r for r in rows if r['EntityKind'] == kind), None)
            if m: return (kind, int(m['LocalId']))
    return None


def revision(store, target_kind: str, target_id) -> str:
    """The stamp advice is pinned to: the proposal's own context revision (messages and status) joined with what that
    revision leaves out and an event changes - the task's state and the newest word its agent said."""
    from .operations import context_revision
    base = context_revision(store, target_kind, target_id)
    if target_kind == 'idea':                         # an idea moves with its own state and words, and the thread it is about
        i = store.get_idea(int(target_id)) or {}
        try: a = json.loads(i.get('ActionJson') or '{}') or {}
        except ValueError: a = {}
        base = f"{i.get('Status')}|{i.get('LastSaid')}|{i.get('Text')}|{i.get('ActionJson')}"
        if a.get('mid'): base += '|' + context_revision(store, 'message', int(a['mid']))
        if a.get('tid'): base += '|' + context_revision(store, 'task', int(a['tid']))
    if target_kind == 'task':
        t = store.get_task(target_id) or {}
        ev = store._one('SELECT MAX(Id) AS Id FROM worker_event WHERE TaskId=?', (int(target_id),)) or {}
        base += f"|{t.get('Status')}|{t.get('Assignee')}|{t.get('DueAt')}|{ev.get('Id')}|{t.get('WaitingOn')}|{t.get('WokeMid')}"
    # ...and every act on it: a line judged "Send" before the send failed stood over the failure, advising the same Send (2026-10-18);
    # one judged "Reply" before the reply WENT stood over "Sent" on the close-out, still saying the sender was waiting (2026-10-19)
    base += f"|{_acted(store, target_kind, target_id)}"
    return hashlib.sha1(base.encode()).hexdigest()[:16]


def _acted(store, target_kind, target_id) -> str:
    """What the owner's acts left on the target: each draft - there or not, how it was decided, whether it went - and the newest
    operation that ran on it, done, failed or declined (a chat's proposed operation still waiting for its yes is no act yet - but a step
    held for the owner's Approve is a pending review, so it is in the reviews read here, and the revision moves when one lands: the
    2026-11-02 audit). DeliveryState alone skipped every NULL, so a reply sent with no delivery receipt (Status approved, DeliveryState
    NULL) changed nothing it saw."""
    col = 'TaskId' if target_kind == 'task' else 'MessageId'
    if target_kind == 'idea':                         # an idea carries no draft; its acts are its own operations
        op = store._one("SELECT OpId, Status FROM operation WHERE TargetKind='idea' AND TargetId=? AND Status<>'proposed' ORDER BY rowid DESC LIMIT 1", (int(target_id),)) or {}
        return f"/{op.get('OpId') or ''}:{op.get('Status') or ''}"
    # ...and whether its draft could not be written: a Reply whose draft failed left the line it was judged before standing (2026-10-19)
    # ...and THE DRAFT'S OWN WORDS: a redraft keeps its review, so "Redraft: it promises an invite" stood over the redraft that had
    # already dropped the promise - the draft was never read again (walk 2026-10-29). The revision is hashed, so the text costs nothing
    rv = store._one(f"SELECT GROUP_CONCAT(ReviewId || ':' || IFNULL(Status,'') || ':' || IFNULL(DeliveryState,'') || ':' || (IFNULL(DraftError,'')<>'') || (IFNULL(DraftNeeds,'')<>'')"
                    f" || ':' || IFNULL(FinalText, IFNULL(DraftText,'')), ',') AS d FROM (SELECT * FROM review WHERE {col}=? ORDER BY ReviewId)", (int(target_id),)) or {}
    op = store._one("SELECT OpId, Status FROM operation WHERE TargetKind=? AND TargetId=? AND Status<>'proposed' ORDER BY rowid DESC LIMIT 1",
                    (target_kind, int(target_id))) or {}
    return f"{rv.get('d') or ''}/{op.get('OpId') or ''}:{op.get('Status') or ''}"


# ADVICE IS KEYED TO ITS ITEM: one task can stand on the rail twice - its draft (review:N) and its agent (agent:N) - and a line
# written for one, with a verb only that one's row carries, stood over the other (2026-10-18). A row belongs to the item it was
# judged as: its rail key, or a key that names that same item (its aliases: task:N for the processing inventory's key).
def keys_of(item: dict | None, key: str = None) -> set:
    return {k for k in (key, *((item or {}).get('key'), *((item or {}).get('aliases') or []))) if k}


def _item(store, target_kind, target_id, key: str = None, build: bool = True):
    """The card the rail would show for this target - the one keyed `key` when asked for an item (keys_of), else found by its task
    or message id, since the rail's key spelling is the processing inventory's (`processing:...`) in a real install and a legacy
    alias in a bare store.
    `build=False`: a task's own read (rulebook.recommended_task), made again on every live write while its agent works - the rail as it
    last stood, else the card built from the task's own rows; never a build of any size, since even the keyed one takes the rail's lock
    and opening a task waited 15 s behind a restart's first build (stage G, 2026-11-10)."""
    from . import funnel
    if target_kind == 'task':
        t = store.get_task(target_id) or {}
        if not t or (t.get('Status') in ('done', 'dropped') and not store.resumable_session(target_id)): return None
    # NEVER A RAIL BUILD, NEVER A WAIT FOR ONE (2026-11-09): this read funnel.pile, so every look and every press waited behind whatever
    # build was running and built again after any write - with an agent busy beside it, GET /api/advice took 84 s and a press 72 s.
    # The rail as last built - its cache, or the build a write emptied it of since (funnel.known); built here only when there has never been
    # one and nobody is building it; else the card the rail would show, built for this one key (no lock, a few rows)
    full, pile = funnel.full_items(store), funnel.cached_pile(store)
    if pile is None: full, pile = funnel.known_full(store), funnel.known(store)
    if pile is None and build and not funnel.building():
        try: pile, full = funnel.pile(store, quiet=True), funnel.full_items(store)
        except Exception as e: logger.debug(f'rulebook: no rail for {key} - {e}')
    items = [*(full or ()), *((pile or {}).get('items') or ())]        # read items kept: the one on the table is often read
    f = 'tid' if target_kind == 'task' else 'idea' if target_kind == 'idea' else 'mid'
    mine = [i for i in items if i.get(f) == int(target_id)]
    hit = next((i for i in mine if key and key in keys_of(i)), None) or next(iter(mine), None)
    if hit or not build: return hit or funnel.item_for_key(store, key_of(target_kind, target_id))
    # (the window's keyed build only - next_item's full-history fallback reads every root, seconds on a big home)
    k = key or key_of(target_kind, target_id)
    try:
        pool = funnel.build(store, keep_surfaced=True, keys=[k])['items'] if not str(k).startswith('fyis:') else []
        hit = next((i for i in pool if i['key'] == k or k in i.get('aliases', [])), None)
        hit = funnel.shut(store, funnel._present_one(store, hit)) if hit else None
    except Exception as e: logger.debug(f'rulebook: no keyed card for {key} - {e}'); hit = None
    return hit or funnel.item_for_key(store, key_of(target_kind, target_id))



def _one(s, n: int) -> str: return ' '.join(str(s or '').split())[:n]


_READ = contextvars.ContextVar('rulebook_reading', default=None)


@contextlib.contextmanager
def reading(seed: dict = None):
    """One look at an item reads its task's messages once: {tid: messages} for the block. rulebook.state asked for them three times a
    look - 1,000 lines each on a long chat, most of what the look cost. `seed`: what the caller holds already (a task's own read)."""
    if _READ.get() is not None and not seed: yield; return
    tok = _READ.set({**(_READ.get() or {}), **(seed or {})})
    try: yield
    finally: _READ.reset(tok)


def _msgs(store, item, target_kind, target_id) -> list:
    """The item's messages, oldest first: the task's own, else the message's thread - any channel, a chat's as much as a mail's."""
    if target_kind == 'task':
        held, tid = _READ.get(), int(target_id)
        ms = held[tid] if held is not None and tid in held else store.list_messages(tid)
        if held is not None: held[tid] = ms
    else:
        m = store.get_message(int(target_id)) or {}
        try: ms = store.thread_messages(m['ConversationId'], m.get('Subject'), limit=12) if m.get('ConversationId') else [m]
        except Exception: ms = [m]
    return sorted([m for m in ms if m], key=lambda m: str(m.get('SentAt') or m.get('CreatedAt') or ''))


def _draft(store, item, target_kind, target_id):
    """The draft waiting for the owner's yes on this item, or None."""
    r = store.get_review(int(item['rid'])) if item.get('rid') else None
    if not r and target_kind == 'task': r = store.pending_review(int(target_id))
    if not r and target_kind == 'message': r = store._one("SELECT * FROM review WHERE MessageId=? AND Status='pending' ORDER BY ReviewId DESC LIMIT 1", (int(target_id),))
    return r if r and r.get('Status') in ('pending', 'held') and (r.get('FinalText') or r.get('DraftText')) else None


def _unwritten(store, item) -> dict:
    "The item's review still waiting with no draft on it - {} when it has one, or none waits."
    r = (store.get_review(int(item['rid'])) if item.get('rid') else None) or (store.pending_review(int(item['tid']), live_only=False) if item.get('tid') else None) or {}
    return {} if r.get('Status') not in ('pending', 'held') or str(r.get('DraftText') or '').strip() else r


def draft_needs(store, item) -> str:
    """What the reply writer said it NEEDS on the item's pending review, with no draft on it - '' when it drafted, or never said."""
    return str(_unwritten(store, item).get('DraftNeeds') or '').strip()


# A REPLY OWED THAT NOTHING HAS WRITTEN is the task's agent's to write (ingest.reply_to_agent; the owner, 2026-11-10: "no more triage
# creates draft. agent should be doing it"). Where its agent did not start by itself - the setting, a stranger held - the move is the
# owner's Send to agent, as it was when the old writer said what it needed
def reply_unwritten(store, item) -> bool:
    r = _unwritten(store, item)
    return r.get('Kind') == 'draft' and not str(r.get('FinalText') or '').strip()



def is_goal(t) -> bool:
    from .store import is_goal as g
    return g(t)

def _checklist(t: dict) -> list:
    try: return [c for c in json.loads((t or {}).get('Checklist') or '[]') if isinstance(c, dict)]
    except (TypeError, ValueError): return []



def failure(store, item: dict) -> dict | None:
    """What last failed on the item - {what, why, fix, unknown, kind} - or None: a draft whose send failed or never answered, else the
    newest act on it that ended in an error. The Advisor was never told, so it advised the Send that had just failed (2026-10-18)."""
    ok = lambda f: f if isinstance(f, dict) and f.get('label') and f.get('href') else None
    r = (store.get_review(int(item['rid'])) if item.get('rid') else None) or (store.pending_review(int(item['tid'])) if item.get('tid') else None) or {}
    try: ops = store.operations_for(item.get('tid'), [item['mid']] if item.get('mid') else [])
    except Exception: ops = []
    last = ops[-1] if ops else {}
    try: out = json.loads(last.get('OutcomeJson') or '{}') or {}
    except (TypeError, ValueError): out = {}
    out = out if isinstance(out, dict) else {}
    drafted_wrong = r.get('Status') == 'pending' and r.get('DraftError')
    # ...WHICHEVER FAILED LAST (the matrix, 2026-10-20): a failure newer than the draft's error is what the screen shows now
    newer = last.get('Status') in ('error', 'refused') and out.get('source') != 'draft'
    # A DRAFT THAT COULD NOT BE WRITTEN is what failed (2026-10-19): with no AI to write it, Reply left an empty box and an error, and
    # the Advisor - never told - read the box with no Send as a chat's draft and said "copy it ... then mark it done" over an email
    if drafted_wrong and not newer:
        from .failures import classify
        c = classify(str(r['DraftError']))
        return {'what': 'the reply could not be drafted', 'why': c['sentence'], 'fix': ok(c['fix']), 'unknown': False, 'kind': 'draft'}
    if r.get('DeliveryState') in ('failed', 'unknown'):
        try: env = json.loads(r.get('Deliver') or '{}') or {}
        except (TypeError, ValueError): env = {}
        why = re.sub(r'^Not sent:\s*', '', str(r.get('Reason') or '')).rstrip('.')
        return {'what': 'the reply was not sent' if r['DeliveryState'] == 'failed' else 'the reply may not have gone',
                'why': why, 'fix': ok(env.get('fix')) if isinstance(env, dict) else None, 'unknown': r['DeliveryState'] == 'unknown', 'kind': 'send'}
    # ...and a report's card or a connection's row has no task: its failure lives on the report or the connector (failures.standing)
    from . import failures
    if (on := failures.target_of(item)) and (f := failures.standing(store, *on)): return f
    # ...and AN AGENT'S RUN THAT FAILED (the deep dive, 2026-10-20): it reached the prompt only as "run ended (failed)", so the line said
    # "it stopped partway - pick it up" and lit Continue into the same unreachable database. An act that failed since outranks it.
    if last.get('Status') not in ('error', 'refused') and (ran := agent_failed(store, item)): return ran
    # ...and an act the demo refused (demo.refused): it went nowhere, so the Send just refused is not advised again (2026-10-19)
    if last.get('Status') not in ('error', 'refused'): return None
    if out.get('source') == 'draft': return None          # a draft written since cleared it
    # the record's own words lead (failures.record - the workflow runner's step says which step stopped); else the act, described
    if out.get('what'): what = str(out['what'])
    else:
        try:
            from . import operations
            what = f'"{concierge.describe_op(store, operations.get(store, last["OpId"]))[0]}" did not happen'
        except Exception: what = f'"{last.get("Kind") or "the last action"}" did not happen'
    from .failures import area_fix
    return {'what': what, 'why': str(last.get('Error') or ''), 'fix': ok(out.get('fix')) or area_fix(out.get('area')),
            'unknown': out.get('delivery') == 'unknown', 'kind': last.get('Kind'), 'source': out.get('source') or 'app',
            'cause': out.get('cause') or 'taskuary'}


def agent_failed(store, item: dict) -> dict | None:
    """The task's agent run, when its last state is failed: {what, why, ...} in failure()'s shape, its why the run's own last words."""
    if not item.get('tid'): return None
    from . import workerstate
    try: st = workerstate.status(store, int(item['tid']))
    except Exception: return None
    if st.get('state') != 'failed': return None
    last = next((e for e in reversed(workerstate.events(store, int(item['tid']), st.get('sid'))) if e['Kind'] == 'failed'), {})
    # ...in plain words, with the place that fixes it (failures.classify): an agent with no AI to run on is fixed by connecting one -
    # it lit "New task to fix this" and turned connecting an AI into another task (owner-approved, 2026-10-21)
    from .failures import classify
    c = classify(_one(st.get('result') or last.get('Text'), 300) or 'it stopped without saying why', tid=int(item['tid']))
    return {'what': "the agent's run failed", 'why': c['sentence'], 'fix': c['fix'], 'unknown': False,
            'kind': 'agent', 'source': 'agent', 'cause': 'taskuary'}


def _retryable_agent(store, item: dict) -> bool:
    """Can the failed run be tried again from its step: a general agent's saved conversation, with nothing live on it."""
    tid = item.get('tid')
    if not tid: return False
    from . import workerstate
    return workerstate._live(int(tid)) is None and concierge._general(store, item)


def fix_task(store, item: dict, f: dict) -> dict:
    """The task "New task to fix this" makes: what failed, why, and on what - in the owner's words, for an agent or for them."""
    on = ' '.join(filter(None, (item.get('ref'), item.get('title'))))
    return {'title': f"Fix: {f['what']}"[:120], 'text': f"{f['what'][:1].upper()}{f['what'][1:]} on {on or 'an item'}. What came back: "
            f"{f['why'] or 'no reason was given'}. Find why, and fix it so it does not fail again."}


def delivery_fix(store, item: dict) -> dict | None:
    """{label, href} of the place that fixes the item's failed send - the draft's envelope (Deliver.fix, kept across a reload),
    else the newest act on the item when it failed with one (OutcomeJson.fix). None when nothing failed, or it named no place."""
    ok = lambda f: f if isinstance(f, dict) and f.get('label') and f.get('href') else None
    r = (store.get_review(int(item['rid'])) if item.get('rid') else None) or {}
    try: env = json.loads(r.get('Deliver') or '{}') or {}
    except (TypeError, ValueError): env = {}
    if isinstance(env, dict) and (r.get('DeliveryState') or env.get('delivery')) == 'failed' and ok(env.get('fix')): return ok(env['fix'])
    try: ops = store.operations_for(item.get('tid'), [item['mid']] if item.get('mid') else [])
    except Exception: ops = []
    last = ops[-1] if ops else {}
    try: out = json.loads(last.get('OutcomeJson') or '{}') if last.get('Status') == 'error' else {}
    except (TypeError, ValueError): out = {}
    return ok((out or {}).get('fix')) if isinstance(out, dict) else None


NOT_MOVES = frozenset({'priority', 'change_kind', 'pick_repo', 'attach', 'close_note', 'next'})


def offered(store, item: dict, known: dict = None) -> list:
    """THE ITEM'S REAL BUTTONS, AND NOTHING IT CANNOT DO: the verbs its row carries minus Next - chips_for, which already drops
    what this install cannot do (capabilities.py: no Send on a draft whose channel cannot send, no coding agent with no
    coding tool) - plus the row's own fix when a send failed and named the place that fixes it, under that place's own name.
    An agent waiting on the owner carries Answer it there (chips_for) - its card once offered only End and Remind me, which the
    prompt forbids for someone waiting, so the Advisor stood silent (2026-10-17 audit). Not added here: a paused, stalled or
    stopped agent has nobody listening, and the row knows which is which.
    THE BUTTONS THE ROW ACTUALLY DRAWS (the design, phase A, 2026-10-23): the verbs came from chips_for while the row drew row_buttons -
    why Review changes, Chase and Accept could never be lit, and why "Not ours" was picked on a task whose row has no Not ours. Only
    the row's moves count: its pickers (who does it, priority, assignee, the code's place), Attach and Close with a note set a field or
    add to a move, and are never the move. Chase joins on a wait with somebody to write to (rulebook.adds); Next is added by the callers."""
    verbs = [buttons.chip(b['verb']) | {'label': b['label']} for b in concierge.row_buttons(store, item, known) if b['verb'] not in NOT_MOVES]
    # ...in the item's own order (its vocabulary, chips_for - a draft's Send first), the row's other moves after it
    first = [c['verb'] for c in concierge.chips_for(store, item)]
    verbs.sort(key=lambda v: first.index(v['verb']) if v['verb'] in first else len(first))
    verbs += [buttons.chip(v) for v in adds(store, item) if v not in {x['verb'] for x in verbs}]
    try: fix = delivery_fix(store, item)
    except Exception as e:
        logger.debug(f'rulebook: no fix read for {item.get("key")} - {e}'); fix = None
    # the fix leads: a send that failed is fixed before it is sent again (ReviewDecision.jsx draws it as '<rid>:fix')
    lead = [buttons.chip('fix') | {'label': fix['label'], 'href': fix['href']}] if fix else []
    # A FAILURE NOTHING HERE FIXES (no fix named, not a send that may yet have gone) can still be made somebody's work: New task, in its
    # "fix" state, carrying what failed (the owner, 2026-10-18: "if it's a more complicated fix, the assistant should create a task")
    try: f = failure(store, item)
    except Exception: f = None
    if not fix and f and f.get('fix'): fix = f['fix']; lead = [buttons.chip('fix') | {'label': fix['label'], 'href': fix['href']}]
    if fix and f and f.get('cause') != 'step' and f.get('source') != 'workflow': f = None      # a fix is the way on; no task besides it
    # ...except a workflow run, which already IS a task: a second one to fix it would be the same work twice - it carries Report
    # this bug instead (agreed with the workflow runner, taskhub-ca, 2026-10-18)
    # ...and nothing for what the demo refused: no task or bug report makes the demo send
    if f and f.get('cause') == 'demo': pass
    elif f and (f.get('cause') == 'step' or f.get('source') == 'workflow'): lead.append(buttons.chip('report_bug'))
    # ...and A GENERAL AGENT'S RUN THAT FAILED with nothing named to fix is tried again from its saved conversation - the step's own
    # Continue, said as Try again (owner-approved, 2026-10-21). A coding agent's keeps New task: Continue reopened it into the same
    # unreachable database (the 2026-10-20 deep dive)
    # ...when it can start again from here: with no brain to run on, Try again is greyed on the page, and New task stands in for it (the
    # Advisor audit's judge, 2026-10-26 - a lit Try again nobody could press left nothing lit at all)
    elif f and f.get('kind') == 'agent' and _retryable_agent(store, item) and not _agent_ready(store, item):
        lead.append(buttons.chip('continue') | {'label': buttons.label('try_again'), 'hint': buttons.hint('try_again')})
    elif f and not f.get('unknown'): lead.append(buttons.chip('new_task', 'fix') | {'task': fix_task(store, item, f)})
    return lead + verbs



def _at_work(store, target_kind: str, target_id) -> bool:
    """An agent at work on the task is nothing for the owner to do. Its continue writes no event the revision sees until the
    prompt lands, so "the agent stopped and is waiting on you" stood over an agent already continued (the owner, 2026-10-13)."""
    if target_kind != 'task': return False
    from . import workerstate
    try: return workerstate.status(store, int(target_id)).get('state') == 'working'
    except Exception: return False



def _label(verbs: list, verb: str, item: dict) -> str:
    if verb == 'next': return buttons.label('next', 'batch') if (item or {}).get('kind') == 'fyis' else buttons.label('next')
    return next((v['label'] for v in verbs if v['verb'] == verb), None) or buttons.label(verb) or verb
def decide(store, key: str) -> dict:
    """The one filled button of the item keyed `key`, in the shape every surface reads: {key, state, verb, label, line, by, revision, ...};
    `verb` None lights nothing, `line` '' says nothing. {} for a key with nothing to decide on, an idea row among them: nothing lights a
    button over the owner's own choice there (the owner, 2026-11-15). A task or a message: its own recommended move (recommended, `by`
    'agent') - plain code off its agent's turn and its facts, no model."""
    tgt = target_of(store, key)
    if not tgt or tgt[0] == 'idea': return {}
    item = _item(store, *tgt, key=key)
    if not item: return {}
    verbs = offered(store, item) + [buttons.chip('next')]
    r = facts(store, item, verbs)
    v = (recommended(store, item, verbs, r) or {}).get('verb')
    # ...two facts are said beside it: what failed, and what leaves with a draft beside its Send (the design rev 2: "a line on top") - and A
    # ROW WITH NOTHING LIT SAYS WHY in its state's one sentence (the owner, 2026-11-10): plain buttons and no word stood over a wait gone late
    says = bool(r.get('line')) and (not v or r['state'] in FAILED or (r['state'] == 'draft_ready' and v in SENDS))
    lbl, ev = _label(verbs, v, item) if v else '', list(r.get('evidence') or []) if says else []
    return {'key': key, 'state': r['state'], 'verb': v, 'label': lbl, 'line': r['line'] if says else '', 'by': 'agent', 'revision': revision(store, *tgt),
            'pill': lbl, 'evidence': ev, 'kind': 'other'}


SENDS = frozenset({'approve', 'send_close'})      # the draft's two sends under it in the chat: Send, and Send and close
AGENT_CHECK = True       # the suite turns this off (tests/conftest.py): a bare store has no brain, and its agents' buttons are not the subject


def _agent_ready(store, item: dict) -> str:
    """'' when an agent can start on the item from here, else why not - the page's own check (capabilities.cannotStart: an AI, and a brain a
    general hand-off can choose), so no button is filled that the page greys."""
    if not AGENT_CHECK: return ''
    from . import capabilities, general, agents as ha
    try:
        if not capabilities.has_ai(store): return 'no AI is connected'
        brains = dict(ha.connection_brains(store))
        ok = any(o.get('type') != 'cli' or ha.runs_here(brains.get(o['pick'][4:])) for o in general.provider_options(store))
        return '' if ok else 'no brain an agent can run on'
    except Exception as e: logger.debug(f'rulebook: no agent check for {item.get("key")} - {e}'); return ''


def unconnected(store, item: dict) -> bool:
    "Whether the card waiting on the item says Connect <X> instead of its Send."
    from . import outbound
    r = (store.get_review(int(item['rid'])) if item.get('rid') else None) or (store.waiting_on_owner(int(item['tid'])) if item.get('tid') else None)
    return bool(r) and r.get('Status') == 'pending' and bool(outbound.review_connect(store, r))


def status(store, key: str) -> dict:
    "decide, or {'none': 'nothing'} for a key nothing is decided on (an idea, a meeting row, a connection): the page lights Next, silent."
    return decide(store, key) or {'none': 'nothing'}


def block(store, item: dict, d: dict | None = None) -> str:
    """The filled button's reason for the chat's system prompt, so 'why?' is answered from it - a lookup, not a think. `d`: the decision
    already read for the item (the chat's CANVAS reads it once for its lit button and this line)."""
    if d is None: d = decide(store, (item or {}).get('key') or '') if item else {}
    if not d.get('verb'): return ''
    return (f"THE TASK'S RECOMMENDED MOVE (read off its agent's own latest turn and the task's facts - if the owner asks why a button is "
            f"filled, this is the answer): {d['label']}" + (f" - {d['line']}" if d.get('line') else '') + '.')
