"""Delivery receipts, claims and recovery, using invented mail and mocked providers."""
import concurrent.futures
import json
import sqlite3
import smtplib
import threading
from pathlib import Path
from unittest import mock

import pytest
import requests

from taskuary import outbound, store as store_mod, verdicts
from taskuary.store import MemoryStore, SQLiteStore


SENT = {'channel': 'email', 'to': ['erin@example.com'], 'cc': []}
BODY = 'The export has been repaired and tested.'


def make_review(s, outgoing=False, kind='draft_reply', task_kind='reply'):
    tid = s.create_task({'Title': 'Repair the export', 'Kind': task_kind, 'Status': 'open', 'Source': 'email'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'graph:fixture-{tid}', 'ConversationId': f'fixture-thread-{tid}',
                         'Channel': 'email', 'SourceName': 'alex@example.com', 'Subject': 'Repair the export',
                         'FromEmail': 'erin@example.com', 'BodyText': 'Please repair the export and test it.',
                         'SentAt': '2026-10-01 09:00:00', 'Status': 'routed', 'Direction': 'out' if outgoing else 'in'})
    env = ({'channel': 'email', 'to': ['erin@example.com'], 'cc': ['gail@example.com'], 'subject': 'Export repaired'}
           if outgoing else {'kind': 'reply', 'to': ['erin@example.com'], 'cc': [], 'mode': 'reply_to'})
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': kind, 'Status': 'pending',
                        'DraftText': BODY, 'Deliver': json.dumps(env)})
    return tid, mid, rid


@pytest.fixture
def s():
    value = MemoryStore()
    yield value
    value.close()


def provider(outgoing):
    return 'taskuary.outbound.send_out' if outgoing else 'taskuary.outbound.reply_to_message'


def reconciliation(outgoing):
    return 'taskuary.outbound.reconcile_outbound' if outgoing else 'taskuary.outbound.reconcile_sent'


@pytest.mark.parametrize('outgoing', [False, True])
def test_concurrent_approvals_across_connections_deliver_once(tmp_path, outgoing):
    path = tmp_path / 'delivery.db'
    first, second = SQLiteStore(str(path)), SQLiteStore(str(path))
    entered, release = threading.Event(), threading.Event()
    try:
        tid, mid, rid = make_review(first, outgoing)
        old = second.get_review(rid)
        def send(*args, **kwargs):
            entered.set()
            assert release.wait(5)
            return SENT
        with mock.patch(provider(outgoing), side_effect=send) as sender, mock.patch.object(outbound, 'send_block', return_value=''):
            with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
                pending = pool.submit(verdicts.decide, first, first.get_review(rid), 'approve')
                assert entered.wait(5)
                try:
                    assert second.get_review(rid)['Status'] == 'pending'
                    assert second.get_review(rid)['DeliveryState'] == 'sending'
                    assert second.sent_reply(message_id=mid) is None
                    overlap = verdicts.decide(second, old, 'approve')
                    assert overlap['delivery'] == 'sending'
                    assert not overlap['ok']
                finally:
                    release.set()
                assert pending.result(timeout=5)['ok']
            assert sender.call_count == 1
        assert first.get_review(rid)['DeliveryState'] == 'sent'
        assert first.get_task(tid)['Status'] == 'done'
        with mock.patch(provider(outgoing)) as sender:
            assert verdicts.decide(second, old, 'approve')['already']
            sender.assert_not_called()
    finally:
        release.set(); first.close(); second.close()


@pytest.mark.parametrize('outgoing', [False, True])
def test_interruption_stays_unknown_and_cannot_be_retried_without_verification(s, outgoing):
    tid, mid, rid = make_review(s, outgoing)
    with mock.patch(provider(outgoing), side_effect=KeyboardInterrupt('interrupted send')):
        with pytest.raises(KeyboardInterrupt):
            verdicts.decide(s, s.get_review(rid), 'approve')
    rv = s.get_review(rid)
    assert (rv['Status'], rv['DeliveryState'], rv['DeliveryClaim']) == ('pending', 'unknown', None)
    assert s.sent_reply(message_id=mid) is None
    assert s.get_task(tid)['Status'] == 'open'
    with mock.patch(provider(outgoing)) as sender, mock.patch(reconciliation(outgoing), return_value=None):
        out = verdicts.decide(s, rv, 'approve')
    assert out['delivery'] == 'unknown'
    assert 'nothing was sent again' in out['send_error']
    sender.assert_not_called()


