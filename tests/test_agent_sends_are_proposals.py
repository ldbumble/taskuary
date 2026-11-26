"""An agent never sends from /api/tools/run (the owner, 2026-10-25: "never send without approval"). Every card starts at FULL
(scopes.FULL), so an agent holding the token could post to LinkedIn, send an invoice or place an order with no press. Now a call
that reaches a person waits as a proposal on the agent's own task; the owner's press runs it. The owner's own calls are unchanged.
"""
import json, unittest
from taskuary import card
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, guard, proposals, scopes, server
from taskuary.reports import REGISTRY

c = TestClient(server.app)
SRV = config.load()['server']


def agent(tid=None):
    "A session's headers: the agent token and the proof of the task it is on - one that names no task in its body proves a task of its own."
    return {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, tid or 999996)}


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

    def test_a_read_whose_executor_answers_rows_and_columns_gives_the_agent_its_data(self):
        """Walk 22, 2026-11-25: an agent's read of linkedin_me - an executor that answers {rows, columns} - came back headline "rows", output
        "columns": the dict unpacked as a pair. Every reader of an executor reads either shape (reports.pair)."""
        me = lambda cfg: {'rows': [{'name': 'Alex Doyle', 'followers': 312}], 'columns': ['name', 'followers']}
        with mock.patch.dict(REGISTRY, {'linkedin_me': me}):
            r = c.post('/api/tools/run', headers=agent(self.tid), json={'task_id': self.tid, 'type': 'linkedin_me'}).json()
        self.assertTrue(r['ok'], r); self.assertEqual(r['headline'], '1 row'); self.assertIn('Alex Doyle', r['output']); self.assertIn('312', r['output'])

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


class ARedditPostFromItsInboxCard(unittest.TestCase):
    """The Reddit card reads an inbox and now posts: as it is seeded (no role set by hand) an agent's post waits for the press, the press
    posts on the card's own sign-in, and Reddit's link is what the card keeps. Reddit's HTTP is stubbed."""
    def setUp(self):
        from taskuary import net
        net._TOKENS.clear()
        s = server.store
        self.tid = s.create_task({'Title': 'Share the payroll write-up', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.card = s.get_connector_by_type('reddit')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Secret': 'pw',
                          'ConfigJson': json.dumps({'client_id': 'cid', 'client_secret': 'cs', 'username': 'alexdoyle'})}, 'test')

    def tearDown(self): server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0}, 'test')

    def test_proposed_then_posted_on_the_press_with_its_link(self):
        from tests.test_social import RedditNet
        from taskuary import inboxes
        r = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'reddit_post', 'task_id': self.tid, 'subreddit': 'smallbusiness',
                   'title': 'How we moved payroll', 'text': 'Three things we learned.', 'why': 'Alex asked to share it'})
        self.assertEqual(r.status_code, 202, r.text)
        rv = server.store.get_review(r.json()['review'])
        rd = RedditNet()
        with mock.patch.object(inboxes.requests, 'request', rd.request): out = proposals.execute(server.store, rv, 'owner')
        self.assertEqual(rd.submitted()[0]['data']['sr'], 'smallbusiness')
        self.assertEqual(out['url'], RedditNet.OK['json']['data']['url'])

    def test_a_refused_press_raises_and_posts_nothing(self):
        from tests.test_social import RedditNet
        from taskuary import inboxes
        r = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'reddit_post', 'task_id': self.tid, 'subreddit': 'smallbusiness',
                   'title': 'T', 'text': 'x', 'why': 'w'})
        rd = RedditNet({'json': {'errors': [['SUBMIT_VALIDATION_FLAIR_REQUIRED', 'Your post must contain post flair.', 'flair']]}}, [{'id': 'f1', 'text': 'Question'}])
        with mock.patch.object(inboxes.requests, 'request', rd.request), self.assertRaises(RuntimeError) as e:
            proposals.execute(server.store, server.store.get_review(r.json()['review']), 'owner')
        self.assertIn('flair - one of: Question', str(e.exception))


