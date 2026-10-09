"""A task typed into + New skips triage, so it had no checklist (the owner, 2026-10-09: "when i create task the task list looks
weird?? (no checkboxes?)"). + New asks for it to be read once it exists: each thing asked becomes a box, as on a promoted mail."""
import json
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server
from taskuary.store import MemoryStore

ASK = json.dumps({'summary': 'x', 'checklist': ['Supervisor sheet downloads as a template', 'Supervisors come from the HR feed'],
                  'outputs': [{'to': 'erin@northwind.example', 'about': 'tell her it is live'}]})


def test_new_reads_the_words_into_boxes_and_the_emails_they_ask_for():
    s, old = MemoryStore(), server.store
    server.store = s
    try:
        c = TestClient(server.app)
        tid = c.post('/api/tasks', json={'Title': '1. Supervisor sheet template 2. HR feed for supervisors, then tell Erin',
                                         'Summary': '1. Supervisor sheet template 2. HR feed for supervisors, then tell Erin'}).json()['taskId']
        assert s.task_checklist(tid) == []                              # making it reads nothing - no model on that road
        with mock.patch('taskuary.concierge.brain', return_value=lambda *a, **k: ASK):
            assert c.post(f'/api/tasks/{tid}/read-ask').json() == {'ok': True}
        items = s.task_checklist(tid)
    finally: server.store = old
    assert [i['text'] for i in items if not i.get('out')] == ['Supervisor sheet downloads as a template', 'Supervisors come from the HR feed']
    assert [i['out']['to'] for i in items if i.get('out')] == ['erin@northwind.example']
    assert s.get_task(tid)['Summary'].startswith('1. Supervisor sheet')    # the owner's own words stay the summary


def test_a_failing_brain_leaves_the_task_as_typed():
    s, old = MemoryStore(), server.store
    server.store = s
    try:
        c = TestClient(server.app)
        tid = c.post('/api/tasks', json={'Title': 'look at the export'}).json()['taskId']
        with mock.patch('taskuary.concierge.brain', side_effect=RuntimeError('no brain')):
            assert c.post(f'/api/tasks/{tid}/read-ask').status_code == 200
        assert s.task_checklist(tid) == []
    finally: server.store = old
