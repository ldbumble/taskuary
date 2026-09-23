"""A chat app's "X sent a message" mail is the chat line again, not a second ask.

A Teams line opened a task, and an hour later the mail Teams sends about unread chats quoted that
same line - with no thread in common, so identity_route opened a second task for one question
(2026-09-23). The two share the words, from the same person, close together: that is what joins
them (ingest.echo_route), never a sender address or a subject pattern.
"""
import unittest
from unittest import mock

from taskuary import ingest
from taskuary.store import MemoryStore

ASK = lambda *a, **k: '{"intent": "task", "kind": "task", "why": "an ask", "relationship": "new"}'
LINE = 'Did you put the new rate in for this pay period? My start date was the 4th...'
NOTICE = ('This email was sent from outside of Northwind. Do not click links unless you know the content is safe.\n\n'
          + LINE + ' ‌ ‌ ‌ ‌\n\nHi,\n\nErin Blake sent a message in chat\n' + LINE
          + '\n\nReply in Teams\n\nThis email was sent from an unmonitored mailbox.')


def chat(s, body=LINE, who='Erin Blake', at='2026-09-23 00:42:28', ext='teams:1'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'teams', 'conversation_id': 'teams:19:erin',
                                         'from_name': who, 'from_email': 'erin@northwind.example', 'subject': f'Teams chat with {who}',
                                         'body': body, 'sent_at': at}, llm=ASK)


def notice(s, body=NOTICE, who='Erin Blake in Teams', at='2026-09-23 01:42:41', ext='graph:1'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'conversation_id': f'AAQk-{ext}',
                                         'from_name': who, 'from_email': 'no-reply@chat.example', 'subject': f'{who.split(" in ")[0]} sent a message',
                                         'body': body, 'sent_at': at}, llm=ASK)


class EchoTests(unittest.TestCase):
    def test_the_notification_mail_files_onto_the_chat_lines_task(self):
        s = MemoryStore()
        a = chat(s); b = notice(s)
        self.assertEqual((b['status'], b['task_id']), ('filed', a['task_id']))
        self.assertEqual(len(s.list_tasks()), 1)
        self.assertIsNone(s.pending_review(a['task_id']))          # never a reply drafted to a no-reply address
        self.assertIn('one message, two ways', s.message_routes(b['message_id'])[-1]['Reason'])

    def test_the_chat_line_after_its_notification_joins_the_mails_task(self):
        s = MemoryStore()
        b = notice(s, at='2026-09-23 00:40:00'); a = chat(s)
        self.assertEqual(a['task_id'], b['task_id'])
        self.assertEqual(len(s.list_tasks()), 1)

    def test_nothing_joins_without_all_three(self):
        cases = {'another person': dict(who='Gail Moreno in Teams', body=NOTICE.replace('Erin Blake', 'Gail Moreno')),
                 'other words': dict(body=NOTICE.replace(LINE, 'Can you send me last month\'s invoice list when you have a minute?')),
                 'a day apart': dict(at='2026-09-24 09:00:00')}
        for name, kw in cases.items():
            with self.subTest(name):
                s = MemoryStore()
                a = chat(s); b = notice(s, **kw)
                self.assertNotEqual(b['task_id'], a['task_id']); self.assertEqual(len(s.list_tasks()), 2)

    def test_a_short_line_is_said_too_often_to_identify_one_message(self):
        s = MemoryStore()
        a = chat(s, body='ok thanks!'); b = notice(s, body=NOTICE.replace(LINE, 'ok thanks!'))
        self.assertNotEqual(b.get('task_id'), a.get('task_id'))

    def test_a_closed_task_is_not_joined(self):
        s = MemoryStore()
        a = chat(s); s.update_task(a['task_id'], {'Status': 'done'}, 'owner')
        b = notice(s)
        self.assertNotEqual(b['task_id'], a['task_id'])


if __name__ == '__main__':
    unittest.main()
