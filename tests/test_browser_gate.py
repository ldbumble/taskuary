"""BROWSER ACTS THAT CAN'T BE UNDONE WAIT FOR THE OWNER'S PRESS (browsergate.py): a look passes without a model; any other
agent-browser command is judged by the model over the page; irreversible, unsure or unjudged is held as a proposal on the task and
refused to the agent; the owner's Approve runs that exact command on that same page and tells the agent; Dismiss tells it no."""
import json, os, re, time, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from taskuary import browsergate as bg, browserview, gatecmd, hooks, proposals, verdicts
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

    def test_a_read_that_fetches_a_magic_link_is_judged_as_opening_it(self):
        link = 'https://vendor.example/invoices/approve?token=9f8e7d6c5b4a39281706f5e4d3c2b1a0ffeeddcc'
        for cmd in (f'agent-browser open {link}', f'agent-browser read {link}', f'agent-browser read --outline {link}'):
            self.assertEqual([x['verb'] for x in bg.acts(cmd)], ['navigate'], cmd)
        for cmd in ('agent-browser read', 'agent-browser read https://docs.example/guide', 'agent-browser read --filter Total'):
            self.assertEqual(bg.acts(cmd), [], cmd)

    def test_a_find_that_only_reads_or_points_is_a_look(self):
        "Searching the page is not acting on it - by agent-browser's own grammar for find's actions, never judged, never held."
        for cmd in ('agent-browser find text "Total gross" text', 'agent-browser find role heading text --name Payroll',
                    "agent-browser find first 'td.total' text", 'agent-browser find nth 2 ".run" hover'):
            self.assertEqual(bg.acts(cmd), [], cmd)
        for cmd in ('agent-browser find text "Pay now"', 'agent-browser find text "Pay now" click', 'agent-browser find role button --name Pay click',
                    'agent-browser find nth 2 ".run" click', 'agent-browser find label "Amount" fill "412.50"'):
            self.assertEqual([x['verb'] for x in bg.acts(cmd)], ['find'], cmd)

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
                    '{ agent-browser click @e12; }', '! agent-browser click @e12', 'stdbuf -oL timeout 9 agent-browser click @e12',
                    'start /b agent-browser click @e12'):
            self.assertEqual([a['verb'] for a in bg.acts(cmd)], ['click'], cmd)
        self.assertTrue(bg.acts('Start-Process agent-browser -ArgumentList "click @e12"'))       # PowerShell's: judged, never a look
        for cmd in ('grep -r agent-browser docs', 'echo agent-browser click', 'which agent-browser', 'timeout 5 agent-browser snapshot -i'):
            self.assertEqual(bg.acts(cmd), [], cmd)

    def test_a_press_behind_a_launcher_or_a_quote_is_still_an_act(self):
        """`timeout 30 agent-browser click @e3` - a press on "Pay now" wrapped the way agents wrap a slow command - was read as a call of
        `timeout` and ran past the gate, and `agent-brows''er` (one word to the shell) did not name the tool at all. A launcher runs what
        follows it; the name is read as the shell joins it."""
        for cmd in ('timeout 30 agent-browser click @e3', 'AGENT=1 timeout -s KILL 30 agent-browser click @e3', 'env DEBUG=1 agent-browser click @e3',
                    'nohup agent-browser click @e3', 'sudo agent-browser click @e3', 'nice -n 5 agent-browser click @e3',
                    'echo @e3 | xargs agent-browser click', "agent-brows''er click @e3", 'stdbuf -oL agent-browser click @e3'):
            [a] = bg.acts(cmd)
            self.assertEqual(a['verb'], 'click', cmd)
        self.assertEqual(bg.acts('timeout 30 agent-browser snapshot -i'), [], 'a look behind a launcher is still a look')
        self.assertEqual(bg.acts('grep -rn agent-browser notes.md'), [], 'naming the tool to another program is no call of it')

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

    def test_a_batch_is_its_steps(self):
        """The vendor walk, 2026-11-19: `agent-browser batch` read as one act, and its card said "Starts a browser batch on RentScope with no
        actions shown" - nobody could judge it. Each quoted argument is a command of its own, read as one; a batch fed its steps on its input
        shows none, and is refused to the agent with the way that shows them - never a card."""
        cmd = "agent-browser --session v1 batch 'open https://rentscope.example/signup' 'fill @e2 \"Alex Doyle\"' 'click @e5' 'snapshot -i'"
        self.assertEqual([a['args'] for a in bg.acts(cmd)], [['fill', '@e2', 'Alex Doyle'], ['click', '@e5']])
        [fed] = bg.acts("echo '[[\"click\", \"@e5\"]]' | agent-browser batch --bail")
        self.assertEqual(fed['verb'], 'batch')
        s = MemoryStore(); tid = Factory(s).task('Vendor trials')
        with on(), verdict({'irreversible': True, 'sure': True, 'what': 'x'}):
            out = bg.check(s, tid, 'run1', "echo '[[\"click\", \"@e5\"]]' | agent-browser batch", Brain(None))
        self.assertEqual(out['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertIn('as its own quoted argument', out['hookSpecificOutput']['permissionDecisionReason'])
        self.assertEqual(s._rows("SELECT * FROM review WHERE TaskId=?", (tid,)), [], 'no card he cannot judge')

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

    def test_a_free_sign_up_runs_and_money_or_his_own_details_wait_as_one_card(self):
        """The owner, 2026-11-19: "anything big like spending money or putting in private info should wait for user for now". The vendor
        walk held every free sign-up "because it can't be undone" - one press each, on work Erin had asked for and he had opened. The gate's
        question is his rule: a step that is not big runs, asked in his words or not; one that spends money, sends his own details, speaks
        for him or deletes something of his is one card, whatever he said; the form's filled boxes are what the judge reads a send by."""
        b = Brain(None)
        said = 'Sign up for a free account on each of the ten vendors and collect their tables.'
        with verdict({'irreversible': True, 'sure': True, 'what': 'Submit the sign-up on RentScope', 'big': False}):
            self.assertFalse(one(self.s, self.act, {'url': CHECKOUT, 'elements': SNAP}, b, said=said)['hold'])
            self.assertFalse(one(self.s, self.act, {'url': CHECKOUT}, Brain(None), said='')['hold'], 'a free sign-up runs on the task he opened')
        self.assertIn(said, b.seen[0])
        for kind, what, why in (('money', 'Pay $49 for DealFlow Pro', 'spends your money'), ('private', 'Send your mobile number to ZoningNow', 'your own details'),
                                ('speaks', 'Post the announcement on social.example', 'speaks for you'), ('deletes', 'Cancel the plan on cloud.example', 'deletes or cancels')):
            with verdict({'irreversible': True, 'sure': True, 'what': what, 'big': True, 'kind': kind}):
                v = one(self.s, self.act, {'url': CHECKOUT}, Brain(None), said='Sign up and pay for DealFlow Pro')
                self.assertTrue(v['hold'], what); self.assertIn(why, v['why']); self.assertEqual(v['what'], what)
        # ...the form's filled boxes are put before the judge: his own phone in one is what makes its send his
        b = Brain(None)
        with verdict({'irreversible': True, 'sure': True, 'what': 'Send your mobile number to ZoningNow', 'big': True, 'kind': 'private'}):
            one(self.s, self.act, {'url': CHECKOUT, 'fields': [{'k': 'mobile', 't': 'tel', 'v': '+1 555 0100'}]}, b)
        self.assertIn('+1 555 0100', b.seen[0]); self.assertIn('SENDS HIS OWN PRIVATE DETAILS', bg.SYSTEM)
        # ...unsure whether it is big is held; and a verdict that does not say whether it is big is no "it is not": a CLI judge carries no
        # schema, and one that left the key out passed a payment he had asked for with no press
        with verdict({'irreversible': True, 'sure': False, 'what': 'Continue on the checkout', 'big': False}):
            self.assertTrue(one(self.s, self.act, {'url': CHECKOUT}, Brain(None))['hold'])
        with verdict({'irreversible': True, 'sure': True, 'what': 'pays $49 on dealflow.example'}):
            self.assertTrue(one(self.s, self.act, {'url': CHECKOUT}, Brain(None), said='Sign up and pay for DealFlow Pro')['hold'])
        from taskuary import general
        self.s.add_comment(self.tid, 'owner', general.USER_TYPE, said)
        self.s.add_comment(self.tid, general.BRIEF_ACTOR, general.USER_TYPE, 'Signed in to x - continue.')
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Sure.')
        self.assertEqual(bg.asked(self.s, self.tid), said, "only his own lines, never Taskuary's or the agent's")

    def test_a_held_steps_words_never_name_a_ref_and_its_line_is_cut_at_a_word(self):
        """Design round 6, D3: "1 of 3 · next: clicks ref e640 on uprinting.com, which is not in the visible snapshot, so its effect is u" and
        "Clicks unknown BotWall control @e30" stood as cards. A ref is the browser's grammar, never his words: the control the page names
        it, else the site; and the next card's line is cut at a word."""
        from taskuary import cardqueue
        with verdict({'irreversible': True, 'sure': False, 'what': 'clicks ref e640 on uprinting.com, which is not in the visible snapshot', 'big': False}):
            v = one(self.s, self.act, {'url': 'https://www.uprinting.example/booklets', 'elements': ''}, Brain(None))
        self.assertTrue(v['hold']); self.assertEqual(v['what'], 'a step on uprinting.example')
        with verdict({'irreversible': True, 'sure': False, 'what': 'Clicks unknown BotWall control @e30', 'big': False}):
            self.assertEqual(one(self.s, self.act, {'url': CHECKOUT, 'elements': SNAP}, Brain(None))['what'], 'click the "Continue" button on toll.example')
        long = 'held before it ran, in the agent browser: ' + 'Submit the sign-up form on the vendor portal for the board data trial with the made-up details'
        u = {'rids': [1], 'rows': [{'ReviewId': 1, 'Kind': 'action', 'Status': 'pending', 'Reason': long, 'DraftText': '{}'}]}
        w = cardqueue.what(self.s, u)
        self.assertTrue(w.endswith('…') and len(w) <= 91 and long.split(': ', 1)[1].startswith(w[:-1]), w)

    def test_his_go_ahead_typed_while_the_turn_runs_is_his_words_at_once(self):
        """The vendor walk, 2026-11-18 (0 of 13 accounts): the task came from a colleague's chat, and "go ahead and submit them all yourself"
        was typed while the agent's turn ran - kept for its next step, so not yet his words to the gate, which read "(none)" and held every
        Create account. A line waiting for the agent is his words all the same."""
        from taskuary import general
        general.wait_line(self.s, self.tid, 'Go ahead and submit them all yourself - free plans only, make up the passwords.')
        self.assertIn('submit them all yourself', bg.asked(self.s, self.tid))
        b = Brain(None)
        with verdict({'irreversible': True, 'sure': True, 'what': 'creates a free account on parcelpulse.example', 'asked': True, 'big': False}):
            self.assertFalse(one(self.s, self.act, {'url': CHECKOUT}, b, said=bg.asked(self.s, self.tid))['hold'])
        self.assertIn('submit them all yourself', b.seen[0])

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
        # ...but the same ref on ANOTHER page is another act: it was folded into the first card - the agent told its "closes the account"
        # waited on a card that said "pays $412.50", on a page the browser had left, and it never reached the owner
        with on('https://pay.toll.example/account/close', '- button "Close my account" [ref=e12]'), \
                verdict({'irreversible': True, 'sure': True, 'what': 'closes the account on toll.example'}):
            bg.check(self.s, self.tid, 'run1', 'agent-browser click @e12', Brain(None))
        self.assertEqual([json.loads(r['DraftText'])['what'] for r in self.pending()],
                         ['pays the $412.50 order on toll.example', 'closes the account on toll.example'])

    def test_his_yes_to_a_press_on_a_site_stands_for_the_task_and_his_no_is_told_not_asked_again(self):
        # ONE RULE (actrule.decide, 2026-11-19): the same press on the same site he approved on this task runs; one he dismissed is his no
        self.held()
        [rv] = self.pending(); p = json.loads(rv['DraftText'])
        self.assertEqual(p['keys'], ['browser|toll.example|click the "Continue" button on toll.example'])
        with mock.patch.object(bg, '_perform', return_value={'performed': 'done'}): bg.perform(self.s, self.tid, p)
        self.s.decide_review(rv['ReviewId'], 'approved', None, 'owner', 'approved')
        self.assertEqual(self.held(), {})                                              # runs: no second card
        self.assertEqual(self.pending(), [])
        s2 = MemoryStore(); t2 = Factory(s2).task('Pay the toll invoice')
        self.s, self.tid = s2, t2
        self.held(); [rv] = self.pending(); p = json.loads(rv['DraftText'])
        with mock.patch.object(bg, '_tell'): bg.declined(self.s, self.tid, p)
        self.s.decide_review(rv['ReviewId'], 'rejected', None, 'owner', 'dismissed')
        self.assertIn('The owner dismissed this same step', self.held()['hookSpecificOutput']['permissionDecisionReason'])
        self.assertEqual(self.pending(), [])

    def test_a_line_of_acts_is_one_ask_not_one_per_act(self):
        # 2026-11-17: a sign-up's four fills and ticks were four model calls in a row, each with the same page, before the hook could answer
        calls, ok = [], {'irreversible': False, 'sure': True, 'what': 'fills the form'}
        with on(), answers(ok, ok, ok, ok, calls=calls):
            out = bg.check(self.s, self.tid, 'run1', 'agent-browser fill @e1 "a" && agent-browser fill @e2 "b" && agent-browser check @e3 && '
                                                     'agent-browser click @e4', Brain(None))
        self.assertEqual((out, len(calls)), ({}, 1))

    def test_his_words_pass_each_act_on_its_own_and_never_a_payment(self):
        said = 'Sign up for DealFlow and buy the Pro plan.'
        todo = bg.acts('agent-browser fill @e1 "a" && agent-browser click @e12')
        with answers({'irreversible': True, 'sure': True, 'what': 'types', 'asked': True, 'big': False},
                     {'irreversible': True, 'sure': True, 'what': 'pays $49', 'asked': True, 'big': True}):
            self.assertEqual([v['hold'] for v in bg.judge(self.s, todo, {'url': CHECKOUT}, Brain(None), said=said)], [False, True])

    def test_a_payment_in_a_line_that_also_pushes_is_held_where_it_runs(self):
        """A line that clicks Pay and pushes (`click @e12 && git push`): the shell's gate judges the push, and the click is held where it
        runs (gatecmd) - never waved through with the push's card, a trusted repo or the terminal's own prompt."""
        pay = {'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example', 'big': True}
        with on(), verdict(pay), mock.patch('taskuary.shellgate.trusted', return_value='northwind/ledger'):
            self.assertEqual(hooks.command_gate(self.s, self.tid, 'run1', 'agent-browser click @e12 && git push origin main', 'Bash', r'C:\work\ledger'), {})
            self.assertIn(bg.HELD, gatecmd.judge(self.s, self.tid, 'run1', 'agent-browser click @e12', r'C:\work\ledger'))
        [rv] = self.pending(); p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['args']), ('browser_act', ['click', '@e12']))

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

    def test_his_yes_runs_only_on_the_tab_it_was_held_on_while_that_tab_is_on_its_page(self):
        """Walk 5, 2026-11-19: a sign-up held on one site's tab stayed lit while another site's tab was shown, and his Approve ran on that other
        site's page. A held step names its tab; Approve runs there only (switched to it if another is shown), and refuses where that tab left
        its page - in plain words, the card over, the agent told."""
        with mock.patch.object(browserview, 'active_tab', return_value='T1'),                 mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': CHECKOUT, 'type': 'page'}]):
            self.held()
        [rv] = self.pending(); p = json.loads(rv['DraftText'])
        self.assertEqual((p['tab'], p['url']), ('T1', CHECKOUT))
        other = {'id': 'T2', 'url': 'http://127.0.0.12:8080/quota', 'type': 'page'}
        switched = []
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': other['url']}),                 mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': CHECKOUT, 'type': 'page'}, other]),                 mock.patch.object(browserview, 'active_tab', side_effect=lambda sid: switched[-1] if switched else 'T2'),                 mock.patch.object(browserview, 'switch_tab', side_effect=lambda sid, t: switched.append(t) or True),                 mock.patch.object(bg, 'page', return_value={'url': CHECKOUT, 'open': True, 'elements': SNAP}),                 mock.patch.object(bg, '_run', return_value=(0, 'done')) as run, mock.patch('taskuary.workerstate._live', return_value=self.sess):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertTrue(out['ok'], out); self.assertEqual(switched, ['T1']); run.assert_called_once()     # on its own tab, never the one shown
        # ...and where its tab has left its page: nothing runs, said plainly
        self.tid = Factory(self.s).task('Pay the parking invoice')
        with mock.patch.object(browserview, 'active_tab', return_value='T1'),                 mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': CHECKOUT, 'type': 'page'}]):
            self.held()
        [rv] = self.pending()
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': other['url']}),                 mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': other['url'], 'type': 'page'}]),                 mock.patch.object(bg, '_run') as run, mock.patch('taskuary.workerstate._live', return_value=self.sess):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); run.assert_not_called()
        self.assertIn('already left that page', out['send_error']); self.assertIn('holds it again', out['send_error'])

    def test_a_held_step_greys_when_its_own_tab_leaves_its_page_whatever_tab_is_shown(self):
        with mock.patch.object(browserview, 'active_tab', return_value='T1'),                 mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': CHECKOUT, 'type': 'page'}]):
            self.held()
        with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': CHECKOUT}, {'id': 'T2', 'url': 'http://127.0.0.12/q'}]),                 mock.patch.object(bg, '_tell'):
            self.assertEqual(bg.left_now(self.s, self.tid), [])                    # another tab shown: its own is on its page, lit
        with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': 'https://pay.toll.example/receipt'}]), mock.patch.object(bg, '_tell'):
            [rid] = bg.left_now(self.s, self.tid)
        self.assertTrue(proposals.passed(self.s.get_review(rid)))

    def test_a_held_upload_runs_in_the_agents_folder_on_approve(self):
        """`upload @e5 ./resume.pdf` held and approved ran from the SERVER's folder: the relative path named another file, or none, and a held
        `download @e5 ./invoice.pdf` saved where nobody looks. The held command runs where the agent ran it, as a held shell step does."""
        work = r'C:\work\offsite'
        with on(snap='- button "Attach your resume" [ref=e5]'), verdict({'irreversible': True, 'sure': True, 'what': 'uploads resume.pdf to jobs.example'}):
            gatecmd.judge(self.s, self.tid, 'run1', 'agent-browser upload @e5 ./resume.pdf', work)
        [rv] = self.pending(); self.assertEqual(json.loads(rv['DraftText'])['cwd'], work)
        ran = []
        def run(sid, args, wait, tag, cwd=None):
            ran.append((args, cwd)); return (0, '- button "Attach your resume" [ref=e5]') if args[0] == 'snapshot' else (0, '✓ Done')
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': CHECKOUT}), mock.patch.object(bg, '_run', run), \
                mock.patch('taskuary.workerstate._live', return_value=self.sess):
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        self.assertIn((['upload', '@e5', './resume.pdf'], work), ran)

    def test_a_hold_that_fails_to_be_filed_still_holds(self):
        """A payment judged irreversible whose card failed to be written - a busy store, a record that raised - ran with no card and no
        press. Once there is an act, a failure is a hold."""
        with on(), verdict({'irreversible': True, 'sure': True, 'what': 'pays the $412.50 order on toll.example'}), \
                mock.patch('taskuary.proposals.queue', side_effect=RuntimeError('database is locked')):
            self.assertIn('nothing was done', gatecmd.judge(self.s, self.tid, 'run1', 'agent-browser click @e12'))

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


