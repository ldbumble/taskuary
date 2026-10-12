"""store.feed looks each row's newest route/review, attachment count and chain size up on an index; the concierge
asks the feed for the ONE row it wants. The plan is pinned (a GROUP BY over the whole route table walked by every
output row cost 1-2 ms a row: 1.5 s for 500 rows, 14 s for the history) and so are the rows it produces."""
import os, tempfile, unittest
from datetime import datetime, timedelta
from taskuary.store import MemoryStore, SQLiteStore
from taskuary import funnel, concierge, evening


def _stamp(**ago): return (datetime.now() - timedelta(**ago)).strftime('%Y-%m-%d %H:%M:%S')


def _seed(s):
    """Several routes and reviews per message, attachments, a task chain with a context row and an older message."""
    tid = s.create_task({'Title': 'ledger export'}, 't')
    mid = lambda ext, **f: s.add_message({'ExternalId': ext, 'Channel': 'email', 'FromEmail': 'erin@northwind.example',
                                          'FromName': 'Erin Blake', 'Subject': f'about {ext}', 'BodyText': 'x', 'Status': 'filed', **f})
    m = {'multi': mid('multi', SentAt=_stamp(hours=1)), 'bare': mid('bare', SentAt=_stamp(hours=2)),
         'draft': mid('draft', SentAt=_stamp(hours=2)),          # same SentAt as `bare`: MessageId breaks the tie
         'chain1': mid('chain1', TaskId=tid, Status='routed', SentAt=_stamp(hours=3), ConversationId='c1'),
         'ctx': mid('ctx', TaskId=tid, Status='context', SentAt=_stamp(hours=4), ConversationId='c1'),
         'chain2': mid('chain2', TaskId=tid, Status='routed', SentAt=_stamp(hours=5), ConversationId='c1')}
    for d, why in (('file', 'fyi'), ('create', 'a task'), ('attach', 'the newest word')): s.add_route(m['multi'], None, d, None, why, [], 'triage')
    s.add_route(m['draft'], None, 'file', None, 'only one', [], 'triage')
    s.add_route(m['chain1'], tid, 'create', None, 'opened it', [], 'triage')
    s.add_review({'MessageId': m['multi'], 'Kind': 'reply', 'Status': 'rejected', 'DraftText': 'an old draft'})
    s.add_review({'MessageId': m['multi'], 'Kind': 'reply', 'Status': 'pending', 'DraftText': ''})
    s.add_review({'MessageId': m['draft'], 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'hello'})
    for n in ('a.png', 'b.pdf'): s.add_attachment({'MessageId': m['multi'], 'Name': n})
    s.add_attachment({'MessageId': m['chain2'], 'Name': 'c.csv'})
    return tid, m


def _oracle(s, r):
    """What each looked-up column must say, read straight off the raw tables."""
    rt = s._one('SELECT * FROM route WHERE MessageId=? ORDER BY RouteId DESC LIMIT 1', (r['MessageId'],))
    rv = s._one('SELECT * FROM review WHERE MessageId=? ORDER BY ReviewId DESC LIMIT 1', (r['MessageId'],))
    chain = (s._one("SELECT COUNT(*) n FROM message WHERE TaskId=? AND Status NOT IN ('context','history')", (r['TaskId'],))['n']
             if r['TaskId'] is not None else 0)
    return {'Decision': rt and rt['Decision'], 'RouteReason': rt and rt['Reason'], 'ReviewId': rv and rv['ReviewId'],
            'ReviewStatus': rv and rv['Status'], 'ReviewKind': rv and rv['Kind'], 'DraftError': rv and rv['DraftError'],
            'HasDraft': None if not rv else int(bool(rv['DraftText'])), 'ChainSize': chain,
            'Attachments': s._one('SELECT COUNT(*) n FROM attachment WHERE MessageId=?', (r['MessageId'],))['n']}


def _captured(s, run):
    """The SQL a call sends, with its parameters (wrapping _rows: the trace callback's text varies by Python)."""
    got, real = [], s._rows
    s._rows = lambda q, p=(): got.append((q, p)) or real(q, p)
    try: run()
    finally: s._rows = real
    return got


def _plan(s, q, p): return ' | '.join(r['detail'] for r in s._rows('EXPLAIN QUERY PLAN ' + q, p)).lower()


