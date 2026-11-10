"""ONE ROAD FOR A LINE THE OWNER TYPES, every agent kind in every state (general.take_line; the owner, 2026-11-10: "coding and general use the
same code when it comes to interactions so there should be no difference. IT should not say waiting on top of the prompt only under it and it
should happen right away"). The line is posted as the page posts it, and the task's chat payload - the read the page polls - is sampled every
50 ms from the post to the answer. In EVERY sample: his line is there exactly once, the turn is at work (`working`), nothing of the new turn
stands before his line, and the turn's clock (`turnStarted`) is the press and never moves. The agents are the fakes the suite already has,
slowed to start in seconds; the people and the work are invented."""
import json, subprocess, sys, threading, time
from pathlib import Path
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import acpcoding, agents, clipool, codingchat, general, session_artifacts, terminal
from taskuary.store import MemoryStore

pytestmark = pytest.mark.acp            # the fake adapter is this file's own (conftest.no_real_acp_adapters)
HERE = Path(__file__).parent
FAKE_ACP, FAKE_CLAUDE = [sys.executable, str(HERE / 'fake_acp_server.py')], str(HERE / 'fake_claude.py')
KINDS = ['general', 'api', 'acp', 'pty']
STATES = ['never', 'rest', 'midturn', 'idled', 'ended', 'restart', 'closed']
LINE = 'can you check the totals and then merge it in'


def until(cond, secs=30):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.05)
    return cond()


class Brain:
    "An API card's model (apiagent's plain road): slow to answer, its answer naming what it was asked last."
    def __call__(self, system, user, **kw):
        time.sleep(1.5)
        return f"Answered: {user.strip().splitlines()[-1][:200]}"


@pytest.fixture
def world(tmp_path, monkeypatch, request):
    kind = request.param
    (tmp_path / 'artifacts').mkdir()
    monkeypatch.setattr(session_artifacts, 'root', lambda: tmp_path / 'artifacts')
    s = MemoryStore()
    monkeypatch.setattr(general, 'idle_for', lambda: 3600)
    if kind in ('acp', 'pty'):
        repo = tmp_path / 'ledger'; repo.mkdir()
        (repo / 'totals.py').write_text('def total(a, tax):\n    return a + tax\n', encoding='utf-8')
        git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True)
        git('init', '-q'); git('config', 'user.name', 'Alex Doyle'); git('config', 'user.email', 'alex@northwind.example')
        git('add', '.'); git('commit', '-qm', 'start')
        s.set_setting(agents.DEV_MODE, '1', 'owner')
        prof = {'cmd': 'claude', 'acp_cmd': FAKE_ACP, 'cwd': str(repo)} if kind == 'acp' else {'cmd': sys.executable, 'args': [str(HERE / 'fake_tui.py')], 'cwd': str(repo)}
        s.upsert_agent('coding', 'coding', 'cli', json.dumps(prof))
        tid = s.create_task({'Title': 'Comment the ledger totals', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [FAKE_ACP[0]])
        monkeypatch.setattr(terminal, 'pretrust', lambda *a, **k: False)
        monkeypatch.setattr(acpcoding, 'FELL_BACK', set())
        monkeypatch.setenv('FAKE_ACP_THINK', '1.5')
    else:
        tid = s.create_task({'Title': 'Research the vendor', 'Kind': 'general', 'Status': 'open'}, 'owner')
        if kind == 'general':
            conn = {'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose']}
            s.upsert_agent('claude', 'general', 'cli', json.dumps(conn))
            monkeypatch.setattr(agents, 'connection_brains', lambda store, cfg=None: [('claude', conn)])
            monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [sys.executable, FAKE_CLAUDE])
            for k, v in (('FAKE_CLAUDE_SPAWN', '1.5'), ('FAKE_CLAUDE_THINK', '1.0'), ('FAKE_CLAUDE_TPS', '2000')):
                monkeypatch.setenv(k, v)
            s.set_setting('assistant_ai', 'cli:claude', 'owner')
        else:
            from taskuary import browserview, llm
            opt = {'pick': 'connector:1', 'label': 'Northwind AI', 'model': '', 'type': 'openai'}
            monkeypatch.setattr(general, 'provider_options', lambda store: [opt])
            monkeypatch.setattr(general, 'default_pick', lambda store, task=None: 'connector:1')
            monkeypatch.setattr(llm, 'build_llm', lambda *a, **k: Brain())
            monkeypatch.setattr(browserview, 'installed', lambda: False)
            monkeypatch.setattr(browserview, 'can_set_up', lambda: False)
    from taskuary import server
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(server, 'store', s):
        yield kind, s, tid, TestClient(server.app)
        for t in list(terminal.SESSIONS.values()):
            try: t.close()
            except Exception: pass
    general.IDLED.pop(tid, None); acpcoding.IDLED.pop(tid, None); general.answered(tid, every=True)
    clipool.close('')


