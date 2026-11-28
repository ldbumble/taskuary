"""EVERY PRESS OF HIS, COUNTED - NEVER TIMED (the owner, 2026-11-27: "we can't have things slow down. it needs to feel snappy... don't like time
tests but code test"). Each press the owner makes is run through the real routes on the cold rail's synthetic home (400+ tasks, thousands of
mail, two profiles - tests/processing/test_cold_rail_after_restart.py) and every SQL statement it runs is counted, on every connection. The
bound is what the press costs today plus a small margin: a read per row, per line or per task anywhere under it breaks it by hundreds or thousands.
Invented people only."""
import json, threading, time
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import cardqueue, chatlog, context, funnel, general, origin, outbound, proposals, server
from tests.processing.test_cold_rail_after_restart import _traced, _two_profiles, home, restarted  # noqa: F401 - the shared home

OWNER = {'X-Taskuary-Token': 'pytest-owner-token'}
c = TestClient(server.app)


@pytest.fixture
def desk(restarted, monkeypatch):
    """The restarted home with his two profiles, the rail built and settled, and one task of his own: Erin's 60-line thread, a letter to Send, an act to
    Approve and a draft to Dismiss. Nothing leaves the machine: a letter's and an act's far side are stood in at their one seam."""
    s, tids = restarted
    _two_profiles(s)
    tid = s.create_task({'Title': 'October close with Erin', 'Kind': 'general', 'Status': 'open', 'Source': 'email', 'OriginBase': 'owner'}, 'owner')
    for j in range(60):                                          # ...enough lines that a read per line is hundreds of statements
        s.add_message({'TaskId': tid, 'Channel': 'email', 'ExternalId': f'oct-{j}', 'ConversationId': 'oct-close', 'Subject': 'October close',
                       'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SourceName': 'alex@northwind.example',
                       'BodyText': f'line {j} on the October close ' * 10, 'Status': 'routed', 'Direction': 'in', 'SentAt': f'2026-11-2{j % 7} 09:00:00'})
    deliver = json.dumps({'channel': 'email', 'to': ['erin@northwind.example'], 'subject': 'October close'})
    rids = {'send': s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi Erin - the close is done. Alex',
                                  'Reason': 'assistant wrote this email', 'Deliver': deliver}),
            'approve': s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': 'the agent proposes to remind',
                                     'DraftText': json.dumps({'action': 'break_out', 'title': 'Split the close'})}),
            'dismiss': s.add_review({'TaskId': tid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'A draft he will not send', 'Reason': 'drafted'})}
    # ...COUNTED, NEVER TIMED: what is kept across reads for a while (a task's state, PILE_EVERY; one read's memo, cardqueue.FRESH) is kept
    # here for the whole test, so the count is the press's work and never how long the machine took to get to it. A write still ends both
    monkeypatch.setattr(funnel, 'PILE_EVERY', 3600); monkeypatch.setattr(cardqueue, 'FRESH', 3600.0)
    monkeypatch.setattr(outbound, 'send_out', lambda *a, **k: {'channel': 'email', 'to': k.get('to') or []})
    monkeypatch.setattr(outbound, 'send_block', lambda *a, **k: '')
    monkeypatch.setattr(proposals, '_run', lambda *a, **k: {'done': True})
    monkeypatch.setattr(context, 'warm', lambda *a, **k: None)
    started = mock.MagicMock(); started.return_value.send_prompt.return_value = 'On it.'
    monkeypatch.setattr(general, 'start_session', started)
    # ...the rail as he left it before the press. His first open makes what it makes once, each on its own thread - the one copy of the home
    # before the chat log (chatlog.backed_up) and his mailboxes' signatures read off Sent mail (signatures._later) - and then the rail is built,
    # its kept holds judged until judging lifts nothing more (a trusted line lifting a stranger's task is recorded once), and built again
    for path in (f'/api/tasks/{tid}', f'/api/tasks/{tid}/conversation'): c.get(path)
    for _ in range(200):
        if chatlog.backed_up(s) and not any(t.name == 'account-signature' for t in threading.enumerate()): break
        time.sleep(0.05)
    server._pile_payload(force=True, fyi=50)
    gen = lambda: s._one("SELECT Gen FROM change_gen WHERE Tbl='trust'")['Gen']
    for _ in range(10):
        was = gen()
        for t in s._rows("SELECT TaskId FROM task WHERE Status NOT IN ('done', 'dropped')"): origin.hold(s, t['TaskId'])
        if gen() == was: break
    for path in (f'/api/tasks/{tid}', f'/api/tasks/{tid}/conversation'): c.get(path)
    server._pile_payload(force=True, fyi=50)
    fyi = s._one("SELECT MessageId FROM message WHERE TaskId IS NULL AND Channel='email' AND Status='filed' ORDER BY MessageId DESC")['MessageId']
    yield s, tid, rids, fyi, tids


