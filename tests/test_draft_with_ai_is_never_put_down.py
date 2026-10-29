"""A draft the owner pressed for is never put down as "no reply" (2026-10-29: a vendor mailed the back office, the owner on Cc, asking
the owner to approve the final invoice. Draft with AI read "you are only copied - the question is the To line's", wrote NO REPLY, the
review was decided no_reply and the task closed under the press; every press came back to "No draft yet")."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import learn, responder, server
from taskuary.store import MemoryStore

ASK = 'Hi Billing, the campaign video is delivered. Alex, can you approve the final invoice so Billing can pay it?'


@pytest.fixture
def s():
    value = MemoryStore()
    value.set_setting('owner_email', 'alex@northwind.example', 'test')
    yield value
    value.close()


def copied_ask(s):
    tid = s.create_task({'Title': 'Approve the final video invoice', 'Kind': 'reply', 'Status': 'open', 'Source': 'email'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'graph:inv-{tid}', 'ConversationId': f'inv-thread-{tid}', 'Channel': 'email',
                         'SourceName': 'alex@northwind.example', 'Subject': 'Final invoice', 'FromName': 'Ray Colton',
                         'FromEmail': 'ray@vendor.example', 'BodyText': ASK, 'SentAt': '2026-10-29 09:00:00', 'Status': 'routed',
                         'RecipientsJson': json.dumps({'to': ['billing@northwind.example'], 'cc': ['alex@northwind.example']})})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                        'Deliver': json.dumps({'kind': 'reply', 'mode': 'reply_all', 'to': ['ray@vendor.example'], 'cc': ['billing@northwind.example']})})
    return tid, rid


def test_the_writer_saying_no_reply_to_a_pressed_draft_fails_and_leaves_the_reply_open(s):
    tid, rid = copied_ask(s)
    with mock.patch.object(learn, 'learn_from'), pytest.raises(RuntimeError, match='no reply'):
        responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'NO REPLY', pressed=True)
    assert s.get_review(rid)['Status'] == 'pending' and s.get_task(tid)['Status'] == 'open'


def test_the_writer_is_told_the_owner_wants_to_answer_only_when_they_pressed(s):
    seen = []
    def llm(system, user, **k): seen.append(system); return 'Approved - Billing, please pay it.'
    for pressed in (True, False):
        tid, rid = copied_ask(s)
        with mock.patch.object(learn, 'learn_from'): responder.draft_for_review(s, tid, rid, llm=llm, pressed=pressed)
    assert responder.ASKED in seen[0] and responder.ASKED not in seen[1]


def test_draft_with_ai_on_the_card_keeps_the_reply_when_the_writer_says_no_reply(s):
    tid, rid = copied_ask(s)
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_refresh_chat_context'), mock.patch.object(learn, 'learn_from'), \
         mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 'NO REPLY'):
        r = TestClient(server.app).post(f'/api/reviews/{rid}/draft', json={})
    assert r.status_code == 422 and s.get_review(rid)['Status'] == 'pending' and s.get_task(tid)['Status'] == 'open'
    assert s.get_review(rid)['DraftError']


def test_readdressed_to_the_back_office_it_leaves_cc(s):
    tid, rid = copied_ask(s)
    with mock.patch.object(server, 'store', s):
        r = TestClient(server.app).put(f'/api/reviews/{rid}/envelope', json={'to': ['billing@northwind.example']})
    assert r.status_code == 200, r.text
    env = json.loads(s.get_review(rid)['Deliver'])
    assert env['to'] == ['billing@northwind.example'] and 'billing@northwind.example' not in env['cc']
