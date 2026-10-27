"""New work on a CLOSED task's thread may be an OPEN task's job (the owner, 2026-10-27: "this task should go on the deep dive rec
task, it's the same thing. why did it not work?"). A vendor's reply on a finished "explain these figures" thread asked for a change
to the sheet the owner's own reconciliation task was rebuilding; triage reopened the closed task, as the open one - made by hand, no
thread, no sender - was never put in front of it. Now it is shown (context.open_same_job) and its `same_as` decides. The model is a stub."""
import json, unittest
from unittest import mock

from taskuary import context, ingest
from taskuary.store import MemoryStore

VENDOR, CONV = 'paula@vendor.example', 'AAQk-coins'


def brain(seen=None, **extra):
    def llm(system, user, **k):
        if seen is not None: seen.append((system, user, k.get('want')))
        return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'scripted', 'title': 'Update the payer categories in the collections mapping',
                           'summary': 'Paula asks for two payers to get their own category in the collections mapping.', **extra})
    llm.takes_want = True
    return llm


def mail(s, ext, body, llm, at='2026-10-27 09:00:00', conv=CONV):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': VENDOR, 'from_name': 'Paula Vance',
                                         'conversation_id': conv, 'subject': 'Re: Co-insurance figures in the collections sheet',
                                         'body': body, 'sent_at': at}, llm=llm)


class ClosedThreadJoinsOpenJob(unittest.TestCase):
    def setUp(self):
        s = self.s = MemoryStore()
        for k in ('calendar_enabled', 'coding_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
        s.set_setting('owner_email', 'alex@northwind.example', 't')
        self.a = mail(s, 'a', 'Alex, can you explain the co-insurance figures in the collections sheet?',
                      brain(title='Explain the co-insurance figures', summary='Paula asks what the co-insurance figures in the collections sheet mean.'),
                      at='2026-10-20 09:00:00')['task_id']
        s.update_task(self.a, {'Status': 'done'}, 'owner')
        # the owner's own deep dive: made by hand, no thread, no sender
        self.b = s.create_task({'Title': 'Reconcile receivables for the North site', 'Summary': 'Deep-dive reconciliation of the collections '
                                'and receivables data, payer by payer, with the payer mapping rebuilt.', 'Kind': 'general',
                                'Status': 'in_progress', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
        s.add_comment(self.b, 'owner', 'human', 'Rebuilt the payer mapping tab; checking the self-pay rows next.')

    ASK = 'Thanks Alex. Could you break out Payworth and Trainly into their own payer category in the mapping, and fix the self-pay category?'

    def test_the_owners_open_job_is_shown_on_a_closed_thread(self):
        seen = []
        mail(self.s, 'b', self.ASK, brain(seen))
        work = json.loads(seen[-1][1])['open_work']
        b = next(w for w in work if w['tid'] == self.b)
        self.assertEqual(b['from'], 'you - your own task, nobody else asked for it')
        self.assertIn('payer', b['why']); self.assertIn('self-pay', b['latest'])
        self.assertIn('same_as', seen[-1][2]['schema']['properties'])

    def test_same_job_joins_the_open_task_and_the_closed_one_stays_closed(self):
        r = mail(self.s, 'b', self.ASK, brain(same_as=self.b, why='the payer mapping the reconciliation is rebuilding'))
        self.assertEqual((r['status'], r['task_id']), ('routed', self.b))
        self.assertEqual(self.s.get_task(self.a)['Status'], 'done')
        self.assertFalse(any(c['Body'].startswith('Reopened') for c in self.s.list_comments(self.a)))
        self.assertEqual(self.s.get_task(self.a)['Title'], 'Explain the co-insurance figures', 'the closed task is not retitled')
        self.assertEqual(self.s.get_task(self.b)['Title'], 'Reconcile receivables for the North site', 'the owner named their own task')
        ref = ingest.task_ref(self.b)
        self.assertTrue(any(f'joined {ref} - same job: the payer mapping' in c['Body'] for c in self.s.list_comments(self.a)))
        self.assertTrue(any(c['Body'].startswith(f'Joined from {ingest.task_ref(self.a)}') for c in self.s.list_comments(self.b)))
        self.assertEqual(self.s.get_message(r['message_id'])['TaskId'], self.b)

    def test_a_different_job_reopens_the_closed_thread_task_as_before(self):
        r = mail(self.s, 'b', self.ASK, brain(same_as=None))
        self.assertEqual((r['status'], r['task_id']), ('attached', self.a))
        self.assertEqual(self.s.get_task(self.a)['Status'], 'open')
        self.assertEqual(self.s.list_messages(self.b), [])

    def test_a_thanks_on_the_closed_thread_stays_there_whatever_same_as_says(self):
        thanks = lambda *a, **k: json.dumps({'intent': 'fyi', 'why': 'thanks', 'same_as': self.b})
        r = mail(self.s, 'b', 'Thanks, that makes sense.', thanks)
        self.assertEqual((r['status'], r['task_id']), ('filed', self.a))
        self.assertEqual(self.s.get_task(self.a)['Status'], 'done')
        self.assertEqual(self.s.list_messages(self.b), [])

    def test_a_reply_on_an_open_tasks_thread_is_unchanged(self):
        self.s.update_task(self.a, {'Status': 'open'}, 'owner')
        seen = []
        r = mail(self.s, 'b', self.ASK, brain(seen, same_as=self.b))
        self.assertEqual(r['task_id'], self.a, 'an open thread keeps its reply')
        self.assertNotIn(self.b, {w['tid'] for w in json.loads(seen[-1][1]).get('open_work') or []},
                         'the owner\'s work is offered only beside a closed thread')

    def test_unrelated_open_work_is_not_offered(self):
        other = self.s.create_task({'Title': 'Book the offsite room', 'Summary': 'Find a room for the Thursday offsite.', 'Kind': 'task',
                                    'Status': 'open', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
        ht = ingest.thread_task(self.s, self.a)
        got = {w['tid'] for w in context.open_same_job(self.s, {'subject': 'Re: Co-insurance', 'body': self.ASK}, ht)}
        self.assertIn(self.b, got); self.assertNotIn(other, got); self.assertNotIn(self.a, got)


if __name__ == '__main__': unittest.main()
