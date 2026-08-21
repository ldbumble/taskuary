"""HTTP API tests over the real FastAPI app (TestClient; store lives in the temp
TASKUARY_HOME from conftest). Covers the all-UI settings surface: agents, report
connections, previews, mssql helpers, app settings.
"""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import config, server
from taskuary.reports import REGISTRY

c = TestClient(server.app)


class GithubIngestTests(unittest.TestCase):
    ITEMS = [
        {'number': 1, 'title': 'Bug: importer crashes', 'body': 'stack trace here', 'html_url': 'https://x/1',
         'updated_at': '2026-08-20T10:00:00Z', 'user': {'login': 'teammate'}, 'author_association': 'MEMBER'},
        {'number': 2, 'title': 'Add my feature', 'body': 'please merge', 'html_url': 'https://x/2',
         'updated_at': '2026-08-20T11:00:00Z', 'user': {'login': 'drive-by'},
         'author_association': 'FIRST_TIME_CONTRIBUTOR', 'pull_request': {'url': 'https://x/pr/2'}},
    ]

    def test_per_repo_modes_and_the_contributor_line(self):
        """Issues and PRs are the source's own call per repo - and every item leads with WHO
        wrote it, so triage judges a stranger's PR on a public repo for what it is."""
        from datetime import datetime
        from taskuary.store import MemoryStore
        from taskuary.channels import ingest_github_issues
        s = MemoryStore()
        seen = {}
        fake = lambda sys_, usr, **kw: seen.update(usr=usr) or '{"intent": "task", "why": "bug"}'
        src = {'Address': 'org/app', 'ConfigJson': '{"issues": "tasks", "prs": "feed"}'}
        with mock.patch('taskuary.github.list_items', return_value=self.ITEMS):
            n = ingest_github_issues(s, src, 'tok', datetime.now(), llm=fake)
        self.assertEqual(n, 2)
        msgs = s.scan_messages()
        pr = next(m for m in msgs if '#2' in m['Subject'])
        self.assertEqual((pr['Status'], pr['TaskId']), ('feed', None))   # PRs: shown, never triaged
        self.assertIn('FIRST_TIME_CONTRIBUTOR', pr['BodyText'])          # who is asking rides along
        issue = next(m for m in msgs if '#1' in m['Subject'])
        self.assertIsNotNone(issue['TaskId'])                            # issues: through triage
        self.assertIn('association: MEMBER', seen['usr'])                # ...and triage READ the author line
        s2 = MemoryStore()
        with mock.patch('taskuary.github.list_items', return_value=self.ITEMS):
            n2 = ingest_github_issues(s2, {'Address': 'org/app', 'ConfigJson': '{"issues": "off", "prs": "off"}'},
                                      'tok', __import__('datetime').datetime.now())
        self.assertEqual((n2, len(s2.scan_messages())), (0, 0))          # off = ignored entirely

    def test_a_repo_picker_alone_makes_github_poll(self):
        """The two-switch trap: 'PRs: tasks' on a repo did nothing while the connector card kept
        its default tool-only role - a Sync that pulled nothing and no error anywhere. An
        explicit picker IS the trigger intent now, and it beats a feed-only role too."""
        from taskuary.store import MemoryStore
        from taskuary import channels
        s = MemoryStore()
        gh = next(x for x in s.list_connectors() if x['Type'] == 'github')
        s.save_connector({'ConnectorId': gh['ConnectorId'], 'Active': 1, 'Secret': 'ghp_x'}, 'o')   # role: tool only
        s.save_source({'Channel': 'github', 'Address': 'org/app', 'ConnectorId': gh['ConnectorId'],
                       'Active': 1, 'ConfigJson': '{"prs": "tasks"}'}, 'o')
        items = [{'number': 5, 'title': 'Fix the export', 'body': 'diff attached', 'html_url': 'https://x/5',
                  'updated_at': '2026-08-20T10:00:00Z', 'user': {'login': 'kai'},
                  'author_association': 'CONTRIBUTOR', 'pull_request': {'url': 'https://x/pr/5'}}]
        with mock.patch('taskuary.github.list_items', return_value=items):
            self.assertEqual(channels.poll_channels(s), 1)                   # the picker alone polls it
        self.assertIn('org/app#5', s.feed()[0]['Subject'])
        # ...and an explicit 'tasks' wins over a feed-only role (feed would have filed it silently)
        s2 = MemoryStore()
        gh2 = next(x for x in s2.list_connectors() if x['Type'] == 'github')
        s2.save_connector({'ConnectorId': gh2['ConnectorId'], 'Active': 1, 'Secret': 'ghp_x', 'Roles': 'feed,tool'}, 'o')
        s2.save_source({'Channel': 'github', 'Address': 'org/app', 'ConnectorId': gh2['ConnectorId'],
                        'Active': 1, 'ConfigJson': '{"issues": "tasks"}'}, 'o')
        issue = [{'number': 6, 'title': 'Importer dies', 'body': 'trace', 'html_url': 'https://x/6',
                  'updated_at': '2026-08-20T10:00:00Z', 'user': {'login': 'kai'}, 'author_association': 'MEMBER'}]
        with mock.patch('taskuary.github.list_items', return_value=issue):
            channels.poll_channels(s2)
        self.assertNotEqual(s2.feed()[0]['MsgStatus'], 'feed')               # triaged, not just shown

    def test_github_items_never_auto_dispatch(self):
        """An open repo must not start a coding agent per drive-by item: github messages carry
        no_auto, so they queue as needs-you while ordinary mail still self-dispatches."""
        from taskuary.store import MemoryStore
        from taskuary.ingest import ingest_message
        s = MemoryStore()
        s.set_setting('coder_auto_enabled', '1', 't')
        spawned = []
        task_llm = lambda *a, **k: '{"intent": "task", "why": "work"}'
        with mock.patch('taskuary.ingest._spawn', side_effect=lambda fn, *a: spawned.append(fn.__name__)):
            ingest_message(s, {'external_id': 'gh1', 'channel': 'github', 'subject': 'org/app#9 docs 404',
                               'body': '[issue by x - association: NONE]\nthe docs page 404s for new users',
                               'from_email': 'x@users.noreply.github.com', 'no_auto': True}, llm=task_llm)
            ingest_message(s, {'external_id': 'm1', 'channel': 'email', 'subject': 'payroll import',
                               'body': 'please rerun the payroll import for August', 'from_email': 'boss@work.example'},
                           llm=task_llm)
        self.assertEqual(spawned, ['_auto_code'])                        # the mail dispatched; github queued