class WhatReaches(unittest.TestCase):
    def test_every_write_to_a_connector_waits_for_his_press(self):
        """The owner, 2026-11-25: "to write to the systems or any connector should require approval mechanically". Every executor that is
        not a read (scopes.ACTIONS) waits, an unclassified one included - only Taskuary's own store is written unpressed."""
        quiet = [t for t in REGISTRY if not t.startswith('_') and t not in ('mcp', 'graphql') and scopes.needs(t) != 'read'
                 and t not in scopes.OWN_STORE | scopes.NEVER_AGENT and not scopes.reaches(t)]      # his own script: no agent's call reaches it
        self.assertEqual(quiet, [])
        self.assertTrue(scopes.reaches('some_new_executor'))

    def test_mcp_reaches_unless_its_server_says_read_only(self):
        self.assertTrue(scopes.reaches('mcp', {}, None))
        self.assertTrue(scopes.reaches('mcp', {}, {'annotations': {}}))
        self.assertEqual(scopes.reaches('mcp', {}, {'annotations': {'readOnlyHint': True}}), '')

    def test_a_graphql_mutation_reaches_and_a_query_does_not(self):
        self.assertEqual(scopes.reaches('graphql', {'query': '{ viewer { login } }'}), '')
        self.assertEqual(scopes.reaches('graphql', {'query': '# who\nquery Me { viewer { login } }'}), '')
        self.assertTrue(scopes.reaches('graphql', {'query': 'mutation{addComment(input:{subjectId:"1",body:"hi"}){clientMutationId}}'}))
        self.assertTrue(scopes.reaches('graphql', {'query': '  # first a comment\n mutation Add { x }'}))

    def test_a_file_save_a_bill_and_a_record_wait_and_their_reads_do_not(self):
        for t in ('sharepoint_save', 'onedrive_save', 'quickbooks_bill', 'quickbooks_expense', 'sftp_put', 'sftp_move', 'smb_write', 'smb_move',
                  'intacct_create', 'intacct_update', 'zoho_invoice_draft', 'winrm'): self.assertTrue(scopes.reaches(t), t)
        for t in ('quickbooks_vendors', 'intacct', 'sftp_get', 'smb_read', 'sharepoint_file', 'calendar', 'google_sheets', 'hub_write'):
            self.assertEqual(scopes.reaches(t), '', t)

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


