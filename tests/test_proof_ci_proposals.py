"""The three execution-core additions: proof of work (evidence, incl. what is MISSING),
the CI loop (draft PR + red build handed back to the agent), and typed proposals (an agent
asks, deterministic code validates, you approve). HTTP and pty faked.
"""
import json, unittest
from unittest import mock

from taskuary import ci, github, proof, proposals, terminal, verdicts
from taskuary.store import MemoryStore

DIFF = '''diff --git a/taskuary/pto.py b/taskuary/pto.py
--- a/taskuary/pto.py
+++ b/taskuary/pto.py
@@ -1,3 +1,4 @@
-old line
+new line
+another
diff --git a/tests/test_pto.py b/tests/test_pto.py
--- a/tests/test_pto.py
+++ b/tests/test_pto.py
@@ -0,0 +1 @@
+def test_it(): pass
'''


class ProofTests(unittest.TestCase):
    def test_files_and_diffstat(self):
        f = proof.files_from(DIFF)
        self.assertEqual([x['path'] for x in f], ['taskuary/pto.py', 'tests/test_pto.py'])
        self.assertEqual((f[0]['added'], f[0]['removed']), (2, 1))

    def test_tests_from_transcript(self):
        self.assertEqual(proof.tests_from('...\n322 passed in 100.54s\n')['passed'], 322)
        r = proof.tests_from('12 passed, 3 failed in 4.10s')
        self.assertEqual((r['passed'], r['failed'], r['runner']), (12, 3, 'pytest'))
        # pytest's REAL order puts failures first - a passed-first pattern read every red run as green
        r = proof.tests_from('=== 1 failed, 12 passed, 2 skipped in 3.20s ===')
        self.assertEqual((r['passed'], r['failed']), (12, 1))
        self.assertEqual(proof.tests_from('3 failed, 2 passed, 1 error in 1.0s')['failed'], 4)
        self.assertEqual(proof.tests_from('Tests:  2 failed, 9 passed')['failed'], 2)
        # the LAST run is the truth: a fixed suite must not report the earlier failure
        self.assertEqual(proof.tests_from('5 passed, 2 failed in 1s\n...\n7 passed in 2s')['failed'], 0)

    def test_merely_mentioning_pytest_is_not_a_result(self):
        self.assertFalse(proof.tests_from('I will now run pytest on the suite')['ran'])
        self.assertFalse(proof.tests_from('')['ran'])

    def test_gather_states_the_gaps(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'PTO rounding', 'Kind': 'coding', 'Status': 'waiting'}, 't')
        rid = s.start_run(tid, 'coder', 'fix it', 'owner')
        s.update_run(rid, {'Status': 'done', 'DiffText': DIFF}, finished=True)
        with mock.patch.object(terminal, 'transcript_for', return_value=('12 passed in 3s', 'claude', 'sid')):
            p = proof.gather(s, tid)
        self.assertEqual(p['diffstat']['files'], 2)
        self.assertTrue(p['tests']['ran'])
        self.assertIn('not landed anywhere yet - no pull request and nothing pushed', p['gaps'])

    def test_gather_is_honest_when_empty(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'nothing', 'Kind': 'coding', 'Status': 'open'}, 't')
        with mock.patch.object(terminal, 'transcript_for', return_value=('', None, None)):
            p = proof.gather(s, tid)
        self.assertEqual(p['diffstat']['files'], 0)
        self.assertTrue(any('no file changes' in g for g in p['gaps']))
        self.assertTrue(any('no test run' in g for g in p['gaps']))


class ChecksTests(unittest.TestCase):
    def _resp(self, j, code=200):
        class R:
            status_code = code
            def json(self_inner): return j
            def raise_for_status(self_inner): pass
        return R()

    def test_failure_names_what_failed(self):
        runs = {'check_runs': [{'name': 'ci / test (3.10)', 'status': 'completed', 'conclusion': 'failure',
                                'html_url': 'u', 'output': {'summary': '2 tests failed'}},
                               {'name': 'ci / build', 'status': 'completed', 'conclusion': 'success'}]}
        with mock.patch('requests.get', side_effect=[self._resp(runs), self._resp({'statuses': []})]):
            ck = github.checks('t', 'o/r', 'sha')
        self.assertEqual(ck['state'], 'failure')
        self.assertEqual([f['name'] for f in ck['failed']], ['ci / test (3.10)'])

    def test_pending_and_none(self):
        with mock.patch('requests.get', side_effect=[self._resp({'check_runs': [{'name': 'x', 'status': 'in_progress'}]}),
                                                     self._resp({'statuses': []})]):
            self.assertEqual(github.checks('t', 'o/r', 's')['state'], 'pending')
        with mock.patch('requests.get', side_effect=[self._resp({'check_runs': []}), self._resp({'statuses': []})]):
            self.assertEqual(github.checks('t', 'o/r', 's')['state'], 'none')


