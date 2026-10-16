"""Every run of a workflow is ONE road: a task worked by its agent, never triage, never a report row.

The owner, 2026-10-16: "Run now creates task but if it runs on schedule it should also show up as task. what's the logo on it
and what does it show triggered it in the task card?" A scheduled workflow with a checkout (`cwd`) went down the REPORT road - a
one-shot CLI whose answer was filed under Reports - while Run now made a task, and a coding run started from Run now opened in
whatever checkout the coding agent guessed rather than the folder the workflow names. These pin the one road end to end: the
clock, Run now, the assistant and the phone each make one task of the same shape with their trigger on it; it runs in its folder,
as the worker it names, on the default brain; a failed start says why; a run still working is not started twice.
"""
import json, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import blackboard, compose, general, ingest, remote_assistant, reports, server, terminal, triage, workflows
from taskuary.store import MemoryStore


class FakeTerm:
    def __init__(self, sid, tid, cwd): self.sid, self.task_id, self.cwd, self.alive, self.started = sid, tid, cwd, True, '2026-10-16 08:00:00'
    def info(self, tail=0): return {'sid': self.sid, 'taskId': self.task_id, 'alive': self.alive, 'cwd': self.cwd}


def store():
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.upsert_agent('ap', 'accounts-payable', 'general', json.dumps({}))
    s.set_setting('general_auto_enabled', '1', 't'); s.set_setting('coding_auto_enabled', '1', 't')
    return s