class AFileSavedIsAWrite(unittest.TestCase):
    """The owner, 2026-11-25: "why would file uploads ... have their own rules? ... to write to the systems or any connector should require
    approval mechanically". An agent's save to SharePoint waits as a card even at write Authority - nothing is put before his press - and
    the press saves it and says where it landed. (It ran unpressed at write before, 2026-10-25.)"""
    def setUp(self):
        s = server.store
        self.card = s.get_connector_by_type('sharepoint')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Roles': 'tool', 'Scope': 'write',
                          'ConfigJson': json.dumps({'tenant_id': 't', 'client_id': 'c'}), 'Secret': 's'}, 'test')

    def tearDown(self): server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0, 'Scope': ''}, 'test')

    def test_an_agents_save_at_write_waits_for_his_press_and_the_press_saves_it(self):
        tid = server.store.create_task({'Title': 'File the Q3 summary', 'Kind': 'general', 'Status': 'open'}, 'owner')
        put = mock.Mock(status_code=201, json=lambda: {'name': 'summary.md', 'webUrl': 'https://northwind.example/sites/Ops/summary.md'})
        with mock.patch('taskuary.sharepoint._token', return_value='tok'), mock.patch('taskuary.sharepoint.site_id', return_value='sid'), \
             mock.patch('taskuary.sharepoint.requests.put', return_value=put) as p:
            r = c.post('/api/tools/run', headers=agent(tid), json={'type': 'sharepoint_save', 'site': 'northwind.example/sites/Ops', 'task_id': tid,
                                                                   'path': 'Shared Documents/summary.md', 'text': '# Q3'})
            self.assertEqual(r.status_code, 202, r.text); self.assertTrue(r.json()['queued'])
            self.assertFalse(p.called, 'nothing is saved before his press')
            out = proposals.execute(server.store, server.store.get_review(r.json()['review']), 'owner')
        self.assertIn('https://northwind.example/sites/Ops/summary.md', json.dumps(out))
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

    def test_a_card_not_marked_an_agent_tool_is_the_same_card_for_his_press(self):
        # 'not marked as an agent tool (Intacct -> Role)' was a 403 the agent could only pass on in words - his press is the yes for this one call
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Roles': 'report', 'Scope': ''}, 'test')
        r = c.post('/api/tools/run', headers=agent(self.tid),
                   json={'type': 'intacct_create', 'object': 'APBILL', 'fields': {'VENDORID': 'V-PAYWORTH'}, 'task_id': self.tid})
        self.assertEqual(r.status_code, 202, r.text); self.assertIn('agent tool', r.json()['says']); self.assertEqual(self.ran, [])
        proposals.execute(server.store, server.store.get_review(r.json()['review']), 'owner')
        self.assertEqual(len(self.ran), 1)

    def test_a_read_on_a_connection_switched_off_is_one_card_whose_press_switches_it_on_and_runs_it(self):
        # the owner, 2026-11-25: "if it says it can't do something it just leaves the user hanging - it should find a way around it"
        from taskuary import outbound
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0, 'Secret': 'k'}, 'test')
        with mock.patch.dict(REGISTRY, {'intacct': lambda cfg: self.ran.append(cfg) or ('1 row', 'VENDOR V-1')}):
            r = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'intacct', 'object': 'VENDOR', 'task_id': self.tid})
            self.assertEqual(r.status_code, 202, r.text); self.assertIn('switched off', r.json()['says']); self.assertEqual(self.ran, [])
            again = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'intacct', 'object': 'APBILL', 'task_id': self.tid})
            self.assertEqual((again.status_code, again.json()['review']), (202, r.json()['review']))       # ...one card, never a pile
            self.assertIn('already up', again.json()['says'])
            rv = server.store.get_review(r.json()['review'])
            self.assertIsNone(outbound.review_connect(server.store, rv), 'set up and switched off: his press, not Connect')
            proposals.execute(server.store, rv, 'owner')
        self.assertEqual(len(self.ran), 1); self.assertTrue(server.store.get_connector(self.card['ConnectorId'])['Active'])

    def test_one_never_set_up_stands_with_its_connect(self):
        from taskuary import outbound
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0, 'Secret': ''}, 'test')
        r = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'intacct', 'object': 'VENDOR', 'task_id': self.tid})
        self.assertEqual(r.status_code, 202, r.text)
        fix = outbound.review_connect(server.store, server.store.get_review(r.json()['review']))
        self.assertTrue(fix and fix['href'] == '#connector=intacct', fix)

    def test_no_card_at_all_says_the_way_on(self):
        from taskuary.agenttools import NEXT_STEP
        r = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'local_file', 'path': 'x', 'task_id': self.tid})
        self.assertEqual(r.status_code, 403, r.text); self.assertIn(NEXT_STEP, r.json()['detail'])

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




def test_post_via_the_browser_hands_the_post_as_he_left_it_to_its_agent_once():
    """The owner, 2026-11-22 ("card first, sign-in at the press"): a post on a network not connected is its card; Post via the browser saves it
    as he left it and hands it to its agent once, however often it is pressed - and the card reads handed over, never Posted."""
    import json
    from unittest import mock
    from taskuary import general, proposals
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Post the week', 'Kind': 'general', 'Status': 'open'}, 'owner')
    rid = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'post it',
                        'DraftText': json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'A good week at Northwind.'})})
    with mock.patch.object(general, 'to_agent', return_value='woke') as to:
        outs = [proposals.via_browser(s, rid, 'A great week at Northwind.') for _ in range(3)]
    assert to.call_count == 1 and 'A great week at Northwind.' in to.call_args.args[2] and 'LinkedIn' in to.call_args.args[2]
    assert outs[0] == {'ok': True, 'status': 'approved', 'told': 'woke'} and all(o.get('already') for o in outs[1:])
    assert json.loads(s.get_review(rid)['FinalText'])['result'] == {'browser': True}
    mail = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps({'action': 'run_tool', 'type': 'github_issue'})})
    assert proposals.via_browser(s, mail, 'x')['ok'] is False


