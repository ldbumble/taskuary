"""A shipped owner document moves on with the template: a stock copy - blank, never edited, or any text shipped before
(templates/history/<name>-*.md) - takes today's; a copy the owner wrote himself keeps every word (store.seed_docs)."""
import unittest
from pathlib import Path

from taskuary import counsel
from taskuary.store import MemoryStore

TEMPLATES = Path(counsel.__file__).parent / 'templates'
def shipped(name): return (TEMPLATES / f'{name}.md').read_text(encoding='utf-8')


class Migration(unittest.TestCase):
    def test_every_stock_copy_shipped_before_takes_todays_whoever_saved_it(self):
        for name in ('counsel', 'advisor'):
            olds = sorted((TEMPLATES / 'history').glob(f'{name}-*.md'))
            self.assertTrue(olds, name)
            for old in olds:
                st = MemoryStore(); st.save_doc(name, old.read_text(encoding='utf-8').replace('\n', '\r\n'), 'startup')
                st.seed_docs()
                self.assertEqual((st.get_doc(name), st.doc_owner(name)), (shipped(name), 'template'), old.name)

    def test_the_document_the_owner_wrote_keeps_every_word(self):
        mine = "# COUNSEL.md — I am Taskuary\n\nAlex's rule: never touch Friday.\n\n## My goal\n- Finish.\n"
        st = MemoryStore(); st.save_doc('counsel', mine, 'owner')
        st.seed_docs()
        self.assertEqual((st.get_doc('counsel'), st.doc_owner('counsel')), (mine, 'owner'))
        # ...and an old shipped text he changed by one word is his too
        his = (TEMPLATES / 'history' / 'counsel-0.4.6.11.md').read_text(encoding='utf-8').replace('as little effort', 'the least effort', 1)
        st.save_doc('counsel', his, 'owner'); st.seed_docs()
        self.assertEqual(st.get_doc('counsel'), his)

    def test_a_blank_document_takes_the_shipped_one(self):
        st = MemoryStore(); st.save_doc('counsel', '   \n\n\t\n', 'owner')
        st.seed_docs()
        self.assertEqual((st.get_doc('counsel'), st.doc_owner('counsel')), (shipped('counsel'), 'template'))

    def test_the_shipped_counsel_fits_its_budget_and_reaches_the_chat_and_the_brief(self):
        st = MemoryStore()
        self.assertLessEqual(len(shipped('counsel')), counsel.BUDGET)
        self.assertIn('## My goal', counsel.for_brief(st)); self.assertIn('## What I see', counsel.for_chat(st))


if __name__ == '__main__': unittest.main()
