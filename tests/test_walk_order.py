"""What the walk puts in front of the owner first, and what it must never bury.

Two things the owner reported on 2026-09-10, looking at a pipe of 1 pending reply and 49 unread fyi:

  "coding task is not surfacing at all. it's stuck on the work timeline?"
      TQ-0459 had a reply drafted and waiting. It was shown once, and after that the walk preferred
      ANY unread row over it - "new arrivals still lead" applied to every lane - so the one item
      actually on them never came up again until fifty fyi had been drained.

  "just surface the morning digest report to the top of the work and then we are good"
      Today's brief is what you read before anything else; it was filed as a landed result (band 3),
      behind every piece of work and sorted oldest-first among a dozen other report runs.
"""
import json, unittest
from datetime import datetime, timedelta

from taskuary import funnel
from taskuary.store import MemoryStore


def ago(hours=0): return (datetime.now() - timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')


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


class TodaysBriefLeadsTests(unittest.TestCase):
    def test_todays_digest_is_work_and_leads_the_pipe(self):
        s = store()
        report_source(s)
        report_run(s, hours=2)
        drafted(s, hours=20)
        items = funnel.build(s)['items']
        self.assertTrue(funnel.todays_brief(items[0]), f"the brief did not lead: {items[0]['title']}")
        self.assertEqual(items[0]['order_band'], 2)               # work, not a landed result
        self.assertIn('your brief for today', items[0]['why'])

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