def workflow(s, **cfg):
    base = {'type': 'agent', 'access': 'write', 'title': 'Vendor bill sweep', 'agent': 'ap', 'prompt': 'Post the bills Erin Blake approved.',
            'cron': '0 8 * * 1', 'route': {'triage': {'how': 'never'}}}
    base.update(cfg)
    return s.save_source({'Channel': 'report', 'Address': base['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(base)}, 'o')


class Harness(unittest.TestCase):
    """The CLI and the general session are fakes; triage and ingest are trip-wires; the worker starts inline."""
    def setUp(self):
        self.s, self.opened, self.session = store(), [], mock.Mock()
        terminal.SESSIONS.clear()
        def fake_open(store_, agent, tid, repo, cwd, rows, cols, actor, model=None, resume=None, brain=None, seed_fn=None):
            t = FakeTerm(f's{tid}', tid, cwd); terminal.SESSIONS[t.sid] = t
            self.opened.append({'agent': agent, 'tid': tid, 'repo': repo, 'cwd': cwd, 'brain': brain}); return t
        for p in (mock.patch.object(workflows, '_spawn', lambda fn: fn()), mock.patch.object(terminal, 'open_session', side_effect=fake_open),
                  mock.patch.object(general, 'start_session', return_value=self.session), mock.patch.object(general, 'history', return_value=[]),
                  mock.patch.object(blackboard, 'live_count', return_value=0), mock.patch.object(server, 'store', self.s),
                  mock.patch.object(remote_assistant, 'send')):
            p.start(); self.addCleanup(p.stop)
        self.start_session = general.start_session
        self.ingested = mock.patch.object(ingest, 'ingest_message', side_effect=AssertionError('a workflow run never goes through ingest')).start()
        self.classified = mock.patch.object(triage, 'classify_intent', side_effect=AssertionError('nor through triage')).start()
        self.oneshot = mock.patch('taskuary.llm.make_cli_llm', side_effect=AssertionError('nor a one-shot report CLI')).start()
        self.addCleanup(mock.patch.stopall); self.addCleanup(terminal.SESSIONS.clear)

    def tick(self, sid): return reports.run_one(self.s, self.s.get_source(sid), None, trigger='schedule')
    def run_now(self, sid): return TestClient(server.app).post(f'/api/reports/{sid}/rerun').json()
    def shape(self, tid):
        t = self.s.get_task(tid)
        return {k: t[k] for k in ('Source', 'SourceRef', 'Kind', 'Assignee', 'Status')} | {'Tags': sorted(str(t['Tags'] or '').split(','))}
    def report_rows(self): return self.s._rows("SELECT * FROM message WHERE Channel='report'")


class OneRoadTests(Harness):
    def test_a_tick_and_run_now_each_make_exactly_one_task_of_the_same_shape_with_the_trigger_on_it(self):
        sid = workflow(self.s)
        self.tick(sid)
        [a] = self.s.dock_tasks(f'workflow:{sid}')
        self.s.update_task(a['TaskId'], {'Status': 'done'}, 'o'); terminal.SESSIONS.clear()
        got = self.run_now(sid)
        b = self.s.get_task(got['task_id'])
        self.assertEqual(len(self.s.dock_tasks(f'workflow:{sid}')), 2)
        self.assertEqual((got['link'], got['workflow']), (f"#task={b['TaskId']}", True))
        sa, sb = self.shape(a['TaskId']), self.shape(b['TaskId'])
        self.assertEqual(sa['Tags'], ['workflow-trigger:schedule']); self.assertEqual(sb['Tags'], ['workflow-trigger:manual'])
        self.assertEqual({k: v for k, v in sa.items() if k not in ('Tags', 'Status')}, {k: v for k, v in sb.items() if k not in ('Tags', 'Status')})
        self.assertEqual((sb['Source'], sb['SourceRef'], sb['Kind'], sb['Assignee']), ('workflow', f'workflow:{sid}', 'general', 'agent:ap'))
        self.assertEqual(self.report_rows(), [])                                                      # nothing filed under Reports
        self.assertEqual(self.session.send_prompt.call_count, 2)
        self.assertIn('Vendor bill sweep - scheduled', self.session.send_prompt.call_args_list[0][0][0])
        self.assertIn('run now by the owner', self.session.send_prompt.call_args_list[1][0][0])
        self.assertIn('TQ-', self.s.report_runs(sid, 1)[-1]['subject'])                               # the clock's history names the task

    def test_a_scheduled_cwd_workflow_is_a_task_in_its_own_folder_not_a_report_row(self):
        here = tempfile.mkdtemp()
        sid = workflow(self.s, title='Dependency bumps', agent='coding', cwd=here, prompt='Bump what is outdated in northwind/ledger.')
        out = self.tick(sid)
        [t] = self.s.dock_tasks(f'workflow:{sid}')
        self.assertEqual((t['Kind'], t['Source'], t['Assignee'], t['Status']), ('coding', 'workflow', 'agent:coding', 'in_progress'))
        self.assertEqual([(o['agent'], o['cwd'], o['repo']) for o in self.opened], [('coding', here, None)])   # its folder, no guessed repo
        self.assertEqual(self.report_rows(), [])
        self.assertIn(t['TaskId'], (out.get('task_id'),))
        self.start_session.assert_not_called()

    def test_run_now_on_a_cwd_workflow_opens_in_that_folder_too(self):
        here = tempfile.mkdtemp()
        sid = workflow(self.s, title='Dependency bumps', agent=None, cwd=here)
        got = self.run_now(sid)
        self.assertEqual([(o['agent'], o['cwd']) for o in self.opened], [('coding', here)])          # unnamed: the coding profile
        self.assertEqual(self.s.get_task(got['task_id'])['Tags'], 'workflow-trigger:manual')

    def test_a_cwd_that_is_gone_says_why_on_the_task_and_starts_nothing(self):
        sid = workflow(self.s, title='Dependency bumps', agent='coding', cwd='C:/nowhere/northwind-ledger-gone')
        terminal.open_session.side_effect = None
        with mock.patch.object(terminal, 'open_session', side_effect=AssertionError('never opened')):
            self.tick(sid)
        [t] = self.s.dock_tasks(f'workflow:{sid}')
        said = ' '.join(c['Body'] for c in self.s.list_comments(t['TaskId']))
        self.assertIn('C:/nowhere/northwind-ledger-gone', said); self.assertIn("Couldn't start", said)
        self.assertEqual(self.s.get_dispatch(t['TaskId'])['State'], 'failed')                        # a setup problem: no retry loop

    def test_the_assistant_and_the_phone_take_the_same_road_and_say_who_started_it(self):
        sid = workflow(self.s)
        op = {'kind': 'report.run', 'target': sid, 'params': {}}
        out = server._run_operation(op, None)
        self.assertEqual(self.s.get_task(out['task_id'])['Tags'], 'workflow-trigger:assistant')
        self.s.update_task(out['task_id'], {'Status': 'done'}, 'o'); terminal.SESSIONS.clear()
        with mock.patch.object(remote_assistant, 'asking', return_value={'channel': 'whatsapp', 'chat': 'c1'}):
            phoned = server._run_operation(op, None)
        self.assertEqual(self.s.get_task(phoned['task_id'])['Tags'], 'workflow-trigger:phone')
        self.assertEqual(phoned['ref'], f"TQ-{phoned['task_id']:04d}")                                 # the receipt names the task, at once
        remote_assistant.send.assert_not_called()                                                     # ...and nothing lands later to say it twice
        self.assertEqual(self.report_rows(), [])

    def test_a_run_still_working_is_not_started_twice_on_overlapping_ticks(self):
        sid = workflow(self.s)
        self.tick(sid)
        terminal.SESSIONS[f"s{self.s.dock_tasks(f'workflow:{sid}')[0]['TaskId']}"] = FakeTerm('live', self.s.dock_tasks(f'workflow:{sid}')[0]['TaskId'], None)
        second = self.tick(sid); again = self.run_now(sid)
        [t] = self.s.dock_tasks(f'workflow:{sid}')
        self.assertEqual(self.session.send_prompt.call_count, 1)
        self.assertEqual(again['task_id'], t['TaskId'])                                              # Run now takes you to the one running
        self.assertIn('still working', ' '.join(c['Body'] for c in self.s.list_comments(t['TaskId'])))
        self.assertFalse(self.s.report_runs(sid, 3)[0].get('failed'))
        # ...but a run that is only waiting on the owner's yes - no session - does not hold tomorrow's back
        terminal.SESSIONS.clear(); self.tick(sid)
        self.assertEqual(len(self.s.dock_tasks(f'workflow:{sid}')), 2)

    def test_a_named_coding_profile_on_a_general_run_is_an_old_brain_pick_not_a_role(self):
        sid = workflow(self.s, agent='coding')                                                        # no cwd: the regular agent
        self.tick(sid)
        [t] = self.s.dock_tasks(f'workflow:{sid}')
        self.assertEqual((t['Kind'], t['Assignee']), ('general', None))
        self.start_session.assert_called_once()

    def test_a_read_only_agent_report_keeps_the_report_road(self):
        cfg = {'type': 'agent', 'title': 'Nightly digest of northwind/ledger', 'agent': 'coding', 'prompt': 'Summarise the night.', 'daily_at': '06:00'}
        sid = self.s.save_source({'Channel': 'report', 'Address': cfg['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 'o')
        self.oneshot.side_effect = None; self.oneshot.return_value = lambda system, user, **k: 'ran it\n- nothing broke'
        self.tick(sid)
        self.assertEqual(self.s.dock_tasks(f'workflow:{sid}'), [])
        self.assertEqual(len(self.report_rows()), 1)


class CardTests(unittest.TestCase):
    def test_the_card_reads_the_workflow_and_its_trigger_off_the_task(self):
        s = store(); sid = workflow(s)
        with mock.patch.object(workflows, '_spawn', lambda fn: None):
            tid = workflows.run(s, s.get_source(sid))['task_id']
        self.assertEqual(workflows.of_task(s, s.get_task(tid)),
                         {'source_id': sid, 'title': 'Vendor bill sweep', 'trigger': 'schedule', 'schedule': 'Mondays 08:00', 'started_by': 'its schedule',
                          'runs_on': ''})                                                                       # no brain connected in this store
        with mock.patch.object(server, 'store', s):
            self.assertEqual(TestClient(server.app).get(f'/api/tasks/{tid}').json()['workflow']['started_by'], 'its schedule')
        s.delete_source(sid)                                                                           # the workflow deleted: the run keeps its name
        self.assertEqual(workflows.of_task(s, s.get_task(tid))['title'], 'Vendor bill sweep')
        self.assertIsNone(workflows.of_task(s, {'Source': 'email'}))

    def test_a_parked_workflow_run_on_the_rail_wears_the_workflow_mark_not_the_terminal(self):
        from taskuary import funnel
        s = store(); sid = workflow(s)
        with mock.patch.object(workflows, '_spawn', lambda fn: None):
            tid = workflows.run(s, s.get_source(sid))['task_id']
        mail = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        live = [{'taskId': x, 'agent': 'ap', 'sid': f's{x}', 'waiting': True, 'state': 'parked', 'line': 'ap is waiting on you'} for x in (tid, mail)]
        self.assertEqual([c['channel'] for c in funnel.from_agents(s, live_state=live)], ['workflow', ''])

    def test_the_clock_is_said_the_way_the_owner_says_it(self):
        w = workflows.when_words
        self.assertEqual([w({'cron': '0 8 * * 1'}), w({'cron': '30 7 * * 1-5'}), w({'daily_at': '08:00'}), w({'cron': '0 9 1 * *'})],
                         ['Mondays 08:00', 'weekdays 07:30', 'daily 08:00', 'day 1 of each month, 09:00'])
        self.assertEqual(w({'every_minutes': 15}), 'every 15 minutes')


class ComposerTests(unittest.TestCase):
    def test_the_composer_tells_the_model_every_run_is_a_task_and_never_builds_a_watch(self):
        self.assertIn('Each run is itself a task', compose.WORKFLOW_SYSTEM)
        self.assertNotIn('"watch"', compose.WORKFLOW_SYSTEM)
        self.assertNotIn('files its result', compose.WORKFLOW_SYSTEM)
        s = store()
        def llm(system, user, **kw): return json.dumps({'config': {'type': 'agent', 'title': 'Bumps', 'agent': 'coding', 'prompt': 'bump deps',
                                                                   'cwd': 'C:/work/ledger'}, 'watch': 'when a bump breaks the build'})
        cfg = compose.compose_workflow(s, 'bump deps in C:/work/ledger and tell me if it breaks', llm)['config']
        self.assertEqual(cfg['route'], {'triage': {'how': 'never'}})                                  # a run is a task: nothing to watch for


if __name__ == '__main__':
    unittest.main()
