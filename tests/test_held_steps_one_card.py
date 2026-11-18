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
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Ship the portal fix to deploy')

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
        [t] = told; self.assertIn('step 2 failed', t)

    def test_a_step_that_failed_is_over_and_the_agents_never_a_card_still_lit(self):
        # the owner, 2026-11-10 ("no idea what this is. it's broken"): "1 of 2 ran - the rest wait" with Approve lit under the failure; the agent,
        # told they still waited, worked the failure while his next press ran the same step into it again
        ids, out, ran, told, _ = self.run_all([0, 1, 0])
        self.assertEqual([self.s.get_review(i)['Status'] for i in ids], ['approved', 'superseded', 'superseded'])
        self.assertIn('The held step failed', self.s.get_review(ids[1])['ActError'])
        self.assertIsNone(proposals.held_pending(self.s, self.tid), 'nothing on the card waits on him')
        [t] = told; self.assertIn('Nothing on that card waits on the owner now', t); self.assertIn('held as a new card', t)
        again = sg.approve_steps(self.s, ids[1:], verdicts.decide)                      # a second press on the old card runs nothing
        self.assertFalse(again['ok']); self.assertEqual(len(ran), 2)

    def test_the_failure_is_the_line_that_says_why_never_the_list_of_files(self):
        said = 'U site/a.js\nU site/b.js\nerror: Merging is not possible because you have unmerged files.\nhint: Fix them up\nfatal: Exiting.'
        self.assertEqual(sg.failed(said, 128), 'The held step failed: error: Merging is not possible because you have unmerged files.')
        self.assertEqual(sg.failed('To example.com:org/app.git\n ! [rejected] master -> master (fetch first)\nerror: failed to push some refs', 1),
                         'The held step failed: error: failed to push some refs')
        self.assertEqual(sg.failed('', 3), 'The held step failed: exit 3')

    def test_a_press_while_its_agent_works_in_that_folder_runs_nothing_and_says_so(self):
        busy = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, busy=True)
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': busy}, clear=True):
            ids, out, ran, told, _ = self.run_all([0, 0, 0])
        self.assertFalse(out['ok']); self.assertEqual(out['busy'], sg.BUSY); self.assertEqual(ran, [])
        self.assertEqual([self.s.get_review(i)['Status'] for i in ids], ['pending'] * 3); self.assertEqual(told, [])

    def test_a_single_press_while_its_agent_works_waits_lit_and_wakes_nobody(self):
        # the phone's or the assistant's Approve on one held step (verdicts.decide, not the card's /steps): the busy refusal was raised inside
        # the act, so the card was settled as failed - "press it again once its turn has ended" over a card with no Approve left - and the
        # agent, mid-turn, was woken with "IT FAILED"
        rv, told = self.hold('git push origin deploy'), []
        busy = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, busy=True)
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': busy}, clear=True), \
             mock.patch.object(general, 'tell', lambda st, t, said, *a, **k: told.append(said) or 'told'):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertEqual(out['busy'], sg.BUSY); self.assertFalse(out.get('act_failed'))
        r = self.s.get_review(rv['ReviewId']); self.assertEqual(r['Status'], 'pending', 'still lit for the press it asks for'); self.assertFalse(r.get('ActError'))
        self.assertEqual(told, [], 'nothing ran, nothing to tell')

    def test_a_read_let_in_while_its_agent_works_is_granted_at_once(self):
        # a read outside the task's folders runs nothing in the agent's folder: its yes never waits on the turn
        sg.check(self.s, self.tid, 'run1', '', 'Bash', HELD, reads=[{'tool': 'read', 'what': 'read files outside this task', 'why': 'outside its folders', 'folder': '/srv/shared'}])
        rv = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (self.tid,))[-1]
        busy = SimpleNamespace(sid='run1', alive=True, task_id=self.tid, busy=True)
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': busy}, clear=True), mock.patch.object(sg, '_tell', lambda *a, **k: None):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertTrue(out['ok'], out); self.assertEqual(self.s.get_review(rv['ReviewId'])['Status'], 'approved')

    def test_one_dismiss_dismisses_them_all_and_the_agent_hears_once(self):
        ids, out, ran, told, _ = self.run_all([0, 0, 0], 'reject')
        self.assertEqual(ran, []); self.assertEqual([self.s.get_review(i)['Status'] for i in ids], ['rejected'] * 3)
        [t] = told; self.assertIn('NOT done', t)

    def test_a_second_press_on_an_answered_card_runs_nothing_and_tells_nobody(self):
        # a double click, or the card pressed again from a page or phone that had not read the first press: the steps were already approved
        # (or dismissed), so nothing failed - the agent was woken with "step 1 failed: this one was already approved" and the card read it
        for verb in ('approve', 'reject'):
            with self.subTest(verb=verb):
                self.setUp(); ids, *_ = self.run_all([0, 0, 0], verb)
                told = []
                with mock.patch.object(sg, '_tell', lambda st, tid, t, **k: told.append(t)):
                    again = sg.approve_steps(self.s, ids, verdicts.decide, 'owner', verb)
                self.assertEqual(told, [], 'the agent heard the press once, at the first')
                self.assertFalse(again['ok']); self.assertIsNone(again['failed'], 'nothing failed'); self.assertTrue(again.get('already'))
                self.assertEqual({self.s.get_review(i)['Status'] for i in ids}, {'approved' if verb == 'approve' else 'rejected'})

    def test_a_step_answered_on_its_own_stops_the_card_without_a_failure_and_the_agent_hears_what_ran(self):
        ids = [self.hold(c)['ReviewId'] for c in ('git push origin deploy', 'git push origin master')]
        verdicts.decide(self.s, self.s.get_review(ids[1]), 'reject')           # step 2 dismissed from an older card
        told = []
        def run(argv, **k): return SimpleNamespace(returncode=0, stdout=b'ok', stderr=b'')
        with mock.patch('taskuary.spawn.run', run), mock.patch.object(sg.os.path, 'isdir', lambda p: p == HELD), \
             mock.patch.object(sg, 'git_bash', return_value='bash'), mock.patch.object(sg, '_tell', lambda st, tid, t, **k: told.append(t)):
            out = sg.approve_steps(self.s, ids, verdicts.decide)
        self.assertIsNone(out['failed']); self.assertEqual([d['review'] for d in out['done']], [ids[0]])
        self.assertEqual(self.s.get_review(ids[1])['Status'], 'rejected', 'its own answer stands')
        [t] = told; self.assertIn('git push origin deploy', t); self.assertNotIn('failed', t)

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
        self.assertIn('never ask them to run it', said); self.assertIn('print it for them to copy', said)
        from taskuary.selfclose import CARD_TAIL
        self.assertIn(CARD_TAIL, said)                    # ...and the one tail every hold ends on: the card says it waits, so the agent never does


if __name__ == '__main__': unittest.main()
