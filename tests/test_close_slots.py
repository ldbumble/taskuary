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


# ── closing waits for every slot ─────────────────────────────────────────────────────────
from taskuary import coder, operations, outbound, verdicts

SENT = {'channel': 'email', 'to': ['x@example.com'], 'cc': []}


def draft(s, tid, i, text='Tab is fine.'):
    it = slots.all_(s, tid)[i]
    rid = s.add_review({'TaskId': tid, 'Kind': slots.KIND, 'Status': 'pending', 'DraftText': text,
                        'Deliver': json.dumps({'channel': 'email', 'to': [it['out']['to']], 'subject': 'Tab', 'slot': it['id'],
                                               'seen': slots.seen(s, tid)})})
    slots.mark(s, tid, it['id'], rid=rid)
    return rid


def approve(s, rid):
    with mock.patch('taskuary.outbound.send_out', return_value=SENT), mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learn.learn_from'):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def mail_task(s):
    from tests.test_review_delivery_safety import make_review
    return make_review(s, task_kind='reply')


def send_reply(s, rid):
    with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learn.learn_from'):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def test_four_slots_stay_open_through_three_sends_and_close_on_the_fourth(s):
    tid = typed(s); rids = [draft(s, tid, n) for n in range(4)]
    for rid in rids[:3]:
        assert approve(s, rid)['ok'] and s.get_task(tid)['Status'] != 'done'
    assert s.get_review(rids[3])['Status'] == 'pending'
    assert approve(s, rids[3])['ok'] and s.get_task(tid)['Status'] == 'done'
    assert all(i['done'] for i in slots.all_(s, tid))


def test_a_rejected_slot_is_dropped_and_counts_as_settled(s):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    with mock.patch('taskuary.learn.learn_from'): verdicts.decide(s, s.get_review(a), 'reject')
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(b)['Status'] == 'pending'
    approve(s, b)
    assert s.get_task(tid)['Status'] == 'done'


@pytest.mark.parametrize('verb', ['no_reply', 'close_unsent'])
def test_not_sending_one_slot_drops_that_slot_not_the_task(s, verb):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    with mock.patch('taskuary.learn.learn_from'): verdicts.decide(s, s.get_review(a), verb)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(b)['Status'] == 'pending'
    assert [i['done'] for i in slots.all_(s, tid)] == [True, False]


def test_a_reply_and_slots_close_only_when_both_are_settled(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    send_reply(s, reply)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(a)['Status'] == 'pending'
    approve(s, a)
    assert s.get_task(tid)['Status'] == 'done'


def test_a_slot_sent_before_the_reply_leaves_the_reply_waiting(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    approve(s, a)
    assert s.get_task(tid)['Status'] != 'done' and s.get_review(reply)['Status'] == 'pending'


def test_a_task_without_slots_closes_on_its_reply_as_before(s):
    tid, mid, reply = mail_task(s)
    send_reply(s, reply)
    assert s.get_task(tid)['Status'] == 'done'


def test_the_closeout_redirect_never_sends_a_slot_as_the_reply(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    s.decide_review(reply, 'rejected', None, 'owner', 'gone')
    co = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': 'merge',
                       'Deliver': json.dumps({'action': 'merge_pr'})})
    with mock.patch('taskuary.proposals.execute', return_value={'ok': True}), mock.patch('taskuary.proposals._action', return_value='merge_pr'), \
         mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch('taskuary.learn.learn_from'):
        verdicts.decide(s, s.get_review(co), 'approve', reply_text='thanks')
    assert not sent.called and s.get_review(a)['Status'] == 'pending'


def test_a_new_inbound_message_makes_a_slot_draft_stale(s):
    tid, mid, reply = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner'); a = draft(s, tid, 0)
    s.add_message({'TaskId': tid, 'ExternalId': 'graph:later', 'ConversationId': f'fixture-thread-{tid}', 'Channel': 'email',
                   'SourceName': 'alex@example.com', 'Subject': 'Repair the export', 'FromEmail': 'erin@example.com',
                   'BodyText': 'Actually, tab 1 changed.', 'SentAt': '2026-10-01 10:00:00', 'Status': 'routed', 'Direction': 'in'})
    assert verdicts.context_moved(s, s.get_review(a))[0] is True


def test_a_finished_run_with_slots_open_waits_instead_of_closing(s):
    tid = typed(s, FOUR[:2]); draft(s, tid, 0)
    prev, coder.REFRESH = coder.REFRESH, None
    try: coder.finish(s, tid, {'summary': 'checked', 'outcome': 'did_work'})
    finally: coder.REFRESH = prev
    assert s.get_task(tid)['Status'] == 'waiting'
    assert [r['Status'] for r in s._rows('SELECT Status FROM review WHERE TaskId=?', (tid,))] == ['pending']
