"""What the walk puts in front of the owner first, and what it must never bury.

Two things the owner reported on 2026-09-10, looking at a pipe of 1 pending reply and 49 unread fyi:

  "coding task is not surfacing at all. it's stuck on the work timeline?"
      TQ-0459 had a reply drafted and waiting. It was shown once, and after that the walk preferred
      ANY unread row over it - "new arrivals still lead" applied to every lane - so the one item
      actually on them never came up again until fifty fyi had been drained.

  "just surface the morning digest report to the top of the work and then we are good"
      Today's brief is what you read before anything else; it was filed as a landed result (band 3),
      behind every piece of work and sorted oldest-first among a dozen other report runs.
      Since 2026-09-23 the walk opens with who wants what, and the brief is a report again - still
      first among the reports ("morning digest is in your tasks. Let's at least put it in the reports").
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import funnel
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


def today_ago(hours, span=3.0, now=None):
    """`hours` ago, but never back past this morning's midnight.

    A brief is today's by CALENDAR DATE (funnel: `ran.date() == datetime.now().date()`), so a run
    stamped "2 hours ago" belongs to YESTERDAY whenever the suite starts before 02:00. CI runs on
    whatever hour a push lands, and went red on all six platforms at 00:52 UTC (2026-09-15) while
    the same commit passed for everyone who ran it by day.

    Early in the day the offsets are squeezed into the part of today that has actually happened,
    which keeps several runs in the ORDER a test needs while leaving them on the day it means. At
    any ordinary hour nothing is scaled and the stamp is exactly `hours` old."""
    now = now or datetime.now()
    elapsed = (now - now.replace(hour=0, minute=0, second=0, microsecond=0)).total_seconds() / 3600
    if elapsed > span + 0.5: return hours
    return hours * (max(elapsed - 0.1, 0.05) / span)


def store():
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', '{}')
    for k in ('calendar_enabled', 'coder_auto_enabled', 'learn_enabled', 'auto_draft_enabled'): s.set_setting(k, '0', 't')
    funnel.invalidate(); funnel.forget_states(); funnel._CACHE.update(cands_at=0.0, cands=[])
    funnel._SOURCES.update(at=0.0, by={}, digest=set())        # the source cache is a module global
    return s


def drafted(s, subject='Export still broken', who='Dana', hours=20):
    """A reply drafted and waiting on the owner - lane 'approve', the thing that is ON them."""
    t = s.create_task({'Title': subject, 'Kind': 'coding', 'Status': 'waiting'}, 'o')
    m = s.add_message({'TaskId': t, 'ExternalId': f'x:{subject}', 'ConversationId': f'c:{subject}', 'Channel': 'email',
                       'Subject': subject, 'FromName': who, 'FromEmail': 'dana@vendor.com', 'SentAt': ago(hours),
                       'BodyText': 'Can you send the corrected file?', 'Status': 'routed'})
    return t, m, s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Attached.', 'Status': 'pending'})


def shown_a_while_ago(s, key, hours=2):
    """Shown, and the 30-minute cooldown long spent - the state the item is in when the owner reads
    it, gets on with their day, and comes back to the walk."""
    s.set_funnel_state(key, 'surfaced', 'owner')
    s._exec('UPDATE funnel_state SET At=? WHERE Key=?', (ago(hours), key))
    funnel.invalidate(); funnel.forget_states()


def fyi(s, subject, hours=3):
    return s.add_message({'ExternalId': f'f:{subject}', 'ConversationId': f'fc:{subject}', 'Channel': 'email',
                          'Subject': subject, 'FromName': 'A List', 'FromEmail': 'list@vendor.com',
                          'SentAt': ago(hours), 'BodyText': 'for your information', 'Status': 'filed',
                          'Category': 'info'})


def report_source(s, title='Morning digest', kind='digest'):
    return s.save_source({'Channel': 'report', 'Address': title, 'Active': 1,
                          'ConfigJson': json.dumps({'title': title, 'type': kind})}, 'o')


def report_run(s, title='Morning digest', hours=2, body='THE WINDOW IN NUMBERS: 1 review waiting'):
    return s.add_message({'ExternalId': f'r:{title}:{hours}', 'Channel': 'report', 'Subject': title,
                          'SourceName': title, 'FromName': title, 'FromEmail': 'reports@taskuary',
                          'SentAt': ago(hours), 'BodyText': body, 'Status': 'filed', 'Category': 'report'})


class OnYouIsNeverBuriedTests(unittest.TestCase):
    def test_a_shown_reply_still_leads_a_pipe_full_of_unread_fyi(self):
        _t, _m, r = drafted(s := store(), hours=6)
        for n in range(6): fyi(s, f'newsletter {n}')
        first = funnel.next_item(s)
        self.assertEqual(first['key'], f'review:{r}')             # it leads: it is the thing on them
        # ...and after being shown it STILL leads. Before this change the walk preferred any unread
        # fyi from here on, so the one item on the owner never came back.
        shown_a_while_ago(s, f'review:{r}')
        again = funnel.next_item(s)
        self.assertIsNotNone(again, 'the walk went silent with a reply still waiting')
        self.assertEqual(again['key'], f'review:{r}', 'the pending reply was buried under the unread fyi')

    def test_on_you_names_the_two_lanes_that_wait_on_the_owner(self):
        self.assertTrue(funnel.on_you({'lane': 'approve'}))       # a reply wants your yes
        self.assertTrue(funnel.on_you({'lane': 'blocked'}))       # an agent stopped and asked
        self.assertFalse(funnel.on_you({'lane': 'fyi'}))
        self.assertFalse(funnel.on_you({'lane': 'report'}))
        self.assertFalse(funnel.on_you({'lane': 'working'}))


class FyiBatchCostTests(unittest.TestCase):
    """An fyi Next used to build the pile twice - once to choose the row, once to find its siblings.
    About 450ms of pure Python each on the owner's store, and CPU is what the server is short of."""

    def test_the_batch_never_forces_a_second_pile(self):
        s = store()
        report_source(s)                       # anything; the batch only reads fyi rows
        for n in range(6): fyi(s, f'newsletter {n}')
        first = next(i for i in funnel.build(s)['items'] if i['lane'] == 'fyi')
        seen = []
        real = funnel.pile
        with mock.patch.object(funnel, 'pile', side_effect=lambda st, force=False, **k: (seen.append(force), real(st, force=force, **k))[1]):
            batch = funnel.fyi_batch(s, first)
        self.assertTrue(batch, 'the batch still comes back')
        self.assertNotIn(True, seen, 'fyi_batch forced a rebuild the caller had already paid for')

    def test_a_caller_holding_the_pile_can_hand_it_over(self):
        s = store()
        for n in range(6): fyi(s, f'newsletter {n}')
        items = funnel.build(s)['items']
        first = next(i for i in items if i['lane'] == 'fyi')
        with mock.patch.object(funnel, 'pile', side_effect=AssertionError('the pile was rebuilt')):
            batch = funnel.fyi_batch(s, first, items=items)
        self.assertEqual(batch[0]['key'], first['key'])
        self.assertTrue(all(i['lane'] == 'fyi' for i in batch))

    def test_the_batch_is_as_big_as_the_setting_says(self):
        s = store()
        s.set_setting('fyi_batch', '2', 'owner')
        for n in range(6): fyi(s, f'newsletter {n}')
        items = funnel.build(s)['items']
        first = next(i for i in items if i['lane'] == 'fyi')
        self.assertEqual(len(funnel.fyi_batch(s, first, items=items)), 2)


