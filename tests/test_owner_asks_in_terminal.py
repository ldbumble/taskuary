"""The owner's own coding agent asks in its own terminal (the owner, 2026-10-21: "no need to add a layer on the terminal.
Just show the emoji terminal stopped and that will tell the user to answer the question").

The ask hook used to HOLD Claude's AskUserQuestion on the owner's task while the question waited in the Assistant: the pane
sat on "running PreToolUse hook" and looked stuck. Now the hook lets go at once, Claude draws its own form, and the open
request it recorded is what puts the task in the waiting-on-you lane - 👋 "<agent> asked you: ..." on the rail, the Board
and the agent's work line. A stranger's session is still held, and its permit still waits on Allow/Deny."""
import json, threading, time, unittest
from pathlib import Path
from types import SimpleNamespace

from taskuary import funnel, hooks, terminal as term, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

CWD = r'C:\code\repo'
Q = 'Which branch should I base this on?'
ONE = {'questions': [{'question': Q, 'options': [{'label': 'main'}, {'label': 'dev'}]}]}
SPIN = ['✻ Pondering… (esc to interrupt)']


def pane(tid, store, mode='full'):
    return SimpleNamespace(sid='run1', mode=mode, alive=True, task_id=tid, cwd=CWD, agent='coding', label='coding', argv=['claude'], last=1.0,
                           ext_id='sess-1', resumed_from='', store=store, witness=SimpleNamespace(note=lambda n: None), n=0,
                           tail=lambda n=3: SPIN, status_tail=lambda n=6: SPIN, waiting=lambda: False)


def payload(ev='PreToolUse', **kw): return {'hook_event_name': ev, 'tool_name': 'AskUserQuestion', 'session_id': 'sess-1', 'cwd': CWD, 'tool_input': ONE, **kw}


class Base(unittest.TestCase):
    mode = 'full'
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the export', kind='coding')
        self._sessions = dict(term.SESSIONS); term.SESSIONS.clear(); ws.HELD.clear()
        self.t = pane(self.tid, self.s, self.mode); term.SESSIONS['run1'] = self.t

    def tearDown(self): term.SESSIONS.clear(); term.SESSIONS.update(self._sessions); ws.HELD.clear()


class TheOwnersQuestion(Base):
    def test_it_is_not_held_claude_draws_its_form_at_once(self):
        t0 = time.monotonic(); out = hooks.ask(payload(), wait=30)
        self.assertLess(time.monotonic() - t0, 2, 'let go at once - the pane asks it')
        self.assertEqual((out, ws.HELD), ({}, {}))

    def test_the_task_says_it_is_waiting_on_you_with_the_question(self):
        hooks.ask(payload(), wait=30)
        w = term.worker_fields(self.s, self.t)
        self.assertEqual((w['waiting'], w['state'], w['held']), (True, 'asking', False))
        self.assertEqual(w['line'], ws.says('asking', 'coding', Q))
        self.assertEqual(w['line'], f'coding asked you: {Q}')

    def test_the_rail_and_board_put_it_in_the_waving_lane(self):
        hooks.ask(payload(), wait=30)
        live = [{'taskId': self.tid, 'agent': 'coding', 'sid': 'run1', 'tail': SPIN, **term.worker_fields(self.s, self.t)}]
        card = funnel.from_agents(self.s, live_state=live)[0]
        self.assertEqual((card['lane'], card['asking'], card['held']), ('blocked', True, False))
        lanes = json.loads((Path(funnel.__file__).parent / 'lanes.json').read_text(encoding='utf-8'))['lanes']
        self.assertEqual(next(l for l in lanes if l['key'] == 'blocked')['mark'], '👋', 'the existing waiting-on-you emoji, nothing new')

    def test_picked_in_the_pane_it_is_no_longer_waiting(self):
        hooks.ask(payload(), wait=30)
        hooks.receive(payload('PostToolUse', tool_response={'answers': {Q: 'main'}}), 'claude')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])
        self.assertIsNone(term.worker_fields(self.s, self.t)['state'])

    def test_a_permission_prompt_is_never_held_either_and_waves_too(self):
        """Claude's own "Do you want to proceed?" on the owner's task: observed, never answered or held by Taskuary."""
        out = hooks.receive({'hook_event_name': 'PermissionRequest', 'tool_name': 'Bash', 'session_id': 'sess-1', 'cwd': CWD,
                             'tool_input': {'command': 'npm install'}}, 'claude')
        self.assertNotIn('hookSpecificOutput', out)
        self.assertEqual(ws.HELD, {})
        w = term.worker_fields(self.s, self.t)
        self.assertEqual((w['waiting'], w['state']), (True, 'approval'))


class AStrangersQuestion(Base):
    mode = 'auto'
    def test_is_still_held_for_the_owner(self):
        th = threading.Thread(target=lambda: hooks.ask(payload(), wait=5), daemon=True); th.start()
        for _ in range(250):
            if ws.HELD: break
            time.sleep(0.02)
        self.assertTrue(ws.HELD, "a stranger's session is held, as before")
        ws.release(self.tid); th.join(5)


if __name__ == '__main__': unittest.main()
