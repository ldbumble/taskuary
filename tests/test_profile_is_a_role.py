"""A profile is a role; a brain is what runs it.

TQ-0588 was a coding task and Copilot worked it, though the default coding agent is Claude.
Triage had named the profile `copilot` - and `copilot` is a CLI, not a worker. The question was
also being asked on the wrong kind: every profile choice in the owner's store landed on a coding
task (TQ-0586 drew an ANALYST on coding work) while general tasks got none at all.

Spec: docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md
"""
import json, unittest

from taskuary import agents as hub_agents, general, triage
from taskuary.store import MemoryStore


def store():
    """The owner's shape: one coding role, the CLI clones beside it, and the general specialists."""
    s = MemoryStore()
    for name in ('coder', 'codex', 'copilot'):
        s.upsert_agent(name, 'coding', 'cli', json.dumps({'cmd': name, 'purpose': 'Write, review and test code in a repository.'}))
    for name, kind in (('researcher', 'research'), ('analyst', 'analysis'), ('trader', 'markets')):
        s.upsert_agent(name, kind, 'cli', json.dumps({'cmd': 'claude', 'purpose': f'{name} work'}))
    return s


def named(roster: str) -> list:
    return [ln.split(':')[0][2:] for ln in roster.splitlines() if ln.startswith('- ')]


class TheRosterTests(unittest.TestCase):
    def test_roster_offers_no_coding_profile(self):
        for cli in ('coder', 'codex', 'copilot'):
            self.assertNotIn(cli, named(hub_agents.roster(store())), f'{cli} is a coding role and must not be a triage choice')

    def test_roster_offers_every_general_role(self):
        self.assertEqual(sorted(named(hub_agents.roster(store()))), ['analyst', 'researcher', 'trader'])

    def test_legacy_cli_kind_is_coding_too(self):
        s = store()
        s.upsert_agent('opencode', 'cli', 'cli', json.dumps({'cmd': 'opencode', 'purpose': 'Write code.'}))
        self.assertNotIn('opencode', hub_agents.roster(s))


class WhichRoleTests(unittest.TestCase):
    def test_coding_always_takes_the_coding_role(self):
        """Written, not left implied: the `agent:` prefix is what puts the row in the pipe's
        `queued` lane - "handed to coder, not started yet" (processing_unread:76)."""
        self.assertEqual(hub_agents.routed_role(store(), 'coding', ''), 'coder')

    def test_coding_ignores_a_profile_triage_named(self):
        """TQ-0588 drew `copilot`, TQ-0586 drew `analyst`. Neither reaches the task."""
        s = store()
        self.assertEqual(hub_agents.routed_role(s, 'coding', 'analyst'), 'coder')
        self.assertEqual(hub_agents.routed_role(s, 'coding', 'copilot'), 'coder')

    def test_general_takes_the_named_specialist(self):
        self.assertEqual(hub_agents.routed_role(store(), 'general', 'analyst'), 'analyst')

    def test_general_with_no_profile_names_nobody(self):
        """No 'default general role' exists, by design - the owner picks at start."""
        self.assertEqual(hub_agents.routed_role(store(), 'general', ''), '')

    def test_general_never_falls_through_to_coder(self):
        self.assertNotEqual(hub_agents.routed_role(store(), 'general', ''), 'coder')

    def test_general_refuses_a_coding_role(self):
        """The two groups never mix. The roster cannot offer `coder` and triage validates against
        it, so this takes a hallucination to reach - which is exactly when it must not land."""
        for cli in ('coder', 'codex', 'copilot'):
            self.assertEqual(hub_agents.routed_role(store(), 'general', cli), '')

    def test_kind_task_names_nobody(self):
        """kind 'task' leaves the job on the owner's list - no agent, so no role."""
        self.assertEqual(hub_agents.routed_role(store(), 'task', 'analyst'), '')

    def test_an_unknown_profile_names_nobody(self):
        self.assertEqual(hub_agents.routed_role(store(), 'general', 'nobody'), '')


