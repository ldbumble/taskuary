"""Every email Taskuary prepares ends with the owner's signature exactly once (the owner, 2026-10-28: "on replies there was no
signature with it. It should use the default signature always (you can put that as a setting)"). A reply they typed into the
empty box, the AI's draft, an agent's, a forward - signed as it leaves, never twice; chat never; the switch off, nothing."""
import json
from unittest import mock

import pytest

from taskuary import outbound, responder, signatures, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

SIG = 'Alex Doyle\nOperations | Northwind'
NW, SIDE = 'alex@northwind.example', 'alex@board.example'


@pytest.fixture
def s():
    s = MemoryStore()
    s.set_setting('email_signature', SIG, 'owner')
    return s


def thread(s, channel='email', box=NW, draft=None):
    f = Factory(s)
    tid = f.task(title='August export', kind='reply')
    mid = f.message(tid, channel=channel, from_email='erin@northwind.example', from_name='Erin Blake', source_name=box,
                    conversation_id=f'{channel}:c1', subject='August export')
    return tid, mid, f.review(tid, mid, draft=draft)


def send(s, rid, text=None):
    """Approve with `text` in the box; what reached the provider."""
    with mock.patch.object(outbound, 'reply_to_message', return_value={'channel': 'email', 'to': ['erin@northwind.example']}) as out, \
         mock.patch.object(outbound, 'send_block', return_value=''), mock.patch.object(outbound, 'can_reply', return_value=True), \
         mock.patch('taskuary.learn.learn_from'):
        got = verdicts.decide(s, s.get_review(rid), 'approve', text)
    return got, (out.call_args.args[2] if out.called else None)


def test_the_owners_own_typed_reply_goes_with_the_signature(s):
    _, _, rid = thread(s, draft='')
    got, body = send(s, rid, 'Hi Erin,\n\nAttached.')
    assert got['ok'], got
    assert body == f'Hi Erin,\n\nAttached.\n\n{SIG}'


def test_an_ai_draft_filed_without_it_is_signed_once_as_it_leaves(s):
    _, _, rid = thread(s, draft='Hi Erin,\n\nThe export ran.')
    got, body = send(s, rid)
    assert body.endswith(SIG) and body.count('Northwind') == 1
    assert got['status'] == 'approved'            # the block going on is not an edit the drafter learns from


def test_an_already_signed_draft_is_not_signed_twice(s):
    _, _, rid = thread(s, draft=f'Hi Erin,\n\nThe export ran.\n\n{SIG}')
    _, body = send(s, rid, f'Hi Erin,\n\nThe export ran - all rows.\n\n{SIG}')
    assert body.count('Operations | Northwind') == 1


def test_the_box_holding_only_the_signature_sends_nothing(s):
    _, _, rid = thread(s, draft='')
    got, body = send(s, rid, f'\n\n{SIG}')
    assert body is None and not got['ok'] and got.get('empty')


def test_a_chat_reply_gets_no_signature(s):
    _, _, rid = thread(s, channel='teams', box='Erin Blake', draft='on it')
    assert signatures.for_review(s, s.get_review(rid)) == ''
    _, body = send(s, rid, 'on it - done by noon')
    assert body == 'on it - done by noon'


def test_switch_off_no_signature_anywhere(s):
    s.set_setting('sign_replies', '0', 'owner')
    _, _, rid = thread(s, draft='')
    assert responder.signature_for(s) == '' and signatures.for_review(s, s.get_review(rid)) == ''
    _, body = send(s, rid, 'Hi Erin,\n\nAttached.')
    assert body == 'Hi Erin,\n\nAttached.'


def test_each_mailbox_signs_as_itself(s):
    s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 1, 'ConfigJson': json.dumps({'address': NW})}, 't')
    b = s.save_connector({'Type': 'imap', 'Name': 'Board', 'Active': 1, 'ConfigJson': json.dumps({'address': SIDE})}, 't')
    signatures.save_mailbox(s, SIDE, 'Alex Doyle\nBoard of Northwind')
    assert json.loads(s.get_connector(b)['ConfigJson'])['signatures'] == {SIDE: 'Alex Doyle\nBoard of Northwind'}
    _, _, mine = thread(s, box=NW, draft='Hi Erin,\n\nYes.')
    _, _, board = thread(s, box=SIDE, draft='Hi Erin,\n\nYes.')
    assert signatures.for_review(s, s.get_review(mine)) == SIG
    assert signatures.for_review(s, s.get_review(board)) == 'Alex Doyle\nBoard of Northwind'
    view = signatures.overview(s)
    assert [m['address'] for m in view['mailboxes']] == [NW, SIDE] and view['on'] and view['default'] == SIG


def test_the_writer_never_signs_and_nothing_saved_signs_with_the_owners_name():
    s = MemoryStore()
    assert 'Do NOT write a sign-off' in responder.email_rule(s)
    assert responder.signature_for(s) == ''
    s.set_setting('owner_name', 'Alex Doyle', 'owner')
    assert responder.signature_for(s) == 'Alex Doyle'


def test_an_invite_answer_keeps_its_own_body(s):
    tid, mid, _ = thread(s)
    rid = Factory(s).review(tid, mid, kind='outbound', draft='See you then', Deliver=json.dumps({'kind': 'calendar'}))
    assert signatures.for_review(s, s.get_review(rid)) == ''


def test_settings_offers_the_signature_read_off_the_sent_mail_once():
    s = MemoryStore()
    assert signatures.overview(s)['offer']
    with mock.patch.object(responder, 'learn_signature', return_value=SIG) as learn:
        assert signatures.suggest(s, NW) == SIG
    assert learn.call_args.kwargs['mailbox'] == NW
    assert not signatures.overview(s)['offer'] and s.get_setting('email_signature') == ''    # offered, never saved behind their back


def test_learning_reads_only_the_named_mailboxes_sent_mail():
    mail = [{'mailbox': NW, 'body': {'content': f'Done.\n\n{SIG}'}}, {'mailbox': NW, 'body': {'content': f'Yes.\n\n{SIG}'}},
            {'mailbox': SIDE, 'body': {'content': 'Ok.\n\nAlex - the board'}}, {'mailbox': SIDE, 'body': {'content': 'Fine.\n\nAlex - the board'}}]
    with mock.patch('taskuary.histgen.sent_mail', return_value=(mail, [], 2, 'IMAP')):
        assert responder.learn_signature(MemoryStore(), mailbox=SIDE) == 'Alex - the board'
        assert responder.learn_signature(MemoryStore(), mailbox=NW) == SIG
