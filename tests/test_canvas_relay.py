"""The assistant relays both ways with the agent on screen (the canvas redesign, 2026-09-29): its context for a turn
about a task holds the agent's state AND what its screen last said, so "what is it doing?" is answered from the
screen - not from a status word."""
import unittest
from unittest import mock

from taskuary import concierge
from test_funnel import store


class RelayContextTests(unittest.TestCase):
    def test_a_turn_about_a_task_carries_the_agents_last_screen_lines(self):
        s = store()
        t = s.create_task({'Title': 'Fix the ledger export', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        live = [{'taskId': t, 'sid': 's1', 'agent': 'claude', 'idle': 3, 'waiting': False}]
        screen = ['> Editing jobs/export_ledger.py', 'Running tests/test_export.py', '12 passed']
        with mock.patch.object(concierge, '_live', return_value=live), \
             mock.patch('taskuary.terminal.asking_lines', return_value=screen) as lines:
            said = concierge.task_now(s, t)
        lines.assert_called_once_with('s1', 8)
        self.assertIn('is WORKING right now', said)
        self.assertIn("THE AGENT'S SCREEN, last lines:\n  > Editing jobs/export_ledger.py\n  Running tests/test_export.py\n  12 passed", said)

    def test_no_session_means_no_screen(self):
        s = store()
        t = s.create_task({'Title': 'Renew the domain', 'Kind': 'task', 'Status': 'open'}, 'owner')
        with mock.patch.object(concierge, '_live', return_value=[]):
            self.assertNotIn('SCREEN', concierge.task_now(s, t))
