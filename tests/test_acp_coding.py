"""A CODING SESSION OVER ACP (acpcoding.py, step 2 of docs/acp-transport.md): a task's claude opens as one ACP connection in its checkout,
every update drawn in the coding chat, its edit a diff row, its permission the owner's buttons, its box a prompt (batched while a turn
runs), Stop a cancel, a resume the agent's own - and in the registry every reader of a coding session already knows. An adapter that will
not start is today's terminal. The agent is tests/fake_acp_server.py; nothing real is installed, and the people are invented."""
import json, subprocess, sys, threading, time
from pathlib import Path
from unittest import mock

import pytest

from taskuary import acpcoding, agents, blackboard, codingchat, devphone, general, peers, permissions, session_artifacts, shellgate, terminal, waitroom
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


def test_a_turn_his_line_began_runs_from_his_press_and_its_clock_never_moves(world, monkeypatch):
    """The 0.3.11.50 release run (macOS): a coding turn's start read 097.551, then 097.771 - the turn's own start, then the CLI's prompt
    hook's time - after a press at 097.522: on screen "working Ns" restarting. It is his press, set once as the turn begins."""
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_THINK', '0.6')
    t = open_(s, tid, repo, seed=''); assert until(lambda: t.client and not t.busy)
    seen, done = [], threading.Event()
    def watch():
        while not done.is_set():
            if (v := general.line_state(s, tid)['turnStarted']): seen.append(v)
            time.sleep(0.005)
    w = threading.Thread(target=watch, daemon=True); w.start()
    pressed = time.time(); general.take_line(s, tid, 'Comment the totals function.', line_id='l-one')
    assert idle(t, 1); done.set(); w.join(2)
    assert seen and len(set(seen)) == 1 and abs(seen[0] - pressed) < 1.0, (sorted(set(seen))[:4], pressed)      # one value, from the press
    # ...and nothing after sets it again: the CLI's own prompt hook (hooks._events) moved it on a slow runner, where the press had gone
    was = t.turn_at; time.sleep(0.05); from taskuary import hooks; hooks._events(t, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'x'})
    assert t.turn_at == was


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
    assert [w['text'] for w in general.waiting_lines(s, tid)] == ['was this code completed?']        # kept as the owner's (general.take_line)
    assert t.cancel() and idle(t, 2)
    assert until(lambda: 'was this code completed?' in ' '.join([x for k, x in t.history if k == 'said'][-1].split()))
    assert codingchat.chat(s, tid)['waiting'] == []
    ups = [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk']
    assert any(u['content']['text'] == 'was this code completed?' and u['_meta']['taskuary'] == 'owner' for u in ups)      # drawn as theirs


def test_a_turn_that_fails_says_so_in_the_chat_and_typing_carries_on(world, monkeypatch):
    """A FAILURE IS KEPT WHERE IT HAPPENED (rules part 4): a turn the adapter ended with an error - an overloaded model - was said only on the
    session's Terminal; the chat, drawn from the kept updates, showed "Looking." and stopped, with nothing to say the turn had failed."""
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_FAIL', 'turn')
    t = open_(s, tid, repo, seed='look at the totals'); assert idle(t)
    [e] = [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'error']
    assert '529 Overloaded' in e['content']['text'] and general.CARRY_ON in e['content']['text'] and e['_meta'] == {'taskuary': 'error'}
    t.prompt('try again'); assert idle(t, 2)
    assert 'heard: try again' in [x for k, x in t.history if k == 'said'][-1]


def test_an_agent_that_dies_mid_turn_is_said_as_a_chat_cli_that_did(world, monkeypatch, tmp_path):
    """ONE SENTENCE FOR ONE FACT (the side-by-side walk, 2026-11-11): a coding agent that died holding a turn read "The turn failed: the agent stopped
    during session/prompt: - type to carry on."; a general chat's CLI that died the same way says clipool.MID_TURN."""
    from taskuary.clipool import MID_TURN
    s, tid, repo = world
    (script := tmp_path / 'script.json').write_text(json.dumps([{'when': 'break now', 'exit': 3}]))
    monkeypatch.setenv('FAKE_ACP_SCRIPT', str(script))
    t = open_(s, tid, repo, seed='break now')
    assert until(lambda: any(u['sessionUpdate'] == 'error' for u in codingchat.acp_updates(tid, t.sid)))
    [e] = [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'error']
    # ...and nothing of the process after it: "(the agent exited)" is the log's (the overnight walk, 2026-11-11)
    assert e['content']['text'] == f'{MID_TURN}.', e['content']['text']


def test_a_turn_its_own_close_ended_is_stopped_never_said_as_a_failure(world, monkeypatch):
    """THE OWNER'S LIVE APP (2026-11-11: "also says error like agent stopped mid turn????"): Mark done or Send and close while the coding agent
    works closes its session under the turn - its process is killed, the turn's request comes back empty, and the chat read "the agent
    stopped in the middle of its turn - nothing was sent again ... type to carry on" on a task he had just closed. And the process IS gone:
    where the tree-kill could not run, the adapter went on working and filed its answer on the closed task."""
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_HANG', '1')
    t = open_(s, tid, repo, seed='look at the totals')
    assert until(lambda: t.in_turn)
    with mock.patch('taskuary.spawn.run', side_effect=OSError('no taskkill here')): terminal.close(t.sid)
    assert until(lambda: t.client.p.poll() is not None), 'its process outlived the close'
    assert until(lambda: not t.in_turn)
    assert not [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'error'], 'a turn Taskuary stopped is not a failed one'


def test_a_note_from_the_waiting_room_is_drawn_as_the_owners_words(world):
    s, tid, repo = world
    t = open_(s, tid, repo, seed='look at the totals'); assert idle(t)
    out = waitroom.add(s, tid, 'use the rounding helper', 'owner')
    assert out['delivered'] == 1 and idle(t, 2)
    ups = [u for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk']
    assert ups[-2]['content']['text'] == 'use the rounding helper' and ups[-2]['_meta']['taskuary'] == 'owner'       # theirs
    assert ups[-1]['_meta'] == {'taskuary': 'brief'} and 'left 1 note' in ups[-1]['content']['text']   # Taskuary's framing, its brief


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
    assert any(u['content']['text'] == 'also the tax line' and (u.get('_meta') or {}).get('taskuary') == 'owner' for u in ups)              # theirs, in the chat
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
    ups = [u['content']['text'] for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk' and (u.get('_meta') or {}).get('taskuary') == 'owner']
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
    mine = [i for i, u in enumerate(ups) if u['sessionUpdate'] == 'user_message_chunk' and (u.get('_meta') or {}).get('taskuary') == 'owner' and u['content']['text'] == 'merge and deploy']
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
    ups = [u['content']['text'] for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'user_message_chunk' and (u.get('_meta') or {}).get('taskuary') == 'owner']
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
    # ...a stranger with NO SENDER TO TRUST - Taskuary's own words from what it read: an untrusted sender's task starts no agent at all (origin.hold)
    s.add_message({'TaskId': t, 'Channel': 'assistant', 'FromEmail': 'someone@vendor.example', 'Status': 'routed'})
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


def test_a_strangers_coding_session_on_a_cli_with_no_reviewer_reads_only_and_never_over_acp(floor):
    "codex has no reviewer (clis.AUTO): a stranger's task runs in its read-only sandbox (clis.READONLY) on the pty's floor - never ACP."
    s, t, repo = floor
    s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'codex', 'acp_cmd': FAKE, 'cwd': str(repo)}))
    with mock.patch.object(terminal, 'Term') as T:
        terminal.open_session(s, 'coding', t, None, str(repo), 32, 110, 'owner', seed_fn=lambda here: 'look')
    argv = [str(x) for x in T.call_args.args[0]]
    assert T.call_args.kwargs['mode'] == 'look' and argv[argv.index('--sandbox') + 1] == 'read-only' and '--dangerously-bypass-approvals-and-sandbox' not in argv


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


