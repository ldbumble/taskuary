"""Handing a task to a person works on any channel this install can send on.

It was email, or posting back into the task's own Teams chat, and nothing else - while the app has
been able to send on WhatsApp, Slack and Telegram for months. So "just send this to Gabi" meant
opening WhatsApp yourself, which is the app Taskuary exists to keep you out of.

The Teams-with-no-address case stays exactly as it was: that one posts into the conversation the
task came from, and needs no recipient.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server

c = TestClient(server.app)


def _task(title='ship the export'):
    return c.post('/api/tasks', json={'Title': title, 'Kind': 'coding'}).json()['taskId']


class HandingItToAPerson(unittest.TestCase):
    def test_a_channel_this_install_cannot_send_on_is_refused_in_words(self):
        tid = _task()
        with mock.patch('taskuary.outbound.can_reply', return_value=False), \
             mock.patch('taskuary.outbound.draft_handoff', return_value='here you go'):
            r = c.post(f'/api/tasks/{tid}/handoff', json={'to': 'gabi', 'channel': 'whatsapp', 'text': 'hi'})
        self.assertEqual(r.status_code, 422)
        self.assertIn('Connections', r.json()['detail'])

    def test_whatsapp_goes_out_the_same_road_a_report_takes(self):
        tid = _task()
        with mock.patch('taskuary.outbound.can_reply', return_value=True), \
             mock.patch('taskuary.outbound.send_out', return_value={'ok': True}) as send:
            r = c.post(f'/api/tasks/{tid}/handoff', json={'to': '15551234@s.whatsapp.net',
                                                          'channel': 'whatsapp', 'text': 'have a look'})
        self.assertEqual(r.status_code, 200, r.text)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1], 'whatsapp')
        self.assertEqual(send.call_args.args[2], '15551234@s.whatsapp.net')

    def test_email_still_uses_the_email_sender(self):
        tid = _task()
        with mock.patch('taskuary.outbound.send_email', return_value={'ok': True}) as send, \
             mock.patch('taskuary.outbound.send_out') as other:
            r = c.post(f'/api/tasks/{tid}/handoff', json={'to': 'dana@x.example', 'channel': 'email', 'text': 'fyi'})
        self.assertEqual(r.status_code, 200, r.text)
        send.assert_called_once()
        other.assert_not_called()

    def test_teams_with_no_address_still_posts_into_the_tasks_own_chat(self):
        """The case that needs no recipient - and the one that breaks if it is routed generically."""
        tid = _task()
        mid = server.store.add_message({'TaskId': tid, 'ExternalId': 'ho:1', 'ConversationId': 'teams:19:abc',
                                        'Channel': 'teams', 'SourceName': 'me', 'Subject': 'chat',
                                        'FromName': 'Jess', 'SentAt': '2026-09-01 10:00:00', 'BodyText': 'hi'})
        self.assertTrue(mid)
        with mock.patch('taskuary.outbound.send_teams', return_value={'ok': True}) as send:
            r = c.post(f'/api/tasks/{tid}/handoff', json={'channel': 'teams', 'text': 'done'})
        self.assertEqual(r.status_code, 200, r.text)
        send.assert_called_once()
        self.assertEqual(send.call_args.args[1], '19:abc')     # the chat id, not an address

    def test_handing_it_over_closes_the_task(self):
        """Somebody else owns it now: leaving the card open asks for a second decision."""
        tid = _task()
        with mock.patch('taskuary.outbound.can_reply', return_value=True), \
             mock.patch('taskuary.outbound.send_out', return_value={'ok': True}):
            c.post(f'/api/tasks/{tid}/handoff', json={'to': 'gabi', 'channel': 'whatsapp', 'text': 'yours'})
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Status'], 'done')

    def test_a_draft_never_sends_anything(self):
        tid = _task()
        with mock.patch('taskuary.outbound.draft_handoff', return_value='a drafted forward'), \
             mock.patch('taskuary.outbound.send_out') as send, \
             mock.patch('taskuary.outbound.send_email') as mail:
            r = c.post(f'/api/tasks/{tid}/handoff', json={'to': 'gabi', 'channel': 'whatsapp', 'draft_only': True})
        self.assertEqual(r.json()['draft'], 'a drafted forward')
        send.assert_not_called()
        mail.assert_not_called()


if __name__ == '__main__':
    unittest.main()
