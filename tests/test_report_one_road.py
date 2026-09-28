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


def test_a_failed_scheduled_run_is_owed_again_after_a_quarter_hour():
    s = MemoryStore()
    src = _report(s, {'type': '_r', 'every_minutes': 60})
    s.set_setting(f"{reports.LAST_RUN}{src['SourceId']}", json.dumps({'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                                                                       'failed': True, 'trigger': 'schedule'}), 't')
    assert reports._failed_lately(s, src['SourceId'])
    old = (datetime.now() - timedelta(minutes=reports.RETRY_MINUTES + 1)).strftime('%Y-%m-%d %H:%M:%S')
    s.set_setting(f"{reports.LAST_RUN}{src['SourceId']}", json.dumps({'at': old, 'failed': True, 'trigger': 'schedule'}), 't')
    assert not reports._failed_lately(s, src['SourceId'])


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
    assert out['failed'] and 'connection is off' in s.get_message(out['message_id'])['BodyText']


# ── C2 and the mute: the alert answers for itself ──────────────────────────────────────
def test_the_alert_fires_on_a_run_that_posted_nothing():
    s = MemoryStore(); _rows(0)
    try:
        src = _report(s, {'type': '_r', 'alert': {'to': '+15550100'},
                          'route': {'timeline': {'how': 'never'}, 'work': {'how': 'never'},
                                    'alert': {'how': 'rule', 'rule': 'nothing_came_back'}}})
        with mock.patch.object(reports, 'alert_or_file', return_value=None) as sent:
            out = reports.run_report_source(s, src, None)
        assert out['quiet'] is True and sent.called
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


# ── C6: a failure stays in the app ─────────────────────────────────────────────────────
def test_a_failure_files_one_row_and_pings_nobody():
    s = MemoryStore()
    src = _report(s, {'type': '_r', 'alert': {'to': '+15550100'}, 'deliver': {'to': 'ops@example.com', 'gate': 'auto'},
                      'route': {'timeline': {'how': 'never'}, 'alert': {'how': 'always'}, 'send': {'how': 'always'}}})
    with mock.patch.object(reports, 'render_report', side_effect=RuntimeError('login timeout')), \
         mock.patch.object(reports, 'alert_or_file') as alerted, mock.patch.object(reports, 'deliver_report') as sent:
        out = reports.run_report_source(s, src, None)
    assert out['failed'] and out['message_id'] and not alerted.called and not sent.called
    assert s.get_message(out['message_id'])['TaskId'] is None


def test_the_same_failure_again_stays_a_failure_in_the_history():
    """It used to be recorded as a clean run, so the one after it spoke again - every other time."""
    s = MemoryStore()
    src = _report(s, {'type': '_r'})
    with mock.patch.object(reports, 'render_report', side_effect=RuntimeError('login timeout')):
        reports.run_report_source(s, src, None)
        second = reports.run_report_source(s, src, None)
        third = reports.run_report_source(s, src, None)
    assert second['quiet'] and third['quiet']
    assert all(r['failed'] for r in s.report_runs(src['SourceId'], 3))


def test_one_test_for_failed():
    assert reports.run_failed('Ledger check — FAILED')
    assert reports.run_failed('Ledger check — cash: 3 rows · the box: FAILED')
    assert not reports.run_failed('Process Error Check — 0 rows')
    assert not reports.run_failed('FAILED jobs — 2 rows')


# ── W3: Timeline never means never ─────────────────────────────────────────────────────
def test_work_only_is_a_task_or_nothing():
    s = MemoryStore(); _rows()
    try:
        src = _report(s, {'type': '_r', 'deliver': {'to': 'x@example.com'},
                          'route': {'timeline': {'how': 'never'}, 'work': {'how': 'always'}, 'send': {'how': 'never'}}})
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
    assert cfg['route'] == {'timeline': rule, 'alert': rule, 'send': {'how': 'always'}, 'work': rule}
    assert cfg['alert'] == {'to': 'me@example.com'} and 'reach' not in cfg and 'triage' not in cfg
    s.cx.close()
