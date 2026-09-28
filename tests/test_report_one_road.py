"""One road for running a report, and one card for where a run goes (the owner, 2026-09-27: C1-C6).

Six doors used to run a report - the clock, app start, Run due now, Run now, the Assistant, the phone - and
each took a different part of the job: one held a lock, one used up the daily cap, one answered the chat.
And three rule sets decided where a run went. These pin the one road and the one card.
"""
import json
from datetime import datetime, timedelta
from unittest import mock

from taskuary import reports
from taskuary.reports import REGISTRY
from taskuary.store import MemoryStore


def _report(s, cfg, title='Ledger check'):
    sid = s.save_source({'Channel': 'report', 'Address': title, 'Active': 1, 'ConfigJson': json.dumps({'title': title, **cfg})}, 't')
    return s.get_source(sid)


def _rows(n=3):
    REGISTRY['_r'] = lambda cfg: (f'{n} rows', '\n'.join(f'row {i}' for i in range(n)))


# ── C3/C4: the one road ─────────────────────────────────────────────────────────────────
def test_a_manual_run_does_not_use_up_once_a_day():
    """Run now at 10:00 must not cancel the 18:00 checkup."""
    s = MemoryStore(); _rows()
    try:
        src = _report(s, {'type': '_r', 'daily_at': '18:00', 'once_per_day': True})
        reports.run_one(s, src, None, 'manual')
        assert not s.get_source(src['SourceId'])['LastPolledAt']
        reports.run_one(s, src, None, 'schedule')
        assert s.get_source(src['SourceId'])['LastPolledAt']
    finally: REGISTRY.pop('_r')


def test_one_run_of_a_report_at_a_time():
    s = MemoryStore()
    src = _report(s, {'type': '_r'})
    reports._RUNNING.add(src['SourceId'])
    try:
        assert reports.run_one(s, src, None, 'manual')['busy'] is True
    finally: reports._RUNNING.discard(src['SourceId'])


def test_a_failed_scheduled_run_waits_for_its_next_slot():
    # never retried in between: every 15 minutes for ever paid for the AI each time (the owner, 2026-09-28)
    s = MemoryStore()
    src = _report(s, {'type': '_r', 'every_minutes': 60})
    with mock.patch.object(reports, 'run_report_source', return_value={'failed': True, 'subject': 'r — FAILED'}):
        assert reports.run_one(s, src, None)['failed']
    assert s.get_source(src['SourceId'])['LastPolledAt']
    assert src['SourceId'] not in [x['SourceId'] for x in reports.due_reports(s)]


def test_a_report_whose_settings_do_not_parse_never_stops_the_others():
    s = MemoryStore()
    bad = _report(s, {'type': '_r', 'every_minutes': 1}, 'broken')
    s.cx.execute('UPDATE source SET ConfigJson=? WHERE SourceId=?', ('{not json', bad['SourceId'])); s.cx.commit()
    good = _report(s, {'type': '_r', 'every_minutes': 1}, 'fine')
    due = [x['SourceId'] for x in reports.due_reports(s)]
    assert good['SourceId'] in due and bad['SourceId'] not in due


def test_no_clock_means_by_hand():
    assert reports.is_due({'type': '_r'}, None) is False
    assert reports.schedule_words({'type': '_r'}) == 'no schedule - run it by hand'


# ── N1: a switched-off connection does not run on a schedule ───────────────────────────
def test_a_switched_off_connection_fails_the_run_and_says_what_to_do():
    s = MemoryStore()
    c = s.get_connector_by_type('mssql')
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 0}, 't')
    src = _report(s, {'type': 'mssql', 'query': 'select 1', 'connector_id': c['ConnectorId']})
    out = reports.run_report_source(s, src, None)
    assert out['failed'] and out['message_id'] is None and 'connection is off' in out['error']
    assert 'connection is off' in s.report_runs(src['SourceId'], 1)[0]['error']


# ── C2 and the mute: the alert answers for itself ──────────────────────────────────────
def test_the_alert_fires_on_a_run_the_timeline_put_down():
    s = MemoryStore(); _rows(0)
    try:
        src = _report(s, {'type': '_r', 'alert': {'to': '+15550100'},
                          'route': {'timeline': {'how': 'never'}, 'alert': {'how': 'rule', 'rule': 'nothing_came_back'}}})
        with mock.patch.object(reports, 'alert_or_file', return_value=None) as sent, \
             mock.patch('taskuary.funnel.settle') as settled:
            out = reports.run_report_source(s, src, None)
        assert sent.called and settled.called and not s.get_message(out['message_id'])['TaskId']
    finally: REGISTRY.pop('_r')


