"""The account's own signature goes under an email when the owner has set none (a user, approved 2026-11-02: "when sending a
message, I want taskuary to use the signature that exists in the gmail (or whatever) account"): Gmail's own over Google's sign-in,
else the closing lines the sent mail plainly shares - after the card's and Settings' signatures, before STYLE.md and the name,
held on the card a day and never asked per draft. A sign-in from before the permission keeps working, and says so."""
import json, time
from unittest import mock

import pytest

from taskuary import googlecal, responder, signatures
from taskuary.store import MemoryStore

ME = 'alex@northwind.example'
HTML = ('<div dir="ltr"><b>Alex Doyle</b><br>Operations Lead | Northwind<br>'
        '<a href="https://northwind.example">northwind.example</a>&nbsp;&middot; +1 555 0100</div>')
PLAIN = 'Alex Doyle\nOperations Lead | Northwind\nnorthwind.example · +1 555 0100'
FULL = f'{googlecal.SCOPE} {googlecal.G_SETTINGS}'


class R:
    def __init__(self, status=200, j=None): self.status_code, self._j, self.text = status, j or {}, json.dumps(j or {})
    def json(self): return self._j


def store(scope=FULL, kind='gmail', **cfg):
    s = MemoryStore()
    s.set_setting('owner_name', 'Alex Doyle', 'owner')
    c = {'address': ME, **({'google_refresh_token': 'rt', 'google_scope': scope} if kind == 'gmail' and scope is not None else {}), **cfg}
    cid = s.save_connector({'Type': kind, 'Name': kind.title(), 'Active': 1, 'ConfigJson': json.dumps(c)}, 't')
    return s, cid


def send_as(*rows): return R(j={'sendAs': [{'sendAsEmail': 'alex.other@vendor.example', 'signature': 'Not me'}, *rows]})


@pytest.fixture(autouse=True)
def quiet():
    """No background read, no live token, no OS keychain: each test says what Google answers."""
    with mock.patch.object(signatures, '_later') as later, mock.patch.object(googlecal, 'access_token', return_value='at'), \
         mock.patch.multiple('taskuary.store.vault', seal=lambda v: v, unseal=lambda v: v):
        yield later


def test_gmail_html_reads_as_the_plain_lines_a_draft_carries():
    assert signatures.plain(HTML) == PLAIN
    assert signatures.plain('<p>Alex</p><p></p><p></p><p>Northwind</p>') == 'Alex\n\nNorthwind'
    assert signatures.plain('') == ''


def test_with_nothing_set_the_gmail_signature_signs_and_is_asked_once(quiet):
    s, _ = store()
    with mock.patch('taskuary.net.get', return_value=send_as({'sendAsEmail': ME.upper(), 'signature': HTML})) as get:
        assert responder.signature_for(s, ME) == PLAIN
        assert responder.signature_for(s, ME) == PLAIN          # held on the card - not asked per draft
    assert get.call_count == 1 and get.call_args.args[0] == signatures.SEND_AS
    quiet.assert_not_called()                                    # fresh: no background read either


def test_the_owners_own_signatures_come_first():
    s, cid = store()
    with mock.patch('taskuary.net.get', return_value=send_as({'sendAsEmail': ME, 'signature': HTML})):
        s.set_setting('email_signature', 'Alex\nSettings one', 'owner')
        assert responder.signature_for(s, ME) == 'Alex\nSettings one'
        cfg = json.loads(s.get_connector(cid)['ConfigJson'])
        s.set_connector_config(cid, {**cfg, 'signature': 'Alex\nCard one'})
        assert responder.signature_for(s, ME) == 'Alex\nCard one'


def test_no_gmail_signature_falls_through_to_style_then_the_name():
    s, _ = store()
    with mock.patch('taskuary.net.get', return_value=send_as({'sendAsEmail': ME, 'signature': ''})):
        assert responder.signature_for(s, ME) == 'Alex Doyle'


def test_a_sign_in_from_before_the_permission_keeps_working_asks_nothing_and_says_so():
    s, cid = store(scope=googlecal.SCOPE)
    with mock.patch('taskuary.net.get') as get:
        assert responder.signature_for(s, ME) == 'Alex Doyle'
    get.assert_not_called()
    cfg = json.loads(s.get_connector(cid)['ConfigJson'])
    assert googlecal.lacks_settings(cfg) and not googlecal.has_settings(cfg)
    assert signatures.regrant(s) == [ME]
    assert signatures.overview(s)['regrant'] == [ME]
    assert not googlecal.lacks_settings({'address': ME})           # no Google sign-in at all: nothing to add by signing in again


