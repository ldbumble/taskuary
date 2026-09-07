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


if __name__ == '__main__': unittest.main()
