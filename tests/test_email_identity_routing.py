"""Email joins a task by conversation identity, never by resemblance (PW-016, PW-017, PW-019).

The router scored a new mail against every open task on subject words, sender and body cosine, so
two unrelated mails with the same subject line joined one task, a reply whose References header
was rewritten could land on a look-alike, and a bounce joined the task its text resembled (the
2026-09-03 wrong-thread reply). Now a mail joins the task ITS OWN conversation already belongs to -
Graph's conversationId, IMAP's References/Message-ID, a tracker item's own id - and nothing else:
no conversation identity means new work, however similar the words. The chain outlives the task:
a reply on a closed task's thread is stored on that conversation and evaluated afresh, and the
closed task stays closed unless triage opens new work.
"""
import unittest
from unittest import mock

from taskuary import ingest
from taskuary.store import MemoryStore

TASK = lambda *a, **k: '{"intent": "task", "kind": "task", "why": "an ask"}'
FYI = lambda *a, **k: '{"intent": "fyi", "why": "thanks"}'


def mail(s, ext, body, conv, subject='Resident Refund Request - Doe, Jane', frm='hudson@regency.example', llm=TASK, at='2026-09-06 09:00:00'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': 'Hudson',
                                         'conversation_id': conv, 'subject': subject, 'body': body, 'sent_at': at}, llm=llm)