class TodaysBriefLeadsTests(unittest.TestCase):
    def test_a_brief_stamp_lands_on_today_at_every_hour_of_the_clock(self):
        """The guard on the guard: whatever hour CI starts, a run these tests call "today's" has
        to BE today's, and two of them have to keep their order."""
        for hour, minute in ((0, 3), (0, 52), (1, 30), (2, 45), (4, 0), (12, 0), (23, 59)):
            now = datetime.now().replace(hour=hour, minute=minute, second=0, microsecond=0)
            early, late = today_ago(3, now=now), today_ago(1, now=now)
            with self.subTest(at=f'{hour:02d}:{minute:02d}'):
                self.assertEqual((now - timedelta(hours=early)).date(), now.date(), 'the earlier run left today')
                self.assertEqual((now - timedelta(hours=late)).date(), now.date(), 'the later run left today')
                self.assertGreater(early, late, 'the 07:20 brief must still be older than the 08:00 one')

    def test_todays_digest_is_a_report_and_leads_the_reports(self):
        s = store()
        report_source(s)
        report_source(s, title='Headcount', kind='metric')
        report_run(s, title='Headcount', hours=today_ago(3), body='5 rows')
        report_run(s, hours=today_ago(2))
        drafted(s, hours=20)
        items = funnel.build(s)['items']
        self.assertFalse(funnel.todays_brief(items[0]), 'the work comes first, not the brief')
        reports = [i for i in items if i['kind'] == 'report']
        self.assertTrue(funnel.todays_brief(reports[0]), f"the brief did not lead the reports: {reports[0]['title']}")
        self.assertEqual(reports[0]['order_band'], 3)             # a report, not work
        self.assertIn('your brief for today', reports[0]['why'])

    def test_yesterdays_digest_is_an_ordinary_landed_report(self):
        """A stale brief at the top of the day is worse than no brief at all."""
        s = store()
        s.set_setting('funnel_hours', '72', 't')       # so yesterday's run is still in the pipe at all
        report_source(s)
        report_run(s, hours=30)
        items = funnel.build(s)['items']
        brief = next(i for i in items if i['kind'] == 'report')
        self.assertFalse(funnel.todays_brief(brief))
        self.assertEqual(brief['order_band'], 3)

    def test_only_the_latest_brief_of_the_day_leads_and_the_earlier_one_lands(self):
        """Two identical rows led the work rail (the owner, 2026-09-14: "we should only have the
        latest one"). The schedule no longer makes a pair - a launch defers to the slot since
        TQ-0589 - but "Run now" on the Reports tab bypasses is_due, so a second brief still can."""
        s = store()
        report_source(s)
        report_run(s, hours=today_ago(3), body='THE WINDOW IN NUMBERS: the 07:20 one')
        report_run(s, hours=today_ago(1), body='THE WINDOW IN NUMBERS: the 08:00 one')
        items = funnel.build(s)['items']
        briefs = [i for i in items if i['kind'] == 'report']
        self.assertEqual(len(briefs), 2, 'both runs are still on the timeline')
        self.assertEqual([funnel.todays_brief(i) for i in briefs], [True, False], 'one brief leads, the other lands')
        self.assertTrue(funnel.todays_brief(briefs[0]))
        self.assertIn('the 08:00 one', briefs[0]['preview'] or briefs[0].get('why') or '')
        self.assertEqual([i['order_band'] for i in briefs], [3, 3])
        self.assertIn('a later brief has replaced this one', briefs[1]['why'])

    def test_an_ordinary_report_run_today_is_not_the_brief(self):
        s = store()
        report_source(s, title='Process Error Check', kind='sql')
        report_run(s, title='Process Error Check', hours=2)
        items = funnel.build(s)['items']
        check = next(i for i in items if i['kind'] == 'report')
        self.assertFalse(funnel.todays_brief(check))
        self.assertEqual(check['order_band'], 3)

    def test_the_brief_is_recognised_by_its_configuration_not_its_name(self):
        """The owner may rename the report; a report merely CALLED digest is not the brief."""
        s = store()
        sid = report_source(s, title='My morning wrap', kind='digest')
        other = report_source(s, title='Digest of vendor invoices', kind='sql')
        self.assertTrue(funnel.is_digest_source(s, sid))
        self.assertFalse(funnel.is_digest_source(s, other))


