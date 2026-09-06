"""Workflows are configured jobs; procedures are how a matching request is handled (PW-203 to PW-208).

A scheduled agent workflow used to run inside the report loop through a coding CLI and file its answer as a
report that triage read back as an arrival. Now a triggered workflow is dispatched straight to its worker:
a task carrying the definition and this run's context, through the same capacity gate as any unattended
start, never through message triage, and never a coding agent unless the job is code. A playbook stays a
playbook; a PTO-style request still selects its procedure in triage without being forced to coding and
without a second agent start.
"""
import json, os, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import blackboard, general, ingest, playbooks, reports, server, terminal, triage, workflows
from taskuary.store import MemoryStore

BILL = ('# Post a vendor bill\nwhen: a card transaction or an invoice arrives\nuses: intacct\nsteps: match the vendor, post it\n'
        'alone: yes\nask first: anything over 500\ndone when: the bill shows in Intacct\n')


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.set_setting('general_auto_enabled', '1', 't'); s.set_setting('coder_auto_enabled', '1', 't')
    return s


def workflow(s, **cfg):
    base = {'type': 'agent', 'access': 'write', 'title': 'Weekly access review', 'agent': 'coder', 'prompt': 'Review who got admin this week and revoke stale grants.',
            'cron': '0 8 * * 1', 'uses': ['entra'], 'inputs': {'window': '7d'}, 'ask_first': 'revoking a grant', 'done_when': 'the review is posted'}
    base.update(cfg)
    return s.save_source({'Channel': 'report', 'Address': base['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(base)}, 'o')


class DefinitionTests(unittest.TestCase):
    def test_a_workflow_is_read_as_a_definition_and_a_playbook_stays_a_procedure(self):
        s = store(); sid = workflow(s)
        d = workflows.definition(s, s.get_source(sid))
        self.assertEqual((d['title'], d['runs_on'], d['allowed_actions'], d['connections'], d['inputs']),
                         ('Weekly access review', 'general', ['write'], ['entra'], {'window': '7d'}))
        self.assertEqual((d['approvals'], d['done_when'], d['schedule']), ('revoking a grant', 'the review is posted', {'cron': '0 8 * * 1'}))
        self.assertTrue(workflows.is_workflow(s.get_source(sid)))
        self.assertFalse(workflows.is_workflow({'type': 'agent', 'prompt': 'read only'}))                   # a report reads; it is not a workflow
        self.assertEqual(workflows.runs_on({'type': 'agent', 'access': 'write', 'cwd': 'C:/repo'}), 'coding')   # a checkout: code work
        self.assertEqual(workflows.runs_on({'type': 'agent', 'access': 'write', 'runs_on': 'coding'}), 'coding')
        home = tempfile.mkdtemp()
        with mock.patch('taskuary.config.home', return_value=__import__('pathlib').Path(home)):
            playbooks.write('bill', BILL)
            cat = workflows.catalog(s)
        self.assertEqual([w['title'] for w in cat['workflows']], ['Weekly access review'])
        self.assertEqual([(p['slug'], p['when']) for p in cat['procedures']], [('bill', 'a card transaction or an invoice arrives')])
        with mock.patch('taskuary.config.home', return_value=__import__('pathlib').Path(home)):
            self.assertEqual([b['slug'] for b in playbooks.list_all()], ['bill'])                              # untouched (PW-207)
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.config.home', return_value=__import__('pathlib').Path(home)):
            got = TestClient(server.app).get('/api/workflows').json()
        self.assertEqual((len(got['workflows']), len(got['procedures'])), (1, 1))


class DispatchTests(unittest.TestCase):
    def _run(self, s, sid, trigger='schedule'):
        session = mock.Mock()
        with mock.patch.object(general, 'start_session', return_value=session) as start, mock.patch.object(general, 'history', return_value=[]), \
             mock.patch.object(ingest, 'ingest_message') as ingested, mock.patch.object(triage, 'classify_intent') as classified, \
             mock.patch.object(blackboard, 'live_count', return_value=0), mock.patch('taskuary.llm.make_cli_llm') as cli:
            out = reports.run_report_source(s, s.get_source(sid), None, trigger=trigger)
        return out, start, session, ingested, classified, cli

    def test_a_scheduled_run_goes_straight_to_the_regular_agent_with_the_definition(self):
        s = store(); sid = workflow(s)
        out, start, session, ingested, classified, cli = self._run(s, sid)
        t = s.get_task(out['task_id'])
        self.assertEqual((t['Kind'], t['Source'], t['SourceRef']), ('general', 'workflow', f'workflow:{sid}'))
        start.assert_called_once(); self.assertEqual(start.call_args[0][1], out['task_id'])
        text = session.send_prompt.call_args[0][0]
        for line in ('WORKFLOW RUN: Weekly access review - scheduled', 'OBJECTIVE: Review who got admin', 'INPUTS: {"window": "7d"}', 'CONNECTIONS: entra',
                     'ALLOWED ACTIONS: you may write', 'ASK FIRST: revoking a grant', 'DONE WHEN: the review is posted', 'no triage and no procedure selection'):
            self.assertIn(line, text)
        ingested.assert_not_called(); classified.assert_not_called(); cli.assert_not_called()               # no triage, no coding CLI
        self.assertEqual([m for m in s.feed(limit=50) if m.get('Channel') == 'report'], [])                  # nothing filed as a report
        runs = s.report_runs(sid, 3)
        self.assertEqual(len(runs), 1); self.assertIn(f"TQ-{out['task_id']:04d}", runs[0]['subject']); self.assertFalse(runs[0].get('failed'))

    def test_run_now_is_the_same_road_and_says_so(self):
        s = store(); sid = workflow(s)
        out, start, session, *_ = self._run(s, sid, trigger='manual')
        self.assertIn('run now by the owner', session.send_prompt.call_args[0][0])
        self.assertIn('manual', s.report_runs(sid, 1)[0]['subject'])

    def test_a_full_house_queues_the_run_and_starts_nothing(self):
        s = store(); sid = workflow(s)
        with mock.patch.object(general, 'start_session') as start, mock.patch.object(blackboard, 'live_count', return_value=99), \
             mock.patch('taskuary.llm.make_cli_llm'):
            out = reports.run_report_source(s, s.get_source(sid), None)
        start.assert_not_called()
        self.assertEqual([q['TaskId'] for q in s.queued_dispatches()], [out['task_id']])                     # capacity is respected (PW-204)

    def test_a_read_only_agent_report_and_a_coding_workflow_keep_their_road(self):
        s = store()
        report = workflow(s, title='Nightly digest', access=None); s_cfg = json.loads(s.get_source(report)['ConfigJson']); s_cfg.pop('access', None)
        s.save_source({'SourceId': report, 'ConfigJson': json.dumps(s_cfg)}, 'o')
        code = workflow(s, title='Dependency bumps', cwd='C:/work/repo')
        calls = []
        def make(store_, name, model=None, cwd=None, **kw):
            calls.append(cwd); return lambda system, user, **k: 'ran it\n- ok'
        with mock.patch('taskuary.llm.make_cli_llm', make), mock.patch.object(general, 'start_session') as start, mock.patch.object(ingest, '_auto_code') as auto_code:
            reports.run_report_source(s, s.get_source(report), None)
            with mock.patch.object(ingest, 'ingest_message') as ingested:
                self.assertIsNotNone(reports.run_report_source(s, s.get_source(code), None))
        start.assert_not_called()                                                                          # neither is the regular agent's
        self.assertEqual(calls, [None, 'C:/work/repo'])                                                    # the report reads; the code job runs in its checkout


class ProcedureTests(unittest.TestCase):
    def test_a_pto_style_request_selects_its_procedure_without_forced_coding_or_a_second_start(self):
        s = store(); home = tempfile.mkdtemp()
        s.set_setting('team_domains', 'ours.com', 't')
        def llm(system, user, **kw): return json.dumps({'intent': 'task', 'kind': 'general', 'why': 'a PTO request', 'playbook': 'pto'})
        session = mock.Mock()
        with mock.patch('taskuary.config.home', return_value=__import__('pathlib').Path(home)):
            playbooks.write('pto', '# PTO request\nwhen: someone asks for time off\nuses: bamboo\nsteps: log it\nalone: yes\nask first: overlaps\ndone when: it is in the calendar\n')
            with mock.patch.object(general, 'start_session', return_value=session) as start, mock.patch.object(general, 'history', return_value=[]), \
                 mock.patch.object(general, 'provider_options', return_value=[{'pick': 'x', 'label': 'x', 'type': 'api'}]), \
                 mock.patch.object(blackboard, 'live_count', return_value=0), mock.patch.object(ingest, '_spawn', lambda fn, *a: fn(*a)), \
                 mock.patch('taskuary.senders.known', return_value=(True, 'a colleague')):
                out = ingest.ingest_message(s, {'external_id': 'pto1', 'channel': 'email', 'conversation_id': 'c:pto', 'subject': 'PTO next Friday',
                                                'from_name': 'Chana', 'from_email': 'chana@ours.com', 'body': 'Can I take next Friday off?', 'to': ['owner@ours.com']}, llm=llm)
            t = s.get_task(out['task_id'])
            self.assertEqual((t['Kind'], playbooks.of_task(t)), ('general', 'pto'))                          # the procedure, not a coding verdict (PW-205)
            self.assertEqual(start.call_count, 1)                                                            # one start
            self.assertIn('PROCEDURE FOR THIS JOB', general._prompt(s, out['task_id'])[0]) if hasattr(general, '_prompt') else None


if __name__ == '__main__':
    unittest.main()
