"""A workflow as steps (flow.py): code runs every step it can, a model only where a step says AI.

The owner, 2026-10-18: "it just runs the same prompt over and over even if part of it should be deterministic ... at least we will
use ai the least". These pin the runner: a workflow with no AI step runs with no model at all; an `ai` step is one call answering in
the shape asked; only_if is the branch without a model; a failed step stops the run and says which; a write below the card's
authority waits on the owner's yes; a step test never writes; a repair is a proposal the owner keeps or not; and a workflow saved
before any of this still runs as the one agent prompt it always was. Everyone in here is invented.
"""
import json, os, sqlite3, tempfile
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import compose, flow, ingest, proposals, server, workflows
from taskuary.store import MemoryStore


def no_model(*a, **k): raise AssertionError('a step with no AI in it never calls a model')


def answering(*replies, seen=None):
    """A fake brain that answers in order - and records what it was asked."""
    it = iter(replies)
    def llm(system, user, **_):
        if seen is not None: seen.append({'system': system, 'user': user})
        r = next(it)
        return r if isinstance(r, str) else json.dumps(r)
    return llm


@pytest.fixture
def db():
    """A small vendor-bill table, as a sqlite file - the deterministic read every test below can use."""
    d = tempfile.mkdtemp(); p = os.path.join(d, 'ap.db')
    cx = sqlite3.connect(p)
    cx.execute('CREATE TABLE bill (vendor TEXT, amount REAL, invoice TEXT)')
    cx.executemany('INSERT INTO bill VALUES (?,?,?)', [('Payworth', 1200, 'INV-1'), ('Payworth', 1200, 'INV-1'), ('Trainly', 80, 'T-9')])
    cx.commit(); cx.close()
    return p


def source(s, steps, **cfg):
    base = {'type': 'agent', 'access': 'write', 'title': 'Duplicate bill check', 'agent': 'assistant', 'flow': steps, **cfg}
    sid = s.save_source({'Channel': 'report', 'Address': base['title'], 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(base)}, 'o')
    return s.get_source(sid)


def run_task(s, src):
    return s.create_task({'Title': 'run', 'Kind': 'general', 'Status': 'open', 'Source': 'workflow', 'SourceRef': f"workflow:{src['SourceId']}"}, 'o')


def read_dupes(db): return {'id': 's1', 'kind': 'source', 'label': 'Read AP bills', 'type': 'sqlite', 'db': db,
                            'query': 'SELECT vendor, invoice, COUNT(*) n FROM bill GROUP BY vendor, invoice HAVING n > 1'}


# ── back-compat ─────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_workflow_with_no_steps_is_the_one_agent_prompt_it_always_was():
    cfg = {'type': 'agent', 'access': 'write', 'title': 'Vendor sweep', 'prompt': 'Post the bills Erin Blake approved.', 'skill': 'ap-sweep'}
    assert flow.steps_of(cfg) == [{'id': 's1', 'kind': 'agent', 'label': 'Agent works it', 'prompt': cfg['prompt'], 'skill': 'ap-sweep'}]
    assert not flow.is_flow(cfg) and not flow.is_flow({**cfg, 'flow': [{'id': 's1', 'kind': 'agent', 'prompt': 'x'}]})
    assert flow.is_flow({**cfg, 'flow': [{'id': 's1', 'kind': 'task', 'title': 'x'}]})


def test_a_legacy_workflow_still_goes_straight_to_the_agent_with_its_brief():
    s = MemoryStore()
    src = source(s, None, prompt='Post the bills Erin Blake approved.')
    with mock.patch.object(workflows, '_spawn', lambda fn: fn()), mock.patch.object(ingest, '_auto_general') as gen, \
            mock.patch.object(flow, 'execute', side_effect=AssertionError('a prompt-only workflow never runs as steps')):
        out = workflows.run(s, src, trigger='manual')
    tid, brief = gen.call_args[0][1], gen.call_args[0][2]
    assert tid == out['task_id'] and not out['steps'] and 'OBJECTIVE: Post the bills Erin Blake approved.' in brief
    assert s.get_task(tid)['Summary'] == brief


