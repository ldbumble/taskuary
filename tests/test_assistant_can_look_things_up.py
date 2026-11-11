"""The assistant chat's own toolset, and the provider it is actually given.

TQ-0420: the owner asked a general task to research a company online. The chat answered "I don't
have a web search tool in this session" - it was running the mail CLASSIFIER's profile (`--tools ''`,
permission bypass stripped), because make_cli_llm treats "no cwd, no cli_tools" as "reads untrusted
text, gets nothing". The chat is the owner talking, not untrusted mail.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, llm, server, terminal
from taskuary.store import MemoryStore


def general_task(store):
    return store.create_task({'Title': 'Research Instinct', 'Summary': 'What do people say about them',
                              'Kind': 'general', 'Status': 'open'}, 'owner')


def connect(test, **conns):
    """CLI tools connected as brains - config.toml's cli_connections, never a profile row - and conftest's empty
    connection_brains put back."""
    from taskuary import agents, config
    real = config.load
    for p in (mock.patch.object(config, 'load', side_effect=lambda: {**real(), 'cli_connections': conns}),
              mock.patch.object(agents, 'connection_brains', getattr(agents.connection_brains, 'real', agents.connection_brains))):
        p.start(); test.addCleanup(p.stop)


def a_claude(test): connect(test, claude={'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']})


class AssistantToolsTests(unittest.TestCase):
    def _argv(self, store, tid, pick, hands=None):
        if hands: store.set_setting('general_agent_hands', hands, 'test')
        seen = {}
        def run_cli(profile, prompt, trace, resume=None, **kwargs):
            seen.update(profile=profile); return 'ok', None, None
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
            session = general.start_session(store, tid, pick=pick)
            session.send_prompt('Research what people say about Instinct online', pick=pick)
        return list(seen['profile']['args'])

    def test_the_assistant_chat_on_a_cli_may_read_and_look_things_up(self):
        store = MemoryStore(); a_claude(self)
        args = self._argv(store, general_task(store), 'cli:claude', hands='look')
        self.assertIn('WebSearch', ' '.join(args))
        self.assertIn('WebFetch', ' '.join(args))
        self.assertIn('--allowedTools', args)          # granted, not merely present - a headless run cannot click

    def test_look_only_is_still_not_permission_to_act(self):
        # the owner's 'look things up only' setting keeps the research grant (2026-10-05)
        store = MemoryStore(); a_claude(self)
        args = self._argv(store, general_task(store), 'cli:claude', hands='look')
        self.assertNotIn('--dangerously-skip-permissions', args)
        self.assertIn('mcp__*', args)                  # a connector may expose writes beside reads
        self.assertNotIn('Bash', ' '.join(args))
        self.assertNotIn('Write', ' '.join(args))

    def test_the_classifier_reading_untrusted_mail_still_gets_nothing(self):
        """The narrow grant above must not leak into the brain that reads other people's words."""
        store = MemoryStore(); a_claude(self)
        seen = {}
        def run_cli(profile, prompt, trace, resume=None, **kwargs):
            seen.update(profile=profile); return 'ok', None, None
        with mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
            llm.make_cli_llm(store, 'claude')('SYS', 'USER')
        args = seen['profile']['args']
        self.assertEqual(args[:5], ['-p', '--tools', '', '--disallowedTools', 'mcp__*'])
        # its instructions ride as the system prompt (a file), which adds no tool of any kind (2026-09-24)
        self.assertEqual(args[5:6], ['--system-prompt-file']); self.assertEqual(len(args), 7)

    def test_two_mails_share_one_cached_system_prompt_on_the_cli(self):
        """Claude Code caches its system prompt whole: one mail's own evidence at its end re-billed the guide on every mail (measured on
        the real CLI, 2026-11-11). The file holds what every call shares; the call's own part leads the turn, above the message."""
        from pathlib import Path
        store = MemoryStore(); a_claude(self)
        seen = []
        def run_cli(profile, prompt, trace, resume=None, **kwargs):
            a = profile['args']; seen.append((a[a.index('--system-prompt-file') + 1], prompt)); return 'ok', None, None
        guide = 'THE GUIDE. ' * 300
        with mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
            brain = llm.make_cli_llm(store, 'claude')
            brain(llm.stable(guide, '\n\nMEMORY', rest='\n\nEVIDENCE - Gail Moreno handles payroll.'), '{"from": "gail@northwind.example"}')
            brain(llm.stable(guide, '\n\nMEMORY', rest='\n\nEVIDENCE - Ray Colton handles overtime.'), '{"from": "ray@northwind.example"}')
            brain(llm.stable(guide, '\n\nMEMORY'), '{"from": "erin@northwind.example"}')
        self.assertEqual(len({f for f, _ in seen}), 1)                               # the same bytes: the provider reads them from its cache
        self.assertEqual(Path(seen[0][0]).read_text(encoding='utf-8'), guide + '\n\nMEMORY')
        self.assertEqual(seen[0][1], 'EVIDENCE - Gail Moreno handles payroll.\n\n{"from": "gail@northwind.example"}')   # nothing is dropped
        self.assertEqual(seen[2][1], '{"from": "erin@northwind.example"}')

    def test_a_one_shot_with_no_hands_reads_none_of_the_owners_cli_setup(self):
        """Their CLAUDE.md, skills and plugins rode every verdict uncached - 5,624 tokens a call against 865 (real CLI, 2026-11-11)."""
        from taskuary import agents
        store = MemoryStore(); a_claude(self)
        seen = {}
        def run_cli(profile, prompt, trace, resume=None, **kwargs):
            seen.update(profile=profile); return 'ok', None, None
        with mock.patch('taskuary.agents.run_cli', side_effect=run_cli), mock.patch('taskuary.agents.cli_has_flag', return_value=True):
            llm.make_cli_llm(store, 'claude')('SYS', 'USER')
            self.assertEqual(agents._own_settings(seen['profile'], 'claude'), ['--setting-sources', 'project,local'])
            # ...and a run with hands in the owner's own checkout keeps it all, as before
            llm.make_cli_llm(store, 'claude', cwd='.')('SYS', 'USER')
            self.assertEqual(agents._own_settings(seen['profile'], 'claude'), [])


class AssistantProviderTests(unittest.TestCase):
    @mock.patch('taskuary.agents.runs_here', lambda p: bool((p or {}).get('cmd')))   # the CLI it connects counts as installed: CI has none on PATH
    def test_the_payload_names_the_provider_the_server_would_choose(self):
        """The picker defaulted to providers[0], which is always a CLI - so a general task with no
        session nominated a CODING agent and sent that as its pick."""
        store = MemoryStore(); tid = general_task(store)
        connect(self, codex={'cmd': 'codex'})
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            data = TestClient(server.app).get(f'/api/tasks/{tid}/assistant').json()
        self.assertIsNone(data['session'])
        self.assertEqual(data['defaultPick'], 'cli:codex')

    def test_an_api_brain_outranks_a_coding_cli_for_the_chat(self):
        store = MemoryStore(); tid = general_task(store)
        connect(self, codex={'cmd': 'codex'})
        row = store.get_connector_by_type('openai')
        store.save_connector({'ConnectorId': row['ConnectorId'], 'Active': 1, 'Secret': 'sk-test',
                              'Name': 'Work model', 'ConfigJson': '{"model":"gpt-test"}'}, 'owner')
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            data = TestClient(server.app).get(f'/api/tasks/{tid}/assistant').json()
        self.assertEqual(data['defaultPick'], f"connector:{row['ConnectorId']}")


if __name__ == '__main__':
    unittest.main()
