"""A workflow runs on the general agents' brain, and may ask that brain for a harder model or more effort.

The owner, 2026-10-16: "Workflow by default should use same brain as agents - general agents but they can choose for hard workflow
to use higher level model and effort". A workflow's `model` was read by nobody once its runs became tasks (workflows.run) - nor
before, for Run now - so a workflow set to opus ran on whatever the session defaulted to. These pin: blank is the general agents'
brain on its main model; a set model and effort reach the CLI's own argv (Claude Code `--model`/`--effort`, Codex `-m`/
`-c model_reasoning_effort=`); an effort the CLI cannot take is dropped and the task says why; the clock and Run now both honour it.
"""
import json, tempfile, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import agents, blackboard, compose, config, general, reports, server, terminal, workflows
from taskuary.store import MemoryStore

CFG = {'cli_connections': {'claude': {'cmd': 'claude', 'model': 'claude-opus-5-5', 'light_model': 'claude-sonnet-5-5'},
                           'codex': {'cmd': 'codex', 'model_arg': '-m'}, 'copilot': {'cmd': 'copilot'}}}


def store(**settings):
    s = MemoryStore()
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.upsert_agent('ap', 'accounts-payable', 'general', json.dumps({}))
    for k, v in {'general_auto_enabled': '1', 'coding_auto_enabled': '1', 'default_brain': 'claude', **settings}.items(): s.set_setting(k, v, 'owner')
    return s


