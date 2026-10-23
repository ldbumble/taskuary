"""What makes the Assistant on a CLI brain answer quickly (the owner, 2026-10-20) - its process started before it is asked, its words
drawn as they are written - and what must not change for it: the answer, the action, one process per chat."""
import json, os, sys, threading
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import agents, clipool, concierge, general
from taskuary.store import MemoryStore

FAKE = os.path.join(os.path.dirname(__file__), 'fake_claude.py')


@pytest.fixture
def fast_fake(monkeypatch, tmp_path):
    """tests/fake_claude.py with no start-up and a quick model, saying `first` to anything."""
    script = tmp_path / 'script.json'
    script.write_text(json.dumps([{'when': '.', 'first': 'It is on the table now.\nCALL: {"kind": "pipe.list", "params": {}}', 'then': 'Ten things.'}]))
    log = tmp_path / 'fake.log'
    monkeypatch.setenv('FAKE_CLAUDE_SCRIPT', str(script)); monkeypatch.setenv('FAKE_CLAUDE_LOG', str(log))
    for k, v in (('FAKE_CLAUDE_SPAWN', '0'), ('FAKE_CLAUDE_THINK', '0'), ('FAKE_CLAUDE_TPS', '2000')): monkeypatch.setenv(k, v)
    monkeypatch.setattr(agents, '_resolve_cmd', lambda name: [sys.executable, FAKE])
    yield log
    clipool.close('')


def _store():
    s = MemoryStore()
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose']}))
    s.set_setting(concierge.AI_KEY, 'cli:claude', 't')
    return s


def _pids(log):
    return [json.loads(l)['pid'] for l in log.read_text().splitlines() if '"ev": "ready"' in l] if log.exists() else []


def test_the_chat_is_warmed_with_the_process_its_first_ask_takes(fast_fake):
    s = _store()
    assert concierge.warm(s, wait=True) is True
    tid = general.dock_task(s, 'owner')[0]['TaskId']
    assert [x['key'] for x in clipool.live()] == [f'{concierge.LIVE_KEY}:{tid}']
    assert concierge.warm(s, wait=True) is False                    # one already live: nothing more is started
    concierge.say(s, "what's waiting on me")
    assert len(set(_pids(fast_fake))) == 1                          # the ask - both its rounds - ran on the warmed process
    turns = [json.loads(l) for l in fast_fake.read_text().splitlines() if '"ev": "turn"' in l]
    assert [t['n'] for t in turns] == [1, 2]


def test_warm_does_nothing_for_an_api_brain_or_a_cli_that_keeps_no_conversation(fast_fake):
    s = _store(); s.set_setting(concierge.AI_KEY, 'connector:1', 't')
    assert concierge.warm(s, wait=True) is False
    s = _store(); s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p']}))   # no stream-json: one shot per call
    assert concierge.warm(s, wait=True) is False
    assert clipool.live() == [] and _pids(fast_fake) == []


def test_every_round_of_a_turn_runs_on_one_set_of_instructions(fast_fake):
    """The CLI is launched with the turn's instructions (--system-prompt-file, by content): a round on other ones restarted it."""
    s = _store()
    files = set()
    real_run = clipool.run
    def run(key, cmd, *a, **k):
        files.add(cmd[cmd.index('--system-prompt-file') + 1]); return real_run(key, cmd, *a, **k)
    with mock.patch.object(clipool, 'run', run):
        concierge.say(s, "what's waiting on me")
        concierge.say(s, 'and the next one?')
    assert len(files) == 1


def test_the_assistants_words_stream_and_its_call_line_never_does(fast_fake):
    s = _store()
    words = []
    concierge.say(s, 'bring up the first one', trace=lambda kind, name, detail: kind == 'words' and words.append(detail))
    assert 'It is on the table now.' in words and words[-1] == 'Ten things.'      # each round's words, the look-up's answer last
    assert not any('CALL' in w or '{' in w for w in words)


@pytest.mark.parametrize('half, shown', [
    ('Here it is', 'Here it is'),
    ('Here it is.\nCAL', 'Here it is.'),                             # might yet be a CALL line: held back
    ('Here it is.\nCALL: {"kind": "pipe', 'Here it is.'),
    ('Pick one.\nOPTIONS: a | b', 'Pick one.'),
    ('{"kind": "next"}', ''),
    ('Done.\n```json\n{}', 'Done.'),
    ('Calling Marcus now', 'Calling Marcus now'),                    # a word that starts like the marker is still a word
])
def test_spoken_is_only_what_the_owner_reads(half, shown):
    assert agents.spoken(half) == shown


def test_a_brain_with_no_partial_flag_streams_no_words(fast_fake):
    """Only the Assistant asks for its words (--include-partial-messages); a general agent's kept conversation draws none."""
    s = MemoryStore()
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json', '--verbose']}))
    from taskuary import llm
    seen = []
    b = llm.make_cli_llm(s, 'claude', keep='general:9', trace=lambda kind, *a: seen.append(kind))
    assert b('SYS', 'hello')
    assert 'words' not in seen


