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

    def test_the_roster_is_a_menu_of_name_and_purpose(self):
        s = store()
        hub_agents.seed_profiles(s)
        menu = hub_agents.roster(s)
        self.assertIn('- researcher: ', menu)
        self.assertIn('- coder: ', menu)                      # the coding profile is on it too
        for line in menu.splitlines():
            self.assertRegex(line, r'^- [a-z0-9-]+: .+')      # what triage validates against

    def test_seeding_never_clobbers_a_profile_the_owner_changed(self):
        s = store()
        hub_agents.seed_profiles(s)
        s.upsert_agent('researcher', 'research', 'cli', json.dumps({'cmd': 'codex', 'purpose': 'mine'}))
        hub_agents.seed_profiles(s)
        prof = json.loads(s.get_agent('researcher')['Config'])
        self.assertEqual(prof['cmd'], 'codex')
        self.assertEqual(prof['purpose'], 'mine')

    def test_a_shipped_profile_inherits_a_cli_that_is_actually_installed(self):
        """`cmd` falls back to the agent's NAME in half the codebase, so a profile with none would
        try to run a command called `researcher`."""
        s = MemoryStore()
        s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        hub_agents.seed_profiles(s)
        self.assertEqual(json.loads(s.get_agent('marketer')['Config'])['cmd'], 'codex')


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
        hub_agents.seed_profiles(s)
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
        hub_agents.seed_profiles(s)
        s.save_doc('coder', 'CODER RULES: work only in the repository the task names.', 'test')
        s.save_doc('marketer', '', 'test')
        tid = s.create_task({'Title': 'Write the launch note', 'Kind': 'coding', 'Status': 'open',
                             'Assignee': 'agent:marketer'}, 'o')
        seed = terminal.seed_text(s, tid)
        self.assertNotIn('work only in the repository', seed)


if __name__ == '__main__':
    unittest.main()