def test_a_post_handed_to_the_browser_is_pressed_not_done_for_the_agent_the_line_and_the_assistant():
    """Walk 6: three post cards in a line; Post via the browser on the LinkedIn one, and its agent was told "Done 7:31 AM: post to LinkedIn"
    in the very message asking it to go and post it, the X card came forward as if it had gone, and "what is waiting on me" left LinkedIn out.
    Pressed and done are two states: handed reads "not done" everywhere until its own final press has run on the site."""
    from taskuary import cardqueue, concierge, general, proposals
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Post the week', 'Kind': 'general', 'Status': 'open'}, 'owner')
    post = lambda kind, words: s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': f'the agent proposes to post on {kind}',
                                             'DraftText': json.dumps({'action': 'run_tool', 'type': kind, 'text': words})})
    li, x = post('linkedin_post', 'A good week at Northwind.'), post('x_post', 'A good week.')
    with mock.patch.object(general, 'to_agent', return_value='woke'): proposals.via_browser(s, li, '')
    said = cardqueue.screen(s, tid)
    assert any('NOT done yet' in l and 'linkedin' in l for l in said.splitlines()) and not any(l.startswith('- Done') for l in said.splitlines()), said
    assert cardqueue.state(s, tid)['live'] == [li] and x in cardqueue.held(s, tid), 'the next post waits until this one has gone'
    assert any(i['rid'] == li and 'not done yet' in i['line'] for i in card.lines(s, tid))
    # ...its own final press ran on the site: done, and the line moves on
    assert cardqueue.done(s, tid, 'Post on linkedin.example') == [li]
    assert not cardqueue.handed(s.get_review(li)) and cardqueue.state(s, tid)['live'] == [x]
    assert any(l.startswith('- Done') and 'linkedin' in l for l in cardqueue.screen(s, tid).splitlines())


def test_an_action_that_is_none_is_refused_with_the_ones_that_are():
    """A Claude agent proposed its LinkedIn post as 'post_linkedin' twice, was told only "unknown action", and handed the post to the owner
    as prose (goal walk, 2026-11-22). The refusal names the actions and how a post is written - which then goes, with no connection."""
    from taskuary import proposals
    from taskuary.store import MemoryStore
    ok, why = proposals.validate(MemoryStore(), {'action': 'post_linkedin', 'why': 'a post'})
    assert not ok and 'run_tool' in why and 'linkedin_post' in why
    assert proposals.validate(MemoryStore(), {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'Three lines.', 'why': 'a post'})[0]


def test_the_final_post_held_in_the_browser_stands_on_the_card_he_pressed_in_front_of_the_next_post():
    """His live app, 2026-11-23: three post cards (X, Reddit, LinkedIn); Post via the browser on X, the agent signed in and wrote the post, and the
    gate held its final Post for his press - queued behind Reddit and LinkedIn, so Reddit stood in front, the browser said nothing waited on him,
    and the agent ended on "I'll bring you the link". The held step is the pressed card's own next press: it stands with it, in front."""
    from taskuary import cardqueue, general, proposals, taskstate
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Post the stroller piece', 'Kind': 'general', 'Status': 'open'}, 'owner')
    post = lambda kind: s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': f'the agent proposes to post on {kind}',
                                      'DraftText': json.dumps({'action': 'run_tool', 'type': kind, 'text': 'Strollers then and now.'})})
    x, rd, li = post('x_post'), post('reddit_post'), post('linkedin_post')
    with mock.patch.object(general, 'to_agent', return_value='woke'): proposals.via_browser(s, x, '')
    held = proposals.queue(s, tid, {'action': 'browser_act', 'sid': 's1', 'args': ['click', '@e91'], 'site': 'x.example', 'what': 'Publish your post on X'})['reviewId']
    st = cardqueue.state(s, tid)
    assert st['live'] == [x, held], st
    assert rd in st['held'] and li in st['held'] and held not in cardqueue.held(s, tid)
    assert taskstate.needs_owner(None, taskstate.browser_acts(s, tid), 's1'), 'the browser shows the press that waits on him'
    # ...his press on Publish ran on the site: the X card is done, and only now does Reddit come forward
    s.decide_review(held, 'approved', None, 'owner')
    assert cardqueue.done(s, tid, 'Posted on x.example') == [x]
    assert cardqueue.state(s, tid)['live'] == [rd]


