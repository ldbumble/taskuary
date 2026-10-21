"""The everyday asks (tests/assistant_queries.py), held: each one's road is right or honestly unsupported, never wrong and never a bare
"Next." - the owner's "Clear all the FYI, please." was answered "Next." (2026-10-20). No real model is ever asked: the scripted brains
answer, and the CLI and API builders raise if anything reaches for one."""
import unittest

from taskuary import concierge
from tests import assistant_queries as Q

# what no tool or desk button does today - a new tool takes its ask off this list on purpose (ASK OWNER before building one)
UNSUPPORTED = {'snooze everything from Ruth until Monday', 'close all the tasks from Priya', 'archive all the read mail', 'approve all the drafts',
               'file a note on it: waiting on the bank', 'set the due date to friday', 'use dark mode', 'mark all the approvals as done',
               'make the font bigger', 'kill all the agents'}


class EverydayAsks(unittest.TestCase):
    @classmethod
    def setUpClass(cls): cls.rows = Q.run_all()

    def test_there_are_enough_of_them_in_every_category(self):
        self.assertGreaterEqual(len(self.rows), 120)
        cats = {r['q'].cat for r in self.rows}
        self.assertEqual(cats, {'navigation', 'bulk', 'item', 'question', 'settings', 'agents', 'reports', 'chat', 'typos', 'short'})

    def test_taskuarys_road_does_what_a_good_answer_asked(self):
        for r in self.rows:
            with self.subTest(ask=r['q'].text, table=r['q'].table):
                self.assertIn(r['ideal']['grade'], ('right', 'unsupported'),
                              f"expected {r['q'].expect}, got {r['ideal']['got']}: {r['ideal']['say'][:200]!r} / told {r['ideal']['told'][:200]!r}")

    def test_the_unsupported_list_is_the_one_we_know(self):
        self.assertEqual({r['q'].text for r in self.rows if r['ideal']['grade'] == 'unsupported'}, UNSUPPORTED)

    def test_the_real_prompt_carries_a_tool_for_every_supported_ask(self):
        for r in self.rows:
            with self.subTest(ask=r['q'].text): self.assertEqual(r['ideal']['missing'], [])

    def test_the_demo_line_is_the_one_the_ask_is_about(self):
        for r in self.rows:
            with self.subTest(ask=r['q'].text):
                self.assertEqual(r['demo']['line'], r['q'].demo, r['demo']['say'][:160])
                self.assertNotEqual(r['demo']['say'].strip(), concierge.RECEIPTS['next'])

    def test_a_number_on_the_desk_is_the_action_word_it_numbers(self):
        r = next(r for r in self.rows if r['q'].text == '2')
        self.assertNotEqual(r['ideal']['heard'], '2', 'the digit reached the model as a digit')

    def test_clear_all_the_fyi_clears_them_and_says_how_many(self):
        r = next(r for r in self.rows if r['q'].text == 'Clear all the FYI, please.')
        self.assertIn('cleared', r['ideal']['got']); self.assertRegex(r['ideal']['say'], r'^Marked \d+ items? read')


if __name__ == '__main__': unittest.main()
