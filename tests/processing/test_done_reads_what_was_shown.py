"""Done and Next put down what the card SHOWED - a message that landed after the card was drawn stays unread.

The receipt was written off a fresh projection at the moment of the press, so whatever had arrived since the card
was drawn - the second mail of a thread, a reply under the one on screen - was marked read without ever being seen.
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
    store = SQLiteStore(str(tmp_path / 'shown.db'))
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    yield store
    store.cx.close()


def mail(db, n, body, at, tid):
    mid = db.add_message({'TaskId': tid, 'ExternalId': f'x:{n}', 'ConversationId': 'c:renewals', 'Channel': 'email', 'Subject': 'Vendor renewals',
                          'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': at.isoformat(sep=' '),
                          'BodyText': body, 'Status': 'open'})
    db.reconcile_processing_membership(fixed_now=STAMP)
    return mid


def card(db, mid):
    db.reconcile_processing_membership(fixed_now=STAMP)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
        funnel.invalidate()
        items = funnel.build(db, live_state=[])['items']
    return next((i for i in items if str(mid) in {str(i.get('mid')), *map(str, i.get('mids') or ())}
                 or f'message:{mid}' in (i.get('member_ids') or ())), None)


def read(db, mid):
    """Its receipt, not the card's unread: an open task with nobody on it is on the rail whatever was read."""
    return bool(db._one("SELECT 1 FROM processing_read_receipt WHERE EntityKind='message' AND LocalId=?", (str(mid),)))


@pytest.fixture
def drawn(db):
    """One mail on the task's card, drawn; then a second lands on the same task before the press."""
    tid = db.create_task({'Title': 'Vendor renewals', 'Kind': 'task', 'Status': 'open'}, 'triage')
    first = mail(db, 1, 'Three renewals land next week.', NOW - timedelta(minutes=30), tid)
    db.activate_processing_reads(fixed_now=STAMP, live_state=[])
    shown = card(db, first)
    assert shown and shown.get('unread'), 'the thread never reached the rail, so this proves nothing'
    second = mail(db, 2, 'One of them auto-renews tomorrow - can you stop it?', NOW - timedelta(minutes=1), tid)
    assert f'message:{second}' not in shown['member_ids'] and not read(db, shown['mid'])
    with db._processing_read() as cur:                    # one card, without drawing it again (that would show the second)
        assert db._processing_read_target(cur, f'msg:{second}')[0] == shown['processing_id'], 'not one card, so this proves nothing'
    return shown, second


@pytest.mark.parametrize('verb', ['done', 'surfaced'])
def test_a_mail_that_landed_after_the_card_stays_unread(db, drawn, verb):
    shown, second = drawn
    funnel.settle(db, shown['key'], verb, 'owner', read=verb == 'surfaced', shown={shown['key']: shown['view_revision']})
    assert read(db, shown['mid']), 'what the card showed was not put down'
    assert not read(db, second), 'the second mail was marked read without ever being on the card'


def test_the_page_that_sends_no_revision_puts_down_what_was_last_drawn(db, drawn):
    """The page's Done sends only the key. What the rail last drew is what it showed."""
    shown, second = drawn
    funnel.settle(db, shown['key'], 'done', 'owner')
    assert read(db, shown['mid']) and not read(db, second)


def test_a_card_that_showed_everything_puts_everything_down(db, drawn):
    shown, second = drawn
    now = card(db, second)
    funnel.settle(db, now['key'], 'done', 'owner', shown={now['key']: now['view_revision']})
    assert read(db, shown['mid']) and read(db, second)


def test_a_phone_pick_carries_the_card_it_was_pressed_off(db, drawn):
    """The phone's message is not redrawn when the page's rail is: the pick carries its own card's revision, and
    the proposal it runs reaches settle() through funnel.showing."""
    from taskuary import remote_assistant
    shown, second = drawn
    text = remote_assistant.turn_text({'say': 'Erin wrote about the renewals.', 'item': shown,
                                       'chips': [{'verb': 'done', 'label': 'Mark it handled'}, {'verb': 'next', 'label': 'Next'}]}, store=db)
    remote_assistant.remember_offered(db, 'whatsapp', 'chat', text)
    acts = remote_assistant.acts_for(db, 'whatsapp', 'chat')
    assert acts['Mark it handled']['rev'] == acts['Next']['rev'] == {shown['key']: shown['view_revision']}
    card(db, second)                                      # the page polls: the rail now holds the second mail
    with funnel.showing(acts['Mark it handled']['rev']):
        funnel.settle(db, shown['key'], 'done', 'owner')
    assert read(db, shown['mid']) and not read(db, second)


def test_a_batch_puts_down_what_each_of_its_cards_showed(db, drawn):
    shown, second = drawn
    funnel.settle(db, f"fyis:{shown['key']}", 'surfaced', 'owner', read=True, shown={shown['key']: shown['view_revision']})
    assert read(db, shown['mid']) and not read(db, second)