def test_a_handed_post_that_cannot_go_comes_back_for_his_press_or_is_dropped_and_the_line_moves_on():
    """Walk 7, 2026-11-23: Post via the browser on the X card; there was no X account to sign in with. withdraw_draft answered "nothing unsent",
    the Reddit card behind it waited for good, and the agent ended on "the earlier X step is blocking it". A handed act its agent cannot do is
    kept with why - the press ends failed, saying it, and the card stands again for his press (try again or Dismiss); one he drops is withdrawn."""
    from taskuary import agenttools, cardqueue, conversation, general, proposals, verdicts
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Post the tea picture', 'Kind': 'general', 'Status': 'open'}, 'owner')
    post = lambda kind: s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': f'the agent proposes to post on {kind}',
                                      'DraftText': json.dumps({'action': 'run_tool', 'type': kind, 'text': 'Rain, tea, a quiet Monday.'})})
    x, rd = post('x_post'), post('reddit_post')
    with mock.patch.object(general, 'to_agent', return_value='woke'): proposals.via_browser(s, x, 'Rain, tea, and a quiet Monday.')
    assert cardqueue.state(s, tid)['live'] == [x]
    refused = json.loads(agenttools.call(s, tid, 'keep_card', {'which': f'rv{x}'}, {}))
    assert not refused['ok'] and 'why' in refused['why'], 'kept without why: his card would not say what stopped it'
    # ...named as the screen fact names it, never by a number (walk 11)
    out = json.loads(agenttools.call(s, tid, 'keep_card', {'which': 'post on x_post', 'why': 'there is no X account to sign in with'}, {}))
    assert out['ok'] and 'rv' not in out['says'], out
    new = int(out['kept'][f'rv{x}'][2:]); old, n = s.get_review(x), s.get_review(new)
    assert conversation._card(old)['status'] == 'failed' and 'no X account' in old['ActError'], 'his press ends failed where he pressed it, saying why'
    assert n['Status'] == 'pending' and json.loads(n['DraftText'])['text'] == 'Rain, tea, and a quiet Monday.' and 'result' not in json.loads(n['DraftText'])
    assert cardqueue.in_flight(s, tid) is None and cardqueue.state(s, tid)['live'] == [rd], 'the line moves on: Reddit comes forward'
    assert new in cardqueue.held(s, tid), 'and X stands again, for his press, after it'
    # ...and one he drops while it is handed is withdrawn on his word, never "nothing unsent"
    with mock.patch.object(general, 'to_agent', return_value='woke'): proposals.via_browser(s, rd, '')
    w = verdicts.withdraw(s, tid, 'he skipped Reddit for now', 'agent', f'rv{rd}')
    assert w['ok'] and s.get_review(rd)['Status'] == 'closed_unsent' and cardqueue.in_flight(s, tid) is None, w
    assert cardqueue.state(s, tid)['live'] == [new]


def test_a_post_proposed_under_a_reordered_name_is_told_the_acts_there_are_and_then_stands_unconnected():
    """HIPAA walk 6, H6: run_tool items typed `post_linkedin`, `post_x`, `post_reddit` came back "there is no tool 'post_linkedin'" - the
    "did you mean" matched only a prefix - and the agent told the owner three times the posts were impossible. The refusal names every act a
    card sets up, by what it does, the nearest first, from the one table; the corrected one stands as its card with no network connected."""
    from taskuary.store import MemoryStore
    from taskuary.testing import Factory
    s = MemoryStore(); tid = Factory(s).task('Post the Q3 headline')
    for wrong, right in (('post_linkedin', 'linkedin_post'), ('post_x', 'x_post'), ('post_reddit', 'reddit_post')):
        ok, why = proposals.validate(s, {'action': 'run_tool', 'type': wrong, 'text': 'Q3 closed at 214.', 'why': 'the headline'})
        assert not ok and why.split('are: ')[1].startswith(f'{right} (Post to'), why
        assert 'propose again' in why and 'browser' in why, 'and the way on'
        assert proposals.queue(s, tid, {'action': 'run_tool', 'type': right, 'text': 'Q3 closed at 214.', 'why': 'the headline'}), right


