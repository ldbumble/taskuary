"""Every consumer of COUNSEL gets the sections for its role, whole (PW-243); nothing cuts the document (PW-258)."""
import json, unittest
from unittest import mock

from taskuary import counsel, digest, evening, general, ingest
from taskuary.store import MemoryStore

DOC = ("# COUNSEL.md — I am Taskuary\n\nIntro line.\n\n"
       "## What I do, and what I never do\n- I SURFACE the top eligible item.\n\n"
       "## My goal\n- Walk them through Unread.\n\n"
       "## Voice\n- Be plain, direct, and concise.\n" + "- Long voice rule.\n" * 400)

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'dana@vendor.example', 'from_name': 'Dana', 'conversation_id': 'AAQk-exp',
       'subject': 'August export', 'sent_at': '2026-09-06 09:00:00', 'body': 'Please write up the August export notes.'}


def _general_prompt(store) -> str:
    """A real general-work task, built the same way test_worker_brief.py builds one, so the
    worker prompt comes from general._prompt itself - not a mock of a function that doesn't exist."""
    llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'w', 'title': 'Write the export notes',
                                      'summary': 'Summarize the August export.', 'checklist': ['Write the notes']})
    with mock.patch.object(ingest, '_spawn'):
        tid = ingest.ingest_message(store, dict(MSG), llm=llm)['task_id']
    system, _user = general._prompt(store, tid)
    return system


class Consumers(unittest.TestCase):
    def setUp(self):
        self.st = MemoryStore(); self.st.save_doc('counsel', DOC, 'owner')

    def test_briefs_speak_in_the_voice_without_the_walkthrough_rules(self):
        for system in (digest.system, evening.system):
            out = system(self.st)
            self.assertIn('Be plain', out); self.assertIn('Walk them through', out); self.assertNotIn('I SURFACE', out)

    def test_the_worker_prompt_carries_the_whole_voice_section_uncut(self):
        out = _general_prompt(self.st)
        self.assertIn('WRITING STYLE', out)
        self.assertEqual(out.count('- Long voice rule.'), 400, 'the 3,000-character cut is gone')
        self.assertNotIn('I SURFACE', out)

    def test_a_worker_never_reads_twice_what_agent_md_already_says(self):
        """The instruction trim, 2026-11-16: two shipped Voice bullets restate AGENT.md - the desk keeps them (it has no AGENT.md), a
        worker does not; a bullet the owner wrote or reworded always reaches it."""
        st = MemoryStore()
        desk, worker = counsel.for_discussion(st), counsel.for_worker(st)
        for b in counsel.SAID_IN_AGENT:
            self.assertIn(' '.join(b.split()[1:4]), ' '.join(desk.split())); self.assertNotIn(' '.join(b.split()[1:4]), ' '.join(worker.split()))
        self.assertIn('calmer than before', worker)
        own = counsel.load(st).replace('A clear next move, and why.', 'A clear next move, and why - always.')
        st.save_doc('counsel', own, 'owner')
        self.assertIn('A clear next move, and why - always.', counsel.for_worker(st))

    def test_a_task_agent_never_hears_the_desks_nothing_goes_out_line(self):
        """The owner, 2026-11-16: agents echoed "nothing goes out until you say so" over the card that says it. Dropped on the agent road
        only - the Assistant keeps it, and his own document is untouched."""
        st = MemoryStore(); doc = counsel.load(st)
        self.assertIn('nothing goes out until you say so', counsel.for_discussion(st))
        self.assertNotIn('nothing goes out', counsel.for_worker(st)); self.assertIn('"this one needs you".', counsel.for_worker(st))
        st.save_doc('counsel', doc, 'owner'); counsel.for_worker(st)
        self.assertEqual(st.get_doc('counsel'), doc)

    def test_over_budget_is_a_warning_and_an_audit_row_never_a_cut(self):
        big = '- Long voice rule.\n' * 600                                    # > counsel.BUDGET; DOC itself is under it
        text = counsel.check_budget(self.st, 'counsel', big)
        self.assertEqual(text, big)
        rows = [r for r in self.st.list_audit('doc', 0) if r['Action'] == 'over_budget']
        self.assertEqual(len(rows), 1)


if __name__ == '__main__': unittest.main()
