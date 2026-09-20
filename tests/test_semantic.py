"""The semantic layer: a number is only trusted once it has reconciled with numbers the owner
already knew. These tests are about the RULE, not about Intacct - `evaluate` is stubbed, because
the point being protected is "an unproved definition refuses to answer", which has nothing to do
with the network.
"""
import json
from datetime import date

import pytest

from taskuary import semantic
from taskuary.store import MemoryStore


@pytest.fixture
def st(): return MemoryStore()


SPEC = {'object': 'GLENTRY', 'value_field': 'AMOUNT', 'aggregate': 'sum',
        'filters': [['LOCATIONID', '=', '{scope}'],
                    ['BATCH_DATE', '>=', '{period_start}'], ['BATCH_DATE', '<=', '{period_end}']]}


def define(st, **over) -> int:
    return st.save_metric({'Name': 'gross_margin', 'Label': 'Gross margin', 'Grain': 'site-month',
                           'Definition': 'revenue less direct cost, as this organisation reports it',
                           'SpecJson': json.dumps({**SPEC, **over})}, 'owner')


def answers(monkeypatch, by_scope: dict):
    """Stub the source: each scope returns whatever this dict says, no network, no credentials."""
    monkeypatch.setattr(semantic, 'evaluate',
                        lambda store, m, scope=None, period=None: {'value': by_scope[scope], 'rows': 1, 'ms': 0,
                                                                   'object': 'GLENTRY', 'filters': [],
                                                                   'scope': scope, 'period': period})


# ── periods: what the owner types vs what Intacct wants ────────────────────────────────
def test_month_becomes_its_first_and_last_day():
    assert semantic.period_range('2026-07') == (date(2026, 7, 1), date(2026, 7, 31))
    assert semantic.period_range('2026-02') == (date(2026, 2, 1), date(2026, 2, 28))


def test_year_and_explicit_window():
    assert semantic.period_range('2026') == (date(2026, 1, 1), date(2026, 12, 31))
    assert semantic.period_range('2026-07-04..2026-07-06') == (date(2026, 7, 4), date(2026, 7, 6))


def test_intacct_gets_us_dates_unless_the_spec_says_iso():
    """The format the API actually accepts, and the one a hand-written query gets wrong first."""
    assert semantic.fmt_date(date(2026, 7, 1)) == '07/01/2026'
    assert semantic.fmt_date(date(2026, 7, 1), 'iso') == '2026-07-01'


def test_placeholders_are_filled_from_the_fixture():
    out = semantic.substitute(SPEC['filters'], 'OAKMONT', '2026-07')
    assert out == [['LOCATIONID', '=', 'OAKMONT'],
                   ['BATCH_DATE', '>=', '07/01/2026'], ['BATCH_DATE', '<=', '07/31/2026']]


# ── the aggregate: Intacct returns every column as text ────────────────────────────────
def test_amounts_arrive_as_text_and_are_still_summed():
    rows = [{'AMOUNT': '1,200.50'}, {'AMOUNT': '$300'}, {'AMOUNT': '(100)'}]
    assert semantic._aggregate(rows, 'AMOUNT', 'sum', 1) == pytest.approx(1400.50)


def test_a_wrong_column_is_an_error_not_a_zero():
    """Averaging an empty column to 0.00 would hide the actual mistake, which is the column name."""
    with pytest.raises(ValueError, match='right column'):
        semantic._aggregate([{'AMOUNT': '5'}], 'AMONUT', 'sum', 1)


def test_no_rows_at_all_is_a_real_zero():
    assert semantic._aggregate([], 'AMOUNT', 'sum', 1) == 0.0


def test_sign_flips_the_credit_convention():
    assert semantic._aggregate([{'AMOUNT': '100'}], 'AMOUNT', 'sum', -1) == -100


# ── tolerance ──────────────────────────────────────────────────────────────────────────
def test_a_fraction_is_a_percentage_and_a_whole_number_is_dollars():
    assert semantic.reconciles(100_500, 100_000, 0.01)          # within 1%
    assert not semantic.reconciles(102_000, 100_000, 0.01)
    assert semantic.reconciles(100_040, 100_000, 50)            # within $50
    assert not semantic.reconciles(100_060, 100_000, 50)


def test_cents_never_fail_a_definition():
    assert semantic.reconciles(1_000_000.004, 1_000_000)


# ── the rule the whole module exists for ───────────────────────────────────────────────
def test_one_matching_case_is_not_a_proof(st, monkeypatch):
    """The owner's own rule: one match is luck, a few is a definition."""
    mid = define(st)
    st.add_fixture(mid, {'Scope': 'OAKMONT', 'Period': '2026-07', 'Expected': 900.0}, 'owner')
    answers(monkeypatch, {'OAKMONT': 900.0})
    r = semantic.check(st, mid)
    assert r['passed'] == 1 and r['status'] == 'draft'
    assert 'needs 3' in r['note']


