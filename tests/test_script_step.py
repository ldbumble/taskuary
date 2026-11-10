"""RULES AS CODE (the owner, 2026-11-10): a rule that is the same on every run is a Python script the owner read and saved, run by plain
code as a report source or a routine step (`python_script`); only the reading of what it prints is a model's.

These pin the two halves. That it RUNS: inline or from the owner's own file, an earlier step's rows on its stdin, rows back from JSON or
CSV, a failing or runaway script as the step failing with its own last words. And that ONLY WHAT WAS SAVED RUNS: no token is ever laid
into the script or its path, the child sees nothing of Taskuary's, a file in Taskuary's own folders is refused, no agent's tool call
reaches it, the composer never runs one to look something up, the Assistant's hands never create or change one, and a repair that
touches the code waits for the owner. Invented people and numbers.
"""
import json, os, sqlite3, tempfile
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import compose, config, flow, reports, scopes, server
from taskuary.store import MemoryStore
from test_flow import no_model, run_task, source

# the rule: a late fee of 2% on what is over thirty days, as the owner would want it computed - the same on every run
LATE_FEE = ('import json, sys\n'
            'rows = [json.loads(l) for l in sys.stdin.read().splitlines() if l.strip()]\n'
            'print(json.dumps([{"invoice": r["invoice"], "fee": round(r["amount"] * 0.02, 2)} for r in rows if r["days"] > 30]))\n')
STEP = {'id': 's2', 'kind': 'source', 'label': 'Late fees', 'type': 'python_script', 'script': LATE_FEE, 'input': '{{s1}}'}


@pytest.fixture
def invoices():
    p = os.path.join(tempfile.mkdtemp(), 'ar.db'); cx = sqlite3.connect(p)
    cx.execute('CREATE TABLE inv (invoice TEXT, amount REAL, days INT)')
    cx.executemany('INSERT INTO inv VALUES (?,?,?)', [('INV-1', 1200, 45), ('INV-2', 300, 10), ('INV-3', 50, 61)])
    cx.commit(); cx.close()
    return {'id': 's1', 'kind': 'source', 'label': 'Open invoices', 'type': 'sqlite', 'db': p, 'query': 'SELECT invoice, amount, days FROM inv'}


def run(**cfg): return reports.run_python_script(cfg)


# ── it runs ────────────────────────────────────────────────────────────────────────
def test_a_script_kept_with_the_routine_runs_and_its_json_or_csv_comes_back_as_rows():
    head, body = run(script='import json\nprint(json.dumps([{"site": "north", "late": 3}, {"site": "south", "late": 0}]))')
    assert head == '2 rows from the script' and [json.loads(l)['site'] for l in body.splitlines()] == ['north', 'south']
    head, body = run(script='print("site;late")\nprint("north;3")')
    assert head == '1 row from the script' and json.loads(body) == {'site': 'north', 'late': '3'}
    assert run(script='print("nothing is late")') == ('1 line from the script', 'nothing is late')


def test_the_owners_own_file_runs_from_where_they_keep_it(tmp_path):
    f = tmp_path / 'late_fees.py'; f.write_text('import sys\nprint("read", len(sys.stdin.read()), "characters")', encoding='utf-8')
    assert run(path=str(f), input='12345') == ('1 line from late_fees.py', 'read 5 characters')
    with pytest.raises(RuntimeError, match='one of them'): run(path=str(f), script='print(1)')
    with pytest.raises(RuntimeError, match='one of them'): run()
    (tmp_path / 'notes.txt').write_text('x', encoding='utf-8')
    with pytest.raises(RuntimeError, match='not a Python script'): run(path=str(tmp_path / 'notes.txt'))


def test_what_an_earlier_step_read_reaches_the_script_as_data_and_the_rule_is_computed_with_no_model(invoices):
    s = MemoryStore()
    src = source(s, [invoices, STEP])
    out = flow.execute(s, src, run_task(s, src), 'manual', llm=no_model)
    [a, b] = out['steps']
    assert (a['status'], b['status'], b['rows']) == ('ok', 'ok', 2), out
    assert [json.loads(l) for l in b['body'].splitlines()] == [{'invoice': 'INV-1', 'fee': 24.0}, {'invoice': 'INV-3', 'fee': 1.0}]
    assert 'no AI used' in out['summary']


def test_a_script_that_fails_or_runs_on_fails_the_step_with_its_own_last_words(invoices):
    with pytest.raises(RuntimeError, match=r'exit code 3: .*no amount column'):
        run(script='import sys\nsys.stderr.write("Traceback...\\nKeyError: no amount column")\nsys.exit(3)')
    with pytest.raises(RuntimeError, match='ran past its 1 second and was stopped'): run(script='import time\ntime.sleep(60)', timeout=1)
    s = MemoryStore()
    src = source(s, [invoices, {**STEP, 'script': 'raise SystemExit("the export has no days column")'}])
    out = flow.execute(s, src, run_task(s, src), 'manual', llm=no_model)
    assert out['steps'][-1]['status'] == 'failed' and 'the export has no days column' in out['steps'][-1]['error']


