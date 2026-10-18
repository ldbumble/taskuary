"""A workflow DOES something - moves data, opens work, drafts what goes out - and every run of one is a task (the owner,
2026-10-18). An ask that only reads and reports is a report: the workflow door says so plainly and hands back the report drafted
from the same reads, for one press to open. The model judges the ask; steps that only read are caught by what they are. Invented
people only."""
import json, os, sqlite3, tempfile
from unittest import mock

import pytest

from taskuary import compose, flow, workflows
from taskuary.store import MemoryStore


@pytest.fixture
def db():
    p = os.path.join(tempfile.mkdtemp(), 'ap.db')
    cx = sqlite3.connect(p); cx.execute('CREATE TABLE bill (vendor TEXT, invoice TEXT)'); cx.commit(); cx.close()
    return p


def read(db): return {'id': 's1', 'kind': 'source', 'label': 'Read AP bills', 'type': 'sqlite', 'db': db, 'query': 'SELECT * FROM bill'}
TELL = {'id': 's3', 'kind': 'task', 'label': 'Tell finance', 'title': 'Bills: {{s1.rows}}'}


def store():
    s = MemoryStore(); s.upsert_agent('assistant', 'assistant', 'general', '{}'); return s


def test_an_ask_that_only_pulls_and_summarizes_gets_the_report_verdict_not_steps():
    s, seen = store(), {}
    report = {'type': 'taskuary', 'card': 'work', 'title': 'Open work summary', 'daily_at': '08:00', 'ai_prompt': 'Summarize what is open.'}
    def llm(system, user, **_):
        seen.update(system=system); return json.dumps({'report': report, 'explain': 'It only reads and summarizes.'})
    out = compose.compose_workflow(s, 'every morning pull the open work and summarize it for me', llm)
    assert out['verdict'] == 'report' and 'config' not in out and 'flow' not in out['report']
    assert out['report']['type'] == 'taskuary' and out['report']['ai_prompt'] == 'Summarize what is open.'
    assert out['explain'].startswith(compose.REPORT_VERDICT) and 'every run of one is a task' in out['explain']
    assert 'Judge it from what they ask for' in seen['system']


def test_drafted_steps_that_only_read_come_back_as_the_report_with_the_same_query(db):
    steps = [read(db), {'id': 's2', 'kind': 'ai', 'label': 'Summary', 'prompt': 'Summarize these:\n{{s1}}\n{{s1.rows}} found', 'output': 'text'}]
    out = compose.compose_workflow(store(), 'x', lambda *a, **k: json.dumps({'config': {'type': 'agent', 'title': 'Bills', 'agent': 'assistant',
                                                                                         'flow': steps, 'cron': '0 8 * * 1'}}))
    r = out['report']
    assert out['verdict'] == 'report' and (r['type'], r['db'], r['query']) == ('sqlite', db, 'SELECT * FROM bill')
    assert r['ai_prompt'] == 'Summarize these:\n[sqlite.read ap bills]\n found' and r['cron'] == '0 8 * * 1' and 'access' not in r
    assert flow.only_reads(steps) and not flow.only_reads([*steps, TELL]) and not flow.only_reads([])
    acts = compose.compose_workflow(store(), 'x', lambda *a, **k: json.dumps({'config': {'type': 'agent', 'title': 'Bills', 'agent': 'assistant',
                                                                                          'flow': [*steps, TELL]}}))
    assert acts['config']['flow'][-1]['kind'] == 'task' and 'verdict' not in acts


def test_every_run_of_a_read_only_flow_is_still_a_task(db):
    """No record-only road: a saved workflow runs as a task whatever its steps are."""
    s = store()
    sid = s.save_source({'Channel': 'report', 'Address': 'Bills', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(
        {'type': 'agent', 'access': 'write', 'title': 'Bills', 'flow': [read(db)]})}, 'o')
    with mock.patch.object(workflows, '_spawn', lambda fn: fn()):
        out = workflows.run(s, s.get_source(sid), trigger='schedule')
    assert s.get_task(out['task_id'])['Source'] == 'workflow'
