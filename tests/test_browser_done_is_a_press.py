"""THE VIEW'S DONE IS A PRESS (the spine audit, 2026-11-09). A step handed to the owner on the agent's page - a captcha, a code only he
has - has a Done on the view (a held press is a card in the chat since 2026-11-18, never handed over on the page). It went to a chat as words typed in the owner's name: a bubble they never wrote, a turn of its own, and
known to the server only by matching those words. It is their press now, by the road every other press takes: the hand-over closes, the
agent is told by Taskuary that they SAY it is done (nothing saw the page move, so it looks first), and the page reads one quiet line.
And the press the page itself saw read "You browser act pressed." under Taskuary's own line saying the same. Invented people."""
import json, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import browsergate as bg, browserview, general, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory, turn_told

PAY, SITE = 'https://pay.vendor.example/checkout', 'vendor.example'      # the one name of a site (signin.site_name)


class DoneIsAPress(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the course fee')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, send_prompt=lambda text, as_owner=True, **k: self.told.append((turn_told(self.s, self.tid, text), as_owner)))
        live = mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': self.sess}, clear=True); live.start()
        self.addCleanup(live.stop); self.addCleanup(bg.HANDS.clear)
        up = mock.patch.object(browserview, 'state', return_value={'open': True, 'url': PAY}); up.start(); self.addCleanup(up.stop)

    def turn(self):
        "The agent handed the page over for a step only a person can do."
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': PAY}):
            return browserview.your_turn(self.s, self.tid, 'run1', 'tick the "I\'m not a robot" box', watch=None)
    def heard(self):
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told
    def lines(self): return [m['content'][0]['text'] for m in general.press_lines(self.s, self.tid)]
    def said(self): return [c['Body'] for c in self.s.list_comments(self.tid, internal=True) if c.get('ActorType') == general.USER_TYPE]
    def open(self): return [r['RequestId'] for r in ws.open_requests(ws.events(self.s, self.tid))]

    def test_done_on_the_view_closes_the_step_and_is_never_a_line_the_owner_typed(self):
        rid = self.turn()
        out = ws.answer(self.s, self.tid, rid, '', press=True)
        self.assertEqual((out['delivered'], out['state']), (True, 'delivered'))
        [(words, as_owner)] = self.heard()
        self.assertFalse(as_owner, "Taskuary's note to the agent, never the owner's line")
        self.assertIn("The owner pressed I'm done", words); self.assertIn("tick the \"I'm not a robot\" box", words)
        self.assertIn('did not see the page move', words); self.assertIn('look at it as it is now', words)
        self.assertEqual(self.said(), [], 'no bubble, and no line by Taskuary either')
        # ...in the words of the button he pressed: the view's "I'm done" left "You pressed Done" (the overnight walk, 2026-11-11)
        self.assertEqual(self.lines(), [f"You pressed I'm done on {SITE}."])          # ...a press, never "the step is finished" (the walk, 2026-11-22)
        self.assertEqual(self.open(), []); self.assertEqual(bg.HANDS, {})
        again = ws.answer(self.s, self.tid, rid, '', press=True)                  # a second press, or the watch got there first
        self.assertEqual((again['delivered'], again['state']), (False, 'resolved')); self.assertEqual(len(self.told), 1)

    def test_his_done_puts_the_browser_back_on_the_steps_own_tab_before_the_agent_looks(self):
        """The owner, 2026-11-15: sites are tabs of one browser, and while a step was his he could show another tab - the agent, told to
        look at the page, worked whichever tab he left showing. The tab the step was handed over on is kept with it, and his I'm done
        switches the browser back to it before the agent is told."""
        order = []
        with mock.patch.object(browserview, 'active_tab', return_value='5E59148433CDB7E3310EE4A0CD72F41B'): rid = self.turn()
        self.sess.send_prompt = lambda text, as_owner=True, **k: order.append(('told', text[:20]))
        with mock.patch.object(browserview, 'switch_tab', side_effect=lambda sid, tab: order.append(('tab', sid, tab)) or True):
            ws.answer(self.s, self.tid, rid, '', press=True)
            end = time.time() + 5
            while len(order) < 2 and time.time() < end: time.sleep(.01)
        self.assertEqual(order[0], ('tab', 'run1', '5E59148433CDB7E3310EE4A0CD72F41B'))
        self.assertEqual(order[1][0], 'told')
        self.assertTrue(browserview.TAB_REF.fullmatch('5E59148433CDB7E3310EE4A0CD72F41B'))
        self.assertIsNone(browserview.TAB_REF.fullmatch('t1 & del x'))

    def test_from_his_done_until_the_agent_is_told_the_task_is_at_work(self):
        """Recorded on the real CLI (the browser audit, 2026-11-15): he passed the check and pressed I'm done; the step closed, and until the
        told agent's turn had begun the task read as nothing at work, the page still drawn beside a chat that said nothing was happening.
        The telling is an input on its way to the agent: at work from the press until it has handed on."""
        import threading
        go, begun = threading.Event(), threading.Event()
        def told(text, as_owner=True, **k): begun.set(); go.wait(5); self.told.append((text, as_owner))
        self.sess.send_prompt = told
        rid = self.turn()
        self.assertFalse(general.starting(self.tid))
        self.assertTrue(ws.answer(self.s, self.tid, rid, '', press=True)['delivered'])
        self.assertTrue(general.starting(self.tid), 'at work from the press, before the agent has been told')
        self.assertTrue(begun.wait(5)); go.set(); self.heard()
        end = time.time() + 5
        while general.starting(self.tid) and time.time() < end: time.sleep(.01)
        self.assertFalse(general.starting(self.tid), 'and no longer once it has handed on')

    def test_a_page_that_moved_on_without_his_press_is_never_said_as_his(self):
        # walk 7, 2026-11-23: the page turned into a browser error and the chat read "You did the step on" it - he had pressed nothing
        rid = self.turn()
        self.assertTrue(bg.pressed(self.s, self.tid, rid, {'href': PAY + '/next', 'title': 'Next'}))
        self.assertIn("moved on without their I'm done", self.heard()[0][0])
        self.assertEqual(self.lines(), [], 'only his I\'m done is his')
        self.assertEqual(self.said(), [])
        self.assertNotIn(rid, self.open())

    def test_a_page_the_agent_moved_on_is_never_said_as_his(self):
        # the owner's rule, tell the truth (2026-11-19): the agent opened another page while a human check waited on him, and the chat read
        # "You did the step on nowsecure.nl - the agent goes on" - he had done nothing
        rid = self.turn()
        browserview._BEGAN['run1'] = time.time() + 1                  # the agent's own command, after the hand-over
        self.addCleanup(browserview._BEGAN.pop, 'run1', None)
        self.assertTrue(bg.agent_moved('run1', rid))
        self.assertTrue(bg.left_by_agent(self.s, self.tid, rid))
        self.assertEqual(self.lines(), [], 'no press of his')
        self.assertEqual(self.said(), [])
        self.assertNotIn(rid, self.open())
        notes = [c['Body'] for c in self.s.list_comments(self.tid, internal=True)]
        self.assertTrue(any(n.startswith(bg.NOT_NEEDED_ANY_MORE) for n in notes)) and self.assertFalse(any('You did the step' in n for n in notes))
        # ...its own move is no new input (walk 7, 2026-11-23: an agent at rest was woken four times after its turn, one more paragraph each):
        # at rest it begins no turn; at work it goes into that turn
        self.assertEqual(self.told, [], 'an agent at rest is never woken by what its own work did')
        steered = []; self.sess.steer = lambda said=None: steered.append(said) or True
        rid = self.turn(); self.assertTrue(bg.left_by_agent(self.s, self.tid, rid))
        self.assertEqual(self.told, []); self.assertIn('they did nothing there', steered[0])

    def test_a_step_that_was_not_done_draws_no_press(self):
        rid = self.turn()
        self.assertTrue(bg.not_pressed(self.s, self.tid, rid, 'the browser was closed before it was done'))
        self.assertIn('NOT done', self.heard()[0][0]); self.assertEqual(self.lines(), [])

    def test_a_terminal_agent_is_told_the_same_way(self):
        # ...by the one road into the agent (general.to_agent): a terminal's is the waiting room, Taskuary's note typed in at its stop -
        # never keys over a turn at work
        pane = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, cli='claude')
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': pane}, clear=True), mock.patch('taskuary.waitroom.deliver', return_value={}):
            rid = self.turn()
            self.assertTrue(ws.answer(self.s, self.tid, rid, '', press=True)['delivered'])
        [n] = self.s.waiting_notes(self.tid)
        self.assertIn("The owner pressed I'm done", n['Note']); self.assertEqual(n['CreatedBy'], 'router', "Taskuary's, never the owner's line")

    def test_a_resting_agent_is_started_on_it(self):
        rid, woke = self.turn(), []
        with mock.patch.dict('taskuary.terminal.SESSIONS', {}, clear=True), mock.patch.object(general, 'to_agent', lambda s, t, w, *a: woke.append(w) or 'woke'):
            self.assertTrue(ws.answer(self.s, self.tid, rid, '', press=True)['delivered'])
        self.assertIn('open it again', woke[0]); self.assertEqual(self.open(), [])

    def test_a_step_whose_page_closed_says_so_and_its_press_brings_it_back(self):
        # the owner, 2026-11-10 ("i cant see the screen"): a step handed over on portal.vendor.example, then the session gone (a restart, a
        # stop) and its browser with it. The card still read "on the page" with Done over no page, and Done told the agent he had finished.
        # It says the page closed, and its one press has the agent open it again and hand the step back
        from taskuary import taskstate
        rid, woke = self.turn(), []
        bg.HANDS.clear()
        with mock.patch.dict('taskuary.terminal.SESSIONS', {}, clear=True), mock.patch.object(browserview, 'state', return_value={'open': False}),                 mock.patch.object(general, 'to_agent', lambda s, t, w, *a: woke.append(w) or 'woke'):
            ask = bg.shown_ask({**taskstate.open_question(self.s, self.tid), 'resting': True})
            self.assertIn('has closed', ask['text']); self.assertNotIn('on the page. I', ask['text'])
            self.assertEqual(ask['choices'], ['Try again']); self.assertEqual(ask['request_id'], rid)
            self.assertTrue(ws.answer(self.s, self.tid, rid, '', press=True)['delivered'])
        self.assertIn('open it again', woke[0]); self.assertNotIn('they say they finished', woke[0])
        self.assertEqual(self.open(), []); self.assertEqual(self.lines(), [], 'nothing was pressed on the page')
        self.assertEqual(bg.shown_ask({'request_id': rid, 'sid': 'run1', 'text': 'x'})['text'], 'x')   # live, its page up: as it was

    def test_another_run_on_the_task_is_never_handed_the_press(self):
        rid = self.turn()
        other = SimpleNamespace(sid='run2', alive=True, task_id=self.tid, send_prompt=lambda *a, **k: self.told.append(a))
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run2': other}, clear=True):
            self.assertEqual(ws.answer(self.s, self.tid, rid, '', press=True)['state'], 'stale')
        self.assertEqual(self.told, []); self.assertEqual(self.lines(), [])

    def test_words_are_still_needed_where_nothing_was_pressed(self):
        rid = self.turn()
        with self.assertRaises(ValueError): ws.answer(self.s, self.tid, rid, '')
        from taskuary import server
        body = server.WorkerAnswerBody(request_id=rid, press=True)
        self.assertEqual((body.text, body.press), ('', True)); self.assertFalse(server.WorkerAnswerBody(request_id=rid, text='ok').press)

    def test_a_row_filed_before_this_reads_in_plain_words_too(self):
        self.assertEqual(general.PRESSES['browser_act_pressed']({'site': SITE}), f'did the step on {SITE}')
        self.assertEqual(general.PRESSES['browser_act_pressed']({}), 'did the step on the page')
        self.assertIn('browser_act_not_pressed', general.QUIET)

    def test_a_step_only_he_can_do_is_one_card_raised_mid_turn_and_his_im_done_wakes_the_agent_once(self):
        """Walk 7, 2026-11-23, and the owner: "Anything for sign in etc should be handed to users with a card ... I need the agent to do its
        job." Ten prompt places told the agent to END ITS TURN with a marker, and three robot checks stood at once with one shown. One call
        mid-turn: a card for him, the turn goes on (nobody is woken), a second is refused while the first waits, and his I'm done wakes it once."""
        from taskuary import agenttools, signin
        out = json.loads(agenttools.call(self.s, self.tid, 'hand_over', {'what': 'tick the "I\'m not a robot" box'}, {}))
        self.assertTrue(out['ok'] and 'go on with the rest' in out['says'].lower(), out)
        rid = bv_open = self.open()
        self.assertEqual(len(rid), 1); self.assertEqual(self.told, [], 'raised mid-turn: the agent is not woken, it goes on')
        again = json.loads(agenttools.call(self.s, self.tid, 'hand_over', {'what': 'enter the card number'}, {}))
        self.assertFalse(again['ok']); self.assertIn('one at a time', again['why']); self.assertEqual(self.open(), bv_open)
        ws.answer(self.s, self.tid, rid[0], '', press=True)
        self.assertEqual(len(self.heard()), 1); self.assertIn("I'm done", self.told[0][0])
        # ...a sign-in Taskuary can do itself is done with no card; one it cannot is his card
        with mock.patch.object(signin, 'saved', return_value={'Secret': 'x'}), mock.patch.object(signin, '_auto'), \
                mock.patch.object(signin, 'shows_signin', return_value=True):
            got = browserview.hand_over(self.s, self.tid, 'sign in', 'vendor.example', 'run1', watch=None)
        self.assertTrue(got['ok'] and got.get('auto')); self.assertEqual(self.open(), [], 'the saved sign-in goes in: nothing asked of him')
        with mock.patch.object(signin, 'saved', return_value=None), mock.patch.object(signin, 'shows_signin', return_value=True):
            got = browserview.hand_over(self.s, self.tid, 'sign in', 'vendor.example', 'run1', watch=None)
        self.assertTrue(got['ok'] and not got.get('auto')); self.assertEqual([ws.ask_of(r)['ask'] for r in self.open()], ['signin'])

    def test_a_saved_sign_in_typed_mid_turn_never_takes_back_the_turn_s_own_answer(self):
        """Walk 10 (2026-11-23): the agent called hand_over mid-turn, a saved sign-in was typed, and the road written for a turn that ENDED on
        a sign-in marker took back "the next answer" as a step - the turn's closing words (what it did, why it stopped) never reached the chat.
        Mid-turn the answer is the turn's own; a marker's turn ended on the hand-over, and only that answer is a step."""
        import threading
        from taskuary import conversation, signin, vault
        self.addCleanup(signin._TRIED.clear)
        for ended, back in ((False, False), (True, True)):
            signin._TRIED.clear()
            with mock.patch.object(signin, 'saved', return_value={'User': 'u', 'Secret': 's'}), mock.patch.object(vault, 'unseal', return_value='pw'), \
                    mock.patch.object(signin, 'shows_signin', return_value=True), mock.patch.object(signin, 'asks_code', return_value=False), \
                    mock.patch.object(signin, 'type_in', return_value={}), mock.patch.object(signin, '_continue'), \
                    mock.patch.object(signin, '_chat', return_value=True), mock.patch.object(signin, 'typing'), mock.patch.object(signin, '_used'), \
                    mock.patch.object(signin, '_audit'), mock.patch.object(conversation, 'take_back') as took:
                got = browserview.hand_over(self.s, self.tid, 'sign in', 'vendor.example', 'run1', watch=None, ended=ended)
                for th in [t for t in threading.enumerate() if t.name == f'signin-{self.tid}']: th.join(5)
            self.assertTrue(got.get('auto'), got)
            self.assertEqual(took.called, back, f'ended={ended}')

    def test_a_step_named_with_its_site_on_a_page_that_asks_no_sign_in_is_his_turn_and_says_so(self):
        """Walk 10 (2026-11-23): "Enter your date of birth" on a sign-up page, handed over with its site, took the saved sign-in's road and
        answered "Taskuary is signing in ... with what it keeps" - while the step went to him as a card ten seconds later."""
        from taskuary import signin
        typed = []
        with mock.patch.object(signin, 'saved', return_value={'Secret': 'x'}), mock.patch.object(signin, '_auto', side_effect=lambda *a: typed.append(a)), \
                mock.patch.object(signin, 'shows_signin', return_value=False), mock.patch.object(signin, 'on_signin_page', return_value=False):
            got = browserview.hand_over(self.s, self.tid, 'Enter your date of birth, then press Next', 'signup.vendor.example', 'run1', watch=None)
        self.assertTrue(got['ok'] and not got.get('auto'), got)
        self.assertIn('Handed to the owner', got['says']); self.assertNotIn('signing in', got['says'])
        self.assertEqual([ws.ask_of(r)['ask'] for r in self.open()], ['turn']); self.assertEqual(typed, [], 'no saved sign-in typed into it')

    def test_a_post_page_or_an_unreadable_one_handed_over_with_its_site_is_his_turn_and_nothing_is_typed_or_sent(self):
        """Walk 11 (2026-11-23): the agent handed over the last step on a news site's submit page - title, address and text boxes, a user-name
        box elsewhere, no password - and the app answered "Taskuary is signing in", typed the saved user name into the TITLE and sent the post.
        A page is a sign-in only where it shows a password or a code box; one that cannot be read is never one. Both are his card."""
        from taskuary import signin
        class Page:
            def __init__(self, f): self.f = f
            def fields(self, want=''): return self.f
            def close(self): pass
        class Gone:
            def fields(self, want=''): raise signin.SignInError('the page did not let Taskuary look at it')
            def close(self): pass
        post = {'top': True, 'href': 'https://news.example/submit', 'user': True, 'password': False, 'loose': 3}
        for page in (Page(post), Gone()):
            for r in self.open(): ws.answer(self.s, self.tid, r, '', press=True)
            typed = []
            with mock.patch.object(signin, 'saved', return_value={'User': 'u', 'Secret': 's'}), mock.patch.object(signin, 'connect', return_value=page), \
                    mock.patch.object(signin, '_auto', side_effect=lambda *a: typed.append(a)), mock.patch.object(signin, 'type_in', side_effect=lambda *a, **k: typed.append(a)), \
                    mock.patch.object(bg, 'page_error', return_value=''):
                got = browserview.hand_over(self.s, self.tid, 'Press submit to post the story', 'news.example', 'run1', watch=None)
            self.assertTrue(got['ok'] and not got.get('auto'), got); self.assertNotIn('signing in', got['says'].lower())
            self.assertEqual([ws.ask_of(r)['ask'] for r in self.open()], ['turn']); self.assertEqual(typed, [], 'no saved sign-in typed or sent')

    def test_a_hand_over_is_the_page_of_the_tab_it_names_and_an_error_page_is_never_his(self):
        """Walk 9 (CLI 8, 4): three sites in three tabs - "Sign in to Reddit" was handed over as "Your turn in the browser on linkedin.com", the
        tab in front; and LinkedIn's own error page was handed to him as a "security check". The tab of the site named comes to the front first,
        by each tab's own address; an error page goes back to the agent as the error it is, with nothing raised for him."""
        tabs = [{'id': 'AAA1', 'type': 'page', 'url': 'https://www.linkedin.example/feed'}, {'id': 'BBB2', 'type': 'page', 'url': 'https://www.reddit.example/login'}]
        switched = []
        with mock.patch.object(browserview, 'pages', return_value=tabs), mock.patch.object(browserview, 'active_tab', return_value='AAA1'), \
                mock.patch.object(browserview, 'switch_tab', side_effect=lambda sid, t: switched.append(t) or True), \
                mock.patch.object(bg, 'page_error', return_value=''), mock.patch('taskuary.signin.shows_signin', return_value=True), \
                mock.patch('taskuary.signin.needs') as needs:
            browserview.hand_over(self.s, self.tid, 'Sign in to Reddit so I can post the tip', 'reddit.example', 'run1', watch=None)
        self.assertEqual(switched, ['BBB2']); self.assertTrue(needs.called)
        bad = 'TASKUARY: https://www.linkedin.example/checkpoint answered with an error (HTTP 404). Decide the next step: ...'
        with mock.patch.object(browserview, 'pages', return_value=tabs), mock.patch.object(browserview, 'active_tab', return_value='AAA1'), \
                mock.patch.object(bg, 'page_error', return_value=bad):
            got = browserview.hand_over(self.s, self.tid, 'complete the security check', 'linkedin.example', 'run1', watch=None)
        self.assertFalse(got['ok']); self.assertIn('HTTP 404', got['why']); self.assertEqual(self.open(), [], 'nothing was handed to him')