def _args(log):
    return [json.loads(l)['args'] for l in log.read_text().splitlines() if '"ev": "ready"' in l]


@pytest.mark.parametrize('old', [False, True])
def test_the_assistants_cli_reads_no_user_settings_and_an_older_cli_runs_as_before(fast_fake, monkeypatch, old):
    """The owner, 2026-10-21: the Assistant's CLI runs without their user-level Claude settings - their user-wide hooks POST to the
    app on every prompt and stop, 0.3-0.5 s a turn. A claude whose --help has no --setting-sources runs without it, and answers."""
    monkeypatch.setattr(agents, '_FLAGS', {})
    if old: monkeypatch.setenv('FAKE_CLAUDE_OLD', '1')
    s = _store()
    assert concierge.say(s, "what's waiting on me")['say'] == 'Ten things.'
    [args] = _args(fast_fake)
    assert (args[args.index('--setting-sources') + 1] == 'project,local') if not old else '--setting-sources' not in args


def test_other_kept_conversations_keep_the_owners_settings(fast_fake, monkeypatch):
    """Coding and general agents keep their hooks: only the brain that asks (the Assistant's) leaves them out."""
    monkeypatch.setattr(agents, '_FLAGS', {})
    from taskuary import llm
    s = MemoryStore()
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json', '--verbose']}))
    assert llm.make_cli_llm(s, 'claude', keep='general:9')('SYS', 'hello')
    [args] = _args(fast_fake)
    assert '--setting-sources' not in args


def _live_proc():
    [lv] = list(clipool._POOL.values())
    return lv


@pytest.mark.parametrize('when', ['between turns', 'before its first turn', 'mid-turn'])
def test_a_cli_that_dies_is_restarted_and_the_turn_answered_as_if_nothing_happened(fast_fake, monkeypatch, when):
    """The installed claude updated itself mid-session (the real-CLI walk, 2026-10-21) and every later turn read "Broken pipe".
    A process that ends - between turns, warmed and never used, or in the middle of a turn - is started once more and the turn
    sent again: the owner sees the answer, never the failure."""
    s = _store()
    if when == 'between turns': concierge.say(s, 'hello')
    else: concierge.warm(s, wait=True)
    first = _live_proc()
    if when == 'mid-turn':
        monkeypatch.setenv('FAKE_CLAUDE_THINK', '1.0')
        threading.Timer(0.4, first.p.kill).start()
    else: first.p.kill(); first.p.wait(5)
    out = concierge.say(s, "what's waiting on me")
    assert out['say'] == 'Ten things.' and not out.get('error')
    assert _live_proc() is not first and _live_proc().alive()


def test_an_agent_with_tools_killed_mid_turn_is_never_sent_its_turn_again(fast_fake, monkeypatch, tmp_path):
    """Only a turn with no side effects is sent twice. A general agent's CLI has its tools: killed part-way through a turn it
    may have done some of the work, so the turn ends saying so (Continue picks it up) - and one killed BETWEEN turns, which
    never got the message, is still started again and answers."""
    from taskuary import llm
    s = MemoryStore()
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--output-format', 'stream-json', '--verbose']}))
    b = llm.make_cli_llm(s, 'claude', keep='general:9', cwd=str(tmp_path), gear='main')
    assert b('SYS', 'hello')
    lv = _live_proc()
    assert '--tools' not in lv.cmd                                  # the agent's hands are on
    lv.p.kill(); lv.p.wait(5)
    assert b('SYS', 'again') and _live_proc() is not lv            # between turns: never delivered, so restarted and answered
    turns = lambda: [json.loads(l) for l in fast_fake.read_text().splitlines() if '"ev": "turn"' in l]
    monkeypatch.setenv('FAKE_CLAUDE_THINK', '1.0')
    lv = _live_proc(); lv.p.kill(); lv.p.wait(5)
    b('SYS', 'warm it up')                                          # a fresh process that reads the new think time
    lv, n = _live_proc(), len(turns())
    threading.Timer(0.4, lv.p.kill).start()
    with pytest.raises(RuntimeError, match='stopped in the middle of its turn'):
        b('SYS', 'do the work')
    assert len(turns()) == n + 1                                     # sent once, never again


