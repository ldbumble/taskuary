"""Which shelf an entry goes on, and whether it is already said, are the WRITER's calls.

Word rules used to decide both. snap_topic filed `payworth-api` under `payworth` unless a
TOPIC_GENERIC word was in the way; similar() upvoted an older post when 60% of the title's
non-stopword words matched, so "the export drops the last row" and "the export keeps the last row"
were one post (the owner, 2026-10-11: "everything should be ai"). The model that writes the entry is
handed the shelves and the entries already there and answers `same_as`; code keeps EXACT identity.
"""
import json
import unittest

from taskuary import handbook
from taskuary.handbook import post
from taskuary.store import MemoryStore


class ExactIdentityOnly(unittest.TestCase):
    def test_the_same_title_on_the_same_shelf_is_an_upvote(self):
        s = MemoryStore()
        a = post(s, 'Deductions are per-division', topic='payworth', author='coding')
        b = post(s, 'deductions are per division.', topic='payworth', author='codex')
        self.assertTrue(b['merged']); self.assertEqual(b['LoreId'], a['LoreId'])

    def test_nearly_the_same_words_are_not_the_same_fact(self):
        s = MemoryStore()
        post(s, 'The export drops the last row', topic='census', author='coding')
        other = post(s, 'The export keeps the last row', topic='census', author='codex')
        self.assertFalse(other['merged'])
        self.assertEqual(s.lore_count()['posts'], 2)

    def test_a_shelf_is_what_the_writer_named_never_snapped_by_its_words(self):
        s = MemoryStore()
        post(s, 'Deductions are per-division', topic='Payworth', author='coding')
        second = post(s, 'The import endpoint rejects blank cost centres', topic='Payworth API', author='coding')
        self.assertEqual(second['Topic'], 'payworth-api')
        self.assertFalse(hasattr(handbook, 'snap_topic') or hasattr(handbook, 'similar') or hasattr(handbook, 'TOPIC_GENERIC'))

    def test_it_still_falls_back_to_the_checkout_when_nothing_was_named(self):
        s = MemoryStore()
        self.assertEqual(post(s, 'the tests need pyodbc', cwd='C:/src/taskuary')['Topic'], 'taskuary')


class TheWriterSaysSameAs(unittest.TestCase):
    def test_same_as_upvotes_the_named_live_entry_and_keeps_the_new_words_as_a_comment(self):
        s = MemoryStore()
        first = post(s, 'Adjustment rows take the first line date', 'so they post to the wrong month', 'payroll', 'gotcha', 'coding')
        again = post(s, 'Adjusting entries use line one for their posting day', 'check the batch header', 'payroll', 'gotcha', 'codex',
                     same_as=first['LoreId'])
        self.assertTrue(again['merged']); self.assertEqual(again['Score'], 1)
        self.assertEqual([c['Body'] for c in s.lore_comments(first['LoreId'])], ['check the batch header'])

    def test_a_same_as_that_names_nothing_live_is_a_new_post(self):
        s = MemoryStore()
        self.assertFalse(post(s, 'Payroll closes on the first Wednesday', topic='payroll', same_as=999)['merged'])

    def test_the_closing_writer_is_shown_the_entries_and_its_same_as_is_used(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the payroll import'}, 'owner')
        first = post(s, 'Adjustment rows take the first line date', '', 'payroll', 'gotcha', 'coding')
        seen = {}
        def llm(system, user, **k):
            seen['system'], seen['user'] = system, user
            return json.dumps({'entries': [{'earned': True, 'why_earned': 'traced three batches through the importer to find it',
                                            'topic': 'payroll', 'kind': 'gotcha', 'title': 'Adjusting entries post on line one\'s day',
                                            'body': 'b', 'same_as': first['LoreId']}]})
        out = handbook.learn_from_session(s, tid, 'a long transcript', 'coding', llm=llm)
        self.assertIn(f"#{first['LoreId']} [payroll] Adjustment rows take the first line date", seen['user'])
        self.assertIn('same_as', seen['system'])
        self.assertTrue(out[0]['merged']); self.assertEqual(s.lore_count()['posts'], 1)


if __name__ == '__main__':
    unittest.main()
