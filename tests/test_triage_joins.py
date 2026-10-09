"""One job, one task (the owner, 2026-09-25, triage step 1).

T1/T2 - a line on the thread of a CLOSED task goes back to that task: filed when it only says thanks, reopening it
when it needs the owner. T4 - triage is shown the open and recently closed work an arrival touches and may answer
that it IS one of them (same_as). T3 - Taskuary's own reports and ideas count as one sender for the exact repeat.
T5 - a message that reached its task before a later step failed is never judged again as new work."""
import json, unittest
from unittest import mock

from taskuary import ingest, triage
from taskuary.store import MemoryStore, task_ref


def brain(intent, same_as=None, title=None, seen=None, kind='task'):
    """Triage, scripted: the verdict it gives, and whether it names a task this message is the same as."""
    def llm(system, user, **k):
        if seen is not None: seen.append({'sys': system, 'usr': user})
        out = {'intent': intent, 'why': 'scripted', 'title': title or 'Fix the nightly export', 'summary': 's'}
        if intent == 'task': out['kind'] = kind
        if same_as is not None: out['same_as'] = same_as
        return json.dumps(out)
    return llm


def mail(s, ext, llm, conv, subject='Nightly export drops rows', body='The export drops inter-company rows again.',
         frm='erin@northwind.example', channel='email'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': channel, 'from_email': frm, 'from_name': 'Erin Blake',
                                         'conversation_id': conv, 'subject': subject, 'body': body,
                                         'sent_at': '2026-09-25 09:00:00'}, llm=llm)


