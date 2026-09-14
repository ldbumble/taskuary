"""Next-day continuity reuses saved records, without automatic checkpoint/summarizer jobs."""
import io
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import agents, continuity, general, guard, llm, server, terminal
from taskuary.store import MemoryStore, SQLiteStore


def task(store, **fields):
    return store.create_task({'Title': 'Prepare item numbers', 'Kind': 'general', 'Status': 'open', **fields}, 'owner')


def connect(store, name='claude'):
    store.upsert_agent(name, 'coding', 'cli', json.dumps({'cmd': name, 'args': ['exec'] if name == 'codex' else ['-p']}))


def brain(text='The numbers are collected. Next: prepare a summary.', sid='native-thread'):
    def answer(*a, **kw): return text
    answer.session_id = sid
    return answer


@pytest.mark.parametrize('provider', ['claude', 'codex'])
def test_database_reopen_restores_exact_native_thread_and_model(tmp_path, provider):
    db = tmp_path / 'tasks.db'; store = SQLiteStore(db); connect(store, provider)
    tid = task(store)
    with mock.patch.object(llm, 'build_llm', return_value=brain()):
        session = general.GeneralSession(store, tid, pick=f'cli:{provider}', model='chosen-model')
        session.send_prompt('Collect item numbers')
    store.cx.close()
    fresh = SQLiteStore(db)
    try:
        resumed = general.GeneralSession(fresh, tid)
        assert resumed.pick == f'cli:{provider}' and resumed.model == 'chosen-model'
        assert resumed.cli_sid == 'native-thread'
        with mock.patch.object(llm, 'build_llm', return_value=brain()) as build:
            resumed.send_prompt('Continue with the summary')
        assert build.call_args.kwargs['resume'] == 'native-thread'
        assert 'Collect item numbers' in build.call_args.kwargs['fallback_user']
        assert general.default_pick(fresh, fresh.get_task(tid)) == f'cli:{provider}'
    finally: fresh.cx.close()


def test_provider_switch_and_changed_configuration_do_not_reuse_a_foreign_thread():
    store = MemoryStore(); connect(store); connect(store, 'codex'); tid = task(store)
    session = general.GeneralSession(store, tid, pick='cli:claude')
    session.cli_sid = 'claude-only'; session._remember_session()
    session.select_provider(pick='cli:codex')
    assert session.cli_sid == ''
    session.cli_sid = 'codex-only'; session._remember_session()
    store.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex', 'args': ['exec', '-c', 'profile="other"']}))
    with mock.patch.object(llm, 'build_llm', return_value=brain(sid='new-context')) as build:
        session.send_prompt('Continue')
    assert not build.call_args.kwargs.get('resume')
    assert store.saved_session(tid)['NativeId'] == 'new-context'
    store.upsert_agent('codex', 'coding', 'cli', json.dumps({'cmd': 'codex', 'args': ['exec']}))
    assert general.GeneralSession(store, tid).cli_sid == ''
    store.delete_task(tid)
    assert store.saved_session(tid) is None


def test_missing_native_session_falls_back_to_saved_history_and_says_so():
    store = MemoryStore(); connect(store); tid = task(store)
    store.add_comment(tid, 'owner', general.USER_TYPE, 'Use the August period, not September.')
    session = general.GeneralSession(store, tid, pick='cli:claude')
    session.cli_sid = 'expired'; session._remember_session()
    failed = mock.Mock(side_effect=RuntimeError('session not found'))
    seen = {}
    def restored(system, user, **kw): seen['user'] = user; return 'Continuing the August report.'
    restored.session_id = 'replacement'
    with mock.patch.object(llm, 'build_llm', side_effect=[failed, restored]):
        session.send_prompt(continuity.RESUME_PROMPT, as_owner=False)
    assert 'August period' in seen['user'] and continuity.RESUME_PROMPT in seen['user']
    assert 'Restored from the saved conversation' in session.info()['resume_notice']
    assert store.saved_session(tid)['NativeId'] == 'replacement'


