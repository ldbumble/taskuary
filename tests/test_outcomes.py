"""The outcome ledger (spec 2026-10-12, build step 2): what the app did, what the owner did next, what came of it."""
import json, unittest
from datetime import datetime, timedelta
from taskuary import autoreply, outcomes
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


class ResolveTests(unittest.TestCase):
    def _thread(self, s, cid='c1'):
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'AP cutover', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                       'SentAt': ago(days=9), 'BodyText': 'Still Thursday?', 'Status': 'filed'})
        return s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Re: AP cutover', 'FromEmail': 'alex@northwind.example',
                              'FromName': 'Alex Doyle', 'SentAt': ago(days=8), 'BodyText': 'Thursday works.', 'Status': 'context'})

    def test_a_reply_nobody_wrote_back_on_is_settled_after_its_window(self):
        s = MemoryStore(); t = s.create_task({'Title': 'AP cutover', 'Status': 'done'}, 'owner'); mid = self._thread(s)
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c1', 'mid': mid}, at=ago(days=8))
        self.assertEqual(outcomes.resolve(s), 1)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'settled')

    def test_more_rounds_after_a_reply_are_unsettled_and_counted(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Payworth billing'}, 'owner'); mid = self._thread(s, 'c2')
        for d in (6, 4): s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Re: billing', 'FromEmail': 'billing@vendor.example',
                                       'FromName': 'Payworth', 'SentAt': ago(days=d), 'BodyText': 'And the PO number?', 'Status': 'filed'})
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c2', 'mid': mid}, at=ago(days=8))
        outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'unsettled: 2 more')

    def test_an_auto_reply_is_not_a_round(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner'); mid = self._thread(s, 'c3')
        s.add_message({'ConversationId': 'c3', 'Channel': 'email', 'Subject': 'Automatic reply: Re: AP cutover', 'FromEmail': 'erin@northwind.example',
                       'FromName': 'Erin Blake', 'SentAt': ago(days=7), 'BodyText': 'I am out of the office until Monday.', 'Status': autoreply.STATUS})   # the connector's mark, never the subject
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c3', 'mid': mid}, at=ago(days=8))
        outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'settled')

    def test_a_closed_task_resolves_after_its_window(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'done'}, 'owner')
        i = outcomes.record(s, 'task.closed', 'task', t, at=ago(days=3))
        self.assertEqual(outcomes.resolve(s), 0)                                   # inside the window: nothing yet
        s._exec('UPDATE outcome SET At=? WHERE Id=?', (ago(days=8), i))
        outcomes.resolve(s); self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'held')
        t2 = s.create_task({'Title': 'y', 'Status': 'open'}, 'owner')
        outcomes.record(s, 'task.closed', 'task', t2, at=ago(days=8)); outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t2)[0]['Verdict'], 'reopened')

    def test_a_stop_takes_the_owners_next_move_from_the_later_row(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', facts={'pr': True}, at=ago(hours=30))
        outcomes.record(s, 'agent.continued', 'task', t, next_move='merge it', at=ago(hours=29))
        outcomes.resolve(s)
        r = s._one('SELECT * FROM outcome WHERE Id=?', (i,))
        self.assertEqual((r['Verdict'], r['NextMove']), ('continued', 'merge it'))
        j = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', at=ago(days=3)); outcomes.resolve(s)
        self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (j,))['Verdict'], 'left')

    def test_a_promise_is_kept_late_or_late(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Send the budget', 'DueAt': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d'), 'Status': 'done'}, 'owner')
        i = outcomes.record(s, 'promise.made', 'task', t, at=ago(days=9)); s._exec('UPDATE task SET ClosedAt=? WHERE TaskId=?', (ago(days=1), t))
        outcomes.resolve(s); self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (i,))['Verdict'], 'kept late')
        t2 = s.create_task({'Title': 'Send the deck', 'DueAt': (datetime.now() - timedelta(days=10)).strftime('%Y-%m-%d'), 'Status': 'open'}, 'owner')
        j = outcomes.record(s, 'promise.made', 'task', t2, at=ago(days=20)); outcomes.resolve(s)
        self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (j,))['Verdict'], 'late')

    def test_an_ignored_sender_who_later_became_a_task_is_regret(self):
        s = MemoryStore()
        i = outcomes.record(s, 'sender.ignored', 'policy', 1, facts={'from': 'news@vendor.example'}, at=ago(days=61))
        outcomes.resolve(s); self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (i,))['Verdict'], 'no regret')
        j = outcomes.record(s, 'sender.ignored', 'policy', 2, facts={'from': 'ray@vendor.example'}, at=ago(days=61))
        t = s.create_task({'Title': 'from ray'}, 'owner')
        s.add_message({'ConversationId': 'c9', 'Channel': 'email', 'Subject': 'Quote', 'FromEmail': 'ray@vendor.example', 'SentAt': ago(days=30), 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
        outcomes.resolve(s); self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (j,))['Verdict'], 'regret')


