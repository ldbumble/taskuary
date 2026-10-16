"""How a batch's session ENDS - the shape of a real incident, with invented people.

The owner opened a session on a one-item batch, asked the agent to merge, and the agent ran `taskuary --item 1 --settled` as a
tool call. Settling the last item wrapped the session from inside that call: the CLI timed out waiting on the wrap, retried,
and the retry wrapped it a second time. The session died mid-turn, two AGENT REPORTs were filed (the second a raw screen dump),
the LAST MESSAGE was the turn BEFORE the merge ("I recommend merging ... waiting on you"), and the task page said nothing
had started "on what came in since" when nothing had come in. Invented repositories only; no model, no pty."""
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace
from unittest import mock

from taskuary import batch, funnel, selfclose, terminal as term, witness, wrapup, workerstate as ws
from taskuary.store import MemoryStore


def pr(s, repo, n):
    return s.add_message({'ExternalId': f'gh:{repo}#{n}@r1', 'ConversationId': f'gh:{repo}#{n}', 'Channel': 'github',
                          'SourceName': repo, 'Subject': f'{repo}#{n} change {n}', 'FromName': 'erin-blake',
                          'FromEmail': 'erin@northwind.example', 'SentAt': '2026-10-12 07:00:00', 'BodyText': f'fixes {n}',
                          'SourceLink': f'https://github.com/{repo}/pull/{n}', 'Status': 'triaging'})


def ago(minutes=0): return (datetime.now() - timedelta(minutes=minutes)).strftime('%Y-%m-%d %H:%M:%S')


