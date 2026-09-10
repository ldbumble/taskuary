"""Agent profiles: CODER.md is one profile, not the ground.

Asked for 2026-09-10. Every worker session was seeded `CODING RULES (CODER.md)` unconditionally
(terminal.py), so a meeting-prep task and a research task were both told "work only in the repository
the task names" - and the system compensated with prose ("NO REPOSITORY", "THIS IS NOT A CODE
CHANGE") rather than by not sending the wrong document. On the owner's own store: 123 general tasks
against 98 coding ones, and 27 agent sessions on general work against 10 on coding.

The model, minimal: a profile IS an agent row, and its rules document is the `doc` row of the same
name. `coder` already was exactly that. Triage is shown the roster and names one, validated against
the menu it was offered - the same shape playbooks already use.
"""
import json, re, unittest
from unittest import mock

from taskuary import agents as hub_agents, terminal, triage
from taskuary.store import MemoryStore


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    return s


def seeded(s):
    """What server.py's boot does: seed the config, then copy it into the store."""
    cfg = {'agents': {'coder': {'cmd': 'claude', 'kind': 'coding'}}}
    hub_agents.seed_profiles(cfg)
    for name, prof in cfg['agents'].items():
        s.upsert_agent(name, prof.get('kind', 'coding'), 'cli', json.dumps(prof))
    return s


class TheRosterTests(unittest.TestCase):
    def test_the_shipped_profiles_are_the_five_the_owner_chose(self):
        self.assertEqual(set(hub_agents.DEFAULT_PROFILES),
                         {'researcher', 'analyst', 'coordinator', 'marketer', 'trader'})
        for name, prof in hub_agents.DEFAULT_PROFILES.items():
            self.assertNotEqual(prof['kind'], 'coding', f'{name} must not be a coding profile')
            self.assertTrue(prof['purpose'].strip(), f'{name} needs a purpose for the roster')

    def test_every_shipped_profile_has_a_document_to_edit(self):
        """A profile with no document is a worker with no rules - the whole point is the stock prompt."""
        from pathlib import Path
        import taskuary
        tpl = Path(taskuary.__file__).parent / 'templates'
        for name in hub_agents.DEFAULT_PROFILES:
            doc = tpl / f'{name}.md'
            self.assertTrue(doc.exists(), f'{name}.md is not shipped')
            self.assertGreater(len(doc.read_text(encoding='utf-8').strip()), 200, f'{name}.md is a stub')

    def test_researcher_and_analyst_are_split_on_whose_information_it_is(self):
        """The first pair of purpose lines both read as "find out something", so "look into last
        month's spend" could land on either (the owner, 2026-09-10: "sharpen analyst vs
        researcher"). The line is OUTSIDE vs OUR OWN, and each document says it too, so a session
        that starts on the wrong side of it hands the job back instead of guessing."""
        from pathlib import Path
        import taskuary
        res, ana = hub_agents.DEFAULT_PROFILES['researcher']['purpose'], hub_agents.DEFAULT_PROFILES['analyst']['purpose']
        self.assertIn('OUTSIDE', res)
        self.assertIn('OUR OWN', ana)
        self.assertNotIn('OUTSIDE', ana)
        tpl = Path(taskuary.__file__).parent / 'templates'
        self.assertIn('analyst', tpl.joinpath('researcher.md').read_text(encoding='utf-8'))
        self.assertIn('researcher', tpl.joinpath('analyst.md').read_text(encoding='utf-8'))

    def test_the_roster_is_a_menu_of_name_and_purpose(self):
        s = store()
        seeded(s)
        menu = hub_agents.roster(s)
        self.assertIn('- researcher: ', menu)
        self.assertIn('- coder: ', menu)                      # the coding profile is on it too
        for line in menu.splitlines():
            self.assertRegex(line, r'^- [a-z0-9-]+: .+')      # what triage validates against

    def test_seeding_never_clobbers_a_profile_the_owner_changed(self):
        """It goes in config.toml, which is what the Agents page reads and writes."""
        cfg = {'agents': {'coder': {'cmd': 'claude', 'args': ['-p'], 'kind': 'coding'}}}
        self.assertIn('researcher', hub_agents.seed_profiles(cfg))
        cfg['agents']['researcher'] = {'cmd': 'codex', 'purpose': 'mine', 'kind': 'research'}
        self.assertEqual(hub_agents.seed_profiles(cfg), [])          # nothing left to add
        self.assertEqual(cfg['agents']['researcher']['cmd'], 'codex')
        self.assertEqual(cfg['agents']['researcher']['purpose'], 'mine')

    def test_a_shipped_profile_inherits_the_whole_cli_setup(self):
        """`cmd` falls back to the agent's NAME in half the codebase, so a profile with none would try
        to run a command called `researcher` - and a claude profile without the skip-permissions flag
        hangs headless, so the FLAGS have to come along too."""
        cfg = {'agents': {'coder': {'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions'],
                                    'timeout': 1500, 'kind': 'coding'}}}
        hub_agents.seed_profiles(cfg)
        got = cfg['agents']['marketer']
        self.assertEqual(got['cmd'], 'claude')
        self.assertIn('--dangerously-skip-permissions', got['args'])
        self.assertEqual(got['timeout'], 1500)
        self.assertEqual(got['kind'], 'marketing')

    def test_nothing_is_seeded_when_there_is_no_coding_agent_to_inherit_from(self):
        """A fresh install with no CLI configured yet: leave it to setup rather than write profiles
        that name a command nobody has."""
        cfg = {}
        self.assertEqual(hub_agents.seed_profiles(cfg), [])
        self.assertEqual(cfg.get('agents'), {})


