"""First run in two steps on the assistant canvas (the owner, 2026-10-14: "Think about a idiot user who knows nothing about
nothing and he should setup this app in 2 steps ... it should never drop the user"). Each card does its whole step and
every answer says what happened and the one thing to press next."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agents, clis, firstrun, server
from taskuary.store import MemoryStore

ROW = {'name': 'codex', 'cmd': 'codex', 'args': ['exec'], 'label': 'OpenAI Codex CLI', 'installed': True, 'installable': True,
       'install': 'codex', 'setup': 'codex', 'why_not': ''}


def detect(**over): return mock.patch.object(clis, 'detect', return_value=[{**ROW, **over}])


class ChooseAiTests(unittest.TestCase):
    def setUp(self):
        self.s, self.cfg = MemoryStore(), {}
        self.p = [mock.patch('taskuary.config.save'), mock.patch('taskuary.cli_connections.sync'),
                  mock.patch.object(agents, 'cli_agent_options', return_value=[])]
        for p in self.p: p.start()

    def tearDown(self):
        for p in reversed(self.p): p.stop()

    def test_not_installed_says_so_and_offers_install(self):
        with detect(installed=False):
            out = firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertEqual((out['ok'], out['fix']), (False, 'install'))
        self.assertIn("ChatGPT isn't on this computer yet", out['why']); self.assertIn('Press Install', out['why'])

    def test_installed_but_silent_asks_for_the_sign_in_never_a_dead_end(self):
        with detect(), mock.patch.object(agents, 'run_cli', side_effect=RuntimeError('not logged in')):
            out = firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertEqual((out['ok'], out['fix']), (False, 'signin'))
        self.assertIn('needs you to sign in once', out['why']); self.assertIn('click the card again', out['why'])
        self.assertEqual(self.s.get_setting('triage_ai') or '', '', 'a brain that does not answer is never made the brain')

    def test_a_working_cli_is_connected_and_becomes_the_brain_in_one_click(self):
        with detect(), mock.patch.object(agents, 'run_cli', return_value=('ok', None, None)) as ran:
            out = firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertTrue(out['ok'], out)
        self.assertEqual(ran.call_args[0][0]['timeout'], firstrun.TEST_SECONDS, 'the test is bounded')
        self.assertIn('codex', self.cfg['cli_connections'])
        self.assertEqual(self.s.get_setting('triage_ai'), 'cli:codex')
        self.assertEqual(self.s.setting_writer('triage_ai'), 'owner', "the owner's own click, not an auto-pick")


class KeyAndMailTests(unittest.TestCase):
    def test_a_key_that_works_is_the_brain_and_one_that_does_not_is_switched_back_off(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('anthropic')['ConnectorId']
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': False, 'detail': '401 invalid key'}):
            bad = firstrun.choose_key(s, 'anthropic', 'sk-ant-wrong-key-123')
        self.assertFalse(bad['ok']); self.assertIn('401 invalid key', bad['why'])
        self.assertFalse(s.get_connector(cid)['Active'])
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': True, 'detail': 'ok'}):
            good = firstrun.choose_key(s, 'anthropic', 'sk-ant-right-key-456')
        self.assertTrue(good['ok']); self.assertEqual(s.get_setting('triage_ai'), f'connector:{cid}')
        self.assertTrue(s.get_connector(cid)['Active'])

    def test_gmail_is_switched_on_its_mailbox_read_and_the_owner_named_from_the_address(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('gmail')['ConnectorId']
        def claims(store, c):
            store.save_source({'Channel': 'email', 'Address': 'alex.doyle@gmail.example', 'ConnectorId': c, 'Active': 0}, 't')
            return {'ok': True, 'detail': 'logged in'}
        with mock.patch('taskuary.channels.test_connector', side_effect=claims):
            out = firstrun.connect_mail(s, 'gmail', 'alex.doyle@gmail.example', 'abcd efgh ijkl mnop')
        self.assertTrue(out['ok'], out)
        c = s.get_connector(cid, with_secret=True)
        self.assertTrue(c['Active']); self.assertEqual(c['Secret'], 'abcdefghijklmnop', "Google shows the App Password in fours")
        self.assertTrue(next(x for x in s.list_sources(active_only=False) if x['Address'] == 'alex.doyle@gmail.example')['Active'])
        self.assertEqual((s.owner()['owner'], s.owner()['owner_email']), ('Alex Doyle', 'alex.doyle@gmail.example'))

    def test_a_wrong_gmail_password_says_app_password_and_leaves_the_card_off(self):
        s = MemoryStore()
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': False, 'detail': 'AUTHENTICATIONFAILED'}):
            out = firstrun.connect_mail(s, 'gmail', 'alex@gmail.example', 'my-normal-password')
        self.assertFalse(out['ok']); self.assertIn('App Password, not your normal password', out['why'])
        self.assertFalse(s.get_connector_by_type('gmail')['Active'])
        self.assertIn('full email address', firstrun.connect_mail(s, 'gmail', 'alex', 'x')['why'])


class StateTests(unittest.TestCase):
    def test_step_one_is_a_choice_not_a_cli_that_happens_to_be_installed(self):
        s = MemoryStore()
        ready = {'ready': True, 'Name': 'claude (CLI)', 'pick': 'cli:coder', 'why': ''}
        with mock.patch('taskuary.setup._ai', return_value=ready), mock.patch('taskuary.setup._inbound', return_value=[]), \
             mock.patch('taskuary.setup._first_items', return_value=[]), detect(name='claude', cmd='claude', label='Claude Code'):
            self.assertEqual(firstrun.state(s)['step'], 'ai', 'installed is not chosen - it may never have signed in')
            s.set_setting('triage_ai', 'cli:coder', 'owner')
            st = firstrun.state(s)
        self.assertEqual(st['step'], 'email'); self.assertTrue(st['next'].startswith('Step 2 of 2: Claude is ready'))

    def test_an_install_already_sorting_mail_is_done_and_never_sees_setup_again(self):
        s = MemoryStore()
        with mock.patch('taskuary.setup._ai', return_value={'ready': True, 'Name': 'x', 'pick': ''}), \
             mock.patch('taskuary.setup._inbound', return_value=['Work mail']), \
             mock.patch('taskuary.setup._first_items', return_value=[{'MessageId': 1}]), detect():
            self.assertEqual(firstrun.state(s)['step'], 'done')

    def test_the_endpoints_are_the_owners_and_a_working_choice_judges_what_waited(self):
        s = MemoryStore()
        with mock.patch.object(server, 'store', s), mock.patch.object(server, 'brain_arrived') as arrived, \
             mock.patch('taskuary.firstrun.choose_cli', return_value={'ok': True, 'why': 'works'}):
            out = TestClient(server.app).post('/api/setup/first-run/ai', json={'name': 'codex'}).json()
        self.assertTrue(out['ok']); self.assertIn('step', out); arrived.assert_called_once()
        from taskuary import guard
        self.assertTrue(any('first-run' in pat for _, pat, _ in guard.DENIED))


if __name__ == '__main__':
    unittest.main()


class NodeFirstTests(unittest.TestCase):
    """Gemini only installs through npm: on a Windows machine with no Node it showed "not installed" with nothing to press.
    Node comes first, through winget in PowerShell, and a Node that will not install says what to do."""
    def test_no_node_installs_node_with_winget_then_the_cli(self):
        from taskuary import cliinstall
        ran, have = [], {'npm': ''}
        def run(cmd, timeout=900):
            ran.append(cmd)
            if cmd == cliinstall.NODE_WINGET: have['npm'] = 'C:/node/npm.cmd'
            return 0, 'ok'
        with mock.patch.object(cliinstall, 'WINDOWS', True), mock.patch.object(cliinstall, 'can_get_node', return_value=True), \
             mock.patch.object(cliinstall, 'npm', side_effect=lambda: have['npm']), \
             mock.patch.object(cliinstall, 'find', side_effect=lambda n: 'C:/node/gemini.cmd' if len(ran) > 1 else ''), \
             mock.patch.object(cliinstall, 'broken', return_value=''), mock.patch.object(cliinstall, 'ensure_on_path'):
            self.assertTrue(cliinstall.plan('gemini'), 'no Node is no longer "nothing to press"')
            out = cliinstall.install('gemini', runner=run)
        self.assertEqual(ran[0], cliinstall.NODE_WINGET)
        self.assertEqual(ran[1][1:4], ['install', '-g', '--include=optional'])
        self.assertEqual(out['phase'], 'done')

    def test_a_node_that_will_not_install_says_where_to_get_it(self):
        from taskuary import cliinstall
        with mock.patch.object(cliinstall, 'WINDOWS', True), mock.patch.object(cliinstall, 'can_get_node', return_value=True), \
             mock.patch.object(cliinstall, 'npm', return_value=''), mock.patch.object(cliinstall, 'ensure_on_path'):
            out = cliinstall.install('gemini', runner=lambda cmd, timeout=900: (1, 'No package found'))
        self.assertEqual(out['phase'], 'failed')
        self.assertIn('Install it from nodejs.org, then press Install again', out['detail'])