def test_backup_provider_receives_history_without_primary_session_id():
    store = MemoryStore(); connect(store); connect(store, 'codex')
    store.set_setting('triage_backup_ai', 'cli:codex', 'owner')
    seen = {}
    def make(st, name, *args, **kw):
        seen[name] = kw.get('resume')
        if name == 'claude': return mock.Mock(side_effect=RuntimeError('provider unavailable'))
        def backup(system, user, **kw): seen['context'] = user; return 'Restored'
        backup.session_id = 'codex-thread'
        return backup
    with mock.patch.object(llm, 'make_cli_llm', side_effect=make), mock.patch.object(agents, 'availability_failure', return_value=True):
        answer = llm._build_llm(store, pick='cli:claude', resume='claude-thread', fallback_user='The complete saved conversation')
        assert answer('system', 'Continue') == 'Restored'
    assert seen == {'claude': 'claude-thread', 'codex': None, 'context': 'The complete saved conversation'}
    assert answer.last_pick == 'cli:codex' and answer.session_id == 'codex-thread'


@pytest.mark.parametrize('provider', ['claude', 'codex'])
def test_runner_uses_exact_resume_id_and_keeps_existing_permissions(provider):
    process = mock.Mock()
    process.stdin = io.StringIO(); process.stderr = io.StringIO()
    process.stdout = io.StringIO(json.dumps({'type': 'result', 'result': 'Ready', 'session_id': 'native-thread'}) + '\n')
    process.returncode = 0
    args = ['exec', '--sandbox', 'read-only'] if provider == 'codex' else ['-p', '--tools', '']
    with mock.patch.object(agents, '_resolve_cmd', return_value=[provider]), mock.patch.object(agents, '_git', return_value=''), \
         mock.patch('taskuary.spawn.popen', return_value=process) as launched:
        agents.run_cli({'cmd': provider, 'args': args}, 'Continue', lambda *a: None, resume='native-thread')
    cmd = launched.call_args.args[0]
    if provider == 'codex':
        assert cmd[-4:] == ['resume', 'native-thread', '--json', '-']
        assert cmd[cmd.index('--sandbox') + 1] == 'read-only'
    else:
        assert cmd[-2:] == ['--resume', 'native-thread']
        assert cmd[cmd.index('--tools') + 1] == ''
    assert '--last' not in cmd


def test_previous_work_uses_saved_recaps_excludes_finished_and_busy_and_prioritizes_review():
    store = MemoryStore()
    resumed = task(store); ready = task(store, Title='Ready report', Status='waiting')
    finished = task(store, Status='done'); dock = task(store, SourceRef='assistant:dock'); working = task(store)
    for tid in (resumed, ready, finished, dock, working):
        store.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The figures are ready. Waiting for your review.')
    rid = store.add_review({'TaskId': ready, 'Kind': 'action', 'Status': 'pending', 'DraftText': '{"action":"write_playbook"}'})
    live = mock.Mock(task_id=working, alive=True, mode='assistant', busy=True)
    with mock.patch.dict(terminal.SESSIONS, {'working': live}, clear=True):
        rows = continuity.previous_work(store)
    assert {r['taskId'] for r in rows} == {resumed, ready}
    assert next(r for r in rows if r['taskId'] == ready)['reviewId'] == rid
    assert next(r for r in rows if r['taskId'] == resumed)['action'] == 'resume'


def test_resume_rechecks_pending_reviews_and_never_starts_work_for_them():
    store = MemoryStore(); tid = task(store)
    rid = store.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'DraftText': '{}'})
    with mock.patch.object(server, 'store', store), mock.patch.object(general, 'start_session') as start:
        out = TestClient(server.app).post(f'/api/tasks/{tid}/resume').json()
    assert out['action'] == 'review' and out['reviewId'] == rid and not start.called
    assert guard.denied('POST', f'/api/tasks/{tid}/resume')


def test_resume_starts_once_after_owner_click_and_finished_tasks_stay_finished():
    store = MemoryStore(); tid = task(store); finished = task(store, Status='done'); seen = []
    session = mock.Mock()
    def start(st, task_id, **kw):
        assert task_id in general.OPENING; seen.append(task_id); return session
    with mock.patch.object(server, 'store', store), mock.patch.object(general, 'provider_options', return_value=[{}]), \
         mock.patch.object(general, 'start_session', side_effect=start), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        client = TestClient(server.app)
        assert client.post(f'/api/tasks/{finished}/resume').status_code == 409
        assert client.post(f'/api/tasks/{tid}/resume').status_code == 200
        general.OPENING.add(tid)
        try: assert client.post(f'/api/tasks/{tid}/resume').json()['action'] == 'open'
        finally: general.OPENING.discard(tid)
    assert seen == [tid]
    assert session.send_prompt.call_args.kwargs == {'as_owner': False, 'echo': False}
