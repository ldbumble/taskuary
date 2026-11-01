"""A big task opens in a beat: the owner, 2026-11-01 - a rail row clicked drew a spinner with the task's title in an empty frame for
seconds before its page came up ("this still happens"). The task was a long WhatsApp group: many lines, files, agent runs, saved
sessions, drafts. Its read (GET /api/tasks/{id}) judged where the task's words came from (origin.of_task) one line at a time, and for
each line asked the database whether the owner had answered that person - a query that tried every pair of lines in the chat against
the lines between them. 200 lines took 1.4-2 s; 1,500 did not finish in twelve minutes. Here: a synthetic home of that shape, built once.
Invented people throughout."""
import os, sqlite3, time
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from taskuary import origin, senders, server, terminal
from taskuary.store import MemoryStore, SQLiteStore

CI = bool(os.environ.get('CI'))
LINES = 1500
# a guard against a read that grows with the square of the chat (minutes), not against a busy machine: ~0.6 s on a desk (2026-11-01)
OPEN = 8.0 if CI else 3.0
WHO = [('Erin Blake', '15550001@s.whatsapp.net'), ('Gail Moreno', '15550002@s.whatsapp.net'), ('Ray Colton', '15550003@s.whatsapp.net')]


def _seed(s, n=LINES, conv='grp-site-ops'):
    "One WhatsApp group on one task: three people and the owner, a photo every fifth line, drafts, notes, twenty runs and saved sessions."
    now = datetime.now()
    tid = s.create_task({'Title': 'Site ops: the walk-in cooler', 'Status': 'open', 'Kind': 'general', 'Source': 'whatsapp'}, 'fixture')
    for j in range(n):
        # Erin, Gail, Ray, then the owner: only Ray is answered (somebody speaks between the others and the owner) - so the task is a
        # stranger's, found on its first line
        mine = j % 4 == 3
        name, addr = ('Alex Doyle', 'alex@northwind.example') if mine else WHO[j % 4 % 3]
        mid = s.add_message({'TaskId': tid, 'Status': 'context' if mine else 'routed', 'Channel': 'whatsapp', 'ExternalId': f'wa-{conv}-{j}',
                             'Subject': 'Site ops', 'FromName': name, 'FromEmail': addr, 'SourceName': 'alex@northwind.example',
                             'BodyText': f'line {j} about the walk-in cooler ' * 8, 'SentAt': (now - timedelta(minutes=n - j)).strftime('%Y-%m-%d %H:%M:%S'),
                             'ConversationId': conv, 'Direction': 'out' if mine else 'in'})
        s.add_route(mid, tid, 'create' if j == 0 else 'attach', None, 'same chat', [], 'triage', verdict={'intent': 'task', 'summary': 'the cooler'})
        if j % 5 == 0: s.add_attachment({'MessageId': mid, 'Name': f'photo{j}.jpg', 'ContentType': 'image/jpeg'})
    for k in range(40):
        s.add_review({'TaskId': tid, 'MessageId': mid, 'Status': 'sent' if k else 'pending', 'Kind': 'draft', 'Reason': 'drafted', 'DraftText': 'a draft ' * 50})
    for k in range(150): s.add_comment(tid, 'agent', 'agent', f'note {k} ' * 40)
    for k in range(20):
        rid = s.start_run(tid, 'general', 'go ' * 50, 'fixture'); s.update_run(rid, {'Status': 'done'}, finished=True)
        s.add_transcript(tid, f'sid-{k}', 'turn text ' * 20000, agent='general', ext_id=f'ext-{k}', brain='claude')
    s.save_session(tid, 'cli:claude', '', 'native', 'ctx')
    return tid


@pytest.fixture(scope='module')
def home(tmp_path_factory):
    path = str(tmp_path_factory.mktemp('big-task') / 'home.db')
    s = SQLiteStore(path); s.set_setting('calendar_enabled', '0', 'fixture')
    tid = _seed(s); s.close()
    return path, tid


@pytest.fixture
def big(home, tmp_path, monkeypatch):
    path = str(tmp_path / 'open.db')
    with sqlite3.connect(home[0]) as src, sqlite3.connect(path) as dst: src.backup(dst)
    s = SQLiteStore(path)
    monkeypatch.setattr(server, 'store', s)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kw: [])
    yield s, home[1]
    s.close()


def test_a_big_task_opens_in_a_beat(big):
    s, tid = big
    c = TestClient(server.app)
    took = time.perf_counter(); r = c.get(f'/api/tasks/{tid}'); took = time.perf_counter() - took
    assert r.status_code == 200 and len(r.json()['messages']) == LINES and len(r.json()['attachments']) == LINES // 5
    assert r.json()['origin']['origin'] == 'stranger'
    assert took < OPEN, f'the task took {took:.1f}s to open'


