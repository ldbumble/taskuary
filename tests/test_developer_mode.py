"""DEVELOPER MODE (the owner, 2026-11-02): "for regular people everything should be a general agent, not coding ... in setup you should
have to enable developer mode and then connect GitHub for the coding CLI to work - though if they have no repos connected you should
still be able to run the coding CLI."

Off - the default on a fresh install - coding does not exist whatever CLI is connected: coding_ready is false, triage is never offered
the kind, the Assistant's index names no coding tool and its coding hand-off is the regular agent's. A home from before the switch
that already codes is turned on once, on the upgrade. The suite runs in developer mode (conftest); these tests put the real switch back."""
import json, unittest
from unittest import mock

from taskuary import agents, capabilities, concierge, counsel, devmode, firstrun, terminal, toolcatalog, triage
from taskuary.store import MemoryStore
from taskuary.testing import Factory

REAL_DEV, REAL_READY = (getattr(f, 'real', f) for f in (agents.developer_mode, agents.coding_ready))   # read at collection, before conftest patches
A_CLI = [('claude', {'cmd': 'claude'})]


def real_switch():
    "The switch and coding_ready as they really are, with a CLI connected that starts here."
    return [mock.patch.object(agents, 'developer_mode', REAL_DEV), mock.patch.object(agents, 'coding_ready', REAL_READY),
            mock.patch.object(agents, 'connection_brains', return_value=A_CLI), mock.patch.object(agents, 'runs_here', return_value=True)]


