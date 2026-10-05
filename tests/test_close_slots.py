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


# ── the agent fills slots ────────────────────────────────────────────────────────────────
from taskuary import selfclose


def test_the_agent_fills_a_slot_by_id(s):
    tid = typed(s, FOUR[:2]); sid = slots.open_(s, tid)[1]['id']
    out = slots.draft(s, tid, 'Tab 2 is short by one feed.', slot=sid, agent='assistant')
    rv = s.get_review(out['review_id'])
    assert (rv['Kind'], rv['Status'], rv['DraftBy'], slots.of_review(rv)) == (slots.KIND, 'pending', 'agent:assistant', sid)
    assert json.loads(rv['Deliver'])['to'] == ['ray@northwind.example'] and slots.all_(s, tid)[1]['rid'] == rv['ReviewId']


def test_by_recipient_and_again_rewrites_the_same_draft(s):
    tid = typed(s, FOUR[:1])
    a = slots.draft(s, tid, 'first', to='PAULA@northwind.example'); b = slots.draft(s, tid, 'second', to='paula@northwind.example')
    assert a['review_id'] == b['review_id'] and s.get_review(a['review_id'])['DraftText'] == 'second'


def test_an_unmatched_recipient_adds_a_slot_and_says_so(s):
    tid = typed(s, FOUR[:1])
    out = slots.draft(s, tid, 'Tab 5 too.', to='omar@northwind.example', subject='Tab 5')
    assert out['added'] and len(slots.all_(s, tid)) == 2
    assert any('added' in c['Body'] for c in s.list_comments(tid))


def test_empty_text_or_nobody_is_refused(s):
    tid = typed(s, FOUR[:1])
    assert not slots.draft(s, tid, '  ', slot=slots.open_(s, tid)[0]['id'])['ok']
    assert not slots.draft(s, tid, 'hi')['ok']


def test_a_drafted_slot_on_a_mail_task_still_sends(s):
    tid, mid, _ = mail_task(s); slots.add(s, tid, FOUR[:1], 'owner')
    out = slots.draft(s, tid, 'Tab 1 is fine.', to='paula@northwind.example')
    assert verdicts.context_moved(s, s.get_review(out['review_id']))[0] is False
    assert approve(s, out['review_id'])['ok']


def test_the_chat_block_is_read_and_taken_out():
    text, found = selfclose.draft_markers('Done.\n[[TASKUARY-DRAFT to=paula@northwind.example subject="Tab 1"]]Tab 1 is fine.[[/TASKUARY-DRAFT]]')
    assert text == 'Done.' and found == [({'to': 'paula@northwind.example', 'subject': 'Tab 1'}, 'Tab 1 is fine.')]


