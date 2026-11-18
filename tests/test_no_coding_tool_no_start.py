"""NO CODING TOOL CHOSEN, NO START (owner-approved, 2026-10-21, the UI/UX audit's R3).

On a fresh install with no coding tool connected, Send to coding agent found a tool on the computer by itself and started it with
its permission checks off, in a folder nobody named. Every road that starts a coding agent comes through terminal.start_on_task -
a press, a queue drain, a workflow - so it refuses there, before anything opens, and says what to do."""
import unittest
from unittest import mock

from taskuary import agents, failures, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class NoCodingTool(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the export', kind='coding')

    def test_with_no_coding_tool_nothing_opens(self):
        with mock.patch.object(agents, 'coding_ready', return_value=False), \
             mock.patch.object(terminal, 'open_session') as opened, self.assertRaises(ValueError) as e:
            terminal.start_on_task(self.s, self.tid, 'coding')
        self.assertEqual(str(e.exception), terminal.NO_CODING_TOOL)
        opened.assert_not_called()

    def test_a_named_brain_does_not_get_round_it(self):
        with mock.patch.object(agents, 'coding_ready', return_value=False), \
             mock.patch.object(terminal, 'open_session') as opened, self.assertRaises(ValueError):
            terminal.start_on_task(self.s, self.tid, 'coding', brain='claude')
        opened.assert_not_called()

    def test_the_refusal_names_its_fix(self):
        c = failures.classify(ValueError(terminal.NO_CODING_TOOL))
        self.assertEqual(c['fix']['label'], 'Connect a coding tool')

    def test_coding_ready_is_a_connected_tool_that_runs_here(self):
        with mock.patch.object(agents, 'connection_brains', return_value=[]):
            self.assertFalse(agents.coding_ready.real(self.s))


class TheLineNamesTheCheckThatRefused(unittest.TestCase):
    """The walks, 2026-11-18: "No coding tool is connected ... connect one under Connections" over a Codex that Connections showed connected -
    the start was refused by Developer mode. With it off a coding job is a general agent's, as at the dispatch door (concierge.handoff_task):
    nothing refuses it. In Developer mode with no command-line AI the line says that, and its button connects one (agents.no_coding_fix)."""
    def test_developer_mode_off_refuses_nothing_and_a_missing_cli_names_itself(self):
        from taskuary import concierge
        s = MemoryStore()
        real = mock.patch.multiple(agents, coding_ready=agents.coding_ready.real, developer_mode=agents.developer_mode.real)
        real.start(); self.addCleanup(real.stop)
        with mock.patch('taskuary.capabilities.has_ai', return_value=True):
            with mock.patch.object(agents, 'cli_ready', return_value=False):
                self.assertEqual(concierge.start_refusal(s, 'coding'), '')                    # Developer mode off: a general agent's job
                s.set_setting(agents.DEV_MODE, '1', 'owner')
                said = concierge.start_refusal(s, 'coding')
                self.assertTrue(said.startswith('No command-line AI (Claude Code, Codex) is connected'), said)
                self.assertEqual(concierge.no_start_chip(s, 'coding')['label'], 'Connect a coding tool')
            with mock.patch.object(agents, 'cli_ready', return_value=True): self.assertEqual(concierge.start_refusal(s, 'coding'), '')


if __name__ == '__main__': unittest.main()
