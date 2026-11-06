"""A GitHub "Create issue" card (the owner, 2026-11-06), the way a LinkedIn post is drawn: the agent sets up the repository, title, body
and labels; the card in that turn shows them with Create issue; nothing is filed until the owner presses it - on a trusted repository too,
since a new issue tells everyone watching it. Filed through the GitHub card's own API road (github.create_issue). GitHub's HTTP is stubbed.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, connectorcatalog as cat, general, github, guard, proposals, scopes, server
from taskuary.reports import REGISTRY, card_of, resolve_cfg

c = TestClient(server.app)
SRV = config.load()['server']
ISSUE = {'repo': 'northwind/portal', 'title': 'Login page warns about the certificate', 'body': 'Users see a certificate warning on login.',
         'labels': 'bug, login'}


def agent(tid): return {'X-Taskuary-Token': SRV['agent_token'], guard.TASK_HDR: guard.task_proof(SRV, tid)}


class GitHubNet:
    "GitHub's HTTP, stubbed: every call recorded, none leaves the machine."
    def __init__(self): self.calls = []
    def post(self, url, **kw):
        self.calls.append((url, kw.get('json'), kw.get('headers', {}).get('Authorization')))
        return mock.Mock(ok=True, status_code=201, json=lambda: {'number': 14, 'html_url': 'https://github.example/northwind/portal/issues/14'})


class TheCardIsDeclared(unittest.TestCase):
    def test_github_declares_create_issue_on_its_own_card_and_it_reaches_people(self):
        a = cat.action_for('github_issue')
        self.assertEqual((a['card'], a['press'], a['road']), ('github', 'Create issue', 'run_tool'))
        self.assertEqual([f['key'] for f in a['fields']], ['repo', 'title', 'labels', 'body'])
        self.assertEqual(cat.text_key(a), 'body')
        self.assertIn('github_issue', REGISTRY); self.assertEqual(card_of('github_issue'), 'github')
        self.assertIn('everyone watching the repository', scopes.REACHES['github_issue'])

    def test_a_new_issue_names_a_real_repository_and_a_title(self):
        self.assertEqual(github.issue_check(ISSUE), '')
        for bad in ({**ISSUE, 'repo': ''}, {**ISSUE, 'repo': 'portal'}, {**ISSUE, 'repo': '../../user'}, {**ISSUE, 'repo': 'northwind/..'},
                    {**ISSUE, 'title': '  '}):
            self.assertTrue(github.issue_check(bad), bad)
        self.assertEqual(github.issue_labels('bug, login,, '), ['bug', 'login'])
        self.assertEqual(github.issue_labels(['bug', ' ']), ['bug'])


class OnePress(unittest.TestCase):
    def setUp(self):
        s = server.store
        self.tid = s.create_task({'Title': 'File the certificate warning', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.card = s.get_connector_by_type('github')
        s.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 1, 'Secret': 'ghtok', 'Roles': 'tool'}, 'github')

    def tearDown(self): server.store.save_connector({'ConnectorId': self.card['ConnectorId'], 'Active': 0, 'ConfigJson': '{}'}, 'test')

    def test_the_card_shows_in_the_turn_nothing_is_filed_before_create_issue_and_the_owners_words_go(self):
        net = GitHubNet()
        with mock.patch.object(github.requests, 'post', net.post):
            r = c.post('/api/agent/propose', headers=agent(self.tid), json={'task_id': self.tid, 'action': 'run_tool', 'type': 'github_issue',
                                                                             'connector_id': self.card['ConnectorId'], 'why': 'Alex asked to file it', **ISSUE})
            self.assertEqual(r.status_code, 200, r.text)
            rv = server.store.get_review(r.json()['review'])
            self.assertEqual(json.loads(rv['DraftText'])['labels'], 'bug, login')
            card = next(x for x in c.get(f'/api/tasks/{self.tid}/assistant').json()['cards'] if x['ReviewId'] == rv['ReviewId'])
            self.assertEqual((card['network'], card['post']['repo'], card['post']['title']), ('GitHub', 'northwind/portal', ISSUE['title']))
            self.assertEqual(net.calls, [])                                             # nothing reached GitHub before the press
            r = c.post(f"/api/reviews/{rv['ReviewId']}/decide", json={'verb': 'approve', 'final_text': 'Users see a warning on login since Monday.'})
        self.assertTrue(r.json()['ok'], r.text)
        url, sent, auth = net.calls[0]
        self.assertTrue(url.endswith('/repos/northwind/portal/issues'))
        self.assertEqual(sent, {'title': ISSUE['title'], 'body': 'Users see a warning on login since Monday.', 'labels': ['bug', 'login']})
        self.assertEqual(auth, 'Bearer ghtok')                                          # the card's own token, never one the agent named
        kept = json.loads(server.store.get_review(rv['ReviewId'])['FinalText'])
        self.assertEqual(kept['result']['url'], 'https://github.example/northwind/portal/issues/14')

    def test_an_agents_direct_call_waits_for_the_press_even_on_a_full_card(self):
        net = GitHubNet()
        with mock.patch.object(github.requests, 'post', net.post):
            r = c.post('/api/tools/run', headers=agent(self.tid), json={'type': 'github_issue', 'task_id': self.tid, 'why': 'file it', **ISSUE})
        self.assertEqual(r.status_code, 202, r.text); self.assertTrue(r.json()['queued']); self.assertEqual(net.calls, [])

    def test_a_proposal_with_no_repository_is_refused_to_the_agent(self):
        r = c.post('/api/agent/propose', headers=agent(self.tid), json={'task_id': self.tid, 'action': 'run_tool', 'type': 'github_issue',
                                                                         'title': 'x', 'why': 'w'})
        self.assertEqual(r.status_code, 422, r.text); self.assertIn('repo', r.text)

    def test_the_connection_hands_the_token_and_nothing_else(self):
        cfg = resolve_cfg(server.store, {'type': 'github_issue', **ISSUE})
        self.assertEqual(cfg['token'], 'ghtok'); self.assertEqual(cfg['repo'], 'northwind/portal')

    def test_the_agent_is_told_the_road_and_what_it_takes(self):
        r = general.roads(server.store)
        self.assertIn('github_issue - opens an issue on GitHub', r)
        self.assertIn('it takes `repo`, `title`, `labels`, `body`', r)


if __name__ == '__main__':
    unittest.main()
