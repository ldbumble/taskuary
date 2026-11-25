"""WHAT A CARD CARRIES AND THE ROW A MAIL STANDS IN (the spine audit, 2026-11-09). Where each card stands is the chat's log now (chatlog.advance,
tests/test_chatlog.py): the payload names no turn for it. Invented people."""
import json
from unittest import mock

from taskuary import general, server
from taskuary.store import MemoryStore


def at(s, table, key, rid, when): s._exec(f'UPDATE {table} SET CreatedAt=? WHERE {key}=?', (when, rid))
def said(s, tid, who, text, when):
    cid = s.add_comment(tid, 'owner' if who == general.USER_TYPE else 'assistant', who, text); at(s, 'comment', 'CommentId', cid, when); return cid
def chat(s):
    "Two turns: asked at 09:00 and answered at 09:02, asked again at 11:00 and answered at 11:01."
    tid = s.create_task({'Title': 'Clear the export folder', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    said(s, tid, general.USER_TYPE, 'clear out the old exports', '2026-11-05 09:00:00'); a1 = said(s, tid, general.ASSISTANT_TYPE, 'One step waits on you.', '2026-11-05 09:02:00')
    said(s, tid, general.USER_TYPE, 'and last year\'s drafts', '2026-11-05 11:00:00'); a2 = said(s, tid, general.ASSISTANT_TYPE, 'That one waits too.', '2026-11-05 11:01:00')
    return tid, f'comment-{a1}', f'comment-{a2}'


def test_a_file_a_draft_carries_is_drawn_on_its_card_never_as_a_preview_of_its_own():
    # the owner, 2026-11-10: "it should have drafted email not show me the file and the privew of the file. don't need preview need the email
    # acion card" - the sheet the agent attached to its reply stood under its answer as a file preview; a file it made for its own sake still does
    import shutil
    from taskuary import outputs
    s = MemoryStore(); tid, a1, a2 = chat(s)
    # ...from an empty folder: task 1's folder is every MemoryStore's, and a file another test left there (CI, 2026-11-15) is not this one's
    d = outputs.folder(tid); shutil.rmtree(d, True); d.mkdir(parents=True, exist_ok=True)
    (d / 'tool review.xlsx').write_bytes(b'PK'); (d / 'notes.txt').write_text('notes')
    rid = s.add_review({'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Short version attached.'})
    s._exec('UPDATE review SET Deliver=? WHERE ReviewId=?', (json.dumps({'kind': 'reply', 'to': ['paula@vendor.example'], 'attachments': [{'name': 'tool review.xlsx'}]}), rid))
    try:
        with mock.patch.object(server, 'store', s): got = server._assistant_payload(tid)
        assert [o['name'] for o in got['outputs']] == ['notes.txt']
    finally: shutil.rmtree(d, True)


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
