"""The assistant chat's own toolset, and the provider it is actually given.

TQ-0420: the owner asked a general task to research a company online. The chat answered "I don't
have a web search tool in this session" - it was running the mail CLASSIFIER's profile (`--tools ''`,
permission bypass stripped), because make_cli_llm treats "no cwd, no cli_tools" as "reads untrusted
text, gets nothing". The chat is the owner talking, not untrusted mail.
"""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, llm, server, terminal
from taskuary.store import MemoryStore


def general_task(store):
    return store.create_task({'Title': 'Research Instinct', 'Summary': 'What do people say about them',
                              'Kind': 'general', 'Status': 'open'}, 'owner')


def a_claude(store, name='my-claude'):
    store.upsert_agent(name, 'coding', 'cli', json.dumps({
        'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']}))


class AssistantToolsTests(unittest.TestCase):
    def _argv(self, store, tid, pick):
        seen = {}
        def run_cli(profile, prompt, trace, resume=None, **kwargs):
            seen.update(profile=profile); return 'ok', None, None
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
            session = general.start_session(store, tid, pick=pick)
            session.send_prompt('Research what people say about Instinct online', pick=pick)
        return list(seen['profile']['args'])

    def test_the_assistant_chat_on_a_cli_may_read_and_look_things_up(self):
        store = MemoryStore(); a_claude(store)
        args = self._argv(store, general_task(store), 'cli:my-claude')
        self.assertIn('WebSearch', ' '.join(args))
        self.assertIn('WebFetch', ' '.join(args))
        self.assertIn('--allowedTools', args)          # granted, not merely present - a headless run cannot click

    def test_looking_things_up_is_still_not_permission_to_act(self):
        store = MemoryStore(); a_claude(store)
        args = self._argv(store, general_task(store), 'cli:my-claude')
        self.assertNotIn('--dangerously-skip-permissions', args)
        self.assertIn('mcp__*', args)                  # a connector may expose writes beside reads
        self.assertNotIn('Bash', ' '.join(args))
        self.assertNotIn('Write', ' '.join(args))

    def test_the_classifier_reading_untrusted_mail_still_gets_nothing(self):
        """The narrow grant above must not leak into the brain that reads other people's words."""
        store = MemoryStore(); a_claude(store)
        seen = {}
        def run_cli(profile, prompt, trace, resume=None, **kwargs):
            seen.update(profile=profile); return 'ok', None, None
        with mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
            llm.make_cli_llm(store, 'my-claude')('SYS', 'USER')
        self.assertEqual(seen['profile']['args'], ['-p', '--tools', ''])


class AssistantProviderTests(unittest.TestCase):
    def test_the_payload_names_the_provider_the_server_would_choose(self):
        """The picker defaulted to providers[0], which is always a CLI - so a general task with no
        session nominated a CODING agent and sent that as its pick."""
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            data = TestClient(server.app).get(f'/api/tasks/{tid}/assistant').json()
        self.assertIsNone(data['session'])
        self.assertEqual(data['defaultPick'], 'cli:my-codex')

    def test_an_api_brain_outranks_a_coding_cli_for_the_chat(self):
        store = MemoryStore(); tid = general_task(store)
        store.upsert_agent('my-codex', 'coding', 'cli', json.dumps({'cmd': 'codex'}))
        row = store.get_connector_by_type('openai')
        store.save_connector({'ConnectorId': row['ConnectorId'], 'Active': 1, 'Secret': 'sk-test',
                              'Name': 'Work model', 'ConfigJson': '{"model":"gpt-test"}'}, 'owner')
        with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
            data = TestClient(server.app).get(f'/api/tasks/{tid}/assistant').json()
        self.assertEqual(data['defaultPick'], f"connector:{row['ConnectorId']}")


if __name__ == '__main__':
    unittest.main()
