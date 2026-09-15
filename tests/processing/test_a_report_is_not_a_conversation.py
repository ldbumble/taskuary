"""A report opens on the report, not on four earlier days of itself.

A one-line ask needs the lines said before it, so the panel carries them in and recedes them. A
DAILY REPORT is not an ask: nobody sent it, each day is self-contained, and its conversation id
names the recurring job rather than a topic. The End of day checkup opened on four previous days'
digests at 58% opacity with today's below the fold (the owner, 2026-09-15: "why does this look so
faded?") - every bubble on the screen was context.
"""
from datetime import datetime, timedelta

import pytest

from taskuary import processing_all
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'reports.db'))
    yield store
    store.cx.close()


def a_thread(db, channel, conversation, subjects, source='End of day checkup'):
    mids = []
    for i, subject in enumerate(subjects):
        when = (NOW - timedelta(days=len(subjects) - i)).isoformat(sep=' ')
        mids.append(db.add_message({
            'ExternalId': f'x:{conversation}:{i}', 'ConversationId': conversation, 'Channel': channel,
            'SourceName': source, 'Subject': subject, 'FromName': source,
            'FromEmail': 'reports@example.test', 'SentAt': when,
            'BodyText': f'Body of {subject}', 'Status': 'routed'}))
    db.reconcile_processing_membership(fixed_now=NOW.isoformat(sep=' '))
    return mids


def bubbles(db, mid):
    target = db.resolve_processing_target('legacy_funnel', f'msg:{mid}')
    detail = processing_all.item_detail(db, target['item_id'], live_state=[])['detail']
    ask = set(detail.get('ask_ids') or [])
    return [(m['MessageId'], m['MessageId'] in ask) for m in detail.get('messages') or []]


def test_a_report_opens_on_itself_alone(db):
    mids = a_thread(db, 'report', 'report:end-of-day',
                    ['End of day checkup ' + str(n) for n in range(5)])
    drawn = bubbles(db, mids[-1])
    assert drawn == [(mids[-1], True)], 'earlier days were carried in as context for a self-contained report'


def test_a_conversation_still_arrives_with_what_came_before_it(db):
    """The rule that made context exist is untouched: a one-line ask keeps its lead-in."""
    mids = a_thread(db, 'email', 'c:budgeting', ['Budgets', 'Re: Budgets', 'Budgeting'],
                    source='Tabitha')
    drawn = bubbles(db, mids[-1])
    assert len(drawn) > 1, 'a short ask lost the lines said before it'
    assert drawn[-1] == (mids[-1], True)
    assert any(not is_ask for _mid, is_ask in drawn), 'the earlier lines must still be named as context'
