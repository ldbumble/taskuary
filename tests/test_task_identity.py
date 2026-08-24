"""A TQ-ref is an identity, not a slot.

The reported failure, reconstructed from the audit log: TQ-0034 was created at 08:19 from a
Resident Refund thread and an agent opened a session on it. At 10:11 the owner said "not our
task" and it was deleted - but the pty kept running, still holding task_id 34. SQLite hands a
deleted rowid straight back, so by 12:38 that id belonged to a scheduled report, and the
timeline showed the orphaned refund agent as "the agent working Process Error Check". Sending
the report to a coder did nothing at all: start_on_task found a live session for task 34 and
returned early.

Two faults, tested separately: the id came back, and the session outlived its task.
"""
import unittest
from unittest import mock

from taskuary.store import MemoryStore


class IdReuseTests(unittest.TestCase):
    def test_a_deleted_task_never_hands_its_number_to_the_next_one(self):
        s = MemoryStore()
        a = s.create_task({'Title': 'Resident refund thread'}, 'router')
        s.audit('task', a, 'create', 'router')
        s.delete_task(a)
        b = s.create_task({'Title': 'Process Error Check'}, 'owner')
        self.assertGreater(b, a)

    def test_the_number_keeps_climbing_across_a_whole_morning_of_deletions(self):
        """Three tasks wore TQ-0034 in one morning. Deleting the tail must not rewind."""
        s, seen = MemoryStore(), []
        for i in range(6):
            t = s.create_task({'Title': f't{i}'}, 'router')
            s.audit('task', t, 'create', 'router')
            seen.append(t)
            s.delete_task(t)                       # delete the newest every time - the worst case
        self.assertEqual(seen, sorted(set(seen)))  # strictly increasing, no repeats

    def test_an_id_issued_before_this_process_started_is_still_off_limits(self):
        """The table forgets a deleted tail; the audit log and the high-water mark do not, and
        either one alone is enough to keep the next id above it."""
        s = MemoryStore()
        s.audit('task', 34, 'create', 'router')      # a task that existed and is long gone
        self.assertGreater(s.create_task({'Title': 'new work'}, 'owner'), 34)

    def test_ordinary_creation_is_still_dense(self):
        s = MemoryStore()
        ids = [s.create_task({'Title': f't{i}'}, 'o') for i in range(4)]
        self.assertEqual(ids, list(range(ids[0], ids[0] + 4)))   # no gaps when nothing is deleted


class SessionOutlivesTaskTests(unittest.TestCase):
    """"Not a task" reads as a kill. It has to BE one."""
    def _client(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        return TestClient(server.app), server

    def test_not_a_task_closes_the_agent_working_it(self):
        c, server = self._client()
        tid = server.store.create_task({'Title': 'refund thread', 'Kind': 'coding'}, 'o')
        with mock.patch.object(server.hub_term, 'for_task', return_value={'sid': 'S1'}), \
             mock.patch.object(server.hub_term, 'close', return_value=True) as close:
            c.post(f'/api/tasks/{tid}/not-a-task', json={'learn': False})
        close.assert_called_once_with('S1')
        self.assertIsNone(server.store.get_task(tid))

    def test_not_our_task_closes_it_too(self):
        c, server = self._client()
        tid = server.store.create_task({'Title': 'refund thread', 'Kind': 'coding'}, 'o')
        mid = server.store.add_message({'Channel': 'email', 'Subject': 'Re: Resident Refund',
                                        'FromEmail': 'a@b.c', 'TaskId': tid, 'ExternalId': 'nm1'})
        with mock.patch.object(server.hub_term, 'for_task', return_value={'sid': 'S2'}), \
             mock.patch.object(server.hub_term, 'close', return_value=True) as close:
            c.post(f'/api/messages/{mid}/not-mine', json={'scope': 'sender'})
        close.assert_called_once_with('S2')

    def test_nothing_to_do_here_closes_it_too(self):
        c, server = self._client()
        tid = server.store.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')
        mid = server.store.add_message({'Channel': 'teams', 'Subject': 'chat', 'TaskId': tid,
                                        'ExternalId': 'file1'})
        with mock.patch.object(server.hub_term, 'for_task', return_value={'sid': 'S3'}), \
             mock.patch.object(server.hub_term, 'close', return_value=True) as close:
            c.post(f'/api/messages/{mid}/file')
        close.assert_called_once_with('S3')

    def test_a_session_that_refuses_to_die_never_blocks_the_delete(self):
        """The task going away is the owner's decision; a stuck pty does not get a veto."""
        c, server = self._client()
        tid = server.store.create_task({'Title': 'stuck', 'Kind': 'coding'}, 'o')
        with mock.patch.object(server.hub_term, 'for_task', return_value={'sid': 'S4'}), \
             mock.patch.object(server.hub_term, 'close', side_effect=OSError('pty is wedged')):
            r = c.post(f'/api/tasks/{tid}/not-a-task', json={'learn': False})
        self.assertEqual(r.status_code, 200)
        self.assertIsNone(server.store.get_task(tid))

    def test_a_task_with_no_session_deletes_exactly_as_before(self):
        c, server = self._client()
        tid = server.store.create_task({'Title': 'quiet', 'Kind': 'general'}, 'o')
        with mock.patch.object(server.hub_term, 'for_task', return_value=None), \
             mock.patch.object(server.hub_term, 'close') as close:
            c.post(f'/api/tasks/{tid}/not-a-task', json={'learn': False})
        close.assert_not_called()
        self.assertIsNone(server.store.get_task(tid))


if __name__ == '__main__':
    unittest.main()
