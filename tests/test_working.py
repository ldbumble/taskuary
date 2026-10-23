""""Is it working?" (the owner, 2026-10-22): the app's calls - a draft, a triage verdict, an agent's result - counted against what the
owner did next, over 7 and 30 days. Rows are written the way the app writes them; the numbers are read back."""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import outcomes, server, working
from taskuary.store import MemoryStore

NOW = datetime(2026, 10, 22, 12, 0, 0)
def ago(days): return (NOW - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')


class NumbersTests(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def sent(self, rid, verb, days=1): outcomes.record(self.s, 'reply.sent', 'task', rid, facts={'review': rid, 'verb': verb}, at=ago(days))

    def test_drafts_as_drafted_edited_or_redrafted(self):
        self.sent(1, 'approve'); self.sent(2, 'approve'); self.sent(3, 'edit'); self.sent(4, 'approve'); self.sent(5, 'edit', days=20)
        self.s.audit('review', 4, 'redraft', 'owner')                 # redrafted, then sent as the second draft stood
        self.s.audit('review', 9, 'redraft', 'owner')                 # a redraft never sent counts for nothing
        self.assertEqual(working.numbers(self.s, 7, NOW)['drafts'], {'sent': 4, 'unedited': 2, 'edited': 1, 'redrafted': 1})
        self.assertEqual(working.numbers(self.s, 30, NOW)['drafts'], {'sent': 5, 'unedited': 2, 'edited': 2, 'redrafted': 1})

    def test_triage_verdicts_and_the_ones_the_owner_overturned(self):
        for mid in (10, 11, 12): self.s.add_route(mid, None, 'create', None, 'triage: yours to do', [], 'triage')
        self.s.add_route(12, None, 'attach', None, 'triage: same thread', [], 'triage')      # one message, one verdict counted
        self.s.add_route(13, None, 'ignore', None, 'policy', [], 'policy')                    # a rule is not triage's call
        self.s.add_route(14, None, 'create', None, 'triage: old', [], 'triage')
        self.s._exec('UPDATE route SET CreatedAt=?', (ago(1),))                               # stamped against NOW, not the clock
        self.s._exec('UPDATE route SET CreatedAt=? WHERE MessageId=14', (ago(20),))
        self.s.add_correction({'OpId': 'op1', 'MessageId': 11, 'Verdict': 'todo', 'Change': 'fyi'})
        self.s.add_correction({'OpId': 'op2', 'MessageId': 11, 'Verdict': 'todo', 'Change': 'review'})   # corrected twice: one call overturned
        self.s.add_correction({'OpId': 'op3', 'MessageId': 14, 'Verdict': 'fyi', 'Change': 'todo'})
        self.assertEqual(working.numbers(self.s, 7, NOW)['triage'], {'verdicts': 3, 'overturned': 1})
        self.assertEqual(working.numbers(self.s, 30, NOW)['triage'], {'verdicts': 4, 'overturned': 2})

    def test_agent_results_accepted_continued_or_waiting(self):
        outcomes.record(self.s, 'agent.stopped', 'task', 1, at=ago(2)); outcomes.record(self.s, 'task.closed', 'task', 1, at=ago(1))
        outcomes.record(self.s, 'agent.stopped', 'task', 2, at=ago(2)); outcomes.record(self.s, 'agent.continued', 'task', 2, at=ago(2))
        outcomes.record(self.s, 'task.closed', 'task', 2, at=ago(1))                       # closed after it was sent on: it was continued
        outcomes.record(self.s, 'agent.stopped', 'task', 3, at=ago(1))
        outcomes.record(self.s, 'task.closed', 'task', 4, at=ago(1))                       # closed with no agent result: not counted
        self.assertEqual(working.numbers(self.s, 7, NOW)['agents'], {'results': 3, 'accepted': 1, 'continued': 1, 'waiting': 1})

    def test_an_empty_home_is_all_zeros(self):
        n = working.numbers(self.s, 7, NOW)
        self.assertEqual((n['days'], n['drafts']['sent'], n['triage']['verdicts'], n['agents']['results']), (7, 0, 0, 0))

    def test_the_endpoint_gives_both_windows(self):
        with mock.patch.object(server, 'store', self.s):
            r = TestClient(server.app).get('/api/working')
        self.assertEqual(r.status_code, 200)
        self.assertEqual([w['days'] for w in r.json()['windows']], [7, 30])


if __name__ == '__main__': unittest.main()