def test_a_user_role_update_the_adapter_sent_itself_is_the_agents_not_the_owners(world):
    """ONLY WHAT THE OWNER TYPED IS HIS (codingchat.owned, 2026-11-10): an adapter sends user-role messages of its own - a slash command's
    output - and the chat drew them in his bubble. Every line he types is recorded (general.take_line), so one that is not his is the agent's;
    an old record of his, written before lines were marked, is still his."""
    s, tid, repo = world
    t = open_(s, tid, repo, seed='look at the totals'); assert idle(t)
    s.add_comment(tid, 'owner', general.USER_TYPE, 'is the tax line right?')          # a line he typed, kept as his
    codingchat.record_update(tid, t.sid, {'sessionUpdate': 'user_message_chunk', 'content': {'type': 'text', 'text': 'is the tax line right?'}})
    codingchat.record_update(tid, t.sid, {'sessionUpdate': 'user_message_chunk', 'content': {'type': 'text', 'text': 'Compacted the conversation.'}})
    ups = [u for ss in codingchat.chat(s, tid)['sessions'] for u in ss.get('updates') or [] if u['sessionUpdate'] == 'user_message_chunk']
    who = {u['content']['text']: u['_meta']['taskuary'] for u in ups}
    assert who['is the tax line right?'] == 'owner' and who['Compacted the conversation.'] == 'agent'