def test_three_reconciling_cases_certify_it(st, monkeypatch, tmp_path):
    mid = define(st)
    for s, v in (('OAKMONT', 900.0), ('BRIARWOOD', 1200.0), ('LAKESIDE', 450.0)):
        st.add_fixture(mid, {'Scope': s, 'Period': '2026-07', 'Expected': v}, 'owner')
    answers(monkeypatch, {'OAKMONT': 900.0, 'BRIARWOOD': 1200.0, 'LAKESIDE': 450.0})
    r = semantic.check(st, mid)
    assert r['status'] == 'verified' and r['passed'] == 3
    assert st.get_metric(mid)['Skill'] == 'metric-gross-margin'


def test_one_case_drifting_demotes_the_whole_metric(st, monkeypatch):
    """A chart-of-accounts change must surface as a failure, not as a wrong number in a report."""
    mid = define(st)
    for s, v in (('OAKMONT', 900.0), ('BRIARWOOD', 1200.0), ('LAKESIDE', 450.0)):
        st.add_fixture(mid, {'Scope': s, 'Period': '2026-07', 'Expected': v}, 'owner')
    answers(monkeypatch, {'OAKMONT': 900.0, 'BRIARWOOD': 1200.0, 'LAKESIDE': 450.0})
    assert semantic.check(st, mid)['status'] == 'verified'
    answers(monkeypatch, {'OAKMONT': 900.0, 'BRIARWOOD': 1200.0, 'LAKESIDE': 700.0})
    r = semantic.check(st, mid)
    assert r['status'] == 'broken' and '1 of 3 did not reconcile' in r['note']
    assert [x['off'] for x in r['results'] if not x['pass']] == [250.0]


def test_an_unverified_metric_refuses_to_answer(st, monkeypatch):
    """The failure this module exists to stop: a plausible number stated as if it were proved."""
    mid = define(st)
    answers(monkeypatch, {'OAKMONT': 900.0})
    with pytest.raises(ValueError, match='not verified'):
        semantic.resolve(st, 'gross_margin', 'OAKMONT', '2026-07')


def test_an_unknown_metric_says_so(st):
    with pytest.raises(ValueError, match='define it first'):
        semantic.resolve(st, 'nonesuch', 'OAKMONT', '2026-07')


def test_a_verified_metric_answers(st, monkeypatch):
    mid = define(st)
    for s, v in (('OAKMONT', 900.0), ('BRIARWOOD', 1200.0), ('LAKESIDE', 450.0)):
        st.add_fixture(mid, {'Scope': s, 'Period': '2026-07', 'Expected': v}, 'owner')
    answers(monkeypatch, {'OAKMONT': 900.0, 'BRIARWOOD': 1200.0, 'LAKESIDE': 450.0, 'RIVERBEND': 610.0})
    semantic.check(st, mid)
    assert semantic.resolve(st, 'gross_margin', 'RIVERBEND', '2026-07')['value'] == 610.0


def test_editing_the_spec_un_verifies_it(st, monkeypatch):
    """The proof was of the OLD query. Nothing has proved the new one."""
    from taskuary import server
    mid = define(st)
    for s, v in (('OAKMONT', 900.0), ('BRIARWOOD', 1200.0), ('LAKESIDE', 450.0)):
        st.add_fixture(mid, {'Scope': s, 'Period': '2026-07', 'Expected': v}, 'owner')
    answers(monkeypatch, {'OAKMONT': 900.0, 'BRIARWOOD': 1200.0, 'LAKESIDE': 450.0})
    semantic.check(st, mid)
    assert st.get_metric(mid)['Status'] == 'verified'
    monkeypatch.setattr(server, 'store', st)
    server.metric_save(server.MetricBody(Name='gross_margin', Spec={**SPEC, 'sign': -1}))
    assert st.get_metric(mid)['Status'] == 'draft'


# ── what the assistant is told ─────────────────────────────────────────────────────────
def test_nothing_defined_says_nothing(st):
    assert semantic.block(st) == ''


def test_the_block_separates_proved_from_unproved(st, monkeypatch):
    good = define(st)
    for s, v in (('OAKMONT', 900.0), ('BRIARWOOD', 1200.0), ('LAKESIDE', 450.0)):
        st.add_fixture(good, {'Scope': s, 'Period': '2026-07', 'Expected': v}, 'owner')
    answers(monkeypatch, {'OAKMONT': 900.0, 'BRIARWOOD': 1200.0, 'LAKESIDE': 450.0})
    semantic.check(st, good)
    st.save_metric({'Name': 'occupancy', 'SpecJson': json.dumps(SPEC)}, 'owner')
    text = semantic.block(st)
    assert 'gross_margin' in text and 'occupancy (draft)' in text
    assert 'unverified' in text and 'refuse to answer' in text


