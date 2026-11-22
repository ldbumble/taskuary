"""An agent run is never killed for running long, and a turn that did run out of time is never said as stopped by you (2026-11-04).

A Codex agent building a marketing plan, a site and a zip of materials hit the CLI's 1500 s turn limit. Its Agent section read
"Codex exit 1: timed out after 1500s." over "You stopped it and its report is written." - the owner had stopped nothing - and offered
Try again and Run another agent, while the files it had made were sitting in its folder: Continue was the move. The owner's ruling: "we
can't have timeout as it's an active agent" - an agent run ends when it finishes or is stopped. One-shot look-ups keep their leash."""
import io, json, threading
from unittest import mock

from taskuary import agents, clipool, funnel, general, terminal, workerstate as ws
from taskuary.store import MemoryStore


def task(s): return s.create_task({'Title': 'Build the spring campaign kit', 'Summary': 'A marketing plan, a site and a zip of materials.',
                                   'Kind': 'general', 'Status': 'in_progress', 'Assignee': 'agent:assistant'}, 'router')


class Hung:
    "A CLI that says which thread it is on, then works past its limit until it is killed."
    def __init__(self):
        self.stdin, self.stderr, self.returncode, self.killed = io.StringIO(), io.StringIO(''), None, threading.Event()
        self.stdout = self._out()
    def _out(self):
        yield json.dumps({'type': 'thread.started', 'thread_id': 'th-kit'}) + '\n'
        self.killed.wait(10)
    def kill(self): self.returncode = 1; self.killed.set()
    def wait(self, timeout=None): self.killed.wait(10); return self.returncode
    def poll(self): return self.returncode


def test_a_cli_turn_past_its_limit_raises_timed_out_with_the_thread_it_was_on():
    with mock.patch.object(agents, '_resolve_cmd', return_value=['codex']), mock.patch('taskuary.spawn.popen', return_value=Hung()), \
         mock.patch.object(agents, '_git', return_value=''):
        try: agents.run_cli({'cmd': 'codex', 'args': ['exec'], 'timeout': 0.3}, 'build the kit', lambda *a: None)
        except clipool.TimedOut as e: err = e
        else: raise AssertionError('a turn past its limit says it timed out')
    assert 'timed out after' in str(err) and err.session_id == 'th-kit'


def test_an_agent_run_has_no_time_limit_and_one_shot_calls_keep_theirs():
    from taskuary import clis, llm as llm_mod
    assert not any('timeout' in c for c in clis.KNOWN)                   # no preset leash for any CLI
    s = MemoryStore(); s.upsert_agent('codex', 'codex', 'cli', json.dumps({'cmd': 'codex', 'timeout': 1500}))     # ...a saved one is dropped
    seen = []
    def run_cli(prof, prompt, trace, resume=None, **k): seen.append(prof.get('timeout')); return 'ok', None, None
    with mock.patch('taskuary.agents.run_cli', run_cli):
        llm_mod.make_cli_llm(s, 'codex', research=True, keep='general:7', task_id=7)('SYS', 'USER')   # a general agent's turn
        llm_mod.make_cli_llm(s, 'codex', cli_tools=True, keep='general:7', task_id=7)('SYS', 'USER')  # ...with hands
        llm_mod.make_cli_llm(s, 'codex', cwd='C:/work/ledger')('SYS', 'USER')                         # an agent scheduled into a folder
        llm_mod.make_cli_llm(s, 'codex', research=True)('SYS', 'USER')                                # a one-shot look-up
        llm_mod.make_cli_llm(s, 'codex')('SYS', 'USER')                                               # the classifier
    assert seen == [None, None, None, 1500, 300]


class Slow(Hung):
    "A CLI that works a long while, then finishes on its own."
    def _out(self):
        yield json.dumps({'type': 'thread.started', 'thread_id': 'th-kit'}) + '\n'
        yield json.dumps({'type': 'item.completed', 'item': {'id': 'm1', 'type': 'agent_message', 'text': 'The kit is built.'}}) + '\n'
        self.returncode = 0; self.killed.set()


def test_a_long_agent_turn_is_never_cut_by_time():
    started = []
    class Clock(threading.Timer):
        def start(self): started.append(self.interval)
    with mock.patch.object(agents, '_resolve_cmd', return_value=['codex']), mock.patch('taskuary.spawn.popen', return_value=Slow()), \
         mock.patch.object(agents, '_git', return_value=''), mock.patch.object(agents.threading, 'Timer', Clock):
        out, sid, _ = agents.run_cli({'cmd': 'codex', 'args': ['exec']}, 'build the kit', lambda *a: None)
    assert out == 'The kit is built.' and sid == 'th-kit' and started == []         # no kill was ever armed
    assert clipool.Live.turn.__defaults__[-1] is None and clipool.run.__kwdefaults__['timeout'] is None   # the kept process waits as long


