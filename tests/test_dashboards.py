"""Dashboards: a report you look at. The spec is checked before it is kept, a run is deterministic (no AI, ever), the rows
are kept for the page to slice, and its one row under Reports says it is fresh and opens the dashboard (dashboards.py)."""
import json
from datetime import datetime, timedelta

import pytest

from taskuary import compose, dashboards, funnel, reports
from taskuary.store import MemoryStore


def _day(n): return (datetime.now() - timedelta(days=n)).strftime('%Y-%m-%d')


SPEC = {'type': 'dashboard', 'title': 'Northwind desk', 'daily_at': '07:00',
        'sources': [{'key': 'tasks', 'label': 'Tasks', 'type': 'taskuary_data', 'dataset': 'tasks', 'date': 'arrived'}],
        'filters': {'range': 30, 'segment': 'kind'},
        'components': [{'kind': 'stat', 'title': 'Open tasks', 'source': 'tasks', 'agg': 'count', 'where': {'state': 'open'}},
                       {'kind': 'bar', 'title': 'Open by kind', 'source': 'tasks', 'x': 'kind', 'where': {'state': 'open'}},
                       {'kind': 'list', 'title': 'Open now', 'source': 'tasks', 'label': 'title', 'meta': 'kind'}]}


def _store():
    s = MemoryStore()
    for title, kind, status in (('Reconcile the GL export', 'general', 'open'), ('Census sync fails', 'coding', 'open'),
                                ('Resend the Q3 numbers', 'reply', 'done')):
        s.create_task({'Title': title, 'Kind': kind, 'Status': status}, 'owner')
    return s


def _save(s, spec=SPEC):
    sid = s.save_source({'Channel': 'report', 'Address': spec['title'], 'Active': 1, 'ConfigJson': json.dumps(spec)}, 't')
    return s.get_source(sid)


# ── the spec ──────────────────────────────────────────────────────────────────────────────────────────
def test_a_good_spec_validates():
    assert dashboards.validate(SPEC, MemoryStore()) == (True, '')


@pytest.mark.parametrize('change, says', [
    ({'title': ''}, 'no title'),
    ({'sources': []}, 'no source'),
    ({'components': []}, 'shows nothing'),
    ({'components': [{'kind': 'pie', 'title': 'Pie', 'source': 'tasks'}]}, 'not a preset'),
    ({'components': [{'kind': 'bar', 'title': 'B', 'source': 'nowhere', 'x': 'kind'}]}, 'not one of the sources'),
    ({'components': [{'kind': 'bar', 'title': 'B', 'source': 'tasks'}]}, 'needs x'),
    ({'components': [{'kind': 'stat', 'title': 'S', 'source': 'tasks', 'agg': 'sum'}]}, 'adds up'),
    ({'sources': [{'key': 'tasks', 'type': 'taskuary_data', 'dataset': 'tasks'}, {'key': 'tasks', 'type': 'taskuary_data', 'dataset': 'mail'}]}, 'own key'),
    ({'sources': [{'key': 'tasks', 'type': 'intacct'}]}, 'cannot run'),
])
def test_a_spec_that_cannot_draw_is_refused(change, says):
    ok, why = dashboards.validate({**SPEC, **change}, MemoryStore())
    assert not ok and says in why


def test_a_component_bound_to_a_column_its_source_never_returned_is_said():
    data = {'sources': {'tasks': {'label': 'Tasks', 'rows': [{'kind': 'general'}], 'columns': ['kind'], 'failed': False}}}
    spec = {**SPEC, 'components': [{'kind': 'bar', 'title': 'By team', 'source': 'tasks', 'x': 'team'}]}
    out = dashboards.problems(spec, data)
    assert any('By team' in p and 'team' in p for p in out)


# ── the data ─────────────────────────────────────────────────────────────────────────────────────────
def test_taskuary_data_is_rows_a_component_can_bind_to():
    s = _store()
    head, body = reports.REGISTRY['taskuary_data'](reports.resolve_cfg(s, {'type': 'taskuary_data', 'dataset': 'tasks'}))
    rows = dashboards.rows_of(body)
    assert head.startswith('3 ') and {r['state'] for r in rows} == {'open', 'closed'}
    assert {'task_id', 'ref', 'kind', 'arrived'} <= set(rows[0])


