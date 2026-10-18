"""Every press on the task page leaves a receipt, and a put-back where one is possible (Stream B, the owner 2026-10-18: "every act
leaves a receipt"). The page's presses run down the operations road (taskOps.runOperation), so each is recorded once, and when the task
is the one on the Assistant's table its receipt is a line in the chat with Take it back under it. An undo that ran offers no undo."""
import json, re
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import concierge, general, operations, server, terminal
from taskuary.store import MemoryStore


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


@pytest.fixture
def c(s):
    with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        yield TestClient(server.app)


def task(s, **kw):
    return s.create_task({'Title': 'Send Erin the signed form', 'Kind': 'task', 'Status': 'open', 'Priority': 'normal', **kw}, 'owner')


def on_table(s, tid):
    dock, _ = general.dock_task(s)
    concierge.set_current(s, dock['TaskId'], f'task:{tid}')
    return dock['TaskId']


def run(c, kind, target, params=None):
    op = c.post('/api/operations', json={'kind': kind, 'target': target, 'params': params or {}}).json()
    return c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']}).json()


def cards(s, dock):
    out = []
    for r in general.chat_rows(s, dock):
        m = re.search(r'<!-- tq:card (.*) -->', r.get('Body') or '', re.S)
        out.append((r.get('Body') or '').split('\n\n<!--')[0] if not m else (r['Body'].split('\n\n<!--')[0], json.loads(m.group(1))))
    return out


def undo_of(s, dock):
    """The newest Take it back the chat holds: (its line, the proposal it runs)."""
    for row in reversed(cards(s, dock)):
        if isinstance(row, tuple) and row[1].get('undo'): return row[0], operations.get(s, row[1]['op'])
    return None, None


def take_back(c, op): return c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']}).json()


# ── the undo each reversible task act names ─────────────────────────────────────────────────
def test_mark_done_offers_reopen_and_reopen_offers_mark_done(s, c):
    tid = task(s)
    out = run(c, 'task.complete', tid)
    assert out['status'] == 'done' and s.get_task(tid)['Status'] == 'done'
    assert out['outcome']['undo'] == {'kind': 'task.reopen', 'target': tid, 'params': {}, 'label': f'Reopen task TQ-{tid:04d}'}
    back = run(c, 'task.reopen', tid)
    assert s.get_task(tid)['Status'] == 'open' and back['outcome']['undo']['kind'] == 'task.complete'
    # ...and a close of a task already closed has nothing to put back
    run(c, 'task.complete', tid)
    assert run(c, 'task.complete', tid)['outcome']['undo'] is None


def test_a_priority_change_puts_the_old_priority_back(s, c):
    tid = task(s)
    out = run(c, 'task.update', tid, {'priority': 'urgent'})
    assert s.get_task(tid)['Priority'] == 'urgent'
    assert out['outcome']['undo'] == {'kind': 'task.update', 'target': tid, 'params': {'priority': 'normal'}, 'label': 'Put priority back to normal'}


def test_unassigned_is_a_change_and_the_old_holder_comes_back_even_a_person(s, c):
    tid = task(s, Assignee='person:gail@northwind.example')
    out = run(c, 'task.update', tid, {'assignee': 'none'})
    assert out['status'] == 'done' and not s.get_task(tid)['Assignee']
    u = out['outcome']['undo']
    assert u['params'] == {'assignee': 'person:gail@northwind.example'}
    # a fresh choice may name only the owner or a worker - the put-back restores what was there
    assert run(c, 'task.update', tid, {'assignee': 'person:gail@northwind.example'})['status'] == 'error'
    assert run(c, 'task.update', tid, {**u['params'], '_undo': True})['status'] == 'done'
    assert s.get_task(tid)['Assignee'] == 'person:gail@northwind.example'


def test_a_due_day_moved_puts_the_old_day_back_even_one_gone(s, c):
    tid = task(s, DueAt='2026-01-05')
    out = run(c, 'task.update', tid, {'due': 'none'})
    assert out['outcome']['undo']['params'] == {'due': '2026-01-05'}
    assert run(c, 'task.update', tid, {'due': '2026-01-05', '_undo': True})['status'] == 'done'
    assert str(s.get_task(tid)['DueAt'])[:10] == '2026-01-05'


def test_a_tick_is_put_back_by_its_own_box_and_an_untick_too(s, c):
    tid = task(s)
    s.set_task_checklist(tid, ['Print the form', 'Sign it'], 'owner')
    box = s.task_checklist(tid)[1]
    out = run(c, 'task.check', tid, {'item': '2', 'id': box['id'], 'done': True})
    assert s.task_checklist(tid)[1]['done']
    assert out['outcome']['undo'] == {'kind': 'task.check', 'target': tid, 'params': {'item': '2', 'id': box['id'], 'done': False}, 'label': 'Untick Sign it'}
    back = run(c, 'task.check', tid, out['outcome']['undo']['params'])
    assert not s.task_checklist(tid)[1]['done'] and back['outcome']['undo']['params']['done'] is True


