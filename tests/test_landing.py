"""Landing a coding task's branch (landing.py): the diff since the task started, the one question - rebase and fast-forward, merge commit,
PR, discard (only for a branch of its own) - and nothing landed half-done: a conflict aborts and goes to the agent. A real git repo in a
temp folder, no network."""
import os, subprocess, tempfile, time, unittest
from unittest import mock

from taskuary import agenttools, guard, landing, shellgate
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def git(cwd, *a, env=None):
    return subprocess.run(['git', '-C', cwd, '-c', 'user.name=Alex Doyle', '-c', 'user.email=alex@northwind.example', *a],
                          capture_output=True, text=True, check=True, env={**os.environ, **(env or {})}).stdout.strip()


def commit(cwd, name, text, msg=None, env=None):
    with open(os.path.join(cwd, name), 'w', encoding='utf-8', newline='\n') as f: f.write(text)
    git(cwd, 'add', name); git(cwd, 'commit', '-q', '-m', msg or f'edit {name}', env=env)


class LandingTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cwd = self.tmp.name
        git(self.cwd, 'init', '-q', '-b', 'master')
        for k, v in (('user.name', 'Alex Doyle'), ('user.email', 'alex@northwind.example')): git(self.cwd, 'config', k, v)
        commit(self.cwd, 'ledger.py', 'one\ntwo\nthree\n', 'start')
        self.s = MemoryStore(); self.tid = Factory(self.s).task(title='Fix the ledger rounding', kind='coding')
        landing.mark_start(self.s, self.tid, self.cwd)
        self.s.add_transcript(self.tid, 'run1', 'Fixed the rounding.', 'claude', self.cwd)     # the agent that worked it: what landing tells

    def tearDown(self):
        try: self.tmp.cleanup()
        except OSError: pass

    def branch(self, name='fix-rounding', text='one\nTWO\nthree\n', ask=True):
        """The agent's branch, and - `ask` - the question it raised on it: the landing card is the agent's (the owner, 2026-11-27: "only the
        agent raises cards"), its unlanded work a fact (`owed`) until it does."""
        git(self.cwd, 'checkout', '-q', '-b', name); commit(self.cwd, 'ledger.py', text)
        if ask: landing.propose(self.s, self.tid, 'rebase')

    def sha(self, ref): return git(self.cwd, 'rev-parse', ref)

    def test_the_start_is_noted_once_and_a_continue_keeps_it(self):
        first = landing.record(self.s, self.tid)['start']
        commit(self.cwd, 'notes.md', 'x\n')
        self.assertIsNone(landing.mark_start(self.s, self.tid, self.cwd))
        self.assertEqual(landing.record(self.s, self.tid)['start'], first)

    def test_no_landing_card_stands_until_its_agent_raises_it_and_its_turn_end_says_the_work_is_not_landed(self):
        """The checkout's question stood by itself - a card no agent raised. Work not landed is a fact the agent is told as its turn ends;
        the card is its own ask, and nothing lands before his press on it."""
        from taskuary import agenttools
        self.branch(ask=False)
        s = landing.state(self.s, self.tid)
        self.assertTrue(s['owed']); self.assertFalse(s['ask'])
        with self.assertRaises(ValueError): landing.land(self.s, self.tid, 'rebase')          # ...nothing stands for his press
        said = agenttools.call(self.s, self.tid, 'end_turn', {'did': 'Fixed the rounding.'}, {})
        self.assertIn('fix-rounding is 1 commit ahead of master', said); self.assertIn('nothing lands without his press', said)
        landing.propose(self.s, self.tid, 'rebase')
        self.assertTrue(landing.state(self.s, self.tid)['ask'])
        self.assertNotIn('nothing lands', agenttools.call(self.s, self.tid, 'end_turn', {'did': 'Asked how it lands.'}, {}), 'its card asks it now')

    def test_an_own_branch_shows_its_diff_and_all_four_answers(self):
        self.branch()
        with mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'): s = landing.state(self.s, self.tid, full=True)
        self.assertTrue(s['ask'] and s['own'])
        self.assertEqual((s['branch'], s['base'], s['ahead'], s['changed'], s['plus'], s['minus']), ('fix-rounding', 'master', 1, 1, 1, 1))
        self.assertEqual([a['how'] for a in s['answers']], ['rebase', 'merge', 'pr', 'discard'])
        # ...and no Open a PR where its origin is no GitHub repository: that press could only fail (the re-walk on Codex, 2026-11-25)
        self.assertEqual([a['how'] for a in landing.state(self.s, self.tid)['answers']], ['rebase', 'merge', 'discard'])
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
        landing.saw(self.s, self.tid, 'Bash', {'command': 'git commit -q -m "edit ledger.py"'})
        s = landing.state(self.s, self.tid)
        self.assertFalse(s['ask'] or s['own']); self.assertEqual(s['answers'], []); self.assertEqual(s['changed'], 1)
        # ...and with no remote to push its commit to, the card says so rather than standing silent (design round 5)
        self.assertTrue(s['shared'] and s['noRemote']); self.assertIn('no remote to push to', s['line'])
        with self.assertRaises(ValueError): landing.land(self.s, self.tid, 'discard')
        git(self.cwd, 'remote', 'add', 'origin', tempfile.mkdtemp())
        s = landing.state(self.s, self.tid)
        self.assertFalse(s['noRemote']); self.assertIn('Push it?', s['line'], 'an origin never fetched still takes the push')

    def test_on_a_shared_base_each_task_counts_only_its_own_commits(self):
        # the owner's live coding task, 2026-11-08: "518 files changed" on master - every other agent's and release's commit since it began
        peer = Factory(self.s).task(title='Tidy the portal', kind='coding'); landing.mark_start(self.s, peer, self.cwd)
        t = int(git(self.cwd, 'log', '-1', '--format=%ct')) + 10
        for k, (tid, name) in enumerate([(self.tid, 'ledger.py'), (peer, 'portal.py'), (None, 'release.txt'), (self.tid, 'rounding.py')]):
            when = t + 10 * k
            commit(self.cwd, name, f'v{k}\n', env={'GIT_COMMITTER_DATE': f'{when} +0000'})
            if tid: landing.saw(self.s, tid, 'Bash', {'command': f'git -C "{self.cwd}" commit -q -m step'}, at=when + 1)
        mine, theirs = landing.state(self.s, self.tid, full=True), landing.state(self.s, peer)
        self.assertEqual(sorted(f['path'] for f in mine['files']), ['ledger.py', 'rounding.py'])
        self.assertEqual([f['path'] for f in theirs['files']], ['portal.py'])
        self.assertEqual(mine['commits'], 2); self.assertNotIn('release.txt', mine['diff']); self.assertNotIn('portal.py', mine['diff'])
        self.assertNotIn('release.txt', landing.changes(self.s, self.tid)['diff'])

    def test_its_uncommitted_edits_count_and_a_peers_do_not(self):
        for name in ('ledger.py', 'peer.txt'):
            with open(os.path.join(self.cwd, name), 'a', encoding='utf-8', newline='\n') as f: f.write('four\n')
        landing.saw(self.s, self.tid, 'Edit', {'file_path': os.path.join(self.cwd, 'ledger.py')})
        s = landing.state(self.s, self.tid, full=True)
        self.assertEqual([f['path'] for f in s['files']], ['ledger.py']); self.assertIn('+four', s['diff']); self.assertNotIn('peer.txt', s['diff'])

    def test_an_acp_sessions_own_record_says_what_it_committed_and_edited(self):
        import json
        from pathlib import Path
        root = Path(tempfile.mkdtemp()); (root / str(self.tid)).mkdir()
        t = int(git(self.cwd, 'log', '-1', '--format=%ct')) + 30
        commit(self.cwd, 'peer.txt', 'p\n', env={'GIT_COMMITTER_DATE': f'{t - 15} +0000'})              # a peer's, before the call
        commit(self.cwd, 'ledger.py', 'one\nTWO\nthree\n', env={'GIT_COMMITTER_DATE': f'{t} +0000'})
        at = lambda x: time.strftime('%Y-%m-%d %H:%M:%S', time.localtime(x))
        rows = [{'sessionUpdate': 'tool_call', 'toolCallId': 'c1', 'kind': 'execute', 'rawInput': {'command': 'git commit -q -F -'}, '_at': at(t - 1)},
                {'sessionUpdate': 'tool_call_update', 'toolCallId': 'c1', 'status': 'completed', 'rawOutput': 'done', '_at': at(t + 1)},
                {'sessionUpdate': 'tool_call', 'toolCallId': 'c2', 'kind': 'edit', '_at': at(t + 5),
                 'content': [{'type': 'diff', 'path': os.path.join(self.cwd, 'notes.md')}]}]
        (root / str(self.tid) / 'acp-s1.jsonl').write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')
        with open(os.path.join(self.cwd, 'notes.md'), 'w', encoding='utf-8') as f: f.write('n\n')
        with mock.patch('taskuary.session_artifacts.root', return_value=root):
            s = landing.state(self.s, self.tid)
        self.assertEqual(sorted(f['path'] for f in s['files']), ['ledger.py', 'notes.md']); self.assertEqual(s['commits'], 1)

    def test_a_file_two_commits_touched_reads_once(self):
        a = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-a\n+b\n'
        b = 'diff --git a/x b/x\n--- a/x\n+++ b/x\n@@ -1 +1 @@\n-b\n+c\ndiff --git a/y b/y\n--- a/y\n+++ b/y\n@@ -1 +1 @@\n-1\n+2\n'
        m = landing.merged([a, b])
        self.assertEqual((m.count('diff --git a/x'), m.count('@@ -1 +1 @@'), m.count('diff --git a/y')), (1, 3, 1))

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

    def test_a_landing_asked_before_any_checkout_is_picked_says_how_to_pick_one(self):
        "A coding agent that called propose_land on a task that never started in a checkout read 'nothing to land' and no next step."
        bare = Factory(self.s).task(title='Fix the portal login', kind='coding')
        with self.assertRaisesRegex(ValueError, 'use_repo') as e: landing.propose(self.s, bare, 'pr', 'the fix is ready')
        # ...the tool names on the agent's own line, never the line the owner's Why line shows (agenttools.refusal)
        what, step = str(e.exception).split('\n')
        self.assertNotIn('use_repo', what); self.assertTrue(step.startswith(agenttools.NEXT_STEP))

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


    def test_a_pull_request_github_will_not_open_is_kept_and_its_agent_told(self):
        """The branch went out, then GitHub refused the pull request (a token without Pull requests: write). That refusal is GitHub's own
        error, not the landing's: it passed the land's handler - no line kept, the agent never told, the press's toast the only trace."""
        from taskuary import github
        self.branch()
        remote = tempfile.mkdtemp(); git(remote, 'init', '-q', '--bare')
        git(self.cwd, 'remote', 'add', 'origin', remote)
        no = github.Refused('the GitHub token may not open a pull request - it needs Pull requests: write for this repository', 403, 'Pull requests: write')
        with mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'), mock.patch('taskuary.waitroom.add') as told, \
             mock.patch('taskuary.ci._conn', return_value={'Secret': 'tok'}), mock.patch('taskuary.github.open_pr', side_effect=no):
            with self.assertRaises(landing.Refused) as e: landing.land(self.s, self.tid, 'pr')
        self.assertIn('Pull requests: write', str(e.exception)); self.assertIn('was pushed', str(e.exception))
        said = told.call_args[0][2]
        self.assertIn('Pull requests: write', said); self.assertNotIn('Nothing went out', said)
        self.assertTrue(any(a['Action'] == 'land_refused' for a in self.s._rows("SELECT * FROM audit WHERE EntityId=?", (self.tid,))))
        self.assertTrue(landing.state(self.s, self.tid)['ask'], 'the question stands: pressed again it opens the pull request')
        # ...and a GitHub card with no token says so before anything is pushed
        git(remote, 'branch', '-D', 'fix-rounding')
        with mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'), mock.patch('taskuary.waitroom.add') as told, \
             mock.patch('taskuary.ci._conn', side_effect=RuntimeError('no GitHub PAT saved')):
            with self.assertRaises(landing.Refused): landing.land(self.s, self.tid, 'pr')
        self.assertIn('no GitHub PAT saved', told.call_args[0][2]); self.assertFalse(git(remote, 'branch', '--list', 'fix-rounding'))

    # ── WORK ON THE SHARED BASE IS A PUSH, ASKED WITH BUTTONS (the owner, 2026-11-09: "i thought actions should be cards/buttons??? why is this
    # text??") - an agent committed straight on master, ended "Ready to push <sha> and deploy (master -> deploy) - go ahead?", and the card
    # under it had no button, so the owner typed "yes"
    def on_master_with_origin(self):
        self.remote = tempfile.mkdtemp(); git(self.remote, 'init', '-q', '--bare')
        git(self.cwd, 'remote', 'add', 'origin', self.remote); git(self.cwd, 'push', '-q', 'origin', 'master')
        commit(self.cwd, 'ledger.py', 'one\nTWO\nthree\n')
        landing.saw(self.s, self.tid, 'Bash', {'command': 'git commit -q -m "edit ledger.py"'})

    def test_its_unpushed_commits_on_the_shared_base_are_a_push_button(self):
        self.on_master_with_origin()
        s = landing.state(self.s, self.tid)
        self.assertTrue(s['owed']); self.assertFalse(s['ask'] or s['own'], 'its unpushed commits are a fact: no card stands that no agent raised')
        self.dev(); landing.propose(self.s, self.tid, 'push')                 # ...the agent raises it
        s = landing.state(self.s, self.tid)
        self.assertTrue(s['ask'])
        self.assertEqual([a['how'] for a in s['answers']], ['push'], 'no deploy branch known yet: Push alone')
        self.assertEqual((s['push']['tip'], s['push']['ahead']), (self.sha('master'), 1))
        self.assertIn('Push it?', s['line'])
        # ...and the press is a line of the chat in the owner's voice, never the audit row's bare name ("You landed.")
        from taskuary import general
        landing.land(self.s, self.tid, 'push')
        self.assertIn("pressed Push on the agent's work - it went through", general.presses(self.s, self.tid)[-1][2])
        # ...and the card that was pressed keeps its place in the chat (the card gallery, 2026-11-25: with nothing of its own left unpushed
        # it had no time to stand at, and was gone from the chat at its own press)
        with mock.patch.object(landing, 'own', return_value={'commits': [], 'paths': {}, 'at': ''}):       # ...the remote has them all now
            s = landing.state(self.s, self.tid)
        self.assertEqual((s['landed']['how'], s['commits']), ('push', 0))
        self.assertEqual(s['at'], s['landed']['at']); self.assertTrue(s['at'])
        # ...and it says what it pushed once, on itself: how many went is kept for its title, and its press is no chat line under it
        self.assertEqual(s['landed']['commits'], 1)
        self.assertFalse([m for m in general.press_lines(self.s, self.tid) if 'went through' in m['content'][0]['text']])

    def test_a_card_read_again_asks_git_nothing_it_already_said_of_its_commits(self):
        """The owner's live app, 2026-11-19: /landing took 23 s - every poll asked git again for each own commit's files and whether each is on
        the base, ~0.1 s a process on Windows. What git says of commits named by sha never changes; it is asked once."""
        self.on_master_with_origin(); landing.state(self.s, self.tid)
        from taskuary import spawn
        with mock.patch.object(spawn, 'run', wraps=spawn.run) as run: s = landing.state(self.s, self.tid)
        asked = [c.args[0][3:] for c in run.call_args_list]
        self.assertFalse([a for a in asked if a[0] in ('show', 'merge-base') and len(a) > 2 and all(len(x) == 40 for x in a[-2:] if not x.startswith('-'))], asked)
        self.assertEqual((s['push']['tip'], s['push']['ahead']), (self.sha('master'), 1))
        commit(self.cwd, 'rounding.py', 'x\n'); landing.saw(self.s, self.tid, 'Bash', {'command': 'git commit -q -m "edit rounding.py"'})
        self.assertEqual(landing.state(self.s, self.tid)['push']['ahead'], 2)        # ...and a new commit is asked of at once

    def test_two_commits_in_one_second_push_up_to_the_newer(self):
        self.on_master_with_origin()
        when = int(git(self.cwd, 'log', '-1', '--format=%ct'))
        commit(self.cwd, 'rounding.py', 'x\n', env={'GIT_COMMITTER_DATE': f'{when} +0000'})
        landing.saw(self.s, self.tid, 'Bash', {'command': 'git commit -q -m "edit rounding.py"'})
        p = landing.state(self.s, self.tid)['push']
        self.assertEqual((p['tip'], p['ahead']), (self.sha('master'), 2))

    def test_the_agent_proposes_push_and_deploy_and_the_press_pushes_both(self):
        from taskuary import card
        self.on_master_with_origin(); tip = self.sha('master')
        with card.raising(self.s, self.tid, 'check it is live, then reply that it is'):      # ...the agent's own step after his press
            landing.propose(self.s, self.tid, 'push', 'the fix counts once it is live', deploy='deploy')
        s = landing.state(self.s, self.tid)
        self.assertEqual([a['how'] for a in s['answers']], ['push', 'deploy']); self.assertEqual(s['proposal']['how'], 'deploy')
        self.assertFalse(git(self.remote, 'branch', '--list', 'deploy'), 'proposing pushes nothing')
        with self.assertRaises(ValueError): landing.propose(self.s, self.tid, 'rebase')          # no branch of its own to rebase
        with mock.patch('taskuary.waitroom.add') as told, mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'):
            out = landing.land(self.s, self.tid, 'deploy')
        self.assertTrue(out['ok']); self.assertIn('deployed it to deploy', out['says'])
        self.assertEqual((git(self.remote, 'rev-parse', 'master'), git(self.remote, 'rev-parse', 'deploy')), (tip, tip))
        self.assertIn('pressed Push & deploy', told.call_args[0][2], 'its `then` names a step after the press: it is told')
        s = landing.state(self.s, self.tid)
        self.assertFalse(s['ask']); self.assertEqual(s['landed']['how'], 'deploy')
        # ...and the next task in this repo is offered the same deploy branch without the agent naming it
        self.assertEqual(landing._deploy_to(self.s, None, 'northwind/ledger'), 'deploy')

    def test_a_push_proposed_through_propose_or_a_mark_is_the_cards_buttons_whatever_the_push_switch(self):
        # with "Agents may push / deploy" off a `land` proposal was refused - the agent, left with no road, asked in words
        from taskuary import proposals
        self.on_master_with_origin()
        self.assertIsNone(landing.from_proposal(self.s, self.tid, {'action': 'comment_issue', 'body': 'x'}))
        self.assertTrue(landing.from_proposal(self.s, self.tid, {'action': 'push_direct', 'deploy': 'deploy', 'why': 'live is the ask'})['ok'])
        self.assertEqual([a['how'] for a in landing.state(self.s, self.tid)['answers']], ['push', 'deploy'])
        t2 = Factory(self.s).task(title='Round the totals', kind='coding'); landing.mark_start(self.s, t2, self.cwd)
        commit(self.cwd, 'totals.py', 'x\n'); landing.saw(self.s, t2, 'Bash', {'command': 'git commit -q -m totals'})
        queued = proposals.collect(self.s, t2, 'Done. TASKUARY-PROPOSE {"action": "land", "why": "ship it"}', 'agent')
        self.assertEqual(queued, [], 'no Approve review beside the card')
        s = landing.state(self.s, t2); self.assertEqual((s['proposal']['how'], [a['how'] for a in s['answers']]), ('push', ['push']))

    def test_a_push_origin_refuses_pushes_nothing_and_says_why(self):
        self.on_master_with_origin()
        other = tempfile.mkdtemp(); git(other, 'clone', '-q', self.remote, '.'); commit(other, 'portal.py', 'x\n'); git(other, 'push', '-q', 'origin', 'master')
        self.dev(); landing.propose(self.s, self.tid, 'push')
        with self.assertRaises(landing.Refused) as e: landing.land(self.s, self.tid, 'push')
        self.assertIn('nothing was pushed', str(e.exception))
        with self.assertRaises(ValueError): landing.land(self.s, self.tid, 'deploy')           # not offered: no deploy branch known

    def test_push_and_deploy_whose_deploy_is_refused_says_the_base_went_and_keeps_it(self):
        """Push & deploy: the base went out, then the deploy branch refused (it had moved on). The press answered "refused ... - master was
        pushed", the agent was told "Nothing went out, and the question stays on the task" - and nothing stayed: the base had nothing left
        to push, so the question was gone and asking again was refused. What went is kept as a push; what did not is said, to both."""
        from taskuary import ci
        self.on_master_with_origin(); tip = self.sha('master')
        other = tempfile.mkdtemp(); git(other, 'clone', '-q', self.remote, '.'); git(other, 'checkout', '-q', '-b', 'deploy')
        commit(other, 'hotfix.py', 'x\n'); git(other, 'push', '-q', 'origin', 'deploy')                  # the deploy branch is ahead of us
        landing.propose(self.s, self.tid, 'push', 'live is the ask', deploy='deploy')
        with mock.patch('taskuary.waitroom.add') as told, mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'):
            out = landing.land(self.s, self.tid, 'deploy')
        self.assertEqual(git(self.remote, 'rev-parse', 'master'), tip, 'the base went out')
        self.assertNotEqual(git(self.remote, 'rev-parse', 'deploy'), tip, 'the deploy did not')
        self.assertIn('master', out['says']); self.assertIn('deploy', out['says']); self.assertIn('refused', out['says'])
        said = told.call_args[0][2]
        self.assertNotIn('Nothing went out', said); self.assertIn('refused', said); self.assertIn(tip[:7], said)
        self.assertEqual(landing.state(self.s, self.tid)['landed']['how'], 'push')
        self.assertEqual((ci.landing_of(self.s, self.tid) or {}).get('sha'), tip, 'the CI watch follows what was pushed')

    # ── AN AGENT'S OWN `git push` IS THE CARD'S QUESTION TOO (the agent walk, 2026-11-09): told to call propose_land, a coding agent ran
    # `git add ... && git commit ... && git push` in its shell. With Developer mode on the owner got "THE AGENT ASKS - It wants to run
    # "git add ... | tail -1; gi"" with Allow once / Reject - cut mid-word, the push not on it - beside a card built to ask it with one Push
    def dev(self): self.s.set_setting('developer_mode', '1', 'test')
    def pushed(self): return git(self.remote, 'rev-parse', 'master') == self.sha('master')

    def test_a_push_run_in_the_shell_becomes_the_push_button(self):
        self.on_master_with_origin(); self.dev()
        held, said = landing.push_asked(self.s, self.tid, 'git push origin master', self.cwd, about='Push the rounding fix')
        self.assertTrue(held); self.assertTrue(said.startswith(shellgate.HELD), said); self.assertIn('Push button', said)
        s = landing.state(self.s, self.tid)
        self.assertEqual(s['proposal']['how'], 'push'); self.assertIn('rounding fix', s['proposal']['why'])
        self.assertFalse(self.pushed(), 'asking pushes nothing')
        # ...a bare `git push` is the same push, and asked twice it is still one question
        self.assertTrue(landing.push_asked(self.s, self.tid, 'git push', self.cwd)[0])
        self.assertTrue(landing.push_asked(self.s, self.tid, 'git push -u origin HEAD', self.cwd)[0])

    # ── NO NOT NOW (the owner, 2026-11-10: "why ddo we need not now card? just hit next ... SHouldn't we just get rid of it totally"): the
    # push card the agent raised is a card like any other - passed once the conversation moves on, raised again if still wanted
    def test_a_push_card_the_agent_raised_is_passed_when_the_conversation_moves_on_and_raised_again(self):
        from taskuary import proposals
        self.on_master_with_origin(); self.dev()
        landing.propose(self.s, self.tid, 'push', 'the fix is ready')
        self.assertTrue(landing.state(self.s, self.tid)['ask'])
        # ...an input after it - his line, a mail - heard by its agent (proposals.set_aside_drafts: one rule with every card's, never a turn's start)
        from taskuary.conversation import ep
        self.assertIn(proposals.LAND, proposals.set_aside_drafts(self.s, self.tid, ep(landing.record(self.s, self.tid)['proposal']['at']) + 0.5))
        s = landing.state(self.s, self.tid)
        self.assertTrue(s['passed']); self.assertFalse(s['ask'], 'nothing pressable')
        # ...yet it keeps its answers: the page draws the same card, its buttons greyed (the owner, 2026-11-18) - and a press is still refused
        self.assertEqual([a['how'] for a in s['answers']], ['push'])
        with self.assertRaises(ValueError) as e: landing.land(self.s, self.tid, 'push')
        self.assertTrue(str(e.exception).startswith('Not sent - '), e.exception); self.assertFalse(self.pushed())
        from taskuary import cardqueue
        self.assertIn('Greyed, will not go (the chat moved on past it): the push question you raised', cardqueue.screen(self.s, self.tid))
        # ...its own `git push` over a passed card is still held - raised again, never run
        self.assertTrue(landing.push_asked(self.s, self.tid, 'git push origin master', self.cwd)[0]); self.assertFalse(self.pushed())
        self.assertTrue(landing.state(self.s, self.tid)['ask'])
        # ...the agent asks again, and is never refused for a hold: a live card again
        self.assertTrue(landing.propose(self.s, self.tid, 'push', 'still needed')['ok'])
        self.assertTrue(landing.state(self.s, self.tid)['ask'])

    def test_unpushed_work_no_turn_raised_stays_live_as_the_checkout_says(self):
        self.on_master_with_origin(); self.dev()
        before = landing.state(self.s, self.tid)
        self.assertEqual(landing.state(self.s, self.tid)['ask'], before['ask'])
        self.assertFalse(landing.state(self.s, self.tid)['passed'])

    def test_a_push_the_remote_refuses_is_kept_and_its_agent_is_told_the_way_past(self):
        """A FAILURE IS KEPT WHERE IT HAPPENED (rules part 4): someone pushed to origin first, so the owner's Push was refused - "pull and rebase,
        then push again". That is the agent's to do, yet only the press's own answer said it: nothing on the task after a reload, the agent
        never told, and the next Push refused the same way."""
        from taskuary import general
        self.on_master_with_origin(); landing.propose(self.s, self.tid, 'push', 'the fix is ready')
        other = tempfile.mkdtemp(); git(other, 'clone', '-q', self.remote, '.')
        for k, v in (('user.name', 'Ray Colton'), ('user.email', 'ray@northwind.example')): git(other, 'config', k, v)
        commit(other, 'notes.md', 'from a teammate\n'); git(other, 'push', '-q', 'origin', 'master')
        told = []
        with mock.patch.object(general, 'to_agent', lambda st, t, said, actor='owner': (told.append(said), 'told')[1]):
            with self.assertRaises(landing.Refused): landing.land(self.s, self.tid, 'push')
        self.assertFalse(self.pushed())
        [line] = [what for _, _, what, *_ in general.presses(self.s, self.tid) if 'Push' in what]
        self.assertIn('it did not go', line); self.assertIn('failed to push', line, "git's own why, in say.owner's words")
        [said] = told
        self.assertIn('was refused', said); self.assertIn('rebase', said)
        self.assertTrue(landing.state(self.s, self.tid)['ask'], 'the question stays: Push is still one press once the agent has rebased')

    def test_a_push_onto_another_branch_is_push_and_deploy(self):
        for cmd in ('git push origin master:deploy', 'git push origin HEAD:deploy', 'git push origin master && git push origin master:deploy'):
            with self.subTest(cmd):
                self.tearDown(); self.setUp(); self.on_master_with_origin(); self.dev()
                self.assertTrue(landing.push_asked(self.s, self.tid, cmd, self.cwd)[0])
                s = landing.state(self.s, self.tid)
                self.assertEqual((s['proposal']['how'], s['proposal']['deploy'], [a['how'] for a in s['answers']]), ('deploy', 'deploy', ['push', 'deploy']))

    def test_commit_and_push_in_one_line_runs_nothing_and_says_how_to_ask(self):
        self.on_master_with_origin(); self.dev()
        held, said = landing.push_asked(self.s, self.tid, 'git add -A && git commit -m "round once" && git push origin master', self.cwd)
        self.assertFalse(held, 'nothing waits on the owner yet: the commit in the line has not run')
        self.assertIn('propose (kind git, how push)', said); self.assertIn('without the push', said)
        self.assertIsNone(landing.state(self.s, self.tid)['proposal'])
        # ...output thrown away is no second step: the push alone is still the button
        self.assertTrue(landing.push_asked(self.s, self.tid, 'git push origin master 2>&1', self.cwd)[0])
        # ...and a push alone with nothing of the task's own on the card is never sent to a tool that would refuse it: held the old way
        t2 = Factory(self.s).task(title='Round the totals', kind='coding'); landing.mark_start(self.s, t2, self.cwd)
        self.assertFalse(landing.push_asked(self.s, t2, 'git push', self.cwd))

    def test_the_tool_carries_the_deploy_branch(self):
        # "how push, deploy <branch>" drew Push alone: the tool's door dropped `deploy`, and the agent asked for the deploy in words
        from taskuary import agenttools
        got = {}
        # ...and a saved session's propose_land is propose kind git, its deploy carried the same (the design audit, 2026-11-27)
        for name, a in (('propose', {'kind': 'git', 'how': 'push'}), ('propose_land', {'how': 'push'})):
            got.clear()
            agenttools.call(self.s, self.tid, name, {**a, 'why': 'live is the ask', 'deploy': 'deploy'},
                            {'propose': lambda tid, p: got.update(p) or {'ok': True, 'review': 1}})
            self.assertEqual((got['action'], got['deploy']), ('push_direct', 'deploy'))

    def test_what_the_card_cannot_do_is_held_the_old_way(self):
        self.on_master_with_origin(); self.dev()
        for cmd in ('git push --force origin master', 'git push --tags', 'git push fork master', 'git push origin :old', 'git push origin +master',
                    'git push origin master other', 'gh pr create --fill && git push', 'git -C ../portal push', 'cd ../portal && git push',
                    'bash -c "git push origin master"', 'git status'):
            with self.subTest(cmd): self.assertFalse(landing.push_asked(self.s, self.tid, cmd, self.cwd))
        other = tempfile.mkdtemp(); git(other, 'init', '-q', '-b', 'master')
        self.assertFalse(landing.push_asked(self.s, self.tid, 'git push', other), 'a push from another checkout is not this task\'s work')
        self.assertFalse(landing.push_asked(self.s, Factory(self.s).task(title='No checkout'), 'git push', self.cwd))
        from taskuary import agents
        with mock.patch.object(agents, 'developer_mode', agents.developer_mode.real):     # the suite runs with it on (conftest)
            self.assertTrue(landing.push_asked(self.s, self.tid, 'git push origin master', self.cwd))
            self.s.set_setting('developer_mode', '0', 'test')
            self.assertFalse(landing.push_asked(self.s, self.tid, 'git push origin master', self.cwd), 'no landing card is drawn with Developer mode off')

    def test_its_own_branch_pushed_is_the_landing_question(self):
        self.remote = tempfile.mkdtemp(); git(self.remote, 'init', '-q', '--bare')
        git(self.cwd, 'remote', 'add', 'origin', self.remote); git(self.cwd, 'push', '-q', 'origin', 'master')
        self.branch(); self.dev()
        # ...AND NEVER AN "Open a PR" NO PRESS COULD OPEN (the re-walk on Codex, 2026-11-25: an origin that pushes to a local folder; the card
        # stood and his press failed "not a GitHub repository"): raised, it is answered with that and the way on - the push is a held step
        with self.assertRaisesRegex(ValueError, r'not a GitHub repository\s+Next: point the checkout.s origin'): landing.propose(self.s, self.tid, 'pr', 'the fix is ready')
        self.assertIsNone(landing.push_asked(self.s, self.tid, 'git push -u origin fix-rounding', self.cwd))
        with mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'):
            held, said = landing.push_asked(self.s, self.tid, 'git push -u origin fix-rounding', self.cwd)
            s = landing.state(self.s, self.tid)
        self.assertTrue(held, said)
        self.assertEqual((s['proposal']['how'], len(s['answers'])), ('pr', 4), 'all four answers, its pick marked')
        self.assertFalse(git(self.remote, 'branch', '--list', 'fix-rounding'))

    def test_both_gates_ask_the_card_first(self):
        from taskuary import gate
        self.on_master_with_origin(); self.dev()
        tc = lambda cmd: {'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd, 'description': 'Push the fix'}}
        ctx = {'store': self.s, 'task_id': self.tid, 'cwd': self.cwd, 'sid': 'run1'}
        with mock.patch.object(shellgate, 'trusted', return_value=''):
            held = {}
            out = gate.answerer(ctx, held=held)({'toolCall': tc('git push origin master'), 'options': [
                {'optionId': 'y', 'kind': 'allow_once'}, {'optionId': 'n', 'kind': 'reject_once'}]})
            self.assertEqual(out.get('optionId'), 'n'); self.assertTrue(held['c'].startswith(shellgate.HELD), held)
            self.assertEqual(gate.tool_call(tc('git add -A && git commit -m x && git push'), ctx)[0], gate.REFUSED)
            # ...the hook's road and an API agent's run_command (shellgate.check): the same answer, and no Approve card filed beside it
            said = shellgate.check(self.s, self.tid, 'run1', 'git push origin master', cwd=self.cwd)['hookSpecificOutput']['permissionDecisionReason']
            self.assertIn('Push button', said)
            self.assertEqual(self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (self.tid,)), [])
        # ...and a repo the owner trusts to act on its own still just pushes
        with mock.patch.object(shellgate, 'trusted', return_value='northwind/ledger'):
            self.assertEqual(shellgate.check(self.s, self.tid, 'run1', 'git push origin master', cwd=self.cwd), {})
            self.assertEqual(gate.tool_call(tc('git push origin master'), ctx)[0], gate.ALLOWED)


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


