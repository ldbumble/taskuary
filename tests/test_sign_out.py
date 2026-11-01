"""Signing out of the CLI in the Agent pane is not the agent finishing (the owner, 2026-11-01: "if you hit logout on agent
working in the agent pane (claude cli) the agent closes instead of letting me logout and log back in").

Claude Code's /logout clears its sign-in, prints LOGGED_OUT and exits 0 a moment later, its SessionEnd hook saying reason
"logout"; Codex's /logout deletes its stored sign-in and exits. The pty's EOF read as the session ending: the task went back
to open with "nobody is working it" and the pane fell to the Result. Now the same CLI opens again in the same pane, on the
same conversation, with nothing typed into its sign-in."""
import os, sys, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import hooks, terminal, workerstate as ws
from taskuary.store import MemoryStore

ECHO = [sys.executable, '-c', "print('hello-from-pty')"]      # a reviewed child (conftest); what it says comes from Pty below


class Pty:
    """The CLI's last screen, then EOF - what a pty gives back when the process exits."""
    said = ''
    def __init__(self, *a, **kw): self.out = [self.said, '']
    def read(self): return self.out.pop(0) if self.out else ''
    def write(self, s): pass
    def resize(self, r, c): pass
    def alive(self): return False
    def kill(self): pass


def _wait(fn, secs=25):
    end = time.time() + secs
    while time.time() < end:
        if fn(): return True
        time.sleep(0.05)
    return False


def working(s):
    return s.create_task({'Title': 'Fix the nightly export', 'Kind': 'coding', 'Status': 'in_progress', 'Assignee': 'agent:coding'}, 'owner')


class SignedOutExitTests(unittest.TestCase):
    def _run(self, said, cli='claude'):
        s = MemoryStore(); tid = working(s)
        again = SimpleNamespace(sid='fresh', relogin=False)
        pty = type('P', (Pty,), {'said': said})
        with mock.patch.object(terminal, 'open_session', return_value=again) as op, mock.patch('taskuary.wrapup.wrap') as wrap,                 mock.patch.object(terminal, '_WinPty', pty), mock.patch.object(terminal, '_UnixPty', pty):
            t = terminal.Term(ECHO, os.getcwd(), 'coding', tid, 'coding', store=s, cli=cli)
            t.ext_id = 'conv-1'; terminal.SESSIONS[t.sid] = t
            try: self.assertTrue(_wait(lambda: t.ended is not None and (op.called or t.sid not in terminal.SESSIONS or
                                                                      s.get_task(tid)['Status'] == 'open')))
            finally: terminal.SESSIONS.pop(t.sid, None)
            time.sleep(.3)
        return s, tid, t, op, wrap, again

    def test_claude_logout_reopens_the_same_conversation_and_the_task_stays_worked(self):
        s, tid, t, op, wrap, again = self._run(f'\x1b[2K  {terminal.LOGGED_OUT}.\r\n')
        op.assert_called_once()
        a, kw = op.call_args
        self.assertEqual((a[1], a[2], a[4]), ('coding', tid, t.cwd))
        self.assertEqual(kw['resume'], 'conv-1')
        self.assertIsNone(kw.get('seed_fn'), 'nothing is typed into its sign-in')
        self.assertTrue(again.relogin)
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')
        bodies = ' '.join(c.get('Body') or '' for c in s.list_comments(tid))
        self.assertNotIn('nobody is working it', bodies)
        self.assertIn('Signed out - sign in again here', bodies)
        wrap.assert_not_called()

    def test_a_plain_exit_still_ends_the_session(self):
        s, tid, t, op, wrap, _ = self._run('bye\r\n')
        op.assert_not_called()
        self.assertTrue(_wait(lambda: s.get_task(tid)['Status'] == 'open'))


class SignedOutTests(unittest.TestCase):
    def _t(self, **kw):
        return SimpleNamespace(**{'task_id': 7, 'agent': 'coding', 'cli': 'claude', 'on_purpose': False, 'signed_out': False,
                                  'relogin': False, 'tail_chars': lambda n: 'bye', **kw})

    def test_the_hook_saying_logout_is_enough(self):
        self.assertTrue(terminal.signed_out(self._t(signed_out=True)))
        self.assertFalse(terminal.signed_out(self._t()))

    def test_a_close_is_never_a_sign_out(self):
        self.assertFalse(terminal.signed_out(self._t(signed_out=True, on_purpose=True)))

    def test_codex_is_asked_whether_it_is_still_signed_in(self):
        with mock.patch('taskuary.clisetup.signed_in', return_value=False) as si:
            self.assertTrue(terminal.signed_out(self._t(cli='codex')))
            si.assert_called_once_with('codex')
            # ...once: a reopened sign-in quit unsigned is the owner leaving, not a second sign-out
            self.assertFalse(terminal.signed_out(self._t(cli='codex', relogin=True)))
        with mock.patch('taskuary.clisetup.signed_in', return_value=True):
            self.assertFalse(terminal.signed_out(self._t(cli='codex')))


class LogoutHookTests(unittest.TestCase):
    def test_session_end_logout_marks_the_pane_and_writes_no_ending(self):
        s = MemoryStore(); tid = working(s)
        t = SimpleNamespace(store=s, task_id=tid, sid='pane-1', bg={}, cli='claude', argv=['claude'])
        ws.record(s, tid, 'pane-1', 'working', source='hook')
        hooks._events(t, {'hook_event_name': 'SessionEnd', 'reason': 'logout'})
        ended = lambda: [e for e in ws.events(s, tid, 'pane-1') if e['Kind'] == 'disconnected']
        self.assertTrue(t.signed_out)
        self.assertEqual(ended(), [])
        hooks._events(t, {'hook_event_name': 'SessionEnd', 'reason': 'prompt_input_exit'})
        self.assertEqual(len(ended()), 1)


if __name__ == '__main__':
    unittest.main()
