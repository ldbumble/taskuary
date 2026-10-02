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
        self.s.set_setting('phone_morning_line', '1', 't')      # off unless turned on (2026-10-02)
        self.patches = [mock.patch.object(ra, 'doorways', _doors),
                        mock.patch.object(ra, 'send', lambda store, ch, chat, text, connector_id=None: (ra.remember_offered(store, ch, chat, text), self.sent.append((ch, chat, text))))]   # the real send remembers the numbers too
        for p in self.patches: p.start()
    def tearDown(self):
        for p in self.patches: p.stop()

    def _pile(self, n):
        return mock.patch('taskuary.funnel.pile', return_value={'items': [{'lane': 'approve'} if i == 0 else {'lane': 'fyi'} for i in range(n)]})   # approve = on you

    def test_nothing_goes_out_unless_the_owner_turned_it_on(self):
        # the owner, 2026-10-02: "it should not be sending to whatsapp anything unless the user asks the assistant a question"
        self.s.set_setting('phone_morning_line', '', 't')
        with self._pile(7): self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
        self.assertEqual(self.sent, [])

    def test_one_line_a_day_with_the_three_scripts_numbered_and_set_up_always_there(self):
        with self._pile(7):
            self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 1)
            self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 12, 0)), 0)      # never twice in a day
        text = self.sent[0][2]
        # the desktop's opener, in words: the count, then who wants what (2026-09-23)
        self.assertIn('7 things: 1 on you, 6 FYI.', text)     # the rail's own bands (2026-10-02)
        self.assertIn('ON YOU · 1', text); self.assertIn('FYI · 6', text)
        self.assertIn('1 · Walk me through my tasks', text); self.assertIn('2 · Set up Taskuary', text); self.assertIn('3 · Set up a report', text)
        # the numbers are remembered against the chat, so "2" is the words
        self.assertEqual(ra.resolve_index(self.s, 'whatsapp', '1555@s.whatsapp.net', '2'), ('Set up Taskuary', True))

    def test_quiet_when_the_pipe_is_empty_before_six_or_switched_off(self):
        with self._pile(0): self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
        with self._pile(3): self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 5, 30)), 0)
        self.s.set_setting('phone_morning_line', '0', 't')
        with self._pile(3): self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
        self.assertEqual(self.sent, [])

    def test_its_options_are_pills_and_the_words_are_the_models(self):
        """A number (or a poll tap) runs the script with no model; typed, "set up" is words like any other (2026-09-25:
        "No hard coded anything... Only if you type 1 or hit poll that's clicking a pill")."""
        self.assertFalse(hasattr(ra, 'script_direct'))
        self.assertIn('what is connected', ra.run_act(self.s, {'t': 'script', 'script': 'set up Taskuary'}, None))
        self.assertIn('sentence', ra.run_act(self.s, {'t': 'script', 'script': 'set up a report'}, None))
        # ...and the sidebar's browse picks after them (the canvas redesign, 2026-09-29; Reports and Hub 2026-09-30)
        self.assertEqual([t for t, _ in ra.SCRIPT_LINES], ['Walk me through my tasks', 'Set up Taskuary', 'Set up a report', 'Connections', 'Reports', 'Hub', 'Settings'])


class NeverIntoAConversationTests(unittest.TestCase):
    setUp, tearDown, _pile = MorningLineTests.setUp, MorningLineTests.tearDown, MorningLineTests._pile
    """2026-09-29: the day's opener landed a minute after a failed Close out, mid-walk, and replaced the card's numbered
    list with its own - the owner's next pick restarted the walk. It waits for a gap, never follows a conversation that
    already happened today, and is recorded where the desk and the model can see it."""
    CHAT = '1555@s.whatsapp.net'

    def test_a_word_in_the_last_minutes_holds_it_until_the_next_pass(self):
        ra.talked(self.s, 'whatsapp', self.CHAT)
        with self._pile(3):
            self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
            with mock.patch.object(ra, 'QUIET', 0.0):
                self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 5)), 1)

    def test_the_owner_already_talking_today_spends_it(self):
        ra.spend_morning(self.s, datetime(2026, 9, 18, 7, 12))            # what a question to the chat does (respond)
        with self._pile(3), mock.patch.object(ra, 'QUIET', 0.0):
            self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
        self.assertEqual(self.sent, [])

    def test_a_walk_handed_to_the_chat_is_its_own_opener(self):
        with self._pile(3), mock.patch.object(ra, 'QUIET', 0.0), mock.patch.object(ra, 'handoff', return_value={'channel': 'whatsapp'}):
            self.assertEqual(ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0)), 0)
        self.assertEqual(self.sent, [])

    def test_what_went_out_is_in_the_conversation_but_not_on_the_desktop(self):
        # the owner, 2026-09-30: the day's summary is for the phone - the desktop's own welcome already shows it
        from taskuary import concierge, general
        with self._pile(3), mock.patch.object(ra, 'QUIET', 0.0):
            ra.morning_line(self.s, now=datetime(2026, 9, 18, 8, 0))
        tid = general.dock_task(self.s)[0]['TaskId']
        said = lambda ts: any(t.startswith('Good morning.') and 'ON YOU' in t for t in ts)
        self.assertFalse(said(h['text'] for h in concierge.history(self.s, tid)))             # what the desktop draws
        self.assertTrue(said(c['Body'] for c in general.chat_rows(self.s, tid)))              # what the model and the desk read


class TheWalkOpensWithTheDayTests(unittest.TestCase):
    """The owner, 2026-09-29: "when you hit walk me through on whatsapp that should trigger the morning summary"."""
    def test_walk_me_through_opens_with_the_same_breath_as_the_morning_line_meetings_included(self):
        s = A.store()
        items = [{'lane': 'approve'}, {'lane': 'fyi'}]
        with mock.patch('taskuary.funnel.pile', return_value={'items': items}), \
             mock.patch.object(ra, 'meetings_line', return_value="TODAY'S MEETINGS · 1\n· 10:00-10:30 Budget review"), \
             mock.patch('taskuary.concierge.resume', return_value={'say': 'Nothing is on the table.', 'item': None}):
            text = ra.walk(s)
        self.assertIn("TODAY'S MEETINGS · 1", text); self.assertIn('ON YOU · 1', text)
        self.assertEqual(str(s.get_settings().get(ra.MORNING_AT) or ''), datetime.now().strftime('%Y-%m-%d'))   # not said twice today


if __name__ == '__main__':
    unittest.main()
