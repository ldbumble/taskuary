"""The triage line - the fourth line of a report's card (reports.LINES). The owner, 2026-10-16: "most reports should not go
through triage ... unless it's a report if something fails, it should be setting. if it's always show up then it's just a report
fyi, not a optional if this happens, then triage then fix type of thing." And: "if triage finds something that is already a task
that triage should not make it a task" - a run about work that exists notes that task, and never joins it."""
import json, os, tempfile, unittest
from unittest import mock
from taskuary import ingest, reports
from taskuary.store import MemoryStore, SQLiteStore

TASK_LLM = lambda sys_, usr, **kw: '{"intent": "task", "kind": "general", "why": "something broke"}'


def _brain(s): s.save_connector({'ConnectorId': s.get_connector_by_type('anthropic')['ConnectorId'], 'Active': 1, 'Secret': 'k'}, 't')


def _src(s, cfg):
    sid = s.save_source({'Channel': 'report', 'Address': cfg['title'], 'ConfigJson': json.dumps(cfg), 'Active': 1}, 't')
    return next(x for x in s.list_sources(active_only=False) if x['SourceId'] == sid)


def _reports(s): return s._rows("SELECT * FROM message WHERE Channel='report' ORDER BY MessageId")


class TriageLineTests(unittest.TestCase):
    def test_nobody_set_it_so_nothing_is_triaged(self):
        self.assertEqual(reports.route_of({'type': 'agent'}, 'triage'), ('never', ''))
        self.assertEqual(reports.full_route({'type': 'evening_inbox'})['triage'], {'how': 'never'})
        self.assertNotIn('triage', reports.route_words({'type': 'agent'}), 'a line about nothing is not said')
        self.assertIn('triage: when anything came back', reports.route_words(
            {'route': {'triage': {'how': 'rule', 'rule': 'something_came_back'}}}))

    def test_a_daily_report_never_reaches_triage_and_never_joins_a_task(self):
        """A daily checkup's line about an open thread was read as that task, and the whole run joined it - then the next run
        followed it there for the chain."""
        s = MemoryStore(); _brain(s)
        tid = s.create_task({'Title': 'Send Erin the vendor contract', 'Kind': 'general', 'Status': 'open'}, 'o')
        src = _src(s, {'type': 'evening_inbox', 'title': 'End of day checkup'})
        with mock.patch.object(reports, 'render_report', return_value=('ran', 'Still open: the vendor contract for Erin')), \
             mock.patch('taskuary.ingest.ingest_message') as door:
            reports.run_report_source(s, src, llm=TASK_LLM); reports.run_report_source(s, src, llm=TASK_LLM)
        door.assert_not_called()
        self.assertEqual([(m['Status'], m['TaskId']) for m in _reports(s)], [('feed', None)] * 2)
        self.assertEqual([t['TaskId'] for t in s.list_tasks()], [tid])

    def test_a_monitor_is_triaged_only_when_its_condition_fires(self):
        s = MemoryStore(); _brain(s)
        src = _src(s, {'type': 'agent', 'title': 'Process Error Check', 'route': {'triage': {'how': 'rule', 'rule': 'something_came_back'}}})
        with mock.patch('taskuary.ingest._spawn'):
            with mock.patch.object(reports, 'render_report', return_value=('0 rows', '')): reports.run_report_source(s, src, llm=TASK_LLM)
            self.assertEqual(s.list_tasks(), [], 'nothing came back: a row, never triage')
            with mock.patch.object(reports, 'render_report', return_value=('2 rows', 'Northwind import failed\nPayworth sync failed')):
                reports.run_report_source(s, src, llm=TASK_LLM)
        self.assertEqual(len(s.list_tasks()), 1)

    def test_the_judge_is_asked_the_triage_question(self):
        cfg = {'route': {'triage': {'how': 'ai', 'when': 'an import failed'}}}
        self.assertIn('TRIAGE: yes|no — let triage judge the run - it decides whether it needs a task, and makes none for what an open task already covers, but only if: an import failed',
                      reports.judge_prompt(cfg))
        no = reports.decide(cfg, reports.read_result('ran', 'all fine'), llm=lambda *a, **k: 'TRIAGE: no')
        yes = reports.decide(cfg, reports.read_result('ran', 'the import failed'), llm=lambda *a, **k: 'TRIAGE: yes')
        self.assertEqual((no['triage'], yes['triage']), (False, True))

    def test_the_line_is_set_like_the_others(self):
        cfg = reports.set_line({'type': 'agent'}, 'triage', 'ai', 'a payment bounced')
        self.assertEqual(reports.route_of(cfg, 'triage'), ('ai', 'a payment bounced'))
        self.assertEqual(reports.route_of(cfg, 'timeline'), ('always', ''))

    def test_a_failed_run_goes_down_no_line(self):
        self.assertFalse(reports.decide({'route': {'triage': {'how': 'always'}}}, reports.read_result('FAILED', '', True))['triage'])

    def test_an_advisor_keeps_triaging_its_ideas_unless_its_line_says_not(self):
        """An assistant voice's ideas are each triaged as they are said (assistant.triage_ideas); its line starts on."""
        self.assertEqual(reports.route_of({'type': 'assistant'}, 'triage'), ('always', ''))
        from taskuary import assistant
        llm = lambda *a, **k: json.dumps({'say': [{'key': 'idea:contract', 'text': 'Erin has waited three days on the contract.',
                                                   'why': 'her last mail', 'mid': None, 'task': None}]})
        for how, called in (('always', True), ('never', False)):
            s = MemoryStore()
            cfg = {'type': 'assistant', 'route': {'timeline': {'how': 'always'}, 'triage': {'how': how}}}
            with self.subTest(how=how), mock.patch.object(assistant, 'triage_ideas') as tri:
                out = assistant.run(s, llm=llm, force=True, judge=lambda lines, n: reports.decide(cfg, reports.read_result('t', lines, False, n)))
                self.assertEqual(out['said'], 1); self.assertEqual(tri.called, called)


