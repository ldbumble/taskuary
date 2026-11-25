"""THE ASSISTANT SEES WHAT AN AGENT TASK HOLDS (the owner, 2026-11-07). Asked "which of my tasks are waiting on me, and what does each one
need?", the Assistant said of a task with two emails ready to send: "it's waiting on you. I haven't seen what it needs yet." Its reads
named the task, never the emails, the post or the agent's question. Now one read (card.lines, from the cards the task's own page
draws) gives each item a short line and its button, and the turn's rail, pipe.list, approvals.list and the dock all carry it. Invented people.
"""
import json
import pytest
from taskuary import card
from unittest import mock

from taskuary import concierge, general, lookups, slots, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from test_worker_events import live


@pytest.fixture(autouse=True)
def _mailbox_sends():
    "A mailbox that sends: its emails' cards draw Send (card.presses - with none, they draw Connect email)."
    with mock.patch('taskuary.capabilities.can_send_draft', return_value=True): yield


def agent_task(s):
    tid = s.create_task({'Title': 'Compare expense tools', 'Kind': 'general', 'Status': 'in_progress', 'OriginBase': 'owner'}, 'owner')
    slots.draft(s, tid, 'Hi Paula - the comparison is attached.', 'paula@northwind.example', 'Expense tools')
    slots.draft(s, tid, 'Hi Gail - the comparison is attached.', 'gail@northwind.example', 'Expense tools')
    s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'the agent proposes to post on LinkedIn',
                  'DraftText': json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'We picked an expense tool.'})})
    return tid


def test_each_thing_a_task_holds_is_one_line_with_its_button():
    s = MemoryStore(); tid = agent_task(s)
    term.SESSIONS['q1'] = live(tid, 'q1')
    try:
        ws.record(s, tid, 'q1', 'input_needed', text='Should the comparison include Ramp?', source='api')
        got = card.lines(s, tid)
    finally: term.SESSIONS.pop('q1', None)
    lines = [x['line'] for x in got]
    assert lines[:2] == ['an email to paula@northwind.example is drafted - Send sends it', 'an email to gail@northwind.example is drafted - Send sends it']
    assert lines[2] == 'a LinkedIn post waits for your Approve' and lines[3] == 'the agent asks: Should the comparison include Ramp?'
    assert [x['verb'] for x in got] == ['approve', 'approve', 'approve', 'answer_agent']
    # ...and what keeps a Send-and-close open is said as before, the question aside
    assert [x['says'] for x in card.lines(s, tid, asks=False)][:2] == ['an email this task owes still waits for your Send'] * 2


def test_the_assistant_the_dock_and_their_reads_all_carry_it():
    s = MemoryStore(); tid = agent_task(s)
    rail = concierge._rail_block({'items': [{'tid': tid, 'ref': f'TQ-{tid:04}', 'who': 'Alex Doyle', 'title': 'Compare expense tools',
                                             'lane': 'approve'}]}, store=s)
    assert '· an email to gail@northwind.example is drafted - Send sends it [rv' in rail and 'WHAT WAITS ON THE OWNER' in rail
    assert 'an email to paula@northwind.example' in general.dock_snapshot(s)
    assert 'a LinkedIn post waits for your Approve' in lookups.approvals_list(s, {})
    with mock.patch('taskuary.funnel.pile', return_value={'items': [{'tid': tid, 'who': 'Alex Doyle', 'title': 'Compare expense tools', 'lane': 'approve'}]}):
        assert 'an email to gail@northwind.example' in lookups.pipe_list(s, {})


def test_the_rail_the_assistant_reads_says_where_each_task_stands_and_counts_what_waits_on_him_by_it():
    """Walk 21, the phone: "Five items need you today" - the dashboard said four. One of the five he had answered by email himself, its row
    still under the title it was opened with ("Erin needs you to confirm ..."); the model read each row's lane word over its title. A task's
    row now says where it stands (taskstate.standing, the header's and the dashboard's reading), and the count of what waits on him is that."""
    s = MemoryStore(); tid = agent_task(s)
    done = s.create_task({'Title': 'Erin needs you to confirm Friday at 2 pm', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    rail = concierge._rail_block({'items': [{'tid': tid, 'ref': f'TQ-{tid:04}', 'who': 'Alex Doyle', 'title': 'Compare expense tools', 'lane': 'approve'},
                                            {'tid': done, 'ref': f'TQ-{done:04}', 'who': 'Erin Blake', 'title': 'Erin needs you to confirm Friday at 2 pm',
                                             'lane': 'blocked'}]}, store=s)
    erin = next(r for r in rail.splitlines() if f'TQ-{done:04}' in r)
    assert 'no input awaited from anyone' in erin and 'waiting on you' not in erin, erin
    assert f'waiting for your input: 1 - TQ-{tid:04}' in rail, rail
