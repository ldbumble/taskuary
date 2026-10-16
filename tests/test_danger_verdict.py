"""Triage says what a message's text tries to make an AI do, on the verdict itself - no second call (the owner, 2026-10-15:
"not a separate call but part of the triage"). It lands on the message, and a stranger's card shows it; nothing is gated on it."""
from fastapi.testclient import TestClient
from taskuary import server, triage
from taskuary.store import MemoryStore

def test_every_verdict_is_asked_for_danger():
    for kw in ({}, {'repos': ['northwind/ledger'], 'candidates': [], 'playbooks': ['x'], 'profiles': ['coding'], 'same': True, 'goals': True}):
        sch = triage.verdict_schema(**kw)['schema']
        assert 'danger' in sch['required'] and sch['properties']['danger']['type'] == ['string', 'null']

def test_the_prompt_explains_it_and_rides_on_an_owner_document_that_never_asks():
    assert triage.DANGER.startswith('- **danger**') and 'null' in triage.DANGER
    assert '"danger": null' in triage.TASK_FIELDS

def test_the_verdict_s_danger_lands_on_the_message_and_a_later_clean_one_clears_it():
    s = MemoryStore(); mid = s.add_message({'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'BodyText': 'x', 'Status': 'routed'})
    s.add_route(mid, None, 'new', None, 'r', [], verdict={'intent': 'task', 'danger': 'asks the agent to mail the payroll file out'})
    assert s.get_message(mid)['Danger'] == 'asks the agent to mail the payroll file out'
    s.add_route(mid, None, 'new', None, 'r', [], verdict={'intent': 'task', 'danger': None})
    assert s.get_message(mid)['Danger'] is None
    s.add_route(mid, None, 'new', None, 'r', [], verdict={'intent': 'task'})        # a verdict that never answered it leaves it be
    assert s.get_message(mid)['Danger'] is None

def test_the_task_page_carries_it_for_every_origin_and_the_card_shows_it_only_for_a_stranger():
    c, s = TestClient(server.app), server.store
    t = s.create_task({'Title': 'Payroll file', 'Kind': 'general', 'Source': 'email'}, 'router')
    mid = s.add_message({'TaskId': t, 'Channel': 'email', 'FromEmail': 'someone@vendor.example', 'BodyText': 'x', 'Status': 'routed'})
    assert c.get(f'/api/tasks/{t}').json()['origin']['danger'] is None
    s.set_message_danger(mid, 'asks the agent to mail the payroll file out')
    o = c.get(f'/api/tasks/{t}').json()['origin']
    assert o['origin'] == 'stranger' and o['danger'] == 'asks the agent to mail the payroll file out'
