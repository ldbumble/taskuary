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

from taskuary import events, general, selfclose, server, wrapup
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
    s._exec('UPDATE task SET TrustedThrough=? WHERE TaskId=?', (10 ** 9, tid))      # he trusts this thread: an untrusted sender's task starts no agent (origin.hold)
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


# what happened rides in the TURN as its events (events.take), not the system prompt: there they changed it every turn, and a CLI chat's
# system prompt is its process's command line, so each turn started a new process


def test_already_sent_replies_are_in_the_turns_context():
    s = MemoryStore(); tid, _, sent, _ = the_owners_day(s)
    _, turn = general._prompt(s, tid)
    line = next(l for l in turn.splitlines() if f'Card rv{sent} ' in l and 'approved' in l)
    assert 'gail@northwind.example' in line and line.endswith('he approved it')

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
    # ...the marker's own road: his line sets a draft older than it aside as it is heard (proposals.set_aside_drafts) - held off here, so the
    # marker is what settles it
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=lambda system, user, **kw: answer), mock.patch('taskuary.hooks.judge_ended'), \
            mock.patch('taskuary.proposals.set_aside_drafts', return_value=[]):
        reply = sess.send_prompt('so withdraw it')
    assert 'TASKUARY-WITHDRAW' not in reply and s.get_review(rid)['DecideNote'] == wrapup.WITHDRAWN + 'wrong month'
    s2 = MemoryStore(); tid2, _, _, rid2 = the_owners_day(s2)
    with mock.patch.object(server, 'store', s2), mock.patch.object(server, '_own_task_only'):
        r = TestClient(server.app).post('/api/agent/withdraw-draft', json={'task_id': tid2, 'why': 'wrong month'})
    assert r.json() == {'ok': True, 'review_id': rid2}


def test_the_cli_and_tools_offer_withdraw():
    from taskuary import agenttools, cli, floor
    assert 'withdraw_draft' in cli.STRANGER_ACTS and '--withdraw-draft' in floor.TASKUARY_OK
    assert 'withdraw_draft' in agenttools.TOOLS and 'reply_not_needed' not in agenttools.TOOLS     # one take-back tool, an own ask's emails too


def test_the_owners_presses_since_the_last_turn_are_in_the_turns_context():
    # the owner, 2026-11-08: Remind me, Watch it, Change, a send on its card - the agent's next turn heard none of them
    s = MemoryStore(); tid = s.create_task({'Title': 'Payworth renewal', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted Gail an email.')
    s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:00' WHERE TaskId=?", (tid,))
    rid = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'Reason': 'the email to Gail', 'DraftText': 'Hi Gail'})
    s.decide_review(rid, 'approved', 'Hi Gail', 'owner')
    s.audit('task', tid, 'remind', 'owner', detail={'from': None, 'to': '2026-11-10 09:00:00'})
    s.audit('task', tid, 'priority', 'owner', detail={'from': 'regular', 'to': 'urgent'})
    s.audit('task', tid, 'continue-work', 'owner'); s.audit('task', tid, 'woke', 'assistant')      # the turn itself; not the owner's
    did = [e['what'] for e in events.pending(s, tid) if e['kind'] == 'press']
    monday = f"set a reminder for {general.clock_of('2026-11-10 09:00:00')} - put away until then"
    assert sorted(did) == sorted([monday, 'changed its priority from regular to urgent']), did
    # ...and the card he pressed is said once, by its card's event, never a second time as a press
    assert events.take(s, tid)[0].count(f'Card rv{rid} ') == 2 and 'he approved it' in events.take(s, tid)[0]
    # ...and each press is the owner's own line in the chat, at its time - a line, never a turn (the owner, 2026-11-08)
    lines = [m for m in general.shown_history(s, tid) if m.get('press')]
    assert [m['content'][0]['text'] for m in lines] == [f'You {monday}.', 'You changed its priority from regular to urgent.']
    assert all(m['role'] == 'user' for m in lines) and not [m for m in general.history(s, tid) if m.get('press')]


