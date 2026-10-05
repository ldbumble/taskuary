"""Freshness checks must not rewrite an uncertain delivery before checking its receipt."""
from unittest import mock

import pytest

from taskuary import outbound, responder, server, verdicts
from taskuary.store import MemoryStore


@pytest.mark.parametrize('checked', [None, {'state': 'sent', 'sent': {'channel': 'email', 'to': ['erin@northwind.example']}}, {'state': 'absent'}])
def test_changed_thread_still_checks_original_delivery_without_redrafting_or_resending(checked):
    store = MemoryStore()
    tid = store.create_task({'Title': 'Check the export', 'Kind': 'reply', 'Status': 'open'}, 'test')
    mid = store.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': 'graph:demo-export',
        'ConversationId': 'demo-export', 'FromEmail': 'erin@northwind.example',
        'SourceName': 'alex@northwind.example', 'BodyText': 'Please check the export.',
        'SentAt': '2026-10-01 09:00:00', 'Status': 'routed'})
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
        'DraftText': 'The export is checked.'})
    try:
        with mock.patch.object(outbound, 'send_block', return_value=''), \
             mock.patch.object(outbound, 'reply_to_message', side_effect=TimeoutError('receipt lost')), \
             mock.patch.object(outbound, 'reconcile_sent', return_value=None):
            assert verdicts.decide(store, store.get_review(rid), 'approve')['delivery'] == 'unknown'
        store.mark_review_stale(rid)
        with mock.patch.object(server, 'store', store), \
             mock.patch.object(server, '_refresh_chat_context') as refresh, \
             mock.patch.object(responder, 'write_draft') as redraft, \
             mock.patch.object(outbound, 'reply_to_message') as send, \
             mock.patch.object(outbound, 'reconcile_sent', return_value=checked) as reconcile:
            result = server.decide(rid, server.DecideBody(verb='approve'))
        refresh.assert_not_called()
        redraft.assert_not_called()
        send.assert_not_called()
        reconcile.assert_called_once()
        assert reconcile.call_args.args[2] == 'The export is checked.'
        if checked and checked['state'] == 'sent':
            assert result['delivery'] == 'reconciled'
        elif checked and checked['state'] == 'absent':
            assert result['stale']
        else:
            assert result['delivery'] == 'unknown'
    finally:
        store.close()