def test_a_coding_agent_is_told_its_duties_about_drafts_once_and_each_turn_after_carries_the_facts_alone(world, monkeypatch):
    """The recorded walk, 2026-11-11: a coding agent said "the draft still waits on your Send" in every turn - each turn's facts came with the
    rules again (latest wins, how to withdraw). Told once, as a chat's agent is (selfclose.DRAFTS_ONCE); a turn carries what is new."""
    from taskuary import acp, selfclose
    s, tid, repo = world
    told, real = [], acp.ACPClient.prompt
    monkeypatch.setattr(acp.ACPClient, 'prompt', lambda self, text, sent=None: (told.append(text), real(self, text, sent=sent))[1])
    t = open_(s, tid, repo, seed='look at the totals'); assert idle(t)
    # ...the mail and its draft after the session began (a sender nobody vouched for changes how a session is opened - not this test's)
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'ConversationId': 'c1', 'Channel': 'email', 'Subject': 'Ledger totals', 'Status': 'routed',
                         'BodyText': 'What does total() return?', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example'})
    s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'Channel': 'email', 'DraftText': 'Hi Gail, the sum plus tax. Alex'})
    for n, w in enumerate(('and the tax line?', 'thanks'), 2): t.prompt(w); assert idle(t, n)
    assert len(told) == 3 and all('THE DRAFT WAITING NOW' in x for x in told[1:]), told
    assert [x.count(selfclose.WITHDRAW_LINE) for x in told] == [0, 1, 0] and [x.count(selfclose.LATEST_LINE) for x in told] == [0, 1, 0]
    assert not any(selfclose.NO_NEW_LINE in x for x in told)


def test_the_taskuary_command_is_in_reach_of_every_session_however_the_app_was_started(tmp_path, monkeypatch):
    """The recorded walk, 2026-11-11: a coding agent told the owner "the taskuary command is not installed in this shell, so I could not read
    the board" - its rules send it to `taskuary --board`, and the app had been started by its interpreter with no such script on PATH."""
    import shutil
    from taskuary import config
    monkeypatch.setattr(config, 'home', lambda: tmp_path); monkeypatch.setattr(terminal, '_OWN', {})
    monkeypatch.setattr(shutil, 'which', lambda name, path=None, **k: None)
    path = terminal.session_env('coding', 7, str(tmp_path), sid='s1')['PATH'].split(terminal.os.pathsep)
    assert path[0] == str(tmp_path / 'bin') and sys.executable in (tmp_path / 'bin' / 'taskuary.cmd').read_text(encoding='utf-8')
    assert '-m taskuary.cli "$@"' in (tmp_path / 'bin' / 'taskuary').read_text(encoding='utf-8')
    # ...and where PATH finds it already, a session's PATH is the app's own
    monkeypatch.setattr(terminal, '_OWN', {}); monkeypatch.setattr(shutil, 'which', lambda name, path=None, **k: 'taskuary')
    assert 'PATH' not in terminal.session_env('coding', 7, str(tmp_path), sid='s1')


