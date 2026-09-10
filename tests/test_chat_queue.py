"""A question asked while the assistant is answering must be answered, not thrown away.

THREE things can be speaking into one chat session: the chat itself, the xterm composer over
the same conversation, and the waiting room delivering queued notes on its own thread. Whoever
got there first held a lock, and the newcomer was refused - "the assistant is already working" -
which, before a failed run said anything at all, reached the owner as pure silence. Two messages
answered, the third one gone (the wall, 2026-08-31).

A person who asks a second question mid-sentence expects to be answered next. So it queues.
"""
import threading
import time
import unittest
from unittest import mock

from taskuary import general
from taskuary.store import MemoryStore


def _session(s, tid, reply='ok', delay=0.0):
    """A session whose brain takes `delay` seconds to answer."""
    sess = general.GeneralSession(s, tid)
    sess.pick, sess.provider, sess.model = 'cli:coder', 'coder', ''
    def brain(system, user, **kw):
        time.sleep(delay)
        return reply
    return sess, mock.patch.object(general.llm_mod, 'build_llm', return_value=brain)


class TakingTurnsTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')

    def test_a_question_asked_mid_answer_is_answered_next(self):
        sess, patched = _session(self.s, self.tid, 'answered', delay=0.6)
        got = []
        with patched:
            first = threading.Thread(target=lambda: got.append(sess.send_prompt('one')))
            first.start()
            time.sleep(0.15)                       # ...while it is still thinking
            got.append(sess.send_prompt('two'))
            first.join(10)
        self.assertEqual(got, ['answered', 'answered'])          # both, not one and a shrug
        said = [c['Body'] for c in general.chat_rows(self.s, self.tid)]
        self.assertEqual(said.count('one') + said.count('two'), 2)

    def test_the_third_one_lands_too(self):
        """The exact report: two answered, the third silent."""
        sess, patched = _session(self.s, self.tid, 'answered', delay=0.3)
        with patched:
            for text in ('hi', 'you still there', 'the thing we were discussing'):
                self.assertEqual(sess.send_prompt(text), 'answered')
        users = [c['Body'] for c in general.chat_rows(self.s, self.tid) if c['ActorType'] == general.USER_TYPE]
        self.assertEqual(users, ['hi', 'you still there', 'the thing we were discussing'])

    def test_a_browser_that_gives_up_stops_waiting(self):
        """Cancelled while queued: it returns, it does not sit on the thread for four minutes."""
        sess, patched = _session(self.s, self.tid, 'answered', delay=1.5)
        cancel = threading.Event()
        with patched:
            threading.Thread(target=lambda: sess.send_prompt('one'), daemon=True).start()
            time.sleep(0.2)
            cancel.set()
            began = time.time()
            with self.assertRaises(RuntimeError):
                sess.send_prompt('two', cancel=cancel)
            self.assertLess(time.time() - began, 1.0)

    def test_a_stuck_answer_eventually_says_so_rather_than_hanging_forever(self):
        sess, patched = _session(self.s, self.tid, 'answered', delay=1.0)
        with patched, mock.patch.object(general, 'WAIT_TURN', 0.2):
            threading.Thread(target=lambda: sess.send_prompt('one'), daemon=True).start()
            time.sleep(0.2)
            with self.assertRaises(RuntimeError) as e:
                sess.send_prompt('two')
        self.assertIn('stuck', str(e.exception))

    def test_the_lock_is_given_back_when_the_brain_fails(self):
        """A failed answer must not wedge the conversation shut."""
        sess = general.GeneralSession(self.s, self.tid)
        sess.pick, sess.provider = 'cli:coder', 'coder'
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=mock.Mock(side_effect=RuntimeError('boom'))):
            with self.assertRaises(RuntimeError): sess.send_prompt('one')
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda *a, **k: 'fine'):
            self.assertEqual(sess.send_prompt('two'), 'fine')


