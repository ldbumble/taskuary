"""Every CLI setup offers must take the prompt the way IT reads one, and setup must offer only the ones that may sort mail - a real
triage through each installed CLI (2026-10-15) found Gemini 0.62 refusing a bare -p ("Not enough arguments following: p"), Devin's
print mode needing its prompt named ("needs a prompt"), and Copilot offered as "your AI" though triage refuses it. Each read as
"needs you to sign in"."""
import io, os, unittest
from unittest import mock

from taskuary import agents, clis, firstrun
from taskuary.store import MemoryStore


class Proc:
    def __init__(self, seen): self.seen, self.stdin, self.stdout, self.stderr, self.returncode = seen, io.StringIO(), iter(['ok\n']), io.StringIO(''), 0
    def wait(self, timeout=None): return 0
    def poll(self): return 0
    def kill(self): pass


def run(name, args):
    seen = {}
    def popen(cmd, **kw):
        seen['cmd'] = cmd
        f = next((cmd[i + 1] for i, a in enumerate(cmd) if a == '--prompt-file'), None)
        if f: seen['file'] = open(f, encoding='utf-8').read()
        p = Proc(seen); seen['proc'] = p; return p
    with mock.patch.object(agents, '_resolve_cmd', return_value=[name]), mock.patch('taskuary.spawn.popen', side_effect=popen), \
         mock.patch.object(agents, '_git', return_value=''):
        try: agents.run_cli({'cmd': name, 'args': args, 'timeout': 30}, 'Reply with exactly: ok', lambda *a: None)
        except Exception: pass
    return seen


class PromptRoadTests(unittest.TestCase):
    def test_gemini_print_mode_gets_a_value_and_reads_the_prompt_on_stdin(self):
        cmd = run('gemini', ['-p', '--yolo'])['cmd']
        i = cmd.index('-p'); self.assertEqual(cmd[i + 1], '', 'an empty -p: the prompt is stdin, appended to it')

    def test_devin_print_mode_gets_its_prompt_as_a_file(self):
        seen = run('devin', ['--permission-mode', 'dangerous', '-p'])
        self.assertIn('--prompt-file', seen['cmd']); self.assertEqual(seen['file'], 'Reply with exactly: ok')


class OnlyBrainsThatMaySortMail(unittest.TestCase):
    def test_setup_offers_no_cli_that_triage_refuses(self):
        rows = [{'name': n, 'label': n, 'installed': True, 'installable': True, 'install': n, 'setup': n} for n in ('claude', 'copilot', 'opencode', 'devin')]
        with mock.patch.object(clis, 'detect', return_value=rows):
            names = [a['name'] for a in firstrun.state(MemoryStore())['ais']]
        self.assertIn('claude', names); self.assertIn('devin', names)
        self.assertNotIn('copilot', names); self.assertNotIn('opencode', names)

    def test_picking_one_anyway_says_it_cannot_sort_mail(self):
        row = {'name': 'copilot', 'label': 'GitHub Copilot CLI', 'installed': True, 'installable': True, 'install': 'copilot', 'setup': 'copilot'}
        with mock.patch.object(clis, 'detect', return_value=[row]):
            out = firstrun.choose_cli(MemoryStore(), {}, 'copilot')
        self.assertFalse(out['ok']); self.assertIn("can't sort what comes in", out['why']); self.assertNotIn('sign in', out['why'])


if __name__ == '__main__': unittest.main()
