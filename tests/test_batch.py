"""One task per batch (batch.py): a ranked repository's head comes in as ONE task whose items an agent works top-down
(the owner, 2026-10-12: "they should all come in as one task and the agent will process them one by one picking the
most valuable one first"). Invented repositories only; no model, no pty."""
import json, unittest
from unittest import mock

from taskuary import batch, channels, ingest, rank
from taskuary.store import MemoryStore


def ranked(s, ctype='github'):
    c = s.get_connector_by_type(ctype)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'bulk': 'rank'})}, 't')


def pr(s, repo, n, value, title=None):
    mid = s.add_message({'ExternalId': f'gh:{repo}#{n}@r1', 'ConversationId': f'gh:{repo}#{n}', 'Channel': 'github',
                         'SourceName': repo, 'Subject': f'{repo}#{n} {title or f"change {n}"}', 'FromName': 'dev',
                         'FromEmail': 'dev@users.noreply.github.com', 'SentAt': '2026-10-12 07:00:00',
                         'BodyText': f'[pull request by dev - association: CONTRIBUTOR]\nfixes {n}',
                         'SourceLink': f'https://github.com/{repo}/pull/{n}', 'Status': 'triaging'})
    s.set_message_rank(mid, value, 'floor', 'rank')
    return mid


class BatchTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); ranked(self.s)
        self.judged = []
        def judge(s, m, **k): self.judged.append(m['_mid']); s.place_message(m['_mid'], None, 'filed')
        self.p = [mock.patch.object(ingest, 'ingest_message', side_effect=judge), mock.patch.object(batch, '_next')]
        for p in self.p: p.start()

    def tearDown(self):
        for p in self.p: p.stop()

    def drain(self):
        with mock.patch.object(rank, 'rank_pending', return_value=0): ingest.drain(self.s)

    # these PRs are by plain contributors on a repository nobody can check, so they are strangers' (batch.outside_row)
    def batch_of(self, repo, outside=True): return self.s.open_batch(batch.source_ref('github', repo, outside))

    def test_a_repositorys_head_comes_in_as_one_task_in_ranked_order(self):
        for n, v in enumerate((0.2, 0.9, 0.5, 0.7, 0.1, 0.6), 170): pr(self.s, 'northwind/portal', n, v)
        self.drain()
        tid = self.batch_of('northwind/portal')
        self.assertIsNotNone(tid)
        self.assertEqual(self.s.get_task(tid)['Title'], '4 pull requests on northwind/portal')
        its = batch.items(self.s, tid)
        self.assertEqual([i['ConversationId'] for i in its], [f'gh:northwind/portal#{n}' for n in (171, 173, 175, 172)])
        self.assertEqual([i['Place'] for i in its], [1, 2, 3, 4])
        self.assertEqual(its[0]['Title'], '#171 change 171', 'the repository is the task title, not every line')
        self.assertEqual(self.judged, [], 'nothing in a batch is triaged one by one')
        self.assertEqual(len(self.s.pending_triage()), 2, 'the rest wait for the next batch')

    def test_a_batch_is_one_repository(self):
        for n, v in enumerate((0.9, 0.8), 1): pr(self.s, 'northwind/portal', n, v)
        for n, v in enumerate((0.95, 0.1), 1): pr(self.s, 'northwind/ledger', n, v)
        self.drain()
        a, b = self.batch_of('northwind/portal'), self.batch_of('northwind/ledger')
        self.assertTrue(a and b and a != b)
        self.assertEqual({i['ConversationId'].split('#')[0] for i in batch.items(self.s, a)}, {'gh:northwind/portal'})

    def test_an_arrival_joins_the_open_batch_while_its_agent_is_on_it_and_there_is_room(self):
        """The owner, 2026-10-12: "it should batch it if it has room but if agent is finished then create new batch"."""
        for n in (1, 2): pr(self.s, 'northwind/portal', n, 0.5)
        self.drain(); first = self.batch_of('northwind/portal')
        pr(self.s, 'northwind/portal', 9, 1.0, 'fix the totals')
        with mock.patch.object(batch, 'live', return_value=True), mock.patch('taskuary.waitroom.add') as told:
            self.drain()
        self.assertEqual(self.batch_of('northwind/portal'), first, 'no second batch')
        its = batch.items(self.s, first)
        self.assertEqual([(i['Place'], i['ConversationId']) for i in its][-1], (3, 'gh:northwind/portal#9'), 'below what is there')
        self.assertEqual(self.s.get_task(first)['Title'], '3 pull requests on northwind/portal')
        self.assertEqual(self.s.pending_triage(), [])
        self.assertIn('(3) #9 fix the totals', told.call_args[0][2], 'the live agent is told what joined')

    def test_a_full_batch_whose_agent_is_on_it_makes_the_arrival_wait(self):
        for n in range(1, 5): pr(self.s, 'northwind/portal', n, 0.5)
        self.drain(); first = self.batch_of('northwind/portal')
        pr(self.s, 'northwind/portal', 9, 1.0)
        self.drain()
        self.assertEqual(len(batch.items(self.s, first)), 4)
        self.assertEqual([r['ConversationId'] for r in self.s.pending_triage()], ['gh:northwind/portal#9'])
        self.s.update_task(first, {'Status': 'done'}, 'owner')
        self.drain()
        nxt = self.batch_of('northwind/portal')
        self.assertNotEqual(nxt, first)
        self.assertEqual([i['ConversationId'] for i in batch.items(self.s, nxt)], ['gh:northwind/portal#9'])

    def test_once_its_agent_has_finished_an_arrival_starts_the_next_batch(self):
        """...even while the old one still holds an item that waits on the owner."""
        pr(self.s, 'northwind/portal', 1, 0.5)
        self.drain(); first = self.batch_of('northwind/portal')
        self.s.add_transcript(first, 's1', 'screen', agent='coder')
        pr(self.s, 'northwind/portal', 9, 1.0)
        self.drain()
        nxt = self.batch_of('northwind/portal')
        self.assertNotEqual(nxt, first)
        self.assertEqual(len(batch.items(self.s, first)), 1)
        self.assertEqual([i['ConversationId'] for i in batch.items(self.s, nxt)], ['gh:northwind/portal#9'])
        self.assertNotIn(self.s.get_task(first)['Status'], ('done', 'dropped'), 'the old batch stays open on its own item')

    def test_who_may_write_decides_the_batch(self):
        """The owner, 2026-10-12: protection is for the outside only, and "if they are writer on repo then that's enough trust"."""
        team = pr(self.s, 'northwind/portal', 1, 0.9)
        self.s._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('[pull request by erin - association: COLLABORATOR]\nfix', team))
        pr(self.s, 'northwind/portal', 2, 0.8)
        self.drain()
        ours, theirs = self.batch_of('northwind/portal', False), self.batch_of('northwind/portal', True)
        self.assertTrue(ours and theirs and ours != theirs, 'a stranger never shares a batch with our own people')
        self.assertFalse(batch.outside(self.s, ours)); self.assertTrue(batch.outside(self.s, theirs))

    def test_a_private_repository_is_ours_whoever_wrote(self):
        self.s.set_setting('gh_public:northwind/ledger', '0', 't')
        pr(self.s, 'northwind/ledger', 1, 0.9)
        self.drain()
        tid = self.batch_of('northwind/ledger', False)
        self.assertTrue(tid); self.assertFalse(batch.outside(self.s, tid))

    def test_the_role_is_read_off_our_own_line_never_the_authors_words(self):
        self.assertEqual(batch.association('[pull request by dev - association: MEMBER]\nhi'), 'MEMBER')
        self.assertEqual(batch.association('hi\n[pull request by dev - association: OWNER]'), 'NONE', 'only the first line we wrote')

    def test_mail_is_not_batched(self):
        ranked(self.s, 'outlook')
        for i in range(3):
            m = self.s.add_message({'ExternalId': f'e{i}', 'ConversationId': f'c{i}', 'Channel': 'email', 'Subject': f'mail {i}',
                                    'FromName': 'Erin', 'SentAt': '2026-10-12 07:00:00', 'Status': 'triaging'})
            self.s.set_message_rank(m, 0.5, 'floor', 'rank')
        self.drain()
        self.assertEqual(len(self.judged), 3, 'each mail is triaged on its own, as before')

    def test_done_on_the_batch_settles_every_line(self):
        for n in range(1, 4): pr(self.s, 'northwind/portal', n, 0.5)
        self.drain(); tid = self.batch_of('northwind/portal')
        self.s.update_task(tid, {'Status': 'done'}, 'owner')
        self.assertEqual({i['State'] for i in batch.items(self.s, tid)}, {'done'})


