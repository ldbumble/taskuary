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


class WalkTests(unittest.TestCase):
    """The owner, 2026-10-21: "it should look like general agent working, not code one, for AI setup". The button starts the
    GENERAL agent on a general task - no terminal, no repository - with the card's Guide as its brief and the card's tools as
    its hands, and its steps are drawn on the card. The brain here is a fake that answers in turn."""
    FIELDS = [['Client ID', 'client_id'], ['Client Secret', 'client_secret'], ['API version (optional)', 'version']]
    BODY = {'guide': ['Create an app at developer.linkedin.com/apps.', 'Paste its Client ID and Client Secret.'],
            'fields': FIELDS, 'secret_label': 'Access token'}

    def setUp(self):
        from taskuary import general, llm
        terminal.SESSIONS.clear(); aisetup.WALKS.clear()
        self.cid = server.store.get_connector_by_type('linkedin')['ConnectorId']
        server.store.save_connector({'ConnectorId': self.cid, 'ConfigJson': '{}', 'Secret': ''}, 'test')
        for t in server.store.list_tasks(active_only=True):
            if t.get('SourceRef') == aisetup.WALK_REF: server.store.update_task(t['TaskId'], {'Status': 'done'}, 'test')
        self.replies, self.seen = [], []
        def brain(system, user, **kw):
            self.seen.append((system, user)); return self.replies.pop(0) if self.replies else 'Waiting for you.'
        brain.takes_web = False
        fake = [{'id': 'connector:9999', 'pick': 'connector:9999', 'type': 'openai', 'label': 'Fake brain (API)', 'model': 'm', 'connector_id': 9999}]
        for p in (mock.patch.object(general, 'provider_options', return_value=fake),
                  mock.patch.object(llm, 'build_llm', return_value=brain),
                  mock.patch.object(aisetup, '_spawn', side_effect=lambda fn, store, cid, tid, *a: fn(store, cid, tid, *a)),
                  mock.patch.object(terminal, 'open_session', side_effect=AssertionError('a walk opens no terminal'))):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(terminal.SESSIONS.clear)

    # THE WALK IS THE CHAT'S NOW (2026-10-30): the card's door opens the Assistant, and a GET of the old road folds an open walk into the
    # conversation (aisetup.move_walk). What is left of the walk is read and driven here through the module, as the agent's own road
    def view(self): return {**aisetup.walk_view(server.store, self.cid), 'ready': not aisetup.ready_why(server.store)}
    def ctx(self): return {'guide': self.BODY['guide'], 'fields': self.BODY['fields'], 'secret_label': self.BODY['secret_label'], 'agent_steps': []}
    def start(self): return aisetup.start_walk(server.store, self.cid, self.ctx())
    def said(self, text='', saved=None): return aisetup.walk_said(server.store, self.cid, self.ctx(), text, saved)

    def test_the_button_starts_the_general_agent_and_its_step_is_on_the_card(self):
        from taskuary import general
        self.replies = ['This needs a LinkedIn app of yours, and its two keys.\n'
                        '[[TASKUARY-CARD-ASK: client_id]] Open developer.linkedin.com/apps, create an app, then paste its Client ID here.']
        r = self.start()
        tk = server.store.get_task(r['session']['taskId'])
        self.assertEqual((tk['Kind'], tk['SourceRef'], tk['Tags']), ('general', aisetup.WALK_REF, f'connector:{self.cid}'))
        sess = general.session_for(tk['TaskId'])
        self.assertEqual(getattr(sess, 'mode', ''), 'assistant')                     # the general agent's session, not a pty
        system, _user = self.seen[0]
        self.assertIn('CONNECTING A CARD', system); self.assertIn('1. Create an app at developer.linkedin.com/apps.', system)
        self.assertIn('Client ID (key client_id)', system); self.assertIn("THE CARD'S TOOLS", system)
        self.assertIn('set: nothing; empty: client_id, client_secret, version', system)
        self.assertNotIn('(what each is, and where it is on this machine', system)      # no repository map
        self.assertNotIn('[[TASKUARY-DONE]]', system); self.assertNotIn('REPLYING FOR THE OWNER', system)   # it owes nobody a reply
        v = self.view()
        self.assertTrue(v['ready'])
        self.assertEqual(v['ask'], {'field': 'client_id', 'label': 'Client ID',
                                    'text': 'Open developer.linkedin.com/apps, create an app, then paste its Client ID here.'})
        said = [s['text'] for s in v['steps'] if s['kind'] == 'agent'][-1]
        self.assertIn('paste its Client ID here', said); self.assertNotIn('TASKUARY-CARD', said)
        # pressed again: the same walk, not a second
        self.assertTrue(self.start()['existing'])

    def test_the_agent_saves_a_field_and_runs_test_and_the_card_shows_each(self):
        from taskuary import channels
        self.replies = ['I will set the version.\n[[TASKUARY-CARD-SAVE: version = 202609]]\n[[TASKUARY-CARD-TEST]]',
                        'LinkedIn is connected.\n[[TASKUARY-CARD-DONE]]']
        with mock.patch.object(channels, 'test_connector', return_value={'ok': True, 'detail': 'signed in as Alex Doyle'}) as tested:
            self.start()
        tested.assert_called_once_with(server.store, self.cid)
        self.assertEqual(json.loads(server.store.get_connector(self.cid)['ConfigJson'])['version'], '202609')
        self.assertIn("The card's Test passed: signed in as Alex Doyle", self.seen[1][1])        # the result went back to the agent
        v = self.view()
        done = [s['text'] for s in v['steps'] if s['kind'] == 'done']
        self.assertIn('Saved on the card: API version (optional)', done)
        self.assertIn('Test passed: signed in as Alex Doyle', done)
        self.assertTrue(v['done'])

    def test_the_agent_may_not_save_a_secret(self):
        self.replies = ['[[TASKUARY-CARD-SAVE: client_secret = abc]]\n[[TASKUARY-CARD-SAVE: Secret = tok]]']
        self.start()
        row = server.store.get_connector(self.cid, with_secret=True)
        self.assertNotIn('client_secret', json.loads(row['ConfigJson'])); self.assertFalse(row.get('Secret'))
        self.assertTrue(any(s['kind'] == 'failed' and 'yours to paste' in s['text'] for s in self.view()['steps']))

    def test_what_the_person_saves_or_says_on_the_card_is_the_agents_next_turn(self):
        self.replies = ['[[TASKUARY-CARD-ASK: client_id]] Paste the Client ID.', 'Thanks - now the secret.', 'It is on the Auth tab.']
        self.start()
        server.store.save_connector({'ConnectorId': self.cid, 'ConfigJson': json.dumps({'client_id': 'app-id'})}, 'test')
        self.said(saved=['Client ID'])
        self.assertIn('The person saved these on the card: Client ID', self.seen[1][1])
        self.assertIn('set: client_id; empty: client_secret, version', self.seen[1][0])          # the card's state, read fresh
        self.assertNotIn('app-id', self.seen[1][0])                                                # keys, never values
        self.said('where is the secret?')
        kinds = [(s['kind'], s['text']) for s in self.view()['steps']]
        self.assertIn(('done', 'You saved on the card: Client ID'), kinds)
        self.assertIn(('you', 'where is the secret?'), kinds)
        self.assertEqual(kinds[-1], ('agent', 'It is on the Auth tab.'))

    def test_no_brain_makes_no_task_and_says_where_to_get_one(self):
        from taskuary import general
        with mock.patch.object(general, 'provider_options', return_value=[]):
            with self.assertRaises(ValueError) as e: self.start()
            self.assertIn('AI CLI agents', str(e.exception))
            self.assertIsNone(aisetup.walk_task(server.store, self.cid))
            self.assertEqual(self.view()['ready'], False)

    def test_done_closes_the_walk_and_its_task_and_wrap_takes_the_same_road(self):
        from taskuary import general
        tid = self.start()['session']['taskId']
        self.assertEqual(c.post(f'/api/connectors/{self.cid}/ai-setup/done').json(), {'wrap': 'done', 'taskId': tid})
        self.assertEqual(server.store.get_task(tid)['Status'], 'done')
        self.assertIsNone(general.session_for(tid)); self.assertIsNone(self.view()['session'])
        r2 = self.start()
        self.assertEqual(c.post(f"/api/tasks/{r2['session']['taskId']}/wrap", json={}).json()['wrap'], 'done')

    def test_an_open_walk_moves_into_the_chat_as_one_record_and_its_task_closes(self):
        """The owner, 2026-10-30: the walk goes on in the Assistant now, with no Board task. One left open from before is folded into
        the conversation the next time the card is opened - "Earlier setup of X · N steps", its steps under it - and its task closes."""
        from taskuary import concierge, general
        self.replies = ['This needs a LinkedIn app.\n[[TASKUARY-CARD-ASK: client_id]] Paste its Client ID.']
        tid = self.start()['session']['taskId']
        v = c.get(f'/api/connectors/{self.cid}/ai-setup').json()
        self.assertTrue(v['moved']); self.assertIsNone(v['session'])
        self.assertRegex(v['earlier']['title'], r'^Earlier setup of .+ · \d+ steps?$')
        self.assertTrue(any('LinkedIn app' in s['summary'] for s in v['earlier']['steps']))
        self.assertEqual(server.store.get_task(tid)['Status'], 'done')
        self.assertTrue(any(aisetup.MOVED in str(x.get('Body')) for x in server.store.list_comments(tid)))
        rows = general.chat_rows(server.store, general.dock_task(server.store)[0]['TaskId'])
        self.assertTrue(any(str(r.get('Body') or '').startswith('Earlier setup of') for r in rows))      # said in the chat, kept there
        again = c.get(f'/api/connectors/{self.cid}/ai-setup').json()
        self.assertFalse(again.get('moved'))                                                          # once
        self.assertTrue(c.post(f'/api/connectors/{self.cid}/ai-setup', json=self.BODY).json()['moved'])   # the old road starts nothing
        self.assertIsNone(aisetup.walk_task(server.store, self.cid))
