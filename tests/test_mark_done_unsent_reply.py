"""MARK DONE OVER A READY REPLY SAYS SO (walk 2026-10-29): the drafted reply was put down as no reply without a word, and the task
kept its reply-owed tag after it closed. Now the close writes one line on the task, the tag goes, and nothing asks to confirm."""
import pytest

from taskuary import concierge, funnel
from taskuary.ingest import REPLY_TAG
from taskuary.store import MemoryStore
from taskuary.testing import Factory

LINE = 'Closed without sending the drafted reply.'


@pytest.fixture
def s():
    v = MemoryStore(); funnel.invalidate(); yield v; v.close()


def task_with(s, draft):
    f = Factory(s)
    tid = f.task(title='Quarterly sync', kind='reply')
    mid = f.message(tid, from_email='omar@northwind.example', from_name='Omar Keller', subject='Quarterly sync')
    rid = f.review(tid, mid, draft=draft)
    s.tag_task(tid, REPLY_TAG, actor='triage')
    return tid, rid


def said(s, tid): return [c['Body'] for c in s.list_comments(tid)]


def test_a_ready_reply_closed_unsent_is_said_once_and_the_tag_goes(s):
    tid, rid = task_with(s, 'Hi Omar,\n\nFriday at 10 works.')
    assert concierge.close_task(s, tid, 'owner')
    assert s.get_task(tid)['Status'] == 'done' and s.get_review(rid)['Status'] == 'no_reply'
    assert said(s, tid).count(LINE) == 1
    assert not s.task_has_tag(tid, REPLY_TAG)


def test_no_draft_written_no_line(s):
    tid, _ = task_with(s, None)
    concierge.close_task(s, tid, 'owner')
    assert LINE not in said(s, tid) and not s.task_has_tag(tid, REPLY_TAG)