@pytest.mark.parametrize('outgoing', [False, True])
def test_hard_interruption_recovers_original_attempt_on_reopen(tmp_path, outgoing):
    path = tmp_path / 'interrupted.db'
    first = SQLiteStore(str(path))
    tid, mid, rid = make_review(first, outgoing)
    rv = first.get_review(rid)
    snapshot = {'envelope': json.loads(rv['Deliver']), 'message': first.get_message(mid), 'body': BODY,
                'status': 'approved', 'actor': 'owner', 'note': None, 'attempted_at': '2026-10-01T10:00:00Z'}
    claim = first.claim_review_delivery(rid, snapshot, rv)
    # A hard process stop cannot run a finally block. Dropping only its volatile
    # claim registration models that boundary while retaining the actual SQLite row.
    with store_mod._DELIVERY_LOCK:
        store_mod._DELIVERY_CLAIMS.discard(claim['token'])
    first.close()
    second = SQLiteStore(str(path))
    try:
        recovered = second.get_review(rid)
        assert recovered['DeliveryState'] == 'unknown'
        assert recovered['DeliveryClaim'] is None
        assert json.loads(recovered['DeliveryEnvelope'])['body'] == BODY
        assert second.sent_reply(message_id=mid) is None
        with mock.patch(provider(outgoing)) as sender, mock.patch(reconciliation(outgoing), return_value={'state': 'sent', 'sent': SENT}):
            result = verdicts.decide(second, recovered, 'approve')
        sender.assert_not_called()
        assert result['delivery'] == 'reconciled'
        assert second.get_task(tid)['Status'] == 'done'
        assert second.sent_reply(message_id=mid)['DeliveryState'] == 'sent'
    finally:
        second.close()


@pytest.mark.parametrize('outgoing', [False, True])
@pytest.mark.parametrize('unverified', [None, {'state': 'unknown'}, {'state': 'sent', 'sent': None}])
def test_unverifiable_reconciliation_never_resends(s, outgoing, unverified):
    tid, mid, rid = make_review(s, outgoing)
    with mock.patch(provider(outgoing), side_effect=requests.exceptions.ReadTimeout('receipt lost')), mock.patch(reconciliation(outgoing), return_value=None):
        first = verdicts.decide(s, s.get_review(rid), 'approve')
    assert first['delivery'] == 'unknown'
    with mock.patch(provider(outgoing)) as sender, mock.patch(reconciliation(outgoing), return_value=unverified):
        retry = verdicts.decide(s, s.get_review(rid), 'approve')
    sender.assert_not_called()
    assert retry['delivery'] == 'unknown'
    assert s.get_task(tid)['Status'] == 'open'
    assert s.sent_reply(message_id=mid) is None


@pytest.mark.parametrize('outgoing', [False, True])
def test_explicit_confirmed_absence_allows_one_new_approved_attempt(s, outgoing):
    tid, mid, rid = make_review(s, outgoing)
    with mock.patch(provider(outgoing), side_effect=TimeoutError('no receipt')), mock.patch(reconciliation(outgoing), return_value=None):
        verdicts.decide(s, s.get_review(rid), 'approve')
    changed = BODY + ' The totals also match.'
    with mock.patch(provider(outgoing), return_value=SENT) as sender, mock.patch(reconciliation(outgoing), return_value={'state': 'absent'}) as checked:
        result = verdicts.decide(s, s.get_review(rid), 'approve', changed)
    assert checked.call_args.args[2] == BODY  # reconcile the old attempt, not the owner's new text
    sender.assert_called_once()
    assert changed in sender.call_args.args
    assert result['status'] == 'edited'
    assert s.get_review(rid)['FinalText'] == changed
    assert s.get_review(rid)['DeliveryState'] == 'sent'
    assert s.get_task(tid)['Status'] == 'done'


