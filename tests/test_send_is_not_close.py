"""SENDING AND CLOSING ARE TWO STEPS (the owner, 2026-10-18): Send only sends, Approve runs only the agent's act, the last of a
task's emails ticks itself - and none of them closes the task. Mark done is the one close, and it is never offered on an item
with no task behind it."""
import json
from unittest import mock

import pytest

from taskuary import advisor, buttons, concierge, funnel, outbound, proposals, slots, verdicts
from taskuary.store import MemoryStore
from tests.test_close_slots import FOUR, SENT, approve, draft, typed
from tests.test_review_delivery_safety import make_review


@pytest.fixture
def s():
    v = MemoryStore(); funnel.invalidate(); funnel.forget_states(); yield v; v.close()


def send(s, rid):
    with mock.patch('taskuary.outbound.reply_to_message', return_value=SENT), mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learn.learn_from'):
        return verdicts.decide(s, s.get_review(rid), 'approve')


def comments(s, tid): return ' | '.join(c['Body'] for c in s.list_comments(tid))


def test_the_button_is_send_and_says_the_task_stays_open():
    assert buttons.label('approve') == 'Send' and 'stays open until you Mark done' in buttons.hint('approve')
    assert buttons.label('approve', 'action') == 'Approve' and buttons.hint('approve', 'action').startswith('Runs only what the agent proposes')
    assert 'Send & close' not in json.dumps(buttons.VERBS)


def test_a_send_leaves_the_task_open(s):
    tid, mid, rid = make_review(s, task_kind='general')
    out = send(s, rid)
    assert out['ok'] and out['sent'] and s.get_review(rid)['Status'] != 'pending'
    assert s.get_task(tid)['Status'] == 'open'
    assert 'Sent by email to' in comments(s, tid) and 'Closed' not in comments(s, tid)


def test_a_send_with_nothing_else_waiting_still_leaves_it_open(s):
    tid, mid, rid = make_review(s, task_kind='reply')         # the old close took exactly this one: no agent, no newer mail, no close-out
    with mock.patch('taskuary.funnel.working_tids', return_value=set()): send(s, rid)
    assert s.get_task(tid)['Status'] not in ('done', 'dropped')


def test_approve_runs_only_the_action(s):
    tid = s.create_task({'Title': 'Land the fix', 'Kind': 'coding', 'Status': 'waiting'}, 'router')
    co = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps({'action': 'merge_pr', 'repo': 'org/app', 'number': 7})})
    with mock.patch('taskuary.proposals.execute', return_value={'merged': 'org/app#7'}) as ran, mock.patch('taskuary.learn.learn_from'):
        out = verdicts.decide(s, s.get_review(co), 'approve')
    assert out['ok'] and ran.call_count == 1 and s.get_review(co)['Status'] == 'approved'
    assert s.get_task(tid)['Status'] not in ('done', 'dropped')
    assert f"{buttons.label('close')} when the task is finished" in comments(s, tid)


def test_the_last_proposal_answered_puts_the_task_back_on_the_owner_open(s):
    tid = s.create_task({'Title': 'Pay the bill', 'Kind': 'general', 'Status': 'waiting'}, 'router')
    s.audit('task', tid, 'awaits_proposals', 'agent')
    rv = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps({'action': 'pay_bill'})})
    with mock.patch('taskuary.proposals.execute', return_value={'ok': True}), mock.patch('taskuary.learn.learn_from'):
        verdicts.decide(s, s.get_review(rv), 'approve')
    assert s.get_task(tid)['Status'] == 'open'


def test_the_last_slot_sent_does_not_close(s):
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    approve(s, a); approve(s, b)
    assert all(i['done'] for i in slots.all_(s, tid)) and s.get_task(tid)['Status'] == 'open'
    assert 'Every email is sent or dropped' in comments(s, tid)


def test_a_pull_request_closed_on_github_does_not_close_the_task(s):
    tid = s.create_task({'Title': 'Land it', 'Kind': 'coding', 'Status': 'waiting'}, 'router')
    proposals.closed_out(s, tid, 'github', 'The pull request is closed.')
    assert s.get_task(tid)['Status'] == 'waiting'


def test_mark_done_closes(s):
    tid, mid, rid = make_review(s, task_kind='general')
    send(s, rid)
    assert concierge.close_task(s, tid, 'owner') and s.get_task(tid)['Status'] == 'done'


@pytest.mark.parametrize('item', [{'kind': 'fyi', 'key': 'msg:1', 'mid': 1}, {'kind': 'report', 'key': 'report:2', 'mid': 2, 'bad': True},
                                  {'kind': 'idea', 'key': 'idea:3', 'idea': 3}, {'kind': 'todo', 'key': 'msg:4', 'mid': 4}])
def test_no_mark_done_on_an_item_with_no_task(s, item):
    assert concierge.cannot(item, 'close', s)
    assert 'close' not in [c['verb'] for c in concierge.chips_for(s, item)]
    assert 'close' in [c['verb'] for c in concierge.chips_for(s, {**item, 'kind': 'todo', 'tid': 9})]


def test_a_sends_receipt_carries_mark_done_and_next(s):
    tid, mid, rid = make_review(s, task_kind='general')
    send(s, rid)
    op = {'kind': 'review.approve', 'status': 'done', 'target': rid}
    assert [(c['verb'], c.get('tid')) for c in concierge.sent_chips(s, op)] == [('close', tid), ('next', None)]
    concierge.close_task(s, tid, 'owner')
    assert [c['verb'] for c in concierge.sent_chips(s, op)] == ['next'], 'a closed task offers no Mark done'
    assert concierge.sent_chips(s, {**op, 'kind': 'task.complete'}) == []


def test_a_send_does_not_settle_the_table():
    assert concierge.PROPOSALS['approve'][2] is False and 'review.approve' not in concierge.SETTLING_KINDS
    assert concierge.PROPOSALS['close'][2] is True


def test_the_advisor_offers_send_before_and_mark_done_after(s):
    tid, mid, rid = make_review(s, task_kind='general')
    before = [v['verb'] for v in advisor.offered(s, {'kind': 'review', 'lane': 'approve', 'rid': rid, 'tid': tid, 'mid': mid, 'draft': True, 'key': f'review:{rid}'})]
    assert before[0] == 'approve'
    send(s, rid)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        item = next(i for i in funnel.pile(s, force=True)['items'] if i.get('tid') == tid)
    after = [v['verb'] for v in advisor.offered(s, item)]
    assert 'close' in after and 'approve' not in after


def test_the_phone_offers_mark_done_and_next_under_a_send_and_its_mark_done_closes(s):
    from taskuary import remote_assistant as ra
    tid, mid, rid = make_review(s, task_kind='general')
    send(s, rid)
    op = {'kind': 'review.approve', 'status': 'done', 'target': rid}
    with mock.patch.object(concierge, 'receipt', return_value='Done - Send.'), mock.patch.object(ra, 'turn_text', side_effect=lambda o, *a, **k: k.get('extra')):
        rows = ra._ran(s, {'key': f'review:{rid}'}, op, {'key': f'review:{rid}'}, 'owner')
    assert rows == [(buttons.label('close'), {'t': 'close', 'tid': tid}), (buttons.label('next'), {'t': 'next'})]
    with mock.patch.object(ra, '_on', side_effect=lambda store, actor, said, **kw: said[0]):
        assert ra._run_act(s, {'t': 'close', 'tid': tid}, None) == f'TQ-{tid:04d} closed.'
    assert s.get_task(tid)['Status'] == 'done'
