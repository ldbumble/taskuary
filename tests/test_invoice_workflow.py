import json

import pytest

from taskuary.store import MemoryStore
from taskuary import invoice_workflow, verdicts, zoho


@pytest.fixture
def store():
    st = MemoryStore()
    card = st.get_connector_by_type('zoho_invoice')
    st.save_connector({'ConnectorId': card['ConnectorId'], 'Active': True, 'Scope': 'write',
                       'ConfigJson': json.dumps({'client_id': 'id', 'client_secret': 'secret',
                                                 'organization_id': 'org'}), 'Secret': 'refresh'}, 'test')
    return st


def source(store):
    card = store.get_connector_by_type('zoho_invoice')
    sid = store.save_source({'Channel': 'report', 'Address': 'Monthly invoices', 'ConnectorId': card['ConnectorId'],
        'Active': True, 'ConfigJson': json.dumps({'type': 'zoho_monthly_invoices', 'title': 'Monthly invoices',
            'connector_id': card['ConnectorId'], 'customers': [
                {'customer_id': 'cust-1', 'customer_name': 'Acme', 'recipient': 'ap@acme.test', 'currency': 'USD'}]})}, 'test')
    return store.get_source(sid)


def test_open_batch_is_idempotent_and_prefills_prior_total(store, monkeypatch):
    monkeypatch.setattr(zoho, 'latest_invoice', lambda *_: {'invoice_id': 'old-1', 'total': 125.5})
    src = source(store)
    one = invoice_workflow.open_batch(store, src, '2026-09')
    two = invoice_workflow.open_batch(store, src, '2026-09')
    assert one['BatchId'] == two['BatchId']
    assert len(store.list_invoice_batches(src['SourceId'])) == 1
    assert len(two['items']) == 1
    assert two['items'][0]['Amount'] == 125.5
    assert two['items'][0]['TemplateInvoiceId'] == 'old-1'
    assert two['items'][0]['Reference'] == f"TASKUARY-{src['SourceId']}-2026-09-cust-1"


def test_prepare_creates_a_durable_review_without_sending(store, monkeypatch):
    monkeypatch.setattr(zoho, 'latest_invoice', lambda *_: {'invoice_id': 'old-1', 'total': 125.5})
    monkeypatch.setattr(zoho, 'create_draft_from', lambda *_: {'invoice_id': 'new-1', 'invoice_number': 'INV-900'})
    monkeypatch.setattr(zoho, 'email_content', lambda *_: {'to': ['ap@acme.test'], 'subject': 'September invoice', 'body': 'Please see the invoice.'})
    batch = invoice_workflow.open_batch(store, source(store), '2026-09')
    out = invoice_workflow.prepare(store, batch['BatchId'])
    item = out['batch']['items'][0]
    assert out['created'] == 1
    assert item['Status'] == 'review_ready'
    rv = store.get_review(item['ReviewId'])
    assert rv['Status'] == 'pending'
    assert json.loads(rv['Deliver'])['invoice_id'] == 'new-1'
    assert store.get_message(rv['MessageId'])['Status'] == 'draft'


def test_approval_is_the_only_send_and_completes_batch(store, monkeypatch):
    monkeypatch.setattr(zoho, 'latest_invoice', lambda *_: {'invoice_id': 'old-1', 'total': 125.5})
    monkeypatch.setattr(zoho, 'create_draft_from', lambda *_: {'invoice_id': 'new-1', 'invoice_number': 'INV-900'})
    monkeypatch.setattr(zoho, 'email_content', lambda *_: {'to': ['ap@acme.test'], 'subject': 'September invoice', 'body': 'Draft body'})
    sent = []
    monkeypatch.setattr(zoho, 'send_invoice', lambda cfg, iid, to, subject, body: sent.append((iid, to, subject, body)) or {'channel': 'zoho_invoice', 'to': [to], 'invoice_id': iid})
    batch = invoice_workflow.open_batch(store, source(store), '2026-09')
    item = invoice_workflow.prepare(store, batch['BatchId'])['batch']['items'][0]
    rv = store.get_review(item['ReviewId'])
    out = verdicts.decide(store, rv, 'approve', 'Edited final body', actor='owner')
    assert out['ok'] is True
    assert sent[0][0] == 'new-1'
    assert sent[0][3] == 'Edited final body'
    assert store.invoice_item(item['ItemId'])['Status'] == 'sent'
    assert store.invoice_batch(batch['BatchId'])['Status'] == 'done'


def test_failed_send_stays_pending_and_keeps_item_retryable(store, monkeypatch):
    monkeypatch.setattr(zoho, 'latest_invoice', lambda *_: {'invoice_id': 'old-1', 'total': 125.5})
    monkeypatch.setattr(zoho, 'create_draft_from', lambda *_: {'invoice_id': 'new-1', 'invoice_number': 'INV-900'})
    monkeypatch.setattr(zoho, 'email_content', lambda *_: {'to': ['ap@acme.test'], 'subject': 'September invoice', 'body': 'Draft body'})
    monkeypatch.setattr(zoho, 'send_invoice', lambda *_: (_ for _ in ()).throw(zoho.ZohoError('mail refused')))
    batch = invoice_workflow.open_batch(store, source(store), '2026-09')
    item = invoice_workflow.prepare(store, batch['BatchId'])['batch']['items'][0]
    rv = store.get_review(item['ReviewId'])
    out = verdicts.decide(store, rv, 'approve', actor='owner')
    assert out['ok'] is False
    assert store.get_review(rv['ReviewId'])['Status'] == 'pending'
    assert store.invoice_item(item['ItemId'])['Status'] == 'review_ready'
    assert 'mail refused' in store.invoice_item(item['ItemId'])['Error']


def test_changed_total_on_multiline_template_is_refused(monkeypatch):
    monkeypatch.setattr(zoho, 'by_reference', lambda *_: None)
    monkeypatch.setattr(zoho, 'invoice', lambda *_: {'customer_id': 'c', 'total': 100, 'line_items': [
        {'item_id': 'one', 'quantity': 1, 'rate': 60}, {'item_id': 'two', 'quantity': 1, 'rate': 40}]})
    with pytest.raises(zoho.ZohoError, match='multiple line items'):
        zoho.create_draft_from({}, 'old', 110, 'ref', '2026-09')


def test_last_month_email_keeps_wording_but_advances_period_and_invoice_number():
    previous = {'Period': '2026-08', 'InvoiceNumber': 'INV-800'}
    text = 'August 2026 services — invoice INV-800 (2026-08). Thank you.'
    assert invoice_workflow._roll_email(text, previous, 'INV-900', '2026-09') == \
        'September 2026 services — invoice INV-900 (2026-09). Thank you.'
