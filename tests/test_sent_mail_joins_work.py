"""A mail the owner sends from their mail app about work already open goes on that work's task, so the reply follows it there
(2026-10-26, the owner: "why didn't triage add the co-insurance question into the deep dive rec task? can email add itself to
task that I opened?"). A task made by hand has no thread and no sender, and a "Docs" subject shares no word with its title:
the promise in the owner's mail became a task of its own, the thread became that task's, and the other side's question about
the work joined it. The sent-words judge is now shown the open work the message may be part of - what touches it, and what the
owner was working just before sending - and its `task` answer decides. The model is a stub (tests/sentjudge_fixture.py)."""
import unittest
from datetime import datetime, timedelta

from taskuary import context, sentjudge
from taskuary.ingest import identity_route
from taskuary.store import MemoryStore
from tests.sentjudge_fixture import judged

ME, RAY = 'alex@northwind.example', 'ray@vendor.example'
def _ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def _store():
    s = MemoryStore()
    for k in ('calendar_enabled', 'coding_auto_enabled', 'learn_enabled'): s.set_setting(k, '0', 't')
    s.set_setting('owner_email', ME, 't')
    return s


def _work(s, hours_ago, status='in_progress'):
    """The owner's own task, made by hand: no thread, no sender - and the owner in it `hours_ago`."""
    tid = s.create_task({'Title': 'Reconcile the Q3 receivables for the east region', 'Summary': 'Tie revenue to cash month by month and '
                         'build the collections workbook by facility and payer.', 'Kind': 'coding', 'Status': status,
                         'Source': 'manual', 'Assignee': 'owner'}, 'owner')
    s._exec('INSERT INTO audit (EntityType,EntityId,Action,Actor,ActorType,CreatedAt) VALUES (?,?,?,?,?,?)',
            ('task', tid, 'continue-session', 'owner', 'human', _ago(hours_ago)))
    return tid


def _sent(s, conv='c-docs', hours_ago=1):
    return s.add_message({'ExternalId': f'sent-{conv}', 'ConversationId': conv, 'Channel': 'email', 'SourceName': ME, 'Subject': 'Docs',
                          'FromName': 'Alex Doyle', 'FromEmail': ME, 'SentAt': _ago(hours_ago), 'Status': 'context',
                          'BodyText': 'Ray - the data is compiled and in the shared folder; still verifying a few accounts, done Sunday.'})


SAID = {'the data is compiled': {'promise': True, 'what': 'finish verifying the accounts'}}


class SentMailJoinsWorkTests(unittest.TestCase):
    def test_the_judge_is_shown_the_work_the_owner_was_in(self):
        s = _store(); tid = _work(s, 3); mid = _sent(s); calls = []
        judged(s, {k: v | {'task': tid} for k, v in SAID.items()}, calls)
        self.assertIn(f'OPEN WORK (this message is on no task yet): [task {tid}] "Reconcile the Q3 receivables', calls[0])
        self.assertIn('you were working on it 2 hours before you sent this', calls[0])
        # ...and its answer puts the mail on that task: no second task for one job, and the promise said on the task
        self.assertEqual(s.get_message(mid)['TaskId'], tid)
        self.assertIsNone(s.promise_task(mid))
        self.assertTrue(any('finish verifying the accounts' in c['Body'] for c in s.list_comments(tid)))
        self.assertEqual(s._one('SELECT RoutedBy FROM route WHERE MessageId=? ORDER BY RouteId DESC', (mid,))['RoutedBy'], 'sentjudge')
        # the other side's question on the thread follows it to the work's task
        r = identity_route(s, {'conversation_id': 'c-docs', 'channel': 'email', 'from_email': RAY, 'subject': 'RE: Docs'})
        self.assertEqual((r['decision'], r['task_id']), ('attach', tid))

    def test_work_it_was_not_shown_is_never_joined(self):
        s = _store(); far = _work(s, 9); mid = _sent(s)                     # in it nine hours before: not shown
        judged(s, {k: v | {'task': far} for k, v in SAID.items()})
        self.assertNotEqual(s.get_message(mid)['TaskId'], far)
        self.assertEqual(s.promise_task(mid)['Title'], 'Finish verifying the accounts')   # the promise is its own task, as before

    def test_its_null_keeps_the_promise_a_task_of_its_own(self):
        s = _store(); tid = _work(s, 1); mid = _sent(s)
        judged(s, SAID)
        self.assertEqual(s.get_message(mid)['TaskId'], s.promise_task(mid)['TaskId'])
        self.assertFalse(any('kept on this task' in c['Body'] for c in s.list_comments(tid)))

    def test_a_message_already_on_a_task_is_its_threads(self):
        s = _store(); _work(s, 1); mid = _sent(s)
        home = s.create_task({'Title': 'Docs for Ray', 'Status': 'open'}, 't')
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (home, mid))
        self.assertEqual(sentjudge.open_work(s, s.get_message(mid)), [])

    def test_only_open_work_from_the_hours_before_is_shown(self):
        s = _store(); now = _work(s, 1); _work(s, 6); _work(s, 2, status='done')
        self.assertEqual([w['tid'] for w in context.worked_before(s, _ago(0))], [now])
        self.assertEqual(context.worked_before(s, 'not a stamp'), [])


if __name__ == '__main__': unittest.main()
