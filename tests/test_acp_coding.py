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


def test_what_each_turn_used_is_on_the_task_s_ai_use(world, monkeypatch):
    "The adapter's count of each turn, added onto the session's route row - a session over ACP files no CLI log on exit, as a pane does."
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_CODE', str(repo / 'totals.py')); monkeypatch.setenv('FAKE_ACP_USAGE', '1')
    t = open_(s, tid, repo)
    assert idle(t)
    row = s.brain_route_of_session(t.sid)
    assert (row['Job'], row['TaskId'], row['Ran'], row['TokensIn'], row['Cached'], row['TokensOut'], row['Calls']) ==            ('coding', tid, 'claude-opus-5-5', 3412, 3000, 250, 1)


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


def test_a_line_typed_while_it_works_is_kept_shown_and_taken_by_the_next_turn(world, monkeypatch):
    """The owner, 2026-11-08: "i asked another question and the text was never sent into the prompt". A line typed mid-turn - in the chat's box
    or the session's Terminal - is the waiting room's: on the task, drawn as theirs on every screen (codingchat `waiting`), and the next turn's.
    And the chat's clock counts from this turn's start, never the session's or the owner's line days back (codingchat.live_of `turnStarted`)."""
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_HANG', '1')
    t = open_(s, tid, repo, seed='look at the totals')
    assert until(lambda: t.in_turn) and not t.steerable()
    t.started, t.turn_at = '2026-11-06 14:43:44', time.time() - 5                           # a session opened two days ago, its turn 5 s old
    live = codingchat.live_of(t)
    assert live['working'] and abs(live['turnStarted'] - (time.time() - 5)) < 2
    t.write('was this code completed?\r')                                                   # ...typed in its Terminal
    assert until(lambda: [w['text'] for w in codingchat.chat(s, tid)['waiting']] == ['was this code completed?'])
    assert s.waiting_notes(tid)[0]['CreatedBy'] == 'owner'
    assert t.cancel() and idle(t, 2)
    assert until(lambda: 'was this code completed?' in ' '.join([x for k, x in t.history if k == 'said'][-1].split()))
    assert codingchat.chat(s, tid)['waiting'] == []
    ups = [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk']
    assert any(u['content']['text'] == 'was this code completed?' and '_meta' not in u for u in ups)      # drawn as theirs


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


def test_words_typed_while_it_works_go_into_the_turn_where_the_adapter_steers(world, monkeypatch):
    """MID-TURN STEERING (both coding adapters advertise _meta.steering at initialize): the box's words join the running turn through
    _session/steering - drawn as the owner's, no second turn - rather than waiting for its end. Without the advertisement they wait (above)."""
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_HANG', '1'); monkeypatch.setenv('FAKE_ACP_STEER', '1')
    t = open_(s, tid, repo, seed='look at the totals')
    assert until(lambda: t.in_turn) and t.steerable()
    out = waitroom.add(s, tid, 'also the tax line', 'owner')
    assert (out['delivered'], out['state']) == (1, 'steered') and s.waiting_notes(tid) == []
    assert idle(t)
    said = [x for k, x in t.history if k == 'said'][-1]
    assert 'steered:' in said and 'also the tax line' in said and 'turn=1' in said and t.turns == 1
    ups = [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk']
    assert any(u['content']['text'] == 'also the tax line' and '_meta' not in u for u in ups)              # theirs, in the chat
    assert any('while the agent worked' in c['Body'] for c in s.list_comments(tid))
    # ...and at rest nothing steers: the next words are a turn of their own
    assert not t.steerable()
    t.prompt('and keep it short'); assert idle(t, 2)
    assert 'heard: and keep it short' in [x for k, x in t.history if k == 'said'][-1]


def test_a_steer_the_adapter_echoes_back_is_one_line_not_two(world, monkeypatch):
    """The owner typed one line mid-turn and the chat drew it twice in one bubble: claude-agent-acp echoed the steer back as a
    user_message_chunk, beside the line Taskuary draws itself - and the chat joins a run of the owner's chunks into one."""
    s, tid, repo = world
    for k in ('FAKE_ACP_HANG', 'FAKE_ACP_STEER', 'FAKE_ACP_STEER_ECHO'): monkeypatch.setenv(k, '1')
    t = open_(s, tid, repo, seed='look at the totals')
    assert until(lambda: t.in_turn) and t.steerable()
    assert waitroom.add(s, tid, 'merge and deploy', 'owner')['state'] == 'steered'
    assert idle(t)
    ups = [u['content']['text'] for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk' and '_meta' not in u]
    assert ups.count('merge and deploy') == 1 and not t._echoes


def test_a_steered_line_is_drawn_above_the_answer_even_when_the_turn_ends_first(world, monkeypatch):
    """The adapter answers the steer, replies and ends the turn in one breath: drawn only once the steer's own reply woke its thread, the
    owner's line landed under the agent's answer to it - and a turn read as over had no line at all (CI on Windows, 2026-11-10)."""
    from taskuary import acp
    s, tid, repo = world
    for k in ('FAKE_ACP_HANG', 'FAKE_ACP_STEER', 'FAKE_ACP_STEER_ECHO'): monkeypatch.setenv(k, '1')
    real = acp.ACPClient.steer
    def slow(self, text, **kw): got = real(self, text, **kw); time.sleep(0.5); return got        # the turn ends before the steer returns
    monkeypatch.setattr(acp.ACPClient, 'steer', slow)
    t = open_(s, tid, repo, seed='look at the totals')
    assert until(lambda: t.in_turn) and t.steerable()
    assert waitroom.add(s, tid, 'merge and deploy', 'owner')['state'] == 'steered'
    assert idle(t)
    ups = codingchat.acp_updates(tid, t.sid)
    mine = [i for i, u in enumerate(ups) if u['sessionUpdate'] == 'user_message_chunk' and '_meta' not in u and u['content']['text'] == 'merge and deploy']
    answer = [i for i, u in enumerate(ups) if u['sessionUpdate'] == 'agent_message_chunk' and u['content']['text'].startswith('steered:')]
    assert len(mine) == 1 and answer and mine[0] < answer[0], ups
    until(lambda: not t._drawn)                                                                    # the slowed steer returns: nothing left marked


@pytest.mark.parametrize('steer', [True, False], ids=['steered', 'queued'])
def test_a_note_two_deliveries_race_for_is_handed_over_once(world, monkeypatch, steer):
    """The owner typed one line while the agent worked and the chat drew it twice: their POST's deliver steered it in, and before that
    deliver marked it handed over (a slow store, 4 s on the live app) the turn ended and the clock's deliver (waitroom.later) read it as
    still waiting and handed it over again - one note, two prompts. Steered into the turn, or queued for a session at rest: once."""
    s, tid, repo = world
    for k in ('FAKE_ACP_HANG', 'FAKE_ACP_STEER') if steer else (): monkeypatch.setenv(k, '1')
    t = open_(s, tid, repo, seed='look at the totals')
    assert until(lambda: t.in_turn) if steer else idle(t)
    real, first = s.deliver_waiting, threading.Event()
    def slow(wids, how):
        if not first.is_set(): first.set(); time.sleep(1.5)
        real(wids, how)
    monkeypatch.setattr(s, 'deliver_waiting', slow)
    th = threading.Thread(target=lambda: waitroom.add(s, tid, 'are both fixes pushed?', 'owner')); th.start()
    assert first.wait(10)
    waitroom.deliver(s, tid)                                               # the clock's look, while the POST's is still marking
    th.join(10)
    assert until(lambda: not t.busy, 10)
    ups = [u['content']['text'] for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk' and '_meta' not in u]
    assert ups.count('are both fixes pushed?') == 1, ups


def test_a_coding_session_idle_past_its_period_closes_quietly_and_the_next_input_brings_it_back(world, monkeypatch):
    """QUIET WHEN IDLE, as the general agent (general.idle_out, its period clipool.IDLE_SECONDS): nothing said in the chat, the chat the
    same, and the next input reopens the same run (its sid) on the agent's own conversation - session/resume."""
    from taskuary import clipool
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_RESUME', '1')
    later = waitroom.later; monkeypatch.setattr(waitroom, 'later', lambda *a, **k: None)  # a turn's end ticks the clock; its sweep raced ours on slow CI
    t = open_(s, tid, repo, seed='look at the totals'); assert idle(t)
    assert acpcoding.idle_sweep() == [] and t.alive                                                    # not idle long enough
    # ...the note first, then the short period: added after it, a sweep on slow CI closed the session in the gap (2026-11-08)
    s.add_waiting(tid, 'a held note', 'owner')
    monkeypatch.setattr(clipool, 'IDLE_SECONDS', 0.1); time.sleep(0.2)
    assert t.idle_why() == 'notes wait for it' and acpcoding.idle_sweep() == []
    s.deliver_waiting([w['WId'] for w in s.waiting_notes(tid)], 'typed')
    said_before, sid = [c['Body'] for c in s.list_comments(tid)], t.sid
    assert acpcoding.idle_sweep() == [tid]
    assert not t.alive and t.sid not in terminal.SESSIONS and acpcoding.idled(tid, s)
    assert [c['Body'] for c in s.list_comments(tid)] == said_before                                     # not a word on the task
    chat = codingchat.chat(s, tid)
    assert chat['live'] and chat['live']['sid'] == sid and not chat['live']['working']                  # the same chat, at rest
    assert any(x['sid'] == sid and x['source'] == 'acp' for x in chat['sessions'])
    monkeypatch.setattr(clipool, 'IDLE_SECONDS', 30 * 60); monkeypatch.setattr(waitroom, 'later', later)
    waitroom.add(s, tid, 'now round the tax', 'owner')
    q = terminal.session_for(tid)
    assert q is not t and q.sid == sid and isinstance(q, acpcoding.ACPCoding) and not acpcoding.idled(tid, s)
    assert idle(q)
    said = [x for k, x in q.history if k == 'said'][-1]
    assert 'now round the tax' in said and 'resumed=sess_fake_1' in said
    assert any(k == 'brief' and 'look at the totals' in x for k, x in q.history)                         # its history carried on
    assert not any('Reopened' in c['Body'] for c in s.list_comments(tid)) and len(terminal.SESSIONS) == 1   # one wake, never a fresh start beside it


def test_the_plan_it_writes_is_in_the_coding_chat(world, monkeypatch):
    "The agent's plan (an ACP `plan` update) is kept beside the task as it arrives and handed to the chat, every entry and its status."
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_CODE', str(repo / 'totals.py'))
    t = open_(s, tid, repo); assert idle(t)
    ups = codingchat.chat(s, tid)['sessions'][-1]['updates']
    plans = [u for u in ups if u['sessionUpdate'] == 'plan']
    assert len(plans) == 2
    assert [(e['content'], e['status']) for e in plans[-1]['entries']] == [('Read the file', 'completed'), ('Add the comment', 'completed')]
    assert [(e['content'], e['status']) for e in plans[0]['entries']][-1] == ('Add the comment', 'in_progress')
    assert t.witness.snapshot([], str(repo), '')['todos']


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
    assert a[a.index('--mcp-config') + 1].endswith(f'TQ-{t}.stranger.mcp.json')   # ...the owner's harmless tools only (agenttools.STRANGER_TOOLS)


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
