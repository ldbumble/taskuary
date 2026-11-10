"""THE VIEW'S DONE IS A PRESS (the spine audit, 2026-11-09). A step handed to the owner on the agent's page - a captcha, the last button of
a checkout - has a Done on the view. It went to a chat as words typed in the owner's name: a bubble they never wrote, a turn of its own, and
known to the server only by matching those words. It is their press now, by the road every other press takes: the hand-over closes, the
agent is told by Taskuary that they SAY it is done (nothing saw the page move, so it looks first), and the page reads one quiet line.
And the press the page itself saw read "You browser act pressed." under Taskuary's own line saying the same. Invented people."""
import time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import browsergate as bg, browserview, general, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

PAY, SITE, BTN = 'https://pay.vendor.example/checkout', 'pay.vendor.example', '"Pay $42.00"'


class DoneIsAPress(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Pay the course fee')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, send_prompt=lambda text, as_owner=True, **k: self.told.append((text, as_owner)))
        live = mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': self.sess}, clear=True); live.start()
        self.addCleanup(live.stop); self.addCleanup(bg.HANDS.clear)

    def turn(self):
        "The agent handed the page over for a step only a person can do."
        with mock.patch.object(browserview, 'state', return_value={'open': True, 'url': PAY}):
            return browserview.your_turn(self.s, self.tid, 'run1', 'tick the "I\'m not a robot" box', watch=None)
    def press(self):
        "The agent's last button was held and handed to the owner to press on the page."
        rid = bg.PRESS + 'abc'
        bg.HANDS[rid] = {'tid': self.tid, 'sid': 'run1', 'btn': BTN, 'name': 'Pay $42.00', 'site': SITE}
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id=rid, text=bg.PRESS_LINE.format(btn=BTN), choices=[browserview.TURN_DONE], source='api')
        return rid
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
        self.assertIn('The owner pressed Done', words); self.assertIn("tick the \"I'm not a robot\" box", words)
        self.assertIn('did not see the page move', words); self.assertIn('look at it as it is now', words)
        self.assertEqual(self.said(), [], 'no bubble, and no line by Taskuary either')
        self.assertEqual(self.lines(), [f'You pressed Done: the step on {SITE} is finished.'])
        self.assertEqual(self.open(), []); self.assertEqual(bg.HANDS, {})
        again = ws.answer(self.s, self.tid, rid, '', press=True)                  # a second press, or the watch got there first
        self.assertEqual((again['delivered'], again['state']), (False, 'resolved')); self.assertEqual(len(self.told), 1)

    def test_done_on_a_button_handed_over_names_the_button(self):
        rid = self.press()
        self.assertTrue(ws.answer(self.s, self.tid, rid, '', press=True)['delivered'])
        self.assertIn(f'pressing {BTN}', self.heard()[0][0])
        self.assertEqual(self.lines(), [f'You pressed Done: {BTN} on {SITE} is pressed.'])

    def test_the_press_the_page_saw_is_one_line_in_plain_words(self):
        rid = self.press()
        self.assertTrue(bg.pressed(self.s, self.tid, rid, {'href': PAY + '/thanks', 'title': 'Thank you'}))
        self.assertIn('pressed "Pay $42.00" on the page themselves', self.heard()[0][0])
        self.assertEqual(self.lines(), [f'You pressed {BTN} on {SITE}.'])
        self.assertEqual(self.said(), [], 'said once: no second line by Taskuary above it')
        rid = self.turn()
        self.assertTrue(bg.pressed(self.s, self.tid, rid, {'href': PAY + '/next', 'title': 'Next'}))
        self.assertEqual(self.lines()[-1], f'You did the step on {SITE}.')
        self.assertFalse(any('browser act' in x for x in self.lines()))

    def test_a_step_that_was_not_done_draws_no_press(self):
        rid = self.press()
        self.assertTrue(bg.not_pressed(self.s, self.tid, rid, 'the browser was closed before it was pressed'))
        self.assertIn('NOT done', self.heard()[0][0]); self.assertEqual(self.lines(), [])
        self.press(); bg.owner_said(self.s, self.tid, 'run1', "don't - wrong card")
        self.assertEqual(self.lines(), [])

    def test_a_terminal_agent_is_told_the_same_way(self):
        typed, pane = [], SimpleNamespace(sid='run1', alive=True, task_id=self.tid, cli='claude')
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': pane}, clear=True), \
                mock.patch('taskuary.terminal.type_into', lambda s, t, **k: typed.append((t, k))):
            rid = self.turn()
            self.assertTrue(ws.answer(self.s, self.tid, rid, '', press=True)['delivered'])
            end = time.time() + 5
            while not typed and time.time() < end: time.sleep(.01)
        self.assertIn('The owner pressed Done', typed[0][0]); self.assertEqual(typed[0][1], {'brief': True})

    def test_a_resting_agent_is_started_on_it(self):
        rid, woke = self.turn(), []
        with mock.patch.dict('taskuary.terminal.SESSIONS', {}, clear=True), mock.patch.object(general, 'tell', lambda s, t, w, *a: woke.append(w) or 'woke'):
            self.assertTrue(ws.answer(self.s, self.tid, rid, '', press=True)['delivered'])
        self.assertIn('The owner pressed Done', woke[0]); self.assertEqual(self.open(), [])

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


if __name__ == '__main__': unittest.main()
