"""A FAILED AGENT IS SAID AS A FAILURE (owner-approved, 2026-10-21, the UI/UX audit's R2).

A general agent whose turn failed - no AI to run on, or a run that broke - stayed open, alive and not busy, which every surface
reads as "waiting on you": the card's chip, the rail row, the Board's column. Its step said "Not started yet", the only lit move
was "New task to fix this", and the reason reached the screen as "connect a CLI agent or an AI provider before starting general
work". Now the session ends on a failed turn, its conversation kept, so the run's own last word (failed) is what every surface
reads: the step says "Failed - <why>", Try again picks it back up, and with no AI connected the fix is Connect an AI."""
import time, unittest
from unittest import mock

from taskuary import funnel, general, taskstate, terminal, workerstate as ws, rulebook
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
        self.assertEqual(rulebook.agent_failed(self.s, {'tid': self.tid})['fix']['label'], 'Connect an AI')

    def test_with_no_ai_the_owners_words_are_kept_and_nothing_says_it_started(self):
        sess = self.fail()
        self.assertIn('compare them', [c['Body'] for c in self.s.list_comments(self.tid) if c.get('ActorType') == general.USER_TYPE])
        self.assertNotIn('working', [e['Kind'] for e in self.s.worker_events(self.tid)], 'no run worked: there was no AI to run on')
        self.assertFalse([t for t in sess.trace if t.get('type') == 'start'], 'no "Started the selected agent" step')

    def test_no_report_is_filed_for_a_failed_turn(self):
        self.fail()
        self.assertFalse(any(str(c.get('Body') or '').startswith('AGENT REPORT') for c in self.s.list_comments(self.tid)))

    def test_an_ai_that_never_answered_is_said_in_words_and_in_the_chat(self):
        """2026-11-09: a gateway that took the call and never answered reached the rail as "Failed - HTTPSConnectionPool(host=...): Read
        timed out. (read timeout=180)", and the chat under the owner's ask was empty. Design round 4 (H3): an AI that never answered is one
        queued state - its one plain line says when it is tried again (general.queue_retry), on the rail and in the chat alike."""
        import requests
        def brain(system, user, **kw): raise requests.ReadTimeout("HTTPSConnectionPool(host='ai.northwind.example', port=443): Read timed out.")
        with mock.patch.object(general, '_selected', return_value=('connector:9', 'Gateway (API)', 'm')):
            sess = general.GeneralSession(self.s, self.tid)
        terminal.SESSIONS[sess.sid] = sess
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain), self.assertRaises(requests.ReadTimeout): sess.send_prompt('sum it up')
        for _ in range(40):
            if not sess.alive: break
            time.sleep(0.05)
        line = funnel.agent_story(self.s, self.tid)['line']
        self.assertTrue(line.startswith("The AI didn't answer - trying again at "), line)
        self.assertNotRegex(line, r'ConnectionPool|northwind|443|\(API\)')
        last = general.with_failure(self.s, self.tid, general.shown_history(self.s, self.tid))[-1]
        self.assertEqual((last['role'], last.get('failed')), ('assistant', True))
        self.assertTrue(last['content'][0]['text'].startswith("⚠ The AI didn't answer - trying again at "), last)
        # ...and the rail's row says the same, never "Failed" or a hand that waits on him (the walk, 2026-11-22): the try is the app's move
        from taskuary import taskstate
        row = funnel.paused_conversation(self.s, {'tid': self.tid, 'lane': 'yours', 'key': f'task:{self.tid}'})
        self.assertTrue(taskstate.retrying(self.s, self.tid))
        self.assertEqual((row['lane'], row.get('failed'), row.get('asking')), ('queued', None, None))
        self.assertTrue(row['why'].startswith("The AI didn't answer - trying again at "), row['why'])

    def test_a_run_that_broke_is_tried_again_not_made_a_new_task(self):
        def brain(system, user, **kw): raise RuntimeError('the test database was not reachable')
        self.fail(brain)
        story = funnel.agent_story(self.s, self.tid)
        self.assertEqual((story['kind'], story['line']), ('failed', 'Failed - The test database was not reachable.'))
        self.assertIsNone(story['fix'])
        lead = rulebook.offered(self.s, {'tid': self.tid, 'kind': 'task', 'key': f'task:{self.tid}'})[0]
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


def test_an_agents_failed_run_is_what_failed_and_offers_the_task_to_fix_it():
    s = MemoryStore(); t = s.create_task({'Title': 'Fix the export', 'Status': 'in_progress', 'Kind': 'coding'}, 'owner')
    ws.record(s, t, 'r1', 'working'); ws.record(s, t, 'r1', 'failed', text='the test database was not reachable')
    item = {'key': f'agent:{t}', 'kind': 'agent', 'lane': 'stopped', 'tid': t, 'title': 'Fix the export'}
    f = rulebook.failure(s, item)
    assert f['what'] == "the agent's run failed" and 'not reachable' in f['why']
    assert 'new_task' in [v['verb'] for v in rulebook.offered(s, item)]
    ws.record(s, t, 'r2', 'working'); ws.record(s, t, 'r2', 'finished', text='done')
    assert rulebook.failure(s, item) is None, 'a run that finished since is no failure'


class AnActThatFailsKeepsTheAnswerTests(unittest.TestCase):
    def test_a_reply_step_that_raises_never_loses_the_answer(self):
        """The agent audit, 2026-11-22: one act of the answer (a draft, a withdraw, the Hub) that raised threw the whole answer away and filed
        the turn as failed - Try again ran the job again. The answer is filed; the act that failed is said on the task in its own line."""
        import time as _t
        s = MemoryStore(); tid = Factory(s).task(title='Answer Ray about the rota', kind='general', status='in_progress')
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')): sess = general.GeneralSession(s, tid)
        try:
            with mock.patch('taskuary.wrapup.agent_reply', side_effect=RuntimeError('database is locked')), mock.patch('taskuary.hooks.judge_ended'):
                sess._file('I checked the rota - Friday is free.\n[[TASKUARY-REPLY]]Hi Ray - Friday works.[[/TASKUARY-REPLY]]', [], _t.time())
            said = [c['Body'] for c in s.list_comments(tid)]
            self.assertTrue(any('Friday is free' in b for b in said), said)
            self.assertTrue(any(b.startswith('Saving the reply it wrote did not work') for b in said), said)
        finally: terminal.SESSIONS.pop(sess.sid, None)