def test_a_peers_note_never_begins_a_turn_on_an_agent_he_stopped_and_rides_the_turn_his_next_line_begins(world, monkeypatch):
    """The recorded stop, 2026-11-11: he stopped the agent, and half a minute on a note from another task's agent began a turn under "You
    stopped the agent" that only said again what stood above it. His stop holds until he speaks; the note goes in with his words."""
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_HANG', '1')
    t = open_(s, tid, repo, seed='look at the totals'); assert until(lambda: t.in_turn)
    assert general.stop_turn(s, tid) and idle(t)
    other = s.create_task({'Title': 'Add a subtotal', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
    s.add_peer_note(other, tid, 'task', '', 'totals.py is free again')
    assert peers.deliver(s, tid) == {'delivered': 0, 'state': 'stopped'} and peers.tick(s) == 0 and t.turns == 1 and not t.busy
    general.take_line(s, tid, 'Carry on.', line_id='l-on')
    assert idle(t, 2) and not s.peer_notes(tid)
    told = next(x for k, x in reversed(t.history) if k == 'brief')
    assert 'totals.py is free again' in told and 'Carry on.' in told, told


@pytest.mark.parametrize('hold', ['1', 'said'], ids=['never answered', 'answered before the stop'])
def test_a_line_typed_into_a_turn_he_then_stops_is_answered_by_one_turn_under_the_stop(world, monkeypatch, tmp_path, hold):
    """The recorded stop, 2026-11-11: two lines typed into a coding turn joined it (steered), he pressed Stop, and nothing ever answered them -
    the CLI took them off its queue and was interrupted. Nothing he typed is dropped: what the stopped turn took in and never spoke to goes
    back as ONE turn under the stop, where a chat's waiting lines enter - drawn once, where it stood. A line the agent had spoken to
    before the stop begins nothing; and a second Stop ends that turn too, with no third."""
    from taskuary import conversation
    s, tid, repo = world
    rules = tmp_path / 'rules.json'; rules.write_text(json.dumps([{'when': '(?s)mention rounding.*came in since.*Thanks', 'first': 'Both answered.'},
                                                                 {'when': 'stopped your turn', 'wait': 60, 'first': 'Rounded.'}]), encoding='utf-8')
    for k, v in {'FAKE_ACP_HANG': '1', 'FAKE_ACP_STEER': '1', 'FAKE_ACP_STEER_ECHO': '1', 'FAKE_ACP_STEER_HOLD': hold, 'FAKE_ACP_SCRIPT': str(rules)}.items(): monkeypatch.setenv(k, v)
    t = open_(s, tid, repo, seed=''); assert until(lambda: t.client and not t.busy)
    general.take_line(s, tid, 'Comment the totals function.', line_id='l-one'); assert until(lambda: t.in_turn and t.steerable())
    general.take_line(s, tid, 'And mention rounding.', line_id='l-two')
    mine = lambda: [u['content']['text'] for u in codingchat.acp_updates(tid, t.sid) if (u.get('_meta') or {}).get('taskuary') == 'owner']
    assert until(lambda: mine() == ['Comment the totals function.', 'And mention rounding.'] and not t._echoes), (mine(), t._echoes)
    if hold == 'said': assert until(lambda: any(u['content']['text'] == 'On it. ' for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'agent_message_chunk'))
    assert general.stop_turn(s, tid)
    kinds = lambda: [x['kind'] for x in conversation.items(s, tid)['items']]
    if hold == 'said':
        assert idle(t) and t.turns == 1 and not conversation.items(s, tid)['working'] and kinds()[-1] == 'press'
        return
    assert until(lambda: t.turns == 1 and t.in_turn), (t.turns, t.busy, t.stop_reason)
    got = conversation.items(s, tid)
    assert got['working'] and not got['pending'] and [x['kind'] for x in got['items']][-2:] == ['press', 'turn'], got['items']
    assert [x['id'] for x in got['items'] if x['kind'] == 'line'] == ['l-one', 'l-two']             # drawn once, where it stood: above his stop
    told = next(x for k, x in reversed(t.history) if k == 'brief')
    assert 'And mention rounding.' in told and 'stopped your turn' in told and sum('mention rounding' in x for k, x in t.history if k == 'you') == 1
    # ...and stopped again, it stays stopped: the lines were handed over, and his stop is his
    assert general.stop_turn(s, tid) and idle(t, 2)
    assert until(lambda: not conversation.items(s, tid)['working']) and t.turns == 2 and not t._q
    # ...and NOT DROPPED (decided 2026-11-12: a line stopped twice is still answered): it rides on the next turn he starts
    general.take_line(s, tid, 'Thanks.', line_id='l-three')
    assert until(lambda: any(u['content']['text'] == 'Both answered.' for u in codingchat.acp_updates(tid, t.sid) if u['sessionUpdate'] == 'agent_message_chunk'))
    assert idle(t, 3) and not t._owed


def test_a_waiting_card_never_moves_under_a_turn_that_only_stopped_at_his_allow(world, monkeypatch):
    """Recorded on the real CLI, 2026-11-12: a reply waited for his Send under the first answer; the next turn stopped at a step for his
    Allow once and the reply card moved down under it, went back up when he pressed (the turn at work again), down again as the turn went
    on under his press, and down once more at its end - four places in twenty seconds. A card never moves (the owner, 2026-11-12: "nothing
    ever goes backwards"): where it was first drawn it stays, greyed from the moment his line moved past it."""
    from taskuary import conversation
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_ASK', 'git push origin main'); monkeypatch.setattr(shellgate, 'trusted', lambda *a, **k: '')
    monkeypatch.setenv('FAKE_ACP_THINK', '0.6')              # the step comes once the line's hand-over has settled, as a real model's does
    t = open_(s, tid, repo, seed=''); assert until(lambda: t.client and not t.busy)
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail - the totals are commented.', 'Reason': 'reply'})
    assert until(lambda: time.time() >= conversation.ep(s.get_review(rid)['CreatedAt']) + 1)        # (a stamp is a whole second)
    live = lambda: [(x.get('id', '') if x['kind'] == 'turn' else 'own', c['status']) for x in conversation.items(s, tid)['items']
                    for c in ([x] if x['kind'] == 'card' else x.get('cards') or []) if c['review'] == rid]
    assert live() == [('own', 'pending')]
    general.take_line(s, tid, 'Push it.', line_id='l-one')
    assert until(lambda: permissions.pending(tid, s) and any(x['kind'] == 'turn' and x['steps'] for x in conversation.items(s, tid)['items'])), t.history
    assert live() == [('own', 'passed')], conversation.items(s, tid)['items']                    # his line moved past it: greyed where it stood
    permissions.answer(s, tid, permissions.pending(tid, s)[0]['id'], 'allow_once')
    assert idle(t, 1)
    # ...waited on as state: the turn's last updates are kept by the session's reader a beat after its prompt returns (a CI runner read the
    # list at `idle` while it still ended on his press, the words under it not yet kept)
    tail = lambda: [x['kind'] for x in conversation.items(s, tid)['items']][-3:]
    assert until(lambda: tail() == ['turn', 'press', 'turn']), json.dumps([conversation.items(s, tid)['items'], s._rows('SELECT * FROM heard WHERE TaskId=?', (tid,)),
                                                                         codingchat.acp_updates(tid, t.sid)], default=str)[:8000]
    got = conversation.items(s, tid)['items']; turns = [x for x in got if x['kind'] == 'turn']
    assert live() == [('own', 'passed')], got                                                        # ...and it never moved
    assert not turns[-2]['cards'] and not turns[-1]['cards']


def test_a_coding_chat_reads_in_the_same_order_once_its_session_has_closed(world, monkeypatch):
    """Recorded on the real CLI, 2026-11-12 (Send and close on a coding task, then the task opened again): his two lines stood first, then
    the reply card by itself, then both turns - every step of the closed session stamped at the moment its transcript was filed, which is
    its END. A session's record reads at its steps' own times, live or closed."""
    from taskuary import conversation
    s, tid, repo = world
    t = open_(s, tid, repo, seed=''); assert until(lambda: t.client and not t.busy)
    general.take_line(s, tid, 'Comment the totals function.', line_id='l-one'); assert idle(t, 1)
    general.take_line(s, tid, 'And mention rounding.', line_id='l-two'); assert idle(t, 2)
    shape = lambda: [(x['kind'], x.get('id', '')) for x in conversation.items(s, tid)['items']]
    was = shape(); assert [k for k, _ in was] == ['line', 'turn', 'line', 'turn'], was
    end = max(x['ended'] for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn')
    assert until(lambda: time.time() >= end + 1.1)                                         # (a stamp is a whole second: it closes in a later one)
    t.close(); assert until(lambda: not codingchat._live(tid) and s._rows('SELECT 1 FROM transcript WHERE TaskId=?', (tid,)))
    # ...in the same order - under it only the task's own line that its run is over (conversation.items `n:left`)
    assert shape() == [*was, ('note', 'n:left')], shape()


def test_a_line_is_never_the_answer_to_a_step_whose_buttons_are_a_beat_away(world, monkeypatch):
    """A step that waits on his Allow is on the rail a beat before its buttons exist (permissions.ask writes the request down first). A
    line handed over in that beat was written down as the step's answer - which refused the step and filed its Approve card instead.
    It waits by the box, as a line under the buttons does."""
    from taskuary import workerstate as ws
    s, tid, repo = world
    t = open_(s, tid, repo, seed=''); assert until(lambda: t.client and not t.busy)
    ws.record(s, tid, t.sid, 'approval_needed', request_id='q:0123456789:1', text='The agent wants to run `git push origin main`',
              choices=['Allow once', 'Reject'], source='permission')                              # ...the request, its PENDING row not yet made
    assert waitroom.state(s, tid)[0] == 'asking' and not permissions.pending(tid, s)
    assert waitroom.add(s, tid, 'What does that push carry?', 'owner')['state'] == 'held_ask'
    assert [e['Kind'] for e in s.worker_events(tid)][-1] == 'approval_needed' and len(s.waiting_notes(tid)) == 1


def test_a_held_step_stays_the_one_lit_card_when_he_asks_the_coding_agent_a_question(world, monkeypatch):
    """The owner's live coding task, 2026-11-11 ("the question has 2 approve buttons?"): his question set the held step aside and the agent
    raised it again beside the greyed one. It stays lit IN ITS TURN (2026-11-12: nothing moves), his line stands with the turn at work under
    it, and the same step run again by that session is the card that waits (tests/test_conversation_list.py has the chat's)."""
    from taskuary import conversation, shellgate
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_THINK', '0.6'); monkeypatch.setattr(shellgate, 'trusted', lambda *a, **k: '')
    t = open_(s, tid, repo, seed=''); assert until(lambda: t.client and not t.busy)
    general.take_line(s, tid, 'Fix the tax rows.', line_id='l-one')
    # ...a failure says what the session was doing (red twice on Windows runners, never here): its state, its record, what it was handed
    assert idle(t, 1), json.dumps({'busy': t.busy, 'turns': t.turns, 'in_turn': t.in_turn, 'q': len(t._q), 'stop': t.stop_reason, 'history': t.history[-8:],
                                   'updates': codingchat.acp_updates(tid, t.sid)[-8:]}, default=str)[:6000]
    hold = lambda: shellgate.check(s, tid, t.sid, 'git push origin main', 'Bash', str(repo))
    hold(); [rv] = s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))
    general.take_line(s, tid, 'What does that step change?', line_id='l-two', wait=False)
    got = conversation.items(s, tid)
    assert [(x['kind'], x.get('state', '')) for x in got['items']][-2:] == [('line', ''), ('turn', 'starting')] and not got['pending'], got['items']
    assert idle(t, 2); hold()
    assert [(r['ReviewId'], r['Status']) for r in s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))] == [(rv['ReviewId'], 'pending')]
    turns = [x for x in conversation.items(s, tid)['items'] if x['kind'] == 'turn']
    assert [c['status'] for c in turns[0]['cards']] == ['pending'] and not any(t['cards'] for t in turns[1:])


