"""The doorway opens itself once a day (the assistant-runs-the-app design, 2026-09-18): one line to the
assistant's own chat with what is waiting and the three scripts as numbered options - and a script named
in so many words runs with no model at all."""
import json, unittest
from datetime import datetime
from unittest import mock

from taskuary import remote_assistant as ra
import tests.test_appfacts as A


def _doors(*_a, **_k): return [{'channel': 'whatsapp', 'chat': '1555@s.whatsapp.net', 'connectorId': 7, 'label': 'WhatsApp', 'name': 'WhatsApp'}]


class MorningLineTests(unittest.TestCase):
    def setUp(self):
        self.s = A.store(); self.sent = []
        self.patches = [mock.patch.object(ra, 'doorways', _doors),
                        mock.patch.object(ra, 'send', lambda store, ch, chat, text, connector_id=None: (ra.remember_offered(store, ch, chat, text), self.sent.append((ch, chat, text))))]   # the real send remembers the numbers too
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()

    def _pile(self, n):
        return mock.patch('taskuary.funnel.pile', return_value={'items': [{'lane': 'approve'} if i == 0 else {'lane': 'fyi'} for i in range(n)]})   # approve = on you

    def test_one_line_a_day_with_the_three_scripts_numbered_and_set_up_always_there(self):
        with self._pile(7):
            self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 1)
            self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 12, 0)), 0)      # never twice in a day
        text = self.sent[0][2]
        # the desktop's opener, in words: the count, then who wants what (2026-09-23)
        self.assertIn('7 things. 1 is ready - you only approve, 6 you can skip.', text)
        self.assertIn('PEOPLE WANT · 1', text); self.assertIn('NOTHING TO DECIDE · 6', text)
        self.assertIn('1 · Walk me through my tasks', text); self.assertIn('2 · Set up Taskuary', text); self.assertIn('3 · Set up a report', text)
        # the numbers are remembered against the chat, so "2" is the words
        self.assertEqual(ra.resolve_index(self.s, 'whatsapp', '1555@s.whatsapp.net', '2'), ('Set up Taskuary', True))

    def test_quiet_when_the_pipe_is_empty_before_six_or_switched_off(self):
        with self._pile(0): self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
        with self._pile(3): self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 5, 30)), 0)
        self.s.set_setting('phone_morning_line', '0', 't')
        with self._pile(3): self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
        self.assertEqual(self.sent, [])

    def test_a_script_named_in_words_runs_with_no_model(self):
        self.assertIn('what is connected', ra.script_direct(self.s, 'Set up Taskuary'))
        self.assertIn('sentence', ra.script_direct(self.s, 'set up a report'))
        self.assertIsNone(ra.script_direct(self.s, 'what reports do we have'))


if __name__ == '__main__':
    unittest.main()