# ── only what was saved runs ───────────────────────────────────────────────────────────────
@pytest.mark.parametrize('key,val', [('script', 'print("{{s1}}")'), ('path', 'C:/scripts/{{s1.head}}.py'), ('script', 'print("{{inputs.month}}")')])
def test_nothing_is_ever_pasted_into_the_script_or_its_path(invoices, key, val):
    bad = {k: v for k, v in STEP.items() if k != 'script'} | {key: val}
    ok, why = flow.validate(MemoryStore(), [invoices, bad])
    assert not ok and 'run exactly as saved' in why and '`input`' in why
    # ...and one saved before the rule existed is refused at the run, never rendered
    with pytest.raises(RuntimeError, match='run exactly as saved'):
        flow._source(MemoryStore(), bad, flow.context({}), None, None, False, [], 't')
    assert flow.validate(MemoryStore(), [invoices, STEP]) == (True, '')


def test_the_script_sees_nothing_of_taskuarys_and_runs_in_a_folder_of_its_own():
    with mock.patch.dict(os.environ, {'TASKUARY_HOME': str(config.home()), 'TASKUARY_TOKEN': 'not-for-a-script', 'TQ_WINRM_SCRIPT': 'x'}):
        _h, body = run(script='import os, json\nprint(json.dumps([{"mine": sorted(k for k in os.environ if k.startswith(("TASKUARY", "TQ_"))), "cwd": os.getcwd()}]))')
    row = json.loads(body)
    assert row['mine'] == [] and 'taskuary-script-' in row['cwd']
    assert str(config.home().resolve()) not in row['cwd'] and not os.path.exists(row['cwd']), 'its folder is gone with it'


def test_a_file_in_taskuarys_own_folders_is_never_run():
    "Mail's attachments and every agent's scratch land under the home: a .py there is not the owner's own script."
    d = config.home() / 'attachments'; d.mkdir(parents=True, exist_ok=True)
    f = d / 'invoice_helper.py'; f.write_text('print("ran")', encoding='utf-8')
    try:
        with pytest.raises(RuntimeError, match="Taskuary's own folders"): run(path=str(f))
        with pytest.raises(RuntimeError, match="Taskuary's own folders"): run(path=str(os.path.join(os.path.dirname(reports.__file__), 'reports.py')))
    finally: f.unlink()


def test_it_is_the_sharpest_level_and_no_agents_tool_call_reaches_it():
    assert scopes.needs('python_script') == 'admin' and flow.writes('python_script') and not scopes.reaches('python_script')
    s = MemoryStore()
    with mock.patch.object(server, 'store', s):
        r = TestClient(server.app).post('/api/tools/run', json={'type': 'python_script', 'script': 'print(1)'})
    assert r.status_code == 403 and 'no connection card' in r.json()['detail']
    assert server.guard.classify('POST', '/api/sources')[0] == 'deny' and server.guard.classify('POST', '/api/workflows/step-test')[0] == 'deny'
    assert server.guard.classify('POST', '/api/reports/preview')[0] == 'deny'


def test_the_composer_knows_when_a_script_fits_and_never_runs_one_to_look_something_up():
    row = next(c for c in compose.catalog(MemoryStore()) if c['type'] == 'python_script')
    assert row['ready'] and row['connection'] is None and 'RULE that is the same every run' in row['takes']
    with mock.patch.object(reports, 'run_python_script', side_effect=AssertionError('a look-up never runs code')):
        said = compose._peek(MemoryStore(), {'type': 'python_script', 'script': 'print(open("secrets").read())'})
    assert 'never run as a look-up' in said
    assert compose.validate_source(MemoryStore(), {'type': 'python_script'})[0] is False
    assert compose.validate_source(MemoryStore(), {'type': 'python_script', 'path': 'C:/scripts/late_fees.py'}) == (True, '')


def test_the_assistants_hands_never_create_or_change_a_script():
    s = MemoryStore()
    with mock.patch.object(server, 'store', s):
        with pytest.raises(RuntimeError, match='saved only by the owner'):
            server._run_kind({'kind': 'report.create', 'target': 0, 'params': {'config': {'type': 'python_script', 'title': 'Late fees', 'script': LATE_FEE}}}, None)
        sid = s.save_source({'Channel': 'report', 'Address': 'Late fees', 'Active': 1, 'Owner': 'owner',
                             'ConfigJson': json.dumps({'type': 'python_script', 'title': 'Late fees', 'script': LATE_FEE})}, 'owner')
        with pytest.raises(server.HTTPException) as e:
            server._run_kind({'kind': 'report.edit', 'target': sid, 'params': {'config': {'script': 'import shutil'}}}, None)
        assert 'saved only by the owner' in e.value.detail and json.loads(s.get_source(sid)['ConfigJson'])['script'] == LATE_FEE
        # ...what is not the code is still theirs to change
        assert server._run_kind({'kind': 'report.edit', 'target': sid, 'params': {'config': {'daily_at': '07:00'}}}, None)['changed'] == ['daily_at']


