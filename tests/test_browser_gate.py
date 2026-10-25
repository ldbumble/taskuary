"""BROWSER ACTS THAT CAN'T BE UNDONE WAIT FOR THE OWNER'S PRESS (browsergate.py): a look passes without a model; any other
agent-browser command is judged by the model over the page; irreversible, unsure or unjudged is held as a proposal on the task and
refused to the agent; the owner's Approve runs that exact command on that same page and tells the agent; Dismiss tells it no."""
import json, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import browsergate as bg, browserview, hooks, proposals, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CHECKOUT = 'https://pay.toll.example/checkout/review'
SNAP = '- heading "Review your order" [level=1]\n- text "Total $412.50"\n- button "Continue" [ref=e12]\n- link "Back to cart" [ref=e3]'


class Brain:
    """The model, stood in: answers each verdict from `say`, and records what it was shown."""
    takes_want = True
    def __init__(self, say): self.say, self.seen = say, []
    def __call__(self, *a, **k): return self


def verdict(v):
    "ask_json stood in: the model's answer is `v` (a dict, or an exception to raise)."
    def ask(brain, system, user, want=None, need=(), **kw):
        brain.seen.append(user) if hasattr(brain, 'seen') else None
        if isinstance(v, Exception): raise v
        return SimpleNamespace(data=v)
    return mock.patch('taskuary.llm.ask_json', ask)


def on(url=CHECKOUT, snap=SNAP):
    return mock.patch.object(bg, 'page', return_value={'url': url, 'open': True, 'elements': snap})


class Reading(unittest.TestCase):
    def test_looks_are_not_acts_and_need_no_model(self):
        for cmd in ('agent-browser snapshot -i -c', 'agent-browser open https://toll.example', 'agent-browser get url && agent-browser screenshot',
                    'git status', 'grep -r agent-browser docs', 'agent-browser --session tq-1 snapshot'):
            self.assertEqual(bg.acts(cmd), [], cmd)

    def test_every_other_command_is_an_act_however_it_is_spelled(self):
        self.assertEqual([a['verb'] for a in bg.acts('agent-browser fill @e1 "alex" && agent-browser click @e12')], ['fill', 'click'])
        self.assertEqual(bg.acts('npx agent-browser click @e12')[0]['args'], ['click', '@e12'])
        self.assertEqual(bg.acts(r'& "C:\tools\agent-browser.exe" press Enter')[0]['verb'], 'press')
        self.assertEqual(bg.acts('FOO=1 agent-browser --json eval "document.forms[0].submit()"')[0]['verb'], 'eval')
        self.assertEqual(bg.acts('bash -c "agent-browser click @e12"')[0]['verb'], 'click')
        self.assertEqual(bg.acts('agent-browser find role button "Pay now" click')[0]['verb'], 'find')
        self.assertEqual(bg.acts('agent-browser click "@e12')[0]['verb'], '?')        # cannot be read: judged, never waved through

    def test_the_agents_own_session_flag_is_not_what_runs(self):
        self.assertEqual(bg._own_args(['--session', 'other', 'click', '@e12', '--headed']), ['click', '@e12'])


