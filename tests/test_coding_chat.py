"""A coding task is the same one chat (codingchat.py, the owner 2026-11-06): the endpoint serves each session's steps - the CLI's own log,
with an edit's own diff - or, for a session run over ACP, its kept updates (the seam step 1 plugs into); the mail that came in, in its
sender's words; and the live CLI. And a part of the diff the owner turns down in review is taken back out in one commit, or nothing moves.
Invented people, a temp git repo, no network."""
import json, os, subprocess, tempfile
from unittest import mock

import pytest

from taskuary import codingchat, guard, landing, session_artifacts, sessionrecord
from taskuary.testing import Factory


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(sessionrecord, '_home', lambda: tmp_path)
    monkeypatch.setattr(sessionrecord, '_FOUND', {})
    (tmp_path / 'artifacts').mkdir()
    monkeypatch.setattr(session_artifacts, 'root', lambda: tmp_path / 'artifacts')
    return tmp_path


@pytest.fixture
def server(home):
    os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp())
    from fastapi.testclient import TestClient
    from taskuary import server
    return server, TestClient(server.app)


def claude_log(home, ext):
    rows = [
        {'type': 'user', 'timestamp': '2026-11-06T09:00:00Z', 'message': {'content': 'The budget total is off by the tax line.'}},
        {'type': 'assistant', 'timestamp': '2026-11-06T09:00:05Z', 'message': {'content': [
            {'type': 'tool_use', 'id': 'r1', 'name': 'Read', 'input': {'file_path': 'C:/work/ledger/store.py'}},
            {'type': 'tool_use', 'id': 'b1', 'name': 'Bash', 'input': {'command': 'pytest -q tests'}},
            {'type': 'tool_use', 'id': 'e1', 'name': 'Edit', 'input': {'file_path': 'C:/work/ledger/budget.py', 'old_string': 'total = a', 'new_string': 'total = a + tax'}}]}},
        {'type': 'user', 'timestamp': '2026-11-06T09:00:09Z', 'message': {'content': [{'type': 'tool_result', 'tool_use_id': 'e1', 'content': 'ok'}]},
         'toolUseResult': {'filePath': 'C:/work/ledger/budget.py', 'structuredPatch': [
             {'oldStart': 11, 'oldLines': 3, 'newStart': 11, 'newLines': 3, 'lines': [' def total(a, tax):', '-    total = a', '+    total = a + tax', '     return total']}]}},
        {'type': 'assistant', 'timestamp': '2026-11-06T09:00:12Z', 'message': {'content': [{'type': 'text', 'text': 'Fixed: the total now adds the tax line.'}]}}]
    p = home / '.claude' / 'projects' / 'C--work-ledger' / f'{ext}.jsonl'
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text('\n'.join(json.dumps(r) for r in rows), encoding='utf-8')


def test_a_claude_edit_keeps_its_args_and_the_patch_claude_wrote(home):
    claude_log(home, 'cc1')
    steps, _ = sessionrecord.cli_steps('claude', 'cc1')
    read, bash, edit = [s for s in steps if s['k'] == 'tool']
    assert read['args'] == {'file_path': 'C:/work/ledger/store.py'} and bash['args'] == {'command': 'pytest -q tests'}
    assert edit['file'] == 'C:/work/ledger/budget.py'
    assert edit['edit']['hunks'][0]['oldStart'] == 11 and edit['edit']['hunks'][0]['lines'][2] == '+    total = a + tax'


def test_a_codex_patch_is_kept_per_file():
    patch = '*** Begin Patch\n*** Update File: portal/app.js\n@@\n-a\n+b\n*** Add File: portal/new.js\n+x\n*** End Patch'
    with tempfile.TemporaryDirectory() as d:
        p = os.path.join(d, 'r.jsonl')
        with open(p, 'w', encoding='utf-8') as f: f.write(json.dumps({'type': 'response_item', 'payload': {'type': 'custom_tool_call', 'name': 'apply_patch', 'input': patch}}))
        from pathlib import Path
        steps = sessionrecord._codex(Path(p))
    assert [(s['file'], s['edit']['patch']) for s in steps] == [('portal/app.js', '@@\n-a\n+b'), ('portal/new.js', '+x')]