class HeldInTheChat(unittest.TestCase):
    """A HELD PRESS IS ONE CARD IN THE CHAT, watched or not (the owner, 2026-11-18: "payment should be an approval like everything else").
    It was handed to him inside the embedded page wherever someone watched (2026-11-05): in the vendor walk he had to find ten "press it"
    banners in ten tabs of a small pane, and the app had no button of its own. What stays his on the page is only what only he can do there."""
    def setUp(self):
        from taskuary import workerstate as ws
        self.ws, self.s = ws, MemoryStore(); self.tid = Factory(self.s).task('Pay the course fee')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, send_prompt=lambda text, as_owner=True: self.told.append(text))
        self.live = mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': self.sess}, clear=True); self.live.start()
        self.addCleanup(self.live.stop); self.addCleanup(bg.HANDS.clear)

    def hand(self, url=PAY):
        with on(url, PAY_SNAP), verdict({'irreversible': True, 'sure': True, 'what': 'pays $42.00 on the course page'}),                 mock.patch.object(bg, 'watch', None), mock.patch.object(bg, '_run', lambda sid, a, w, t: (0, '')):
            return bg.check(self.s, self.tid, 'run1', "agent-browser click '@e12'", Brain(None))

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
    def heard(self):
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told

    def test_an_agents_click_on_pay_with_the_owner_watching_is_a_card_never_a_press_on_the_page(self):
        why = self.hand()['hookSpecificOutput']
        self.assertEqual(why['permissionDecision'], 'deny')
        [rv] = self.pending(); p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['args'], p['control']), ('browser_act', ["click", "@e12"], {'name': 'Pay $42.00', 'role': 'button'}))
        self.assertFalse([r for r in self.ws.open_requests(self.ws.events(self.s, self.tid)) if r['RequestId'].startswith(browserview.TURN_PREFIX)],
                         'nothing is handed to him inside the page')
        self.assertTrue(bg.waiting(self.s, self.tid, 'run1')); self.assertTrue(hooks.held_for(self.s, self.tid, 'run1'))
        self.hand(); self.assertEqual(len(self.pending()), 1, 'tried again: the same card')

    def test_a_button_gone_from_the_same_address_is_past_too(self):
        here, paid = {'href': PAY, 'title': 'Pay', 'there': True}, {'href': PAY + '#paid', 'title': 'Pay', 'there': False}
        self.assertTrue(bg.past(here, paid)); self.assertFalse(bg.past(here, {**here, 'href': PAY + '#top'}))

    def test_a_captcha_hand_over_is_watched_and_goes_on_by_itself(self):
        # the owner, 2026-11-05: "if we need the user we should wait for them to do it" - the page moving on closes it, Done stays
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': PAY}):
            rid = browserview.your_turn(self.s, self.tid, 'run1', 'tick the "I am not a robot" box', watch=None)
        self.assertIn(rid, bg.HANDS)
        self.assertEqual(json.loads(self.ws.events(self.s, self.tid)[-1]['ChoicesJson']), [browserview.TURN_DONE])
        here = {'href': PAY, 'title': 'Check', 'marks': ['f:https://challenge.example/box', 'i:card']}
        gone = {'href': PAY, 'title': 'Check', 'marks': ['i:notes']}                  # same address, the challenge and the box gone
        self.assertTrue(bg.watch(self.s, self.tid, 'run1', rid, conn=Page(here, gone), every=0))
        self.assertIn('The owner did the step you handed them', self.heard()[0])
        self.assertIsNone(next((r for r in self.ws.open_requests(self.ws.events(self.s, self.tid)) if r['RequestId'] == rid), None))

    def test_a_captcha_whose_browser_closed_tells_the_agent_it_was_not_done(self):
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': PAY}):
            rid = browserview.your_turn(self.s, self.tid, 'run1', 'tick the check box', watch=None)
        here = {'href': PAY, 'title': 'Check', 'marks': ['i:card']}
        with mock.patch.object(browserview, 'state', return_value={'open': False}):
            self.assertTrue(bg.watch(self.s, self.tid, 'run1', rid, conn=Page(here, RuntimeError('gone')), every=0))
        self.assertIn('did not do the step you handed them', self.heard()[0]); self.assertIn('NOT done', self.told[0])

    def test_the_agent_is_told_the_step_is_a_card_never_a_screen_to_point_at(self):
        # the owner, 2026-11-10: "please click Save at the bottom of the page in the browser pane" - "i cant see the screen"
        carded = self.hand()['hookSpecificOutput']['permissionDecisionReason']
        for said in (carded, browserview.brief(), browserview.offer()):
            self.assertNotIn('beside', said); self.assertNotIn('WATCHING', said)
        self.assertIn('card in this task', carded); self.assertIn('never ask', carded.lower())
        self.assertIn('one card in this chat', browserview.HOLD_LINE); self.assertIn('never ask', browserview.HOLD_LINE.lower())

    def test_the_brief_says_to_fill_it_and_leave_the_last_press_to_the_owner(self):
        self.assertIn('fill in everything first', browserview.brief())