class SessionTest(unittest.TestCase):
    """A batch of two with a live session in it (a fake pty in terminal.SESSIONS, so workerstate sees it as the live run)."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = batch.create(self.s, 'github', 'northwind/ledger', [self.s.get_message(pr(self.s, 'northwind/ledger', n)) for n in (1, 2)])
        self.sess = SimpleNamespace(sid='s1', task_id=self.tid, alive=True, started=0, started_ts=0, n=5000, agent='coding', witness=None)
        term.SESSIONS['s1'] = self.sess
        self.wraps, self.later = [], []
        def wrap(store, tid, **k):
            self.wraps.append(k); store.update_task(tid, {'Status': 'done'}, k.get('actor') or 'x'); self.sess.alive = False
            return {'wrap': 'done'}
        self.p = [mock.patch.object(batch, '_next'), mock.patch.object(wrapup, 'wrap', side_effect=wrap),
                  mock.patch.object(batch, '_later', side_effect=self.later.append)]   # the grace after a turn: run by flush()
        for p in self.p: p.start()
        batch.forget(self.tid)

    def tearDown(self):
        for p in self.p: p.stop()
        term.SESSIONS.pop('s1', None); batch.forget(self.tid); selfclose.forget(self.tid)

    def settled(self): return [c for c in self.s.list_comments(self.tid) if c['Body'].startswith('Every item of this batch is settled.')]

    def flush(self):
        while self.later: self.later.pop(0)()


class MidTurnTests(SessionTest):
    def test_settling_the_last_item_mid_turn_leaves_the_session_and_the_task_open(self):
        ws.record(self.s, self.tid, 's1', 'working', source='hook')              # the agent's turn: its settle is a tool call in it
        batch.report(self.s, self.tid, 1, 'Merged on the owner\'s say-so.', settled=True)
        batch.report(self.s, self.tid, 2, 'Nothing to do.', settled=True)
        batch.report(self.s, self.tid, 2, 'Nothing to do.', settled=True)        # ...and the CLI's retry of the same call
        self.assertEqual(self.wraps, [], 'nothing is wrapped while the agent is still working')
        self.assertTrue(self.sess.alive)
        self.assertNotIn(self.s.get_task(self.tid)['Status'], ('done', 'dropped'))
        self.assertEqual(len(self.settled()), 1, 'the fact is said once, not once per retry')

    def test_when_the_turn_then_ends_the_batch_closes(self):
        ws.record(self.s, self.tid, 's1', 'working', source='hook')
        for n in (1, 2): batch.report(self.s, self.tid, n, 'Done.', settled=True)
        self.assertEqual(self.wraps, [])
        ws.record(self.s, self.tid, 's1', 'turn_end', text='Both reviewed and settled.', source='hook')
        self.flush()
        self.assertEqual(len(self.wraps), 1)
        self.assertTrue(self.wraps[0]['close'])
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_a_turn_that_ends_with_work_still_running_waits_for_the_next(self):
        ws.record(self.s, self.tid, 's1', 'working', source='hook')
        for n in (1, 2): batch.report(self.s, self.tid, n, 'Done.', settled=True)
        ws.record(self.s, self.tid, 's1', 'turn_end', text='Waiting on the build.', source='hook')
        ws.record(self.s, self.tid, 's1', 'working', source='hook')              # a new turn began before the close got there
        self.flush()
        self.assertEqual(self.wraps, [], 'a turn in flight is never cut off')
        ws.record(self.s, self.tid, 's1', 'turn_end', text='Build passed.', source='hook')
        self.flush()
        self.assertEqual(len(self.wraps), 1)

    def test_an_idle_session_closes_at_the_settle_as_before(self):
        ws.record(self.s, self.tid, 's1', 'working', source='hook')
        ws.record(self.s, self.tid, 's1', 'turn_end', text='Waiting on you.', source='hook')
        for n in (1, 2): batch.act(self.s, self.tid, n, 'settle')                # the owner's own presses, between turns
        self.assertEqual(len(self.wraps), 1)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_done_on_a_fully_settled_batch_closes_it(self):
        ws.record(self.s, self.tid, 's1', 'working', source='hook')
        for n in (1, 2): batch.report(self.s, self.tid, n, 'Done.', settled=True)
        out = selfclose.declare(self.s, self.tid, 'Both items reviewed and settled.', agent='coding')
        self.assertTrue(out['closed'], out)
        self.assertEqual(len(self.wraps), 1)
        ws.record(self.s, self.tid, 's1', 'turn_end', text='Done.', source='hook')
        self.flush()
        self.assertEqual(len(self.wraps), 1, 'the pending close does not run a second time')

    def test_done_with_an_item_still_open_is_refused(self):
        ws.record(self.s, self.tid, 's1', 'working', source='hook')
        batch.report(self.s, self.tid, 1, 'Done.', settled=True)
        out = selfclose.declare(self.s, self.tid, 'All done.', agent='coding')
        self.assertFalse(out['closed'])
        self.assertIn('2', out['why'])
        self.assertEqual(self.wraps, [])

    def test_the_seed_lets_the_agent_end_it_once_every_item_is_settled(self):
        with mock.patch.object(batch, '_diff', return_value=('diff --git a/x b/x', 'abc123')):
            seed = batch.seed(self.s, self.tid, 'northwind/ledger')
        self.assertNotIn('Do NOT run --done', seed)
        self.assertIn('taskuary --done', seed)


class WrapOnceTests(unittest.TestCase):
    """One session, one ending: the same sid wrapped again files nothing more."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        wrapup.forget(self.tid)
        self.p = [mock.patch.object(term, 'transcript_for', return_value=('$ gh pr view 7\nmerged', 'coding', 'sid-w')),
                  mock.patch.object(term, 'close'), mock.patch.object(term, 'session_for', return_value=None),
                  mock.patch('taskuary.handbook.enabled', return_value=False),
                  mock.patch('taskuary.playbooks.draft', return_value=None),
                  mock.patch.object(wrapup, 'report_from_transcript', return_value={'determination': 'merged', 'actions': '', 'summary': 'Merged it.'})]
        for p in self.p: p.start()

    def tearDown(self):
        for p in self.p: p.stop()
        wrapup.forget(self.tid)

    def reports(self): return [c for c in self.s.list_comments(self.tid) if wrapup.is_report(c['Body'])]
    def closes(self): return [c for c in self.s.list_comments(self.tid) if c['Body'].startswith('Closed the session')]

    def test_a_second_wrap_of_the_same_session_files_nothing(self):
        wrapup.wrap(self.s, self.tid, close=True, actor='coding', no_reply=True)
        self.s.update_task(self.tid, {'Status': 'in_progress'}, 'o')           # whatever the status did meanwhile
        out = wrapup.wrap(self.s, self.tid, close=True, actor='coding', no_reply=True)
        self.assertEqual(out.get('wrap'), 'already')
        self.assertEqual((len(self.reports()), len(self.closes())), (1, 1))

    def test_a_wrap_that_lands_while_the_first_is_still_writing_files_nothing(self):
        inner = []
        def slow(store, tid, text, agent='', **k):                                  # the second settle arrives mid-report
            if not inner: inner.append(wrapup.wrap(store, tid, close=True, actor='coding', no_reply=True))
            return {'determination': '', 'actions': '', 'summary': 'Merged it.'}
        with mock.patch.object(wrapup, 'report_from_transcript', side_effect=slow):
            wrapup.wrap(self.s, self.tid, close=True, actor='coding', no_reply=True)
        self.assertEqual(inner[0].get('wrap'), 'already')
        self.assertEqual((len(self.reports()), len(self.closes())), (1, 1))

    def test_the_session_already_wrapped_before_a_restart_is_not_wrapped_again(self):
        self.s.audit('terminal', self.tid, 'wrap', 'coding', detail={'sid': 'sid-w', 'close': True})
        out = wrapup.wrap(self.s, self.tid, close=True, actor='coding', no_reply=True)
        self.assertEqual(out.get('wrap'), 'already')
        self.assertEqual(self.reports(), [])

    def test_the_owner_closing_a_saved_session_still_closes_the_task(self):
        wrapup.wrap(self.s, self.tid, close=False, actor='owner')               # Save and end session
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        wrapup.wrap(self.s, self.tid, close=True, actor='owner', no_reply=True) # ...then Done
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
        self.assertEqual(len(self.reports()), 1)


