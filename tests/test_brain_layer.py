"""A brain is a thing of its own: which CLI runs the work, and on which gear.

Spec: docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md
"""
import json, unittest

from taskuary import agents as hub_agents, terminal
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
