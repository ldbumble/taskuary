"""An open task stays under Tasks when its agent is done for now (the agent walk, 2026-11-09).

Erin asked how many seats. The chat agent drafted the answer, the owner pressed Send, and the agent's next turn asked nothing: "Nothing is
left on my side." The task was still open - and its row left Tasks for the Reports pile, then left the rail at the next Next as a report
that had been read. Its "done for now" row was built on the `report` lane, from before the rail had sections. Rows never move sections:
it is the owner's open task, worded "agent done", where it was. Invented people."""
from datetime import datetime
from unittest import mock

import pytest

from taskuary import funnel, general, lanes
from taskuary.store import SQLiteStore

STAMP = datetime.now().replace(microsecond=0).isoformat(sep=' ')


@pytest.fixture
def store(tmp_path):
    s = SQLiteStore(str(tmp_path / 'done.db')); s.set_setting('funnel_hours', '72', 'fixture')
    yield s
    s.close()


def answered(s):
    tid = s.create_task({'Title': 'Seats and budget for Erin', 'Kind': 'general', 'Status': 'in_progress'}, 'triage')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'x:seats', 'ConversationId': 'c:seats', 'Channel': 'email', 'Subject': 'Seats',
                         'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': STAMP, 'BodyText': 'How many seats?', 'Status': 'routed'})
    s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'approved', 'DraftText': 'Forty seats.', 'FinalText': 'Forty seats.'})
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Sent. Nothing is left on my side.')
    s.reconcile_processing_membership(fixed_now=STAMP); s.activate_processing_reads(fixed_now=STAMP, live_state=[])
    return tid


def row(s, tid, live):
    funnel.invalidate(); funnel.forget_states()
    with mock.patch('taskuary.terminal.live_sessions', return_value=live):
        return next(i for i in funnel.build(s, live_state=live, keep_surfaced=True)['items'] if i.get('tid') == tid)


def test_the_row_of_a_chat_agent_done_for_now_is_under_tasks(store):
    tid = answered(store)
    parked = [{'taskId': tid, 'sid': 'g1', 'agent': 'assistant', 'mode': 'assistant', 'alive': True, 'started': STAMP, 'waiting': True,
               'state': 'parked', 'idle': 0, 'tail': []}]
    r = row(store, tid, parked)
    assert (r['kind'], r.get('chat_done'), funnel.lane_word(r)) == ('wrapup', True, 'agent done')
    assert lanes.lane_section(r['lane']) == 'task' and lanes.band_of(r) == 2, 'an open task, the owner\'s - never a report that landed'


def coding(s):
    tid = s.create_task({'Title': 'late_fee is wrong in northwind/ledger', 'Kind': 'coding', 'Status': 'in_progress'}, 'triage')
    s.add_message({'TaskId': tid, 'ExternalId': 'x:fee', 'ConversationId': 'c:fee', 'Channel': 'email', 'Subject': 'late_fee',
                   'FromName': 'Ray Colton', 'FromEmail': 'ray@northwind.example', 'SentAt': STAMP, 'BodyText': 'Three tests fail.', 'Status': 'routed'})
    s.reconcile_processing_membership(fixed_now=STAMP); s.activate_processing_reads(fixed_now=STAMP, live_state=[])
    return tid, [{'taskId': tid, 'sid': 'c1', 'agent': 'coding', 'mode': 'terminal', 'alive': True, 'started': STAMP, 'waiting': True,
                  'state': 'parked', 'idle': 0, 'tail': []}]


def test_a_coding_agent_whose_turn_ended_with_nothing_left_is_done_for_now(store):
    "Agent walk 2: it pushed, said 'Nothing is left to do on this task' - and the row read 'agent waiting on you' with no button lit."
    from taskuary import landing, rulebook, taskstate, workerstate as ws
    tid, parked = coding(store)
    key = lambda: taskstate.task_state(store, tid=tid, session=parked[0]).key
    assert (row(store, tid, parked)['lane'], key()) == ('blocked', 'blocked'), 'a pane just opened has done nothing: it waits on you'
    ws.record(store, tid, 'c1', 'working', source='hook'); ws.record(store, tid, 'c1', 'turn_end', text='Nothing is left to do on this task.', source='hook')
    r = row(store, tid, parked)
    assert (r['kind'], r.get('chat_done'), funnel.lane_word(r), key()) == ('wrapup', True, 'agent done', 'agentdone')
    assert lanes.lane_section(r['lane']) == 'task', 'still open, still under Tasks'
    with mock.patch('taskuary.terminal.live_sessions', return_value=parked): lit = rulebook.recommended(store, r)
    assert ((lit or {}).get('verb'), (lit or {}).get('label')) == ('close', 'Mark done'), 'Mark done is the lit button'
    landing._save(store, tid, {'proposal': {'how': 'push', 'at': STAMP}})
    assert (row(store, tid, parked)['lane'], key()) == ('blocked', 'blocked'), 'its Push card waits on you'
    landing._save(store, tid, {'proposal': {'how': 'push', 'at': STAMP}, 'landed': {'how': 'push', 'at': STAMP[:-1] + 'z'}})
    assert key() == 'agentdone', 'pushed: nothing is left'
