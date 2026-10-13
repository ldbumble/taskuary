"""The outcome ledger (spec 2026-10-12, build step 2): what the app did, what the owner did next, what came of it."""
import json, unittest
from types import SimpleNamespace
from unittest import mock
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


def _thread(s, cid='c1'):
    s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'AP cutover', 'FromEmail': 'erin@northwind.example', 'FromName': 'Erin Blake',
                   'SentAt': ago(days=9), 'BodyText': 'Still Thursday?', 'Status': 'filed'})
    return s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Re: AP cutover', 'FromEmail': 'alex@northwind.example',
                          'FromName': 'Alex Doyle', 'SentAt': ago(days=8), 'BodyText': 'Thursday works.', 'Status': 'context'})


class ResolveTests(unittest.TestCase):

    def test_a_reply_nobody_wrote_back_on_is_settled_after_its_window(self):
        s = MemoryStore(); t = s.create_task({'Title': 'AP cutover', 'Status': 'done'}, 'owner'); mid = _thread(s)
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c1', 'mid': mid}, at=ago(days=8))
        self.assertEqual(outcomes.resolve(s), 1)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'settled')

    def test_more_rounds_after_a_reply_are_unsettled_and_counted(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Payworth billing'}, 'owner'); mid = _thread(s, 'c2')
        for d in (6, 4): s.add_message({'ConversationId': 'c2', 'Channel': 'email', 'Subject': 'Re: billing', 'FromEmail': 'billing@vendor.example',
                                       'FromName': 'Payworth', 'SentAt': ago(days=d), 'BodyText': 'And the PO number?', 'Status': 'filed'})
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c2', 'mid': mid}, at=ago(days=8))
        outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'unsettled: 2 more')

    def test_an_auto_reply_is_not_a_round(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner'); mid = _thread(s, 'c3')
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
        self.assertEqual((r['Kind'], r['Actor'], json.loads(r['FactsJson'])['from']), ('task.closed', 'owner', 'open'))

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


class FixPassTests(unittest.TestCase):
    """The review's fix pass (2026-10-12): rows that would have taught reflection a false habit."""
    def _session(self, s, tid):
        return SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd='C:/x', agent='coder', label='coder', argv=['claude'], last=1.0,
                               ext_id='', started=ago(hours=1), typed=[], files=lambda: [], tail=lambda n=3: [], idle=lambda: 0.0,
                               witness=SimpleNamespace(note=lambda n: None), store=s, bg={})

    def test_a_stop_is_one_open_row_however_many_turns_end_and_the_pane_prompt_settles_it(self):
        from taskuary import hooks
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner'); sess = self._session(s, t)
        for _ in range(3): hooks._events(sess, {'hook_event_name': 'Stop', 'last_assistant_message': ''})
        self.assertEqual(len([r for r in outcomes.rows_for(s, 'task', t) if r['Kind'] == 'agent.stopped']), 1)
        hooks._events(sess, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'merge it'})
        r = outcomes.rows_for(s, 'task', t)[0]
        self.assertEqual((r['Kind'], r['Verdict'], r['NextMove']), ('agent.stopped', 'continued', 'merge it'))
        hooks._events(sess, {'hook_event_name': 'Stop', 'last_assistant_message': ''})          # a new stretch: a new row
        self.assertEqual(len([r for r in outcomes.rows_for(s, 'task', t) if r['Kind'] == 'agent.stopped']), 2)

    def test_a_wordless_continue_says_so_and_invents_no_words(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        i = outcomes.record(s, 'agent.stopped', 'task', t, 'agent:coder', at=ago(hours=2))
        outcomes.record(s, 'agent.continued', 'task', t, next_move=None, at=ago(hours=1)); outcomes.resolve(s)
        r = s._one('SELECT * FROM outcome WHERE Id=?', (i,))
        self.assertEqual((r['Verdict'], r['NextMove']), ('continued', ''))
        line = next(l for l in outcomes.evidence(s, ago(days=1)) if l.startswith(f'out{i}: '))
        self.assertIn('no words', line); self.assertNotIn('"continued"', line)

    def test_any_road_that_closes_a_task_writes_one_row_and_a_close_that_did_not_close_writes_none(self):
        from taskuary import concierge
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        s.update_task(t, {'Status': 'done'}, 'owner')                                   # the Done button, a batch, a chat: any road
        s.update_task(t, {'Status': 'done'}, 'owner')                                   # closed again: no second row
        rows = [r for r in outcomes.rows_for(s, 'task', t) if r['Kind'] == 'task.closed']
        self.assertEqual([(r['Actor'], json.loads(r['FactsJson'])['from']) for r in rows], [('owner', 'open')])
        t2 = s.create_task({'Title': 'y'}, 'owner'); concierge.close_task(s, t2, 'owner')
        self.assertEqual(len([r for r in outcomes.rows_for(s, 'task', t2) if r['Kind'] == 'task.closed']), 1)
        t3 = s.create_task({'Title': 'z'}, 'owner'); s.update_task(t3, {'Status': 'waiting'}, 'agent:coder')   # a self-close that drafted a reply
        self.assertEqual(outcomes.rows_for(s, 'task', t3), [])

    def test_a_delivered_promise_is_its_own_row_not_a_close(self):
        s = MemoryStore()
        mid = s.add_message({'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Budget', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(days=2), 'BodyText': 'x', 'Status': 'context'})
        t = s.task_for_promise(mid, 'send the budget', None)
        s.put_sent_verdict(mid, 'c1', False, True, 'send the budget', None, 'test'); s.deliver_promise(mid, mid)
        self.assertEqual([r['Kind'] for r in outcomes.rows_for(s, 'task', t)], ['promise.made'])

    def test_a_ledger_failure_never_reaches_the_door(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        with mock.patch.object(s, '_exec', side_effect=RuntimeError('database is locked')):
            self.assertEqual(outcomes.record(s, 'task.closed', 'task', t), 0)
        with self.assertRaises(ValueError): outcomes.record(s, 'nonsense', 'task', t)

    def test_a_reply_with_no_thread_is_unknown_and_not_evidence(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'done'}, 'owner')
        i = outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': None, 'mid': 1}, at=ago(days=8)); outcomes.resolve(s)
        self.assertEqual(s._one('SELECT Verdict FROM outcome WHERE Id=?', (i,))['Verdict'], 'unknown')
        self.assertEqual(outcomes.evidence(s, ago(days=30)), [])

    def test_the_owners_own_later_mail_is_not_a_round(self):
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 'test'); t = s.create_task({'Title': 'x'}, 'owner'); mid = _thread(s, 'c4')
        s.add_message({'ConversationId': 'c4', 'Channel': 'email', 'Subject': 'Re: AP cutover', 'Direction': 'out', 'SentAt': ago(days=6),
                       'BodyText': 'Also: the PO is attached.', 'Status': 'filed'})                # sent by us, no FromEmail (outbox.py)
        outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': 'c4', 'mid': mid}, at=ago(days=8)); outcomes.resolve(s)
        self.assertEqual(outcomes.rows_for(s, 'task', t)[0]['Verdict'], 'settled')