class TriageNamesTheProfileTests(unittest.TestCase):
    def test_the_contract_asks_for_a_profile_and_explains_it(self):
        self.assertIn('"profile"', triage.INTENT_SYSTEM)

    def _classify(self, answer, profiles):
        msg = {'Subject': 'Look into the vendor', 'BodyText': 'Can you find out who they are?',
               'FromEmail': 'a@b.test', 'FromName': 'A'}
        return triage.classify_intent(msg, llm=lambda *a, **k: json.dumps(answer), profiles=profiles)

    def test_a_profile_from_the_menu_rides_on_the_verdict(self):
        out = self._classify({'intent': 'task', 'kind': 'coding', 'profile': 'researcher', 'why': 'a look-up'},
                             profiles='- researcher: find out and report\n- coder: code')
        self.assertEqual(out['profile'], 'researcher')
        self.assertEqual(out['kind'], 'coding')               # profile does not disturb the three-way route

    def test_a_profile_that_was_never_offered_is_refused(self):
        out = self._classify({'intent': 'task', 'kind': 'coding', 'profile': 'lawyer', 'why': 'a look-up'},
                             profiles='- researcher: find out and report')
        self.assertNotIn('profile', out)

    def test_no_roster_means_no_profile_field_at_all(self):
        out = self._classify({'intent': 'task', 'kind': 'coding', 'profile': 'researcher', 'why': 'a look-up'},
                             profiles=None)
        self.assertNotIn('profile', out)

    def test_a_reply_only_message_gets_no_profile(self):
        """Nothing works a reply_only message, so naming a worker for it is meaningless."""
        out = self._classify({'intent': 'reply_only', 'profile': 'researcher', 'why': 'just answer them'},
                             profiles='- researcher: find out and report')
        self.assertNotIn('profile', out)


