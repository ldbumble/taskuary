"""A task says what closes it: output slots on the checklist (spec 2026-10-05-task-close-slots-design.md).

The shape: one ask, four addressed drafts, each approved on its own, the task closing when the last is sent.
"""
import json
from unittest import mock

import pytest

from taskuary import slots
from taskuary.store import MemoryStore

FOUR = [{'to': 'paula@northwind.example', 'about': 'where tab 1 stands'}, {'to': 'ray@northwind.example', 'about': 'where tab 2 stands'},
        {'to': 'Gail Moreno', 'about': 'where tab 3 stands'}, {'to': 'erin@northwind.example', 'about': 'where tab 4 stands'}]


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def typed(s, outputs=FOUR):
    tid = s.create_task({'Title': 'Check the four tabs', 'Kind': 'general', 'Status': 'open', 'Source': 'assistant'}, 'owner')
    s.set_task_checklist(tid, ['Check the four tabs'], 'owner')
    slots.add(s, tid, outputs, 'owner')
    return tid


def test_clean_keeps_known_kinds_and_drops_junk():
    got = slots.clean([{'to': 'a@example.com', 'about': 'x'}, {'to': '', 'about': 'y'}, 'nope', {'about': 'z'},
                       {'to': 'b@example.com', 'about': 'w', 'kind': 'fax'}])
    assert [g['out'] for g in got] == [{'kind': 'email', 'to': 'a@example.com', 'subject': ''}]


def test_slots_ride_on_the_checklist(s):
    tid = typed(s)
    items = s.task_checklist(tid)
    assert len(items) == 5 and items[0].get('out') is None
    assert [i['out']['to'] for i in items[1:]] == [o['to'] for o in FOUR]
    assert len(slots.open_(s, tid)) == 4


def test_a_name_is_kept_as_said_never_guessed_into_an_address(s):
    tid = typed(s)
    assert slots.open_(s, tid)[2]['out']['to'] == 'Gail Moreno'


def test_rewording_another_item_keeps_the_slots(s):
    tid = typed(s); before = s.task_checklist(tid)
    slots.mark(s, tid, before[1]['id'], rid=77)
    s.set_task_checklist(tid, ['Check all four tabs'] + [i['text'] for i in before[1:]], 'owner')
    after = s.task_checklist(tid)
    assert after[1]['out'] == before[1]['out'] and after[1]['rid'] == 77


def test_the_agent_sees_its_slots_and_how_to_fill_them(s):
    tid = typed(s); sid = slots.open_(s, tid)[0]['id']
    md = s.checklist_markdown(tid)
    assert 'email to paula@northwind.example' in md and f'--slot {sid}' in md


def test_a_slot_draft_is_never_the_tasks_reply(s):
    tid = typed(s)
    s.add_review({'TaskId': tid, 'Kind': slots.KIND, 'Status': 'pending', 'DraftText': 'hi',
                  'Deliver': json.dumps({'channel': 'email', 'to': ['paula@northwind.example'], 'subject': 'Tab 1', 'slot': 'x'})})
    assert s.pending_review(tid) is None and s.pending_review(tid, live_only=False) is None
