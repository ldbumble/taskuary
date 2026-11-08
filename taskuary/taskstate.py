"""ONE STATE PER TASK, for the Tasks list and the Board (T1-T9, the owner, 2026-09-25: "everything should be the task
list and the board just follows whatever is going on there").

The list said "on you" for a task waiting to start, a session you saved and an agent that stopped; the Board put all
three - and a task Taskuary closed on - in one "Queued" column, and its "Waiting on you" held an asking agent, a
drafted reply and a task waiting on somebody else. Each page decided from its own facts in the browser. This decides
once, on the server, with the rail's rules (funnel.left_by_facts, general_not_started, finish_evidence) and the rail's
words (lanes.json), and both pages draw what it says.

The keys are lanes.json's own: a lane where the rail has one (blocked, working, approve, queued, saved, stopped,
yours), `theirs` for a task waiting on somebody else, and for a closed task `agentdone` (the agent finished
it) or `closed` (you did) - `agentdone` as well for an open task whose last run said it finished (workerstate.ended).
"""
from . import funnel, workerstate
from .processing_unread import OWNER_ACTORS, finish_evidence

# the Board's columns, left to right: what each holds (T2, T3)
BOARD = (('queued', ('queued',)), ('working', ('working',)), ('blocked', ('blocked',)),
         ('left', ('saved', 'stopped')), ('agentdone', ('agentdone', 'approve')))


def _general_waiting(store, t) -> bool:
    """A regular-agent task triage handed on and nothing started (A10): read only for an open general task, the one
    kind the rule can hold."""
    if str(t.get('Kind') or '') != 'general' or t.get('Status') not in ('open', 'in_progress'): return False
    from .general import ASSISTANT_TYPE, USER_TYPE
    talked = any(c.get('ActorType') in (USER_TYPE, ASSISTANT_TYPE) for c in store.list_comments(t['TaskId']) or [])
    return funnel.general_not_started(t, talked, store.list_routes(t['TaskId']) or [])


def chat_moved_on(store, tid: int) -> bool:
    """THE CHAT AGENT IS DONE FOR NOW (the owner, 2026-11-06: one cycle - agent working, agent waiting on you, and after you Send "agent done"
    until you type again): the owner answered the agent's newest turn - its reply sent from here, or their own answer on the thread - and
    nothing is pending. The rail (funnel.from_agents), the task's state and the page's chip all read this, so they cannot disagree."""
    if store.waiting_on_owner(tid): return False
    from .general import ASSISTANT_TYPE
    last = (store._one('SELECT MAX(CreatedAt) AS at FROM comment WHERE TaskId=? AND ActorType=?', (tid, ASSISTANT_TYPE)) or {}).get('at') or ''
    sent, own = store.sent_reply(task_id=tid), store.own_reply_on_thread(task_id=tid)
    went = max(str((sent or {}).get('DecidedAt') or (sent or {}).get('CreatedAt') or ''), str((own or {}).get('SentAt') or ''))
    return bool(went) and went >= str(last)


def open_question(store, tid: int) -> dict | None:
    """THE AGENT'S OPEN QUESTION, AS SAVED WITH THE TASK (the owner, 2026-11-07: an idled-out agent's question vanished from the chip, the rail
    and the Assistant though nobody answered it): its run's own recorded ask, open until the owner speaks - whether its process is alive or
    not. None when none is open."""
    return workerstate.shown_ask([r for r in workerstate.status(store, tid)['requests'] if workerstate.own_question(r)])


def _chat_resting(store, t: dict) -> str | None:
    "An open chat task with no live agent: 'blocked' while its question is open, 'agentdone' once it has answered, else None."
    from .general import ASSISTANT_TYPE, handles, is_dock
    if not handles(t) or is_dock(t) or t.get('Status') not in ('open', 'in_progress'): return None
    if open_question(store, t['TaskId']): return 'blocked'
    if store.waiting_on_owner(t['TaskId']): return 'approve'          # an email it set up waits for your Send, never "agent done"
    spoke = store._one('SELECT 1 AS x FROM comment WHERE TaskId=? AND ActorType=? LIMIT 1', (t['TaskId'], ASSISTANT_TYPE))
    return 'agentdone' if spoke else None


