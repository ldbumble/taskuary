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
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.set_setting('general_auto_enabled', '1', 't'); s.set_setting('coding_auto_enabled', '1', 't')
    return s


def workflow(s, **cfg):
    base = {'type': 'agent', 'access': 'write', 'title': 'Weekly access review', 'agent': 'coding', 'prompt': 'Review who got admin this week and revoke stale grants.',
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
             mock.patch.object(blackboard, 'live_count', return_value=0), mock.patch('taskuary.llm.make_cli_llm') as cli, \
             mock.patch.object(workflows, '_spawn', lambda fn: fn()):
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
                     'ASK FIRST: revoking a grant', 'DONE WHEN: the review is posted'):
            self.assertIn(line, text)
        # ...and no rule of the code's (his live app, 2026-11-25): told it "may write to the connected systems this workflow names", a run
        # for posts on three networks, one named, wrote them as prose with no card - what an act may do is the gates', a card for his press
        for rule in ('ALLOWED ACTIONS', 'systems this workflow names', '--done', 'procedure selection'): self.assertNotIn(rule, text)
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
             mock.patch('taskuary.llm.make_cli_llm'), mock.patch.object(workflows, '_spawn', lambda fn: fn()):
            out = reports.run_report_source(s, s.get_source(sid), None)
        start.assert_not_called()
        self.assertEqual([q['TaskId'] for q in s.queued_dispatches()], [out['task_id']])                     # capacity is respected (PW-204)

    def test_a_read_only_agent_report_keeps_its_road_and_a_coding_workflow_is_a_task_too(self):
        """A coding workflow used to stay on the report road - a one-shot CLI in its checkout, filed under Reports - while its Run
        now made a task (the owner, 2026-10-16). Now only the read-only report reads through the CLI; the code job is a task."""
        s = store()
        report = workflow(s, title='Nightly digest', access=None); s_cfg = json.loads(s.get_source(report)['ConfigJson']); s_cfg.pop('access', None)
        s.save_source({'SourceId': report, 'ConfigJson': json.dumps(s_cfg)}, 'o')
        code = workflow(s, title='Dependency bumps', cwd='C:/work/repo')
        calls = []
        def make(store_, name, model=None, cwd=None, **kw):
            calls.append(cwd); return lambda system, user, **k: 'ran it\n- ok'
        # ...on the CLI the one resolver picks: its `agent` names the coding profile, which no road reads since profiles went
        with mock.patch('taskuary.llm.make_cli_llm', make), mock.patch('taskuary.agents.resolve_brain', return_value='cli:claude'), \
             mock.patch.object(general, 'start_session') as start, \
             mock.patch.object(ingest, '_auto_code') as auto_code, mock.patch.object(workflows, '_spawn', lambda fn: fn()):
            reports.run_report_source(s, s.get_source(report), None)
            out = reports.run_report_source(s, s.get_source(code), None)
        start.assert_not_called()                                                                          # neither is the regular agent's
        self.assertEqual(calls, [None])                                                                    # only the report reads through the CLI
        self.assertEqual((s.get_task(out['task_id'])['Kind'], s.get_task(out['task_id'])['Source']), ('coding', 'workflow'))
        auto_code.assert_called_once_with(s, out['task_id'])


class StepsRunTests(unittest.TestCase):
    def test_a_routine_running_its_steps_reads_at_work_and_its_chat_shows_the_steps_then_the_outcome(self):
        """A routine whose steps run by code read "not started yet" with an empty chat for as long as they ran (walk, 2026-11-17): nothing
        read the run in flight. Mid-run - the second step still going - it reads working, the done step drawn in a turn at work; after, that
        turn holds both steps and the run's own last word."""
        from taskuary import conversation, flow, funnel, taskstate
        s = store()
        sid = s.save_source({'Channel': 'report', 'Address': 'Duplicate bill check', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(
            {'type': 'agent', 'access': 'write', 'title': 'Duplicate bill check', 'flow': [
                {'id': 's1', 'kind': 'source', 'label': 'Read AP bills', 'type': 'sqlite'}, {'id': 's2', 'kind': 'source', 'label': 'Read vendors', 'type': 'sqlite'}]})}, 'o')
        mid = {}
        def step(store_, st, ctx, llm, tid, *a, **k):
            if st['id'] == 's2':
                mid.update(key=taskstate.state(s, s.get_task(tid)), idle=funnel.idle_state(s, tid)['row'], chat=conversation.items(s, tid))
            return {'head': f"read {st['label'].split()[-1]}"}
        with mock.patch.dict(flow.RUNNERS, {'source': step}):
            out = workflows.run(s, s.get_source(sid), trigger='manual', background=False)
        self.assertEqual((mid['key'], mid['idle']), ('working', 'working'))
        turns = [x for x in mid['chat']['items'] if x['kind'] == 'turn']
        self.assertTrue(mid['chat']['working'])
        self.assertEqual([(t['state'], [x['text'] for x in t['steps']]) for t in turns], [('working', ['Read AP bills: read bills'])])
        # ...and the run itself opens its chat, named - what started it, never only the box's chip (the owner, 2026-11-18)
        self.assertEqual([(x['kind'], x.get('head')) for x in mid['chat']['items']][:1], [('arrival', 'From the routine Duplicate bill check')])
        xs = conversation.items(s, out['task_id'])['items']
        self.assertEqual((xs[0]['id'], xs[0]['head']), (f"s:{out['task_id']}", 'From the routine Duplicate bill check'))
        turns = [x for x in xs if x['kind'] == 'turn']
        self.assertEqual([(t['state'], len(t['steps'])) for t in turns], [('done', 2)])
        self.assertTrue(turns[0]['text'].startswith('Ran 2 steps in'))


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
                                                'from_name': 'Erin', 'from_email': 'erin@ours.com', 'body': 'Can I take next Friday off?', 'to': ['owner@ours.com']}, llm=llm)
            t = s.get_task(out['task_id'])
            self.assertEqual((t['Kind'], playbooks.of_task(t)), ('general', 'pto'))                          # the procedure, not a coding verdict (PW-205)
            self.assertEqual(start.call_count, 1)                                                            # one start


if __name__ == '__main__':
    unittest.main()
