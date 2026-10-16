"""Small seams left after the stranger and chat-trust layers (live check 2026-10-14): what the floor refused is on the
record, two homes keep their strangers apart, a stranger's seed does not send it to a refused command first, a chat
sender named 'You' is not the owner, and the chat servers that can say one-to-one now do."""
import os, tempfile
from unittest import mock
import pytest
from taskuary import chatservers, devtools, floor, ingest, origin, senders, sessionrecord, terminal
from taskuary.store import MemoryStore
from taskuary.testing import Factory

@pytest.fixture(autouse=True)
def _iso(monkeypatch, tmp_path):
    monkeypatch.setattr(origin, '_claude_version', lambda cmd='claude': (2, 1, 300))
    (tmp_path / 'temp').mkdir(); monkeypatch.setattr(tempfile, 'gettempdir', lambda: str(tmp_path / 'temp'))
    monkeypatch.setattr(sessionrecord, '_home', lambda: tmp_path)
    monkeypatch.setattr(devtools, '_DM', {})

def _stranger(s):
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'email'}, 'router')
    s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'FromName': 'Someone', 'BodyText': 'hi', 'Status': 'routed'})
    return t


# ── what the floor refused is on the record ─────────────────────────────────────────────────────────────────────
def test_a_session_s_floor_refusals_are_on_its_record():
    s = MemoryStore(); tid = Factory(s).task(title='x')
    s.add_transcript(tid, 'pane-1', 'screen', 'coding', '', 'c1', brain='claude')
    s.add_worker_event({'TaskId': tid, 'Sid': 'pane-1', 'Kind': 'floor_denied', 'Text': 'Read: that file is Taskuary\'s own', 'Source': 'floor'})
    s.add_worker_event({'TaskId': tid, 'Sid': 'other', 'Kind': 'floor_denied', 'Text': 'not this run', 'Source': 'floor'})
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert [r['text'] for r in rec['refused']] == ["Read: that file is Taskuary's own"] and rec['refused'][0]['at']

def test_a_headless_run_s_refusals_follow_the_cli_s_id():
    s = MemoryStore(); tid = Factory(s).task(title='x')
    s.add_transcript(tid, 'hl-1', 'screen', 'coding', '', 'cli-abc', brain='claude')
    s.add_worker_event({'TaskId': tid, 'Sid': 'cli-abc', 'Kind': 'floor_denied', 'Text': 'Bash: refused', 'Source': 'floor'})
    [rec] = sessionrecord.record(s, tid)['sessions']
    assert [r['text'] for r in rec['refused']] == ['Bash: refused']

def test_a_session_nothing_was_refused_carries_no_list():
    s = MemoryStore(); tid = Factory(s).task(title='x')
    s.add_transcript(tid, 'pane-1', 'screen', 'coding', '', 'c1', brain='claude')
    assert 'refused' not in sessionrecord.record(s, tid)['sessions'][0]


# ── two homes, two strangers ────────────────────────────────────────────────────────────────────────────────────
def test_two_homes_give_the_same_task_number_two_folders(monkeypatch, tmp_path):
    monkeypatch.setenv('TASKUARY_HOME', str(tmp_path / 'a')); a = origin.stranger_path(1)
    monkeypatch.setenv('TASKUARY_HOME', str(tmp_path / 'b')); b = origin.stranger_path(1)
    assert a != b and a.parent == b.parent == tmp_path / 'temp' / 'taskuary-stranger' and a.name.startswith('TQ-0001-')
    # ...and this home's task 1 is not let into the other home's folder
    assert floor.check({'tool_name': 'Read', 'tool_input': {'file_path': str(b / 'x.md')}}, 1) == {}
    assert floor.check({'tool_name': 'Read', 'tool_input': {'file_path': str(a / 'x.md')}}, 1)['hookSpecificOutput']['permissionDecision'] == 'deny'


# ── a stranger's seed names the commands it does not run ────────────────────────────────────────────────────────
def test_a_stranger_s_seed_says_which_agent_commands_it_skips():
    s = MemoryStore(); t = _stranger(s)
    seed = terminal.seed_text(s, t)
    line = next(p for p in seed.split('\n\n') if p.startswith('THIS SESSION:'))
    assert '--board' in line and '--learned' in line and '--upvote' in line and '--reply' not in line and '--note still' in line