class TheSessionGetsItsOwnRulesTests(unittest.TestCase):
    def test_a_profile_task_is_seeded_its_own_document_and_not_coder(self):
        s = store()
        seeded(s)
        s.save_doc('coder', 'CODER RULES: work only in the repository the task names.', 'test')
        s.save_doc('researcher', 'RESEARCH RULES: cite every source; change nothing.', 'test')
        tid = s.create_task({'Title': 'Who are Acme?', 'Kind': 'coding', 'Status': 'open',
                             'Assignee': 'agent:researcher'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertIn('cite every source', seed)
        self.assertNotIn('work only in the repository', seed)
        self.assertIn('RESEARCHER.md', seed)

    def test_a_coding_task_still_gets_coder_md(self):
        """The regression that matters: coding work must be untouched by this."""
        s = store()
        s.save_doc('coder', 'CODER RULES: work only in the repository the task names.', 'test')
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open',
                             'Assignee': 'agent:coder'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertIn('work only in the repository', seed)
        self.assertIn('CODER.md', seed)

    def test_a_task_with_no_assignee_falls_back_to_the_default_profile(self):
        s = store()
        s.save_doc('coder', 'CODER RULES: work only in the repository the task names.', 'test')
        tid = s.create_task({'Title': 'Something', 'Kind': 'coding', 'Status': 'open'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertIn('work only in the repository', seed)

    def test_a_profile_with_an_empty_document_seeds_no_rules_block_rather_than_coders(self):
        """Falling back to CODER.md here is the bug, not a safety net."""
        s = store()
        seeded(s)
        s.save_doc('coder', 'CODER RULES: work only in the repository the task names.', 'test')
        s.save_doc('marketer', '', 'test')
        tid = s.create_task({'Title': 'Write the launch note', 'Kind': 'coding', 'Status': 'open',
                             'Assignee': 'agent:marketer'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertNotIn('work only in the repository', seed)


if __name__ == '__main__':
    unittest.main()


class WorkflowsAreNotCodeTests(unittest.TestCase):
    """"workflows should not be coder always as well. it's not code" (the owner, 2026-09-10).

    run_agent fell back to a hardcoded 'coder', and - because that road never loaded an operator
    document at all - a workflow pointed at `researcher` got the researcher's CLI and none of the
    researcher's rules."""

    def test_an_unnamed_workflow_goes_to_the_default_worker_not_the_coder(self):
        from taskuary import reports
        s = seeded(store())
        s.set_setting('default_agent', 'researcher', 'test')
        seen = {}
        def fake_cli(store_, name, model=None, **kw):
            seen['name'] = name
            return lambda system, user, **k: seen.update(ask=user) or 'done'
        with mock.patch.object(reports, 'make_cli_llm', fake_cli, create=True), \
             mock.patch('taskuary.llm.make_cli_llm', fake_cli):
            reports.run_agent({'store': s, 'prompt': 'summarise the week'})
        self.assertEqual(seen['name'], 'researcher')

    def test_a_named_workflow_runs_under_that_profiles_rules(self):
        from taskuary import reports
        s = seeded(store())
        s.save_doc('researcher', 'RESEARCH RULES: cite every source.', 'test')
        seen = {}
        def fake_cli(store_, name, model=None, **kw):
            seen['name'] = name
            return lambda system, user, **k: seen.update(ask=user) or 'done'
        with mock.patch('taskuary.llm.make_cli_llm', fake_cli):
            reports.run_agent({'store': s, 'agent': 'researcher', 'prompt': 'who are Acme?'})
        self.assertEqual(seen['name'], 'researcher')
        self.assertIn('cite every source', seen['ask'])
        self.assertIn('RESEARCHER.md', seen['ask'])

    def test_an_unnamed_workflow_gets_no_rules_block_so_nothing_existing_changes(self):
        from taskuary import reports
        s = seeded(store())
        s.save_doc('coder', 'CODER RULES: work only in the repository.', 'test')
        seen = {}
        def fake_cli(store_, name, model=None, **kw):
            return lambda system, user, **k: seen.update(ask=user) or 'done'
        with mock.patch('taskuary.llm.make_cli_llm', fake_cli):
            reports.run_agent({'store': s, 'prompt': 'the weekly numbers'})
        self.assertNotIn('work only in the repository', seen['ask'])
