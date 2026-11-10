"""AN AGENT WAITING ON THE OWNER IS STILL WAITING AFTER A RESTART (the owner, 2026-11-03).

The shape: a coding agent asked "Ready to push to main - go ahead?" and an update restarted Taskuary before anyone answered. The restart
cuts every session off ("disconnected", source shutdown) and tags the task interrupted. Now such an agent - only one asking, never one
that was working - gets its own conversation back on the next start, with nothing typed or sent, and its question carried onto the new
run so it reads live and asking. Once: a question already brought back is not brought back again, and a resume that fails leaves the
ended run's Answer it. Invented Northwind data only (CLAUDE.md)."""
import json
from types import SimpleNamespace
import pytest
from taskuary import general, server, terminal, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ASK = 'Ready to push a1b2c3d to main, which deploys the portal to production. Go ahead?'


@pytest.fixture
def s(monkeypatch, tmp_path):
    s = MemoryStore(); s.set_setting('calendar_enabled', '0', 'test')
    s.upsert_agent('claude', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    monkeypatch.setattr(server, 'store', s)
    monkeypatch.setattr(server, '_brainless', lambda coding: '')
    monkeypatch.setattr(terminal, 'SESSIONS', {})
    s.cwd = str(tmp_path)
    return s


def ev(s, tid, kind, text='', source='hook', rid=None, sid='c1', choices=None):
    s.add_worker_event({'TaskId': tid, 'Sid': sid, 'Kind': kind, 'RequestId': rid, 'Text': text, 'Source': source,
                        'ChoicesJson': json.dumps(choices) if choices else None})


def cut_off(s, kind='coding', asking=True, status='open', source='api', choices=None, cut='shutdown', rid=None):
    t = Factory(s).task(title='Packet download fails for large teams', kind=kind, status=status)
    s.note_session_id(t, 'c1', 'claude-thread', 'claude', s.cwd)
    ev(s, t, 'working'); ev(s, t, 'turn_end', ASK if asking else 'Looking at the export code now.')
    if asking: ev(s, t, 'input_needed', ASK, source=source, rid=rid or ws.request_id_for(ASK), choices=choices)
    ev(s, t, 'disconnected', 'the session ended', source=cut)
    s.tag_task(t, terminal.INTERRUPTED, True, cut)
    return t


def live(s, tid, sid, **kw):
    "What a start leaves behind: a live session on the task, the interruption over."
    terminal.SESSIONS[sid] = SimpleNamespace(sid=sid, task_id=tid, alive=True, agent='claude', **kw)
    terminal.resume_task(s, tid, 'startup')
    return terminal.SESSIONS[sid]


@pytest.fixture
def starts(s, monkeypatch):
    got = []
    def start(store, tid, agent='', model=None, instruction=None, actor='owner', **kw):
        got.append({'tid': tid, 'agent': agent, 'instruction': instruction, 'actor': actor, **kw})
        return {'sid': live(s, tid, f'r{len(got)}').sid}
    monkeypatch.setattr(server.hub_term, 'start_on_task', start)
    return got


def tagged(s, tid): return terminal.INTERRUPTED in str(s.get_task(tid).get('Tags') or '')
def audits(s, tid): return [a for a in s.audit_since('') if a['Action'] == 'resume-asking' and str(a['EntityId']) == str(tid)]


def test_a_coding_agent_cut_off_asking_is_back_live_and_asking_with_nothing_typed(s, starts):
    t = cut_off(s)
    assert server.resume_asking() == [t]
    st = starts[0]
    assert (st['resume'], st['quiet'], st['instruction'], st['actor'], st['cwd']) == ('claude-thread', True, None, 'startup', s.cwd)
    w = ws.status(s, t)
    assert w['live'] and w['state'] == 'input_needed' and [r['text'] for r in w['requests']] == [ASK]
    assert not tagged(s, t) and ws.left_asking(s, t) == [], 'live again: its own pane asks'
    assert json.loads(audits(s, t)[0]['Detail'])['questions'] == [ws.request_id_for(ASK)]
    assert s.list_comments(t)[-1]['Body'] == server.RESTARTED


def test_it_resumes_once_and_a_second_cut_falls_back_to_answer_it(s, starts):
    t = cut_off(s); server.resume_asking()
    terminal.SESSIONS.clear(); ev(s, t, 'disconnected', 'the session ended', source='shutdown', sid='r1')
    s.tag_task(t, terminal.INTERRUPTED, True, 'shutdown')
    assert server.resume_asking() == [] and len(starts) == 1
    assert [r['text'] for r in ws.left_asking(s, t)] == [ASK], 'the ended run still offers Answer it'


def test_a_resume_that_fails_leaves_the_task_interrupted_and_its_question_answerable(s, monkeypatch):
    t = cut_off(s)
    def boom(store, tid, *a, **kw): terminal.resume_task(store, tid, 'startup'); raise RuntimeError('claude could not start')
    monkeypatch.setattr(server.hub_term, 'start_on_task', boom)
    assert server.resume_asking() == []
    assert tagged(s, t) and [r['text'] for r in ws.left_asking(s, t)] == [ASK]
    assert 'claude could not start' in json.loads(audits(s, t)[0]['Detail'])['failed']


@pytest.mark.parametrize('how', ['working', 'owner_stopped', 'done', 'dropped', 'answered'])
def test_only_an_agent_still_asking_on_an_open_task_comes_back(s, starts, how):
    t = cut_off(s, asking=how != 'working', status={'done': 'done', 'dropped': 'dropped'}.get(how, 'open'),
                cut='owner' if how == 'owner_stopped' else 'shutdown')
    if how == 'owner_stopped': ev(s, t, 'stopped', 'stopped by you', source='owner')
    if how == 'answered': ev(s, t, 'working', 'yes, push it'); ev(s, t, 'disconnected', 'the session ended', source='shutdown')
    assert server.resume_asking() == [] and starts == []


def test_no_ai_connected_starts_nothing(s, starts, monkeypatch):
    t = cut_off(s)
    monkeypatch.setattr(server, '_brainless', lambda coding: 'No AI is connected')
    assert server.resume_asking() == [] and starts == [] and tagged(s, t)


def test_a_coding_choosers_options_ride_the_question_so_the_answer_goes_in_words(s, starts):
    t = cut_off(s, source='hook', choices=['Push it', 'Hold off'], rid=ws.question_id(ws.group_key('push'), 1))   # its question tool's
    assert server.resume_asking() == [t]
    r = ws.status(s, t)['requests'][0]
    assert r['text'] == f'{ASK} (Push it / Hold off)' and r['choices'] == [] and r['source'] == ws.RESUMED


def test_a_general_agent_waiting_comes_back_on_its_saved_chat(s, monkeypatch):
    t = cut_off(s, kind='general', source='api', choices=['Push it', 'Hold off'])
    monkeypatch.setattr(general, 'provider_options', lambda store: [{'id': 'cli:claude'}])
    got = []
    def start(store, tid, actor='owner', **kw): got.append(actor); return live(s, tid, 'g1')
    monkeypatch.setattr(general, 'start_session', start)
    assert server.resume_asking() == [t] and got == ['startup']
    w = ws.status(s, t)
    assert w['live'] and w['state'] == 'input_needed' and w['requests'][0]['choices'] == ['Push it', 'Hold off']


def test_a_quiet_resume_types_nothing_into_the_reopened_pane(s, monkeypatch):
    t = cut_off(s)
    seen = {}
    def opened(store, agent, tid, *a, seed_fn='unset', resume=None, **kw):
        seen.update(seed_fn=seed_fn, resume=resume); raise RuntimeError('stop here')
    monkeypatch.setattr(terminal, 'open_session', opened)
    with pytest.raises(RuntimeError): terminal.start_on_task(s, t, 'claude', None, None, 'startup', cwd=s.cwd, resume='claude-thread', quiet=True)
    assert seen == {'seed_fn': None, 'resume': 'claude-thread'}
