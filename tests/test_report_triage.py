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

    def test_a_new_run_retires_the_one_before_it(self):
        """Seven "Process Error Check - 0 rows" stacked up in the reports band say nothing the
        newest one does not (the owner, 2026-09-16). NOTHING IS DELETED: the earlier run is settled
        done, off the work rail and still on the Timeline with its rows."""
        from taskuary import funnel
        s = MemoryStore()
        src = self._src(s, {'type': 'agent', 'title': 'Process Error Check'})
        with mock.patch.object(reports, 'render_report', return_value=('ran', '# Check - 0 rows')):
            reports.run_report_source(s, src)
            first = s._rows("SELECT * FROM message WHERE Channel='report' ORDER BY MessageId DESC")[0]['MessageId']
            self.assertEqual(funnel.build(s)['items'][0]['mid'], first)      # it is on the rail
            reports.run_report_source(s, src)
        rows = s._rows("SELECT * FROM message WHERE Channel='report' ORDER BY MessageId")
        self.assertEqual(len(rows), 2, 'the old run is kept, not deleted')
        # ...and only the newest is still waiting on the owner
        self.assertEqual([i['mid'] for i in funnel.build(s)['items']], [rows[-1]['MessageId']])
        self.assertEqual(s.funnel_states()[f'report:{first}']['Status'], 'done')

    def test_a_run_that_became_work_is_never_retired(self):
        """A job does not expire because a schedule fired."""
        from taskuary import funnel
        s = MemoryStore()
        src = self._src(s, {'type': 'agent', 'title': 'Process Error Check'})
        with mock.patch.object(reports, 'render_report', return_value=('ran', '# Check - 0 rows')):
            reports.run_report_source(s, src)
            first = s._rows("SELECT * FROM message WHERE Channel='report' ORDER BY MessageId DESC")[0]['MessageId']
            tid = s.create_task({'Title': 'Chase the failing check', 'Kind': 'coding', 'Status': 'open'}, 'o')
            s.place_message(first, tid, 'routed')                 # the owner promoted it
            reports.run_report_source(s, src)
        self.assertNotIn(f'report:{first}', s.funnel_states(), 'work is not a stale copy of the newest run')

    def test_the_owner_can_turn_it_off_per_report(self):
        from taskuary import funnel
        s = MemoryStore()
        src = self._src(s, {'type': 'agent', 'title': 'Process Error Check', 'expire': False})
        with mock.patch.object(reports, 'render_report', return_value=('ran', '# Check - 0 rows')):
            reports.run_report_source(s, src)
            first = s._rows("SELECT * FROM message WHERE Channel='report' ORDER BY MessageId DESC")[0]['MessageId']
            reports.run_report_source(s, src)
        # nothing was settled: both runs are still waiting on the owner. (The rail may still fold
        # them into one row with a +N - one report is one conversation - but that is grouping, and
        # grouping is not the same as being marked done.)
        self.assertNotIn(f'report:{first}', s.funnel_states())
        self.assertEqual(len(s._rows("SELECT * FROM message WHERE Channel='report'")), 2)

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
