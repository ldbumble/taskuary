"""A coding pane's own conversation is resumable too - not only the assistant's.

The assistant has kept a native session id since session_resume; a PTY kept one only in memory
(Term.ext_id, learned from a claude hook or a codex rollout) and dropped it when the pane died.
These tests pin the id to disk the moment it is learned, and the road back into that exact
conversation - including on a task that was already finished.
"""
import json
import os
from types import SimpleNamespace
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import agents, climodels, continuity, hooks, server, terminal, witness
from taskuary.store import MemoryStore


def coder(store, name='claude', cmd='claude'):
    store.upsert_agent(name, 'coding', 'cli', json.dumps({'cmd': cmd, 'args': ['-p']}))


def task(store, **fields):
    return store.create_task({'Title': 'Fix Ben email on Monday VPO report', 'Kind': 'coding',
                              'Status': 'in_progress', **fields}, 'owner')


def pane(store, tid, cwd, sid='pane-1', cli='claude'):
    return SimpleNamespace(sid=sid, alive=True, task_id=tid, cwd=cwd, agent='coder', label='coder',
                           argv=[cli], last=1.0, ext_id='', witness=witness.Witness(), store=store,
                           files=lambda: [], tail=lambda n=3: [])


def test_a_claude_hook_files_its_session_id_before_the_pane_ever_closes(tmp_path):
    store = MemoryStore(); tid = task(store); t = pane(store, tid, str(tmp_path))
    with mock.patch.dict(terminal.SESSIONS, {t.sid: t}, clear=True):
        bound = hooks.receive({'session_id': 'claude-thread', 'cwd': str(tmp_path),
                               'hook_event_name': 'UserPromptSubmit'})
    assert bound['bound'] and t.ext_id == 'claude-thread'
    assert store.resumable_session(tid)['ExtId'] == 'claude-thread'


def test_a_codex_rollout_files_its_session_id_when_the_tail_binds(tmp_path):
    store = MemoryStore(); cwd = tmp_path / 'repo'; cwd.mkdir(); tid = task(store)
    t = pane(store, tid, str(cwd), cli='codex')
    day = tmp_path / 'home' / 'sessions' / '2026' / '09' / '15'; day.mkdir(parents=True)
    (day / 'rollout-2026-09-15T10-11-12-codex-thread.jsonl').write_text(
        json.dumps({'type': 'session_meta', 'payload': {'id': 'codex-thread', 'cwd': str(cwd)}}) + '\n',
        encoding='utf-8')
    with mock.patch.object(climodels, 'codex_home', return_value=tmp_path / 'home'):
        assert witness.RolloutTail(t)._find()
    assert store.resumable_session(tid)['ExtId'] == 'codex-thread'


def test_filing_the_transcript_keeps_the_session_id_the_hook_already_saved(tmp_path):
    store = MemoryStore(); tid = task(store)
    store.note_session_id(tid, 'pane-1', 'claude-thread', 'coder', str(tmp_path))
    store.add_transcript(tid, 'pane-1', 'what was on the screen', 'coder', str(tmp_path))
    row = store.resumable_session(tid)
    assert (row['ExtId'], row['Text']) == ('claude-thread', 'what was on the screen')


def test_the_newest_session_carrying_an_id_is_the_one_offered(tmp_path):
    store = MemoryStore(); tid = task(store)
    store.note_session_id(tid, 'pane-1', 'first-thread', 'coder', str(tmp_path))
    store.add_transcript(tid, 'pane-2', 'a session that never bound an id', 'coder', str(tmp_path))
    assert store.resumable_session(tid)['ExtId'] == 'first-thread'


@pytest.mark.parametrize('profile,expected', [
    ({'cmd': 'claude'}, ['--resume', 'S']),
    ({'cmd': 'codex'}, ['resume', 'S']),
    # copilot's --resume takes an OPTIONAL value, so a space-separated id is not read as its value
    ({'cmd': 'copilot'}, ['--resume=S']),
    ({'cmd': 'mycli', 'resume_args': ['--continue']}, ['--continue', 'S']),
    ({'cmd': 'mycli', 'resume_args': ['--pick={id}', '--go']}, ['--pick=S', '--go']),
    ({'cmd': 'gemini'}, ['--resume', 'S']),
    ({'cmd': 'qwen'}, ['--resume', 'S']),
    ({'cmd': 'cursor-agent'}, ['--resume=S']),
    ({'cmd': 'muse'}, []),          # nothing verified for it yet, so it is offered nothing
])
def test_each_backend_spells_resume_in_its_own_words(profile, expected):
    assert agents.resume_argv(profile, 'S') == expected


