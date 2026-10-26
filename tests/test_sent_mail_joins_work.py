"""A mail the owner sends from their mail app about work already open goes on that work's task, so the reply follows it there
(2026-10-26, the owner: "why didn't triage add the co-insurance question into the deep dive rec task? can email add itself to
task that I opened?"). A task made by hand has no thread and no sender, and a "Docs" subject shares no word with its title:
the promise in the owner's mail became a task of its own, the thread became that task's, and the other side's question about
the work joined it. The sent-words judge is now shown the open work the message may be part of - what touches it, and what the
owner was working just before sending - and its `task` answer decides. The model is a stub (tests/sentjudge_fixture.py)."""
import json, re, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import context, ingest, sentjudge
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
        self.assertFalse(any('Kept on this task' in c['Body'] for c in s.list_comments(tid)))

    def test_a_message_already_on_a_task_is_its_threads(self):
        s = _store(); _work(s, 1); mid = _sent(s)
        home = s.create_task({'Title': 'Docs for Ray', 'Status': 'open'}, 't')
        s._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (home, mid))
        self.assertEqual(sentjudge.open_work(s, s.get_message(mid)), [])

    def test_only_open_work_from_the_hours_before_is_shown(self):
        s = _store(); now = _work(s, 1); _work(s, 6); _work(s, 2, status='done')
        self.assertEqual([w['tid'] for w in context.worked_before(s, _ago(0))], [now])
        self.assertEqual(context.worked_before(s, 'not a stamp'), [])


def _day(days): return (datetime.now() + timedelta(days=days)).strftime('%Y-%m-%d')


class PromiseDayTests(unittest.TestCase):
    """The owner, 2026-10-26: "if date promised then due date otherwise just a note"."""
    def _land(self, due=None, task_due=None):
        s = _store(); tid = _work(s, 1); mid = _sent(s)
        if task_due: s.update_task(tid, {'DueAt': task_due}, 'owner')
        judged(s, {'the data is compiled': {'promise': True, 'what': 'finish verifying the accounts', 'due': due, 'task': tid}})
        self.assertEqual(s.get_message(mid)['TaskId'], tid)
        return s.get_task(tid), next(c['Body'] for c in s.list_comments(tid) if 'finish verifying' in c['Body'])

    def test_a_promised_day_is_the_tasks_due_day(self):
        t, note = self._land(due=_day(3))
        self.assertEqual(str(t['DueAt'])[:10], _day(3))
        self.assertIn(f"by {_day(3)} - set as this task's due date", note)

    def test_no_day_is_only_a_note(self):
        t, note = self._land()
        self.assertFalse(t.get('DueAt'))
        self.assertNotIn('due', note)

    def test_an_earlier_due_day_is_never_pushed_out(self):
        t, note = self._land(due=_day(5), task_due=_day(2))
        self.assertEqual(str(t['DueAt'])[:10], _day(2))
        self.assertIn(f'the task stays due {_day(2)}', note)

    def test_a_later_due_day_is_brought_in(self):
        t, _ = self._land(due=_day(2), task_due=_day(6))
        self.assertEqual(str(t['DueAt'])[:10], _day(2))


def triage_brain(seen):
    """Triage, scripted to answer from its evidence: same_as the hand-made task only when it was shown it."""
    def llm(system, user, **k):
        seen.append(user)
        tid = next((int(x) for x in re.findall(r'"tid": (\d+)', user)), None) if 'started this thread' in user else None
        return json.dumps({'intent': 'task', 'kind': 'task', 'why': 'scripted', 'title': 'Explain the payer figures', 'summary': 's',
                           **({'same_as': tid} if tid else {})})
    return llm


def _reply(s, conv, llm, ext='r1'):
    with mock.patch.object(ingest, '_spawn'):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': RAY, 'from_name': 'Ray Colton',
                                         'conversation_id': conv, 'subject': 'RE: Docs', 'sent_at': _ago(0),
                                         'body': 'Row 17 on the by-payer tab - is that amount still collectable?'}, llm=llm)


class OwnerStartedThreadTests(unittest.TestCase):
    """The owner, 2026-10-26: "Yes" - a reply on a thread they started from their mail app sees the work they were in."""
    def test_a_reply_joins_the_hand_made_task_the_owner_was_working(self):
        s = _store(); tid = _work(s, 2); _sent(s, hours_ago=1); seen = []
        self.assertEqual(ingest.identity_route(s, {'conversation_id': 'c-docs', 'channel': 'email'})['decision'], 'create')  # no task yet: triage decides
        got = _reply(s, 'c-docs', triage_brain(seen))
        self.assertIn('you started this thread', seen[-1])
        self.assertEqual(got['task_id'], tid)
        # ...and the next reply follows the thread there
        r = ingest.identity_route(s, {'conversation_id': 'c-docs', 'channel': 'email'})
        self.assertEqual((r['decision'], r['task_id']), ('attach', tid))

    def test_an_unrelated_reply_still_makes_its_own_task(self):
        s = _store(); tid = _work(s, 2); seen = []
        s.add_message({'ExternalId': 'theirs', 'ConversationId': 'c-other', 'Channel': 'email', 'SourceName': ME, 'Subject': 'Docs',
                       'FromName': 'Ray Colton', 'FromEmail': RAY, 'SentAt': _ago(1), 'BodyText': 'Hello', 'Status': 'filed'})
        got = _reply(s, 'c-other', triage_brain(seen))                    # a thread THEY started: the owner's work is not shown
        self.assertNotIn('started this thread', seen[-1])
        self.assertNotEqual(got['task_id'], tid)
        self.assertTrue(got['task_id'])


if __name__ == '__main__': unittest.main()