def test_a_lone_saved_agent_step_reads_its_words_from_the_step():
    s = MemoryStore()
    src = source(s, [{'id': 's1', 'kind': 'agent', 'label': 'Agent', 'prompt': 'Reconcile the August payroll export.'}])
    assert workflows.definition(s, src)['objective'] == 'Reconcile the August payroll export.'


# ── the deterministic runner ────────────────────────────────────────────────────────────────────────────────────────────
def test_steps_with_no_ai_run_without_any_model_and_every_step_is_recorded(db):
    s = MemoryStore()
    src = source(s, [read_dupes(db),
                     {'id': 's2', 'kind': 'task', 'label': 'Open a task', 'title': 'Duplicate bills: {{s1.rows}} pair',
                      'summary': 'Found:\n{{s1}}', 'only_if': {'step': 's1', 'is': 'rows'}}])
    tid = run_task(s, src)
    out = flow.execute(s, src, tid, 'manual', llm=no_model)
    [a, b] = out['steps']
    assert (a['status'], a['rows'], b['status']) == ('ok', 1, 'ok') and 'Payworth' in a['body']
    made = s.get_task(b['task_id'])
    assert made['Title'] == 'Duplicate bills: 1 pair' and 'INV-1' in made['Summary']
    assert (made['Source'], made['SourceRef'], made['ParentId']) == ('workflow', f"workflow:{src['SourceId']}", tid)
    assert out['summary'].startswith('Ran 2 steps in') and 'no AI used' in out['summary']
    assert s.get_task(tid)['Status'] == 'done'                                  # nothing waits on the owner
    run = s.report_run_of_task(tid)
    assert run['type'] == 'flow' and [x['status'] for x in run['steps']] == ['ok', 'ok'] and not run['failed']
    said = [c['Body'] for c in s.list_comments(tid)]
    assert any(x.startswith('Step 1/2 Read AP bills:') for x in said) and any(x.startswith('Step 2/2 Open a task: TQ-') for x in said)
    assert json.loads(s.get_setting(f"report_last_run:{src['SourceId']}"))['steps'][0]['rows'] == 1


def test_a_token_that_names_nothing_is_left_visible_and_said():
    ctx = flow.context({'inputs': {'site': 'North'}}, 'schedule')
    warns = []
    assert flow.render({'q': ['{{inputs.site}} on {{run.trigger}}', '{{s9.head}}']}, ctx, warns) == {'q': ['North on schedule', '{{s9.head}}']}
    assert warns == ['{{s9.head}} names nothing - left as written']


def test_a_step_may_be_named_by_its_label(db):
    s = MemoryStore()
    src = source(s, [read_dupes(db), {'id': 's2', 'kind': 'task', 'label': 'T', 'title': '{{read ap bills.rows}} found'}])
    out = flow.execute(s, src, run_task(s, src), llm=no_model)
    assert s.get_task(out['steps'][1]['task_id'])['Title'] == '1 found'


def test_only_if_skips_on_the_ai_answer_and_the_ai_step_is_one_call_in_the_shape_asked(db):
    s, seen = MemoryStore(), []
    steps = [read_dupes(db),
             {'id': 's2', 'kind': 'ai', 'label': 'Real duplicates?', 'prompt': 'Are these real duplicates?\n{{s1}}', 'output': 'yes_no'},
             {'id': 's3', 'kind': 'task', 'label': 'Tell finance', 'title': 'Duplicates: {{s2.why}}', 'only_if': {'step': 's2', 'is': 'yes'}}]
    src = source(s, steps)
    out = flow.execute(s, src, run_task(s, src), llm=answering({'answer': False, 'why': 'a reissued invoice'}, seen=seen))
    assert [x['status'] for x in out['steps']] == ['ok', 'ok', 'skipped'] and out['steps'][1]['answer'] is False
    assert len(seen) == 1 and seen[0]['system'] == flow.FLOW_AI_SYSTEM and 'Payworth' in seen[0]['user'] and '"answer": true or false' in seen[0]['user']
    assert '1 with AI' in out['summary']
    out = flow.execute(s, src, run_task(s, src), llm=answering('{"answer": true, "why": "same invoice twice"}'))
    assert out['steps'][2]['status'] == 'ok' and s.get_task(out['steps'][2]['task_id'])['Title'] == 'Duplicates: same invoice twice'