def test_a_step_handed_to_him_on_a_page_is_on_his_screen_never_nothing_waits():
    """Walk 9, 2026-11-23: the agent handed him a robot check on a newsletter's page, his Approve on another card woke it, and its screen fact
    said "Nothing waits for his press" - the step it had handed him was lost. The one record of what he was asked says it."""
    from taskuary import cardqueue, workerstate as ws
    from taskuary.browserview import TURN_PREFIX
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Two newsletters', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'approved', 'Reason': 'sign up', 'DecidedAt': '2026-11-23 12:21:50',
                  'DraftText': json.dumps({'action': 'browser_act', 'what': 'Submit the sign-up on news.example'})})
    ws.record(s, tid, 'run1', 'working')
    ws.record(s, tid, 'run1', 'input_needed', request_id=f'{TURN_PREFIX}robot1', text="Your turn in the browser on news.example: tick the human check")
    said = cardqueue.screen(s, tid)
    assert 'tick the human check' in said and cardqueue.NOTHING not in said, said


def test_a_github_comment_posts_the_words_he_left_on_its_card():
    """The one card (the owner, 2026-11-24: "one generic white raised artifact with editable text"): a GitHub comment's box was read-only and
    Approve posted the agent's words as proposed. What he left in the box is what is posted; pressed off the card, it goes as filed."""
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Totals off in the export', 'Kind': 'general', 'Status': 'open'}, 'owner')
    rv = {'ReviewId': 0, 'TaskId': tid, 'Kind': 'action', 'DraftText': json.dumps({'action': 'comment_issue', 'body': 'Fixed.', 'why': 'he asked'})}
    with mock.patch.object(proposals, 'validate', return_value=(True, '')), mock.patch.object(proposals, 'linked', return_value=('northwind/ledger', 12)), \
         mock.patch('taskuary.ci._conn', return_value={'Secret': 'fixture-token'}), mock.patch('taskuary.github.comment_issue', return_value='https://github.example/c/1') as post:
        proposals.execute(s, rv, 'owner', 'Fixed in the totals branch - thanks Erin.')
        proposals.execute(s, rv, 'owner', None)
    assert [c.args[3] for c in post.call_args_list] == ['Fixed in the totals branch - thanks Erin.', 'Fixed.']


