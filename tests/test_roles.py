"""An AP rep should not have to assemble a worker, two playbooks, a route and a workflow by hand.

roles.apply lays them out in one go; these pin what it may and may not touch - above all that
applying twice changes nothing, and that nothing the owner already chose is overwritten.
"""
import json, tempfile, unittest
from pathlib import Path
from unittest import mock
import xml.etree.ElementTree as ET

from taskuary import agents, config, intacct, playbooks, roles, workflows
from taskuary.store import MemoryStore


def setup():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    return s, {'agents': {'coder': {'cmd': 'claude', 'args': ['-p']}}}


class RoleTests(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        for p in (mock.patch.object(playbooks, 'folder', return_value=Path(self.dir.name)),
                  mock.patch.object(config, 'save')):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(self.dir.cleanup)

    def test_ap_lays_out_the_worker_its_playbooks_the_route_and_an_off_workflow(self):
        s, cfg = setup()
        s.save_connector({'Type': 'intacct', 'Name': 'Intacct', 'Active': 1}, 'o')
        r = roles.apply(s, cfg, 'ap', 'https://portal.example/bills')
        a = s.get_agent('ap')
        self.assertEqual(a['Kind'], 'accounts-payable')
        self.assertTrue(json.loads(a['Config'])['triage_enabled'])
        self.assertEqual(cfg['agents']['ap']['cmd'], 'claude')          # runnable on day one
        self.assertIn('vendor asks where their money is', s.get_doc('ap'))
        self.assertIn('- ap: ACCOUNTS PAYABLE', agents.roster(s))
        self.assertEqual(sorted(r['playbooks_added']), ['portal-bill-approvals', 'vendor-payment-inquiry'])
        self.assertEqual(s.get_setting('default_profile'), 'ap')
        self.assertEqual(s.get_connector_by_type('intacct')['Scope'], 'read')
        src = s.get_source(r['workflow_id'])
        self.assertEqual(src['Active'], 0)                              # needs a sign-in first
        c = json.loads(src['ConfigJson'])
        self.assertTrue(workflows.is_workflow(c))
        self.assertIn('https://portal.example/bills', c['prompt'])

    def test_applying_twice_changes_nothing_and_never_overrides_the_owner(self):
        s, cfg = setup()
        s.save_connector({'Type': 'intacct', 'Name': 'Intacct', 'Active': 1, 'Scope': 'write'}, 'o')
        first = roles.apply(s, cfg, 'ap')
        self.assertEqual(first['ledger_narrowed'], '')                   # the owner chose write
        self.assertEqual(s.get_connector_by_type('intacct')['Scope'], 'write')
        s.save_doc('ap', 'my own rules', 'owner')
        (Path(self.dir.name) / 'vendor-payment-inquiry.md').write_text('# mine\nwhen: x\n', encoding='utf-8')
        again = roles.apply(s, cfg, 'ap')
        self.assertFalse(again['profile_added']); self.assertEqual(again['playbooks_added'], [])
        self.assertEqual(again['workflow_id'], first['workflow_id'])
        self.assertEqual(len([x for x in s.list_sources(active_only=False) if x.get('Address') == roles.ROLES['ap']['workflow']['title']]), 1)
        self.assertEqual(s.get_doc('ap'), 'my own rules')
        self.assertIn('# mine', playbooks.read('vendor-payment-inquiry'))

    def test_an_unknown_role_is_refused(self):
        s, cfg = setup()
        with self.assertRaises(ValueError): roles.apply(s, cfg, 'astronaut')

    def test_the_shipped_playbooks_parse_reach_the_ledger_and_are_not_about_code(self):
        for slug in roles.ROLES['ap']['playbooks']:
            pb = playbooks.parse(roles.playbook_text(slug))
            self.assertTrue(all(pb[f] for f in playbooks.FIELDS), slug)
            self.assertIn('intacct', playbooks.uses_of(pb))
            self.assertFalse(playbooks.about_code(pb))
        self.assertIn('bank', playbooks.parse(roles.playbook_text('vendor-payment-inquiry'))['ask first'])
        # the portal posts approved bills itself: the job is approving, and only on the owner's named yes
        pb = playbooks.parse(roles.playbook_text('portal-bill-approvals'))
        self.assertIn('EVERY approval', pb['ask first']); self.assertIn('owner named', pb['ask first'])
        self.assertIn('never write to the ledger', roles.ROLES['ap']['workflow']['ask_first'])


class DefaultProfileTests(unittest.TestCase):
    def test_general_work_triage_named_nobody_for_goes_to_the_default(self):
        s, _ = setup()
        s.upsert_agent('ap', 'accounts-payable', 'cli', '{}'); s.upsert_agent('researcher', 'research', 'cli', '{}')
        self.assertEqual(agents.routed_role(s, 'general', ''), '')        # blank keeps the old answer
        s.set_setting('default_profile', 'ap', 'o')
        self.assertEqual(agents.routed_role(s, 'general', ''), 'ap')
        self.assertEqual(agents.routed_role(s, 'general', 'invented'), 'ap')
        self.assertEqual(agents.routed_role(s, 'general', 'researcher'), 'researcher')   # a better fit still wins
        self.assertEqual(agents.routed_role(s, 'coding', ''), 'coder')
        self.assertEqual(agents.routed_role(s, 'task', ''), '')           # the owner's own list stays theirs

    def test_a_coding_or_switched_off_default_routes_nothing(self):
        s, _ = setup()
        s.set_setting('default_profile', 'coder', 'o')
        self.assertEqual(agents.routed_role(s, 'general', ''), '')
        s.upsert_agent('ap', 'accounts-payable', 'cli', '{}'); s.set_setting('default_profile', 'ap', 'o')
        self.assertEqual(agents.routed_role(s, 'general', ''), 'ap')
        s._exec("UPDATE agent SET Active=0 WHERE Name='ap'")
        self.assertEqual(agents.routed_role(s, 'general', ''), '')


class WorkflowRunsAsItsWorkerTests(unittest.TestCase):
    def run_it(self, s, agent):
        sid = s.save_source({'Channel': 'report', 'Address': 'Bills', 'Owner': 'o', 'Active': 1,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Bills', 'agent': agent, 'browser': True, 'prompt': 'go'})}, 'o')
        from taskuary import ingest
        with mock.patch.object(ingest, '_auto_general'), mock.patch.object(ingest, '_auto_code'):
            return s.get_task(workflows.run(s, s.get_source(sid))['task_id'])

    def test_a_general_worker_is_stamped_and_a_coding_name_is_not(self):
        s, _ = setup()
        s.upsert_agent('ap', 'accounts-payable', 'cli', '{}')
        self.assertEqual(self.run_it(s, 'ap')['Assignee'], 'agent:ap')
        self.assertFalse(self.run_it(s, 'coder').get('Assignee'))


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
        from taskuary import coder, proposals
        s, _ = setup()
        s.save_connector({'Type': 'intacct', 'Name': 'Intacct', 'Active': 1, 'Scope': 'read'}, 'o')
        tid = s.create_task({'Title': 'bills', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        proposals.collect(s, tid, ANestedBillIsProposedTests.REPLY, 'assistant')
        coder.finish(s, tid, {'summary': 'one bill proposed'}, None, 'assistant')
        return s, tid, s.list_reviews('pending')

    def test_the_task_waits_and_the_proposal_stays_pending(self):
        s, tid, pending = self.finished()
        self.assertEqual(s.get_task(tid)['Status'], 'waiting')
        self.assertEqual(len([r for r in pending if r['TaskId'] == tid and r['Kind'] == 'action']), 1)

    def test_answering_the_last_proposal_closes_it_yes_or_no(self):
        from taskuary import proposals
        for verb, status in (('reject', 'rejected'), ('approve', 'approved')):
            s, tid, pending = self.finished()
            rv = next(r for r in pending if r['TaskId'] == tid and r['Kind'] == 'action')
            s.decide_review(rv['ReviewId'], status, None, 'owner', '')
            proposals.settle(s, rv, verb, 'owner')
            self.assertEqual(s.get_task(tid)['Status'], 'done', verb)

    def test_the_owners_own_done_still_closes_at_once(self):
        from taskuary import coder, proposals
        s, _ = setup()
        tid = s.create_task({'Title': 'bills', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        proposals.collect(s, tid, ANestedBillIsProposedTests.REPLY, 'assistant')
        coder.finish(s, tid, {'summary': 'x'}, None, 'owner', owner_done=True)
        self.assertEqual(s.get_task(tid)['Status'], 'done')


class IntacctNegativeFiltersTests(unittest.TestCase):
    def test_notin_and_notlike_reach_the_gateway(self):
        q = ET.Element('query')
        intacct._filter_xml(q, [['STATE', 'notin', ['Paid', 'Voided']], ['VENDORNAME', 'notlike', 'Test%']])
        self.assertEqual([v.text for v in q.find('filter/and/notin').findall('value')], ['Paid', 'Voided'])
        self.assertEqual(q.find('filter/and/notlike/value').text, 'Test%')


class RolesApiTests(unittest.TestCase):
    def test_the_page_lists_the_role_and_applying_it_says_what_changed(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s, cfg = setup()
        tmp = tempfile.TemporaryDirectory(); self.addCleanup(tmp.cleanup)
        with mock.patch.object(server, 'store', s), mock.patch.object(server, 'cfg', {**server.cfg, **cfg}), \
             mock.patch.object(playbooks, 'folder', return_value=Path(tmp.name)), mock.patch.object(config, 'save'):
            c = TestClient(server.app)
            ap = next(r for r in c.get('/api/roles').json()['data'] if r['name'] == 'ap')
            self.assertFalse(ap['applied'])
            got = c.post('/api/roles/ap', json={'portal': ''}).json()
            self.assertTrue(got['profile_added'])
            self.assertTrue(next(r for r in c.get('/api/roles').json()['data'] if r['name'] == 'ap')['is_default'])
            self.assertEqual(c.post('/api/roles/nope', json={}).status_code, 422)


class TheAssistantSetsARoleUpTests(unittest.TestCase):
    """The owner, 2026-10-08: "the assistant should be able to walk a user through setting up new role and work". The chat
    asks its questions, then puts the whole set-up on ONE card; the yes runs the Profiles page's own road."""
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory(); self.addCleanup(self.dir.cleanup)
        for p in (mock.patch.object(playbooks, 'folder', return_value=Path(self.dir.name)), mock.patch.object(config, 'save')):
            p.start(); self.addCleanup(p.stop)

    def card(self, s, params):
        from taskuary import concierge, terminal
        line = 'CALL: ' + json.dumps({'kind': 'role.apply', 'params': params})
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            return concierge.say(s, 'set me up as an AP rep', llm=lambda *a, **k: line)

    def run_card(self, s, cfg, p):
        from fastapi.testclient import TestClient
        from taskuary import server, terminal
        with mock.patch.object(server, 'store', s), mock.patch.object(server, 'cfg', {**server.cfg, **cfg}),              mock.patch.object(terminal, 'live_sessions', return_value=[]):
            return TestClient(server.app).post(f"/api/operations/{p['id']}/execute", json={'version': p['version']}).json()

    def test_a_trial_sets_up_the_worker_and_the_job_and_leaves_the_mail_alone(self):
        s, cfg = setup()
        p = self.card(s, {'role': 'ap', 'portal': 'https://portal.example', 'route_mail': 'no'})['proposal']
        self.assertEqual((p['kind'], p['label'], p['targetKind']), ('role.apply', 'Set it up', 'role'))
        self.assertIsNone(s.get_agent('ap'))                                   # nothing before the yes
        r = self.run_card(s, cfg, p)
        self.assertEqual(r['status'], 'done')
        self.assertFalse(json.loads(s.get_agent('ap')['Config'])['triage_enabled'])
        self.assertNotIn('- ap:', agents.roster(s)); self.assertEqual(s.get_setting('default_profile') or '', '')
        self.assertIn('https://portal.example', json.loads(s.get_source(r['outcome']['workflow_id'])['ConfigJson'])['prompt'])
        from taskuary import concierge
        said = concierge._outcome_line('role.apply', p['params'], r['outcome'])
        self.assertIn('your mail goes where it went before', said); self.assertIn('switched off', said)

    def test_handing_over_the_mail_is_said_outright(self):
        s, cfg = setup()
        p = self.card(s, {'role': 'ap', 'route_mail': True})['proposal']
        self.assertEqual(self.run_card(s, cfg, p)['status'], 'done')
        self.assertEqual(s.get_setting('default_profile'), 'ap')
        self.assertIn('- ap:', agents.roster(s))

    def test_a_role_nobody_ships_is_answered_with_the_ones_there_are(self):
        s, _ = setup()
        out = self.card(s, {'role': 'astronaut'})
        self.assertFalse(out.get('proposal'))
        self.assertIn('accounts payable', out['say'].lower())

    def test_the_walk_asks_its_questions_then_puts_one_card_with_what_it_lays_out(self):
        from taskuary import concierge, terminal
        s, cfg = setup()
        def brain(system, user, **kw):
            if 'sort one set-up request' in system: return json.dumps({'kind': 'role', 'role': 'ap', 'why': 'their job'})
            if 'answer to set-up questions' in system: return json.dumps({'portal': 'portal.example/bills', 'route_mail': False})
            return '{}'
        def turn(text):
            line = 'CALL: ' + json.dumps({'kind': 'setup', 'params': {'text': text}})
            with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(concierge, '_compose_llm', return_value=brain):
                return concierge.say(s, text, llm=lambda *a, **k: line)
        first = turn('I am an AP rep, set Taskuary up for my job')
        self.assertFalse(first.get('proposal'))
        self.assertIn('1. What is the address of your bill-approval portal', first['say']); self.assertIn('2. Should your own', first['say'])
        p = turn('portal.example/bills, and I am only trying it out')['proposal']
        self.assertEqual((p['kind'], p['params']), ('role.apply', {'role': 'ap', 'portal': 'https://portal.example/bills', 'route_mail': False}))
        for line in ('Worker: AP.md', 'Your mail: goes where it goes today', 'created switched off'): self.assertIn(line, p['say'])
        self.assertEqual(self.run_card(s, cfg, p)['status'], 'done')
        self.assertEqual(s.get_setting('default_profile') or '', '')

    def test_a_worker_already_on_the_roster_is_said_to_still_be_reachable(self):
        from taskuary import concierge
        s, cfg = setup()
        s.upsert_agent('ap', 'accounts-payable', 'cli', json.dumps({'triage_enabled': True, 'purpose': 'AP work'}))
        o = roles.apply(s, cfg, 'ap', route_mail=False)
        self.assertFalse(o['profile_added']); self.assertTrue(o['on_roster'])
        said = concierge._outcome_line('role.apply', {}, o)
        self.assertIn("on triage's list", said); self.assertNotIn('where it went before', said)

    def test_the_catalogue_offers_it_with_its_questions(self):
        from taskuary import toolcatalog
        self.assertIn('role.apply', toolcatalog.bucket_list('app'))
        d = toolcatalog.describe('role.apply')
        self.assertIn('ap (accounts payable)', d); self.assertIn('route_mail', d); self.assertIn('a card the owner confirms', d)


class RunNowOpensTheWorkflowsTaskTests(unittest.TestCase):
    """The owner, 2026-10-08: "when you hit run now it should not be like report that runs in background but the task
    should show up in assistant canvas". The task is made before the call returns; the agent starts on its own thread."""
    def test_run_now_hands_back_the_task_and_the_agent_starts_off_the_request(self):
        import threading
        from fastapi.testclient import TestClient
        from taskuary import ingest, server
        s, _ = setup()
        s.upsert_agent('ap', 'accounts-payable', 'cli', '{}')
        sid = s.save_source({'Channel': 'report', 'Address': 'Bills', 'Owner': 'o', 'Active': 0,
                             'ConfigJson': json.dumps({'type': 'agent', 'title': 'Bills', 'agent': 'ap', 'browser': True, 'prompt': 'go'})}, 'o')
        started, gate = [], threading.Event()
        def slow_start(store, tid, text=None): gate.wait(5); started.append(tid)
        with mock.patch.object(server, 'store', s), mock.patch.object(ingest, '_auto_general', side_effect=slow_start):
            r = TestClient(server.app).post(f'/api/reports/{sid}/rerun').json()
            self.assertEqual(started, [])                       # the call did not wait for the agent
            gate.set()
        t = s.get_task(r['task_id'])
        self.assertEqual((r['workflow'], r['ref'], r['link']), (True, f"TQ-{r['task_id']:04d}", f"#task={r['task_id']}"))
        self.assertEqual((t['Assignee'], t['Tags']), ('agent:ap', 'needs:browser'))
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