def test_an_unknown_dataset_says_which_there_are():
    with pytest.raises(ValueError, match='agent_runs'):
        reports.REGISTRY['taskuary_data']({'store': MemoryStore(), 'dataset': 'nope'})


def test_a_dashboard_keeps_every_row_not_the_report_body_cap(monkeypatch):
    """The 20K body is the AI pass's budget; a dashboard draws all of the rows."""
    rows = [{'n': i, 'pad': 'x' * 80} for i in range(600)]
    monkeypatch.setitem(reports.REGISTRY, '_many', lambda cfg: reports.rows_out(rows, reports.row_limit(cfg)[0]))
    s = MemoryStore()
    data = dashboards.collect(s, {'sources': [{'key': 'm', 'type': '_many'}]})
    assert len(data['sources']['m']['rows']) == 600
    assert len(reports.rows_out(rows, 600)[1]) <= reports.BODY_CHARS        # ...and a report's body is still capped


def test_one_failing_source_is_said_in_place():
    s = MemoryStore()
    data = dashboards.collect(s, {'sources': [{'key': 'a', 'type': 'taskuary_data', 'dataset': 'tasks'},
                                              {'key': 'b', 'type': 'taskuary_data', 'dataset': 'nope'}]})
    assert not data['sources']['a']['failed'] and data['sources']['b']['failed']
    assert 'nope' in data['sources']['b']['error']


def test_the_stat_reads_the_range_and_the_where():
    rows = [{'d': _day(1), 's': 'open', 'v': 2}, {'d': _day(3), 's': 'open', 'v': 4}, {'d': _day(40), 's': 'open', 'v': 9},
            {'d': _day(2), 's': 'done', 'v': 1}]
    got = dashboards.where(dashboards.in_range(rows, 'd', 30), {'s': 'open'})
    assert dashboards.aggregate(got) == 2 and dashboards.aggregate(got, 'sum', 'v') == 6 and dashboards.aggregate(got, 'avg', 'v') == 3
    assert dashboards.fmt(12900) == '12.9K' and dashboards.fmt(None) == '-'


# ── a run ────────────────────────────────────────────────────────────────────────────────────────────
def test_a_run_asks_no_ai_keeps_the_rows_and_files_one_row_that_opens_the_dashboard():
    s = _store(); src = _save(s)
    def no_ai(*a, **k): raise AssertionError('a dashboard run never asks a model')
    out = reports.run_one(s, src, no_ai, 'manual')
    assert not out['failed'] and 'Open tasks 2' in out['subject']
    kept = dashboards.last(s, src['SourceId'])
    assert len(kept['sources']['tasks']['rows']) == 3
    funnel._SOURCES['at'] = 0
    items = funnel.pile(s, force=True)['items']
    item = next(i for i in items if i.get('source_id') == src['SourceId'])
    msg = s.get_message(out['message_id'])
    assert msg['Channel'] == 'report' and msg['ConversationId'] == f"report:{src['SourceId']}"
    assert item['kind'] == 'report' and item['dashboard'] is True
    assert not any(i.get('dashboard') for i in items if i is not item)


def test_next_walks_past_a_dashboard_as_it_walks_past_a_report_and_the_next_refresh_brings_it_back():
    """The owner, 2026-10-23: "it shows up on report rail and when you hit next it goes away like report"."""
    from taskuary import concierge
    s = _store(); src = _save(s)
    report = _save(s, {'type': '_none', 'title': 'Plain report'})
    mid = reports.run_one(s, src, None, 'manual')['message_id']
    rmid = s.add_message({'Channel': 'report', 'SourceName': 'Plain report', 'Subject': 'Plain report - 2 rows', 'FromName': 'Plain report',
                          'ConversationId': f"report:{report['SourceId']}", 'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
                          'BodyText': 'x', 'Status': 'feed'})
    funnel._SOURCES['at'] = 0
    keys = lambda: {i['key'] for i in funnel.pile(s, force=True)['items']}
    assert {f'report:{mid}', f'report:{rmid}'} <= keys()
    concierge.move_on(s, f'report:{mid}'); concierge.move_on(s, f'report:{rmid}')
    after = keys()
    assert f'report:{mid}' not in after and f'report:{rmid}' not in after
    again = reports.run_one(s, s.get_source(src['SourceId']), None, 'manual')['message_id']
    assert f'report:{again}' in keys() and f'report:{mid}' not in keys()


