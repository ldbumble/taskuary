"""A promise task knows whom it owes (the owner, 2026-10-26: "it does not show who to send it back to?? meaning if the promise was to x
it should save who to send to and draft response to them"). The sent mail the promise was made in sits on its thread's own task, so the
promise task had no message, and the agent's --reply was filed as "nobody is waiting on a reply". The mail is the reply's anchor now:
the draft goes to whom it went (its To, its Cc), on that thread, waiting on the owner's Send like any other reply."""
import json

from fastapi.testclient import TestClient

from taskuary import concierge, funnel, responder, server, wrapup
from taskuary.store import MemoryStore

OWN = 'alex@northwind.example'


def _promise(s, channel='email'):
    thread = s.create_task({'Title': 'Firewall allow-list for the portal', 'Kind': 'task', 'Status': 'open'}, 'router')
    cid = f'{channel}:fw-{thread}' if channel != 'email' else f'fw-{thread}'
    add = lambda i, **m: s.add_message({'TaskId': thread, 'ExternalId': f'fw-{thread}-{i}', 'ConversationId': cid, 'Channel': channel,
                                        'SourceName': OWN if channel == 'email' else 'Northwind', 'Subject': 'Firewall allow-list' if channel == 'email' else '', **m})
    ask = add(1, FromName='Erin Blake', FromEmail='erin@vendor.example', SentAt='2026-10-22 15:18:05', BodyText='Which IPs will you call from?',
              RecipientsJson=json.dumps({'to': [OWN], 'cc': ['ray@northwind.example']}))
    sent = add(2, FromName='Alex Doyle', FromEmail=OWN, Status='context', Direction='out', SentAt='2026-10-22 17:30:56',
               BodyText="I'll send you the source IPs tomorrow.",
               RecipientsJson=json.dumps({'to': ['erin@vendor.example'], 'cc': ['ray@northwind.example']}))
    tid = s.task_for_promise(sent, 'send the source IPs', None)
    assert s.get_message(sent)['TaskId'] == thread and s.list_messages(tid) == []
    return tid, sent, ask


def test_the_agents_reply_is_queued_to_whom_the_promise_was_made():
    s = MemoryStore(); prev, wrapup.REFRESH = wrapup.REFRESH, None
    try:
        tid, sent, _ = _promise(s)
        assert wrapup.reply_target(s, tid) == sent
        out = wrapup.agent_reply(s, tid, 'Hi Erin - the source IPs are 192.0.2.10 and 192.0.2.11.', 'coding')
        assert out['ok'] and out.get('saved') != 'result', out
        rv = s.get_review(out['review_id'])
        assert (rv['TaskId'], rv['MessageId'], rv['Status']) == (tid, sent, 'pending')
        env = s.review_envelope(rv['ReviewId'])
        assert (env['to'], env['cc']) == (['erin@vendor.example'], ['ray@northwind.example'])     # the original's To and Cc, never the owner
    finally: wrapup.REFRESH = prev


def test_the_writer_answers_the_promise_and_pins_its_envelope():
    s = MemoryStore()
    tid, sent, _ = _promise(s)
    rid = s.add_review({'TaskId': tid, 'MessageId': sent, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'test'})
    seen = {}
    responder.draft_for_review(s, tid, rid, llm=lambda system, user, **k: (seen.update(user=user), 'Hi Erin - here are the IPs.')[1])
    assert 'YOUR OWN, to Erin Blake' in seen['user'] and 'send the source IPs' in seen['user']
    assert s.review_envelope(rid)['to'] == ['erin@vendor.example']


def test_the_task_page_answers_them_and_the_reply_lands_on_the_promise_task():
    s = server.store
    tid, sent, ask = _promise(s)
    c = TestClient(server.app)
    d = c.get(f'/api/tasks/{tid}').json()
    assert d['owed']['MessageId'] == sent and d['owed']['OwedTo'] == 'Erin Blake'
    out = c.post(f'/api/messages/{sent}/reply', json={'draft': False}).json()
    assert out['taskId'] == tid                                          # not the thread's task, whose newest ask is Erin's
    rv = s.get_review(out['reviewId'])
    assert rv['MessageId'] == sent and s.review_envelope(rv['ReviewId'])['to'] == ['erin@vendor.example']
    r = next(r for r in c.get(f'/api/tasks/{tid}').json()['reviews'] if r['ReviewId'] == rv['ReviewId'])
    assert (r['FromName'], r['FromEmail']) == ('Erin Blake', '')         # "sends this to" them, never its author


def test_a_task_of_its_own_owes_nothing_extra():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Typed by hand', 'Kind': 'task'}, 'owner')
    assert wrapup.reply_target(s, tid) is None and funnel.reply_to(s, tid) is None


def test_reply_is_on_the_row_and_the_advisor_sees_it():
    s = MemoryStore()
    tid, sent, _ = _promise(s)
    assert funnel.reply_to(s, tid) == sent
    it = funnel.item_for_key(s, f'task:{tid}')
    assert 'reply' in {b['verb'] for b in concierge.row_buttons(s, it)}


def test_a_promise_in_a_chat_answers_in_that_chat():
    s = MemoryStore(); prev, wrapup.REFRESH = wrapup.REFRESH, None
    try:
        tid, sent, _ = _promise(s, 'whatsapp')
        assert s.promisee(s.get_message(sent)) == 'Erin Blake'
        out = wrapup.agent_reply(s, tid, 'Here are the IPs.', 'coding')
        rv = s.get_review(out['review_id'])
        assert rv['MessageId'] == sent and s.get_message(sent)['ConversationId'].startswith('whatsapp:')   # outbound answers the room
    finally: wrapup.REFRESH = prev
