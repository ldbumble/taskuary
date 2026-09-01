"""A coding agent belongs on a coding task, and nothing else.

The reported failure: a Teams message about someone's job scope ("I own the deployment
system, production/uptime, and support") became work with a CLI session opened on a
repository. Two separate faults let that happen - the keyword that called prose a bug, and
the dispatch gate that asked "is this a reply?" instead of "is this code?". Both are here.
And the way out was worse than the way in: with no task on the message, the only exit
offered wrote a durable verdict against the sender.
"""
import unittest
from unittest import mock

from taskuary.ingest import ingest_message
from taskuary.routing import draft_task_fields
from taskuary.store import MemoryStore

# verbatim shape of the message that started this
JOB_SCOPE = ("Not really velocity. I think the bigger change is what the job has absorbed. I own AR "
             "end to end now, plus the pieces underneath the whole app: security and access control, "
             "the deployment system, production/uptime, and support. None of those were specifically "
             "assigned to me. I have a whole document outlining the scope and responsibilities.")


class KindTests(unittest.TestCase):
    """The keyword scan's "I cannot tell" answer is `task` - the owner's own list. It used to be
    `general`, which meant the same thing until general came to mean the assistant's chat; a scan
    that could not read the message has no business opening a conversation about it."""
    def test_prose_that_merely_mentions_deployment_is_not_coding(self):
        self.assertEqual(draft_task_fields({'subject': 'Teams chat with Priya', 'body': JOB_SCOPE})['kind'], 'task')

    def test_one_soft_word_is_somebody_talking_about_their_week(self):
        for body in ("We had an error in judgement on the vendor call.",
                     "The deploy team is hiring two people this quarter.",
                     "My endpoint of the process is the monthly close."):
            self.assertEqual(draft_task_fields({'subject': 'chat', 'body': body})['kind'], 'task', body)

    def test_two_soft_words_together_are_a_report(self):
        f = draft_task_fields({'subject': 'export', 'body': 'The nightly export is broken and the deploy failed.'})
        self.assertEqual(f['kind'], 'coding')

    def test_one_hard_signal_is_enough_on_its_own(self):
        for body in ('Traceback (most recent call last):\n  File "app/run.py", line 3',
                     'see https://github.com/o/r/pull/18 when you can',
                     'the importer returns a 500 error every night',
                     'please look at services/export.py'):
            self.assertEqual(draft_task_fields({'subject': 'x', 'body': body})['kind'], 'coding', body)

    def test_a_question_is_still_a_reply(self):
        self.assertEqual(draft_task_fields({'subject': 'T&E', 'body': 'Can you send me the numbers?'})['kind'], 'reply')

    def test_real_work_with_no_code_in_it_is_a_task_not_coding(self):
        """Chasing a vendor IS a task - it just has no repository, so no agent is dispatched."""
        f = draft_task_fields({'subject': 'March invoice', 'body': 'The vendor never sent it. Someone needs to chase them.'})
        self.assertEqual(f['kind'], 'task')


class DispatchGateTests(unittest.TestCase):
    """The gate used to be "not a reply", so EVERY other kind - including the ones the task
    pickers never even offered - opened a coding session."""
    def _ingest(self, subject, body):
        """intent_classify_enabled=0 is the app's own "everything is a task" path - no AI
        needed, and it puts the KIND heuristic and the dispatch gate under the microscope,
        which is the pair that failed."""
        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 'o')
        s.set_setting('intent_classify_enabled', '0', 'o')
        with mock.patch('taskuary.ingest._spawn') as spawn:
            out = ingest_message(s, {'external_id': 'x1', 'channel': 'teams', 'subject': subject,
                                     'body': body, 'from_name': 'Someone', 'from_email': 'a@b.c'})
        started = [c for c in spawn.call_args_list if getattr(c[0][0], '__name__', '') == '_auto_code']
        return s, out, started

    def test_a_task_with_no_code_in_it_waits_on_your_list(self):
        """The owner's rule as it now stands (2026-08-30): almost everything goes to the agent,
        and the one exception is work that is clearly not a coding job. `kind` carries that
        verdict - here from the keyword scan, because this path has triage switched off."""
        s, out, started = self._ingest('Teams chat with Priya', JOB_SCOPE)
        self.assertEqual(started, [])                                    # no session bought
        # `task`, not `general`: general is the assistant's chat now, and a keyword scan that
        # could not tell what this is should not open one
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'task')     # and labelled honestly

    def test_a_real_bug_report_still_reaches_the_coder(self):
        s, out, started = self._ingest('export down', 'The export is broken and the deploy failed.')
        self.assertEqual(len(started), 1)
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'coding')

    def test_the_route_line_says_which_way_it_went(self):
        s, _out, _ = self._ingest('Teams chat with Priya', JOB_SCOPE)
        self.assertIn('yours to do', s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])
        s2, _out2, _ = self._ingest('export down', 'The export is broken and the deploy failed.')
        self.assertIn('sent to the coding agent', s2._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])


