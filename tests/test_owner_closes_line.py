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


def test_a_task_someone_wrote_in_about_is_closed_by_the_owner_too():
    # the owner, 2026-11-05: the agent never closes a chat task - not even one somebody wrote in about
    s = MemoryStore()
    t = s.create_task({'Title': 'March invoice batch', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': t, 'Channel': 'email', 'Subject': 'March invoice batch', 'FromName': 'Gail Moreno',
                   'FromEmail': 'gail@northwind.example', 'BodyText': 'Can you check the March batch?', 'Status': 'routed'})
    system, _ = general._prompt(s, t)
    assert selfclose.CHAT_LINE not in system and selfclose.owner_closes_line() in system


def test_a_draft_is_said_in_a_line_and_its_words_are_the_cards():
    """The agent walk, 2026-11-10: each draft was said twice - subject and body quoted in the answer, over the card that showed them."""
    s = MemoryStore()
    t = s.create_task({'Title': 'March invoice batch', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': t, 'Channel': 'email', 'Subject': 'March invoice batch', 'FromName': 'Gail Moreno',
                   'FromEmail': 'gail@northwind.example', 'BodyText': 'Can you check the March batch?', 'Status': 'routed'})
    line = selfclose.owner_closes_line()
    assert 'say in one line what you set up and for whom' in line and "never repeat the draft's words" in line and 'assum' in line
    marked = general._prompt(s, t)[0]; tooled = general.by_tool(marked)
    for system in (marked, tooled): assert system.count("never repeat the draft's words") == 1
    # ...a session that drafts by marked block writes the words once, in the block: there the block IS the draft
    assert 'the block IS the draft' in selfclose.REPLY_LINE and 'the block IS the draft' in selfclose.DRAFT_LINE
    assert 'the block IS the draft' not in tooled and 'never as text in the conversation' not in marked
