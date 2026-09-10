"""Setting a coding CLI up in a pane Taskuary hosts: what it may start, who may press it, and
what the session is allowed to keep.

Nothing here starts a real CLI. `Term` is faked in every test that reaches one - a suite that
spawns claude is a suite that runs an onboarding on whoever's machine it runs on.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import aisetup, clisetup, guard, server

c = TestClient(server.app)


class TableTests(unittest.TestCase):
    """This runs a program on the owner's machine. An open field would be 'run anything here'."""

    def test_the_menu_is_closed(self):
        for bad in ('rm -rf /', 'some-cli-nobody-vetted', '', 'aider'):
            with self.assertRaises(ValueError): clisetup.argv(bad)

    def test_every_name_is_the_recipe_not_the_binary(self):
        """`cursor-agent` is the binary; `cursor` is the recipe, and what the UI holds."""
        from taskuary import cliinstall
        self.assertIn('cursor', clisetup.SETUP)
        self.assertNotIn('cursor-agent', clisetup.SETUP)
        for name in clisetup.SETUP: self.assertIn(name, cliinstall.RECIPES, name)

    def test_it_starts_the_cli_and_nothing_else(self):
        """The CLI's own onboarding asks for the settings and the sign-in. Adding to that command
        line - or typing into the box - is us guessing at a conversation it has properly."""
        for name in clisetup.SETUP:
            with mock.patch('taskuary.cliinstall.find', return_value='/x/thing'):
                self.assertEqual(clisetup.argv(name), ['/x/thing'], name)

    def test_a_set_up_ends_the_way_a_setup_task_ends(self):
        """No report, no proposals, no reply draft - coder.wrap routes Kind='setup' to this."""
        self.assertEqual(clisetup.KIND, aisetup.KIND)
        self.assertIs(clisetup.finish, aisetup.finish)


class ArgvTests(unittest.TestCase):
    """The seam: a CLI installed a minute ago has no profile, and this server's PATH predates it."""

    def test_the_binary_is_found_never_assumed(self):
        with mock.patch('taskuary.cliinstall.find', return_value=r'C:\x\codex.exe'):
            self.assertEqual(clisetup.argv('codex'), [r'C:\x\codex.exe'])

    def test_a_cli_that_is_not_here_yet_says_so_instead_of_starting_nothing(self):
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            with self.assertRaises(ValueError) as e: clisetup.argv('claude')
        self.assertIn('install', str(e.exception).lower())


class FakeTerm:
    """A pane that never spawns anything. Records anything it was asked to type."""

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
        r = c.post('/api/cli/setup', json={'name': 'claude'})
        self.assertEqual(r.status_code, 200, r.text)
        tid = r.json()['taskId']
        task = server.store.get_task(tid)
        self.assertEqual(task['Kind'], 'setup')
        self.assertEqual(task['Status'], 'in_progress')
        self.assertIn('cli:claude', str(task['Tags']))
        self.assertIn('Claude Code', task['Title'])          # the label, not the bare recipe name

    def test_the_pane_keeps_no_transcript_and_nothing_is_typed_for_the_owner(self):
        from taskuary import terminal as term
        c.post('/api/cli/setup', json={'name': 'claude'})
        t = term.SESSIONS['fake123']
        self.assertFalse(t.keep_transcript)                   # an account and a token go in here
        self.assertIsNone(t.seeded)                           # the CLI runs its own onboarding
        self.assertIsNone(t.agent)                            # off the blackboard, off the roster
        self.assertEqual(t.argv, ['/x/claude'])

    def test_a_second_press_reattaches_instead_of_starting_a_second_one(self):
        first = c.post('/api/cli/setup', json={'name': 'claude'}).json()
        again = c.post('/api/cli/setup', json={'name': 'claude'}).json()
        self.assertTrue(again['existing'])
        self.assertEqual(again['taskId'], first['taskId'])

    def test_an_unknown_cli_is_refused(self):
        self.assertEqual(c.post('/api/cli/setup', json={'name': 'rm -rf /'}).status_code, 422)

    def test_a_cli_that_is_not_installed_is_refused(self):
        with mock.patch('taskuary.cliinstall.find', return_value=''):
            self.assertEqual(c.post('/api/cli/setup', json={'name': 'claude'}).status_code, 422)


class GuardTests(unittest.TestCase):
    def test_an_agent_may_not_start_one(self):
        """An agent reads untrusted mail. Running a CLI's setup on this machine is the owner's."""
        self.assertTrue(guard.denied('POST', '/api/cli/setup'), 'POST /api/cli/setup must be on guard.DENIED')

    def test_the_page_is_told_which_clis_can_be_set_up(self):
        """A button is never drawn over a road that does not exist - `installable`'s own rule."""
        rows = c.get('/api/cli/detect').json()['data']
        self.assertTrue(rows)
        for row in rows:
            self.assertIn('setup', row)
            if row['setup']: self.assertIn(row['setup'], clisetup.SETUP)


class SignedOutMessageTests(unittest.TestCase):
    """The sentence a failing run shows. It used to send the owner to a terminal."""

    def test_it_names_the_button_this_app_now_has(self):
        from taskuary import agents
        msg = agents.signed_out_msg('coder', 'not logged in', r'C:\n\claude.cmd')
        self.assertIn('Set it up', msg)
        self.assertNotIn('Open a terminal', msg)

    def test_a_profile_is_mapped_to_its_cli_not_read_as_one(self):
        """Every install ships a profile called `coder`; _LOGIN_HOW.get('coder') always missed."""
        from taskuary import agents
        self.assertIn('/login', agents.signed_out_msg('coder', 'x', r'C:\n\claude.cmd'))
        self.assertIn('codex login', agents.signed_out_msg('coder', 'x', '/usr/bin/codex'))

    def test_all_five_clis_have_a_terminal_sentence_too(self):
        """The pane is the road; a terminal is still a road, and the only one when the app is not
        the thing in front of you."""
        from taskuary import agents
        for name in clisetup.SETUP: self.assertIn(name, agents._LOGIN_HOW, name)

    def test_an_unknown_cli_still_gets_a_usable_sentence(self):
        from taskuary import agents
        self.assertIn('aider', agents.signed_out_msg('aider', 'x', '/usr/bin/aider'))
