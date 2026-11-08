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