class ACardRunsWhatItShows(unittest.TestCase):
    """Red team F1: a run_tool card showed the agent's `text` while a hidden field ran at the press, and the cardless python_script
    executor - never an agent's - was reachable through propose. What runs is what the card shows, and that card as it was shown."""
    def setUp(self):
        self.tid = server.store.create_task({'Title': 'Post the Northwind week', 'Kind': 'general', 'Status': 'open'}, 'owner')

    def test_an_agents_python_script_is_refused(self):
        miss = []
        self.assertIsNone(proposals.queue(server.store, self.tid, {'action': 'run_tool', 'type': 'python_script', 'text': 'Tidy the folder',
                                                                   'script': 'import os; os.remove("x")'}, 'agent', refused=miss))
        self.assertIn('never an agent', miss[0])

    def test_a_field_its_card_does_not_draw_never_rides_on_it(self):
        # ...dropped where the card is raised (proposals.shown_only, 2026-11-25): the card stands, and what it runs is only what it draws
        miss = []
        got = proposals.queue(server.store, self.tid, {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'A good week.',
                                                      'script': 'print(1)', 'query': 'DROP TABLE x'}, 'agent', refused=miss)
        kept = json.loads(server.store.get_review(got['reviewId'])['DraftText'])
        self.assertEqual(miss, []); self.assertNotIn('script', kept); self.assertNotIn('query', kept)

    def test_a_card_changed_after_it_was_shown_never_runs(self):
        s, ran = server.store, []
        shown = {'action': 'run_tool', 'type': 'linkedin_post', 'text': 'A good week.'}
        rid = s.add_review({'TaskId': self.tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'post it', 'DraftText': json.dumps(shown)})
        s._exec('UPDATE review SET DraftText=? WHERE ReviewId=?', (json.dumps({**shown, 'text': 'Something else entirely.'}), rid))
        with mock.patch.dict(REGISTRY, {'linkedin_post': lambda cfg: ran.append(cfg) or ('posted', '')}):
            r = c.post(f'/api/reviews/{rid}/decide', headers=owner(), json={'verb': 'approve', 'shown': shown})
        self.assertTrue(r.json()['changed'], r.text); self.assertEqual(ran, [])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')

    def test_a_letter_whose_recipient_changed_after_it_was_shown_never_goes(self):
        """Red team round 4: an agent's second save of its email in the same turn rewrites the card in place (slots.draft) - its To swapped
        between the card on his screen and his Send, and the letter went to the address he never saw."""
        from taskuary import outbound
        s, sent = server.store, []
        rid = s.add_review({'TaskId': self.tid, 'Kind': 'email', 'Status': 'pending', 'Reason': 'the agent wrote this email', 'DraftText': 'The figures are attached.',
                            'Deliver': json.dumps({'channel': 'email', 'to': ['erin@northwind.example'], 'subject': 'Q3 figures'})})
        s.set_review_deliver(rid, json.dumps({'channel': 'email', 'to': ['taker@outsider.example'], 'subject': 'Q3 figures'}))
        with mock.patch.object(outbound, 'send_out', lambda *a, **k: sent.append(a) or {'ok': True}):
            r = c.post(f'/api/reviews/{rid}/decide', headers=owner(), json={'verb': 'approve', 'final_text': 'The figures are attached.',
                                                                           'shown': {'to': ['Erin@northwind.example']}})
        self.assertTrue(r.json()['changed'], r.text); self.assertEqual(sent, [])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertIsNone(proposals.unlike_shown(s.get_review(rid), {'to': ['taker@outsider.example']}, 'approve'), 'the card as it stands now goes')


