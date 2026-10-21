"""#238: a connection's card says what leans on it, beside Remove - before the press, never as a question after it.
Each dependent is found the way its own reader finds the card; nothing leaning says nothing. Invented world only."""
import json
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import dependents, playbooks, server
from taskuary.store import SQLiteStore

ALEX = 'alex@northwind.example'


def report(store, title, cfg, active=1):
    return store.save_source({'Channel': 'report', 'Address': title, 'Active': active,
                              'ConfigJson': json.dumps({'title': title, **cfg})}, 'test')


def kinds(store, cid): return {d['kind']: d['names'] for d in dependents.of(store, cid)}


def test_reports_and_workflows_that_read_the_card_are_named():
    store = SQLiteStore(':memory:')
    sql = store.get_connector_by_type('mssql')['ConnectorId']
    store.save_connector({'ConnectorId': sql, 'Active': 1}, 'test')
    report(store, 'Morning sales', {'type': 'mssql', 'query': 'select 1'})                       # by type: the default instance answers it
    report(store, 'Ledger check', {'type': 'mssql', 'connector_id': sql, 'query': 'select 2'})
    report(store, 'Paused one', {'type': 'mssql', 'query': 'select 3'}, active=0)                # off: nothing breaks
    report(store, 'Month close', {'type': 'agent', 'access': 'write', 'prompt': 'close the month', 'uses': [sql]})
    report(store, 'Invoice run', {'type': 'agent', 'flow': [{'id': 's1', 'kind': 'source', 'type': 'mssql', 'connector_id': sql},
                                                           {'id': 's2', 'kind': 'agent', 'prompt': 'file it'}]})
    report(store, 'Weather', {'type': 'rest', 'url': 'https://api.vendor.example/w'})           # another card's
    got = kinds(store, sql)
    assert sorted(got['report']) == ['Ledger check', 'Morning sales']
    assert sorted(got['workflow']) == ['Invoice run', 'Month close']


def test_a_second_instance_is_not_blamed_for_the_default_ones_reports():
    store = SQLiteStore(':memory:')
    first = store.get_connector_by_type('mssql')['ConnectorId']
    store.save_connector({'ConnectorId': first, 'Active': 1}, 'test')
    second = store.save_connector({'Type': 'mssql', 'Name': 'Northwind archive'}, 'test')
    report(store, 'Morning sales', {'type': 'mssql', 'query': 'select 1'})
    assert kinds(store, second) == {}, 'nothing names the second card: nothing to say'
    assert kinds(store, first)['report'] == ['Morning sales']


def test_brains_borrowers_drafts_rules_and_sources_of_a_mailbox_card():
    store = SQLiteStore(':memory:')
    ol = store.get_connector_by_type('outlook')['ConnectorId']
    store.save_connector({'ConnectorId': ol, 'Active': 1, 'Secret': 'rt', 'ConfigJson': json.dumps({'auth': 'user', 'account': ALEX})}, 'test')
    store.save_source({'Channel': 'email', 'Address': ALEX, 'ConnectorId': ol, 'Active': 1}, 'test')
    store.set_setting('triage_ai', f'connector:{ol}', 'test')
    # a Teams card with no sign-in of its own, naming the same account: it reads chats through this card
    teams = store.get_connector_by_type('teams')['ConnectorId']
    store.save_connector({'ConnectorId': teams, 'Active': 1}, 'test')
    store.save_source({'Channel': 'teams', 'Address': ALEX, 'ConnectorId': teams, 'Active': 1}, 'test')
    # a reply drafted to mail that arrived in this mailbox, and a rule kept for it
    tid = store._insert('task', {'Title': 'Invoice from Payworth'}, ('Title',))
    mid = store._insert('message', {'TaskId': tid, 'Channel': 'email', 'SourceName': ALEX, 'Subject': 'Invoice'}, ('TaskId', 'Channel', 'SourceName', 'Subject'))
    store._insert('review', {'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'DraftText': 'Paid today.', 'Status': 'pending'},
                  ('TaskId', 'MessageId', 'Kind', 'DraftText', 'Status'))
    store._insert('policy', {'Name': 'Payworth is fyi', 'Kind': 'sender', 'Pattern': 'payworth', 'Action': 'fyi', 'Mailbox': ALEX, 'Active': 1},
                  ('Name', 'Kind', 'Pattern', 'Action', 'Mailbox', 'Active'))
    got = kinds(store, ol)
    assert got['brain'] == ['Triage brain']
    assert got['card'] == [store.get_connector(teams)['Name']]
    assert len(got['draft']) == 1 and got['rule'] == ['Payworth is fyi'] and got['source'] == [ALEX]


def test_playbooks_that_name_the_card_kind(tmp_path):
    store = SQLiteStore(':memory:')
    qb = store.get_connector_by_type('quickbooks')['ConnectorId']
    (tmp_path / 'vendor-bill.md').write_text('# Enter a vendor bill\n\nwhen: a vendor invoice arrives\nuses: quickbooks (write: bills)\n'
                                             'steps: enter it\nalone: yes\nask first: over $500\ndone when: the bill is in\n', encoding='utf-8')
    with mock.patch.object(playbooks, 'folder', return_value=tmp_path):
        assert kinds(store, qb) == {'playbook': ['Enter a vendor bill']}


def test_the_route_answers_for_the_card_and_404s_a_missing_one():
    c = TestClient(server.app)
    cid = c.post('/api/connectors', json={'Type': 'prometheus', 'Name': 'Northwind metrics uses'}).json()['connectorId']
    assert c.get(f'/api/connectors/{cid}/uses').json() == {'data': []}
    assert c.get('/api/connectors/987654/uses').status_code == 404
