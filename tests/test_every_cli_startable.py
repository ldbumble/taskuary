"""Every AI CLI on the machine can be started.

A CLI reaches the pickers only through a WORKER - a profile saying what it is for, bound to a
connection saying how to run it. The setup wizard writes those for whatever was installed the day it
ran and never again, so Devin and Copilot, installed later and detected by /api/cli/detect ever
since, appeared in no picker and could not be started at all (the owner, 2026-09-14: "any ai cli
agents should be possible to start no? isn't that the whole idea of it").

Coding is the profile, so a new CLI needs no new one: it gets a coding worker carrying CODER.md and
the repositories the other coding workers already know. What varies between `coder`, `codex` and
`devin` is which CLI runs the same job.
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
    def test_a_cli_installed_after_setup_becomes_a_worker_of_its_own(self):
        cfg, store = config_with('claude', 'codex'), MemoryStore()
        _, find = installed('claude', 'codex', 'devin')
        with find:
            made = cli_connections.adopt_installed(cfg, store)
        self.assertEqual(made, ['devin'])
        worker = cfg['agents']['devin']
        self.assertEqual((worker['kind'], worker['rules_doc'], worker['provider']), ('coding', 'coder', 'cli:devin'))
        # ...in the same checkouts as the workers that were already there
        self.assertEqual(worker['cwd_map'], {'acme/app': 'C:/work/app'})
        # ...and it can actually be run: the connection carries the flags clis.KNOWN names for it
        self.assertEqual(cfg['cli_connections']['devin']['cmd'], 'devin')
        self.assertIn('--permission-mode', cfg['cli_connections']['devin']['args'])
        # ...and it reached the store, which is what every picker reads
        row = store.get_agent('devin')
        self.assertEqual(row['Kind'], 'coding')
        self.assertEqual(json.loads(row['Config'])['cmd'], 'devin')

    def test_it_adds_nothing_twice(self):
        cfg, store = config_with('claude'), MemoryStore()
        _, find = installed('claude', 'devin')
        with find:
            self.assertEqual(cli_connections.adopt_installed(cfg, store), ['devin'])
            self.assertEqual(cli_connections.adopt_installed(cfg, store), [])

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
        self.assertEqual(cfg['agents']['devin']['provider'], 'cli:devin')              # but now usable


if __name__ == '__main__':
    unittest.main()