class WalkingAwayIsNotStoppingTests(unittest.TestCase):
    """Closing the stream used to kill the run. Leaving the Board tab, pressing refresh, or any
    remount of the pane therefore ended an answer that was seconds from done - and because the
    reply is only filed when the run finishes, it was lost. The chat looked as though it had
    ignored the question (the owner's log, 2026-08-31: a stream at 16:55:32, the pane remounting
    at 16:55:40, no reply ever)."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')

    def test_a_run_nobody_is_watching_still_files_its_answer(self):
        sess, patched = _session(self.s, self.tid, 'the answer', delay=0.4)
        with patched:
            done = threading.Event()
            threading.Thread(target=lambda: (sess.send_prompt('ask'), done.set()), daemon=True).start()
            done.wait(10)
        said = [c['Body'] for c in general.chat_rows(self.s, self.tid) if c['ActorType'] == general.ASSISTANT_TYPE]
        self.assertEqual(said, ['the answer'])

    def test_stop_is_the_only_thing_that_stops_it(self):
        sess, patched = _session(self.s, self.tid, 'answered', delay=1.0)
        self.assertFalse(sess.stop())                    # nothing running: nothing to stop
        with patched:
            threading.Thread(target=lambda: sess.send_prompt('ask'), daemon=True).start()
            time.sleep(0.25)
            self.assertTrue(sess.stop())                 # ...and mid-answer it stops that answer
            self.assertTrue(sess._cancel is None or sess._cancel.is_set())

    def test_the_stop_switch_is_put_away_afterwards(self):
        sess, patched = _session(self.s, self.tid, 'answered')
        with patched: sess.send_prompt('ask')
        self.assertIsNone(sess._cancel)
        self.assertFalse(sess.stop())

    def test_the_endpoint_says_when_there_was_nothing_to_stop(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        c = TestClient(server.app)
        tid = c.post('/api/tasks', json={'Title': 'chat', 'Kind': 'general'}).json()['taskId']
        self.assertEqual(c.post(f'/api/tasks/{tid}/assistant/cancel').json(), {'stopped': False})


class OneConversationNotTwentyTests(unittest.TestCase):
    """Every turn used to be a brand-new `claude -p` with the whole transcript typed into it
    again: slower, dearer, and silently forgetful once the conversation outgrew MAX_CONTEXT.
    run_cli has always taken a `resume`, and nothing ever passed one."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')
        self.sess = general.GeneralSession(self.s, self.tid)
        self.sess.pick, self.sess.provider = 'cli:coder', 'coder'

    def _brain(self, sid='sess-1', fail_on_resume=False):
        seen = []
        def brain(system, user, **kw):
            seen.append({'system': system, 'user': user, 'resume': brain.session_id})
            if fail_on_resume and brain.session_id: raise RuntimeError('no conversation found to resume')
            brain.session_id = sid
            return 'answered'
        brain.session_id = None
        return brain, seen

    def _run(self, texts, brain):
        made = []
        def build(store, pick=None, model=None, trace=None, cancel=None, resume=None, **kwargs):
            brain.session_id = resume
            made.append(resume)
            return brain
        with mock.patch.object(general.llm_mod, 'build_llm', side_effect=build):
            for t in texts: self.sess.send_prompt(t)
        return made

    def test_the_second_turn_resumes_the_first(self):
        brain, seen = self._brain()
        made = self._run(['one', 'two', 'three'], brain)
        self.assertEqual(made, [None, 'sess-1', 'sess-1'])          # started once, continued twice

    def test_a_resumed_turn_says_only_the_new_turn(self):
        brain, seen = self._brain()
        self._run(['tell me about the wall', 'and what about the chat'], brain)
        self.assertIn('CONVERSATION', seen[0]['user'])               # the first says everything
        self.assertNotIn('CONVERSATION', seen[1]['user'])            # the second only the new turn
        self.assertIn('and what about the chat', seen[1]['user'])
        self.assertLess(len(seen[1]['user']), len(seen[0]['user']))

    def test_a_cli_that_cannot_resume_starts_over_rather_than_failing(self):
        """Its history was cleared, or the id aged out: say the whole thing again, once."""
        brain, seen = self._brain(fail_on_resume=True)
        made = self._run(['one'], brain)
        self.sess.cli_sid = 'gone'
        with mock.patch.object(general.llm_mod, 'build_llm',
                               side_effect=lambda store, **kw: (setattr(brain, 'session_id', kw.get('resume')), brain)[1]):
            self.assertEqual(self.sess.send_prompt('two'), 'answered')
        self.assertIn('CONVERSATION', seen[-1]['user'])              # the full transcript, again
        self.assertEqual(self.sess.cli_sid, 'sess-1')                # ...and a new conversation to continue


class AFinishedSessionTests(unittest.TestCase):
    def test_an_ended_session_stops_occupying_its_task(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')
        with mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:coder', 'label': 'coder', 'model': ''}]):
            first = general.start_session(s, tid)
            first.close()
            second = general.start_session(s, tid)
        self.assertIsNot(first, second)                    # a new one, not "already has a session"
        self.assertTrue(second.alive)

    def test_dropping_finished_sessions_leaves_the_live_one_alone(self):
        from taskuary import terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'chat', 'Kind': 'general'}, 'o')
        with mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:coder', 'label': 'coder', 'model': ''}]):
            live = general.start_session(s, tid)
        self.assertEqual(general.drop_session(tid), 0)
        self.assertIn(live.sid, terminal.SESSIONS)
        live.close()
        self.assertEqual(general.drop_session(tid), 1)
        self.assertNotIn(live.sid, terminal.SESSIONS)


if __name__ == '__main__':
    unittest.main()
