"""First run as three questions on the assistant canvas - what AI, what email, any other connection (the owner, 2026-10-14: "Think about a idiot user who knows nothing about
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
        # the CLI's own "am I signed in?" is asked only when a check fails; never the real one in a test
        self.p = [mock.patch('taskuary.config.save'), mock.patch('taskuary.cli_connections.sync'),
                  mock.patch.object(agents, 'cli_agent_options', return_value=[]),
                  mock.patch('taskuary.clisetup.signed_in', return_value=False),
                  mock.patch.object(firstrun, '_prove', return_value='')]        # ProvenOnMailTests proves the proof
        for p in self.p: p.start()

    def tearDown(self):
        for p in reversed(self.p): p.stop()

    def test_not_installed_says_so_and_offers_install(self):
        with detect(installed=False):
            out = firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertEqual((out['ok'], out['fix']), (False, 'install'))
        self.assertIn("Codex isn't on this computer yet", out['why']); self.assertIn('Press Install', out['why'])

    def test_installed_but_silent_asks_for_the_sign_in_never_a_dead_end(self):
        with detect(), mock.patch.object(agents, 'run_cli', side_effect=RuntimeError('not logged in')):
            out = firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertEqual((out['ok'], out['fix']), (False, 'signin'))
        self.assertIn('needs you to sign in once', out['why']); self.assertIn('Press Sign in below', out['why'])
        self.assertEqual(self.s.get_setting('triage_ai') or '', '', 'a brain that does not answer is never made the brain')

    def test_signed_in_but_failing_never_sends_you_back_to_sign_in(self):
        """The sign-in said "Successfully logged in", the check failed for another reason, and the card asked to sign in again - a loop
        with no way out (the owner, 2026-10-15). The CLI says whether it is signed in; when it is, the real error is said and the moves
        are the ones that can fix it: update it, try again, or report it."""
        with detect(), mock.patch.object(agents, 'run_cli', side_effect=RuntimeError("error: unexpected argument '--flag' found")),              mock.patch('taskuary.clisetup.signed_in', return_value=True):
            out = firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertEqual((out['ok'], out['fix']), (False, 'update'))
        self.assertIn('signed in', out['why']); self.assertNotIn('sign in once', out['why'])
        fix = firstrun.state(self.s)['fix']
        self.assertEqual((fix['fix'], fix['install']), ('update', 'codex')); self.assertIn("unexpected argument '--flag'", fix['detail'])

    def test_a_failed_pick_is_still_said_after_a_reload_and_cleared_when_it_works(self):
        """The NEXT line went back to "pick your AI" after a failed pick, and a reload lost the Sign in button too."""
        with detect(), mock.patch.object(agents, 'run_cli', side_effect=RuntimeError('not logged in')):
            firstrun.choose_cli(self.s, self.cfg, 'codex')
            st = firstrun.state(self.s)                           # what a reload reads
        self.assertEqual((st['fix']['name'], st['fix']['fix'], st['fix']['setup']), ('codex', 'signin', 'codex'))
        self.assertIn('sign in', st['next'])
        with detect(), mock.patch.object(agents, 'run_cli', return_value=('ok', None, None)):
            firstrun.choose_cli(self.s, self.cfg, 'codex')
            self.assertIsNone(firstrun.state(self.s)['fix'])

    def test_a_pick_that_works_closes_the_sign_in_task_it_left(self):
        """Sign in opens the CLI on a "Set up" task; it stayed under On you after the AI worked."""
        from taskuary import clisetup
        tid = self.s.create_task({'Title': 'Set up codex', 'Kind': clisetup.KIND, 'Status': 'in_progress', 'Tags': clisetup.tag('codex')}, 'owner')
        with detect(), mock.patch.object(agents, 'run_cli', return_value=('ok', None, None)):
            firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertEqual(self.s.get_task(tid)['Status'], 'done')

    def test_a_working_cli_is_connected_and_becomes_the_brain_in_one_click(self):
        with detect(), mock.patch.object(agents, 'run_cli', return_value=('ok', None, None)) as ran:
            out = firstrun.choose_cli(self.s, self.cfg, 'codex')
        self.assertTrue(out['ok'], out)
        self.assertEqual(ran.call_args[0][0]['timeout'], firstrun.TEST_SECONDS, 'the test is bounded')
        self.assertIn('codex', self.cfg['cli_connections'])
        self.assertEqual(self.s.get_setting('triage_ai'), 'cli:codex')
        self.assertEqual(self.s.setting_writer('triage_ai'), 'owner', "the owner's own click, not an auto-pick")
        # ...and it is THE AI, not triage's alone: general tasks, the Assistant and coding sessions run on it too
        self.assertEqual([self.s.get_setting(k) for k in ('assistant_ai', 'concierge_ai', 'default_brain')], ['cli:codex', 'cli:codex', 'codex'])


class KeyAndMailTests(unittest.TestCase):
    def setUp(self): p = mock.patch.object(firstrun, '_prove', return_value=''); p.start(); self.addCleanup(p.stop)

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
        self.assertEqual(s.get_setting('assistant_ai'), f'connector:{cid}', 'the key runs general work too')
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

    def test_a_failure_that_already_says_what_to_check_is_said_once(self):
        s = MemoryStore()
        said = "The server's address could not be found. Check the host name for typos, and that this computer is online."
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': False, 'detail': said}):
            out = firstrun.connect_mail(s, 'imap', 'alex@northwind.example', 'pw', 'imap.northwind.invalid')
        self.assertNotIn('..', out['why']); self.assertEqual(out['why'].count('Check'), 1, out['why'])

    def test_any_ai_card_with_its_own_fields_can_be_the_brain(self):
        """More AI shows every Connections AI card; one with an endpoint (Azure) saves its fields with the key."""
        s = MemoryStore()
        cid = s.get_connector_by_type('azure_openai')['ConnectorId']
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': True, 'detail': 'ok'}):
            out = firstrun.choose_key(s, 'azure_openai', 'azure-key-1234567890', cid=cid, config={'endpoint': 'https://northwind.example'})
        self.assertTrue(out['ok'], out); self.assertEqual(s.get_setting('triage_ai'), f'connector:{cid}')
        self.assertEqual(json.loads(s.get_connector(cid)['ConfigJson'])['endpoint'], 'https://northwind.example')


class StateTests(unittest.TestCase):
    def test_step_one_is_a_choice_not_a_cli_that_happens_to_be_installed(self):
        s = MemoryStore()
        ready = {'ready': True, 'Name': 'claude (CLI)', 'pick': 'cli:claude', 'why': ''}
        with mock.patch('taskuary.setup._ai', return_value=ready), mock.patch('taskuary.setup._inbound', return_value=[]), \
             mock.patch('taskuary.setup._first_items', return_value=[]), detect(name='claude', cmd='claude', label='Claude Code'):
            self.assertEqual(firstrun.state(s)['step'], 'ai', 'installed is not chosen - it may never have signed in')
            s.set_setting('triage_ai', 'cli:claude', 'owner')
            st = firstrun.state(s)
        self.assertEqual(st['step'], 'email'); self.assertIn('What email do you have?', st['next']); self.assertIn('Claude is ready', st['next'])

    def test_step_two_names_the_ai_not_the_profile_that_runs_it(self):
        """A fresh install's brain was the coding profile on claude: step 2 said "<profile> is ready" (a fresh-home run, 2026-10-15).
        The pick names the tool now; the coding profile beside it is instructions and never the AI's name."""
        s = MemoryStore(); s.set_setting('triage_ai', 'cli:claude', 'owner')
        s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
        ready = {'ready': True, 'Name': 'claude (CLI)', 'pick': 'cli:claude', 'why': ''}
        with mock.patch('taskuary.setup._ai', return_value=ready), mock.patch('taskuary.setup._inbound', return_value=[]),              mock.patch('taskuary.setup._first_items', return_value=[]), detect(name='claude', cmd='claude', label='Claude Code'),              mock.patch.object(agents, 'cli_agent_options', return_value=[{'value': 'claude', 'cli': 'claude'}]):
            st = firstrun.state(s)
        self.assertEqual(st['brain']['name'], 'Claude'); self.assertNotIn('coding', st['next'])

    def test_each_step_is_a_plain_question(self):
        s = MemoryStore()
        def at(ready, inbound, items):
            with mock.patch('taskuary.setup._ai', return_value={'ready': ready, 'Name': 'x', 'pick': ''}),                  mock.patch('taskuary.setup._inbound', return_value=inbound), mock.patch('taskuary.setup._first_items', return_value=items), detect():
                return firstrun.state(s)
        self.assertIn('What AI do you have?', at(False, [], [])['next'])
        # what is next, in the words the rail and the top bar's chip say - one source for all three
        self.assertEqual(at(False, [], [])['todo'], 'pick your AI')
        done = at(True, ['Work mail'], [{'MessageId': 1}])
        self.assertIn('optional', done['next']); self.assertNotIn('Walk me through my tasks', done['next'])   # a button setup does not offer is not named (Advisor audit, 2026-10-15)
        self.assertEqual(done['todo'], '')
        s.set_setting('triage_ai', 'cli:codex', 'owner')
        self.assertEqual(at(True, [], [])['todo'], 'connect your email')
        self.assertEqual(at(True, ['Work mail'], [])['todo'], 'reading your mail')

    def test_the_top_bar_chip_says_what_is_next_from_the_same_state(self):
        s = MemoryStore()
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.firstrun.state', return_value={'step': 'email', 'todo': 'connect your email'}):
            out = TestClient(server.app).get('/api/setup').json()
        self.assertEqual((out['first_step'], out['first_todo'], out['first_left']), ('email', 'connect your email', 1))

    def test_no_report_asks_an_ai_nobody_picked_yet(self):
        """The shipped Advisor report ran at the first start on the signed-out claude a blank brain falls to, and the bell
        turned red over the question asking which AI (a fresh-home run, 2026-10-15)."""
        from taskuary import assistant
        s = MemoryStore()
        with mock.patch('taskuary.llm.build_llm') as built, mock.patch('taskuary.setup._first_items', return_value=[]):
            out = assistant._run(s, None, '', None, None)
        built.assert_not_called(); self.assertFalse(out.get('failed'), out)
        self.assertTrue(firstrun.unchosen(s))
        s.set_setting('triage_ai', 'cli:codex', 'owner')
        self.assertFalse(firstrun.unchosen(s))

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

