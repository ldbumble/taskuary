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
        self.assertEqual(r.status_code, 200); self.assertIn('Taskuary', r.text); self.assertIn('Settings', r.text)

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
        self.assertEqual(c.get('/api/agents').json()['data']['uitest'], prof)
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

    def test_connectors_lists_types(self):
        d = {x['type']: x['status'] for x in c.get('/api/connectors').json()['data']}
        self.assertEqual(d['mssql'], 'builtin'); self.assertEqual(d['mcp'], 'builtin')
        self.assertEqual(d['postgres'], 'planned')

    def test_mssql_endpoints(self):
        with mock.patch('taskuary.mssql.drivers', return_value=['ODBC Driver 18 for SQL Server']):
            self.assertEqual(c.get('/api/mssql/drivers').json()['data'], ['ODBC Driver 18 for SQL Server'])
        with mock.patch('taskuary.mssql.test', return_value={'ok': True, 'version': 'v', 'database': 'd'}):
            self.assertTrue(c.post('/api/mssql/test', json={'server': 'localhost'}).json()['ok'])

    def test_token_gate(self):
        server.cfg['server']['token'] = 'secret'
        try:
            self.assertEqual(c.get('/api/settings').status_code, 401)
            self.assertEqual(c.get('/api/settings', headers={'X-Taskuary-Token': 'secret'}).status_code, 200)
        finally:
            server.cfg['server'].pop('token')


if __name__ == '__main__':
    unittest.main()
