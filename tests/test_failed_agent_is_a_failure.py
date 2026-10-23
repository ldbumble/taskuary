"""A FAILED AGENT IS SAID AS A FAILURE (owner-approved, 2026-10-21, the UI/UX audit's R2).

A general agent whose turn failed - no AI to run on, or a run that broke - stayed open, alive and not busy, which every surface
reads as "waiting on you": the card's chip, the rail row, the Board's column. Its step said "Not started yet", the only lit move
was "New task to fix this", and the reason reached the screen as "connect a CLI agent or an AI provider before starting general
work". Now the session ends on a failed turn, its conversation kept, so the run's own last word (failed) is what every surface
reads: the step says "Failed - <why>", Try again picks it back up, and with no AI connected the fix is Connect an AI."""
import time, unittest
from unittest import mock

from taskuary import advisor, funnel, general, taskstate, terminal, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class FailedAgent(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self.tid = self.fx.task(title='Compare three payroll vendors on price', kind='general', status='in_progress')
        self.addCleanup(lambda: [terminal.SESSIONS.pop(k, None) for k in [k for k, v in terminal.SESSIONS.items() if v.task_id == self.tid]])

    def fail(self, brain=None):
        pick = ('api:test', 'Test', 'm') if brain else ('', '', '')
        with mock.patch.object(general, '_selected', return_value=pick):
            sess = general.GeneralSession(self.s, self.tid)
        terminal.SESSIONS[sess.sid] = sess
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain), self.assertRaises(RuntimeError):
            sess.send_prompt('compare them')
        for _ in range(40):                                  # the session ends off the failing thread
            if not sess.alive: break
            time.sleep(0.05)
        return sess

    def test_no_ai_ends_the_session_and_reads_failed_everywhere(self):
        sess = self.fail()
        self.assertFalse(sess.alive, 'a failed turn leaves no live session to read as waiting on you')
        self.assertEqual(ws.ended(self.s, self.tid), 'failed')
        self.assertEqual(taskstate.state(self.s, self.s.get_task(self.tid)), 'stopped', 'never the Board\'s "agent waiting on you"')
        story = funnel.agent_story(self.s, self.tid)
        self.assertEqual(story['kind'], 'failed')
        self.assertTrue(story['line'].startswith('Failed - No AI is connected'), story['line'])
        self.assertNotRegex(story['line'], r'CLI agent|AI provider')
        self.assertEqual(story['fix']['label'], 'Connect an AI')
        self.assertEqual(advisor.agent_failed(self.s, {'tid': self.tid})['fix']['label'], 'Connect an AI')

    def test_with_no_ai_the_owners_words_are_kept_and_nothing_says_it_started(self):
        sess = self.fail()
        self.assertIn('compare them', [c['Body'] for c in self.s.list_comments(self.tid) if c.get('ActorType') == general.USER_TYPE])
        self.assertNotIn('working', [e['Kind'] for e in self.s.worker_events(self.tid)], 'no run worked: there was no AI to run on')
        self.assertFalse([t for t in sess.trace if t.get('type') == 'start'], 'no "Started the selected agent" step')

    def test_no_report_is_filed_for_a_failed_turn(self):
        self.fail()
        self.assertFalse(any(str(c.get('Body') or '').startswith('AGENT REPORT') for c in self.s.list_comments(self.tid)))

    def test_a_run_that_broke_is_tried_again_not_made_a_new_task(self):
        def brain(system, user, **kw): raise RuntimeError('the test database was not reachable')
        self.fail(brain)
        story = funnel.agent_story(self.s, self.tid)
        self.assertEqual((story['kind'], story['line']), ('failed', 'Failed - The test database was not reachable.'))
        self.assertIsNone(story['fix'])
        lead = advisor.offered(self.s, {'tid': self.tid, 'kind': 'task', 'key': f'task:{self.tid}'})[0]
        self.assertEqual((lead['verb'], lead['label']), ('continue', 'Try again'))

    def test_a_stopped_turn_is_not_a_failure(self):
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(self.s, self.tid)
        terminal.SESSIONS[sess.sid] = sess
        import threading
        stop = threading.Event(); stop.set()
        def brain(system, user, **kw): raise RuntimeError('cancelled')
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain), self.assertRaises(RuntimeError):
            sess.send_prompt('compare them', cancel=stop)
        time.sleep(0.3)
        self.assertTrue(sess.alive, 'the owner pressed stop - the conversation stays open')


if __name__ == '__main__': unittest.main()
