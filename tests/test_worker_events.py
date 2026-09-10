"""One shared worker status model, fed by explicit events, consumed by every surface (PW-222, PW-226, PW-227, PW-137, PW-139, PW-141).

A session's status was read off its screen: a bare prompt meant "stopped and waiting on you", a
quiet terminal meant a question, and every consumer disagreed with the next. Now a worker's state
is derived from explicit, persisted events - Working, Input needed (with the unanswered question),
Approval needed (with the specific pending action), Finished (an explicit result), Failed,
Disconnected, Stopped - keyed by task, run and request id, deduplicated, with stale events from an
old run rejected. A response ending is not a finish: without an explicit result or question the
state is unknown, never a guessed hand raise. An answer is bound to the exact outstanding request
and run: delivered once, refused when resolved or when the run changed, and recorded with its
delivery outcome - queued, delivered or failed - in the task's discussion, never "told the agent"
from HTTP success alone.
"""
import json, unittest
from types import SimpleNamespace
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import hooks, selfclose, server, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def live(tid, sid='run1', cwd=r'C:\code\repo', agent='coder', argv=('claude',)):
    typed = []
    s = SimpleNamespace(sid=sid, alive=True, task_id=tid, cwd=cwd, agent=agent, label=agent, argv=list(argv), last=1.0, ext_id='',
                        started='2026-09-06 09:00:00', typed=typed, files=lambda: [], tail=lambda n=3: [], idle=lambda: 0.0,
                        witness=SimpleNamespace(note=lambda n: None), store=None)
    return s


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear()
        self.tid = self.fx.task(title='Fix the cron', kind='coding')
    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions)


class EventModelTests(Base):
    def test_events_persist_and_the_state_is_derived_from_them(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'working', source='hook', event_id='e1')
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'working')
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which environment: staging or prod?', choices=['staging', 'prod'], event_id='e2')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'input_needed'); self.assertEqual(st['requests'][0]['request_id'], 'q1')
        self.assertEqual(st['requests'][0]['choices'], ['staging', 'prod']); self.assertIn('staging or prod', st['requests'][0]['text'])
        ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id='p1', text='Run `alembic upgrade head`?', event_id='e3')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'approval_needed')                          # an approval outranks a question: it blocks harder
        self.assertEqual([r['request_id'] for r in st['requests']], ['q1', 'p1'])

    def test_a_response_ending_is_not_a_finish(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'working', event_id='e1')
        ws.record(self.s, self.tid, 'run1', 'turn_end', text='I looked at the cron config.', event_id='e2')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'unknown'); self.assertNotIn('finished', st['state'])
        self.assertEqual(st['result'], None)
        ws.record(self.s, self.tid, 'run1', 'finished', text='Fixed: the cron ran under the wrong user.', event_id='e3')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'finished'); self.assertIn('wrong user', st['result'])
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')             # Finished closes nothing by itself (PW-222)

    def test_failures_disconnections_and_owner_stops_are_never_completion(self):
        for kind in ('failed', 'disconnected', 'stopped'):
            tid = self.fx.task(title=kind, kind='coding'); term.SESSIONS[f's-{kind}'] = live(tid, sid=f's-{kind}')
            ws.record(self.s, tid, f's-{kind}', 'working', event_id=f'{kind}-1')
            ws.record(self.s, tid, f's-{kind}', kind, text='boom', event_id=f'{kind}-2')
            st = ws.status(self.s, tid)
            self.assertEqual(st['state'], kind); self.assertIsNone(st['result'])

    def test_a_dead_session_with_no_finish_is_disconnected_not_finished_and_an_idle_one_raises_no_hand(self):
        term.SESSIONS['run1'] = live(self.tid)
        ws.record(self.s, self.tid, 'run1', 'working', event_id='e1')
        term.SESSIONS['run1'].alive = False
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'disconnected')
        tid2 = self.fx.task(title='idle', kind='coding'); term.SESSIONS['run2'] = live(tid2, sid='run2')
        term.SESSIONS['run2'].tail = lambda n=3: ['> ']                                 # a bare prompt on screen
        st = ws.status(self.s, tid2)
        self.assertEqual(st['state'], 'unknown'); self.assertEqual(st['requests'], [])  # no event, no guessed question

    def test_duplicates_and_stale_events_are_rejected(self):
        term.SESSIONS['run2'] = live(self.tid, sid='run2')
        self.assertTrue(ws.record(self.s, self.tid, 'run2', 'input_needed', request_id='q1', text='A or B?', event_id='dup'))
        self.assertFalse(ws.record(self.s, self.tid, 'run2', 'input_needed', request_id='q1', text='A or B?', event_id='dup'))   # replayed
        self.assertFalse(ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='old', text='from the run before', event_id='old1'))  # an old run
        st = ws.status(self.s, self.tid)
        self.assertEqual([r['request_id'] for r in st['requests']], ['q1'])
        self.assertEqual(len(ws.events(self.s, self.tid)), 1)


