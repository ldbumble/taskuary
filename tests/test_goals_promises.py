"""The owner's own promise, judged from sent mail, is a task on them with its date (spec 2026-10-12, build step 1).
The Advisor stops raising a promise that is already a row: one thing, one place."""
import unittest
from datetime import datetime, timedelta

from taskuary import assistant
from taskuary.store import MemoryStore
from tests.sentjudge_fixture import judged

ME, GAIL = 'alex@northwind.example', 'gail@northwind.example'
def _ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
def _day(days=0): return (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')


def _store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('owner_email', ME, 't')
    return s


N = [0]
def _theirs(s, body, days, conv):
    N[0] += 1
    return s.add_message({'ExternalId': f't{N[0]}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME, 'Subject': 'Revised budget',
                          'FromName': 'Gail Moreno', 'FromEmail': GAIL, 'SentAt': _ago(days), 'BodyText': body, 'Status': 'filed'})


def _mine(s, body, days, conv):
    N[0] += 1
    return s.add_message({'ExternalId': f'm{N[0]}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME, 'Subject': 'Re: Revised budget',
                          'FromName': 'Alex Doyle', 'FromEmail': ME, 'SentAt': _ago(days), 'BodyText': body, 'Status': 'context'})


class PromiseTaskTests(unittest.TestCase):
    def test_a_promise_becomes_one_task_once_and_delivery_closes_it(self):
        s = _store()
        _theirs(s, 'Can I have the revised budget?', 4, 'c1'); m1 = _mine(s, "I'll send the revised budget Friday", 3, 'c1')
        judged(s, {'revised budget Friday': {'promise': True, 'what': 'send the revised budget', 'due': _day(2)}})
        t = s.promise_task(m1)
        self.assertEqual((t['Title'], t['Status'], t['Assignee'], t['DueAt'], t['Source'], t['SourceRef']),
                         ('Send the revised budget', 'open', 'owner', _day(2), 'email', f'promise:{m1}'))
        self.assertEqual(s.task_for_promise(m1, 'send the revised budget', _day(2)), t['TaskId'])     # once
        _mine(s, 'Here is the revised budget, attached.', 1, 'c1')
        judged(s, {'attached': {'delivers': [f'm{m1}']}})
        self.assertEqual(s.get_task(t['TaskId'])['Status'], 'done')

    def test_a_promise_with_no_date_has_no_due_and_a_second_pass_makes_no_second_task(self):
        s = _store()
        _theirs(s, 'Can you sort the refund?', 4, 'c2'); m1 = _mine(s, 'Leave it with me', 3, 'c2')
        judged(s, {'Leave it with me': {'promise': True, 'what': 'sort the refund', 'due': None}})
        s.task_for_promise(m1, 'sort the refund', None)
        tasks = [t for t in s.list_tasks() if str(t.get('SourceRef') or '').startswith('promise:')]
        self.assertEqual(len(tasks), 1); self.assertIsNone(tasks[0]['DueAt'])

    def test_the_advisor_does_not_raise_a_promise_that_is_already_a_task(self):
        s = _store()
        _theirs(s, 'Can I have the revised budget?', 4, 'c3'); m1 = _mine(s, "I'll send the revised budget Friday", 3, 'c3')
        s.put_sent_verdict(m1, 'c3', False, True, 'send the revised budget', _day(-1), 'test')    # judged, no task yet
        self.assertEqual([c['kind'] for c in assistant.followups(s, 24, want=('promise',))], ['promise'])
        s.task_for_promise(m1, 'send the revised budget', _day(-1))
        self.assertEqual(assistant.followups(s, 24, want=('promise',)), [])


class PromiseContextTests(unittest.TestCase):
    """The review (2026-10-12): a promise task opened with a title and nothing else - no recipient, no thread."""
    def test_a_promise_task_names_who_and_carries_its_thread(self):
        s = _store()
        _theirs(s, 'Can I have the revised budget?', 4, 'c4'); m1 = _mine(s, "I'll send the revised budget Friday", 3, 'c4')
        judged(s, {'revised budget Friday': {'promise': True, 'what': 'send the revised budget', 'due': _day(2)}})
        t = s.promise_task(m1)
        self.assertIn('Gail', t['Summary']); self.assertIn('Revised budget', t['Summary'])
        self.assertEqual(t['Source'], 'email')
        self.assertEqual(s.get_message(m1)['TaskId'], t['TaskId'])
