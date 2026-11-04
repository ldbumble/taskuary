"""WHERE THE CLOSE IS THE OWNER'S, THE AGENT IS TOLD SO (the desktop stress test, 2026-11-03): a general agent on a task nobody wrote in
about said "I couldn't close the task from here", a failure over finished work. Its prompt now says the owner closes it with Mark done."""
from taskuary import general, selfclose
from taskuary.store import MemoryStore


def test_a_task_the_owner_started_tells_the_agent_the_owner_closes_it():
    s = MemoryStore()
    t = s.create_task({'Title': 'Unzip the notes in Downloads', 'Kind': 'general', 'Status': 'open'}, 'owner')
    system, _ = general._prompt(s, t)
    assert selfclose.owner_closes_line() in system and 'Mark done' in selfclose.owner_closes_line()
    assert selfclose.CHAT_LINE not in system


def test_a_task_someone_wrote_in_about_keeps_the_agents_own_close():
    s = MemoryStore()
    t = s.create_task({'Title': 'March invoice batch', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': t, 'Channel': 'email', 'Subject': 'March invoice batch', 'FromName': 'Gail Moreno',
                   'FromEmail': 'gail@northwind.example', 'BodyText': 'Can you check the March batch?', 'Status': 'routed'})
    system, _ = general._prompt(s, t)
    assert selfclose.CHAT_LINE in system and selfclose.owner_closes_line() not in system