def test_a_general_agent_killed_mid_turn_reads_stopped_offers_continue_and_continue_resumes_it(fast_fake, monkeypatch):
    """After its CLI dies part-way through a turn the turn is not sent again - so the session ends, its conversation saved: the task
    reads stopped (taskstate), the detail says how the run ended (runEnded, which draws the bar's Continue: taskWorkspace.barContinues),
    and Continue (/continue-work) picks that same conversation back up on a new process."""
    import time
    from taskuary import server, taskstate, workerstate
    s = MemoryStore()
    s.upsert_agent('claude', 'general', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose']}))
    tid = s.create_task({'Title': 'Research the vendor', 'Kind': 'general', 'Status': 'open'}, 'owner')
    conn = {'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose']}
    monkeypatch.setattr(agents, 'connection_brains', lambda store, cfg=None: [('claude', conn)])     # Claude Code connected
    monkeypatch.setenv('FAKE_CLAUDE_THINK', '1.0')
    sess = general.start_session(s, tid, pick='cli:claude')
    assert sess.send_prompt('look the vendor up')
    sid = sess.cli_sid
    lv = _live_proc()
    threading.Timer(0.4, lv.p.kill).start()
    with pytest.raises(RuntimeError, match='stopped in the middle of its turn'):
        sess.send_prompt('now write it up')
    assert len(_args(fast_fake)) == 1                                # nothing started again, not even as a fresh conversation
    for _ in range(50):
        if not sess.alive: break
        time.sleep(0.05)
    assert not sess.alive and workerstate.ended(s, tid) == 'failed'
    assert taskstate.state(s, s.get_task(tid)) == 'stopped'
    monkeypatch.setattr(server, 'store', s)
    c = TestClient(server.app)
    assert c.get(f'/api/tasks/{tid}').json()['runEnded'] == 'failed'
    assert c.post(f'/api/tasks/{tid}/continue-work', json={}).json()['continued']
    for _ in range(100):
        args = _args(fast_fake)
        if len(args) == 2 and any('"ev": "turn"' in l and '"n": 1' in l for l in fast_fake.read_text().splitlines()[-3:]): break
        time.sleep(0.05)
    resumed = _args(fast_fake)[-1]
    assert resumed[resumed.index('--resume') + 1] == sid                # the same conversation, on a new process
    for _ in range(100):                                                # ...and once its turn is answered, nothing is left live
        live = general.session_for(tid)
        if live is None or not live.busy: break
        time.sleep(0.05)
    if live: live.close(learn=False)
    general.drop_session(tid)


def test_a_cli_that_dies_again_on_restart_is_said_plainly(fast_fake, monkeypatch):
    s = _store()
    concierge.say(s, 'hello')
    monkeypatch.setenv('FAKE_CLAUDE_BROKEN', '1')                   # the restart finds the CLI half-updated
    _live_proc().p.kill(); _live_proc().p.wait(5)
    out = concierge.say(s, "what's waiting on me")
    assert out.get('error') and out['say'].startswith('My AI tool stopped, and stopped again when I restarted it')


def test_continue_lit_with_notes_carries_them_and_says_so():
    """"Rerun the agent with these notes: use the new template" lit Continue and dropped the notes (the real-CLI walk, 2026-10-20):
    the light carries them - Continue's box opens holding them - and the line says they go with it. Without notes, as before."""
    from tests import assistant_walk as W
    s = W.world()
    with mock.patch('taskuary.ingest._spawn'):
        said = lambda call: concierge.say(s, 'rerun the agent', key='msg:17', llm=lambda *a, **k: 'Sending it back.\nCALL: ' + json.dumps(call))
        out = said({'kind': 'agent.continue', 'params': {'ref': 'TQ-0012', 'note': 'use the new template'}})
        assert out['light']['verb'] == 'continue' and out['light']['note'] == 'use the new template'
        assert out['say'] == 'Lit Continue on TQ-0012 with your notes: use the new template'
        assert 'your notes are in its box' in out['light']['line']
        bare = said({'kind': 'agent.continue', 'params': {'ref': 'TQ-0012'}})
        assert bare['say'] == 'Lit Continue on TQ-0012.' and 'note' not in bare['light']


def test_the_tool_text_tells_marking_read_from_putting_down():
    """"mark the FYI read" over one FYI chose Next on the real CLI: the decision and the tool now say which is which."""
    from taskuary import toolcatalog
    assert 'mark the FYI read' in toolcatalog.PURPOSE['pipe.clear'] and 'never next' in toolcatalog.PURPOSE['pipe.clear']
    assert 'marked nothing' in toolcatalog.DECISIONS['next'] and 'pipe.clear' in toolcatalog.DECISIONS['next']


def test_the_page_opening_new_chat_and_a_new_brain_each_warm_it(monkeypatch):
    from taskuary import server
    s = _store()
    calls = []
    monkeypatch.setattr(server, 'store', s)
    monkeypatch.setattr(server, '_warm_assistant', lambda: calls.append('warm'))
    c = TestClient(server.app)
    assert c.get('/api/concierge').status_code == 200
    assert c.post('/api/concierge/ai', json={'pick': ''}).status_code == 200
    assert c.post('/api/assistant/dock/new').status_code == 200
    assert calls == ['warm'] * 3


def test_the_demo_says_its_assistant_is_scripted(monkeypatch):
    """Settings' "Which AI speaks here" said "No AI connected" while the demo's scripted brain answered (the UX walk, 2026-10-22)."""
    from taskuary import server, demo
    monkeypatch.setattr(server, 'store', _store())
    monkeypatch.setattr(server, '_warm_assistant', lambda: None)
    c = TestClient(server.app)
    monkeypatch.setenv(demo.FLAG, '1')
    assert c.get('/api/concierge').json()['scripted'] is True
    monkeypatch.delenv(demo.FLAG)
    assert c.get('/api/concierge').json()['scripted'] is False