def armed(s, ci_watch='feedback'):
    cid = s.get_connector_by_type('github')['ConnectorId']
    s.save_connector({'ConnectorId': cid, 'Secret': 'ghp_x', 'Active': 1}, 't')
    s.set_setting('ci_watch', ci_watch, 't')
    s.set_setting('agent_push_enabled', '1', 't')
    return s


class CiLoopTests(unittest.TestCase):
    def _task_with_pr(self, s):
        tid = s.create_task({'Title': 'importer', 'Kind': 'coding', 'Status': 'waiting'}, 't')
        ci._save_pr(s, tid, {'repo': 'o/r', 'number': 7, 'url': 'https://gh/pr/7', 'state': 'open'})
        return tid

    def test_red_build_reaches_the_agent_once(self):
        s = armed(MemoryStore()); tid = self._task_with_pr(s)
        fresh = {'number': 7, 'url': 'u', 'head': 'fix', 'sha': 'abc1234def', 'state': 'open'}
        ck = {'state': 'failure', 'total': 2, 'pending': 0,
              'failed': [{'name': 'ci / test', 'url': 'u', 'summary': '2 failed'}]}
        with mock.patch.object(github, 'pr', return_value=fresh), mock.patch.object(github, 'checks', return_value=ck), \
             mock.patch.object(terminal, 'say_to_task', return_value=True) as say:
            out = ci.check_task(s, tid)
            self.assertEqual((out['state'], out['fed'], out['handed']), ('failure', True, True))
            self.assertIn('ci / test', say.call_args[0][2]['BodyText'])
            again = ci.check_task(s, tid)      # same commit, same failures: told once
        self.assertFalse(again['fed'])

    def test_no_live_session_puts_it_back_on_the_owner(self):
        s = armed(MemoryStore()); tid = self._task_with_pr(s)
        with mock.patch.object(github, 'pr', return_value={'number': 7, 'url': 'u', 'head': 'f', 'sha': 'z', 'state': 'open'}), \
             mock.patch.object(github, 'checks', return_value={'state': 'failure', 'total': 1, 'pending': 0,
                                                              'failed': [{'name': 'lint', 'url': '', 'summary': ''}]}), \
             mock.patch.object(terminal, 'say_to_task', return_value=False):
            ci.check_task(s, tid)
        self.assertEqual(s.get_task(tid)['Status'], 'open')

    def test_green_says_nothing(self):
        s = armed(MemoryStore()); tid = self._task_with_pr(s)
        with mock.patch.object(github, 'pr', return_value={'number': 7, 'url': 'u', 'head': 'f', 'sha': 'z', 'state': 'open'}), \
             mock.patch.object(github, 'checks', return_value={'state': 'success', 'total': 3, 'pending': 0, 'failed': []}), \
             mock.patch.object(terminal, 'say_to_task') as say:
            out = ci.check_task(s, tid)
        self.assertEqual(out['state'], 'success'); say.assert_not_called()

    def test_poll_is_off_by_default(self):
        s = MemoryStore()
        self.assertEqual(s.get_settings()['ci_watch'], 'off')
        self.assertEqual(ci.poll(s), 0)

    def test_pr_needs_the_push_switch(self):
        s = MemoryStore()
        cid = s.get_connector_by_type('github')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'Secret': 'x', 'Active': 1}, 't')
        tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'open'}, 't')
        with self.assertRaises(RuntimeError) as e: ci.open_for_task(s, tid)
        self.assertIn('pushing is off', str(e.exception))


class FakeSession:
    def __init__(self, cwd='C:/repo'): self.cwd, self.alive, self.task_id, self.n = cwd, True, 1, 0


def git_says(**answers):
    """Fake taskuary.agents._git and _git_rc: keyed on the first arg of the git command. A push
    answer that says 'rejected' comes back with git's non-zero exit, as the real one does."""
    import contextlib
    def _g(cwd, *args, **kw): return answers.get(args[0], '')
    def _rc(cwd, *args, **kw): out = answers.get(args[0], ''); return (1 if 'rejected' in out else 0), out
    stack = contextlib.ExitStack()
    stack.enter_context(mock.patch('taskuary.agents._git', _g)); stack.enter_context(mock.patch('taskuary.agents._git_rc', _rc))
    return stack


