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

    def test_memory_add_and_toggle(self):
        r = c.post('/api/memory', json={'note': 'Never draft replies to cash reports', 'scope': 'global'}).json()
        self.assertTrue(r['ok'])
        c.patch(f"/api/memory/{r['memoryId']}", json={'active': False})
        row = next(m for m in c.get('/api/memory').json()['data'] if m['MemoryId'] == r['memoryId'])
        self.assertEqual(row['Active'], 0)
        self.assertEqual(c.post('/api/memory', json={'note': ' ', 'scope': 'global'}).status_code, 422)
        self.assertEqual(c.post('/api/memory', json={'note': 'x', 'scope': 'weird'}).status_code, 422)

    def test_not_a_task_learns_and_deletes(self):
        out = c.post('/api/ingest/push', json={'subject': 'please fix the export', 'body': 'please fix the export job',
                                               'from_email': 'noise@vendor.com', 'channel': 'api'}).json()
        tid = out['task_id']
        r = c.post(f'/api/tasks/{tid}/not-a-task').json()
        self.assertEqual(r['learned']['policy'], 'noise@vendor.com')
        self.assertEqual(c.get(f'/api/tasks/{tid}').status_code, 404)
        self.assertTrue(any(p['Pattern'] == 'noise@vendor.com' and p['Action'] == 'ignore'
                            for p in c.get('/api/policies').json()['data']))

    def test_dispatch_validates(self):
        tid = c.post('/api/tasks', json={'Title': 'd'}).json()['taskId']
        self.assertEqual(c.post(f'/api/tasks/{tid}/dispatch', json={'agent': 'ghost'}).status_code, 422)
        self.assertEqual(c.post('/api/tasks/999999/dispatch', json={'agent': 'coder'}).status_code, 404)

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
