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


class HowATurnReadsIsSaidOnce(unittest.TestCase):
    """The owner, 2026-10-27: the canvas's, the rail's and the closing instructions rode every turn word for word, and a CLI conversation
    keeps every turn - they are the launch instructions now (TURN_GUIDE). And the rail goes whole once per conversation, then "unchanged"
    while it is: only to a CLI brain, which keeps the conversation; an API brain reads each call alone."""
    def setUp(self):
        self.st = mock.patch.object(terminal, 'live_sessions', return_value=[]); self.st.start()
        self.sp = mock.patch.object(ingest, '_spawn'); self.sp.start()
        self.s, self.dock = world()
        concierge._RAIL_SEEN.clear()

    def tearDown(self): self.sp.stop(); self.st.stop(); concierge._RAIL_SEEN.clear()

    def cli(self):
        llm, seen = scripted()
        llm.session_id, llm.warm = 'sid-1', lambda *a, **k: False             # what a kept CLI conversation looks like (llm.make_cli_llm)
        return llm, seen

    def test_the_instructions_carry_how_a_turn_reads_and_the_turn_does_not(self):
        system = concierge.turn_system(self.s)
        for said in ('Act from it first', 'only to find the one the owner names', 'WHAT THEIR WORDS ARE ABOUT', 'CALL next', 'no words before it'):
            self.assertIn(said, system)
        llm, seen = scripted()
        concierge.say(self.s, 'what is this', key='msg:1', llm=llm)
        for said in ('Act from it first', 'only to find the one', 'WHAT THEIR WORDS ARE ABOUT', 'If a look-up would answer'):
            self.assertNotIn(said, seen[0])
        self.assertTrue(seen[0].rstrip().endswith(f"{concierge.OWNER_SAYS}what is this\nAnswer them, briefly."), seen[0][-200:])

    def test_a_cli_conversation_reads_the_rail_whole_once_then_unchanged(self):
        llm, seen = self.cli()
        for text in ('what is this', 'and this one', 'and again'): concierge.say(self.s, text, key='msg:1', llm=llm)
        self.assertIn('TQ-0001 · ', seen[0]); self.assertNotIn(concierge.RAIL_SAME, seen[0])
        self.assertIn(concierge.RAIL_SAME, seen[1]); self.assertNotIn('\n- TQ-0001 · ', seen[1])
        self.assertIn(concierge.RAIL_SAME, seen[2])

    def test_a_moved_rail_a_new_conversation_or_an_api_brain_get_it_whole(self):
        llm, seen = self.cli()
        concierge.say(self.s, 'what is this', key='msg:1', llm=llm)
        self.s.set_funnel_state('msg:5', 'surfaced', '', 'owner', read=True); funnel.invalidate()     # a row went: the rail moved
        concierge.say(self.s, 'and this one', key='msg:1', llm=llm)
        self.assertNotIn(concierge.RAIL_SAME, seen[1])
        llm.session_id = 'sid-2'                                                                      # New chat: another conversation
        concierge.say(self.s, 'and again', key='msg:1', llm=llm)
        self.assertNotIn(concierge.RAIL_SAME, seen[2])
        api, said = scripted()
        for text in ('one', 'two'): concierge.say(self.s, text, key='msg:1', llm=api)
        self.assertNotIn(concierge.RAIL_SAME, said[1])

    def test_a_long_conversation_reads_it_whole_again(self):
        llm, seen = self.cli()
        for i in range(concierge.RAIL_FULL_EVERY + 2): concierge.say(self.s, f'turn {i}', key='msg:1', llm=llm)
        whole = [i for i, u in enumerate(seen) if concierge.RAIL_SAME not in u]
        self.assertEqual(whole, [0, concierge.RAIL_FULL_EVERY + 1])


class TheTurnBuildsNoPipeItDoesNotNeed(unittest.TestCase):
    """The canvas timing (2026-10-26): every typed turn built the whole pipe twice more for SELECT's few words - the index's selector,
    which names no value, and the turn's values, unchanged since the last turn. Built once while nothing moved, and never for the index."""
    def test_the_values_are_built_once_while_nothing_moved(self):
        from taskuary import toolcatalog
        with mock.patch.object(terminal, 'live_sessions', return_value=[]), mock.patch.object(ingest, '_spawn'):
            s, _ = world()
            with mock.patch.object(funnel, 'build', wraps=funnel.build) as b:
                toolcatalog.block(s)
                self.assertEqual(b.call_count, 0, 'the index names no value')
                a = toolcatalog.select_values(s); self.assertEqual(toolcatalog.select_values(s), a)
                self.assertEqual(b.call_count, 1)
                s.set_funnel_state('msg:5', 'surfaced', '', 'owner', read=True)       # a write: read again
                toolcatalog.select_values(s)
                self.assertEqual(b.call_count, 2)


if __name__ == '__main__': unittest.main()
