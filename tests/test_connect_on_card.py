"""A SEND CARD WHOSE CHANNEL IS NOT CONNECTED SAYS SO (the owner, 2026-11-08): "LinkedIn isn't connected" with Connect LinkedIn, which opens
that connection's card, in place of a Post that fails - and an email with no mailbox at all, which had Send lit. One answer for every card
(outbound.connect_fix), on the reviews the page reads and on a post's card. Invented world."""
import json
from unittest import mock

from taskuary import outbound, server
from taskuary.store import MemoryStore


def test_one_answer_says_what_is_not_connected_and_where_to_connect_it():
    s = MemoryStore()
    assert outbound.connect_fix(s, 'linkedin') == {'says': "LinkedIn isn't connected", 'label': 'Connect LinkedIn', 'href': '#connector=linkedin', 'waits': 'the draft waits here - copy it to post it yourself'}
    s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 0}, 'owner')
    assert outbound.connect_fix(s, 'email') == {'says': 'No mailbox is connected', 'label': 'Connect email', 'href': '#connector=outlook'}
    assert outbound.connect_fix(s, 'own') is None and outbound.connect_fix(s, '') is None      # nothing to connect for those
    li = s.save_connector({'Type': 'linkedin', 'Name': 'LinkedIn', 'Active': 1}, 'owner')
    assert outbound.connect_fix(s, 'linkedin')['label'] == 'Connect LinkedIn'      # switched on, never signed in: not connected (the walks, 2026-11-18)
    s.save_connector({'ConnectorId': li, 'Secret': 'tok'}, 'owner'); s.save_connector({'Type': 'gmail', 'Name': 'Mail', 'Active': 1}, 'owner')
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


def test_a_tracker_comment_whose_tracker_is_not_connected_offers_connect():
    """The card round, 2026-11-18: a comment on a tracker item (jira, linear, monday) with its tracker not connected had Post comment lit, and
    the press could only fail - the reply channels that never take a reply (outbound.NEVER: a ticket is answered on its tracker) were read as
    "nothing to connect" for an act's own connection too. An act's card asks for its connection whatever its kind, on the chat's payload as on
    the reviews the page reads: one answer (review_connect)."""
    s = MemoryStore(); tid = s.create_task({'Title': 'Comment on the ledger ticket', 'Kind': 'general', 'Status': 'open'}, 'owner')
    for tool, name in (('jira_comment', 'Jira'), ('linear_comment', 'Linear'), ('monday_comment', 'monday.com')):
        rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'r',
                            'DraftText': json.dumps({'action': 'run_tool', 'type': tool, 'item': 'NW-12', 'body': 'Fixed.'})})
        got = outbound.review_connect(s, s.get_review(rid))
        assert got and got['says'].endswith("isn't connected") and got['label'].startswith('Connect '), (tool, got)
        with mock.patch.object(server, 'store', s):
            card = next(c for c in server._assistant_payload(tid)['cards'] if c['ReviewId'] == rid)
        assert card['connect'] == got, (tool, card['connect'])
    # ...while a reply on a tracker's own thread still has nothing to connect here
    assert outbound.review_connect(s, {'Kind': 'outbound', 'Channel': 'jira', 'Deliver': '{}'}) is None


def test_a_network_signed_in_once_and_signed_out_since_is_its_connect_never_its_press():
    # the judge's look, 2026-11-20: a LinkedIn card signed in once kept "Post to LinkedIn" lit, and the press failed into "LinkedIn isn't signed in"
    from unittest import mock
    from taskuary import connectorcatalog
    s = MemoryStore(); s.save_connector({'Type': 'linkedin', 'Name': 'LinkedIn', 'Active': 1}, 't')
    for st, says in (('signed_out', 'LinkedIn needs you to sign in again'), ('not_signed_in', "LinkedIn isn't signed in")):
        with mock.patch.object(connectorcatalog, 'state', return_value={'state': st}):
            got = outbound.connect_fix(s, 'linkedin')
        assert got['label'] == 'Connect LinkedIn' and got['says'] == says and 'copy' in got['waits']
    for st in ('connected', 'failing'):
        with mock.patch.object(connectorcatalog, 'state', return_value={'state': st}): assert outbound.connect_fix(s, 'linkedin') is None
