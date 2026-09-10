import json
from datetime import timedelta
from unittest import mock

from taskuary import channels
from taskuary.store import SQLiteStore
from tests.test_mail_catchup import FakeGraph, T0, graph_mail


MAILBOX = 'me@x.com'
CONVERSATION = 'shared-configured-folder-thread'


def _message(number, when, folder):
    row = graph_mail(number, when, folder=folder)
    row['conversationId'] = CONVERSATION
    return row


def _store(tmp_path):
    store = SQLiteStore(str(tmp_path / 'graph-chain.db'))
    outlook = store.get_connector_by_type('outlook')
    store.save_connector({
        'ConnectorId': outlook['ConnectorId'], 'Active': 1, 'Secret': 'synthetic-secret',
        'Roles': 'feed', 'ConfigJson': json.dumps({'tenant_id': 'T', 'client_id': 'C'}),
    }, 'fixture')
    source_id = store.save_source({
        'Channel': 'email', 'Address': MAILBOX, 'ConnectorId': outlook['ConnectorId'],
        'Active': 1, 'ConfigJson': json.dumps({'folders': ['inbox', 'archive']}),
    }, 'fixture')
    watermark = (T0 - timedelta(hours=1)).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    store._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?', (watermark, source_id))
    return store, source_id, watermark


def _poll(store, fake):
    with mock.patch.object(channels, 'graph_token', return_value='synthetic-token'), \
         mock.patch.object(channels, '_mail_msgs', fake), \
         mock.patch.object(channels.requests, 'get', side_effect=fake.history_get), \
         mock.patch.object(channels, '_body', side_effect=lambda m: m['body']['content']), \
         mock.patch.object(channels, '_addrs', return_value=[]), \
         mock.patch.object(channels, '_mail_cutoff',
                           return_value=(T0 + timedelta(hours=1)).strftime('%Y-%m-%dT%H:%M:%SZ')):
        return channels.poll_channels(store)


def _conversation_rows(store):
    return store._rows(
        'SELECT * FROM message WHERE ConversationId=? ORDER BY MessageId',
        (CONVERSATION,))


def test_history_waits_until_every_configured_folder_has_delivered_normal_arrivals(tmp_path):
    store, _source_id, _watermark = _store(tmp_path)
    inbox_d = _message(4, T0 + timedelta(minutes=20), 'inbox')
    archive_c = _message(3, T0 + timedelta(minutes=10), 'archive')
    fake = FakeGraph({'inbox': [inbox_d], 'archive': [archive_c]})

    added = _poll(store, fake)

    rows = _conversation_rows(store)
    assert added == 2
    assert {row['ExternalId'] for row in rows} == {'graph:inbox-4', 'graph:archive-3'}
    assert len(rows) == 2
    assert all(row['Status'] not in ('history', 'context') for row in rows)
    assert store.chain_coverage(CONVERSATION)['complete'] is True
    store.cx.close()


def test_failed_configured_folder_cannot_be_consumed_as_history_and_retry_routes_it_once(tmp_path):
    store, source_id, watermark = _store(tmp_path)
    old_mid = store.add_message({
        'ExternalId': 'fixture:old', 'ConversationId': 'fixture:old-thread',
        'Channel': 'email', 'Subject': 'preserve old row', 'BodyText': 'exact old body',
        'Status': 'surfaced',
    })
    store.set_funnel_state(f'msg:{old_mid}', 'done', note='exact old read receipt')
    store.save_doc('counsel', 'exact owner document', 'owner')
    old_row, old_states = dict(store.get_message(old_mid)), store.funnel_states()

    inbox_d = _message(4, T0 + timedelta(minutes=20), 'inbox')
    archive_c = _message(3, T0 + timedelta(minutes=10), 'archive')
    broken = FakeGraph({'inbox': [inbox_d], 'archive': [archive_c]}, fail_on_call=3)

    assert _poll(store, broken) == 1
    first = _conversation_rows(store)
    assert [row['ExternalId'] for row in first] == ['graph:inbox-4']
    assert first[0]['Status'] not in ('history', 'context')
    assert store.get_source(source_id)['LastPolledAt'] == watermark
    coverage = store.chain_coverage(CONVERSATION)
    assert coverage is None or coverage['complete'] is False

    healthy = FakeGraph({'inbox': [inbox_d], 'archive': [archive_c]})
    assert _poll(store, healthy) == 1

    rows = _conversation_rows(store)
    assert {row['ExternalId'] for row in rows} == {'graph:inbox-4', 'graph:archive-3'}
    assert len(rows) == 2
    assert all(row['Status'] not in ('history', 'context') for row in rows)
    assert store.chain_coverage(CONVERSATION)['complete'] is True
    assert dict(store.get_message(old_mid)) == old_row
    assert store.funnel_states() == old_states
    assert store.doc('counsel') == 'exact owner document'
    store.cx.close()