class ReportMentionsTests(unittest.TestCase):
    """A run sent through triage that is about an open task: no new task, never joined to it, one note on it a day."""
    def setUp(self):
        self.s = s = MemoryStore(); _brain(s)
        self.tid = s.create_task({'Title': 'Send Erin the vendor contract', 'Kind': 'general', 'Status': 'open'}, 'o')
        self.src = _src(s, {'type': 'agent', 'title': 'Contract watch', 'route': {'triage': {'how': 'always'}}})

    def _run(self, verdict, body='Still open: the vendor contract for Erin'):
        with mock.patch.object(reports, 'render_report', return_value=('ran', body)), mock.patch('taskuary.ingest._spawn'), \
             mock.patch('taskuary.ingest.judge', return_value=(verdict, {})):
            return reports.run_report_source(self.s, self.src, llm=TASK_LLM)

    def _notes(self): return [c for c in self.s.list_comments(self.tid) if c['Body'].startswith('Contract watch mentions this')]
    def _on_task(self): return self.s._rows('SELECT * FROM message WHERE TaskId=?', (self.tid,))

    def test_a_run_about_an_open_task_notes_it_and_is_not_joined_to_it(self):
        self._run({'intent': 'task', 'kind': 'general', 'why': 'the contract', 'same_as': self.tid})
        m = _reports(self.s)[-1]
        self.assertEqual((m['Status'], m['TaskId']), ('feed', None))
        self.assertEqual([t['TaskId'] for t in self.s.list_tasks()], [self.tid], 'no second task for work that has one')
        self.assertEqual(self._on_task(), [], 'never on the task, so never its origin')
        self.assertEqual(len(self._notes()), 1); self.assertIn(f"#{m['MessageId']}", self._notes()[0]['Body'])

    def test_the_next_run_does_not_stack_a_second_note_or_follow_the_chain(self):
        v = {'intent': 'fyi', 'why': 'the contract again', 'same_as': self.tid}
        self._run(v); self._run(v)
        self.assertEqual(len(self._notes()), 1); self.assertEqual(self._on_task(), [])
        self.assertEqual(len(_reports(self.s)), 2)

    def test_a_problem_no_task_covers_opens_one(self):
        self._run({'intent': 'task', 'kind': 'general', 'why': 'a new failure', 'title': 'Payworth sync is failing'},
                  body='Payworth sync failed overnight')
        self.assertEqual(len(self.s.list_tasks()), 2); self.assertEqual(self._notes(), [])

    def test_a_run_never_joins_by_the_reports_own_thread(self):
        """Every run of one report shares `report:<sid>`: one that once landed on a task pulled every later run onto it."""
        conv = f"report:{self.src['SourceId']}"
        self.s.add_message({'TaskId': self.tid, 'ExternalId': 'report:x:1', 'ConversationId': conv, 'Channel': 'report',
                            'Subject': 'an older run', 'Status': 'routed'})
        r = ingest.identity_route(self.s, {'channel': 'report', 'conversation_id': conv})
        self.assertEqual((r['decision'], r['task_id']), ('create', None))