def test_the_skill_file_carries_the_definition_and_its_proof(st, monkeypatch):
    mid = define(st)
    for s, v in (('OAKMONT', 900.0), ('BRIARWOOD', 1200.0), ('LAKESIDE', 450.0)):
        st.add_fixture(mid, {'Scope': s, 'Period': '2026-07', 'Expected': v, 'Source': 'the monthly package'}, 'owner')
    answers(monkeypatch, {'OAKMONT': 900.0, 'BRIARWOOD': 1200.0, 'LAKESIDE': 450.0})
    semantic.check(st, mid)
    from taskuary import config
    md = (config.home() / 'skills' / 'metric-gross-margin' / 'SKILL.md').read_text(encoding='utf-8')
    assert 'site-month' in md and 'OAKMONT' in md and 'the monthly package' in md
    assert '"object": "GLENTRY"' in md


# ── the HTTP surface the chat actually drives ──────────────────────────────────────────
def test_the_whole_loop_over_the_api(monkeypatch, tmp_path):
    """Define, try, give it known numbers, prove it - the exact sequence the assistant is told
    to walk the owner through, over the endpoints it is told to call."""
    from fastapi.testclient import TestClient
    from taskuary import server
    c = TestClient(server.app)
    monkeypatch.setattr(semantic, 'evaluate',
                        lambda store, m, scope=None, period=None: {'value': {'A': 10.0, 'B': 20.0, 'C': 30.0}[scope],
                                                                   'rows': 1, 'ms': 1, 'object': 'GLENTRY',
                                                                   'filters': [], 'scope': scope, 'period': period})
    m = c.post('/api/semantic/metrics', json={'Name': 'apitest', 'Label': 'API test', 'Grain': 'site-month',
                                              'Definition': 'a number', 'Spec': SPEC}).json()
    mid = m['MetricId']
    assert m['Status'] == 'draft'
    assert c.post(f'/api/semantic/metrics/{mid}/try', json={'scope': 'A', 'period': '2026-07'}).json()['value'] == 10.0
    for s, v in (('A', 10.0), ('B', 20.0), ('C', 30.0)):
        c.post(f'/api/semantic/metrics/{mid}/fixtures', json={'Scope': s, 'Period': '2026-07', 'Expected': v})
    r = c.post(f'/api/semantic/metrics/{mid}/check').json()
    assert r['status'] == 'verified' and r['passed'] == 3
    listed = next(x for x in c.get('/api/semantic/metrics').json()['data'] if x['MetricId'] == mid)
    assert listed['Status'] == 'verified' and len(listed['fixtures']) == 3
    c.delete(f'/api/semantic/metrics/{mid}')
    assert not any(x['MetricId'] == mid for x in c.get('/api/semantic/metrics').json()['data'])


def test_the_metric_tool_refuses_an_unproved_number(monkeypatch):
    """POST /api/tools/run is the road the assistant is given; it must not hand back a guess."""
    from taskuary.reports import REGISTRY
    st = MemoryStore()
    st.save_metric({'Name': 'unproved', 'SpecJson': json.dumps(SPEC)}, 'owner')
    with pytest.raises(ValueError, match='not verified'):
        REGISTRY['metric']({'store': st, 'name': 'unproved', 'scope': 'A', 'period': '2026-07'})


def test_the_metric_tools_are_reachable_on_a_read_only_intacct_card():
    """The card ships at 'read' and the assistant is told to fetch certified numbers through
    /api/tools/run. Unclassified, both types would have needed 'write' (UNKNOWN_NEEDS) and every
    one of those calls would have been refused."""
    from taskuary import scopes
    card = {'Type': 'intacct'}
    assert scopes.scope_of(card) == 'read'
    assert scopes.allows(card, 'metric') and scopes.allows(card, 'metric_check')


# Fail-closed is the right default, but a type nobody classified is a refusal nobody predicted: it
# needs 'write' on its card, so it is simply denied wherever that card ships at 'read'. These seven
# were already unclassified. The test is here so an EIGHTH is a decision somebody made on purpose
# rather than a tool that mysteriously will not run - adding a report type means giving it an
# authority in scopes.ACTIONS, or adding it below and saying why 'write' is right for it.
UNCLASSIFIED = ['agent', 'assistant', 'calendar', 'google_sheets', 'kb_reindex',
                'sharepoint_file', 'sharepoint_list', 'taskuary']   # a Taskuary card reads the store, like the assistant


