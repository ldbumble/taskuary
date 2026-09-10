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
        mine = "# COUNSEL.md — I am Taskuary\n\nUri's rule: never touch Friday.\n\n## Voice\n- Dry.\n\n## My goal\n- Finish.\n"
        st.save_doc('counsel', mine, 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        after = st.get_doc('counsel')
        self.assertIn("Uri's rule: never touch Friday.", after); self.assertIn('- Dry.', after)
        self.assertLess(after.index('## When the owner decides'), after.index('## My goal'))
        self.assertIn('coder and setup are not the same road', after)
        rows = [r for r in st.list_audit('doc', 0) if r['Action'] == 'migrated']
        self.assertEqual(len(rows), 1)
        self.assertEqual(counsel.migrate(st), 'unchanged')

    def test_a_document_without_the_goal_heading_gets_the_section_at_the_end(self):
        st = MemoryStore(); st.save_doc('counsel', '# Mine\n\n## Voice\n- Dry.\n', 'owner')
        self.assertEqual(counsel.migrate(st), 'appended')
        self.assertTrue(st.get_doc('counsel').rstrip().endswith('I load, I orchestrate, Taskuary does.'))

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


if __name__ == '__main__': unittest.main()