class PersonFactsTests(unittest.TestCase):
    """The ledger's person facts (spec 2026-10-12, build step 4): who answered, how fast, after what, who was copied."""
    def _answered(self, s, who, days, chase=False, cc=()):
        """A reply sent to `who` eight days ago that they answered `days` days later."""
        cid = f"c{(s._one('SELECT COUNT(*) AS n FROM outcome') or {}).get('n', 0) + 1}"
        t = s.create_task({'Title': 'x'}, 'owner')
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'x', 'FromEmail': who, 'SentAt': ago(days=10), 'BodyText': 'q', 'Status': 'filed', 'TaskId': t})
        s.add_message({'ConversationId': cid, 'Channel': 'email', 'Subject': 'Re: x', 'FromEmail': who, 'SentAt': ago(days=8 - days), 'BodyText': 'a', 'Status': 'filed', 'TaskId': t})
        return outcomes.record(s, 'reply.sent', 'task', t, facts={'cid': cid, 'mid': 1, 'verb': 'approve', 'who': who, 'cc': list(cc), 'chase': chase}, at=ago(days=8))

    def test_an_answer_records_how_many_days_it_took(self):
        s = MemoryStore(); i = self._answered(s, 'ray@northwind.example', 3)
        outcomes.resolve(s)
        f = json.loads(s._one('SELECT FactsJson FROM outcome WHERE Id=?', (i,))['FactsJson'])
        self.assertAlmostEqual(f['answer_days'], 3.0, delta=0.2); self.assertEqual(f['answered_by'], 'ray@northwind.example')

    def test_person_facts_are_counts_from_the_rows(self):
        s = MemoryStore(); who = 'ray@northwind.example'
        for d, chase, cc in ((2, False, ()), (4, True, ('omar@northwind.example',)), (3, True, ('omar@northwind.example',))): self._answered(s, who, d, chase, cc)
        outcomes.resolve(s)
        outcomes.record(s, 'chase.let_go', 'message', 9, facts={'who': who}); outcomes.resolve(s)
        f = outcomes.person_facts(s, who)
        self.assertEqual((f['replies'], f['answered'], f['chased'], f['answered_after_chase'], f['let_go']), (3, 3, 2, 2, 1))
        self.assertAlmostEqual(f['median_days'], 3.0, delta=0.2)
        self.assertEqual(f['cc']['omar@northwind.example'], [2, 2])
        self.assertEqual(outcomes.chase_cc(s, who), 'omar@northwind.example')
        self.assertEqual(outcomes.person_facts(s, 'nobody@northwind.example')['replies'], 0)

    def test_late_after_needs_three_answers(self):
        s = MemoryStore(); who = 'gail@northwind.example'
        self._answered(s, who, 1); outcomes.resolve(s)
        self.assertEqual(outcomes.late_after(s, who), 5)                                   # one answer is not a habit
        self._answered(s, who, 1); self._answered(s, who, 2); outcomes.resolve(s)
        self.assertEqual(outcomes.late_after(s, who), 2)                                   # median 1 day -> 1.5 -> at least 2
        self.assertEqual(outcomes.late_after(s, who, default=9), 2)

    def test_a_persons_step_closing_records_who_and_how_late(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Schema sign-off', 'Status': 'waiting', 'Assignee': 'person:ray@northwind.example',
                           'DueAt': (datetime.now() - timedelta(days=3)).strftime('%Y-%m-%d')}, 'owner')
        s.update_task(t, {'Status': 'done'}, 'owner')
        f = json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])
        self.assertEqual((f['who'], f['late_days']), ('ray@northwind.example', 3))
        self.assertEqual(outcomes.person_facts(s, 'ray@northwind.example')['steps_late'], 1)


class OwnerWordsTests(unittest.TestCase):
    def test_a_resume_keeps_the_owners_words_and_drops_ours(self):
        from taskuary.continuity import RESUME_PROMPT
        from taskuary.outcomes import owner_words
        self.assertEqual(owner_words(f'FROM THE OWNER: merge it if the tests pass {RESUME_PROMPT}'), 'merge it if the tests pass')
        self.assertEqual(owner_words(RESUME_PROMPT), '')
        self.assertEqual(owner_words('just keep going'), 'just keep going')
