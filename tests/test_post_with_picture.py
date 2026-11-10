"""A post is set up for the owner's one press, with its picture (the owner, 2026-11-05: "it's not showing the post and the image as a
linkedin post and asking me if i want to post it ... I have linkedin connected"). The agent proposes the post with a picture from its
task folder; nothing reaches LinkedIn until Approve; the press uploads the picture (initializeUpload, then the bytes), posts with it, and
the review keeps what went and where. The general agent is told the roads THIS owner has connected, from the store.
"""
import json, shutil, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, general, guard, linkedin, outputs, proposals, server, verdicts

c = TestClient(server.app)
SRV = config.load()['server']
PNG = b'\x89PNG\r\n\x1a\n' + b'\0' * 64


def agent(tid): return {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, tid)}


class LinkedIn:
    "LinkedIn's HTTP, stubbed: every call recorded, none leaves the machine."
    def __init__(self): self.calls = []
    def get(self, url, **kw):
        self.calls.append(('GET', url)); return mock.Mock(ok=True, json=lambda: {'sub': 'ALEX1', 'name': 'Alex Doyle'})
    def post(self, url, **kw):
        self.calls.append(('POST', url, kw.get('json')))
        if 'initializeUpload' in url:
            return mock.Mock(ok=True, json=lambda: {'value': {'uploadUrl': 'https://upload.linkedin.test/up/1', 'image': 'urn:li:image:C1'}})
        return mock.Mock(ok=True, headers={'x-restli-id': 'urn:li:share:42'}, json=lambda: {})
    def put(self, url, **kw):
        self.calls.append(('PUT', url, len(kw.get('data') or b''))); return mock.Mock(ok=True)


def stubbed(net): return mock.patch.multiple(linkedin.requests, get=net.get, post=net.post, put=net.put)


class TheExecutor(unittest.TestCase):
    def test_a_picture_is_uploaded_then_named_on_the_post(self):
        f = outputs.folder(9001); f.mkdir(parents=True, exist_ok=True); (f / 'gas.png').write_bytes(PNG)
        net = LinkedIn()
        with stubbed(net): out = linkedin.run_linkedin_post({'token': 't', 'text': 'Gas is up 4 cents.', 'image_path': str(f / 'gas.png')})
        kinds = [x[0] + (' init' if 'initializeUpload' in x[1] else '') for x in net.calls]
        self.assertEqual(kinds, ['GET', 'POST init', 'PUT', 'POST'])           # who, the upload address, the bytes, then the post
        self.assertEqual(net.calls[1][2]['initializeUploadRequest']['owner'], 'urn:li:person:ALEX1')
        self.assertEqual(net.calls[2][2], len(PNG))
        self.assertEqual(net.calls[3][2]['content'], {'media': {'id': 'urn:li:image:C1'}})
        self.assertEqual(out['rows'][0]['url'], 'https://www.linkedin.com/feed/update/urn:li:share:42')

    def test_no_picture_is_the_plain_post(self):
        net = LinkedIn()
        with stubbed(net): linkedin.run_linkedin_post({'token': 't', 'text': 'Hi', 'author': 'urn:li:person:a'})
        self.assertEqual(len(net.calls), 1); self.assertNotIn('content', net.calls[0][2])


