"""A first run that connected an AI and a mailbox and got no triage (a first-run log, 2026-10-14): the owner's only CLI was
Codex, its Test passed, and every mail still landed "awaiting triage (no AI connector)". adopt-brain wrote nothing because
no PROFILE runs codex (a fresh install's profiles all run claude), and a blank brain only ever looked for claude."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agents, llm, server
from taskuary.store import MemoryStore

CODEX = {'cmd': 'codex', 'args': ['exec']}


class CodexOnlyTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.p = [mock.patch.object(server, 'store', self.s),
                  mock.patch.object(agents, 'connection_brains', return_value=[('codex', CODEX)]),
                  mock.patch.object(agents, 'cli_agent_options', return_value=[]),          # no profile runs codex
                  mock.patch.object(agents, 'runs_here', side_effect=lambda prof: (prof or {}).get('cmd') == 'codex'),
                  mock.patch.object(server, 'brain_arrived')]
        for p in self.p: p.start()
        self.arrived = server.brain_arrived

    def tearDown(self):
        for p in reversed(self.p): p.stop()

    def test_a_passing_codex_test_makes_codex_the_triage_brain_and_judges_what_waited(self):
        out = TestClient(server.app).post('/api/setup/adopt-brain', json={'cli': 'codex'}).json()
        self.assertTrue(out['adopted'])
        self.assertEqual(self.s.get_setting('triage_ai'), 'cli:codex')
        self.arrived.assert_called_once()                                # the waiting mail is judged now, not in a day

    def test_a_blank_brain_finds_codex_when_claude_is_not_here(self):
        self.assertEqual(agents.default_pick.real(self.s), 'cli:codex')       # conftest stubs the default brain; this test is about it
        with mock.patch.object(agents, 'agent_row', return_value={'Name': 'codex', 'Config': json.dumps(CODEX)}),              mock.patch.object(agents, 'default_pick', agents.default_pick.real):
            self.assertTrue(llm.brain_status(self.s)['ready'])

    def test_a_brain_the_owner_picked_is_still_never_stomped(self):
        self.s.set_setting('triage_ai', 'connector:7', 'owner')
        out = TestClient(server.app).post('/api/setup/adopt-brain', json={'cli': 'codex'}).json()
        self.assertFalse(out['adopted'])
        self.assertEqual(self.s.get_setting('triage_ai'), 'connector:7')
        self.arrived.assert_not_called()


class SignInNamesTheOwnerTests(unittest.TestCase):
    """Signing in to the mailbox is the second (and last) step: it switches the mailbox on - even a source row left switched
    off - and names the owner from the account, so "Say who you are" is not a step of its own."""
    def test_the_microsoft_sign_in_turns_the_mailbox_on_and_names_the_owner(self):
        s = MemoryStore()
        cid = s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 0}, 't')
        s.save_source({'Channel': 'email', 'Address': 'alex@northwind.example', 'ConnectorId': cid, 'Active': 0}, 't')
        server._MSFLOWS['f1'] = {'cfg': {}, 'cid': cid, 'device_code': 'dc'}
        token = {'refresh_token': 'r', 'access_token': 'a', 'scope': 'Mail.Read offline_access'}
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.msauth.device_poll', return_value=token), \
             mock.patch('taskuary.msauth.me', return_value={'account': 'alex@northwind.example', 'name': 'Alex Doyle'}), \
             mock.patch.object(server, '_poll_reports'), mock.patch('taskuary.docsync.sync_connections'):
            out = TestClient(server.app).post(f'/api/connectors/{cid}/ms/poll', json={'flow': 'f1'}).json()
        self.assertEqual(out.get('status'), 'ok', out)
        src = next(x for x in s.list_sources(active_only=False) if x['Address'] == 'alex@northwind.example')
        self.assertEqual(src['Active'], 1, 'a source left switched off comes back on at sign-in')
        self.assertEqual((s.owner()['owner'], s.owner()['owner_email']), ('Alex Doyle', 'alex@northwind.example'))


if __name__ == '__main__':
    unittest.main()


class ChatGptSignInTests(unittest.TestCase):
    """The first-run log's other road: a ChatGPT sign-in that worked, then "Pick it as a brain under Settings" - the drop."""
    def test_a_chatgpt_sign_in_with_no_brain_chosen_becomes_the_brain_and_judges_what_waited(self):
        s = MemoryStore()
        cid = s.save_connector({'Type': 'chatgpt', 'Name': 'ChatGPT', 'Active': 0}, 't')
        t = {'client_id': 'c', 'host_id': 'h', 'email': 'alex@northwind.example', 'name': 'Alex Doyle', 'sub': 's', 'scope': 'x',
             'refresh_token': 'r'}
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_chatgpt_card', return_value=({}, {})), \
             mock.patch('taskuary.chatgptauth.poll', return_value=t), mock.patch.object(server, 'brain_arrived') as arrived:
            out = TestClient(server.app).post(f'/api/connectors/{cid}/chatgpt/poll', json={'flow': 'f'}).json()
            self.assertTrue(out['adopted']); self.assertEqual(s.get_setting('triage_ai'), f'connector:{cid}'); arrived.assert_called_once()
            s.set_setting('triage_ai', 'cli:claude', 'owner')
            again = TestClient(server.app).post(f'/api/connectors/{cid}/chatgpt/poll', json={'flow': 'f'}).json()
        self.assertFalse(again['adopted']); self.assertEqual(s.get_setting('triage_ai'), 'cli:claude', "the owner's choice stays")
