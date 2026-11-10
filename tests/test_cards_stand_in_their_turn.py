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
    # ...a draft written before his first line is no card of the turn that line began (the owner, 2026-11-10): with no row before it, none
    assert (got[triaged], got[kept]) == (None, a2)
    s.decide_review(int(kept), 'approved', 'Hi Gail - the folder is clear.', 'owner')
    assert turns(s, tid)[kept] == a2, 'sent, it is the card in that turn still'


def test_an_email_owed_is_no_card_of_a_turn():
    s = MemoryStore(); tid, a1, a2 = chat(s)
    slot = act(s, tid, '2026-11-05 09:01:00', 'Hi Ray,', kind='slot')
    assert slot not in turns(s, tid)


def test_a_file_a_draft_carries_is_drawn_on_its_card_never_as_a_preview_of_its_own():
    # the owner, 2026-11-10: "it should have drafted email not show me the file and the privew of the file. don't need preview need the email
    # acion card" - the sheet the agent attached to its reply stood under its answer as a file preview; a file it made for its own sake still does
    import shutil
    from taskuary import outputs
    s = MemoryStore(); tid, a1, a2 = chat(s)
    d = outputs.folder(tid); d.mkdir(parents=True, exist_ok=True)
    (d / 'tool review.xlsx').write_bytes(b'PK'); (d / 'notes.txt').write_text('notes')
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Short version attached.'})
    s._exec('UPDATE review SET Deliver=? WHERE ReviewId=?', (json.dumps({'kind': 'reply', 'to': ['paula@vendor.example'], 'attachments': [{'name': 'tool review.xlsx'}]}), rid))
    try:
        with mock.patch.object(server, 'store', s): got = server._assistant_payload(tid)
        assert [o['name'] for o in got['outputs']] == ['notes.txt']
    finally: shutil.rmtree(d, True)


def test_a_draft_written_before_the_owner_s_line_is_no_card_of_the_turn_that_line_began():
    # the owner, 2026-11-10: "i asked it to rewrite a email, it reqrote in place then put it under the prompt" - a reply drafted on arrival, before
    # any turn: named with the first answer filed after it, its card (and once replaced, its record) stood in the turn his rewrite began
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor review for Erin', 'Kind': 'general', 'Status': 'open'}, 't')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                         'SentAt': '2026-11-10 08:00:00', 'BodyText': 'Your review of the tool?', 'Status': 'routed'})
    old = act(s, tid, '2026-11-10 08:01:00', 'A long review of every flaw.', kind='draft_reply')
    said(s, tid, general.USER_TYPE, 'make it shorter and attach the sheet', '2026-11-10 09:00:00')
    a1 = said(s, tid, general.ASSISTANT_TYPE, 'Rewrote it short.', '2026-11-10 09:00:20')
    new = act(s, tid, '2026-11-10 09:00:10', 'Short version, sheet attached.', kind='draft_reply')
    got = turns(s, tid)
    assert got[new] == f'comment-{a1}', 'the new letter is the turn\'s that wrote it'
    assert got[old] != f'comment-{a1}', 'the old one is not: it stands where it stood, before his line'


def test_the_mail_that_came_in_keeps_one_id_before_and_after_the_owner_s_first_line():
    # the browser walk, 2026-11-10: the row of the mail that started a task was "came-in-<its message>" while nothing else was in the chat and
    # "came-in-<the task>" once the owner had typed - two ids for one row, so a card placed under it found no row and was drawn nowhere for a beat
    s = MemoryStore(); tid = s.create_task({'Title': 'Vendor review for Erin', 'Kind': 'general', 'Status': 'open'}, 't')
    for i in range(3): s.add_message({'TaskId': None, 'ExternalId': f'x{i}', 'Channel': 'email', 'FromEmail': 'gail@northwind.example', 'BodyText': 'other', 'Status': 'routed'})
    s.add_message({'TaskId': tid, 'ExternalId': 'm1', 'Channel': 'email', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                   'SentAt': '2026-11-10 08:00:00', 'BodyText': 'Your review of the tool?', 'Status': 'routed'})
    ids = lambda: [m['id'] for m in general.shown_history(s, tid) if m.get('brief') and m.get('mail')]
    first = ids()
    said(s, tid, general.USER_TYPE, 'make it shorter', '2099-11-10 09:00:00')
    assert first and ids() == first, (first, ids())