def _count(s, monkeypatch, press) -> int:
    reads = _traced(s, monkeypatch)
    press()
    n = len(reads)
    for cx in (s.cx, s._rail_cx, *s._readers):
        if cx is not None: cx.set_trace_callback(None)
    return n


# EACH BOUND IS TODAY'S COUNT ON THIS HOME (2026-11-27, 0.4.6.13 with the stored holds kept) PLUS A SMALL MARGIN - every statement on every
# connection, a trigger's own steps too. The press's task has 60 lines and the rail 2,400+ rows, so a read per line or per row is hundreds or
# thousands over. Measured: open 454, poll 101 (unchanged 101), Send ~557, Approve 179, Dismiss 176, rail served 24 / rebuilt 8,661,
# search 150, Reply ~264, his first line ~575 and his next one ~150.
BOUND = {'open': 540, 'poll': 130, 'send': 660, 'approve': 215, 'dismiss': 210, 'rail': 60, 'rebuilt': 10_000, 'search': 180, 'reply': 320,
         'line': 680, 'next line': 190}


def test_opening_a_task_reads_no_row_per_line(desk, monkeypatch):
    s, tid, *_ = desk
    n = _count(s, monkeypatch, lambda: c.get(f'/api/tasks/{tid}', params={'opened': 1}).raise_for_status())
    assert n < BOUND['open'], f'opening a 60-line task ran {n} statements'


def test_the_chat_poll_reads_no_row_per_line(desk, monkeypatch):
    s, tid, *_ = desk
    rev = c.get(f'/api/tasks/{tid}/conversation').json()['rev']
    n = _count(s, monkeypatch, lambda: c.get(f'/api/tasks/{tid}/conversation').raise_for_status())
    same = _count(s, monkeypatch, lambda: c.get(f'/api/tasks/{tid}/conversation', params={'rev': rev}).raise_for_status())
    assert n < BOUND['poll'] and same < BOUND['poll'], f'the chat poll ran {n} statements, {same} unchanged'


@pytest.mark.parametrize('verb', ['send', 'approve', 'dismiss'])
def test_a_card_press_reads_no_row_per_line(desk, monkeypatch, verb):
    s, tid, rids, *_ = desk
    body = {'verb': 'reject' if verb == 'dismiss' else 'approve', **({'final_text': 'Hi Erin - the close is done. Alex'} if verb == 'send' else {})}
    n = _count(s, monkeypatch, lambda: c.post(f'/api/reviews/{rids[verb]}/decide', headers=OWNER, json=body).raise_for_status())
    assert s.get_review(rids[verb])['Status'] == ('rejected' if verb == 'dismiss' else 'approved'), 'the press did what it says'
    assert n < BOUND[verb], f'{verb} ran {n} statements'


def test_loading_the_rail_reads_no_row_per_row(desk, monkeypatch):
    s, *_ = desk
    n = _count(s, monkeypatch, lambda: c.get('/api/funnel/pile', params={'fyi': 50}).raise_for_status())
    funnel.invalidate()
    rebuilt = _count(s, monkeypatch, lambda: c.get('/api/funnel/pile', params={'fyi': 50, 'force': True}).raise_for_status())
    assert n < BOUND['rail'], f'the rail as it stands ran {n} statements'
    assert rebuilt < BOUND['rebuilt'], f'the rail rebuilt ran {rebuilt} statements'


def test_a_search_reads_no_row_per_result(desk, monkeypatch):
    s, *_ = desk
    n = _count(s, monkeypatch, lambda: c.get('/api/search', params={'q': 'October close'}).raise_for_status())
    assert n < BOUND['search'], f'a search ran {n} statements'


def test_reply_on_an_fyi_reads_no_row_per_row(desk, monkeypatch):
    s, tid, rids, fyi, _ = desk
    n = _count(s, monkeypatch, lambda: c.post(f'/api/messages/{fyi}/reply', headers=OWNER, json={}).raise_for_status())
    assert n < BOUND['reply'], f'Reply on an FYI ran {n} statements'


def test_his_line_in_a_task_hands_its_thread_once(desk, monkeypatch):
    """His first line hands the agent the task's mail it has not heard (once a message); his next reads nothing per line."""
    s, tid, *_ = desk
    say = lambda text: c.post(f'/api/tasks/{tid}/assistant/messages', headers=OWNER, json={'text': text}).raise_for_status()
    first = _count(s, monkeypatch, lambda: say('Send Erin the totals'))
    then = _count(s, monkeypatch, lambda: say('And the sheet'))
    assert first < BOUND['line'] and then < BOUND['next line'], f'his line ran {first} statements, his next {then}'