def _counted(s):
    "Every read the store makes from here on, counted."
    n, rows = [0], s._rows
    s._rows = lambda *a, **kw: n.__setitem__(0, n[0] + 1) or rows(*a, **kw)
    return n


def test_its_read_asks_the_database_a_bounded_number_of_times(big):
    """No question per line: the files, the verdicts, the senders and the calendar are each read once for the whole task."""
    s, tid = big
    n = _counted(s); server.task_detail(tid)
    assert n[0] < LINES / 10, f'{n[0]} reads for {LINES} lines'


def test_judging_a_long_group_per_person_says_what_judging_it_per_line_says():
    """origin.of_task asks each person's history once (store._witnessed) and stops at the first stranger. The edge it has to keep: the
    owner answered someone exactly once - that line is not its own witness, every other line of theirs is."""
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    tid = s.create_task({'Title': 'Site ops', 'Status': 'open', 'Kind': 'reply', 'Source': 'whatsapp'}, 't')
    line = lambda who, **kw: s.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'ConversationId': 'grp', 'SourceName': 'team', 'FromName': who,
                                            'FromEmail': who.split()[0].lower() + '@s.whatsapp.net', 'BodyText': 'y', 'Status': 'routed', **kw})
    mine = lambda: line('Alex Doyle', Status='context', Direction='out')
    once = line('Paula Vance'); mine(); line('Paula Vance'); line('Paula Vance')      # answered once: that line, and only it, proves it
    line('Omar Keller'); mine(); line('Omar Keller'); mine()                            # answered twice
    per_line = {m['MessageId']: origin.of_message(s, m) for m in s.list_messages(tid)}
    memo = {}
    assert {m['MessageId']: origin.of_message(s, m, memo) for m in s.list_messages(tid)} == per_line
    assert per_line[once][0] == 'stranger' and all(v[0] in ('trusted', 'owner') for k, v in per_line.items() if k != once)
    assert origin.of_task(s, tid)[0] == 'stranger'
    # ...and each person is asked once, however many lines they wrote: past Paula's one witness everyone is trusted, every line judged
    n = _counted(s); origin.of_task(s, tid, s.list_messages(tid)[1:])
    assert n[0] < 12, f'{n[0]} reads for 7 lines from 2 people'
    line('Omar Keller'); line('Omar Keller'); line('Omar Keller'); mine()
    n[0] = 0; origin.of_task(s, tid, s.list_messages(tid)[1:])
    assert n[0] < 12, f'{n[0]} reads for 11 lines from 2 people'


def test_a_long_chat_everyone_on_it_trusted_is_judged_per_person():
    """No stranger to stop at: every line is judged, and each of the three people is still asked once (the memo), not once a line."""
    s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
    tid = s.create_task({'Title': 'Site ops', 'Status': 'open', 'Kind': 'reply', 'Source': 'whatsapp'}, 't')
    for j in range(600):
        mine = j % 2
        name, addr = ('Alex Doyle', 'alex@northwind.example') if mine else WHO[j // 2 % 3]
        s.add_message({'TaskId': tid, 'Channel': 'whatsapp', 'ConversationId': 'grp', 'SourceName': 'team', 'FromName': name, 'FromEmail': addr,
                       'BodyText': 'y', 'Status': 'context' if mine else 'routed', 'Direction': 'out' if mine else 'in'})
    n = _counted(s)
    assert origin.of_task(s, tid)[0] == 'trusted'
    assert n[0] < 30, f'{n[0]} reads for 600 lines from 3 people'


def test_the_owner_s_first_line_after_theirs_is_the_one_that_counts():
    """talked_with's 'answered', read from the owner's first line after each of theirs, finds what reading every later line found."""
    s = MemoryStore()
    line = lambda who, **kw: s.add_message({'Channel': 'whatsapp', 'ConversationId': 'grp', 'SourceName': 'team', 'FromName': who,
                                            'FromEmail': '', 'BodyText': 'y', 'Status': 'routed', **kw})
    mine = lambda: line('Alex Doyle', Status='context', Direction='out')
    line('Gail Moreno'); line('Erin Blake'); mine(); mine(); line('Ray Colton'); mine()
    assert s.talked_with('whatsapp', 'gail moreno') is None          # Erin spoke between Gail and every line of the owner's after
    assert s.talked_with('whatsapp', 'erin blake') == 'answered'
    assert s.talked_with('whatsapp', 'ray colton') == 'answered'
    assert senders.known(s, {'channel': 'whatsapp', 'from_name': 'Ray Colton', 'conversation_id': 'grp'})[0]
