"""Landing a coding task's branch (landing.py): the diff since the task started, the one question - rebase and fast-forward, merge commit,
PR, discard (only for a branch of its own) - and nothing landed half-done: a conflict aborts and goes to the agent. A real git repo in a
temp folder, no network."""
import os, subprocess, tempfile, time, unittest
from unittest import mock

from taskuary import guard, landing, shellgate
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
        landing.saw(self.s, self.tid, 'Bash', {'command': 'git commit -q -m "edit ledger.py"'})
        s = landing.state(self.s, self.tid)
        self.assertFalse(s['ask'] or s['own']); self.assertEqual(s['answers'], []); self.assertEqual(s['changed'], 1)
        self.assertTrue(s['shared']); self.assertIn('shared with other agents', s['line'])
        with self.assertRaises(ValueError): landing.land(self.s, self.tid, 'discard')

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
        self.assertTrue(s['ask']); self.assertFalse(s['own'])
        self.assertEqual([a['how'] for a in s['answers']], ['push'], 'no deploy branch known yet: Push alone')
        self.assertEqual((s['push']['tip'], s['push']['ahead']), (self.sha('master'), 1))
        self.assertIn('Push it?', s['line'])

    def test_two_commits_in_one_second_push_up_to_the_newer(self):
        self.on_master_with_origin()
        when = int(git(self.cwd, 'log', '-1', '--format=%ct'))
        commit(self.cwd, 'rounding.py', 'x\n', env={'GIT_COMMITTER_DATE': f'{when} +0000'})
        landing.saw(self.s, self.tid, 'Bash', {'command': 'git commit -q -m "edit rounding.py"'})
        p = landing.state(self.s, self.tid)['push']
        self.assertEqual((p['tip'], p['ahead']), (self.sha('master'), 2))

    def test_the_agent_proposes_push_and_deploy_and_the_press_pushes_both(self):
        self.on_master_with_origin(); tip = self.sha('master')
        landing.propose(self.s, self.tid, 'push', 'the fix counts once it is live', deploy='deploy')
        s = landing.state(self.s, self.tid)
        self.assertEqual([a['how'] for a in s['answers']], ['push', 'deploy']); self.assertEqual(s['proposal']['how'], 'deploy')
        self.assertFalse(git(self.remote, 'branch', '--list', 'deploy'), 'proposing pushes nothing')
        with self.assertRaises(ValueError): landing.propose(self.s, self.tid, 'rebase')          # no branch of its own to rebase
        with mock.patch('taskuary.waitroom.add') as told, mock.patch('taskuary.shellgate.repo_of', return_value='northwind/ledger'):
            out = landing.land(self.s, self.tid, 'deploy')
        self.assertTrue(out['ok']); self.assertIn('deployed it to deploy', out['says'])
        self.assertEqual((git(self.remote, 'rev-parse', 'master'), git(self.remote, 'rev-parse', 'deploy')), (tip, tip))
        self.assertIn('Check it is live', told.call_args[0][2], 'the press is the go-ahead the agent waited on')
        s = landing.state(self.s, self.tid)
        self.assertFalse(s['ask']); self.assertEqual(s['landed']['how'], 'deploy')
        # ...and the next task in this repo is offered the same deploy branch without the agent naming it
        self.assertEqual(landing._deploy_to(self.s, None, 'northwind/ledger'), 'deploy')

    def test_a_push_proposed_through_propose_or_a_mark_is_the_cards_buttons_whatever_the_push_switch(self):
        # with "Agents may push / deploy" off a `land` proposal was refused - the agent, left with no road, asked in words
        from taskuary import proposals
        self.on_master_with_origin()
        self.assertIsNone(landing.from_proposal(self.s, self.tid, {'action': 'comment_issue', 'body': 'x'}))
        self.assertTrue(landing.from_proposal(self.s, self.tid, {'action': 'push', 'deploy': 'deploy', 'why': 'live is the ask'})['ok'])
        self.assertEqual([a['how'] for a in landing.state(self.s, self.tid)['answers']], ['push', 'deploy'])
        t2 = Factory(self.s).task(title='Round the totals', kind='coding'); landing.mark_start(self.s, t2, self.cwd)
        commit(self.cwd, 'totals.py', 'x\n'); landing.saw(self.s, t2, 'Bash', {'command': 'git commit -q -m totals'})
        queued = proposals.collect(self.s, t2, 'Done. TASKUARY-PROPOSE {"action": "land", "why": "ship it"}', 'agent')
        self.assertEqual(queued, [], 'no Approve review beside the card')
        s = landing.state(self.s, t2); self.assertEqual((s['proposal']['how'], [a['how'] for a in s['answers']]), ('push', ['push']))

    def test_a_push_origin_refuses_pushes_nothing_and_says_why(self):
        self.on_master_with_origin()
        other = tempfile.mkdtemp(); git(other, 'clone', '-q', self.remote, '.'); commit(other, 'portal.py', 'x\n'); git(other, 'push', '-q', 'origin', 'master')
        with self.assertRaises(landing.Refused) as e: landing.land(self.s, self.tid, 'push')
        self.assertIn('nothing was pushed', str(e.exception))
        with self.assertRaises(ValueError): landing.land(self.s, self.tid, 'deploy')           # not offered: no deploy branch known

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
        self.assertIn('propose_land', said); self.assertIn('without the push', said)
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
        agenttools.call(self.s, self.tid, 'propose_land', {'how': 'push', 'why': 'live is the ask', 'deploy': 'deploy'},
                        {'propose_land': lambda tid, how, why, deploy='': got.update(how=how, deploy=deploy) or {'ok': True}})
        self.assertEqual(got, {'how': 'push', 'deploy': 'deploy'})

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
        held, said = landing.push_asked(self.s, self.tid, 'git push -u origin fix-rounding', self.cwd)
        self.assertTrue(held, said)
        s = landing.state(self.s, self.tid)
        self.assertEqual((s['proposal']['how'], len(s['answers'])), ('pr', 4), 'all four answers, its pick marked')
        self.assertFalse(git(self.remote, 'branch', '--list', 'fix-rounding'))

    def test_both_gates_ask_the_card_first(self):
        from taskuary import acpgate
        self.on_master_with_origin(); self.dev()
        tc = lambda cmd: {'toolCallId': 'c', 'kind': 'execute', 'rawInput': {'command': cmd, 'description': 'Push the fix'}}
        ctx = {'store': self.s, 'task_id': self.tid, 'cwd': self.cwd, 'sid': 'run1', 'owner_asks': True}
        with mock.patch.object(shellgate, 'trusted', return_value=''):
            asked = []
            with mock.patch('taskuary.permissions.ask', side_effect=lambda *a, **k: asked.append(a) or 'reject_once'):
                held = {}
                out = acpgate.answerer({k: v for k, v in ctx.items() if k != 'owner_asks'}, held=held)({'toolCall': tc('git push origin master'), 'options': [
                    {'optionId': 'y', 'kind': 'allow_once'}, {'optionId': 'n', 'kind': 'reject_once'}]})
            self.assertEqual(asked, [], 'no Allow once / Reject card beside the Push button')
            self.assertEqual(out.get('optionId'), 'n'); self.assertTrue(held['c'].startswith(shellgate.HELD), held)
            self.assertEqual(acpgate.decide(tc('git add -A && git commit -m x && git push'), ctx)[0], acpgate.REFUSED)
            # ...the hook's road and an API agent's run_command (shellgate.check): the same answer, and no Approve card filed beside it
            said = shellgate.check(self.s, self.tid, 'run1', 'git push origin master', cwd=self.cwd)['hookSpecificOutput']['permissionDecisionReason']
            self.assertIn('Push button', said)
            self.assertEqual(self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (self.tid,)), [])
        # ...and a repo the owner trusts to act on its own still just pushes
        with mock.patch.object(shellgate, 'trusted', return_value='northwind/ledger'):
            self.assertEqual(shellgate.check(self.s, self.tid, 'run1', 'git push origin master', cwd=self.cwd), {})
            self.assertEqual(acpgate.decide(tc('git push origin master'), ctx)[0], acpgate.ALLOWED)


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
