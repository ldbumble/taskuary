"""Shared operations, correction evidence and durable discussion (PW-129 to PW-134).

Every owner action used to be its own endpoint doing its own thing: the same correction was
written five ways, a double click ran an action twice, and what the owner and the assistant
said about an item lived only in the browser. Now an action is a proposal with an immutable id,
a confirmation version and the context revision it was judged on; execution is idempotent,
refuses stale proposals, reports the real outcome, and - when it succeeded and differs from what
triage said - records correction EVIDENCE keyed to that operation. Evidence informs fresh triage;
it is not a rule, not a memory note and never a sender exclusion. Discussion about a source item
is kept against the item and travels onto the task it later becomes, per item, not per batch.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import ingest, operations, server
from taskuary.store import MemoryStore

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'dana@vendor.example', 'from_name': 'Dana', 'conversation_id': 'AAQk-x',
       'subject': 'August export', 'sent_at': '2026-09-06 09:00:00', 'body': 'Hi Uri, could you send me the August export? Dana'}


def arrive(s, intent='fyi', kind='general', **over):
    """One message through the funnel with the verdict named - the way triage leaves it."""
    llm = lambda *a, **k: json.dumps({'intent': intent, 'kind': kind, 'why': 'test'})
    with mock.patch.object(ingest, '_spawn'):
        out = ingest.ingest_message(s, {**MSG, **over}, llm=llm)
    return out


class ExecutionTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.mid = arrive(self.s, 'fyi')['message_id']

    def test_a_confirmed_proposal_runs_once_and_a_repeated_click_returns_the_same_receipt(self):
        runs = []
        op = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        first = operations.execute(self.s, op['id'], op['version'], lambda: runs.append(1) or {'taskId': 7}, 'owner')
        again = operations.execute(self.s, op['id'], op['version'], lambda: runs.append(1) or {'taskId': 8}, 'owner')
        self.assertEqual((first['status'], first['outcome']), ('done', {'taskId': 7}))
        self.assertEqual((again['status'], again['outcome'], again['duplicate']), ('done', {'taskId': 7}, True))
        self.assertEqual(runs, [1])

    def test_two_confirmations_at_once_run_the_handler_once(self):
        """PW-129/130: two confirms that both read 'proposed' both ran the handler. The claim is a compare-and-set
        on the row; the loser gets the same receipt shape with duplicate=True and runs nothing."""
        import threading, time
        op = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        self.assertTrue(self.s.claim_operation(op['id'], op['version']))
        self.assertFalse(self.s.claim_operation(op['id'], op['version']), 'the second confirm loses the race')
        runs = []
        lost = operations.execute(self.s, op['id'], op['version'], lambda: runs.append(1) or {'taskId': 9}, 'owner')
        self.assertEqual(runs, []); self.assertTrue(lost['duplicate']); self.assertEqual(lost['status'], 'running')
        # and truly concurrent: two threads, one barrier, one run
        op2 = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        gate, ran, results = threading.Barrier(2), [], []
        def confirm():
            gate.wait()
            results.append(operations.execute(self.s, op2['id'], op2['version'], lambda: (time.sleep(0.05), ran.append(1))[1] or {'taskId': 10}, 'owner'))
        ts = [threading.Thread(target=confirm) for _ in range(2)]
        for t in ts: t.start()
        for t in ts: t.join(5)
        self.assertEqual(ran, [1]); self.assertEqual(sorted(r['duplicate'] for r in results), [False, True])

    def test_an_outcome_that_says_it_failed_is_an_error_teaches_nothing_and_can_be_retried(self):
        """PW-130: a handler that returned {'ok': False} was recorded as done and its 'correction' as evidence."""
        op = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        out = operations.execute(self.s, op['id'], op['version'], lambda: {'ok': False, 'error': 'the repository is missing'}, 'owner')
        self.assertEqual((out['status'], out['evidence']), ('error', 'none')); self.assertIn('repository', out['error'])
        self.assertEqual(self.s.corrections(message_id=self.mid), [])
        retry = operations.execute(self.s, op['id'], op['version'], lambda: {'taskId': 11}, 'owner')
        self.assertEqual((retry['status'], retry['duplicate']), ('done', False))
        self.assertEqual(len(self.s.corrections(message_id=self.mid)), 1, 'the success afterwards is the correction')

    def test_an_edited_proposal_is_a_new_version_and_the_old_confirmation_is_stale(self):
        runs = []
        op = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        rev = operations.revise(self.s, op['id'], {'kind': 'coding'}, 'owner')
        self.assertEqual((rev['version'], rev['params']), (2, {'kind': 'coding'}))
        out = operations.execute(self.s, op['id'], 1, lambda: runs.append(1), 'owner')
        self.assertEqual(out['status'], 'stale'); self.assertEqual(runs, [])
        ok = operations.execute(self.s, op['id'], 2, lambda: runs.append(1) or {'ok': True}, 'owner')
        self.assertEqual(ok['status'], 'done'); self.assertEqual(runs, [1])

    def test_new_context_on_the_target_makes_the_proposal_stale(self):
        runs = []
        op = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        arrive(self.s, 'fyi', external_id='e2', body='Actually, never mind - found it.')      # the thread moved on
        out = operations.execute(self.s, op['id'], op['version'], lambda: runs.append(1), 'owner')
        self.assertEqual(out['status'], 'stale'); self.assertIn('context', out['error']); self.assertEqual(runs, [])

    def test_a_failed_execution_reports_the_error_teaches_nothing_and_can_be_retried(self):
        op = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        def boom(): raise RuntimeError('agent did not start')
        out = operations.execute(self.s, op['id'], op['version'], boom, 'owner')
        self.assertEqual(out['status'], 'error'); self.assertIn('agent did not start', out['error'])
        self.assertEqual(operations.corrections(self.s, message_id=self.mid), [])
        ok = operations.execute(self.s, op['id'], op['version'], lambda: {'taskId': 1}, 'owner')
        self.assertEqual(ok['status'], 'done')
        self.assertEqual(len(operations.corrections(self.s, message_id=self.mid)), 1)

    def test_a_cancelled_proposal_never_runs(self):
        runs = []
        op = operations.propose(self.s, 'task.create_from_message', self.mid, {'kind': 'task'}, 'owner')
        operations.cancel(self.s, op['id'], 'owner')
        out = operations.execute(self.s, op['id'], op['version'], lambda: runs.append(1), 'owner')
        self.assertEqual(out['status'], 'cancelled'); self.assertEqual(runs, [])
        self.assertEqual(operations.corrections(self.s, message_id=self.mid), [])

    def test_an_unknown_kind_or_missing_parameter_is_refused_before_anything_is_written(self):
        with self.assertRaises(ValueError): operations.propose(self.s, 'task.explode', self.mid, {}, 'owner')
        with self.assertRaises(ValueError): operations.propose(self.s, 'task.create_from_message', self.mid, {}, 'owner')
        self.assertEqual(operations.history(self.s, message_id=self.mid), [])


class CorrectionTests(unittest.TestCase):
    def run_op(self, s, kind, target, params):
        op = operations.propose(s, kind, target, params, 'owner')
        return operations.execute(s, op['id'], op['version'], lambda: {'ok': True}, 'owner')

    def test_fyi_made_a_task_is_a_correction_with_the_verdict_and_the_change(self):
        s = MemoryStore(); mid = arrive(s, 'fyi')['message_id']
        self.run_op(s, 'task.create_from_message', mid, {'kind': 'task'})
        c = operations.corrections(s, message_id=mid)
        self.assertEqual(len(c), 1)
        self.assertEqual((c[0]['Verdict'], c[0]['Change'], c[0]['Sender']), ('fyi', 'task', 'dana@vendor.example'))
        self.assertTrue(c[0]['OpId'] and c[0]['VerdictRouteId'])

    def test_general_sent_to_coding_is_a_correction(self):
        s = MemoryStore(); out = arrive(s, 'task', 'general')
        self.run_op(s, 'dispatch.prepare', out['task_id'], {'kind': 'coding'})
        c = operations.corrections(s, task_id=out['task_id'])
        self.assertEqual([(x['Verdict'], x['Change']) for x in c], [('general', 'coding')])

    def test_reply_needed_dismissed_is_a_correction(self):
        s = MemoryStore(); mid = arrive(s, 'reply_only')['message_id']
        self.run_op(s, 'message.file', mid, {})
        c = operations.corrections(s, message_id=mid)
        self.assertEqual([(x['Verdict'], x['Change']) for x in c], [('reply', 'dismissed')])

    def test_deferral_and_discussion_and_an_unchanged_verdict_teach_nothing(self):
        s = MemoryStore(); out = arrive(s, 'task', 'general')
        self.run_op(s, 'task.defer', out['task_id'], {'until': '2026-09-07 09:00:00'})
        operations.discuss(s, 'owner', 'what is this about?', task_id=out['task_id'])
        self.run_op(s, 'dispatch.prepare', out['task_id'], {'kind': 'general'})
        self.assertEqual(operations.corrections(s, task_id=out['task_id']), [])

    def test_evidence_is_not_a_memory_note_and_not_a_sender_rule(self):
        s = MemoryStore(); mid = arrive(s, 'fyi')['message_id']
        before = (len(s.list_memories(False)), len(s.list_policies(False)))
        self.run_op(s, 'task.create_from_message', mid, {'kind': 'task'})
        self.assertEqual((len(s.list_memories(False)), len(s.list_policies(False))), before)
        self.assertEqual(len(operations.corrections(s, message_id=mid)), 1)

    def test_evidence_that_could_not_be_written_is_recovered_without_repeating_the_action(self):
        s = MemoryStore(); mid = arrive(s, 'fyi')['message_id']; runs = []
        op = operations.propose(s, 'task.create_from_message', mid, {'kind': 'task'}, 'owner')
        with mock.patch.object(s, 'add_correction', side_effect=RuntimeError('disk full')):
            out = operations.execute(s, op['id'], op['version'], lambda: runs.append(1) or {'ok': True}, 'owner')
        self.assertEqual(out['status'], 'done'); self.assertEqual(operations.corrections(s, message_id=mid), [])
        self.assertEqual(operations.get(s, op['id'])['evidence'], 'pending')
        self.assertEqual(operations.recover_evidence(s), 1)
        self.assertEqual(len(operations.corrections(s, message_id=mid)), 1); self.assertEqual(runs, [1])
        self.assertEqual(operations.recover_evidence(s), 0)

    def test_the_evidence_reaches_fresh_triage_as_evidence(self):
        s = MemoryStore(); mid = arrive(s, 'fyi')['message_id']
        self.run_op(s, 'task.create_from_message', mid, {'kind': 'task'})
        lines = operations.evidence_lines(s, {'from_email': 'dana@vendor.example', 'subject': 'Re: August export'})
        self.assertEqual(len(lines), 1); self.assertIn('fyi', lines[0]); self.assertIn('task', lines[0])
        self.assertEqual(operations.evidence_lines(s, {'from_email': 'someone@else.example', 'subject': 'lunch'}), [])


class DiscussionTests(unittest.TestCase):
    def test_discussion_on_a_taskless_fyi_travels_onto_the_task_it_becomes_and_not_onto_its_siblings(self):
        s = MemoryStore()
        a = arrive(s, 'fyi')['message_id']
        b = arrive(s, 'fyi', external_id='e2', conversation_id='AAQk-y', subject='Parking')['message_id']
        operations.discuss(s, 'owner', 'is this the export Finance asked for?', message_id=a)
        operations.discuss(s, 'assistant', 'Yes - Dana asked for August.', message_id=a)
        operations.discuss(s, 'owner', 'ignore the parking note', message_id=b)
        tid = ingest.task_from_message(s, a, 'owner', 'task', 'owner')
        rows = operations.discussion(s, task_id=tid)
        self.assertEqual([(r['Actor'], r['Body'][:6]) for r in rows], [('owner', 'is thi'), ('assistant', 'Yes - ')])
        self.assertEqual([r['MessageId'] for r in rows], [a, a])
        self.assertEqual(len(operations.discussion(s, message_id=b)), 1)

    def test_history_is_the_receipts_the_discussion_and_the_corrections_in_order(self):
        s = MemoryStore(); mid = arrive(s, 'fyi')['message_id']
        operations.discuss(s, 'owner', 'make this a task', message_id=mid)
        op = operations.propose(s, 'task.create_from_message', mid, {'kind': 'task'}, 'owner')
        operations.execute(s, op['id'], op['version'], lambda: {'taskId': 1}, 'owner')
        h = operations.history(s, message_id=mid)
        self.assertEqual([x['type'] for x in h], ['discussion', 'operation', 'correction'])
        self.assertEqual(h[1]['status'], 'done')


class EntryPointTests(unittest.TestCase):
    """The task page and the timeline record the same evidence the confirmation box will."""
    def setUp(self):
        self.s = MemoryStore()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def test_mine_on_a_filed_message_records_fyi_to_task(self):
        mid = arrive(self.s, 'fyi')['message_id']
        r = self.c.post(f'/api/messages/{mid}/mine', json={'kind': 'task'})
        self.assertEqual(r.status_code, 200)
        c = operations.corrections(self.s, message_id=mid)
        self.assertEqual([(x['Verdict'], x['Change']) for x in c], [('fyi', 'task')])

    def test_not_coding_on_a_coding_task_records_the_change_once(self):
        out = arrive(self.s, 'task', 'coding')
        r = self.c.post(f"/api/tasks/{out['task_id']}/not-coding", json={'learn': False})
        self.assertEqual(r.status_code, 200)
        c = operations.corrections(self.s, task_id=out['task_id'])
        self.assertEqual([(x['Verdict'], x['Change']) for x in c], [('coding', 'task')])

    def test_filing_a_reply_needed_message_records_the_dismissal(self):
        mid = arrive(self.s, 'reply_only')['message_id']
        self.assertEqual(self.c.post(f'/api/messages/{mid}/file', json={'learn': False}).status_code, 200)
        c = operations.corrections(self.s, message_id=mid)
        self.assertEqual([(x['Verdict'], x['Change']) for x in c], [('reply', 'dismissed')])

    def test_the_api_confirms_by_proposal_and_version_and_a_double_click_is_one_task(self):
        mid = arrive(self.s, 'fyi')['message_id']
        p = self.c.post('/api/operations', json={'kind': 'task.create_from_message', 'target': mid, 'params': {'kind': 'task'}}).json()
        self.assertEqual(p['version'], 1)
        a = self.c.post(f"/api/operations/{p['id']}/execute", json={'version': 1}).json()
        b = self.c.post(f"/api/operations/{p['id']}/execute", json={'version': 1}).json()
        self.assertEqual(a['status'], 'done'); self.assertEqual(b['status'], 'done'); self.assertTrue(b['duplicate'])
        self.assertEqual(a['outcome']['taskId'], b['outcome']['taskId'])
        self.assertEqual(len(self.s.list_tasks()), 1)
        h = self.c.get(f"/api/tasks/{a['outcome']['taskId']}/history").json()['data']
        self.assertIn('operation', [x['type'] for x in h]); self.assertIn('correction', [x['type'] for x in h])

    def test_a_stale_confirmation_is_refused_by_the_api(self):
        mid = arrive(self.s, 'fyi')['message_id']
        p = self.c.post('/api/operations', json={'kind': 'task.create_from_message', 'target': mid, 'params': {'kind': 'task'}}).json()
        self.c.patch(f"/api/operations/{p['id']}", json={'params': {'kind': 'general'}})
        r = self.c.post(f"/api/operations/{p['id']}/execute", json={'version': 1})
        self.assertEqual(r.status_code, 409); self.assertEqual(self.s.list_tasks(), [])


if __name__ == '__main__':
    unittest.main()