def _restart(s, tid, t):
    "Taskuary goes away under a session and comes back: nothing of the session's own endings runs, and start-up repairs what it left."
    t.alive, t.closing = False, True; t.client.close(); terminal.SESSIONS.clear(); general.answered(tid, every=True)
    terminal.recover_after_restart(s); general.keep_cut_turns(s)


def test_a_coding_turn_a_restart_cut_says_so_under_his_line_and_the_line_that_waited_goes_in_by_itself(world, monkeypatch):
    """The recorded restart, 2026-11-11 (a coding task over ACP): his lines stood in the chat as heard with nothing under them - no turn, no
    word that it was cut, nothing at work. As a chat's: the cut turn stays where it was cut and says so, the line that waited by the box
    stays there, and the session comes back for it without him typing again."""
    from taskuary import conversation, taskstate
    s, tid, repo = world
    monkeypatch.setenv('FAKE_ACP_HANG', '1')
    t = open_(s, tid, repo, seed=''); assert until(lambda: t.client and not t.busy)
    general.take_line(s, tid, 'Comment the totals function.', line_id='l-one')
    assert until(lambda: t.in_turn and any(u.get('sessionUpdate') == 'agent_message_chunk' for u in codingchat.acp_updates(tid, t.sid)))
    general.take_line(s, tid, 'And mention rounding.', line_id='l-two')                     # ...mid-turn, to an adapter that does not steer: by the box
    _restart(s, tid, t)
    got = conversation.items(s, tid); shape = [(x['kind'], x.get('id', '')[:5], x.get('text') or '') for x in got['items']]
    assert [k for k, *_ in shape] == ['line', 'turn', 'note'] and shape[2][2] == general.CUT_ON.strip('_'), shape
    assert not got['working'] and [x['id'] for x in got['pending']] == ['l-two'] and taskstate.state(s, s.get_task(tid)) != 'working'
    # ...the waiting room's next look brings the session back for the line that waited: heard under the cut, a turn at work under it
    cut_at = conversation.ep(next(x['at'] for x in got['items'] if x['kind'] == 'note'))
    assert until(lambda: time.time() >= cut_at + 1)                                         # (a stamp is a whole second, and no restart is inside one)
    waitroom.tick(s)
    assert until(lambda: (g := conversation.items(s, tid))['working'] and not g['pending'] and [x['kind'] for x in g['items']][-2:] == ['line', 'turn']), conversation.items(s, tid)
    assert [x['id'] for x in conversation.items(s, tid)['items'] if x['kind'] == 'line'] == ['l-one', 'l-two']
    # ...and with nothing waiting, the cut says how he carries on - once (a restart with no turn under way says nothing)
    t2 = terminal.session_for(tid); assert until(lambda: t2.in_turn)
    _restart(s, tid, t2); _restart(s, tid, t2)
    notes = [x['text'] for x in conversation.items(s, tid)['items'] if x['kind'] == 'note']
    assert notes == [general.CUT_ON.strip('_'), general.CUT.strip('_')] and general.CARRY_ON in notes[-1], notes