class ARunOfHisReportIsAskedOnOneCard(unittest.TestCase):
    """The owner, 2026-11-25: "for security issues, wouldn't you ask the user to allow it?" - a task's agent asking to run one of his saved
    reports or routines was a flat 403. A run hands it nothing but the result, so it is one card; his press is his Run now."""
    def test_the_agent_asks_and_his_press_runs_it(self):
        s = server.store
        tid = s.create_task({'Title': 'Check the nightly export', 'Kind': 'general', 'Status': 'open'}, 'owner')
        sid = s.save_source({'Channel': 'report', 'Address': 'Nightly export', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Nightly export'})}, 'o')
        with mock.patch.object(server, '_rerun_report', return_value={'ok': True, 'title': 'Nightly export'}) as run:
            r = c.post(f'/api/reports/{sid}/rerun', headers=agent(tid))
            self.assertEqual(r.status_code, 202, r.text); run.assert_not_called()
            rv = s.get_review(r.json()['review'])
            self.assertIn('run "Nightly export" now', rv['Reason'])
            proposals.execute(s, rv, 'owner')
        run.assert_called_once_with(sid, by='owner')
        self.assertEqual(c.post(f'/api/reports/{sid}/rerun', headers=agent()).status_code, 403)       # ...on no task of its own: no card


class ACallOnAnotherProfilesAccountIsTheMoveCard(unittest.TestCase):
    """PROFILES (the owner, 2026-11-26): Alex Doyle works at Northwind and runs Harbor Bakery. A connection tagged to Harbor Bakery is
    used by a Harbor task's agent alone; a Northwind agent's call on it runs nothing and is never a flat no - one card, "Move this task
    to Harbor Bakery", whose press moves it. An untagged connection serves both, and with one profile there is no wall at all."""
    def setUp(self):
        from taskuary import workstreams as W
        s, self.W = server.store, W
        self.was = s.get_setting(W.KEY)
        W.save(s, [{'name': 'Northwind'}, {'name': 'Harbor Bakery'}])
        self.tid = s.create_task({'Title': 'Close the Northwind quarter', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.bakery = s.create_task({'Title': 'Order flour for Harbor Bakery', 'Kind': 'general', 'Status': 'open'}, 'owner')
        W.set_task(s, self.tid, 'northwind', 'owner'); W.set_task(s, self.bakery, 'harbor-bakery', 'owner')
        self.card = s.get_connector_by_type('linkedin')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Roles': 'tool'}, 'test')
        W.tag_account(s, 'harbor-bakery', connector_id=self.card['ConnectorId'])
        self.ran = []
        me = lambda cfg: self.ran.append(cfg) or {'rows': [{'name': 'Harbor Bakery'}], 'columns': ['name']}
        self.patch = mock.patch.dict(REGISTRY, {'linkedin_me': me, 'linkedin_post': lambda cfg: self.ran.append(cfg) or ('posted', 'urn:li:share:1')})
        self.patch.start()

    def tearDown(self):
        self.patch.stop()
        s = server.store
        self.W.tag_account(s, '', connector_id=self.card['ConnectorId'])
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0}, 'test')
        s.set_setting(self.W.KEY, self.was or '', 'test')

    def read(self, tid): return c.post('/api/tools/run', headers=agent(tid), json={'task_id': tid, 'type': 'linkedin_me'})

    def test_nothing_runs_one_card_goes_up_and_his_press_moves_the_task(self):
        s = server.store
        r = self.read(self.tid)
        self.assertEqual(r.status_code, 202, r.text)
        j = r.json()
        self.assertEqual(self.ran, [])                                   # the account was never called
        self.assertIn('Harbor Bakery', j['says']); self.assertIn('Northwind', j['says']); self.assertIn('nothing was run', j['says'])
        rv = s.get_review(j['review'])
        p = json.loads(rv['DraftText'])
        self.assertEqual((rv['TaskId'], rv['Status'], p['action'], p['profile']), (self.tid, 'pending', 'move_profile', 'harbor-bakery'))
        self.assertTrue(card.then_of(rv))                                # his press wakes the agent to make its call
        # ...a second call, and a write through the propose door, stand behind the same card: never a pile, never the account's own card
        self.assertEqual(self.read(self.tid).json()['review'], j['review'])
        w = c.post('/api/tools/run', headers=agent(self.tid), json={'task_id': self.tid, 'type': 'linkedin_post', 'text': 'Fresh loaves.'})
        self.assertEqual((w.status_code, w.json()['review']), (202, j['review']))
        self.assertEqual(self.ran, [])
        # ...his press is the move, and the same call then runs
        proposals.execute(s, rv, 'owner')
        self.assertEqual(s.get_task(self.tid)['Workstream'], 'harbor-bakery')
        self.assertTrue(self.read(self.tid).json()['ok']); self.assertEqual(len(self.ran), 1)

    def test_its_own_profiles_agent_an_untagged_account_and_the_owner_are_never_stopped(self):
        self.assertTrue(self.read(self.bakery).json()['ok'])             # Harbor's own task
        self.assertTrue(c.post('/api/tools/run', headers=owner(), json={'type': 'linkedin_me'}).json()['ok'])      # his own call is his
        self.W.tag_account(server.store, '', connector_id=self.card['ConnectorId'])
        self.assertTrue(self.read(self.tid).json()['ok'])                # untagged: every profile's
        self.assertEqual(len(self.ran), 3)

    def test_with_one_profile_there_is_no_wall(self):
        self.W.save(server.store, [{'name': 'Northwind'}])
        self.assertTrue(self.read(self.tid).json()['ok']); self.assertEqual(len(self.ran), 1)

    def test_no_agent_may_raise_the_move_itself(self):
        self.assertIn('move_profile', proposals.NOT_ASKED)