class TriageLineMigrationTests(unittest.TestCase):
    """Every report was triaged every run before the line existed: each gets the line its own behaviour already says, once."""
    CASES = [({'type': 'mssql', 'route': {'timeline': {'how': 'ai', 'when': 'an import failed'}}}, {'how': 'ai', 'when': 'an import failed'}),
             ({'type': 'agent', 'route': {'timeline': {'how': 'rule', 'rule': 'something_came_back'}}}, {'how': 'rule', 'rule': 'something_came_back'}),
             ({'type': 'evening_inbox', 'route': {'timeline': {'how': 'always'}}}, {'how': 'never'}),
             ({'type': 'digest'}, {'how': 'never'}),
             ({'type': 'assistant', 'route': {'timeline': {'how': 'ai', 'when': 'it has an idea'}}}, {'how': 'always'}),
             ({'type': 'assistant', 'route': {'timeline': {'how': 'rule', 'rule': 'something_came_back'}}}, {'how': 'rule', 'rule': 'something_came_back'}),
             ({'type': 'agent', 'route': {'timeline': {'how': 'always'}, 'work': {'how': 'ai', 'when': 'a build broke'}}}, {'how': 'ai', 'when': 'a build broke'})]

    def test_the_mapping(self):
        for cfg, want in self.CASES:
            with self.subTest(cfg=cfg): self.assertEqual(reports.triage_from(cfg if cfg.get('route') else reports.from_old_rules(cfg)), want)

    def test_the_startup_migration_runs_once(self):
        d = tempfile.mkdtemp(); fn = os.path.join(d, 't.db')
        s = SQLiteStore(fn)
        s.cx.execute("DELETE FROM setting WHERE Name='report_triage_line_set'"); s.cx.execute("DELETE FROM source WHERE Channel='report'")
        s.cx.executemany("INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES ('report', 'r', 'owner', 1, ?)",
                         [(json.dumps({'title': f'r{i}', **c}),) for i, (c, _) in enumerate(self.CASES)])
        s.cx.commit(); s.cx.close()
        s = SQLiteStore(fn)
        routes = lambda: [json.loads(r['ConfigJson'])['route'] for r in s._rows("SELECT * FROM source WHERE Channel='report' ORDER BY SourceId")]
        self.assertEqual([r['triage'] for r in routes()], [w for _, w in self.CASES])
        # ...and once: an owner who later turns a daily report's triage on keeps it across launches
        sid = s._rows("SELECT SourceId FROM source WHERE Channel='report' ORDER BY SourceId")[2]['SourceId']
        s.save_source({'SourceId': sid, 'ConfigJson': json.dumps(reports.set_line(json.loads(s.get_source(sid)['ConfigJson']), 'triage', 'always'))}, 'o')
        s.cx.close(); s = SQLiteStore(fn)
        self.assertEqual(routes()[2]['triage'], {'how': 'always'})
        s.cx.close()


def _answering(payload):
    return lambda system, user, **k: json.dumps(payload)