def test_the_endpoint_serves_the_log_the_mail_and_no_live_cli(home, server):
    srv, c = server
    claude_log(home, 'cc2')
    f = Factory(srv.store)
    tid = f.task(title='Budget total misses tax', kind='coding')
    f.message(task_id=tid, from_name='Erin Blake', from_email='erin@northwind.example', body='The budget total skips the tax line again.')
    srv.store.add_transcript(tid, 'pane-1', 'screen', 'coding', 'C:/work/ledger', 'cc2', brain='claude')
    got = c.get(f'/api/tasks/{tid}/coding-chat').json()['data']
    assert got['live'] is None
    assert [m['who'] for m in got['mails']] == ['Erin Blake'] and 'tax line' in got['mails'][0]['words']
    (s,) = got['sessions']
    assert (s['sid'], s['cli'], s['source']) == ('pane-1', 'claude', 'Claude Code log')
    assert [x['k'] for x in s['steps']] == ['you', 'tool', 'tool', 'tool', 'said']
    # ...each step's time in the server's own zone, as the mail's: a CLI log stamps UTC
    assert s['steps'][0]['at'] == sessionrecord._local('2026-11-06T09:00:00Z')
    assert c.get('/api/tasks/999999/coding-chat').status_code == 404


def test_an_acp_session_is_served_as_its_updates(home, server):
    srv, c = server
    tid = Factory(srv.store).task(title='Budget total misses tax', kind='coding')
    srv.store.add_transcript(tid, 'acp-7', 'screen', 'coding', 'C:/work/ledger', '', brain='claude')
    for u in ({'sessionUpdate': 'tool_call', 'toolCallId': 't1', 'kind': 'read', 'title': 'Read store.py', 'locations': [{'path': 'C:/work/ledger/store.py'}]},
              {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': 'Fixed.'}}):
        codingchat.record_update(tid, 'acp-7', u)
    codingchat.record_update(tid, 'acp-7', 'not a dict')          # a bad line costs nothing
    (s,) = c.get(f'/api/tasks/{tid}/coding-chat').json()['data']['sessions']
    assert s['source'] == 'acp' and [u['sessionUpdate'] for u in s['updates']] == ['tool_call', 'agent_message_chunk']


def test_each_card_is_named_with_the_turn_that_raised_it_as_the_page_names_that_turns_step():
    """ONE PLACEMENT ROAD (2026-11-11): the page placed a coding card by comparing times and named the turns by position, so the server could not
    name one. A card is of the turn whose step was newest when it was raised (`sid#n`, the update's place); raised on arrival or after his line
    before the turn's first step, none. A draft is stale once his line came after it and no step of the agent's has since."""
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = s.create_task({'Title': 'Ledger totals', 'Kind': 'coding'}, 'owner')
    u = lambda at, k, meta=None: {'sessionUpdate': k, '_at': at, **({'_meta': {'taskuary': meta}} if meta else {})}
    ss = [{'sid': 'a1', 'updates': [u('2026-11-11 09:00:00', 'user_message_chunk', 'owner'), u('2026-11-11 09:00:05', 'tool_call'),
                                    u('2026-11-11 09:00:09', 'agent_message_chunk'), u('2026-11-11 09:10:00', 'user_message_chunk', 'owner')]}]
    def card(at, kind='draft_reply'):
        rid = s.add_review({'TaskId': tid, 'Kind': kind, 'Status': 'pending', 'DraftText': 'Hi Erin'}); s._exec('UPDATE review SET CreatedAt=? WHERE ReviewId=?', (at, rid)); return rid
    arrival, mine, after_his, held = card('2026-11-11 08:00:00'), card('2026-11-11 09:00:06'), card('2026-11-11 09:10:01'), card('2026-11-11 09:00:09', 'action')
    got = codingchat.cards(s, tid, ss)
    assert got['turns'] == {str(arrival): None, str(mine): 'a1#1', str(after_his): None, str(held): 'a1#2'}
    assert [(d['review'], d['turn'], d['stale']) for d in got['drafts']] == [(arrival, None, False), (mine, 'a1#1', True), (after_his, None, False)]


def test_a_resumed_conversation_is_drawn_once(home, server):
    srv, c = server
    claude_log(home, 'cc3')
    tid = Factory(srv.store).task(title='Budget total misses tax', kind='coding')
    for sid in ('pane-1', 'pane-2'): srv.store.add_transcript(tid, sid, 'screen', 'coding', 'C:/work/ledger', 'cc3', brain='claude')
    assert [s['sid'] for s in c.get(f'/api/tasks/{tid}/coding-chat').json()['data']['sessions']] == ['pane-2']


# ── review: a part turned down is reverted on the branch ─────────────────────────────────────
def git(cwd, *a):
    return subprocess.run(['git', '-C', cwd, '-c', 'user.name=Alex Doyle', '-c', 'user.email=alex@northwind.example', *a],
                          capture_output=True, text=True, check=True).stdout.strip()


def write(cwd, name, text):
    with open(os.path.join(cwd, name), 'w', encoding='utf-8', newline='\n') as f: f.write(text)


@pytest.fixture
def repo(tmp_path):
    cwd = str(tmp_path / 'ledger'); os.makedirs(cwd)
    git(cwd, 'init', '-q', '-b', 'master')
    for k, v in (('user.name', 'Alex Doyle'), ('user.email', 'alex@northwind.example')): git(cwd, 'config', k, v)
    write(cwd, 'budget.py', ''.join(f'line {i}\n' for i in range(1, 31))); git(cwd, 'add', '.'); git(cwd, 'commit', '-q', '-m', 'start')
    from taskuary.store import MemoryStore
    s = MemoryStore(); tid = Factory(s).task(title='Budget total misses tax', kind='coding')
    landing.mark_start(s, tid, cwd)
    git(cwd, 'checkout', '-q', '-b', 'fix-tax')
    text = ''.join(f'line {i}\n' for i in range(1, 31)).replace('line 2\n', 'line 2 + tax\n').replace('line 25\n', 'line 25 rounded\n')
    write(cwd, 'budget.py', text); git(cwd, 'commit', '-qam', 'tax and rounding')
    return s, tid, cwd


def hunks(cwd, s, tid):
    head, hs = landing.hunks_of(landing._raw(cwd, 'diff', landing.record(s, tid)['start'], 'fix-tax', '--', 'budget.py'))
    return [b'\n'.join(h).decode() for h in hs]


def test_a_turned_down_part_is_reverted_alone_in_one_commit(repo):
    s, tid, cwd = repo
    hs = hunks(cwd, s, tid)
    assert len(hs) == 2
    out = landing.revert(s, tid, [{'path': 'budget.py', 'index': 1, 'text': hs[1]}])
    assert out['ok'] and 'Reverted 1 part of budget.py' in out['says']
    body = open(os.path.join(cwd, 'budget.py'), encoding='utf-8').read()
    assert 'line 2 + tax' in body and 'line 25 rounded' not in body
    assert 'turned down in review' in git(cwd, 'log', '-1', '--format=%s') and not git(cwd, 'status', '--porcelain')


def test_a_part_that_changed_since_it_was_shown_moves_nothing(repo):
    s, tid, cwd = repo
    head = git(cwd, 'rev-parse', 'HEAD')
    with pytest.raises(landing.Refused, match='changed since'):
        landing.revert(s, tid, [{'path': 'budget.py', 'index': 0, 'text': '@@ -1,5 +1,5 @@\n something else'}])
    assert git(cwd, 'rev-parse', 'HEAD') == head


def test_a_checkout_on_another_branch_or_with_an_agent_in_it_moves_nothing(repo):
    s, tid, cwd = repo
    hs = hunks(cwd, s, tid)
    assert landing.state(s, tid)['own']                           # the branch is seen as the agent's own while it is checked out
    git(cwd, 'checkout', '-q', 'master')
    with pytest.raises(landing.Refused, match='checked out'): landing.revert(s, tid, [{'path': 'budget.py', 'index': 0, 'text': hs[0]}])
    git(cwd, 'checkout', '-q', 'fix-tax')
    busy = type('T', (), {'cwd': cwd, 'task_id': 99})()
    with mock.patch('taskuary.peers._cli_sessions', return_value=[busy]), pytest.raises(landing.Refused, match='agent is working'):
        landing.revert(s, tid, [{'path': 'budget.py', 'index': 0, 'text': hs[0]}])


def test_reverting_is_the_owners_door():
    assert guard.classify('POST', '/api/tasks/7/landing/revert')[0] == 'deny'
    assert guard.classify('GET', '/api/tasks/7/coding-chat')[0] == 'read'


def test_a_press_on_a_coding_task_is_a_line_in_its_chat_as_in_a_general_one(home, server):
    """The audit, 2026-11-10: Remind me or Push on a coding task left no line in its chat - the general chat draws each press as one quiet
    line in the owner's voice (general.press_lines); the coding chat's payload carries the same lines, from the same function."""
    from taskuary import general, remind
    srv, c = server
    tid = Factory(srv.store).task(title='Budget total misses tax', kind='coding')
    remind.set_reminder(srv.store, tid, 'friday', 'owner')
    got = c.get(f'/api/tasks/{tid}/coding-chat').json()['data']['presses']
    assert [m['content'][0]['text'] for m in got] == [m['content'][0]['text'] for m in general.press_lines(srv.store, tid)]
    assert len(got) == 1 and got[0]['content'][0]['text'].startswith('You set a reminder for')


def test_a_coding_agent_s_question_reads_as_a_chat_s_does(home, server, monkeypatch):
    """The audit, 2026-11-10: over ACP a coding agent's [[TASKUARY-ASK]] came a token at a time - the chat drew the bare marker, and the
    payload carried no question to answer. Its words read as a general answer's (selfclose.asked_inline), its ask by the one read (taskstate.asking)."""
    from types import SimpleNamespace
    from taskuary import workerstate as ws
    srv, c = server
    tid = Factory(srv.store).task(title='Pick the vendor', kind='coding')
    for w in ('Q3 totals are in the reply. One thing only you can say:\n[[TASKU', 'ARY-ASK]] Which vendor - Payworth or Trainly?'):
        codingchat.record_update(tid, 'acp-8', {'sessionUpdate': 'agent_message_chunk', 'content': {'type': 'text', 'text': w}})
    ws.record(srv.store, tid, 'acp-8', 'input_needed', request_id='q1', text='Which vendor - Payworth or Trainly?', source='hook')
    from taskuary import terminal                                      # ...its session at rest over ACP, the question waiting on him
    live = SimpleNamespace(task_id=tid, sid='acp-8', alive=True, acp=True, started='2026-11-10 09:00:00', cli='claude', cwd='', _q=[], phase=lambda: 'parked')
    monkeypatch.setitem(terminal.SESSIONS, 'acp-8', live)
    d = c.get(f'/api/tasks/{tid}/coding-chat').json()['data']
    (said,) = [u['content']['text'] for u in d['sessions'][0]['updates'] if u['sessionUpdate'] == 'agent_message_chunk']
    assert said == 'Q3 totals are in the reply. One thing only you can say:\n\nWhich vendor - Payworth or Trainly?'
    assert d['asking']['text'] == 'Which vendor - Payworth or Trainly?'
