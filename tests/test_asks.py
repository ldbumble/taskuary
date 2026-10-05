"""The assistant remembers what you asked, and says when it moves (spec 2026-10-05-assistant-remembers-asks-design.md).

An ask is a task marked with where you asked. Its state is its rail lane; a move into a lane that needs you, or its end,
is said once at that door - the phone only when you asked from it or the walk is handed there.
"""
from unittest import mock

import pytest

from taskuary import asks, concierge, remote_assistant
from taskuary.store import MemoryStore


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def made(s, text='Check the four tabs', **k):
    with mock.patch('taskuary.concierge._handoff_brief', side_effect=lambda st, tid, job: job), \
         mock.patch('taskuary.concierge._handoff_title', return_value=text):
        return concierge.setup_task(s, text, 'owner', kind='general', agent_job=True, **k)['taskId']


# ── the mark ─────────────────────────────────────────────────────────────────────────────
def test_a_chat_ask_on_the_desktop_is_marked_desktop(s):
    assert s.get_task(made(s))['AskedVia'] == 'desktop'


def test_an_ask_from_the_phone_is_marked_with_its_chat(s):
    remote_assistant._ASKING.chat = {'channel': 'whatsapp', 'chat': 'c1@example.com', 'connector_id': 3}
    try: tid = made(s)
    finally: remote_assistant._ASKING.chat = None
    assert s.get_task(tid)['AskedVia'] == 'whatsapp:c1@example.com' and asks.of(s.get_task(tid)) == 'whatsapp:c1@example.com'


def test_a_task_made_with_new_is_marked_desktop(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    with mock.patch.object(server, 'store', s):
        tid = TestClient(server.app).post('/api/tasks', json={'Title': 'Pull the August numbers'}).json()['taskId']
    assert s.get_task(tid)['AskedVia'] == 'desktop'


def test_triage_work_is_not_an_ask_and_the_mark_survives_an_update(s):
    mail = s.create_task({'Title': 'From mail', 'Kind': 'task', 'Source': 'email'}, 'triage')
    assert asks.of(s.get_task(mail)) is None
    tid = made(s); s.update_task(tid, {'Priority': 'high'}, 'owner')
    assert s.get_task(tid)['AskedVia'] == 'desktop'


# ── where an ask stands: its rail lane, in the rail's words ──────────────────────────────
def rail(*items):
    return mock.patch('taskuary.asks._rail', return_value=list(items))


def test_the_state_is_the_rail_lane_and_its_sentence(s):
    tid = made(s)
    with rail({'tid': tid, 'lane': 'blocked', 'why': 'the agent asked you: which branch?'}):
        assert asks.state(s, tid) == ('blocked', 'the agent asked you: which branch?')


def test_an_approve_lane_with_emails_says_how_many(s):
    from taskuary import slots
    tid = made(s); slots.add(s, tid, [{'to': 'paula@northwind.example'}, {'to': 'ray@northwind.example'}], 'owner')
    slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')
    with rail({'tid': tid, 'lane': 'approve', 'why': '1 email drafted for you to send'}):
        lane, says = asks.state(s, tid)
    assert lane == 'approve' and '1 of 2 emails drafted' in says


def test_a_closed_ask_is_finished_with_the_agents_summary(s):
    tid = made(s); s.add_comment(tid, 'coder', 'agent', 'CODER REPORT\nSummary: checked all four tabs, two hold items.')
    s.update_task(tid, {'Status': 'done'}, 'coder')
    with rail():
        lane, says = asks.state(s, tid)
    assert lane == 'finished' and 'two hold items' in says


def test_off_the_rail_and_open_is_quiet(s):
    tid = made(s)
    with rail(): assert asks.state(s, tid)[0] == 'quiet'


def test_an_agent_touched_it_or_not(s):
    tid = made(s); todo = s.create_task({'Title': 'Call the bank', 'AskedVia': 'desktop'}, 'owner')
    assert asks.agent_touched(s, tid) and not asks.agent_touched(s, todo)


def test_the_real_rail_reads_approve_for_drafted_emails(s):
    from taskuary import funnel, slots
    tid = made(s); slots.add(s, tid, [{'to': 'paula@northwind.example'}], 'owner')
    slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example'); funnel.invalidate()
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        assert asks.state(s, tid)[0] == 'approve'