class HarmlessExitTests(unittest.TestCase):
    """The timeline's "Not a task" is the SAME verdict as the task list's, so it teaches the same
    thing (owner, 2026-08-30). What made the old exit dangerous is still barred: it never mutes a
    sender - that is "Skip this sender" - and it writes nothing at all when a channel gives it no
    address and no topic to key a note to, which is where a verdict against everyone came from."""
    def test_filing_never_mutes_the_sender(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        c = TestClient(server.app)
        mid = s.add_message({'Channel': 'email', 'Subject': 'Quarterly newsletter roundup', 'FromEmail': 'news@vendor.com',
                             'BodyText': JOB_SCOPE, 'ExternalId': 'file-me', 'Status': 'filed'})
        before = len(c.get('/api/policies').json()['data'])
        r = c.post(f'/api/messages/{mid}/file')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(c.get('/api/policies').json()['data']), before)     # no ignore rule
        self.assertIn('NOT A TASK', next(m['Note'] for m in s.list_memories()
                                         if m['MemoryId'] == r.json()['memoryId']))
        self.assertEqual(s.get_message(mid)['Status'], 'ignored')
        self.assertFalse(r.json()['taskDeleted'])

    def test_a_message_with_nothing_to_key_on_teaches_nothing(self):
        """A Teams chat carries no address, and "Teams chat" is not a topic. A note keyed to
        neither is a verdict against everyone, so none is written - the thread is still ruled."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        before = len(s.list_memories())
        mid = s.add_message({'Channel': 'teams', 'Subject': 'chat', 'FromName': 'Priya',
                             'BodyText': JOB_SCOPE, 'ExternalId': 'file-me-teams', 'Status': 'filed'})
        r = TestClient(server.app).post(f'/api/messages/{mid}/file')
        self.assertIsNone(r.json()['memoryId'])
        self.assertEqual(len(s.list_memories()), before)

    def test_one_off_dismissal_explicitly_teaches_nothing(self):
        """The Timeline's lighter exit must stay different from its neighboring Memory verdict."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        before = len(s.list_memories())
        mid = s.add_message({'Channel': 'email', 'Subject': 'A real topic that could be learned',
                             'FromEmail': 'updates@vendor.com', 'BodyText': 'one-off note',
                             'ExternalId': 'dismiss-once', 'Status': 'filed'})
        r = TestClient(server.app).post(f'/api/messages/{mid}/file', json={'learn': False})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(r.json()['memoryId'])
        self.assertEqual(len(s.list_memories()), before)
        self.assertEqual(s.get_message(mid)['Status'], 'ignored')

    def test_filing_also_removes_a_task_the_message_had(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        tid = s.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')
        mid = s.add_message({'Channel': 'teams', 'Subject': 'chat', 'TaskId': tid,
                             'BodyText': 'yes', 'ExternalId': 'file-me-2'})
        r = TestClient(server.app).post(f'/api/messages/{mid}/file')
        self.assertTrue(r.json()['taskDeleted'])
        self.assertIsNone(s.get_task(tid))

    def test_both_doors_teach_the_same_verdict(self):
        """The task list's button and the timeline's must not drift apart again."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        c = TestClient(server.app)
        notes = []
        for i, door in enumerate(('task', 'message')):
            tid = s.create_task({'Title': 'Vendor renewal reminder', 'Kind': 'general'}, 'o')
            mid = s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Vendor renewal reminder',
                                 'FromEmail': 'billing@vendor.com', 'BodyText': 'your plan renews',
                                 'ExternalId': f'both-doors-{i}', 'Status': 'routed'})
            r = c.post(f'/api/tasks/{tid}/not-a-task' if door == 'task' else f'/api/messages/{mid}/file').json()
            memid = r['learned']['memory_id'] if door == 'task' else r['memoryId']
            notes.append(next(m for m in s.list_memories() if m['MemoryId'] == memid))
        self.assertEqual(notes[0]['Scope'], notes[1]['Scope'])
        self.assertEqual(notes[0]['ScopeKey'], notes[1]['ScopeKey'])
        self.assertEqual(notes[0]['Note'], notes[1]['Note'])

    def test_filing_an_unknown_message_is_a_404_not_a_500(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.assertEqual(TestClient(server.app).post('/api/messages/999999/file').status_code, 404)


if __name__ == '__main__':
    unittest.main()
