"""An agent's SEVERAL questions, answered together (the owner, 2026-09-28: "does coding agent propose 3 questions ...
render correctly to assistant where you can answer and that will be sent back to coding agent correctly? never
tested that but i don't believe it would work").

It did not: the card showed only the newest question, and the pick was typed as words into Claude's form, which
stands on question 1 and takes a digit. Measured on Claude Code 2.1.283 (memory: askuserquestion-protocol): a
PreToolUse hook that returns updatedInput.answers answers AskUserQuestion with no form drawn - so an ask from a pane
of ours is HELD while the owner answers in the Assistant or on the phone. These pin: one group per ask, the hold and
its answers, the release, the form's own keys when the form is up, a regular agent's several markers, and the
install of the hook.
"""
import json, os, tempfile, threading, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import guard, hooks, selfclose, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CWD = r'C:\code\repo'
QS = {'questions': [{'question': 'Which branch?', 'options': [{'label': 'main'}, {'label': 'release'}]},
                    {'question': 'Which color?', 'options': [{'label': 'red'}, {'label': 'blue'}]},
                    {'question': 'Which size?', 'options': [{'label': 'small'}, {'label': 'large'}]}]}


def pane(tid, store, ext_id='sess-1', argv=('claude',)):
    return SimpleNamespace(sid='run1', alive=True, task_id=tid, cwd=CWD, agent='coder', label='coder', argv=list(argv), last=1.0,
                           ext_id=ext_id, resumed_from='', store=store, witness=SimpleNamespace(note=lambda n: None), written=[],
                           write=None)


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the export', kind='coding')
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
        self.t = pane(self.tid, self.s); self.t.write = self.t.written.append
        term.SESSIONS['run1'] = self.t
        ws.HELD.clear()

    def tearDown(self):
        term.SESSIONS.clear(); term.SESSIONS.update(self._sessions); ws.HELD.clear()

    def ask_in_background(self, sid='sess-1', wait=5.0):
        got = {}
        th = threading.Thread(target=lambda: got.update(out=hooks.ask({'hook_event_name': 'PreToolUse', 'tool_name': 'AskUserQuestion',
                                                                         'session_id': sid, 'cwd': CWD, 'tool_input': QS}, wait=wait)))
        th.start()
        for _ in range(100):
            if ws.HELD or not th.is_alive(): break
            time.sleep(0.02)
        return th, got


class HeldAskTests(Base):
    def test_the_three_questions_are_one_group_on_the_card_in_order(self):
        th, _ = self.ask_in_background()
        qs = ws.question_group(self.s, self.t)
        self.assertEqual([q['text'] for q in qs], ['Which branch?', 'Which color?', 'Which size?'])
        self.assertEqual(qs[1]['choices'], ['red', 'blue'])
        ws.release(self.tid); th.join(2)

    def test_answers_from_the_assistant_become_the_tools_input(self):
        th, got = self.ask_in_background()
        qs = ws.question_group(self.s, self.t)
        out = ws.answer_group(self.s, self.tid, {qs[0]['request_id']: 'main', qs[1]['request_id']: 'green', qs[2]['request_id']: 'large'})
        th.join(2)
        self.assertEqual((out['delivered'], out['path']), (True, 'hook'))
        spec = got['out']['hookSpecificOutput']
        self.assertEqual((spec['hookEventName'], spec['permissionDecision']), ('PreToolUse', 'allow'))
        self.assertEqual(spec['updatedInput']['answers'], {'Which branch?': 'main', 'Which color?': 'green', 'Which size?': 'large'})
        self.assertEqual(spec['updatedInput']['questions'], QS['questions'], 'the rest of the tool input is untouched')
        self.assertEqual(ws.question_group(self.s, self.t), [], 'answered - nothing left open')
        self.assertEqual(self.t.written, [], 'nothing was typed into the pane')

    def test_one_answer_at_a_time_waits_for_the_last(self):
        th, got = self.ask_in_background()
        qs = ws.question_group(self.s, self.t)
        self.assertEqual(ws.answer(self.s, self.tid, qs[0]['request_id'], 'main')['state'], 'noted')
        self.assertTrue(th.is_alive(), 'still held - two questions have no answer')
        ws.answer(self.s, self.tid, qs[1]['request_id'], 'red'); ws.answer(self.s, self.tid, qs[2]['request_id'], 'small')
        th.join(2)
        self.assertEqual(got['out']['hookSpecificOutput']['updatedInput']['answers']['Which size?'], 'small')

    def test_answering_in_the_terminal_instead_lets_the_form_appear(self):
        th, got = self.ask_in_background()
        self.assertTrue(ws.release(self.tid))
        th.join(2)
        self.assertEqual(got['out'], {}, 'nothing returned: Claude draws its own form')

    def test_out_of_time_lets_the_form_appear_too(self):
        th, got = self.ask_in_background(wait=0.1)
        th.join(2)
        self.assertEqual(got['out'], {})

    def test_another_claude_in_the_folder_is_never_held(self):
        """The owner's own CLI beside the coder: its question is its own, drawn in its own terminal at once."""
        t0 = time.time()
        out = hooks.ask({'tool_name': 'AskUserQuestion', 'session_id': 'owners-own', 'cwd': CWD, 'tool_input': QS}, wait=5)
        self.assertEqual(out, {}); self.assertLess(time.time() - t0, 1)
        self.assertEqual(ws.HELD, {})

    def test_the_three_hooks_of_one_ask_name_the_same_questions(self):
        th, _ = self.ask_in_background()
        # the permission prompt of the same tool call arrives too: the same requests, not three more
        hooks.receive({'hook_event_name': 'PermissionRequest', 'tool_name': 'AskUserQuestion', 'session_id': 'sess-1', 'cwd': CWD, 'tool_input': QS})
        self.assertEqual(len(ws.question_group(self.s, self.t)), 3)
        ws.release(self.tid); th.join(2)


