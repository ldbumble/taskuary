""""The triage is always wrong even after memory."

What that looked like in one database: the same Teams chat opened a task six times in a week,
and the owner deleted it six times. The verdict they pressed each time - "Not a task, just
conversation" - is the one built to teach nothing about the SENDER, which is right (one click
must not silence a colleague); but it also taught nothing about the CONVERSATION, so the very
next burst on the same chat went to the classifier as if nothing had ever been said.

These tests walk the three verdicts an owner gives on a triaged item, and what the NEXT
message on that conversation does afterwards:
  - not a task            -> the rest of the conversation is filed (an email thread for life,
                             a chat for CHAT_VERDICT_HOURS - a chat id is a relationship)
  - task, but no agent    -> reclassified to a reply: the follow-up joins the task, no coder
  - sent to a coding agent -> the follow-up joins that task; nothing re-triages it
"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server, store as store_mod
from taskuary.store import MemoryStore

c = TestClient(server.app)
_shared = None


def setUpModule():
    """A store of our own: the app-wide one is shared by every API test in the run, and the
    router attaches on text similarity - an open task another test left behind would absorb
    these messages and every assertion here would be about that task instead."""
    global _shared
    _shared, server.store = server.store, MemoryStore()
    server.store.set_setting('coder_auto_enabled', '0', 'test')


def tearDownModule():
    server.store = _shared
CHAT = 'teams:19:vp-security-chat@thread.v2'
# every test speaks about something different: the router attaches on subject + body
# similarity, so two tests sharing one wording would join each other's tasks
ASK = {'mfa': ('VPN Helpdesk', "Can someone reset John's MFA? He is locked out of the app again."),
       'vpn': ('VPN certificate renewals', 'The VPN certificate expires Friday - who is renewing it?'),
       'pct': ('Collection %', 'Why does the percentage stay the same if I exclude those payers?'),
       'badge': ('Badge printer offline', 'The badge printer on floor 2 is offline again, can someone look?'),
       'wifi': ('Guest wifi password', 'What is the guest wifi password this month?')}


def stamp(**kw): return (datetime.now() + timedelta(**kw)).isoformat(sep=' ', timespec='seconds')


def llm_saying(intent, calls=None):
    """A classifier that always answers `intent`, counting how often it was asked."""
    def f(sys_, usr_, **kw):
        if calls is not None: calls.append(usr_)
        return '{"intent": "%s", "why": "test"}' % intent
    return f


def push(i, conv=CHAT, sent_at=None, intent='task', calls=None, about='mfa', **over):
    subject, text = ASK[about]
    body = {'external_id': f'vp-{conv}-{i}', 'channel': 'teams', 'conversation_id': conv, 'from_name': 'Sam Okafor',
            'subject': subject, 'body': text, 'sent_at': sent_at or stamp(), **over}
    with mock.patch('taskuary.server._llm', return_value=llm_saying(intent, calls)):
        return c.post('/api/ingest/push', json=body).json()


def feed_row(mid): return next(r for r in c.get('/api/feed').json()['data'] if r['MessageId'] == mid)


class NotATaskTests(unittest.TestCase):
    def test_the_next_burst_on_the_chat_is_filed_without_asking_the_classifier(self):
        first = push(1)
        self.assertEqual(first['status'], 'created')
        # the timeline button: "Not a task - just conversation" (server.file_message)
        self.assertTrue(c.post(f"/api/messages/{first['message_id']}/file").json()['taskDeleted'])
        asked = []
        second = push(2, sent_at=stamp(hours=2), calls=asked)
        self.assertEqual((second['status'], second['task_id']), ('filed', None))
        self.assertEqual(asked, [])                                  # decided, not advised
        row = feed_row(second['message_id'])
        self.assertEqual(row['NeedsYou'], 0)
        self.assertIn('already ruled on this conversation', row['RouteReason'])
        self.assertIn('nothing to do', row['RouteReason'])

    def test_a_chat_verdict_covers_the_episode_not_the_relationship(self):
        conv = CHAT + '-episode'
        first = push(1, conv=conv, about='vpn')
        c.post(f"/api/messages/{first['message_id']}/file")
        asked = []
        later = push(2, conv=conv, about='vpn', sent_at=stamp(hours=store_mod.CHAT_VERDICT_HOURS + 6), calls=asked)
        self.assertEqual(later['status'], 'created')                 # a new ask days later is a new episode
        self.assertEqual(len(asked), 1)

    def test_an_email_thread_stays_ruled_for_life(self):
        conv = 'AAQkADNj-email-thread-1'
        first = push(1, conv=conv, about='pct', channel='email', from_email='dwhitfield@client.example')
        c.post(f"/api/messages/{first['message_id']}/file")
        asked = []
        later = push(2, conv=conv, about='pct', channel='email', from_email='dwhitfield@client.example', subject='Re: Collection %',
                     sent_at=stamp(days=10), calls=asked)
        self.assertEqual((later['status'], later['task_id']), ('filed', None))
        self.assertEqual(asked, [])

    def test_the_task_level_not_a_task_rules_the_thread_even_when_it_learns_nothing(self):
        """Teams messages carry no email address, so the task-level verdict used to write
        nothing at all - not even for the chat it was given on."""
        conv = CHAT + '-tasklevel'
        first = push(1, conv=conv, about='badge')
        r = c.post(f"/api/tasks/{first['task_id']}/not-a-task", json={'learn': False}).json()
        self.assertEqual((r['ok'], r['learned']), (True, None))
        asked = []
        second = push(2, conv=conv, about='badge', sent_at=stamp(hours=1), calls=asked)
        self.assertEqual((second['status'], second['task_id']), ('filed', None))
        self.assertEqual(asked, [])
        self.assertIn('not a task - Badge printer offline', feed_row(second['message_id'])['RouteReason'])

    def test_another_conversation_from_the_same_people_is_still_triaged(self):
        first = push(1, conv=CHAT + '-a', about='wifi')
        c.post(f"/api/messages/{first['message_id']}/file")
        asked = []
        self.assertEqual(push(1, conv=CHAT + '-b', about='wifi', calls=asked)['status'], 'created')
        self.assertEqual(len(asked), 1)


class TaskWithoutAgentTests(unittest.TestCase):
    """Triage called it coding work; the owner says it only needs an answer."""
    def test_reclassified_to_reply_the_follow_up_joins_the_task_and_no_coder_starts(self):
        conv = 'AAQkADNj-payroll-thread'
        with mock.patch.object(server.hub_term, 'start_on_task') as coder:
            first = push(1, conv=conv, channel='email', from_email='gw@corp.com', subject='Payroll file imports',
                         body='The payroll import crashes with KeyError: EmployeeId on every file, please fix it.')
            self.assertEqual(first['status'], 'created')
            tid = first['task_id']
            self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Kind'], 'coding')
            with mock.patch('taskuary.learn.learn_from') as learned:
                self.assertEqual(c.patch(f'/api/tasks/{tid}', json={'Kind': 'reply'}).status_code, 200)
            self.assertIn('over-reached', learned.call_args[0][1])
            pend = [x for x in c.get('/api/reviews', params={'status': 'pending'}).json()['data'] if x['TaskId'] == tid]
            self.assertEqual(len(pend), 1)
            server.store.set_setting('coder_auto_enabled', '1', 'test')
            try:
                asked = []
                second = push(2, conv=conv, channel='email', from_email='gw@corp.com', subject='Re: Payroll file imports',
                              body='Any update on this?', sent_at=stamp(hours=3), calls=asked)
            finally:
                server.store.set_setting('coder_auto_enabled', '0', 'test')
            self.assertEqual((second['status'], second['task_id']), ('attached', tid))
            self.assertEqual(asked, [])                              # a thread with a task needs no re-triage
            coder.assert_not_called()                                # a reply task never gets an agent


class SentToAgentTests(unittest.TestCase):
    """Triage filed it; the owner sends it to a coding agent from the timeline."""
    def test_the_promoted_message_becomes_the_task_the_thread_then_joins(self):
        conv = 'AAQkADNj-process-check'
        first = push(1, conv=conv, channel='email', from_email='reports@vendor.com', subject='Process Check - FAILED',
                     body='Pex export failed: LedgerBalance mismatch on 3 rows', intent='fyi')
        self.assertEqual((first['status'], first['task_id']), ('filed', None))
        server.store.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude"}')
        with mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's1'}) as coder, \
             mock.patch('taskuary.learn.learn_from') as learned:
            r = c.post(f"/api/messages/{first['message_id']}/dispatch", json={'agent': 'coder'}).json()
        tid = r['taskId']
        self.assertEqual(coder.call_args[0][1:3], (tid, 'coder'))
        self.assertIn('under-reached', learned.call_args[0][1])      # the miss in the other direction is a lesson too
        asked = []
        second = push(2, conv=conv, channel='email', from_email='reports@vendor.com', subject='Re: Process Check - FAILED',
                      body='Re-ran it, still 3 rows off', sent_at=stamp(hours=1), calls=asked)
        self.assertEqual((second['status'], second['task_id']), ('attached', tid))
        self.assertEqual(asked, [])
        self.assertEqual(feed_row(second['message_id'])['MsgStatus'], 'routed')


if __name__ == '__main__':
    unittest.main()
