"""Next on a task handed to an agent that never started must not choose it again.

An assigned-but-unstarted task is forced unread whatever its read receipts say - that clause keeps
live work visible - and `queued` was not one of the lanes allowed to carry the shown-mark. So the
walk introduced it, the walk chose it again, and no amount of pressing Next got past it (the owner,
2026-09-14: "i keep on clicking next on the assistant idea but it just comes right back behind the
current one"). It stays in the work tab; it just stops being what comes next.
"""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import funnel
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0).isoformat(sep=' ')


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'walk.db'))
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    yield store
    store.cx.close()


def handed_over(db, title, sender):
    tid = db.create_task({'Title': title, 'Kind': 'coding', 'Status': 'open',
                          'Assignee': 'agent:codex'}, 'triage')
    db.add_message({'TaskId': tid, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}',
                    'Channel': 'email', 'Subject': title, 'FromName': 'A Person', 'FromEmail': sender,
                    'SentAt': NOW, 'BodyText': 'Please look at this.', 'Status': 'routed'})
    return tid


def activate(db):
    db.reconcile_processing_membership(fixed_now=NOW)
    db.activate_processing_reads(fixed_now=NOW, live_state=[])
    funnel.invalidate()


def test_a_queued_task_shown_once_is_not_offered_again(db):
    handed_over(db, 'Add skip policy for PCC provisioning mail', 'assistant@example.test')
    handed_over(db, 'Something else entirely', 'other@example.test')
    activate(db)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        first = funnel.next_item(db)
        assert first is not None
        assert first['lane'] == 'queued', first['lane']
        db.set_funnel_state(first['key'], 'surfaced')       # what showing it in the chat records
        funnel.invalidate()
        again = funnel.next_item(db)
    assert again is not None, 'the walk went silent with other work waiting'
    assert again['key'] != first['key'], 'Next bounced straight back to the row it had just shown'


def test_it_is_still_unread_work_on_the_rail(db):
    """Shown is not settled: the task tab must still hold it, or Next would be a way to lose work."""
    handed_over(db, 'Add skip policy for PCC provisioning mail', 'assistant@example.test')
    activate(db)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        shown = funnel.next_item(db)
        db.set_funnel_state(shown['key'], 'surfaced')
        funnel.invalidate()
        item = next(i for i in funnel.build(db, keep_surfaced=True)['items'] if i['key'] == shown['key'])
    assert item['unread'] is True, 'shown is not settled - the work tab must still hold it'
    assert item['surfaced'] is True, 'and the mark that keeps the walk off it is recorded'