def test_an_email_the_owner_dropped_is_told_to_its_agent_and_is_a_line_in_the_chat():
    # the agent walk, 2026-11-09: "Don't send" on one of two emails - its agent heard "turned down rv3 (<its own caption>)", or nothing at
    # all for an email not drafted yet, and went on saying the dropped one "waits for Send"
    from taskuary import slots
    s = MemoryStore(); tid = s.create_task({'Title': 'Trainly rollout', 'Kind': 'general', 'Status': 'open', 'Source': 'assistant'}, 'owner')
    slots.add(s, tid, [{'to': 'Ray Colton', 'about': 'the new date'}, {'to': 'paula@northwind.example', 'about': 'the licence count'}], 'triage')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted Paula an email.')
    rid = slots.draft(s, tid, 'Hi Paula', to='paula@northwind.example', agent='assistant')['review_id']
    s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:00' WHERE TaskId=?", (tid,))
    for i in slots.open_(s, tid): slots.drop(s, tid, i['id'], 'owner')
    did = [e['what'] for e in events.pending(s, tid) if e['kind'] == 'press']
    assert did == ['dropped the email to Ray Colton - it will not be sent', 'dropped the email to paula@northwind.example - it will not be sent'], did
    lines = [m['content'][0]['text'] for m in general.shown_history(s, tid) if m.get('press')]
    assert lines == ['You dropped the email to Ray Colton - it will not be sent.', 'You dropped the email to paula@northwind.example - it will not be sent.'], lines
    assert s.get_review(rid)['Status'] == 'rejected'