class OnePress(unittest.TestCase):
    def setUp(self):
        s = server.store
        self.tid = s.create_task({'Title': 'A post about local gas prices', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.card = s.get_connector_by_type('linkedin')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Secret': 'tok',
                          'ConfigJson': json.dumps({'member_name': 'Alex Doyle'})}, 'linkedin')
        f = outputs.folder(self.tid); f.mkdir(parents=True, exist_ok=True); (f / 'gas-prices.png').write_bytes(PNG)

    def tearDown(self):
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0}, 'test')
        shutil.rmtree(outputs.folder(self.tid), ignore_errors=True)       # the home is shared: another test's task of this number would offer the picture

    def propose(self, **kw):
        return c.post('/api/agent/propose', headers=agent(self.tid), json={
            'task_id': self.tid, 'action': 'run_tool', 'type': 'linkedin_post', 'connector_id': self.card['ConnectorId'],
            'why': 'Alex asked for a post with a visual', **kw})

    def test_proposed_waits_then_posts_with_the_picture_on_approve(self):
        net = LinkedIn()
        with stubbed(net):
            r = self.propose(text='Gas rose 4 cents this week.', image='gas-prices.png', image_path='C:/Windows/win.ini')
            self.assertEqual(r.status_code, 200, r.text)
            self.assertEqual(net.calls, [])                                   # nothing reached LinkedIn before the press
            rv = server.store.get_review(r.json()['review'])
            self.assertNotIn('image_path', json.loads(rv['DraftText']))      # a path is Taskuary's to resolve, never the agent's
            got = c.get(f'/api/tasks/{self.tid}/assistant').json()
            post = next(p for p in got['cards'] if p['ReviewId'] == rv['ReviewId'])
            self.assertEqual((post['network'], post['as'], post['Status']), ('LinkedIn', 'Alex Doyle', 'pending'))
            out = verdicts.decide(server.store, rv, 'approve', 'Gas rose 4 cents this week - here is why.')
        self.assertTrue(out['ok'], out)
        sent = [x for x in net.calls if x[0] == 'POST' and x[1].endswith('/rest/posts')][0][2]
        self.assertEqual(sent['commentary'], 'Gas rose 4 cents this week - here is why.')      # the owner's edit is what went
        self.assertEqual(sent['content']['media']['id'], 'urn:li:image:C1')
        kept = json.loads(server.store.get_review(rv['ReviewId'])['FinalText'])
        self.assertEqual(kept['result']['url'], 'https://www.linkedin.com/feed/update/urn:li:share:42')

    def test_a_picture_named_by_its_full_path_is_kept_by_its_name(self):
        """A real turn named the picture by its full path; the card builds its address from the name in the folder."""
        r = self.propose(text='Hi', image=str(outputs.folder(self.tid) / 'gas-prices.png'))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(json.loads(server.store.get_review(r.json()['review'])['DraftText'])['image'], 'gas-prices.png')

    def test_a_home_named_by_its_short_form_still_carries_the_picture(self):
        """A home given as C:/Users/ABCDEF~1 (an 8.3 short name, as %TEMP% often is) resolves to the long name, and one side of the
        comparison was never resolved: every picture post crashed. The short form is real where the disk makes one, else stood in for by
        a path that resolves to somewhere spelled differently - the same mismatch."""
        home = config.home()
        short = home.parent / '_alias' / '..' / home.name                   # resolves to home, spelled otherwise
        try:
            import ctypes
            buf = ctypes.create_unicode_buffer(1024)
            if ctypes.windll.kernel32.GetShortPathNameW(str(home), buf, 1024) and buf.value != str(home): short = type(home)(buf.value)
        except (AttributeError, OSError): pass
        self.assertNotEqual(str(short), str(short.resolve()))
        with mock.patch.object(outputs.config, 'home', lambda: short):
            r = self.propose(text='Hi', image=str(home / 'scratch' / 'outputs' / outputs.task_ref(self.tid) / 'gas-prices.png'))
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(json.loads(server.store.get_review(r.json()['review'])['DraftText'])['image'], 'gas-prices.png')

    def test_a_tool_failure_comes_back_in_words(self):
        from taskuary import agenttools
        def run(name, a): raise ValueError("gas.png is not a file in your task folder - save the picture there first")
        out = agenttools.rpc({'id': 1, 'method': 'tools/call', 'params': {'name': 'propose', 'arguments': {}}}, run)['result']
        self.assertTrue(out['isError']); self.assertEqual(out['content'][0]['text'], 'gas.png is not a file in your task folder - save the picture there first')
        def boom(name, a): raise RuntimeError('database is locked')
        said = agenttools.rpc({'id': 1, 'method': 'tools/call', 'params': {'name': 'tick', 'arguments': {}}}, boom)['result']['content'][0]['text']
        self.assertNotIn('Error', said); self.assertNotIn('Traceback', said)
        def need(name, a): return a['item']
        said = agenttools.rpc({'id': 1, 'method': 'tools/call', 'params': {'name': 'tick', 'arguments': {}}}, need)['result']['content'][0]['text']
        self.assertEqual(said, 'tick needs `item` - call it again with it')

    def test_a_picture_outside_the_task_folder_is_refused(self):
        r = self.propose(text='Hi', image='../../secret.png')
        self.assertEqual(r.status_code, 422, r.text)

    def test_a_network_that_takes_no_picture_from_here_says_so(self):
        self.assertIn('no picture', proposals.picture_why(self.tid, {'type': 'bluesky_post', 'image': 'gas-prices.png'}))

    def test_the_prompt_names_the_connected_road(self):
        system, _ = general._prompt(server.store, self.tid)
        self.assertIn('NEXT STEPS - DO WHAT YOU CAN DO', system)
        self.assertIn(f"(connector_id {self.card['ConnectorId']}): linkedin_post", system)
        server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0}, 'test')
        self.assertNotIn('linkedin_post -', general.roads(server.store))     # off is not a road


if __name__ == '__main__':
    unittest.main()


def test_the_agent_keeps_going_when_a_way_fails_and_hands_the_page_over():
    """The owner, 2026-11-05: "did you update the agent to be more persistent to try to do things?" A failed tool is a reason to try
    the next way, changed, until the ways are used up or the next needs the owner; a payment's last press is the owner's on the page."""
    from taskuary import general
    from taskuary.store import MemoryStore
    said = general.action_line(MemoryStore())
    assert 'KEEP GOING WHEN A WAY FAILS' in said and 'same failing call unchanged more than twice' in said and 'one line per way you tried' in said
    assert 'hands the real page to the owner' in said and "owner's Approve" not in said