def read(kind, c, tid) -> dict:
    "The payload the page polls, as {lines: [the owner's lines in order], after: [what the agent said after the last of his], working, at}."
    if kind in ('general', 'api'):
        d = c.get(f'/api/tasks/{tid}/assistant').json()
        msgs = d['messages']
        said = [m for m in msgs if m['role'] == 'user' and not m.get('brief')]
        text = lambda m: ''.join(x.get('text', '') for x in m['content'])
        lines = [text(m) for m in said] + [w['text'] for w in d['waiting']]
        last = max((i for i, m in enumerate(msgs) if m['role'] == 'user' and text(m) == LINE), default=None)
        after = [text(m) for m in msgs[last + 1:] if m['role'] == 'assistant'] if last is not None else []
        before = [text(m) for m in msgs[:last] if m['role'] == 'assistant' and str(m.get('createdAt') or '') > str(said[-1].get('createdAt'))] if last is not None else []
    else:
        d = c.get(f'/api/tasks/{tid}/coding-chat').json()['data']
        ups = [u for ss in d['sessions'] for u in ss.get('updates') or []]
        mine = [i for i, u in enumerate(ups) if u['sessionUpdate'] == 'user_message_chunk' and (u.get('_meta') or {}).get('taskuary') == 'owner']
        lines = [ups[i]['content']['text'] for i in mine] + [w['text'] for w in d['waiting']]
        last = max((i for i in mine if ups[i]['content']['text'] == LINE), default=None)
        chunks = [u['content']['text'] for u in ups[last + 1:] if u['sessionUpdate'] == 'agent_message_chunk'] if last is not None else []
        after, before = [''.join(chunks)] if chunks else [], []
    return {'lines': lines, 'after': after, 'before': before, 'working': d['working'], 'at': d['turnStarted']}


def answered(r) -> bool: return any(a.strip() and ('heard:' in a or 'Looking.' not in a) for a in r['after'])     # a chat's answer; an ACP turn's last words


def first_turn(kind, s, tid, c, wait=True):
    "A turn before his line, on the same road: the task's agent up and once at work."
    c.post(f'/api/tasks/{tid}/assistant/messages', json={'text': 'look at the totals first'}, timeout=120) if wait else \
        threading.Thread(target=lambda: c.post(f'/api/tasks/{tid}/assistant/messages', json={'text': 'look at the totals first'}), daemon=True).start()
    if wait: assert until(lambda: not read(kind, c, tid)['working'], 60), 'the first turn ended'
    else: assert until(lambda: read(kind, c, tid)['working'] and general._live_of(tid) is not None, 30)


def put_in(state, kind, s, tid, c, monkeypatch):
    if state == 'never': return
    first_turn(kind, s, tid, c, wait=state != 'midturn')
    t = general._live_of(tid)
    if state == 'idled':
        monkeypatch.setattr(general, 'idle_for', lambda: 0); t.last -= 100
        assert t.idle_out(), t.idle_why()
        monkeypatch.setattr(general, 'idle_for', lambda: 3600)
    if state in ('ended', 'restart', 'closed'):
        t.close(); general.drop_session(tid); terminal.SESSIONS.pop(t.sid, None)
    if state == 'restart':                    # a new process: nothing in memory but the store
        general.IDLED.clear(); acpcoding.IDLED.clear(); general.answered(tid, every=True)
    if state == 'closed': s.update_task(tid, {'Status': 'done'}, 'owner')


@pytest.mark.parametrize('state', STATES)
@pytest.mark.parametrize('world', KINDS, indirect=True)
def test_a_typed_line_is_his_once_and_at_work_from_the_press_to_the_answer(world, state, monkeypatch):
    kind, s, tid, c = world
    if kind == 'pty': pytest.skip("a pane's turns are read from its CLI's own log, which the stand-in TUI does not write: see the report")
    put_in(state, kind, s, tid, c, monkeypatch)
    pressed = time.time()
    posted = threading.Thread(target=lambda: c.post(f'/api/tasks/{tid}/assistant/messages', json={'text': LINE}, timeout=120), daemon=True)
    posted.start()
    assert until(lambda: LINE in read(kind, c, tid)['lines'], 5), 'his line is kept by the time a read comes'
    bad, ats, end = [], [], time.time() + 60
    while time.time() < end:
        r = read(kind, c, tid)
        if answered(r): break
        # ...mid-turn, the turn at work finishes first, its answer over his line: what may never stand there is the turn HE asked for
        if r['lines'].count(LINE) != 1 or not r['working'] or (r['before'] and state != 'midturn'): bad.append((round(time.time() - pressed, 2), r['lines'].count(LINE), r['working'], r['before']))
        if r['at']: ats.append(r['at'])
        time.sleep(0.05)
    assert answered(r), f'the line was answered: {r}'
    assert bad == [], f'from the press to the answer the payload said (s, times his line, working, new turn before it): {bad[:6]}'
    if state != 'midturn':
        assert ats and len(set(ats)) == 1 and abs(ats[0] - pressed) < 1.0, f'the turn runs from the press, its clock never moving: {sorted(set(ats))[:4]} vs {pressed}'
    else: assert ats == sorted(ats), 'the clock never runs backwards'
    assert s.get_task(tid)['Status'] in ('open', 'in_progress')
    if state == 'closed':
        acts = [r['Action'] for r in s._rows("SELECT Action FROM audit WHERE EntityType='task' AND EntityId=?", (tid,))]
        assert 'reopened_by_typing' in acts and 'continue-session' not in acts, acts     # one reopen, by one rule, whichever agent