def test_an_ai_answer_out_of_shape_or_empty_fails_the_step():
    s = MemoryStore()
    for reply, words in (('', 'empty'), ('maybe?', 'shape'), ('{"answer": "perhaps"}', 'yes or no')):
        src = source(s, [{'id': 's1', 'kind': 'ai', 'label': 'Judge', 'prompt': 'judge', 'output': 'yes_no'}])
        out = flow.execute(s, src, run_task(s, src), llm=answering(reply))
        assert out['failed'] and words in out['steps'][0]['error']
    src = source(s, [{'id': 's1', 'kind': 'ai', 'label': 'Pull', 'prompt': 'p', 'output': 'fields', 'fields': ['vendor', 'amount']}])
    assert 'left out amount' in flow.execute(s, src, run_task(s, src), llm=answering({'vendor': 'Payworth'}))['steps'][0]['error']
    out = flow.execute(s, src, run_task(s, src), llm=answering({'vendor': 'Payworth', 'amount': 1200}))
    assert out['steps'][0]['fields'] == {'vendor': 'Payworth', 'amount': 1200}


def test_a_failed_step_stops_the_run_and_the_run_says_which(db):
    s = MemoryStore()
    src = source(s, [{**read_dupes(db), 'query': 'SELECT * FROM no_such_table'},
                     {'id': 's2', 'kind': 'task', 'label': 'Never', 'title': 'never'}])
    tid = run_task(s, src)
    out = flow.execute(s, src, tid, llm=no_model)
    assert [x['status'] for x in out['steps']] == ['failed'] and 'no such table' in out['steps'][0]['error']
    run = s.report_run_of_task(tid)
    assert run['failed'] and run['error'].startswith('step 1 Read AP bills: ') and s.get_task(tid)['Status'] == 'open'
    assert s.list_comments(tid)[-1]['Body'].startswith('Step 1 failed: ')


def test_a_write_below_the_cards_authority_waits_for_the_owners_yes():
    s = MemoryStore()
    card = s.get_connector_by_type('smb_file')
    s.save_connector({'ConnectorId': card['ConnectorId'], 'Active': True, 'Scope': 'read'}, 'test')
    src = source(s, [{'id': 's1', 'kind': 'source', 'label': 'File the export', 'type': 'smb_write', 'path': 'exports/ap.csv', 'content': 'x'},
                     {'id': 's2', 'kind': 'task', 'label': 'After', 'title': 'after'}])
    tid = run_task(s, src)
    out = flow.execute(s, src, tid, llm=no_model)
    [r] = out['steps']
    assert (r['status'], out['waiting'], out['failed']) == ('waiting', True, False)
    rv = s._one('SELECT * FROM review WHERE ReviewId=?', (r['review_id'],))
    p = json.loads(rv['DraftText'])
    assert (rv['TaskId'], p['action'], p['type'], p['path']) == (tid, 'run_tool', 'smb_write', 'exports/ap.csv')
    assert 'step File the export' in p['why'] and out['summary'] == 'Waiting for your yes on step 1.'
    assert s.get_task(tid)['Status'] == 'open'


def test_the_last_agent_step_gets_what_the_steps_above_found(db):
    s = MemoryStore()
    src = source(s, [read_dupes(db), {'id': 's2', 'kind': 'agent', 'label': 'Fix them', 'prompt': 'Void the second copy of each pair.'}])
    tid = run_task(s, src)
    with mock.patch.object(ingest, '_auto_general') as gen: out = flow.execute(s, src, tid, llm=no_model)
    brief = gen.call_args[0][2]
    assert 'OBJECTIVE: Void the second copy of each pair.' in brief and '"done_so_far"' in brief and 'Payworth' in brief
    assert out['steps'][-1]['kind'] == 'agent' and s.get_task(tid)['Status'] == 'open'


