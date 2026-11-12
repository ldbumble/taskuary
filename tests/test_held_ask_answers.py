"""A Claude question held for the owner, and an answer to a chooser, as the owner actually sends them (B11, B12).

B11: while hooks.ask HOLDS an AskUserQuestion, Claude keeps its spinner up - so the waiting room read the screen,
said `working`, and queued the owner's typed answer until the 540 s hold ran out. A held ask is asking, whatever the
screen says: the words go straight to the hook.

B12: after the hold times out Claude draws its own form, and the request keeps source='hook'. One answer was typed as
WORDS + Enter, so Enter submitted whichever option was highlighted (option 1) while the log said "delivered"; a
permission prompt answered "no, don't delete that" got Enter on its default Yes. A pick is the option's NUMBER; words
that name no option are never typed into a chooser.

2026-11-11: ...and never refused either. They were kept with "not_a_choice: coding is waiting on a pick - say one of: ..." and every line
after them piled up behind the chooser. They are the owner's next line: a terminal's chooser is put down with its own Esc and the words
typed as any line; under a held request's buttons they wait as a line does and the request stays lit; over ACP there is no screen to
read a chooser off at all - the agent's own numbered list a turn back was read as one.
"""
import threading, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import hooks, server, terminal as term, waitroom, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CWD = r'C:\code\repo'
ONE = {'questions': [{'question': 'Which branch should I base this on?',
                      'options': [{'label': 'main'}, {'label': 'release/2026-10'}, {'label': 'hotfix'}]}]}
PERMISSION = ['Bash command', '  rm -rf build/', 'Do you want to proceed?',
              '❯ 1. Yes', "  2. Yes, and don't ask again for rm commands in this folder",
              '  3. No, and tell Claude what to do differently (esc)']


def pane(tid, store, working=True, mode='auto'):
    # a stranger's session: the owner's own task is never held, its question is asked in the terminal (hooks.ask)
    t = SimpleNamespace(sid='run1', mode=mode, alive=True, task_id=tid, cwd=CWD, agent='coding', label='coding', argv=['claude'], last=1.0,
                        ext_id='sess-1', resumed_from='', store=store, witness=SimpleNamespace(note=lambda n: None), written=[],
                        n=0, tail=lambda n=3: ['✻ Pondering… (esc to interrupt)'], status_tail=lambda n=6: ['✻ Pondering… (esc to interrupt)'])
    t.write = t.written.append
    t.waiting = lambda: not working              # the spinner: the screen alone says it is working
    return t


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the export', kind='coding')
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear(); ws.HELD.clear()
        self.t = pane(self.tid, self.s); term.SESSIONS['run1'] = self.t

    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions); ws.HELD.clear()

    def hold(self, tool_input=ONE, wait=5.0):
        got = {}
        th = threading.Thread(target=lambda: got.update(out=hooks.ask({'hook_event_name': 'PreToolUse', 'tool_name': 'AskUserQuestion',
                                                                         'session_id': 'sess-1', 'cwd': CWD, 'tool_input': tool_input}, wait=wait)))
        th.start()
        for _ in range(250):
            if ws.HELD or not th.is_alive(): break
            time.sleep(0.02)
        return th, got


class HeldAskIsAsking(Base):
    def test_a_note_typed_while_the_ask_is_held_goes_straight_to_the_hook(self):
        th, got = self.hold()
        self.assertEqual(waitroom.state(self.s, self.tid)[0], 'asking', 'held = asking, whatever the spinner says')
        out = waitroom.add(self.s, self.tid, 'release/2026-10')
        th.join(2)
        self.assertFalse(th.is_alive(), 'the hook let go at once - not after ASK_WAIT')
        self.assertEqual((out['delivered'], out['state']), (1, 'answered'))
        self.assertEqual(got['out']['hookSpecificOutput']['updatedInput']['answers'], {'Which branch should I base this on?': 'release/2026-10'})
        self.assertEqual(self.t.written, [], 'nothing typed into the pane')
        self.assertEqual(self.s.waiting_notes(self.tid), [])

    def test_own_words_are_an_answer_to_a_held_ask_too(self):
        th, got = self.hold()
        waitroom.add(self.s, self.tid, 'base it on the tag v4.2 instead')
        th.join(2)
        self.assertEqual(list(got['out']['hookSpecificOutput']['updatedInput']['answers'].values()), ['base it on the tag v4.2 instead'])

    def test_with_nothing_held_a_working_screen_still_queues(self):
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which branch?', choices=['main', 'dev'], source='hook')
        self.assertEqual(waitroom.state(self.s, self.tid)[0], 'working')