def test_no_new_report_type_is_left_unclassified():
    from taskuary import scopes
    from taskuary.reports import PLANNED, REGISTRY
    assert sorted(t for t in REGISTRY if t not in PLANNED and t not in scopes.ACTIONS) == UNCLASSIFIED


# ── what reconciling against a real ERP actually needed. Both of these were found by proving
#    definitions against an accounting team's own published figures: without them the numbers
#    were not close, they were meaningless. (Illustrative values below - never real books.)
def test_an_unsigned_amount_column_needs_its_direction_field():
    """GLENTRY.AMOUNT is UNSIGNED - the debit/credit direction lives in TR_TYPE. Summing AMOUNT
    alone adds credits to debits: not wrong by a little, meaningless. Nothing in the field list
    says so, which is why only a reconciliation against known numbers catches it."""
    rows = [{'AMOUNT': '1000.00', 'TR_TYPE': '-1'}, {'AMOUNT': '250.00', 'TR_TYPE': '1'}]
    assert semantic._aggregate(rows, 'AMOUNT', 'sum', 1) == pytest.approx(1250.00)            # nonsense
    assert semantic._aggregate(rows, 'AMOUNT', 'sum', -1, 'TR_TYPE') == pytest.approx(750.00)


def test_a_ratio_divides_two_independent_reads(st, monkeypatch):
    """A rate is one quantity over the units it is spread across, and the two often live in
    different places entirely. A metric that could only sum a single query could not express it."""
    spec = {'object': 'GLENTRY', 'value_field': 'AMOUNT', 'sign': -1,
            'filters': [['ACCOUNTNO', 'in', ['40000']], ['LOCATION', '=', '{scope}']],
            'over': {'object': 'GLENTRY', 'value_field': 'AMOUNT',
                     'filters': [['ACCOUNTNO', 'in', ['90000']], ['LOCATION', '=', '{scope}']]}}
    mid = st.save_metric({'Name': 'unit_rate', 'SpecJson': json.dumps(spec)}, 'owner')
    sides = iter([(80_000.0, 9, 'numerator read', 'intacct'), (100.0, 3, 'denominator read', 'intacct')])
    monkeypatch.setattr(semantic, '_side', lambda store, m, s, scope, period: next(sides))
    out = semantic.evaluate(st, st.get_metric(mid), 'A-SCOPE', '2025-09')
    assert out['value'] == pytest.approx(800.0)                  # amount per unit
    assert out['numerator'] == 80_000.0 and out['denominator'] == 100.0
    assert out['rows'] == 12                                     # both sides counted


def test_a_rate_with_no_units_refuses_rather_than_dividing_by_zero(st, monkeypatch):
    """A scope with no units that period has no rate - saying so beats
    a ZeroDivisionError, and beats inventing 0.00."""
    spec = {'object': 'GLENTRY', 'value_field': 'AMOUNT',
            'over': {'object': 'GLENTRY', 'value_field': 'AMOUNT', 'label': 'the unit count'}}
    mid = st.save_metric({'Name': 'rate_no_units', 'SpecJson': json.dumps(spec)}, 'owner')
    sides = iter([(5000.0, 2, 'numerator read', 'intacct'), (0.0, 0, 'denominator read', 'intacct')])
    monkeypatch.setattr(semantic, '_side', lambda store, m, s, scope, period: next(sides))
    with pytest.raises(ValueError, match='the unit count.*came back zero'):
        semantic.evaluate(st, st.get_metric(mid), 'A-SCOPE', '2025-09')


def test_the_source_is_pluggable_and_named_by_the_spec():
    """The definition and its proof are the point, not which system holds the data. A metric may
    read an ERP object or run SQL against any configured database; adding a source is one
    function that returns rows."""
    assert set(semantic.SOURCES) >= {'intacct', 'mssql', 'database', 'sqlite'}
    assert semantic.DEFAULT_SOURCE in semantic.SOURCES


def test_an_unknown_source_says_which_ones_exist(st):
    mid = st.save_metric({'Name': 'nowhere', 'SpecJson': json.dumps({'source': 'oracle-erp'})}, 'owner')
    with pytest.raises(ValueError, match='unknown source'):
        semantic.evaluate(st, st.get_metric(mid), 'A-SCOPE', '2026-07')


def test_a_sql_spec_gets_its_placeholders_filled():
    """A SQL source has no filter list - the placeholders go straight into the query text, and
    SQL wants ISO dates where an ERP API often insists on MM/DD/YYYY."""
    q = semantic.fill('SELECT x FROM t WHERE site={scope} AND d BETWEEN {period_start} AND {period_end}',
                      'A-SCOPE', '2026-07', 'iso')
    assert q == "SELECT x FROM t WHERE site=A-SCOPE AND d BETWEEN 2026-07-01 AND 2026-07-31"