def test_a_run_now_of_a_flow_makes_its_task_then_walks_the_steps(db):
    s = MemoryStore()
    src = source(s, [read_dupes(db)])
    with mock.patch.object(workflows, '_spawn', lambda fn: fn()), mock.patch.object(ingest, '_auto_general', side_effect=AssertionError('no agent')), \
            mock.patch('taskuary.llm.build_llm', side_effect=AssertionError('no model either')):
        out = workflows.run(s, src, trigger='manual')
    t = s.get_task(out['task_id'])
    assert out['steps'] and t['Summary'].startswith('WORKFLOW RUN: Duplicate bill check') and '1. Read/write a system - Read AP bills' in t['Summary']
    assert workflows.of_task(s, t)['steps'][0]['status'] == 'ok' and t['Status'] == 'done'
    assert reports_rows(s) == []


def reports_rows(s): return s._rows("SELECT * FROM message WHERE Channel='report'")


# ── validation ──────────────────────────────────────────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('steps, says', [
    ([], 'no steps'),
    ([{'id': 's1', 'kind': 'agent', 'prompt': 'x'}, {'id': 's2', 'kind': 'task', 'title': 't'}], 'always the last'),
    ([{'id': 's1', 'kind': 'task', 'title': 't'}, {'id': 's1', 'kind': 'task', 'title': 't'}], 'two steps'),
    ([{'id': 's1', 'kind': 'task', 'title': '{{s2.head}}'}, {'id': 's2', 'kind': 'task', 'title': 't'}], 'not a step before it'),
    ([{'id': 's1', 'kind': 'task', 'title': 't', 'only_if': {'step': 's1', 'is': 'yes'}}], 'must name a step before it'),
    ([{'id': 's1', 'kind': 'source', 'type': 'sqlite', 'db': 'x.db'}], 'no query'),
    ([{'id': 's1', 'kind': 'ai', 'prompt': 'p', 'output': 'fields'}], 'name the fields'),
    ([{'id': 's1', 'kind': 'nope'}], 'unknown kind'),
])
def test_a_broken_list_is_refused_with_what_to_change(steps, says):
    ok, why = flow.validate(MemoryStore(), steps)
    assert not ok and says in why


def test_a_broken_flow_cannot_be_saved():
    s = MemoryStore()
    with mock.patch.object(server, 'store', s):
        bad = TestClient(server.app).post('/api/sources', json={'Channel': 'report', 'Address': 'X', 'ConfigJson': json.dumps(
            {'type': 'agent', 'access': 'write', 'title': 'X', 'flow': [{'id': 's1', 'kind': 'task'}]})})
        good = TestClient(server.app).post('/api/sources', json={'Channel': 'report', 'Address': 'X', 'ConfigJson': json.dumps(
            {'type': 'agent', 'access': 'write', 'title': 'X', 'flow': [{'id': 's1', 'kind': 'task', 'title': 'Weekly check'}]})})
    assert bad.status_code == 422 and 'the task has no title' in bad.json()['detail']
    assert good.status_code == 200


