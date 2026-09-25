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

    def test_a_task_it_was_never_shown_joins_nothing(self):
        s = MemoryStore()
        first = mail(s, 'a', brain('task'), conv='c1')
        other = mail(s, 'b', brain('task', same_as=9999, title='Something else entirely'), conv='c2',
                     subject='Printer on floor 3', body='The printer is jammed.', frm='omar@northwind.example')
        self.assertEqual(other['status'], 'created'); self.assertNotEqual(other['task_id'], first['task_id'])


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
        b = mail(s, 'i1', brain('task', title='Nightly export failed'), conv='report:140:idea:export', channel='assistant', frm='',
                 subject='Idea', body='The nightly export failed - worth a look.')
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
