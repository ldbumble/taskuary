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


def test_a_finished_run_with_a_post_waiting_is_that_press_not_agent_done():
    # the owner's render check, 2026-11-08: a LinkedIn post waiting for Post read "agent done" and "the agent finished - read what it found"
    from taskuary import workerstate as ws
    s = MemoryStore(); tid = s.create_task({'Title': 'LinkedIn post: expense tool rollout', 'Kind': 'general', 'Status': 'open'}, 'owner')
    ws.record(s, tid, 'g1', 'finished', text='The post is ready for your Post.', source='api')
    s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Reason': 'the agent proposes to post on LinkedIn',
                  'DraftText': json.dumps({'action': 'run_tool', 'type': 'linkedin_post', 'text': 'Northwind rolled out Spendly.'})})
    s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'superseded', 'DraftText': 'old'})        # the newest row is not the waiting one
    assert taskstate.state(s, s.get_task(tid)) == 'approve'
