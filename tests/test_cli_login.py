"""Signing a coding CLI in, in a pane Taskuary hosts: what it may start, who may press it, and
what the session is allowed to keep.

Nothing here starts a real CLI. `Term` is faked in every test that reaches one - a suite that
spawns claude is a suite that opens an OAuth flow on whoever's machine it runs on.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import aisetup, clilogin, guard, server

c = TestClient(server.app)


class TableTests(unittest.TestCase):
    """This starts a process and types into it. An open field would be 'run anything here'."""

    def test_the_menu_is_closed(self):
        for bad in ('rm -rf /', 'some-cli-nobody-vetted', '', 'aider'):
            with self.assertRaises(ValueError): clilogin.argv(bad)

    def test_every_row_is_keyed_by_the_recipe_name_not_the_binary(self):
        """`cursor-agent` is the binary; `cursor` is the recipe, and what the UI holds."""
        from taskuary import cliinstall
        self.assertIn('cursor', clilogin.RECIPES)
        self.assertNotIn('cursor-agent', clilogin.RECIPES)
        for name in clilogin.RECIPES: self.assertIn(name, cliinstall.RECIPES, name)

    def test_the_two_shapes_are_the_ones_the_clis_actually_have(self):
        self.assertEqual(clilogin.RECIPES['codex']['args'], ['login'])
        self.assertEqual(clilogin.RECIPES['cursor']['args'], ['login'])
        self.assertEqual(clilogin.RECIPES['claude']['type'], '/login')
        self.assertEqual(clilogin.RECIPES['copilot']['type'], '/login')
        # gemini opens Google's page on a plain run: nothing on argv, nothing typed
        self.assertEqual(clilogin.RECIPES['gemini'], {'args': [], 'type': ''})

    def test_a_sign_in_ends_the_way_a_setup_task_ends(self):
        """No report, no proposals, no reply draft - coder.wrap routes Kind='setup' to this."""
        self.assertEqual(clilogin.KIND, aisetup.KIND)
        self.assertIs(clilogin.finish, aisetup.finish)


class ArgvTests(unittest.TestCase):
    """The seam: a CLI installed a minute ago has no profile, and this server's PATH predates it."""

    def test_the_binary_is_found_never_assumed(self):
        with mock.patch('taskuary.cliinstall.find', return_value=r'C:\x\codex.exe'):
            self.assertEqual(clilogin.argv('codex'), [r'C:\x\codex.exe', 'login'])

    def test_a_cli_that_is_not_here_yet_says_so_instead_of_starting_nothing(self):
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            with self.assertRaises(ValueError) as e: clilogin.argv('claude')
        self.assertIn('install', str(e.exception).lower())


class FakeTerm:
    """A pane that never spawns anything. Records what it was asked to type."""

    def __init__(self, argv, cwd, label, task_id=None, agent=None, rows=32, cols=110, store=None):
        self.argv, self.cwd, self.label, self.task_id, self.agent = argv, cwd, label, task_id, agent
        self.sid, self.alive, self.keep_transcript, self.seeded = 'fake123', True, True, None

    def seed(self, text): self.seeded = text
    def info(self, tail=0, details=True): return {'sid': self.sid, 'alive': True, 'label': self.label}


class EndpointTests(unittest.TestCase):
    def setUp(self):
        from taskuary import terminal as term
        self.term = mock.patch('taskuary.terminal.Term', FakeTerm); self.term.start()
        self.find = mock.patch('taskuary.cliinstall.find', return_value='/x/claude'); self.find.start()
        self.addCleanup(self.term.stop); self.addCleanup(self.find.stop)
        self.addCleanup(lambda: term.SESSIONS.pop('fake123', None))

    def test_it_opens_a_setup_task_the_board_will_show(self):
        r = c.post('/api/cli/login', json={'name': 'claude'})
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()['taskId']
        task = server.store.get_task(tid)
        self.assertEqual(task['Kind'], 'setup')
        self.assertEqual(task['Status'], 'in_progress')
        self.assertIn('cli:claude', str(task['Tags']))
        self.assertIn('Claude Code', task['Title'])          # the label, not the bare recipe name

    def test_the_pane_keeps_no_transcript_and_types_the_login(self):
        from taskuary import terminal as term
        c.post('/api/cli/login', json={'name': 'claude'})
        t = term.SESSIONS['fake123']
        self.assertFalse(t.keep_transcript)                   # secrets are typed into this one
        self.assertEqual(t.seeded, '/login')
        self.assertIsNone(t.agent)                            # off the blackboard, off the roster

    def test_a_subcommand_cli_is_not_typed_into(self):
        from taskuary import terminal as term
        c.post('/api/cli/login', json={'name': 'codex'})
        self.assertIsNone(term.SESSIONS['fake123'].seeded)

    def test_a_second_press_reattaches_instead_of_starting_a_second_oauth(self):
        first = c.post('/api/cli/login', json={'name': 'claude'}).json()
        again = c.post('/api/cli/login', json={'name': 'claude'}).json()
        self.assertTrue(again['existing'])
        self.assertEqual(again['taskId'], first['taskId'])

    def test_an_unknown_cli_is_refused(self):
        self.assertEqual(c.post('/api/cli/login', json={'name': 'rm -rf /'}).status_code, 422)

    def test_a_cli_that_is_not_installed_is_refused(self):
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            self.assertEqual(c.post('/api/cli/login', json={'name': 'claude'}).status_code, 422)


class GuardTests(unittest.TestCase):
    def test_an_agent_may_not_start_an_oauth_flow(self):
        """An agent reads untrusted mail. Starting a sign-in on the owner's machine is theirs."""
        self.assertTrue(guard.denied('POST', '/api/cli/login'), 'POST /api/cli/login must be on guard.DENIED')

    def test_the_page_is_told_which_clis_can_be_signed_in(self):
        """A button is never drawn over a road that does not exist - `installable`'s own rule."""
        rows = c.get('/api/cli/detect').json()['data']
        self.assertTrue(rows)
        for row in rows:
            self.assertIn('login', row)
            if row['login']: self.assertIn(row['login'], clilogin.RECIPES)
