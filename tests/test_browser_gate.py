"""BROWSER ACTS THAT CAN'T BE UNDONE WAIT FOR THE OWNER'S PRESS (browsergate.py): a look passes without a model; any other
agent-browser command is judged by the model over the page; irreversible, unsure or unjudged is held as a proposal on the task and
refused to the agent; the owner's Approve runs that exact command on that same page and tells the agent; Dismiss tells it no."""
import json, re, time, unittest
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
    "ask_json stood in: the model's answer is `v` for each act it is shown, in one call (a dict, or an exception to raise)."
    def ask(brain, system, user, want=None, need=(), **kw):
        brain.seen.append(user) if hasattr(brain, 'seen') else None
        if isinstance(v, Exception): raise v
        return SimpleNamespace(data={'acts': [v] * len(re.findall(r'^ACT \d+:', user, re.M))})
    return mock.patch('taskuary.llm.ask_json', ask)


def answers(*vs, calls=None):
    "ask_json stood in: the model's answer is the array `vs`, whatever it is shown; `calls` counts the asks."
    def ask(brain, system, user, want=None, need=(), **kw):
        if calls is not None: calls.append(user)
        return SimpleNamespace(data={'acts': list(vs)})
    return mock.patch('taskuary.llm.ask_json', ask)


def one(store, act, pg, brain=None, **kw): return bg.judge(store, [act], pg, brain, **kw)[0]


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

    def test_a_command_run_by_another_or_inside_a_loop_is_still_an_act(self):
        """`timeout 30 agent-browser click @e12`, `echo @e12 | xargs agent-browser click`, `sudo`, `nohup`, `env`, `nice`, and a click in a
        `for ... do` or an `if ... then` read as no browser act at all - the click ran ungated. The shell's own grammar: its reserved words
        open a command, and a program that runs the command after it (by its options) is no command of its own."""
        for cmd in ('timeout 30 agent-browser click @e12', 'echo @e12 | xargs agent-browser click', 'sudo -u alex agent-browser click @e12',
                    'nohup agent-browser click @e12 &', 'env FOO=1 agent-browser click @e12', 'time agent-browser click @e12',
                    'nice -n 5 agent-browser click @e12', 'for r in e1 e12; do agent-browser click @$r; done',
                    'if true; then agent-browser click @e12; fi', 'while true; do agent-browser click @e12; break; done',
                    '{ agent-browser click @e12; }', '! agent-browser click @e12', 'stdbuf -oL timeout 9 agent-browser click @e12'):
            self.assertEqual([a['verb'] for a in bg.acts(cmd)], ['click'], cmd)
        for cmd in ('grep -r agent-browser docs', 'echo agent-browser click', 'which agent-browser', 'timeout 5 agent-browser snapshot -i'):
            self.assertEqual(bg.acts(cmd), [], cmd)

    def test_a_line_break_in_typed_text_is_never_plain_typing(self):
        # _segments reads a newline as `;`, so a break inside quotes came back as " ; " and fill passed with no AI (2026-10-31)
        self.assertTrue(bg.typing(bg.acts('agent-browser fill @e1 "Dear Erin"')[0]))
        for cmd in ("agent-browser fill @e1 'line one\nline two'", 'agent-browser fill @e1 "line one`nline two"'):
            a = bg.acts(cmd)
            if a: self.assertFalse(bg.typing(a[0]), cmd)
        self.assertEqual(bg.acts('npx agent-browser@0.41.0 click @e12')[0]['verb'], 'click')      # a pinned version is the same tool

    def test_a_redirection_is_no_argument(self):
        """The real-CLI walk, 2026-11-16: `fill @e1 "Alex Doyle" 2>/dev/null` read as fill @e1 "Alex Doyle" 2, and run for the owner the
        box said "Alex Doyle 2". A redirection's descriptor and target are the shell's, never the command's; quoted text keeps its >."""
        cmd = 'agent-browser fill @e1 "Alex Doyle" 2>/dev/null && agent-browser click @e3 2>&1 | tail -1; agent-browser fill @e2 x &>log.txt'
        self.assertEqual([a['args'] for a in bg.acts(cmd)], [['fill', '@e1', 'Alex Doyle'], ['click', '@e3'], ['fill', '@e2', 'x']])
        self.assertEqual(bg.acts('agent-browser type @e2 "a > b"')[0]['args'], ['type', '@e2', 'a > b'])

    def test_the_agents_own_session_flag_is_not_what_runs(self):
        self.assertEqual(bg._own_args(['--session', 'other', 'click', '@e12', '--headed']), ['click', '@e12'])


