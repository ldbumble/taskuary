"""A CORRECTION REWORDS THE TO-DO IT CORRECTS (the owner, 2026-11-09): "Tuesday 10am... sorry, Wednesday" left both "book Tuesday" and
"book Wednesday" on the task, and "Dec 3-5... correction, Dec 4-6" the same. Triage is shown the task's open to-dos numbered and may answer
`reword` [{n, text}] - the model judges what corrects what; only an open to-do's words change, nothing is ticked, removed or added for it."""
import json, unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.store import MemoryStore
from tests.test_agent_at_work_triage import mail


def brain(seen, checklist, **extra):
    def llm(system, user, **k):
        seen.append((system, json.loads(user)))
        return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'scripted', 'title': 'Book the Payworth demo', 'summary': 'Erin asks for the demo.',
                           'checklist': checklist, **extra})
    return llm


class ACorrection(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = mail(self.s, 'a', 'Alex, can you book the Payworth demo for Tuesday 10am? And send Ray the agenda.',
                        brain([], ['Book the Payworth demo for Tuesday 10am', 'Send Ray Colton the agenda']), frm='erin@northwind.example', name='Erin Blake')['task_id']

    def texts(self): return [(i['text'], bool(i.get('done'))) for i in self.s.task_checklist(self.tid)]

    def test_it_rewords_the_one_it_corrects_and_adds_nothing_for_it(self):
        seen = []
        with mock.patch.object(ingest, 'pass_in_why', return_value='scripted'):
            b = mail(self.s, 'b', 'Sorry - Wednesday 10am, not Tuesday.', brain(seen, [], new_job=None, reword=[{'n': 1, 'text': 'Book the Payworth demo for Wednesday 10am'}]),
                     at='2026-11-02 10:00:00', frm='erin@northwind.example', name='Erin Blake')
        self.assertEqual(b['task_id'], self.tid)
        self.assertEqual(seen[-1][1]['thread_task']['open_todos'][0], {'n': 1, 'text': 'Book the Payworth demo for Tuesday 10am'})
        self.assertEqual(self.texts(), [('Book the Payworth demo for Wednesday 10am', False), ('Send Ray Colton the agenda', False)])
        self.assertTrue(any(c['Body'].startswith('Changed by the latest message:') and '-> Book the Payworth demo for Wednesday 10am' in c['Body']
                            for c in self.s.list_comments(self.tid)))

    def test_a_number_it_was_not_shown_or_a_done_one_changes_nothing(self):
        self.s.tick_checklist_item(self.tid, self.s.task_checklist(self.tid)[1]['id'], True, 'owner')
        with mock.patch.object(ingest, 'pass_in_why', return_value='scripted'):
            mail(self.s, 'b', 'Dec 4-6 actually.', brain([], [], new_job=None, reword=[{'n': 2, 'text': 'Send Ray the Dec 4-6 agenda'}, {'n': 9, 'text': 'x'}]),
                 at='2026-11-02 10:00:00', frm='erin@northwind.example', name='Erin Blake')
        self.assertEqual(self.texts(), [('Book the Payworth demo for Tuesday 10am', False), ('Send Ray Colton the agenda', True)])


class TheVerdict(unittest.TestCase):
    def test_reword_is_on_the_schema_where_a_task_is_joined_and_is_read_back_checked(self):
        self.assertIn('reword', triage.verdict_schema(thread_task=True)['schema']['properties'])
        self.assertNotIn('reword', triage.verdict_schema()['schema']['properties'])
        llm = lambda system, user, **k: json.dumps({'intent': 'task', 'why': 'w', 'title': 't', 'summary': 's',
                                                    'reword': [{'n': 1, 'text': '  Book it for  Wednesday '}, {'n': 'x', 'text': 'no'}, {'n': 2, 'text': ''}]})
        out = triage.classify_intent({'subject': 's', 'body': 'b', 'from_email': 'erin@northwind.example'}, llm=llm,
                                     thread={'thread_task': {'tid': 1, 'title': 't', 'open_todos': [{'n': 1, 'text': 'Book it for Tuesday'}]}})
        self.assertEqual(out['reword'], [{'n': 1, 'text': 'Book it for Wednesday'}])

    def test_the_guide_says_it_in_one_line_and_an_owner_written_one_is_told(self):
        self.assertIn('then `reword` names that to-do by its number in `open_todos`', triage.SHIPPED)
        self.assertIn('answer reword', triage.FIELDS['open_todos'])


if __name__ == '__main__': unittest.main()