class RepairTests(unittest.TestCase):
    def rows(self, s):
        return {t['TaskId']: t.get('Assignee') for t in s.list_tasks()}

    def test_a_coding_task_routed_to_a_cli_is_corrected(self):
        """TQ-0585 held agent:copilot; TQ-0586 held agent:analyst on coding work."""
        s = store()
        a = s.create_task({'Title': 'copilot one', 'Kind': 'coding', 'Status': 'open', 'Assignee': 'agent:copilot'}, 'test')
        b = s.create_task({'Title': 'analyst one', 'Kind': 'coding', 'Status': 'in_progress', 'Assignee': 'agent:analyst'}, 'test')
        self.assertEqual(hub_agents.repair_role_assignees(s), 2)
        self.assertEqual(self.rows(s)[a], 'agent:coder')
        self.assertEqual(self.rows(s)[b], 'agent:coder')

    def test_finished_work_is_history_and_is_left_alone(self):
        """transcript.Agent says copilot actually worked TQ-0585. Rewriting a done task's stamp to
        `coder` would make the row claim otherwise - and the repair did exactly that, once."""
        s = store()
        for status in ('done', 'dropped'):
            t = s.create_task({'Title': status, 'Kind': 'coding', 'Status': status, 'Assignee': 'agent:copilot'}, 'test')
            self.assertEqual(hub_agents.repair_role_assignees(s), 0)
            self.assertEqual(self.rows(s)[t], 'agent:copilot')

    def test_general_assignees_are_left_alone(self):
        s = store()
        g = s.create_task({'Title': 'general one', 'Kind': 'general', 'Assignee': 'agent:analyst'}, 'test')
        hub_agents.repair_role_assignees(s)
        self.assertEqual(self.rows(s)[g], 'agent:analyst')

    def test_a_human_assignee_is_left_alone(self):
        """A person owning a task outranks any routing - `mine` put them there."""
        s = store()
        h = s.create_task({'Title': 'mine', 'Kind': 'coding', 'Assignee': 'owner'}, 'test')
        hub_agents.repair_role_assignees(s)
        self.assertEqual(self.rows(s)[h], 'owner')

    def test_an_unassigned_task_is_left_alone(self):
        s = store()
        u = s.create_task({'Title': 'nobody', 'Kind': 'coding'}, 'test')
        hub_agents.repair_role_assignees(s)
        self.assertFalse(self.rows(s)[u])

    def test_it_is_idempotent(self):
        s = store()
        s.create_task({'Title': 'copilot one', 'Kind': 'coding', 'Assignee': 'agent:copilot'}, 'test')
        self.assertEqual(hub_agents.repair_role_assignees(s), 1)
        self.assertEqual(hub_agents.repair_role_assignees(s), 0)


class GeneralRoleTests(unittest.TestCase):
    """On general work the role chose the EXECUTABLE too: assigned_pick turned
    `Assignee = agent:analyst` into the provider pick `cli:analyst`. The comment above one of its
    call sites stated the principle outright - "its instructions and CLI must travel together,
    otherwise a research profile is only a label on the task". The worry is answered rather than
    dismissed: the role still picks the rules document, so it is not only a label."""

    def task(self, assignee):
        return {'TaskId': 1, 'Kind': 'general', 'Assignee': assignee}

    def test_the_role_is_a_bare_name_not_a_provider(self):
        self.assertEqual(general.assigned_role(store(), self.task('agent:analyst')), 'analyst')

    def test_no_assignee_names_no_role(self):
        self.assertEqual(general.assigned_role(store(), self.task(None)), '')

    def test_an_unknown_name_names_no_role(self):
        self.assertEqual(general.assigned_role(store(), self.task('agent:ghost')), '')

    def test_assigned_pick_is_gone(self):
        """A role must never reach a provider picker again - that IS the bug."""
        self.assertFalse(hasattr(general, 'assigned_pick'))

    def test_a_named_role_does_not_choose_the_provider(self):
        self.assertNotIn('analyst', general.default_pick(store(), self.task('agent:analyst')))


class TheWorkersBlockTests(unittest.TestCase):
    def prompt(self, **kw):
        """The system prompt classify_intent builds, without calling a model."""
        seen = []

        def fake(system, user, **_):
            seen.append(system)
            return '{"intent": "fyi", "why": "x"}'

        triage.classify_intent({'subject': 's', 'body': 'b'}, llm=fake, profiles='- analyst: our figures', **kw)
        return seen[0]

    def test_the_block_asks_on_general_not_coding(self):
        p = self.prompt()
        self.assertIn('THE WORKERS', p)
        self.assertNotIn('(kind: coding)', p)
        self.assertIn('"kind": "general"', p)

    def test_the_block_says_coding_needs_no_profile(self):
        self.assertRegex(self.prompt(), r'[Cc]oding needs no profile')

    def test_the_block_survives_an_operator_document(self):
        """The owner's store holds a TRIAGE.md that REPLACES INTENT_SYSTEM (triage.py:408). The
        rule has to ride in the appended block or it never reaches that install."""
        p = self.prompt(system='My own triage document. Answer JSON with intent, kind, checklist, "summary".')
        self.assertIn('My own triage document', p)
        self.assertIn('THE WORKERS', p)
        self.assertNotIn('(kind: coding)', p)
