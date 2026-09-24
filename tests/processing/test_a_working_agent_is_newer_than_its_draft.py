"""The latest action is the status: an agent still working is newer than the reply it drafted.

A coder wrote its reply a minute into the session (coder.agent_reply takes the held draft back out as
pending) and then worked on for forty more - edits, a build. The rail said "reply ready" the whole
time, offering to send words the work was still moving under (the owner, 2026-09-24: "it says reply
ready but agent is still working? ... meaning the latest action is the status").

A draft outranked a live session only because a WORKING agent had no card of its own: a parked or
asking agent (funnel.from_agents) already wins. Now working wins too, and the reply is back the
moment the agent parks or its session ends.
"""
from datetime import datetime
from unittest import mock

import pytest

from taskuary import funnel
from taskuary.store import MemoryStore, SQLiteStore

STAMP = datetime.now().replace(microsecond=0).isoformat(sep=' ')


def drafted(store, *, canonical):
    tid = store.create_task({'Title': 'Budget tab missing', 'Kind': 'coding', 'Status': 'in_progress',
                             'Assignee': 'agent:coder'}, 'triage')
    mid = store.add_message({'TaskId': tid, 'ExternalId': 'x:budget', 'ConversationId': 'c:budget',
                             'Channel': 'email', 'Subject': 'Budget tab missing', 'FromName': 'Erin Blake',
                             'FromEmail': 'erin@northwind.example', 'SentAt': STAMP,
                             'BodyText': 'I still cannot see the budget tab.', 'Status': 'routed'})
    store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending',
                      'DraftText': 'Your access is fixed.', 'Reason': 'coder wrote this reply in its session - approve to send'})
    if canonical:
        store.reconcile_processing_membership(fixed_now=STAMP)
        store.activate_processing_reads(fixed_now=STAMP, live_state=[])
    return tid


def session(tid, *, waiting):
    return [{'taskId': tid, 'sid': 's-budget', 'agent': 'coder', 'label': 'coder', 'alive': True,
             'started': STAMP, 'waiting': waiting, 'idle': 0, 'tail': ['npm run build']}]


def lane(store, tid, live):
    funnel.invalidate(); funnel.forget_states()
    with mock.patch('taskuary.terminal.live_sessions', return_value=live):
        items = funnel.build(store, live_state=live, keep_surfaced=True)['items']
    return next(i['lane'] for i in items if i.get('tid') == tid)


@pytest.fixture(params=['canonical', 'legacy'])
def store(request, tmp_path):
    s = SQLiteStore(str(tmp_path / 'draft.db')) if request.param == 'canonical' else MemoryStore()
    s.set_setting('funnel_hours', '72', 'fixture')
    s.canonical = request.param == 'canonical'
    yield s
    if s.canonical: s.cx.close()


def test_a_working_agent_is_the_status_not_its_draft(store):
    tid = drafted(store, canonical=store.canonical)
    assert lane(store, tid, session(tid, waiting=False)) == 'working'


def test_the_reply_is_ready_again_once_the_session_ends(store):
    tid = drafted(store, canonical=store.canonical)
    assert lane(store, tid, []) == 'approve'


def test_a_parked_agent_still_speaks_for_the_task(store):
    # unchanged: an agent waiting at its prompt already outranked the draft
    tid = drafted(store, canonical=store.canonical)
    assert lane(store, tid, session(tid, waiting=True)) == 'blocked'