@pytest.mark.parametrize('outgoing', [False, True])
def test_definite_failure_remains_retryable_and_success_finishes_the_task(s, outgoing):
    tid, mid, rid = make_review(s, outgoing)
    with mock.patch(provider(outgoing), side_effect=RuntimeError('fixture provider refused (403)')):
        failed = verdicts.decide(s, s.get_review(rid), 'approve')
    assert failed['delivery'] == 'failed'
    assert s.get_review(rid)['Status'] == 'pending'
    assert s.get_task(tid)['Status'] == 'open'
    assert s.sent_reply(message_id=mid) is None
    with mock.patch(provider(outgoing), return_value=SENT) as sender:
        sent = verdicts.decide(s, s.get_review(rid), 'approve')
    sender.assert_called_once()
    assert sent['delivery'] == 'sent'
    assert s.get_task(tid)['Status'] == 'done'


@pytest.mark.parametrize('outgoing', [False, True])
@pytest.mark.parametrize('receipt', [None, {}, {'to': ['erin@example.com']}])
def test_missing_provider_receipt_is_unknown_not_success(s, outgoing, receipt):
    tid, mid, rid = make_review(s, outgoing)
    with mock.patch(provider(outgoing), return_value=receipt):
        result = verdicts.decide(s, s.get_review(rid), 'approve')
    assert result['delivery'] == 'unknown'
    assert s.get_review(rid)['Status'] == 'pending'
    assert s.get_task(tid)['Status'] == 'open'
    assert s.sent_reply(message_id=mid) is None


def test_live_send_blocks_rejection_attachment_removal_and_envelope_changes(s):
    tid, mid, rid = make_review(s)
    file = verdicts.attach(s, rid, 'report.txt', b'original report')['attachments'][0]
    def send(_store, msg, body, **kwargs):
        assert not verdicts.decide(s, s.get_review(rid), 'reject')['ok']
        s.decide_review(rid, 'rejected', None, 'owner')
        assert s.get_review(rid)['Status'] == 'pending'
        with pytest.raises(ValueError, match='attachments must be kept'):
            verdicts.attach(s, rid, 'report.txt', b'replacement')
        with pytest.raises(ValueError, match='attachments must be kept'):
            verdicts.detach(s, rid, 'report.txt')
        assert not s.set_review_envelope(rid, {'kind': 'reply', 'to': ['ray@example.com']})
        s.update_review_draft(rid, 'Different text.', None)
        assert body == BODY
        assert kwargs['to'] == ['erin@example.com']
        assert Path(file['path']).read_bytes() == b'original report'
        assert s.get_review(rid)['DraftText'] == BODY
        return SENT
    with mock.patch.object(outbound, 'reply_to_message', side_effect=send):
        result = verdicts.decide(s, s.get_review(rid), 'approve')
    assert result['ok']
    assert s.get_review(rid)['Status'] == 'approved'


def test_unknown_attempt_keeps_attachments_and_recipient_envelope(s):
    tid, mid, rid = make_review(s)
    file = verdicts.attach(s, rid, 'report.txt', b'original report')['attachments'][0]
    with mock.patch.object(outbound, 'reply_to_message', side_effect=TimeoutError()), mock.patch.object(outbound, 'reconcile_sent', return_value=None):
        verdicts.decide(s, s.get_review(rid), 'approve')
    with pytest.raises(ValueError): verdicts.detach(s, rid, 'report.txt')
    with pytest.raises(ValueError): verdicts.attach(s, rid, 'report.txt', b'new')
    assert not s.set_review_envelope(rid, {'kind': 'reply', 'to': ['ray@example.com']})
    s.update_review_draft(rid, 'A new reply.', None)
    assert s.get_review(rid)['DraftText'] == BODY
    assert Path(file['path']).read_bytes() == b'original report'