WATCH = 'the import job shows an error'
PLAIN = {'type': 'agent', 'title': 'Morning trends', 'prompt': 'List the fastest-rising repositories.', 'daily_at': '08:00'}


class ComposerTests(unittest.TestCase):
    """The composer sets the line from what the owner wrote: a report they simply want is never triaged; a watch speaks when its
    condition holds and triage judges that same run."""
    def test_a_report_the_owner_simply_wants_is_never_triaged(self):
        from taskuary import compose
        # ...even when the model writes a route of its own: the server writes the card, from `watch` alone
        out = compose.compose(MemoryStore(), 'send me the trending repositories every morning',
                              _answering({'config': {**PLAIN, 'route': {'triage': {'how': 'always'}}}, 'explain': 'x', 'confidence': 'high'}))
        self.assertEqual(out['config']['route'], {'triage': {'how': 'never'}})
        self.assertEqual(reports.route_of(out['config'], 'timeline'), ('always', ''))

    def test_a_watch_shows_on_its_condition_and_triage_judges_the_same_run(self):
        from taskuary import compose
        seen = {}
        def llm(system, user, **k):
            seen['system'] = system
            return json.dumps({'config': {**PLAIN, 'title': 'Import watch', 'watch': WATCH}, 'explain': 'x', 'confidence': 'high'})
        out = compose.compose(MemoryStore(), 'tell me if the import job shows an error', llm)
        cfg = out['config']
        self.assertNotIn('watch', cfg)
        self.assertEqual((reports.route_of(cfg, 'timeline'), reports.route_of(cfg, 'triage')), (('ai', WATCH), ('ai', WATCH)))
        self.assertIn('"watch": ONLY when the owner wants to hear from it IF something happens', seen['system'])
        self.assertIn('makes none for what an open task already covers', seen['system'])
        self.assertNotIn('escalate', seen['system'].lower())

    def test_a_workflow_never_keeps_a_watch_checkout_or_not(self):
        """Every workflow run is a task handed to its worker (workflows.run) - a coding one with its checkout too: no run is
        filed as a report, so no condition is waited for and triage never reads one."""
        from taskuary import compose
        s = MemoryStore(); s.upsert_agent('coding', 'cli', 'local', json.dumps({'cmd': 'codex'}))
        wf = {'type': 'agent', 'title': 'Dependency watch', 'agent': 'coding', 'prompt': 'Bump what is outdated.', 'watch': 'a bump breaks the build'}
        coded = compose.compose_workflow(s, 'bump deps and tell me if it breaks', _answering({'config': {**wf, 'cwd': 'C:/work/ledger'}}))['config']
        handed = compose.compose_workflow(s, 'bump deps and tell me if it breaks', _answering({'config': wf}))['config']
        self.assertEqual((coded['route'], handed['route']), ({'triage': {'how': 'never'}}, {'triage': {'how': 'never'}}))


