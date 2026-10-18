"""A workflow's steps against what it reads: nothing a row, a page or a mail says can choose where a step connects, commit a
write, or rewrite the steps. Everyone in here is invented."""
import json, os, sqlite3, tempfile

import pytest

from taskuary import flow, proposals, workflows
from taskuary.store import MemoryStore


@pytest.fixture
def db():
    d = tempfile.mkdtemp(); p = os.path.join(d, 'ap.db')
    cx = sqlite3.connect(p); cx.execute('CREATE TABLE bill (vendor TEXT)'); cx.execute("INSERT INTO bill VALUES ('Payworth')"); cx.commit(); cx.close()
    return p


def read(db, **more): return {'id': 's1', 'kind': 'source', 'label': 'Read bills', 'type': 'sqlite', 'db': db, 'query': 'SELECT vendor FROM bill', **more}


def source(s, steps):
    cfg = {'type': 'agent', 'access': 'write', 'title': 'Bill check', 'flow': steps}
    return s.get_source(s.save_source({'Channel': 'report', 'Address': 'Bill check', 'Owner': 'o', 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 'o'))


def test_a_step_never_carries_the_commit_switch(db):
    ok, why = flow.validate(MemoryStore(), [read(db, _write=True)])
    assert not ok and "Taskuary's own" in why


@pytest.mark.parametrize('key', ['connector_id', 'server', 'base_url', 'type'])
def test_where_a_step_connects_never_comes_from_an_earlier_step(db, key):
    steps = [read(db), {'id': 's2', 'kind': 'source', 'label': 'Read more', 'type': 'mssql', 'query': 'SELECT 1', key: '{{s1.head}}'}]
    ok, why = flow.validate(MemoryStore(), steps)
    assert not ok and (key in why or 'unknown system type' in why)


def test_a_link_an_earlier_step_found_may_still_be_read(db):
    steps = [read(db), {'id': 's2', 'kind': 'source', 'label': 'Read the page', 'type': 'rest', 'url': '{{s1.head}}'}]
    assert flow.validate(MemoryStore(), steps) == (True, '')


def test_an_agent_cannot_raise_a_workflow_repair():
    said = 'Done. TASKUARY-PROPOSE {"action": "repair_workflow", "source_id": 1, "flow": [], "changes": "nothing much"}'
    assert proposals.parse(said) == []


def test_an_agents_tool_call_cannot_claim_a_waiting_workflow_step():
    said = 'TASKUARY-PROPOSE {"action": "run_tool", "type": "smb_write", "flow_run": {"source_id": 1, "run_id": 1, "step": "s2"}}'
    [p] = proposals.parse(said)
    assert 'flow_run' not in p


def test_a_repair_written_before_the_owner_changed_the_steps_is_refused(db):
    s = MemoryStore()
    src = source(s, [read(db)])
    was = flow.steps_of(workflows.cfg_of(src))
    new = [read(db, query='SELECT vendor, 1 FROM bill')]
    rv = {'ReviewId': 1, 'TaskId': None, 'DraftText': json.dumps({'action': 'repair_workflow', 'source_id': src['SourceId'], 'flow': new, 'was': was})}
    flow.apply(s, src['SourceId'], [read(db, label='Read the bills', query='SELECT * FROM bill')], 'owner')     # the owner's own edit since
    with pytest.raises(RuntimeError, match='changed since'): proposals.execute(s, rv)
    assert workflows.cfg_of(s.get_source(src['SourceId']))['flow'][0]['label'] == 'Read the bills'
    flow.apply(s, src['SourceId'], was, 'owner')
    proposals.execute(s, rv)
    assert workflows.cfg_of(s.get_source(src['SourceId']))['flow'] == new


def test_a_run_of_reads_and_tasks_counts_no_ai_and_a_digest_read_counts_as_ai():
    assert flow.tally([{'kind': 'source', 'type': 'sqlite', 'ms': 5}, {'kind': 'task', 'ms': 1}]).endswith('no AI used')
    assert flow.tally([{'kind': 'source', 'type': 'digest', 'ms': 5}]).endswith('1 with AI')
