"""An open task you cleared comes back when it has been quiet for an hour.

Pressing Next or Done on a task marked it read and that was the end of it: the task tab still held
it, but the work tab never raised it again, however long it sat there open (the owner, 2026-09-15:
"when i hit done on a task it dimsses it from work but is still in the task bar... it should show
back up in the work also if it's still open later").

A task handed to an agent used to be the exception - forced unread whatever its receipts said, so it
never left the work tab at all. That was the same question answered two different ways in the same
column ("why is that one showing up but not 575"). Both now clear, and both come back.
"""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import funnel
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)
STAMP = NOW.isoformat(sep=' ')


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'back.db'))
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    yield store
    store.cx.close()


def a_task(db, title, *, assignee=None):
    tid = db.create_task({'Title': title, 'Kind': 'coding' if assignee else 'task', 'Status': 'open',
                          'Assignee': assignee}, 'triage')
    db.add_message({'TaskId': tid, 'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}',
                    'Channel': 'email', 'Subject': title, 'FromName': 'A Person',
                    'FromEmail': 'person@example.test', 'SentAt': STAMP,
                    'BodyText': 'Please look at this.', 'Status': 'routed'})
    db.reconcile_processing_membership(fixed_now=STAMP)
    db.activate_processing_reads(fixed_now=STAMP, live_state=[])
    funnel.invalidate()
    return tid


def after(**delta):
    """A moment after the clear, on the clock the receipt is stamped with. NOW is the module's
    import time, and a receipt is stamped when settle runs - on a slow CI runner that was more
    than the minute of slack these checks had, so "61 minutes after NOW" fell short of an hour
    after the clear and four tests said a task never came back (windows 3.12, 2026-09-18)."""
    return datetime.now().replace(microsecond=0) + timedelta(**delta)


def work(db, at=None):
    """The work tab: what is unread at `at`."""
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        funnel.invalidate()
        return {i['key']: i for i in funnel.build(db, now=at or NOW, live_state=[])['items']}


def clear_it(db, key):
    funnel.settle(db, key, 'done')


def only_key(db):
    return next(iter(work(db)))


def test_a_cleared_task_is_gone_from_work(db):
    a_task(db, 'Call Maya about PAM review')
    clear_it(db, only_key(db))
    assert work(db) == {}, 'Done must take it off the work tab now'


def test_it_comes_back_once_the_hour_is_up(db):
    a_task(db, 'Call Maya about PAM review')
    key = only_key(db)
    clear_it(db, key)
    assert key not in work(db, after(minutes=59)), 'it came back before the hour was up'
    assert key in work(db, after(minutes=61)), 'an open task never came back to the work tab'


def test_a_task_handed_to_an_agent_clears_like_any_other(db):
    """The asymmetry the owner found: 576 sat in work for ever while 575 vanished on Done."""
    a_task(db, 'Investigate repeated CI failures', assignee='agent:codex')
    key = only_key(db)
    clear_it(db, key)
    assert work(db) == {}, 'a queued task ignored Done and stayed in the work tab'
    assert key in work(db, after(minutes=61)), 'and then it never came back'


def test_later_still_holds_it_past_the_hour(db):
    """The nudge must not undo the owner's own "not now"."""
    a_task(db, 'Call Maya about PAM review')
    key = only_key(db)
    funnel.settle(db, key, 'later', hours=6)
    assert key not in work(db, after(minutes=61)), 'the hourly nudge overrode Later'
    assert key in work(db, after(hours=7)), 'and then Later never expired'


def test_a_closed_task_never_comes_back(db):
    tid = a_task(db, 'Call Maya about PAM review')
    key = only_key(db)
    clear_it(db, key)
    db.update_task(tid, {'Status': 'done'}, 'owner')
    assert work(db, after(days=2)) == {}, 'a closed task is not work'


def test_the_setting_moves_the_clock(db):
    db.set_setting('task_return_minutes', '5', 'owner')
    a_task(db, 'Call Maya about PAM review')
    key = only_key(db)
    clear_it(db, key)
    assert key in work(db, after(minutes=6)), 'the setting did not shorten the quiet spell'


def test_it_says_why_it_is_back(db):
    """"if they ask why explain it should be closed" - the card carries that sentence itself."""
    a_task(db, 'Call Maya about PAM review')
    key = only_key(db)
    assert not work(db)[key].get('why_open'), 'a task you have not cleared yet is not back from anywhere'
    clear_it(db, key)
    assert 'close' in (work(db, after(minutes=61))[key].get('why_open') or '').lower()


def test_the_owner_can_change_the_clock_by_saying_so(db):
    """The knob is a switch the assistant may propose, and only ever as a whole number."""
    from taskuary import proposals
    changes, why = proposals.setting_changes({'changes': [{'name': 'task_return_minutes', 'value': '90'}]})
    assert changes == [{'name': 'task_return_minutes', 'value': '90',
                        'says': proposals.SETTING_ALLOW['task_return_minutes']}], why
    assert proposals.setting_changes({'changes': [{'name': 'task_return_minutes', 'value': 'soon'}]})[1] \
        == 'task_return_minutes must be a whole number'


def test_a_nonsense_setting_falls_back_to_the_hour(db):
    from taskuary import processing_unread
    db.set_setting('task_return_minutes', 'soon', 'owner')
    assert processing_unread.return_minutes(db) == 60
