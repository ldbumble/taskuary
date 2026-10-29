"""THE OWNER ANSWERED OUTSIDE TASKUARY (the owner, 2026-10-29): a Teams chat, the colleague wrote twice, the owner replied in Teams
themselves (channels.ingest_own_message: a `context` row, Direction out). The task opened on Came from with "Mark done is next" under an
Agent nobody started. The Advisor's own pick decides it: its Mark done carries the reply that went as its reason, and names Close out as the
section its move is in - the section the page opens on (taskLayout.sectionHere). Invented Northwind people only (CLAUDE.md)."""
from datetime import datetime, timedelta
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


def test_the_advisors_mark_done_names_close_out_where_the_owner_answered_in_teams():
    s = MemoryStore(); tid = teams_task(s)
    d = advisor.decide(s, f'task:{tid}')
    assert (d['verb'], d['label'], d.get('section')) == ('close', 'Mark done', 'close'), d
    assert d['line'].startswith('Your reply went') and 'nothing since' in d['line'], d['line']


def test_nothing_answered_or_asked_again_names_no_section():
    s = MemoryStore(); tid = teams_task(s, answered=False)
    assert advisor.decide(s, f'task:{tid}').get('section') is None
    s = MemoryStore(); tid = teams_task(s, again=True)
    d = advisor.decide(s, f'task:{tid}')
    assert d.get('section') is None and d.get('verb') != 'close', d


def test_the_rule_carries_the_section_only_beside_its_lit_move():
    """rulebook.SEC rides with the state's facts and is handed on only with a verb lit - never as a line or a fact of the strip."""
    s = MemoryStore(); tid = teams_task(s)
    item = advisor._item(s, 'task', tid, key=f'task:{tid}')
    r = rulebook.decide(s, item, advisor.offered(s, item))
    assert (r['verb'], r.get('section')) == ('close', 'close') and '{' not in r['line'] and rulebook.SEC not in r


def test_the_api_hands_the_page_the_section_it_opens_on(monkeypatch):
    from fastapi.testclient import TestClient
    from taskuary import server
    s = MemoryStore(); tid = teams_task(s)
    monkeypatch.setattr(server, 'store', s)
    got = TestClient(server.app).get('/api/advice', params={'key': f'task:{tid}'}).json()
    assert (got.get('verb'), got.get('section')) == ('close', 'close'), got
