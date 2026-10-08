"""The opening screen's two lines (since.py): what happened since six last evening, and what was learned this week -
counted from the store, said only when there is something to say."""
import unittest
from datetime import datetime
from taskuary import since
from taskuary.store import MemoryStore

NOW = datetime(2026, 10, 7, 9, 0)


class SinceTests(unittest.TestCase):
    def test_overnight_counts_what_happened_after_six_last_evening_and_nothing_before(self):
        s = MemoryStore()
        for at, ch in (('2026-10-06 19:00:00', 'email'), ('2026-10-07 07:00:00', 'teams'), ('2026-10-06 17:00:00', 'email'),
                       ('2026-10-07 06:00:00', 'report')):
            mid = s.add_message({'ExternalId': f'x{at}{ch}', 'Channel': ch, 'Subject': 's', 'BodyText': 'b'})
            s._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (at, mid))
        out = since.overnight(s, NOW)
        self.assertEqual((out['mail'], out['reports']), (2, 1))                     # 17:00 was the day before
        self.assertEqual(out['line'], 'Since last night: 2 messages read, 1 report ran.')

    def test_a_quiet_night_says_nothing(self):
        self.assertEqual(since.overnight(MemoryStore(), NOW)['line'], '')
        self.assertEqual(since.learned(MemoryStore(), NOW)['line'], '')

    def test_learned_counts_new_guesses_and_new_rules_this_week(self):
        s = MemoryStore()
        s.add_learned_event('k1', 'Alex answers vendors himself.', 'hypothesis', 2, '', 'born', 'learn')
        s.add_learned_event('k1', 'Alex answers vendors himself.', 'live', 5, '', 'promoted', 'reflect')
        s.add_learned_event('k2', 'Alex files newsletters.', 'hypothesis', 0, '', 'faded', 'reflect')   # a fade is not learning
        out = since.learned(s, datetime.now())
        self.assertEqual(out['line'], 'Learned this week: 2 new things about how you work.')
        self.assertEqual(out['latest'], 'Alex answers vendors himself.')