class FeedLooksRowsUpTests(unittest.TestCase):
    def setUp(self):
        self.s = SQLiteStore(os.path.join(tempfile.mkdtemp(), 't.db'))     # a file: the planner sees real indexes
        self.tid, self.m = _seed(self.s)
    def tearDown(self): self.s.close()

    def test_every_looked_up_column_says_what_the_raw_tables_say(self):
        rows = self.s.feed(limit=50, live_state=())
        self.assertEqual({r['MessageId'] for r in rows}, set(self.m.values()) - {self.m['ctx']})
        for r in rows: self.assertEqual({k: r[k] for k in _oracle(self.s, r)}, _oracle(self.s, r), r['MessageId'])
        by = {r['MessageId']: r for r in rows}
        multi, bare, draft = by[self.m['multi']], by[self.m['bare']], by[self.m['draft']]
        self.assertEqual((multi['Decision'], multi['ReviewStatus'], multi['HasDraft'], multi['Attachments']), ('attach', 'pending', 0, 2))
        self.assertEqual((bare['Decision'], bare['ReviewId'], bare['HasDraft'], bare['Attachments'], bare['ChainSize']), (None, None, None, 0, 0))
        self.assertEqual(draft['HasDraft'], 1)
        self.assertEqual(by[self.m['chain1']]['ChainSize'], 2)          # the context row is not the chain
        self.assertEqual([r['MessageId'] for r in rows][:3], [self.m['multi'], self.m['draft'], self.m['bare']])

    def test_no_query_walks_a_whole_table_list_per_row(self):
        for name, run in (('feed', lambda: self.s.feed(limit=50, live_state=())),
                          ('pending', lambda: self.s.feed(limit=50, pending_only=True, live_state=())),
                          ('evening', lambda: evening.gather(self.s, 24))):
            q, p = next(x for x in _captured(self.s, run) if 'FROM message m' in x[0])
            plan = _plan(self.s, q, p)
            self.assertNotIn('list subquery', plan, name)
            for t in ('route', 'review', 'attachment'):
                self.assertNotRegex(plan, rf'scan {t}\b', f'{name}: {plan}')
            self.assertIn('idx_route_message', plan, name)

    def test_a_narrowed_feed_is_the_same_row_the_whole_feed_has(self):
        whole = {r['MessageId']: r for r in self.s.feed(limit=50, live_state=())}
        for mid in self.m.values():
            got = self.s.feed(limit=1, days=3650, ids=[mid], live_state=())
            self.assertEqual(got, [whole[mid]] if mid in whole else [])
        first = next(r for r in self.s.feed(limit=50, live_state=()) if r['TaskId'] == self.tid)
        self.assertEqual(self.s.feed(limit=1, task_id=self.tid, live_state=()), [first])


class ItemForKeyTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid, self.m = _seed(self.s)

    def test_a_task_speaks_through_the_row_the_feed_puts_first(self):
        it = funnel.item_for_key(self.s, f'task:{self.tid}')
        self.assertEqual(it['mid'], self.m['chain1'])
        self.assertEqual(it['tid'], self.tid)

    def test_a_message_is_found_whatever_its_age(self):
        """It used to be fished out of the last week's 500 rows, so an older Recent row named in chat was 'not found'."""
        self.s._exec('UPDATE message SET CreatedAt=?, SentAt=? WHERE MessageId=?', (_stamp(days=40), _stamp(days=40), self.m['bare']))
        self.assertEqual(funnel.item_for_key(self.s, f"msg:{self.m['bare']}")['mid'], self.m['bare'])
        self.assertIsNone(funnel.item_for_key(self.s, f"msg:{self.m['ctx']}"))      # still not a Timeline row
        self.assertIsNone(funnel.item_for_key(self.s, 'msg:999999'))

    def test_a_task_whose_mail_is_all_old_still_has_its_row(self):
        self.s._exec('UPDATE message SET CreatedAt=? WHERE TaskId=?', (_stamp(days=40), self.tid))
        self.assertEqual(funnel.item_for_key(self.s, f'task:{self.tid}')['mid'], self.m['chain1'])

    def test_a_feed_call_asks_for_one_row(self):
        calls, real = [], self.s.feed
        self.s.feed = lambda **k: calls.append(k) or real(**k)
        funnel.item_for_key(self.s, f"msg:{self.m['multi']}"); funnel.item_for_key(self.s, f'task:{self.tid}')
        self.assertTrue(calls and all(c['limit'] == 1 for c in calls), calls)


class NewestRowsTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        same = _stamp(hours=1)
        for i in range(260):     # SentAt ties across page edges: the order must still be the feed's
            self.s.add_message({'ExternalId': f'n{i}', 'Channel': 'email', 'FromEmail': 'gail@northwind.example', 'Subject': f's{i}',
                                'Status': 'filed', 'SentAt': same if i % 3 else _stamp(minutes=i)})

    def test_pages_are_the_one_big_feed_in_the_same_order(self):
        ids = lambda rows: [r['MessageId'] for r in rows]
        for cap in (50, 100, 250, 4000):
            self.assertEqual(ids(concierge.newest_rows(self.s, 3650, cap)), ids(self.s.feed(limit=cap, days=3650, live_state=())), cap)

    def test_a_search_by_category_alone_stops_at_its_hits(self):
        calls, real = [], self.s.feed
        self.s.feed = lambda **k: calls.append(k) or real(**k)
        hits = concierge.search_timeline(self.s, {'category': 'filed'})
        self.assertEqual(len(hits), 12)
        self.assertEqual([c['limit'] for c in calls], [100])        # one page, not 4,000 rows built to keep twelve
        want = [r['MessageId'] for r in real(limit=4000, days=3650) if r['Category'] == 'filed'][:12]
        self.assertEqual([h['mid'] for h in hits], want)


if __name__ == '__main__': unittest.main()
