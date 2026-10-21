"""The write-up runs behind the press (writeup.py, 2026-10-20): Mark done on a live agent, Close agent and Stop and save return at
once, and the server's own job harvests the session, writes it up and - for a close - closes the task. It leaves exactly what the
two requests the page used to make left; a close pressed meanwhile waits for it and never ends the session unharvested; a
restart mid-job finishes from the saved harvest; a write-up that fails still closes and says so on the task."""
import json, re, threading, time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import handbook, playbooks, server, terminal, writeup, wrapup
from taskuary.store import MemoryStore

SESSION = 'matched the hardware store to vendor 87, expense account 6120, created bill 1043 for 84.10. ' * 8
LAT = 0.3


def brain(system, user, **kw):
    time.sleep(LAT)
    if 'determination' in str(system):
        return json.dumps({'determination': 'Matched the charge.', 'actions': 'Created bill 1043', 'summary': 'Posted the bill.', 'outcome': 'did_work'})
    return json.dumps({'entries': [], 'playbook': None})


def rows(s):
    """Every row of every table, without the clock, the session id or file names stamped with it."""
    out = {}
    for (name,) in s.cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name"):
        if name in ('setting', 'operation'): continue          # the job's own record (emptied) and the proposal ids
        cur = s.cx.execute(f'SELECT * FROM "{name}"'); cols = [d[0] for d in cur.description]
        keep = [i for i, c in enumerate(cols) if not (c.endswith('At') or c.endswith('Time') or c in ('Detail', 'OperationId', 'Version'))]
        out[name] = sorted(re.sub(r'[0-9a-f]{64}', 'H', re.sub(r'\d{8}-\d{6}-\d{6}', 'TS', json.dumps([r[i] for i in keep], default=str)))
                           for r in cur.fetchall())
    return out


@pytest.fixture
def world(monkeypatch, tmp_path):
    monkeypatch.setattr(handbook, 'enabled', lambda store: False)
    monkeypatch.setattr(playbooks, 'folder', lambda: tmp_path / 'playbooks')
    monkeypatch.setattr(writeup, '_folder', lambda store: str(tmp_path))
    closed, order = [], []
    def transcript_for(store, tid): order.append('harvest'); return SESSION, 'coding', f'sid-{tid}'
    def close(sid): order.append('close'); closed.append(sid); return True
    stack = [mock.patch('taskuary.terminal.transcript_for', transcript_for), mock.patch('taskuary.terminal.close', close),
             mock.patch('taskuary.terminal.session_for', lambda tid: None), mock.patch('taskuary.llm.build_llm', return_value=brain)]
    for p in stack: p.start()
    def make():
        s = MemoryStore(); monkeypatch.setattr(server, 'store', s)
        tid = s.create_task({'Title': 'Post the hardware store charge', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        return s, tid
    yield make, order
    for p in stack: p.stop()
    writeup._JOBS.clear(); writeup._STATE.clear()


def press_close_today(c, tid):
    c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'no_reply': True})
    op = c.post('/api/operations', json={'kind': 'task.complete', 'target': tid, 'params': {}}).json()
    c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})


def test_mark_done_in_the_background_leaves_what_the_two_requests_left(world):
    make, order = world
    s, tid = make(); c = TestClient(server.app)
    press_close_today(c, tid); wrapup.forget(tid); today = rows(s)
    s, tid = make(); c = TestClient(server.app)
    t = time.perf_counter(); r = c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'no_reply': True, 'background': True, 'then_close': True})
    took = time.perf_counter() - t
    assert r.status_code == 200 and r.json()['wrap'] == 'started' and took < LAT, f'the press came back at once ({took:.2f} s)'
    assert writeup.wait_for(tid, 30); wrapup.forget(tid)
    assert rows(s) == today
    assert (s.get_task(tid) or {}).get('Status') == 'done'
    assert writeup.state(tid)['close'] is True, 'a close says so: Close out does not wait on it, the task leaves the table'


def test_stop_and_save_in_the_background_leaves_what_it_left(world):
    make, _ = world
    s, tid = make(); c = TestClient(server.app)
    c.post(f'/api/tasks/{tid}/wrap', json={'close': False}); wrapup.forget(tid); today = rows(s)
    s, tid = make(); c = TestClient(server.app)
    assert c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'background': True}).json()['wrap'] == 'started'
    assert writeup.wait_for(tid, 30); wrapup.forget(tid)
    assert rows(s) == today and (s.get_task(tid) or {}).get('Status') != 'done'


def test_a_close_pressed_during_the_write_up_waits_for_it_and_the_task_ends_closed_with_its_report(world):
    make, order = world
    s, tid = make(); c = TestClient(server.app)
    c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'no_reply': True, 'background': True, 'then_close': True})
    op = c.post('/api/operations', json={'kind': 'task.complete', 'target': tid, 'params': {}}).json()     # Mark done from elsewhere, at once
    c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})
    assert not writeup.running(tid), 'the second close waited for the write-up'
    assert order.index('harvest') < order.index('close'), 'the session was harvested before anything closed it'
    assert (s.get_task(tid) or {}).get('Status') == 'done'
    assert any(str(x.get('Body') or '').startswith(wrapup.REPORT) for x in s.list_comments(tid)), 'the report was kept'
    wrapup.forget(tid)


