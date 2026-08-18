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
        tid = c.post('/api/tasks', json={'Title': 'escalated thing'}).json()['taskId']
        server.store.add_review({'TaskId': tid, 'Kind': 'escalation', 'Status': 'pending', 'Reason': 'r'})
        rid = next(r['ReviewId'] for r in c.get('/api/reviews', params={'status': 'pending'}).json()['data']
                   if r['TaskId'] == tid)
        r = c.post(f'/api/reviews/{rid}/decide', json={'verb': 'reject', 'final_text': None})
        self.assertEqual(r.status_code, 200)
        self.assertFalse(any(x['ReviewId'] == rid for x in c.get('/api/reviews', params={'status': 'pending'}).json()['data']))
        # explicit nulls must be accepted across the board (create-task dialog sends them)
        self.assertEqual(c.post('/api/tasks', json={'Title': 't2', 'Summary': None, 'Tags': None}).status_code, 200)

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
        with mock.patch.object(server.hub_agents, 'dispatch', return_value={'run_id': 1, 'status': 'done', 'result': 'ok'}) as d:
            r = c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'coder', 'instruction': 'find why it failed'}).json()
        tid = r['taskId']
        self.assertEqual(r['ref'], f'TQ-{tid:04d}')
        self.assertEqual(d.call_args[0][3], 'find why it failed')
        self.assertEqual([m['MessageId'] for m in server.store.list_messages(tid)], [mid])
        # a second send reuses the task it already made instead of forking a new one
        with mock.patch.object(server.hub_agents, 'dispatch', return_value={'run_id': 2, 'status': 'done', 'result': 'ok'}):
            self.assertEqual(c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'coder'}).json()['taskId'], tid)
        self.assertEqual(c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'ghost'}).status_code, 422)
        self.assertEqual(c.post('/api/messages/999999/dispatch', json={'agent': 'coder'}).status_code, 404)
        self.assertEqual(c.get('/api/messages/999999').status_code, 404)

    def test_live_runs_tail(self):
        tid = c.post('/api/tasks', json={'Title': 'live'}).json()['taskId']
        rid = server.store.start_run(tid, 'coder', 'work it', 'owner')
        server.store.update_run(rid, {'TraceJson': json.dumps(
            [{'kind': 'prompt', 'detail': 'ignored'}] + [{'kind': 'live', 'detail': f'line {i}'} for i in range(5)])})
        row = next(r for r in c.get('/api/runs/live').json()['data'] if r['RunId'] == rid)
        self.assertEqual(row['tail'], ['line 2', 'line 3', 'line 4'])      # newest 3, prompts excluded
        server.store.update_run(rid, {'Status': 'done'}, finished=True)
        self.assertFalse(any(r['RunId'] == rid for r in c.get('/api/runs/live').json()['data']))

    def test_code_endpoint_takes_an_agent(self):
        tid = c.post('/api/tasks', json={'Title': 'pick my CLI'}).json()['taskId']
        server.store.upsert_agent('codex', 'coding', 'cli', '{"cmd": "codex"}')
        with mock.patch.object(server, 'run_coding_task') as rct:
            self.assertEqual(c.post(f'/api/tasks/{tid}/code', json={'agent': 'codex'}).json()['agent'], 'codex')
        self.assertEqual(rct.call_args[0][-1], 'codex')
        self.assertEqual(c.post(f'/api/tasks/{tid}/code', json={'agent': 'ghost'}).status_code, 422)

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


if __name__ == '__main__':
    unittest.main()