@pytest.mark.parametrize('cmd,expected', [
    ('claude', ['--session-id', 'U']),        # verified 2026-09-15: assigned, then resumed, by round trip
    ('copilot', ['--session-id=U']),
    ('qwen', ['--session-id', 'U']),
    ('codex', []),                            # codex names its own; the rollout tells us which
])
def test_a_cli_that_lets_us_name_the_conversation_is_told_its_name(cmd, expected):
    assert agents.assign_argv({'cmd': cmd}, 'U') == expected


def test_a_pane_records_the_name_we_gave_it_before_it_has_said_anything(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store)
    with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
         mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(terminal, 'Term') as Term:
        # a real Term carries these; a MagicMock would hand bind_ext a mock store to write into
        Term.return_value.sid, Term.return_value.task_id, Term.return_value.store = 'pane-9', tid, store
        Term.return_value.agent, Term.return_value.cwd, Term.return_value.ext_id = 'claude', str(tmp_path), ''
        terminal.open_session(store, 'claude', tid, None, str(tmp_path), actor='owner', seed_fn=lambda here: 'go')
    argv = Term.call_args.args[0]
    assigned = argv[argv.index('--session-id') + 1]
    # nothing has run, nothing has hooked, nothing has been harvested - and it is already resumable
    assert store.resumable_session(tid)['ExtId'] == assigned


def test_a_resumed_pane_is_not_also_handed_a_new_name(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store)
    with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
         mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(terminal, 'Term') as Term:
        terminal.open_session(store, 'claude', tid, None, str(tmp_path), actor='owner',
                              seed_fn=lambda here: 'carry on', resume='claude-thread')
    assert '--session-id' not in Term.call_args.args[0]


def test_a_resumed_pane_carries_the_resume_flag_and_types_its_prompt(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store)
    with mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
         mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(terminal, 'Term') as Term:
        terminal.open_session(store, 'claude', tid, None, str(tmp_path), actor='owner',
                              seed_fn=lambda here: 'carry on', resume='claude-thread')
    argv = Term.call_args.args[0]
    assert argv[-2:] == ['--resume', 'claude-thread']
    assert 'carry on' not in argv        # a resumed TUI is typed into, never given a positional prompt


def test_the_resumed_seed_is_the_resume_prompt_and_the_owner_s_words_only():
    seed = terminal.resume_seed('and check the tests still pass')
    assert continuity.RESUME_PROMPT in seed and 'and check the tests still pass' in seed
    assert continuity.RESUME_PROMPT.strip() == terminal.resume_seed('').strip()


def test_continuing_a_coding_session_reopens_that_conversation_not_a_new_one(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store)
    store.note_session_id(tid, 'pane-1', 'claude-thread', 'claude', str(tmp_path))
    store.add_transcript(tid, 'pane-1', 'what was on the screen', 'claude', str(tmp_path))
    with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's2'}) as start:
        out = TestClient(server.app).post(f'/api/tasks/{tid}/continue-session').json()
    assert out['resumed'] == 'claude-thread' and out['agent'] == 'claude'
    assert start.call_args.kwargs['resume'] == 'claude-thread'
    assert start.call_args.kwargs['cwd'] == str(tmp_path)


def test_continuing_a_finished_coding_task_puts_it_back_in_progress(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store, Status='done')
    store.note_session_id(tid, 'pane-1', 'claude-thread', 'claude', str(tmp_path))
    store.add_transcript(tid, 'pane-1', 'what was on the screen', 'claude', str(tmp_path))
    with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(server.hub_term, 'start_on_task', return_value={'sid': 's2'}):
        assert TestClient(server.app).post(f'/api/tasks/{tid}/continue-session').status_code == 200
    assert store.get_task(tid)['Status'] == 'in_progress'


