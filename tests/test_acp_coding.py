"""A CODING SESSION OVER ACP (acpcoding.py, step 2 of docs/acp-transport.md): a task's claude opens as one ACP connection in its checkout,
every update drawn in the coding chat, its edit a diff row, its permission the owner's buttons, its box a prompt (batched while a turn
runs), Stop a cancel, a resume the agent's own - and in the registry every reader of a coding session already knows. An adapter that will
not start is today's terminal. The agent is tests/fake_acp_server.py; nothing real is installed, and the people are invented."""
import json, subprocess, sys, threading, time
from pathlib import Path
from unittest import mock

import pytest

from taskuary import acpcoding, agents, blackboard, codingchat, devphone, peers, permissions, session_artifacts, shellgate, terminal, waitroom
from taskuary.store import MemoryStore
from taskuary import llm, origin

pytestmark = pytest.mark.acp
FAKE = [sys.executable, str(Path(__file__).parent / 'fake_acp_server.py')]


def until(cond, secs=20):
    end = time.time() + secs
    while time.time() < end:
        if cond(): return True
        time.sleep(0.05)
    return cond()


@pytest.fixture
def world(tmp_path, monkeypatch):
    "A checkout with one file, a coding profile on claude whose adapter is the fake, and a task on it."
    (tmp_path / 'artifacts').mkdir()
    monkeypatch.setattr(session_artifacts, 'root', lambda: tmp_path / 'artifacts')
    repo = tmp_path / 'ledger'; repo.mkdir()
    (repo / 'totals.py').write_text('def total(a, tax):\n    return a + tax\n', encoding='utf-8')
    git = lambda *a: subprocess.run(['git', '-C', str(repo), *a], check=True, capture_output=True)
    git('init', '-q'); git('config', 'user.name', 'Alex Doyle'); git('config', 'user.email', 'alex@northwind.example')
    git('add', '.'); git('commit', '-qm', 'start')
    s = MemoryStore()
    s.set_setting(agents.DEV_MODE, '1', 'owner')
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'acp_cmd': FAKE, 'cwd': str(repo)}))
    tid = s.create_task({'Title': 'Comment the ledger totals', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [FAKE[0]])
    monkeypatch.setattr(terminal, 'pretrust', lambda *a, **k: False)
    monkeypatch.setattr(acpcoding, 'FELL_BACK', set())
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        yield s, tid, repo
        for t in list(terminal.SESSIONS.values()):
            try: t.close()
            except Exception: pass


def open_(s, tid, repo, seed='add a one-line comment to the top of totals.py', **kw):
    return terminal.open_session(s, 'coding', tid, None, str(repo), 32, 110, 'owner', seed_fn=(lambda here: seed) if seed else None, **kw)


def idle(t, turns=1): return until(lambda: not t.busy and t.turns >= turns)


def test_a_coding_task_on_claude_runs_over_acp_and_its_turn_is_the_chat(world, monkeypatch):
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_CODE', str(repo / 'totals.py'))
    t = open_(s, tid, repo, model='sonnet@low')
    assert isinstance(t, acpcoding.ACPCoding) and terminal.SESSIONS[t.sid] is t
    assert idle(t)
    assert (repo / 'totals.py').read_text(encoding='utf-8').startswith('# keeps the ledger totals')
    said = [x for k, x in t.history if k == 'said'][-1]
    assert 'model=sonnet effort=low' in said and 'mode=default' in said           # the router's gears, the mode that makes it ask
    ups = codingchat.acp_updates(tid, t.sid)
    first = ups[0]
    assert first['sessionUpdate'] == 'user_message_chunk' and first['_meta'] == {'taskuary': 'brief'} and 'one-line comment' in first['content']['text']
    assert all(u.get('_at') for u in ups)                                            # stamped: the chat places each turn under its mail
    assert any(b.get('type') == 'diff' for u in ups if u['sessionUpdate'] == 'tool_call_update' for b in u.get('content') or [])
    chat = codingchat.chat(s, tid)
    assert chat['sessions'][-1]['source'] == 'acp' and chat['live']['transport'] == 'acp' and chat['live']['terminal']
    assert t.ext_id == 'sess_fake_1' and s.resumable_session(tid)['ExtId'] == 'sess_fake_1'
    # its Terminal: the command and its streamed output, never a blank pane
    assert '$' in t.scrollback() and 'git status --short' in t.scrollback() and 'M totals.py' in t.scrollback()


def test_its_registry_entry_is_what_the_board_peers_and_the_phone_read(world, monkeypatch):
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_CODE', str(repo / 'totals.py'))
    t = open_(s, tid, repo); assert idle(t)
    row = next(r for r in terminal.listing() if r['sid'] == t.sid)
    assert row['taskId'] == tid and row['cli'] == 'claude' and row['transport'] == 'acp' and row['phase'] == 'parked' and row['alive']
    assert 'totals.py' in row['files'] and row['work']['files'] and row['work']['todos']        # the Board card: its files and its list
    assert terminal.for_task(tid)['sid'] == t.sid and terminal.session_for(tid) is t
    assert waitroom.state(s, tid)[0] == 'parked'
    other = s.create_task({'Title': 'Rename the tax flag', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    p = blackboard.peers(s, str(repo), exclude_tid=other)
    assert p and p[0]['tid'] == tid and 'totals.py' in p[0]['files']
    assert t in peers._cli_sessions()
    assert devphone.rows(s)[0]['tid'] == tid and devphone.rows(s)[0]['state'] == 'idle at its prompt'
    assert 'Agent: Added the comment.' in terminal.transcript_for(s, tid)[0]
    # ...and while it touches a file, file:line is what a peer reads about it
    t.touched[str(repo / 'totals.py')]['at'] = time.time()
    assert t.touching() == ['totals.py:1']


def test_a_push_it_asks_for_is_the_owners_buttons(world, monkeypatch):
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_ASK', 'git push origin main')
    monkeypatch.setattr(shellgate, 'trusted', lambda *a, **k: '')
    def press():
        assert until(lambda: permissions.pending(tid, s))
        p = permissions.pending(tid, s)[0]
        assert 'git push origin main' in p['line']
        permissions.answer(s, tid, p['id'], 'allow_once')
    th = threading.Thread(target=press, daemon=True); th.start()
    t = open_(s, tid, repo)
    assert idle(t); th.join(5)
    assert any(k == 'said' and x.startswith('granted') for k, x in t.history)


def test_the_box_while_it_works_waits_and_goes_in_as_one_prompt_and_stop_cancels(world, monkeypatch):
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_HANG', '1')
    t = open_(s, tid, repo, seed='look at the totals')
    assert until(lambda: t.client and t.busy and any(u.get('sessionUpdate') == 'agent_message_chunk' for u in codingchat.acp_updates(tid, t.sid)))
    terminal.type_into(t, 'also the tax line')                  # the chat's box, the waiting room, a relay: a prompt, never keys
    t.prompt('and keep it short')
    assert waitroom.state(s, tid)[0] == 'working'
    assert t.cancel() and until(lambda: t.stop_reason == 'cancelled' or sum(k == 'said' for k, _ in t.history) >= 1)
    assert idle(t, 2)
    said = [x for k, x in t.history if k == 'said'][-1]
    assert 'heard: also the tax line and keep it short' in ' '.join(said.split()) and 'turn=2' in said


def test_a_note_from_the_waiting_room_is_drawn_as_the_owners_words(world):
    s, tid, repo = world
    t = open_(s, tid, repo, seed='look at the totals'); assert idle(t)
    out = waitroom.add(s, tid, 'use the rounding helper', 'owner')
    assert out['delivered'] == 1 and idle(t, 2)
    ups = [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk']
    assert ups[-2]['content']['text'] == 'use the rounding helper' and '_meta' not in ups[-2]       # theirs
    assert ups[-1]['_meta'] == {'taskuary': 'brief'} and 'queued' in ups[-1]['content']['text']   # Taskuary's framing, its brief


def test_a_resume_is_the_agents_own_conversation(world, monkeypatch):
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_RESUME', '1')
    t = open_(s, tid, repo, seed='carry on', resume='sess_fake_1')
    assert idle(t)
    assert 'resumed=sess_fake_1' in [x for k, x in t.history if k == 'said'][-1] and t.ext_id == 'sess_fake_1'
    # ...and a quiet one opens with nothing typed: back at its prompt
    t.close(); terminal.SESSIONS.clear()
    q = terminal.open_session(s, 'coding', tid, None, str(repo), 32, 110, 'owner', resume='sess_fake_1')
    assert until(lambda: q.client and not q.busy) and not [u for u in codingchat.acp_updates(tid, q.sid) if u['sessionUpdate'] == 'user_message_chunk']


class Pane:
    "A pty stand-in: the fallback's terminal, without starting a real one."
    def __init__(self, argv, cwd, label, task_id=None, agent=None, rows=32, cols=110, store=None, cli='', mode='full'):
        self.sid, self.argv, self.cwd, self.task_id, self.agent, self.cli, self.alive, self.started = 'pty-1', argv, cwd, task_id, agent, cli, True, ''
        self.seeded, self.accepted, self.ext_id = '', None, ''
    def seed(self, text): self.seeded = text
    def info(self, *a, **k): return {'sid': self.sid}


def test_an_adapter_that_will_not_start_is_todays_terminal_said_once(world, monkeypatch):
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_FAIL', 'init')
    monkeypatch.setattr(terminal, 'Term', Pane)
    t = open_(s, tid, repo)
    assert isinstance(t, acpcoding.ACPCoding)
    assert until(lambda: 'pty-1' in terminal.SESSIONS) and t.sid not in terminal.SESSIONS
    pane = terminal.SESSIONS['pty-1']
    assert pane.seeded == 'add a one-line comment to the top of totals.py'             # the same seed, typed in as today
    assert any('did not start over ACP' in (c.get('Body') or '') and 'its terminal' in (c.get('Body') or '') for c in s.list_comments(tid))
    assert acpcoding.FELL_BACK == {'claude'}


@pytest.mark.parametrize('how', ['switch off', 'no adapter', 'a stranger'])
def test_the_switch_off_a_cli_without_acp_and_a_strangers_task_keep_the_terminal(world, monkeypatch, how):
    s, tid, repo = world
    monkeypatch.setattr(terminal, 'Term', Pane)
    if how == 'switch off': s.set_setting(agents.ACP_SETTING, '0', 'owner')
    if how == 'no adapter': s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'gemini', 'cwd': str(repo)}))
    if how == 'a stranger': monkeypatch.setattr('taskuary.origin.launch_mode', lambda *a, **k: 'auto')
    assert isinstance(open_(s, tid, repo), Pane)


# ── a stranger's task: never over ACP, on either road ────────────────────────────────────────────────────────────────────────
def stranger(s):
    t = s.create_task({'Title': 'Fix the import warning', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'})
    assert origin.of_task(s, t)[0] == 'stranger'
    return t


@pytest.fixture
def floor(world, monkeypatch, tmp_path):
    "A stranger's task beside the owner's, the switch on, the adapters present, and a claude new enough to run one."
    s, tid, repo = world
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 299))
    (tmp_path / 'temp').mkdir(); monkeypatch.setattr('tempfile.gettempdir', lambda: str(tmp_path / 'temp'))
    monkeypatch.setattr(terminal, 'Term', Pane)
    assert agents.acp_on(s)
    return s, stranger(s), repo


class Pane2(Pane):
    "The pty stand-in, keeping how it was started."
    def __init__(self, argv, cwd, label, task_id=None, agent=None, rows=32, cols=110, store=None, cli='', mode='full'):
        super().__init__(argv, cwd, label, task_id, agent, rows, cols, store, cli, mode); self.mode = mode


@pytest.mark.parametrize('resume', ['', 'sess_fake_1'])
def test_a_strangers_coding_session_on_claude_keeps_its_terminal_and_its_floor(floor, monkeypatch, resume):
    """A stranger's task on claude runs 'auto' (origin.launch_mode): the CLI's own reviewer, --strict-mcp-config, its session settings
    file with the floor's hooks, a trimmed environment (Term mode 'auto' -> strict) - in a pty, new or resumed, never over ACP."""
    s, t, repo = floor
    monkeypatch.setattr(terminal, 'Term', Pane2)
    p = terminal.open_session(s, 'coding', t, None, str(repo), 32, 110, 'owner', seed_fn=lambda here: 'look', resume=resume or None)
    assert isinstance(p, Pane2) and p.mode == 'auto' and not any(terminal.is_acp(x) for x in terminal.SESSIONS.values())
    a = [str(x) for x in p.argv]
    assert a[a.index('--permission-mode') + 1] == 'auto' and '--strict-mcp-config' in a and '--dangerously-skip-permissions' not in a
    assert a[a.index('--settings') + 1] == origin.session_settings(s, t)
    assert '--mcp-config' not in a                              # Taskuary's toolbox is trusted work's only


def test_a_strangers_coding_session_on_a_cli_with_no_reviewer_starts_nowhere(floor):
    "codex has no reviewer (clis.AUTO): a stranger's task is refused - no pty, and no ACP session either."
    s, t, repo = floor
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'codex', 'acp_cmd': FAKE, 'cwd': str(repo)}))
    with pytest.raises(ValueError, match='no built-in reviewer'):
        terminal.open_session(s, 'coding', t, None, str(repo), 32, 110, 'owner', seed_fn=lambda here: 'look')
    assert not terminal.SESSIONS


