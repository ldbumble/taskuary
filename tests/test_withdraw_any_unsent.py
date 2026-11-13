"""THE AGENT TAKES BACK WHAT IT SET UP (the owner, 2026-11-07). Asked to draft Paula an email, then told "send it to Gail instead", the agent
drafted Gail's and said it could not remove Paula's - two Sends, one of them wrong, on every later turn. Now a new email can name the one it
`replaces` in the same call, and withdraw_draft reaches any unsent thing the agent made on its task: the reply, an email, a post. What
already went is untouched. Invented people.
"""
import json
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agenttools, server, verdicts
from taskuary.store import MemoryStore
from test_agent_toolbox import hdr
from test_own_ask_no_reply import own_task

c = TestClient(server.app)


def call(tid, name, **a):
    r = c.post(f'/api/mcp?task={tid}', headers=hdr(tid), json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                               'params': {'name': name, 'arguments': a}}).json()['result']
    return r['content'][0]['text'], r['isError']


def waiting(s, tid): return [(r['Kind'], r['ReviewId']) for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (tid,))]


def test_a_new_email_replaces_the_old_one_in_the_same_call():
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s):
        assert 'withdraw_draft' in {t['name'] for t in c.post(f'/api/mcp?task={tid}', headers=hdr(tid), json={
            'jsonrpc': '2.0', 'id': 1, 'method': 'tools/list'}).json()['result']['tools']}       # offered on the owner's own ask
        paula = json.loads(call(tid, 'propose_email', to='paula@northwind.example', subject='The tools table', text='Hi Paula - the table.')[0])
        gail = json.loads(call(tid, 'propose_email', to='gail@northwind.example', subject='The tools table', text='Hi Gail - the table.',
                               replaces=str(paula['review_id']))[0])
    assert gail['ok'] and gail['replaced'] == paula['review_id']
    assert waiting(s, tid) == [('slot', gail['review_id'])]                                # one Send left, and it is Gail's
    old = s.get_review(paula['review_id'])
    assert old['Status'] == 'closed_unsent' and old['DecideNote'].startswith('withdrawn - ')
    paula_slot = next(i for i in s.task_checklist(tid) if i.get('rid') == paula['review_id'])
    assert paula_slot['done']                                                              # nothing still owed to Paula


def test_withdraw_reaches_an_email_or_a_post_by_its_id_or_who_it_was_to():
    s = MemoryStore(); tid = own_task(s, 'general')
    post = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'the agent proposes to post on LinkedIn',
                         'DraftText': json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'Portal v2 is live.'})})
    close = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'finishing it: merge pull request #4',
                          'DraftText': json.dumps({'action': 'merge_pr', 'closeout': True, 'number': 4})})
    with mock.patch.object(server, 'store', s):
        mail = json.loads(call(tid, 'propose_email', to='gail@northwind.example', subject='Lunch', text='Hi Gail')[0])
        said, bad = call(tid, 'withdraw_draft', why='the owner changed the plan')
        assert bad is False and '"ok": false' in said and 'name which one' in said and str(post) in said
        assert str(close) not in said                                                       # a close-out is Taskuary's, never the agent's
        assert json.loads(call(tid, 'withdraw_draft', why='not posting after all', which=str(post))[0])['ok']
        assert json.loads(call(tid, 'withdraw_draft', why='Gail is away', which='gail@northwind.example')[0])['review_id'] == mail['review_id']
    assert waiting(s, tid) == [('action', close)]


def test_what_already_went_is_never_withdrawn():
    s = MemoryStore(); tid = own_task(s, 'general')
    rid = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'Deliver': json.dumps({'to': ['ray@northwind.example']})})
    s.decide_review(rid, 'approved', 'Hi Ray', 'owner'); s._exec("UPDATE review SET DeliveryState='sent' WHERE ReviewId=?", (rid,))
    out = verdicts.withdraw(s, tid, 'changed my mind', 'agent', which=str(rid))
    assert out['ok'] is False and s.get_review(rid)['Status'] == 'approved'


