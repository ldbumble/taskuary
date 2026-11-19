"""AN EMAIL THE AGENT SET UP WAITS ON YOU (the product audit, 2026-11-08). A chat task whose agent drafted an email to Paula read "agent done"
in its header and went under Reports, while its session said it waited on you: every "is anything waiting" asked store.pending_review,
which leaves a task's emails (slots.py) out because they are never its reply. store.waiting_on_owner counts them, and the rail, the
task's state and its stage all read it. Invented people."""
import json

from taskuary import funnel, general, stages, taskstate
from taskuary.store import MemoryStore


def chat_with_email():
    s = MemoryStore()
    tid = s.create_task({'Title': 'Q4 budget review room', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'The email to Paula Vance is ready for your Send.')
    rid = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi Paula - 3pm.',
                        'Deliver': json.dumps({'channel': 'email', 'to': ['paula@northwind.example'], 'cc': []})})
    return s, tid, rid


def test_an_unsent_agent_email_is_what_waits_on_you_everywhere():
    s, tid, rid = chat_with_email()
    assert s.pending_review(tid) is None and s.waiting_on_owner(tid)['ReviewId'] == rid
    live = {'alive': True, 'waiting': True, 'state': 'parked'}
    assert taskstate.state(s, s.get_task(tid), session=live) == 'approve'
    assert taskstate.state(s, s.get_task(tid)) == 'approve', 'idled out or restarted: it reads as it did live'
    assert stages.state_of(s, s.get_task(tid)) == 'approve'
    assert not taskstate.chat_moved_on(s, tid)
    row = funnel.from_agents(s, live_state=[{'taskId': tid, 'agent': 'assistant', 'sid': 'g1', 'mode': 'assistant', 'waiting': True,
                                             'state': 'parked', 'line': 'the agent is ready for you', 'tail': []}])[0]
    assert row['kind'] == 'agent' and row.get('lane') != 'report'


def test_once_the_email_is_sent_the_chat_agent_is_done_for_now():
    s, tid, rid = chat_with_email()
    s._exec("UPDATE review SET Status='approved', DeliveryState='sent' WHERE ReviewId=?", (rid,))
    assert s.waiting_on_owner(tid) is None
    assert taskstate.state(s, s.get_task(tid), session={'alive': True, 'waiting': True, 'state': 'parked'}) == 'agentdone'
    # ...and its row stays under Tasks, where the open task was - it went to the Reports pile with the send (the agent walk, 2026-11-09)
    from taskuary import lanes
    row = funnel.from_agents(s, live_state=[{'taskId': tid, 'agent': 'assistant', 'sid': 'g1', 'mode': 'assistant', 'waiting': True,
                                             'state': 'parked', 'line': '', 'tail': []}])[0]
    assert (row['kind'], row.get('chat_done'), lanes.lane_section(row['lane'])) == ('wrapup', True, 'task')


def test_a_finished_run_with_a_post_waiting_is_that_press_not_agent_done():
    # the owner's render check, 2026-11-08: a LinkedIn post waiting for Post read "agent done" and "the agent finished - read what it found"
    from taskuary import workerstate as ws
    s = MemoryStore(); tid = s.create_task({'Title': 'LinkedIn post: expense tool rollout', 'Kind': 'general', 'Status': 'open'}, 'owner')
    ws.record(s, tid, 'g1', 'finished', text='The post is ready for your Post.', source='api')
    s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'the agent proposes to post on LinkedIn',
                  'DraftText': json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'Northwind rolled out Spendly.'})})
    s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'superseded', 'DraftText': 'old'})        # the newest row is not the waiting one
    assert taskstate.state(s, s.get_task(tid)) == 'approve'


def test_a_reply_held_behind_a_post_is_lit_and_offered_nowhere():
    # the roads audit, 2026-11-19 (#4): "what waits on him" had two answers - waiting_on_owner (the pill, the rail) left out a card held behind
    # another (cardqueue), pending_review (the desk's lit Send, the phone's picks, the Assistant) did not. Ray Colton's reply, written behind a
    # post still waiting, was the phone's "Send the reply" while the pill and the chat said the post stood. Every surface asks one rule now.
    from taskuary import asks, cardqueue, rulebook
    s = MemoryStore(); tid = s.create_task({'Title': 'Expense tool rollout post', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
    post = s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'the agent proposes to post on LinkedIn',
                         'DraftText': json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'Northwind rolled out Spendly.'})})
    reply = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Ray - the post goes up today.'})
    assert cardqueue.held(s, tid) == {reply}
    assert s.pending_review(tid)['ReviewId'] == reply, 'the row a decider re-drafts into is still found'
    assert s.waiting_on_owner(tid)['ReviewId'] == post
    assert rulebook._draft(s, {'tid': tid}, 'task', tid)['ReviewId'] == post, "the desk's lit button is the card that stands"
    text, picks = asks.phone_text(s, s.get_task(tid), 'approve', 'a post waits for your Post')
    assert 'Hi Ray' not in text and not any(a.get('rid') == reply for _, a in picks), 'the phone offers no held reply'
    assert s.waiting_on_owner(tid, ('draft', 'draft_reply')) is None


def test_the_tasks_status_and_its_words_are_said_once_by_the_server():
    # the roads audit, 2026-11-19 (#9): the pill put a chat's words, a reply owed and a failed start over the state key in the page, while the
    # phone and the list said the key's own words - one function says the status and its words, and the page's detail carries it
    from fastapi.testclient import TestClient
    from unittest import mock
    from taskuary import lanes, server
    s, tid, rid = chat_with_email()
    s._exec("UPDATE review SET Status='approved', DeliveryState='sent' WHERE ReviewId=?", (rid,))
    with mock.patch.object(server, 'store', s):
        got = TestClient(server.app).get(f'/api/tasks/{tid}').json()
    assert got['state'] == taskstate.state(s, s.get_task(tid)) == 'agentdone'
    assert got['status'] == taskstate.status(s, s.get_task(tid)) and (got['status']['key'], got['status']['word']) == ('chat_done', lanes.word('chat_done'))
    # ...a reply owed that nothing has written is said so, never "ready to send"
    r = MemoryStore(); t = r.create_task({'Title': 'Visitor parking', 'Kind': 'reply', 'Status': 'open'}, 'o')
    r.add_review({'TaskId': t, 'Kind': 'draft', 'Status': 'pending', 'DraftText': ''})
    assert taskstate.state(r, r.get_task(t)) == 'approve' and taskstate.status(r, r.get_task(t))['word'] == lanes.word('owed')
    # ...and a start that failed says it could not start, never "waiting to start"
    assert taskstate.status(r, r.get_task(t), key='queued', queued={'State': 'failed'})['key'] == 'start_failed'