def workflow(s, **cfg):
    base = {'type': 'agent', 'access': 'write', 'title': 'Month-end accruals', 'agent': 'ap', 'prompt': 'Book the accruals Gail Moreno listed.',
            'cron': '0 8 1 * *', 'route': {'triage': {'how': 'never'}}, **cfg}
    return s.save_source({'Channel': 'report', 'Address': base['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(base)}, 'o')


class Base(unittest.TestCase):
    def setUp(self):
        # the conftest stubs the brains out; these tests ARE about the brains, so the real readers come back over CFG
        for p in (mock.patch.object(config, 'load', return_value=CFG), mock.patch('taskuary.agents.runs_here', return_value=True),
                  mock.patch.object(agents, 'connection_brains', getattr(agents.connection_brains, 'real', agents.connection_brains)),
                  mock.patch.object(agents, 'default_pick', getattr(agents.default_pick, 'real', agents.default_pick))):
            p.start(); self.addCleanup(p.stop)


class BrainTests(Base):
    def test_blank_is_the_general_agents_brain_on_its_main_model(self):
        b = workflows.brain(store(), {})
        self.assertEqual((b['pick'], b['cli'], b['model'], b['effort'], b['dropped']), ('cli:claude', 'claude', 'claude-opus-5-5', '', ''))
        self.assertEqual(b['said'], 'Claude Code · claude-opus-5-5')
        # ...and it follows the general agent's own setting, not the coding one
        b = workflows.brain(store(assistant_ai='cli:codex'), {})
        self.assertEqual((b['pick'], b['cli'], b['model']), ('cli:codex', 'codex', ''))
        self.assertEqual(workflows.brain(store(assistant_model='claude-sonnet-5-5'), {})['model'], 'claude-sonnet-5-5')

    def test_a_set_model_and_effort_ride_the_same_brain_as_one_pick(self):
        self.assertEqual(workflows.brain(store(), {'model': 'opus', 'effort': 'high'})['model'], 'opus@high')
        b = workflows.brain(store(assistant_ai='cli:codex'), {'model': 'gpt-5.5', 'effort': 'xhigh'})
        self.assertEqual((b['model'], b['said']), ('gpt-5.5@xhigh', 'OpenAI Codex CLI · gpt-5.5, xhigh effort'))
        # effort alone keeps the brain's own model
        self.assertEqual(workflows.brain(store(), {'effort': 'max'})['model'], 'claude-opus-5-5@max')
        self.assertEqual(workflows.brain(store(assistant_ai='cli:codex'), {'effort': 'high'})['model'], '@high')

    def test_an_effort_the_cli_cannot_take_is_dropped_with_a_reason(self):
        b = workflows.brain(store(assistant_ai='cli:codex'), {'model': 'gpt-5.5', 'effort': 'max'})
        self.assertEqual(b['model'], 'gpt-5.5'); self.assertIn('max', b['dropped']); self.assertIn('xhigh', b['dropped'])
        b = workflows.brain(store(assistant_ai='cli:copilot'), {'effort': 'high'})
        self.assertEqual((b['model'], b['effort']), ('', '')); self.assertIn('no effort setting', b['dropped'])
        s = store(); cid = s.save_connector({'Type': 'anthropic', 'Name': 'Anthropic', 'ConfigJson': '{}', 'Active': 1, 'Secret': 'k'}, 'owner')
        s.set_setting('assistant_ai', f'connector:{cid}', 'owner')
        b = workflows.brain(s, {'model': 'claude-opus-5', 'effort': 'high'})
        self.assertEqual((b['pick'], b['model'], b['effort']), (f'connector:{cid}', 'claude-opus-5', '')); self.assertIn('effort', b['dropped'])

    def test_a_coding_workflow_rides_the_same_brain_when_it_is_a_cli_else_the_coding_cli(self):
        b = workflows.brain(store(assistant_ai='cli:codex'), {'cwd': 'C:/work/ledger', 'model': 'gpt-5.5'})
        self.assertEqual((b['key'], b['model']), ('codex', 'gpt-5.5'))
        s = store(); cid = s.save_connector({'Type': 'anthropic', 'Name': 'Anthropic', 'ConfigJson': '{}', 'Active': 1, 'Secret': 'k'}, 'owner')
        s.set_setting('assistant_ai', f'connector:{cid}', 'owner')
        self.assertEqual(workflows.brain(s, {'cwd': 'C:/work/ledger'})['key'], 'claude')                 # an API brain has no terminal

    def test_the_editor_is_offered_the_brains_models_and_only_the_efforts_each_takes(self):
        o = workflows.brain_options(store(assistant_ai='cli:codex'))
        self.assertEqual((o['cli'], o['said']), ('codex', 'OpenAI Codex CLI · its default model'))
        self.assertTrue(o['models'] and all(set(m['efforts']) <= {'low', 'medium', 'high', 'xhigh', 'max'} for m in o['models']))
        self.assertNotIn('max', next(m for m in o['models'] if m['id'] == 'gpt-5.5')['efforts'])
        self.assertEqual(workflows.brain_options(store(assistant_ai='cli:copilot'))['efforts'], [])       # no flag to spell: nothing offered
        with mock.patch.object(server, 'store', store()):
            got = TestClient(server.app).get('/api/workflows/brain').json()
        self.assertEqual(got['said'], 'Claude Code · claude-opus-5-5')


class ArgvTests(unittest.TestCase):
    def argv(self, prof, model):
        with mock.patch('taskuary.agents._resolve_cmd', side_effect=lambda c: [c]): return terminal.agent_argv(prof, model)

    def test_a_live_pane_gets_the_model_and_the_effort_in_its_own_clis_spelling(self):
        a = self.argv({'cmd': 'claude'}, 'opus@high')
        self.assertEqual(a[a.index('--model') + 1], 'opus'); self.assertEqual(a[a.index('--effort') + 1], 'high')
        a = self.argv({'cmd': 'codex', 'model_arg': '-m'}, 'gpt-5.5@high')
        self.assertEqual(a[a.index('-m') + 1], 'gpt-5.5'); self.assertIn('model_reasoning_effort=high', a)
        a = self.argv({'cmd': 'codex', 'model_arg': '-m'}, '@low')
        self.assertNotIn('-m', a); self.assertIn('model_reasoning_effort=low', a)                      # effort alone: no empty model flag
        self.assertFalse(any('@' in str(x) for x in self.argv({'cmd': 'copilot'}, 'auto@high')))       # no flag to spell: never `auto@high`

    def test_a_headless_turn_with_effort_alone_names_no_empty_model(self):
        from taskuary.agents import run_cli
        with mock.patch('taskuary.agents._resolve_cmd', return_value=['X']), mock.patch('taskuary.spawn.popen', side_effect=RuntimeError('stop')) as pop:
            with self.assertRaises(RuntimeError): run_cli({'cmd': 'claude', 'args': ['-p'], 'model': '@high'}, 'hi', lambda *a: None)
        argv = pop.call_args[0][0]
        self.assertNotIn('--model', argv); self.assertEqual(argv[argv.index('--effort') + 1], 'high')


class FakeTerm:
    def __init__(self, sid, tid, cwd): self.sid, self.task_id, self.cwd, self.alive, self.started = sid, tid, cwd, True, '2026-10-16 08:00:00'
    def info(self, tail=0): return {'sid': self.sid, 'taskId': self.task_id, 'alive': self.alive, 'cwd': self.cwd}


class RoadTests(Base):
    """The clock and Run now both start the task's session with the workflow's brain - general and coding alike."""
    def setUp(self):
        super().setUp()
        self.s, self.opened, self.made = store(), [], []
        terminal.SESSIONS.clear()
        def fake_open(store_, agent, tid, repo, cwd, rows, cols, actor, model=None, resume=None, brain=None, seed_fn=None):
            t = FakeTerm(f's{tid}', tid, cwd); terminal.SESSIONS[t.sid] = t
            self.opened.append({'tid': tid, 'model': model, 'brain': brain}); return t
        def fake_session(store_, tid, connector_id=None, model=None, pick=None):
            self.made.append({'tid': tid, 'pick': pick, 'model': model})
            return mock.Mock(sid=f'g{tid}', task_id=tid, alive=True, browser_wanted=False, busy=False, pick=pick or '')
        # the router's start runs for real down to the session it builds (the conftest guard passes an owner's start through)
        guarded = general.start_session
        def start(st, tid, connector_id=None, model=None, actor='owner', pick=None): return guarded(st, tid, connector_id, model, 'owner', pick)
        for p in (mock.patch.object(workflows, '_spawn', lambda fn: fn()), mock.patch.object(terminal, 'open_session', side_effect=fake_open),
                  mock.patch.object(general, 'start_session', start), mock.patch.object(terminal, 'resume_task'),
                  mock.patch.object(general, 'GeneralSession', side_effect=fake_session), mock.patch.object(general, 'history', return_value=[]),
                  mock.patch.object(blackboard, 'live_count', return_value=0), mock.patch.object(server, 'store', self.s)):
            p.start(); self.addCleanup(p.stop)
        self.addCleanup(terminal.SESSIONS.clear)

    def tick(self, sid): return reports.run_one(self.s, self.s.get_source(sid), None, trigger='schedule')
    def run_now(self, sid): return TestClient(server.app).post(f'/api/reports/{sid}/rerun').json()
    def said(self, tid): return ' '.join(c['Body'] for c in self.s.list_comments(tid))

    def test_a_general_run_on_the_clock_and_on_run_now_starts_on_the_workflows_model_and_effort(self):
        sid = workflow(self.s, model='opus', effort='high')
        self.tick(sid)
        [a] = self.s.dock_tasks(f'workflow:{sid}')
        self.s.update_task(a['TaskId'], {'Status': 'done'}, 'o'); terminal.SESSIONS.clear()
        b = self.run_now(sid)['task_id']
        self.assertEqual([(m['tid'], m['pick'], m['model']) for m in self.made],
                         [(a['TaskId'], 'cli:claude', 'opus@high'), (b, 'cli:claude', 'opus@high')])
        self.assertIn('Claude Code · opus, high effort', self.said(b))
        self.assertEqual(workflows.of_task(self.s, self.s.get_task(b))['runs_on'], 'Claude Code · opus, high effort')

    def test_a_blank_workflow_starts_on_the_general_agents_main_model(self):
        sid = workflow(self.s)
        self.run_now(sid)
        self.assertEqual([(m['pick'], m['model']) for m in self.made], [('cli:claude', 'claude-opus-5-5')])

    def test_a_coding_run_opens_its_pane_on_the_workflows_brain_and_model(self):
        here = tempfile.mkdtemp()
        sid = workflow(self.s, title='Dependency bumps', agent='coding', cwd=here, model='claude-opus-5-5', effort='max')
        self.tick(sid)
        self.assertEqual([(o['brain'], o['model']) for o in self.opened], [('claude', 'claude-opus-5-5@max')])

    def test_a_dropped_effort_is_said_on_the_task(self):
        self.s.set_setting('assistant_ai', 'cli:copilot', 'owner')
        sid = workflow(self.s, effort='high')
        tid = self.run_now(sid)['task_id']
        self.assertIn('no effort setting', self.said(tid))
        self.assertFalse(self.made[0]['model'])                                                     # the brain's own model, no effort

    def test_a_task_the_owner_already_steered_keeps_their_choice(self):
        sid = workflow(self.s, model='opus')
        with mock.patch.object(workflows, '_spawn', lambda fn: None): tid = self.run_now(sid)['task_id']
        general.start_session(self.s, tid, model='haiku', actor='owner')
        self.assertEqual(self.made[-1]['model'], 'haiku')


class ComposerTests(Base):
    def compose(self, said):
        def llm(system, user, **kw): return json.dumps({'config': {'type': 'agent', 'title': 'Accruals', 'agent': 'ap', 'prompt': 'book them', **said}})
        return compose.compose_workflow(store(), 'book the month-end accruals', llm)['config']

    def test_the_composer_leaves_model_and_effort_blank_unless_the_owner_asked_for_harder(self):
        cfg = self.compose({})
        self.assertNotIn('model', cfg); self.assertNotIn('effort', cfg)
        self.assertIn('effort', compose.WORKFLOW_SYSTEM)
        self.assertIn('think hard', compose.WORKFLOW_SYSTEM)

    def test_the_composer_keeps_only_a_model_the_brain_offers_and_an_effort_it_takes(self):
        cfg = self.compose({'model': 'opus', 'effort': 'high'})
        self.assertEqual((cfg['model'], cfg['effort']), ('opus', 'high'))
        cfg = self.compose({'model': 'gpt-9-imaginary', 'effort': 'ludicrous'})
        self.assertNotIn('model', cfg); self.assertNotIn('effort', cfg)


if __name__ == '__main__': unittest.main()
