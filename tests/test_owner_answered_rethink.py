"""The owner answers a task's thread themselves, outside Taskuary (the owner, 2026-11-05: "it should trigger a revaluation of the agent pondering
i saw you responded and that took care of most of it so i recommend close it"): the agent is told so and RECOMMENDS the close - it never closes,
and the reply is not drawn as a bubble of its own. Invented people only."""
from taskuary import general, selfclose
from taskuary.store import MemoryStore


def _task(s):
    tid = s.create_task({'Title': 'Badge list for the new starters', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Badge list', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example',
                   'BodyText': 'Can you send the badge list?', 'Status': 'routed', 'SentAt': '2026-11-05 09:00:00'})
    return tid


def test_the_owners_own_reply_is_the_newest_and_marked_theirs():
    s = MemoryStore(); tid = _task(s)
    assert not general.owner_answered_last(s, tid)
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Re: Badge list', 'FromName': 'You', 'FromEmail': 'alex@northwind.example',
                   'BodyText': 'Sent it over just now.', 'Status': 'context', 'Direction': 'out', 'SentAt': '2026-11-05 09:30:00'})
    assert general.owner_answered_last(s, tid)


def test_the_agent_is_told_to_recommend_the_close_never_to_make_it():
    s = MemoryStore(); tid = _task(s)
    s.add_message({'TaskId': tid, 'Channel': 'email', 'Subject': 'Re: Badge list', 'FromName': 'You', 'FromEmail': 'alex@northwind.example',
                   'BodyText': 'Sent it over just now.', 'Status': 'context', 'Direction': 'out', 'SentAt': '2026-11-05 09:30:00'})
    system, _ = general._prompt(s, tid)
    assert selfclose.OWNER_ANSWERED_LINE in system
    assert 'recommend they close the task' in selfclose.OWNER_ANSWERED_LINE and selfclose.MARKER not in selfclose.OWNER_ANSWERED_LINE


def test_a_chat_that_opens_on_an_answer_opens_on_the_mail_that_started_it_first():
    """The owner, 2026-11-05: "input should always be first?" - a conversation picked back up opened on an answer with nothing above it."""
    s = MemoryStore(); tid = _task(s)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Here is the badge list.')
    shown = general.shown_history(s, tid)
    assert shown[0].get('brief') and shown[0]['mail'][0]['who'] == 'Gail Moreno'
    assert shown[0]['mail'][0]['words'].startswith('Can you send the badge list')
    assert shown[1]['role'] == 'assistant'
