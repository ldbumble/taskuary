""""The triage is always wrong even after memory."

What that looked like in one database: the same Teams chat opened a task six times in a week,
and the owner deleted it six times. The verdict they pressed each time - "Not a task, just
conversation" - is the one built to teach nothing about the SENDER, which is right (one click
must not silence a colleague); but it also taught nothing about the CONVERSATION, so the very
next burst on the same chat went to the classifier as if nothing had ever been said.

These tests walk the three verdicts an owner gives on a triaged item, and what the NEXT
message on that conversation does afterwards:
  - not a task            -> the rest of an email THREAD is filed (same thread, same topic).
                             A CHAT carries nothing forward: a room is a relationship, and
                             "nothing to do here" is about the line it was said on. That
                             verdict still reaches the classifier as evidence.
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
ASK = {'northwind': ('VPN Helpdesk', "Can someone reset John's MFA? He is locked out of the app again."),
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


def push(i, conv=CHAT, sent_at=None, intent='task', calls=None, about='northwind', **over):
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
        # ...and the NEXT line in that chat is judged on its own merits. It used to be filed
        # unread for a day, so "I just remembered..." never reached the funnel (2026-08-31).
        self.assertEqual(second['status'], 'created')
        self.assertEqual(len(asked), 1)                              # advised, not decided

    def test_a_chat_ruling_covers_nobody_else_and_not_the_person_either(self):
        """The support chat is a ROOM. Richard's "Thank you" was filed as nothing to do - which
        says nothing about Ivan's request, and nothing about Richard's NEXT one either."""
        conv = CHAT + '-room'
        first = push(1, conv=conv, about='vpn', from_name='Richard Spencer')
        c.post(f"/api/messages/{first['message_id']}/file")
        asked = []
        other = push(2, conv=conv, about='badge', from_name='Ivan Stanley', sent_at=stamp(hours=3), calls=asked)
        self.assertEqual(other['status'], 'created')
        same = push(3, conv=conv, about='vpn', from_name='Richard Spencer', sent_at=stamp(hours=4), calls=asked)
        self.assertNotEqual(same['status'], 'filed')                 # ...and Richard is not muted either
        self.assertGreaterEqual(len(asked), 1)

    def test_a_chat_verdict_decides_nothing_about_the_next_line(self):
        """Not an hour later, not a day later, not ever: a room is not a topic."""
        conv = CHAT + '-episode'
        first = push(1, conv=conv, about='vpn')
        c.post(f"/api/messages/{first['message_id']}/file")
        for hours in (1, 26):
            later = push(hours + 1, conv=conv, about='vpn', sent_at=stamp(hours=hours))
            # it may open a task or join the one already open - what it must never be is FILED
            # unread because of something the owner said about an earlier line
            self.assertNotEqual(later['status'], 'filed', f'{hours}h later')

    def test_an_email_thread_stays_ruled_for_life(self):
        conv = 'AAQkADNj-email-thread-1'
        first = push(1, conv=conv, about='pct', channel='email', from_email='dwhitfield@client.example')
        c.post(f"/api/messages/{first['message_id']}/file")
        asked = []
        later = push(2, conv=conv, about='pct', channel='email', from_email='dwhitfield@client.example', subject='Re: Collection %',
                     sent_at=stamp(days=10), calls=asked)
        self.assertEqual((later['status'], later['task_id']), ('filed', None))
        self.assertEqual(asked, [])

    def test_the_task_level_not_a_task_still_writes_the_verdict_down(self):
        """It records the ruling (and used to write nothing at all for a chat) - it just no
        longer DECIDES the next line of that chat."""
        conv = CHAT + '-tasklevel'
        first = push(1, conv=conv, about='badge')
        r = c.post(f"/api/tasks/{first['task_id']}/not-a-task", json={'learn': False}).json()
        self.assertEqual((r['ok'], r['learned']), (True, None))
        ruled = store_mod  # keep the import used
        asked = []
        second = push(2, conv=conv, about='badge', sent_at=stamp(hours=1), calls=asked)
        self.assertEqual(second['status'], 'created')
        self.assertEqual(len(asked), 1)

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
            # the follow-up IS judged now - what a reply on an open task is, is triage's call (the
            # owner, 2026-09-03) - and a verdict of work leaves it attached, with no agent on a reply task
            self.assertEqual(len(asked), 1)
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
        self.assertEqual(len(asked), 1)                              # judged, and it says there is still work
        self.assertEqual(feed_row(second['message_id'])['MsgStatus'], 'routed')


if __name__ == '__main__':
    unittest.main()
