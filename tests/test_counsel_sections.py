"""COUNSEL is one document with sections; each consumer gets the sections for its role (PW-243)."""
import unittest

from taskuary import counsel
from taskuary.store import MemoryStore

DOC = ("# COUNSEL.md — I am Taskuary\n\nI have Uri's back.\n\n"
       "## What I do, and what I never do\n- I SURFACE the top eligible item.\n\n"
       "## My goal\n- Walk them through Unread.\n\n"
       "## Voice\n- Be plain, direct, and concise.\n")


class Sections(unittest.TestCase):
    def test_sections_split_on_h2_and_keep_the_intro(self):
        s = counsel.sections(DOC)
        self.assertEqual(list(s), ['', 'What I do, and what I never do', 'My goal', 'Voice'])
        self.assertIn("I have Uri's back.", s[''])
        self.assertEqual(s['Voice'].strip(), '- Be plain, direct, and concise.')

    def test_each_role_gets_its_sections_and_nothing_else(self):
        st = MemoryStore(); st.save_doc('counsel', DOC, 'owner')
        self.assertIn('I SURFACE', counsel.for_chat(st))
        brief = counsel.for_brief(st)
        self.assertIn('Walk them through Unread', brief); self.assertIn('Be plain', brief); self.assertNotIn('I SURFACE', brief)
        for f in (counsel.for_discussion, counsel.for_worker):
            out = f(st)
            self.assertIn('Be plain', out); self.assertNotIn('I SURFACE', out); self.assertNotIn('Walk them through', out)
            self.assertIn("I have Uri's back.", out, 'the intro travels with every role')

    def test_renamed_headings_fall_back_to_the_whole_document(self):
        st = MemoryStore(); st.save_doc('counsel', "# Mine\n\n## How I talk\n- Short.\n", 'owner')
        self.assertEqual(counsel.for_worker(st).strip(), "# Mine\n\n## How I talk\n- Short.")

    def test_load_strips_comments_and_restores_a_blank_document(self):
        st = MemoryStore(); st.save_doc('counsel', '<!-- nothing -->', 'owner')
        text = counsel.load(st)
        self.assertIn('I am Taskuary', text)
        self.assertEqual(st.get_doc_row('counsel')['UpdatedBy'], 'template')


if __name__ == '__main__': unittest.main()
