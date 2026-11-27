"""A hook that holds Claude must be holding something the owner can SEE (2026-10-21: a pane sat on "running PreToolUse
hook" for minutes, nothing asked anywhere). While the ask hook holds an AskUserQuestion, Claude draws nothing in its pane
- so the question must be on the task page as an open request the moment it is held, or not held at all, and a permit
whose card could not be shown is refused at once with the reason, never held for the hook's seven days."""
import asyncio, threading, time, unittest
from types import SimpleNamespace

from taskuary import hooks, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CWD = r'C:\code\repo'
ONE = {'questions': [{'question': 'Which branch should I base this on?', 'options': [{'label': 'main'}, {'label': 'dev'}]}]}


def pane(tid, store, sid='run1', ext='sess-1', mode='auto'):
    "a stranger's session (mode 'auto'): the one session whose ask is still held - the owner's own is asked in its terminal"
    return SimpleNamespace(sid=sid, mode=mode, alive=True, task_id=tid, cwd=CWD, agent='coding', label='coding', argv=['claude'], last=1.0,
                           ext_id=ext, resumed_from='', store=store, witness=SimpleNamespace(note=lambda n: None), n=0,
                           tail=lambda n=3: ['✻ Pondering… (esc to interrupt)'], status_tail=lambda n=6: ['✻ Pondering… (esc to interrupt)'])


def ask(wait=5.0):
    return hooks.ask({'hook_event_name': 'PreToolUse', 'tool_name': 'AskUserQuestion', 'session_id': 'sess-1', 'cwd': CWD, 'tool_input': ONE},
                     wait=wait)


class Base(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the export', kind='coding')
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear(); ws.HELD.clear()
        self.t = pane(self.tid, self.s); term.SESSIONS['run1'] = self.t

    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions); ws.HELD.clear()

    def another_run_owns_the_task(self):
        "the task's live run (the first live session on it) is not the one whose hook is asking"
        term.SESSIONS.clear(); term.SESSIONS['run0'] = pane(self.tid, self.s, sid='run0', ext='sess-0'); term.SESSIONS['run1'] = self.t

    def open_(self): return [r['text'] for r in ws.status(self.s, self.tid)['requests']]


class TheAskHook(Base):
    def test_a_held_question_is_on_the_page_while_it_is_held(self):
        seen = {}
        th = threading.Thread(target=lambda: seen.update(out=ask()), daemon=True); th.start()
        for _ in range(250):
            if ws.HELD: break
            time.sleep(0.02)
        self.assertTrue(ws.HELD, 'held')
        self.assertEqual(self.open_(), ['Which branch should I base this on?'], 'held = on the page, at once')
        ws.release(self.tid); th.join(5)
        self.assertEqual(seen['out'], {})

    def test_a_question_asked_again_after_its_answer_is_shown_again_never_held_out_of_sight(self):
        """Its id is its words, and that id was answered - so the second asking was recorded but never shown, while the hook
        held Claude on "running PreToolUse hook" for the whole ASK_WAIT. An answer closes what was asked BEFORE it
        (workerstate.open_requests): asked again, the question is on the page again, and what the hook holds is one he can answer."""
        th = threading.Thread(target=ask, daemon=True); th.start()
        for _ in range(250):
            if ws.HELD: break
            time.sleep(0.02)
        rid = ws.status(self.s, self.tid)['requests'][0]['request_id']
        ws.answer_group(self.s, self.tid, {rid: 'main'}, 'owner'); th.join(5)
        self.assertEqual(self.open_(), [])
        t0 = time.monotonic(); out = ask(wait=0.3)
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual((out, ws.HELD), ({}, {}))
        self.assertEqual(self.open_(), ['Which branch should I base this on?'], 'asked again, it is shown again')

    def test_a_card_refused_as_another_runs_is_not_held(self):
        self.another_run_owns_the_task()
        t0 = time.monotonic(); out = ask(wait=30)
        self.assertLess(time.monotonic() - t0, 2)
        self.assertEqual((out, ws.HELD), ({}, {}))

    def test_unanswered_it_lets_go_and_the_question_stays_asked(self):
        """Out of time: Claude draws its own form, and the page still says it asked - nothing is lost or silent."""
        t0 = time.monotonic(); out = ask(wait=0.3)
        self.assertLess(time.monotonic() - t0, 3)
        self.assertEqual((out, ws.HELD), ({}, {}))
        self.assertEqual(self.open_(), ['Which branch should I base this on?'])

    def test_the_hold_outlives_nothing(self):
        """The server lets go before curl does, and curl before Claude's own limit on the hook - each says something."""
        self.assertLess(hooks.ASK_WAIT, hooks.ASK_WAIT + 30)
        self.assertIn(f'-m {hooks.ASK_WAIT + 30}', hooks.ask_command('http://127.0.0.1:1'))
        self.assertLess(hooks.ASK_WAIT + 30, hooks.ASK_TIMEOUT)


