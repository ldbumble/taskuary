"""The bell (problems.py): what is failing, each with where to fix it - and quiet once it is not."""
import unittest
from taskuary import problems
from taskuary.store import MemoryStore


class Problems(unittest.TestCase):
    def test_a_failing_connector_shows_with_its_card_and_clears_on_a_clean_poll(self):
        s = MemoryStore()
        wa = next(c for c in s.list_connectors() if c['Type'] == 'whatsapp')
        s._exec('UPDATE connector SET Active=1 WHERE ConnectorId=?', (wa['ConnectorId'],))
        s.touch_connector(wa['ConnectorId'], 'the WhatsApp bridge is not running at http://127.0.0.1:8977')
        got = {p['key']: p for p in problems.collect(s)}
        self.assertIn('connector:whatsapp', got)
        self.assertEqual((got['connector:whatsapp']['where'], got['connector:whatsapp']['connector']), ('Connectors', 'whatsapp'))
        self.assertIn('bridge is not running', got['connector:whatsapp']['detail'])
        s.touch_connector(wa['ConnectorId'])                         # a clean poll: the bell goes quiet
        self.assertNotIn('connector:whatsapp', {p['key'] for p in problems.collect(s)})

    def test_an_inactive_connector_with_an_old_error_does_not_nag(self):
        s = MemoryStore()
        c = next(c for c in s.list_connectors() if c['Type'] == 'slack')
        s.touch_connector(c['ConnectorId'], 'invalid_auth')
        self.assertNotIn('connector:slack', {p['key'] for p in problems.collect(s)})

    def test_the_triage_brain_down_is_a_problem(self):
        s = MemoryStore()
        s.set_setting('triage_last_error', 'azure_openai: 401 Unauthorized', 'system')
        s.set_setting('triage_ai', 'connector:azure_openai', 'owner')
        got = {p['key']: p for p in problems.collect(s)}
        self.assertEqual(got['triage']['connector'], 'azure_openai')
