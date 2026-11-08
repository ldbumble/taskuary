"""PROMPT MACHINERY IS NOT A COMMENT (the owner, 2026-11-08): a brief Taskuary handed the agent, a turn's summary JSON and a line kept for a turn
were rows like any comment, so exports, search, the phone, an agent's my_task and the Assistant read them raw. One filter in the store keeps
them out unless a reader asks with `internal` - the agent's own machinery does, and the chat still draws its brief and summary. Invented people."""
import json

from taskuary import general
from taskuary.store import MemoryStore, is_internal


def test_machinery_rows_stay_out_of_every_reader_but_the_agents_own():
    s = MemoryStore(); tid = s.create_task({'Title': 'Reply to Erin on the Q4 room', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'THIS TASK IS A REPLY OWED to Erin Blake.')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted Erin a reply.')
    s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps({'about': 'Erin asked for a room', 'did': 'Drafted the reply'}))
    general.wait_line(s, tid, 'make it 3pm')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Keep Gail on cc.')
    shown = [c['Body'] for c in s.list_comments(tid)]
    assert shown == ['Drafted Erin a reply.', 'Keep Gail on cc.'], shown
    assert len(s.list_comments(tid, internal=True)) == 5 and sum(map(is_internal, s.list_comments(tid, internal=True))) == 3
    assert [c['Body'] for c in s.task_detail(tid)['comments']] == shown                      # what the API hands every page and tool
    hist = general.shown_history(s, tid)                                                      # ...and the chat still draws the brief
    assert hist[0].get('brief') and any(m.get('summary') for m in hist)
    assert [x['text'] for x in general.waiting_lines(s, tid)] == ['make it 3pm']
