"""One sentence per state of a blocked agent, on every surface (the 2026-09-18 audit's top open item).

Seven surfaces each composed "the agent is parked" from two booleans, in six spellings, and none of
them could say "stuck on a rate limit" - the state the hooks now report - because a stall is neither
`asking` nor `not asking`. The sentence lives in lanes.json once; every site reads it through
workerstate.says (Python) or funnelPile.says (desktop), keyed by the request's kind."""
import json, os, sys, unittest
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from taskuary import workerstate as ws

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


class SubState(unittest.TestCase):
    def test_the_requests_kind_picks_the_sentence(self):
        self.assertEqual(ws.sub_state(req={'kind': 'stalled'}), 'stalled')
        self.assertEqual(ws.sub_state(req={'kind': 'approval_needed'}), 'approval')
        self.assertEqual(ws.sub_state(req={'kind': 'input_needed'}), 'asking')

    def test_without_a_request_the_booleans_decide(self):
        self.assertEqual(ws.sub_state(True, True), 'asking')
        self.assertEqual(ws.sub_state(True, False), 'parked')
        self.assertIsNone(ws.sub_state(False, True))

    def test_the_request_outranks_the_screen(self):
        # a stall LOOKS like a question on the screen; the hook said what it is
        self.assertEqual(ws.sub_state(True, True, {'kind': 'stalled'}), 'stalled')


class Says(unittest.TestCase):
    def test_every_sub_state_has_a_bare_sentence_naming_the_agent(self):
        for sub in ('asking', 'approval', 'stalled', 'parked'):
            self.assertTrue(ws.says(sub, 'coder').startswith('coder '), sub)

    def test_the_requests_words_ride_on_the_line(self):
        self.assertEqual(ws.says('stalled', 'coder', 'rate limit: resets at 3pm'), 'coder is stuck - rate limit: resets at 3pm')
        self.assertEqual(ws.says('asking', 'codex', 'Which branch?'), 'codex asked you: Which branch?')
        self.assertEqual(ws.says('approval', 'coder', 'Bash rm -rf build'), 'coder needs your approval: Bash rm -rf build')

    def test_parked_has_no_words_to_carry(self):
        self.assertEqual(ws.says('parked', 'coder', 'whatever the screen said'), 'coder stopped and is waiting on you')

    def test_request_line_is_the_same_table(self):
        self.assertEqual(ws.request_line('coder', {'kind': 'stalled', 'text': 'rate limit'}), ws.says('stalled', 'coder', 'rate limit'))
        self.assertEqual(ws.request_line('coder', {'kind': 'input_needed', 'text': 'Which?'}), 'coder asked you: Which?')

    def test_the_desktop_reads_the_same_entry(self):
        lanes = json.load(open(os.path.join(ROOT, 'taskuary', 'lanes.json'), encoding='utf-8'))
        blocked = next(l for l in lanes['lanes'] if l['key'] == 'blocked')
        self.assertEqual(set(blocked['says']), {'asking', 'approval', 'stalled', 'parked'})
        self.assertEqual(blocked['says'], ws.SAYS)


class EverySurface(unittest.TestCase):
    """No site may spell the state its own way any more: the sentences appear in code ONLY in lanes.json."""
    def test_no_python_or_desktop_site_composes_the_sentence_itself(self):
        import re
        spelled = re.compile(r'(stopped and is waiting on you|asked you something|parked at its prompt|stopped at its prompt|stopped - waiting on you|(?<!what )needs your approval)')
        blank = lambda m: '\n' * m.group(0).count('\n')                 # strip a comment, keep the line numbers
        bad = []
        for sub, exts in (('taskuary', ('.py',)), ('website/src', ('.js', '.jsx'))):
            for dp, _, fns in os.walk(os.path.join(ROOT, sub)):
                if 'demo' in dp or 'node_modules' in dp or 'web' + os.sep + 'assets' in dp: continue
                for fn in fns:
                    if not fn.endswith(exts) or fn.startswith('demo'): continue
                    src = open(os.path.join(dp, fn), encoding='utf-8', errors='replace').read()
                    if fn.endswith('.py'): src = re.sub(r'(?m)#.*$', '', re.sub(r'("""|\'\'\')[\s\S]*?\1', blank, src))
                    else: src = re.sub(r'(?m)(^\s*//.*$|\s// .*$)', '', re.sub(r'/\*[\s\S]*?\*/', blank, src))
                    bad += [f'{fn}:{i}' for i, line in enumerate(src.splitlines(), 1) if spelled.search(line)]
        self.assertEqual(bad, [], 'these compose the agent sentence themselves; read it from lanes.json')


if __name__ == '__main__': unittest.main()
