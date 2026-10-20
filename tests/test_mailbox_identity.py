"""Two mailboxes are two hats. Mail that came in on the second one was answered under the first one's signature, and a new
message on its task went out from whichever Outlook card was first. Each mailbox card may carry its own signature (blank: the
one in Settings), and a new email on a task leaves from the mailbox the task's mail came in on. Replies already leave through
the account they arrived on - that stays."""
import json
from unittest import mock

import pytest

from taskuary import outbound, outbox, responder, slots, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

NW, CT = 'alex@northwind.example', 'alex@contoso.example'
SENT = {'channel': 'email', 'to': ['erin@northwind.example']}


@pytest.fixture
def s():
    s = MemoryStore()
    s.set_setting('email_signature', 'Alex Doyle\nNorthwind', 'owner')
    a = s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 1, 'ConfigJson': json.dumps({'address': NW})}, 't')
    b = s.save_connector({'Type': 'imap', 'Name': 'Contoso', 'Active': 1,
                          'ConfigJson': json.dumps({'address': CT, 'signature': 'Alex Doyle\nContoso board'})}, 't')
    s.boxes = (a, b)
    return s


def asked_on(s, box, title='Budget numbers'):
    f = Factory(s)
    tid = f.task(title=title)
    mid = f.message(tid, from_email='paula@contoso.example', from_name='Paula Vance', source_name=box, subject=title)
    return tid, mid


def test_a_card_signature_wins_and_a_blank_one_keeps_the_global(s):
    assert responder.signature_for(s, CT) == 'Alex Doyle\nContoso board'
    assert responder.signature_for(s, NW) == responder.signature_for(s) == 'Alex Doyle\nNorthwind'
    assert responder.signature_for(s, 'who@else.example') == 'Alex Doyle\nNorthwind'      # no card sends as it
    assert responder.email_rule(s, CT) == responder.EMAIL_SIGNED


def test_a_card_signature_alone_still_tells_the_writer_not_to_sign(s):
    s.set_setting('email_signature', '', 'owner')
    assert responder.email_rule(s, CT) == responder.EMAIL_SIGNED and responder.email_rule(s, NW) == responder.EMAIL


def test_the_task_mailbox_is_where_its_mail_came_in(s):
    tid, _ = asked_on(s, CT)
    assert outbound.task_mailbox(s, tid) == CT
    mine = Factory(s).task(title='Mine', source='manual')
    assert outbound.task_mailbox(s, mine) is None                                    # nothing came in by mail


def test_a_reply_draft_is_signed_for_the_mailbox_it_answers(s):
    tid, mid = asked_on(s, CT)
    rid = Factory(s).review(tid, mid, kind='draft_reply')
    with mock.patch('taskuary.calendar.context_for', return_value=''), mock.patch('taskuary.knowledge.block', return_value=''):
        text = responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: 'Hi Paula,\n\nThe numbers are attached.')
    assert text.endswith('Alex Doyle\nContoso board') and 'Northwind' not in text


def test_a_new_email_on_the_task_leaves_from_its_mailbox(s):
    tid, _ = asked_on(s, CT)
    llm = lambda system, user, max_tokens=0: 'Budget is final' if max_tokens <= 40 else 'Hi Erin,\n\nThe budget is final.'
    with mock.patch.object(outbound, 'can_reply', return_value=True):
        out = outbox.task_email(s, tid, 'erin@northwind.example', 'tell her', llm=llm)
    with mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learn.learn_from'):
        verdicts.decide(s, s.get_review(out['review_id']), 'approve')
    assert sent.call_args.kwargs['mailbox'] == CT


def test_the_owners_pick_and_a_task_with_no_mail_in_are_as_before(s):
    tid, _ = asked_on(s, CT)
    llm = lambda system, user, max_tokens=0: 'Budget is final' if max_tokens <= 40 else 'Hi Erin,\n\nThe budget is final.'
    mine = Factory(s).task(title='Mine', source='manual')
    for t, pick, want in ((tid, NW, NW), (mine, None, None)):
        with mock.patch.object(outbound, 'can_reply', return_value=True):
            out = outbox.task_email(s, t, 'erin@northwind.example', 'tell her', llm=llm, mailbox=pick)
        with mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch.object(outbound, 'send_block', return_value=''), \
             mock.patch('taskuary.learn.learn_from'):
            verdicts.decide(s, s.get_review(out['review_id']), 'approve')
        assert sent.call_args.kwargs['mailbox'] == want


def test_the_from_picker_starts_on_the_tasks_mailbox(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    s.save_source({'Channel': 'email', 'Address': CT, 'Active': 1, 'ConnectorId': s.boxes[1]}, 't')
    tid, _ = asked_on(s, CT)
    old, server.store = server.store, s
    try:
        c = TestClient(server.app)
        got, plain = c.get('/api/mailboxes', params={'task': tid}).json(), c.get('/api/mailboxes').json()
    finally: server.store = old
    assert got['default'] == CT and plain['default'] == plain['data'][0]['address']


def test_saving_an_edit_signs_it_for_the_sending_mailbox(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    tid, mid = asked_on(s, CT)
    rid = Factory(s).review(tid, mid, kind='draft_reply', draft='x')
    old, server.store = server.store, s
    try: r = TestClient(server.app).patch(f'/api/reviews/{rid}', json={'body': 'Hi Paula,\n\nDone.'})
    finally: server.store = old
    assert r.json()['draft'].endswith('Contoso board')