class APickIsItsNumber(Base):
    """The hold timed out: Claude's form is in the pane and the request is still source='hook'."""
    def asked(self):
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which branch should I base this on?',
                  choices=['main', 'release/2026-10', 'hotfix'], source='hook')

    def test_a_chosen_label_is_sent_as_its_digit(self):
        self.asked(); typed = []
        with mock.patch.object(term, 'type_into', side_effect=lambda t, x: typed.append(x)):
            out = ws.answer(self.s, self.tid, 'q1', 'release/2026-10')
        self.assertTrue(out['delivered']); self.assertEqual(typed, ['2'])
        self.assertTrue(any('release/2026-10' in c['Body'] for c in self.s.list_comments(self.tid)), 'the comment keeps what was chosen')

    def test_words_that_name_no_option_put_the_chooser_down_and_go_in_as_his_line(self):
        self.asked(); typed = []
        with mock.patch.object(term, 'type_into', side_effect=lambda t, x: typed.append(x)), mock.patch.object(ws, 'PUT_DOWN', 0):
            out = ws.answer(self.s, self.tid, 'q1', 'use whatever the last release used')
        self.assertEqual((out['delivered'], out['state']), (True, 'delivered'), 'never refused with a state code')
        self.assertEqual((self.t.written, typed), (['\x1b'], ['use whatever the last release used']), 'Esc on the chooser - never Enter - then his words')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [], 'a question he answered in words is closed by that answer')

    def test_the_waiting_room_hands_such_words_over_too(self):
        self.asked(); self.t.waiting = lambda: True; typed = []
        with mock.patch.object(term, 'type_into', side_effect=lambda t, x: typed.append(x)), mock.patch.object(ws, 'PUT_DOWN', 0):
            out = waitroom.add(self.s, self.tid, 'use whatever the last release used')
        self.assertEqual((out['delivered'], out['state'], typed), (1, 'answered', ['use whatever the last release used']))
        self.assertEqual(self.t.written, ['\x1b']); self.assertNotIn('why', out)
        self.assertEqual(self.s.waiting_notes(self.tid), [], 'nothing piles up behind the chooser')

    def test_a_codex_question_with_choices_is_still_answered_in_words(self):
        self.t.argv, self.t.cli = ['codex'], 'codex'; self.asked(); typed = []
        with mock.patch.object(term, 'queue_codex', return_value=False), mock.patch.object(term, 'type_into', side_effect=lambda t, x: typed.append(x)):
            self.assertTrue(ws.answer(self.s, self.tid, 'q1', 'hotfix')['delivered'])
        self.assertEqual(typed, ['hotfix'], 'codex asked in prose: its answer is words')


class APermissionIsAPickToo(Base):
    def asked(self, rid='p1'):
        ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id=rid, text='Bash rm -rf build/', source='hook')

    def answer(self, words, rid='p1'):
        typed = []
        with mock.patch.object(term, 'screen', lambda sid, n=32: {'lines': list(PERMISSION)}), \
             mock.patch.object(term, 'type_into', side_effect=lambda t, x: typed.append(x)):
            return ws.answer(self.s, self.tid, rid, words), typed

    def test_no_in_a_sentence_never_lands_on_the_default_yes(self):
        self.asked()
        with mock.patch.object(ws, 'PUT_DOWN', 0): out, typed = self.answer("no, don't delete that")
        self.assertEqual((out['delivered'], self.t.written, typed), (True, ['\x1b'], ["no, don't delete that"]), 'the prompt is put down, his words are his line')

    def test_over_acp_there_is_no_screen_to_read_a_chooser_off(self):
        """The live shape (2026-11-11): the agent asked "1. short 2. long" in words a turn back, he answered in words, and "yes do it" typed
        under a later approval was refused with those two as the options - the session's transcript read as a pane."""
        self.t.acp, said = True, []
        self.t.say = lambda x, done=None: said.append(x)
        self.t.screen_lines = lambda n=32: ['Which do you want?', '1. A short one-line docstring', '2. A long one covering the arguments']
        self.asked()
        self.assertIsNone(term.screen_question(self.t))
        out = ws.answer(self.s, self.tid, 'p1', 'yes do it')
        self.assertEqual((out['delivered'], said, self.t.written), (True, ['yes do it'], []))

    def test_the_options_own_words_and_numbers_pick(self):
        for i, (words, key) in enumerate((('yes', '1'), ('No', '3'), ('2', '2'), ("Yes, and don't ask again for rm commands in this folder", '2'))):
            self.asked(f'p{i}')
            out, typed = self.answer(words, f'p{i}')
            self.assertEqual((out['delivered'], typed), (True, [key]), words)

    def test_options_it_cannot_read_leave_the_old_road(self):
        self.asked(); typed = []
        with mock.patch.object(term, 'type_into', side_effect=lambda t, x: typed.append(x)):
            self.assertTrue(ws.answer(self.s, self.tid, 'p1', 'yes')['delivered'])
        self.assertEqual(typed, ['yes'])