def test_a_reminder_the_agent_set_is_a_line_in_the_chat():
    # the agent walk, 2026-11-09: asked to "remind me Wednesday", the agent set it by tool and the page showed it nowhere but in its prose
    from taskuary import remind
    s = MemoryStore(); tid = s.create_task({'Title': 'Trainly rollout', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'On it.')
    remind.set_reminder(s, tid, '2099-11-11 09:00', 'assistant', agent=True)
    at = s.get_task(tid)['RemindAt']
    lines = [m for m in general.shown_history(s, tid) if m.get('press')]
    assert [m['content'][0]['text'] for m in lines] == [f'Reminder set for you: {general.clock_of(at)}.'], lines
    assert not [e for e in events.pending(s, tid) if e['kind'] == 'press'] and not [m for m in general.history(s, tid) if m.get('press')]   # the agent's own act: never told back to it
    remind.set_reminder(s, tid, None, 'owner')                                                              # ...the owner's own stays theirs
    assert [m['content'][0]['text'] for m in general.shown_history(s, tid) if m.get('press')][-1] == 'You took the reminder off.'


def test_one_person_on_two_channels_is_named_by_address_and_channel():
    # the night run, 2026-11-09: asked to answer Gail on WhatsApp, the agent's "to: Gail Moreno" fitted her email and her chat line, and
    # the refusal named no address but the email's - so the reply went by email
    s = MemoryStore(); tid = s.create_task({'Title': 'October accrual', 'Kind': 'general', 'Status': 'open'}, 'owner')
    for ext, ch, frm in (('e1', 'email', 'gail@northwind.example'), ('w1', 'whatsapp', 'whatsapp:15550004444')):
        mid = s.add_message({'ExternalId': ext, 'ConversationId': ext, 'Channel': ch, 'FromName': 'Gail Moreno', 'FromEmail': frm,
                             'SentAt': '2026-11-09 02:00:00', 'BodyText': 'accrual?', 'Status': 'routed'}); s.attach_message(mid, tid)
    hit, why = wrapup.addressee(s, tid, 'Gail Moreno')
    assert hit is None and 'whatsapp:15550004444 on whatsapp' in why and 'gail@northwind.example on email' in why, why
    assert wrapup.addressee(s, tid, 'whatsapp:15550004444')[0]


def test_a_letter_filed_while_his_line_still_waits_for_the_turn_is_a_new_draft():
    """The overnight audit, 2026-11-10, in a coding chat: a reply drafted on arrival waited; the owner typed "make it shorter"; the coding
    turn filed its new letter before its record took his line (still kept for the turn, general.WAITING_TYPE) - and the old draft was
    rewritten in place, under his line, instead of greying where it stood with the new letter a card of its own."""
    s = MemoryStore(); tid, mid = task_with(s)
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': OLD})
    at(s, 'review', 'ReviewId', rid, '2026-11-06 14:48:00')
    at(s, 'comment', 'CommentId', general.wait_line(s, tid, 'make it shorter'), '2026-11-06 15:22:00')
    out = wrapup.agent_reply(s, tid, NEW, 'assistant', sid='c1')
    assert out['ok'] and out['review_id'] != rid
    old = s.get_review(rid)
    assert (old['Status'], old['DecideNote'], old['DraftText']) == ('closed_unsent', wrapup.REPLACED, OLD)


def test_a_close_a_message_reopened_since_is_told_with_the_reopening():
    # a stress round, 2026-11-18: Mark done, then a question that reopened the task woke its agent - told "marked it done" under "take it as
    # said, never undo it", and nowhere that the task was open again because of the message it was woken for
    from taskuary import concierge, ingest
    s = MemoryStore(); tid = s.create_task({'Title': 'Offsite venue for Erin', 'Kind': 'general', 'Status': 'open'}, 'owner')
    s.add_comment(tid, 'agent', general.ASSISTANT_TYPE, 'Harbor Hall is booked.')
    s._exec("UPDATE comment SET CreatedAt='2000-01-01 00:00:00' WHERE TaskId=?", (tid,))
    concierge.close_task(s, tid, 'owner')
    assert [e['what'] for e in events.pending(s, tid) if e['kind'] == 'press'] == ['marked it done']
    ingest._reopen(s, tid, {'from_name': 'Erin Blake', 'subject': 'Which room?'}, 'router', {'intent': 'reply_only'})
    assert [e['what'] for e in events.pending(s, tid) if e['kind'] == 'press'] == ['marked it done'], 'his close, once: the message that reopened it is its own event'

def test_the_owners_line_this_turn_carries_is_not_quoted_in_its_facts_as_well():
    """The Continue round, 2026-11-18: a finished chat, Mark done, then Continue with a note. The kept conversation's turn is the note, and the
    facts above it - there because he closed and reopened - quoted it again as THE NEWEST MESSAGE: his note reached the agent twice. The facts
    name it, and point at the line; a mail that is the newest is still quoted (it is in the turn nowhere else)."""
    s = MemoryStore(); tid = s.create_task({'Title': 'Compare payroll vendors', 'Kind': 'general', 'Status': 'open'}, 'owner')
    at(s, 'comment', 'CommentId', s.add_comment(tid, 'owner', general.USER_TYPE, 'compare the payroll vendors on price'), '2026-11-06 14:00:00')
    at(s, 'comment', 'CommentId', s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Payworth is cheapest.'), '2026-11-06 14:01:00')
    s.audit('task', tid, 'close_from_assistant', 'owner'); s.audit('task', tid, 'reopened', 'owner')
    note = 'now check the south office too'
    at(s, 'comment', 'CommentId', s.add_comment(tid, 'owner', general.USER_TYPE, note), '2099-01-01 00:00:00')
    assert general._prompt(s, tid)[1].count(note) == 1, 'a fresh turn: the conversation ends on it, said once'
    assert 'The owner marked it done.' in general._prompt(s, tid)[1]


def test_a_withdraw_marker_never_takes_back_the_letter_its_own_turn_wrote():
    """WALK 8 (2026-11-20): a reply raised empty waited for his times; the next turn's propose_reply filled that very card, then the turn ended
    with [[TASKUARY-WITHDRAW which=rv<n>]] for "the earlier draft" - its own new letter. The chat said "drafted for your Send" over no card."""
    s = MemoryStore(); tid, _, _, rid = the_owners_day(s)
    s._exec("UPDATE review SET DraftText='' WHERE ReviewId=?", (rid,))
    summ = f"{selfclose.SUMMARY_OPEN}{json.dumps({'did': 'Drafted it'})}{selfclose.SUMMARY_CLOSE}"
    def turn(system, user, **kw):
        assert wrapup.agent_reply(s, tid, 'Hi Gail, the November list is attached. Alex', 'assistant')['review_id'] == rid
        return f"[[TASKUARY-WITHDRAW which=rv{rid}: replaced by the new letter]]\nThe reply is drafted for your Send.\n{summ}"
    with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')): sess = general.GeneralSession(s, tid)
    with mock.patch.object(general.llm_mod, 'build_llm', return_value=turn), mock.patch('taskuary.hooks.judge_ended'), \
            mock.patch('taskuary.proposals.set_aside_drafts', return_value=[]):
        sess.send_prompt('the November one, please')
    assert s.get_review(rid)['Status'] == 'pending', 'the card it just wrote still stands'