class AtTheCommand(unittest.TestCase):
    """THE HOLD IS UNDER THE ROAD (the design round, 2026-11-18): on Codex the agent's browser pressed a site's final Post itself - the hold
    lived in Claude's hook. Every task session runs Taskuary's `agent-browser` first (gatecmd), which asks before the real one runs."""
    def setUp(self): self.s = MemoryStore(); self.tid = Factory(self.s).task('Post the portal launch')

    def run_shim(self, *args, said=None):
        "The shim run as a Codex shell runs it: no hook, the server asked over HTTP (stood in by judge on this store), the real program recorded."
        ran, asked = [], []
        class Reply:
            def __init__(self, why): self.why = why
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, *a): return json.dumps({'why': self.why}).encode()
        def urlopen(req, timeout=None):
            b = json.loads(req.data); asked.append(b['cmd'])
            return Reply(gatecmd.judge(self.s, self.tid, 'run1', b['cmd'], b['cwd']))
        with on(snap='- button "Post" [ref=e7]'), verdict(said or {'irreversible': True, 'sure': True, 'what': 'posts the announcement on x.example'}), \
                mock.patch.object(gatecmd, 'real', return_value='real-agent-browser'), mock.patch('urllib.request.urlopen', urlopen), \
                mock.patch('taskuary.spawn.run', lambda argv, **k: ran.append(argv) or type('Done', (), {'returncode': 0})()), mock.patch.object(browserview, 'on_demand'):
            rc = gatecmd.main(['gatefolder', 'agent-browser', *args])
        return rc, ran, asked

    def test_every_task_session_runs_the_gate_first_whatever_its_ai(self):
        from taskuary import terminal
        env = terminal.session_env('assistant', self.tid, sid='run1')
        first = env['PATH'].split(os.pathsep)[0]
        self.assertEqual(first, gatecmd.folder())
        for n in ('agent-browser', 'agent-browser.cmd', 'agent-desktop', 'agent-desktop.cmd'):
            self.assertIn('taskuary.gatecmd', (Path(first) / n).read_text(encoding='utf-8'), n)

    def test_a_final_post_on_a_road_with_no_hook_is_held_before_it_runs(self):
        rc, ran, asked = self.run_shim('click', '@e7')
        self.assertEqual((rc, ran, asked), (1, [], ['agent-browser click @e7']))
        [rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
        self.assertEqual(json.loads(rv['DraftText'])['args'], ['click', '@e7'])

    def test_a_look_runs_at_once_and_a_reversible_act_after_asking(self):
        self.assertEqual(self.run_shim('snapshot', '-i'), (0, [['real-agent-browser', 'snapshot', '-i']], []))
        rc, ran, asked = self.run_shim('fill', '@e1', 'Q&A day', said={'irreversible': False, 'sure': True, 'what': 'types the post'})
        self.assertEqual((rc, ran), (0, [['real-agent-browser', 'fill', '@e1', 'Q&A day']]))

    def test_an_unreachable_taskuary_holds_a_press_and_lets_a_look_go(self):
        with mock.patch('urllib.request.urlopen', side_effect=OSError('connection refused')):
            self.assertIn(bg.HELD, gatecmd.ask('agent-browser', ['click', '@e7']))
            self.assertEqual(gatecmd.ask('agent-browser', ['open', 'https://x.example']), '')

    def test_an_agent_token_may_ask(self):
        from taskuary import guard
        self.assertEqual(guard.denied('POST', '/api/agent/gate'), '')


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


    def test_a_script_run_while_a_password_box_holds_one_is_refused(self):
        """`get value` on a password box is refused - and `eval` read the same box: judged only on whether it can be undone, a read passed,
        and the password Taskuary had just typed (a sign-up's, waiting for the owner's press) was the agent's to print."""
        snap = '- textbox "Email" [ref=e1]\n- textbox "Password" [ref=e2]'
        cmd = 'agent-browser eval "document.querySelector(\'input[type=password]\').value"'
        s = MemoryStore(); t = Factory(s).task()
        with on(snap=snap), verdict({'irreversible': False, 'sure': True, 'what': 'reads the page'}):
            with mock.patch('taskuary.signin.holds_password', return_value=True):
                self.assertEqual(bg.check(s, t, 's1', cmd, brain=Brain({}))['hookSpecificOutput']['permissionDecision'], 'deny')
            with mock.patch('taskuary.signin.holds_password', return_value=False):
                self.assertEqual(bg.check(s, t, 's1', cmd, brain=Brain({})), {}, 'with no password in the page, a script is judged as before')


class AFormFieldIsNotTheSending(unittest.TestCase):
    def test_the_judge_is_told_a_field_of_an_unsent_form_is_reversible(self):
        """Recorded on the real CLI (the browser audit, 2026-11-15): told to tick a sign-in page's "keep this browser verified for 30 days"
        before handing the code step over, the agent's tick was held for the owner's approval as a security setting - and the press the
        page then saw was said to him as his tick. A field of a form not sent yet changes nothing outside the browser; the sending is
        judged on its own."""
        from taskuary import browsergate as bg
        self.assertIn('ticking or choosing in a box sends nothing until the form is sent', bg.SYSTEM)
        self.assertIn('the sending is judged on its own', bg.SYSTEM)


def test_taskuarys_own_browser_calls_run_the_real_program_never_the_agents_hold_in_front_of_it(tmp_path, monkeypatch):
    """macOS CI, 2026-11-18: with the agents' hold first on PATH, the pane's own navigation ran the hold's launcher - which asked the server
    to approve the server, and the run hung. Taskuary's own calls find the real agent-browser past any launcher of the hold."""
    import os, stat
    from taskuary import browserview, gatecmd
    gate, real = tmp_path / 'gate', tmp_path / 'real'; gate.mkdir(); real.mkdir()
    for d, body in ((gate, '#!/bin/sh\nexec python -m taskuary.gatecmd "$(dirname "$0")" agent-browser "$@"\n'), (real, '#!/bin/sh\necho real\n')):
        for n in ('agent-browser', 'agent-browser.cmd'):
            (d / n).write_text(body, encoding='utf-8'); (d / n).chmod((d / n).stat().st_mode | stat.S_IEXEC)
    monkeypatch.setenv('PATH', os.pathsep.join([str(gate), str(real)]))
    got = browserview.program()
    assert got and not gatecmd.is_gate(got) and os.path.dirname(got) == str(real), got



class WhatTheSiteDid(unittest.TestCase):
    """THE VENDOR WALKS, 2026-11-18 (the owner: "stuck sites should not happen. It should be able to figure out next steps or try another
    way or ask the user for help"): a form posted to a site that never answers left the click "Done" and every command after it failing 30 s
    later with a socket error - six minutes of fresh tabs; a site's 500 and a robots wall read as pages like any other. After an act or an
    open, what the site did is the command's own result, in one line, at once; the next step is the agent's."""
    def test_a_load_that_never_finishes_is_stopped_and_said(self):
        stopped = []
        with mock.patch.object(bg, '_run', side_effect=RuntimeError(bg.LATE)), \
             mock.patch.object(browserview, 'unstick', lambda sid, since=None, every=False: stopped.append((sid, every)) or True):
            line = bg.outcome('run1')
        self.assertEqual(stopped, [('run1', True)])
        self.assertIn('did not finish loading', line); self.assertIn('another way', line); self.assertIn('one question to the owner', line)

    def test_an_error_status_is_said_by_its_number_and_a_working_page_says_nothing(self):
        def said(status):
            page = SimpleNamespace(js=lambda expr: {'status': status, 'url': 'http://127.0.0.12:18791/s/quotabase/signup'}, close=lambda: None)
            with mock.patch.object(bg, '_run', return_value=(0, 'http://127.0.0.12:18791/s/quotabase/signup')), \
                 mock.patch('taskuary.signin.connect', return_value=page):
                return bg.outcome('run1')
        self.assertIn('a server error (HTTP 500)', said(500))
        self.assertIn('turns this visit away (HTTP 403)', said(403))
        self.assertEqual(said(200), ''); self.assertEqual(said(0), '')

    def test_the_command_prints_what_the_site_did_after_it_ran(self):
        from taskuary import gatecmd
        asked = []
        def ask(name, args, after=False): asked.append(after); return 'TASKUARY: the page did not finish loading in 12 s' if after else ''
        with mock.patch.object(gatecmd, 'real', return_value='agent-browser'), mock.patch.object(gatecmd, 'ask', ask), \
             mock.patch('taskuary.spawn.run', return_value=SimpleNamespace(returncode=0)), mock.patch('sys.stderr') as err:
            self.assertEqual(gatecmd.main(['gate', 'agent-browser', 'click', '@e7']), 0)
        self.assertEqual(asked, [False, True])
        self.assertIn('did not finish loading', ''.join(str(c.args[0]) for c in err.write.call_args_list))


def test_plain_typing_runs_without_a_verdict_and_the_press_after_it_is_one():
    """The vendor walk, 2026-11-18: every box of every sign-up was a model call - six seconds a box, four boxes a form, thirteen forms. Typing
    leaves nothing outside the page until something is pressed: it runs at once, and only the press of the same line is judged."""
    s, calls = MemoryStore(), []
    t = Factory(s).task()
    with on(), answers({'irreversible': True, 'sure': True, 'what': 'creates an account', 'asked': True, 'big': False}, calls=calls):
        assert bg.check(s, t, 'run1', 'agent-browser fill @e1 "Alex Doyle"', Brain({})) == {}
        assert calls == [], 'typing asks no model'
        bg.check(s, t, 'run1', 'agent-browser fill @e2 "alex@northwind.example" && agent-browser click @e12', Brain({}))
    assert len(calls) == 1 and 'fill @e2' not in calls[0] and 'click @e12' in calls[0]


def test_the_launcher_runs_this_servers_code_and_hands_the_real_programs_output_on(tmp_path):
    """Round 4, 2026-11-19: a real program behind a .cmd, started with no console, wrote nothing to the handles it only inherited - every
    snapshot, url and read came back empty, and the agent worked the vendor sites with curl. And `-m taskuary` from the agent's folder ran
    whichever taskuary that Python had installed, not the server's own."""
    import subprocess, sys
    root = str(Path(gatecmd.__file__).resolve().parent.parent)
    gatecmd._DIR.clear()
    try:
        with mock.patch('taskuary.config.home', return_value=tmp_path): d = gatecmd.folder()
    finally: gatecmd._DIR.clear()
    assert root in (Path(d) / 'agent-browser.cmd').read_text(encoding='utf-8') and root.replace(chr(92), '/') in (Path(d) / 'agent-browser').read_text(encoding='utf-8')
    real = tmp_path / ('real.cmd' if os.name == 'nt' else 'real.sh')
    real.write_text('@echo page-snapshot\r\n' if os.name == 'nt' else '#!/bin/sh\necho page-snapshot\n'); real.chmod(0o755)
    script = tmp_path / 'launch.py'
    script.write_text(f'import sys; sys.path.insert(0, {root!r}); from unittest import mock; from taskuary import gatecmd\n'
                      f'with mock.patch.object(gatecmd, "real", return_value={str(real)!r}), mock.patch.object(gatecmd, "ask", return_value=""):\n'
                      f'    sys.exit(gatecmd.main(["gate", "agent-browser", "snapshot"]))\n', encoding='utf-8')
    out = subprocess.run([sys.executable, '-I', str(script)], capture_output=True, text=True, timeout=60)
    assert 'page-snapshot' in out.stdout, (out.stdout, out.stderr)


def test_signup_is_taskuarys_own_verb_answered_by_the_server_never_the_real_program():
    assert gatecmd.own('agent-browser signup') == 'signup' and gatecmd.own('agent-browser --session x signup') == 'signup'
    assert gatecmd.own('agent-browser click @e3') == '' and gatecmd.own('agent-browser snapshot -i') == ''
    ran, posted = [], []
    with mock.patch.object(gatecmd, 'real', return_value='real-agent-browser'), mock.patch('taskuary.spawn.run', lambda argv, **k: ran.append(argv)), \
         mock.patch.object(gatecmd, 'post', lambda cmd, after=False, wait=0: posted.append(cmd) or {'own': True, 'ok': True, 'said': 'Signed up on x.example'}):
        assert gatecmd.main(['gate', 'agent-browser', 'signup']) == 0
    assert ran == [] and posted == ['agent-browser signup']


def test_an_answer_out_of_shape_is_asked_once_more_before_anything_waits_on_him():
    """The owner's live app, 2026-11-19: a click to the second page of a file list was held - "the AI could not tell" - because the judge's
    entry came back out of shape. It is asked once more; only what it still cannot read waits on him."""
    s, calls, said = MemoryStore(), [], iter([{'acts': [{'what': 'next page'}]}, {'acts': [{'big': False, 'sure': True, 'irreversible': False,
                                                                                                'what': 'Show the second page of files on Box'}]}])
    def ask(brain, system, user, want=None, need=(), **kw): calls.append(user); return SimpleNamespace(data=next(said))
    with mock.patch('taskuary.llm.ask_json', ask):
        v = one(s, bg.acts('agent-browser click @e12')[0], {'url': 'https://app.box.example/folder/9', 'elements': SNAP}, Brain(None))
    assert (v['hold'], len(calls)) == (False, 2), (v, calls)


# ── the walk, 2026-11-19 ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_step_found_by_what_it_is_is_named_for_him_never_as_the_command():
    pg = {'url': 'https://pay.toll.example/checkout', 'elements': ''}
    a = bg.acts('agent-browser find role button click --name Next')[0]
    assert bg.target(a, pg) == 'click the "Next" button on toll.example'
    assert bg.target(bg.acts('agent-browser find label Email fill alex@northwind.example')[0], pg) == 'type into the "Email" box on toll.example'
    # ...and a page reached by a bare address by its own name (signin.site_name, its title), never "127.0.0.5"
    assert bg.target(a, {'url': 'http://127.0.0.5:8080/signup', 'elements': '', 'name': 'Trainly sign-up'}) == 'click the "Next" button on Trainly sign-up'
    with verdict(ValueError('no answer')):
        v = one(MemoryStore(), a, pg, Brain(None))
    assert not v['what'].lower().startswith('agent-browser')


def test_a_held_step_its_tab_left_greys_where_it_stood_and_the_agent_is_told():
    s, told = MemoryStore(), []
    tid = Factory(s).task('Sign up on the vendor portal')
    for args in (['find', 'role', 'button', 'click', '--name', 'Next'], ['click', '@e12']):        # a named click too: its tab is its page
        proposals.queue(s, tid, {'action': 'browser_act', 'sid': 'run1', 'args': args, 'url': CHECKOUT, 'tab': 'T1', 'site': 'toll.example',
                                 'what': f'step {args[-1]}', 'why': 'x'}, 'agent')
    with mock.patch.object(bg, '_tell', side_effect=lambda st, t, text, **k: told.append(text)):
        with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': CHECKOUT}]): assert bg.left_page(s, tid, 'run1') == []
        with mock.patch.object(browserview, 'pages', return_value=[]): assert bg.left_page(s, tid, 'run1') == []     # unread: nothing greys
        with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': 'https://pay.toll.example/receipt'}]):
            gone = bg.left_page(s, tid, 'run1')
    assert len(gone) == 2 and all(proposals.passed(s.get_review(r)) and proposals.passed_why(s, s.get_review(r)) == '' for r in gone)
    assert len(told) == 1 and 'left that page' in told[0]


def test_his_done_on_the_page_is_a_line_in_the_chat_even_under_a_turn_at_work():
    from taskuary import chatlog
    assert 'browser_act_pressed' in chatlog.AT_ONCE


def test_a_held_step_greys_when_the_task_is_read_after_its_tab_left_the_page():
    # the merge blocker (2026-11-19): greyed when it is served, not at the agent's next command
    s = MemoryStore(); tid = Factory(s).task('Sign up on the vendor portal')
    proposals.queue(s, tid, {'action': 'browser_act', 'sid': 'run1', 'args': ['find', 'role', 'button', 'click', '--name', 'Next'], 'url': CHECKOUT,
                             'tab': 'T1', 'site': 'toll.example', 'what': 'click the "Next" button on toll.example', 'why': 'x'}, 'agent')
    with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': CHECKOUT}]), mock.patch.object(bg, '_tell'): assert bg.left_now(s, tid) == []
    with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T2', 'url': CHECKOUT}]), mock.patch.object(bg, '_tell') as told:
        [rid] = bg.left_now(s, tid)                                         # its own tab gone - another tab on the same address is not it
    assert proposals.passed(s.get_review(rid)) and told.call_count == 1


def test_a_step_the_judge_says_is_not_big_runs_unless_it_is_also_unsure_and_for_good():
    # the walk, 2026-11-19: a free sign-up the judge said was not big, only unsure, was held as "it may spend money"
    pg = {'url': 'https://events.trainly.example/signup', 'elements': '- button "Create account" [ref=e5]'}
    a = bg.acts('agent-browser click @e5')[0]
    assert not bg._verdict(a, {'big': False, 'sure': False, 'irreversible': False, 'what': 'Submit the sign-up on Trainly'}, pg, '')['hold']
    v = bg._verdict(a, {'big': False, 'sure': False, 'irreversible': True, 'what': 'Submit the sign-up on Trainly'}, pg, '')
    assert v['hold'] and 'money' not in v['why']
    assert 'go-ahead HE GAVE' in bg.SYSTEM and 'work email' in bg.SYSTEM and 'never "the owner"' in bg.SYSTEM
    assert 'a post or message published in his name, still wait for his press' in bg.SYSTEM     # ...a post through the browser is always his press