class Judging(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll invoice'); self.act = bg.acts('agent-browser click @e12')[0]

    def test_the_model_reads_the_page_and_the_command(self):
        b = Brain(None)
        with verdict({'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example'}):
            v = one(self.s, self.act, {'url': CHECKOUT, 'elements': SNAP}, b)
        self.assertEqual(v, {'hold': True, 'what': 'pays the $412.50 order on toll.example', 'why': "it can't be undone"})
        self.assertIn('button "Continue" [ref=e12]', b.seen[0]); self.assertIn('agent-browser click @e12', b.seen[0])

    def test_unsure_unread_or_unjudged_is_a_hold(self):
        for v in ({'irreversible': False, 'sure': False}, {'nonsense': 1}, RuntimeError('timed out')):
            with verdict(v): self.assertTrue(one(self.s, self.act, {'url': CHECKOUT}, Brain(None))['hold'], v)
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertTrue(one(self.s, self.act, {'url': CHECKOUT})['hold'])      # no AI at all: it waits for the owner

    def test_with_no_ai_typing_passes_and_everything_else_waits(self):
        typed = ('agent-browser fill @e1 "alex@northwind.example"', 'agent-browser type @e2 "hello"', 'agent-browser keyboard type "abc"',
                 'agent-browser --session tq-1 keyboard inserttext "abc"', 'agent-browser find label "Email" fill "alex@northwind.example"',
                 'agent-browser find role textbox fill "x" --name Email')
        pressed = ('agent-browser click @e12', 'agent-browser press Enter', 'agent-browser keyboard press Enter', 'agent-browser check @e4',
                   'agent-browser select @e5 "Express"', 'agent-browser find role button click --name Submit', 'agent-browser eval "1"',
                   'agent-browser find role x --exact fill click', 'agent-browser keyboard --delay 5 type "x"', 'agent-browser click "@e12')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            for cmd in typed: self.assertFalse(one(self.s, bg.acts(cmd)[0], {'url': CHECKOUT})['hold'], cmd)
            for cmd in pressed:
                v = one(self.s, bg.acts(cmd)[0], {'url': CHECKOUT})
                self.assertTrue(v['hold'], cmd); self.assertIn('no AI', v['why'])
            self.assertFalse(bg.typing({'args': ['type', '@e2', 'hi\nthere'], 'verb': 'type'}))     # a line break can be the form's Enter
            with on(): self.assertEqual(bg.check(self.s, self.tid, 'run1', 'agent-browser fill @e1 "a" && agent-browser fill @e2 "b"'), {})
            with on(): self.assertEqual(bg.check(self.s, self.tid, 'run1', 'agent-browser fill @e1 "a" && agent-browser click @e3')
                                        ['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_with_an_ai_typing_is_still_judged(self):
        # ...inside the line's one ask (2026-11-17): the fill is an entry of the same verdict as the click after it, never a free pass
        b, todo = Brain(None), bg.acts('agent-browser fill @e1 "a" && agent-browser click @e12')
        with verdict({'irreversible': True, 'sure': True, 'what': 'x'}):
            self.assertEqual([v['hold'] for v in bg.judge(self.s, todo, {'url': CHECKOUT}, b)], [True, True])
        [seen] = b.seen; self.assertIn('ACT 1: ', seen); self.assertIn('agent-browser fill @e1 a', seen); self.assertIn('ACT 2: ', seen)

    def test_unsure_of_a_tick_or_a_choice_lets_it_go_but_sure_it_cannot_be_undone_still_holds(self):
        """The real-CLI walk, 2026-11-16: ticking a sign-up's "I agree to the terms" box was held as "the AI could not tell whether it can be
        undone" - the owner was handed a checkbox, and an Enter on the page could not tick it. A tick, an untick, a choice or typing sends
        nothing: unsure on one of them it goes on. Sure it can't be undone (a toggle that saves itself), it is held as ever; a click unsure is held."""
        unsure, sure = {'irreversible': True, 'sure': False, 'what': 'agrees to the terms'}, {'irreversible': True, 'sure': True, 'what': 'turns 2FA off'}
        for cmd in ('agent-browser check @e4', 'agent-browser uncheck @e4', 'agent-browser select @e5 "free"', 'agent-browser fill @e1 "a"'):
            with verdict(unsure): self.assertFalse(one(self.s, bg.acts(cmd)[0], {'url': CHECKOUT}, Brain(None))['hold'], cmd)
            with verdict(sure): self.assertTrue(one(self.s, bg.acts(cmd)[0], {'url': CHECKOUT}, Brain(None))['hold'], cmd)
        with verdict(unsure): self.assertTrue(one(self.s, self.act, {'url': CHECKOUT}, Brain(None))['hold'])

    def test_what_the_owner_asked_for_in_his_own_words_is_done_save_money(self):
        """The owner, 2026-11-17: "If you ask it to sign up to those sites it should do it, nothing else required." His own words are given to
        the verdict; an act they ask for is not held for a second yes - unless it pays or moves money, which always waits. No words of his,
        no such pass, whatever the model says."""
        b = Brain(None)
        said = 'Sign up for a free account on each of the ten vendors and collect their tables.'
        with verdict({'irreversible': True, 'sure': True, 'what': 'creates an account on rentscope.example', 'asked': True, 'money': False}):
            self.assertFalse(one(self.s, self.act, {'url': CHECKOUT, 'elements': SNAP}, b, said=said)['hold'])
            self.assertTrue(one(self.s, self.act, {'url': CHECKOUT}, Brain(None), said='')['hold'], 'no words of his, no pass')
        self.assertIn(said, b.seen[0])
        with verdict({'irreversible': True, 'sure': True, 'what': 'pays $49 on dealflow.example', 'asked': True, 'money': True}):
            self.assertTrue(one(self.s, self.act, {'url': CHECKOUT}, Brain(None), said='Sign up and pay for DealFlow Pro')['hold'])
        # ...and a verdict that does not say whether it moves money is no "it does not": a CLI judge carries no schema, and one that left the
        # key out passed a payment he had asked for with no press
        with verdict({'irreversible': True, 'sure': True, 'what': 'pays $49 on dealflow.example', 'asked': True}):
            self.assertTrue(one(self.s, self.act, {'url': CHECKOUT}, Brain(None), said='Sign up and pay for DealFlow Pro')['hold'])
        from taskuary import general
        self.s.add_comment(self.tid, 'owner', general.USER_TYPE, said)
        self.s.add_comment(self.tid, general.BRIEF_ACTOR, general.USER_TYPE, 'Signed in to x - continue.')
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Sure.')
        self.assertEqual(bg.asked(self.s, self.tid), said, "only his own lines, never Taskuary's or the agent's")

    def test_a_reversible_act_sure_of_it_passes(self):
        with verdict({'irreversible': False, 'sure': True, 'what': 'opens the order summary'}):
            self.assertFalse(one(self.s, self.act, {'url': CHECKOUT}, Brain(None))['hold'])


class Holding(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll invoice')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: self.told.append(text))

    def held(self, cmd='agent-browser click @e12', v=None):
        with on(), verdict(v or {'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example'}):
            return bg.check(self.s, self.tid, 'run1', cmd, Brain(None))

    def heard(self):
        "What the agent was told - on its own thread now, since a chat's send_prompt is its whole next turn (browsergate._tell)."
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told

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

    def test_the_boxes_filled_before_a_held_press_in_one_line_go_in_and_nothing_after_it_runs(self):
        """The real-CLI walk, 2026-11-16: "fill name && fill email && click Next" was held whole - the boxes were never filled, the owner was
        handed an empty form "left as you filled it", and every press of his was refused by the site. The acts the gate passes on their own,
        before the held one, run first and in order; the held one waits; what comes after it does not run. One ask for the line (2026-11-17)."""
        ran, calls, ok = [], [], {'irreversible': False, 'sure': True, 'what': 'fills the sign-up'}
        cmd = ("agent-browser fill @e1 'Alex Doyle' && agent-browser fill @e2 alex@northwind.example && agent-browser check @e4 && "
               "agent-browser click @e12 && agent-browser fill @e3 x")
        with on(), answers(ok, ok, ok, {'irreversible': True, 'sure': True, 'what': 'goes to step 2 of the sign-up'}, ok, calls=calls),                 mock.patch.object(bg, '_run', lambda sid, args, wait, tag: ran.append(args) or (0, '')):
            out = bg.check(self.s, self.tid, 'run1', cmd, Brain(None))
        self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(ran, [['fill', '@e1', 'Alex Doyle'], ['fill', '@e2', 'alex@northwind.example'], ['check', '@e4']])
        [rv] = self.pending(); self.assertEqual(json.loads(rv['DraftText'])['args'], ['click', '@e12'])
        self.assertEqual(len(calls), 1)

    def test_a_line_of_acts_is_one_ask_not_one_per_act(self):
        # 2026-11-17: a sign-up's four fills and ticks were four model calls in a row, each with the same page, before the hook could answer
        calls, ok = [], {'irreversible': False, 'sure': True, 'what': 'fills the form'}
        with on(), answers(ok, ok, ok, ok, calls=calls):
            out = bg.check(self.s, self.tid, 'run1', 'agent-browser fill @e1 "a" && agent-browser fill @e2 "b" && agent-browser check @e3 && '
                                                     'agent-browser click @e4', Brain(None))
        self.assertEqual((out, len(calls)), ({}, 1))

    def test_an_answer_short_of_the_line_holds_from_the_first_act_it_left_out(self):
        ran, ok = [], {'irreversible': False, 'sure': True, 'what': 'fills the form'}
        with on(), answers(ok, ok), mock.patch.object(bg, '_run', lambda sid, args, wait, tag: ran.append(args) or (0, '')):
            out = bg.check(self.s, self.tid, 'run1', 'agent-browser fill @e1 "a" && agent-browser fill @e2 "b" && agent-browser check @e3 && '
                                                     'agent-browser click @e4', Brain(None))
        self.assertIn("could not be read", out['hookSpecificOutput']['permissionDecisionReason'])
        self.assertEqual(ran, [['fill', '@e1', 'a'], ['fill', '@e2', 'b']])
        [rv] = self.pending(); self.assertEqual(json.loads(rv['DraftText'])['args'], ['check', '@e3'])

    def test_his_words_pass_each_act_on_its_own_and_never_a_payment(self):
        said = 'Sign up for DealFlow and buy the Pro plan.'
        todo = bg.acts('agent-browser fill @e1 "a" && agent-browser click @e12')
        with answers({'irreversible': True, 'sure': True, 'what': 'types', 'asked': True, 'money': False},
                     {'irreversible': True, 'sure': True, 'what': 'pays $49', 'asked': True, 'money': True}):
            self.assertEqual([v['hold'] for v in bg.judge(self.s, todo, {'url': CHECKOUT}, Brain(None), said=said)], [False, True])

    def test_a_payment_in_a_line_that_also_pushes_is_still_judged_as_a_browser_act(self):
        """A line that clicks Pay and pushes (`click @e12 && git push`) went to the shell gate alone: its card said "push", its Approve - or
        a trusted repo, or the terminal's own prompt - ran the payment with it, unseen. Every gate a line touches judges its part of it."""
        pay = {'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example', 'money': True}
        for trust in (False, True):
            self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the toll invoice')
            with on(), verdict(pay), mock.patch('taskuary.shellgate.trusted', return_value='northwind/ledger' if trust else ''):
                out = hooks.command_gate(self.s, self.tid, 'run1', 'agent-browser click @e12 && git push origin main', 'Bash', r'C:\work\ledger')
            self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny', trust)
            [rv] = self.pending(); p = json.loads(rv['DraftText'])
            self.assertEqual((p['action'], p['args']), ('browser_act', ['click', '@e12']), trust)
            for ask in ('terminal', 'chat'):
                with on(), verdict(pay):
                    d = hooks.command_gate(self.s, self.tid, 'run1', 'git push origin main; agent-browser click @e12', 'Bash', r'C:\work\ledger', ask)
                self.assertEqual(d['hookSpecificOutput']['permissionDecision'], 'deny', ask)

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
                mock.patch.object(bg, '_run', lambda sid, args, wait, tag: (0, SNAP) if args[0] == 'snapshot' else ran.append((sid, args)) or (0, '✓ Done')):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertTrue(out['ok'], out)
        self.assertEqual(ran, [('run1', ['click', '@e12'])])
        self.assertIn('The owner approved it', self.heard()[0]); self.assertIn('agent-browser click @e12', self.told[0])
        self.assertEqual(self.pending(), [])

    def test_a_page_that_moved_on_is_not_acted_on(self):
        self.held(); [rv] = self.pending()
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': 'https://pay.toll.example/checkout/other'}), \
                mock.patch.object(bg, '_run') as run:
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertIn('moved on', out['send_error'])
        run.assert_not_called()
        self.assertEqual(self.pending(), [], 'over, its error kept - the agent holds it anew (the owner, 2026-11-16: no Try again)')

    def test_a_hold_that_fails_to_be_filed_still_holds(self):
        """The hook's route lets a command go on any error (server.cli_hook_browser), so a payment judged irreversible whose card failed to be
        written - a busy store, a record that raised - ran with no card and no press. Once there is an act, a failure is a hold."""
        with on(), verdict({'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example'}), \
                mock.patch('taskuary.proposals.queue', side_effect=RuntimeError('database is locked')):
            out = hooks.command_gate(self.s, self.tid, 'run1', 'agent-browser click @e12', 'Bash', '')
        d = out['hookSpecificOutput']
        self.assertEqual(d['permissionDecision'], 'deny'); self.assertIn('nothing was done', d['permissionDecisionReason'])

    def test_a_ref_that_names_another_control_by_the_press_is_not_acted_on(self):
        """A checkout on one address re-draws itself: held as @e12 "Continue", by the owner's Approve a fresh snapshot gave @e12 to "Remove
        item" - the address was the same, so the click ran on a control nobody approved. The ref must still name what was held."""
        self.held(); [rv] = self.pending()
        self.assertEqual(json.loads(rv['DraftText'])['control'], {'name': 'Continue', 'role': 'button'})
        moved = SNAP.replace('button "Continue" [ref=e12]', 'button "Remove item" [ref=e12]')
        ran = []
        def run(sid, args, wait, tag):
            ran.append(args)
            return (0, moved) if args[0] == 'snapshot' else (0, '✓ Done')
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': CHECKOUT}), mock.patch.object(bg, '_run', run):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertIn('no longer', out['send_error'])
        self.assertNotIn(['click', '@e12'], ran)

    def test_dismiss_tells_the_agent_it_was_not_done(self):
        self.held(); [rv] = self.pending()
        with mock.patch('taskuary.workerstate._live', return_value=self.sess), mock.patch.object(bg, '_run') as run:
            self.assertTrue(verdicts.decide(self.s, rv, 'reject')['ok'])
        run.assert_not_called()
        self.assertIn('did not approve it', self.heard()[0])


PAY = 'http://127.0.0.1:8765/checkout'
PAY_SNAP = '- heading "Pay for your order" [level=1]\n- textbox "Card name" [ref=e3]\n- button "Pay $42.00" [ref=e12]'


class Page:
    "The DevTools connection, stood in: each look at the page reads the next of `reads` (the last repeats); an exception is a page that cannot be read."
    def __init__(self, *reads): self.reads, self.n = list(reads), 0
    def js(self, expr):
        r = self.reads[min(self.n, len(self.reads) - 1)]; self.n += 1
        if isinstance(r, Exception): raise r
        return r
    def close(self): pass


class HandingOver(unittest.TestCase):
    """THE OWNER PRESSES PAY ON THE PAGE (the owner, 2026-11-05): where someone watches the session, the agent's held press is not a card - the
    page is handed to the owner as the agent filled it, and their own press on it is the approval."""
    def setUp(self):
        from taskuary import workerstate as ws
        self.ws, self.s = ws, MemoryStore(); self.tid = Factory(self.s).task('Pay the course fee')
        self.told, self.scrolled = [], []
        self.sess = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, send_prompt=lambda text, as_owner=True: self.told.append(text))
        self.live = mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': self.sess}, clear=True); self.live.start()
        self.addCleanup(self.live.stop); self.addCleanup(bg.HANDS.clear)

    def hand(self, url=PAY):
        with on(url, PAY_SNAP), verdict({'irreversible': True, 'sure': True, 'what': 'pays $42.00 on the course page'}), \
                mock.patch.object(bg, 'watch', None), mock.patch.object(bg, '_run', lambda sid, a, w, t: self.scrolled.append((sid, a)) or (0, '')):
            return bg.check(self.s, self.tid, 'run1', "agent-browser click '@e12'", Brain(None))

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
    def heard(self):
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told

    def test_an_agents_click_on_pay_becomes_a_hand_over_not_a_proposal(self):
        why = self.hand()['hookSpecificOutput']
        self.assertEqual(why['permissionDecision'], 'deny')
        self.assertIn('a card in this task waiting for it', why['permissionDecisionReason'])
        self.assertEqual(self.pending(), [])                                          # no Approve card
        req = bg.handing(self.s, self.tid, 'run1')
        self.assertTrue(req['RequestId'].startswith(bg.PRESS) and req['RequestId'].startswith(browserview.TURN_PREFIX))
        self.assertEqual(req['Text'], 'Your turn: check it and press "Pay $42.00" on the page. I\'ll go on when you\'re done.')
        self.assertEqual(self.scrolled, [('run1', ['scrollintoview', '@e12'])])        # the page is left on the button
        self.assertTrue(bg.waiting(self.s, self.tid, 'run1')); self.assertTrue(hooks.held_for(self.s, self.tid, 'run1'))
        self.hand()                                                                   # tried again: the same hand-over
        self.assertEqual(len([r for r in self.ws.open_requests(self.ws.events(self.s, self.tid)) if r['RequestId'].startswith(bg.PRESS)]), 1)

    def test_the_same_press_handed_over_again_is_on_screen_again(self):
        # the owner, 2026-11-10 ("i cant see the screen"): a client record's Save on portal.vendor.example, handed over, closed (his Done, the
        # page unmoved), then handed over again by the agent's next turn - recorded under the answered id, it was never open: no card, no
        # chip, "agent done" and Mark done lit while the step waited on him
        from taskuary import taskstate
        self.hand(); rid = bg.handing(self.s, self.tid, 'run1')['RequestId']
        self.assertTrue(bg.done(self.s, self.tid, rid)); self.heard()
        self.ws.record(self.s, self.tid, 'run1', 'working', text=self.ws.WAKE, source='api')     # the agent's told turn
        self.hand()
        req = bg.handing(self.s, self.tid, 'run1')
        self.assertIsNotNone(req, 'the second hand-over waits on the owner')
        self.assertTrue(req['RequestId'].startswith(bg.PRESS)); self.assertNotEqual(req['RequestId'], rid)
        self.assertEqual(self.ws.asking_of(self.s, self.sess)['request_id'], req['RequestId'])         # the chat's card, live
        t = {**self.s.get_task(self.tid), 'Kind': 'general'}
        self.assertFalse(taskstate.done_for_now(self.s, t, {'state': 'asking', 'request': self.ws.asking_of(self.s, self.sess)}))
        with mock.patch.dict('taskuary.terminal.SESSIONS', {}, clear=True):                          # at rest, or after a restart
            self.assertEqual(taskstate.open_question(self.s, self.tid)['request_id'], req['RequestId'])
        self.hand(); self.assertEqual(bg.handing(self.s, self.tid, 'run1')['RequestId'], req['RequestId'])     # still one, not two

    def test_the_page_moving_past_the_step_tells_the_agent_it_was_done(self):
        self.hand(); rid = bg.handing(self.s, self.tid, 'run1')['RequestId']
        here = {'href': PAY, 'title': 'Pay for your order', 'there': True}
        done = {'href': 'http://127.0.0.1:8765/checkout/thanks', 'title': 'Thank you - payment received', 'there': False}
        self.assertTrue(bg.watch(self.s, self.tid, 'run1', rid, conn=Page(here, here, done), every=0))
        self.assertIn('The page moved on from "Pay $42.00"', self.heard()[0])
        self.assertIn('Thank you - payment received', self.told[0])
        # ...SAID AS SEEN: the page moving is not the press - "Back to cart" moves it too, and told "The owner pressed Pay", the agent
        # reported a payment that was never made
        self.assertNotIn('The owner pressed', self.told[0]); self.assertIn('not which control', self.told[0])
        self.assertIsNone(bg.handing(self.s, self.tid, 'run1'))                       # the hand-over is closed
        self.assertFalse(bg.watch(self.s, self.tid, 'run1', rid, conn=Page(done), every=0))   # ...once

    def test_a_button_gone_from_the_same_address_is_past_too(self):
        here, paid = {'href': PAY, 'title': 'Pay', 'there': True}, {'href': PAY + '#paid', 'title': 'Pay', 'there': False}
        self.assertTrue(bg.past(here, paid)); self.assertFalse(bg.past(here, {**here, 'href': PAY + '#top'}))

    def test_the_owner_saying_no_tells_the_agent_it_was_not_done(self):
        self.hand()
        note = bg.owner_said(self.s, self.tid, 'run1', "don't - wrong card")
        self.assertIn('NOT pressed', note); self.assertIn('"Pay $42.00"', note)
        self.hand(); self.assertEqual(bg.owner_said(self.s, self.tid, 'run1', browserview.TURN_BACK), '')     # their Done is theirs, as it is

    def test_words_instead_of_the_press_leave_nothing_waiting_and_the_agent_hears_so(self):
        # the owner, 2026-11-10: "i cant see the screen" closed the hand-over; the agent, told only "NOT pressed", answered that Save was
        # "held for your press in the browser pane beside this chat" - the chip read "agent done" and Mark done was lit, which was the truth
        from taskuary import taskstate
        self.hand()
        note = bg.owner_said(self.s, self.tid, 'run1', 'i cant see the screen')
        self.ws.record(self.s, self.tid, 'run1', 'working', source='api')             # his line is the agent's next turn
        self.assertIsNone(bg.handing(self.s, self.tid, 'run1')); self.assertIsNone(taskstate.open_question(self.s, self.tid))
        self.assertIn('nothing waits for their press now', note)
        self.assertIn(proposals.AGAIN, note)   # the one sentence every passed card's agent hears (proposals.move_on)
        self.hand(); self.assertIsNotNone(bg.handing(self.s, self.tid, 'run1'))      # ...and that brings it back in front of him

    def test_a_pane_answered_in_words_hears_it_was_not_done(self):
        pane = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, cli='claude')
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': pane}, clear=True):
            self.hand(); rid = bg.handing(self.s, self.tid, 'run1')['RequestId']
            typed = []
            with mock.patch('taskuary.terminal.type_into', lambda s, t: typed.append(t)):
                self.ws.answer(self.s, self.tid, rid, 'not now')
        self.assertTrue(typed[0].startswith('not now (')); self.assertIn('NOT pressed', typed[0]); self.assertNotIn('\n', typed[0])
        self.assertIsNone(bg.handing(self.s, self.tid, 'run1'))

    def test_the_browser_closed_tells_the_agent_it_was_not_done(self):
        self.hand(); rid = bg.handing(self.s, self.tid, 'run1')['RequestId']
        here = {'href': PAY, 'title': 'Pay', 'there': True}
        with mock.patch.object(browserview, 'state', return_value={'open': False}):
            self.assertTrue(bg.watch(self.s, self.tid, 'run1', rid, conn=Page(here, RuntimeError('gone')), every=0))
        self.assertIn('did not press "Pay $42.00"', self.heard()[0]); self.assertIn('NOT done', self.told[0])

    def test_a_headless_run_still_gets_a_proposal(self):
        with mock.patch.dict('taskuary.terminal.SESSIONS', {}, clear=True): self.hand()
        self.assertEqual(len(self.pending()), 1); self.assertIsNone(bg.handing(self.s, self.tid, 'run1'))
        self.s._exec("DELETE FROM review WHERE TaskId=?", (self.tid,))
        self.hand('about:blank')                                                      # a session, but no page to show it on
        self.assertEqual(len(self.pending()), 1); self.assertIsNone(bg.handing(self.s, self.tid, 'run1'))

    def test_a_captcha_hand_over_is_watched_and_goes_on_by_itself(self):
        # the owner, 2026-11-05: "if we need the user we should wait for them to do it" - the page moving on closes it, Done stays
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': PAY}):
            rid = browserview.your_turn(self.s, self.tid, 'run1', 'tick the "I\'m not a robot" box', watch=None)
        self.assertEqual(bg.HANDS[rid]['kind'], 'turn')
        self.assertEqual(json.loads(self.ws.events(self.s, self.tid)[-1]['ChoicesJson']), [browserview.TURN_DONE])
        here = {'href': PAY, 'title': 'Check', 'marks': ['f:https://challenge.example/box', 'i:card']}
        gone = {'href': PAY, 'title': 'Check', 'marks': ['i:notes']}                  # same address, the challenge and the box gone
        self.assertTrue(bg.watch(self.s, self.tid, 'run1', rid, conn=Page(here, gone), every=0))
        self.assertIn('The owner did the step you handed them', self.heard()[0])
        self.assertIsNone(next((r for r in self.ws.open_requests(self.ws.events(self.s, self.tid)) if r['RequestId'] == rid), None))

    def test_after_the_watch_stops_typing_still_goes_on(self):
        self.hand(); rid = bg.handing(self.s, self.tid, 'run1')['RequestId']
        here = {'href': PAY, 'title': 'Pay', 'there': True}
        self.assertFalse(bg.watch(self.s, self.tid, 'run1', rid, conn=Page(here), every=0, until=0.05))
        self.assertTrue(bg.HANDS[rid]['expired'])
        note = bg.owner_said(self.s, self.tid, 'run1', 'paid it just now')        # the chat's send_prompt, on the owner's next line
        self.assertIn('stopped watching the page', note); self.assertIn('Look at the page as it is now', note)
        self.ws.record(self.s, self.tid, 'run1', 'working', source='api')           # ...and that line is the agent's next turn
        self.assertIsNone(bg.handing(self.s, self.tid, 'run1'))

    def test_the_agent_is_told_the_step_is_a_card_never_a_screen_to_point_at(self):
        # the owner, 2026-11-10: "please click Save at the bottom of the page in the browser pane" - "i cant see the screen". The pane is drawn
        # only when the app shows it; the agent is told what is true wherever the owner stands, and never to ask for the click in words
        handed = self.hand()['hookSpecificOutput']['permissionDecisionReason']
        with mock.patch.dict('taskuary.terminal.SESSIONS', {}, clear=True): self.s._exec("DELETE FROM worker_event"); carded = self.hand()
        carded = carded['hookSpecificOutput']['permissionDecisionReason']
        for said in (handed, carded, browserview.brief(held=True), browserview.offer(held=True)):
            self.assertNotIn('beside', said); self.assertNotIn('WATCHING', said)
        self.assertNotIn('in this browser', handed)
        for said in (handed, carded, browserview.HOLD_LINE):
            self.assertIn('card in this task', said); self.assertIn('never ask', said.lower())

    def test_the_brief_says_to_fill_it_and_leave_the_last_press_to_the_owner(self):
        self.assertIn('fill in everything first', browserview.brief(held=True))
        self.assertIn('TASKUARY-YOURTURN', browserview.ASK_FIRST_LINE); self.assertIn('NEVER press it', browserview.ASK_FIRST_LINE)


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


class LooksThatAreNot(unittest.TestCase):
    """M4: an address carrying a token is a magic link or a way out, and `get value` reads a password box the vault just filled."""
    def test_an_address_with_a_token_or_a_long_query_is_judged_and_a_plain_one_is_not(self):
        for cmd in ('agent-browser open https://toll.example', 'agent-browser goto https://docs.example/guide/setup?tab=mail',
                    'agent-browser get text @e3'):
            self.assertEqual(bg.acts(cmd), [], cmd)
        for url in ('https://bank.example/approve?t=9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c', 'https://x.example/?d=' + 'a' * 50,
                    'https://x.example/c/eyJhbGciOiJIUzI1NiJ9eyJzdWIiOiIxMjM0NTY3ODkwIn0'):
            self.assertEqual([a['verb'] for a in bg.acts(f'agent-browser open {url}')], ['navigate'], url)
        with on(), verdict({'irreversible': True, 'sure': True, 'what': 'approve a payment'}):
            s = MemoryStore(); t = Factory(s).task()
            out = bg.check(s, t, 's1', 'agent-browser open https://bank.example/approve?t=9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c', brain=Brain({}))
        self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_an_address_that_runs_script_or_a_new_tabs_magic_link_is_judged(self):
        """`open "javascript:document.forms[0].submit()"` sent a form as a look, never judged; and `tab new <address>` opened a magic link
        with no look at its token - only open/goto/navigate were read for one."""
        for cmd in ('agent-browser open "javascript:document.forms[0].submit()"', 'agent-browser goto JavaScript:void(0)',
                    'agent-browser tab new "javascript:document.querySelector(\'#pay\').click()"',
                    'agent-browser tab new https://bank.example/approve?t=9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c',
                    # ...and `read <address>`, which fetches it without the browser: the same link, the same way out for what the agent read
                    'agent-browser read https://bank.example/approve?t=9f8a7b6c5d4e3f2a1b0c9d8e7f6a5b4c', 'agent-browser read https://x.example/?d=' + 'a' * 50):
            self.assertEqual([a['verb'] for a in bg.acts(cmd)], ['navigate'], cmd)
        for cmd in ('agent-browser tab new https://toll.example', 'agent-browser tab 2', 'agent-browser tab', 'agent-browser open about:blank',
                    'agent-browser read', 'agent-browser read https://docs.example/guide --filter auth'):
            self.assertEqual(bg.acts(cmd), [], cmd)

    def test_get_value_on_a_password_box_or_an_unknown_box_is_refused(self):
        snap = '- textbox "Email" [ref=e1]\n- textbox "Password" [ref=e2]'
        s = MemoryStore(); t = Factory(s).task()
        with on(snap=snap):
            self.assertEqual(bg.check(s, t, 's1', 'agent-browser get value @e1'), {})
            for ref in ('@e2', '@e9', '"#pw"'):
                self.assertEqual(bg.check(s, t, 's1', f'agent-browser get value {ref}')['hookSpecificOutput']['permissionDecision'], 'deny', ref)


class AFormFieldIsNotTheSending(unittest.TestCase):
    def test_the_judge_is_told_a_field_of_an_unsent_form_is_reversible(self):
        """Recorded on the real CLI (the browser audit, 2026-11-15): told to tick a sign-in page's "keep this browser verified for 30 days"
        before handing the code step over, the agent's tick was held for the owner's approval as a security setting - and the press the
        page then saw was said to him as his tick. A field of a form not sent yet changes nothing outside the browser; the sending is
        judged on its own."""
        from taskuary import browsergate as bg
        self.assertIn('ticking, choosing or filling a field of a form that is not sent yet', bg.SYSTEM)
        self.assertIn('the sending is judged on its own', bg.SYSTEM)
