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
