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


class OpenCardContextTests(unittest.TestCase):
    """A card browsed open in the canvas (a connector, a settings group, a report) is what "this" means in the next turn."""
    def test_the_open_card_rides_the_turn(self):
        s = store()
        seen = {}
        def llm(system, prompt, **kw):
            seen['prompt'] = prompt
            return 'It reads card spend once it is connected.'
        with mock.patch.object(concierge, '_live', return_value=[]):
            out = concierge.say(s, 'what does this one do?', llm=llm, open_card='the Spendly connector card (Connections - Finance), not connected')
        self.assertIn('ON SCREEN NOW: the Spendly connector card (Connections - Finance), not connected', seen['prompt'])
        self.assertTrue(out['say'])

    def test_a_page_with_nothing_opened_is_the_context_too(self):
        """Asked over the Connections wall with no card open, the turn went out with no context at all, and "which AI agent tool
        do I need for this thing to work" was answered about the app in general (the owner, 2026-10-01)."""
        s = store()
        seen = {}
        def llm(system, prompt, **kw):
            seen['prompt'] = prompt
            return 'For the agents section: an AI CLI agent.'
        page = 'the Connections page, AI - agents & models section - nothing opened on it yet'
        with mock.patch.object(concierge, '_live', return_value=[]):
            concierge.say(s, 'which ai agent tool do I need for this thing to work', llm=llm, open_card=page)
        self.assertIn(f"ON SCREEN NOW: {page} - 'this' and 'here' mean what is on screen", seen['prompt'])
        self.assertLess(seen['prompt'].index('ON SCREEN NOW'), seen['prompt'].index('The owner says:'), 'the screen first, then the words')

    def test_no_card_no_line(self):
        s = store()
        seen = {}
        def llm(system, prompt, **kw):
            seen['prompt'] = prompt
            return 'Hello.'
        with mock.patch.object(concierge, '_live', return_value=[]):
            concierge.say(s, 'hi', llm=llm)
        self.assertNotIn('ON SCREEN NOW', seen['prompt'])