@pytest.mark.parametrize('mode', ['full', 'auto', 'look', ''])
def test_the_acp_gate_refuses_a_strangers_task_whatever_mode_it_is_handed(floor, mode):
    s, t, repo = floor
    prof = {'cmd': 'claude'}
    assert not acpcoding.wanted(s, prof, mode, t)
    assert acpcoding.wanted(s, prof, 'full', s.create_task({'Title': 'mine', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner'))


def _general(s, t, **kw):
    brain = llm.make_cli_llm(s, 'coding', task_id=t, **kw)
    with mock.patch.object(agents, 'run_cli', return_value=('ok', 'sid', '')) as run: brain('', 'hi')
    return run.call_args.args[0]


@pytest.mark.parametrize('how', [dict(cli_tools=True), dict(research=True), dict(research='web'), dict()])
def test_the_general_road_refuses_a_strangers_task_too(floor, how):
    """A general agent's run on a stranger's task - with hands ('auto': the reviewer, its settings, a trimmed env, its own folder), a
    look (no tools), or the classifier (every tool off) - stays on argv: acp_ok False, and the road refuses a trimmed env on its own."""
    s, t, repo = floor
    p = _general(s, t, **how)
    assert not p.get('acp_ok') and not agents._acp_road(p, s)
    if how: assert p.get('strict_env') is True
    assert not agents._acp_road({**p, 'acp_ok': True}, s) if p.get('strict_env') else True
    mine = _general(s, s.create_task({'Title': 'mine', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner'), cli_tools=True)
    assert mine.get('acp_ok') is True and agents._acp_road(mine, s)          # the owner's own run with hands is the one that goes