class SweepTests(unittest.TestCase):
    def test_the_sweep_runs_once_a_day(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'done'}, 'owner')
        outcomes.record(s, 'task.closed', 'task', t, at=ago(days=8))
        self.assertEqual(outcomes.sweep_if_due(s), 1)
        outcomes.record(s, 'task.closed', 'task', t, at=ago(days=8))
        self.assertIsNone(outcomes.sweep_if_due(s))                                 # swept today already
        self.assertEqual(outcomes.sweep_if_due(s, now=datetime.now() + timedelta(days=1)), 1)


class DoorsTests(unittest.TestCase):
    def test_closing_a_task_from_the_assistant_records_it(self):
        from taskuary import concierge
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        concierge.close_task(s, t, 'owner')
        r = outcomes.rows_for(s, 'task', t)[0]
        self.assertEqual((r['Kind'], r['Actor'], json.loads(r['FactsJson'])['how']), ('task.closed', 'owner', 'close_from_assistant'))

    def test_a_promise_task_records_its_making_and_its_delivery(self):
        s = MemoryStore()
        mid = s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=2), 'BodyText': 'x', 'Status': 'context'})
        t = s.task_for_promise(mid, 'send the budget', (datetime.now() + timedelta(days=2)).strftime('%Y-%m-%d'))
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Kind'], 'promise.made')
        s.put_sent_verdict(mid, 'c1', False, True, 'send the budget', None, 'test'); s.deliver_promise(mid, mid)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'kept')

    def test_a_continue_with_no_words_records_an_empty_move(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        outcomes.record(s, 'agent.continued', 'task', t, next_move=None, facts={'door': 'continue-session'})
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['NextMove'], '')


class EvidenceTests(unittest.TestCase):
    def test_resolved_rows_become_evidence_lines_with_their_ids(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Export job'}, 'owner')
        i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', facts={'pr': True}, at=ago(hours=30))
        outcomes.record(s, 'agent.continued', 'task', t, next_move='merge it', at=ago(hours=29)); outcomes.resolve(s)
        lines = outcomes.evidence(s, ago(days=30))
        self.assertTrue(lines[0].startswith(f'out{i}: ') or lines[1].startswith(f'out{i}: '))
        self.assertTrue(any('"merge it"' in l and 'coder stopped' in l for l in lines))

    def test_reflection_gathers_the_ledger_and_the_graph_resolves_out_ids(self):
        from taskuary import learn, learnedgraph
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'done'}, 'owner')
        i = outcomes.record(s, 'task.closed', 'task', t, at=ago(days=8)); outcomes.resolve(s)
        self.assertIn('WHAT CAME OF ACTIONS', learn.gather(s, ago(days=30)))
        self.assertIn(f'out{i}', learn.gather(s, ago(days=30)))
        self.assertEqual(learnedgraph._EV.match(f'out{i}').group(1), 'out')