class SameAsTests(unittest.TestCase):
    def test_triage_is_shown_the_open_work_and_asked_whether_this_is_it(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        seen = []
        mail(s, 'b', brain('task', seen=seen), conv='c2')                     # a new thread, the same subject
        self.assertIn('same_as', seen[-1]['sys'])
        self.assertIn(f'"tid": {first["task_id"]}', seen[-1]['usr'])

    def test_same_as_an_open_task_joins_it_instead_of_a_second_task(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        again = mail(s, 'b', brain('task', same_as=first['task_id'], title='Export still drops rows'), conv='c2')
        self.assertEqual((again['status'], again['task_id']), ('routed', first['task_id']))
        self.assertEqual(len(s.list_tasks()), 1)
        self.assertIn('the same as', s.message_routes(again['message_id'])[-1]['Reason'])

    def test_one_pull_request_never_joins_another_ones_task(self):
        """The owner, 2026-09-28: two docs PRs from one contributor read alike, and triage filed #121 into #120's task.
        A pull request or an issue is its own job; a new push on the SAME one still joins its task."""
        # ...said to TRIAGE as a rule it applies, not enforced over its answer (2026-10-08): it is told, it answers null
        s = MemoryStore()
        seen = []
        first = mail(s, 'pr120', brain('task'), conv='gh:northwind/portal#120', channel='github', subject='northwind/portal#120 docs: fix the example')
        other = mail(s, 'pr121', brain('task', seen=seen), conv='gh:northwind/portal#121', channel='github',
                     subject='northwind/portal#121 docs: fill in the descriptions')
        self.assertIn('a different pull request or issue number', seen[-1]['sys'])    # a sign it is new (the guide, section 3)
        self.assertNotEqual(other['task_id'], first['task_id'])
        again = mail(s, 'pr120-push', brain('task', same_as=first['task_id']), conv='gh:northwind/portal#120', channel='github',
                     subject='northwind/portal#120 docs: fix the example')
        self.assertEqual(again['task_id'], first['task_id'])

    def test_same_as_a_closed_task_reopens_it_and_an_fyi_leaves_it_closed(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1'); tid = first['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        note = mail(s, 'b', brain('fyi', same_as=tid, title='Export report, same as before'), conv='c2')
        self.assertEqual((note['status'], note['task_id']), ('filed', tid))
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        back = mail(s, 'c', brain('task', same_as=tid, title='The export fix did not hold'), conv='c3')
        self.assertEqual((back['status'], back['task_id']), ('routed', tid))
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertEqual(len(s.list_tasks()), 1)

    def test_a_report_run_is_never_filed_away_on_yesterdays_closed_task(self):
        """A daily report shares one conversation, so triage saw yesterday's closed task and called today's run "the
        same", fyi - and filing it on a closed task put it nowhere: the morning report never showed (2026-10-01). A
        run judged fyi lands as its own row, where the report's Timeline line decides; an OPEN task still takes it."""
        s = MemoryStore()
        run = lambda ext, llm: mail(s, ext, llm, conv='report:7', channel='report', frm='', subject='Morning digest - 40 lines')
        first = run('report:7:mon', brain('task', title='Review the morning digest')); tid = first['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        # the rule is TRIAGE's to apply (2026-10-08) - told, it answers null; code no longer unjoins its answer
        seen = []
        today = run('report:7:tue', brain('fyi', title='Morning digest', seen=seen))
        self.assertIn('a report run that needs nothing from the owner is better as its own quiet row than filed on a closed task', seen[-1]['sys'])
        self.assertEqual((today['status'], today['task_id']), ('filed', None), 'today\'s run vanished into the closed task')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        s.update_task(tid, {'Status': 'open'}, 'owner')
        again = run('report:7:wed', brain('fyi', same_as=tid, title='Morning digest'))
        self.assertEqual(again['task_id'], tid, 'an open task is still where its next run belongs')

    def test_a_task_it_was_never_shown_joins_nothing(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        other = mail(s, 'b', brain('task', same_as=9999, title='Something else entirely'), conv='c2',
                     subject='Printer on floor 3', body='The printer is jammed.', frm='omar@northwind.example')
        self.assertEqual(other['status'], 'created'); self.assertNotEqual(other['task_id'], first['task_id'])


class SomeoneElsesAskTests(unittest.TestCase):
    """A stranger's pull request that closes the owner's issue shares every word of it, and triage joined the two -
    reopening the owner's finished task, its agent session and its old draft, now addressed to the stranger
    (2026-09-25). The judge is told who each task is from, and that another person's new thread is a new ask."""

    def test_triage_sees_the_task_is_someone_elses(self):
        s = MemoryStore()
        issue = mail(s, 'i', brain('task', title='Split long Discord replies'), conv='gh:northwind/ledger#53',
                     frm='alex@northwind.example', subject='Discord replies are cut off at 2,000 characters')
        s.update_task(issue['task_id'], {'Status': 'done'}, 'owner')
        seen = []
        mail(s, 'p', brain('task', seen=seen), conv='gh:northwind/ledger#65', frm='ray@vendor.example',
             subject='Send long Discord replies without truncation', body='Discord replies are cut off at 2,000 characters. Closes #53.')
        self.assertIn('"from": "someone else: alex@northwind.example - not this sender"', seen[-1]['usr'])
        self.assertIn("someone else's new thread about a similar subject", seen[-1]['sys'])

    def test_the_same_sender_again_is_told_so(self):
        s = MemoryStore()
        mail(s, 'a', brain('task'), conv='c1')
        seen = []
        mail(s, 'b', brain('task', seen=seen), conv='c2')
        self.assertIn('"from": "this sender"', seen[-1]['usr'])

    def test_their_pull_request_left_unjoined_is_a_task_of_its_own(self):
        s = MemoryStore()
        issue = mail(s, 'i', brain('task'), conv='gh:northwind/ledger#53', frm='alex@northwind.example')
        s.update_task(issue['task_id'], {'Status': 'done'}, 'owner')
        pr = mail(s, 'p', brain('task', title='Review the Discord chunking PR'), conv='gh:northwind/ledger#65', frm='ray@vendor.example')
        self.assertEqual(pr['status'], 'created'); self.assertNotEqual(pr['task_id'], issue['task_id'])
        self.assertEqual(s.get_task(issue['task_id'])['Status'], 'done')


class ChatReopensTests(unittest.TestCase):
    def test_a_chat_line_that_answers_a_closed_ask_goes_back_to_it(self):
        s = MemoryStore()
        chat = lambda ext, body, llm: mail(s, ext, llm, conv='room-1', subject='', body=body, channel='teams')
        first = chat('t1', 'Can you send me the August statement?', brain('reply_only')); tid = first['task_id']
        s.update_task(tid, {'Status': 'done'}, 'owner')
        mid1 = first['message_id']
        def answers(system, user, **k):
            return json.dumps({'intent': 'reply_only', 'why': 'asks again', 'title': 'August statement', 'summary': 's',
                               'relationship': 'answers', 'related_message_ids': [mid1], 'existing_task_id': tid, 'same_problem': True})
        back = chat('t2', 'still need that statement, the one for August', answers)
        self.assertEqual((back['status'], back['task_id']), ('attached', tid))
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        self.assertEqual(len(s.list_tasks()), 1)


class OwnChannelRepeatTests(unittest.TestCase):
    def test_the_advisor_and_a_report_on_one_event_make_one_task(self):
        s = MemoryStore()
        a = mail(s, 'r1', brain('task', title='Nightly export failed'), conv='report:1', channel='report', frm='',
                 subject='Process error check', body='The nightly export failed at 02:00.')
        # one task because TRIAGE says this idea IS that task - shown it as open work - not an exact-title check (2026-10-08)
        seen = []
        b = mail(s, 'i1', brain('task', same_as=a['task_id'], title='Nightly export failed', seen=seen), conv='report:140:idea:export',
                 channel='assistant', frm='', subject='Idea', body='The nightly export failed - worth a look.')
        self.assertIn(f"TQ-{a['task_id']:04d}", seen[-1]['usr'])
        self.assertEqual(b['task_id'], a['task_id'])
        self.assertEqual(len(s.list_tasks()), 1)


class LaterStepFailedTests(unittest.TestCase):
    def test_a_message_that_reached_its_task_is_not_retriaged_when_a_later_step_breaks(self):
        s = MemoryStore()
        mid = s.add_message({'ExternalId': 'x1', 'Channel': 'email', 'FromEmail': 'erin@northwind.example', 'Subject': 'Fix the export',
                             'BodyText': 'please fix', 'ConversationId': 'c9', 'SentAt': '2026-09-25 09:00:00', 'Status': 'triaging'})
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'task', 'Status': 'open'}, 't')
        def boom(store, msg, **k):
            store.place_message(msg['_mid'], tid, 'routed')          # triaged onto its task...
            raise RuntimeError('agent start failed')                  # ...then a later step broke
        with mock.patch.object(ingest, 'ingest_message', side_effect=boom):
            ingest.drain(s)
        m = s.get_message(mid)
        self.assertEqual((m['Status'], m['TaskId']), ('routed', tid))
        self.assertTrue(any('a later step failed' in c['Body'] for c in s.list_comments(tid)))
        self.assertEqual(s.stranded_triage_failures(10), [])


if __name__ == '__main__':
    unittest.main()
