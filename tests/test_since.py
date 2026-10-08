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


class WhatChangedTests(unittest.TestCase):
    """The opening card's top (the owner picked "A +", 2026-10-08): up to three cards for what changed while you were away - agents
    that finished, a report that said something, what was learned - and the newest Morning digest, folded under them."""
    def store(self):
        import json
        s = MemoryStore()
        self.digest = s.save_source({'Channel': 'report', 'Address': 'Morning digest', 'Active': 1,
                                     'ConfigJson': json.dumps({'type': 'digest', 'title': 'Morning digest'})}, 't')
        self.check = s.save_source({'Channel': 'report', 'Address': 'Export check', 'Active': 1,
                                    'ConfigJson': json.dumps({'type': 'taskuary', 'title': 'Export check'})}, 't')
        return s

    def test_agents_that_finished_then_a_report_fill_the_three_cards(self):
        s = self.store()
        for title in ('Fix the export', 'Rename the vendor', 'Archive the old ledger'):
            tid = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'done'}, 'o')
            s.audit('task', tid, 'self_close', 'coder', 'agent', {'why': 'finished'})
        mid = s.add_message({'ExternalId': 'r1', 'Channel': 'report', 'Subject': 'Export check — 1 real failure', 'BodyText': 'x'})
        s.add_report_run(self.check, {'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'type': 'taskuary', 'title': 'Export check',
                                      'subject': 'Export check — 1 real failure', 'message_id': mid})
        got = since.cards(s)
        self.assertEqual([c['kind'] for c in got], ['agent', 'agent', 'report'], 'two agents at most, so a report gets its say')
        self.assertTrue(got[0]['key'].startswith('task:') and got[0]['label'].startswith('Agent finished · TQ-'))
        self.assertEqual((got[2]['key'], got[2]['text']), (f'report:{mid}', 'Export check: 1 real failure'))

    def test_the_newest_digest_is_handed_whole_with_when_it_was_written_and_what_reruns_it(self):
        s = self.store()
        self.assertEqual(since.digest(s), {'source_id': self.digest, 'at': None, 'text': ''})
        mid = s.add_message({'ExternalId': 'd1', 'Channel': 'report', 'Subject': 'Morning digest', 'BodyText': 'People want\n1. Erin wants the export.'})
        s.add_report_run(self.digest, {'at': '2026-10-08 08:00:45', 'type': 'digest', 'title': 'Morning digest', 'message_id': mid})
        self.assertEqual(since.digest(s), {'source_id': self.digest, 'at': '2026-10-08 08:00:45', 'text': 'People want\n1. Erin wants the export.'})
        self.assertNotIn('digest', [c.get('text', '').lower() for c in since.cards(s)], 'the digest is the line under the cards, not a card')
