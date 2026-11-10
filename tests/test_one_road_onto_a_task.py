"""One road onto a task that exists (the spine audit, 2026-11-09).

A message reaches a task by its own thread, by triage naming the task it is (`same_as`), or by triage naming the goal step it serves -
and each road had its own copy of what landing means. They had drifted: a mail nothing had read reopened a closed thread; a chat line
whose verdict failed joined as if it had been read; a `same_as` rejoined a task the owner had dropped; only the thread's road brought
a task back from Remind; a goal took a mail by a filing rule of its own. `ingest.land_on` is the one landing now. Invented people."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import ingest
from taskuary.store import MemoryStore

TODAY = f'{datetime.now():%Y-%m-%d}'
ERIN, DM = 'erin@northwind.example', 'whatsapp:erin-blake'


def brain(**v):
    def llm(system, user, **k):
        return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'scripted', 'title': 'Send Erin the seat count', 'summary': 'Erin asks how many seats.', **v})
    llm.takes_want = True
    return llm

def down(system, user, **k): raise RuntimeError('503 from the model')
def babble(system, user, **k): return 'I am not sure what you would like me to do with this.'

def mail(s, ext, body, llm, conv='c:seats', at='09:00:00', **kw):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': ERIN, 'from_name': 'Erin Blake', 'conversation_id': conv,
                                         'subject': 'Seats for the offsite', 'body': body, 'sent_at': f'{TODAY} {at}', **kw}, llm=llm)

def chat(s, ext, body, llm, at):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'whatsapp', 'from_name': 'Erin Blake', 'from_email': None, 'conversation_id': DM,
                                         'subject': 'Chat with Erin Blake', 'body': body, 'sent_at': f'{TODAY} {at}', 'source_name': 'Erin Blake',
                                         'mail_meta': {'dm': True}}, llm=llm)

def store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    return s

def said(s, r): return s.message_routes(r['message_id'])[-1]['Reason']


class NothingReadItTests(unittest.TestCase):
    "A line triage did not read decides nothing: it is kept on its task as unread, with Retry - by whichever road its verdict came."
    def test_a_mail_on_a_closed_thread_with_no_brain_waits_unread(self):
        s = store(); t = mail(s, 'a', 'How many seats do we have?', brain())['task_id']; s.update_task(t, {'Status': 'done'}, 'owner')
        r = mail(s, 'b', 'And what is the budget per head?', None, at='10:00:00')
        self.assertEqual((r['status'], r['task_id'], s.get_task(t)['Status']), ('error', t, 'done'), 'it reopened the task with nobody having read it')
        self.assertRegex(said(s, r), s.TRIAGE_UNJUDGED, 'the retry sweep finds it the moment a brain exists')
        self.assertIn(ingest.task_ref(t), said(s, r))

    def test_on_an_open_thread_it_still_joins(self):
        s = store(); t = mail(s, 'a', 'How many seats do we have?', brain())['task_id']
        self.assertEqual(mail(s, 'b', 'And what is the budget per head?', None, at='10:00:00')['status'], 'attached')
        self.assertNotIn(s.get_task(t)['Status'], ('done', 'dropped'))

    def test_a_chat_line_whose_verdict_failed_does_not_reopen_the_chats_task(self):
        for llm, words in ((down, 'AI triage failed (503 from the model)'), (babble, 'could not read as a verdict')):
            with self.subTest(words):
                s = store(); t = chat(s, 'a', 'How many seats do we have?', brain(relationship='new'), '09:00:00')['task_id']
                s.update_task(t, {'Status': 'done'}, 'owner')
                r = chat(s, 'b', 'and what is the budget per head?', llm, '10:00:00')
                self.assertEqual((r['status'], r['task_id'], s.get_task(t)['Status']), ('error', t, 'done'))
                self.assertIn(words, said(s, r)); self.assertRegex(said(s, r), s.TRIAGE_UNJUDGED)
                self.assertFalse(s.pending_review(t), 'nothing is drafted to a line nobody read')


class SameAsTests(unittest.TestCase):
    def setUp(self):
        s = self.s = store()
        self.t = mail(s, 'a', 'How many seats do we have?', brain())['task_id']

    def test_a_dropped_task_is_never_rejoined(self):
        self.s.update_task(self.t, {'Status': 'dropped'}, 'owner')
        r = mail(self.s, 'b', 'Seats again - how many?', brain(same_as=self.t), conv='c:other')
        self.assertEqual(r['status'], 'created'); self.assertNotEqual(r['task_id'], self.t)
        self.assertEqual(self.s.get_task(self.t)['Status'], 'dropped')

    def test_work_that_joins_brings_the_task_back_from_remind(self):
        self.s.update_task(self.t, {'RemindAt': f'{datetime.now() + timedelta(days=9):%Y-%m-%d %H:%M:%S}'}, 'owner')
        r = mail(self.s, 'b', 'The caterer needs the seat count tomorrow.', brain(same_as=self.t), conv='c:other')
        self.assertEqual((r['status'], r['task_id']), ('routed', self.t))
        self.assertFalse(self.s.get_task(self.t).get('RemindAt'), 'it joined a task put away for nine days and stayed there')

    def test_a_filed_line_that_joins_marks_nothing(self):
        mail(self.s, 'b', 'Thanks, got it.', brain(intent='fyi', kind=None, same_as=self.t, urgent=True, due=TODAY), conv='c:other')
        t = self.s.get_task(self.t)
        self.assertNotEqual(t.get('Priority'), 'urgent'); self.assertFalse(t.get('DueAt'), "a line filed for the chain is not the task's new day")


class StepTests(unittest.TestCase):
    def setUp(self):
        s = self.s = store()
        self.g = s.create_task({'Title': 'Move the offsite to the new venue', 'Kind': 'task', 'Status': 'open', 'DoneWhen': 'everyone has a seat'}, 'owner')
        s.set_task_checklist(self.g, ['Erin confirms the seats', 'Gail books the coach'], 'owner')
        self.ids = [x['id'] for x in s.goal_steps(self.g)]

    def serve(self, ext, k=0, **v):
        return mail(self.s, ext, 'About the seats.', brain(serves={'task': self.g, 'step': self.ids[k], 'done': False}, **v), conv=f'c:{ext}')

    def test_a_closed_goal_follows_the_one_rule(self):
        self.s.update_task(self.g, {'Status': 'done'}, 'owner')
        r = self.serve('b', intent='reply_only', kind=None)                       # an answer, nothing asked of the owner
        self.assertEqual((r['status'], r['task_id'], self.s.get_task(self.g)['Status']), ('filed', self.g, 'done'))
        self.assertFalse(self.s.pending_review(self.g), 'a reply was drafted on a closed goal nobody looks at')
        r = self.serve('c')                                                       # new work: it comes back
        self.assertEqual(r['status'], 'routed'); self.assertNotIn(self.s.get_task(self.g)['Status'], ('done', 'dropped'))

    def test_a_dropped_steps_task_is_not_come_back_to(self):
        c = self.s.create_task({'Title': 'Erin confirms the seats', 'Status': 'open'}, 'owner'); self.s.link_step(self.g, self.ids[0], c, 'owner')
        self.s.update_task(c, {'Status': 'dropped'}, 'owner')
        r = self.serve('b')
        self.assertEqual((r['task_id'], self.s.get_task(c)['Status']), (self.g, 'dropped'))

    def test_the_goal_itself_is_never_set_working_by_its_mail(self):
        with mock.patch.object(ingest, '_carry_on') as go: r = self.serve('b', kind='general')
        self.assertEqual(r['task_id'], self.g); go.assert_not_called()
        self.assertEqual(self.s.get_task(self.g)['Kind'], 'task')
