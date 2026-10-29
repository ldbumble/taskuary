"""Wording slips the email walk found (2026-10-29): sentences cut mid-word, a label with nothing after it."""
import unittest
from taskuary import blackboard


class WordingSlipTests(unittest.TestCase):
    def test_a_start_failure_reason_is_cut_on_a_word_never_mid_word(self):
        err = 'The agent could not open the checkout ' + 'because the repository folder was moved away ' * 8
        line = blackboard.failed_line(err, False)
        why = line.split(': ', 1)[1].split('. Press Start')[0]
        self.assertTrue(why.endswith('…'), why)
        self.assertTrue(err.startswith(why[:-1]) and err[len(why) - 1] == ' ', f'ends on a whole word: {why}')
        first = 'First the login failed on the allowed host because the vendor had not yet added our address to its list of callers'
        self.assertEqual(blackboard._why(f'{first}. ' + 'Then the retry timed out waiting for it ' * 6), first)    # a whole sentence
        self.assertEqual(blackboard._why('short reason.'), 'short reason')

    def test_a_review_cited_as_evidence_names_what_it_was_about(self):
        from taskuary.store import MemoryStore
        from taskuary import learnedgraph
        s = MemoryStore()
        tid = s.create_task({'Title': 'Webinar sign-up for Erin', 'Kind': 'reply', 'Status': 'open'}, 'owner')
        rid = s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'needs a reply'})
        self.assertEqual(learnedgraph._resolve(s, f'rv{rid}')['label'], 'pending: Webinar sign-up for Erin')   # never "pending:" alone
        bare = s.add_review({'TaskId': s.create_task({'Title': '', 'Kind': 'reply', 'Status': 'open'}, 'owner'), 'Kind': 'draft', 'Status': 'pending'})
        self.assertEqual(learnedgraph._resolve(s, f'rv{bare}')['label'], 'pending')

    def test_a_date_header_ahead_of_the_clock_never_makes_the_rail_say_in_5h(self):
        from datetime import datetime, timedelta
        from taskuary.store import MemoryStore
        from taskuary import processing_unread, funnel
        s = MemoryStore()
        tid = s.create_task({'Title': 'Webinar invite', 'Kind': 'reply', 'Status': 'open'}, 'owner')
        ahead = (datetime.now() + timedelta(hours=5)).strftime('%Y-%m-%d %H:%M:%S')
        made = s.get_task(tid)['CreatedAt']
        got = processing_unread.arrived_at(s, {'tid': tid}, s.get_task(tid), {'messages': [{'MessageId': 1, 'SentAt': ahead}]}, None)
        self.assertEqual(got, made)
        came = (datetime.now() - timedelta(minutes=3)).strftime('%Y-%m-%d %H:%M:%S')      # an FYI row: no task, only its mail
        got = processing_unread.arrived_at(s, {}, {}, {'messages': [{'MessageId': 2, 'SentAt': ahead, 'CreatedAt': came}]}, None)
        self.assertEqual(got, came)
        self.assertEqual(funnel.not_ahead([ahead]), [ahead], 'all ahead: kept, never nothing')


if __name__ == '__main__': unittest.main()