def timed_out_turn(s, tid, sid='th-kit'):
    with mock.patch.object(general, '_selected', return_value=('cli:codex', 'Codex', '')):
        ses = general.GeneralSession(s, tid)
    def hit(*a, **k): raise clipool.TimedOut('Codex exit 1: timed out after 1500s', sid)
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=hit), mock.patch.object(ses, 'close') as close, \
         mock.patch('taskuary.continuity.can_resume', return_value=True), mock.patch('threading.Timer') as timer:
        try: ses.send_prompt('Build the kit.', brief=True)
        except general.Stopped: pass
        else: raise AssertionError('a turn that ran out of time ends its start - nothing queues it again')
    for c in timer.call_args_list: c.args[1](**c.kwargs.get('kwargs', {}))      # the session's close, run here
    return ses, close


def test_a_turn_that_ran_out_of_time_pauses_its_run_and_keeps_its_thread():
    s = MemoryStore(); tid = task(s)
    ses, close = timed_out_turn(s, tid)
    last = s.last_worker_event(tid, skip=ws.NOTES)
    assert last['Kind'] == 'stopped' and last['Source'] == general.TIMED_OUT
    assert last['Text'] == "The agent's run was cut off by a time limit while it was still working. What it made so far is kept - type to carry on from there."
    assert ses.cli_sid == 'th-kit'                       # Continue resumes the thread it was on
    close.assert_called_once_with(learn=False, report=False)


def test_a_timed_out_run_says_it_ran_out_of_time_never_that_you_stopped_it():
    s = MemoryStore(); tid = task(s)
    timed_out_turn(s, tid)
    s.tag_task(tid, terminal.SAVED, True, 'owner')      # a saved mark however it got there cannot speak over the run's own last word
    with mock.patch.object(ws, '_live', return_value=False): line = funnel.not_started_why(s, tid)
    assert 'cut off by a time limit' in line and 'You stopped it' not in line
    with mock.patch.object(ws, '_live', return_value=False):
        assert ws.ended(s, tid) == 'stopped'               # the page offers Continue (taskWorkspace.barContinues), not Try again
        story = funnel.agent_story(s, tid)
    assert story['kind'] != 'failed' and 'cut off by a time limit' in story['line']
    assert any(st['text'] == 'Cut off by a time limit' for st in story['steps'])


def test_a_new_turn_clears_the_saved_mark():
    s = MemoryStore(); tid = task(s)
    s.tag_task(tid, terminal.SAVED, True, 'owner')
    timed_out_turn(s, tid)
    assert terminal.SAVED not in str(s.get_task(tid).get('Tags') or '')


# ── A STOPPED TURN, ON EVERY ROAD (workstream 6): one contract, clipool.Cancelled with its conversation, carried as a time-out's is ────────
import sys
from pathlib import Path
import pytest
HERE = Path(__file__).parent
CLAUDE = ['-p', '--output-format', 'stream-json', '--verbose']
ROADS = {'argv': ({'cmd': 'claude', 'args': CLAUDE}, False),
         'kept': ({'cmd': 'claude', 'args': CLAUDE + ['--input-format', 'stream-json']}, True),
         'acp': ({'cmd': sys.executable, 'args': [], 'acp': [str(HERE / 'fake_acp_server.py')], 'acp_ok': True}, True)}


import contextlib
@contextlib.contextmanager
def on_road(road, monkeypatch, env, rules, keep=None):
    """A general session whose turns run on a REAL road (agents.run_cli under llm.make_cli_llm, the stand-in CLIs): (session, the resume id
    each turn was handed, an Event set at the agent's own first event of a turn). `keep` False runs a kept road's turns one-shot."""
    from taskuary import llm as llm_mod
    prof, kept = ROADS[road]
    keep = kept if keep is None else keep
    for k, v in {'FAKE_CLAUDE_SCRIPT': str(rules), 'FAKE_ACP_SCRIPT': str(rules), 'FAKE_CLAUDE_SPAWN': '0', 'FAKE_CLAUDE_THINK': '0', **env}.items():
        monkeypatch.setenv(k, v)
    s = MemoryStore(); tid = task(s); s.upsert_agent('fake', 'fake', 'cli', json.dumps({**prof, 'cwd': str(HERE)}))
    with mock.patch.object(general, '_selected', return_value=('cli:fake', 'Fake', '')):
        ses = general.GeneralSession(s, tid)
    began, resumes, real = threading.Event(), [], agents.run_cli
    def run_cli(p, prompt, trace, resume=None, **k): resumes.append(resume); return real(p, prompt, trace, resume=resume, **k)
    def build(store, **kw):
        def heard(kind, name, detail=None):
            if kind not in ('prompt', 'tool'): began.set()          # the agent's own first event: its turn is under way
            kw['trace'](kind, name, detail)
        return llm_mod.make_cli_llm(store, 'fake', cancel=kw.get('cancel'), resume=kw.get('resume'), keep=kw.get('keep') if keep else None,
                                    task_id=kw.get('task_id'), trace=heard, cli_tools=True)
    fake = [sys.executable, str(HERE / 'fake_claude.py')] if prof['cmd'] == 'claude' else [sys.executable]
    steps = agents.ACPSteps.__call__                                    # ...an ACP agent's first session update is its first event
    monkeypatch.setattr(agents.ACPSteps, '__call__', lambda self, u: (steps(self, u), began.set())[0])
    try:
        with mock.patch.object(general.llm_mod, 'build_llm', side_effect=build), mock.patch.object(agents, 'run_cli', run_cli), \
             mock.patch.object(agents, '_resolve_cmd', return_value=fake), mock.patch('taskuary.continuity.can_resume', return_value=True), \
             mock.patch.object(ses, '_end_soon'):
            yield ses, resumes, began
    finally: clipool.close(ses.keep())