class SignInTests(unittest.TestCase):
    """The sign-in opened the CLI plain, so Codex led with its own "Update available" menu and the sign-in was somewhere after it
    (the owner, 2026-10-15). Where the CLI has a login command, Sign in runs that and nothing else."""
    def argv(self, name, login):
        from taskuary import clisetup, cliinstall
        with mock.patch.object(cliinstall, 'find', return_value=f'/bin/{name}'), mock.patch.object(cliinstall, 'working', return_value=(f'/bin/{name}', '')):
            return clisetup.command(name, login)

    def test_sign_in_runs_the_login_command(self):
        self.assertEqual(self.argv('codex', True), ['/bin/codex', 'login'])
        self.assertEqual(self.argv('claude', True), ['/bin/claude', 'auth', 'login'])

    def test_a_cli_with_no_login_command_and_the_plain_set_up_open_it_plain(self):
        self.assertEqual(self.argv('gemini', True), ['/bin/gemini'])
        self.assertEqual(self.argv('codex', False), ['/bin/codex'])



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


class SignedInTests(unittest.TestCase):
    """Asked of the CLI itself (its exit code), never guessed from an error's words."""
    def run_status(self, name, code):
        from taskuary import clisetup, cliinstall
        done = mock.Mock(returncode=code)
        with mock.patch.object(cliinstall, 'find', return_value=f'/bin/{name}'), mock.patch.object(cliinstall, 'working', return_value=(f'/bin/{name}', '')), \
             mock.patch('subprocess.run', return_value=done) as ran:
            return clisetup.signed_in(name), ran

    def test_the_cli_answers_by_its_exit_code(self):
        ok, ran = self.run_status('codex', 0)
        self.assertIs(ok, True); self.assertEqual(ran.call_args[0][0], ['/bin/codex', 'login', 'status'])
        self.assertIs(self.run_status('claude', 1)[0], False)

    def test_a_cli_with_no_status_command_is_unknown(self):
        self.assertIsNone(self.run_status('gemini', 0)[0])


