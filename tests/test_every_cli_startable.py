"""Every AI CLI on the machine can be started.

A CLI reaches the pickers only through a WORKER - a profile saying what it is for, bound to a
connection saying how to run it. The setup wizard writes those for whatever was installed the day it
ran and never again, so Devin and Copilot, installed later and detected by /api/cli/detect ever
since, appeared in no picker and could not be started at all (the owner, 2026-09-14: "any ai cli
agents should be possible to start no? isn't that the whole idea of it").

A CLI is a BRAIN, not a worker named after one: adopting registers its CONNECTION and stops there,
and the picker offers brains directly. Minting a clone worker per CLI is what put `copilot` on
triage's menu and sent TQ-0588's coding work to it (the 2026-09-16 spec).
"""
import json
import unittest
from unittest import mock

from taskuary import cli_connections
from taskuary.store import MemoryStore


def config_with(*names):
    """A config as the wizard left it: a connection and a coding worker per CLI it found."""
    cfg = {'cli_connections': {}, 'agents': {}}
    for n in names:
        cfg['cli_connections'][n] = {'cmd': n, 'args': ['-p'], 'timeout': 1500}
        cfg['agents']['coder' if n == 'claude' else n] = {
            'kind': 'coding', 'rules_doc': 'coder', 'provider': f'cli:{n}',
            'purpose': 'Write, review and test code in a repository.',
            'cwd_map': {'acme/app': 'C:/work/app'}}
    return cfg


def installed(*names):
    """cliinstall.find's answer for this machine."""
    return mock.patch.object(cli_connections, 'adopt_installed', wraps=cli_connections.adopt_installed), \
        mock.patch('taskuary.cliinstall.find', side_effect=lambda n: f'/usr/bin/{n}' if n in names else '')


class AdoptTests(unittest.TestCase):
    def test_a_cli_installed_after_setup_becomes_a_brain_of_its_own(self):
        cfg, store = config_with('claude', 'codex'), MemoryStore()
        _, find = installed('claude', 'codex', 'devin')
        with find:
            made = cli_connections.adopt_installed(cfg, store)
        self.assertEqual(made, [])                       # no worker is invented for it
        self.assertNotIn('devin', cfg['agents'])
        # it can actually be run: the connection carries the flags clis.KNOWN names for it, and the
        # picker offers every configured connection as a brain
        self.assertEqual(cfg['cli_connections']['devin']['cmd'], 'devin')
        self.assertIn('--permission-mode', cfg['cli_connections']['devin']['args'])

    def test_it_adds_nothing_twice(self):
        cfg, store = config_with('claude'), MemoryStore()
        _, find = installed('claude', 'devin')
        with find:
            cli_connections.adopt_installed(cfg, store)
            before = dict(cfg['cli_connections'])
            cli_connections.adopt_installed(cfg, store)
        self.assertEqual(cfg['cli_connections'], before)

    def test_a_cli_that_is_not_installed_is_not_offered(self):
        cfg, store = config_with('claude'), MemoryStore()
        _, find = installed('claude')
        with find:
            self.assertEqual(cli_connections.adopt_installed(cfg, store), [])
        self.assertNotIn('devin', cfg['agents'])
        self.assertNotIn('gemini', cfg['cli_connections'])

    def test_a_cli_already_worked_by_a_differently_named_worker_gains_no_twin(self):
        """`coder` IS claude. Adopting must not file a second worker called claude beside it."""
        cfg, store = config_with('claude'), MemoryStore()
        _, find = installed('claude')
        with find:
            cli_connections.adopt_installed(cfg, store)
        self.assertEqual(sorted(cfg['agents']), ['coder'])

    def test_what_the_owner_configured_is_left_alone(self):
        cfg, store = config_with('claude'), MemoryStore()
        cfg['cli_connections']['devin'] = {'cmd': 'devin', 'args': ['--my-own-flag'], 'timeout': 60}
        _, find = installed('claude', 'devin')
        with find:
            cli_connections.adopt_installed(cfg, store)
        self.assertEqual(cfg['cli_connections']['devin']['args'], ['--my-own-flag'])   # not overwritten


if __name__ == '__main__':
    unittest.main()
