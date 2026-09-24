"""A chat Taskuary READS is not a chat Taskuary writes to.

Report #140 "Assistant for Backend Monitoring" was posting its alert into the WhatsApp group it
takes its messages from. Nobody chose that: `send_targets` offered every input source as a
destination ("a chat you already take messages from"), sorted the list by most recent activity - so
a busy input group is always first and the owner's own chat, which has no timestamp, is always last
- and flipping on "AND ALSO TELL ME ON" called firstDest(), which took the first one.

It sat harmless for months because the alert block was DEAD for Assistant-sourced reports; when
06447455 made it fire, the first thing it did was post into the group (the owner, 2026-09-17: "it
should never send to input channels ... default should be the assistant channel").

The loop that looks like it follows - our own message read back in as a question - never happened:
the bridge stamps Taskuary's own sends and poll_whatsapp discards them before either interceptor.
"""
import json

import pytest

from taskuary import outbound, reports
from taskuary.store import MemoryStore


@pytest.fixture
def store():
    s = MemoryStore()
    s.save_connector({'Type': 'whatsapp', 'Name': 'WhatsApp', 'Active': 1,
                      'ConfigJson': json.dumps({'assistant_chat': '15551234567@s.whatsapp.net'})}, 'test')
    s.save_source({'Channel': 'whatsapp', 'Address': '120363000000000001@g.us', 'Active': 1,
                   'Owner': 'test', 'ConfigJson': '{}'}, 'test')
    return s


def test_a_source_chat_is_an_inbox(store):
    assert outbound.input_chats(store)['whatsapp'] == {'120363000000000001@g.us'}


def test_an_email_source_is_not_an_inbox_in_this_sense(store):
    """Mailing yourself is an ordinary thing a report does - "Automation ideas" does it today."""
    store.save_source({'Channel': 'email', 'Address': 'owner@example.com', 'Active': 1,
                       'Owner': 'test', 'ConfigJson': '{}'}, 'test')
    assert 'email' not in outbound.input_chats(store)


def test_the_group_it_reads_is_refused_as_a_destination(store):
    why = outbound.refuse_input_chat(store, 'whatsapp', '120363000000000001@g.us')
    assert 'inbox, not a destination' in why


def test_the_owners_own_chat_is_not_refused(store):
    assert outbound.refuse_input_chat(store, 'whatsapp', '15551234567@s.whatsapp.net') == ''


def test_an_alert_addressed_at_an_inbox_does_not_send_and_says_why(store):
    """At the DOOR, not only in the picker: #140 already holds the old address."""
    cfg = {'title': 'Assistant for Backend Monitoring',
           'alert': {'channel': 'whatsapp', 'to': '120363000000000001@g.us'}}
    src = {'SourceId': 140, 'Address': 'Assistant for Backend Monitoring'}
    with pytest.raises(RuntimeError, match='it is an inbox, not a destination'):
        reports.send_alert(store, src, cfg, '1 came back', 'head', 'body')


def test_nothing_was_filed_for_the_refused_alert(store):
    """A send that never happened must not leave a receipt saying it did."""
    cfg = {'title': 'x', 'alert': {'channel': 'whatsapp', 'to': '120363000000000001@g.us'}}
    before = len(store.scan_messages())
    with pytest.raises(RuntimeError):
        reports.send_alert(store, {'SourceId': 140, 'Address': 'x'}, cfg, 'why', 'head', 'body')
    assert len(store.scan_messages()) == before


# ── ...and what it says when it does send ───────────────────────────────────────────────
# "Assistant for Backend Monitoring: 1 came back." then "Assistant for Backend Monitoring -
# 1 line(s)" then the finding: the name twice and a plural nobody writes, on a phone screen.
def sent_text(store, cfg, why, head, body):
    from unittest import mock
    with mock.patch('taskuary.outbound.send_out', return_value={'ok': True}):
        reports.send_alert(store, {'SourceId': 140, 'Address': 'x'}, cfg, why, head, body)
    return store.scan_messages()[0]['BodyText']


def alerting(store):
    return {'title': 'Assistant for Backend Monitoring',
            'alert': {'channel': 'whatsapp', 'to': '15551234567@s.whatsapp.net'}}


def test_the_report_names_itself_once(store):
    text = sent_text(store, alerting(store), '1 came back',
                     'Assistant for Backend Monitoring - 1 line(s)', 'the ledger job has not run')
    assert text.count('Assistant for Backend Monitoring') == 1
    assert 'line(s)' not in text
    assert text.startswith('Assistant for Backend Monitoring: 1 came back.')
    assert text.endswith('the ledger job has not run')


def test_a_headline_that_says_something_new_is_kept(store):
    """Only the ECHO goes. A row report's "12 rows" is news and stays."""
    text = sent_text(store, alerting(store), 'more than expected', '12 rows (capped at 200)', 'a\nb')
    assert '12 rows (capped at 200)' in text


def test_a_note_you_wrote_still_rides_along(store):
    cfg = alerting(store)
    cfg['alert']['note'] = 'check the VPN first'
    assert 'check the VPN first' in sent_text(store, cfg, 'x', 'Assistant for Backend Monitoring - 1 line(s)', 'y')


# ── ...and a refused alert is not SILENT ────────────────────────────────────────────────
# Refused at the door, it was a log line and nothing else: the owner went a week "not getting those
# messages" (2026-09-24). It files a broken row on the work rail instead - once a day per report.
def test_a_refused_alert_lands_on_the_work_rail_once_a_day():
    from taskuary import funnel
    s = MemoryStore()
    s.save_source({'Channel': 'whatsapp', 'Address': 'ops-room@g.test', 'Active': 1, 'Owner': 'test', 'ConfigJson': '{}'}, 'test')
    cfg = {'title': 'Nightly checks', 'alert': {'channel': 'whatsapp', 'to': 'ops-room@g.test'}}
    src = {'SourceId': 7, 'Address': 'Nightly checks'}
    err = reports.alert_or_file(s, src, cfg, '1 came back', 'head', 'the ledger job has not run')
    assert 'inbox, not a destination' in err
    rows = [m for m in s.scan_messages() if 'alert NOT SENT' in (m['Subject'] or '')]
    assert len(rows) == 1 and rows[0]['ConversationId'] == 'report:7'
    assert funnel.report_failed(s, rows[0]['Subject'])                 # the broken lane: work, not an fyi
    assert 'ops-room@g.test' in rows[0]['BodyText']
    reports.alert_or_file(s, src, cfg, '1 came back', 'head', 'again, an hour later')
    assert len([m for m in s.scan_messages() if 'alert NOT SENT' in (m['Subject'] or '')]) == 1


def test_an_alert_that_went_files_nothing_extra():
    from unittest import mock
    s = MemoryStore()
    cfg = {'title': 'Nightly checks', 'alert': {'channel': 'whatsapp', 'to': 'me@s.test'}}
    with mock.patch('taskuary.outbound.send_out', return_value={'ok': True}):
        assert reports.alert_or_file(s, {'SourceId': 7, 'Address': 'x'}, cfg, 'why', 'head', 'body') is None
    assert not [m for m in s.scan_messages() if 'alert NOT SENT' in (m['Subject'] or '')]
