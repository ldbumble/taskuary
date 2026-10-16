"""The Assistant says which tool and model run each brain (the owner, 2026-10-15: "it's not set to coding agent. it's to a specific
model"), and knows the page they are set on ("can you find me the setting for assistant ai brain")."""
import unittest
from unittest import mock

from taskuary import aidefaults, appfacts, concierge
from taskuary.store import MemoryStore

CFG = {'cli_connections': {'claude': {'cmd': 'claude'}},
       'agents': {'writer': {'kind': 'coding', 'provider': 'cli:claude'}}}


class BrainSaidTests(unittest.TestCase):
    def test_a_cli_brain_is_its_tool_and_model(self):
        s = MemoryStore()
        s.set_setting('concierge_ai', 'cli:claude', 't'); s.set_setting('concierge_model', 'claude-sonnet-5-5', 't')
        said = aidefaults.said(s, 'concierge_ai', CFG)
        self.assertTrue(said.startswith('Claude Code, claude-sonnet-5-5'), said)

    def test_a_pick_that_names_a_profile_still_says_the_tool_never_the_profile(self):
        s = MemoryStore()
        s.set_setting('concierge_ai', 'cli:writer', 't'); s.set_setting('concierge_model', 'claude-sonnet-5-5', 't')
        said = aidefaults.said(s, 'concierge_ai', CFG)
        self.assertIn('Claude Code', said); self.assertNotIn('writer', said)

    def test_an_azure_brain_is_its_deployment(self):
        s = MemoryStore()
        cid = s.save_connector({'Type': 'azure_openai', 'Name': 'Azure OpenAI', 'ConfigJson': '{"deployment": "gpt-5.4"}', 'Active': 1}, 'owner')
        s.set_setting('triage_ai', f'connector:{cid}', 't')
        self.assertEqual(aidefaults.said(s, 'triage_ai', CFG), 'Azure OpenAI, gpt-5.4')

    def test_the_facts_carry_the_words_and_the_pages_carry_the_brains_page(self):
        s = MemoryStore()
        s.set_setting('concierge_ai', 'cli:claude', 't')
        with mock.patch.object(aidefaults, 'said', lambda st, k, cfg=None: f'said {k}'):
            self.assertIn('assistant: said concierge_ai', appfacts.brains(s))
        self.assertIn('#settings=config&group=Triage%20%26%20agents', concierge.pages_block(s))


if __name__ == '__main__': unittest.main()
