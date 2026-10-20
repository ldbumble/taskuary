"""The page's FYI paging (funnel.page_fyi): same rows in the same order, every count from the whole, whatever is on the table whole."""
from taskuary import funnel


def _row(n, lane='fyi', band=4, **kw):
    return {'key': f'msg:{n}', 'lane': lane, 'order_band': band, 'kind': 'email', 'title': f'Status note {n}', 'who': 'Erin Blake',
            'shows': {'who': 'Erin Blake', 'state': 'fyi'}, 'when': f'2026-10-{1 + n % 20:02d} 09:00:00', 'category': 'info',
            'status': 'new', 'channel': 'email', 'aliases': [f'processing:pi_{n}'], 'preview': 'x' * 40, **kw}


def _pile():
    work = [_row(i, lane='yours', band=2) for i in range(3)]
    fyi = [_row(i) for i in range(3, 103)]
    odd = [_row(200, settling=True), _row(201, put_down=True), _row(202, kind='idea')]
    return {'items': work + fyi[:40] + odd + fyi[40:], 'lanes': [{'lane': 'fyi', 'n': 103}], 'counts': {'unread': 106},
            'expected_next_key': 'fyis:msg:3,msg:4', 'expected_next_members': ['msg:3', 'msg:4']}


def test_paged_rows_are_the_whole_rows_in_order():
    p = _pile(); paged = funnel.page_fyi(p, 10, keep=('msg:90',))
    keys = [i['key'] for i in paged['items']]
    assert keys == [i['key'] for i in p['items'] if i['key'] in set(keys)]          # same order, nothing moved
    tail = paged['fyi_tail']; f = tail['fields']
    assert len(keys) + len(tail['rows']) == len(p['items'])
    whole = {i['key']: i for i in p['items']}
    for r in tail['rows']:
        row = whole[r[f.index('key')]]
        assert row['lane'] == tail['lane'] == 'fyi' and row['order_band'] == tail['order_band'] == 4
        assert [row.get(k) if k != 'shows_who' else row['shows']['who'] for k in f] == r
    assert [r[f.index('key')] for r in tail['rows']] == [i['key'] for i in p['items'] if i['key'] not in set(keys)]
    assert paged['lanes'] == p['lanes'] and paged['counts'] == p['counts']


def test_what_is_not_plain_fyi_and_what_is_held_stays_whole():
    keys = {i['key'] for i in funnel.page_fyi(_pile(), 5, keep=('msg:90', 'processing:pi_95', 'fyis:msg:60,msg:61'))['items']}
    assert {'msg:0', 'msg:1', 'msg:2', 'msg:200', 'msg:201', 'msg:202'} <= keys      # work, settling, put down, an idea
    assert {'msg:90', 'msg:95', 'msg:60', 'msg:61'} <= keys                            # the table (by key, alias or batch)
    assert len([k for k in keys if int(k[4:]) in range(3, 103)]) == 5 + 4


def test_a_page_bigger_than_the_tail_sends_everything():
    p = _pile(); paged = funnel.page_fyi(p, 10_000)
    assert paged['items'] == p['items'] and paged['fyi_tail']['rows'] == []
