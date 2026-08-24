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
    def test_prose_that_merely_mentions_deployment_is_not_coding(self):
        self.assertEqual(draft_task_fields({'subject': 'Teams chat with Mindy', 'body': JOB_SCOPE})['kind'], 'general')

    def test_one_soft_word_is_somebody_talking_about_their_week(self):
        for body in ("We had an error in judgement on the vendor call.",
                     "The deploy team is hiring two people this quarter.",
                     "My endpoint of the process is the monthly close."):
            self.assertEqual(draft_task_fields({'subject': 'chat', 'body': body})['kind'], 'general', body)

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

    def test_real_work_with_no_code_in_it_is_general_not_coding(self):
        """Chasing a vendor IS a task - it just has no repository, so no agent is dispatched."""
        f = draft_task_fields({'subject': 'March invoice', 'body': 'The vendor never sent it. Someone needs to chase them.'})
        self.assertEqual(f['kind'], 'general')


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

    def test_a_task_with_no_code_in_it_never_opens_a_coding_session(self):
        s, out, started = self._ingest('Teams chat with Mindy', JOB_SCOPE)
        self.assertEqual(started, [])                                  # nobody was dispatched
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'general')  # but it IS still a task

    def test_a_real_bug_report_still_reaches_the_coder(self):
        s, out, started = self._ingest('export down', 'The export is broken and the deploy failed.')
        self.assertEqual(len(started), 1)
        self.assertEqual(s.get_task(out['task_id'])['Kind'], 'coding')

    def test_the_route_line_stops_promising_an_agent_that_was_never_sent(self):
        s, out, _ = self._ingest('Teams chat with Mindy', JOB_SCOPE)
        reason = s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason']
        self.assertIn('no agent dispatched', reason)
        self.assertNotIn('sent to the coding agent', reason)


class HarmlessExitTests(unittest.TestCase):
    def test_filing_a_message_teaches_nothing_about_its_sender(self):
        """The whole point. "Not our task" writes a verdict that suppresses the sender - and on
        a channel with no address to key on it is written GLOBALLY. Getting one chat off the
        timeline must not cost you a colleague."""
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        mid = s.add_message({'Channel': 'teams', 'Subject': 'Teams chat', 'FromName': 'Mindy',
                             'BodyText': JOB_SCOPE, 'ExternalId': 'file-me', 'Status': 'filed'})
        before = len(s.list_memories())
        r = TestClient(server.app).post(f'/api/messages/{mid}/file')
        self.assertEqual(r.status_code, 200)
        self.assertEqual(len(s.list_memories()), before)        # nothing learned
        self.assertEqual(s.get_message(mid)['Status'], 'ignored')
        self.assertFalse(r.json()['taskDeleted'])

    def test_filing_also_removes_a_task_the_message_had(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = server.store
        tid = s.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')
        mid = s.add_message({'Channel': 'teams', 'Subject': 'Teams chat', 'TaskId': tid,
                             'BodyText': 'yes', 'ExternalId': 'file-me-2'})
        before = len(s.list_memories())          # server.store is shared - count, never assume 0
        r = TestClient(server.app).post(f'/api/messages/{mid}/file')
        self.assertTrue(r.json()['taskDeleted'])
        self.assertIsNone(s.get_task(tid))
        self.assertEqual(len(s.list_memories()), before)

    def test_filing_an_unknown_message_is_a_404_not_a_500(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        self.assertEqual(TestClient(server.app).post('/api/messages/999999/file').status_code, 404)


if __name__ == '__main__':
    unittest.main()