if __name__ == '__main__':
    unittest.main()


if __name__ == '__main__':
    unittest.main()


class BatchWakesTabsOnceTests(unittest.TestCase):
    """Every settle empties the pile cache and wakes every open tab, which answers with a rebuild.
    A handful of fyi settled together did that once per member, so several rebuilds of the whole
    pile raced each other in front of the Next behind them (the owner, 2026-09-14: "when i hit
    'all read, next' on fyi it takes 2/3 seconds")."""

    def _watch(self):
        """What actually reaches the tabs: live.emit, below _poke and below the hold."""
        from taskuary import live
        seen = []
        return mock.patch.object(live, 'emit', lambda kind, **p: seen.append(kind)), seen

    def _keys(self, s, n=4):
        for i in range(n + 2): fyi(s, f'newsletter {i}')
        return [i['key'] for i in funnel.build(s)['items'] if i['lane'] == 'fyi'][:n]

    def test_a_batch_wakes_the_tabs_once_not_once_per_member(self):
        s = store()
        keys = self._keys(s)
        woke = self._watch()
        with woke[0]:
            funnel.settle(s, 'fyis:' + ','.join(keys), 'done', 'owner')
        self.assertEqual(woke[1].count('feed-changed'), 1,
                         f'{woke[1].count("feed-changed")} wake-ups for one batch of {len(keys)}')

    def test_the_members_are_all_still_settled(self):
        """Coalescing the shouting must not coalesce the writing."""
        s = store()
        keys = self._keys(s)
        funnel.settle(s, 'fyis:' + ','.join(keys), 'done', 'owner')
        states = s.funnel_states()
        for k in keys:
            self.assertEqual((states.get(k) or {}).get('Status'), 'done', k)

    def test_a_single_item_still_wakes_them(self):
        s = store()
        key = self._keys(s, 1)[0]
        woke = self._watch()
        with woke[0]:
            funnel.settle(s, key, 'done', 'owner')
        self.assertIn('feed-changed', woke[1], 'one item must still wake the tabs')

    def test_the_wake_up_survives_a_failure_half_way_through(self):
        """A caller that raised part way has still changed what the tabs are looking at."""
        s = store()
        woke = self._watch()
        with woke[0]:
            with self.assertRaises(RuntimeError):
                with s.one_poke():
                    s._poke('feed-changed')
                    raise RuntimeError('half way')
        self.assertEqual(woke[1].count('feed-changed'), 1)
