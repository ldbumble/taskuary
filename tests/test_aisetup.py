"""Get AI to set it up (aisetup.py + /api/connectors/{cid}/ai-setup): the card's guide becomes the
agent's prompt, in a live session on the card that is also a task on the Board."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import aisetup, server, terminal

c = TestClient(server.app)
SERVER = {'host': '127.0.0.1', 'port': 7787, 'token': 'tok-1'}
GUIDE = ['Create a Slack app (api.slack.com/apps) -> OAuth & Permissions.', 'Install it to the workspace and copy the bot token.']
FIELDS = [['workspace', 'team'], ['channel filter', 'channels']]


class FakeTerm:
    def __init__(self, sid, task_id): self.sid, self.task_id, self.alive, self.keep_transcript = sid, task_id, True, True
    def info(self, tail=0): return {'sid': self.sid, 'taskId': self.task_id, 'alive': self.alive, 'agent': 'coder', 'label': 'coder'}


def _slack(): return next(x for x in server.store.list_connectors() if x['Type'] == 'slack')


class PromptTests(unittest.TestCase):
    def test_the_prompt_is_the_guide_plus_how_to_save_and_the_rules_and_no_values(self):
        conn = {**_slack(), 'ConfigJson': json.dumps({'team': 'acme-secret-name', 'channels': ''}), 'HasSecret': False}
        p = aisetup.prompt(conn, SERVER, GUIDE, FIELDS, 'bot token')
        self.assertIn('1. Create a Slack app', p); self.assertIn('2. Install it', p)                 # the guide, in order
        self.assertIn(f"POST http://127.0.0.1:7787/api/connectors with header X-Taskuary-Token: tok-1", p)
        self.assertIn(f"/api/connectors/{conn['ConnectorId']}/test", p)
        self.assertIn('CURRENTLY SET: team. EMPTY: channels. Secret: not set.', p)
        self.assertNotIn('acme-secret-name', p)                                                       # keys, never values
        self.assertIn('never print it back', p); self.assertIn('one thing at a time', p); self.assertIn('SETUP DONE', p)
        self.assertNotIn('\n', p)                                                                     # one line: a newline submits in a TUI
        self.assertNotIn('X-Taskuary-Token', aisetup.prompt(conn, {'host': 'h', 'port': 1}, GUIDE, FIELDS, ''))   # no token configured: no header


class EndpointTests(unittest.TestCase):
    def setUp(self): terminal.SESSIONS.clear()
    def tearDown(self): terminal.SESSIONS.clear()

    def test_the_button_opens_a_session_on_a_setup_task_and_reattaches_to_it(self):
        cid = _slack()['ConnectorId']
        made = []
        def fake_open(store, agent, tid, repo, cwd, rows, cols, actor, model, seed_fn=None):
            t = FakeTerm('s1', tid); terminal.SESSIONS['s1'] = t; made.append((agent, cwd, seed_fn(cwd))); return t
        with mock.patch.object(terminal, 'open_session', side_effect=fake_open):
            r = c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE, 'fields': FIELDS, 'secret_label': 'bot token'}).json()
        self.assertEqual((r['sid'], r['existing']), ('s1', False))
        tk = server.store.get_task(r['taskId'])
        self.assertEqual((tk['Kind'], tk['Status'], tk['Tags']), ('setup', 'in_progress', f'connector:{cid}'))
        self.assertTrue(tk['Title'].startswith('Set up '))
        agent, cwd, seed = made[0]
        self.assertEqual(agent, 'coder'); self.assertIn('1. Create a Slack app', seed); self.assertNotIn('Do NOT call the Taskuary API', seed)
        self.assertFalse(terminal.SESSIONS['s1'].keep_transcript)                                    # tokens get typed here: no transcript filed
        # the card reloads: the same session comes back, and a second click does not start a second agent
        self.assertEqual(c.get(f'/api/connectors/{cid}/ai-setup').json()['session']['sid'], 's1')
        with mock.patch.object(terminal, 'open_session', side_effect=AssertionError('must not open a second one')):
            self.assertTrue(c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE}).json()['existing'])
        # Done on a setup task: close, mark done, no report / proposals / reply draft
        with mock.patch.object(terminal, 'close') as cl:
            self.assertEqual(c.post(f"/api/tasks/{r['taskId']}/wrap", json={}).json(), {'wrap': 'done', 'taskId': r['taskId']})
        cl.assert_called_once_with('s1')
        self.assertEqual(server.store.get_task(r['taskId'])['Status'], 'done')
        self.assertFalse(any(str(x.get('Body', '')).startswith('CODER REPORT') for x in server.store.list_comments(r['taskId'])))

    def test_no_agent_is_said_not_500ed(self):
        cid = _slack()['ConnectorId']
        r = c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE, 'agent': 'nobody'})
        self.assertEqual(r.status_code, 422); self.assertIn('nobody', r.json()['detail'])
        self.assertEqual(c.post('/api/connectors/999999/ai-setup', json={'guide': GUIDE}).status_code, 422)
