import email.message
import email.utils
import json
from datetime import datetime, timedelta
from pathlib import Path
from unittest import mock

import pytest

from taskuary import chains, imapmail
from taskuary.store import SQLiteStore
from tests.test_imap_catchup import FakeBox, NOW


USER = 'me@myco.example'
ROOT = '<chain-root@partner.example>'


def _mail(uid, when, *, owner=False):
    msg = email.message.EmailMessage()
    msg['From'] = f'Me <{USER}>' if owner else 'Rita <rita@partner.example>'
    msg['To'] = USER
    msg['Subject'] = f'chain {uid}'
    msg['Date'] = email.utils.format_datetime(when)
    msg['Message-ID'] = ROOT if uid == 1 else f'<chain-{uid}@partner.example>'
    if uid != 1:
        msg['References'] = ROOT
    msg.set_content(f'exact body {uid}\n')
    return msg.as_bytes(), when


def _mails(uids, *, owner=False):
    return {uid: _mail(uid, NOW - timedelta(minutes=20 - uid), owner=owner)
            for uid in uids}


def _store(tmp_path: Path, config=None):
    tmp_path.mkdir(parents=True, exist_ok=True)
    store = SQLiteStore(str(tmp_path / 'chain.db'))
    connector = store.get_connector_by_type('gmail', with_secret=True)
    cfg = {'address': USER, 'imap_host': 'imap.gmail.com', **dict(config or {})}
    store.save_connector({
        'ConnectorId': connector['ConnectorId'], 'Secret': 'synthetic-password',
        'Active': 1, 'ConfigJson': json.dumps(cfg),
    }, 'fixture')
    store.save_source({
        'Channel': 'email', 'Address': USER,
        'ConnectorId': connector['ConnectorId'], 'Active': 1,
    }, 'fixture')
    return store, store.get_connector_by_type('gmail', with_secret=True)


def _poll(store, connector, box):
    with mock.patch.object(imapmail.imaplib, 'IMAP4_SSL', return_value=box):
        return imapmail.poll_imap(store, connector, [], llm=None)


def _config(store):
    return json.loads(store.get_connector_by_type('gmail')['ConfigJson'])


def _identity(*, sent=False, validity=7):
    box = 'Sent' if sent else 'INBOX'
    return {
        'scope': imapmail._scope('imap.gmail.com', 993, USER, box),
        'validity': validity,
        'mode': 'scoped-v1',
    }


class _SelectLog(FakeBox):
    def __init__(self, inbox, **kwargs):
        super().__init__(inbox, **kwargs)
        self.selections = []

    def select(self, box, readonly=False):
        self.selections.append((box.strip('"'), readonly))
        return super().select(box, readonly=readonly)


def test_chain_history_uses_the_exact_scoped_epoch_and_does_not_duplicate_or_hide_reused_uid(tmp_path):
    store, _connector = _store(tmp_path)
    scoped = imapmail._external_id(False, USER, 1, **_identity())
    original = store.add_message({
        'ExternalId': scoped, 'ConversationId': ROOT, 'Channel': 'email',
        'SourceName': USER, 'Subject': 'chain 1', 'FromEmail': 'rita@partner.example',
        'SentAt': '2026-09-06 10:00:00', 'BodyText': 'preserve existing scoped body',
        'Status': 'surfaced',
    })
    before = dict(store.get_message(original))

    box = _SelectLog(_mails([1]), validity=7)
    cov = chains.refresh_imap(
        store, box, USER, ROOT, before='2099-01-01 00:00:00', readonly=False,
        folder_identity=lambda sent, _box, _validity, _uids: _identity(sent=sent))

    assert cov['added'] == 0
    assert [row['ExternalId'] for row in store.thread_messages(ROOT)] == [scoped]
    assert dict(store.get_message(original)) == before
    assert box.selections == [('INBOX', True), ('INBOX', False)]

    # The same UID in a confirmed later epoch is a distinct provider message. An old legacy
    # identity must neither suppress it nor be rewritten.
    legacy = store.add_message({
        'ExternalId': f'imap:{USER}:9', 'ConversationId': ROOT, 'Channel': 'email',
        'SourceName': USER, 'Subject': 'old epoch', 'FromEmail': 'rita@partner.example',
        'SentAt': '2026-09-05 10:00:00', 'BodyText': 'preserve old epoch body',
        'Status': 'history',
    })
    old = dict(store.get_message(legacy))
    box = FakeBox(_mails([9]), validity=8)
    cov = chains.refresh_imap(
        store, box, USER, ROOT, before='2099-01-01 00:00:00',
        folder_identity=lambda sent, _box, _validity, _uids: _identity(sent=sent, validity=8))
    epoch8 = imapmail._external_id(False, USER, 9, **_identity(validity=8))
    assert cov['added'] == 1
    assert store.message_by_external(epoch8)['BodyText'] == 'exact body 9'
    assert dict(store.get_message(legacy)) == old
    store.cx.close()