class ThePermit(Base):
    def test_a_permit_whose_card_cannot_be_shown_is_refused_at_once_with_the_reason(self):
        self.another_run_owns_the_task()
        out = {}
        th = threading.Thread(target=lambda: out.update(r=hooks.permit({'tool_name': 'Bash', 'tool_input': {'command': 'ls'}, 'session_id': 'x'},
                                                                       self.tid, store=self.s)), daemon=True)
        # the hook asks for run1 while run0 owns the task
        orig = hooks.run_sid
        hooks.run_sid = lambda p, tid: 'run1'
        try:
            th.start(); th.join(3)
        finally: hooks.run_sid = orig
        self.assertFalse(th.is_alive(), 'never held out of sight')
        dec = out['r']['hookSpecificOutput']['decision']
        self.assertEqual(dec['behavior'], 'deny')
        self.assertIn('could not put this request in front of the owner', dec['message'])
        self.assertEqual(ws.HELD, {})


class TheGateThatCannotAnswer(Base):
    """Red team round 6: waits parked on the gate's own threads left its judging queued until the hook's curl gave up - and the command ran.
    A gate that cannot answer holds: its judging has threads no wait can take, and a step with no answer in time is refused, never run."""
    def setUp(self):
        super().setUp()
        from unittest import mock
        from taskuary import server
        self.server, self.mock = server, mock
        self.t.ext_id, self.t.argv = 'sess-1', ['claude']
        self.push = {'tool_name': 'Bash', 'tool_input': {'command': 'git push origin main'}, 'session_id': 'sess-1', 'cwd': CWD}

    def hook(self, payload, within=10): return asyncio.run(asyncio.wait_for(self.server.cli_hook_browser(payload), within))

    def test_waits_that_fill_the_permits_threads_leave_the_gate_judging(self):
        gate, n = threading.Event(), self.server._PERMIT_POOL._max_workers
        fs = [self.server._PERMIT_POOL.submit(gate.wait, 30) for _ in range(n)]
        try:
            with self.mock.patch.object(hooks, 'browser', return_value={'judged': True}):
                self.assertEqual(self.hook(self.push, within=5), {'judged': True})
        finally:
            gate.set(); [f.result(5) for f in fs]

    def test_a_task_parks_only_so_many_waits_and_the_next_is_refused_at_once(self):
        gate, req = threading.Event(), SimpleNamespace(headers={}, method='POST', url=SimpleNamespace(path='/api/hooks/claude/permit'))
        async def go():
            parked = [asyncio.ensure_future(self.server.cli_hook_permit({}, self.tid, req)) for _ in range(self.server.PARK_MAX)]
            await asyncio.sleep(0.2)
            over = await asyncio.wait_for(self.server.cli_hook_permit({}, self.tid, req), 3)
            other = asyncio.ensure_future(self.server.cli_hook_permit({}, self.tid + 1, req))       # ...another task's wait still parks
            await asyncio.sleep(0.2); gate.set()
            return over, await asyncio.gather(*parked), await other
        with self.mock.patch.object(self.server, '_own_task_only'), self.mock.patch.object(hooks, 'permit', side_effect=lambda *a, **k: gate.wait(30) and {'parked': True}):
            over, parked, other = asyncio.run(go())
        self.assertEqual(over['hookSpecificOutput']['decision']['behavior'], 'deny')
        self.assertEqual((parked, other), ([{'parked': True}] * self.server.PARK_MAX, {'parked': True}))
        self.assertEqual(self.server._PARKED, {}, 'every place given back')

    def test_a_judging_with_no_answer_in_time_or_that_fails_holds_our_sessions_step(self):
        slow = lambda *a, **k: time.sleep(1.5) or {}
        for why, how in (('no answer in time', {'side_effect': slow}), ('judging it failed', {'side_effect': RuntimeError('a line the gate could not read')})):
            with self.mock.patch.object(hooks, 'browser', **how), self.mock.patch.object(hooks, 'GATE_WAIT', 0.3):
                d = self.hook(self.push)['hookSpecificOutput']
                self.assertEqual(d['permissionDecision'], 'deny', why); self.assertIn(why, d['permissionDecisionReason'])
                self.assertIn('Run it again', d['permissionDecisionReason'], 'no dead end: it says what to do next')
                # ...the owner's own Claude, in no pane of ours, and a tool the gate does not judge are Claude's as ever
                self.assertEqual(self.hook({**self.push, 'session_id': 'his-own'}), {})
                self.assertEqual(self.hook({**self.push, 'tool_name': 'WebSearch'}), {})

    def test_a_gate_hook_that_rides_in_a_sessions_own_settings_blocks_where_it_fails(self):
        [h] = [x for m in hooks.session_hooks('tok', 'http://127.0.0.1:1')['PreToolUse'] if m['matcher'] == hooks.BROWSER_MATCH for x in m['hooks']]
        self.assertEqual(h.get('onFailure'), 'block')
        self.assertEqual(hooks._browser_hold('s1')['hooks'][0].get('onFailure'), 'block')
        self.assertLess(hooks.GATE_WAIT, hooks.BROWSER_WAIT, 'the server answers before curl gives up')


if __name__ == '__main__':
    unittest.main()
