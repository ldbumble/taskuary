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
