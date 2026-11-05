"""A CHAT TASK'S WAITING MOVE IS THE AGENT'S (the owner, 2026-11-05: "we can remove reply ready for you since it can be any action"). The rail
marks a general task's ready-to-send or waiting-agent row `chat`, and the page says "agent ready for you" over it (railStatus.chatReady); a
coding task's row is not marked and keeps its own words. Invented world only (demo.seed)."""
from taskuary import demo, funnel
from taskuary.store import MemoryStore


def test_a_chat_tasks_ready_row_is_marked_and_a_coding_tasks_is_not():
    s = MemoryStore(); demo.seed(s); funnel.invalidate()
    tids = sorted({i['tid'] for i in funnel.pile(s, force=True)['items'] if i.get('lane') == 'approve' and i.get('tid')})
    assert len(tids) >= 2, 'the demo has two drafts waiting on tasks'
    s._exec("UPDATE task SET Kind='general' WHERE TaskId=?", (tids[0],)); s._exec("UPDATE task SET Kind='coding' WHERE TaskId=?", (tids[1],))
    funnel.invalidate()
    rows = {i['tid']: i for i in funnel.pile(s, force=True)['items'] if i.get('tid') in tids[:2] and i.get('lane') == 'approve'}
    assert rows[tids[0]].get('chat') is True and not rows[tids[1]].get('chat')
    assert all(i.get('lane') in funnel.CHAT_READY_LANES for i in funnel.pile(s, force=True)['items'] if i.get('chat'))


def test_the_phone_and_the_assistant_say_agent_ready_for_you_for_a_chat_task_and_a_coding_task_keeps_its_words():
    """The sentence words (funnel.lane_word) that the phone's card (remote_assistant.status_line, story_block) and the Assistant's prompt lines
    read: a chat row's ready reply and its waiting agent both say the chat word; a coding row's say its lane's."""
    from taskuary import funnel_presentation, lanes, remote_assistant
    ready = lanes.word('chat_ready')
    for lane in funnel.CHAT_READY_LANES:
        assert funnel.lane_word({'lane': lane, 'chat': True}) == ready
        assert funnel.lane_word({'lane': lane}) == funnel.LANE_WORDS[lane][0] != ready
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