class ScreenFallbackTests(unittest.TestCase):
    SCREEN = '● Bash(cd /c/work; gh pr view 7 --json state)\n  ⎿  MERGED\n✢ Swooping… (32s · ↓ 1.1k tokens)'

    def test_no_ai_never_files_the_raw_screen_as_the_summary(self):
        s = MemoryStore(); tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding'}, 'o')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            rep = wrapup.report_from_transcript(s, tid, self.SCREEN)
        self.assertNotIn('Bash(', rep['summary']); self.assertNotIn('●', rep['summary'])
        self.assertTrue(rep['summary'].strip())

    def test_no_ai_files_the_agents_own_last_word_when_there_is_one(self):
        s = MemoryStore(); tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding'}, 'o')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            rep = wrapup.report_from_transcript(s, tid, self.SCREEN, final_message='Merged pull request 7.')
        self.assertIn('Merged pull request 7.', rep['summary'])


class LastMessageTests(unittest.TestCase):
    """The witness keeps the last finished turn's words; a turn begun after it makes them old news."""
    def test_a_new_turn_makes_the_last_message_stale(self):
        w = witness.Witness()
        w.note({'k': 'done', 'text': 'I recommend merging it - waiting on you.'})
        self.assertEqual(w.said_now(), 'I recommend merging it - waiting on you.')
        self.assertFalse(w.cut_off())
        w.note({'k': 'turn'})                                                   # the owner: "merge it please"
        self.assertEqual(w.said_now(), '')
        self.assertTrue(w.cut_off())
        w.note({'k': 'say', 'text': 'Merging now.'})                            # codex says things mid-turn
        self.assertEqual(w.said_now(), 'Merging now.')
        w.note({'k': 'done', 'text': 'Merged.'})
        self.assertFalse(w.cut_off())

    def test_a_session_closed_mid_turn_says_so_instead_of_the_older_message(self):
        s = MemoryStore(); tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        wrapup.forget(tid)
        w = witness.Witness()
        w.note({'k': 'done', 'text': 'I recommend merging it - waiting on you.'}); w.note({'k': 'turn'})
        live = SimpleNamespace(sid='sid-m', alive=True, witness=w)
        with mock.patch.object(term, 'transcript_for', return_value=('$ gh pr merge 7', 'coding', 'sid-m')), \
             mock.patch.object(term, 'close'), mock.patch.object(term, 'session_for', return_value=live), \
             mock.patch('taskuary.handbook.enabled', return_value=False), mock.patch('taskuary.playbooks.draft', return_value=None), \
             mock.patch.object(wrapup, 'report_from_transcript', return_value={'summary': 'Merged it.'}):
            wrapup.wrap(s, tid, close=True, actor='owner', no_reply=True)
        rep = next(c['Body'] for c in s.list_comments(tid) if wrapup.is_report(c['Body']))
        self.assertNotIn('I recommend merging', rep)
        self.assertIn('LAST MESSAGE', rep)
        self.assertIn('still working', rep)
        wrapup.forget(tid)


class ClosedSessionStateTests(unittest.TestCase):
    def finished_run(self, s, t):
        ws.record(s, t, 's1', 'working', source='hook')
        ws.record(s, t, 's1', 'turn_end', text='Merged it.', source='hook')
        s.add_transcript(t, 's1', 'screen text', agent='coding')
        s.add_comment(t, 'coding', 'agent', f'{wrapup.REPORT}\nSummary: merged.')

    def test_a_finished_session_with_nothing_new_does_not_say_something_came_in(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Review the pull request', 'Kind': 'coding', 'Status': 'open', 'Assignee': 'agent:coding'}, 'o')
        self.finished_run(s, t)
        why = funnel.not_started_why(s, t)
        self.assertIn('finished its last session', why)
        self.assertNotIn('came in since', why)

    def test_a_task_whose_session_finished_is_not_under_agents_working(self):
        from tests.test_funnel import store, mail
        s = store()
        t = s.create_task({'Title': 'Review the pull request', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        mail(s, 'Review the pull request', hours=1, tid=t)
        self.finished_run(s, t)
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            items = [i for i in funnel.build(s)['items'] if i.get('tid') == t]
        self.assertTrue(items)
        self.assertNotIn('working', [i['lane'] for i in items])


if __name__ == '__main__':
    unittest.main()