@pytest.mark.parametrize('road', ROADS)
def test_a_stopped_first_turn_keeps_its_conversation_and_the_next_turn_resumes_it(road, tmp_path, monkeypatch):
    """ACP answered a Stop with ('', its id) - a blank success - and that id was kept; the one-shot and kept roads raised a bare 'cancelled'
    and kept none: a stopped FIRST turn lost its conversation and the next opened a fresh one. Every road raises clipool.Cancelled with the
    conversation it was on, and the turn's caller keeps it as it keeps a time-out's. Driven through the caller (GeneralSession.send_prompt) on
    the real roads, the stop pressed once the agent has begun (its first event), never on a clock."""
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': 'Pull the first ledger', 'anywhere': True, 'wait': 120, 'first': 'never'}]))
    with on_road(road, monkeypatch, {'FAKE_ACP_HANG': '1', 'FAKE_ACP_SCRIPT': ''}, rules) as (ses, resumes, began):     # ACP: hangs till stopped
        pressed = {}
        def press(): pressed['after it began'] = began.wait(60); ses.stop()
        threading.Thread(target=press, daemon=True).start()
        try: ses.send_prompt('Pull the first ledger.', brief=True)
        except general.Stopped: pass
        else: raise AssertionError('a stopped turn is stopped')
        assert pressed == {'after it began': True}, pressed
        # ...said in one word on every road: "stopped", never the kind's own name ("cancelled")
        assert [e['detail']['result'] for e in ses.trace if e.get('type') == 'error'][-1:] == ['stopped'], ses.trace[-3:]
        first = ses.cli_sid
        assert first, 'the stopped first turn kept the conversation it was on'
        ses.send_prompt('And the second one.', brief=True)
    assert resumes == [None, first], resumes                     # ...and the next turn picked that one up, not a fresh one


@pytest.mark.parametrize('later', [False, True], ids=['first-turn', 'later-turn'])
def test_an_acp_turn_that_ended_early_is_said_once_and_the_next_line_resumes_its_conversation(later, tmp_path, monkeypatch):
    """An ACP turn that ended early before a word (a refusal, a limit) raised an error with no conversation id: on a first turn the next line
    opened a fresh conversation that knew nothing of it, and on a later one the caller asked the whole turn again on a fresh conversation
    (it re-asks any failure but a death it read by its words) - the turn run twice, the sentence never shown. It is clipool.PartWay: one
    call, its sentence what the owner reads, its conversation the next line's."""
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': 'Pull the first ledger', 'silent': True, 'stop': 'max_tokens'}]))
    with on_road('acp', monkeypatch, {}, rules) as (ses, resumes, began):
        if later: ses.send_prompt('Hello there.', brief=True)
        before = ses.cli_sid
        with pytest.raises(Exception): ses.send_prompt('Pull the first ledger.', brief=True)
        assert len(resumes) == 1 + later, resumes                     # ...asked once, never again on a fresh conversation
        assert ses.store.last_worker_event(ses.task_id, skip=ws.NOTES)['Text'] == clipool.ended_early('max_tokens')
        sid = ses.cli_sid
        assert sid and (not later or sid == before)
        ses.send_prompt('And then the second.', brief=True)
    assert resumes[-1] == sid, resumes                                 # the next line goes on in that conversation


