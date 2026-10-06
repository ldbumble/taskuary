"""The shipped COUNSEL grows a section; a live document the owner edited gets it appended, never overwritten (PW-256)."""
import unittest
from pathlib import Path

from taskuary import counsel
from taskuary.store import MemoryStore

TEMPLATES = Path(counsel.__file__).parent / 'templates'


class Migration(unittest.TestCase):
    def test_a_stock_previous_release_is_replaced_by_the_new_template(self):
        st = MemoryStore()
        st.save_doc('counsel', (TEMPLATES / 'history' / 'counsel-0.3.3.5.md').read_text(encoding='utf-8'), 'owner')
        self.assertEqual(counsel.migrate(st), 'replaced')
        self.assertIn('<!-- counsel:deciding -->', st.get_doc('counsel'))
        self.assertEqual(counsel.migrate(st), 'unchanged')

    def test_an_owner_edited_document_keeps_every_word_and_gains_the_section(self):
        st = MemoryStore()
        mine = "# COUNSEL.md — I am Taskuary\n\nAlex's rule: never touch Friday.\n\n## Voice\n- Dry.\n\n## My goal\n- Finish.\n"
        st.save_doc('counsel', mine, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertIn("Alex's rule: never touch Friday.", after); self.assertIn('- Dry.', after)
        self.assertLess(after.index('## When the owner decides'), after.index('## My goal'))
        self.assertIn('Research is never a set-up', after)
        rows = [r for r in st.list_audit('doc', 0) if r['Action'] == 'migrated']
        self.assertEqual(len(rows), 1)
        self.assertEqual(counsel.migrate(st), 'unchanged')

    def test_a_document_without_the_goal_heading_gets_the_section_at_the_end(self):
        st = MemoryStore(); st.save_doc('counsel', '# Mine\n\n## Voice\n- Dry.\n', 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        self.assertTrue(st.get_doc('counsel').rstrip().endswith('never blame myself for not seeing it.'))

    def test_a_goal_heading_look_alike_in_a_fence_or_a_deeper_heading_is_never_mistaken_for_the_real_one(self):
        # a bare substring .replace() matches inside a fenced sample AND inside '### My goal' (which
        # CONTAINS '## My goal' one character in) - either would glue the section into the wrong spot.
        mine = ("# Mine\n\n## Voice\n- Dry.\n\n### My goal\nsubheading using the same words, not the section\n\n"
                "```\n## My goal\nfenced, not a heading\n```\n\n## My goal\n- Finish.\n")
        st = MemoryStore(); st.save_doc('counsel', mine, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertIn('### My goal\nsubheading using the same words, not the section', after)
        self.assertIn('```\n## My goal\nfenced, not a heading\n```', after)
        self.assertLess(after.index('## When the owner decides'), after.rindex('## My goal\n- Finish.'))

    def test_a_whitespace_only_document_takes_the_stock_path_not_appended(self):
        st = MemoryStore(); st.save_doc('counsel', '   \n\n\t\n', 'owner')
        self.assertEqual(counsel.migrate(st), 'replaced')
        self.assertIn('<!-- counsel:deciding -->', st.get_doc('counsel'))

    def test_migrated_text_over_the_budget_is_audited_not_silently_cut(self):
        mine = '# Mine\n\n## Voice\n- Dry.\n\n' + ('x ' * 5000) + '\n\n## My goal\n- Finish.\n'
        st = MemoryStore(); st.save_doc('counsel', mine, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertGreater(len(after), counsel.BUDGET)
        self.assertIn('- Finish.', after)  # nothing was cut to make it fit
        rows = [r for r in st.list_audit('doc', 0) if r['Action'] == 'over_budget']
        self.assertEqual(len(rows), 1)


class MatchFirst(unittest.TestCase):
    """The 2026-10-01 press audit: the assistant's FIRST job on typed words is to match them to one of the actions offered
    for the item on the table, and to ask when it cannot tell - an owner-edited COUNSEL gains that one bullet, nothing else."""
    RULE = 'first I match them to one of its actions'

    def test_the_shipped_document_says_it_and_reaches_the_chat(self):
        st = MemoryStore()                                          # a fresh install is seeded from the template itself
        self.assertEqual(counsel.migrate(st), 'unchanged')
        self.assertIn(counsel.MATCH_MARKER, st.get_doc('counsel'))
        self.assertIn(self.RULE, counsel.for_chat(st))
        self.assertLessEqual(len((TEMPLATES / 'counsel.md').read_text(encoding='utf-8')), counsel.BUDGET)

    def test_the_last_stock_release_is_replaced(self):
        st = MemoryStore()
        st.save_doc('counsel', (TEMPLATES / 'history' / 'counsel-0.3.7.4.md').read_text(encoding='utf-8'), 'owner')
        self.assertEqual(counsel.migrate(st), 'replaced')
        self.assertIn(self.RULE, st.get_doc('counsel'))

    def test_a_stock_document_with_both_markers_is_still_replaced(self):
        # one with both markers returned 'unchanged' before the stock test, so no template change after 0.3.7.4 landed (2026-10-06)
        st = MemoryStore()
        st.save_doc('counsel', (TEMPLATES / 'history' / 'counsel-0.3.7.7.md').read_text(encoding='utf-8'), 'owner')
        self.assertEqual(counsel.migrate(st), 'replaced')
        self.assertIn('READING a system', st.get_doc('counsel'))
        self.assertEqual(counsel.migrate(st), 'unchanged')

    def test_an_owner_copy_learns_that_reading_is_not_coding_and_keeps_its_own_words(self):
        old = (TEMPLATES / 'history' / 'counsel-0.3.7.7.md').read_text(encoding='utf-8').replace('## My goal', "## My goal\n- Alex's own goal.", 1)
        st = MemoryStore(); st.save_doc('counsel', old, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertIn(counsel._CODING_NOW, after); self.assertNotIn('a database, a query, a file', after)
        self.assertIn("- Alex's own goal.", after)
        self.assertEqual(counsel.migrate(st), 'unchanged'); self.assertEqual(st.get_doc('counsel'), after)

    def test_an_owner_edited_document_with_the_deciding_section_gains_only_the_bullet(self):
        mine = ("# Mine\n\nAlex's rule: never touch Friday.\n\n## When the owner decides\n<!-- counsel:deciding -->\n\n"
                "- Erin's mail always waits a day.\n\n## My goal\n- Finish.\n")
        st = MemoryStore(); st.save_doc('counsel', mine, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        for kept in ("Alex's rule: never touch Friday.", "- Erin's mail always waits a day.", '- Finish.'): self.assertIn(kept, after)
        self.assertLess(after.index(self.RULE), after.index("- Erin's mail always waits a day."))
        self.assertGreater(after.index(self.RULE), after.index('<!-- counsel:deciding -->'))
        self.assertEqual(after.count('## When the owner decides'), 1)
        self.assertEqual(counsel.migrate(st), 'unchanged')
        self.assertEqual(st.get_doc('counsel'), after)

    def test_an_owner_document_without_either_gets_both_once(self):
        st = MemoryStore(); st.save_doc('counsel', '# Mine\n\n## Voice\n- Dry.\n\n## My goal\n- Finish.\n', 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertEqual(after.count(self.RULE), 1); self.assertEqual(after.count(counsel.MATCH_MARKER), 1)
        self.assertEqual(counsel.migrate(st), 'unchanged')


if __name__ == '__main__': unittest.main()