class _FailFirstFetchOnce(FakeBox):
    def __init__(self, inbox, uid):
        super().__init__(inbox, validity=7)
        self.fail_uid = uid
        self.failed = False

    def uid(self, cmd, *args):
        if cmd == 'fetch' and int(args[0]) == self.fail_uid and not self.failed:
            self.failed = True
            self.fetched.append((self.box, self.fail_uid))
            return 'NO', [None]
        return super().uid(cmd, *args)


def test_pending_inbox_uid_and_retry_hole_cannot_be_swallowed_as_history(tmp_path):
    store, connector = _store(tmp_path)
    old_mid = store.add_message({
        'ExternalId': 'fixture:old', 'ConversationId': 'old-thread', 'Channel': 'email',
        'Subject': 'old preserved', 'BodyText': 'owner raw body', 'Status': 'surfaced',
    })
    store.set_funnel_state(f'msg:{old_mid}', 'done', note='owner exact read')
    store.save_doc('counsel', 'owner exact document', 'owner')
    old_row, old_states = dict(store.get_message(old_mid)), store.funnel_states()

    # The normal UID1 fetch fails once. An unprotected history scan would immediately fetch it
    # successfully while processing UID2 and permanently turn the owed arrival into history.
    broken = _FailFirstFetchOnce(_mails([1, 2]), 1)
    with pytest.raises(imapmail.IMAPPartialFailure):
        _poll(store, connector, broken)

    cfg = _config(store)
    assert cfg['imap_retry_uids']['uids'] == [1]
    assert [hit for hit in broken.fetched if hit == ('INBOX', 1)] == [('INBOX', 1)]
    assert store.message_by_external(f'imap:{USER}:1') is None
    assert not [row for row in store.thread_messages(ROOT) if row['Status'] == 'history']

    healthy = FakeBox(_mails([1, 2]), validity=7)
    assert _poll(store, store.get_connector_by_type('gmail', with_secret=True), healthy) == 1
    rows = store.thread_messages(ROOT)
    assert len(rows) == 2
    assert all(row['Status'] != 'history' for row in rows)
    assert dict(store.get_message(old_mid)) == old_row
    assert store.funnel_states() == old_states
    assert store.doc('counsel') == 'owner exact document'
    store.cx.close()


def test_later_inbox_uid_with_an_older_date_remains_an_arrival(tmp_path):
    store, connector = _store(tmp_path)
    inbox = {
        1: _mail(1, NOW),
        2: _mail(2, NOW - timedelta(days=1)),
    }

    assert _poll(store, connector, FakeBox(inbox, validity=7)) == 2

    rows = store.thread_messages(ROOT)
    assert len(rows) == 2
    assert all(row['Status'] != 'history' for row in rows)
    cfg = _config(store)
    uid2 = imapmail._external_id(
        False, USER, 2, scope=cfg['imap_uid_scope'],
        validity=cfg['imap_uidvalidity'], mode=cfg['imap_uid_identity'])
    assert store.message_by_external(uid2)['BodyText'] == 'exact body 2'
    store.cx.close()


