"""THE CANVAS, FIRST IN EVERY TYPED TURN (the owner, 2026-10-26: "the context for the assistant should be everything in the canvas, so if task
is open the status of that task should be first ... and then on mark done or read on other tasks the summary should be 'read' into the ai
context ... This will make assistant quicker without having to call tools right away to be able to click buttons").

The table - its stage, ask, lit button, draft and the row's buttons by the id a CALL takes - then what this walk put down, one line each,
bounded; and a button named from it is pressed or lit in the same round, with no look-up first."""
import json, os, tempfile, unittest
from unittest import mock

os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='tq-canvas-'))
from taskuary import concierge, funnel, general, ingest, server, terminal     # noqa: E402
from tests import assistant_walk as aw                                         # noqa: E402


def world():
    s = aw.world()
    return s, general.dock_task(s, 'owner')[0]['TaskId']


def item(s, key): return funnel.next_item(s, key, items=funnel.full_items(s)) or funnel.item_for_key(s, key)


def scripted(*answers):
    seen, left = [], list(answers)
    def llm(system, user, **kw):
        seen.append(user); return left.pop(0) if left else 'Ok.'
    return llm, seen


class TheCanvasBlock(unittest.TestCase):
    def setUp(self):
        self.st = mock.patch.object(terminal, 'live_sessions', return_value=[]); self.st.start()
        self.sp = mock.patch.object(ingest, '_spawn'); self.sp.start()
        self.s, self.dock = world()

    def tearDown(self): self.sp.stop(); self.st.stop()

    def test_the_table_comes_first_with_its_stage_ask_and_buttons_by_id(self):
        it = item(self.s, 'msg:1')
        b = concierge.canvas_block(self.s, it, self.dock)
        lines = b.splitlines()
        self.assertTrue(lines[0].startswith('CANVAS'))
        self.assertTrue(lines[1].startswith(f"ON THE TABLE: {it['ref']} · {it['title']}"))
        self.assertIn('  stage: to_start (to start)', b)
        self.assertIn('  ask: ', b)
        # every button the row draws, by its id and label; a tool's own name where the id is no decision of its own
        for r in concierge.row_buttons(self.s, it): self.assertIn(f'{r["verb"]} "{r["label"]}"', b)
        self.assertIn('defer "Remind me" = task.defer(until)', b)
        self.assertIn('close "Mark done"', b)
        self.assertIn('next "Next"', b)

    def test_a_drafted_reply_is_close_out_with_its_first_line_and_send_first(self):
        it = item(self.s, 'review:2')
        b = concierge.canvas_block(self.s, it, self.dock)
        self.assertIn('stage: close_out (close out)', b)
        self.assertIn('draft waiting for Send: "', b)
        buttons = next(l for l in b.splitlines() if l.startswith('  buttons: '))
        self.assertTrue(buttons.startswith('  buttons: approve '), buttons)

    def test_what_this_walk_put_down_is_said_one_line_each_newest_first(self):
        done, fyis, shown = item(self.s, 'msg:2'), item(self.s, 'msg:5'), item(self.s, 'msg:11')
        rec = lambda it, **kw: concierge.record(self.s, self.dock, 'assistant', 'x', concierge.card_for(it) | kw)
        rec(shown); rec(fyis, pressed='All read, next'); rec(done, pressed='Close with a note', pressed_note='laptop ordered')
        b = concierge.canvas_block(self.s, item(self.s, 'msg:1'), self.dock)
        walk = b.split('EARLIER ON THE CANVAS THIS WALK (newest first):\n')[1].splitlines()
        self.assertEqual(walk[0], f"  {done['ref']} · {done['title']} · closed with a note: laptop ordered")
        self.assertTrue(walk[1].endswith(' · all read'), walk[1])
        self.assertTrue(walk[2].endswith(' · shown') or walk[2].endswith(' · read'), walk[2])
        self.assertLess(b.index('ON THE TABLE'), b.index('EARLIER ON THE CANVAS'), 'the table first')

    def test_the_table_is_not_said_twice_and_the_walk_is_capped(self):
        keys = [i['key'] for i in funnel.pile(self.s)['items']][:20]
        for k in keys: concierge.record(self.s, self.dock, 'assistant', 'x', concierge.card_for(item(self.s, k)) | {'pressed': 'Next'})
        it = item(self.s, keys[0])
        b = concierge.canvas_block(self.s, it, self.dock)
        walk = b.split('EARLIER ON THE CANVAS THIS WALK (newest first):\n')[1].splitlines()
        self.assertLessEqual(len(walk), concierge.CANVAS_ROWS)
        self.assertLessEqual(len(b), concierge.CANVAS_CAP)
        self.assertFalse(any(l.startswith(f"  {concierge.handle_of(it)} ·") for l in walk), 'the table is not in the walk')

    def test_nothing_on_the_table_still_says_the_walk(self):
        concierge.record(self.s, self.dock, 'assistant', 'x', concierge.card_for(item(self.s, 'msg:2')) | {'pressed': 'Mark done'})
        b = concierge.canvas_block(self.s, None, self.dock)
        self.assertIn('ON THE TABLE: nothing', b)
        self.assertIn('· marked done', b)

    def test_the_turn_opens_on_the_canvas(self):
        llm, seen = scripted('Ok.')
        concierge.say(self.s, 'hm', key='msg:1', llm=llm)
        self.assertTrue(seen[0].startswith('CANVAS'))
        self.assertLess(seen[0].index('ON THE TABLE'), seen[0].index('NOW:'))
        # the row's buttons ride once, in the canvas, not again with every tool's description
        self.assertNotIn('ACTIONS FOR THE ITEM ON THE TABLE', seen[0])


class AButtonFromTheCanvasActsInOneRound(unittest.TestCase):
    """The model reads the id off the canvas and CALLs it: one model round, no look-up, the row's own button pressed or lit."""
    def setUp(self):
        self.st = mock.patch.object(terminal, 'live_sessions', return_value=[]); self.st.start()
        self.sp = mock.patch.object(ingest, '_spawn'); self.sp.start()
        self.s, self.dock = world()
        self.sv = mock.patch.object(server, 'store', self.s); self.sv.start()     # the operation's handler reads the app's store

    def tearDown(self): self.sv.stop(); self.sp.stop(); self.st.stop()

    def turn(self, answer, text, key='msg:1'):
        reads = []
        real = concierge._read
        llm, seen = scripted(answer)
        with mock.patch.object(concierge, '_read', lambda st, it, call: (reads.append(call['kind']), real(st, it, call))[1]):
            out = concierge.say(self.s, text, key=key, llm=llm)
        self.assertEqual((len(seen), reads), (1, []), 'one round, no look-up')
        return out

    def test_mark_it_done_is_pressed(self):
        out = self.turn('CALL: {"kind": "close", "params": {}}', 'mark it done')
        self.assertEqual(out['pressed']['verb'], 'close')
        self.assertEqual(self.s.get_task(1)['Status'], 'done')

    def test_remind_me_monday_lights_remind_me(self):
        out = self.turn('CALL: {"kind": "task.defer", "params": {"until": "monday"}}', 'remind me Monday')
        self.assertEqual(out['light']['verb'], 'defer')

    def test_a_button_with_no_tool_of_its_own_is_lit_by_its_id(self):
        out = self.turn('CALL: {"kind": "button.light", "params": {"button": "share_result"}}', 'share this')
        self.assertEqual(out['light']['verb'], 'share_result')


if __name__ == '__main__': unittest.main()