class FormKeysTests(Base):
    def test_the_form_on_screen_is_answered_by_its_own_keys(self):
        """Measured: Left back to question 1, a digit per option (it moves on), the "Type something." row for your own
        words, then 1 on the review to submit them all."""
        with mock.patch.object(term.threading, 'Thread', lambda target, daemon=True: SimpleNamespace(start=target)), \
             mock.patch.object(term.time, 'sleep', lambda s: None):
            term.answer_form(self.t, [(['main', 'release'], 'release'), (['red', 'blue'], 'green'), (['small', 'large'], 'Large')])
        self.assertEqual(self.t.written, ['\x1b[D'] * 4 + ['2', '3', 'green', '\r', '2', '1'])

    def test_answers_to_a_form_already_up_use_the_keys(self):
        for i, q in enumerate(QS['questions'], 1):
            ws.record(self.s, self.tid, 'run1', 'input_needed', request_id=ws.question_id('abcdef0123', i), text=q['question'],
                      choices=[o['label'] for o in q['options']], source='hook')
        with mock.patch.object(term, 'answer_form') as keys:
            out = ws.answer_group(self.s, self.tid, {ws.question_id('abcdef0123', i): a for i, a in enumerate(['main', 'blue', 'small'], 1)})
        self.assertTrue(out['delivered'])
        self.assertEqual(keys.call_args[0][1], [(['main', 'release'], 'main'), (['red', 'blue'], 'blue'), (['small', 'large'], 'small')])


class ChatAnswerTests(Base):
    def test_one_line_answers_the_numbered_questions(self):
        qs = [{'request_id': 'a'}, {'request_id': 'b'}, {'request_id': 'c'}]
        self.assertEqual(ws.split_answers('1 main, 2 raise the cap; 3: no backfill', qs), {'a': 'main', 'b': 'raise the cap', 'c': 'no backfill'})
        self.assertEqual(ws.split_answers('stream it', qs), {'a': 'stream it', 'b': 'stream it', 'c': 'stream it'})

    def test_the_chats_line_answers_the_whole_held_ask(self):
        th, got = self.ask_in_background()
        out = ws.answer_open(self.s, self.tid, '1 release, 2 blue, 3 small')
        th.join(2)
        self.assertTrue(out['delivered'])
        self.assertEqual(got['out']['hookSpecificOutput']['updatedInput']['answers'], {'Which branch?': 'release', 'Which color?': 'blue', 'Which size?': 'small'})