def test_an_agent_with_no_shell_takes_back_an_email_by_its_marker():
    # agent-flow audit 2026-11-07: [[TASKUARY-WITHDRAW: ...]] reached only the reply draft - an API card's wrong email stood with its Send
    from taskuary import general, selfclose, slots
    s = MemoryStore(); tid = own_task(s, 'general')
    paula = slots.draft(s, tid, 'Hi Paula - the table.', to='paula@northwind.example', subject='The tools table')['review_id']
    gail = slots.draft(s, tid, 'Hi Gail - the table.', to='gail@northwind.example', subject='The tools table')['review_id']
    brief = general.latest_block(s, tid)
    assert f'rv{paula}: the email to paula@northwind.example' in brief and 'which=' in brief
    text, found = selfclose.withdraw_markers(f'Done.\n[[TASKUARY-WITHDRAW which=rv{paula}: sent to Gail instead]]\n'
                                             '[[TASKUARY-WITHDRAW which="gail@northwind.example": Gail is away]]\n[[TASKUARY-WITHDRAW: no reply]]')
    assert text == 'Done.' and found == [(f'rv{paula}', 'sent to Gail instead'), ('gail@northwind.example', 'Gail is away'), ('', 'no reply')]
    answer = f'Taken back.\n[[TASKUARY-WITHDRAW which=rv{paula}: the owner wants it to go to Gail only]]'
    with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')): sess = general.GeneralSession(s, tid)
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: answer), mock.patch('taskuary.hooks.judge_ended'):
        reply = sess.send_prompt('only Gail, please', as_owner=False)          # Taskuary's own word to it: nothing of his is written past
    assert 'TASKUARY-WITHDRAW' not in reply and s.get_review(paula)['Status'] == 'closed_unsent'
    assert waiting(s, tid) == [('slot', gail)]


def test_a_playbook_the_agent_proposed_is_its_own_to_take_back_and_the_ledgers_is_not():
    s = MemoryStore(); tid = own_task(s, 'general')
    mine = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'the agent proposes a playbook',
                         'DraftText': json.dumps({'action': 'write_playbook', 'slug': 'w-9', 'text': '# Send our W-9'})})
    s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'what the ledger counted',
                  'DraftText': json.dumps({'action': 'amend_playbook', 'slug': 'w-9', 'block': 'Counted: 3 of 4 sent as drafted', 'text': '# Send our W-9'})})
    assert [r['rid'] for r in verdicts.unsent(s, tid)] == [mine]
    assert verdicts.withdraw(s, tid, 'the owner said the steps are wrong', 'assistant', which=str(mine))['ok']
    assert s.get_review(mine)['Status'] == 'closed_unsent'


def test_a_reply_nobody_has_written_is_nothing_set_up():
    """The audit, 2026-11-10: a reply owed at arrival - its review open, no word in it yet - was told to the agent's first turn as "ALSO SET UP AND
    NOT SENT ... rv1: the reply to erin@...", a thing it had set up and might take back. Nothing was set up; once written it is listed."""
    from taskuary import general
    s = MemoryStore(); tid = own_task(s, 'general')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'e1', 'ConversationId': 'c1', 'Channel': 'email', 'FromName': 'Erin Blake',
                         'FromEmail': 'erin@northwind.example', 'Subject': 'Tuesday', 'BodyText': 'Free Tuesday?', 'Status': 'routed'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': ''})
    assert verdicts.unsent(s, tid) == [] and 'ALSO SET UP' not in general.turn_facts(s, tid)
    s.update_review_draft(rid, 'Yes, Tuesday works.', None)
    assert [x['rid'] for x in verdicts.unsent(s, tid)] == [rid]


def test_an_email_waiting_is_told_to_the_agent_with_its_words():
    """The audit's real turn, 2026-11-10: told only "rv1: the email to paula@...", the agent asked to make it shorter could not see what it
    said, and asked the owner. Each letter set up and not sent is told with its words."""
    from taskuary import general
    s = MemoryStore(); tid = own_task(s, 'general')
    with mock.patch.object(server, 'store', s):
        call(tid, 'propose_email', to='paula@northwind.example', subject='October report', text='Hi Paula, here is the October report.')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'make it shorter')
    assert 'the email to paula@northwind.example: "Hi Paula, here is the October report."' in general.turn_facts(s, tid)
