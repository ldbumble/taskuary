"""A message that arrives moments before a poll must not be lost for good.

The reported case, reconstructed from the log and Graph itself. A Teams message from Richard
Spencer was created at 19:29:11Z. A poll ran at 15:29:19 local - eight seconds later - and
asked getAllMessages/delta for everything newer than its own last watermark. Graph's delta is
eventually consistent and had not surfaced an eight-second-old message yet, so the poll saw
nothing and moved the watermark to 15:29:19 regardless. Every poll after that asked for
"newer than 15:29:19", and the message sat permanently on the wrong side of the line: Sync
now could not find it, because syncing is what buried it.

Every channel here shares that shape - a watermark that jumps to now - so the window reaches
back past it. Dedupe makes the re-read free: ingest_message checks external_id in its first
line, before policies and before any AI call.
"""
import unittest
from datetime import datetime, timedelta

from taskuary.channels import POLL_OVERLAP, _since


class OverlapTests(unittest.TestCase):
    def test_the_window_reaches_back_past_its_own_watermark(self):
        polled = datetime.now() - timedelta(minutes=1)
        got = _since({'LastPolledAt': polled.isoformat(sep=' ', timespec='seconds')})
        self.assertLess(got, polled)
        self.assertAlmostEqual((polled - got).total_seconds(), POLL_OVERLAP.total_seconds(), delta=2)

    def test_the_eight_second_message_is_inside_the_next_window(self):
        """The actual failure, to the second: sent at :11, polled at :19, and the poll after
        that must still be able to see it."""
        sent = datetime(2026, 8, 24, 15, 29, 11)
        watermark = datetime(2026, 8, 24, 15, 29, 19)          # what that poll wrote
        self.assertLess(_since({'LastPolledAt': watermark.isoformat(sep=' ')}), sent)

    def test_a_source_never_polled_still_reaches_back_a_day(self):
        got = _since({})
        self.assertAlmostEqual((datetime.now() - got).total_seconds(), 86400, delta=5)

    def test_a_backfill_still_widens_the_window_rather_than_narrowing_it(self):
        """Startup catch-up asks for days; the overlap must never make that window smaller."""
        polled = (datetime.now() - timedelta(minutes=1)).isoformat(sep=' ', timespec='seconds')
        got = _since({'LastPolledAt': polled}, backfill_days=3)
        self.assertAlmostEqual((datetime.now() - got).days, 3, delta=1)

    def test_re_reading_the_overlap_costs_nothing(self):
        """The whole fix rests on this: a message seen twice is dropped on the FIRST line of
        ingest, before any policy is evaluated and before any AI is called."""
        from unittest import mock
        from taskuary.ingest import ingest_message
        from taskuary.store import MemoryStore
        s = MemoryStore()
        m = {'external_id': 'teams:c1:1', 'channel': 'teams', 'subject': 'x', 'body': 'hello',
             'from_name': 'Ray Silva', 'from_email': 'rs@partner.example'}
        ingest_message(s, m, llm=lambda *a, **k: '{"intent": "fyi", "why": "t"}')
        with mock.patch('taskuary.ingest.evaluate') as pol:
            llm = mock.Mock()
            out = ingest_message(s, m, llm=llm)
        self.assertEqual(out['status'], 'duplicate')
        pol.assert_not_called()                                # no policy pass
        llm.assert_not_called()                                # and no AI call


if __name__ == '__main__':
    unittest.main()
