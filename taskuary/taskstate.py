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

And ONE RECORD under it (TaskState, the spine audit 2026-11-09): what is true of a task's agent - the facts, read once - and the
rules over them, which the rail, All, the page's story and this key had each written out for themselves.
"""
from functools import cached_property

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
    talked = any(c.get('ActorType') in (USER_TYPE, ASSISTANT_TYPE) for c in store.list_comments(t['TaskId'], internal=True) or [])
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


def asking(store, task: dict, session=None) -> dict | None:
    """WHAT THE AGENT ASKS THE OWNER, as every chat draws it - the general payload and the coding one alike (the audit, 2026-11-10: a coding agent's
    [[TASKUARY-ASK]] over ACP was recorded and drawn nowhere): its live run's open request, else - an agent at rest, idled out or after a restart -
    its saved question, `resting`: typing answers it as the next turn. A step handed over on a page that has closed since says so (browsergate)."""
    from . import acpcoding, browsergate, general
    tid = task['TaskId']
    if (s := session or workerstate._live(tid)): return browsergate.shown_ask(workerstate.asking_of(store, s))
    rests = general.handles(task) or acpcoding.idled(tid, store)
    return browsergate.shown_ask({**q, 'resting': True}) if rests and (q := open_question(store, tid)) else None


def _chat_resting(store, t: dict) -> str | None:
    "An open chat task with no live agent: 'blocked' while its question is open, 'agentdone' once it has answered, else None."
    from .general import ASSISTANT_TYPE, handles, is_dock
    if not handles(t) or is_dock(t) or t.get('Status') not in ('open', 'in_progress'): return None
    if open_question(store, t['TaskId']): return 'blocked'
    if store.waiting_on_owner(t['TaskId']): return 'approve'          # an email it set up waits for your Send, never "agent done"
    spoke = store._one('SELECT 1 AS x FROM comment WHERE TaskId=? AND ActorType=? LIMIT 1', (t['TaskId'], ASSISTANT_TYPE))
    return 'agentdone' if spoke else None


class TaskState:
    """ONE RECORD OF A TASK'S AGENT WORK (the spine audit, 2026-11-09). "Did its agent start, leave, finish or fail" was worked out by a
    dozen functions - funnel.idle_state, agent_story, agent_left, session_saved, news_since_agent, run_failed, `state` below, the rail's
    card - each reading the tags, the runs, the transcript and the worker's events for itself, in its own order: one rail row read its
    task four times to say one lane, and a rule mended in one reader stayed wrong in the next. The FACTS are read here, once each and
    only when a rule asks for them; the RULES are written here once, and the old names read them off the record.

    `t` is the task's row when the caller holds it - the list's, carrying its latest ReviewStatus and RunStatus - else it is read when
    first asked for; `session` is its live session row and `queued` its dispatch-queue row, which only `key` reads. A record is one
    reading: build it, read it, drop it - a rail build makes one per row and hands it down (processing_unread.card_for)."""
    def __init__(self, store, t=None, session=None, queued=None, tid=None):
        self.store,self.session,self.queued,self.tid = store,session,queued,tid or (t or {}).get('TaskId')
        if t is not None: self.t = t

    # ── the facts ──
    @cached_property
    def t(self): return self.store.get_task(self.tid) or {}
    @cached_property
    def tags(self): return [x.strip() for x in str(self.t.get('Tags') or '').split(',')]
    @cached_property
    def transcript(self): return self.store.last_transcript(self.tid) or {}
    @cached_property
    def events(self): return self.store.worker_events(self.tid) or []
    @cached_property
    def runs(self): return self.store.list_runs(self.tid) or []
    @cached_property
    def inbound(self): return self.store.last_inbound_on_task(self.tid) or {}
    @property
    def saved(self) -> bool:
        """The owner ended the agent's session and its result is written (Stop and save): `session saved`, never
        "left without finishing" (A1, 2026-09-25). A new session clears it (terminal.open_session)."""
        from . import terminal
        return terminal.SAVED in self.tags
    @property
    def interrupted(self) -> bool:
        "Taskuary itself closed on top of a live worker (terminal.release_task, PW-262): nothing restarts by itself."
        from . import terminal
        return terminal.INTERRUPTED in self.tags
    def last(self, kinds=None, skip=()):
        "Its newest worker event of `kinds`, none of `skip` - off the events when a rule has read them already, else the one indexed row."
        return workerstate.newest(self.store, self.tid, self.__dict__.get('events'), kinds, skip)
    @cached_property
    def end(self):
        "How its last run ENDED, by its own word (workerstate.ended) - read off the events when a rule has them in hand already."
        return workerstate.ended(self.store, self.tid, evs=self.__dict__.get('events'))
    @cached_property
    def finished(self) -> bool: return funnel.session_finished(self.store, self.tid, self.events)
    @cached_property
    def failed(self): return funnel.run_failed(self.store, self.tid, st=self)
    # ...and ITS LIVE SESSION, read as the page reads it (info) when the caller holds none: the rail and the story read a coding agent parked over
    # a reply waiting as "stopped - ran on this and left without finishing it", where its page and a chat read approve (the audit, 2026-11-10)
    @cached_property
    def live(self) -> dict | None:
        if self.session is not None: return self.session
        from . import terminal
        s = terminal.session_for(self.tid)
        try: return s.info(details=False) if s is not None and s.alive else None
        except Exception: return None

    # ── the rules ──
    @cached_property
    def news(self) -> dict | None:
        """The message somebody sent AFTER the agent's last session ended - what an open task is about now - or None.

        An agent finished, the task closed, and days later the sender wrote again: the task reopened, correctly, and then
        opened on the old session's "You ended the session - its report is written" as if that were the news (the owner,
        2026-10-12: "it has to be clear what is going on ... it was reopened since x happened so reopen coding session")."""
        from . import terminal
        if not self.t or self.t.get('Status') in ('done', 'dropped') or getattr(terminal.session_for(self.tid), 'alive', False): return None
        ended = max(str(self.transcript.get('CreatedAt') or ''), str(self.events[-1].get('CreatedAt') or '') if self.events else '')
        if not ended: return None                     # no agent ever ran: nothing for news to come after
        return self.inbound if str(self.inbound.get('SentAt') or '') > ended else None

    @cached_property
    def left(self) -> str:
        """'saved' | 'stopped' when an agent HAD this and is gone, else '': the interrupted tag, a session the owner saved, a run that
        stopped (funnel.left_by_facts - what All can read of it), the run's own last word that it failed or was stopped
        (workerstate.ended - the reading `key` takes, G7), or a transcript with nothing live behind it and no finished session over it.
        The lane word for that is `stopped`, never `queued`: a restart killed the agent's session on TQ-0616, the task list said
        interrupted / needs you, and the rail said "handed to an agent, not started yet" (2026-09-17). Never over news: what is open
        then is the message, not the session that went before it."""
        if self.news or self.live: return ''
        return funnel.left_by_facts(self.t.get('Tags'), self.runs) or (
            'stopped' if self.end in workerstate.TERMINAL or (bool(self.transcript) and not self.finished) else '')

    @cached_property
    def idle(self) -> dict:
        "Why nothing is running on it, in the owner's words: {'kind', 'line', 'row'} (funnel.idle_state, which words this record)."
        return funnel.idle_state(self.store, self.tid, self)

    @cached_property
    def key(self) -> str:
        """Its state key, for the Tasks list, the Board, the page and the stage (stages.facts).
        ...and where it still reads less than `left` does, it reads what it always read - the owner's to settle, not this record's
        (the spine audit, 2026-11-09): only the LATEST run's status where the rail takes any run that stopped, a bare transcript only
        under an `agent:` assignee and whether or not its session finished, and no word about mail that came after the agent."""
        store, t, session, tid = self.store, self.t, self.live, self.tid
        live = bool(session and session.get('alive', True))
        # a live session is the fact happening now - a done task continued is work in progress again (T8). A session that
        # PREDATES the close is a terminal nobody shut, not the task picked back up (the Board's old rule, kept).
        if live and t.get('Status') == 'done' and t.get('ClosedAt') and str(session.get('started') or '') < str(t['ClosedAt']): live = False
        if live:
            # ...by the one function every surface asks (general.working): the session's own word here, or a line it was just handed
            from .general import owed
            if not session.get('waiting') or owed(store, tid): return 'working'
            # ...but an agent PARKED - it answered, asked nothing - over a reply it drafted is the reply waiting, as the rail says: the Board
            # put it under "agent waiting on you" with "ready to send" on the same card, and the header said so until a reload (email walk 2026-10-29)
            parked = (session.get('state') or 'parked') == 'parked' and not session.get('request')
            if parked and waits_press(store, t): return 'approve'
            # ...A CHAT SESSION THAT NEVER BEGAN A TURN IS NO AGENT AT REST (recorded on the real CLI, 2026-11-13: a start was refused - its
            # sender not trusted yet - after the session had opened; the session stayed, parked, and the task read "agent done" with Mark
            # done lit over a chat that held only the sender's message and the Trust action): the task reads as it does with no session
            if not (parked and never_ran(store, t, session)):
                # ...and an agent whose turn asked nothing is done for now, never waiting on you (the owner, 2026-11-07) - as it reads once idled out
                return 'agentdone' if done_for_now(store, t, session) else 'blocked'
        st = t.get('Status')
        if st == 'dropped': return 'dropped'
        # ...and a start in flight for his line is at work from the press, whichever agent comes up (general.OPENING - one mark for every kind): a
        # coding task read "yours" while its adapter came up, a chat "working" (the audit, 2026-11-10)
        from .general import OPENING
        if tid in OPENING and st in ('open', 'in_progress'): return 'working'
        if st == 'done':
            if str(t.get('UpdatedBy') or '') in OWNER_ACTORS: return 'closed'        # yours: no need to read its notes
            return 'agentdone' if finish_evidence(store, tid) else 'closed'
        if t.get('RunStatus') == 'running': return 'working'
        if waits_press(store, t, row=True): return 'approve'
        # still waiting to start, a failed start included - the row carries the error and the page offers Start now / Cancel (T10)
        if self.queued: return 'queued'
        left = funnel.left_by_facts(t.get('Tags'), [{'Status': t.get('RunStatus')}] if t.get('RunStatus') else [])
        # ...and HOW ITS LAST RUN ENDED, in the run's own word (workerstate.ended) - the reading the rail takes too: a run that failed
        # or was stopped read "on you", and one that finished read "waiting to start", while the worker said what happened (G7)
        end = None if left else self.end
        if end == 'finished': return 'approve' if store.waiting_on_owner(tid) else 'agentdone'     # a post or an act left for your press
        if end: left = 'stopped'
        if not left and str(t.get('Assignee') or '').startswith('agent:') and self.transcript: left = 'stopped'
        if left: return left
        # A CHAT AGENT NOT RUNNING - idled out, or the server restarted - reads as it did live (the owner, 2026-11-07): its open question still
        # waits on you, and a turn that asked nothing is done for now. Read off the task's saved record, never the in-memory IDLED
        if (chat := _chat_resting(store, t)): return chat
        if str(t.get('Assignee') or '').startswith('agent:') or _general_waiting(store, t): return 'queued'
        if st == 'waiting': return 'theirs'
        return 'yours'


def never_ran(store, t: dict, session: dict) -> bool:
    "A chat agent's live session with no word of its own - no event of a turn, no answer on the task: opened, and never set to work."
    from . import workerstate as ws
    from .general import ASSISTANT_TYPE, handles
    if not handles(t) or (session.get('mode') or 'assistant') != 'assistant': return False
    if any(e['Kind'] not in ws.NOTES for e in ws.events(store, t['TaskId'], session.get('sid'))): return False
    return not store._one('SELECT 1 AS x FROM comment WHERE TaskId=? AND ActorType=? LIMIT 1', (t['TaskId'], ASSISTANT_TYPE))


def waits_press(store, t: dict, row: bool = False) -> bool:
    """DOES SOMETHING ON THIS TASK WAIT FOR HIS PRESS - one read for the task's state: the list row's own latest ReviewStatus, and (not `row`)
    anything else the queue shows waiting (store.waiting_on_owner). Never a reply draft the thread has moved past (proposals.written_past):
    its row still reads pending until an agent hears the newer message, and the pill said "ready to send" over a draft the chat had greyed
    (the owner's live task, 2026-11-13)."""
    from . import proposals
    pending = t.get('ReviewStatus') == 'pending'
    if pending and not proposals.written_past(store, t['TaskId']): return True
    return bool(store.waiting_on_owner(t['TaskId'])) if pending or not row else False


def done_for_now(store, t: dict, session: dict) -> bool:
    """A live agent whose turn ENDED with nothing asked and nothing left for a press: "agent done", Mark done lit, the task still open under
    Tasks (the owner, 2026-11-10). A chat agent always read so; a coding agent that had pushed and said "Nothing is left to do on this
    task" read "agent waiting on you" with no button lit (agent walk 2). Any other agent's reads it once a turn of this session has ended -
    a pane just opened has done nothing yet, and one with work still in the background is not over - and no landing question of its waits."""
    if (session.get('state') or 'parked') != 'parked' or session.get('request') or session.get('held'): return False
    tid = t['TaskId']
    if waits_press(store, t): return False
    from . import landing, workerstate as ws
    from .general import handles
    last = next((e['Kind'] for e in reversed(ws.events(store, tid, session.get('sid'))) if e['Kind'] not in ws.NOTES), None)
    # ...a chat agent in its own chat, unless its last turn was STOPPED (the audit, 2026-11-10: Remind me pressed mid-turn lit Mark done over the
    # turn it had just stopped, in the beat before its session rested); one of its kind in a pane (a routine's run) is read by its turns, as a
    # coding agent is
    if handles(t) and (session.get('mode') or 'assistant') == 'assistant': return last not in ('stopped', 'failed')
    return last == 'turn_end' and not landing.asked(store, tid)


def task_state(store, t: dict = None, session=None, queued=None, tid=None) -> TaskState:
    "THE record for a task: by its row `t` when the caller holds one, else by `tid` - every reader of a task's agent state starts here."
    return TaskState(store, t, session, queued, tid)


def state(store, t: dict, session=None, queued=None) -> str:
    """This task's state key. `session` is its live session row, `queued` its dispatch-queue row."""
    return TaskState(store, t, session, queued).key


def column(key: str) -> str | None:
    """The Board column a state sits in, or None - a task that is yours, or waiting on them, is not agent work."""
    return next((c for c, keys in BOARD if key in keys), None)


def closed_why(store, t: dict, comments=None) -> str | None:
    """WHO CLOSED IT AND WHY, in one line, for a task its agent closed (the owner, 2026-10-21: "when an agent closes a task and
    no close out is needed, I have no idea what the agent did and why it closed"). The agent's own done sentence, else the
    first line of its report. None for an open task, one the owner closed, or one its upstream item ended (`ended` says that)."""
    if not t or t.get('Status') != 'done': return None
    # ...A ROUTINE'S RUN CLOSED BY THE ROUTINE (flow.execute; the visual audit, 2026-11-13): it read "✓ Mark done just now", a press the owner
    # never made, over nothing of what ran - its last line says that, and a draft step's line where its draft waits
    if str(t.get('UpdatedBy') or '') == 'workflow':
        said = [str(c.get('Body') or '') for c in (comments if comments is not None else store.list_comments(t['TaskId'], internal=True) or [])
                if c.get('Actor') == 'workflow']
        waits = [b.split(': ', 1)[-1].rsplit(' (', 1)[0] for b in said if 'waiting for your yes on' in b]
        if said: return 'Closed by the routine: ' + ' '.join([said[-1], *(f'{w[:1].upper()}{w[1:]}.' for w in waits)])[:400]
    ev = finish_evidence(store, t['TaskId'])
    if not ev or str(ev.get('who') or '').startswith('Its '): return None
    from .wrapup import is_report, report_body
    rep = next((report_body(c.get('Body')) for c in reversed(comments if comments is not None else store.list_comments(t['TaskId'], internal=True) or [])
                if is_report(c.get('Body'))), '')
    said = ' '.join(str(ev.get('summary') or '').split()) or next((ln.strip() for ln in rep.splitlines() if ln.strip()), '')
    return f'Closed by the agent: {said[:300]}' if said else 'Closed by the agent - it said it was finished.'