def test_the_endpoint_files_the_draft_on_the_sessions_own_task(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    tid = typed(s, FOUR[:1])
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only', return_value=None):
        r = TestClient(server.app).post('/api/agent/draft', json={'task_id': tid, 'text': 'hi', 'to': 'paula@northwind.example'})
    assert r.json()['ok'] and slots.all_(s, tid)[0]['rid']


# ── triage and the assistant say what closes a task ──────────────────────────────────────
from taskuary import concierge, triage


def test_triage_reads_outputs_only_on_a_task():
    j = {'intent': 'task', 'why': 'w', 'title': 't', 'summary': 's', 'kind': 'task', 'checklist': ['a'], 'urgent': False,
         'outputs': [{'to': 'erin@northwind.example', 'about': 'the numbers'}, {'to': '', 'about': 'x'}]}
    assert triage.parse_outputs(j) == [{'to': 'erin@northwind.example', 'about': 'the numbers'}]
    assert triage.parse_outputs({**j, 'intent': 'fyi'}) == [] and triage.parse_outputs({**j, 'outputs': None}) == []


def test_the_schema_offers_outputs():
    p = triage.verdict_schema()['schema']['properties']
    assert p['outputs']['type'] == ['array', 'null'] and p['outputs']['items']['additionalProperties'] is False
    assert 'outputs' in triage.verdict_schema()['schema']['required']


def test_a_hand_made_ask_returns_its_outputs():
    llm = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': ['check'], 'outputs': [{'to': 'paula@northwind.example', 'about': 'tab 1'}]})
    assert triage.extract_ask({'body': 'Check tab 1 and email Paula'}, llm)['outputs'] == [{'to': 'paula@northwind.example', 'about': 'tab 1'}]
    assert triage.extract_ask({'body': 'x'}, None)['outputs'] == []


class Inline:                     # threading.Thread, run where it is started
    def __init__(self, target=None, args=(), **k): self.go = lambda: target(*args)
    def start(self): self.go()


def handoff(s, brain):
    session = mock.Mock()
    with mock.patch('taskuary.concierge.brain', **brain), mock.patch('taskuary.general.start_session', return_value=session), \
         mock.patch('taskuary.concierge.threading.Thread', Inline):
        made = concierge.handoff_task(s, 'Check the four tabs and draft an email to each owner', kind='general')
    return made, session


def test_a_chat_handoff_reads_its_slots_before_the_agents_first_turn(s):
    llm = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': [], 'outputs': FOUR})
    made, session = handoff(s, {'return_value': llm})
    assert len(slots.open_(s, made['taskId'])) == 4 and session.send_prompt.called


def test_the_slots_are_there_when_the_agent_is_prompted(s):
    llm = lambda sys, user, **k: json.dumps({'summary': 's', 'checklist': [], 'outputs': FOUR[:1]})
    session, seen = mock.Mock(), []
    session.send_prompt.side_effect = lambda brief: seen.append(len(slots.open_(s, made_box[0])))
    made_box = []
    real_start = lambda st, tid, **k: made_box.append(tid) or session
    with mock.patch('taskuary.concierge.brain', return_value=llm), mock.patch('taskuary.general.start_session', side_effect=real_start), \
         mock.patch('taskuary.concierge.threading.Thread', Inline):
        concierge.handoff_task(s, 'Email Paula where tab 1 stands', kind='general')
    assert seen == [1]


def test_a_handoff_whose_brain_fails_is_made_anyway(s):
    made, session = handoff(s, {'side_effect': RuntimeError('no brain')})
    assert s.get_task(made['taskId']) and slots.all_(s, made['taskId']) == [] and session.send_prompt.called


def test_a_triaged_message_that_asks_for_emails_gets_slots():
    from datetime import datetime
    from fastapi.testclient import TestClient
    from taskuary import server
    verdict = json.dumps({'intent': 'task', 'kind': 'task', 'why': 'asks for two updates', 'title': 'Send the tab updates',
                          'summary': 'Marcus Reed wants Erin and Gail told where the tabs stand.', 'checklist': ['Tell Erin and Gail'],
                          'outputs': [{'to': 'erin@northwind.example', 'about': 'the tabs'}, {'to': 'Gail Moreno', 'about': 'the tabs'}]})
    st, prev = MemoryStore(), server.store
    server.store = st; st.set_setting('coder_auto_enabled', '0', 'test')
    try:
        body = {'external_id': 'slots-1', 'channel': 'teams', 'conversation_id': 'teams:19:slots@thread.v2', 'from_name': 'Marcus Reed',
                'subject': 'Tab updates', 'body': 'Could you let Erin and Gail know where each tab stands?',
                'sent_at': datetime.now().isoformat(sep=' ', timespec='seconds')}
        with mock.patch('taskuary.server._llm', return_value=lambda sys_, usr_, **kw: verdict):
            TestClient(server.app).post('/api/ingest/push', json=body)
        tid = next(t['TaskId'] for t in st.list_tasks(active_only=True))
        assert [i['out']['to'] for i in slots.all_(st, tid)] == ['erin@northwind.example', 'Gail Moreno']
    finally: server.store = prev


# ── the work rail ────────────────────────────────────────────────────────────────────────
def test_the_rail_shows_one_row_per_task_with_its_count(s):
    from taskuary import funnel
    tid = typed(s, FOUR[:2]); a, b = draft(s, tid, 0), draft(s, tid, 1)
    rows = [r for r in funnel.from_proposals(s, set()) if r.get('tid') == tid]
    assert len(rows) == 1 and rows[0]['key'] == f'review:{a}' and rows[0]['lane'] == 'approve' and '2 emails' in rows[0]['why']
    approve(s, a)
    rows = [r for r in funnel.from_proposals(s, set()) if r.get('tid') == tid]
    assert len(rows) == 1 and rows[0]['key'] == f'review:{b}' and '1 email ' in rows[0]['why']


def test_the_processing_rail_calls_them_emails_not_a_reply():
    import sys, os; sys.path.insert(0, os.path.dirname(__file__))
    from taskuary import funnel, processing_unread
    from test_funnel import ago, store
    st = store(); tid = typed(st, FOUR[:2]); draft(st, tid, 0); draft(st, tid, 1)
    def rail():
        st.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            return processing_unread.build(st, live_state=[])['items']
    rail(); st.activate_processing_reads(fixed_now=ago(0), live_state=[])
    rows = [r for r in rail() if r.get('tid') == tid]
    assert len(rows) == 1 and rows[0]['lane'] == 'approve' and '2 emails' in rows[0]['why'] and 'reply' not in rows[0]['why']
