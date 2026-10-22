"""Every press on the task page leaves a receipt (Stream B, the owner 2026-10-18: "every act leaves a receipt"). The page's presses run
down the operations road (taskOps.runOperation), so each is recorded once, and when the task is the one on the Assistant's table its
receipt is a line in the chat. Nothing offers to take it back (the owner, 2026-10-19: "no take it back button. hate that"): a wrong Mark
done is put right with Reopen task, a priority with the priority picker."""
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


def undos(s, dock):
    """Any line of the chat that offers to take an act back - there are none now."""
    return [r for r in cards(s, dock) if (isinstance(r, tuple) and (r[1].get('undo') or 'Undo:' in r[0])) or (isinstance(r, str) and 'Undo:' in r)]


# ── each act does what it says, and hands back nothing to undo ───────────────────────────────
def test_mark_done_and_reopen_are_two_acts_and_neither_carries_an_undo(s, c):
    tid = task(s)
    out = run(c, 'task.complete', tid)
    assert out['status'] == 'done' and s.get_task(tid)['Status'] == 'done' and 'undo' not in out['outcome']
    back = run(c, 'task.reopen', tid)
    assert s.get_task(tid)['Status'] == 'open' and 'undo' not in (back['outcome'] or {})


def test_a_fresh_choice_of_holder_or_day_is_held_to_the_contract(s, c):
    tid = task(s, Assignee='person:gail@northwind.example', DueAt='2026-01-05')
    assert run(c, 'task.update', tid, {'assignee': 'none'})['status'] == 'done' and not s.get_task(tid)['Assignee']
    # a fresh choice may name only the owner or a worker, and never a day already gone - there is no put-back to slip one past
    assert run(c, 'task.update', tid, {'assignee': 'person:gail@northwind.example'})['status'] == 'error'
    assert run(c, 'task.update', tid, {'assignee': 'person:gail@northwind.example', '_undo': True})['status'] == 'error'
    assert run(c, 'task.update', tid, {'due': '2026-01-05', '_undo': True})['status'] == 'error'


def test_a_tick_and_an_untick_each_name_their_own_box(s, c):
    tid = task(s)
    s.set_task_checklist(tid, ['Print the form', 'Sign it'], 'owner')
    box = s.task_checklist(tid)[1]
    run(c, 'task.check', tid, {'item': '2', 'id': box['id'], 'done': True})
    assert s.task_checklist(tid)[1]['done']
    run(c, 'task.check', tid, {'item': '2', 'id': box['id'], 'done': False})
    assert not s.task_checklist(tid)[1]['done']


def test_the_box_named_by_id_wins_over_a_number_read_off_a_moved_list(s, c):
    tid = task(s)
    s.set_task_checklist(tid, ['Print the form', 'Sign it'], 'owner')
    box = s.task_checklist(tid)[1]
    run(c, 'task.check', tid, {'item': '1', 'id': box['id'], 'done': True})
    assert [i['done'] for i in s.task_checklist(tid)] == [False, True]
    assert run(c, 'task.check', tid, {'item': '1', 'id': 'gone', 'done': True})['status'] == 'error'


def test_a_reworded_list_and_a_kind_change_run_as_asked(s, c):
    tid = task(s, Kind='general')
    s.set_task_checklist(tid, ['Print the form'], 'owner')
    run(c, 'task.checklist', tid, {'items': ['Print the form', 'Post it']})
    assert [i['text'] for i in s.task_checklist(tid)] == ['Print the form', 'Post it']
    run(c, 'task.set_kind', tid, {'kind': 'coding'})
    assert s.get_task(tid)['Kind'] == 'coding'


def test_not_a_task_deletes(s, c):
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


# ── on the table: a press is a badge on its card, never a line - and nothing to take back ────────
# (the owner, 2026-10-22: "why do we have done-mark done text. we don't need that text ever. I hate free text" ... "put a little
# animation on the corner of the past task - like button marked done not free text")
def drawn(s, dock, tid):
    """The item's own line in the chat - the card the walk drew for it - as the page reads it back. Its count of lines."""
    concierge.record(s, dock, 'assistant', 'Next up: a task.', {'kind': 'task', 'key': f'task:{tid}', 'tid': tid, 'title': 'Send Erin the signed form'})
    return len(cards(s, dock))


@pytest.mark.parametrize('kind,params', [('task.complete', {}), ('task.update', {'priority': 'high'}), ('task.check', {'item': '1'})])
def test_a_press_on_the_tables_task_is_its_cards_badge_and_no_line(s, c, kind, params):
    tid = task(s)
    s.set_task_checklist(tid, ['Print the form'], 'owner')
    dock = on_table(s, tid); n = drawn(s, dock, tid)
    with mock.patch.object(server.live_bus, 'emit') as emit:
        out = run(c, kind, tid, params)
    assert out['status'] == 'done' and out['receipt']               # the words still come back - the phone answers with them
    emit.assert_any_call(server.live_bus.CHAT)                  # the chat reads the badge now, not on its next tick
    rows = cards(s, dock)
    assert len(rows) == n and not any('Done - ' in (r[0] if isinstance(r, tuple) else r) for r in rows)    # no line said
    assert rows[-1][1]['pressed'] == concierge.describe_op(s, operations.history(s, task_id=tid)[0])[0].split(': ')[0]  # the button's label
    assert undos(s, dock) == [] and 'Undo' not in out['receipt']
    assert [o for o in operations.history(s, task_id=tid) if o.get('status') == 'proposed'] == []


def test_mark_done_on_the_table_wears_mark_done(s, c):
    tid = task(s)
    dock = on_table(s, tid); drawn(s, dock, tid)
    run(c, 'task.complete', tid)
    assert cards(s, dock)[-1][1]['pressed'] == 'Mark done'


def test_a_reminder_from_the_table_is_its_cards_badge_and_no_line(s, c):
    tid = task(s)
    dock = on_table(s, tid); n = drawn(s, dock, tid)
    out = c.post(f'/api/tasks/{tid}/remind', json={'until': '2 weeks'}).json()
    assert 'Away until' in out['receipt'] and 'undo' not in out
    rows = cards(s, dock)
    assert len(rows) == n and rows[-1][1]['pressed'] == 'Remind me'


def test_not_a_task_on_the_table_is_no_line_and_nothing_to_take_back(s, c):
    tid = task(s)
    dock = on_table(s, tid); n = drawn(s, dock, tid)
    out = run(c, 'task.not_a_task', tid)
    assert out['status'] == 'done' and s.get_task(tid) is None
    assert len(cards(s, dock)) == n and undos(s, dock) == []


def test_a_press_that_did_not_go_through_is_still_said(s, c):
    """An error is not a receipt: the line saying it failed, with its way on, stays - and the card wears no badge."""
    tid = task(s)
    dock = on_table(s, tid); n = drawn(s, dock, tid)
    with mock.patch.object(server, '_run_kind', side_effect=RuntimeError('the mailbox is not answering')):
        out = run(c, 'task.complete', tid)
    assert out['status'] == 'error' and out['receipt'].startswith('Not done - ')
    rows = cards(s, dock)
    assert len(rows) == n + 1 and rows[-1][0].startswith('Not done - ') and 'pressed' not in rows[-2][1]


def test_the_same_press_off_the_table_records_the_operation_and_says_nothing_in_the_chat(s, c):
    tid, other = task(s), task(s, Title='Book the courier')
    dock = on_table(s, other)
    run(c, 'task.update', tid, {'priority': 'low'})
    assert operations.history(s, task_id=tid)[0]['kind'] == 'task.update'
    assert cards(s, dock) == []