def test_a_repair_that_touches_the_code_always_waits_for_the_owner(invoices):
    old = [invoices, STEP]
    assert flow.targets([invoices, {**STEP, 'input': '{{s1.rows}}', 'timeout': 300}]) == flow.targets(old), 'not the code: no new place'
    for new in ({**STEP, 'script': LATE_FEE.replace('0.02', '0.2')}, {k: v for k, v in STEP.items() if k != 'script'} | {'path': 'C:/scripts/other.py'}):
        wider = flow.targets([invoices, new]) - flow.targets(old)
        assert any(t.startswith('code:python_script:') for t in wider), wider


# ── a script written on a job, kept as a routine: the agent proposes, the owner's press saves ───────────────────────────────
def task(s, **kw): return s.create_task({'Title': 'Work out the late fees for October', 'Kind': 'general', 'Status': 'open', **kw}, 'owner')
def routines(s): return [x for x in s.list_sources(active_only=False) if x.get('Channel') == 'report' and x.get('Address') == 'Late fees']
ASK = {'action': 'save_routine', 'title': 'Late fees', 'script': LATE_FEE, 'prompt': 'Say which invoices carry a fee and the total.',
       'daily_at': '07:00', 'why': 'the same rule every month', 'reads': {'type': 'local_file', 'path': 'C:/exports/ar-*.csv'}}


@pytest.mark.parametrize('bad,says', [({'script': ''}, 'save_routine needs script'), ({'script': 'print("{{inputs.month}}")'}, 'run exactly as saved'),
                                      ({'reads': {'type': 'python_script', 'script': 'print(1)'}}, 'never a write'),
                                      ({'reads': {'type': 'smb_write', 'path': 'x'}}, 'never a write'), ({'daily_at': '7am'}, 'not a time')])
def test_a_routine_that_would_not_hold_is_refused_at_the_door(bad, says):
    from taskuary import proposals
    s = MemoryStore(); tid = task(s); refused = []
    assert proposals.queue(s, tid, {**ASK, **bad}, refused=refused) is None
    assert says in refused[0] and not routines(s) and not s.pending_review(tid)


def test_the_owners_press_saves_the_routine_and_nothing_exists_before_it():
    from taskuary import proposals
    s = MemoryStore(); tid = task(s)
    q = proposals.queue(s, tid, dict(ASK))
    rv = s.get_review(q['reviewId'])
    assert (rv['Kind'], rv['Status']) == ('action', 'pending') and 'save a script as the routine "Late fees", to run daily 07:00' in rv['Reason']
    assert json.loads(rv['DraftText'])['script'] == LATE_FEE, 'the card holds the script whole'
    assert not routines(s), 'nothing is saved, and nothing has run, before the press'
    with mock.patch.object(reports, 'run_python_script', side_effect=AssertionError('the press saves - it runs nothing')):
        out = proposals.execute(s, rv)
    [src] = routines(s); cfg = json.loads(src['ConfigJson'])
    assert out['source'] == src['SourceId'] and src['Active'] and cfg['daily_at'] == '07:00' and flow.validate(s, cfg['flow']) == (True, '')
    assert [(x['kind'], x.get('type')) for x in cfg['flow']] == [('source', 'local_file'), ('source', 'python_script'), ('ai', None)]
    assert cfg['flow'][1]['script'] == LATE_FEE and cfg['flow'][1]['input'] == '{{s1}}' and cfg['flow'][2]['prompt'].endswith('{{s2}}')
    # ...and a second press makes no second routine
    with pytest.raises(RuntimeError, match='already exists'): proposals.execute(s, rv)
    assert len(routines(s)) == 1


def test_a_script_from_a_strangers_task_is_never_offered_and_one_with_no_clock_runs_on_demand():
    from taskuary import origin, proposals
    s = MemoryStore(); tid = task(s); refused = []
    with mock.patch.object(origin, 'of_task', return_value=('stranger', 'never written to them')):
        assert proposals.queue(s, tid, dict(ASK), refused=refused) is None and 'stranger' in refused[0]
    q = proposals.queue(s, tid, {k: v for k, v in ASK.items() if k not in ('daily_at', 'reads', 'prompt')})
    assert 'to run when you run it' in s.get_review(q['reviewId'])['Reason']
    proposals.execute(s, s.get_review(q['reviewId']))
    cfg = json.loads(routines(s)[0]['ConfigJson'])
    assert [x['type'] for x in cfg['flow']] == ['python_script'] and not reports.is_due(cfg, None)


def test_the_agent_is_told_the_road_and_never_to_ask_it_in_prose():
    from taskuary import agenttools, general
    assert 'save_routine {title, script' in str(agenttools.TOOLS['propose'])
    assert '"action": "save_routine"' in general._ACTION and 'never for a one-off' in general._ACTION
