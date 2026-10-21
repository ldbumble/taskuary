"""A hook that holds Claude must be holding something the owner can SEE (2026-10-21: a pane sat on "running PreToolUse
hook" for minutes, nothing asked anywhere). While the ask hook holds an AskUserQuestion, Claude draws nothing in its pane
- so the question must be on the task page as an open request the moment it is held, or not held at all, and a permit
whose card could not be shown is refused at once with the reason, never held for the hook's seven days."""
import asyncio, inspect, threading, time, unittest
from types import SimpleNamespace

from taskuary import hooks, server, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CWD = r'C:\code\repo'
ONE = {'questions': [{'question': 'Which branch should I base this on?', 'options': [{'label': 'main'}, {'label': 'dev'}]}]}


def pane(tid, store, sid='run1', ext='sess-1'):
    return SimpleNamespace(sid=sid, alive=True, task_id=tid, cwd=CWD, agent='coding', label='coding', argv=['claude'], last=1.0,
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

    def test_a_question_asked_again_after_its_answer_is_not_held_out_of_sight(self):
        """Its id is its words, and that id is answered - so the second asking was recorded but never shown, while the hook
        held Claude on "running PreToolUse hook" for the whole ASK_WAIT."""
        th = threading.Thread(target=ask, daemon=True); th.start()
        for _ in range(250):
            if ws.HELD: break
            time.sleep(0.02)
        rid = ws.status(self.s, self.tid)['requests'][0]['request_id']
        ws.answer_group(self.s, self.tid, {rid: 'main'}, 'owner'); th.join(5)
        self.assertEqual(self.open_(), [])
        t0 = time.monotonic(); out = ask(wait=30)
        self.assertLess(time.monotonic() - t0, 2, 'let go at once - the form goes in the pane')
        self.assertEqual((out, ws.HELD), ({}, {}))

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

    def test_it_waits_on_its_own_threads_not_the_shared_pool(self):
        """A sync route takes one of anyio's forty threads: behind them the question was recorded nowhere at all."""
        self.assertTrue(inspect.iscoroutinefunction(server.cli_hook_ask))
        src = inspect.getsource(server.cli_hook_ask)
        self.assertIn('_PERMIT_POOL', src)


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


if __name__ == '__main__':
    unittest.main()