def state(store, t: dict, session=None, queued=None) -> str:
    """This task's state key. `session` is its live session row, `queued` its dispatch-queue row."""
    live = bool(session and session.get('alive', True))
    # a live session is the fact happening now - a done task continued is work in progress again (T8). A session that
    # PREDATES the close is a terminal nobody shut, not the task picked back up (the Board's old rule, kept).
    if live and t.get('Status') == 'done' and t.get('ClosedAt') and str(session.get('started') or '') < str(t['ClosedAt']): live = False
    if live:
        if not session.get('waiting'): return 'working'
        # ...but an agent PARKED - it answered, asked nothing - over a reply it drafted is the reply waiting, as the rail says: the Board
        # put it under "agent waiting on you" with "ready to send" on the same card, and the header said so until a reload (email walk 2026-10-29)
        parked = (session.get('state') or 'parked') == 'parked' and not session.get('request')
        if parked and (t.get('ReviewStatus') == 'pending' or store.waiting_on_owner(t['TaskId'])): return 'approve'

        # ...and a CHAT agent whose turn asked nothing is done for now, never waiting on you (the owner, 2026-11-07) - as it reads once idled out
        from .general import handles
        if parked and handles(t): return 'agentdone'
        return 'blocked'
    st = t.get('Status')
    if st == 'dropped': return 'dropped'
    if st == 'done':
        if str(t.get('UpdatedBy') or '') in OWNER_ACTORS: return 'closed'        # yours: no need to read its notes
        return 'agentdone' if finish_evidence(store, t['TaskId']) else 'closed'
    if t.get('RunStatus') == 'running': return 'working'
    if t.get('ReviewStatus') == 'pending': return 'approve'
    # still waiting to start, a failed start included - the row carries the error and the page offers Start now / Cancel (T10)
    if queued: return 'queued'
    left = funnel.left_by_facts(t.get('Tags'), [{'Status': t.get('RunStatus')}] if t.get('RunStatus') else [])
    # ...and HOW ITS LAST RUN ENDED, in the run's own word (workerstate.ended) - the reading the rail takes too: a run that failed
    # or was stopped read "on you", and one that finished read "waiting to start", while the worker said what happened (G7)
    end = None if left else workerstate.ended(store, t['TaskId'])
    if end == 'finished': return 'agentdone'
    if end: left = 'stopped'
    if not left and str(t.get('Assignee') or '').startswith('agent:') and store.last_transcript(t['TaskId']): left = 'stopped'
    if left: return left
    # A CHAT AGENT NOT RUNNING - idled out, or the server restarted - reads as it did live (the owner, 2026-11-07): its open question still
    # waits on you, and a turn that asked nothing is done for now. Read off the task's saved record, never the in-memory IDLED
    if (chat := _chat_resting(store, t)): return chat
    if str(t.get('Assignee') or '').startswith('agent:') or _general_waiting(store, t): return 'queued'
    if st == 'waiting': return 'theirs'
    return 'yours'


def column(key: str) -> str | None:
    """The Board column a state sits in, or None - a task that is yours, or waiting on them, is not agent work."""
    return next((c for c, keys in BOARD if key in keys), None)


def closed_why(store, t: dict, comments=None) -> str | None:
    """WHO CLOSED IT AND WHY, in one line, for a task its agent closed (the owner, 2026-10-21: "when an agent closes a task and
    no close out is needed, I have no idea what the agent did and why it closed"). The agent's own done sentence, else the
    first line of its report. None for an open task, one the owner closed, or one its upstream item ended (`ended` says that)."""
    if not t or t.get('Status') != 'done': return None
    ev = finish_evidence(store, t['TaskId'])
    if not ev or str(ev.get('who') or '').startswith('Its '): return None
    from .wrapup import is_report, report_body
    rep = next((report_body(c.get('Body')) for c in reversed(comments if comments is not None else store.list_comments(t['TaskId']) or [])
                if is_report(c.get('Body'))), '')
    said = ' '.join(str(ev.get('summary') or '').split()) or next((ln.strip() for ln in rep.splitlines() if ln.strip()), '')
    return f'Closed by the agent: {said[:300]}' if said else 'Closed by the agent - it said it was finished.'
