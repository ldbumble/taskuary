"""A colleague answers the question on the thread while a reply draft waits: the redraft's NO REPLY marks the draft Not needed (kept,
Send still works) instead of leaving it "ready to send"."""
from unittest import mock

import pytest

from taskuary import learn, responder
from taskuary.store import MemoryStore
from tests.test_review_delivery_safety import make_review, BODY


@pytest.fixture
def s():
    v = MemoryStore(); yield v; v.close()


def redraft(s, said, rid, tid):
    with mock.patch.object(learn, 'learn_from'): return responder.draft_for_review(s, tid, rid, llm=lambda *a, **k: said)


def test_no_reply_with_why_marks_the_pending_draft_not_needed(s):
    tid, mid, rid = make_review(s)
    assert redraft(s, 'NO REPLY\n\nWHY: Gail Moreno answered Ray on 11/4.', rid, tid) == ''
    rv = s.get_review(rid)
    assert rv['Status'] == 'pending' and rv['DraftText'] == BODY and 'Gail Moreno answered Ray on 11/4' in rv['NotNeeded']
    assert s.get_task(tid)['Status'] == 'open'
    assert any('not needed' in c['Body'] for c in s.list_comments(tid))


def test_no_reply_without_why_says_a_plain_default(s):
    tid, mid, rid = make_review(s)
    redraft(s, 'NO REPLY', rid, tid)
    assert 'no longer asks you for a reply' in s.get_review(rid)['NotNeeded']


def test_a_later_real_redraft_clears_it(s):
    tid, mid, rid = make_review(s)
    redraft(s, 'NO REPLY', rid, tid)
    redraft(s, 'Hi Ray,\n\nThe export runs again.\n\nThanks,', rid, tid)
    rv = s.get_review(rid)
    assert not rv['NotNeeded'] and 'The export runs again' in rv['DraftText']


def test_a_first_draft_that_says_no_reply_is_put_down_as_before(s):
    tid, mid, rid = make_review(s)
    s._exec("UPDATE review SET DraftText=NULL WHERE ReviewId=?", (rid,))
    redraft(s, 'NO REPLY', rid, tid)
    rv = s.get_review(rid)
    assert rv['Status'] == 'no_reply' and not rv.get('NotNeeded')