def test_a_muted_report_does_not_ping_you():
    s = MemoryStore(); _rows()
    try:
        src = _report(s, {'type': '_r', 'alert': {'to': '+15550100'}, 'route': {'alert': {'how': 'always'}}})
        s.set_setting('funnel_mutes', json.dumps([{'words': ['ledger', 'check'], 'why': 'handled elsewhere'}]), 't')
        with mock.patch.object(reports, 'alert_or_file', return_value=None) as sent:
            reports.run_report_source(s, src, None)
        assert not sent.called
    finally: REGISTRY.pop('_r')


def test_a_muted_report_is_out_of_the_morning_brief():
    # G1: a mute covered the alert and the rail, never the brief the docs said it did
    from taskuary import assistant
    s = MemoryStore(); _rows()
    try:
        src = _report(s, {'type': '_r', 'route': {'timeline': {'how': 'always'}}})
        reports.run_report_source(s, src, None)
        assert 'Ledger check' in assistant._recent(s)
        s.set_setting('funnel_mutes', json.dumps([{'words': ['ledger', 'check'], 'why': 'handled elsewhere'}]), 't')
        assert 'Ledger check' not in assistant._recent(s)
    finally: REGISTRY.pop('_r')


def test_one_source_of_two_failing_keeps_the_other_and_the_bell_names_the_missing_one():
    # D7 (2026-09-28): the whole run used to count as failed, and the good source's rows were dropped
    from taskuary import problems
    s = MemoryStore()
    REGISTRY['_ok'] = lambda cfg: ('3 rows', '\n'.join('abc'))
    def boom(cfg): raise RuntimeError('login timeout')
    REGISTRY['_bad'] = boom
    try:
        src = _report(s, {'sources': [{'type': '_ok', 'label': 'cash'}, {'type': '_bad', 'label': 'the box'}],
                          'route': {'timeline': {'how': 'always'}}})
        out = reports.run_report_source(s, src, None)
    finally: REGISTRY.pop('_ok'); REGISTRY.pop('_bad')
    assert not out.get('failed')
    subjects = [r['Subject'] for r in s.feed(limit=10, days=1, channel='report')]
    # the failed source is no row of its own: the bell says which one the run went without
    assert len(subjects) == 1 and 'cash: 3 rows' in subjects[0]
    assert [p['title'] for p in problems.collect(s) if p['key'] == f"report:{src['SourceId']}"] == ['Ledger check ran without the box']


# ── C6: a failure stays in the app - in the bell, and nowhere else ─────────────────────
def test_a_failure_files_no_row_and_pings_nobody():
    s = MemoryStore()
    src = _report(s, {'type': '_r', 'alert': {'to': '+15550100'}, 'deliver': {'to': 'ops@example.com', 'gate': 'auto'},
                      'route': {'timeline': {'how': 'always'}, 'alert': {'how': 'always'}, 'send': {'how': 'always'}}})
    with mock.patch.object(reports, 'render_report', side_effect=RuntimeError('login timeout')), \
         mock.patch.object(reports, 'alert_or_file') as alerted, mock.patch.object(reports, 'deliver_report') as sent:
        out = reports.run_report_source(s, src, None)
    assert out['failed'] and out['message_id'] is None and not alerted.called and not sent.called
    assert s.feed(limit=10, days=1, channel='report') == []
    last = s.report_runs(src['SourceId'], 1)[0]
    assert last['failed'] and 'login timeout' in last['error']


def test_a_failed_run_rings_the_bell_until_a_run_works():
    """The owner, 2026-09-28: a failure files no row, so the bell is where it is seen - and it clears
    itself the moment the report runs again, rather than waiting to be dismissed."""
    from taskuary import problems
    s = MemoryStore(); _rows()
    try:
        src = _report(s, {'type': '_r'})
        with mock.patch.object(reports, 'render_report', side_effect=RuntimeError('login timeout')):
            reports.run_report_source(s, src, None)
        rung = [p for p in problems.collect(s) if p['key'] == f"report:{src['SourceId']}"]
        assert len(rung) == 1 and rung[0]['title'] == 'Report failed: Ledger check' and rung[0]['report'] == src['SourceId']
        assert 'login timeout' in rung[0]['detail']
        reports.run_report_source(s, src, None)
        assert not [p for p in problems.collect(s) if p['key'] == f"report:{src['SourceId']}"]
    finally: REGISTRY.pop('_r')


