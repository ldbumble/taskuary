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
    def info(self, tail=0): return {'sid': self.sid, 'taskId': self.task_id, 'alive': self.alive, 'agent': 'coding', 'label': 'coding'}


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


    def test_agent_steps_are_written_for_the_agent_and_the_machine_side_is_its_job(self):
        """Handed the human guide raw, the agent told the owner to run npm install. The card's Agent
        tab carries steps written for the agent, with {base}/{cid}/{hdr} filled in, and the standing
        rule makes the machine-side work the agent's whether or not such steps exist."""
        conn = {**_slack(), 'ConfigJson': '{}', 'HasSecret': False}
        p = aisetup.prompt(conn, SERVER, GUIDE, FIELDS, '', ['Run `npm install` yourself.', 'POST {base}/api/connectors/{cid}/test{hdr} and read ok.'])
        self.assertIn('STEPS FOR YOU (written for you, the agent', p)
        self.assertIn(f"2. POST http://127.0.0.1:7787/api/connectors/{conn['ConnectorId']}/test with header X-Taskuary-Token: tok-1 and read ok.", p)
        self.assertIn('OWNER GUIDE (what a person would do by hand - for reference', p); self.assertIn('1. Create a Slack app', p)
        self.assertIn('never hand the owner a command to run', p); self.assertIn("Taskuary's package folder on this machine is", p)
        q = aisetup.prompt(conn, SERVER, GUIDE, FIELDS, '')                        # no agent steps: the guide, under the same rule
        self.assertNotIn('STEPS FOR YOU', q); self.assertIn('doing the machine-side parts yourself', q); self.assertIn('never hand the owner a command', q)


def _setups(cid): return [t for t in server.store.list_tasks(active_only=True) if t.get('Kind') == 'setup' and t.get('Tags') == f'connector:{cid}']


class EndpointTests(unittest.TestCase):
    def setUp(self):
        terminal.SESSIONS.clear()
        for t in server.store.list_tasks(active_only=True):
            if t.get('Kind') == 'setup': server.store.delete_task(t['TaskId'])
        # the CLI is "here" unless a test says otherwise: whether claude is on THIS box's PATH is not what these pin
        self.found = mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']); self.found.start()
    def tearDown(self): self.found.stop(); terminal.SESSIONS.clear()

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
        self.assertEqual(agent, 'coding'); self.assertIn('1. Create a Slack app', seed); self.assertNotIn('Do NOT call the Taskuary API', seed)
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
        self.assertFalse(any(str(x.get('Body', '')).startswith('AGENT REPORT') for x in server.store.list_comments(r['taskId'])))

    def test_no_agent_is_said_not_500ed(self):
        cid = _slack()['ConnectorId']
        r = c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE, 'agent': 'nobody'})
        self.assertEqual(r.status_code, 422); self.assertIn('nobody', r.json()['detail'])
        self.assertEqual(c.post('/api/connectors/999999/ai-setup', json={'guide': GUIDE}).status_code, 422)

    def test_no_ai_app_here_makes_no_task_and_says_where_to_get_one(self):
        """A new install without any AI CLI: each press of the card's biggest button left one more
        empty "Set up Outlook mail" in progress and answered "command not found: claude" (B10).
        The CLI is resolved first now - nothing to hand the setup to, no task, and a sentence with
        a next step. The card asks the same question up front and can hide the button."""
        cid = _slack()['ConnectorId']
        self.found.stop()
        with mock.patch('taskuary.agents._resolve_cmd', side_effect=FileNotFoundError("'claude' not found on PATH - is the CLI installed?")), \
             mock.patch.object(terminal, 'open_session', side_effect=AssertionError('nothing to start')):
            for _ in range(2):
                r = c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE})
                self.assertEqual(r.status_code, 422)
                self.assertIn('AI CLI agents', r.json()['detail']); self.assertNotIn('PATH', r.json()['detail'])
            self.assertEqual(_setups(cid), [])
            g = c.get(f'/api/connectors/{cid}/ai-setup').json()
            self.assertEqual((g['session'], g['ready']), (None, False)); self.assertIn('AI CLI agents', g['why'])
        self.found.start()
        self.assertEqual(c.get(f'/api/connectors/{cid}/ai-setup').json()['ready'], True)

    def test_a_dead_session_s_task_is_reused_not_doubled(self):
        """The pane died (the CLI crashed, the app restarted): the task stayed in progress, and the
        next press made a second one beside it. clisetup reuses the open task (TQ-0726); so does this."""
        cid = _slack()['ConnectorId']
        n = iter(range(100))
        def fake_open(store, agent, tid, repo, cwd, rows, cols, actor, model, seed_fn=None):
            t = FakeTerm(f's{next(n)}', tid); terminal.SESSIONS[t.sid] = t; return t
        with mock.patch.object(terminal, 'open_session', side_effect=fake_open):
            a = c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE}).json()
            terminal.SESSIONS[a['sid']].alive = False
            b = c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE}).json()
        self.assertEqual(b['taskId'], a['taskId']); self.assertNotEqual(b['sid'], a['sid'])
        self.assertEqual(len(_setups(cid)), 1)

    def test_a_cli_that_will_not_start_leaves_no_task_behind(self):
        """Found is not always runnable - a shim whose target is gone fails in the spawn itself. The
        task this press made goes with it, and the owner reads what to do rather than the pty's words."""
        cid = _slack()['ConnectorId']
        with mock.patch.object(terminal, 'open_session', side_effect=FileNotFoundError('The command was not found or was not executable: claude')):
            for _ in range(2):
                r = c.post(f'/api/connectors/{cid}/ai-setup', json={'guide': GUIDE})
                self.assertEqual(r.status_code, 422); self.assertIn('AI CLI agents', r.json()['detail'])
        self.assertEqual(_setups(cid), [])
