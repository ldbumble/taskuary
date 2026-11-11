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
    assert 'say in ONE short line what you set up and for whom' in line and 'never repeat any of that' in line and 'assum' in line
    # ...nor its id (agent walk 2, 2026-11-10: "send it after rv3"): the prompt names drafts by Taskuary's handle, which the owner never sees
    assert selfclose.HANDLES_LINE in line and 'the owner never sees it' in line
    marked = general._prompt(s, t)[0]; tooled = general.by_tool(marked)
    for system in (marked, tooled): assert system.count("never repeat any of that") == 1
    # ...a session that drafts by marked block writes the words once, in the block: there the block IS the draft
    assert 'the block IS the draft' in selfclose.REPLY_LINE and 'the block IS the draft' in selfclose.DRAFT_LINE
    assert 'the block IS the draft' not in tooled and 'never as text in the conversation' not in marked


def test_the_draft_tools_answer_says_the_same_one_sentence():
    # the owner, 2026-11-10: on a turn that REPLACED a waiting reply the agent quoted the new one whole, and its scratch folder's path under it -
    # the tool's own answer said nothing of the card. One sentence (selfclose.CARD_SAID): in the guide every general turn carries, and in the answer
    from taskuary import agenttools
    assert selfclose.CARD_SAID in selfclose.owner_closes_line() and 'the file it carries' in selfclose.CARD_SAID
    assert agenttools.said_once({'ok': True, 'review_id': 7})['shown'] == selfclose.CARD_SAID
    assert 'shown' not in agenttools.said_once({'ok': False, 'why': 'nothing was saved'})
