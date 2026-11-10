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
