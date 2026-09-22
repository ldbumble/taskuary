"""A row's preview is what the sender wrote, not the wrapper IT arrived in.

Every mail from outside Northwind opens with a security banner, so the Timeline's Message step read "This
email was sent from outside of Northwind. ** Do not click links or download attachments..." on every one
of them and never got as far as the message. The owner was looking at a CI failure whose summary
said nothing about CI (2026-09-15).

triage.strip_boilerplate is already the app's one answer to this - the assistant uses it for exactly
this - so the preview uses it too rather than inventing a second rule. Classification is deliberately
NOT affected: category_of re-reads the raw body, because "unsubscribe" in a footer is how a promo is
recognised.
"""
from datetime import datetime

import pytest

from taskuary import processing_all
from taskuary.store import SQLiteStore

NOW = datetime.now().replace(microsecond=0)
STAMP = NOW.isoformat(sep=' ')
BANNER = ('This email was sent from outside of Northwind. ** Do not click links or download attachments '
          'unless you know the content is safe. If you are not sure whether this email is safe, '
          'contact the Northwind Helpdesk at 866-Northwind-DESK.**')


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'preview.db'))
    yield store
    store.cx.close()


def a_message(db, subject, body, sender='notifications@github.com'):
    mid = db.add_message({'ExternalId': f'x:{subject}', 'ConversationId': f'c:{subject}',
                          'Channel': 'email', 'Subject': subject, 'FromName': 'Alex',
                          'FromEmail': sender, 'SentAt': STAMP, 'BodyText': body, 'Status': 'routed'})
    db.reconcile_processing_membership(fixed_now=STAMP)
    return mid


def row_for(db, mid):
    snap = db.processing_inventory_snapshot(fixed_now=NOW.isoformat(), live_state=[],
                                            display_only=True, history_days=14)
    out, _c, _n = processing_all.compact_inventory(
        snap, processing_all.normalize_query(None, None, 14), include_excluded=True, degraded_ok=True)
    return next(r['row'] for r in out if r['row'].get('MessageId') == mid)


def test_the_external_banner_is_not_the_message(db):
    mid = a_message(db, '[ldbumble/taskuary] Run failed: ci - master (7d7424a)',
                    BANNER + '\r\n\r\n\r\n\r\n[ldbumble/taskuary] ci workflow failed on master.')
    preview = row_for(db, mid)['Preview']
    assert 'sent from outside of Northwind' not in preview, 'the wrapper is not the message'
    assert preview.lstrip().startswith('[ldbumble/taskuary] ci workflow failed')


def test_a_message_that_is_only_a_banner_still_says_something(db):
    """Stripping must never leave a row with nothing to show."""
    mid = a_message(db, 'Nothing but the wrapper', BANNER)
    assert row_for(db, mid)['Preview'].strip(), 'a row with an empty preview says less than the banner did'


def test_an_ordinary_body_is_untouched(db):
    body = 'Can you approve the Heflin refund before Friday?\n\nThanks,\nMaya'
    mid = a_message(db, 'Refund', body, sender='maya@example.test')
    assert row_for(db, mid)['Preview'].startswith('Can you approve the Heflin refund')


def test_stripping_for_display_does_not_reclassify_the_sender(db):
    """"unsubscribe" in a footer is how a promo is recognised, and the banner is a signal of its own.
    Stripping them for DISPLAY must leave the verdict exactly where it was - category_of re-reads the
    raw body for that reason, and this is the guard that it still does."""
    body = 'Two new ways to browse.\n\nUnsubscribe | Manage preferences'
    plain = a_message(db, 'Plain', body, sender='team@vendor.example')
    wrapped = a_message(db, 'Wrapped', BANNER + '\r\n\r\n' + body, sender='team@vendor.example')
    assert row_for(db, wrapped)['Category'] == row_for(db, plain)['Category']