def test_a_write_up_that_fails_still_closes_and_says_so_on_the_task(world):
    make, _ = world
    s, tid = make(); c = TestClient(server.app)
    with mock.patch('taskuary.session_artifacts.coding', side_effect=RuntimeError('disk full')):
        c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'no_reply': True, 'background': True, 'then_close': True})
        assert writeup.wait_for(tid, 30)
    assert (s.get_task(tid) or {}).get('Status') == 'done'
    assert any(str(x.get('Body') or '').startswith(writeup.FAILED) and 'disk full' in x['Body'] for x in s.list_comments(tid))
    wrapup.forget(tid)


def test_a_restart_mid_job_finishes_from_the_saved_harvest(world):
    make, order = world
    s, tid = make(); c = TestClient(server.app)
    gate = threading.Event()
    def stuck(system, user, **kw): gate.wait(10); raise RuntimeError('the process went away')
    with mock.patch('taskuary.llm.build_llm', return_value=stuck):
        c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'no_reply': True, 'background': True, 'then_close': True})
        record = json.loads(s.get_setting(writeup.PREFIX + str(tid)))
        assert record['harvest'], 'the harvest is on disk before any AI answered'
        # ...the restart: this process's job is gone, the record and the harvest stay
        saved = s.get_setting(writeup.PREFIX + str(tid))
        writeup._JOBS.clear(); wrapup.forget(tid)
    with mock.patch('taskuary.terminal.transcript_for', side_effect=AssertionError('the session is gone after a restart')):
        s.set_setting(writeup.PREFIX + str(tid), saved, 'test')
        assert writeup.resume(s) == 1 and writeup.wait_for(tid, 30)
    gate.set()
    assert (s.get_task(tid) or {}).get('Status') == 'done'
    assert any(str(x.get('Body') or '').startswith(wrapup.REPORT) for x in s.list_comments(tid))
    assert not s.get_setting(writeup.PREFIX + str(tid))
    wrapup.forget(tid)


# WHAT THE WRITE-UP IS DOING NOW (the owner, 2026-10-21): Stop and save opens Close out at once, and its pending block says the job's
# real stage - read from the job, never a timer - until the draft replaces it.
def stages_of(monkeypatch):
    seen, real = [], writeup._set
    def spy(tid, job, **kw):
        real(tid, job, **kw); st = writeup.state(tid) or {}
        if not seen or seen[-1] != (st.get('stage'), st.get('running')): seen.append((st.get('stage'), st.get('running')))
    monkeypatch.setattr(writeup, '_set', spy)
    return seen


def test_stop_and_save_says_each_stage_it_reaches_and_the_detail_carries_it(world, monkeypatch):
    make, _ = world
    s, tid = make(); c = TestClient(server.app); seen = stages_of(monkeypatch)
    r = c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'background': True}).json()
    assert r['job'] and writeup.wait_for(tid, 30)
    assert seen == [('report', True), ('reply', True), ('learning', True), ('done', False)]
    assert c.get(f'/api/tasks/{tid}').json()['writeup'] == {'job': r['job'], 'stage': 'done', 'running': False, 'error': '', 'close': False}
    wrapup.forget(tid)


def test_the_press_answers_while_the_job_writes_and_the_detail_says_where_it_is(world):
    make, _ = world
    s, tid = make(); c = TestClient(server.app)
    gate = threading.Event()
    def slow(system, user, **kw): gate.wait(10); return brain(system, user, **kw)
    with mock.patch('taskuary.llm.build_llm', return_value=slow):
        r = c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'background': True}).json()
        st = c.get(f'/api/tasks/{tid}').json()['writeup']
        assert st['job'] == r['job'] and st['running'] and st['stage'] in ('reading', 'report')
        assert c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'background': True}).json()['job'] == r['job'], 'a second press joins it'
        gate.set(); assert writeup.wait_for(tid, 30)
    assert writeup.state(tid)['stage'] == 'done'
    wrapup.forget(tid)


def test_a_write_up_that_fails_says_failed_and_why(world):
    make, _ = world
    s, tid = make(); c = TestClient(server.app)
    with mock.patch('taskuary.session_artifacts.coding', side_effect=RuntimeError('disk full')):
        c.post(f'/api/tasks/{tid}/wrap', json={'close': False, 'background': True})
        assert writeup.wait_for(tid, 30)
    st = c.get(f'/api/tasks/{tid}').json()['writeup']
    assert st['stage'] == 'failed' and not st['running'] and 'disk full' in st['error']
    wrapup.forget(tid)


def test_a_wrap_outside_a_job_says_no_stage(world):
    make, _ = world
    s, tid = make(); c = TestClient(server.app)
    c.post(f'/api/tasks/{tid}/wrap', json={'close': False})
    assert writeup.state(tid) is None and c.get(f'/api/tasks/{tid}').json()['writeup'] is None
    wrapup.forget(tid)