def test_a_dismissed_task_is_still_refused(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store, Status='dropped')
    store.note_session_id(tid, 'pane-1', 'claude-thread', 'claude', str(tmp_path))
    store.add_transcript(tid, 'pane-1', 'what was on the screen', 'claude', str(tmp_path))
    with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(server.hub_term, 'start_on_task') as start:
        assert TestClient(server.app).post(f'/api/tasks/{tid}/continue-session').status_code == 409
    assert not start.called


def test_nothing_saved_refuses_rather_than_quietly_starting_a_fresh_agent(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store)
    store.add_transcript(tid, 'pane-1', 'a session that never bound an id', 'claude', str(tmp_path))
    with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(server.hub_term, 'start_on_task') as start:
        r = TestClient(server.app).post(f'/api/tasks/{tid}/continue-session')
    assert r.status_code == 409 and 'saved session' in r.json()['detail']
    assert not start.called


def test_a_checkout_that_moved_refuses_rather_than_resuming_in_the_wrong_tree(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store)
    gone = str(tmp_path / 'deleted-checkout')
    store.note_session_id(tid, 'pane-1', 'claude-thread', 'claude', gone)
    store.add_transcript(tid, 'pane-1', 'what was on the screen', 'claude', gone)
    with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch.object(server.hub_term, 'start_on_task') as start:
        r = TestClient(server.app).post(f'/api/tasks/{tid}/continue-session')
    assert r.status_code == 409 and 'no longer exists' in r.json()['detail']
    assert not start.called


def test_the_task_detail_says_which_session_can_be_continued(tmp_path):
    store = MemoryStore(); coder(store); tid = task(store)
    store.note_session_id(tid, 'pane-1', 'claude-thread', 'claude', str(tmp_path))
    store.add_transcript(tid, 'pane-1', 'what was on the screen', 'claude', str(tmp_path))
    with mock.patch.object(server, 'store', store), mock.patch.dict(terminal.SESSIONS, {}, clear=True):
        detail = TestClient(server.app).get(f'/api/tasks/{tid}').json()
    assert detail['resumable']['agent'] == 'claude' and detail['resumable']['sid'] == 'pane-1'
    assert 'claude-thread' not in json.dumps(detail)     # the id is ours to use, not the page's to show


def test_a_resumed_session_is_told_what_arrived_since_its_last_run_and_where_the_screenshots_are(tmp_path):
    """TQ-0731 (the owner, 2026-09-24: "claude did not get the rest of the messages"): two messages with
    screenshots arrived after the agent's run; continuing the session said only "carry on", and the context file
    was the one written when the task began. It is rewritten on resume - attachments listed with their paths -
    and the seed says how many messages are new."""
    store = MemoryStore(); tid = store.create_task({'Title': 'Update fails', 'Kind': 'coding', 'Status': 'open'}, 'o')
    first = store.add_message({'TaskId': tid, 'ExternalId': 'w1', 'Channel': 'whatsapp', 'ConversationId': 'wa:gabi',
                               'FromName': 'Gabi', 'SentAt': '2026-09-24 14:53:24', 'BodyText': 'When updating, this is what I got', 'Status': 'routed'})
    store._exec("INSERT INTO transcript (TaskId, Sid, Agent, Text, CreatedAt) VALUES (?, 's1', 'coder', 'did the work', '2026-09-24 14:57:40')", (tid,))
    later = store.add_message({'TaskId': tid, 'ExternalId': 'w2', 'Channel': 'whatsapp', 'ConversationId': 'wa:gabi',
                               'FromName': 'Gabi', 'SentAt': '2026-09-24 15:00:47', 'BodyText': 'It says AI not set up but it is', 'Status': 'routed'})
    shot = tmp_path / 'shot.jpg'; shot.write_bytes(b'jpg')
    store.add_attachment({'MessageId': later, 'Name': 'shot.jpg', 'ContentType': 'image/jpeg', 'Path': str(shot), 'Size': 3})
    with mock.patch.dict(os.environ, {'TASKUARY_HOME': str(tmp_path)}):
        seed = terminal.resume_seed('', store, tid)
    assert continuity.RESUME_PROMPT in seed
    assert 'NEW SINCE YOUR LAST RUN: 1 message' in seed
    cpath = seed.split(' in ', 1)[1].split(' (the thread section)')[0]
    text = open(cpath, encoding='utf-8').read()
    assert 'It says AI not set up but it is' in text and str(shot) in text
