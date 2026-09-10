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