class AnswerBindingTests(Base):
    def test_an_answer_is_bound_to_the_request_and_run_delivered_once_and_recorded_with_its_outcome(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which environment?', event_id='e1')
        ws.record(self.s, self.tid, 'run1', 'approval_needed', request_id='p1', text='Run the migration?', event_id='e2')
        with mock.patch.object(term, 'type_into', side_effect=lambda t, text: sess.typed.append(text)) as typed:
            out = ws.answer(self.s, self.tid, 'q1', 'staging', actor='owner')
        self.assertEqual((out['delivered'], out['state']), (True, 'delivered')); self.assertIn('staging', sess.typed[0])
        st = ws.status(self.s, self.tid)
        self.assertEqual([r['request_id'] for r in st['requests']], ['p1'])            # only the answered request closed
        self.assertEqual(st['state'], 'approval_needed')
        again = ws.answer(self.s, self.tid, 'q1', 'staging', actor='owner')
        self.assertEqual((again['delivered'], again['state']), (False, 'resolved'))    # a second click delivers nothing
        bodies = [c['Body'] for c in self.s.list_comments(self.tid)]
        self.assertTrue(any('Which environment?' in b and 'staging' in b and 'delivered' in b for b in bodies))

    def test_a_changed_or_dead_run_refuses_delivery_instead_of_forwarding_to_a_replacement(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which environment?', event_id='e1')
        term.SESSIONS.clear(); term.SESSIONS['run2'] = live(self.tid, sid='run2')      # a new worker on the same task
        with mock.patch.object(term, 'type_into') as typed:
            out = ws.answer(self.s, self.tid, 'q1', 'staging', actor='owner')
        typed.assert_not_called(); self.assertEqual((out['delivered'], out['state']), (False, 'stale'))
        term.SESSIONS.clear()
        ws.record(self.s, self.tid, 'run2', 'input_needed', request_id='q2', text='Still there?', event_id='e2')
        out2 = ws.answer(self.s, self.tid, 'q2', 'yes', actor='owner')
        self.assertEqual((out2['delivered'], out2['state']), (False, 'disconnected'))
        self.assertEqual(ws.status(self.s, self.tid)['requests'][0]['request_id'], 'q2')  # the question stays open for the workspace fallback

    def test_a_delivery_that_fails_is_a_failure_not_told_the_agent(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which environment?', event_id='e1')
        with mock.patch.object(term, 'type_into', side_effect=RuntimeError('pty closed')):
            out = ws.answer(self.s, self.tid, 'q1', 'staging', actor='owner')
        self.assertEqual((out['delivered'], out['state']), (False, 'failed'))
        self.assertEqual(ws.status(self.s, self.tid)['requests'][0]['request_id'], 'q1')  # still outstanding
        self.assertTrue(any('could not be delivered' in c['Body'] for c in self.s.list_comments(self.tid)))


class ProducersTests(Base):
    def test_claude_code_hooks_become_events_without_guessing(self):
        sess = live(self.tid); sess.store = self.s; term.SESSIONS['run1'] = sess
        base = {'cwd': r'C:\code\repo', 'session_id': 'cc-1'}
        hooks.receive({**base, 'hook_event_name': 'UserPromptSubmit', 'prompt': 'fix the cron'})
        self.assertEqual(ws.status(self.s, self.tid)['state'], 'working')
        hooks.receive({**base, 'hook_event_name': 'PostToolUse', 'tool_name': 'AskUserQuestion',
                       'tool_input': {'questions': [{'question': 'Which environment?', 'options': [{'label': 'staging'}, {'label': 'prod'}]}]}})
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'input_needed'); self.assertEqual(st['requests'][0]['choices'], ['staging', 'prod'])
        hooks.receive({**base, 'hook_event_name': 'Notification', 'notification_type': 'permission_prompt', 'message': 'Claude needs your permission to use Bash'})
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'approval_needed'); self.assertIn('Bash', st['requests'][-1]['text'])
        with mock.patch.object(selfclose, 'spawn_on_stop'):
            hooks.receive({**base, 'hook_event_name': 'Stop', 'last_assistant_message': 'I have looked into it.'})
        self.assertNotEqual(ws.status(self.s, self.tid)['state'], 'finished')          # Stop = the response ended, not the task

    def test_an_explicit_done_is_the_finished_event_with_its_result(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        selfclose.forget(self.tid)                                   # the once-only mark is process-wide; another suite may have used this id
        with mock.patch.object(selfclose, '_wrap', return_value={'closed': True, 'drafting': False}), \
             mock.patch.object(selfclose, 'blocked', return_value=''), mock.patch.object(selfclose, 'stays_open', return_value=False):
            selfclose.declare(self.s, self.tid, 'cleared the stuck cron and re-ran it', 'coder')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'finished'); self.assertIn('stuck cron', st['result'])


class ApiTests(Base):
    def setUp(self):
        super().setUp()
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def test_the_status_and_the_answer_share_one_endpoint_pair(self):
        sess = live(self.tid); term.SESSIONS['run1'] = sess
        ws.record(self.s, self.tid, 'run1', 'input_needed', request_id='q1', text='Which environment?', event_id='e1')
        st = self.c.get(f'/api/tasks/{self.tid}/worker').json()
        self.assertEqual(st['state'], 'input_needed'); self.assertEqual(st['requests'][0]['request_id'], 'q1')
        with mock.patch.object(term, 'type_into', side_effect=lambda t, text: sess.typed.append(text)):
            r = self.c.post(f'/api/tasks/{self.tid}/worker/answer', json={'request_id': 'q1', 'text': 'staging'})
        self.assertEqual((r.status_code, r.json()['delivered']), (200, True))
        r2 = self.c.post(f'/api/tasks/{self.tid}/worker/answer', json={'request_id': 'q1', 'text': 'staging'})
        self.assertEqual(r2.status_code, 409)


if __name__ == '__main__':
    unittest.main()
