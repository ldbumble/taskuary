"""The mailbox's own signature goes under an email when the owner has set none (a user, approved 2026-11-02: "when sending a
message, I want taskuary to use the signature that exists in the gmail (or whatever) account"): the closing lines its sent mail
plainly shares - after the card's and Settings' signatures, before STYLE.md and the name, held on the card a day and never read
per draft. Gmail's own signature setting is not read yet (the owner, 2026-11-02): no Google permission is asked for it."""
import json, time
from unittest import mock

import pytest

from taskuary import googlecal, responder, signatures
from taskuary.store import MemoryStore

ME = 'alex@northwind.example'
SIG = 'Best,\nAlex Doyle\nOperations Lead | Northwind'


def store(kind='imap'):
    s = MemoryStore()
    s.set_setting('owner_name', 'Alex Doyle', 'owner')
    cid = s.save_connector({'Type': kind, 'Name': kind.title(), 'Active': 1, 'ConfigJson': json.dumps({'address': ME})}, 't')
    return s, cid


def hold(s, cid, sig, age=0):
    cfg = json.loads(s.get_connector(cid)['ConfigJson'])
    s.set_connector_config(cid, {**cfg, signatures.ACCOUNT: {ME: {'signature': sig, 'source': 'sent', 'at': time.time() - age}}})


def tail(lines, n, read): return mock.patch('taskuary.responder.signature_tail', return_value=(lines, n, read))


@pytest.fixture(autouse=True)
def later():
    """No background read: each test says what the sent mail holds."""
    with mock.patch.object(signatures, '_later') as later: yield later


def test_no_gmail_settings_permission_is_asked_for():
    assert 'gmail.settings' not in googlecal.SCOPES


@pytest.mark.parametrize('kind', ['imap', 'gmail', 'outlook'])
def test_with_nothing_set_the_mailboxs_own_signs(kind):
    s, cid = store(kind)
    with tail(SIG.splitlines(), 9, 12): signatures.refresh(s, {'connector_id': cid, 'address': ME})
    assert responder.signature_for(s, ME) == SIG
    assert signatures.overview(s)['accounts'] == [{'address': ME, 'signature': SIG}]


def test_the_owners_own_signatures_come_first():
    s, cid = store()
    hold(s, cid, SIG)
    s.set_setting('email_signature', 'Alex\nSettings one', 'owner')
    assert responder.signature_for(s, ME) == 'Alex\nSettings one'
    cfg = json.loads(s.get_connector(cid)['ConfigJson'])
    s.set_connector_config(cid, {**cfg, 'signature': 'Alex\nCard one'})
    assert responder.signature_for(s, ME) == 'Alex\nCard one'


def test_none_read_yet_falls_through_to_the_name_and_reads_behind_the_draft(later):
    s, _ = store()
    with mock.patch.object(signatures, 'confident') as read:
        assert responder.signature_for(s, ME) == 'Alex Doyle'
    read.assert_not_called(); later.assert_called_once()        # never in front of the draft


def test_fresh_is_not_read_again_and_a_day_old_one_is_used_while_it_is(later):
    s, cid = store()
    hold(s, cid, SIG)
    assert responder.signature_for(s, ME) == SIG
    later.assert_not_called()
    hold(s, cid, 'Alex Doyle\nOld one', age=signatures.DAY + 5)
    assert responder.signature_for(s, ME) == 'Alex Doyle\nOld one'
    later.assert_called_once()


def test_a_failed_read_keeps_the_last_good_one_and_reads_again_within_the_hour():
    s, cid = store()
    hold(s, cid, SIG)
    with mock.patch.object(signatures, 'confident', side_effect=OSError('imap down')):
        row = signatures.refresh(s, {'connector_id': cid, 'address': ME})
    assert row['signature'] == SIG
    assert time.time() - row['at'] > signatures.DAY - signatures.RETRY - 5


@pytest.mark.parametrize('lines,n,read,want', [
    (SIG.splitlines(), 9, 12, SIG),                              # most of plenty of mail, with the owner's name: used
    (SIG.splitlines(), 3, 3, ''),                                 # too little mail to be sure: stays Settings' offer
    (SIG.splitlines(), 6, 12, ''),                                # half is not most
    (['Thanks'], 10, 12, ''),                                     # a sign-off word is not a signature
    (['Operations', 'Northwind'], 10, 12, ''),                    # not the owner's name
    (['Alex Doyle', 'Sent from my iPhone'], 10, 12, ''),          # a phone's footer
])
def test_the_sent_mails_ending_is_used_only_when_it_plainly_is_the_signature(lines, n, read, want):
    s, _ = store()
    with tail(lines, n, read): assert signatures.confident(s, ME) == want


def test_learn_signature_still_reads_the_same():
    mails = [{'subject': 'Re: x', 'body': {'content': f'Hi,\n\n{w}\n\n{SIG}'}} for w in ('Done.', 'Sent it.', 'Friday works.')]
    with mock.patch('taskuary.histgen.sent_mail', return_value=(mails, [], 1, 'IMAP')):
        assert responder.learn_signature(MemoryStore()) == SIG
        assert responder.signature_tail(MemoryStore()) == (SIG.splitlines(), 3, 3)
