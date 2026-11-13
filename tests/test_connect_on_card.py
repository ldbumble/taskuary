"""A SEND CARD WHOSE CHANNEL IS NOT CONNECTED SAYS SO (the owner, 2026-11-08): "LinkedIn isn't connected" with Connect LinkedIn, which opens
that connection's card, in place of a Post that fails - and an email with no mailbox at all, which had Send lit. One answer for every card
(outbound.connect_fix), on the reviews the page reads and on a post's card. Invented world."""
import json
from unittest import mock

from taskuary import outbound, server
from taskuary.store import MemoryStore


def test_one_answer_says_what_is_not_connected_and_where_to_connect_it():
    s = MemoryStore()
    assert outbound.connect_fix(s, 'linkedin') == {'says': "LinkedIn isn't connected", 'label': 'Connect LinkedIn', 'href': '#connector=linkedin'}
    s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 0}, 'owner')
    assert outbound.connect_fix(s, 'email') == {'says': 'No mailbox is connected', 'label': 'Connect email', 'href': '#connector=outlook'}
    assert outbound.connect_fix(s, 'own') is None and outbound.connect_fix(s, '') is None      # nothing to connect for those
    s.save_connector({'Type': 'linkedin', 'Name': 'LinkedIn', 'Active': 1}, 'owner'); s.save_connector({'Type': 'gmail', 'Name': 'Mail', 'Active': 1}, 'owner')
    assert outbound.connect_fix(s, 'linkedin') is None and outbound.connect_fix(s, 'email') is None


def test_an_agent_email_with_no_mailbox_carries_connect_on_the_review():
    s = MemoryStore(); tid = s.create_task({'Title': 'Q4 review room', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi Paula',
                  'Deliver': json.dumps({'channel': 'email', 'to': ['paula@northwind.example'], 'cc': []})})
    with mock.patch.object(server, 'store', s):
        got = server._review_connect({}, s._rows('SELECT * FROM review WHERE TaskId=?', (tid,))[0])
    assert got['says'] == 'No mailbox is connected'


def test_a_mail_card_that_cannot_send_says_why_on_the_reply_and_its_fix():
    """The mailbox is connected and reads, but its card cannot send (a Microsoft sign-in that never granted Mail.Send): the reply card
    showed Copy alone, its reason only in Copy's hover. Now the review carries the reason and the card's fix, as a missing mailbox does."""
    s = MemoryStore(); me = 'alex@northwind.example'
    s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 1,
                      'ConfigJson': json.dumps({'auth': 'user', 'account': me, 'granted_scope': 'offline_access User.Read Mail.ReadWrite'})}, 'owner')
    tid = s.create_task({'Title': 'Badge access', 'Kind': 'general', 'Status': 'open'}, 'router')
    mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'SourceName': me, 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                         'Subject': 'Badge access', 'BodyText': 'Can you add me to the badge list?', 'Status': 'routed'})
    s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'outbound', 'Status': 'pending', 'DraftText': 'Done - you are on it.'})
    assert not outbound.can_reply(s, 'email')
    with mock.patch.object(server, 'store', s):
        got = server._review_connect({}, s._rows('SELECT * FROM review WHERE TaskId=?', (tid,))[0])
    assert got and 'Mail.Send' in got['says'] and (got['label'], got['href']) == ('Sign in again', '#connector=outlook'), got
