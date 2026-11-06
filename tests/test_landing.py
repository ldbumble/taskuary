"""Landing a coding task's branch (landing.py): the diff since the task started, the one question - rebase and fast-forward, merge commit,
PR, discard (only for a branch of its own) - and nothing landed half-done: a conflict aborts and goes to the agent. A real git repo in a
temp folder, no network."""
import os, subprocess, tempfile, unittest
from unittest import mock

from taskuary import guard, landing
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def git(cwd, *a):
    return subprocess.run(['git', '-C', cwd, '-c', 'user.name=Alex Doyle', '-c', 'user.email=alex@northwind.example', *a],
                          capture_output=True, text=True, check=True).stdout.strip()


def commit(cwd, name, text, msg=None):
    with open(os.path.join(cwd, name), 'w', encoding='utf-8', newline='\n') as f: f.write(text)
    git(cwd, 'add', name); git(cwd, 'commit', '-q', '-m', msg or f'edit {name}')


class LandingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cwd = self.tmp.name
        git(self.cwd, 'init', '-q', '-b', 'master')
        for k, v in (('user.name', 'Alex Doyle'), ('user.email', 'alex@northwind.example')): git(self.cwd, 'config', k, v)
        commit(self.cwd, 'ledger.py', 'one\ntwo\nthree\n', 'start')
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the ledger rounding', kind='coding')
        landing.mark_start(self.s, self.tid, self.cwd)

    def tearDown(self):
        try: self.tmp.cleanup()
        except OSError: pass

    def branch(self, name='fix-rounding', text='one\nTWO\nthree\n'):
        git(self.cwd, 'checkout', '-q', '-b', name); commit(self.cwd, 'ledger.py', text)

    def sha(self, ref): return git(self.cwd, 'rev-parse', ref)

    def test_the_start_is_noted_once_and_a_continue_keeps_it(self):
        first = landing.record(self.s, self.tid)['start']
        commit(self.cwd, 'notes.md', 'x\n')
        self.assertIsNone(landing.mark_start(self.s, self.tid, self.cwd))
        self.assertEqual(landing.record(self.s, self.tid)['start'], first)

    def test_an_own_branch_shows_its_diff_and_all_four_answers(self):
        self.branch()
        s = landing.state(self.s, self.tid, full=True)
        self.assertTrue(s['ask'] and s['own'])
        self.assertEqual((s['branch'], s['base'], s['ahead'], s['changed'], s['plus'], s['minus']), ('fix-rounding', 'master', 1, 1, 1, 1))
        self.assertEqual([a['how'] for a in s['answers']], ['rebase', 'merge', 'pr', 'discard'])
        self.assertIn('+TWO', s['diff'])
        self.assertIn('How should it land?', s['line'])

    def test_changes_are_the_whole_work_so_far_committed_or_not_new_files_too(self):
        # the header's Changes (the owner, 2026-11-06: "where is the diff button to see code changed?"), while the agent still works
        self.branch()
        with open(os.path.join(self.cwd, 'ledger.py'), 'a', encoding='utf-8', newline='\n') as f: f.write('four\n')
        with open(os.path.join(self.cwd, 'rounding.py'), 'w', encoding='utf-8', newline='\n') as f: f.write('def r(x): return round(x, 2)\n')
        c = landing.changes(self.s, self.tid)
        self.assertEqual(c['base'], 'master')
        for line in ('+TWO', '+four', '+def r(x)', '+++ b/rounding.py'): self.assertIn(line, c['diff'])
        git(self.cwd, 'checkout', '-q', '--', 'ledger.py'); git(self.cwd, 'checkout', '-q', 'master')        # ...the checkout moved on: what it committed is what is its
        c = landing.changes(self.s, self.tid)
        self.assertIn('+TWO', c['diff']); self.assertNotIn('+four', c['diff'])
        self.assertIsNone(landing.changes(self.s, Factory(self.s).task(title='Never started', kind='coding')))

    def test_work_straight_on_the_base_asks_nothing_and_never_offers_discard(self):
        commit(self.cwd, 'ledger.py', 'one\nTWO\nthree\n')
        s = landing.state(self.s, self.tid)
        self.assertFalse(s['ask'] or s['own']); self.assertEqual(s['answers'], []); self.assertEqual(s['changed'], 1)
        with self.assertRaises(ValueError): landing.land(self.s, self.tid, 'discard')

    def test_rebase_fast_forwards_when_the_base_did_not_move(self):
        self.branch()
        out = landing.land(self.s, self.tid, 'rebase')
        self.assertTrue(out['ok']); self.assertEqual(self.sha('master'), self.sha('fix-rounding'))
        self.assertFalse(landing.state(self.s, self.tid)['ask'])           # landed: asked no more

    def test_rebase_onto_a_base_that_moved_is_linear(self):
        self.branch()
        git(self.cwd, 'checkout', '-q', 'master'); commit(self.cwd, 'portal.py', 'p\n'); git(self.cwd, 'checkout', '-q', 'fix-rounding')
        self.assertTrue(landing.land(self.s, self.tid, 'rebase')['ok'])
        self.assertEqual(self.sha('master'), self.sha('fix-rounding'))
        self.assertEqual(git(self.cwd, 'rev-list', '--count', '--merges', 'master'), '0')
        self.assertIn('portal.py', git(self.cwd, 'ls-tree', '--name-only', 'master'))

    def test_a_merge_commit_onto_an_unchecked_out_base_leaves_the_shared_tree_alone(self):
        self.branch()
        git(self.cwd, 'checkout', '-q', 'master'); commit(self.cwd, 'portal.py', 'p\n'); git(self.cwd, 'checkout', '-q', 'fix-rounding')
        with open(os.path.join(self.cwd, 'peer.txt'), 'w') as f: f.write('a peer agent is mid-edit\n')    # another agent's work in progress
        self.assertTrue(landing.land(self.s, self.tid, 'merge')['ok'])
        self.assertEqual(len(git(self.cwd, 'rev-list', '--parents', '-n', '1', 'master').split()), 3)   # two parents
        self.assertEqual(git(self.cwd, 'rev-parse', '--abbrev-ref', 'HEAD'), 'fix-rounding')
        self.assertTrue(os.path.exists(os.path.join(self.cwd, 'peer.txt')))

    def test_a_merge_conflict_lands_nothing_and_goes_to_the_agent(self):
        self.branch()
        git(self.cwd, 'checkout', '-q', 'master'); commit(self.cwd, 'ledger.py', 'one\nzwei\nthree\n'); git(self.cwd, 'checkout', '-q', 'fix-rounding')
        was = self.sha('master')
        out = landing.land(self.s, self.tid, 'merge')
        self.assertFalse(out['ok']); self.assertEqual(out['conflict'], ['ledger.py'])
        self.assertEqual(self.sha('master'), was)
        notes = self.s.waiting_notes(self.tid)
        self.assertTrue(notes and 'resolve these conflicts' in notes[0]['Note'].lower() and 'say done' in notes[0]['Note'])
        self.assertEqual(notes[0]['CreatedBy'], 'router')                   # Taskuary's words, never the owner's
        self.assertTrue(landing.state(self.s, self.tid)['ask'])              # still to land

    def test_a_rebase_conflict_is_aborted_and_the_checkout_is_as_it_was(self):
        self.branch()
        git(self.cwd, 'checkout', '-q', 'master'); commit(self.cwd, 'ledger.py', 'one\nzwei\nthree\n'); git(self.cwd, 'checkout', '-q', 'fix-rounding')
        tip, was = self.sha('fix-rounding'), self.sha('master')
        out = landing.land(self.s, self.tid, 'rebase')
        self.assertEqual(out['conflict'], ['ledger.py'])
        self.assertEqual((self.sha('fix-rounding'), self.sha('master')), (tip, was))
        self.assertEqual(git(self.cwd, 'rev-parse', '--abbrev-ref', 'HEAD'), 'fix-rounding')
        self.assertFalse(os.path.isdir(os.path.join(self.cwd, '.git', 'rebase-merge')))
        self.assertEqual(git(self.cwd, 'status', '--porcelain'), '')

    def test_discard_drops_only_the_agents_own_branch(self):
        self.branch()
        landing.land(self.s, self.tid, 'discard')
        self.assertNotIn('fix-rounding', git(self.cwd, 'branch', '--list'))
        self.assertEqual(git(self.cwd, 'rev-parse', '--abbrev-ref', 'HEAD'), 'master')

    def test_the_branch_is_kept_once_another_agent_switches_the_checkout(self):
        self.branch(); landing.seen(self.s, self.tid)
        git(self.cwd, 'checkout', '-q', 'master'); git(self.cwd, 'checkout', '-q', '-b', 'someone-elses')
        self.assertEqual(landing.state(self.s, self.tid)['branch'], 'fix-rounding')

    def test_the_agent_proposes_and_nothing_lands(self):
        self.branch()
        before = self.sha('master')
        self.assertTrue(landing.propose(self.s, self.tid, 'merge', 'the base moved twice today')['ok'])
        s = landing.state(self.s, self.tid)
        self.assertEqual(s['proposal']['how'], 'merge'); self.assertTrue(s['ask'])
        self.assertEqual(self.sha('master'), before)
        with self.assertRaises(ValueError): landing.propose(self.s, self.tid, 'force-push')

    def test_a_pr_pushes_and_opens_through_the_github_card(self):
        self.branch()
        remote = tempfile.mkdtemp(); git(remote, 'init', '-q', '--bare')
        git(self.cwd, 'remote', 'add', 'origin', remote)
        pr = {'number': 12, 'url': 'https://github.com/northwind/ledger/pull/12', 'head': 'fix-rounding', 'base': 'master', 'state': 'open'}
        with mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'), \
             mock.patch('taskuary.ci._conn', return_value={'Secret': 'tok'}), mock.patch('taskuary.github.open_pr', return_value=pr) as op:
            out = landing.land(self.s, self.tid, 'pr')
        self.assertTrue(out['ok']); self.assertEqual(out['pr'], 12)
        self.assertEqual(op.call_args[0][1:4], ('northwind/ledger', 'fix-rounding', 'master'))
        self.assertTrue(git(remote, 'rev-parse', 'fix-rounding'))


class LandingDoorTests(unittest.TestCase):
    def test_landing_is_the_owners_and_proposing_is_the_agents(self):
        self.assertEqual(guard.classify('POST', '/api/tasks/7/landing')[0], 'deny')
        self.assertEqual(guard.classify('POST', '/api/agent/propose-land')[0], 'agent')
        self.assertEqual(guard.classify('GET', '/api/tasks/7/landing')[0], 'read')

    def test_the_question_is_not_drawn_with_developer_mode_off(self):
        os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp())
        from fastapi.testclient import TestClient
        from taskuary import server
        with mock.patch.object(server.hub_agents, 'developer_mode', return_value=False):
            c = TestClient(server.app); tid = Factory(server.store).task(title='x', kind='coding')
            self.assertIsNone(c.get(f'/api/tasks/{tid}/landing').json()['data'])
            self.assertEqual(c.post(f'/api/tasks/{tid}/landing', json={'how': 'rebase'}).status_code, 409)
