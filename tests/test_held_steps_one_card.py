"""ONE CARD, ONE APPROVE FOR A TURN'S HELD STEPS (the owner, 2026-11-09: "this should be one action button and one card"): steps held under the
same owner line share a turn; the one Approve runs each through the same decide door, in order, stops at the first failure and says which,
and the agent hears once."""
import json, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import general, proposals, shellgate as sg, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

HELD = r'C:\work\portal'


class HeldStepsOneCard(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Ship the portal fix to deploy'); proposals._PRESSED.clear()

    def hold(self, cmd):
        sg.check(self.s, self.tid, 'run1', cmd, 'Bash', HELD)
        return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending' ORDER BY ReviewId", (self.tid,))[-1]

    def turn(self, rv): return json.loads(rv['DraftText'])['turn']

    def test_steps_under_one_owner_line_share_a_turn_and_a_later_line_starts_another(self):
        a, b = self.hold('git push origin deploy'), self.hold('git push origin master')
        self.assertEqual(self.turn(a), self.turn(b))
        self.s.add_comment(self.tid, 'owner', general.USER_TYPE, 'and tag it')
        self.assertNotEqual(self.turn(self.hold('git push origin v2')), self.turn(a))

    def run_all(self, rcs, verb='approve'):
        ids = [self.hold(c)['ReviewId'] for c in ('git push origin deploy', 'git push origin master', 'git push origin --tags')]
        ran, told, seen = [], [], []
        def run(argv, **k): ran.append(argv[-1]); rc = rcs[len(ran) - 1]; return SimpleNamespace(returncode=rc, stdout=b'ok' if not rc else b'rejected', stderr=b'')
        real = verdicts.decide
        def door(store, rv, v, **kw): seen.append(rv['ReviewId']); return real(store, rv, v, **kw)
        with mock.patch.object(sg.subprocess, 'run', run), mock.patch('taskuary.spawn.run', run), mock.patch.object(sg.os.path, 'isdir', lambda p: p == HELD), \
             mock.patch.object(sg, 'git_bash', return_value='bash'), mock.patch.object(sg, '_tell', lambda st, tid, t, **k: told.append(t)):
            out = sg.approve_steps(self.s, ids, door, 'owner', verb)
        return ids, out, ran, told, seen

    def test_one_approve_runs_every_step_in_order_through_the_decide_door_and_tells_the_agent_once(self):
        ids, out, ran, told, seen = self.run_all([0, 0, 0])
        self.assertTrue(out['ok']); self.assertEqual(seen, ids, 'each step through the one decide door, in order')
        self.assertEqual(ran, ['git push origin deploy', 'git push origin master', 'git push origin --tags'])
        self.assertEqual([self.s.get_review(i)['Status'] for i in ids], ['approved'] * 3)
        self.assertEqual(len(told), 1, told); self.assertIn('ran them in order', told[0])

    def test_it_stops_at_the_first_failure_and_says_which(self):
        ids, out, ran, told, _ = self.run_all([0, 1, 0])
        self.assertFalse(out['ok']); self.assertEqual(out['failed']['step'], 2); self.assertEqual(out['failed']['review'], ids[1])
        self.assertEqual(len(ran), 2, 'the third step never ran'); self.assertEqual(out['left'], [ids[2]])
        self.assertEqual([self.s.get_review(i)['Status'] for i in ids], ['approved', 'pending', 'pending'])
        [t] = told; self.assertIn('step 2 failed', t)

    def test_one_dismiss_dismisses_them_all_and_the_agent_hears_once(self):
        ids, out, ran, told, _ = self.run_all([0, 0, 0], 'reject')
        self.assertEqual(ran, []); self.assertEqual([self.s.get_review(i)['Status'] for i in ids], ['rejected'] * 3)
        [t] = told; self.assertIn('NOT done', t)

    def test_only_held_shell_steps_go_together(self):
        rid = Factory(self.s).review(self.tid, kind='action', reason='x', draft=json.dumps({'action': 'comment_issue', 'body': 'hi'}))
        with self.assertRaises(ValueError): sg.approve_steps(self.s, [rid if isinstance(rid, int) else rid['ReviewId']], verdicts.decide)

    def test_a_restart_keeps_every_held_step_of_the_turn(self):
        # the store's startup heal kept only the newest pending review of a kind per task: a turn's first push vanished on restart
        import os, tempfile
        from taskuary.store import SQLiteStore
        path = os.path.join(tempfile.mkdtemp(), 'held.db'); s = SQLiteStore(path); tid = Factory(s).task('Ship it')
        for c in ('git push origin deploy', 'git push origin master'): sg.check(s, tid, 'run1', c, 'Bash', HELD)
        self.assertEqual(len(SQLiteStore(path)._rows("SELECT 1 FROM review WHERE TaskId=? AND Status='pending'", (tid,))), 2)

    def test_the_hold_tells_the_agent_the_button_is_the_ask(self):
        said = sg.check(self.s, self.tid, 'run1', 'git push origin deploy', 'Bash', HELD)['hookSpecificOutput']['permissionDecisionReason']
        self.assertIn('never ask them to run it', said); self.assertIn('never print the command', said)


if __name__ == '__main__': unittest.main()
