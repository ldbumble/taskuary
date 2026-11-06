"""LATEST MESSAGE WINS (the owner, 2026-11-06).

"I told it the file you made is wrong but when it generated response it generated response to the first question of incoming not the most
recent one ... it's just resending the original response that was already sent." A draft was waiting, the owner corrected the agent, and the
next turn left that draft standing under its own Next steps as though it answered the correction. Now each turn is told the newest message,
the draft waiting and when it was made, and what already went; a later turn's letter takes the old draft's place; the agent can withdraw one;
and the chat hears which turn a draft is and whether a newer message passed it by. Invented people only.
"""
import json
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, selfclose, server, wrapup
from taskuary.store import MemoryStore

SENT = 'Hi Gail - the October list is attached.'
OLD = 'Hi Gail - attached is the October list again, as promised.'
NEW = 'Hi Gail - sorry, the list I sent had the wrong month. The corrected November list is attached.'
FIX = 'the file you made is wrong - it is the October list, she asked for November'


def task_with(s):
    tid = s.create_task({'Title': 'Vendor list', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'g-1', 'ConversationId': 'conv-g', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'Subject': 'Vendor list', 'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'SentAt': '2026-11-05 09:00:00',
                         'BodyText': 'Can you send me the vendor list?', 'Status': 'routed'})
    s._exec("UPDATE message SET CreatedAt='2026-11-05 09:00:00' WHERE MessageId=?", (mid,))
    return tid, mid


def at(s, table, key, rid, when): s._exec(f'UPDATE {table} SET CreatedAt=? WHERE {key}=?', (when, rid))


def the_owners_day(s):
    """Yesterday a reply went; today at 14:48 a turn left another draft; at 15:22 the owner corrected the agent; a turn answered at 15:23
    and left the draft untouched."""
    tid, mid = task_with(s)
    sent = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': SENT})
    s.decide_review(sent, 'approved', SENT, 'owner'); s._exec("UPDATE review SET DecidedAt='2026-11-05 18:10:00' WHERE ReviewId=?", (sent,))
    s.add_comment(tid, 'owner', general.USER_TYPE, 'send her the list again'); a1 = s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted it.')
    rid = wrapup.agent_reply(s, tid, OLD, 'assistant', sid='s1', follow_up=True)['review_id']
    s.snap_draft(rid, a1)
    for t, k, i, w in (('comment', 'CommentId', a1 - 1, '2026-11-06 14:47:00'), ('comment', 'CommentId', a1, '2026-11-06 14:48:00'),
                       ('draft_snapshot', 'ReviewId', rid, '2026-11-06 14:48:00'), ('review', 'ReviewId', rid, '2026-11-06 14:48:00')): at(s, t, k, i, w)
    at(s, 'comment', 'CommentId', s.add_comment(tid, 'owner', general.USER_TYPE, FIX), '2026-11-06 15:22:00')
    return tid, mid, sent, rid


# the facts ride in the TURN (general.turn_facts), not the system prompt: there they changed it every turn, and a CLI chat's system
# prompt is its process's command line, so each turn started a new process
def test_a_correction_after_a_pending_draft_names_the_newest_message_and_the_draft():
    s = MemoryStore(); tid, _, _, rid = the_owners_day(s)
    system, turn = general._prompt(s, tid)
    assert selfclose.LATEST_LINE in turn and 'THE NEWEST MESSAGE' not in system
    assert 'THE NEWEST MESSAGE - from the owner (in this chat)' in turn and FIX in turn
    assert f'THE DRAFT WAITING NOW (rv{rid}, to Gail Moreno, drafted at 02:48 PM' in turn and 'BEFORE the newest message' in turn
    assert OLD in turn and selfclose.WITHDRAW_LINE in turn


def test_already_sent_replies_are_in_the_turns_context():
    s = MemoryStore(); tid, *_ = the_owners_day(s)
    _, turn = general._prompt(s, tid)
    assert 'ALREADY SENT ON THIS TASK - never draft these again' in turn
    line = next(l for l in turn.splitlines() if SENT in l)
    assert 'to Gail Moreno' in line and line.startswith('- 06:10 PM')

