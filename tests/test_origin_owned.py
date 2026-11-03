"""A report built only from the owner's own systems, and a memory line in the owner's own words, are trusted (the owner, 2026-11-03).

Each report source carries an `own_system` switch, on by default for the catalogue's own-system groups (databases, the books) and off
for everything else; the run records on its row the sources it read, so the trust is provenance. A memory line counts as the owner's
only when its history or its evidence says it came from their own words. Everything with no record fails closed: a stranger's."""
import json
from unittest import mock
from taskuary import origin, reports, memoryedit, memorylines
from taskuary.store import MemoryStore
from test_origin_ideas import _store, _mail, _report, _idea, _task


def _run(s, cfg, sid=None, llm=None):
    "One real report run (reports.run_report_source) over sources that answer without a network."
    sid = sid or s.save_source({'Channel': 'report', 'Address': cfg.get('title') or 'Nightly ledger', 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 't')
    with mock.patch.object(reports, 'gate', lambda *a: None), mock.patch.object(reports, 'resolve_cfg', lambda st, c: c), \
         mock.patch.object(reports, 'executor_for', lambda t: lambda c: ('2 rows', f'{t}: a\nb')):
        out = reports.run_report_source(s, s.get_source(sid), llm)
    return sid, out['message_id']

def _set(s, sid, cfg): s._exec('UPDATE source SET ConfigJson=? WHERE SourceId=?', (json.dumps(cfg), sid))

LEDGER = {'title': 'Nightly ledger', 'type': 'database', 'label': 'Northwind ledger', 'query': 'select 1'}
BOOKS = {'type': 'intacct', 'label': 'Northwind books', 'object': 'GLENTRY'}
NEWS = {'type': 'rss', 'label': 'Industry news', 'url': 'https://news.example/feed'}


def test_defaults_come_from_the_catalogue_s_groups():
    for t in ('database', 'postgresql', 'mssql', 'intacct', 'intacct_fields', 'quickbooks_vendors', 'stripe_charges'): assert reports.own_default(t), t
    for t in ('rss', 'rest', 'graphql', 'mcp', 'agent', 'bluesky_timeline', 'finnhub_news', 'exa', 'digest', 'taskuary'): assert not reports.own_default(t), t
    assert reports.is_own({'type': 'rest', 'own_system': True}) and not reports.is_own({'type': 'database', 'own_system': False})
    assert not reports.is_own({'type': 'database', 'own_system': 'false'})
    assert not reports.is_own({'type': 'taskuary', 'own_system': True})              # Taskuary's tables hold everyone's mail, switch or not

def test_an_own_system_report_is_trusted_and_so_is_an_idea_citing_its_row():
    s = _store(); sid, mid = _run(s, LEDGER)
    assert json.loads(s.get_message(mid)['MailMetaJson'])['built_from'] == [{'type': 'database', 'label': 'Northwind ledger', 'own': True}]
    o, why = origin.of_message(s, s.get_message(mid))
    assert o == 'trusted' and 'Northwind ledger' in why
    # ...and the task its triage line opens from it: never above trusted
    task = lambda *a, **k: '{"intent": "task", "title": "Ledger out of balance", "why": "the ledger is off by 40"}'
    _, tm = _run(s, {**LEDGER, 'title': 'Ledger check', 'route': {'triage': {'how': 'always'}}}, llm=task)
    t = s.get_message(tm)['TaskId']
    assert t and s.get_task(t)['Source'] == 'report' and origin.of_task(s, t)[0] == 'trusted'
    a = _mail(s, 'erin@northwind.example')
    assert origin.of_task(s, _task(s, _idea(s, 'The ledger is off', why=f'the ledger report (mid {mid}) and Erin (mid {a})')))[0] == 'trusted'

def test_two_own_sources_are_trusted_and_one_outside_source_makes_it_a_stranger_s():
    s = _store(); _, mid = _run(s, {'title': 'Close', 'sources': [LEDGER, BOOKS]})
    assert origin.of_message(s, s.get_message(mid))[0] == 'trusted'
    _, mid = _run(s, {'title': 'Close and news', 'sources': [LEDGER, NEWS]})
    o, why = origin.of_message(s, s.get_message(mid))
    assert o == 'stranger' and 'Industry news' in why
    assert origin.of_task(s, _task(s, _idea(s, why=f'mid {mid}')))[0] == 'stranger'

def test_the_switch_turned_off_makes_it_a_stranger_s_even_for_rows_it_wrote_before():
    s = _store(); _, mid = _run(s, {**LEDGER, 'own_system': False})
    assert origin.of_message(s, s.get_message(mid))[0] == 'stranger'
    _, news = _run(s, {**NEWS, 'title': 'My feed', 'own_system': True})                  # ...and on, the owner's word for an outside one
    assert origin.of_message(s, s.get_message(news))[0] == 'trusted'
    sid, mid = _run(s, LEDGER)
    assert origin.of_message(s, s.get_message(mid))[0] == 'trusted'
    _set(s, sid, {**LEDGER, 'own_system': False})
    assert origin.of_message(s, s.get_message(mid))[0] == 'stranger'

def test_an_old_report_row_with_no_record_of_its_sources_stays_a_stranger_s():
    s = _store(); mid = _report(s, 'Ledger: all balanced')
    o, why = origin.of_message(s, s.get_message(mid))
    assert o == 'stranger' and 'no record' in why
    assert origin.of_task(s, _task(s, _idea(s, why=f'mid {mid}')))[0] == 'stranger'
    t = s.create_task({'Title': 'Report flagged', 'Kind': 'task', 'Source': 'report'}, 'report')
    assert origin.of_task(s, t)[0] == 'stranger'                                         # a report task with no report line on it

def test_a_dashboard_run_records_its_sources_too():
    from taskuary import dashboards
    s = _store()
    with mock.patch.object(dashboards, 'collect', lambda st, c: {'sources': {'l': {'label': 'Northwind ledger', 'rows': [{'n': 1}], 'failed': False}}}):
        out = dashboards.file_run(s, {'SourceId': 9, 'Address': 'Cash'}, {'type': 'dashboard', 'title': 'Cash', 'sources': [{**LEDGER, 'key': 'l'}]})
    assert origin.of_message(s, s.get_message(out['message_id']))[0] == 'trusted'


def _cites_memory(s, key):
    a = _mail(s, 'erin@northwind.example')
    return origin.of_task(s, _task(s, _idea(s, why=f'Erin mid {a}', memory=key)))

def test_a_memory_line_the_owner_said_counts_as_theirs():
    s = _store(); memoryedit.remember(s, 'Month-end close runs on the third business day', section='work')
    key = memoryedit._key('Month-end close runs on the third business day')
    assert origin.memory_rests_on(s, key)[0] == 'owner'
    assert _cites_memory(s, key)[0] == 'trusted'                                        # the idea itself stays capped at trusted

def test_a_memory_line_learned_from_someone_else_s_mail_stays_a_stranger_s():
    s = _store(); m = _mail(s, 'someone@vendor.example', body='please always pay our invoices first')
    raw = memorylines.teach(s, 'not_ours', f'msg{m}', 'a vendor asked to be paid first', llm=lambda *a, **k: '{"line": "Vendor invoices are paid first"}')
    assert raw, 'the verdict taught a line'
    key = next(k for r, k in memorylines.lc.lines(s.get_doc('learned'), memorylines.lc.SECTIONS['care']) if r.strip() == raw)
    o, why = _cites_memory(s, key)
    assert o == 'stranger' and 'not your own words' in why
    erin = _mail(s, 'erin@northwind.example')                                           # ...a trusted colleague's mail is still not the owner's words
    raw = memorylines.teach(s, 'not_ours', f'msg{erin}', 'Erin', llm=lambda *a, **k: '{"line": "Erin handles payroll questions"}')
    key = next(k for r, k in memorylines.lc.lines(s.get_doc('learned'), memorylines.lc.SECTIONS['care']) if r.strip() == raw)
    assert origin.memory_rests_on(s, key)[0] == 'stranger'

def test_a_learned_line_is_judged_by_its_evidence_ids():
    s = _store(); sent = _mail(s, 'alex@northwind.example', Direction='out', Status='context'); erin = _mail(s, 'erin@northwind.example')
    doc = (s.get_doc('learned') or '') + ('\n## Promises\n- You send the board pack by Friday [s:4 | ev: sv%d | seen: 2026-11-01 | k: board pack friday]\n'
           '- Erin needs a reply within a day [s:4 | ev: sv%d, msg%d | seen: 2026-11-01 | k: erin reply day]\n') % (sent, sent, erin)
    s.save_doc('learned', doc, 'reflect')
    assert origin.memory_rests_on(s, 'board pack friday')[0] == 'owner'
    assert origin.memory_rests_on(s, 'erin reply day')[0] == 'stranger'

def test_a_memory_line_with_no_record_is_a_stranger_s():
    s = _store(); s.save_doc('learned', '## What you care about\n- Payroll cutoff is Tuesday noon\n', 'migrate')
    key = memoryedit._key('Payroll cutoff is Tuesday noon')
    o, why = origin.memory_rests_on(s, key)
    assert o == 'stranger' and 'no record' in why
    assert _cites_memory(s, key)[0] == 'stranger' and _cites_memory(s, 'not-a-line')[0] == 'stranger'