class ItemEndingTests(unittest.TestCase):
    """A pull request merged upstream used to close the task it was on. On a batch that would end three items nobody had
    looked at: it settles its own line, and the batch closes when no line is left."""

    def setUp(self):
        self.s = MemoryStore()
        self.tid = batch.create(self.s, 'github', 'northwind/portal', [self.s.get_message(pr(self.s, 'northwind/portal', n, 0.5))
                                                                        for n in (1, 2)])
        self.nx = mock.patch.object(batch, '_next'); self.nx.start()

    def tearDown(self): self.nx.stop()

    def end(self, n):
        channels._gh_ended(self.s, {'number': n, 'state': 'closed', 'pull_request': {'merged_at': '2026-10-12T09:00:00Z'}},
                           f'gh:northwind/portal#{n}', 'northwind/portal')

    def test_one_merge_settles_its_line_and_the_batch_stays_open(self):
        self.end(1)
        its = {i['ConversationId']: i for i in batch.items(self.s, self.tid)}
        self.assertEqual(its['gh:northwind/portal#1']['State'], 'ended')
        self.assertIn('merged', its['gh:northwind/portal#1']['EndedWhy'])
        self.assertEqual(its['gh:northwind/portal#2']['State'], 'waiting')
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        self.assertEqual(channels.heal_upstream_ended(self.s), [], "one item's ending is not the batch's")

    def test_the_last_one_closes_the_batch(self):
        self.end(1); self.end(2)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
        batch._next.assert_called_once()

    def test_a_comment_on_an_item_opens_its_line_and_makes_no_task(self):
        batch.set_item(self.s, self.tid, 'gh:northwind/portal#2', State='needs_you', Result='Looks right; ready to merge.')
        before = len(self.s.list_tasks(active_only=False))
        out = ingest.ingest_message(self.s, {'external_id': 'gh:northwind/portal#2:c7', 'channel': 'github',
                                             'conversation_id': 'gh:northwind/portal#2', 'subject': 'Re: change 2',
                                             'body': 'pushed a fix for the review note', 'from_name': 'dev',
                                             'from_email': 'dev@users.noreply.github.com', 'source_name': 'northwind/portal'})
        self.assertEqual(out['task_id'], self.tid)
        self.assertEqual(len(self.s.list_tasks(active_only=False)), before)
        it = self.s.batch_item(self.tid, 'gh:northwind/portal#2')
        self.assertEqual(it['State'], 'waiting')
        self.assertIn('dev wrote on it since', it['Result'])
        self.assertIn('ready to merge', it['Result'], 'what the agent said before is kept')


