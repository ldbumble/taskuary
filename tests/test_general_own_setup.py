"""A GENERAL TASK'S AGENT READS NONE OF THE OWNER'S OWN CLAUDE SETUP (the owner, 2026-11-09): a WhatsApp task's agent read their
coding-style guide, the skills their plugins add, and searched mail through their claude.ai connector, outside Taskuary's checks.
It runs on its user settings left out, Taskuary's MCP server alone, and one settings file carrying Taskuary's own hooks (the user-wide
ones lived in the settings it no longer reads) with their CLAUDE.md excluded. A coding task keeps it all: it works in their code."""
import json, unittest
from unittest import mock

from taskuary import agents, llm
from taskuary.store import MemoryStore
from test_general import connect_cli


class GeneralRunsOnTaskuarysSetupAlone(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def _argv(self, kind, hold=None):
        connect_cli(self, claude={'cmd': 'claude', 'args': ['-p']})
        tid = self.s.create_task({'Title': 'Lunch with Erin', 'Kind': kind, 'Status': 'open'}, 'owner'); got = {}
        def run_cli(prof, prompt, trace, **kw): got['a'] = list(prof.get('args') or []); return ('ok', 's1', None)
        with mock.patch.object(agents, 'run_cli', run_cli), mock.patch.object(agents, 'cli_has_flag', return_value=True):
            llm.make_cli_llm(self.s, 'claude', cli_tools=True, task_id=tid, hold_sid=hold)('sys', 'user')
        return got['a']

    def test_a_general_task_leaves_out_the_owners_settings_mcp_and_claude_md_and_keeps_taskuarys_hooks(self):
        a = self._argv('general', hold='abc')
        self.assertEqual(a[a.index('--setting-sources') + 1], 'project,local'); self.assertIn('--strict-mcp-config', a)
        self.assertEqual(a.count('--settings'), 1)             # Claude keeps only the last one: the hold rides in the same file
        d = json.loads(open(a[a.index('--settings') + 1], encoding='utf-8').read())
        self.assertTrue(any(x.endswith('/.claude/CLAUDE.md') for x in d['claudeMdExcludes']))
        self.assertIn('Stop', d['hooks'])
        self.assertTrue(any('sid=abc' in h['command'] for g in d['hooks']['PreToolUse'] for h in g['hooks']))

    def test_a_coding_task_keeps_the_owners_own_setup(self):
        a = self._argv('coding')
        self.assertNotIn('--setting-sources', a); self.assertNotIn('--strict-mcp-config', a)


if __name__ == '__main__': unittest.main()