def test_new_message_during_send_keeps_task_open(s):
    tid, mid, rid = make_review(s, task_kind='coding')
    def send(*args, **kwargs):
        s.add_message({'TaskId': tid, 'ExternalId': 'graph:new-ask', 'ConversationId': f'fixture-thread-{tid}',
                       'Channel': 'email', 'FromEmail': 'erin@example.com', 'BodyText': 'Please also add the totals.',
                       'SentAt': '2026-10-01 10:00:00', 'Status': 'routed'})
        return SENT
    with mock.patch.object(outbound, 'reply_to_message', side_effect=send):
        assert verdicts.decide(s, s.get_review(rid), 'approve')['ok']
    assert s.get_review(rid)['DeliveryState'] == 'sent'
    assert s.get_task(tid)['Status'] == 'open'


def test_clarification_delivery_keeps_task_waiting(s):
    tid, mid, rid = make_review(s, kind='clarification', task_kind='coding')
    with mock.patch.object(outbound, 'reply_to_message', return_value=SENT):
        assert verdicts.decide(s, s.get_review(rid), 'approve')['ok']
    assert s.get_task(tid)['Status'] == 'waiting'


def test_owner_closure_during_send_is_not_overwritten(s):
    tid, mid, rid = make_review(s)
    def send(*args, **kwargs):
        # Mark done elsewhere can retire a draft via a different lifecycle route.
        s._exec("UPDATE review SET Status='closed_unsent' WHERE ReviewId=?", (rid,))
        return SENT
    with mock.patch.object(outbound, 'reply_to_message', side_effect=send):
        verdicts.decide(s, s.get_review(rid), 'approve')
    assert s.get_review(rid)['Status'] == 'closed_unsent'
    assert s.get_review(rid)['DeliveryState'] == 'sent'
    assert s.sent_reply(message_id=mid) is not None


def test_sent_folder_absence_and_matching_greeting_are_unverifiable(s):
    msg = {'Channel': 'email', 'ExternalId': 'graph:fixture', 'ConversationId': 'fixture', 'SourceName': 'alex@example.com'}
    response = mock.Mock(status_code=200)
    response.json.return_value = {'value': [{'id': 'other', 'sentDateTime': '2026-10-01T10:00:01Z',
                                            'body': {'contentType': 'Text', 'content': BODY[:20] + ' Other work.'},
                                            'toRecipients': [{'emailAddress': {'address': 'erin@example.com'}}]}]}
    with mock.patch.object(outbound, '_graph_token', return_value='fixture-token'), mock.patch.object(outbound.requests, 'get', return_value=response):
        result = outbound.reconcile_sent(s, msg, BODY, since='2026-10-01T10:00:00Z', to=['erin@example.com'])
    assert result['state'] == 'unknown'
    response.json.return_value = {'value': []}
    with mock.patch.object(outbound, '_graph_token', return_value='fixture-token'), mock.patch.object(outbound.requests, 'get', return_value=response):
        assert outbound.reconcile_sent(s, msg, BODY)['state'] == 'unknown'


def test_provider_check_failure_is_unverifiable(s):
    msg = {'Channel': 'email', 'ExternalId': 'graph:fixture', 'SourceName': 'alex@example.com'}
    with mock.patch.object(outbound, '_graph_token', return_value='fixture-token'), mock.patch.object(outbound.requests, 'get', return_value=mock.Mock(status_code=503)):
        assert outbound.reconcile_sent(s, msg, BODY)['state'] == 'unknown'


def test_old_unknown_envelope_migrates_without_becoming_sent(tmp_path):
    path = tmp_path / 'old.db'
    with sqlite3.connect(path) as cx:
        cx.execute('CREATE TABLE review (ReviewId INTEGER PRIMARY KEY, TaskId INTEGER, MessageId INTEGER, RunId INTEGER, Kind TEXT, DraftText TEXT, FinalText TEXT, Status TEXT, Reason TEXT, DecidedBy TEXT, DecidedAt TEXT, DecideNote TEXT, CreatedAt TEXT, Deliver TEXT)')
        cx.execute('INSERT INTO review (ReviewId,Kind,DraftText,FinalText,Status,Deliver) VALUES (1,?,?,?,?,?)',
                   ('draft_reply', BODY, BODY, 'pending', json.dumps({'kind': 'reply', 'delivery': 'unknown', 'attempted_at': '2026-10-01T10:00:00Z'})))
    migrated = SQLiteStore(str(path))
    try:
        assert migrated.get_review(1)['DeliveryState'] == 'unknown'
        assert migrated.sent_reply(message_id=1) is None
        with mock.patch.object(outbound, 'reply_to_message') as sender, mock.patch.object(outbound, 'reconcile_sent', return_value=None) as checked:
            assert verdicts.decide(migrated, migrated.get_review(1), 'approve')['delivery'] == 'unknown'
        sender.assert_not_called()
        assert checked.call_args.kwargs['since'] == '2026-10-01T10:00:00Z'
    finally:
        migrated.close()


