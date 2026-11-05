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
