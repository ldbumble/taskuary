"""Is a profile still a role, and a brain still what runs it - everywhere?

The 2026-09-16 split has one failure mode: a new call site quietly asks a PROFILE which CLI to run,
and the fusion grows back. These are the invariants, so that regression is a red test rather than a
Copilot session on a coding task somebody notices weeks later.

WHERE THE SPLIT IS NOT COMPLETE, on purpose and written down rather than implied:

  * `concierge.py:223` - the Assistant and the one-message jobs build their brain from an agent ROW
    (`llm.make_cli_llm(store, agent_name)`), so `triage_ai = cli:coder` still means "coder's CLI",
    not "the brain named coder". Removing this is what lets `_build_llm`'s dedupe go too.
  * `general.provider_options` - a general session's provider list is one entry per AGENT, so its
    picker still offers workers where the coding picker now offers brains.

Both are listed in the spec's status block. The tests below cover what IS split; the two above are
named here so nobody has to rediscover them by reading every call site.

Re-run the census by hand with:
    grep -rn "get('cmd')\\|\\['cmd'\\]" taskuary/*.py | grep -v clis.py
and ask of each hit: is it reading a CONNECTION (fine) or a PROFILE to decide what runs (fusion)?
"""
import json, unittest
from unittest import mock

from taskuary import agents as hub_agents, terminal
from taskuary.store import MemoryStore


def store(default_brain='claude'):
    """The owner's shape after the split: one coding role, the general specialists, no CLI clones."""
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', 'provider': 'cli:claude'}))
    for name, kind in (('researcher', 'research'), ('analyst', 'analysis')):
        s.upsert_agent(name, kind, 'cli', json.dumps({'cmd': 'claude', 'purpose': f'{name} work'}))
    s.set_setting('default_agent', 'coder', 'owner')
    if default_brain: s.set_setting('default_brain', default_brain, 'owner')
    return s


CFG = {'cli_connections': {'claude': {'cmd': 'claude'}, 'codex': {'cmd': 'codex', 'args': ['exec']}}}


class TriageOnlyEverNamesARole(unittest.TestCase):
    def test_no_brain_can_reach_the_roster(self):
        """Structural, not validated after the fact: the wrong answer is not in the menu."""
        s = store()
        s.upsert_agent('copilot', 'coding', 'cli', json.dumps({'cmd': 'copilot'}))
        offered = [l.split(':')[0][2:] for l in hub_agents.roster(s).splitlines() if l.startswith('- ')]
        self.assertEqual(sorted(offered), ['analyst', 'researcher'])

    def test_a_coding_verdict_lands_on_the_coding_role_whatever_it_named(self):
        s = store()
        for named in ('copilot', 'analyst', 'codex', ''):
            self.assertEqual(hub_agents.routed_role(s, 'coding', named), 'coder', named)

    def test_a_general_verdict_cannot_land_on_a_coding_role(self):
        s = store()
        s.upsert_agent('copilot', 'coding', 'cli', json.dumps({'cmd': 'copilot'}))
        for named in ('coder', 'copilot'):
            self.assertEqual(hub_agents.routed_role(s, 'general', named), '', named)


class TheSessionRunsTheBrain(unittest.TestCase):
    def test_the_profiles_own_command_does_not_decide_what_runs(self):
        """coder's profile says claude; settings say codex. Settings win, and the ROLE is unchanged."""
        s = store('codex')
        self.assertEqual(hub_agents.brain_command(s, 'coder', CFG).get('cmd'), 'codex')

    def test_open_session_launches_the_brain_not_the_profile(self):
        s = store('codex')
        seen = {}

        def fake_term(argv, cwd, label, task_id=None, agent=None, *a, **kw):
            seen['argv'], seen['agent'], seen['cli'] = argv, agent, kw.get('cli')
            return mock.Mock(sid='s1', cwd=cwd, info=lambda: {}, seeded='')

        with mock.patch.object(hub_agents, 'brain_command', return_value={'cmd': 'codex', 'args': ['exec']}), \
             mock.patch.object(terminal, 'Term', side_effect=fake_term), \
             mock.patch('taskuary.agents._resolve_cmd', side_effect=lambda c: [c]):
            terminal.open_session(s, 'coder')
        self.assertEqual(seen['argv'][0], 'codex')     # what RUNS is the brain
        self.assertEqual(seen['agent'], 'coder')       # what it IS is the role
        self.assertEqual(seen['cli'], 'codex')         # and the card is told the brain

    def test_the_card_is_told_the_cli_not_its_launcher(self):
        """argv[0] is the wrapper for anything behind a .BAT or node - `cmd`, `node`."""
        self.assertEqual(terminal.cli_named({'cmd': 'copilot'}, ['cmd', '/c', 'x/copilot.BAT']), 'copilot')
        self.assertEqual(terminal.cli_named({'cmd': 'qwen'}, ['C:/node.EXE', 'qwen.js']), 'qwen')


class FailoverWalksBrains(unittest.TestCase):
    def test_the_chain_is_brains_and_needs_no_dedupe(self):
        s = store()
        s.set_setting('backup_brains', 'codex,copilot', 'owner')
        self.assertEqual(hub_agents.brain_chain(s, 'claude', cfg=CFG), ['claude', 'codex', 'copilot'])

    def test_the_old_role_chain_is_gone(self):
        """It had to skip candidates whose cli_of it had already seen - a list of roles that was
        really a list of brains. Brains are distinct by construction."""
        self.assertFalse(hasattr(hub_agents, 'agent_chain'))


class NothingMintsAWorkerForACli(unittest.TestCase):
    def test_adopting_an_installed_cli_registers_a_connection_and_no_profile(self):
        from taskuary import cli_connections, cliinstall
        cfg, s = {'agents': {}, 'cli_connections': {}}, MemoryStore()
        with mock.patch.object(cliinstall, 'find', side_effect=lambda n: '/bin/devin' if n == 'devin' else ''):
            self.assertEqual(cli_connections.adopt_installed(cfg, s), [])
        self.assertEqual(cfg['agents'], {})
        self.assertEqual(cfg['cli_connections']['devin']['cmd'], 'devin')


class GearsBelongToTheBrain(unittest.TestCase):
    def test_a_profile_carries_no_model(self):
        from taskuary import cli_connections
        cfg = {'cli_connections': {'claude': {'cmd': 'claude'}},
               'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude', 'model': 'opus'}}}
        cli_connections.migrate(cfg)
        self.assertNotIn('model', cfg['agents']['coder'])
        self.assertEqual(cli_connections.gears(cfg, 'claude')['model'], 'opus')


if __name__ == '__main__':
    unittest.main()