@pytest.mark.parametrize('verb', ['reject', 'no_reply', 'close_unsent'])
def test_late_other_verdict_cannot_overwrite_confirmed_edited_receipt(s, verb):
    tid, mid, rid = make_review(s)
    entered, release = threading.Event(), threading.Event()
    original = s.decide_review
    expected_status = verdicts.VERB2STATUS[verb]
    def delayed(*args, **kwargs):
        if args[1] == expected_status:
            entered.set()
            assert release.wait(5)
        return original(*args, **kwargs)
    edited = BODY + ' Totals verified.'
    with mock.patch.object(s, 'decide_review', side_effect=delayed), mock.patch.object(outbound, 'reply_to_message', return_value=SENT):
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
            other = pool.submit(verdicts.decide, s, s.get_review(rid), verb)
            assert entered.wait(5)
            try:
                assert verdicts.decide(s, s.get_review(rid), 'approve', edited)['ok']
            finally:
                release.set()
            result = other.result(timeout=5)
    assert not result['ok']
    assert result['already']
    receipt = s.sent_reply(message_id=mid)
    assert (receipt['Status'], receipt['DeliveryState'], receipt['FinalText']) == ('edited', 'sent', edited)
    assert not any('Closed without sending' in c['Body'] for c in s.list_comments(tid))


@pytest.mark.parametrize('mutation', ['draft', 'envelope', 'attachment'])
def test_stale_reviewed_content_is_not_silently_substituted(s, mutation):
    tid, mid, rid = make_review(s)
    if mutation == 'attachment': verdicts.attach(s, rid, 'report.txt', b'first')
    reviewed = s.get_review(rid)
    if mutation == 'draft': s.save_review_draft(rid, 'Another reply entirely.')
    elif mutation == 'envelope': s.set_review_envelope(rid, {'kind': 'reply', 'to': ['ray@example.com']})
    else: verdicts.attach(s, rid, 'report.txt', b'other')  # same name and byte length
    with mock.patch.object(outbound, 'reply_to_message') as sender:
        result = verdicts.decide(s, reviewed, 'approve')
    assert not result['ok']
    assert 'changed before approval' in result['send_error']
    sender.assert_not_called()
    assert s.get_task(tid)['Status'] == 'open'


@pytest.mark.parametrize('state', ['sent', 'absent', 'unknown'])
def test_recovery_checks_original_attempt_even_after_new_inbound(s, state):
    tid, mid, rid = make_review(s, task_kind='coding')
    with mock.patch.object(outbound, 'reply_to_message', side_effect=TimeoutError()), mock.patch.object(outbound, 'reconcile_sent', return_value=None):
        verdicts.decide(s, s.get_review(rid), 'approve')
    s.add_message({'TaskId': tid, 'ExternalId': 'graph:later-question', 'ConversationId': f'fixture-thread-{tid}',
                   'Channel': 'email', 'FromEmail': 'erin@example.com', 'BodyText': 'Please also add totals.',
                   'SentAt': '2026-10-01 10:00:00', 'Status': 'routed'})
    s.mark_review_stale(rid)
    with mock.patch.object(outbound, 'reply_to_message') as sender, mock.patch.object(outbound, 'reconcile_sent', return_value={'state': state, 'sent': SENT}) as checked:
        result = verdicts.decide(s, s.get_review(rid), 'approve')
    checked.assert_called_once()
    assert checked.call_args.args[2] == BODY
    sender.assert_not_called()
    assert s.get_task(tid)['Status'] == 'open'
    if state == 'sent':
        assert result['delivery'] == 'reconciled'
        assert s.sent_reply(message_id=mid)['FinalText'] == BODY
    elif state == 'absent':
        assert result['stale'] and result['delivery'] == 'failed'
        assert s.sent_reply(message_id=mid) is None
    else:
        assert result['delivery'] == 'unknown'