def test_the_box_named_by_id_wins_over_a_number_read_off_a_moved_list(s, c):
    tid = task(s)
    s.set_task_checklist(tid, ['Print the form', 'Sign it'], 'owner')
    box = s.task_checklist(tid)[1]
    run(c, 'task.check', tid, {'item': '1', 'id': box['id'], 'done': True})
    assert [i['done'] for i in s.task_checklist(tid)] == [False, True]
    assert run(c, 'task.check', tid, {'item': '1', 'id': 'gone', 'done': True})['status'] == 'error'


def test_a_reworded_list_puts_the_old_words_back(s, c):
    tid = task(s)
    s.set_task_checklist(tid, ['Print the form'], 'owner')
    out = run(c, 'task.checklist', tid, {'items': ['Print the form', 'Post it']})
    assert [i['text'] for i in s.task_checklist(tid)] == ['Print the form', 'Post it']
    assert out['outcome']['undo']['params'] == {'items': ['Print the form']}


def test_a_kind_change_puts_the_old_kind_back_without_teaching(s, c):
    tid = task(s, Kind='general')
    out = run(c, 'task.set_kind', tid, {'kind': 'coding'})
    assert s.get_task(tid)['Kind'] == 'coding'
    assert out['outcome']['undo']['params'] == {'kind': 'general', 'learn': False}


def test_not_a_task_deletes_so_nothing_is_offered_back(s, c):
    tid = task(s)
    out = run(c, 'task.not_a_task', tid)
    assert out['status'] == 'done' and s.get_task(tid) is None and not (out['outcome'] or {}).get('undo')


# ── the page's other presses, each its own handler down the one road ──────────────────────────
def test_a_note_a_question_and_a_trust_each_run_their_page_handler(s, c):
    tid = task(s)
    mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': 'tp-1', 'FromEmail': 'erin@vendor.example', 'FromName': 'Erin Blake',
                         'Subject': 'Signed form', 'BodyText': 'Could you return it?', 'SentAt': '2026-10-18 09:00:00', 'Direction': 'in'})
    assert run(c, 'task.comment', tid, {'text': 'Printed it this morning.'})['status'] == 'done'
    assert any(x.get('Body') == 'Printed it this morning.' for x in s.list_comments(tid))
    assert run(c, 'task.clarify', tid, {'text': 'Which page needs the signature?', 'message_id': mid})['status'] == 'done'
    rv = s.pending_review(tid, 'clarification')
    assert rv['MessageId'] == mid and rv['DraftText'] == 'Which page needs the signature?'
    with mock.patch('taskuary.origin.raise_to') as up:
        assert run(c, 'task.trust', tid)['status'] == 'done'
    up.assert_called_once()


def test_the_pages_split_keeps_both_halves_as_written(s, c):
    tid = task(s)
    out = run(c, 'task.split', tid, {'text': 'Book the courier', 'first': {'title': 'Sign the form'}, 'second': {'title': 'Book the courier'}})
    assert out['status'] == 'done' and s.get_task(out['outcome']['taskId'])['Title'] == 'Book the courier'
    assert s.get_task(tid)['Title'] == 'Sign the form'


def test_the_trust_link_is_never_a_chat_tool():
    from taskuary import toolcatalog
    assert 'task.trust' in operations.KINDS and 'task.trust' not in toolcatalog.PURPOSE


# ── on the table: the receipt is a chat line, with Take it back under it ───────────────────────
@pytest.mark.parametrize('kind,params,undo', [
    ('task.complete', {}, 'Reopen task'),
    ('task.update', {'priority': 'high'}, 'Put priority back to normal'),
    ('task.check', {'item': '1'}, 'Untick Print the form'),
])
def test_a_press_on_the_tables_task_says_so_in_the_chat_with_its_undo(s, c, kind, params, undo):
    tid = task(s)
    s.set_task_checklist(tid, ['Print the form'], 'owner')
    dock = on_table(s, tid)
    with mock.patch.object(server.live_bus, 'emit') as emit:
        out = run(c, kind, tid, params)
    assert out['status'] == 'done' and out['receipt'].startswith('Done - ')
    emit.assert_any_call(server.live_bus.CHAT)                  # the chat reads it now, not on its next tick
    line, op = undo_of(s, dock)
    assert undo in line and op['status'] == 'proposed' and op['params']['_undo'] is True
    # Take it back runs once, and its own receipt offers no undo of itself
    back = take_back(c, op)
    assert back['status'] == 'done' and undo_of(s, dock)[1]['id'] == op['id']


def test_not_a_task_on_the_table_is_a_line_with_nothing_to_take_back(s, c):
    tid = task(s)
    dock = on_table(s, tid)
    out = run(c, 'task.not_a_task', tid)
    assert out['status'] == 'done' and s.get_task(tid) is None
    assert any(isinstance(r, str) and r.startswith('Done - ') for r in cards(s, dock))
    assert undo_of(s, dock) == (None, None)


def test_the_same_press_off_the_table_records_the_operation_and_says_nothing_in_the_chat(s, c):
    tid, other = task(s), task(s, Title='Book the courier')
    dock = on_table(s, other)
    run(c, 'task.update', tid, {'priority': 'low'})
    assert operations.history(s, task_id=tid)[0]['kind'] == 'task.update'
    assert cards(s, dock) == []