class DirectPushTests(unittest.TestCase):
    """git_flow=direct: the commits already in the checkout go straight onto the default
    branch. Deliberately narrow, and every refusal is one the owner can act on."""
    def _armed(self):
        s = armed(MemoryStore())
        cid = s.get_connector_by_type('github')['ConnectorId']
        s.save_connector({'ConnectorId': cid, 'ConfigJson': json.dumps({'default_repo': 'o/r', 'default_base': 'main'})}, 't')
        s.set_setting('git_flow', 'direct', 't')
        tid = s.create_task({'Title': 'fix the importer', 'Kind': 'coding', 'Status': 'waiting'}, 't')
        return s, tid

    def test_pushes_and_records_where_it_went(self):
        s, tid = self._armed()
        with mock.patch.object(terminal, 'session_for', return_value=FakeSession()), \
             mock.patch.object(terminal, 'guess_repo', return_value=('o/r', '')), \
             git_says(**{'status': '', 'rev-list': '2', 'rev-parse': 'abc1234def567', 'push': 'Everything up-to-date', 'fetch': ''}):
            out = ci.push_direct(s, tid)
        self.assertEqual((out['branch'], out['commits'], out['sha'][:7]), ('main', 2, 'abc1234'))
        at = ci.landing_of(s, tid)
        self.assertEqual((at['kind'], at['branch']), ('push', 'main'))
        self.assertTrue(any('straight to main' in c['Body'] for c in s.list_comments(tid)))

    def test_dirty_checkout_is_refused_not_committed(self):
        s, tid = self._armed()
        with mock.patch.object(terminal, 'session_for', return_value=FakeSession()), \
             mock.patch.object(terminal, 'guess_repo', return_value=('o/r', '')), \
             git_says(**{'status': ' M taskuary/x.py', 'rev-list': '1'}):
            with self.assertRaises(RuntimeError) as e: ci.push_direct(s, tid)
        self.assertIn('uncommitted changes', str(e.exception))

    def test_nothing_ahead_is_nothing_to_do(self):
        s, tid = self._armed()
        with mock.patch.object(terminal, 'session_for', return_value=FakeSession()), \
             mock.patch.object(terminal, 'guess_repo', return_value=('o/r', '')), \
             git_says(**{'status': '', 'rev-list': '0', 'fetch': ''}):
            with self.assertRaises(RuntimeError) as e: ci.push_direct(s, tid)
        self.assertIn('nothing to push', str(e.exception))

    def test_a_silent_non_zero_exit_is_a_refusal_too(self):
        """git writes push output to stderr and _git() returned '' for any failure - so a rejected
        push used to be filed as 'Pushed' (audit 2026-09-02)."""
        s, tid = self._armed()
        with mock.patch.object(terminal, 'session_for', return_value=FakeSession()), \
             mock.patch.object(terminal, 'guess_repo', return_value=('o/r', '')), \
             git_says(**{'status': '', 'rev-list': '1', 'rev-parse': 'z', 'fetch': ''}), \
             mock.patch('taskuary.agents._git_rc', lambda cwd, *a, **k: (128, '')):
            with self.assertRaises(RuntimeError) as e: ci.push_direct(s, tid)
        self.assertIn('git refused the push', str(e.exception))
        self.assertIsNone(ci.landing_of(s, tid))

    def test_rejected_push_is_never_forced(self):
        s, tid = self._armed()
        with mock.patch.object(terminal, 'session_for', return_value=FakeSession()), \
             mock.patch.object(terminal, 'guess_repo', return_value=('o/r', '')), \
             git_says(**{'status': '', 'rev-list': '1', 'rev-parse': 'z', 'fetch': '',
                         'push': '! [rejected] main -> main (fetch first)'}):
            with self.assertRaises(RuntimeError) as e: ci.push_direct(s, tid)
        self.assertIn('never force-pushes', str(e.exception))

    def test_push_still_needs_the_switch(self):
        s, tid = self._armed()
        s.set_setting('agent_push_enabled', '0', 't')
        with self.assertRaises(RuntimeError) as e: ci.push_direct(s, tid)
        self.assertIn('pushing is off', str(e.exception))

    def test_land_follows_the_setting(self):
        s, tid = self._armed()
        with mock.patch.object(ci, 'push_direct', return_value={'sha': 'x'}) as direct, \
             mock.patch.object(ci, 'open_for_task') as pr:
            ci.land(s, tid)
        direct.assert_called_once(); pr.assert_not_called()
        s.set_setting('git_flow', 'pr', 't')
        with mock.patch.object(ci, 'push_direct') as direct2, \
             mock.patch.object(ci, 'open_for_task', return_value={'number': 1}) as pr2:
            ci.land(s, tid)
        pr2.assert_called_once(); direct2.assert_not_called()

    def test_ci_feedback_on_a_direct_push_says_it_is_already_on_the_branch(self):
        s, tid = self._armed()
        ci._save_push(s, tid, {'repo': 'o/r', 'branch': 'main', 'sha': 'abc1234def', 'state': 'pushed'})
        ck = {'state': 'failure', 'total': 1, 'pending': 0,
              'failed': [{'name': 'ci / test', 'url': 'u', 'summary': '1 failed'}]}
        with mock.patch.object(github, 'checks', return_value=ck), \
             mock.patch.object(terminal, 'say_to_task', return_value=True) as say:
            out = ci.check_task(s, tid)
        self.assertEqual((out['state'], out['kind']), ('failure', 'push'))
        told = say.call_args[0][2]['BodyText']
        self.assertIn('ALREADY on the branch', told)
        self.assertNotIn('do not merge', told)          # there is no PR to hold anything back