def test_a_second_run_retires_the_first_row():
    s = _store(); src = _save(s)
    first = reports.run_one(s, src, None, 'manual')['message_id']
    reports.run_one(s, src, None, 'manual')
    st = s._one('SELECT Status FROM funnel_state WHERE Key=?', (f'report:{first}',))
    assert st and st['Status'] == 'done'


def test_a_run_whose_every_source_failed_is_the_bells_and_keeps_the_last_rows():
    s = _store(); src = _save(s)
    reports.run_one(s, src, None, 'manual')
    broken = {**SPEC, 'sources': [{'key': 'tasks', 'type': 'taskuary_data', 'dataset': 'gone'}]}
    s.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps(broken)}, 't')
    out = reports.run_one(s, s.get_source(src['SourceId']), None, 'manual')
    assert out['failed'] and out['message_id'] is None
    assert len(dashboards.last(s, src['SourceId'])['sources']['tasks']['rows']) == 3


def test_a_dashboard_is_listed_and_restored_as_a_dashboard():
    from taskuary import recentlydeleted
    s = _store(); src = _save(s)
    assert recentlydeleted.source_kind(src) == 'dashboard'


# ── set up with AI ──────────────────────────────────────────────────────────────────────────────────────
def _model(*answers):
    it = iter(answers)
    def fn(system, user, max_tokens=None):
        fn.seen.append(json.loads(user)); return next(it)
    fn.seen = []
    return fn


def test_the_composer_writes_a_spec_from_the_presets_only():
    s = MemoryStore()
    llm = _model(json.dumps({'config': {**SPEC, 'ai_prompt': 'summarise it', 'deliver': {'to': 'x@example.com'}}, 'explain': 'ok', 'confidence': 'high'}))
    out = compose.compose_dashboard(s, 'my open work by kind', llm)
    assert out['config']['type'] == 'dashboard' and 'ai_prompt' not in out['config'] and 'deliver' not in out['config']
    assert 'taskuary_data' in {c['type'] for c in llm.seen[0]['catalog']}
    assert 'dashboard' not in {c['type'] for c in llm.seen[0]['catalog']}


def test_the_composer_hands_back_a_spec_that_cannot_draw_with_the_reason():
    llm = _model(json.dumps({'config': {**SPEC, 'components': [{'kind': 'donut', 'source': 'tasks'}]}}))
    out = compose.compose_dashboard(MemoryStore(), 'a donut', llm)
    assert 'not a preset' in out['error'] and out['config']


def test_a_report_composer_never_offers_a_dashboard_as_a_source():
    assert 'dashboard' not in {c['type'] for c in compose.catalog(MemoryStore())}


def test_no_ai_says_so_with_its_fix():
    out = compose.compose_dashboard(MemoryStore(), 'anything', None)
    assert out['fix']['label']


def test_a_count_of_what_is_true_now_is_not_cut_by_the_range():
    old = (datetime.now() - timedelta(days=40)).strftime('%Y-%m-%d')
    data = {'sources': {'t': {'rows': [{'arrived': old, 'state': 'open'}, {'arrived': _day(1), 'state': 'open'}]}}}
    spec = {'filters': {'range': 7}, 'sources': [{'key': 't', 'date': 'arrived'}],
            'components': [{'kind': 'stat', 'title': 'Arrived', 'source': 't'}, {'kind': 'stat', 'title': 'Open', 'source': 't', 'range': False}]}
    assert dashboards.headline(spec, data) == [('Arrived', '1'), ('Open', '2')]


def test_the_card_under_the_line_keeps_the_dashboard_mark_and_no_other_card_grows_one():
    from taskuary import concierge
    assert concierge.card_for({'kind': 'report', 'dashboard': True})['dashboard'] is True
    assert 'dashboard' not in concierge.card_for({'kind': 'report'})
