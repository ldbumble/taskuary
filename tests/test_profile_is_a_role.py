"""A profile is a role; a brain is what runs it.

TQ-0588 was a coding task and Copilot worked it, though the default coding agent is Claude.
Triage had named the profile `copilot` - and `copilot` is a CLI, not a worker. The question was
also being asked on the wrong kind: every profile choice in the owner's store landed on a coding
task (TQ-0586 drew an ANALYST on coding work) while general tasks got none at all.

Spec: docs/superpowers/specs/2026-09-16-profile-brain-separation-design.md
"""
import json, unittest

from taskuary import agents as hub_agents
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
