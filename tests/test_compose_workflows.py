import json

from taskuary import compose, zoho
from taskuary.store import MemoryStore


def answering(payload, seen=None):
    def llm(system, user, **_kwargs):
        if seen is not None: seen.update(system=system, user=json.loads(user))
        return json.dumps(payload)
    return llm


def test_ai_agent_workflow_uses_a_real_configured_agent():
    store = MemoryStore()
    store.upsert_agent('coder', 'cli', 'local', json.dumps({'cmd': 'codex'}))
    seen = {}
    out = compose.compose_workflow(store, 'Have coder run the weekly access review every Monday', answering({
        'config': {'type': 'agent', 'title': 'Weekly access review', 'agent': 'coder',
                   'skill': '/weekly-access-review', 'cron': '0 8 * * 1', 'deliver': {'to': 'invented'}},
        'explain': 'Coder runs the saved skill every Monday.', 'confidence': 'high'}, seen))
    assert out['config'] == {'type': 'agent', 'title': 'Weekly access review', 'agent': 'coder',
                             'skill': 'weekly-access-review', 'cron': '0 8 * * 1', 'access': 'write'}
    assert seen['user']['workflow_options']['agent'] == [{'name': 'coder'}]
    assert 'reports only read and summarize' in seen['system']


def test_invoice_workflow_resolves_customer_ids_to_trusted_zoho_records(monkeypatch):
    store = MemoryStore()
    card = store.get_connector_by_type('zoho_invoice')
    store.save_connector({'ConnectorId': card['ConnectorId'], 'Active': True, 'Scope': 'write',
                          'ConfigJson': json.dumps({'organization_id': 'org'}), 'Secret': 'refresh'}, 'test')
    customers = [
        {'customer_id': 'c-1', 'customer_name': 'Acme', 'recipient': 'billing@acme.test', 'currency': 'USD'},
        {'customer_id': 'c-2', 'customer_name': 'Northwind', 'recipient': 'ap@northwind.test', 'currency': 'USD'},
    ]
    monkeypatch.setattr(zoho, 'connection', lambda *_: {'organization_id': 'org'})
    monkeypatch.setattr(zoho, 'customers', lambda *_: customers)
    seen = {}
    out = compose.compose_workflow(store, 'Prepare Acme monthly invoices on the first', answering({
        'config': {'type': 'zoho_monthly_invoices', 'title': 'Monthly Acme invoices',
                   'connector_id': card['ConnectorId'], 'customer_ids': ['c-1'], 'cron': '0 9 1 * *'},
        'explain': 'A review-first monthly batch for Acme.', 'confidence': 'high'}, seen))
    assert out['config']['customers'] == [customers[0]]
    assert out['config']['connector_id'] == card['ConnectorId']
    assert 'customer_ids' not in out['config']
    assert seen['user']['workflow_options']['zoho_monthly_invoices'][0]['customers'] == customers


def test_workflow_composer_refuses_invented_agents_and_customers():
    store = MemoryStore()
    bad_agent = compose.compose_workflow(store, 'do a thing', answering({
        'config': {'type': 'agent', 'title': 'Thing', 'agent': 'imaginary', 'prompt': 'Do it'}}))
    assert 'configured CLI agents' in bad_agent['error']