@pytest.mark.parametrize('ends', [lambda: clipool.PartWay(clipool.MID_TURN, 'sess-1'), lambda: clipool.TimedOut('timed out after 300s', 'sess-1')])
def test_a_turn_that_did_not_finish_on_a_conversation_under_way_is_never_asked_again_on_a_fresh_one(ends):
    """A failed turn on a conversation under way (cli_sid set) is asked again on a fresh conversation, the whole thing said again - right for a
    conversation its CLI lost, never for a turn that may have done part of the work. The caller read that off the exception's words (MID_TURN in
    the text); it reads the kind (clipool.Unfinished) - one call, the conversation kept, and what ended it is what the owner reads."""
    s = MemoryStore(); tid = task(s); calls = []
    with mock.patch.object(general, '_selected', return_value=('cli:codex', 'Codex', '')):
        ses = general.GeneralSession(s, tid)
    ses.cli_sid = 'sess-1'
    def brain(*a, **k): calls.append(1); raise ends()
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain), mock.patch.object(ses, '_end_soon'), \
         mock.patch('taskuary.continuity.can_resume', return_value=True):
        try: ses.send_prompt('Pull the ledger.', brief=True)
        except Exception: pass
    assert len(calls) == 1 and ses.cli_sid == 'sess-1'
    last = s.last_worker_event(tid, skip=ws.NOTES)
    assert last['Text'] in (clipool.MID_TURN, general.timed_out_line()), last


def test_a_failure_whose_chain_comes_back_on_itself_is_read_to_its_end():
    """CI, 2026-11-21: an ACP agent that died mid-turn hung its turn forever - its failure, re-raised in its own handler, had a cause chain
    that came back on itself, and the walk down it never ended. Each failure in the chain is read once."""
    from taskuary import general
    a, b = RuntimeError('died'), ValueError('wrapped'); b.__context__ = a; a.__context__ = b
    assert [x for x in general._chain(b)] == [b, a] and general._unfinished(b) is None and general.unreached_line(b) == ''


class Spawned(set):
    "agents._CLI_CHILDREN, every process it was ever handed remembered."
    def __init__(self): super().__init__(); self.ever = []
    def add(self, p): self.ever.append(p); super().add(p)


@pytest.mark.parametrize('keep', [True, False], ids=['kept', 'one-shot'])
@pytest.mark.parametrize('later', [False, True], ids=['first turn', 'later turn'])
def test_an_acp_agent_that_dies_mid_turn_is_said_as_a_death_and_its_turn_is_cleaned_up(later, keep, tmp_path, monkeypatch):
    """An ACP agent that died mid-turn read "Cannot access local variable 'ok' ..." to the owner: the run's `ok` was never set before its
    `try`, so its `finally` raised over the death - and skipped the rest of itself: the dead conversation stayed in the pool, a one-shot
    process was never closed, its child never forgotten. The owner reads the death's one sentence, its conversation is kept for the next
    line, and the turn's cleanup ran."""
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': 'Pull the first ledger', 'exit': 3}]))
    spawned = Spawned(); monkeypatch.setattr(agents, '_CLI_CHILDREN', spawned)
    with on_road('acp', monkeypatch, {}, rules, keep=keep) as (ses, resumes, began):
        if later: ses.send_prompt('Hello there.', brief=True)
        before = ses.cli_sid
        with pytest.raises(Exception): ses.send_prompt('Pull the first ledger.', brief=True)
        assert ses.store.last_worker_event(ses.task_id, skip=ws.NOTES)['Text'] == clipool.MID_TURN
        assert ses.cli_sid and (not later or ses.cli_sid == before), 'the conversation it died on is kept'
        assert clipool._POOL.get(ses.keep()) is None, 'the dead conversation was dropped'
        assert spawned.ever and not spawned and all(p.poll() is not None for p in spawned.ever), 'no process is left'


def test_a_turn_that_reached_its_limit_reads_the_one_sentence_for_it_on_the_kept_road_too(tmp_path, monkeypatch):
    """The same fact read two ways: ACP said a turn that hit its limit in the early-end sentence, while kept claude's own error_max_turns result
    read "Claude: error_max_turns" - a stop code, no way on. One function says it on every road (clipool.ended_early), and the conversation
    is kept for the next line."""
    rules = tmp_path / 'r.json'; rules.write_text(json.dumps([{'when': 'Pull the first ledger', 'first': 'Half of the ledger.'}]))
    with on_road('kept', monkeypatch, {'FAKE_CLAUDE_RESULT': json.dumps({'subtype': 'error_max_turns', 'is_error': True, 'result': ''})}, rules) as (ses, resumes, began):
        with pytest.raises(Exception): ses.send_prompt('Pull the first ledger.', brief=True)
        assert ses.store.last_worker_event(ses.task_id, skip=ws.NOTES)['Text'] == clipool.ended_early('error_max_turns')
        assert ses.cli_sid and len(resumes) == 1
