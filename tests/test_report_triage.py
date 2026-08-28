"""A report may become work: with `triage` on, each run is an inbound message TRIAGE.md judges;
off (the default) it stays informational. And the Board's Done lane is agent work only."""
import json, unittest
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import reports, server
from taskuary.store import MemoryStore

TASK_LLM = lambda sys_, usr, **kw: '{"intent": "task", "kind": "coding", "why": "the research names a doc to build"}'


class ReportTriageTests(unittest.TestCase):
    def _src(self, s, cfg):
        sid = s.save_source({'Channel': 'report', 'Address': cfg['title'], 'ConfigJson': json.dumps(cfg), 'Active': 1}, 't')
        return next(x for x in s.list_sources(active_only=False) if x['SourceId'] == sid)

    def test_off_by_default_a_report_is_informational(self):
        s = MemoryStore()
        src = self._src(s, {'type': 'agent', 'title': 'Trends'})
        with mock.patch.object(reports, 'render_report', return_value=('coder ran a prompt', '# Trends\nbuild a doc about X')):
            reports.run_report_source(s, src, llm=TASK_LLM)
        m = s._rows("SELECT * FROM message WHERE Channel='report'")[0]
        self.assertEqual((m['Status'], m['TaskId']), ('feed', None))
        self.assertIn('never a task', s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])

    def test_with_triage_on_the_brain_decides_and_a_task_can_open(self):
        s = MemoryStore()
        s.save_connector({'ConnectorId': s.get_connector_by_type('anthropic')['ConnectorId'], 'Active': 1, 'Secret': 'k'}, 't')   # triage needs a brain card
        src = self._src(s, {'type': 'agent', 'title': 'Trends', 'triage': True})
        with mock.patch.object(reports, 'render_report', return_value=('coder ran a prompt', '# Trends\nbuild a doc about X')), \
             mock.patch('taskuary.ingest._spawn'):
            reports.run_report_source(s, src, llm=TASK_LLM)
        m = s._rows("SELECT * FROM message WHERE Channel='report'")[0]
        self.assertEqual(m['Status'], 'routed'); self.assertTrue(m['TaskId'])
        t = s.get_task(m['TaskId'])
        self.assertEqual(t['Kind'], 'coding'); self.assertIn('Trends', t['Title'])
        self.assertIn('triage:', s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])

    def test_a_failed_run_is_never_triaged(self):
        s = MemoryStore()
        s.save_connector({'ConnectorId': s.get_connector_by_type('anthropic')['ConnectorId'], 'Active': 1, 'Secret': 'k'}, 't')
        src = self._src(s, {'type': 'agent', 'title': 'Trends', 'triage': True})
        with mock.patch.object(reports, 'render_report', side_effect=RuntimeError('claude exit 1')):
            reports.run_report_source(s, src, llm=TASK_LLM)
        m = s._rows("SELECT * FROM message WHERE Channel='report'")[0]
        self.assertEqual((m['Status'], m['TaskId']), ('feed', None)); self.assertIn('FAILED', m['Subject'])
        self.assertIn('not triaged', s._rows('SELECT * FROM route ORDER BY RouteId DESC')[0]['Reason'])


class BoardDoneTests(unittest.TestCase):
    def test_tasks_say_whether_an_agent_ever_touched_them(self):
        c = TestClient(server.app)
        s = server.store
        a = s.create_task({'Title': 'answered by hand', 'Kind': 'reply', 'Status': 'done'}, 't')
        b = s.create_task({'Title': 'agent worked it', 'Kind': 'general', 'Status': 'done'}, 't')
        s.add_transcript(b, 'sid-x', 'did things', 'coder', 'C:/x')
        rows = {r['TaskId']: r for r in c.get('/api/tasks').json()['data']}
        self.assertFalse(rows[a]['HadAgent']); self.assertTrue(rows[b]['HadAgent'])
