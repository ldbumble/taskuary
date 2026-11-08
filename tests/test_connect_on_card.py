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
    assert outbound.connect_fix(s, 'email')['label'] == outbound.MAIL[0]
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
