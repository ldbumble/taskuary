"""Report delivery requires an explicit valid approval policy before any side effect."""
from unittest import mock

import pytest

from taskuary import outbound, reports
from taskuary.store import MemoryStore


def _source(store):
    sid = store.save_source({'Channel': 'report', 'Address': 'Weekly figures',
                             'Active': 1, 'ConfigJson': '{}'}, 'owner')
    return store.get_source(sid)


@pytest.mark.parametrize('gate', ['review ', ' REVIEW', '\treview\n'])
def test_review_with_whitespace_still_requires_approval(gate):
    store = MemoryStore()
    cfg = {'deliver': {'to': 'ops@northwind.example', 'gate': gate}}
    with mock.patch.object(outbound, 'send_out') as send:
        result = reports.deliver_report(store, _source(store), cfg, 'Weekly figures', 'Checked figures')
    send.assert_not_called()
    assert result['gate'] == 'review'
    assert store.get_message(result['message_id'])['Status'] == 'draft'
    assert len(store.list_reviews('pending')) == 1


@pytest.mark.parametrize('gate', ['automatic', 'approve', 'autoo', 'false', 1, True, {'mode': 'auto'}])
def test_invalid_gate_is_refused_before_creating_or_sending_anything(gate):
    store = MemoryStore()
    source = _source(store)
    cfg = {'deliver': {'to': 'ops@northwind.example', 'gate': gate}}
    with mock.patch.object(outbound, 'send_out') as send, pytest.raises(ValueError, match='delivery gate'):
        reports.deliver_report(store, source, cfg, 'Weekly figures', 'Checked figures')
    send.assert_not_called()
    assert store.list_reviews() == []
    assert store._rows('SELECT * FROM message') == []


def test_explicit_auto_still_sends_once():
    store = MemoryStore()
    cfg = {'deliver': {'to': 'ops@northwind.example', 'gate': 'auto'}}
    receipt = {'channel': 'email', 'to': ['ops@northwind.example']}
    with mock.patch.object(outbound, 'send_out', return_value=receipt) as send:
        result = reports.deliver_report(store, _source(store), cfg, 'Weekly figures', 'Checked figures')
    send.assert_called_once()
    assert result['gate'] == 'auto'
    assert store.get_message(result['message_id'])['Status'] == 'sent'
    assert store.list_reviews('pending') == []


def test_auto_report_is_not_recorded_as_sent_before_the_provider_confirms():
    store = MemoryStore()
    cfg = {'deliver': {'to': 'ops@northwind.example', 'gate': 'auto'}}
    def send(*args, **kwargs):
        assert store._one('SELECT Status FROM message')['Status'] == 'draft'
        return {'channel': 'email', 'to': ['ops@northwind.example']}
    with mock.patch.object(outbound, 'send_out', side_effect=send):
        result = reports.deliver_report(store, _source(store), cfg, 'Weekly figures', 'Checked figures')
    assert store.get_message(result['message_id'])['Status'] == 'sent'


def test_failed_auto_report_keeps_an_unsent_record():
    store = MemoryStore()
    cfg = {'deliver': {'to': 'ops@northwind.example', 'gate': 'auto'}}
    with mock.patch.object(outbound, 'send_out', side_effect=RuntimeError('fixture provider refused')):
        with pytest.raises(RuntimeError, match='provider refused'):
            reports.deliver_report(store, _source(store), cfg, 'Weekly figures', 'Checked figures')
    assert store._one('SELECT Status FROM message')['Status'] == 'draft'
