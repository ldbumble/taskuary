"""A workflow's agent proposing ledger writes, its run task, and Run now - kept from the roles tests when roles went (2026-11-23)."""
import json, unittest
from unittest import mock
import xml.etree.ElementTree as ET

from taskuary import agents, intacct, workflows
from taskuary.store import MemoryStore


def setup():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.set_setting('default_brain', 'claude', 'owner')        # his pick: the one resolver takes it at its word (agents.picked)
    return s, {'agents': {'coding': {'kind': 'coding'}}, 'cli_connections': {'claude': {'cmd': 'claude', 'args': ['-p']}}}


class DefaultProfileTests(unittest.TestCase):
    def test_an_old_default_routes_nothing(self):
        """A general agent working a TASK walks the owner through their work (the owner, 2026-11-04): an old default routes nothing."""
        s, cfg = setup()
        self.assertEqual(agents.routed_role(s, 'general'), '')
        s.set_setting('default_profile', 'ap', 'o')                       # one an older version wrote
        self.assertEqual(agents.routed_role(s, 'general'), '')
        self.assertEqual(agents.routed_role(s, 'coding'), 'coding')
        self.assertEqual(agents.routed_role(s, 'task'), '')           # the owner's own list stays theirs


class AWorkflowRunNamesNoWorkerTests(unittest.TestCase):
    def test_a_routine_that_still_names_an_agent_runs_unassigned(self):
        """A routine saved naming a worker (`agent`) from before profiles went is simply that routine: its run task carries no
        `agent:` stamp, and general work runs on the assistant (2026-11-23)."""
        s, _ = setup()
        sid = s.save_source({'Channel': 'report', 'Address': 'Bills', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Bills', 'agent': 'ap', 'browser': True, 'prompt': 'go'})}, 'o')
        from taskuary import ingest
        with mock.patch.object(ingest, '_auto_general'), mock.patch.object(ingest, '_auto_code'):
            t = s.get_task(workflows.run(s, s.get_source(sid))['task_id'])
        self.assertFalse(t.get('Assignee'))


class ANestedBillIsProposedTests(unittest.TestCase):
    """An Intacct bill nests its record and line items. The lazy `{.*?}` that read proposals stopped at the first
    inner brace, so every such bill was dropped without a word and a stray `}` was left in the agent's report
    (found driving the portal workflow live)."""
    REPLY = ('Trainly TR-2209 is missing, proposed below.\n'
             'TASKUARY-PROPOSE {"action": "run_tool", "type": "intacct_create", "object": "APBILL", "record": {"VENDORID": "V-TRN", '
             '"RECORDID": "TR-2209", "APBILLITEMS": [{"ACCOUNTNO": "6400", "TRX_AMOUNT": "450.00"}]}, "why": "missing from the ledger"}\n'
             'Nothing is posted until you approve it.')

    def test_the_whole_record_is_read_and_cut_from_the_report(self):
        from taskuary import proposals
        [p] = proposals.parse(self.REPLY)
        self.assertEqual(p['record']['APBILLITEMS'][0]['TRX_AMOUNT'], '450.00')
        left = proposals.strip(self.REPLY)
        self.assertNotIn('}', left); self.assertNotIn('TASKUARY-PROPOSE', left)
        self.assertIn('Nothing is posted until you approve it.', left)

    def test_it_lands_on_the_task_as_a_pending_review(self):
        from taskuary import proposals
        s, _ = setup()
        s.save_connector({'Type': 'intacct', 'Name': 'Intacct', 'Active': 1, 'Scope': 'read'}, 'o')
        tid = s.create_task({'Title': 'bills', 'Kind': 'general', 'Status': 'open'}, 'o')
        got = proposals.collect(s, tid, self.REPLY, 'assistant')
        self.assertEqual([g['action'] for g in got], ['run_tool'])
        self.assertEqual(json.loads(s.list_reviews('pending')[0]['DraftText'])['record']['VENDORID'], 'V-TRN')

    def test_a_seed_example_with_placeholders_is_still_skipped_quietly(self):
        from taskuary import proposals
        self.assertEqual(proposals.parse('TASKUARY-PROPOSE {"action": "run_tool", "type": "<one of its tools>", ...}'), [])


class AFinishedAgentLeavesItsProposalForTheOwnerTests(unittest.TestCase):
    """The agent's own finish closed the task, and closing supersedes every pending review: the bill it had just
    proposed was cancelled before the owner saw it (live AP portal run). It now waits on the owner instead."""
    def finished(self):
        from taskuary import wrapup, proposals
        s, _ = setup()
        s.save_connector({'Type': 'intacct', 'Name': 'Intacct', 'Active': 1, 'Scope': 'read'}, 'o')
        tid = s.create_task({'Title': 'bills', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        proposals.collect(s, tid, ANestedBillIsProposedTests.REPLY, 'assistant')
        wrapup.finish(s, tid, {'summary': 'one bill proposed'}, None, 'assistant')
        return s, tid, s.list_reviews('pending')

    def test_the_task_waits_and_the_proposal_stays_pending(self):
        s, tid, pending = self.finished()
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')
        self.assertEqual(len([r for r in pending if r['TaskId'] == tid and r['Kind'] == 'action']), 1)

    def test_answering_the_last_proposal_puts_it_back_on_the_owner_yes_or_no(self):
        from taskuary import proposals
        for verb, status in (('reject', 'rejected'), ('approve', 'approved')):
            s, tid, pending = self.finished()
            rv = next(r for r in pending if r['TaskId'] == tid and r['Kind'] == 'action')
            s.decide_review(rv['ReviewId'], status, None, 'owner', '')
            proposals.settle(s, rv, verb, 'owner')
            self.assertEqual(s.get_task(tid)['Status'], 'open', verb)          # open, for Mark done - Approve closes nothing (2026-10-18)

    def test_the_owners_own_done_still_closes_at_once(self):
        from taskuary import wrapup, proposals
        s, _ = setup()
        tid = s.create_task({'Title': 'bills', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        proposals.collect(s, tid, ANestedBillIsProposedTests.REPLY, 'assistant')
        wrapup.finish(s, tid, {'summary': 'x'}, None, 'owner', owner_done=True)
        self.assertEqual(s.get_task(tid)['Status'], 'done')


class IntacctNegativeFiltersTests(unittest.TestCase):
    def test_notin_and_notlike_reach_the_gateway(self):
        q = ET.Element('query')
        intacct._filter_xml(q, [['STATE', 'notin', ['Paid', 'Voided']], ['VENDORNAME', 'notlike', 'Test%']])
        self.assertEqual([v.text for v in q.find('filter/and/notin').findall('value')], ['Paid', 'Voided'])
        self.assertEqual(q.find('filter/and/notlike/value').text, 'Test%')


class RunNowOpensTheWorkflowsTaskTests(unittest.TestCase):
    """The owner, 2026-10-08: "when you hit run now it should not be like report that runs in background but the task
    should show up in assistant canvas". The task is made before the call returns; the agent starts on its own thread."""
    def test_run_now_hands_back_the_task_and_the_agent_starts_off_the_request(self):
        import threading
        from fastapi.testclient import TestClient
        from taskuary import ingest, server
        s, _ = setup()
        sid = s.save_source({'Channel': 'report', 'Address': 'Bills', 'Owner': 'o', 'Active': 0,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Bills', 'browser': True, 'prompt': 'go'})}, 'o')
        started, gate = [], threading.Event()
        def slow_start(store, tid, text=None): gate.wait(5); started.append(tid)
        with mock.patch.object(server, 'store', s), mock.patch.object(ingest, '_auto_general', side_effect=slow_start):
            r = TestClient(server.app).post(f'/api/reports/{sid}/rerun').json()
            self.assertEqual(started, [])                       # the call did not wait for the agent
            gate.set()
        t = s.get_task(r['task_id'])
        self.assertEqual((r['workflow'], r['ref'], r['link']), (True, f"TQ-{r['task_id']:04d}", f"#task={r['task_id']}"))
        self.assertEqual(t['Tags'], 'needs:browser,workflow-trigger:manual')   # ...and who started it
        for _ in range(50):
            if started: break
            threading.Event().wait(0.05)
        self.assertEqual(started, [r['task_id']])

    def test_a_plain_report_still_runs_in_the_background(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s, _ = setup()
        sid = s.save_source({'Channel': 'report', 'Address': 'Counts', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'rest', 'title': 'Counts', 'url': 'https://x.example'})}, 'o')
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_spawn_rerun'):
            r = TestClient(server.app).post(f'/api/reports/{sid}/rerun').json()
        self.assertTrue(r['queued']); self.assertNotIn('task_id', r)


if __name__ == '__main__': unittest.main()