@pytest.mark.parametrize('state', ['sending', 'unknown', 'sent'])
def test_all_draft_hold_and_context_mutations_preserve_attempt(s, state):
    tid, mid, rid = make_review(s)
    rv = s.get_review(rid)
    snapshot = {'envelope': json.loads(rv['Deliver']), 'message': s.get_message(mid), 'body': BODY,
                'status': 'approved', 'actor': 'owner', 'note': None, 'attempted_at': '2026-10-01T10:00:00Z'}
    claim = s.claim_review_delivery(rid, snapshot, rv)
    if state != 'sending': s.finish_review_delivery(rid, claim['token'], state, receipt=SENT if state == 'sent' else None)
    try:
        s.save_review_draft(rid, 'An unreviewed replacement.')
        s.update_review_draft(rid, 'A generated replacement.', None)
        s.pin_review_context(rid, 12345, 'new-revision')
        s.update_review_message(rid, 12345)
        assert s.hold_reviews(tid) == 0
        s.unhold_review(rid)
        row = s.get_review(rid)
        assert row['DraftText'] == BODY and row['MessageId'] == mid
        assert row['ContextRevision'] is None
        assert row['Status'] == ('approved' if state == 'sent' else 'pending')
    finally:
        if state == 'sending': s.finish_review_delivery(rid, claim['token'], 'unknown')


@pytest.mark.parametrize('error', [RuntimeError('Zoho provider refused (503)'), RuntimeError('Messages.app did not answer within 20s'),
                                  RuntimeError('1 of 2 parts were sent before it failed')])
def test_unestablished_provider_outcome_is_not_retryable(s, error):
    tid, mid, rid = make_review(s)
    with mock.patch.object(outbound, 'reply_to_message', side_effect=error), mock.patch.object(outbound, 'reconcile_sent', return_value=None):
        result = verdicts.decide(s, s.get_review(rid), 'approve')
    assert result['delivery'] == 'unknown'
    assert s.sent_reply(message_id=mid) is None


def test_provider_status_classification_is_conservative():
    from taskuary.github import Refused
    response = requests.Response()
    response.status_code = 503
    assert outbound.delivery_uncertain(requests.HTTPError('server failure', response=response))
    assert outbound.delivery_uncertain(Refused('server failure', status=503))
    assert not outbound.delivery_uncertain(Refused('permission denied', status=403))
    assert not outbound.delivery_uncertain(smtplib.SMTPResponseException(550, 'mailbox refused'))


def test_partial_discord_reply_cannot_repeat_delivered_prefix(s):
    from taskuary import devtools
    tid, mid, rid = make_review(s)
    s._exec("UPDATE message SET Channel='discord', ExternalId='discord:fixture', ConversationId='discord:room' WHERE MessageId=?", (mid,))
    s.save_review_draft(rid, 'Export results: ' + ('verified ' * 245))
    with mock.patch.object(outbound, 'send_block', return_value=''), mock.patch.object(devtools, 'discord_send',
            side_effect=[{'channel': 'discord', 'to': ['room']}, RuntimeError('fixture refusal (403)')]) as sender:
        assert verdicts.decide(s, s.get_review(rid), 'approve')['delivery'] == 'unknown'
        assert verdicts.decide(s, s.get_review(rid), 'approve')['delivery'] == 'unknown'
    assert sender.call_count == 2  # two parts in the original attempt; no duplicate prefix
    assert s.get_task(tid)['Status'] == 'open'