class WordsUnderButtonsAreALine(Base):
    "A held request with buttons (a stranger's permit door, the owner's Allow / Reject): words that name none of them never answer it."
    def held(self):
        g = ws.group_key('permit:x'); rid = ws.question_id(g, 1)
        ws.hold(self.tid, 'run1', g, [rid])
        ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id=rid, text='The agent wants to use Bash: git push', choices=['Allow', 'Deny'], source='hook')
        return g, rid

    def test_words_leave_the_hold_waiting_and_are_handed_back_as_a_line(self):
        g, rid = self.held()
        self.assertEqual(ws.answer(self.s, self.tid, rid, 'what does it push?')['state'], 'line')
        self.assertIn(g, ws.HELD, 'the hold still waits on its buttons'); self.assertEqual(len(ws.status(self.s, self.tid)['requests']), 1)
        out = waitroom.add(self.s, self.tid, 'what does it push?')
        self.assertEqual((out['delivered'], out['state']), (0, 'held_ask')); self.assertNotIn('why', out)
        self.assertEqual(len(self.s.waiting_notes(self.tid)), 1, 'kept as his line, waiting for the agent')

    def test_over_acp_a_line_typed_while_a_step_waits_on_his_allow_keeps_its_place_and_the_step_stays_lit(self):
        """The recorded hold, 2026-11-11: a coding agent over ACP waited on Allow once / Reject for a delete, he typed "is that the only file
        it removes?", and the line was written down as the answer and sent at the stopped turn - dots under it while nothing ran, then
        handed over a second time when the turn moved (told twice, drawn twice). It waits as a line does; the request stays open."""
        from taskuary import permissions
        g, rid = self.held()
        sent = []; self.t.prompt = lambda *a, **k: sent.append(a); self.t.steerable = lambda: True
        with mock.patch.object(term, 'is_acp', return_value=True), mock.patch.object(permissions, 'pending', return_value=[{'id': 'p1'}]):
            out = waitroom.add(self.s, self.tid, 'is that the only file it removes?')
        self.assertEqual((out['delivered'], out['state']), (0, 'held_ask'))
        self.assertEqual(sent, []); self.assertIn(g, ws.HELD); self.assertEqual(len(ws.status(self.s, self.tid)['requests']), 1)
        self.assertEqual(len(self.s.waiting_notes(self.tid)), 1)

    def test_a_button_named_in_words_still_presses_it(self):
        g, rid = self.held()
        self.assertTrue(ws.answer(self.s, self.tid, rid, 'allow')['delivered'])
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_the_answer_door_sends_such_words_down_the_line_road(self):
        from taskuary import general
        g, rid = self.held(); took = []
        with mock.patch.object(server, 'store', self.s), mock.patch.object(general, 'take_line', side_effect=lambda st, tid, text, *a, **k: took.append((tid, text))):
            out = server.worker_answer(self.tid, server.WorkerAnswerBody(request_id=rid, text='what does it push?'))
        self.assertEqual((out, took), ({'delivered': True, 'state': 'line'}, [(self.tid, 'what does it push?')]))


class NeverDefaultsToYes(Base):
    def test_an_answer_with_no_words_is_refused_not_sent_as_yes(self):
        self.t.send_prompt = lambda x: self.t.written.append(x)
        ws.record(self.s, self.tid, 'run1', 'approval_needed', text='Run the migration?', source='hook')
        with mock.patch.object(server, 'store', self.s), self.assertRaises(Exception):
            server._run_operation({'kind': 'agent.answer', 'target': self.tid, 'params': {}}, None)
        self.assertEqual(self.t.written, [])


if __name__ == '__main__': unittest.main()