def test_the_same_failure_again_stays_a_failure_in_the_history():
    """It used to be recorded as a clean run, so the one after it spoke again - every other time."""
    s = MemoryStore()
    src = _report(s, {'type': '_r'})
    with mock.patch.object(reports, 'render_report', side_effect=RuntimeError('login timeout')):
        runs = [reports.run_report_source(s, src, None) for _ in range(3)]
    assert all(r['failed'] and r['message_id'] is None for r in runs)
    assert all(r['failed'] for r in s.report_runs(src['SourceId'], 3))


def test_one_test_for_failed():
    assert reports.run_failed('Ledger check — FAILED')
    assert reports.run_failed('Ledger check — cash: FAILED · the box: FAILED')
    # one source of two failing is a run that worked without it (D7)
    assert not reports.run_failed('Ledger check — cash: 3 rows · the box: FAILED')
    assert reports.failed_sources('Ledger check — cash: 3 rows · the box: FAILED') == ['the box']
    assert not reports.run_failed('Process Error Check — 0 rows')
    assert not reports.run_failed('FAILED jobs — 2 rows')
    # a title with a dash of its own still fails (R1: it read as a success and mailed its error out)
    assert reports.run_failed('AP — daily — FAILED')
    assert not reports.run_failed('AP — daily — 3 rows')


# ── W3: Timeline never means never ─────────────────────────────────────────────────────
def test_timeline_never_is_a_task_or_nothing():
    s = MemoryStore(); _rows()
    try:
        src = _report(s, {'type': '_r', 'deliver': {'to': 'x@example.com'},
                          'route': {'timeline': {'how': 'never'}, 'send': {'how': 'never'}}})
        with mock.patch('taskuary.ingest.ingest_message', return_value={'message_id': None}), \
             mock.patch('taskuary.funnel.settle') as settled:
            out = reports.run_report_source(s, src, None)
        settled.assert_called_once_with(s, f"report:{out['message_id']}", 'done', 'report')
    finally: REGISTRY.pop('_r')


# ── C1: every report is the card, from the moment the store opens ──────────────────────
def test_the_store_converts_a_report_written_the_old_way_when_it_opens(tmp_path):
    from taskuary.store import SQLiteStore
    db = str(tmp_path / 'old.db')
    s = SQLiteStore(db)
    s.cx.execute('INSERT INTO source (Channel, Address, Owner, Active, ConfigJson) VALUES (?,?,?,?,?)',
                 ('report', 'Old', 'owner', 1, json.dumps({'type': 'mssql', 'reach': 'rule', 'triage': True,
                                                             'alert': {'when': 'more_than', 'count': 5, 'to': 'me@example.com'}})))
    s.cx.commit(); s.cx.close()
    s = SQLiteStore(db)
    cfg = json.loads(next(x for x in s.list_sources(active_only=False) if x['Address'] == 'Old')['ConfigJson'])
    rule = {'how': 'rule', 'rule': 'more_than', 'count': 5}
    # the triage switch has no line to become: every run is triaged now (2026-09-28)
    assert cfg['route'] == {'timeline': rule, 'alert': rule, 'send': {'how': 'always'}}
    assert cfg['alert'] == {'to': 'me@example.com'} and 'reach' not in cfg and 'triage' not in cfg
    s.cx.close()


def test_the_demo_runs_no_reports_on_a_clock(monkeypatch):
    """A made-up world with its report rows already in it: an Advisor posting mid-session moved the rows a
    visitor - and the browser tests - were reading (CI, 2026-09-28)."""
    from taskuary import server
    monkeypatch.setenv('TASKUARY_DEMO', '1')
    with mock.patch.object(server, 'run_due_reports') as ran:
        assert server.report_pass(startup=True) is None
    ran.assert_not_called()


def test_an_advisor_whose_model_fails_is_a_failed_run():
    """R2: it posted the facts alone, read as a success and moved the clock (the owner, 2026-09-28: "same error")."""
    s = MemoryStore()
    src = _report(s, {'type': 'assistant'}, 'Advisor')
    with mock.patch('taskuary.assistant.run', return_value={'ran': True, 'said': 0, 'failed': True, 'error': 'the model pass failed: 529'}):
        out = reports.run_report_source(s, src, None)
    assert out['failed'] and reports.run_failed(out['subject'])
    assert s.report_runs(src['SourceId'], 1)[0]['failed']