def test_a_day_old_one_is_used_while_it_is_asked_again_behind_the_draft(quiet):
    s, cid = store()
    cfg = json.loads(s.get_connector(cid)['ConfigJson'])
    s.set_connector_config(cid, {**cfg, signatures.ACCOUNT: {ME: {'signature': 'Alex\nOld one', 'source': 'gmail',
                                                                  'at': time.time() - signatures.DAY - 5}}})
    with mock.patch('taskuary.net.get') as get:
        assert responder.signature_for(s, ME) == 'Alex\nOld one'
    get.assert_not_called(); quiet.assert_called_once()


def test_a_failed_read_keeps_the_last_good_one_and_asks_again_within_the_hour():
    s, cid = store()
    box = {'connector_id': cid, 'address': ME}
    with mock.patch('taskuary.net.get', return_value=send_as({'sendAsEmail': ME, 'signature': HTML})):
        signatures.refresh(s, box)
    with mock.patch('taskuary.net.get', return_value=R(500)), mock.patch.object(signatures, 'confident', return_value=''):
        row = signatures.refresh(s, box)
    assert row['signature'] == PLAIN
    assert time.time() - row['at'] > signatures.DAY - signatures.RETRY - 5


def test_signing_in_again_drops_the_held_one_so_the_next_draft_asks_with_the_new_permission():
    s, cid = store()
    cfg = json.loads(s.get_connector(cid)['ConfigJson'])
    s.set_connector_config(cid, {**cfg, signatures.ACCOUNT: {ME: {'signature': 'x', 'at': time.time()}}})
    f = {'cid': cid, 'verifier': 'v', 'client': ('id', 'sec')}
    tok = R(j={'access_token': 'a', 'refresh_token': 'rt2', 'expires_in': 3600, 'scope': FULL})
    with mock.patch('taskuary.googlecal.requests.post', return_value=tok), mock.patch('taskuary.calendar._REPLY', {}), \
         mock.patch('taskuary.calendar._UPCOMING', {}), mock.patch('taskuary.calendar._TODAY', {}), mock.patch('taskuary.peoplesearch.forget'):
        ok, said = googlecal._exchange(s, {'port': 7787}, f, 'code', None)
    assert ok and 'Gmail signature' in said
    assert signatures.ACCOUNT not in json.loads(s.get_connector(cid)['ConfigJson'])


# ...everything else: the sent mail's ending, used unasked only when it plainly is the signature
SIG = 'Best,\nAlex Doyle\nOperations Lead | Northwind'


def tail(lines, n, read):
    return mock.patch('taskuary.responder.signature_tail', return_value=(lines, n, read))


@pytest.mark.parametrize('lines,n,read,want', [
    (SIG.splitlines(), 9, 12, SIG),                              # most of plenty of mail, with the owner's name: used
    (SIG.splitlines(), 3, 3, ''),                                 # too little mail to be sure: stays Settings' offer
    (SIG.splitlines(), 6, 12, ''),                                # half is not most
    (['Thanks'], 10, 12, ''),                                     # a sign-off word is not a signature
    (['Operations', 'Northwind'], 10, 12, ''),                    # not the owner's name
    (['Alex Doyle', 'Sent from my iPhone'], 10, 12, ''),          # a phone's footer
])
def test_the_sent_mails_ending_is_used_only_when_it_plainly_is_the_signature(lines, n, read, want):
    s, _ = store(kind='imap')
    with tail(lines, n, read): assert signatures.confident(s, ME) == want


def test_an_imap_mailbox_signs_with_its_confident_sent_mail_ending():
    s, cid = store(kind='imap')
    with tail(SIG.splitlines(), 9, 12): signatures.refresh(s, {'connector_id': cid, 'address': ME})
    assert responder.signature_for(s, ME) == SIG
    assert signatures.overview(s)['accounts'] == [{'address': ME, 'signature': SIG}]


def test_learn_signature_still_reads_the_same():
    mails = [{'subject': 'Re: x', 'body': {'content': f'Hi,\n\n{w}\n\n{SIG}'}} for w in ('Done.', 'Sent it.', 'Friday works.')]
    with mock.patch('taskuary.histgen.sent_mail', return_value=(mails, [], 1, 'IMAP')):
        assert responder.learn_signature(MemoryStore()) == SIG
        assert responder.signature_tail(MemoryStore()) == (SIG.splitlines(), 3, 3)