class _ArrivalDuringChainSearch(FakeBox):
    def __init__(self, inbox, arriving):
        super().__init__(inbox, validity=7)
        self.arriving = arriving
        self.inserted = False

    def uid(self, cmd, *args):
        if cmd == 'search' and 'HEADER' in str(args[1]) and not self.inserted:
            self.boxes['INBOX'][3] = self.arriving
            self.inserted = True
        return super().uid(cmd, *args)


def test_uid_arriving_after_initial_search_is_left_for_the_next_normal_poll(tmp_path):
    store, connector = _store(tmp_path, {'imap_uid': 1, 'imap_uidvalidity': 7})
    initial = {2: _mail(2, NOW)}
    older_new_arrival = _mail(3, NOW - timedelta(days=2))
    first = _ArrivalDuringChainSearch(initial, older_new_arrival)

    assert _poll(store, connector, first) == 1
    assert first.inserted
    assert store.message_by_external(f'imap:{USER}:3') is None
    assert _config(store)['imap_uid'] == 2

    healthy = FakeBox({**initial, 3: older_new_arrival}, validity=7)
    assert _poll(store, store.get_connector_by_type('gmail', with_secret=True), healthy) == 1
    arrived = store.message_by_external(f'imap:{USER}:3')
    assert arrived is not None
    assert arrived['Status'] != 'history'
    assert _config(store)['imap_uid'] == 3
    store.cx.close()


def test_sent_chain_rows_use_the_same_prepared_identity_as_the_following_sent_poll(tmp_path):
    store, connector = _store(tmp_path)
    inbox = {3: _mail(3, NOW)}
    sent = {2: _mail(2, NOW - timedelta(minutes=5), owner=True)}

    assert _poll(store, connector, FakeBox(inbox, sent=sent, validity=7)) == 1

    cfg = _config(store)
    expected = imapmail._external_id(
        True, USER, 2, scope=cfg['imap_sent_uid_scope'],
        validity=cfg['imap_sent_uidvalidity'], mode=cfg['imap_sent_uid_identity'])
    sent_rows = store._rows("SELECT * FROM message WHERE Status='context' ORDER BY MessageId")
    assert [row['ExternalId'] for row in sent_rows] == [expected]
    assert store.message_by_external(f'imap-sent:{USER}:2') is None
    assert cfg['imap_sent_uid'] == 2
    store.cx.close()


class _ValiditySequence(FakeBox):
    def __init__(self, inbox, values):
        super().__init__(inbox, validity=None)
        self.values = list(values)

    def response(self, code):
        if code != 'UIDVALIDITY':
            return super().response(code)
        value = self.values.pop(0) if self.values else None
        return code, ([str(value).encode()] if value is not None else [None])


def test_missing_or_newly_observed_validity_keeps_the_active_poll_namespace(tmp_path):
    # An established saved epoch remains authoritative when this server omits UIDVALIDITY.
    saved, connector = _store(tmp_path / 'saved', {'imap_uid': 0, 'imap_uidvalidity': 7})
    assert _poll(saved, connector, FakeBox(_mails([1]), validity=None)) == 1
    saved_cfg = _config(saved)
    assert saved_cfg['imap_uidvalidity'] == 7
    assert saved_cfg['imap_uid_identity'] == 'legacy'
    assert saved.message_by_external(f'imap:{USER}:1') is not None
    saved.cx.close()

    # A fresh unknown epoch may become observable during the history SELECT. The active drain
    # keeps its unknown namespace; it does not rewrite its basis beneath its own closure.
    learned, connector = _store(tmp_path / 'learned')
    box = _ValiditySequence(_mails([1]), [None, 7, 7])
    assert _poll(learned, connector, box) == 1
    learned_cfg = _config(learned)
    assert learned_cfg['imap_uid_identity'] == 'scoped-unknown-v1'
    assert 'imap_uidvalidity' not in learned_cfg
    unknown = imapmail._external_id(
        False, USER, 1, scope=learned_cfg['imap_uid_scope'],
        validity=None, mode='scoped-unknown-v1')
    assert learned.message_by_external(unknown) is not None
    learned.cx.close()