def test_attachment_write_holds_durable_database_claim_exclusion(tmp_path):
    path = tmp_path / 'attachments.db'
    s = SQLiteStore(str(path))
    try:
        tid, mid, rid = make_review(s)
        write = Path.write_bytes
        blocked = []
        def competing_writer(file, data):
            # This independent connection does not use Taskuary's process-local lock.
            # A second process's claim begins with this same SQLite write reservation.
            with sqlite3.connect(path, timeout=0.02) as independent:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    independent.execute('BEGIN IMMEDIATE')
                blocked.append(True)
            return write(file, data)
        with mock.patch.object(Path, 'write_bytes', autospec=True, side_effect=competing_writer):
            verdicts.attach(s, rid, 'report.txt', b'approved report')
        assert blocked == [True]
        with mock.patch.object(outbound, 'reply_to_message', return_value=SENT) as sender:
            assert verdicts.decide(s, s.get_review(rid), 'approve')['ok']
        assert Path(sender.call_args.kwargs['attachments'][0]['path']).read_bytes() == b'approved report'
    finally:
        s.close()


def test_detach_excludes_reattach_and_claim_until_unlink_is_complete(tmp_path):
    path = tmp_path / 'detach.db'
    s = SQLiteStore(str(path))
    try:
        tid, mid, rid = make_review(s)
        verdicts.attach(s, rid, 'report.txt', b'old report')
        unlink = Path.unlink
        blocked = []
        def competing_writer(file, *args, **kwargs):
            # Reattaching from another process starts with the same write reservation.
            # It must remain excluded until the old attachment has been removed.
            with sqlite3.connect(path, timeout=0.02) as independent:
                with pytest.raises(sqlite3.OperationalError, match='locked'):
                    independent.execute('BEGIN IMMEDIATE')
                blocked.append(True)
            return unlink(file, *args, **kwargs)
        with mock.patch.object(Path, 'unlink', autospec=True, side_effect=competing_writer):
            assert verdicts.detach(s, rid, 'report.txt')['attachments'] == []
        assert blocked == [True]
        replacement = verdicts.attach(s, rid, 'report.txt', b'new approved report')['attachments'][0]
        def send(*args, **kwargs):
            assert kwargs['attachments'] == [replacement]
            assert Path(replacement['path']).read_bytes() == b'new approved report'
            return SENT
        with mock.patch.object(outbound, 'reply_to_message', side_effect=send):
            assert verdicts.decide(s, s.get_review(rid), 'approve')['ok']
        assert s.get_review(rid)['DeliveryState'] == 'sent'
    finally:
        s.close()


def test_closeout_comment_uses_the_same_claim_and_interruption_recovery(s):
    from taskuary import github
    tid, mid, rid = make_review(s)
    closeout = {'TaskId': tid, 'DraftText': json.dumps({'action': 'merge_pr', 'repo': 'northwind/ledger', 'number': 7})}
    def comment(*args):
        overlap = verdicts._post_with_closeout(s, closeout, s.get_review(rid), '', 'owner')
        assert not overlap['ok'] and overlap['delivery'] == 'sending'
        raise TimeoutError('lost comment receipt')
    with mock.patch('taskuary.ci._conn', return_value={'Secret': 'fixture-token'}), mock.patch.object(github, 'comment_issue', side_effect=comment) as sender:
        assert verdicts._post_with_closeout(s, closeout, s.get_review(rid), '', 'owner')['delivery'] == 'unknown'
        assert verdicts._post_with_closeout(s, closeout, s.get_review(rid), '', 'owner')['delivery'] == 'unknown'
    sender.assert_called_once()
    assert s.sent_reply(message_id=mid) is None


def test_recovery_of_unknown_reply_does_not_execute_pending_closeout(s):
    from taskuary import proposals
    tid, mid, rid = make_review(s)
    with mock.patch.object(outbound, 'reply_to_message', side_effect=TimeoutError()), mock.patch.object(outbound, 'reconcile_sent', return_value=None):
        verdicts.decide(s, s.get_review(rid), 'approve')
    pending = {'ReviewId': 999, 'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': 'fixture close-out'}
    with mock.patch.object(proposals, 'closeout_pending', return_value=pending), mock.patch.object(proposals, 'execute') as execute, \
            mock.patch.object(outbound, 'reply_to_message') as sender, mock.patch.object(outbound, 'reconcile_sent', return_value=None) as checked:
        result = verdicts.decide(s, s.get_review(rid), 'approve')
    checked.assert_called_once()
    sender.assert_not_called()
    execute.assert_not_called()
    assert result['delivery'] == 'unknown'
