"""An outside pull request fixed in GitHub's cloud, never on this machine (cloudfix.py), and the settings that say who is outside
(the owner, 2026-10-12: "I still want to be able to process github public pr's ... run on cloud"; "Is this configurable in
settings please for private vs public stuff"). Invented repositories; GitHub is mocked."""
import io, json, re, unittest, zipfile
from unittest import mock

from taskuary import batch, cloudfix, github
from taskuary.store import MemoryStore

REPO = 'northwind/portal'


def row(s, n, assoc='CONTRIBUTOR', repo=REPO):
    return s.add_message({'ExternalId': f'gh:{repo}#{n}@r1', 'ConversationId': f'gh:{repo}#{n}', 'Channel': 'github', 'SourceName': repo,
                          'Subject': f'{repo}#{n} change {n}', 'FromName': 'dev', 'SentAt': '2026-10-12 07:00:00',
                          'BodyText': f'[pull request by dev - association: {assoc}]\nfixes {n}',
                          'SourceLink': f'https://github.com/{repo}/pull/{n}', 'Status': 'triaging'})


class Resp:
    def __init__(self, status=200, body=None, content=b''): self.status_code, self._b, self.content = status, body or {}, content
    ok = property(lambda self: self.status_code < 400)
    text = property(lambda self: json.dumps(self._b))
    headers = {}
    def json(self): return self._b


class TrustSettingsTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.r = self.s.get_message(row(self.s, 1))

    def test_defaults_are_writers_on_public_and_ours_on_private(self):
        self.s.set_setting(f'gh_public:{REPO}', '1', 't')
        self.assertTrue(batch.outside_row(self.s, self.r))
        self.s.set_setting(f'gh_public:{REPO}', '0', 't')
        self.assertFalse(batch.outside_row(self.s, self.r))

    def test_the_owner_moves_either_side(self):
        self.s.set_setting(f'gh_public:{REPO}', '0', 't'); self.s.set_setting('repo_trust_private', 'outside', 't')
        self.assertTrue(batch.outside_row(self.s, self.r), 'a private repository treated as outside')
        self.s.set_setting(f'gh_public:{REPO}', '1', 't')
        self.s.set_setting('repo_trust_public', 'anyone', 't'); self.assertFalse(batch.outside_row(self.s, self.r))
        member = self.s.get_message(row(self.s, 2, 'MEMBER'))
        self.s.set_setting('repo_trust_public', 'nobody', 't'); self.assertTrue(batch.outside_row(self.s, member))

    def test_the_knobs_are_on_the_page(self):
        knobs = json.load(open('taskuary/settings_schema.json', encoding='utf-8'))['knobs']
        for k in ('repo_trust_private', 'repo_trust_public', 'outside_prs'):
            self.assertEqual(knobs[k]['group'], 'Agent permissions')
            self.assertIn(self.s.get_setting(k), knobs[k]['options'], 'its default is one of its options')


class WorkflowTests(unittest.TestCase):
    def test_the_job_that_runs_their_code_cannot_push(self):
        fix, push = cloudfix.WORKFLOW.split('\n  push:')
        self.assertIn('permissions: {contents: read}', fix); self.assertIn('persist-credentials: false', fix)
        self.assertIn('permissions: {contents: write}', push)
        self.assertNotIn('claude', push.lower().replace('taskuary', '')); self.assertNotIn('npm', push)

    def test_no_input_is_spliced_into_a_shell_line(self):
        """A pull request's words reach the shell only through env (the ask is written from its review): never as ${{ }} in a script."""
        lines, scripts, i = cloudfix.WORKFLOW.splitlines(), [], 0
        while i < len(lines):
            l = lines[i]
            if l.strip().startswith(('run:', '- run:')):
                ind, body = len(l) - len(l.lstrip()), [l.split('run:', 1)[1]]
                i += 1
                while i < len(lines) and (not lines[i].strip() or len(lines[i]) - len(lines[i].lstrip()) > ind): body.append(lines[i]); i += 1
                scripts.append('\n'.join(body)); continue
            i += 1
        self.assertGreaterEqual(len(scripts), 4)
        for sc in scripts: self.assertNotIn('${{', sc, sc)

    def test_the_run_is_named_for_its_pull_request(self):
        # unquoted, YAML read ' #' as a comment and every run was named "Taskuary fix" - poll() could never find one
        self.assertIn("run-name: 'Taskuary fix #${{ inputs.pr }}'", cloudfix.WORKFLOW)

    def test_it_runs_the_head_that_was_reviewed_and_leaves_github_alone(self):
        self.assertIn('the pull request moved since it was reviewed', cloudfix.WORKFLOW)
        self.assertIn(":!.github", cloudfix.WORKFLOW)


class FixTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.s.set_setting(f'gh_public:{REPO}', '1', 't')
        rows = [self.s.get_message(row(self.s, 7))]
        self.tid = batch.create(self.s, 'github', REPO, rows, strangers=True)
        self.it = batch.items(self.s, self.tid)[0]
        batch.report(self.s, self.tid, 1, 'Right idea, but the label is missing.', propose='changes')
        self.s.update_batch_item(self.tid, self.it['ConversationId'], {'Sha': 'abc'})
        self.tok = mock.patch.object(batch, '_token', return_value='tok'); self.tok.start()

    def tearDown(self): self.tok.stop()

    def item(self): return batch.items(self.s, self.tid)[0]

    def test_review_only_refuses_and_says_where_to_turn_it_on(self):
        out = batch.act(self.s, self.tid, 1, 'fix')
        self.assertFalse(out['ok']); self.assertIn('Agent permissions', out['why'])

    def test_a_repository_not_set_up_is_offered_set_up_not_an_error(self):
        self.s.set_setting('outside_prs', 'cloud', 't')
        with mock.patch.object(cloudfix, 'setup_state', return_value={'repo': REPO, 'workflow': False, 'secret': None}):
            out = batch.act(self.s, self.tid, 1, 'fix')
        self.assertFalse(out['ok']); self.assertEqual(out['setup']['repo'], REPO)

    def test_fix_it_dispatches_the_reviewed_head_and_the_review(self):
        self.s.set_setting('outside_prs', 'cloud', 't')
        with mock.patch.object(cloudfix, 'setup_state', return_value={'repo': REPO, 'workflow': True, 'secret': True}), \
             mock.patch.object(github, 'repo_info', return_value={'default_branch': 'main'}), \
             mock.patch.object(cloudfix.requests, 'post', return_value=Resp(204)) as post:
            out = batch.act(self.s, self.tid, 1, 'fix')
        self.assertTrue(out['ok'], out)
        sent = post.call_args.kwargs['json']
        self.assertEqual((sent['ref'], sent['inputs']['pr'], sent['inputs']['sha']), ('main', '7', 'abc'))
        self.assertIn('the label is missing', sent['inputs']['ask'])
        self.assertEqual((self.item()['Fix'], self.item()['State']), ('running', 'working'))

    def test_a_finished_run_opens_the_fixs_pull_request_and_merge_merges_it(self):
        self.s.update_batch_item(self.tid, self.it['ConversationId'], {'Fix': 'running', 'FixAt': '2026-10-12T20:00:00Z'})
        z = io.BytesIO()
        with zipfile.ZipFile(z, 'w') as f: f.writestr('report.md', 'Added the label; 12 tests pass.')
        def get(url, **kw):
            if url.endswith('/runs'): return Resp(body={'workflow_runs': [{'id': 5, 'display_title': 'Taskuary fix #7', 'created_at': '2026-10-12T20:00:09Z',
                                                                          'status': 'completed', 'conclusion': 'success', 'html_url': 'u'}]})
            if url.endswith('/artifacts'): return Resp(body={'artifacts': [{'name': 'taskuary-fix', 'archive_download_url': 'zip'}]})
            if url == 'zip': return Resp(content=z.getvalue())
            if '/branches/' in url: return Resp(body={'commit': {'sha': 'fixhead'}})
            return Resp(404)
        with mock.patch.object(cloudfix.requests, 'get', side_effect=get), \
             mock.patch.object(github, 'repo_info', return_value={'default_branch': 'main', 'methods': ['merge', 'squash']}), \
             mock.patch.object(github, 'open_pr', return_value={'url': f'https://github.com/{REPO}/pull/9'}) as opened:
            self.assertEqual(cloudfix.poll(self.s), 1)
        self.assertEqual(opened.call_args.args[2], 'taskuary/pr-7')
        it = self.item()
        self.assertEqual((it['Fix'], it['FixLink'], it['Sha'], it['Propose']), ('done', f'https://github.com/{REPO}/pull/9', 'fixhead', 'merge'))
        self.assertIn('12 tests pass', it['Result'])
        with mock.patch.object(github, 'repo_info', return_value={'methods': ['merge', 'squash']}), \
             mock.patch.object(github, 'merge_pr') as merged, mock.patch.object(github, 'pr', return_value={'state': 'closed'}):
            self.assertTrue(batch.act(self.s, self.tid, 1, 'merge')['ok'])
        self.assertEqual(merged.call_args.args[1:4], (REPO, 9, 'fixhead'), 'the fix, pinned to the head the cloud pushed')
        self.assertEqual(merged.call_args.kwargs['method'], 'merge', "a merge commit keeps the contributor's commits")

    def test_our_own_peoples_fix_goes_to_the_agent_here(self):
        self.s.set_setting(f'gh_public:{REPO}', '0', 't')
        with mock.patch('taskuary.waitroom.add') as told:
            out = batch.act(self.s, self.tid, 1, 'fix')
        self.assertTrue(out['ok']); self.assertIn('FIX ITEM 1', told.call_args.args[2])


class TaskPageTests(unittest.TestCase):
    def test_fix_it_is_offered_only_where_it_can_run(self):
        """The owner, 2026-10-12: a Fix it that could only answer "turn it on in Settings" - "what does this do?" """
        from fastapi.testclient import TestClient
        from taskuary import server
        c, s = TestClient(server.app), server.store
        s.set_setting(f'gh_public:{REPO}', '1', 't'); s.set_setting('outside_prs', 'review', 't')
        tid = batch.create(s, 'github', REPO, [s.get_message(row(s, 41))], strangers=True)
        d = c.get(f'/api/tasks/{tid}').json()
        self.assertTrue(d['batchOutside']); self.assertFalse(d['batch'][0]['canFix'])
        s.set_setting('outside_prs', 'cloud', 't')
        self.assertTrue(c.get(f'/api/tasks/{tid}').json()['batch'][0]['canFix'])


if __name__ == '__main__':
    unittest.main()