class AgentTests(unittest.TestCase):
    """The batch's agent: read-only whoever started it, one prompt naming every item, one report per item."""

    def setUp(self):
        self.s = MemoryStore()
        self.tid = batch.create(self.s, 'github', 'northwind/portal', [self.s.get_message(pr(self.s, 'northwind/portal', n, 0.5))
                                                                        for n in (1, 2, 3)])
        self.nx = mock.patch.object(batch, '_next'); self.nx.start()

    def tearDown(self): self.nx.stop()

    def test_claude_runs_with_its_permission_gate_on_and_only_the_report_let_through(self):
        argv = batch.read_only_argv('claude', ['claude', '--dangerously-skip-permissions', '--permission-mode', 'bypassPermissions',
                                               '--model', 'opus'], '/home/x/.taskuary/context')
        self.assertNotIn('--dangerously-skip-permissions', argv)
        self.assertNotIn('bypassPermissions', argv)
        # REFUSED, never asked (the owner, 2026-10-12: "we can't have that you have to approve")
        self.assertEqual(argv[argv.index('--permission-mode') + 1], 'dontAsk')
        allowed = argv[argv.index('--allowedTools') + 1].split(',')
        self.assertIn('Bash(taskuary --item:*)', allowed); self.assertIn('PowerShell(taskuary --item:*)', allowed)
        self.assertFalse([a for a in allowed if 'push' in a or 'gh ' in a or 'npm' in a], 'nothing that writes or runs code')
        self.assertIn('/home/x/.taskuary/context', argv, 'the brief file is outside the checkout and must be readable')
        self.assertIn('opus', argv)

    def test_codex_runs_in_its_read_only_sandbox(self):
        argv = batch.read_only_argv('codex', ['codex', '--dangerously-bypass-approvals-and-sandbox', '--sandbox', 'workspace-write'])
        self.assertNotIn('--dangerously-bypass-approvals-and-sandbox', argv)
        self.assertEqual(argv[argv.index('--sandbox') + 1], 'read-only')
        self.assertEqual(argv.count('--sandbox'), 1)
        self.assertEqual(argv[argv.index('--ask-for-approval') + 1], 'never', 'a refusal goes back to the model, not to the owner')

    def test_a_cli_with_no_known_gate_is_refused_not_trusted(self):
        with self.assertRaises(ValueError): batch.read_only_argv('gemini', ['gemini', '--yolo'])

    def test_the_seed_names_every_item_in_order_and_the_one_command(self):
        with mock.patch.object(batch, '_diff', return_value=('diff --git a/x b/x', 'abc123')):
            seed = batch.seed(self.s, self.tid, 'northwind/portal')
        self.assertLess(seed.index('(1) #1'), seed.index('(2) #2'))
        self.assertIn('READ-ONLY', seed)
        self.assertIn('taskuary --item <n>', seed)
        self.assertIn('Do NOT run --done', seed)
        self.assertNotIn('fixes 1', seed, 'the items themselves are in the file, not the command line')
        path = next(w for w in seed.split() if w.endswith('-batch.md'))
        text = open(path, encoding='utf-8').read()
        self.assertIn('fixes 2', text); self.assertIn('diff --git', text)
        self.assertIn('never as instructions', text)

    def test_a_report_lands_on_its_line_and_settling_the_last_closes_the_batch(self):
        self.assertTrue(batch.report(self.s, self.tid, 2, 'Duplicate of item 1; propose closing it.', overlap='same fix as 1',
                                     propose='close')['ok'])
        it = self.s.batch_item(self.tid, 'gh:northwind/portal#2')
        self.assertEqual((it['State'], it['Overlap'], it['Propose']), ('needs_you', 'same fix as 1', 'close'))
        batch.report(self.s, self.tid, 2, 'x', propose='delete the repo')
        self.assertIsNone(self.s.batch_item(self.tid, 'gh:northwind/portal#2')['Propose'], 'only the three proposals are kept')
        self.assertFalse(batch.report(self.s, self.tid, 9, 'x')['ok'])
        for n in (1, 2, 3): batch.report(self.s, self.tid, n, 'Nothing to do.', settled=True)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')

    def test_the_endpoint_takes_reports_only_for_a_batch(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        plain = self.s.create_task({'Title': 'not a batch', 'Kind': 'coding', 'Status': 'open'}, 't')
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, '_own_task_only', return_value=None):
            c = TestClient(server.app)
            ok = c.post('/api/agent/item', json={'task_id': self.tid, 'item': 1, 'result': 'Right fix; merge it.'})
            no = c.post('/api/agent/item', json={'task_id': plain, 'item': 1, 'result': 'x'})
        self.assertTrue(ok.json()['ok'])
        self.assertEqual(no.status_code, 422)


