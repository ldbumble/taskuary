"""'N ARRIVED TODAY' COUNTS ARRIVALS (trust audit F2, 2026-10-28): the rail's header counted the unread cards, so it fell 16 -> 11 -> 9 as the
owner read them. The pile carries when each recent message came in, read or not; the page counts the ones on its own today."""
from datetime import datetime, timedelta
from taskuary import processing_unread
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def test_arrivals_are_every_recent_inbound_message_read_or_not():
    s, now = MemoryStore(), datetime.now()
    f, at = Factory(s), lambda h: (now - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
    a = f.message(subject='Badge access', from_email='erin@northwind.example', sent_at=at(1))
    f.message(subject='Badge access', from_email='erin@northwind.example', sent_at=at(2), status='ignored')     # read and put away
    f.message(subject='RE: Badge access', direction='out', from_email='alex@northwind.example', sent_at=at(0.5))   # the owner's own
    f.message(subject='Old thread', from_email='ray@northwind.example', sent_at=at(60))                          # days ago
    f.message(subject='Standup', channel='teams', from_email='gail@northwind.example', sent_at=at(3))
    q = processing_unread.query_for(s)
    got = processing_unread.arrived(s, now, q)
    assert sorted(got) == sorted([at(1), at(2), at(3)])
    s._exec("UPDATE message SET Status='filed' WHERE MessageId=?", (a,))
    assert len(processing_unread.arrived(s, now, q)) == 3, 'reading or filing a message never takes it out of what arrived'
    assert processing_unread.arrived(s, now, {**q, 'channel': ['teams']}) == [at(3)], 'a filtered rail counts only what it shows'


def test_a_report_run_that_found_nothing_is_not_an_arrival():
    """A scheduled check that came back with nothing (0 rows), held off the Timeline by its own line, landed as a row put down at once -
    and still counted one more in "arrived today", on a day nothing came in. A run that found something still counts."""
    import json
    from unittest import mock
    from taskuary import reports
    s, now = MemoryStore(), datetime.now()
    sid = s.save_source({'Channel': 'report', 'Address': 'Overdue invoices', 'Active': 1, 'ConfigJson': json.dumps(
        {'title': 'Overdue invoices', 'route': {'timeline': {'how': 'rule', 'rule': 'something_came_back'}}})}, 't')
    run = lambda head, rows: mock.patch.object(reports, 'render_report', return_value=(head, rows))
    with run('0 rows', ''): reports.run_report_source(s, s.get_source(sid), None)
    q = processing_unread.query_for(s)
    assert processing_unread.arrived(s, now, q) == [], 'nothing found is nothing arrived'
    with run('2 rows', '{"invoice": "INV-1001"}\n{"invoice": "INV-1002"}'): reports.run_report_source(s, s.get_source(sid), None)
    assert len(processing_unread.arrived(s, now, q)) == 1, 'a run with something in it reached the Timeline and is an arrival'
