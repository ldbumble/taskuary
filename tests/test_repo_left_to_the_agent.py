"""Which repository a coding task is worked in is the CODING AGENT's to pick (the owner, 2026-11-06: "let's take repo decision out of the
triage - remove it completely and then the use_repo tool to figure it out or check out folders").

Triage says the kind and nothing about where. A structural fact still places the task (the owner's `repo:` tag, a GitHub or GitLab item's
own repository, the agent's own earlier pick); otherwise the session opens in the task's own folder with a REPOSITORIES block, and
use_repo validates, records and switches. Real git checkouts in temp folders; no pty, no network."""
import json, os, subprocess, tempfile, unittest
from unittest import mock

os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp())

from taskuary import agenttools, guard, ingest, landing, repochoice, terminal, triage
from taskuary.store import MemoryStore, SQLiteStore
from taskuary.testing import Factory

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake', 'conversation_id': 'c-ledger',
       'subject': 'Invoice rounding', 'body': 'The invoice totals round the wrong way in the ledger export. Can you fix it?',
       'sent_at': '2026-11-06 09:00:00'}


def git(cwd, *a): return subprocess.run(['git', '-C', cwd, *a], capture_output=True, text=True, check=True).stdout.strip()


def checkout(root, name, remote=None):
    d = os.path.join(root, name); os.makedirs(d)
    git(d, 'init', '-q', '-b', 'master')
    if remote: git(d, 'remote', 'add', 'origin', remote)
    with open(os.path.join(d, 'README.md'), 'w', encoding='utf-8') as f: f.write(name)
    git(d, 'add', 'README.md'); git(d, '-c', 'user.name=Alex Doyle', '-c', 'user.email=alex@northwind.example', 'commit', '-q', '-m', 'start')
    return d


class TriageNamesNoRepositoryTests(unittest.TestCase):
    def test_a_coding_verdict_writes_no_repository_on_the_task(self):
        s, seen = MemoryStore(), []
        s.set_setting('coding_auto_enabled', '0', 't')
        s.save_doc('soul', '## Repository map\n- **northwind/ledger**: invoicing and the ledger export\n', 'owner')
        def llm(system, user, **k):
            seen.append({'system': system, 'user': json.loads(user), 'want': k.get('want')})
            # a model reading an old guide may still answer one - it lands nowhere
            return json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'a bug in the export', 'repository': 'northwind/ledger',
                               'needs_repo_choice': True, 'repo_reason': 'the export'})
        with mock.patch.object(ingest, '_spawn'): out = ingest.ingest_message(s, dict(MSG), llm=llm)
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Kind'], 'coding')                                       # still coding work
        self.assertNotIn('repo', str(t.get('Tags') or ''))
        self.assertFalse(any('repositor' in str(c['Body']).lower() for c in s.list_comments(out['task_id'])))
        self.assertFalse({'known_repositories', 'project_context'} & set(seen[0]['user']))
        self.assertNotIn('needs_repo_choice', seen[0]['system']); self.assertNotIn('known_repositories', seen[0]['system'])
        props = (seen[0]['want'] or triage.verdict_schema())['schema']['properties']
        self.assertFalse({'repository', 'needs_repo_choice', 'repo_reason'} & set(props))

    def test_the_guide_asks_for_none_and_an_owners_edited_copy_loses_the_paragraph(self):
        from taskuary import store as store_mod
        tmpl = open(os.path.join(os.path.dirname(store_mod.__file__), 'templates', 'triage.md'), encoding='utf-8').read()
        self.assertNotIn('Which repository', tmpl); self.assertNotIn(store_mod._REPO_CHOICE_WAS, tmpl)
        p = os.path.join(tempfile.mkdtemp(), 't.db')
        s = SQLiteStore(p); s.save_doc('triage', f'Mine first.\n\n{store_mod._REPO_CHOICE_WAS}\n\nMy last line.', 'owner')
        s.cx.execute("DELETE FROM setting WHERE Name='triage_no_repo_choice'"); s.cx.commit(); s.close()
        after = SQLiteStore(p).doc('triage')
        self.assertNotIn('Which repository', after); self.assertIn('Mine first.', after); self.assertIn('My last line.', after)


class StructureStillPlacesItTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self.prof = {'cwd_map': {'northwind/ledger': 'C:/code/ledger', 'northwind/portal': 'C:/code/portal'}}

    def test_the_owners_tag_wins_over_everything(self):
        tid = self.fx.task(kind='coding', Tags='repo:northwind/portal,agent-repo:northwind/ledger')
        self.assertEqual(terminal.guess_repo(self.s, tid, self.prof), ('northwind/portal', 'tagged on the task'))

    def test_a_code_hosts_item_names_its_own_repository(self):
        for ch, name, said in (('github', 'northwind/portal', 'GitHub'), ('gitlab', 'northwind/infra/portal', 'GitLab')):
            tid = self.fx.task(kind='coding')
            self.fx.message(tid, channel=ch, SourceName=name)
            self.assertEqual(terminal.guess_repo(self.s, tid, self.prof), (name, f'the {said} item belongs to this repository'))

    def test_the_agents_own_pick_carries_to_its_next_session(self):
        tid = self.fx.task(kind='coding', Tags='agent-repo:northwind/ledger')
        self.assertEqual(terminal.guess_repo(self.s, tid, self.prof)[0], 'northwind/ledger')

    def test_nothing_else_decides_it_not_even_the_only_path_or_an_old_triage_tag(self):
        tid = self.fx.task(kind='coding', Tags='triage-repo:northwind/ledger')
        self.assertIsNone(terminal.guess_repo(self.s, tid, {'cwd_map': {'northwind/ledger': 'C:/code/ledger'}})[0])
        self.assertIsNone(terminal.guess_repo(self.s, self.fx.task(kind='coding'), self.prof)[0])

    def test_an_unplaced_session_opens_in_the_tasks_folder_with_the_repositories_to_pick_from(self):
        tid = self.fx.task(kind='coding', title='Fix the export')
        self.s.save_doc('soul', '## Repository map\n- **northwind/ledger**: invoicing and the ledger export\n', 'owner')
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', **self.prof}))
        seen = {}
        class T:
            def __init__(self, argv, cwd, *a, **k): seen['cwd'] = cwd; self.sid, self.cwd = 'x', cwd
        with mock.patch.object(terminal, 'Term', T), mock.patch.object(terminal, 'agent_argv', return_value=['claude']), \
             mock.patch.object(terminal, 'pretrust'), mock.patch('taskuary.hooks.install_user'), mock.patch('taskuary.agenttools.session_args', return_value=[]):
            terminal.open_session(self.s, 'coding', tid, None, None, 30, 100, 'owner',
                                  seed_fn=lambda here: seen.update(seed=terminal.seed_text(self.s, tid, None, None, here, cli='claude')) or seen['seed'])
        self.assertTrue(repochoice.is_scratch(tid, seen['cwd']))
        self.assertIn('REPOSITORIES - no checkout is chosen', seen['seed']); self.assertIn('use_repo', seen['seed'])
        self.assertIn('northwind/ledger (C:/code/ledger): invoicing and the ledger export', seen['seed'])
        self.assertNotIn('REPO: ', seen['seed'])

    def test_with_no_repository_known_the_agent_is_told_it_may_start_one(self):
        """The owner, 2026-11-12: "even if you don't have repos you can start coding session and it will figure out what to do either
        start a new repo or whatever is needed" - with none known, the block said only that, and left the agent nowhere to go."""
        tid = self.fx.task(kind='coding', title='A small tool for the rota')
        said = repochoice.block(self.s, tid, 'C:/tasks/1')
        self.assertIn('No repository is known yet', said); self.assertIn('git init', said); self.assertIn('use_repo', said)

    def test_an_unplaced_task_shares_a_checkout_with_nobody(self):
        from taskuary import blackboard as bb
        a, b = self.fx.task(kind='coding'), self.fx.task(kind='coding')
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', **self.prof}))
        self.assertNotEqual(bb.target_cwd(self.s, a, 'coding'), bb.target_cwd(self.s, b, 'coding'))
        self.assertTrue(repochoice.is_scratch(a, bb.target_cwd(self.s, a, 'coding')))


class UseRepoTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); root = self.tmp.name
        self.code, self.elsewhere = os.path.join(root, 'code'), os.path.join(root, 'elsewhere')
        os.makedirs(self.code); os.makedirs(self.elsewhere)
        self.ledger = checkout(self.code, 'ledger', 'git@github.com:northwind/ledger.git')
        self.portal = checkout(self.code, 'portal-work', 'https://github.com/northwind/portal.git')
        self.outside = checkout(self.elsewhere, 'secret', 'https://github.com/org/app.git')
        self.plain = os.path.join(self.code, 'notes'); os.makedirs(self.plain)
        self.s = MemoryStore(); self.fx = Factory(self.s)
        self.s.set_setting(repochoice.FOLDERS_KEY, self.code, 't')
        self.s.save_doc('soul', '## Repository map\n- **northwind/ledger**: invoicing\n', 'owner')
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'northwind/ledger': self.ledger}}))
        self.tid = self.fx.task(kind='coding', title='Fix the export')
        self.p = [mock.patch('taskuary.origin.of_task', return_value=('owner', '')), mock.patch('taskuary.terminal.remember_path')]
        for p in self.p: p.start()
        repochoice._found.clear()

    def tearDown(self):
        for p in self.p: p.stop()
        try: self.tmp.cleanup()
        except OSError: pass

    def test_a_known_repository_by_name_is_recorded_on_the_task(self):
        out = repochoice.use(self.s, self.tid, 'ledger', 'the export is the ledger code')
        self.assertEqual((out['repo'], out['path']), ('northwind/ledger', self.ledger))
        self.assertTrue(self.s.task_has_tag(self.tid, 'agent-repo:northwind/ledger'))
        self.assertEqual(terminal.guess_repo(self.s, self.tid, {})[0], 'northwind/ledger')     # ci.py and the next session read it
        self.assertEqual(landing.record(self.s, self.tid)['cwd'], self.ledger)                 # the landing card's start
        self.assertIn('Working in northwind/ledger - the export is the ledger code', [c['Body'] for c in self.s.list_comments(self.tid)])
        self.assertIn(f'cd "{self.ledger}"', out['says'])

    def test_the_live_session_moves_and_its_hooks_still_find_it(self):
        from types import SimpleNamespace
        from taskuary import hooks
        scratch = repochoice.scratch(self.tid)
        t = SimpleNamespace(alive=True, task_id=self.tid, cwd=scratch, opened_in=scratch, started='2026-11-06 09:00:00', sid='s1', agent='coding',
                            argv=['claude'])
        with mock.patch.dict(terminal.SESSIONS, {'s1': t}, clear=True):
            repochoice.use(self.s, self.tid, self.ledger, 'the ledger export')
            self.assertEqual(t.cwd, self.ledger)
            self.assertTrue(hooks._here(t, scratch) and hooks._here(t, self.ledger))
        wall = [n for n in self.s.notes(None, 20) if n.get('TaskId') == self.tid]
        self.assertTrue(wall and wall[0]['Body'].startswith('working in northwind/ledger'))

    def test_a_found_checkout_joins_the_project_map_with_where_it_was_found(self):
        out = repochoice.use(self.s, self.tid, self.portal, 'the login page lives here')
        self.assertEqual(out['repo'], 'northwind/portal'); self.assertTrue(out['added'])
        line = f'Agent added northwind/portal (found at {self.portal})'
        self.assertIn(f'- **northwind/portal**: {line}', self.s.get_doc('soul'))
        self.assertIn(line, [c['Body'] for c in self.s.list_comments(self.tid)])
        terminal.remember_path.assert_called_once_with(self.s, 'coding', 'northwind/portal', self.portal)

    def test_a_folder_that_is_no_git_checkout_is_refused(self):
        with self.assertRaises(ValueError) as e: repochoice.use(self.s, self.tid, self.plain, 'notes')
        self.assertIn('not a git checkout', str(e.exception))
        with self.assertRaises(ValueError): repochoice.use(self.s, self.tid, 'northwind/nowhere', 'a guess')
        self.assertFalse(any(x.startswith('agent-repo:') for x in str(self.s.get_task(self.tid).get('Tags') or '').split(',')))

    def test_a_checkout_outside_the_allowed_folders_is_refused(self):
        with self.assertRaises(PermissionError) as e: repochoice.use(self.s, self.tid, self.outside, 'found it')
        self.assertIn('Settings → Agents', str(e.exception))
        self.s.set_setting(repochoice.FOLDERS_KEY, f'{self.code}\n{self.elsewhere}', 'owner')
        self.assertEqual(repochoice.use(self.s, self.tid, self.outside, 'found it')['repo'], 'org/app')

    def test_the_owners_pick_is_never_overruled_and_a_strangers_task_picks_nothing(self):
        self.s.tag_task(self.tid, 'repo:northwind/ledger', actor='owner')
        with self.assertRaises(PermissionError): repochoice.use(self.s, self.tid, self.portal, 'better')
        other = self.fx.task(kind='coding')
        with mock.patch('taskuary.origin.of_task', return_value=('stranger', 'a new sender')), self.assertRaises(PermissionError):
            repochoice.use(self.s, other, self.ledger, 'theirs')

    def test_find_repos_lists_the_checkouts_under_the_allowed_folders(self):
        rows = repochoice.find(self.s)
        self.assertEqual(sorted(r['repo'] for r in rows), ['northwind/ledger', 'northwind/portal'])     # not the one outside, not notes/
        self.assertTrue(all(r['last'] for r in rows)); self.assertEqual({r['repo']: r['known'] for r in rows}['northwind/ledger'], True)
        self.assertEqual([r['repo'] for r in repochoice.find(self.s, 'portal')], ['northwind/portal'])

    def test_the_door_answers_and_the_owners_change_replaces_the_agents_pick(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        with mock.patch.object(server, 'store', self.s):
            c = TestClient(server.app)
            r = c.post('/api/agent/use-repo', json={'task_id': self.tid, 'path_or_name': 'ledger', 'why': 'the export'})
            self.assertEqual((r.status_code, r.json()['repo']), (200, 'northwind/ledger'))
            self.assertEqual(c.post('/api/agent/use-repo', json={'task_id': self.tid, 'path_or_name': self.outside, 'why': 'x'}).status_code, 403)
            self.assertEqual(c.get('/api/agent/repos', params={'task_id': self.tid, 'query': 'portal'}).json()['data'][0]['repo'], 'northwind/portal')
            c.put(f'/api/tasks/{self.tid}/repo', json={'repo': 'northwind/portal'})
        tags = str(self.s.get_task(self.tid).get('Tags') or '')
        self.assertIn('repo:northwind/portal', tags); self.assertNotIn('agent-repo:', tags)

    def test_the_tools_are_listed_and_their_doors_are_the_agents(self):
        names = {t['name'] for t in agenttools.listing()}
        self.assertTrue({'use_repo', 'find_repos'} <= names)
        for n in ('use_repo', 'find_repos'): self.assertEqual(guard.classify(*agenttools.TOOLS[n][3])[0], 'agent' if n == 'use_repo' else 'read')
        seen = {}
        agenttools.call(self.s, self.tid, 'use_repo', {'path_or_name': 'ledger', 'why': 'w'},
                        {'use_repo': lambda tid, target, why: seen.update(tid=tid, target=target, why=why) or {'says': 'ok'}})
        self.assertEqual(seen, {'tid': self.tid, 'target': 'ledger', 'why': 'w'})
        self.assertIn('northwind/portal', agenttools.call(self.s, self.tid, 'find_repos', {'query': 'portal'}, {}))


if __name__ == '__main__':
    unittest.main()