class RegularAgentTests(unittest.TestCase):
    def test_every_marker_is_a_question(self):
        reply = 'Half done.\n[[TASKUARY-ASK]] Which branch? | main | release\n[[TASKUARY-ASK]] Backfill September? | Yes | No'
        self.assertEqual(selfclose.ask_markers(reply), ('Half done.', [('Which branch?', ['main', 'release']), ('Backfill September?', ['Yes', 'No'])]))

    def test_a_general_agent_hears_its_answers_as_one_message(self):
        s = MemoryStore(); tid = Factory(s).task(title='Research vendors')
        sent = []
        sess = SimpleNamespace(sid='api1', alive=True, task_id=tid, send_prompt=lambda text: sent.append(text))
        saved = dict(term.SESSIONS); term.SESSIONS.clear(); term.SESSIONS['api1'] = sess
        try:
            for i, q in enumerate(['Which vendor?', 'Which quarter?'], 1):
                ws.record(s, tid, 'api1', 'input_needed', request_id=ws.question_id('0123456789', i), text=q, source='api')
            out = ws.answer_group(s, tid, {ws.question_id('0123456789', 1): 'Payworth', ws.question_id('0123456789', 2): 'Q3'})
        finally:
            term.SESSIONS.clear(); term.SESSIONS.update(saved)
        self.assertTrue(out['delivered'])
        self.assertEqual(sent, ['1. Which vendor? - Payworth\n2. Which quarter? - Q3'])


class PhoneTests(unittest.TestCase):
    ITEM = {'kind': 'agent', 'lane': 'blocked', 'asking': True, 'tid': 3, 'ref': 'TQ-0003', 'title': 'Fix the export', 'who': 'coder',
            'agent': 'coder', 'choices': ['main', 'release'],
            'questions': [{'request_id': 'q:1', 'text': 'Which branch?', 'choices': ['main', 'release']},
                          {'request_id': 'q:2', 'text': 'Which color?', 'choices': ['red', 'blue']}]}

    def test_every_question_is_numbered_and_answered_in_one_line(self):
        from taskuary import remote_assistant as ra
        text = ra.turn_text({'say': 'coder asked you two things.', 'item': self.ITEM,
                             'chips': [{'verb': 'answer_agent', 'label': 'Answer it'}, {'verb': 'next', 'label': 'Next'}]})
        self.assertIn('**1. Which branch?** (main / release)', text)
        self.assertIn('**2. Which color?** (red / blue)', text)
        self.assertIn('in one line', text)
        # a poll holds ONE question's answers, and "Answer it" carries no words - neither is offered for several
        self.assertEqual(ra.agent_answers(self.ITEM), [])
        self.assertNotIn('Answer it', text)
        self.assertNotIn('**coder** asked', text, "an agent card's `who` is the agent, never the asker")


class InstallAndGuardTests(unittest.TestCase):
    def test_the_ask_hook_is_installed_for_askuserquestion_only_and_waits(self):
        with tempfile.TemporaryDirectory() as home:
            hooks.install_user('claude', base='http://127.0.0.1:7787', token='t', home=home)
            hooks.install_user('claude', base='http://127.0.0.1:7787', token='t', home=home)     # twice: still one entry
            with open(os.path.join(home, '.claude', 'settings.json'), encoding='utf-8') as f: cfg = json.load(f)['hooks']
            pre = [g for g in cfg['PreToolUse'] if any(hooks.ASK_MARK in h['command'] for h in g['hooks'])]
            self.assertEqual(len(pre), 1)
            self.assertEqual(pre[0]['matcher'], 'AskUserQuestion')
            self.assertEqual(pre[0]['hooks'][0]['timeout'], hooks.ASK_TIMEOUT)
            self.assertNotIn('-o ', pre[0]['hooks'][0]['command'], 'its answer is printed - Claude reads it as the decision')
            self.assertGreater(hooks.ASK_TIMEOUT, hooks.ASK_WAIT)

    def test_an_agent_cannot_answer_its_own_question(self):
        for path in ('/api/tasks/7/worker/answer', '/api/tasks/7/worker/answers', '/api/tasks/7/worker/release'):
            self.assertTrue(guard.denied('POST', path), path)
        self.assertEqual(guard.denied('POST', '/api/hooks/claude/ask'), '')


if __name__ == '__main__':
    unittest.main()
