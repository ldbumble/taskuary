"""A report's alert files the message it just sent. That is a receipt, not an ask.

reports.send_alert writes the outbound line so you can see that it went - Taskuary writing to YOU,
on WhatsApp or Telegram. It came out on the table wearing a sender's face: "Ignore this sender",
"Block them in Settings", offered on Taskuary's own outbound message, where blocking the sender
would mean blocking yourself (the owner, 2026-09-17).

The funnel has always known this - _feed_skip drops `Direction == 'out'` - but the canonical road
asks from_feed to RENDER a row whose membership was decided upstream, so `canonical=True` walks
straight past it. The rule belongs where Unread is decided.
"""
from datetime import datetime

import pytest

from taskuary import processing_startup, processing_unread
from taskuary.store import SQLiteStore


@pytest.fixture
def store(tmp_path):
    return SQLiteStore(str(tmp_path / 'receipt.db'))


def alert_receipt(store, channel, stamp='2026-09-17 09:28:28'):
    """Exactly what reports.send_alert writes."""
    return store.add_message({
        'ExternalId': f'alert:140:{stamp}:{channel}', 'ConversationId': 'report:140',
        'Channel': channel, 'SourceName': 'Assistant for Backend Monitoring', 'FromName': 'Taskuary',
        'Subject': 'Assistant for Backend Monitoring — 1 came back', 'SentAt': stamp,
        'BodyText': 'Assistant for Backend Monitoring: 1 came back.', 'Direction': 'out', 'Status': 'sent'})


def rail(store):
    processing_startup.initialize(store, live_state=[])
    out = processing_unread.build(store, now=datetime(2026, 9, 17, 10, 0, 0), live_state=[])
    return out['items']


def subjects(cards):
    return ' | '.join(str(c.get('title') or '') for c in cards)


@pytest.mark.parametrize('channel', ['whatsapp', 'telegram'])
def test_the_alert_we_sent_does_not_come_back_as_work(store, channel):
    alert_receipt(store, channel)
    assert not [c for c in rail(store) if 'Backend Monitoring' in str(c.get('title') or '')], \
        f'our own {channel} send is on the table: {subjects(rail(store))}'


@pytest.mark.parametrize('channel', ['whatsapp', 'telegram'])
def test_a_real_arrival_on_the_same_channel_still_lands(store, channel):
    """The rule is DIRECTION, not the channel - muting the channel would be the wrong fix."""
    store.add_message({'ExternalId': f'{channel}:real-1', 'ConversationId': f'{channel}:15551234567',
                       'Channel': channel, 'SourceName': 'Marcus', 'FromName': 'Marcus',
                       'Subject': 'the export is broken', 'SentAt': '2026-09-17 09:30:00',
                       'BodyText': 'the export is broken', 'Direction': 'in', 'Status': 'routed'})
    assert [c for c in rail(store) if 'export is broken' in str(c.get('title') or '')], \
        'an inbound message must still reach the table'


def test_both_at_once_leaves_only_the_arrival(store):
    alert_receipt(store, 'whatsapp')
    alert_receipt(store, 'telegram', '2026-09-17 09:29:00')
    store.add_message({'ExternalId': 'whatsapp:real-2', 'ConversationId': 'whatsapp:15551234567',
                       'Channel': 'whatsapp', 'SourceName': 'Marcus', 'FromName': 'Marcus',
                       'Subject': 'can you look at this', 'SentAt': '2026-09-17 09:31:00',
                       'BodyText': 'can you look at this', 'Direction': 'in', 'Status': 'routed'})
    titles = subjects(rail(store))
    assert 'can you look at this' in titles
    assert 'Backend Monitoring' not in titles