def test_a_resumed_turn_carries_the_draft_and_the_sent_but_not_a_bare_answer():
    s = MemoryStore(); tid, *_ = the_owners_day(s)
    b = general.latest_block(s, tid, resumed=True)
    assert 'THE DRAFT WAITING NOW' in b and 'ALREADY SENT ON THIS TASK' in b
    t = s.create_task({'Title': 'x', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_comment(t, 'owner', general.USER_TYPE, 'hi'); s.add_comment(t, 'assistant', general.ASSISTANT_TYPE, 'Hello.')
    assert general.latest_block(s, t) and not general.latest_block(s, t, resumed=True)    # the CLI has the chat; its turn is the newest


def test_a_new_mail_is_the_newest_message_and_the_replan_says_latest_wins():
    from taskuary import ingest
    s = MemoryStore(); tid, *_ = the_owners_day(s)
    m = s.add_message({'TaskId': tid, 'ExternalId': 'g-2', 'ConversationId': 'conv-g', 'Channel': 'email', 'FromName': 'Gail Moreno',
                       'FromEmail': 'gail@northwind.example', 'BodyText': 'Actually I need the December one.', 'Status': 'routed'})
    at(s, 'message', 'MessageId', m, '2026-11-06 15:40:00')
    assert general.newest_message(s, tid)['who'] == 'Gail Moreno'
    assert 'withdraw' in ingest.REPLAN and 'newest message' in ingest.REPLAN


def test_the_agents_new_draft_supersedes_the_old_one():
    s = MemoryStore(); tid, _, _, rid = the_owners_day(s)
    out = wrapup.agent_reply(s, tid, NEW, 'assistant', sid='s1')
    assert out['ok'] and out['review_id'] != rid
    old = s.get_review(rid)
    assert old['Status'] == 'closed_unsent' and old['DecideNote'] == wrapup.REPLACED and old['DraftText'] == OLD
    pend = s._rows("SELECT * FROM review WHERE TaskId=? AND Status='pending'", (tid,))
    assert [r['DraftText'] for r in pend] == [NEW], 'one pending reply per person'
    # ...and the same turn saving its letter again rewrites its own draft in place
    again = wrapup.agent_reply(s, tid, NEW + ' Thanks.', 'assistant', sid='s1')
    assert again['review_id'] == out['review_id']


def test_withdraw_closes_the_draft_with_why():
    from taskuary import verdicts
    s = MemoryStore(); tid, _, _, rid = the_owners_day(s)
    assert verdicts.withdraw(s, tid, '', 'assistant')['ok'] is False
    out = verdicts.withdraw(s, tid, 'the owner says the file was the wrong month', 'assistant')
    assert out == {'ok': True, 'review_id': rid}
    rv = s.get_review(rid)
    assert rv['Status'] == 'closed_unsent' and rv['DecideNote'] == wrapup.WITHDRAWN + 'the owner says the file was the wrong month'
    assert s.pending_review(tid) is None and verdicts.withdraw(s, tid, 'again', 'assistant')['ok'] is False


def test_withdraw_by_its_marker_and_by_the_cli_door():
    s = MemoryStore(); tid, _, _, rid = the_owners_day(s)
    summ = f"{selfclose.SUMMARY_OPEN}{json.dumps({'did': 'Withdrew it'})}{selfclose.SUMMARY_CLOSE}"
    answer = f"You're right - that was October.\n[[TASKUARY-WITHDRAW: wrong month]]\n{summ}"
    with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')): sess = general.GeneralSession(s, tid)
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: answer), mock.patch('taskuary.hooks.judge_ended'):
        reply = sess.send_prompt('so withdraw it')
    assert 'TASKUARY-WITHDRAW' not in reply and s.get_review(rid)['DecideNote'] == wrapup.WITHDRAWN + 'wrong month'
    s2 = MemoryStore(); tid2, _, _, rid2 = the_owners_day(s2)
    with mock.patch.object(server, 'store', s2), mock.patch.object(server, '_own_task_only'):
        r = TestClient(server.app).post('/api/agent/withdraw-draft', json={'task_id': tid2, 'why': 'wrong month'})
    assert r.json() == {'ok': True, 'review_id': rid2}


def test_a_pending_draft_the_newest_turn_left_untouched_is_stale_with_its_time():
    s = MemoryStore(); tid, _, _, rid = the_owners_day(s)
    a1 = s._one('SELECT CommentId FROM draft_snapshot WHERE ReviewId=?', (rid,))['CommentId']
    # ...not yet: the owner wrote, nothing answered
    assert general.draft_turns(s, tid) == [{'review': rid, 'turn': f'comment-{a1}', 'at': '2026-11-06 14:48:00', 'stale': False, 'before': None}]
    at(s, 'comment', 'CommentId', s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Looked again.'), '2026-11-06 15:23:00')
    assert general.draft_turns(s, tid) == [{'review': rid, 'turn': f'comment-{a1}', 'at': '2026-11-06 14:48:00', 'stale': True, 'before': '2026-11-06 15:22:00'}]
    with mock.patch.object(server, 'store', s):
        assert server._assistant_payload(tid)['drafts'][0]['stale'] is True


def test_the_cli_and_tools_offer_withdraw():
    from taskuary import agenttools, cli, floor
    assert 'withdraw_draft' in cli.STRANGER_ACTS and '--withdraw-draft' in floor.TASKUARY_OK
    assert 'withdraw_draft' in agenttools.TOOLS and 'withdraw_draft' in agenttools.REPLY_TOOLS