class WorkflowRoadTests(unittest.TestCase):
    """compose -> run (a fake CLI) -> route, end to end, for the agent-type report a workflow is."""
    def setUp(self):
        self.s = s = MemoryStore(); _brain(s)
        s.upsert_agent('coding', 'cli', 'local', json.dumps({'cmd': 'codex'}))
        s.set_setting('default_brain', 'codex', 'owner')          # the CLI the report runs on: with none, it says "No AI is connected"
        s.set_setting('general_auto_enabled', '1', 't'); s.set_setting('coding_auto_enabled', '1', 't')
        self.tid = s.create_task({'Title': 'Fix the Northwind import', 'Kind': 'general', 'Status': 'open'}, 'o')

    def _saved(self, cfg):
        return _src(self.s, cfg)

    def _run(self, src, said, verdict=None, triage_says='no'):
        """`said` is what the fake CLI answers; the routing judge answers TIMELINE/TRIAGE from `triage_says`."""
        judge = lambda system, user, **k: f'TIMELINE: {triage_says}\nTRIAGE: {triage_says}'
        with mock.patch('taskuary.llm.make_cli_llm', lambda *a, **k: (lambda system, user, **kw: said)), \
             mock.patch('taskuary.ingest._spawn'), mock.patch('taskuary.ingest._auto_code'), mock.patch('taskuary.ingest._auto_general'), \
             mock.patch('taskuary.ingest.judge', return_value=(verdict or {'intent': 'fyi', 'why': 'nothing'}, {})) as tri:
            out = reports.run_report_source(self.s, src, llm=judge)
        return out, tri

    def test_a_plain_agent_report_is_a_row_under_reports_and_never_reaches_triage(self):
        from taskuary import compose
        cfg = compose.compose(self.s, 'send me the trending repositories every morning', _answering({'config': PLAIN}))['config']
        out, tri = self._run(self._saved(cfg), 'Five repositories rose this week; the import fix is still open.')
        tri.assert_not_called()
        self.assertEqual((self.s.get_message(out['message_id'])['Status'], self.s.get_message(out['message_id'])['TaskId']), ('feed', None))
        self.assertEqual([t['TaskId'] for t in self.s.list_tasks()], [self.tid])

    def test_a_watch_goes_to_triage_only_when_it_fires_and_never_joins_the_task_it_names(self):
        from taskuary import compose
        cfg = compose.compose(self.s, 'tell me if the import job shows an error',
                              _answering({'config': {**PLAIN, 'title': 'Import watch', 'watch': WATCH}}))['config']
        src = self._saved(cfg)
        _, tri = self._run(src, 'All imports ran clean.', triage_says='no')
        tri.assert_not_called()
        out, tri = self._run(src, 'The Northwind import failed again.', {'intent': 'task', 'kind': 'general', 'why': 'the import', 'same_as': self.tid},
                             triage_says='yes')
        tri.assert_called_once()
        self.assertEqual(self.s._rows('SELECT * FROM message WHERE TaskId=?', (self.tid,)), [], 'a mention, never a message on the task')
        self.assertEqual([t['TaskId'] for t in self.s.list_tasks()], [self.tid], 'no second task for work that has one')
        self.assertEqual(len([c for c in self.s.list_comments(self.tid) if 'Import watch mentions this' in c['Body']]), 1)

    def test_a_coding_workflow_is_its_own_task_too_and_never_triage(self):
        """It ran on the report road and triage read what it said (the owner, 2026-10-16: "if it runs on schedule it should also
        show up as task"): now its run is a coding task like its Run now, and no report row is filed."""
        from taskuary import compose
        wf = {'type': 'agent', 'title': 'Dependency watch', 'agent': 'coding', 'prompt': 'Bump what is outdated.', 'cwd': 'C:/work/ledger',
              'watch': 'a bump breaks the build'}
        src = self._saved(compose.compose_workflow(self.s, 'bump deps and tell me if it breaks', _answering({'config': wf}))['config'])
        with mock.patch('taskuary.workflows._spawn', lambda fn: fn()):
            out, tri = self._run(src, 'The build broke after the bump.', triage_says='yes')
        tri.assert_not_called()
        t = self.s.get_task(out['task_id'])
        self.assertEqual((t['Source'], t['Kind'], self.s._rows("SELECT * FROM message WHERE Channel='report'")), ('workflow', 'coding', []))

    def test_a_workflow_with_no_checkout_is_its_own_task_and_never_triage(self):
        """Today's road for a composed workflow (workflows.run): each run is a task handed to its worker - no report row, no triage."""
        from taskuary import compose
        wf = {'type': 'agent', 'title': 'Weekly access review', 'agent': 'coding', 'prompt': 'Revoke stale admin grants.'}
        src = self._saved(compose.compose_workflow(self.s, 'review admin grants weekly', _answering({'config': wf}))['config'])
        out, tri = self._run(src, 'unused')
        tri.assert_not_called()
        t = self.s.get_task(out['task_id'])
        self.assertEqual((t['Source'], self.s._rows("SELECT * FROM message WHERE Channel='report'")), ('workflow', []))


if __name__ == '__main__': unittest.main()
