"""The thread is a hint, the topic is the task (the owner, 2026-10-26: "same chat, same task" is "a decent guide but not
deterministic"). A mail on a thread with a task still joins that task by default - but triage is shown the thread's task
(`thread_task`) and may answer `new_job`: then the mail opens a task of its own, and the thread's task gets one quiet note and is
neither reopened nor retitled by it. A chat room asks the same question through `relationship`, judged once."""
import json, unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.store import MemoryStore

ASK = 'Alex, can you approve the Payworth refund for the Q3 overpayment? Paperwork attached.'


def brain(seen=None, **extra):
    def llm(system, user, **k):
        if seen is not None: seen.append((system, user, k.get('want')))
        return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'scripted', 'title': 'Approve the Payworth Q3 refund',
                           'summary': 'Gail asks for the Q3 overpayment refund to be approved.', **extra})
    llm.takes_want = True                # the schema rides on the wire, so the test reads which fields were offered
    return llm


def mail(s, ext, body, llm, at='2026-10-26 09:00:00', frm='gail@northwind.example', name='Gail Moreno', conv='AAQk-refund'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': name, 'conversation_id': conv,
                                         'subject': 'Re: Payworth Q3 refund', 'body': body, 'sent_at': at}, llm=llm)


class ThreadIsAHint(unittest.TestCase):
    def test_a_thanks_on_the_thread_joins_and_triage_saw_the_threads_task(self):
        s = MemoryStore(); tid = mail(s, 'a', ASK, brain())['task_id']; seen = []
        thanks = lambda *a, **k: (seen.append(a), json.dumps({'intent': 'fyi', 'why': 'thanks, file attached', 'new_job': None}))[1]
        b = mail(s, 'b', 'Thanks Alex - signed form attached.', thanks, at='2026-10-26 10:00:00')
        self.assertEqual((b['status'], b['task_id']), ('filed', tid))
        self.assertIn('"thread_task": {"tid": %d' % tid, seen[-1][1])
        self.assertEqual(len(s.list_tasks()), 1)

    def test_the_schema_offers_new_job_only_on_a_thread_with_a_task(self):
        s = MemoryStore(); seen = []
        tid = mail(s, 'a', ASK, brain(seen))['task_id']
        self.assertNotIn('new_job', seen[-1][2]['schema']['properties'], 'a fresh mail has no thread task to differ from')
        mail(s, 'b', 'Any news on this?', brain(seen), at='2026-10-26 10:00:00')
        self.assertIn('new_job', seen[-1][2]['schema']['properties'])
        self.assertIn('new_job', triage.SHIPPED, 'the guide says when to answer it')

    def test_a_different_job_on_the_thread_opens_its_own_task_and_leaves_the_old_one_a_note(self):
        s = MemoryStore(); first = mail(s, 'a', ASK, brain()); tid = first['task_id']
        title = s.get_task(tid)['Title']
        other = brain(new_job='a laptop for the new starter, nothing to do with the refund', title='Set up a laptop for Omar Keller')
        b = mail(s, 'b', 'Separately - Omar Keller starts Monday, can you set up his laptop?', other, at='2026-10-26 10:00:00')
        self.assertEqual(b['status'], 'created'); self.assertNotEqual(b['task_id'], tid)
        self.assertEqual(s.get_task(b['task_id'])['Title'], 'Set up a laptop for Omar Keller')
        self.assertEqual(s.get_task(tid)['Title'], title, 'the thread task is not retitled by another job')
        self.assertTrue(any(f'different ask -> {ingest.task_ref(b["task_id"])}' in c['Body'] for c in s.list_comments(tid)))
        route = s.message_routes(b['message_id'])[-1]
        self.assertEqual((route['Decision'], route['RoutedBy']), ('create', 'triage'))
        self.assertIn(f'a different job from {ingest.task_ref(tid)}', route['Reason'])
        self.assertIn('new_job', json.loads(route['VerdictJson']), 'the decision is kept, so a correction can learn from it')

    def test_a_different_job_on_a_closed_thread_leaves_it_closed(self):
        s = MemoryStore(); tid = mail(s, 'a', ASK, brain())['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        b = mail(s, 'b', 'Different thing - can you renew the Trainly licence before it lapses?',
                 brain(new_job='a licence renewal, not the refund', title='Renew the Trainly licence'), at='2026-10-27 09:00:00')
        self.assertEqual(b['status'], 'created'); self.assertNotEqual(b['task_id'], tid)
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertFalse(any(c['Body'].startswith('Reopened') for c in s.list_comments(tid)))

    def test_new_work_on_the_same_job_still_reopens_the_closed_thread_task(self):
        s = MemoryStore(); tid = mail(s, 'a', ASK, brain())['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        b = mail(s, 'b', 'The refund bounced - can you re-issue it?', brain(new_job=None), at='2026-10-27 09:00:00')
        self.assertEqual((b['status'], b['task_id']), ('attached', tid))
        self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_new_job_that_names_the_thread_task_as_same_as_keeps_the_join(self):
        s = MemoryStore(); tid = mail(s, 'a', ASK, brain())['task_id']
        b = mail(s, 'b', 'Also the PO number is 4471.', brain(new_job='yes', same_as=tid), at='2026-10-26 10:00:00')
        self.assertEqual((b['status'], b['task_id']), ('attached', tid))

    def test_an_fyi_never_splits_it_stays_on_the_thread(self):
        s = MemoryStore(); tid = mail(s, 'a', ASK, brain())['task_id']
        fyi = lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'news', 'new_job': 'a different subject'})
        b = mail(s, 'b', 'FYI the office is closed Friday.', fyi, at='2026-10-26 10:00:00')
        self.assertEqual((b['status'], b['task_id']), ('filed', tid))


class ChatRoomAsksOnce(unittest.TestCase):
    """A chat room's question is `relationship`, among the room's same-day lines - never a second `new_job` beside it."""
    def line(self, s, ext, body, llm, at):
        with mock.patch.object(ingest, '_spawn'):
            return ingest.ingest_message(s, {'external_id': ext, 'channel': 'teams', 'from_email': '', 'from_name': 'Erin Blake',
                                             'conversation_id': 'teams:ops-room', 'subject': '', 'body': body, 'sent_at': at}, llm=llm)

    def test_a_different_ask_in_the_room_is_its_own_task_and_a_thanks_joins(self):
        s = MemoryStore(); seen = []
        first = self.line(s, 'c1', 'the ledger export fails with a timeout, can you look?', brain(seen, relationship='new'), '2026-10-26 09:00:00')
        mid = first['message_id']
        new = self.line(s, 'c2', 'separate thing: can you add Ray Colton to the portal admins?',
                        brain(seen, relationship='new', title='Add Ray Colton to portal admins'), '2026-10-26 09:05:00')
        self.assertNotIn('new_job', seen[-1][2]['schema']['properties'], 'judged once, by relationship')
        self.assertNotEqual(new['task_id'], first['task_id'])
        thanks = lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'thanks', 'relationship': 'answers', 'related_message_ids': [mid]})
        t = self.line(s, 'c3', 'thanks, the export works now', thanks, '2026-10-26 09:30:00')
        self.assertEqual(t['task_id'], first['task_id'])


if __name__ == '__main__':
    unittest.main()