if __name__ == '__main__': unittest.main()


class TheHandedTabIsHis(unittest.TestCase):
    """WALK 9 (2026-11-23): the agent handed him a robot check on one tab, he approved another card of the task, and that press's result was
    bound as the ANSWER to the hand-over - it closed, the task idled out, the browser went with it, and the agent's last words still promised
    the page. A tab handed to him is his (browsergate.owner_tabs) until his I'm done: Taskuary's words go in as the next turn, the gate never
    moves or closes that tab, and a tab that closes anyway says so on his card with a way on."""
    setUp = DoneIsAPress.setUp
    turn = DoneIsAPress.turn
    open = DoneIsAPress.open

    def test_a_press_elsewhere_reaches_the_agent_and_never_closes_his_step(self):
        rid = self.turn()
        self.sess.waiting = lambda: True                                            # the chat at rest after the turn that handed it over
        with mock.patch.object(general, '_next_turn') as nt:
            self.assertEqual(general.to_agent(self.s, self.tid, 'The owner approved it and Taskuary ran the click.', frm='taskuary'), 'told')
        self.assertTrue(nt.called)
        self.assertEqual(self.open(), [rid], 'the robot check is still his')
        self.assertTrue(general.page_needs_owner(self.s, self.tid), 'and the session is not idled out from under it')
        from taskuary import waitroom
        with mock.patch.object(waitroom, 'state', return_value=('asking', self.sess)), \
             mock.patch.object(waitroom, 'to_general', return_value=False) as tg, mock.patch.object(general, 'GeneralSession', SimpleNamespace):
            waitroom.add(self.s, self.tid, 'Your landing went in.', 'router'); waitroom._deliver(self.s, self.tid)
        self.assertTrue(tg.called); self.assertEqual(self.open(), [rid])

    def test_the_gate_never_moves_or_closes_his_tab_and_a_new_tab_runs(self):
        with mock.patch.object(browserview, 'active_tab', return_value='T1'): self.turn()
        with mock.patch.object(browserview, 'active_tab', return_value='T1'):
            for cmd in ('agent-browser open https://futuretools.example/news', 'agent-browser reload', 'agent-browser tab close', 'agent-browser close'):
                said = bg.check(self.s, self.tid, 'run1', cmd)['hookSpecificOutput']['permissionDecisionReason']
                self.assertIn("the owner's", said, cmd)
            self.assertEqual(bg.check(self.s, self.tid, 'run1', 'agent-browser tab new https://futuretools.example/news'), {})
        with mock.patch.object(browserview, 'active_tab', return_value='T2'):
            self.assertEqual(bg.check(self.s, self.tid, 'run1', 'agent-browser open https://futuretools.example/news'), {})
            self.assertIn('close', bg.check(self.s, self.tid, 'run1', 'agent-browser close')['hookSpecificOutput']['permissionDecisionReason'])

    def test_a_tab_that_closes_anyway_says_so_on_his_card_and_the_agent_is_told(self):
        with mock.patch.object(browserview, 'active_tab', return_value='T1'): rid = self.turn()
        req = ws.asking_of(self.s, self.sess)
        with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T2', 'url': PAY}]), mock.patch.object(bg, '_tell') as told:
            self.assertTrue(bg.shown_ask(req)['gone'])
            self.assertTrue(bg.tab_gone(self.s, self.tid, rid))
        self.assertIn('closed before they did the step', told.call_args[0][2])
        with mock.patch.object(browserview, 'pages', return_value=[{'id': 'T1', 'url': PAY}]): self.assertNotIn('gone', bg.shown_ask(req))
