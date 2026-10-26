"""TWO ROWS FILED IN THE SAME SECOND HAVE ONE ORDER, EVERYWHERE (2026-10-25): a nightly run filed two dashboards in one second, and the rail
broke the tie by the row's key - `processing:pi_<hex>`, a hash - while the page put a row back by its arrival alone, after every row of
that second. The two swapped and were drawn over each other as the rail moved (the dead-end walk's SWAP); the demo hid it by filing one a
minute later. The tie goes to ids that never change - the task number, then the first message - on the server (funnel.place_id) and on the
page (funnelPile.placeId) alike, and Next walks that order down - website/test/railTie.test.mjs holds the page to the same rows, and
browser/rail-tie.test.mjs the two together. Invented people only."""
from datetime import datetime, timedelta
from unittest import mock

import pytest

from taskuary import concierge, funnel, lanes
from taskuary.store import SQLiteStore

STAMP = (datetime.now() - timedelta(hours=2)).replace(microsecond=0).strftime('%Y-%m-%d %H:%M:%S')
TITLES = ('Headcount by site, nightly', 'AP ageing over 30 days', 'Open invoices by vendor', 'Mileage claims this week')


def file(store, title, at=STAMP, channel='report', cat=None):
    return store.add_message({'ExternalId': f'x:{title}', 'ConversationId': f'c:{title}', 'Channel': channel, 'Subject': title,
                              'FromName': 'Gail Moreno', 'FromEmail': 'gail@northwind.example', 'SentAt': at, 'BodyText': '5 rows.',
                              'Status': 'routed', **({'Category': cat} if cat else {})})


def settle(store):
    at = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    store.reconcile_processing_membership(fixed_now=at); store.activate_processing_reads(fixed_now=at, live_state=[]); funnel.invalidate()


@pytest.fixture
def db(tmp_path):
    path = str(tmp_path / 'tie.db')
    store = SQLiteStore(path)
    store.set_setting('funnel_hours', '72', 'fixture')
    funnel.invalidate(); funnel.forget_states()
    mids = [file(store, t) for t in TITLES]                     # four reports, one second
    file(store, 'Office closed Friday', (datetime.now() - timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M:%S'), 'email', 'info')
    settle(store)
    with mock.patch('taskuary.terminal.live_sessions', return_value=[]): yield store, mids, path
    store.cx.close()


def reports(store):
    funnel.invalidate()
    return [i for i in funnel.build(store, live_state=[])['items'] if (i.get('unread') or i.get('deferred')) and lanes.level_of(i) == 'reports']


def first_mid(i): return min(int(m.split(':')[1]) for m in i['member_ids'] if m.startswith('message:'))


def test_a_same_second_tie_goes_to_the_first_filed_not_the_key(db):
    store, mids, _ = db
    rows = reports(store)
    assert len({funnel.arrived(i) for i in rows}) == 1, 'the fixture did not file them in one second'
    assert [first_mid(i) for i in rows] == mids, f"the tie followed the key, not the first filed: {[i['title'] for i in rows]}"


def test_the_order_holds_across_rebuilds_and_a_reopened_store(db):
    store, _, path = db
    once = [i['key'] for i in reports(store)]
    assert [i['key'] for i in reports(store)] == once
    again = SQLiteStore(path)
    try:
        funnel.invalidate()
        assert [i['key'] for i in funnel.build(again, live_state=[])['items'] if i['key'] in once] == once, 'a reload reordered the tie'
    finally: again.cx.close()


def test_next_walks_the_tie_down_and_never_back_up(db):
    store, mids, _ = db
    rows = reports(store)
    out, seen = concierge.surface(store, rows[0]['key']), [rows[0]['key']]
    while out['item'] and lanes.level_of(out['item']) == 'reports':
        out = concierge.surface(store, leaving=out['item']['key'])
        if out['item'] and lanes.level_of(out['item']) == 'reports': seen.append(out['item']['key'])
    assert seen == [i['key'] for i in rows], f'Next did not walk the tie in order: {seen}'


def test_next_from_the_lower_of_a_tie_goes_on_down_not_up_to_its_twin(db):
    store, _, _ = db
    rows = reports(store)
    concierge.surface(store, rows[-1]['key'])                  # the last of the four clicked; the three above it unseen
    out = concierge.surface(store, leaving=rows[-1]['key'])     # Next reads it, so it leaves the rail: the walk goes on from its place
    assert out['item'] is None or out['item']['key'] not in [i['key'] for i in rows[:-1]], \
        f"Next went back up the tie to {out['item'] and out['item'].get('title')}"



def test_rows_with_no_task_and_no_message_tie_by_their_first_member():
    """The release walk's sweep (2026-10-25): two rows of one second with neither a task nor a message (an idea, a review on its own) were
    still settled by the hash. Their first member decides - kind, then the number as a number (idea:10 after idea:9), as the page does."""
    rows = [{'key': f'processing:pi_{h}', 'lane': 'fyi', 'kind': 'idea', 'member_ids': [f'review:{n + 40}', f'idea:{n}'], 'arrived_at': STAMP}
            for n, h in ((10, '00'), (9, 'ff'))]
    assert [r['member_ids'][1] for r in sorted(rows, key=funnel.order_key)] == ['idea:9', 'idea:10']
    assert funnel.first_member(rows[1]) == 'idea:000000000009'
    assert funnel.place_id({'key': 'k', 'tid': 4, 'member_ids': ['idea:1']})[4] == ''
