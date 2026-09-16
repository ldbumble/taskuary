"""A brain is a thing of its own: which CLI runs the work, and on which gear.

Spec: docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md
"""
import json, unittest

from taskuary import agents as hub_agents, cli_connections as clic, terminal
from taskuary.store import MemoryStore


class CliNameTests(unittest.TestCase):
    def test_a_wrapper_is_not_the_cli(self):
        """copilot resolves to `cmd /c ...copilot.BAT` and qwen is launched through node.EXE, so
        argv[0] names the LAUNCHER. The card said `cmd` and `node`, and the task page's `by:` chip
        named the wrong product outright - `by: claude` over a Copilot session."""
        for cmd in ('copilot', 'qwen', 'claude', 'codex'):
            argv = terminal.agent_argv({'cmd': cmd})
            self.assertEqual(terminal.cli_named({'cmd': cmd}, argv), cmd,
                             f'{cmd} is what runs; argv[0] is {argv[0]!r}')

    def test_cli_of_still_reads_a_plain_argv(self):
        """The fallback for a bare shell, which has no profile to ask."""
        self.assertEqual(terminal.cli_of(['/usr/bin/claude', '-p']), 'claude')

    def test_no_profile_falls_back_to_argv(self):
        self.assertEqual(terminal.cli_named({}, ['/usr/bin/codex', 'exec']), 'codex')


class GearTests(unittest.TestCase):
    """`model_arg` (the FLAG) already lived on the connection; `model` and `light_model` (the
    VALUES) were stranded on the profile behind a patch that scrubbed them whenever the provider
    changed - whose own comment said "Model names belong to their provider"."""

    def cfg(self):
        return {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'opus', 'light_model': 'haiku'}},
                'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude'}}}

    def test_gears_belong_to_the_connection(self):
        self.assertEqual(clic.gears(self.cfg(), 'claude'), {'model': 'opus', 'light_model': 'haiku'})

    def test_resolving_a_profile_takes_the_connection_gears(self):
        c = self.cfg()
        got = clic.resolve(c, c['agents']['coder'])
        self.assertEqual((got['model'], got['light_model']), ('opus', 'haiku'))

    def test_one_brain_two_gears_is_still_one_brain(self):
        """The owner's rule: triage runs the main brain on a quicker model, and a CLI session
        always takes the main one. Not two providers."""
        c = self.cfg()
        self.assertEqual(clic.gears(c, 'claude'), {'model': 'opus', 'light_model': 'haiku'})

    def test_an_unknown_brain_has_no_gears_rather_than_raising(self):
        self.assertEqual(clic.gears(self.cfg(), 'nobody'), {'model': '', 'light_model': ''})

    def test_gears_already_on_a_profile_are_lifted_onto_its_connection(self):
        """Adding them to COMMAND_FIELDS makes resolve() DROP whatever the profile holds, so an
        install that already has a provider would silently lose the models the owner chose."""
        c = {'cli_connections': {'claude': {'cmd': 'claude'}},
             'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude', 'model': 'opus', 'light_model': 'haiku'}}}
        clic.migrate(c)
        self.assertEqual(clic.gears(c, 'claude'), {'model': 'opus', 'light_model': 'haiku'})
        self.assertNotIn('model', c['agents']['coder'])

    def test_a_connection_that_already_has_gears_is_not_overwritten(self):
        c = {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'mine'}},
             'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude', 'model': 'theirs'}}}
        clic.migrate(c)
        self.assertEqual(clic.gears(c, 'claude')['model'], 'mine')