class ChatGptPlanTests(unittest.TestCase):
    """ChatGPT is a browser sign-in, not a CLI in a terminal (the owner, 2026-10-15: "for chatgpt regular why are you opening a
    terminal??? ... it's a regular oauth setup"). Signed in on its card, it is tested and made the AI everywhere in one call."""
    def setUp(self):
        p = mock.patch.object(firstrun, '_prove', return_value=''); p.start(); self.addCleanup(p.stop)
        self.s = MemoryStore()
        self.cid = self.s.get_connector_by_type('chatgpt')['ConnectorId']
        self.s.save_connector({'ConnectorId': self.cid, 'Secret': 'refresh-token', 'Active': 1}, 'test')

    def test_a_signed_in_plan_that_answers_becomes_the_ai_everywhere(self):
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': True}):
            out = firstrun.choose_connector(self.s, self.cid)
        self.assertTrue(out['ok'])
        for k in firstrun.BRAINS: self.assertEqual(self.s.get_setting(k), f'connector:{self.cid}')
        self.assertIsNone(firstrun.state(self.s)['fix'])

    def test_one_that_does_not_answer_says_what_it_said_and_survives_a_reload(self):
        self.s.set_setting('triage_ai', f'connector:{self.cid}', 'owner')      # what the sign-in itself adopts (server.chatgpt_poll)
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': False, 'detail': 'weekly cap reached'}):
            out = firstrun.choose_connector(self.s, self.cid)
        self.assertFalse(out['ok']); self.assertEqual(self.s.get_setting('triage_ai') or '', '')
        fix = firstrun.state(self.s)['fix']
        self.assertEqual((fix['key'], fix['fix'], fix['title']), (f'c{self.cid}', 'retry', 'ChatGPT'))
        self.assertIn('weekly cap reached', fix['detail']); self.assertIn('sign in again', fix['why']); self.assertNotIn("You're signed in", fix['why'])

    def test_codex_is_its_own_card_named_codex(self):
        self.assertEqual(firstrun.PLAIN['codex'][0], 'Codex')