# ── test this step ──────────────────────────────────────────────────────────────────────────────────────────────────────
def test_testing_a_step_reads_for_real_and_never_writes(db):
    s = MemoryStore()
    steps = [read_dupes(db), {'id': 's2', 'kind': 'task', 'label': 'Tell finance', 'title': 'Duplicate pair: {{s1.rows}}'},
             {'id': 's3', 'kind': 'draft', 'label': 'Email Gail', 'to': 'gail@northwind.example', 'about': '{{s1}}'},
             {'id': 's4', 'kind': 'agent', 'label': 'Agent', 'prompt': 'Void them.'}]
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_llm', return_value=no_model):
        c = TestClient(server.app)
        first = c.post('/api/workflows/step-test', json={'flow': steps, 'index': 0}).json()
        outs = {'s1': first}
        task = c.post('/api/workflows/step-test', json={'flow': steps, 'index': 1, 'outputs': outs}).json()
        draft = c.post('/api/workflows/step-test', json={'flow': steps, 'index': 2, 'outputs': outs}).json()
        agent = c.post('/api/workflows/step-test', json={'flow': steps, 'index': 3, 'outputs': outs}).json()
    assert (first['status'], first['rows']) == ('ok', 1)
    assert task['status'] == 'dry' and task['head'] == "would open a task 'Duplicate pair: 1'"
    assert draft['status'] == 'dry' and draft['head'] == 'would draft for gail@northwind.example'
    assert agent['status'] == 'dry' and 'OBJECTIVE: Void them.' in agent['body'] and 'done_so_far' in agent['body']
    assert s.list_tasks() == [] and s._rows('SELECT * FROM review') == []


def test_testing_a_write_step_dry_runs_it():
    s = MemoryStore()
    card = s.get_connector_by_type('smb_file')
    s.save_connector({'ConnectorId': card['ConnectorId'], 'Active': True, 'Scope': 'admin'}, 'test')
    steps = [{'id': 's1', 'kind': 'source', 'label': 'Put', 'type': 'smb_write', 'path': 'out/{{run.date}}.csv'}]
    with mock.patch.object(server, 'store', s):
        r = TestClient(server.app).post('/api/workflows/step-test', json={'flow': steps, 'index': 0}).json()
    assert r['status'] == 'dry' and r['head'] == 'would run smb_write' and '"path": "out/20' in r['body']