class _RestoreFails(FakeBox):
    def __init__(self, inbox, sent, failure):
        super().__init__(inbox, sent=sent, validity=7)
        self.failure = failure
        self.inbox_selects = 0

    def select(self, box, readonly=False):
        name = box.strip('"')
        if name == 'INBOX':
            self.inbox_selects += 1
            if self.inbox_selects == 3:
                if self.failure == 'raise':
                    raise OSError('synthetic restore transport failure')
                return 'NO', [b'synthetic restore rejected']
        return super().select(box, readonly=readonly)


@pytest.mark.parametrize('failure', ['NO', 'raise'])
def test_failed_restore_is_fatal_before_cursor_progress_and_retry_keeps_owner_data(tmp_path, failure):
    store, connector = _store(tmp_path)
    old_mid = store.add_message({
        'ExternalId': 'fixture:preserved', 'ConversationId': 'preserved-thread',
        'Channel': 'email', 'Subject': 'preserved', 'BodyText': 'exact owner raw row',
        'Status': 'surfaced',
    })
    store.set_funnel_state(f'msg:{old_mid}', 'later', until='2099-01-01 00:00:00',
                           note='exact owner defer')
    store.save_doc('counsel', 'exact owner counsel', 'owner')
    old_row, old_states = dict(store.get_message(old_mid)), store.funnel_states()

    with pytest.raises(chains.IMAPRestoreError):
        box = _RestoreFails(_mails([1, 2]), _mails([2], owner=True), failure)
        _poll(store, connector, box)

    cfg = _config(store)
    assert cfg['imap_uid'] == 0
    assert box.box == 'Sent'
    chain_rows = store.thread_messages(ROOT)
    arrivals = [row for row in chain_rows if row['Status'] != 'context']
    assert len(arrivals) == 1
    assert arrivals[0]['Status'] != 'history'
    inbox_uid2 = imapmail._external_id(
        False, USER, 2, scope=cfg['imap_uid_scope'],
        validity=cfg['imap_uidvalidity'], mode=cfg['imap_uid_identity'])
    assert store.message_by_external(inbox_uid2) is None
    assert store.chain_coverage(ROOT)['complete'] is False
    assert dict(store.get_message(old_mid)) == old_row
    assert store.funnel_states() == old_states
    assert store.doc('counsel') == 'exact owner counsel'

    assert _poll(store, store.get_connector_by_type('gmail', with_secret=True),
                 FakeBox(_mails([1, 2]), sent=_mails([2], owner=True), validity=7)) == 2
    rows = store.thread_messages(ROOT)
    assert len([row for row in rows if row['Status'] != 'context']) == 2
    assert _config(store)['imap_uid'] == 2
    store.cx.close()


@pytest.mark.parametrize('failure', ['select', 'search'])
def test_sent_history_discovery_failure_is_incomplete_without_preparing_sent_state(tmp_path, failure):
    store, connector = _store(tmp_path)
    box = FakeBox(
        {1: _mail(1, NOW)}, sent={2: _mail(2, NOW - timedelta(minutes=5), owner=True)},
        validity=7,
        **({'select_bad': {'Sent'}} if failure == 'select' else {'search_bad': {'Sent'}}))

    with pytest.raises(imapmail.IMAPCommandError):
        _poll(store, connector, box)

    cfg = _config(store)
    assert store.chain_coverage(ROOT)['complete'] is False
    assert not any(key.startswith('imap_sent_') for key in cfg)
    store.cx.close()