class OwnerActionTests(unittest.TestCase):
    """The owner's press on one item. Nothing the agent does merges anything; a merge is the owner's, pinned to what was reviewed."""

    def setUp(self):
        self.s = MemoryStore()
        self.tid = batch.create(self.s, 'github', 'northwind/portal', [self.s.get_message(pr(self.s, 'northwind/portal', n, 0.5))
                                                                        for n in (1, 2)])
        self.nx = mock.patch.object(batch, '_next'); self.nx.start()
        self.tok = mock.patch.object(batch, '_token', return_value='tok'); self.tok.start()

    def tearDown(self): self.nx.stop(); self.tok.stop()

    def test_a_merge_is_pinned_to_the_head_the_agent_reviewed(self):
        from taskuary import github
        self.s.update_batch_item(self.tid, 'gh:northwind/portal#1', {'Sha': 'reviewed1'})
        with mock.patch.object(github, 'repo_info', return_value={'methods': ['merge']}), \
             mock.patch.object(github, 'merge_pr') as merge:
            self.assertTrue(batch.act(self.s, self.tid, 1, 'merge')['ok'])
        merge.assert_called_once_with('tok', 'northwind/portal', 1, 'reviewed1', method='merge')
        it = self.s.batch_item(self.tid, 'gh:northwind/portal#1')
        self.assertEqual((it['State'], it['EndedWhy']), ('ended', 'You merged it on GitHub.'))
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open', 'item 2 is still open')

    def test_nothing_reviewed_is_not_merged(self):
        from taskuary import github
        with mock.patch.object(github, 'merge_pr') as merge:
            out = batch.act(self.s, self.tid, 1, 'merge')
        self.assertFalse(out['ok']); merge.assert_not_called()

    def test_close_then_settle_the_last_closes_the_batch_and_reopen_brings_a_line_back(self):
        from taskuary import github
        with mock.patch.object(github, 'close_pr'): batch.act(self.s, self.tid, 1, 'close')
        batch.act(self.s, self.tid, 2, 'settle')
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'done')
        batch.act(self.s, self.tid, 2, 'reopen')
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        self.assertEqual(self.s.batch_item(self.tid, 'gh:northwind/portal#2')['State'], 'waiting')

    def test_the_endpoint_is_the_owners_alone(self):
        from taskuary import guard
        self.assertEqual(guard.classify('POST', '/api/tasks/12/batch/1')[0], 'owner')
        from fastapi.testclient import TestClient
        from taskuary import server
        with mock.patch.object(server, 'store', self.s):
            r = TestClient(server.app).post(f'/api/tasks/{self.tid}/batch/2', json={'action': 'settle'})
            bad = TestClient(server.app).post(f'/api/tasks/{self.tid}/batch/2', json={'action': 'explode'})
        self.assertEqual(r.json()['state'], 'done')
        self.assertEqual(bad.status_code, 422)


