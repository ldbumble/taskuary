"""The earlier lines an ask rests on (2026-10-22). A chat line that was only a pasted list was judged as the follow-up to a question
asked weeks before in the same chat - rightly - but the task showed only the list, so its ask named something nowhere on the page.
Triage names those lines from the exchange it was shown; the task page shows them with the task's own messages."""
import json
from taskuary import ingest, triage
from taskuary.store import MemoryStore


def _store():
    s = MemoryStore()
    old_task = s.create_task({'Title': 'Look at the uncleared checks', 'Kind': 'general', 'Status': 'done'}, 'router')
    old = s.add_message({'TaskId': old_task, 'ExternalId': 'teams:1', 'ConversationId': 'chat:erin', 'Channel': 'teams', 'FromName': 'Erin Blake',
                         'FromEmail': 'teams:erin', 'SentAt': '2026-08-19 11:15:00', 'BodyText': 'can you look at the uncleared checks at the east site?'})
    return s, old


def test_the_exchange_carries_each_line_s_id_for_triage_only():
    s, old = _store()
    msg = {'conversation_id': 'chat:erin', 'sent_at': '2026-10-22 09:42:00'}
    assert ingest.exchange_lines(s, msg, ids=True)[0].startswith(f'[#{old}] Erin Blake')
    assert ingest.exchange_lines(s, msg)[0].startswith('Erin Blake')                 # the reply writer and the brief read it unmarked


def test_rests_on_keeps_only_lines_it_was_shown():
    s, old = _store()
    lines = ingest.exchange_lines(s, {'conversation_id': 'chat:erin', 'sent_at': '2026-10-22 09:42:00'}, ids=True)
    llm = lambda system, user, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'x', 'title': 't', 'summary': 's',
                                               'rests_on': [old, 99999, 'nope']})
    got = triage.classify_intent({'subject': '', 'body': 'Members: 1, 2, 3'}, llm=llm, thread={'exchange': lines})
    assert got['rests_on'] == [old]
    assert 'rests_on' not in triage.classify_intent({'subject': '', 'body': 'Members'}, llm=llm)   # no exchange shown, nothing to name
    assert 'rests_on' in triage.verdict_schema(earlier=True)['schema']['properties']
    assert 'rests_on' not in triage.verdict_schema()['schema']['properties']


def test_the_task_page_gets_the_earlier_message_without_moving_it():
    from fastapi.testclient import TestClient
    from taskuary import server
    s = server.store
    old_task = s.create_task({'Title': 'Look at the uncleared checks', 'Kind': 'general', 'Status': 'done'}, 'router')
    old = s.add_message({'TaskId': old_task, 'ExternalId': 'teams:rests-1', 'ConversationId': 'chat:rests', 'Channel': 'teams',
                         'FromName': 'Erin Blake', 'FromEmail': 'teams:erin', 'SentAt': '2026-08-19 11:15:00', 'BodyText': 'can you look at the checks?'})
    tid = s.create_task({'Title': 'Investigate the checks', 'Kind': 'general', 'Status': 'open'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'teams:rests-2', 'ConversationId': 'chat:rests', 'Channel': 'teams',
                         'FromName': 'Erin Blake', 'FromEmail': 'teams:erin', 'SentAt': '2026-10-22 09:42:00', 'BodyText': 'Members: 1, 2, 3'})
    s.add_route(mid, tid, 'create', 0.0, 'triage', [], 'router', verdict={'intent': 'task', 'rests_on': [old, mid]})
    d = TestClient(server.app).get(f'/api/tasks/{tid}').json()
    assert [m['MessageId'] for m in d['earlier']] == [old]                 # its own message is not "earlier"
    assert s.get_message(old)['TaskId'] == old_task                         # shown, never moved