def test_an_owner_s_seed_has_no_such_line():
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    t = s.create_task({'Title': 'x', 'Kind': 'coding', 'Source': 'manual', 'OriginBase': 'owner'}, 'owner')
    assert 'THIS SESSION:' not in terminal.seed_text(s, t)


# ── 'You' is a name anyone can take ─────────────────────────────────────────────────────────────────────────────
def test_a_chat_sender_named_you_is_not_ours():
    assert not ingest.is_ours({'Channel': 'teams', 'FromName': 'You', 'Status': 'routed'})
    assert ingest.is_ours({'Channel': 'own', 'FromName': 'You', 'Status': 'routed'})          # ownwork's own row
    assert ingest.is_ours({'Channel': 'teams', 'FromName': 'You', 'Status': 'context'})
    assert ingest.is_ours({'Channel': 'email', 'FromName': 'Erin Blake', 'Direction': 'out'})


# ── the chat servers that can say one-to-one ────────────────────────────────────────────────────────────────────
def _caught():
    got = []
    return got, mock.patch('taskuary.ingest.ingest_message', side_effect=lambda store, msg, **k: got.append(msg) or {'status': 'new'})

@pytest.mark.parametrize('kind,dm', [('D', True), ('O', False), ('G', False)])
def test_mattermost_marks_a_direct_channel(kind, dm):
    def mm(c, method, path, **kw):
        if path.endswith('/posts'): return {'order': ['p1'], 'posts': {'p1': {'message': 'hi', 'user_id': 'u1', 'create_at': 0}}}
        return {'type': kind}
    got, p = _caught()
    with p, mock.patch.object(chatservers, '_mm', mm):
        chatservers.poll_mattermost(None, {}, {'Address': f'ch-{kind}'}, __import__('datetime').datetime.now())
    assert bool(got[0].get('mail_meta', {}).get('dm')) is dm

@pytest.mark.parametrize('space,dm', [({'spaceType': 'DIRECT_MESSAGE'}, True), ({'type': 'DM'}, True), ({'spaceType': 'GROUP_CHAT'}, False)])
def test_google_chat_marks_a_direct_message_space(space, dm):
    def gc(store, c, method, path, **kw):
        return {'messages': [{'name': 'spaces/s/messages/1', 'text': 'hi', 'sender': {'name': 'users/1'}}]} if path.endswith('/messages') else space
    got, p = _caught()
    with p, mock.patch.object(chatservers, '_gc', gc):
        chatservers.poll_google_chat(None, {}, {'Address': f'spaces/{len(str(space))}{dm}'}, __import__('datetime').datetime.now())
    assert bool(got[0].get('mail_meta', {}).get('dm')) is dm

@pytest.mark.parametrize('typ,dm', [(1, True), (0, False), (3, False)])
def test_discord_marks_a_dm_channel(typ, dm):
    from datetime import datetime, timedelta
    def dc(c, method, path, **kw):
        if path.endswith('/messages'): return [{'id': '1', 'content': 'hi', 'timestamp': datetime.now().isoformat(), 'author': {'id': '9'}}]
        return {'type': typ}
    got, p = _caught()
    with p, mock.patch.object(devtools, '_discord', dc):
        devtools.poll_discord(None, {}, {'Address': f'c{typ}'}, datetime.now() - timedelta(hours=1))
    assert bool(got[0].get('mail_meta', {}).get('dm')) is dm

def test_a_room_type_that_cannot_be_read_is_not_one_to_one_and_is_asked_again():
    calls = []
    def boom(): calls.append(1); raise RuntimeError('403')
    assert devtools.is_dm('mattermost', 'r', boom) is False and devtools.is_dm('mattermost', 'r', boom) is False and len(calls) == 2
    assert devtools.is_dm('mattermost', 'r', lambda: True) is True and devtools.is_dm('mattermost', 'r', boom) is True   # then kept
