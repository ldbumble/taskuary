"""THE OWNER ANSWERED OUTSIDE TASKUARY (the owner, 2026-10-29): a Teams chat, the colleague wrote twice, the owner replied in Teams
themselves (channels.ingest_own_message: a `context` row, Direction out). The task opened on Came from with "Mark done is next" under an
Agent nobody started. The task's own recommended move decides it (rulebook.recommended - no model reads it, the owner 2026-11-09): Mark
done, with the reply that went as its reason. It names no section any
more - every task is Came from and its one chat, and the chat holds Mark done (the owner, 2026-11-06). Invented Northwind people only (CLAUDE.md)."""
import re
from datetime import datetime, timedelta
from unittest import mock
from taskuary import advisor, rulebook
from taskuary.channels import ingest_own_message
from taskuary.store import MemoryStore

CONV = 'teams:chat-erin'
at = lambda mins: (datetime.now() - timedelta(minutes=mins)).strftime('%Y-%m-%d %H:%M:%S')


def teams_task(s, answered=True, again=False):
    ids = [s.add_message({'ExternalId': f'tm-{i}', 'ConversationId': CONV, 'Channel': 'teams', 'SourceName': 'Teams', 'Subject': 'Chat with Erin Blake',
                          'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': at(m), 'BodyText': b, 'Status': 'routed'})
           for i, (m, b) in enumerate(((50, 'Can you look at the vendor invoice?'), (40, 'It is the one from vendor.example.')))]
    tid = s.create_task({'Title': 'Look at the vendor invoice', 'Kind': 'reply', 'Status': 'open'}, 'router')
    for m in ids: s.attach_message(m, tid)
    if answered:
        ingest_own_message(s, {'external_id': 'tm-out', 'conversation_id': CONV, 'channel': 'teams', 'source_name': 'Teams',
                               'sent_at': at(20), 'body': 'Looked - it is fine, paying it today.'}, 'your line in this chat - kept for context')
    if again:
        s.attach_message(s.add_message({'ExternalId': 'tm-again', 'ConversationId': CONV, 'Channel': 'teams', 'SourceName': 'Teams',
                                        'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': at(5),
                                        'BodyText': 'And the second one?', 'Status': 'routed'}), tid)
    return tid


def read(s, tid):
    def no_model(*a, **kw): raise AssertionError('no model reads a task')
    with mock.patch.object(advisor, 'build_llm', no_model): return advisor.decide(s, f'task:{tid}')


def test_mark_done_is_lit_where_the_owner_answered_in_teams():
    s = MemoryStore(); tid = teams_task(s)
    d = read(s, tid)
    assert (d['verb'], d['label'], d['by'], d.get('section')) == ('close', 'Mark done', 'agent', None), d
    r = rulebook.recommended_task(s, tid)
    assert r['verb'] == 'close' and re.search(r'^Your reply went .*nothing since', r['why']), 'the reply that went is its reason'


def test_nothing_answered_or_asked_again_is_not_over_and_names_no_section():
    s = MemoryStore(); tid = teams_task(s, answered=False)
    d = read(s, tid)
    assert d.get('section') is None and d['verb'] == 'regular_agent', d          # an ask no agent took: Send to agent (2026-11-10)
    s = MemoryStore(); tid = teams_task(s, again=True)
    d = read(s, tid)
    assert d.get('section') is None and d['verb'] == 'regular_agent', 'she wrote again after the answer: it is not over'


def test_the_facts_say_the_answer_and_name_no_section():
    """The answered state's facts are its line alone - no page section rides with them, lit move or not."""
    s = MemoryStore(); tid = teams_task(s)
    item = advisor._item(s, 'task', tid, key=f'task:{tid}')
    r = rulebook.facts(s, item, advisor.offered(s, item))
    assert r['state'] in ('answered', 'agent_done') and 'section' not in r and '{' not in r['line'] and 'verb' not in r
    assert not hasattr(rulebook, 'SEC')
    assert read(s, tid).get('section') is None


def test_the_api_hands_the_page_no_section(monkeypatch):
    from fastapi.testclient import TestClient
    from taskuary import server
    s = MemoryStore(); tid = teams_task(s)
    monkeypatch.setattr(server, 'store', s)
    got = TestClient(server.app).get('/api/advice', params={'key': f'task:{tid}'}).json()
    assert (got.get('verb'), got.get('section')) == ('close', None), got
    assert TestClient(server.app).get(f'/api/tasks/{tid}').json()['recommended']['verb'] == 'close', 'the task page reads it off its own payload'