# ── repair ──────────────────────────────────────────────────────────────────────────────────────────────────────────────
def test_a_failed_scheduled_run_proposes_a_repair_that_is_validated_and_kept_on_yes(db):
    s = MemoryStore()
    broken = {**read_dupes(db), 'query': 'SELECT * FROM bills'}
    src = source(s, [broken, {'id': 's2', 'kind': 'task', 'label': 'T', 'title': 't'}], repair='propose')
    fixed = [{**read_dupes(db), 'query': 'SELECT * FROM bill'}, {'id': 's2', 'kind': 'task', 'label': 'T', 'title': 't'}]
    tid, seen = run_task(s, src), []
    out = flow.execute(s, src, tid, 'schedule', llm=answering({'flow': fixed, 'explain': 'the table is called bill'}, seen=seen))
    assert out['failed'] and json.loads(seen[0]['user'])['failed_step']['error'].startswith('no such table')
    rv = s._one("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    p = json.loads(rv['DraftText'])
    assert (p['action'], p['source_id'], p['why']) == ('repair_workflow', src['SourceId'], 'the table is called bill')
    assert 'query: SELECT * FROM bills -> SELECT * FROM bill' in p['changes']
    proposals.execute(s, rv)
    assert workflows.cfg_of(s.get_source(src['SourceId']))['flow'] == fixed
    # ...and a list that does not hold is refused at the yes, never saved
    rv2 = {'ReviewId': 0, 'TaskId': tid, 'DraftText': json.dumps({**p, 'flow': [{'id': 's1', 'kind': 'task'}]})}
    with pytest.raises(RuntimeError, match='do not hold'): proposals.execute(s, rv2)
    assert workflows.cfg_of(s.get_source(src['SourceId']))['flow'] == fixed


def test_auto_repair_keeps_the_fix_and_reruns_from_the_failed_step_once(db):
    s = MemoryStore()
    src = source(s, [{**read_dupes(db), 'query': 'SELECT * FROM bills'}], repair='auto')
    still_broken = [{**read_dupes(db), 'query': 'SELECT * FROM bils'}]
    llm = answering({'flow': still_broken, 'explain': 'try bils'}, {'flow': [read_dupes(db)], 'explain': 'never asked'})
    out = flow.execute(s, src, run_task(s, src), 'schedule', llm=llm)
    assert out['failed'] and workflows.cfg_of(s.get_source(src['SourceId']))['flow'] == still_broken
    assert len(s.report_runs(src['SourceId'])) == 2               # the run and its one rerun - no loop


def test_fix_with_ai_returns_a_diff_and_saves_nothing(db):
    s = MemoryStore()
    src = source(s, [{**read_dupes(db), 'query': 'SELECT * FROM bills'}])
    out = flow.execute(s, src, run_task(s, src), llm=no_model)
    fixed = [{**read_dupes(db), 'query': 'SELECT * FROM bill'}]
    with mock.patch.object(server, 'store', s), mock.patch.object(server, '_llm', return_value=answering({'flow': fixed, 'explain': 'bill'})):
        r = TestClient(server.app).post(f"/api/workflows/{src['SourceId']}/repair", json={'run_id': out['run_id']}).json()
    assert r['flow'] == fixed and r['diff'][0]['keys'] == [{'key': 'query', 'was': 'SELECT * FROM bills', 'now': 'SELECT * FROM bill'}]
    assert workflows.cfg_of(s.get_source(src['SourceId']))['flow'][0]['query'] == 'SELECT * FROM bills'


# ── the composer writes the steps ───────────────────────────────────────────────────────────────────────────────────────
def test_the_composer_drafts_a_valid_flow_and_refuses_one_that_does_not_hold():
    s = MemoryStore(); s.upsert_agent('assistant', 'assistant', 'general', '{}')
    steps = [{'id': 's1', 'kind': 'source', 'label': 'Open tasks', 'type': 'taskuary', 'card': 'work'},
             {'id': 's2', 'kind': 'ai', 'label': 'Anything stuck?', 'prompt': 'Is anything stuck?\n{{s1}}', 'output': 'yes_no'},
             {'id': 's3', 'kind': 'task', 'label': 'Chase', 'title': 'Stuck work: {{s2.why}}', 'only_if': {'step': 's2', 'is': 'yes'}}]
    seen = []
    def llm(system, user, **_):
        seen.append(json.loads(user))
        return json.dumps({'config': {'type': 'agent', 'title': 'Stuck work check', 'agent': 'assistant', 'flow': steps, 'repair': 'propose'}})
    out = compose.compose_workflow(s, 'every morning, open a task if work is stuck', llm)
    assert out['config']['flow'] == steps and out['config']['repair'] == 'propose' and 'prompt' not in out['config']
    assert any(c['type'] == 'taskuary' for c in seen[0]['catalog']) and 'FLOW RULES' in compose.WORKFLOW_SYSTEM
    bad = compose.compose_workflow(s, 'x', lambda *a, **k: json.dumps({'config': {'type': 'agent', 'title': 'X', 'agent': 'assistant',
                                                                                  'flow': [{'id': 's1', 'kind': 'agent', 'prompt': 'p'}, {'id': 's2', 'kind': 'task', 'title': 't'}]}}))
    assert 'always the last step' in bad['error']


def test_the_composer_may_peek_at_a_schema_before_it_writes_a_step(db):
    s, asked = MemoryStore(), []
    s.upsert_agent('assistant', 'assistant', 'general', '{}')
    replies = iter([{'peek': {'type': 'sqlite', 'db': db, 'query': "SELECT name FROM sqlite_master WHERE type='table'"}},
                    {'config': {'type': 'agent', 'title': 'Dupes', 'agent': 'assistant', 'flow': [read_dupes(db), TELL]}}])
    def llm(system, user, **_): asked.append(json.loads(user)); return json.dumps(next(replies))
    out = compose.compose_workflow(s, 'find duplicate bills', llm)
    assert out['config']['flow'] == [read_dupes(db), TELL] and out['looked_at'][0]['type'] == 'sqlite'
    assert '"name": "bill"' in asked[1]['what_you_looked_at'][0]['result']


TELL = {'id': 's2', 'kind': 'task', 'label': 'Tell finance', 'title': 'Duplicate bills: {{s1.rows}}'}
