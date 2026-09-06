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

    def test_a_reply_on_a_closed_tasks_thread_does_not_reopen_it(self):
        s = MemoryStore()
        a = mail(s, 'a', 'Please approve the refund for Jane Doe.', 'AAQk-thread-A')
        s.update_task(a['task_id'], {'Status': 'done'}, 'owner')
        thanks = mail(s, 'b', 'Thanks, all done.', 'AAQk-thread-A', llm=FYI, at='2026-09-06 10:00:00')
        self.assertEqual(thanks['status'], 'filed'); self.assertEqual(s.get_task(a['task_id'])['Status'], 'done')
        self.assertEqual(s.get_message(thanks['message_id'])['ConversationId'], 'AAQk-thread-A')   # the chain keeps it
        again = mail(s, 'c', 'Actually the refund bounced, can you re-issue it?', 'AAQk-thread-A', at='2026-09-06 11:00:00')
        self.assertEqual(again['status'], 'created'); self.assertNotEqual(again['task_id'], a['task_id'])
        self.assertEqual(s.get_task(a['task_id'])['Status'], 'done')

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


if __name__ == '__main__':
    unittest.main()