class IdentityTests(unittest.TestCase):
    def test_identical_subjects_on_different_threads_stay_separate(self):
        s = MemoryStore()
        a = mail(s, 'a', 'Please approve the refund for Jane Doe, paperwork attached.', 'AAQk-thread-A')
        b = mail(s, 'b', 'Please approve the refund for Jane Doe, second copy of the paperwork attached.', 'AAQk-thread-B')
        self.assertEqual((a['status'], b['status']), ('created', 'created'))
        self.assertNotEqual(a['task_id'], b['task_id'])

    def test_a_genuine_reply_reuses_its_conversations_task(self):
        s = MemoryStore()
        a = mail(s, 'a', 'Please approve the refund for Jane Doe.', 'AAQk-thread-A')
        b = mail(s, 'b', 'Any news?', 'AAQk-thread-A', subject='Re: something else entirely', frm='another@regency.example')
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']))

    def test_no_conversation_identity_means_new_work_however_alike(self):
        s = MemoryStore()
        a = mail(s, 'a', 'Please approve the refund for Jane Doe, paperwork attached.', 'AAQk-thread-A')
        b = mail(s, 'b', 'Please approve the refund for Jane Doe, paperwork attached.', None)
        self.assertEqual(b['status'], 'created'); self.assertNotEqual(b['task_id'], a['task_id'])
        self.assertIn('no conversation identity', s.message_routes(b['message_id'])[-1]['Reason'])

    def test_the_same_ask_from_the_same_sender_joins_the_open_task_it_already_has(self):
        """A daily machine alert gets a new conversation every morning, so the thread check finds
        nothing to join: TQ-0510 and TQ-0511, one title, one sender, one day apart (2026-09-14)."""
        # ...and it is TRIAGE that says so: it is shown the sender's open task (open_work) and names it - an exact-title check
        # used to join them over its answer (2026-10-08: no code in front of the AI)
        s = MemoryStore()
        seen = []
        def gateway(system, user, **k):
            seen.append(user)
            same = ', "same_as": 1' if len(seen) > 1 else ''
            return ('{"intent": "task", "kind": "task", "why": "the gateway is deprecated", '
                    '"title": "Upgrade deprecated Power BI gateway"' + same + '}')
        frm = 'no-reply-powerbi@microsoft.com'
        a = mail(s, 'a', 'Refresh succeeded with critical warnings.', 'AAQk-day-1', frm=frm, llm=gateway)
        b = mail(s, 'b', 'Refresh succeeded with critical warnings.', 'AAQk-day-2', frm=frm, llm=gateway,
                 at='2026-09-07 09:00:00')
        self.assertIn('TQ-0001', seen[-1], 'the open task from this sender is in front of triage')
        self.assertEqual((a['status'], b['status']), ('created', 'routed'))
        self.assertEqual(b['task_id'], a['task_id'])
        self.assertIn('the same as', s.message_routes(b['message_id'])[-1]['Reason'])

    def test_a_repeat_is_matched_on_the_triaged_ask_not_the_subject_line(self):
        """The subject is the resemblance that joined two unrelated refunds; a verdict with no title
        of its own has said nothing to match on, so the mails stay apart however alike they read."""
        s = MemoryStore()
        a = mail(s, 'a', 'Please approve the refund for Jane Doe.', 'AAQk-thread-A')
        b = mail(s, 'b', 'Please approve the refund for Jane Doe.', 'AAQk-thread-B')
        self.assertNotEqual(b['task_id'], a['task_id'])

    def test_a_repeat_never_reopens_a_closed_task(self):
        s = MemoryStore()
        named = lambda *a, **k: '{"intent": "task", "kind": "task", "why": "an ask", "title": "Send the July file"}'
        a = mail(s, 'a', 'The July file please.', 'AAQk-thread-A', llm=named)
        s.update_task(a['task_id'], {'Status': 'done'}, 'owner')
        b = mail(s, 'b', 'The July file please.', 'AAQk-thread-B', llm=named, at='2026-09-07 09:00:00')
        self.assertEqual(b['status'], 'created'); self.assertNotEqual(b['task_id'], a['task_id'])

    def test_a_reply_on_a_closed_tasks_thread_joins_it_and_reopens_it_only_when_it_needs_you(self):
        """The thread's closed task is still its task (the owner, 2026-09-25): a thanks is filed on it and it stays
        closed; a line that needs the owner reopens THAT task - never a second one for the same thread."""
        s = MemoryStore()
        a = mail(s, 'a', 'Please approve the refund for Jane Doe.', 'AAQk-thread-A')
        s.update_task(a['task_id'], {'Status': 'done'}, 'owner')
        thanks = mail(s, 'b', 'Thanks, all done.', 'AAQk-thread-A', llm=FYI, at='2026-09-06 10:00:00')
        self.assertEqual(thanks['status'], 'filed'); self.assertEqual(s.get_task(a['task_id'])['Status'], 'done')
        self.assertEqual(s.get_message(thanks['message_id'])['ConversationId'], 'AAQk-thread-A')   # the chain keeps it
        self.assertEqual(thanks['task_id'], a['task_id'])                                          # ...on its own task
        again = mail(s, 'c', 'Actually the refund bounced, can you re-issue it?', 'AAQk-thread-A', at='2026-09-06 11:00:00')
        self.assertEqual((again['status'], again['task_id']), ('attached', a['task_id']))
        self.assertEqual(s.get_task(a['task_id'])['Status'], 'open')                                 # reopened
        self.assertTrue(any(c['Body'].startswith('Reopened') for c in s.list_comments(a['task_id'])))

    def test_a_tracker_item_keeps_its_own_identity(self):
        s = MemoryStore()
        with mock.patch.object(ingest, '_spawn'):
            a = ingest.ingest_message(s, {'external_id': 'gh:o/r#7', 'channel': 'github', 'conversation_id': 'gh:o/r#7', 'subject': 'o/r#7 importer crash',
                                          'body': '[issue by kai - association: NONE]\nthe importer crashes on empty files', 'from_email': 'kai@users.noreply.github.com',
                                          'no_auto': True}, llm=TASK)
            b = ingest.ingest_message(s, {'external_id': 'gh:o/r#7:c2', 'channel': 'github', 'conversation_id': 'gh:o/r#7', 'subject': 'o/r#7 importer crash',
                                          'body': '[comment by kai]\nalso on files with a BOM', 'from_email': 'kai@users.noreply.github.com', 'no_auto': True}, llm=TASK)
            c = ingest.ingest_message(s, {'external_id': 'gh:o/r#8', 'channel': 'github', 'conversation_id': 'gh:o/r#8', 'subject': 'o/r#8 importer crash',
                                          'body': '[issue by kai - association: NONE]\nthe importer crashes on empty files too', 'from_email': 'kai@users.noreply.github.com',
                                          'no_auto': True}, llm=TASK)
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']))
        self.assertEqual(c['status'], 'created'); self.assertNotEqual(c['task_id'], a['task_id'])

    def test_two_copies_of_one_mail_in_flight_at_once_make_one_task(self):
        """Two copies of one mail 3 s apart (walk 11): each was judged while the other was still being judged, each found no task on
        the thread, and each made one - two tasks and two agents asking the same question."""
        import threading, time
        s, out = MemoryStore(), []
        def slow(*a, **k): time.sleep(0.3); return TASK()
        def one(ext): out.append(ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': 'alex@northwind.example',
                                                            'from_name': 'Alex Doyle', 'conversation_id': 'bridge-monthly spend',
                                                            'subject': 'Monthly spend', 'body': 'Erin - the monthly spend by vendor, please?'}, llm=slow))
        with mock.patch.object(ingest, '_spawn'):
            ts = [threading.Thread(target=one, args=(e,)) for e in ('api:1', 'api:2')]
            for t in ts: t.start()
            for t in ts: t.join()
        self.assertEqual(len({o['task_id'] for o in out}), 1, out)

    def test_a_reply_lands_on_the_task_whose_mail_it_answers(self):
        """A thread with two tasks (walk 11): the owner's question went out on the first; the sender then wrote a new ask on the thread,
        which triage made a second task. Her answer to the question joined the newest task of the thread - the one that asked never heard it."""
        import json
        s = MemoryStore()
        first = s.create_task({'Title': 'Monthly spend by vendor', 'Kind': 'task', 'Status': 'open'}, 'owner')
        second = s.create_task({'Title': 'Trainly quote', 'Kind': 'task', 'Status': 'open'}, 'owner')
        conv = 'AAQk-spend'
        s.add_message({'ExternalId': 'sent-q', 'ConversationId': conv, 'Channel': 'email', 'TaskId': first, 'Status': 'context', 'Direction': 'out',
                       'FromEmail': 'alex@northwind.example', 'Subject': 'Monthly spend', 'BodyText': 'Which vendor grew fastest?',
                       'MailMetaJson': json.dumps({'mid': '<q1@northwind.example>'})})
        s.add_message({'ExternalId': 'in-quote', 'ConversationId': conv, 'Channel': 'email', 'TaskId': second, 'Status': 'routed',
                       'FromEmail': 'erin@northwind.example', 'Subject': 'Re: Monthly spend', 'BodyText': 'Also - here is the Trainly quote.',
                       'MailMetaJson': json.dumps({'mid': '<e2@northwind.example>', 'refs': ['<q1@northwind.example>']})})
        answer = {'conversation_id': conv, 'channel': 'email', 'from_email': 'erin@northwind.example', 'subject': 'Re: Monthly spend',
                  'mail_meta': {'refs': ['<q1@northwind.example>']}}
        self.assertEqual(ingest.identity_route(s, answer)['task_id'], first)
        # ...and a mail answering her own quote mail, or naming nothing of ours, stays where the thread is
        self.assertEqual(ingest.identity_route(s, {**answer, 'mail_meta': {'refs': ['<q1@northwind.example>', '<e2@northwind.example>']}})['task_id'], second)
        self.assertEqual(ingest.identity_route(s, {**answer, 'mail_meta': {}})['task_id'], second)


if __name__ == '__main__':
    unittest.main()