class ApiTests(unittest.TestCase):
    def test_index_serves_ui(self):
        r = c.get('/')
        self.assertEqual(r.status_code, 200); self.assertIn('Taskuary', r.text); self.assertIn('assets/index-', r.text)
        js = r.text.split('assets/')[1].split('"')[0]
        self.assertEqual(c.get(f'/assets/{js}').status_code, 200)

    def test_task_crud_and_board(self):
        tid = c.post('/api/tasks', json={'Title': 'do the thing'}).json()['taskId']
        self.assertTrue(any(t['TaskId'] == tid for t in c.get('/api/tasks').json()['data']))
        c.patch(f'/api/tasks/{tid}', json={'Status': 'done'})
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Status'], 'done')

    def test_decide_accepts_explicit_null_final_text(self):
        # the UI sends {"verb": "reject", "final_text": null} - pydantic v2 422'd on the
        # explicit null (str = None is not Optional), which blanked the Review screen
        tid = c.post('/api/tasks', json={'Title': 'a drafted thing'}).json()['taskId']
        server.store.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'r'})
        rid = next(r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']
                   if r['TaskId'] == tid)
        r = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'reject', 'final_text': None})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(any(x['ReviewId'] == rid for x in c.get('/api/reviews', params={'status': 'pending'}).json()['data']))
        # explicit nulls must be accepted across the board (create-task dialog sends them)
        self.assertEqual(c.post('/api/tasks', json={'Title': 't2', 'Summary': None, 'Tags': None}).status_code, 200)

    def test_split_suggest_asks_the_brain_and_split_makes_the_second_task(self):
        tid = c.post('/api/tasks', json={'Title': 'PTO import failing',
                                         'Summary': 'Please fix the mapping. Also add the 112 active employees.'}).json()['taskId']
        with mock.patch.object(server, '_llm', lambda: (lambda sysmsg, user, mt=None:
                '{"two": true, "why": "two asks", "first": {"title": "Fix the mapping", "summary": "x"},'
                ' "second": {"title": "Add the 112 active employees", "summary": "y"}}')):
            sug = c.get(f'/api/tasks/{tid}/split/suggest').json()
        self.assertEqual((sug['ai'], sug['two'], sug['second']['title']), (True, True, 'Add the 112 active employees'))
        # with no AI connector it still answers - the owner types the second job themselves
        self.assertFalse(c.get(f'/api/tasks/{tid}/split/suggest').json()['ai'])
        r = c.post(f'/api/tasks/{tid}/split', json={'first': sug['first'], 'second': sug['second']})
        new = r.json()['taskId']
        self.assertEqual(c.get(f'/api/tasks/{new}').json()['task']['Title'], 'Add the 112 active employees')
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Title'], 'Fix the mapping')
        self.assertEqual(c.post(f'/api/tasks/{tid}/split', json={'second': {'title': ''}}).status_code, 422)
        self.assertEqual(c.get('/api/tasks/999999/split/suggest').status_code, 404)

    def test_merge_folds_one_task_into_the_other_and_refuses_nonsense(self):
        keep = c.post('/api/tasks', json={'Title': 'Roster work', 'Summary': 'add the employees'}).json()['taskId']
        dupe = c.post('/api/tasks', json={'Title': 'Add the employees to the roster'}).json()['taskId']
        cands = c.get(f'/api/tasks/{dupe}/merge-candidates').json()['data']
        self.assertIn(keep, [x['task_id'] for x in cands])
        self.assertTrue(all('why' in x and 'ref' in x for x in cands))
        out = c.post(f'/api/tasks/{dupe}/merge', json={'into': keep}).json()
        self.assertEqual(out['task_id'], keep)
        self.assertEqual(c.get(f'/api/tasks/{dupe}').json()['task']['Status'], 'dropped')
        self.assertEqual(c.post(f'/api/tasks/{keep}/merge', json={'into': keep}).status_code, 422)
        self.assertEqual(c.post(f'/api/tasks/{keep}/merge', json={'into': 999999}).status_code, 404)

    def test_attachments_are_kept_served_and_counted(self):
        """"See below" mail is a screenshot with a sentence on top - a text-only funnel threw the
        actual ask away. The bytes go to disk, the panel draws the images, the row shows a clip."""
        import base64
        from taskuary import channels
        mid = server.store.add_message({'ExternalId': 'graph:ATT1', 'Channel': 'email', 'Subject': 'Payroll File Imports',
                                        'FromEmail': 'dreyes@northwind.example', 'SentAt': '2026-08-19 15:03',
                                        'BodyText': 'We need to fix this error. See below.', 'Status': 'filed'})
        png = base64.b64encode(bytes.fromhex('89504e470d0a1a0a')).decode()
        channels.save_attachments(server.store, mid, [
            {'id': 'a1', 'name': 'payroll.png', 'contentType': 'image/png', 'size': 8, 'isInline': True, 'contentBytes': png},
            {'id': 'a2', 'name': 'ledger.xlsx', 'size': 4096,
             'contentType': 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', 'contentBytes': png},
            {'id': 'a3', 'name': 'forwarded mail', 'size': 900},          # itemAttachment: no bytes to keep
        ], 'graph:ATT1')
        rows = c.get(f'/api/messages/{mid}/attachments').json()['data']
        self.assertEqual([r['name'] for r in rows], ['payroll.png', 'ledger.xlsx', 'forwarded mail'])
        self.assertEqual([r['is_image'] for r in rows], [True, False, False])
        self.assertIsNone(rows[2]['url'])                                  # nothing saved, so nothing to serve
        img = c.get(rows[0]['url'])
        self.assertEqual((img.status_code, img.headers['content-type']), (200, 'image/png'))
        self.assertIn('inline', img.headers.get('content-disposition', ''))
        self.assertIn('attachment', c.get(rows[1]['url']).headers.get('content-disposition', ''))
        self.assertEqual(c.get(f'/api/attachments/{rows[2]["id"]}').status_code, 404)
        # re-running the same Graph payload never duplicates them, and the feed row carries the count
        self.assertEqual(channels.save_attachments(server.store, mid, [{'id': 'a1', 'name': 'payroll.png'}], 'graph:ATT1'), 0)
        row = next(r for r in c.get('/api/feed').json()['data'] if r['MessageId'] == mid)
        self.assertEqual(row['Attachments'], 3)
        self.assertEqual(c.post(f'/api/messages/{mid}/attachments/fetch', json={}).status_code, 422)  # no Outlook connection
        self.assertEqual(c.get('/api/messages/999999/attachments').status_code, 404)

    def test_settings_roundtrip(self):
        self.assertEqual(c.patch('/api/settings', json={'name': 'feed_days', 'value': '7'}).json(), {'ok': True})
        vals = {s['Name']: s['Value'] for s in c.get('/api/settings').json()['data']}
        self.assertEqual(vals['feed_days'], '7')

    def test_agents_ui_flow_persists_to_config(self):
        prof = {'cmd': 'claude', 'args': ['-p'], 'resume_args': ['--resume'], 'timeout': 900,
                'cwd_map': {'o/r': 'C:/src/r'}}
        self.assertEqual(c.put('/api/agents/uitest', json=prof).json(), {'ok': True})
        self.assertEqual(c.get('/api/agents').json()['config']['uitest'], prof)
        self.assertTrue(any(a['Name'] == 'uitest' for a in c.get('/api/agents').json()['data']))
        self.assertEqual(config.load()['agents']['uitest'], prof)  # written to config.toml
        self.assertEqual(c.put('/api/agents/bad', json={'args': []}).status_code, 422)
        self.assertEqual(c.delete('/api/agents/uitest').json(), {'ok': True})
        self.assertNotIn('uitest', config.load().get('agents', {}))
        self.assertEqual(c.delete('/api/agents/uitest').status_code, 404)

    def test_sources_crud_run_and_delete(self):
        REGISTRY['_t'] = lambda cfg: ('2 rows', 'x\ny')
        try:
            cfg = {'type': '_t', 'title': 'T', 'every_minutes': 30}
            sid = c.post('/api/sources', json={'Channel': 'report', 'Address': 'T',
                                               'ConfigJson': json.dumps(cfg), 'Active': True}).json()['sourceId']
            out = c.post(f'/api/sources/{sid}/run', json={}).json()
            self.assertIn('2 rows', out['subject'])
            self.assertEqual(c.delete(f'/api/sources/{sid}').json(), {'ok': True})
            self.assertEqual(c.delete(f'/api/sources/{sid}').status_code, 404)
        finally:
            REGISTRY.pop('_t')

    def test_tool_run_needs_the_tool_role(self):
        """An agent using a connected system: allowed for tool-role connections, refused
        otherwise, and errors come back as data instead of a 500."""
        REGISTRY['_tool'] = lambda cfg: (f"ran {cfg.get('q')}", 'rows here')
        try:
            r = c.post('/api/tools/run', json={'type': '_tool', 'q': 'select 1'}).json()
            self.assertEqual((r['ok'], r['headline'], r['output']), (True, 'ran select 1', 'rows here'))
            self.assertEqual(c.post('/api/tools/run', json={'type': 'nope'}).status_code, 422)
            cid = next(x['ConnectorId'] for x in c.get('/api/connectors').json()['data'] if x['Type'] == 'winrm')
            c.post('/api/connectors', json={'ConnectorId': cid, 'Roles': 'report'})
            self.assertEqual(c.post('/api/tools/run', json={'type': 'winrm', 'script': 'hostname'}).status_code, 403)
            c.post('/api/connectors', json={'ConnectorId': cid, 'Roles': 'report,tool'})
            REGISTRY['winrm'], real = lambda cfg: (_ for _ in ()).throw(RuntimeError('box unreachable')), REGISTRY['winrm']
            try:
                out = c.post('/api/tools/run', json={'type': 'winrm', 'script': 'hostname'}).json()
                self.assertEqual((out['ok'], 'box unreachable' in out['error']), (False, True))
            finally:
                REGISTRY['winrm'] = real
        finally:
            REGISTRY.pop('_tool')

    def test_preview_ok_and_error(self):
        REGISTRY['_p'] = lambda cfg: ('head', 'sum')
        try:
            r = c.post('/api/reports/preview', json={'type': '_p'}).json()
            self.assertEqual((r['ok'], r['headline'], r['summary']), (True, 'head', 'sum'))
        finally:
            REGISTRY.pop('_p')
        r = c.post('/api/reports/preview', json={'type': 'postgres'}).json()
        self.assertFalse(r['ok']); self.assertIn('roadmap', r['error'])

    def test_report_types(self):
        d = {x['type']: x['status'] for x in c.get('/api/report-types').json()['data']}
        self.assertEqual(d['mssql'], 'builtin'); self.assertEqual(d['mcp'], 'builtin')
        self.assertEqual(d['postgres'], 'planned')

    def test_channel_connectors_seeded_and_secret_writeonly(self):
        rows = {x['Type']: x for x in c.get('/api/connectors').json()['data']}
        self.assertEqual(set(rows) >= {'outlook', 'teams', 'github'}, True)
        self.assertNotIn('Secret', rows['github'])
        cid = rows['outlook']['ConnectorId']
        c.post('/api/connectors', json={'ConnectorId': cid, 'ConfigJson': '{"tenant_id": "t1"}', 'Active': True})
        row = next(x for x in c.get('/api/connectors').json()['data'] if x['ConnectorId'] == cid)
        self.assertEqual((row['Active'], row['ConfigJson']), (1, '{"tenant_id": "t1"}'))
        self.assertEqual(row['HasSecret'], 0)
        c.post('/api/connectors', json={'ConnectorId': cid, 'Secret': 's3cret'})
        row = next(x for x in c.get('/api/connectors').json()['data'] if x['ConnectorId'] == cid)
        self.assertEqual(row['HasSecret'], 1); self.assertNotIn('s3cret', json.dumps(row))
        c.post('/api/connectors', json={'ConnectorId': cid, 'Active': False})

    def test_connector_roles_and_brain_choices(self):
        rows = {x['Type']: x for x in c.get('/api/connectors').json()['data']}
        self.assertEqual(rows['github']['Roles'], 'tool')            # github is a tool, not a trigger, by default
        self.assertEqual(rows['outlook']['Roles'], 'trigger,tool')
        cid = rows['github']['ConnectorId']
        try:
            self.assertTrue(c.post('/api/connectors', json={'ConnectorId': cid, 'Roles': 'trigger,tool'}).json()['ok'])
            row = next(x for x in c.get('/api/connectors').json()['data'] if x['ConnectorId'] == cid)
            self.assertEqual(row['Roles'], 'trigger,tool')
            self.assertEqual(c.post('/api/connectors', json={'ConnectorId': cid, 'Roles': 'trigger,wat'}).status_code, 422)
        finally:
            c.post('/api/connectors', json={'ConnectorId': cid, 'Roles': 'tool'})
        b = c.get('/api/brains').json()
        self.assertEqual(b['data'][0]['value'], '')                  # auto first
        self.assertIn('connector:anthropic', [x['value'] for x in b['data']])
        self.assertIn('cli:coder', [x['value'] for x in b['data']])  # your coding CLI can be the brain
        self.assertFalse(next(x for x in b['data'] if x['value'] == 'connector:anthropic')['ready'])   # no key saved

    def test_connector_test_fails_cleanly_without_creds(self):
        cid = next(x['ConnectorId'] for x in c.get('/api/connectors').json()['data'] if x['Type'] == 'teams')
        r = c.post(f'/api/connectors/{cid}/test').json()
        self.assertFalse(r['ok']); self.assertIn('tenant_id', r['detail'])
        self.assertEqual(c.post('/api/connectors/999999/test').status_code, 404)

    def test_github_discovery_on_pat_save(self):
        from unittest import mock
        cid = next(x['ConnectorId'] for x in c.get('/api/connectors').json()['data'] if x['Type'] == 'github')
        with mock.patch('taskuary.channels.github_discover', return_value={'login': 'u', 'repos': 2, 'added': 2}):
            r = c.post('/api/connectors', json={'ConnectorId': cid, 'Secret': 'ghp_x'}).json()
        self.assertEqual(r['discovery'], {'login': 'u', 'repos': 2, 'added': 2})

    def test_mssql_endpoints(self):
        with mock.patch('taskuary.mssql.drivers', return_value=['ODBC Driver 18 for SQL Server']):
            self.assertEqual(c.get('/api/mssql/drivers').json()['data'], ['ODBC Driver 18 for SQL Server'])
        with mock.patch('taskuary.mssql.test', return_value={'ok': True, 'version': 'v', 'database': 'd'}):
            self.assertTrue(c.post('/api/mssql/test', json={'server': 'localhost'}).json()['ok'])

    def test_policies_crud(self):
        r = c.post('/api/policies', json={'Name': 'quiet fyi', 'Kind': 'keyword', 'Pattern': 'newsletter',
                                          'Action': 'ignore', 'Reason': 'noise', 'SortOrder': 10}).json()
        self.assertTrue(r['ok'])
        rows = c.get('/api/policies').json()['data']
        me = next(p for p in rows if p['PolicyId'] == r['policyId'])
        self.assertEqual((me['Action'], me['Active']), ('ignore', 1))
        c.post('/api/policies', json={'PolicyId': r['policyId'], 'Active': False})
        me = next(p for p in c.get('/api/policies').json()['data'] if p['PolicyId'] == r['policyId'])
        self.assertEqual(me['Active'], 0)
        self.assertEqual(c.post('/api/policies', json={'Name': 'incomplete'}).status_code, 422)

    def test_skip_policy_applies_to_history_through_the_api(self):
        for i in range(2):
            c.post('/api/ingest/push', json={'external_id': f'flood{i}', 'subject': 'Provisioning notice',
                                             'body': 'automated, no action required', 'from_email': 'flood@vendor.com',
                                             'channel': 'email'})
        seen = lambda: [m for m in c.get('/api/feed').json()['data'] if m['FromEmail'] == 'flood@vendor.com']
        self.assertEqual(len(seen()), 2)
        r = c.post('/api/policies', json={'Name': 'skip:flood@vendor.com', 'Kind': 'sender', 'Pattern': 'flood@vendor.com',
                                          'Action': 'skip', 'Reason': 'flood sender', 'SortOrder': 10, 'Active': True}).json()
        self.assertEqual(r['affected'], 2)                       # the back catalogue leaves the timeline too
        self.assertEqual(seen(), [])
        back = c.post('/api/policies', json={'PolicyId': r['policyId'], 'Active': False}).json()
        self.assertEqual((back['affected'], len(seen())), (2, 2))   # switching it off restores them

    def test_memory_add_and_toggle(self):
        r = c.post('/api/memory', json={'note': 'Never draft replies to cash reports', 'scope': 'global'}).json()
        self.assertTrue(r['ok'])
        c.patch(f"/api/memory/{r['memoryId']}", json={'active': False})
        row = next(m for m in c.get('/api/memory').json()['data'] if m['MemoryId'] == r['memoryId'])
        self.assertEqual(row['Active'], 0)
        self.assertEqual(c.post('/api/memory', json={'note': ' ', 'scope': 'global'}).status_code, 422)
        self.assertEqual(c.post('/api/memory', json={'note': 'x', 'scope': 'weird'}).status_code, 422)

    def test_not_a_task_learns_and_deletes(self):
        with mock.patch('taskuary.server._llm', return_value=lambda s_, u_: '{"intent": "task", "why": "x"}'):
            out = c.post('/api/ingest/push', json={'subject': 'please fix the export', 'body': 'please fix the export job',
                                                   'from_email': 'noise@vendor.com', 'channel': 'api'}).json()
        tid = out['task_id']
        r = c.post(f'/api/tasks/{tid}/not-a-task').json()
        self.assertEqual(r['learned']['policy'], 'noise@vendor.com')
        self.assertEqual(c.get(f'/api/tasks/{tid}').status_code, 404)
        self.assertTrue(any(p['Pattern'] == 'noise@vendor.com' and p['Action'] == 'ignore'
                            for p in c.get('/api/policies').json()['data']))

    def test_push_without_ai_files(self):
        out = c.post('/api/ingest/push', json={'subject': 'automated provisioning notice 77', 'body': 'please add the new user',
                                               'from_email': 'apinotify@vendor.com', 'channel': 'api'}).json()
        self.assertEqual((out['status'], out['task_id']), ('filed', None))

    def test_dispatch_validates(self):
        tid = c.post('/api/tasks', json={'Title': 'd'}).json()['taskId']
        self.assertEqual(c.post(f'/api/tasks/{tid}/dispatch', json={'agent': 'ghost'}).status_code, 422)
        self.assertEqual(c.post('/api/tasks/999999/dispatch', json={'agent': 'coder'}).status_code, 404)

    def test_message_dispatch_promotes_and_runs(self):
        """'Send to coding agent' from the timeline: a filed message (report/ignored mail)
        becomes a task carrying the message, then the agent runs on it."""
        out = c.post('/api/ingest/push', json={'subject': 'Process Check - FAILED', 'body': 'Pex export failed: LedgerBalance',
                                               'from_email': 'reports@vendor.com', 'channel': 'report'}).json()
        mid = out['message_id']
        self.assertIsNone(out['task_id'])
        self.assertEqual(c.get(f'/api/messages/{mid}').json()['Subject'], 'Process Check - FAILED')
        server.store.upsert_agent('coder', 'coding', 'cli', '{"cmd": "claude"}')
        # sending it to an agent opens a REAL session on the task - there is no pipe behind
        # any button, so the owner can always read, interrupt and answer what it is doing
        with mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's1'}) as d:
            r = c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'coder', 'instruction': 'find why it failed'}).json()
        tid = r['taskId']
        self.assertEqual((r['ref'], r['dispatch']), (f'TQ-{tid:04d}', 'session'))
        self.assertEqual(d.call_args[0][1:5], (tid, 'coder', None, 'find why it failed'))   # your prompt is typed in
        self.assertEqual([m['MessageId'] for m in server.store.list_messages(tid)], [mid])
        # a second send reuses the task it already made instead of forking a new one
        with mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's1', 'existing': True}):
            self.assertEqual(c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'coder'}).json()['taskId'], tid)
        self.assertEqual(c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'ghost'}).status_code, 422)
        self.assertEqual(c.post('/api/messages/999999/dispatch', json={'agent': 'coder'}).status_code, 404)
        self.assertEqual(c.get('/api/messages/999999').status_code, 404)

    def test_not_mine_writes_memory_and_triage_reads_it(self):
        """'Not our task' has to TEACH, not just hide: the note lands in memory and the next
        message from that sender is classified with it in hand."""
        push = lambda i: c.post('/api/ingest/push', json={
            'external_id': f'notmine{i}', 'subject': 'Resident refund request - Register, Glenda S',
            'body': 'Attached is the check. Cash correction needs to be done.',
            'from_email': 'michelle.soto@example.org', 'channel': 'email'}).json()
        first = push(1)
        mid = first['message_id']
        suggested = c.get(f'/api/messages/{mid}/not-mine/suggest').json()['note']
        self.assertIn('michelle.soto@example.org', suggested)
        out = c.post(f'/api/messages/{mid}/not-mine', json={'note': None, 'scope': 'sender'}).json()
        self.assertEqual((out['ok'], out['scope'], out['scopeKey']), (True, 'sender', 'michelle.soto@example.org'))
        self.assertEqual(suggested, out['note'])                     # the suggestion is what gets saved
        row = next(m for m in c.get('/api/feed').json()['data'] if m['MessageId'] == mid)
        self.assertEqual(row['MsgStatus'], 'ignored')
        self.assertIn('not ours', row['RouteReason'])
        # the note now rides into every later triage call for that sender
        from taskuary.ingest import notes_for
        notes = notes_for(server.store, {'from_email': 'MICHELLE.SOTO@example.org'})
        self.assertTrue(any('other people' in n for n in notes))
        seen = {}
        with mock.patch('taskuary.server._llm',
                        return_value=lambda sys_, usr_, **kw: seen.update(sys=sys_) or '{"intent": "fyi", "why": "not ours"}'):
            second = push(2)
        self.assertEqual((second['status'], second['task_id']), ('filed', None))
        self.assertIn('VERDICTS they already gave', seen['sys'])
        self.assertIn('other people', seen['sys'])
        self.assertEqual(c.post('/api/messages/999999/not-mine', json={}).status_code, 404)
        self.assertEqual(c.post(f'/api/messages/{mid}/not-mine', json={'scope': 'weird'}).status_code, 422)

    def test_editing_a_draft_teaches_learned_md(self):
        """The README's promise, made true: your edit to a draft leaves a lesson behind - a
        hypothesis in LEARNED.md, written by the triage brain the moment you decide."""
        tid = c.post('/api/tasks', json={'Title': 'a question'}).json()['taskId']
        server.store.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'r',
                                 'DraftText': 'Dear sir, I will most certainly look into it.'})
        rid = next(r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']
                   if r['TaskId'] == tid)
        bullet = f'- {{{{owner_first}}}} drops formal openers. [s:2 | ev: rv{rid} | seen: 2026-08-21]'
        seen = {}
        fake = lambda sys_, usr, **kw: seen.update(usr=usr) or bullet
        with mock.patch('taskuary.llm.build_llm', return_value=fake):
            r = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': 'On it.'})
        self.assertEqual(r.json()['status'], 'edited')            # the diff, not the verb, says edited
        self.assertIn('DRAFT:', seen['usr']); self.assertIn('On it.', seen['usr'])   # the edit IS the lesson
        self.assertIn(bullet, server.store.get_doc('learned'))
        # and a plain approve teaches nothing hot-path: it is aggregate confirmation, counted at reflection
        server.store.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'r', 'DraftText': 'ok'})
        rid2 = next(r2['ReviewId'] for r2 in c.get('/api/reviews', params={'status': 'pending'}).json()['data']
                    if r2['TaskId'] == tid)
        before = server.store.get_doc('learned')
        with mock.patch('taskuary.llm.build_llm', return_value=fake):
            c.post(f'/api/reviews/{rid2}/decide', json={'verb': 'approve', 'final_text': None})
        self.assertEqual(server.store.get_doc('learned'), before)

    def test_ingest_status_heals_ghost_running(self):
        # a poll that died with the app used to leave 'running' behind forever - the timeline
        # banner showed "catching up" until someone edited the database
        server.store.set_setting('ingest_status', json.dumps(
            {'state': 'running', 'what': 'catching up on the last 3 days', 'at': '2020-01-01 00:00:00'}), 't')
        self.assertEqual(c.get('/api/ingest/status').json()['status']['state'], 'idle')
        # while a poll REALLY runs (the lock is held), running is reported faithfully
        server._POLL_BUSY.acquire()
        try:
            server.store.set_setting('ingest_status', json.dumps({'state': 'running', 'what': 'x'}), 't')
            self.assertEqual(c.get('/api/ingest/status').json()['status']['state'], 'running')
        finally:
            server._POLL_BUSY.release()
        self.assertEqual(c.get('/api/ingest/status').json()['status']['state'], 'idle')

    def test_second_poll_skips_while_one_runs_however_long(self):
        """The Image-#1 loop as a regression: a catch-up slower than the old 10-minute guard let
        the auto-sync start second polls forever. Now overlap is impossible for the process's
        lifetime, and the state still lands on idle."""
        import threading
        started, release, calls = threading.Event(), threading.Event(), []
        def slow_reports(s): calls.append(1); started.set(); release.wait(10)
        with mock.patch.object(server, 'run_due_reports', slow_reports), \
             mock.patch('taskuary.channels.poll_channels', lambda s, d: None):
            t = threading.Thread(target=server._poll_reports, kwargs={'what': 'catching up'}, daemon=True)
            t.start()
            self.assertTrue(started.wait(10))
            self.assertEqual(c.get('/api/ingest/status').json()['status']['state'], 'running')
            server._poll_reports(what='auto-sync')              # the 10-min timer firing mid-catch-up
            self.assertEqual(calls, [1])                        # skipped, not raced
            self.assertEqual(json.loads(server.store.get_settings()['ingest_status'])['what'],
                             'catching up')                     # and it did not rewrite the banner
            release.set(); t.join(10)
        self.assertEqual(c.get('/api/ingest/status').json()['status']['state'], 'idle')

    def test_startup_catchup_asks_for_the_gap_not_the_ceiling(self):
        """Reopening an app closed ten minutes should not re-read three days of every mailbox -
        the catch-up window is the actual time closed, with startup_sync_days as the ceiling."""
        from datetime import datetime, timedelta
        src = server.store.save_source({'Channel': 'email', 'Address': 'gap@test.example', 'Active': 1}, 't')
        stamp = lambda h: (datetime.now() - timedelta(hours=h)).isoformat(sep=' ', timespec='seconds')
        try:
            server.store._exec('UPDATE source SET LastPolledAt=NULL', ())     # only this source speaks
            server.store._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?', (stamp(0.2), src))
            self.assertEqual(server._catchup_days(3), 0)      # closed ten minutes: plain incremental
            server.store._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?', (stamp(30), src))
            self.assertEqual(server._catchup_days(3), 2)      # overnight and change: two days
            server.store._exec('UPDATE source SET LastPolledAt=? WHERE SourceId=?', (stamp(24 * 10), src))
            self.assertEqual(server._catchup_days(3), 3)      # a long holiday still caps at the setting
            server.store._exec('UPDATE source SET LastPolledAt=NULL', ())
            self.assertEqual(server._catchup_days(3), 3)      # never polled: the full ceiling
        finally:
            server.store.delete_source(src)

    def test_learn_reflect_endpoint_and_gather(self):
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(c.post('/api/learn/reflect').json(), {'ok': True, 'reflected': False})
        good = server.store.get_doc('learned')
        with mock.patch('taskuary.llm.build_llm', return_value=lambda sys_, usr, **kw: good):
            self.assertTrue(c.post('/api/learn/reflect').json()['reflected'])
        from taskuary.learn import gather
        self.assertIn('DRAFT VERDICTS', gather(server.store, '2000-01-01'))

    def test_a_failed_send_returns_the_review_to_the_queue(self):
        """The Image-#5 bug: a Teams send died on permissions but the card read 'approved' and
        the task closed - an answer that never left the machine, dressed as finished. Now the
        review comes back pending wearing the error, and approving again retries the send."""
        push = c.post('/api/ingest/push', json={'external_id': 'sendfail1', 'subject': 'security app help',
                                                'body': 'can you check her accounts?', 'from_email': 'hr@work.example',
                                                'channel': 'teams'}).json()
        mid = push['message_id']
        tid = c.post(f'/api/messages/{mid}/reply').json()['taskId']
        rid = next(r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']
                   if r['MessageId'] == mid)
        with mock.patch.object(server.outbound, 'reply_to_message',
                               side_effect=RuntimeError('Teams: 403 - the app has no ChatMessage.Send permission')):
            out = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': 'All provisioned.'}).json()
        self.assertEqual(out['status'], 'pending')
        self.assertIn('no ChatMessage.Send', out['send_error'])
        rv = server.store.get_review(rid)
        self.assertEqual(rv['Status'], 'pending')                        # back in the queue...
        self.assertIn('sending FAILED', rv['Reason'])                    # ...wearing the error
        self.assertEqual(rv['DraftText'], 'All provisioned.')            # approve again = retry as-is
        self.assertNotEqual((server.store.get_task(tid) or {}).get('Status'), 'done')   # nothing finished
        # the channel fixed, the retry sends and closes for real
        with mock.patch.object(server.outbound, 'reply_to_message',
                               return_value={'channel': 'teams', 'to': ['hr@work.example']}):
            out2 = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': None}).json()
        self.assertEqual((out2['status'], out2['send_error']), ('approved', None))
        self.assertEqual(server.store.get_review(rid)['Status'], 'approved')

    def test_done_and_doc_save_persist(self):
        # Save on a doc is a real write-read roundtrip
        was = c.get('/api/doc/coder').json()['content']
        try:
            c.put('/api/doc/coder', json={'content': '# my coder rules v2'})
            self.assertEqual(c.get('/api/doc/coder').json()['content'], '# my coder rules v2')
        finally:
            c.put('/api/doc/coder', json={'content': was})
        # Done on a task persists AND resolves its pending reviews with it
        tid = c.post('/api/tasks', json={'Title': 'wrap me'}).json()['taskId']
        server.store.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'Reason': 'r'})
        c.patch(f'/api/tasks/{tid}', json={'Status': 'done'})
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Status'], 'done')
        self.assertFalse(any(r['TaskId'] == tid for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']))

    def test_live_runs_tail(self):
        tid = c.post('/api/tasks', json={'Title': 'live'}).json()['taskId']
        rid = server.store.start_run(tid, 'coder', 'work it', 'owner')
        server.store.update_run(rid, {'TraceJson': json.dumps(
            [{'kind': 'prompt', 'detail': 'ignored'}] + [{'kind': 'live', 'detail': f'line {i}'} for i in range(5)])})
        row = next(r for r in c.get('/api/runs/live').json()['data'] if r['RunId'] == rid)
        self.assertEqual(row['tail'], ['line 2', 'line 3', 'line 4'])      # newest 3, prompts excluded
        server.store.update_run(rid, {'Status': 'done'}, finished=True)
        self.assertFalse(any(r['RunId'] == rid for r in c.get('/api/runs/live').json()['data']))

    def test_code_endpoint_opens_a_real_session_never_a_headless_run(self):
        """Nothing starts where it cannot be watched. /code was the last headless door: it now
        opens the same live session as every other way of putting a CLI on a task."""
        tid = c.post('/api/tasks', json={'Title': 'pick my CLI'}).json()['taskId']
        server.store.upsert_agent('codex', 'coding', 'cli', '{"cmd": "codex"}')
        with mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 'x'}) as start:
            out = c.post(f'/api/tasks/{tid}/code', json={'agent': 'codex', 'model': 'gpt-5-codex',
                                                         'instruction': 'just the importer'}).json()
        self.assertEqual((out['coder'], out['agent'], out['model']), ('session', 'codex', 'gpt-5-codex'))
        self.assertEqual(start.call_args[0][1:], (tid, 'codex', 'gpt-5-codex', 'just the importer', server.ACTOR))
        self.assertEqual(c.post(f'/api/tasks/{tid}/code', json={'agent': 'ghost'}).status_code, 422)

    def test_approving_a_draft_actually_answers_the_sender(self):
        """Approving used to file a verdict and stop - the person who wrote in never heard
        back. Approve IS send, in the original thread, and a failure says so on the task."""
        tid = c.post('/api/tasks', json={'Title': 'reply to Mindy', 'Kind': 'reply'}).json()['taskId']
        mid = server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:AAA', 'Channel': 'email',
                                        'SourceName': 'me@corp.com', 'Subject': 'PTO', 'FromEmail': 'mindy@corp.com',
                                        'BodyText': 'am I covered monday?', 'Status': 'routed'})
        rid = server.store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                       'DraftText': 'Yes - covered, enjoy Monday.'})
        with mock.patch.object(server.outbound, 'send_email', return_value={'channel': 'email', 'to': ['mindy@corp.com'],
                                                                           'threaded': True}) as send:
            out = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve'}).json()
        self.assertEqual((out['sent']['channel'], out['sent']['threaded']), ('email', True))
        self.assertEqual(send.call_args[0][1], ['mindy@corp.com'])            # to
        self.assertEqual(send.call_args[0][3], 'Yes - covered, enjoy Monday.')  # body
        self.assertEqual(send.call_args[0][4], 'AAA')                          # threaded on the Graph id
        # and when Graph refuses, the approved text is still on the task, marked NOT SENT
        rid2 = server.store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending',
                                        'DraftText': 'second try'})
        with mock.patch.object(server.outbound, 'send_email', side_effect=RuntimeError('mailbox not found')):
            out = c.post(f'/api/reviews/{rid2}/decide', json={'verb': 'approve'}).json()
        self.assertIn('mailbox not found', out['send_error'])
        self.assertTrue(any('NOT SENT' in cm['Body'] for cm in server.store.list_comments(tid)))

    def test_sending_the_coders_reply_closes_the_task_it_was_waiting_on(self):
        """A coding task the coder finished waits on one thing: you sending the answer. The
        send is the last step, so it closes the task - it must not sit in 'waiting' forever."""
        tid = c.post('/api/tasks', json={'Title': 'importer down', 'Kind': 'coding'}).json()['taskId']
        server.store.update_task(tid, {'Status': 'waiting'}, 'coder')
        mid = server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:BBB', 'Channel': 'email',
                                        'SourceName': 'me@corp.com', 'FromEmail': 'ap@client.com',
                                        'BodyText': 'nothing imported', 'Status': 'routed'})
        rid = server.store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending',
                                       'DraftText': 'Running again - a bad date had stopped it.'})
        with mock.patch.object(server.outbound, 'send_email', return_value={'channel': 'email', 'to': ['ap@client.com']}):
            c.post(f'/api/reviews/{rid}/decide', json={'verb': 'approve'})
        self.assertEqual(server.store.get_task(tid)['Status'], 'done')

    def test_mine_makes_a_task_for_the_owner_with_nobody_dispatched(self):
        """An ADP "approve this workflow" mail is real work and not an agent's. Filing it as
        nothing-to-do was the only option; now it becomes a task with your name on it, which
        the feed reads as needs-you, and no agent gets sent at it."""
        mid = server.store.add_message({'ExternalId': 'adp:1', 'Channel': 'email', 'SourceName': 'me@corp.com',
                                        'Subject': 'Action Needed: Pending Workflow Approval', 'FromEmail': 'noreply@adp.com',
                                        'SentAt': '2026-08-19 08:25', 'BodyText': 'Mindy Gorelick needs your approval.',
                                        'Status': 'ignored'})
        out = c.post(f'/api/messages/{mid}/mine', json={}).json()
        t = server.store.get_task(out['taskId'])
        self.assertEqual((t['Kind'], t['Status'], t['Assignee']), ('general', 'open', server.ACTOR))
        self.assertEqual(server.store.get_message(mid)['TaskId'], out['taskId'])   # off the filed pile
        self.assertEqual(server.store.list_runs(out['taskId']), [])                # nobody dispatched
        row = next(r for r in server.store.feed() if r['MessageId'] == mid)
        self.assertEqual((row['NeedsYou'], row['TaskId']), (1, out['taskId']))
        # clicking it twice must not spawn a second task
        self.assertEqual(c.post(f'/api/messages/{mid}/mine', json={}).json()['taskId'], out['taskId'])

    def test_handoff_drafts_then_sends(self):
        tid = c.post('/api/tasks', json={'Title': 'AD account for Christina'}).json()['taskId']
        with mock.patch.object(server.outbound, 'draft_handoff', return_value='Ross - this one is yours: …') as d:
            out = c.post(f'/api/tasks/{tid}/handoff', json={'to': 'ross@corp.com', 'draft_only': True}).json()
        self.assertEqual(out['draft'], 'Ross - this one is yours: …')
        self.assertEqual(d.call_args[0][2], 'ross@corp.com')
        with mock.patch.object(server.outbound, 'send_email', return_value={'channel': 'email', 'to': ['ross@corp.com']}):
            out = c.post(f'/api/tasks/{tid}/handoff', json={'to': 'ross@corp.com', 'text': 'take this please'}).json()
        self.assertEqual(out['sent']['to'], ['ross@corp.com'])
        self.assertTrue(any('Handed off to ross@corp.com' in cm['Body'] for cm in server.store.list_comments(tid)))
        # a chat hand-off needs a chat: this task never came from one
        self.assertEqual(c.post(f'/api/tasks/{tid}/handoff',
                                json={'to': 'ross', 'channel': 'teams', 'text': 'x'}).status_code, 422)

    def test_a_live_session_is_visible_work(self):
        """A pty session is not a 'run', so the board used to show a task as Queued while its
        CLI sat there asking a question. Sessions now surface next to runs - with the idle
        time that separates 'thinking' from 'waiting on you'."""
        import time as _t
        from taskuary import terminal as term
        tid = c.post('/api/tasks', json={'Title': 'live one'}).json()['taskId']

        class FakeTerm:
            alive, task_id, agent, label = True, tid, 'coder', 'coder'
            sid, cwd, argv = 'sid1', 'C:/repo', ['claude']
            started = '2026-08-18 20:00:00'
            def __init__(self): self.last = _t.time()
            idle = term.Term.idle
            tail = lambda self, n=3: ['Christina needs an AD account created. How do you want it done?']
            info = term.Term.info

        term.SESSIONS['sid1'] = FakeTerm()
        try:
            t = next(x for x in c.get('/api/tasks').json()['data'] if x['TaskId'] == tid)
            self.assertEqual(t['Session']['agent'], 'coder')
            self.assertLess(t['Session']['idle'], 5)                       # just spoke = working
            live = next(r for r in c.get('/api/runs/live').json()['data'] if r['TaskId'] == tid)
            self.assertEqual((live['kind'], live['RunId']), ('session', None))
            self.assertIn('How do you want it done?', live['tail'][0])
            self.assertEqual(c.get(f'/api/tasks/{tid}').json()['session']['sid'], 'sid1')
            term.SESSIONS['sid1'].last -= 120                              # gone quiet: parked at its prompt
            t = next(x for x in c.get('/api/tasks').json()['data'] if x['TaskId'] == tid)
            self.assertGreater(t['Session']['idle'], term.IDLE_WAITING)
        finally:
            term.SESSIONS.pop('sid1', None)

    def test_runs_audit_ingest_status(self):
        self.assertEqual(c.get('/api/runs/999999').status_code, 404)
        self.assertIsInstance(c.get('/api/audit/recent').json()['data'], list)
        self.assertIn(c.get('/api/ingest/status').json()['status']['state'], ('idle', 'running'))
        self.assertEqual(c.post('/api/ingest/poll').json(), {'report': 'running'})
        self.assertNotIn('ingest_status', {s['Name'] for s in c.get('/api/settings').json()['data']})

    def test_token_gate(self):
        server.cfg['server']['token'] = 'secret'
        try:
            self.assertEqual(c.get('/api/settings').status_code, 401)
            self.assertEqual(c.get('/api/settings', headers={'X-Taskuary-Token': 'secret'}).status_code, 200)
        finally:
            server.cfg['server'].pop('token')


    def test_reclassifying_to_reply_routes_the_task_into_review(self):
        """"This is not a coding task" - the mail asked for FILES, not a fix, and triage sent an
        agent at it. Switching the kind to reply is the correction: a draft review appears, the
        way the question would have been handled at triage."""
        tid = c.post('/api/tasks', json={'Title': 'PTO true up', 'Kind': 'coding'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:KIND1', 'Channel': 'email',
                                  'FromEmail': 'gw@corp.com', 'BodyText': 'can you send me the PTO files for July?',
                                  'Status': 'routed'})
        r = c.patch(f'/api/tasks/{tid}', json={'Kind': 'reply'})
        self.assertEqual(r.status_code, 200)
        self.assertEqual(c.get(f'/api/tasks/{tid}').json()['task']['Kind'], 'reply')
        pend = [x for x in c.get('/api/reviews', params={'status': 'pending'}).json()['data'] if x['TaskId'] == tid]
        self.assertEqual(len(pend), 1)
        self.assertIn('a question, not work to do', pend[0]['Reason'])
        # saying it twice must not stack a second review
        c.patch(f'/api/tasks/{tid}', json={'Kind': 'general'})
        c.patch(f'/api/tasks/{tid}', json={'Kind': 'reply'})
        pend = [x for x in c.get('/api/reviews', params={'status': 'pending'}).json()['data'] if x['TaskId'] == tid]
        self.assertEqual(len(pend), 1)
        self.assertEqual(c.patch('/api/tasks/999999', json={'Kind': 'reply'}).status_code, 404)

    def test_a_reply_can_be_opened_on_any_message(self):
        """After a coder ran (or triage filed it) there was NO way to answer from the panel -
        nothing pending meant the draft box was unreachable. Opening a reply creates the review
        and drafts it; opening again reuses the same one."""
        tid = c.post('/api/tasks', json={'Title': 'coder finished this', 'Kind': 'coding'}).json()['taskId']
        mid = server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:REPLY1', 'Channel': 'email',
                                        'FromEmail': 'asker@corp.com', 'BodyText': 'is it fixed?', 'Status': 'routed'})
        with mock.patch('taskuary.responder.write_draft', return_value='Fixed - deploys again tonight.') as wd:
            out = c.post(f'/api/messages/{mid}/reply', json={}).json()
        self.assertEqual(out['draft'], 'Fixed - deploys again tonight.')
        self.assertEqual(wd.call_args.args[2], out['reviewId'])
        pend = [r for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data'] if r['TaskId'] == tid]
        self.assertEqual(len(pend), 1)
        again = c.post(f'/api/messages/{mid}/reply', json={'draft': False}).json()
        self.assertEqual(again['reviewId'], out['reviewId'])            # reused, never stacked
        self.assertEqual(c.post('/api/messages/999999/reply', json={}).status_code, 404)

    def test_replying_to_a_filed_message_creates_no_task(self):
        """Answering chatter is a REPLY, not a project - promoting the filed message to a task
        just to hold the review put a TQ badge on 'it was just his demo'. The review rides
        task-less, still lands in the pending queue, and approving still sends."""
        mid = server.store.add_message({'ExternalId': 'graph:FILED1', 'Channel': 'teams',
                                        'FromName': 'J. D. Hancock', 'ConversationId': 'teams:19:x',
                                        'BodyText': 'It was just his demo. Ready to move over.', 'Status': 'filed'})
        tasks_before = len(server.store.list_tasks())
        with mock.patch('taskuary.responder.draft_for_message', return_value='Got it - send it over.'):
            out = c.post(f'/api/messages/{mid}/reply', json={}).json()
        self.assertIsNone(out['taskId'])
        self.assertEqual(len(server.store.list_tasks()), tasks_before)          # no task materialized
        pend = [r for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']
                if r['ReviewId'] == out['reviewId']]
        self.assertEqual(len(pend), 1)                                          # still visible in the queue
        with mock.patch('taskuary.outbound.reply_to_message', return_value={'channel': 'teams', 'to': []}):
            r = c.post(f"/api/reviews/{out['reviewId']}/decide", json={'verb': 'approve', 'final_text': 'Got it.'}).json()
        self.assertTrue(r['sent'])
        self.assertEqual(len(server.store.list_tasks()), tasks_before)          # approving made none either

    def test_not_a_task_without_learning_deletes_and_teaches_nothing(self):
        """Someone answered 'yes' - that is chatter, not a verdict about the sender. The lighter
        not-a-task deletes the task and leaves no policy and no memory behind."""
        tid = c.post('/api/tasks', json={'Title': 'yes'}).json()['taskId']
        server.store.add_message({'TaskId': tid, 'ExternalId': 'graph:CHAT1', 'Channel': 'teams',
                                  'FromEmail': 'mindy@corp.com', 'BodyText': 'yes', 'Status': 'routed'})
        before_p = len(c.get('/api/policies').json()['data'])
        r = c.post(f'/api/tasks/{tid}/not-a-task', json={'learn': False}).json()
        self.assertIsNone(r['learned'])
        self.assertEqual(len(c.get('/api/policies').json()['data']), before_p)
        self.assertNotIn('mindy@corp.com', str(server.store.list_memories()))
        self.assertEqual(c.get(f'/api/tasks/{tid}').status_code, 404)   # the task is gone


if __name__ == '__main__':
    unittest.main()