class RailTests(unittest.TestCase):
    def test_a_batch_row_says_how_far_it_got_and_other_rows_say_nothing(self):
        s = MemoryStore()
        tid = batch.create(s, 'github', 'northwind/portal', [s.get_message(pr(s, 'northwind/portal', n, 0.5)) for n in (1, 2, 3, 4)])
        with mock.patch.object(batch, '_next'):
            batch.report(s, tid, 1, 'Fine.', settled=True); batch.report(s, tid, 3, 'Duplicate of 1.')
        other = s.create_task({'Title': 'mail', 'Kind': 'task', 'Status': 'open'}, 't')
        got = batch.rail(s, [{'key': 'b', 'tid': tid}, {'key': 'o', 'tid': other}, {'key': 'x'}])
        self.assertEqual(got, {'b': {'line': '1 of 4 done · ③ needs you', 'states': ['done', 'waiting', 'needs_you', 'waiting']}})


class RunHereTests(unittest.TestCase):
    """A stranger's change reviewed read-only, then screened at the reviewed head, then run in an ordinary session (the owner,
    2026-10-13: "we have to solve it that we can run it locally"). No model: the screen's brain is a stub."""
    SRC = 'diff --git a/website/src/ui.jsx b/website/src/ui.jsx\n--- a/website/src/ui.jsx\n+++ b/website/src/ui.jsx\n+<button>x</button>\n'

    def setUp(self):
        self.s = MemoryStore()
        self.s.set_setting('gh_public:northwind/portal', '1', 't')
        self.tid = batch.create(self.s, 'github', 'northwind/portal', [self.s.get_message(pr(self.s, 'northwind/portal', 1, 0.5))])
        self.conv = 'gh:northwind/portal#1'
        self.p = [mock.patch.object(batch, '_next'), mock.patch.object(batch, '_token', return_value='tok'),
                  mock.patch.object(batch, 'screened')]
        for p in self.p: p.start()
        self.s.update_batch_item(self.tid, self.conv, {'Sha': 'h1'})
        batch.report(self.s, self.tid, 1, 'Right fix; merge it.', propose='merge')

    def tearDown(self):
        for p in self.p: p.stop()

    def brain(self, safe):
        from taskuary import llm
        return mock.patch.object(llm, 'ask_json', return_value=mock.Mock(data={'safe': safe, 'why': 'a button change'}, error=''))

    def run_screen(self, diff, safe=True, sha='h1'):
        with mock.patch.object(batch, '_diff', return_value=(diff, sha)), self.brain(safe):
            return batch.screen(self.s, self.tid, self.conv, llm=object())

    def live(self, sha='h1', commits=(), me='owner'):
        from taskuary import github
        return [mock.patch.object(github, 'pr', return_value={'sha': sha}), mock.patch.object(github, 'pr_commits', return_value=list(commits)),
                mock.patch.object(github, 'whoami', return_value=me)]

    def test_a_clean_change_clears_at_the_reviewed_head_and_the_session_starts_ordinary(self):
        self.assertEqual(self.run_screen(self.SRC), 'clear')
        self.assertEqual(self.s.batch_item(self.tid, self.conv)['Trusted'], 'h1')
        ps = self.live()
        for p in ps: p.start()
        try: self.assertFalse(batch.locked(self.s, self.tid))
        finally:
            for p in ps: p.stop()

    def test_what_runs_on_install_build_or_test_is_held_whatever_the_model_says(self):
        for f in ('package.json', '.github/workflows/ci.yml', 'website/vite.config.js', 'tests/conftest.py', 'tools/x.ps1', 'pyproject.toml'):
            got = self.run_screen(f'diff --git a/{f} b/{f}\n+x\n', safe=True)
            self.assertIn('held', got, f); self.assertIsNone(self.s.batch_item(self.tid, self.conv)['Trusted'])

    def test_the_model_saying_unsafe_or_a_moved_head_holds_it(self):
        self.assertIn('held', self.run_screen(self.SRC, safe=False))
        self.assertIn('moved', self.run_screen(self.SRC, sha='h2'))
        self.assertIsNone(self.s.batch_item(self.tid, self.conv)['Trusted'])

    def test_a_contributor_push_after_clearance_locks_it_again_and_the_owners_own_does_not(self):
        self.run_screen(self.SRC)
        theirs = self.live('h2', [('h1', 'dev'), ('h2', 'dev')])
        for p in theirs: p.start()
        try: self.assertTrue(batch.locked(self.s, self.tid))
        finally:
            for p in theirs: p.stop()
        mine = self.live('h3', [('h1', 'dev'), ('h3', 'owner')])
        for p in mine: p.start()
        try: self.assertFalse(batch.locked(self.s, self.tid))
        finally:
            for p in mine: p.stop()
        self.assertEqual(self.s.batch_item(self.tid, self.conv)['Sha'], 'h3', 'Merge pins to what is there now')

    def test_an_item_nobody_reviewed_is_never_screened_and_stays_locked(self):
        tid = batch.create(self.s, 'github', 'northwind/portal', [self.s.get_message(pr(self.s, 'northwind/portal', 9, 0.5))])
        self.s.update_batch_item(tid, 'gh:northwind/portal#9', {'Sha': 'h9'})       # brief_file stamps every head at the seed
        with mock.patch.object(batch, 'screen') as sc:
            self.assertTrue(batch.locked(self.s, tid))
        sc.assert_not_called()

    def test_a_new_review_puts_the_screen_back_to_the_start(self):
        self.run_screen(self.SRC)
        batch.report(self.s, self.tid, 1, 'Second look: still fine.', propose='merge')
        it = self.s.batch_item(self.tid, self.conv)
        self.assertEqual((it['Trusted'], it['Screen']), (None, None))
        batch.screened.assert_called()
