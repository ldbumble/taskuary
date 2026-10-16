"""An install from before brains named tools, through the one startup migration (agents.layer_profiles).

The owner, 2026-10-15: "never ever use coder ... there is no such profile or brain.. it's models or cli tools only". Every
literal `coder` below is the OLD install's data on purpose - this file is the one place it has to be written, because it
is what the migration reads.
"""
import json, unittest

from taskuary import agents
from taskuary.store import MemoryStore


def legacy():
    cfg = {'cli_connections': {'claude': {'cmd': 'claude'}, 'codex': {'cmd': 'codex'}},
           'agents': {'coder': {'kind': 'coding', 'provider': 'cli:claude', 'rules_doc': 'coder'},
                      'researcher': {'kind': 'research', 'purpose': 'outside information', 'provider': 'cli:codex'},
                      'analyst': {'kind': 'analysis', 'purpose': 'our own figures', 'provider': 'cli:claude'}}}
    s = MemoryStore()
    for n, p in cfg['agents'].items(): s.upsert_agent(n, p['kind'], 'cli', json.dumps({**p, 'cmd': p['provider'][4:]}))
    s.save_doc('coder', 'Edited coding rules: never push.', 'owner')
    tid = s.create_task({'Title': 'Fix the importer', 'Kind': 'coding', 'Assignee': 'agent:coder'}, 'test')
    s.set_setting('default_agent', 'coder', 'owner'); s.set_setting('concierge_ai', 'cli:coder', 'owner')
    return cfg, s, tid


class LayerProfilesTests(unittest.TestCase):
    def test_brains_name_tools_and_profiles_name_none(self):
        cfg, s, _ = legacy()
        self.assertTrue(agents.layer_profiles(cfg, s))
        self.assertEqual(s.get_setting('concierge_ai'), 'cli:claude')              # the pick names the tool the profile ran
        self.assertEqual(s.get_setting('default_brain'), 'claude')
        self.assertFalse(s.get_setting('default_agent'))
        self.assertFalse(any('provider' in p for p in cfg['agents'].values()))
        # only the role that ran somewhere else keeps that somewhere, as its brain override
        self.assertEqual(json.loads(s.get_setting('profile_brains')), {'researcher': 'codex'})

    def test_the_coding_profile_is_renamed_everywhere_and_keeps_its_edits(self):
        cfg, s, tid = legacy()
        agents.layer_profiles(cfg, s)
        self.assertNotIn('coder', cfg['agents']); self.assertEqual(cfg['agents']['coding']['rules_doc'], 'coding')
        self.assertIsNone(s.get_agent('coder')); self.assertEqual(s.get_agent('coding')['Kind'], 'coding')
        self.assertEqual(s.get_doc('coding'), 'Edited coding rules: never push.'); self.assertFalse(s.get_doc('coder'))
        self.assertEqual(s.get_task(tid)['Assignee'], 'agent:coding')
        self.assertEqual(agents.coding_role(s), 'coding')

    def test_a_second_start_changes_nothing(self):
        cfg, s, _ = legacy()
        agents.layer_profiles(cfg, s)
        snap = (json.dumps(cfg, sort_keys=True), s.get_setting('profile_brains'), s.get_setting('concierge_ai'))
        self.assertFalse(agents.layer_profiles(cfg, s))
        self.assertEqual(snap, (json.dumps(cfg, sort_keys=True), s.get_setting('profile_brains'), s.get_setting('concierge_ai')))

    def test_a_task_old_code_assigned_after_the_rename_is_repaired_on_the_next_start(self):
        cfg, s, _ = legacy()
        agents.layer_profiles(cfg, s)
        late = s.create_task({'Title': 'Investigate the export failure', 'Kind': 'coding', 'Assignee': 'agent:coder'}, 'test')
        agents.layer_profiles(cfg, s)
        self.assertEqual(s.get_task(late)['Assignee'], 'agent:coding')

    def test_an_owners_own_coding_profile_is_never_overwritten(self):
        cfg, s, _ = legacy()
        cfg['agents']['coding'] = {'kind': 'coding', 'purpose': 'mine'}
        agents.layer_profiles(cfg, s)
        self.assertEqual(cfg['agents']['coding']['purpose'], 'mine')


if __name__ == '__main__':
    unittest.main()