class NamedCheckoutTests(unittest.TestCase):
    """A GENERAL AGENT'S FIX IN A CHECKOUT THE OWNER NAMED IS ONE PUSH CARD (design round 5, 2026-11-19: "fix the rounding bug - my checkout is
    at <path>" from New, on both CLIs; the fix committed there, then a raw shell card in the agent's own folder on one, "only you can grant
    that folder access in Settings -> Agents" on the other). Developer mode off, a general task: his naming the folder is the go-ahead."""
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cwd = os.path.join(self.tmp.name, 'ledger'); os.mkdir(self.cwd)
        self.scratch = os.path.join(self.tmp.name, 'scratch'); os.mkdir(self.scratch)
        git(self.cwd, 'init', '-q', '-b', 'master'); commit(self.cwd, 'totals.py', 'def total(a): return sum(a)\n', 'start')
        self.remote = os.path.join(self.tmp.name, 'origin.git'); git(self.tmp.name, 'init', '-q', '--bare', 'origin.git')
        git(self.cwd, 'remote', 'add', 'origin', self.remote); git(self.cwd, 'push', '-q', 'origin', 'master')
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Fix the ledger rounding', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner',
                                       'Summary': f'Fix the rounding bug in the ledger totals. My checkout is at {self.cwd}'}, 'owner')
        self.s.add_transcript(self.tid, 'run1', 'Fixed the rounding.', 'claude', self.scratch)
        from taskuary import agents
        self.dev = mock.patch.object(agents, 'developer_mode', agents.developer_mode.real); self.dev.start()

    def tearDown(self):
        self.dev.stop()
        try: self.tmp.cleanup()
        except OSError: pass

    def fix(self):
        "The agent's commit, made after the task began (git stamps to the second)."
        later = str(int(time.time()) + 5)
        commit(self.cwd, 'totals.py', 'def total(a): return round(sum(a), 2)\n', 'Round totals to cents',
               env={'GIT_COMMITTER_DATE': f'{later} +0000', 'GIT_AUTHOR_DATE': f'{later} +0000'})

    def test_his_named_checkout_pushes_through_one_card_with_developer_mode_off(self):
        self.fix()
        self.assertIsNone(landing.state(self.s, self.tid), 'nothing adopted before a push is asked')
        held, said = landing.push_asked(self.s, self.tid, f'Set-Location "{self.cwd}"; git push', self.scratch, about='Push the rounding fix')
        self.assertTrue(held); self.assertIn('Push button', said)
        s = landing.state(self.s, self.tid)
        self.assertTrue(s['ask']); self.assertEqual((s['push']['ahead'], s['name'], [a['how'] for a in s['answers']]), (1, 'ledger', ['push']))
        self.assertIn('of ledger', s['line'])
        self.assertTrue(landing.shown(self.s, self.tid))
        with mock.patch('taskuary.waitroom.add'): out = landing.land(self.s, self.tid, 'push')
        self.assertTrue(out['ok']); self.assertEqual(git(self.remote, 'rev-parse', 'master'), git(self.cwd, 'rev-parse', 'master'))

    def test_his_push_runs_through_the_one_executor_a_held_step_does(self):
        # the roads audit, 2026-11-19 (#8): an approved held step ran as the agent's own tool would (shellgate.replay: its shell, its git) while
        # the Push card ran Taskuary's own `git -C` - two executors for one push, and on his machine only one of the gits could push.
        self.fix()
        landing.push_asked(self.s, self.tid, f'Set-Location "{self.cwd}"; git push', self.scratch, about='Push the rounding fix')
        seen, real = [], shellgate.run_
        def spy(p, cwd='', timeout=300): seen.append((p, cwd)); return real(p, cwd, timeout)
        with mock.patch.object(shellgate, 'run_', spy), mock.patch('taskuary.waitroom.add'): out = landing.land(self.s, self.tid, 'push')
        self.assertTrue(out['ok'], out); self.assertEqual(len(seen), 1)
        (p, cwd), = seen
        self.assertTrue(os.path.samefile(cwd, self.cwd)); self.assertTrue(p['command'].startswith('git push origin '))
        self.assertEqual(shellgate.replay(p)[1:], ['-c', p['command']], "the agent's Bash tool's own road")
        self.assertEqual(git(self.remote, 'rev-parse', 'master'), git(self.cwd, 'rev-parse', 'master'))

    def test_a_pull_request_card_reads_its_branch_from_the_checkout_he_named(self):
        """The card gallery, 2026-11-25: a general agent's pull request from the checkout he named showed its body alone - no branch, no
        repository. Its card reads them off that checkout (ci.pr_plan); a folder he never named gives it nothing."""
        from taskuary import ci
        git(self.cwd, 'checkout', '-q', '-b', 'fix-rounding'); self.fix()
        plan = ci.pr_plan(self.s, self.tid, {'cwd': self.cwd, 'repo': 'northwind/ledger', 'title': 'Keep cents in totals'})
        self.assertEqual((plan['branch'], plan['base'], plan['repo']), ('fix-rounding', 'master', 'northwind/ledger'))
        self.assertTrue(plan['title'].endswith('] Keep cents in totals'))
        other = tempfile.mkdtemp(); git(other, 'init', '-q', '-b', 'side'); commit(other, 'x.py', 'x\n')
        self.assertNotEqual(ci.pr_plan(self.s, self.tid, {'cwd': other})['cwd'], other, 'a folder he never named is never the one it opens from')

    def test_a_pull_request_goes_into_the_repositorys_own_branch_and_is_never_raised_or_opened_with_nothing_committed(self):
        """Walk 22, 2026-11-25, both CLIs: "open a PR with this fix - it is uncommitted in my checkout". The repository's branch is main; the
        card read "main -> master", nothing was committed, and the press said "Opened the pull request" having pushed nothing. The card's
        base is the repository's own; one that cannot be opened is refused at the raise with the exact fix; the press pushes the branch."""
        from taskuary import ci, proposals, verdicts
        git(self.cwd, 'branch', '-m', 'main'); git(self.cwd, 'push', '-q', 'origin', 'main'); git(self.cwd, 'remote', 'set-head', 'origin', 'main')
        with open(os.path.join(self.cwd, 'totals.py'), 'w', encoding='utf-8', newline='\n') as f: f.write('def total(a): return round(sum(a), 2)\n')
        def ask():
            no = []
            return proposals.queue(self.s, self.tid, {'action': 'open_pr', 'cwd': self.cwd, 'repo': 'northwind/ledger', 'title': 'Round totals'}, 'agent', no), no
        made, no = ask()
        self.assertIsNone(made); self.assertIn("on 'main', the branch a pull request goes into", no[0]); self.assertIn('git switch -c', no[0])
        git(self.cwd, 'switch', '-q', '-c', 'fix-rounding')
        made, no = ask()
        self.assertIsNone(made); self.assertEqual(no[0], 'nothing committed on fix-rounding - commit the fix first')
        self.fix()
        made, no = ask()
        rv = self.s.get_review(made['reviewId'])
        self.assertEqual([proposals._draft(rv)['pr'][k] for k in ('branch', 'base', 'repo')], ['fix-rounding', 'main', 'northwind/ledger'])
        pr = {'number': 7, 'url': 'https://github.com/northwind/ledger/pull/7', 'head': 'fix-rounding', 'base': 'main', 'state': 'open'}
        with mock.patch('taskuary.ci._conn', return_value={'Secret': 'tok'}), mock.patch('taskuary.github.open_pr', return_value=pr) as op, \
             mock.patch('taskuary.general.to_agent'):
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertEqual((out['status'], op.call_args[0][2:4]), ('approved', ('fix-rounding', 'main')))
        self.assertEqual(git(self.remote, 'rev-parse', 'fix-rounding'), git(self.cwd, 'rev-parse', 'HEAD'), 'the press pushed the branch it opened')

    def test_a_pull_request_card_never_goes_up_for_a_repository_nobody_checked(self):
        """Walk 25, 2026-11-26: refused for no `repo`, an agent made one up ("alexdoyle/ledger", and said so) while the checkout's own origin
        named northwind/ledger behind a rewrite; the card went up and his Approve opened the pull request there. What the checkout says wins,
        and the agent is answered with it; a repository only the agent names is read through the GitHub card first, and one that is not
        there is answered with the fix. And the agent's why is drawn as the plain line it is."""
        from taskuary import ci, proposals
        git(self.cwd, 'checkout', '-q', '-b', 'fix-rounding'); self.fix()
        def ask(**kw):
            no = []
            return proposals.queue(self.s, self.tid, {'action': 'open_pr', 'cwd': self.cwd, 'title': 'Round totals', **kw}, 'agent', no), no
        gone = RuntimeError('GitHub said 404 Not Found: read alexdoyle/ledger')
        with mock.patch.object(self.s, 'github_for', return_value={'Secret': 'tok', 'Type': 'github'}), mock.patch('taskuary.github.repo_info', side_effect=gone) as read:
            made, no = ask(repo='alexdoyle/ledger')
        self.assertIsNone(made); read.assert_called_with('tok', 'alexdoyle/ledger')
        for want in ('alexdoyle/ledger could not be read through the GitHub card', '404 Not Found', 'git remote -v'): self.assertIn(want, no[0])
        # ...the checkout's origin as it wrote it down, sent elsewhere by a rewrite: that is the repository, whatever the agent names
        was = git(self.cwd, 'config', '--get', 'remote.origin.url')
        git(self.cwd, 'config', f'url.{was}.insteadOf', 'https://github.com/northwind/ledger.git')
        git(self.cwd, 'config', 'remote.origin.url', 'https://github.com/northwind/ledger.git')
        self.assertEqual(ci.known_repo(self.s, self.tid, self.cwd), 'northwind/ledger')
        with mock.patch('taskuary.github.repo_info', side_effect=AssertionError('a known repository is not asked for')):
            made, no = ask(repo='alexdoyle/ledger')
            self.assertIsNone(made); self.assertEqual(no[0], "this task's pull request goes to northwind/ledger, not alexdoyle/ledger - give `repo` as northwind/ledger, or leave it out")
            made, no = ask(why='Open a pull request from `fix-rounding` into `master`')
        rv = self.s.get_review(made['reviewId'])
        self.assertEqual(proposals._draft(rv)['pr']['repo'], 'northwind/ledger')
        self.assertTrue(rv['Reason'].endswith('Open a pull request from fix-rounding into master'), rv['Reason'])

    def agent(self, **a):
        "One propose call of the task's agent over /api/mcp: (its answer, was it an error)."
        from fastapi.testclient import TestClient
        from taskuary import config, guard, server
        srv = config.load()['server']
        hdr = {'X-Taskuary-Token': srv['agent_token'], guard.TASK_HDR: guard.task_proof(srv, self.tid)}
        with mock.patch.object(server, 'store', self.s):
            r = TestClient(server.app).post(f'/api/mcp?task={self.tid}', headers=hdr, json={'jsonrpc': '2.0', 'id': 1, 'method': 'tools/call',
                                                                                          'params': {'name': 'propose', 'arguments': a}}).json()['result']
        return r['content'][0]['text'], r['isError']

    def test_a_push_is_kind_git_from_the_checkout_he_named_with_no_folder_given(self):
        """Walks 25-26: "git push", "pr" and "push" were guessed as a free-text `action`. The act is the kind: `kind: git, how: push`, and the
        checkout is the one he named on the task - no `cwd` asked for."""
        self.fix()
        said, err = self.agent(kind='git', how='push', why='the rounding fix')
        self.assertFalse(err, said); self.assertEqual(landing.state(self.s, self.tid)['proposal']['how'], 'push')

    def test_a_pull_request_is_kind_git_its_checkout_and_repository_found_for_it(self):
        """The HIPAA road took four calls for one PR: refused for no `cwd`, then for no `repo` - which the schema never named. Both default:
        the checkout he named, and the repository its origin pushes to."""
        from taskuary import proposals
        was = git(self.cwd, 'config', '--get', 'remote.origin.url')
        git(self.cwd, 'config', f'url.{was}.insteadOf', 'https://github.com/northwind/ledger.git')
        git(self.cwd, 'config', 'remote.origin.url', 'https://github.com/northwind/ledger.git')
        git(self.cwd, 'checkout', '-q', '-b', 'fix-rounding'); self.fix()
        said, err = self.agent(kind='git', how='pr', title='Keep cents in totals')
        self.assertFalse(err, said)
        [rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
        p = proposals._draft(rv)
        self.assertEqual((p['action'], p['pr']['repo'], p['pr']['branch']), ('open_pr', 'northwind/ledger', 'fix-rounding'))

    def test_propose_push_with_no_folder_takes_the_one_he_named(self):
        self.fix()
        out = landing.from_proposal(self.s, self.tid, {'action': 'push_direct', 'why': 'the rounding fix'})
        self.assertTrue(out['ok']); self.assertEqual(landing.state(self.s, self.tid)['proposal']['how'], 'push')
        self.assertIn('sees the Push card now', out['says'])

    def test_the_agent_is_told_its_push_card_waits_behind_another_not_that_it_is_up(self):
        # design round 6, D1: told "the owner sees it" whatever the page drew, the agent said three times a card was waiting that was not there
        self.fix(); Factory(self.s).review(self.tid, kind='slot', draft='Hi Gail, the fix is in.', reason='an email to gail@northwind.example')
        out = landing.from_proposal(self.s, self.tid, {'action': 'push_direct', 'why': 'the rounding fix'})
        self.assertIn('NOT on his screen yet', out['says']); self.assertNotIn('sees the', out['says'])

    def test_a_push_no_card_can_draw_is_refused_with_why_not_told_as_up(self):
        from taskuary import agents
        t = Factory(self.s).task(title='Look at the ledger', kind='coding'); landing.mark_start(self.s, t, self.cwd); self.fix()
        with mock.patch.object(agents, 'developer_mode', return_value=False), self.assertRaisesRegex(ValueError, 'no Push card can be drawn'):
            landing.propose(self.s, t, 'push')

    def test_a_checkout_with_no_remote_says_so_on_the_card_and_to_the_agent(self):
        git(self.cwd, 'remote', 'remove', 'origin'); self.fix()
        with self.assertRaises(ValueError) as e: landing.from_proposal(self.s, self.tid, {'action': 'push_direct', 'cwd': self.cwd, 'why': 'the fix'})
        self.assertIn('no remote to push to', str(e.exception)); self.assertIn('git remote add origin', str(e.exception))
        s = landing.state(self.s, self.tid)
        self.assertTrue(s['noRemote'] and not s['ask']); self.assertEqual(s['commits'], 1, 'only the commit made since the task began')
        self.assertIn('no remote to push to', s['line'])

    def test_the_page_draws_the_card_his_named_checkout_raised_and_no_other(self):
        # design round 6, D1: the agent proposed the push, was told "the owner sees it", and the page - gating the card on its own coding
        # switch, off with Developer mode - drew nothing; "Press Push" three times on both CLIs. The page reads one fact: landing.shown
        os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp())
        from fastapi.testclient import TestClient
        from taskuary import agents, server
        st, c = server.store, TestClient(server.app)
        tid = st.create_task({'Title': 'Fix the ledger rounding', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner',
                              'Summary': f'Fix the rounding bug in the ledger totals. My checkout is at {self.cwd}'}, 'owner')
        st.add_transcript(tid, 'run1', 'Fixed the rounding.', 'claude', self.scratch); self.fix()
        with mock.patch.object(agents, 'developer_mode', return_value=False):
            self.assertTrue(landing.from_proposal(st, tid, {'action': 'push_direct', 'cwd': self.cwd, 'why': 'the rounding fix'})['ok'])
            self.assertTrue(c.get(f'/api/tasks/{tid}').json()['checkout'], 'the card the agent was told is up is drawn')
            self.assertTrue(c.get(f'/api/tasks/{tid}/landing').json()['data']['ask'])
            # ...and a session that merely works in a git folder he never named draws no card, as its landing read returns none
            t2 = Factory(st).task(title='Look at the ledger', kind='coding'); st.add_transcript(t2, 'run2', 'Read it.', 'claude', self.cwd)
            landing.mark_start(st, t2, self.cwd)
            self.assertIsNone(c.get(f'/api/tasks/{t2}/landing').json()['data'])
            self.assertFalse(c.get(f'/api/tasks/{t2}').json()['checkout'])

    def test_a_folder_he_never_named_adopts_nothing(self):
        other = tempfile.mkdtemp(); git(other, 'init', '-q', '-b', 'master'); commit(other, 'x.py', 'x\n')
        self.assertIsNone(landing.push_asked(self.s, self.tid, 'git push', other))
        self.assertFalse(landing.record(self.s, self.tid))
        t2 = self.s.create_task({'Title': 'Ask about the ledger', 'Kind': 'general', 'Status': 'open', 'Summary': f'From Ray: my checkout is at {self.cwd}'}, 'router')
        with self.assertRaisesRegex(ValueError, 'no checkout'): landing.from_proposal(self.s, t2, {'action': 'push_direct', 'cwd': self.cwd})
        self.assertFalse(landing.shown(self.s, t2), "a stranger's words name no checkout")

    def test_use_repo_takes_his_named_checkout_without_a_settings_visit(self):
        from taskuary import repochoice
        self.s.set_setting(repochoice.FOLDERS_KEY, self.scratch, 'owner')
        self.assertTrue(repochoice.allowed(self.s, self.cwd, self.tid)); self.assertFalse(repochoice.allowed(self.s, self.cwd))
