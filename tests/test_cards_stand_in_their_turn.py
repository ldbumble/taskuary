"""EVERY CARD STANDS IN THE TURN THAT RAISED IT (the spine audit, 2026-11-09). A post's card was named with its answer by the server; a held
step, a proposal and a reply that went were placed by the page, which read an answer's stamp as the moment its turn BEGAN - it is when the
turn filed its answer. So a step held while the second turn worked stood, pressed, in the first; and everything still waiting rode one block
under whichever turn was newest. The chat's payload names the answer of every one of them, by the rule the post's card already had: the
first answer filed at or after it, and for a reply the turn that last left it. Invented people."""
import json
from unittest import mock

from taskuary import general, server
from taskuary.store import MemoryStore

STEP = {'action': 'shell_act', 'sid': 'run1', 'turn': 1, 'command': 'rm -rf old-export', 'shell': 'bash', 'cwd': '', 'what': 'delete the old export', 'why': 'it deletes files'}


def at(s, table, key, rid, when): s._exec(f'UPDATE {table} SET CreatedAt=? WHERE {key}=?', (when, rid))
def said(s, tid, who, text, when):
    cid = s.add_comment(tid, 'owner' if who == general.USER_TYPE else 'assistant', who, text); at(s, 'comment', 'CommentId', cid, when); return cid
def chat(s):
    "Two turns: asked at 09:00 and answered at 09:02, asked again at 11:00 and answered at 11:01."
    tid = s.create_task({'Title': 'Clear the export folder', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    said(s, tid, general.USER_TYPE, 'clear out the old exports', '2026-11-05 09:00:00'); a1 = said(s, tid, general.ASSISTANT_TYPE, 'One step waits on you.', '2026-11-05 09:02:00')
    said(s, tid, general.USER_TYPE, 'and last year\'s drafts', '2026-11-05 11:00:00'); a2 = said(s, tid, general.ASSISTANT_TYPE, 'That one waits too.', '2026-11-05 11:01:00')
    return tid, f'comment-{a1}', f'comment-{a2}'
def act(s, tid, when, p=STEP, status='pending', kind='action'):
    rid = s.add_review({'TaskId': tid, 'Kind': kind, 'Status': 'pending', 'DraftText': json.dumps(p) if kind == 'action' else p}); at(s, 'review', 'ReviewId', rid, when)
    if status != 'pending': s.decide_review(rid, status, None, 'owner')
    return str(rid)
def turns(s, tid):
    with mock.patch.object(server, 'store', s): return server._assistant_payload(tid)['turns']


def test_a_step_stands_in_the_turn_that_was_at_work_when_it_was_held():
    s = MemoryStore(); tid, a1, a2 = chat(s)
    first, second = act(s, tid, '2026-11-05 09:01:00'), act(s, tid, '2026-11-05 11:00:30', {**STEP, 'turn': 3})
    assert turns(s, tid) == {first: a1, second: a2}, 'an answer is stamped when its turn ENDS: the step held at 11:00:30 is the second turn\'s'


def test_pressed_or_waiting_it_is_the_same_turn():
    s = MemoryStore(); tid, a1, a2 = chat(s)
    ran, dropped, waits = (act(s, tid, '2026-11-05 09:01:00', status=st) for st in ('approved', 'rejected', 'pending'))
    assert turns(s, tid) == {ran: a1, dropped: a1, waits: a1}


def test_what_no_answer_has_followed_waits_at_the_foot():
    s = MemoryStore(); tid, a1, a2 = chat(s)
    late = act(s, tid, '2026-11-05 11:05:00', {'action': 'close_task', 'why': 'the folder is clear'})
    assert turns(s, tid)[late] is None
    said(s, tid, general.ASSISTANT_TYPE, 'Closing it once you say so.', '2026-11-05 11:06:00')
    assert turns(s, tid)[late].startswith('comment-') and turns(s, tid)[late] not in (a1, a2), 'the turn that answers next is the one that raised it'


def test_a_reply_stands_in_the_turn_that_last_left_it():
    s = MemoryStore(); tid, a1, a2 = chat(s)
    triaged = act(s, tid, '2026-11-05 08:00:00', 'Hi Gail - on it.', kind='draft_reply')
    kept = act(s, tid, '2026-11-05 09:01:00', 'Hi Gail - the folder is clear.', kind='draft_reply')
    s.snap_draft(int(kept), int(a2.split('-')[1]))                               # the second turn rewrote it
    got = turns(s, tid)
    assert (got[triaged], got[kept]) == (a1, a2)
    s.decide_review(int(kept), 'approved', 'Hi Gail - the folder is clear.', 'owner')
    assert turns(s, tid)[kept] == a2, 'sent, it is the card in that turn still'


def test_an_email_owed_is_no_card_of_a_turn():
    s = MemoryStore(); tid, a1, a2 = chat(s)
    slot = act(s, tid, '2026-11-05 09:01:00', 'Hi Ray,', kind='slot')
    assert slot not in turns(s, tid)
