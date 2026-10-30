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
    store.upsert_agent('coding', 'cli', 'local', json.dumps({'cmd': 'codex'}))
    seen = {}
    out = compose.compose_workflow(store, 'Have coding run the weekly access review every Monday', answering({
        'config': {'type': 'agent', 'title': 'Weekly access review', 'agent': 'coding',
                   'skill': '/weekly-access-review', 'cron': '0 8 * * 1', 'deliver': {'to': 'invented'}},
        'explain': 'Coding runs the saved skill every Monday.', 'confidence': 'high'}, seen))
    assert out['config'] == {'type': 'agent', 'title': 'Weekly access review', 'agent': 'coding',
                             'skill': 'weekly-access-review', 'cron': '0 8 * * 1', 'access': 'write',
                             'route': {'triage': {'how': 'never'}}}   # a workflow, not a watch: never triaged
    assert seen['user']['workflow_options']['agent'] == [{'name': 'coding'}]
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
    # no agent at all is a thing the owner fixes in Connections - the button says so; one that exists is named to pick from
    assert bad_agent['fix']['href'].startswith('#connections=AI') and 'AI' in bad_agent['error']
    store.upsert_agent('ap', 'accounts-payable', 'cli', '{}')
    named = compose.compose_workflow(store, 'do a thing', answering({
        'config': {'type': 'agent', 'title': 'Thing', 'agent': 'imaginary', 'prompt': 'Do it'}}))
    assert 'ap' in named['error'] and 'fix' not in named


def test_a_model_miss_asks_the_owner_to_say_it_again_not_a_config_error():
    """The owner cannot fix a missing config - "the model answered without a workflow config" was all they got (2026-10-17)."""
    for said in ({'explain': 'hm'}, {'config': {'type': 'nonsense', 'title': 'x'}}, {'config': {'type': 'agent', 'title': ''}}):
        out = compose.compose_workflow(MemoryStore(), 'do a thing', answering(said))
        assert out['error'] == compose.AGAIN.format('a routine') and 'config' not in out['error']
    assert compose.compose_workflow(MemoryStore(), 'do a thing', None)['fix']['label'] == 'Connect an AI'


def test_an_agent_workflow_carries_its_connections_what_it_asks_and_when_it_is_done():
    """The run reads uses / ask_first / done_when / browser (workflows.definition); the composer could set none of them."""
    store = MemoryStore()
    store.upsert_agent('ap', 'accounts-payable', 'cli', '{}')
    on = next(c for c in store.list_connectors() if c.get('Type') == 'handbook')
    store.save_connector({'ConnectorId': on['ConnectorId'], 'Active': True}, 'test')
    off = next(c for c in store.list_connectors() if not c.get('Active'))
    seen = {}
    out = compose.compose_workflow(store, 'every Monday at 8 check for duplicates', answering({
        'config': {'type': 'agent', 'title': 'Duplicate check', 'agent': 'ap', 'prompt': 'Find duplicates', 'cron': '0 8 * * 1',
                   'uses': [on['ConnectorId']], 'ask_first': 'changing any record', 'done_when': 'all clear or one task per pair',
                   'browser': False}}, seen))
    assert out['config']['uses'] == [on['ConnectorId']] and out['config']['ask_first'] == 'changing any record'
    assert out['config']['done_when'] == 'all clear or one task per pair' and 'browser' not in out['config']
    assert {'id': on['ConnectorId'], 'name': on.get('Name') or on.get('Type'), 'type': on['Type']} in seen['user']['workflow_options']['connections']
    assert 'daily_at is EVERY day' in seen['system']
    bad = compose.compose_workflow(store, 'x', answering({'config': {'type': 'agent', 'title': 'X', 'agent': 'ap', 'prompt': 'p',
                                                                      'uses': [off['ConnectorId']]}}))
    assert 'not switched on' in bad['error']


def test_the_definition_keeps_a_daily_time_and_names_its_connections():
    from taskuary import workflows
    store = MemoryStore()
    c = next(c for c in store.list_connectors() if c.get('Type') == 'handbook')
    d = workflows.definition(store, {'SourceId': 1, 'ConfigJson': json.dumps({'type': 'agent', 'title': 'T', 'prompt': 'p',
                                                                              'access': 'write', 'daily_at': '07:30', 'uses': [c['ConnectorId']]})})
    assert d['schedule'] == {'daily_at': '07:30'}
    assert f"CONNECTIONS: {c.get('Name') or c['Type']} (connection {c['ConnectorId']})" in workflows.brief(d, 'manual', 'now')


def test_the_builder_knows_taskuary_is_where_results_land_and_builds_a_clear_request():
    """The owner, 2026-10-15: it asked which connection - Teams or Outlook - would "open the finance tasks", called a job that
    opens tasks "really a report", and asked about things the request already said. "It does not have to ask us questions
    if it's clear." """
    s = compose.WORKFLOW_SYSTEM
    assert 'TASKUARY IS WHERE RESULTS LAND' in s and 'Never ask which connection opens a task' in s
    assert 'Opening tasks or drafting IS doing work' in s
    assert 'A clear request is built' in s and 'never ask which' in s
    assert 'A clear request is built, not questioned' in compose.JUDGEMENT          # the report builder too


def test_an_unclear_request_is_still_asked_about():
    """The owner, 2026-10-15: "it's okay if workflow asks questions if it's not clear" - building a clear request must not
    become guessing at an unclear one."""
    assert 'when the request is unclear - what the job is, what it should produce, for whom' in compose.WORKFLOW_SYSTEM


def test_the_workflow_builder_sees_the_catalog_and_a_lone_agent_step_is_still_a_prompt():
    """Steps are report source cards (flow.py), so the builder is handed the same ready catalog the report builder is - and a job
    that is nothing but an agent's hands stays the prompt-only workflow every run already knows."""
    store = MemoryStore()
    store.upsert_agent('ap', 'accounts-payable', 'cli', '{}')
    seen = {}
    out = compose.compose_workflow(store, 'sign in to the vendor portal every Monday and download the statements', answering({
        'config': {'type': 'agent', 'title': 'Portal statements', 'agent': 'ap', 'browser': True, 'repair': 'sometimes',
                   'flow': [{'id': 's1', 'kind': 'agent', 'label': 'Download', 'prompt': "Download this week's statements."}]}}, seen))
    assert 'flow' not in out['config'] and out['config']['prompt'] == "Download this week's statements." and 'repair' not in out['config']
    assert {c['type'] for c in seen['user']['catalog']} >= {'sqlite', 'taskuary'} and 'FLOW RULES' in seen['system']
