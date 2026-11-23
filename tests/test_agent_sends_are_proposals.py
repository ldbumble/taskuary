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
    assert any('NOT done yet' in l and f'rv{li}' in l for l in said.splitlines()) and not any(l.startswith('- Done') for l in said.splitlines()), said
    assert cardqueue.state(s, tid)['live'] == [li] and x in cardqueue.held(s, tid), 'the next post waits until this one has gone'
    assert any(i['rid'] == li and 'not done yet' in i['line'] for i in card.lines(s, tid))
    # ...its own final press ran on the site: done, and the line moves on
    assert cardqueue.done(s, tid, 'Post on linkedin.example') == [li]
    assert not cardqueue.handed(s.get_review(li)) and cardqueue.state(s, tid)['live'] == [x]
    assert any(l.startswith('- Done') and f'rv{li}' in l for l in cardqueue.screen(s, tid).splitlines())


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
    held = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'held before it ran: Publish your post on X',
                         'DraftText': json.dumps({'action': 'browser_act', 'sid': 's1', 'args': ['click', '@e91'], 'site': 'x.example'})})
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
    out = json.loads(agenttools.call(s, tid, 'keep_card', {'which': f'rv{x}', 'why': 'there is no X account to sign in with'}, {}))
    assert out['ok'], out
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