class ProposalTests(unittest.TestCase):
    def test_parse_and_validate(self):
        text = ('working…\nTASKUARY-PROPOSE {"action": "open_pr", "why": "tests pass"}\n'
                'TASKUARY-PROPOSE {"action": "nonsense"}\nTASKUARY-PROPOSE not json\n')
        ps = proposals.parse(text)
        self.assertEqual([p['action'] for p in ps], ['open_pr'])
        s = MemoryStore()
        ok, why = proposals.validate(s, ps[0])
        self.assertFalse(ok); self.assertIn('switch off', why)      # push is off by default
        s.set_setting('agent_push_enabled', '1', 't')
        self.assertTrue(proposals.validate(s, ps[0])[0])

    def test_collect_queues_a_review_and_records_refusals(self):
        s = MemoryStore(); s.set_setting('agent_push_enabled', '1', 't')
        tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'open'}, 't')
        made = proposals.collect(s, tid, 'TASKUARY-PROPOSE {"action": "open_pr", "why": "ready"}\n'
                                         'TASKUARY-PROPOSE {"action": "comment_issue", "body": "hi"}')
        self.assertEqual([m['action'] for m in made], ['open_pr'])   # replies switch is off
        rv = s.get_review(made[0]['reviewId'])
        self.assertEqual((rv['Kind'], rv['Status']), ('action', 'pending'))
        self.assertIn('DRAFT pull request', rv['Reason'])
        self.assertTrue(any('PROPOSAL REFUSED' in c['Body'] for c in s.list_comments(tid)))

    def test_approving_runs_it_and_rejecting_does_not(self):
        s = armed(MemoryStore()); tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'open'}, 't')
        rid = proposals.collect(s, tid, 'TASKUARY-PROPOSE {"action": "open_pr"}')[0]['reviewId']
        with mock.patch.object(ci, 'open_for_task', return_value={'number': 9, 'url': 'u'}) as op:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        op.assert_called_once()
        self.assertEqual((out['status'], out['result']['pr']), ('approved', 9))
        rid2 = proposals.collect(s, tid, 'TASKUARY-PROPOSE {"action": "open_pr"}')[0]['reviewId']
        with mock.patch.object(ci, 'open_for_task') as op2:
            verdicts.decide(s, s.get_review(rid2), 'reject')
        op2.assert_not_called()
        self.assertEqual(s.get_review(rid2)['Status'], 'rejected')

    def test_permission_revoked_between_propose_and_approve(self):
        s = armed(MemoryStore()); tid = s.create_task({'Title': 't', 'Kind': 'coding', 'Status': 'open'}, 't')
        rid = proposals.collect(s, tid, 'TASKUARY-PROPOSE {"action": "open_pr"}')[0]['reviewId']
        s.set_setting('agent_push_enabled', '0', 't')                # owner changed their mind
        with mock.patch.object(ci, 'open_for_task') as op:
            out = verdicts.decide(s, s.get_review(rid), 'approve')
        op.assert_not_called()
        self.assertFalse(out['ok']); self.assertIn('refused at execution', out['send_error'])


if __name__ == '__main__':
    unittest.main()
