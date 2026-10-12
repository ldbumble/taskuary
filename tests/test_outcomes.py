"""The outcome ledger (spec 2026-10-12, build step 2): what the app did, what the owner did next, what came of it."""
import json, unittest
from datetime import datetime, timedelta
from taskuary import outcomes
from taskuary.store import MemoryStore


def ago(days=0, hours=0): return (datetime.now() - timedelta(days=days, hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


class RecordTests(unittest.TestCase):
    def test_a_row_is_written_and_read_back_newest_first(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'x'}, 'owner')
        a = outcomes.record(s, 'task.closed', 'task', t, 'owner', facts={'how': 'close_from_assistant'})
        b = outcomes.record(s, 'agent.continued', 'task', t, 'owner', next_move='merge it')
        rows = outcomes.rows_for(s, 'task', t)
        self.assertEqual([r['Id'] for r in rows], [b, a])
        self.assertEqual((rows[0]['Kind'], rows[0]['NextMove'], rows[1]['Verdict']), ('agent.continued', 'merge it', None))
        self.assertEqual(rows[1]['FactsJson'], '{"how": "close_from_assistant"}')

    def test_an_unknown_kind_is_refused(self):
        with self.assertRaises(ValueError): outcomes.record(MemoryStore(), 'nonsense', 'task', 1)

    def test_settle_closes_a_row_once(self):
        s = MemoryStore()
        i = outcomes.record(s, 'promise.made', 'task', 1)
        outcomes.settle(s, i, 'delivered 2 days early', 'kept')
        self.assertEqual([r['Id'] for r in outcomes.open_rows(s)], [])
        r = outcomes.rows_for(s, 'task', 1)[0]
        self.assertEqual((r['Outcome'], r['Verdict']), ('delivered 2 days early', 'kept')); self.assertTrue(r['ResolvedAt'])
