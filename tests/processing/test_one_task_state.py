"""ONE STATE OF A TASK, ON EVERY SURFACE (the spine audit, 2026-11-09). "Did its agent start, leave, finish or fail" was worked out
separately for the rail's row, for All's row, for the Tasks list / Board / page (taskstate.state) and for the stage the Assistant is told
(stages) - each reading the tags, the runs, the transcript and the worker's own events for itself. The facts are read once now, into one
record (taskstate.task_state), and the rules over them are written there once.

This is the pin, at the rail level: one task in each state there is, built in a real store and read off all four surfaces.

- `test_each_surface_reads_what_it_read` holds every surface to the word it said before the record: the record changed who works a
  state out, never what the owner is shown.
- `test_every_surface_says_the_one_state` asks for the point of it - the four agree. Where they do not agree TODAY the case is a strict
  xfail that names the question: which surface is right is the owner's to say, and a fix that settles one turns its xfail red.

Invented people only."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import funnel, general, processing_unread, stages, taskstate, terminal, workerstate as ws
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)
def at(minutes): return (NOW - timedelta(minutes=minutes)).isoformat(sep=' ')
STAMP = at(0)
SAID = 'Nothing is left on my side.'


def mail(s, tid, x, minutes, body):
    return s.add_message({'TaskId': tid, 'ExternalId': f'{x}:{tid}', 'ConversationId': f'c:{tid}', 'Channel': 'email', 'Subject': 'Ledger total',
                          'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': at(minutes), 'BodyText': body, 'Status': 'routed'})
def task(s, kind='coding', has_mail=True, **fields):
    tid = s.create_task({'Title': 'Fix the ledger total', 'Kind': kind, 'Status': 'in_progress', **fields}, 'triage')
    if has_mail: mail(s, tid, 'x', 60, 'The total is off by one.')
    return tid
def handed(s, **fields): return task(s, Assignee='agent:coding', **fields)
def ran(s, tid, *kinds):
    "The worker's own word for its run, in order (workerstate)."
    for k in kinds: ws.record(s, tid, 'r1', k, text='the test database was not reachable' if k == 'failed' else '')
def run_row(s, tid, status): s.update_run(s.start_run(tid, 'coding', 'do it', 'router'), {'Status': status}, finished=True)
def spoke(s, tid, text=SAID): s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, text)
def later(s, tid): mail(s, tid, 'y', -5, 'It is still off.')         # after everything the agent wrote, which the store stamps now
def draft(s, tid):
    s.add_review({'TaskId': tid, 'MessageId': s.list_messages(tid)[0]['MessageId'], 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'It is fixed.'})
def session(tid, waiting, mode='terminal', agent='coding'):
    return [{'taskId': tid, 'sid': 'g1', 'agent': agent, 'mode': mode, 'alive': True, 'started': STAMP, 'waiting': waiting,
             'state': 'parked' if waiting else 'working', 'idle': 0, 'tail': []}]


# ── a task in each state: what happened to it -> (its id, its live sessions) ──
def yours(s): return task(s, 'task'), ()
def yours_no_mail(s): return task(s, 'task', has_mail=False), ()
def handed_not_started(s): return handed(s), ()
def working(s): t = handed(s); return t, session(t, False)
def asking(s): t = handed(s); return t, session(t, True)
def reply_drafted(s): t = task(s, 'reply'); draft(s, t); return t, ()
def saved(s): t = handed(s); ran(s, t, 'working', 'stopped'); s.tag_task(t, terminal.SAVED, True, 'owner'); return t, ()
def saved_unassigned(s): t = task(s); ran(s, t, 'working', 'stopped'); s.tag_task(t, terminal.SAVED, True, 'owner'); return t, ()
def saved_and_interrupted(s): t = handed(s); s.tag_task(t, terminal.SAVED, True, 'owner'); s.tag_task(t, terminal.INTERRUPTED, True, 'startup'); return t, ()
def interrupted(s): t = handed(s); s.tag_task(t, terminal.INTERRUPTED, True, 'startup'); return t, ()
def interrupted_mid_run(s):
    t = handed(s); ran(s, t, 'working', 'turn_end'); ws.record(s, t, 'r1', 'disconnected', source='startup')
    s.tag_task(t, terminal.INTERRUPTED, True, 'startup'); return t, ()
def run_row_failed(s): t = handed(s); run_row(s, t, 'failed'); return t, ()
def held_for_repo(s): t = handed(s); funnel.hold_for_repo(s, t, 'no repository named'); return t, ()
def waits_for_a_slot(s): t = task(s); s.enqueue_dispatch(t, None, 'coding', 'all slots busy'); return t, ()
def start_failed(s):
    t = task(s); s.enqueue_dispatch(t, None, 'coding', 'x')
    s._exec("UPDATE dispatchq SET State='failed', LastError='the coding tool is not installed', Attempts=2 WHERE TaskId=?", (t,)); return t, ()
def chat_new(s): return task(s, 'general'), ()
def chat_saved(s): t = task(s, 'general'); s.save_session(t, 'assistant', 'm', 'n1', 'k'); spoke(s, t); s.tag_task(t, terminal.SAVED, True, 'owner'); return t, ()
def closed_by_owner(s): t = task(s, 'task'); s.update_task(t, {'Status': 'done'}, 'owner'); return t, ()
def closed_by_agent(s): t = handed(s); ran(s, t, 'working', 'finished'); s.update_task(t, {'Status': 'done'}, 'coding'); return t, ()
def dropped(s): t = task(s, 'task'); s.update_task(t, {'Status': 'dropped'}, 'owner'); return t, ()
def transcript_unassigned(s): t = task(s); s.add_transcript(t, 'p1', 'it ran and went', agent='coding'); return t, ()
# ...and the ones the surfaces read differently today
def said_failed(s): t = handed(s); ran(s, t, 'working', 'failed'); return t, ()
def said_failed_unassigned(s): t = task(s); ran(s, t, 'working', 'failed'); return t, ()
def said_stopped(s): t = handed(s); ran(s, t, 'working', 'stopped'); return t, ()
def said_finished(s): t = handed(s); ran(s, t, 'working', 'finished'); return t, ()
def said_finished_unassigned(s): t = task(s); ran(s, t, 'working', 'finished'); return t, ()
def transcript_only(s): t = handed(s); s.add_transcript(t, 'p1', 'it ran and went', agent='coding'); return t, ()
def timed_out(s):
    t = task(s, 'general', Assignee='agent:assistant'); ws.record(s, t, 'r1', 'working')
    ws.record(s, t, 'r1', 'stopped', text='It ran out of time.', source=general.TIMED_OUT); return t, ()
def held_after_a_run(s): t = handed(s); s.add_transcript(t, 'p1', 'wrong code', agent='coding'); funnel.hold_for_repo(s, t, 'not here'); return t, ()
def finished_with_a_draft(s): t = task(s, 'general', Assignee='agent:assistant'); ran(s, t, 'working', 'finished'); draft(s, t); return t, ()
def mail_after_finished(s): t = handed(s); ran(s, t, 'working', 'finished'); later(s, t); return t, ()
def mail_after_stopped(s): t = handed(s); ran(s, t, 'working', 'stopped'); later(s, t); return t, ()
def mail_after_failed(s): t = handed(s); ran(s, t, 'working', 'failed'); later(s, t); return t, ()
def mail_after_saved(s): t = handed(s); ran(s, t, 'working', 'stopped'); s.tag_task(t, terminal.SAVED, True, 'owner'); later(s, t); return t, ()
def failed_then_ran_fine(s): t = handed(s); run_row(s, t, 'failed'); run_row(s, t, 'done'); return t, ()
def finished_by_its_report(s):
    t = handed(s); ran(s, t, 'working', 'turn_end'); s.add_transcript(t, 'p1', 'it ran', agent='coding')
    s.add_comment(t, 'coding', 'agent', 'AGENT REPORT\nSummary: the total adds up now.'); return t, ()
def saved_tag_alone(s): t = task(s); s.tag_task(t, terminal.SAVED, True, 'owner'); return t, ()
def interrupted_unassigned(s): t = task(s); s.tag_task(t, terminal.INTERRUPTED, True, 'startup'); return t, ()
def chat_parked(s): t = task(s, 'general'); spoke(s, t); return t, session(t, True, 'assistant', 'assistant')
def chat_idled_out(s): t = task(s, 'general'); s.save_session(t, 'assistant', 'm', 'n1', 'k'); spoke(s, t); return t, ()
def chat_after_restart(s): t = task(s, 'general'); s.save_session(t, 'assistant', 'm', 'n1', 'k'); spoke(s, t); return t, ()
def chat_after_restart_no_session(s): t = task(s, 'general'); spoke(s, t); return t, ()
def chat_failed(s): t = task(s, 'general'); s.save_session(t, 'assistant', 'm', 'n1', 'k'); spoke(s, t); ran(s, t, 'working', 'failed'); return t, ()
def waiting_on_them(s): return task(s, 'task', has_mail=False, Status='waiting'), ()
def waiting_on_them_with_mail(s): return task(s, 'task', Status='waiting'), ()

IDLED = {'chat_idled_out'}             # general.IDLED is this process's memory of a chat that idled out: gone after a restart

# the words each surface says today: (rail, All, list/Board/page, stage). The rail's is its lane, `/done` when the row reads "agent done"
SAYS = {
    'yours': (yours, 'yours', 'asked', 'yours', 'to_reply'),
    'yours_no_mail': (yours_no_mail, 'yours', 'asked', 'yours', 'to_start'),
    'handed_not_started': (handed_not_started, 'queued', 'queued', 'queued', 'to_start'),
    'working': (working, 'working', 'working', 'working', 'agent_working'),
    'asking': (asking, 'blocked', 'blocked', 'blocked', 'agent_working'),
    'reply_drafted': (reply_drafted, 'approve', 'approve', 'approve', 'to_send'),
    'saved': (saved, 'saved', 'saved', 'saved', 'agent_result'),
    'saved_unassigned': (saved_unassigned, 'saved', 'saved', 'saved', 'agent_result'),
    'saved_and_interrupted': (saved_and_interrupted, 'saved', 'saved', 'saved', 'agent_result'),
    'interrupted': (interrupted, 'stopped', 'stopped', 'stopped', 'agent_result'),
    'interrupted_mid_run': (interrupted_mid_run, 'stopped', 'stopped', 'stopped', 'agent_result'),
    'run_row_failed': (run_row_failed, 'stopped', 'stopped', 'stopped', 'agent_result'),
    'held_for_repo': (held_for_repo, 'queued', 'queued', 'queued', 'to_start'),
    'waits_for_a_slot': (waits_for_a_slot, 'queued', 'queued', 'queued', 'to_start'),
    'start_failed': (start_failed, 'queued', 'queued', 'queued', 'to_start'),
    'chat_new': (chat_new, 'yours', 'asked', 'yours', 'to_start'),
    'chat_saved': (chat_saved, 'saved', 'saved', 'saved', 'agent_result'),
    'closed_by_owner': (closed_by_owner, 'fyi', 'fyi', 'closed', 'done'),
    'closed_by_agent': (closed_by_agent, 'fyi', 'fyi', 'closed', 'done'),
    'dropped': (dropped, 'fyi', 'fyi', 'dropped', 'done'),
    'transcript_unassigned': (transcript_unassigned, 'yours', 'asked', 'yours', 'to_start'),
    # ── where they part today (ASK below) ──
    'said_failed': (said_failed, 'stopped', 'queued', 'stopped', 'agent_result'),
    'said_failed_unassigned': (said_failed_unassigned, 'stopped', 'asked', 'stopped', 'agent_result'),
    'said_stopped': (said_stopped, 'stopped', 'queued', 'stopped', 'agent_result'),
    'said_finished': (said_finished, 'yours/done', 'queued', 'agentdone', 'agent_result'),
    'said_finished_unassigned': (said_finished_unassigned, 'yours/done', 'asked', 'agentdone', 'agent_result'),
    'transcript_only': (transcript_only, 'stopped', 'queued', 'stopped', 'agent_result'),
    'timed_out': (timed_out, 'stopped', 'queued', 'stopped', 'agent_result'),
    'held_after_a_run': (held_after_a_run, 'stopped', 'queued', 'stopped', 'agent_result'),
    'finished_with_a_draft': (finished_with_a_draft, 'approve', 'queued', 'approve', 'to_send'),
    'chat_failed': (chat_failed, 'stopped', 'asked', 'stopped', 'agent_result'),
    'mail_after_finished': (mail_after_finished, 'asked', 'queued', 'agentdone', 'agent_result'),
    'mail_after_stopped': (mail_after_stopped, 'asked', 'queued', 'stopped', 'agent_result'),
    'mail_after_failed': (mail_after_failed, 'asked', 'queued', 'stopped', 'agent_result'),
    'mail_after_saved': (mail_after_saved, 'asked', 'saved', 'saved', 'agent_result'),
    'failed_then_ran_fine': (failed_then_ran_fine, 'stopped', 'stopped', 'queued', 'to_start'),
    'finished_by_its_report': (finished_by_its_report, 'queued', 'queued', 'stopped', 'agent_result'),
    'saved_tag_alone': (saved_tag_alone, 'yours', 'saved', 'saved', 'agent_result'),
    'interrupted_unassigned': (interrupted_unassigned, 'yours', 'stopped', 'stopped', 'agent_result'),
    'chat_parked': (chat_parked, 'yours/done', 'blocked', 'agentdone', 'agent_result'),
    'chat_idled_out': (chat_idled_out, 'yours/done', 'asked', 'agentdone', 'agent_result'),
    'chat_after_restart': (chat_after_restart, 'stopped', 'asked', 'agentdone', 'agent_result'),
    'chat_after_restart_no_session': (chat_after_restart_no_session, 'yours', 'asked', 'agentdone', 'agent_result'),
    'waiting_on_them': (waiting_on_them, 'theirs', 'asked', 'theirs', 'waiting'),
    'waiting_on_them_with_mail': (waiting_on_them_with_mail, 'yours', 'asked', 'theirs', 'waiting'),
}

# the same state under each surface's own word for it
ONE = {'asked': 'yours', 'yours/done': 'finished', 'asked/done': 'finished', 'agentdone': 'finished', 'fyi': 'closed', 'dropped': 'closed'}
STAGE = {'to_reply': {'yours'}, 'to_start': {'yours', 'queued'}, 'agent_working': {'working', 'blocked'}, 'to_send': {'approve'},
         'agent_result': {'saved', 'stopped', 'finished'}, 'waiting': {'theirs'}, 'done': {'closed'}}

# ASK OWNER: where two surfaces say different things of one task today. The record did not pick - each surface reads what it read
ASK = {n: f'ASK OWNER ({q}' for q, names in {
    "a): All reads only the tags and the run rows - a run that ended by the worker's own word (failed, stopped, finished, timed out) or left "
    "only a transcript is `agent stopped` / `agent done` on the rail and the list, and still `queued` (unassigned: `asked`) on All":
        'said_failed said_failed_unassigned said_stopped said_finished said_finished_unassigned transcript_only timed_out held_after_a_run '
        'finished_with_a_draft chat_failed',
    "b): mail after the agent's last session - the rail says `asked you` (the message is what is open), the list and the stage still say "
    "how the old session ended, All `queued` or `saved`": 'mail_after_finished mail_after_stopped mail_after_failed mail_after_saved',
    "c): an older run failed and the latest ended fine - the rail and All say `agent stopped` (any run that stopped), the list `queued` "
    "and the stage `to start` (the latest run only)": 'failed_then_ran_fine',
    "d): a session that finished by its report, with no `finished` word from the worker - the rail and All say `waiting to start`, "
    "the list `agent stopped`": 'finished_by_its_report',
    "e): a saved / interrupted tag on a task no agent holds and no worker wrote on - the rail says `on you`, All and the list "
    "`saved` / `agent stopped`": 'saved_tag_alone interrupted_unassigned',
    "f): a chat agent done for now - the list says `agent done` always; the rail says it only while the chat is live or remembered as "
    "idled out, and after a restart `agent stopped` (a saved session) or plain `on you` (none); All says `blocked` live, else `asked`":
        'chat_parked chat_idled_out chat_after_restart chat_after_restart_no_session',
    "g): waiting on somebody else - All has no such lane (`asked`), and with unread mail the rail says `on you` while the list and the "
    "stage say waiting": 'waiting_on_them waiting_on_them_with_mail',
}.items() for n in names.split()}


READ = {}
def read(name, tmp_path_factory) -> tuple:
    "(rail, All, key, stage) for the case, each off the surface's own road - one store and one rail build a case."
    if name in READ: return READ[name]
    s = SQLiteStore(str(tmp_path_factory.mktemp(name) / 'one.db')); s.set_setting('funnel_hours', '72', 'fixture')
    tid, live = SAYS[name][0](s); live, seen = list(live), {}
    real = processing_unread.card_for
    def card_for(store, item, compact, *a, **k):
        card = real(store, item, compact, *a, **k)
        if card and card.get('tid') == tid: seen['all'] = (compact.get('row') or {}).get('Lane')      # the row All draws for this item
        return card
    s.reconcile_processing_membership(fixed_now=STAMP); s.activate_processing_reads(fixed_now=STAMP, live_state=live)
    funnel.invalidate(); funnel.forget_states()
    with mock.patch('taskuary.terminal.live_sessions', return_value=live), mock.patch.object(processing_unread, 'card_for', card_for), \
         mock.patch.dict(general.IDLED, {tid: 'n1'} if name in IDLED else {}):
        row = next(i for i in funnel.build(s, live_state=live, keep_surfaced=True)['items'] if i.get('tid') == tid)
        sess, t = next((x for x in live if x['taskId'] == tid), None), s.get_task(tid)
        out = (row['lane'] + ('/done' if row.get('finished') or row.get('chat_done') else ''), seen.get('all'),
               stages.state_of(s, t, sess), stages.of_task(s, t, session=sess))
    funnel.invalidate(); funnel.forget_states(); s.close()
    return READ.setdefault(name, out)


@pytest.mark.parametrize('name', list(SAYS))
def test_each_surface_reads_what_it_read(name, tmp_path_factory):
    assert read(name, tmp_path_factory) == SAYS[name][1:], f'{name}: (rail, All, list, stage) changed for the owner'


@pytest.mark.parametrize('name', [pytest.param(n, marks=pytest.mark.xfail(strict=True, reason=ASK[n])) if n in ASK else n for n in SAYS])
def test_every_surface_says_the_one_state(name, tmp_path_factory):
    rail, everything, key, stage = read(name, tmp_path_factory)
    said = {ONE.get(w, w) for w in (rail, everything, key)}
    assert len(said) == 1, f'{name}: the rail says {rail}, All {everything}, the list {key}'
    assert said <= STAGE[stage], f'{name}: {said} is stage {stage}'


@pytest.mark.parametrize('name', 'yours handed_not_started saved said_failed said_finished transcript_only mail_after_stopped chat_after_restart'.split())
def test_the_old_names_read_the_record(name, tmp_path):
    "Every reader of a task's agent state is a reading of the one record: none works it out for itself again."
    s = SQLiteStore(str(tmp_path / 'one.db')); tid, _ = SAYS[name][0](s); t = s.get_task(tid)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        st = taskstate.task_state(s, tid=tid)
        assert funnel.idle_state(s, tid) == st.idle and funnel.agent_left(s, tid) == bool(st.left) and funnel.session_saved(s, tid) == st.saved
        assert funnel.news_since_agent(s, tid) == st.news and funnel.run_failed(s, tid) == st.failed
        assert taskstate.state(s, t) == taskstate.task_state(s, t).key == stages.state_of(s, t)
    s.close()


@pytest.mark.parametrize('name', 'yours handed_not_started saved said_failed said_stopped said_finished transcript_only chat_after_restart'.split())
def test_a_rail_row_reads_its_task_once(name, tmp_path):
    """One record a row, and each fact on it read once: the card read its task's events, transcript and runs again for every rule it asked
    - four times over for one lane word."""
    s = SQLiteStore(str(tmp_path / 'one.db')); s.set_setting('funnel_hours', '72', 'fixture'); tid, _ = SAYS[name][0](s)
    s.reconcile_processing_membership(fixed_now=STAMP); s.activate_processing_reads(fixed_now=STAMP, live_state=[])
    funnel.invalidate(); funnel.forget_states()
    real, made, n = processing_unread.card_for, [], {}
    def card_for(store, *a, **k):
        facts = ('worker_events', 'last_transcript', 'list_runs', 'last_inbound_on_task')
        def counted(f): return lambda *aa, **kk: (n.__setitem__(f, n.get(f, 0) + 1), getattr(type(store), f)(store, *aa, **kk))[1]
        def record(*aa, **kk): made.append(1); return taskstate.TaskState(*aa, **kk)
        with mock.patch.multiple(store, **{f: counted(f) for f in facts}), mock.patch.object(taskstate, 'task_state', record): return real(store, *a, **k)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]), mock.patch.object(processing_unread, 'card_for', card_for):
        assert any(i.get('tid') == tid for i in funnel.build(s, live_state=[], keep_surfaced=True)['items'])
    assert len(made) <= 1, f'{name}: the row built {len(made)} records of its one task'
    assert all(v <= 1 for v in n.values()), f'{name}: the row read a fact more than once - {n}'
    funnel.invalidate(); funnel.forget_states(); s.close()
