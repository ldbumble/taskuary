"""THE OWNER'S REPLY IS AN INPUT ON THE CANVAS (the owner, 2026-11-09, said ~40 times: "if we respond show on left side and then agent
reevaluates if action still required ... any new input pushes up the last agent turn").

The shape: the agent drafted a reply to Erin in a WhatsApp group; the owner answered Erin from the phone. Their line stands in the task's
chat BELOW the agent's turn, as theirs; the re-read says in one line that nothing more is owed, never quoting their words again; and the
draft is gone - nothing pending, so no card and no Send. Invented people only."""
import json
from unittest import mock

from taskuary import channels, general, slots
from taskuary.store import MemoryStore

CONV = 'whatsapp:120363000000000077@g.us'


def room(s, title='Erin asks about the Friday meeting'):
    tid = s.create_task({'Title': title, 'Kind': 'general', 'Status': 'open'}, 't')
    s._exec("UPDATE task SET CreatedAt='2026-11-09 11:00:00' WHERE TaskId=?", (tid,))
    mid = s.add_message({'TaskId': tid, 'ExternalId': f'{CONV}:IN{tid}', 'ConversationId': CONV, 'Channel': 'whatsapp', 'FromName': 'Erin Blake',
                         'FromEmail': 'whatsapp:8000', 'SentAt': '2026-11-09 11:50:00', 'BodyText': 'should I come over for the meeting?',
                         'Status': 'routed'})
    s._exec("UPDATE message SET CreatedAt='2026-11-09 11:50:00' WHERE MessageId=?", (mid,))
    return tid, mid


def drafted(s, tid, mid):
    s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, 'brief')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I drafted a reply asking Erin to come over.')
    rows = s._rows('SELECT CommentId FROM comment WHERE TaskId=? ORDER BY CommentId', (tid,))
    for r, at in zip(rows, ('2026-11-09 11:55:00', '2026-11-09 11:56:00')): s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (at, r['CommentId']))
    return s.add_review({'TaskId': tid, 'MessageId': mid, 'ConversationId': CONV, 'Kind': 'draft_reply', 'Status': 'pending',
                         'DraftText': 'Hi Erin, yes - come over for the meeting.', 'SentAt': '2026-11-09 11:50:00'})


def own(s, ext='ME1', at='2026-11-09 12:07:00', body="up to you but I'm good with it"):
    with mock.patch.object(channels, 'reread', return_value=('covered', '')):
        channels.ingest_own_message(s, {'external_id': ext, 'channel': 'whatsapp', 'conversation_id': CONV, 'sent_at': at, 'body': body,
                                        'from_email': 'me'}, 'your line in the chat')


def test_the_owners_reply_stands_after_the_agent_turn_and_the_one_line_rethink_retires_the_draft():
    s = MemoryStore(); tid, mid = room(s); rid = drafted(s, tid, mid)
    own(s)
    assert s.get_review(rid)['Status'] == 'superseded' and s.pending_review(tid) is None        # no card, no Send
    msgs = general.shown_history(s, tid)
    turn = next(i for i, m in enumerate(msgs) if m['role'] == 'assistant')
    mine = next(i for i, m in enumerate(msgs) if any(x['own'] for x in m.get('mail') or []))
    assert turn < mine, 'the owner\'s line lands below the agent turn it came after'
    x = next(x for x in msgs[mine]['mail'] if x['own'])
    assert (x['who'], x['channel'], x['words']) == ('You', 'whatsapp', "up to you but I'm good with it")
    said = [m['content'][0]['text'] for m in msgs[mine + 1:] if m['role'] == 'assistant']
    assert said == ['You answered Erin Blake yourself - no new response needed.'], said        # one line, their words not said twice


def test_a_reply_filed_on_the_other_task_in_the_room_is_drawn_here_too():
    # two asks in one group: the owner's line is filed on one task, and the other's agent hears it (own_replies) - its chat draws it as well
    s = MemoryStore(); tid, mid = room(s); drafted(s, tid, mid)
    other, _ = room(s, 'Erin asks for the slides')
    s.add_message({'TaskId': other, 'ExternalId': 'ME2', 'ConversationId': CONV, 'Channel': 'whatsapp', 'FromName': 'You', 'SentAt': '2026-11-09 12:09:00',
                   'BodyText': 'slides are in the shared folder', 'Status': 'context', 'Direction': 'out'})
    msgs = general.shown_history(s, tid)
    mail = [x for m in msgs for x in m.get('mail') or [] if x['own']]
    assert [(x['who'], x['words']) for x in mail] == [('You', 'slides are in the shared folder')]
    assert msgs[-1].get('mail') and msgs[-1]['mail'][-1]['own'], 'the newest input is at the foot, under the last turn'


def test_a_marker_draft_with_no_address_is_heard_on_the_next_turn():
    # the HIPAA AI drafts through a marker, read after its turn ends: the "no address" the tool road returns at once reaches it next turn
    s = MemoryStore(); tid, mid = room(s)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'I drafted the email to the bank.')
    s._write_checklist(tid, [{'id': 'e1', 'text': 'Email the bank', 'out': {'kind': 'email', 'to': 'Harbor Savings Bank'}}], 't')
    with mock.patch.object(slots, 'address_for', return_value=('', False)):
        out = slots.draft(s, tid, 'Hello - please send the statement.', 'Harbor Savings Bank', 'Statement', 'e1', 'assistant')
    assert out.get('ok') and out.get('to_missing') == slots.to_missing('Harbor Savings Bank')
    assert slots.needs_address(s, tid) == [(out['review_id'], 'Harbor Savings Bank')]
    lb = general.latest_block(s, tid)
    assert 'AN EMAIL YOU DRAFTED HAS NO ADDRESS' in lb and slots.to_missing('Harbor Savings Bank') in lb
    d = json.loads(s.get_review(out['review_id'])['Deliver']); assert d['to'] == [] and d['needs'] == 'Harbor Savings Bank'
