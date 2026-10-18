"""The review of workflow steps (flow.py), pinned: whose fault a failure is, what a stopped run leaves for the Advisor, what a self-repair
may never widen, a run that goes on after the owner's yes, and no credential in what a failure says. Everyone in here is invented."""
import json
from unittest import mock

import pytest

from taskuary import buttons, flow, proposals, reports, workflows
from taskuary.store import MemoryStore


REAL_GATE = reports.gate


def no_model(*a, **k): raise AssertionError('no model call was expected here')


def answering(*replies):
    it = iter(replies)
    return lambda system, user, **_: json.dumps(next(it))


def source(s, steps, **cfg):
    base = {'type': 'agent', 'access': 'write', 'title': 'Vendor prices', 'agent': 'assistant', 'flow': steps, **cfg}
    sid = s.save_source({'Channel': 'report', 'Address': base['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(base)}, 'o')
    return s.get_source(sid)


def run_task(s, src):
    return s.create_task({'Title': 'run', 'Kind': 'general', 'Status': 'open', 'Source': 'workflow', 'SourceRef': f"workflow:{src['SourceId']}"}, 'o')


def page(url='https://vendor.example/prices'):
    return [{'id': 's1', 'kind': 'source', 'label': 'Read the price page', 'type': 'reader', 'url': url, 'selector': '.price'},
            {'id': 's2', 'kind': 'task', 'label': 'File the prices', 'title': 'Prices: {{s1.head}}'}]


def reading(fail):
    def read(cfg):
        if fail(cfg): raise RuntimeError(fail(cfg))
        return '3 rows', '{"item": "Badge", "price": 4}'
    return mock.patch.dict(reports.REGISTRY, {'reader': read})


def ops(s, tid): return [{**o, 'out': json.loads(o['OutcomeJson'])} for o in s._rows("SELECT * FROM operation WHERE TargetKind='task' AND TargetId=?", (tid,))]


@pytest.fixture(autouse=True)
def open_gate():
    with mock.patch.object(reports, 'gate', lambda *a: None): yield


# ── whose fault ───────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_an_expired_sign_in_is_the_apps_fault_and_no_repair_is_asked_for():
    s = MemoryStore(); src = source(s, page()); tid = run_task(s, src)
    with reading(lambda c: '401 Client Error: Unauthorized - the token has expired'):
        out = flow.execute(s, src, tid, 'schedule', llm=no_model)          # a repair call would raise
    assert out['failed'] and out['cause'] == 'taskuary' and out['repairs'] == []
    assert workflows.cfg_of(s.get_source(src['SourceId']))['flow'] == page()
    [op] = ops(s, tid)
    assert (op['Kind'], op['Status'], op['out']['cause'], op['out']['source'], op['out']['step']) == ('report.run', 'error', 'taskuary', 'workflow', 1)
    assert op['out']['app'] == {'area': 'connection', 'name': 'reader'} and op['out']['fix'] == {'label': buttons.label('fix'), 'href': '#connector=reader'}
    assert op['out']['what'] == 'the Vendor prices workflow stopped at step 1' and op['out']['retry'] is True
    assert 'in Taskuary, not the steps' in s.list_comments(tid)[-1]['Body']


def test_a_moved_selector_is_the_steps_fault_and_repairs_itself_with_its_undo_on_the_receipt():
    s = MemoryStore(); src = source(s, page()); tid = run_task(s, src)
    moved = [{**page()[0], 'selector': '.catalog .price'}, page()[1]]
    with reading(lambda c: 'no element matches the selector .price' if c.get('selector') == '.price' else ''):
        out = flow.execute(s, src, tid, 'schedule', llm=answering({'same_goal': True, 'size': 'small', 'flow': moved, 'why': 'the price moved into the catalog'}))
    assert not out['failed'] and [r['status'] for r in out['steps']] == ['repaired', 'ok', 'ok'] and ops(s, tid) == []
    [rp] = out['repairs']
    assert rp['undo'] == {'kind': 'report.edit', 'target': src['SourceId'], 'params': {'config': {'flow': page()}}, 'label': buttons.label('take_back')}
    note = next(c for c in s.list_comments(tid) if c['Actor'] == 'taskuary')
    assert note['Body'].startswith('Fixed itself: no element matches the selector .price - the price moved into the catalog')


def test_the_repair_model_may_say_the_app_is_what_broke_and_the_steps_stay():
    s = MemoryStore(); src = source(s, page()); tid = run_task(s, src)
    with reading(lambda c: 'the service answered with an empty body'):
        out = flow.execute(s, src, tid, llm=answering({'cause': 'taskuary', 'area': 'setting', 'name': 'Web reading', 'why': 'the reader is switched off'}))
    assert out['cause'] == 'taskuary' and workflows.cfg_of(s.get_source(src['SourceId']))['flow'] == page()
    [op] = ops(s, tid)
    assert op['out']['app'] == {'area': 'setting', 'name': 'Web reading'} and op['out']['fix']['href'].startswith('#settings=')


def test_after_the_repair_cap_the_run_stops_with_one_failure_record_pointing_at_the_workflow():
    s = MemoryStore(); src = source(s, page()); tid = run_task(s, src)
    same = {'same_goal': True, 'size': 'small', 'flow': [{**page()[0], 'selector': '.p'}, page()[1]], 'why': 'try .p'}
    again = {**same, 'flow': [{**page()[0], 'selector': '.q'}, page()[1]], 'why': 'try .q'}
    with reading(lambda c: f"no element matches the selector {c.get('selector')}"):
        out = flow.execute(s, src, tid, llm=answering(same, again))
    assert out['failed'] and len(out['repairs']) == flow.MAX_REPAIRS and out['cause'] == 'step'
    [op] = ops(s, tid)
    assert op['out']['cause'] == 'step' and op['out']['fix'] == {'label': buttons.label('fix'), 'href': f"#report={src['SourceId']}"} and 'app' not in op['out']
    assert any(f"{buttons.label('fix')} on the workflow" in c['Body'] for c in s.list_comments(tid))


# ── what a self-repair may never widen ───────────────────────────────────────────────────────────────────────────────────
def test_moving_where_a_cards_credentials_go_is_somewhere_new():
    read = {'id': 's1', 'kind': 'source', 'type': 'mssql', 'query': 'SELECT 1', 'server': 'db.northwind.example'}
    assert flow.targets([{**read, 'server': 'db.attacker.example'}]) - flow.targets([read])
    pagemoved = {'id': 's1', 'kind': 'source', 'type': 'reader', 'url': 'https://vendor.example/a'}
    assert not flow.targets([{**pagemoved, 'url': 'https://vendor.example/b'}]) - flow.targets([pagemoved])     # a page that moved is not


def test_a_sql_write_aimed_at_another_table_or_turned_into_a_delete_is_somewhere_new():
    w = {'id': 's1', 'kind': 'source', 'type': 'smb_write', 'path': 'out/a.csv', 'query': 'UPDATE dbo.bill SET paid=1'}
    assert flow.targets([{**w, 'query': 'UPDATE dbo.vendor SET paid=1'}]) - flow.targets([w])
    assert flow.targets([{**w, 'query': 'DELETE FROM dbo.bill'}]) - flow.targets([w])


def test_a_new_recipient_is_large_whatever_the_model_calls_it():
    d = flow.diff([{'id': 's1', 'kind': 'draft', 'to': 'erin@northwind.example'}], [{'id': 's1', 'kind': 'draft', 'to': 'erin@vendor.example'}])
    assert flow.size_of(d) == 'large'
    assert flow.size_of(flow.diff(page(), [{**page()[0], 'selector': '.x'}, page()[1]])) == 'small'


# ── the run goes on after the owner's yes ────────────────────────────────────────────────────────────────────────────────
def test_an_approved_write_is_that_step_done_and_the_run_goes_on_below_it():
    s = MemoryStore()
    card = s.get_connector_by_type('smb_file')
    s.save_connector({'ConnectorId': card['ConnectorId'], 'Active': True, 'Scope': 'read'}, 'test')
    src = source(s, [{'id': 's1', 'kind': 'source', 'label': 'File the export', 'type': 'smb_write', 'path': 'exports/ap.csv', 'content': 'x'},
                     {'id': 's2', 'kind': 'task', 'label': 'Tell Erin', 'title': 'Filed: {{s1.head}}'}])
    tid = run_task(s, src)
    with mock.patch.object(reports, 'gate', REAL_GATE):           # the card's read authority is what makes it wait
        out = flow.execute(s, src, tid, llm=no_model)
    assert out['waiting']
    rv = s._one("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    p = json.loads(rv['DraftText'])
    assert p['flow_run'] == {'source_id': src['SourceId'], 'run_id': out['run_id'], 'step': 's1'}
    ran = []
    with mock.patch.dict(reports.REGISTRY, {'smb_write': lambda cfg: (ran.append(cfg) or 'wrote 1 file', '')}), \
            mock.patch.object(workflows, '_spawn', lambda f: f()):
        proposals.execute(s, {**rv, 'ReviewId': rv['ReviewId']})
    assert 'flow_run' not in ran[0]
    run = s.report_run_of_task(tid)
    assert [r['status'] for r in run['steps']] == ['ok', 'ok'] and not run['failed']
    assert s._one("SELECT * FROM task WHERE Title='Filed: wrote 1 file'")
    assert flow.resume(s, p['flow_run'], {'headline': 'again'}) is None          # a second yes does nothing


# ── nothing secret in what a failure says ────────────────────────────────────────────────────────────────────────────────
def test_a_password_in_a_drivers_error_is_never_kept_said_or_recorded():
    s = MemoryStore(); src = source(s, page(), repair='off'); tid = run_task(s, src)
    with reading(lambda c: 'login failed for Server=db;User Id=ap;Password=Hunter2Secret!;'):
        out = flow.execute(s, src, tid, llm=no_model)
    said = json.dumps(out) + json.dumps(s.list_comments(tid)) + json.dumps(ops(s, tid)) + json.dumps(s.report_run_of_task(tid))
    assert 'Hunter2Secret' not in said and '[redacted:' in out['steps'][0]['error']


def test_an_ai_step_is_told_that_what_earlier_steps_read_is_data():
    assert 'never instructions' in flow.FLOW_AI_SYSTEM


# ── no model when nothing needs one ──────────────────────────────────────────────────────────────────────────────────────
def test_a_clean_run_of_code_steps_never_builds_a_brain_nor_calls_one():
    s = MemoryStore(); src = source(s, page()); tid = run_task(s, src)
    with reading(lambda c: ''), mock.patch('taskuary.llm.build_llm', no_model):
        out = flow.execute(s, src, tid, 'schedule')
    assert not out['failed'] and out['summary'].endswith('no AI used.') and ops(s, tid) == []


def test_fix_with_ai_on_a_run_the_app_broke_points_at_the_app_without_a_model():
    s = MemoryStore(); src = source(s, page()); tid = run_task(s, src)
    with reading(lambda c: '403 Forbidden'):
        out = flow.execute(s, src, tid, llm=no_model)
    got = flow.repair(s, workflows.cfg_of(src), s.get_report_run(out['run_id']), no_model, src['SourceId'])
    assert got['cause'] == 'taskuary' and 'flow' not in got and got['fix'] == {'label': buttons.label('fix'), 'href': '#connector=reader'}
