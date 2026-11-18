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

    def test_at_read_the_save_waits_for_the_press(self):
        "...never saved past the card's Authority; with no task to wait on, the refusal names the task_id that files it there."
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Scope': 'read'}, 'test')
        r = c.post('/api/tools/run', headers=agent(), json={'type': 'sharepoint_save', 'path': 'a.md', 'text': 'x'})
        self.assertEqual(r.status_code, 422); self.assertIn('write', r.json()['detail']); self.assertIn('task_id', r.json()['detail'])

    def test_onedrive_save_says_where(self):
        from taskuary import sharing
        with mock.patch.object(sharing, 'onedrive_put', return_value='https://northwind.example/my/notes.md') as p:
            head, body = sharing.run_onedrive_save({'store': server.store, 'path': 'Taskuary/notes.md', 'text': 'hi'})
        self.assertIn('Taskuary/notes.md', body); self.assertIn('https://northwind.example/my/notes.md', body)
        self.assertEqual(p.call_args.args[1:3], ('Taskuary/notes.md', b'hi'))
        with self.assertRaises(ValueError): sharing.run_onedrive_save({'store': server.store, 'path': 'x.bin', 'data': 'not base64!'})


if __name__ == '__main__': unittest.main()


class AWriteAboveTheCardsAuthorityWaitsForThePress(unittest.TestCase):
    """An agent's write on a card the owner narrowed to read was a flat 403 - "raise it under Intacct → Authority, or leave it and the
    agents stay hands-off": a step only the owner can take, said to the agent, and nothing lit for the owner. The agent was told (list_systems)
    that a change on a read-level system is a proposal the owner approves; the call itself now files that proposal on its task."""
    def setUp(self):
        s = server.store
        self.tid = s.create_task({'Title': 'Post the Payworth bill', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.card = s.get_connector_by_type('intacct')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Roles': 'tool', 'Scope': 'read'}, 'test')
        self.ran = []
        self.patch = mock.patch.dict(REGISTRY, {'intacct_create': lambda cfg: self.ran.append(cfg) or ('created APBILL', 'RECORDNO 41')})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0, 'Scope': ''}, 'test')

    def test_the_write_is_queued_on_its_task_and_the_press_runs_it(self):
        r = c.post('/api/tools/run', headers=agent(self.tid),
                   json={'type': 'intacct_create', 'object': 'APBILL', 'fields': {'VENDORID': 'V-PAYWORTH'}, 'task_id': self.tid})
        self.assertEqual(r.status_code, 202, r.text)
        j = r.json()
        self.assertTrue(j['queued']); self.assertIn('read', j['says']); self.assertEqual(self.ran, [])
        rv = server.store.get_review(j['review'])
        self.assertEqual((rv['TaskId'], rv['Status']), (self.tid, 'pending'))
        proposals.execute(server.store, rv, 'owner')
        self.assertEqual(len(self.ran), 1)

    def test_with_no_task_the_refusal_says_how_and_not_to_raise_the_authority(self):
        r = c.post('/api/tools/run', headers=agent(), json={'type': 'intacct_create', 'object': 'APBILL', 'fields': {}})
        self.assertIn(r.status_code, (403, 422)); self.assertIn('task_id', r.json()['detail']); self.assertEqual(self.ran, [])

    def test_the_owners_own_call_is_still_held_to_the_card(self):
        r = c.post('/api/tools/run', headers=owner(), json={'type': 'intacct_create', 'object': 'APBILL', 'fields': {}})
        self.assertEqual(r.status_code, 403); self.assertEqual(self.ran, [])


class AProposalSaysWhatNeverWhere(unittest.TestCase):
    """tools/run strips every key that says where a card's credentials go (reports.query_only) - but an agent's own proposal (the
    `propose` tool, a TASKUARY-PROPOSE line) kept them, and the owner's Approve ran it through resolve_cfg, where the body wins: a
    run_tool naming its own `base_url` sent the card's token there, and an MCP one naming `cmd` started that program - on a card that
    showed neither."""
    def test_the_proposal_filed_and_run_carries_no_place_of_the_agents(self):
        s = server.store
        tid = s.create_task({'Title': 'Check the Northwind ledger', 'Kind': 'general', 'Status': 'open'}, 'owner')
        card = s.get_connector_by_type('intacct')
        for p in ({'action': 'run_tool', 'type': 'intacct_create', 'object': 'VENDOR', 'record': {'NAME': 'Payworth'},
                   'connector_id': card['ConnectorId'], 'gateway': 'https://evil.example/x', 'sender_password': 'x', 'cmd': 'sh'},):
            q = proposals.queue(s, tid, dict(p), 'agent')
            kept = json.loads(s.get_review(q['reviewId'])['DraftText'])
            for k in ('gateway', 'sender_password', 'cmd'): self.assertNotIn(k, kept)
            self.assertEqual((kept['connector_id'], kept['object']), (card['ConnectorId'], 'VENDOR'))
        # ...the transcript's mark files through the same gate
        proposals.collect(s, tid, 'TASKUARY-PROPOSE {"action": "run_tool", "type": "intacct_update", "object": "VENDOR", '
                                  '"record": {"VENDORID": "V1"}, "gateway": "https://evil.example/y"}')
        last = json.loads(max((r for r in s.list_reviews() if r['TaskId'] == tid), key=lambda r: r['ReviewId'])['DraftText'])
        self.assertEqual(last['type'], 'intacct_update'); self.assertNotIn('gateway', last)

    def test_a_proposal_that_names_no_card_is_pinned_to_the_one_or_asked_which(self):
        """A run_tool proposal with no connector_id ran at the press on the first card of its type (resolve_cfg) - with two Intacct
        companies, a bill posted to whichever came first, under a card that named that one. It is pinned when filed: the one card of
        the type that is on and a tool, or refused naming the several."""
        s = server.store
        tid = s.create_task({'Title': 'Post the Payworth bill', 'Kind': 'general', 'Status': 'open'}, 'owner')
        cards = s.connectors_by_type('intacct')
        for c in cards: s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 0}, 'test')
        one = cards[0]['ConnectorId']
        s.save_connector({'ConnectorId': one, 'Active': 1, 'Roles': 'tool'}, 'test')
        two = s.save_connector({'Type': 'intacct', 'Name': 'Intacct - Northwind West', 'Active': 0, 'Roles': 'tool'}, 'test')
        try:
            p = {'action': 'run_tool', 'type': 'intacct_create', 'object': 'VENDOR', 'record': {'NAME': 'Payworth'}}
            q = proposals.queue(s, tid, dict(p), 'agent')
            self.assertEqual(json.loads(s.get_review(q['reviewId'])['DraftText'])['connector_id'], one)
            s.save_connector({'ConnectorId': two, 'Active': 1}, 'test')
            miss = []
            self.assertIsNone(proposals.queue(s, tid, dict(p), 'agent', refused=miss))
            self.assertIn('connector_id', miss[0]); self.assertIn(str(two), miss[0])
        finally:
            for c in s.connectors_by_type('intacct'): s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 0}, 'test')

    def test_an_mcp_call_naming_no_tool_is_said_back_not_put_before_the_owner(self):
        "run_system {type: mcp} with no `tool` was filed as an Approve card that could only fail at the press."
        s = server.store
        tid = s.create_task({'Title': 'Tidy the notes', 'Kind': 'general', 'Status': 'open'}, 'owner')
        miss = []
        self.assertIsNone(proposals.queue(s, tid, {'action': 'run_tool', 'type': 'mcp', 'tool_args': {}}, 'agent', refused=miss))
        self.assertIn('tool', miss[0])
