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


def test_one_browser_hook_carries_the_task_and_its_hold():
    """Timed on the real CLI, 2026-11-16: a reply turn's every shell call ran two browser hooks to the same door - one naming the task, one the
    chat's hold - each the whole shell gate. One hook names both."""
    import json as _json
    from pathlib import Path
    from taskuary import hooks
    d = _json.loads(Path(hooks.general_settings(7, 'abc123')).read_text(encoding='utf-8'))
    bw = [x for h in d['hooks']['PreToolUse'] if h.get('matcher') == hooks.BROWSER_MATCH for x in h['hooks']]
    assert len(bw) == 1 and '?task=7&sid=abc123' in bw[0]['command'] and bw[0]['timeout'] == hooks.BROWSER_WAIT + 10



def test_every_hook_command_is_one_shell_line_its_address_one_word():
    """The real-CLI walk, 2026-11-16: the one hook's address, `...?task=7&sid=abc123`, was bare in its command, and the shell Claude runs a
    hook in split it at `&` - curl went off with no token and no body, `-H` ran as a command (exit 127), the hook printed nothing, and every
    shell call of the chat ran ungated ("A hook gave no usable answer"). Read as a shell reads it: no control operator, the address one word."""
    import json as _json, shlex
    from pathlib import Path
    from taskuary import hooks
    d = _json.loads(Path(hooks.general_settings(7, 'abc123')).read_text(encoding='utf-8'))
    cmds = [x['command'] for groups in d['hooks'].values() for g in groups for x in g['hooks']]         + [_json.loads(Path(hooks.browser_settings('s9')).read_text(encoding='utf-8'))['hooks']['PreToolUse'][0]['hooks'][0]['command']]
    for cmd in cmds:
        lex = shlex.shlex(cmd, posix=True, punctuation_chars=True); lex.whitespace_split = True
        words = list(lex)
        assert not {'&', '&&', ';', '|', '||'} & set(words), (cmd, words)
        url = next(w for w in words if '/api/hooks/' in w)
        assert '-H' in words and '--data-binary' in words, words
        if 'browser' in url and '?' in url: assert ('task=7' in url and 'sid=abc123' in url) or 'sid=s9' in url, url