class Judging(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll invoice'); self.act = bg.acts('agent-browser click @e12')[0]

    def test_the_model_reads_the_page_and_the_command(self):
        b = Brain(None)
        with verdict({'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example'}):
            v = bg.judge(self.s, self.act, {'url': CHECKOUT, 'elements': SNAP}, b)
        self.assertEqual(v, {'hold': True, 'what': 'pays the $412.50 order on toll.example', 'why': "it can't be undone"})
        self.assertIn('button "Continue" [ref=e12]', b.seen[0]); self.assertIn('agent-browser click @e12', b.seen[0])

    def test_unsure_unread_or_unjudged_is_a_hold(self):
        for v in ({'irreversible': False, 'sure': False}, {'nonsense': 1}, RuntimeError('timed out')):
            with verdict(v): self.assertTrue(bg.judge(self.s, self.act, {'url': CHECKOUT}, Brain(None))['hold'], v)
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertTrue(bg.judge(self.s, self.act, {'url': CHECKOUT})['hold'])      # no AI at all: it waits for the owner

    def test_with_no_ai_typing_passes_and_everything_else_waits(self):
        typed = ('agent-browser fill @e1 "alex@northwind.example"', 'agent-browser type @e2 "hello"', 'agent-browser keyboard type "abc"',
                 'agent-browser --session tq-1 keyboard inserttext "abc"', 'agent-browser find label "Email" fill "alex@northwind.example"',
                 'agent-browser find role textbox fill "x" --name Email')
        pressed = ('agent-browser click @e12', 'agent-browser press Enter', 'agent-browser keyboard press Enter', 'agent-browser check @e4',
                   'agent-browser select @e5 "Express"', 'agent-browser find role button click --name Submit', 'agent-browser eval "1"',
                   'agent-browser find role x --exact fill click', 'agent-browser keyboard --delay 5 type "x"', 'agent-browser click "@e12')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            for cmd in typed: self.assertFalse(bg.judge(self.s, bg.acts(cmd)[0], {'url': CHECKOUT})['hold'], cmd)
            for cmd in pressed:
                v = bg.judge(self.s, bg.acts(cmd)[0], {'url': CHECKOUT})
                self.assertTrue(v['hold'], cmd); self.assertIn('no AI', v['why'])
            self.assertFalse(bg.typing({'args': ['type', '@e2', 'hi\nthere'], 'verb': 'type'}))     # a line break can be the form's Enter
            with on(): self.assertEqual(bg.check(self.s, self.tid, 'run1', 'agent-browser fill @e1 "a" && agent-browser fill @e2 "b"'), {})
            with on(): self.assertEqual(bg.check(self.s, self.tid, 'run1', 'agent-browser fill @e1 "a" && agent-browser click @e3')
                                        ['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_with_an_ai_typing_is_still_judged(self):
        b = Brain(None)
        with verdict({'irreversible': True, 'sure': True, 'what': 'x'}):
            self.assertTrue(bg.judge(self.s, bg.acts('agent-browser fill @e1 "a"')[0], {'url': CHECKOUT}, b)['hold'])
        self.assertTrue(b.seen)

    def test_a_reversible_act_sure_of_it_passes(self):
        with verdict({'irreversible': False, 'sure': True, 'what': 'opens the order summary'}):
            self.assertFalse(bg.judge(self.s, self.act, {'url': CHECKOUT}, Brain(None))['hold'])


class Holding(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll invoice')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: self.told.append(text))

    def held(self, cmd='agent-browser click @e12', v=None):
        with on(), verdict(v or {'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example'}):
            return bg.check(self.s, self.tid, 'run1', cmd, Brain(None))

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))

    def test_an_irreversible_act_is_refused_and_put_on_the_task(self):
        out = self.held()
        d = out['hookSpecificOutput']
        self.assertEqual((d['hookEventName'], d['permissionDecision']), ('PreToolUse', 'deny'))
        self.assertIn('held this for the owner', d['permissionDecisionReason'])
        [rv] = self.pending()
        p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['sid'], p['args'], p['url'], p['site']), ('browser_act', 'run1', ['click', '@e12'], CHECKOUT, 'toll.example'))
        self.assertIn('pays the $412.50 order on toll.example', rv['Reason'])
        self.held()                                                                   # tried again: the same card, not a second
        self.assertEqual(len(self.pending()), 1)

    def test_a_reversible_act_runs_and_nothing_is_queued(self):
        self.assertEqual(self.held('agent-browser fill @e1 "Northwind"', {'irreversible': False, 'sure': True, 'what': 'types a name'}), {})
        self.assertEqual(self.pending(), [])

    def test_an_agent_cannot_propose_one_itself(self):
        self.assertEqual(proposals.parse('TASKUARY-PROPOSE {"action": "browser_act", "sid": "run1", "args": ["click", "@e12"]}'), [])

    def test_approve_runs_that_command_on_that_page_and_tells_the_agent(self):
        self.held(); [rv] = self.pending()
        ran = []
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': CHECKOUT + '#top'}), \
                mock.patch('taskuary.workerstate._live', return_value=self.sess), \
                mock.patch.object(bg, '_run', lambda sid, args, wait, tag: ran.append((sid, args)) or (0, '✓ Done')):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertTrue(out['ok'], out)
        self.assertEqual(ran, [('run1', ['click', '@e12'])])
        self.assertIn('The owner approved it', self.told[0]); self.assertIn('agent-browser click @e12', self.told[0])
        self.assertEqual(self.pending(), [])

    def test_a_page_that_moved_on_is_not_acted_on(self):
        self.held(); [rv] = self.pending()
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': 'https://pay.toll.example/checkout/other'}), \
                mock.patch.object(bg, '_run') as run:
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertIn('moved on', out['send_error'])
        run.assert_not_called()
        self.assertEqual(len(self.pending()), 1)                                    # still the owner's to dismiss

    def test_dismiss_tells_the_agent_it_was_not_done(self):
        self.held(); [rv] = self.pending()
        with mock.patch('taskuary.workerstate._live', return_value=self.sess), mock.patch.object(bg, '_run') as run:
            self.assertTrue(verdicts.decide(self.s, rv, 'reject')['ok'])
        run.assert_not_called()
        self.assertIn('did not approve it', self.told[0])


class Hook(unittest.TestCase):
    def test_the_hook_reads_shell_commands_of_our_panes_only(self):
        s = MemoryStore(); tid = Factory(s).task('Pay the toll invoice')
        pane = SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd=r'C:\work', argv=['claude'], ext_id='c-1', resumed_from='', store=s)
        pay = {'tool_name': 'Bash', 'tool_input': {'command': 'agent-browser click @e12'}, 'session_id': 'c-1', 'cwd': r'C:\work'}
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': pane}, clear=True), on(), \
                verdict({'irreversible': True, 'sure': True, 'what': 'pays'}):
            self.assertEqual(hooks.browser({**pay, 'tool_name': 'Read'}, Brain(None)), {})
            self.assertEqual(hooks.browser({**pay, 'tool_input': {'command': 'ls'}}, Brain(None)), {})
            self.assertEqual(hooks.browser({**pay, 'session_id': 'someone-else'}, Brain(None)), {})      # not our pane: Claude's own
            self.assertEqual(hooks.browser(pay, Brain(None))['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_every_session_carries_the_hook(self):
        pre = hooks.session_hooks(token='t', base='http://127.0.0.1:1')['PreToolUse']
        g = [x for x in pre if x['matcher'] == hooks.BROWSER_MATCH]
        self.assertEqual(len(g), 1); self.assertIn(hooks.BROWSER_MARK, g[0]['hooks'][0]['command'])

    def test_an_agent_token_may_call_it(self):
        from taskuary import guard
        self.assertEqual(guard.denied('POST', '/api/hooks/claude/browser'), '')


if __name__ == '__main__': unittest.main()
