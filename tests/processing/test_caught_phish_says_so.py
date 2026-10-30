"""A phishing mail triage caught is shown AS what triage made of it (B3, the email walk 2026-10-29).

Triage filed a fake "your password expires today" mail as FYI, titled it "Suspected phishing: ..." and recorded what it tries to
make the reader do (message.Danger). The rail and the FYI card still wore the mail's own subject and no warning: the row the card is
drawn from (processing_all.message_row) carried neither the verdict's title nor its danger. Both ride the card now - the subject
beside the title, and the danger for the warning line - and nothing about it gates anything.
"""
from datetime import datetime

import pytest

from taskuary import concierge, processing_startup, processing_unread
from taskuary.store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(str(tmp_path / 'phish.db'))


def rail(store):
    processing_startup.initialize(store, live_state=[])
    return processing_unread.build(store, now=datetime(2026, 10, 29, 10, 0, 0), live_state=[])['items']


def test_the_fyi_card_carries_triage_s_title_its_subject_and_the_danger(store):
    mid = store.add_message({'ExternalId': 'phish-1', 'ConversationId': 'c-phish', 'Channel': 'email', 'SourceName': 'email',
                             'FromName': 'Mailbox Security', 'FromEmail': 'security@login.invalid',
                             'Subject': 'Action required: your password expires today', 'SentAt': '2026-10-29 09:00:00',
                             'BodyText': 'Confirm your current password at the link below.', 'Direction': 'in', 'Status': 'filed',
                             'TriageTitle': 'Suspected phishing: fake password expiry notice'})
    store.set_message_danger(mid, 'Tries to get the reader to enter their password on a fake login page.')
    card = next(c for c in rail(store) if c.get('mid') == mid)
    assert card['title'] == 'Suspected phishing: fake password expiry notice'
    assert card['subject'] == 'Action required: your password expires today'
    assert card['danger'].startswith('Tries to get the reader')
    # ...and the card the canvas draws keeps both (concierge's few fields)
    shown = concierge.card_for(card)
    assert shown['danger'] == card['danger'] and shown['subject'] == card['subject']
    # ...a reading that never said whom reads as text steering the agent, as every row before 2026-10-30 did
    assert card['danger_aim'] == shown['danger_aim'] == 'agent'


def test_a_scam_on_the_owner_says_whom_it_is_aimed_at(store):
    """The owner, 2026-10-30: a phish on them read "an attempt to steer the agent" - triage's danger_aim rides to the card."""
    mid = store.add_message({'ExternalId': 'phish-2', 'ConversationId': 'c-phish-2', 'Channel': 'email', 'SourceName': 'email',
                             'FromName': 'IT Helpdesk', 'FromEmail': 'it@northwind-support.invalid', 'Subject': 'Verify your password',
                             'SentAt': '2026-10-29 09:00:00', 'BodyText': 'Sign in within 24 hours or lose access.', 'Direction': 'in',
                             'Status': 'filed'})
    store.add_route(mid, None, 'file', None, 'triage: fyi', [], 'triage',
                    verdict={'intent': 'fyi', 'danger': 'Wants Alex to sign in on a look-alike page.', 'danger_aim': 'owner'})
    card = next(c for c in rail(store) if c.get('mid') == mid)
    assert (card['danger'], card['danger_aim']) == ('Wants Alex to sign in on a look-alike page.', 'owner')
    assert concierge.card_for(card)['danger_aim'] == 'owner'
    # ...and a later clean reading clears both
    store.set_message_danger(mid, None)
    assert store.get_message(mid)['DangerAim'] is None


def test_a_plain_mail_carries_no_danger(store):
    mid = store.add_message({'ExternalId': 'plain-1', 'ConversationId': 'c-plain', 'Channel': 'email', 'SourceName': 'email',
                             'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'Subject': 'Lunch on Friday',
                             'SentAt': '2026-10-29 09:00:00', 'BodyText': 'Team lunch is at noon.', 'Direction': 'in', 'Status': 'filed'})
    card = next(c for c in rail(store) if c.get('mid') == mid)
    assert card['danger'] is None and card['danger_aim'] is None and card['title'] == 'Lunch on Friday'