class Switch(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        for p in real_switch(): p.start(); self.addCleanup(p.stop)

    def test_a_fresh_store_ships_it_off(self):
        self.assertEqual(self.s.get_setting('developer_mode'), '0')
        self.assertFalse(agents.developer_mode(self.s))

    def test_off_means_no_coding_even_with_a_cli_that_runs_here(self):
        self.assertTrue(agents.cli_ready(self.s))
        self.assertFalse(agents.coding_ready(self.s)); self.assertFalse(capabilities.can_code(self.s))
        self.assertFalse(capabilities.capabilities(self.s)['coding'])

    def test_on_with_a_cli_is_coding(self):
        self.s.set_setting('developer_mode', '1', 'owner')
        self.assertTrue(agents.coding_ready(self.s)); self.assertTrue(capabilities.can_code(self.s))

    def test_on_without_a_cli_is_still_no_coding(self):
        self.s.set_setting('developer_mode', '1', 'owner')
        with mock.patch.object(agents, 'connection_brains', return_value=[]): self.assertFalse(agents.coding_ready(self.s))

    def test_why_names_the_switch_when_it_is_off(self):
        self.assertIn('Developer mode', agents.no_coding_why(self.s))
        self.s.set_setting('developer_mode', '1', 'owner')
        self.assertNotIn('Developer mode', agents.no_coding_why(self.s))


class Triage(unittest.TestCase):
    MSG = {'subject': 'The export script writes empty files', 'body': 'Can you fix the export script?', 'from': 'erin@northwind.example'}

    def test_off_the_guide_and_the_schema_offer_no_coding(self):
        seen = {}
        def brain(system, user, **kw):
            seen.update(system=system, want=kw.get('want'))
            return json.dumps({'intent': 'task', 'why': 'asks for a fix', 'kind': 'general', 'title': 'Fix the export', 'summary': 's'})
        triage.classify_intent(self.MSG, llm=brain, system=triage.SHIPPED, coding=False)
        self.assertNotIn('- **coding**', seen['system']); self.assertNotIn('coding|general|task', seen['system'])
        self.assertIn('"kind": "general|task"', seen['system'])
        if seen['want']: self.assertNotIn('coding', json.dumps(seen['want']['schema']['properties']['kind']))

    def test_on_the_guide_keeps_its_coding_option(self):
        self.assertIn('- **coding**', triage.SHIPPED)
        kind = lambda on: json.dumps(triage.verdict_schema(coding=on)['schema']['properties']['kind'])
        self.assertIn('coding', kind(True)); self.assertNotIn('coding', kind(False))

    def test_the_shipped_guide_loses_only_the_coding_option(self):
        out = triage.without_coding(triage.SHIPPED)
        self.assertEqual(len(triage.SHIPPED.split('\n')) - len(out.split('\n')), 1)
        self.assertIn('- **general**', out)

    def test_ingest_hands_triage_the_switch(self):
        s = MemoryStore()
        with mock.patch.object(agents, 'developer_mode', REAL_DEV), mock.patch.object(agents, 'coding_ready', REAL_READY), \
             mock.patch.object(agents, 'connection_brains', return_value=A_CLI), mock.patch.object(agents, 'runs_here', return_value=True):
            self.assertFalse(capabilities.can_code(s), 'ingest passes capabilities.can_code as triage\'s coding option')


class Migration(unittest.TestCase):
    def test_a_fresh_home_stays_off_and_says_why(self):
        s = MemoryStore()
        self.assertEqual(devmode.migrate(s, {}), 'off: nothing coding here')
        self.assertEqual(s.get_setting('developer_mode'), '0'); self.assertEqual(s.setting_writer(devmode.DECIDED), 'migration')

    def test_it_is_decided_once(self):
        s = MemoryStore(); devmode.migrate(s, {})
        Factory(s).task(title='Fix the export', kind='coding')
        self.assertIsNone(devmode.migrate(s, {}), 'decided once: a later coding task does not turn it on')
        self.assertEqual(s.get_setting('developer_mode'), '0')

    def test_a_home_with_coding_history_turns_on(self):
        s = MemoryStore(); Factory(s).task(title='Fix the export', kind='coding')
        self.assertEqual(devmode.migrate(s, {}), 'on: a coding task')
        self.assertEqual(s.get_setting('developer_mode'), '1')

    def test_each_kind_of_evidence_counts(self):
        cases = [({'cli_connections': {'codex': {'cmd': 'codex'}}}, None, 'a coding CLI connected'),
                 ({}, lambda s: s.set_setting('default_brain', 'claude', 'owner'), 'a coding brain picked'),
                 ({'github': {'default_repo': 'northwind/ledger'}}, None, 'a repository map')]
        for cfg, prep, said in cases:
            s = MemoryStore()
            if prep: prep(s)
            self.assertEqual(devmode.evidence(s, cfg), said)
        s = MemoryStore()
        s.save_connector({'ConnectorId': s.get_connector_by_type('github')['ConnectorId'], 'Active': 1}, 'test')
        self.assertEqual(devmode.evidence(s, {}), 'a code-host card')

    def test_the_owners_own_choice_is_kept(self):
        s = MemoryStore(); Factory(s).task(title='Fix the export', kind='coding')
        s.set_setting('developer_mode', '0', 'owner')
        self.assertEqual(devmode.migrate(s, {}), 'kept: the owner set it')
        self.assertEqual(s.get_setting('developer_mode'), '0')


class Assistant(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        for p in real_switch(): p.start(); self.addCleanup(p.stop)

    def test_off_the_index_names_no_coding_tool(self):
        text = toolcatalog.block(self.s)
        for k in toolcatalog.CODING_ONLY: self.assertNotIn(k, text)
        self.assertNotIn('coding_agent', toolcatalog.bucket_list('table', self.s))
        self.assertNotIn('task.set_repo', toolcatalog.bucket_list('task', self.s))
        self.assertIn('not here', toolcatalog.describe('coding_agent', self.s))

    def test_on_it_names_them(self):
        self.s.set_setting('developer_mode', '1', 'owner')
        text = toolcatalog.block(self.s)
        for k in toolcatalog.CODING_ONLY: self.assertIn(k, text)

    def test_off_a_coding_hand_off_is_the_regular_agents_and_no_repo_picker_lights(self):
        self.assertEqual(concierge.handoff_verb(self.s, 'coding_agent'), 'regular_agent')
        self.assertEqual(concierge.kind_button(self.s, 'task.set_repo'), '')
        self.assertEqual(concierge.kind_button(self.s, 'task.complete'), 'close')
        tid = Factory(self.s).task(title='Fix the export', kind='coding')
        self.assertEqual(concierge.kind_button(self.s, 'task.set_repo', {'tid': tid}), 'pick_repo', 'a task already coding keeps its picker')
        self.s.set_setting('developer_mode', '1', 'owner')
        self.assertEqual(concierge.kind_button(self.s, 'task.set_repo'), 'pick_repo')

    def test_off_repos_list_says_why(self):
        self.assertIn('Developer mode', concierge.read_op(self.s, 'repos.list', {}))

    def test_off_the_counsel_says_where_the_switch_is(self):
        with mock.patch.object(counsel, 'load', return_value='# Mine\n\n- Hand coding work to the coding agent.'):
            self.assertTrue(counsel.for_chat(self.s).endswith(counsel.NO_DEV))

    def test_setting_set_takes_the_switch_like_any_knob(self):
        from taskuary import settings_schema
        meta = settings_schema.knobs()['developer_mode']
        self.assertEqual((meta['label'], meta['type']), ('Developer mode', 'switch'))
        self.assertIn('Off: every job goes to a general agent', meta['desc'])


class Start(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        for p in real_switch(): p.start(); self.addCleanup(p.stop)

    def test_off_new_work_starts_as_a_general_agent(self):
        tid = Factory(self.s).task(title='Fix the export', kind='general')
        with mock.patch.object(terminal, '_as_general', return_value={'general': True}) as gen, \
             mock.patch.object(terminal, 'open_session') as opened:
            self.assertEqual(terminal.start_on_task(self.s, tid, 'coding'), {'general': True})
        gen.assert_called_once(); opened.assert_not_called()

    def test_off_a_coding_task_with_no_session_yet_is_new_work(self):
        tid = Factory(self.s).task(title='Fix the export', kind='coding')
        with mock.patch.object(terminal, '_as_general', return_value={'general': True}) as gen:
            terminal.start_on_task(self.s, tid, 'coding')
        gen.assert_called_once()

    def test_off_a_task_already_coding_keeps_its_coding_agent(self):
        tid = Factory(self.s).task(title='Fix the export', kind='coding')
        self.s.start_run(tid, 'coding', 'fix it', 'test')
        with mock.patch.object(terminal, '_as_general') as gen, \
             mock.patch.object(terminal, 'open_session', side_effect=RuntimeError('opened')):
            try: terminal.start_on_task(self.s, tid, 'coding')
            except (RuntimeError, ValueError) as e: self.assertNotEqual(str(e), terminal.NO_CODING_TOOL)
        gen.assert_not_called()


class Setup(unittest.TestCase):
    def rows(self, **st): return {r['key']: r for r in firstrun.rail({'step': 'done', 'about_done': True, **st})['rail']}

    def test_developer_mode_is_an_optional_step_and_github_follows_it(self):
        off = self.rows(developer_mode=False)
        self.assertTrue(off['dev']['optional']); self.assertNotIn('github', off)
        on = self.rows(developer_mode=True)
        self.assertTrue(on['github']['optional']); self.assertFalse(on['github']['done'])
        self.assertTrue(self.rows(developer_mode=True, github=True)['github']['done'])

    def test_skipping_them_never_holds_finish(self):
        self.assertTrue(firstrun.rail({'step': 'done', 'about_done': True, 'developer_mode': True})['ready'])

    def test_state_carries_the_switch(self):
        s = MemoryStore()
        with mock.patch.object(agents, 'developer_mode', REAL_DEV):
            self.assertEqual(firstrun.developer(s), {'developer_mode': False, 'dev_chosen': False, 'github': False})
            s.set_setting('developer_mode', '1', 'owner')
            self.assertEqual(firstrun.developer(s), {'developer_mode': True, 'dev_chosen': True, 'github': False})


if __name__ == '__main__': unittest.main()
