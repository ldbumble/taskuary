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