class ProvenOnMailTests(unittest.TestCase):
    """A Vertex key passed its one-word Test, became the AI, and then sorted no mail - every email ⚠, setup spinning (the owner,
    2026-10-15: "if there is error timeout and say connect another one ... each cli tool or cloud tool or local tool should work by
    itself for assistant/triage/and agent"). An AI is the AI only once it has sorted one invented email the way triage will."""
    def setUp(self):
        self.s = MemoryStore(); self.cid = self.s.get_connector_by_type('chatgpt')['ConnectorId']
        self.s.save_connector({'ConnectorId': self.cid, 'Secret': 'refresh-token', 'Active': 1}, 'test')

    def pick(self, verdict=None, error=None, slow=0):
        import time
        def classify(msg, **kw):
            if slow: time.sleep(slow)
            if error: raise RuntimeError(error)
            return verdict
        with mock.patch('taskuary.channels.test_connector', return_value={'ok': True}), mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: ''), \
             mock.patch('taskuary.triage.classify_intent', side_effect=classify), mock.patch.object(firstrun, 'PROVE_SECONDS', 0.5):
            return firstrun.choose_connector(self.s, self.cid)

    def test_one_that_sorts_the_test_email_is_the_ai_for_triage_the_assistant_and_agents(self):
        out = self.pick(verdict={'intent': 'task', 'kind': 'task', 'title': 'Approve the invoice'})
        self.assertTrue(out['ok'])
        for k in firstrun.BRAINS: self.assertEqual(self.s.get_setting(k), f'connector:{self.cid}')

    def test_one_that_answers_but_cannot_sort_mail_is_not_the_ai_and_says_pick_another(self):
        out = self.pick(verdict={'intent': None, 'degraded': True, 'parse_error': 'RuntimeError: vertex_ai sent back no answer'})
        self.assertFalse(out['ok']); self.assertIn('pick another AI', out['why'])
        for k in firstrun.BRAINS: self.assertEqual(self.s.get_setting(k) or '', '')
        self.assertIn('sent back no answer', firstrun.state(self.s)['fix']['detail'])

    def test_one_that_hangs_is_cut_off_and_says_so(self):
        out = self.pick(verdict={'intent': 'fyi'}, slow=2)
        self.assertFalse(out['ok']); self.assertIn('too long', firstrun.state(self.s)['fix']['detail'])
        self.assertEqual(self.s.get_setting('triage_ai') or '', '')
