"""A colleague answers the question on the thread while a reply draft waits: the redraft's NO REPLY puts the draft down as not needed -
closed unsent, kept under Not sent with its words (the owner, 2026-11-09: no card, no Send for a reply nobody owes) - instead of leaving it
"ready to send"."""
import os, tempfile
from unittest import mock

import pytest

from taskuary import learn, responder
from taskuary.store import MemoryStore, SQLiteStore
from tests.test_review_delivery_safety import make_review, BODY


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def redraft(s, said, rid, tid):
    with mock.patch.object(learn, 'learn_from'): return responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: said)


def test_no_reply_with_why_puts_the_pending_draft_down_as_not_needed(s):
    tid, mid, rid = make_review(s)
    assert redraft(s, 'NO REPLY\n\nWHY: Gail Moreno answered Ray on 11/4.', rid, tid) == ''
    rv = s.get_review(rid)
    assert rv['Status'] == 'closed_unsent' and rv['DraftText'] == BODY and 'Gail Moreno answered Ray on 11/4' in rv['NotNeeded']
    assert rv['DecideNote'].startswith('withdrawn - ') and s.pending_review(tid) is None     # nothing left to draw, nothing to Send
    assert s.get_task(tid)['Status'] == 'open'
    assert any('not needed' in c['Body'] and 'Not sent' in c['Body'] for c in s.list_comments(tid))


def test_no_reply_without_why_says_a_plain_default(s):
    tid, mid, rid = make_review(s)
    redraft(s, 'NO REPLY', rid, tid)
    assert 'no longer asks you for a reply' in s.get_review(rid)['NotNeeded']


def test_a_draft_marked_under_the_old_rule_is_retired_when_the_store_opens():
    # one marked Not needed before 2026-11-09 still sat pending with Send under it: it goes where a withdrawn draft goes
    fn = os.path.join(tempfile.mkdtemp(), 'old.db')
    s = SQLiteStore(fn); tid, mid, rid = make_review(s)
    s._exec("UPDATE review SET NotNeeded='Gail answered it' WHERE ReviewId=?", (rid,)); s.close()
    s = SQLiteStore(fn)
    rv = s.get_review(rid)
    assert (rv['Status'], rv['DecideNote'], rv['DraftText']) == ('closed_unsent', 'withdrawn - Gail answered it', BODY)
    s.close()


def test_a_first_draft_that_says_no_reply_is_put_down_as_before(s):
    tid, mid, rid = make_review(s)
    s._exec("UPDATE review SET DraftText=NULL WHERE ReviewId=?", (rid,))
    redraft(s, 'NO REPLY', rid, tid)
    rv = s.get_review(rid)
    assert rv['Status'] == 'no_reply' and not rv.get('NotNeeded')
