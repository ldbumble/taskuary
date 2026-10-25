"""An agent never sends from /api/tools/run (the owner, 2026-10-25: "never send without approval"). Every card starts at FULL
(scopes.FULL), so an agent holding the token could post to LinkedIn, send an invoice or place an order with no press. Now a call
that reaches a person waits as a proposal on the agent's own task; the owner's press runs it. The owner's own calls are unchanged.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, guard, proposals, scopes, server
from taskuary.reports import REGISTRY

c = TestClient(server.app)
SRV = config.load()['server']


def agent(tid=None):
    h = {'X-Taskuary-Token': SRV['agent_token']}
    return {**h, guard.TASK_HDR: guard.task_proof(SRV, tid)} if tid else h


def owner(): return {'X-Taskuary-Token': SRV.get('token') or ''}


class AgentSendsWaitForThePress(unittest.TestCase):
    def setUp(self):
        s = server.store
        self.tid = s.create_task({'Title': 'Announce the Northwind launch', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.card = s.get_connector_by_type('linkedin')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Roles': 'tool'}, 'test')
        self.ran = []
        self.patch = mock.patch.dict(REGISTRY, {'linkedin_post': lambda cfg: self.ran.append(cfg) or ('posted', 'urn:li:share:1')})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0}, 'test')

    def test_an_agents_post_on_a_full_card_is_queued_and_never_runs(self):
        self.assertEqual(scopes.scope_of(server.store.get_connector(self.card['ConnectorId'])), 'admin')
        r = c.post('/api/tools/run', headers=agent(self.tid),
                   json={'type': 'linkedin_post', 'text': 'We shipped.', 'task_id': self.tid, 'why': 'Alex asked for a launch post'})
        self.assertEqual(r.status_code, 202, r.text)
        j = r.json()
        self.assertTrue(j['queued']); self.assertIn("owner's press", j['says'])
        self.assertEqual(self.ran, [])                                   # the upstream was never called
        rv = server.store.get_review(j['review'])
        self.assertEqual((rv['TaskId'], rv['Kind'], rv['Status']), (self.tid, 'action', 'pending'))
        p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['type'], p['text'], p['connector_id']), ('run_tool', 'linkedin_post', 'We shipped.', self.card['ConnectorId']))
        self.assertNotIn('task_id', p)
        # ...and the owner's press is what runs it
        proposals.execute(server.store, rv, 'owner')
        self.assertEqual(len(self.ran), 1)

    def test_the_owner_still_runs_it_directly(self):
        r = c.post('/api/tools/run', headers=owner(), json={'type': 'linkedin_post', 'text': 'We shipped.'})
        self.assertTrue(r.json()['ok'], r.text); self.assertEqual(len(self.ran), 1)

    def test_no_task_named_is_a_refusal_that_says_how(self):
        r = c.post('/api/tools/run', headers=agent(), json={'type': 'linkedin_post', 'text': 'hi'})
        self.assertEqual(r.status_code, 422); self.assertIn('task_id', r.json()['detail']); self.assertEqual(self.ran, [])

    def test_a_neighbours_task_is_refused(self):
        other = server.store.create_task({'Title': 'Another job', 'Status': 'open'}, 'owner')
        r = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'linkedin_post', 'text': 'hi', 'task_id': other})
        self.assertEqual(r.status_code, 403); self.assertEqual(self.ran, [])

    def test_an_agent_cannot_smuggle_a_workflow_resume_onto_its_proposal(self):
        r = c.post('/api/tools/run', headers=agent(self.tid),
                   json={'type': 'linkedin_post', 'text': 'x', 'task_id': self.tid, 'flow_run': {'run': 1}, 'closeout': True})
        p = json.loads(server.store.get_review(r.json()['review'])['DraftText'])
        self.assertNotIn('flow_run', p); self.assertNotIn('closeout', p)


class WhatReaches(unittest.TestCase):
    def test_every_executor_is_a_decision(self):
        "A new executor is either a read, a write that reaches nobody, or a send - never inherited."
        undecided = [t for t in REGISTRY if not t.startswith('_') and scopes.needs(t) != 'read'
                     and t not in scopes.REACHES and t not in scopes.QUIET_WRITES]
        self.assertEqual(undecided, [])
        self.assertFalse(set(scopes.REACHES) & scopes.QUIET_WRITES)

    def test_mcp_reaches_unless_its_server_says_read_only(self):
        self.assertTrue(scopes.reaches('mcp', {}, None))
        self.assertTrue(scopes.reaches('mcp', {}, {'annotations': {}}))
        self.assertEqual(scopes.reaches('mcp', {}, {'annotations': {'readOnlyHint': True}}), '')

    def test_a_graphql_mutation_reaches_and_a_query_does_not(self):
        self.assertEqual(scopes.reaches('graphql', {'query': '{ viewer { login } }'}), '')
        self.assertEqual(scopes.reaches('graphql', {'query': '# who\nquery Me { viewer { login } }'}), '')
        self.assertTrue(scopes.reaches('graphql', {'query': 'mutation{addComment(input:{subjectId:"1",body:"hi"}){clientMutationId}}'}))
        self.assertTrue(scopes.reaches('graphql', {'query': '  # first a comment\n mutation Add { x }'}))

    def test_a_file_save_and_a_bill_do_not_reach(self):
        for t in ('sharepoint_save', 'onedrive_save', 'quickbooks_bill', 'sftp_put'): self.assertEqual(scopes.reaches(t), '', t)

    def test_an_agents_unannotated_mcp_tool_waits(self):
        s = server.store
        tid = s.create_task({'Title': 'Tell Erin the numbers', 'Status': 'open'}, 'owner')
        if not s.get_connector_by_type('mcp'):
            s.save_connector({'Type': 'mcp', 'Name': 'Chat server', 'Active': 1, 'Roles': 'tool', 'ConfigJson': json.dumps({'cmd': 'fake'})}, 'test')
        card = s.get_connector_by_type('mcp')
        s.save_connector({'ConnectorId': card['ConnectorId'], 'Active': 1, 'Roles': 'tool'}, 'test')
        ran = []
        tools = [{'name': 'post_message', 'read_only': False}, {'name': 'list_channels', 'read_only': True}]
        with mock.patch.dict(REGISTRY, {'mcp': lambda cfg: ran.append(cfg['tool']) or ('ok', 'done')}), \
             mock.patch('taskuary.mcp.list_tools', return_value=tools):
            r = c.post('/api/tools/run', headers=agent(tid), json={'type': 'mcp', 'tool': 'post_message', 'task_id': tid,
                                                                   'tool_args': {'text': 'hi'}})
            self.assertEqual(r.status_code, 202, r.text)
            self.assertTrue(c.post('/api/tools/run', headers=agent(tid), json={'type': 'mcp', 'tool': 'list_channels'}).json()['ok'])
        self.assertEqual(ran, ['list_channels'])
        s.save_connector({'ConnectorId': card['ConnectorId'], 'Active': 0}, 'test')


class AFileIsNotAMessage(unittest.TestCase):
    """The owner, 2026-10-25: agents may save to SharePoint or OneDrive through a card with write Authority, with no press - and say
    where it landed."""
    def setUp(self):
        s = server.store
        self.card = s.get_connector_by_type('sharepoint')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Roles': 'tool', 'Scope': 'write',
                          'ConfigJson': json.dumps({'tenant_id': 't', 'client_id': 'c'}), 'Secret': 's'}, 'test')

    def tearDown(self): server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0, 'Scope': ''}, 'test')

    def test_an_agent_saves_to_sharepoint_at_write_and_is_told_where(self):
        put = mock.Mock(status_code=201, json=lambda: {'name': 'summary.md', 'webUrl': 'https://northwind.example/sites/Ops/summary.md'})
        with mock.patch('taskuary.sharepoint._token', return_value='tok'), mock.patch('taskuary.sharepoint.site_id', return_value='sid'), \
             mock.patch('taskuary.sharepoint.requests.put', return_value=put) as p:
            r = c.post('/api/tools/run', headers=agent(), json={'type': 'sharepoint_save', 'site': 'northwind.example/sites/Ops',
                                                                'path': 'Shared Documents/summary.md', 'text': '# Q3'})
        j = r.json()
        self.assertEqual(r.status_code, 200); self.assertTrue(j['ok'], j)
        self.assertIn('https://northwind.example/sites/Ops/summary.md', j['output'])
        self.assertEqual(p.call_args.kwargs['data'], b'# Q3')
        self.assertEqual(p.call_args.kwargs['params'], {'@microsoft.graph.conflictBehavior': 'rename'})   # never overwrites

    def test_at_read_the_save_is_refused(self):
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Scope': 'read'}, 'test')
        r = c.post('/api/tools/run', headers=agent(), json={'type': 'sharepoint_save', 'path': 'a.md', 'text': 'x'})
        self.assertEqual(r.status_code, 403); self.assertIn('write', r.json()['detail'])

    def test_onedrive_save_says_where(self):
        from taskuary import sharing
        with mock.patch.object(sharing, 'onedrive_put', return_value='https://northwind.example/my/notes.md') as p:
            head, body = sharing.run_onedrive_save({'store': server.store, 'path': 'Taskuary/notes.md', 'text': 'hi'})
        self.assertIn('Taskuary/notes.md', body); self.assertIn('https://northwind.example/my/notes.md', body)
        self.assertEqual(p.call_args.args[1:3], ('Taskuary/notes.md', b'hi'))
        with self.assertRaises(ValueError): sharing.run_onedrive_save({'store': server.store, 'path': 'x.bin', 'data': 'not base64!'})


if __name__ == '__main__': unittest.main()
