"""A CHAT TASK'S WAITING MOVE IS THE AGENT'S (the owner, 2026-11-05: "we can remove reply ready for you since it can be any action"). The rail
marks a general task's ready-to-send or waiting-agent row `chat`, and the page says "agent ready for you" over it (railStatus.chatReady); a
coding task's row is not marked and keeps its own words. Invented world only."""
from taskuary import funnel
from taskuary.store import MemoryStore


def test_the_phone_and_the_assistant_say_agent_ready_for_you_for_a_chat_task_and_a_coding_task_keeps_its_words():
    """The sentence words (funnel.lane_word) that the phone's card (remote_assistant.status_line, story_block) and the Assistant's prompt lines
    read: a chat row's ready reply and its waiting agent both say the chat word; a coding row's say its lane's."""
    from taskuary import funnel_presentation, lanes, remote_assistant
    ready = lanes.word('chat_ready')
    for lane in funnel.CHAT_READY_LANES:
        assert funnel.lane_word({'lane': lane, 'chat': True}) == ready
        assert funnel.lane_word({'lane': lane}) == funnel.LANE_WORDS[lane][0]
        assert funnel_presentation.state_of({'lane': lane, 'chat': True, 'kind': 'action'}) == ready
    assert funnel.lane_word({'lane': 'working', 'chat': True}) == funnel.LANE_WORDS['working'][0], 'only the waiting move changes words'
    assert remote_assistant.status_line({'lane': 'approve', 'chat': True, 'why': 'a draft to Erin Blake'}).startswith(ready)


def test_a_parked_chat_agent_is_ready_for_you_and_a_coding_one_waits_on_you(monkeypatch):
    from taskuary import lanes, terminal
    class GeneralSession:
        alive = True
        def waiting(self): return True
    class PtySession(GeneralSession): pass
    monkeypatch.setattr(terminal, 'session_for', lambda tid: GeneralSession())
    assert funnel.live_session_state(1)[1] == lanes.word('chat_ready')
    monkeypatch.setattr(terminal, 'session_for', lambda tid: PtySession())
    assert funnel.live_session_state(1)[1] == 'waiting on you'


def test_after_the_owner_sends_a_chat_agent_is_done_until_typed_to_again():
    """ONE CYCLE (the owner, 2026-11-06): working, waiting on you, and after a Send "agent done" - the rail row, the task's state and the
    sentence words all read taskstate.chat_moved_on."""
    from taskuary import general, lanes, taskstate
    s = MemoryStore()
    tid = s.create_task({'Title': 'Pay date for Gail', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted Gail a reply.')
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Gail, Friday. Alex'})
    live = {'alive': True, 'waiting': True, 'state': 'parked'}
    assert not taskstate.chat_moved_on(s, tid), 'a draft waits: the agent waits on you'
    s._exec("UPDATE review SET Status='approved', FinalText=DraftText, DecidedAt='2999-01-01 00:00:00' WHERE ReviewId=?", (rid,))
    assert taskstate.chat_moved_on(s, tid)
    assert taskstate.state(s, s.get_task(tid), session=live) == 'agentdone'
    assert taskstate.state(s, s.get_task(tid), session={**live, 'waiting': False}) == 'working', 'typed to again: working'
    s._exec("UPDATE comment SET CreatedAt='2999-01-02 00:00:00' WHERE TaskId=?", (tid,))
    assert not taskstate.chat_moved_on(s, tid), 'it answered again since the send: waiting on you'
    assert funnel.lane_word({'lane': 'yours', 'kind': 'wrapup', 'chat_done': True}) == lanes.word('chat_done') == 'agent done'
