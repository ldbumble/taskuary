"""A triage failure is retried when a brain comes back, not only when somebody clicks it.

Retry was a button on one opened row, so an outage stranded everything it touched: the endpoint
answered 500 for an hour, the brain came back, and it judged only what arrived AFTER it while the
messages it had failed on sat wearing no verdict until the owner noticed each one (the owner,
2026-09-15: "we should also retry the ones that triage failed if it becomes available on next
sync no?").

The sweep is deliberately cheap when the brain is still down: the FIRST failure ends it, so a dead
endpoint costs one call a cycle rather than one per stranded row.
"""
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import ingest
from taskuary.store import MemoryStore

# RELATIVE, never a fixed date: the sweep only reaches back RETRY_HOURS, so a hardcoded stamp puts
# every one of these messages outside the window the day after it is written.
def ago(**kw): return (datetime.now() - timedelta(**kw)).strftime('%Y-%m-%d %H:%M:%S')

MSG = {'external_id': 'e1', 'channel': 'email', 'from_email': 'someone@partner.example', 'from_name': 'Someone',
       'conversation_id': 'conv-e1', 'subject': 'Refund for Watson', 'body': 'Please look at the attached history.',
       'sent_at': ago(minutes=5)}

FYI = lambda *a, **k: '{"intent": "fyi", "why": "an automated notice"}'


def boom(*a, **k): raise RuntimeError('azure_openai error 500')


class SweepTests(unittest.TestCase):
    def setUp(self): self.s = MemoryStore()

    def failed(self, n=1):
        out = []
        for i in range(n):
            r = ingest.ingest_message(self.s, {**MSG, 'external_id': f'e{i}', 'conversation_id': f'c{i}'}, llm=boom)
            self.assertEqual(r['status'], 'error')
            out.append(r['message_id'])
        return out

    def test_the_brain_coming_back_judges_what_it_failed_on(self):
        mids = self.failed(3)
        self.assertEqual(ingest.retry_failed_triage(self.s, FYI), 3)
        for mid in mids:
            self.assertEqual(self.s.get_message(mid)['Status'], 'filed')

    def test_a_still_dead_brain_costs_one_call_not_one_per_row(self):
        self.failed(5)
        calls = []
        def counted(*a, **k):
            calls.append(1); raise RuntimeError('azure_openai error 500')
        self.assertEqual(ingest.retry_failed_triage(self.s, counted), 0)
        self.assertEqual(len(calls), 1, 'the first failure ends the sweep')
        self.assertEqual(len(self.s.stranded_triage_failures()), 5, 'and they are all still there for next sync')

    def test_no_brain_at_all_sweeps_nothing(self):
        self.failed(2)
        self.assertEqual(ingest.retry_failed_triage(self.s, None), 0)

    def test_a_row_waiting_for_a_connector_is_swept_too(self):
        """An install with no AI files the row as `awaiting AI triage` - unjudged in exactly the
        same way, and connecting a brain is exactly the event that should judge it."""
        out = ingest.ingest_message(self.s, dict(MSG), llm=None)
        self.assertEqual(out['status'], 'error')
        self.assertEqual(ingest.retry_failed_triage(self.s, FYI), 1)
        self.assertEqual(self.s.get_message(out['message_id'])['Status'], 'filed')

    def test_a_row_that_keeps_failing_is_left_for_the_owners_button(self):
        """An outage is over in a cycle or two. A row still failing after RETRY_TRIES is failing
        for its own reasons, and retrying it every cycle forever would buy nothing."""
        mid = self.failed(1)[0]
        for _ in range(ingest.RETRY_TRIES + 2):
            ingest.retry_failed_triage(self.s, boom)
        tries = self.s.stranded_triage_failures()[0]['Tries']
        self.assertLessEqual(tries, ingest.RETRY_TRIES,
                             'it stops being retried instead of costing a call every cycle forever')
        self.assertEqual(self.s.get_message(mid)['Status'], 'error')

    def test_a_judged_row_is_never_swept_back_into_triage(self):
        ok = ingest.ingest_message(self.s, {**MSG, 'external_id': 'ok', 'conversation_id': 'ok'}, llm=FYI)
        self.assertEqual(ok['status'], 'filed')
        self.assertEqual(self.s.stranded_triage_failures(), [])
        self.assertEqual(ingest.retry_failed_triage(self.s, boom), 0)
        self.assertEqual(self.s.get_message(ok['message_id'])['Status'], 'filed')

    def test_the_sweep_takes_the_oldest_first(self):
        mids = self.failed(3)
        self.assertEqual([r['MessageId'] for r in self.s.stranded_triage_failures()], mids)

    def test_a_sweep_and_a_click_cannot_both_triage_one_message(self):
        """claim_retriage is the same compare-and-set the button uses."""
        mid = self.failed(1)[0]
        self.assertTrue(self.s.claim_retriage(mid))            # the owner's click got there first
        self.assertEqual(ingest.retry_failed_triage(self.s, FYI), 0)


class AgeTests(unittest.TestCase):
    """The sweep reaches back only as far as triage's job does.

    The first version had no age bound, so the moment the brain came back it judged everything that
    had EVER failed: two WhatsApp lines and an email from two weeks earlier became live tasks with
    drafted replies, on a conversation that had moved on days before. Both drafts were written and
    only escaped being sent because the assistant spotted a later reply (the owner, 2026-09-15:
    "what is this? don't see them in the task list?").
    """
    def setUp(self): self.s = MemoryStore()

    def _failed(self, sent_at, ext='old'):
        out = ingest.ingest_message(self.s, {**MSG, 'external_id': ext, 'conversation_id': ext,
                                             'sent_at': sent_at}, llm=boom)
        self.assertEqual(out['status'], 'error')
        return out['message_id']

    def test_a_fortnight_old_failure_is_not_resurrected(self):
        mid = self._failed(ago(days=14))
        self.assertEqual(ingest.retry_failed_triage(self.s, FYI), 0)
        self.assertEqual(self.s.get_message(mid)['Status'], 'error', 'it keeps its Retry button')

    def test_this_outages_rows_are_swept(self):
        mid = self._failed(ago(hours=2))
        self.assertEqual(ingest.retry_failed_triage(self.s, FYI), 1)
        self.assertEqual(self.s.get_message(mid)['Status'], 'filed')

    def test_the_owners_own_retry_still_reaches_anything(self):
        """The button is a decision somebody made; only the automatic sweep is bounded."""
        mid = self._failed(ago(days=30))
        self.assertTrue(self.s.claim_retriage(mid), 'no age bound on the explicit path')

    def test_the_window_is_the_query_not_a_filter_after_it(self):
        old = self._failed(ago(days=9), 'a')
        new = self._failed(ago(hours=1), 'b')
        since = ago(hours=24)
        got = [r['MessageId'] for r in self.s.stranded_triage_failures(25, since=since)]
        self.assertEqual(got, [new])
        self.assertIn(old, [r['MessageId'] for r in self.s.stranded_triage_failures(25)])


class PollWiringTests(unittest.TestCase):
    def test_the_full_sync_sweeps_after_it_drains(self):
        """Today's arrivals are judged first, so a still-dead endpoint is discovered on them
        rather than on the backlog."""
        import inspect
        from taskuary import server
        src = inspect.getsource(server._poll_reports)
        self.assertIn('retry_failed_triage', src)
        self.assertLess(src.index('_drain_worker'), src.index('retry_failed_triage'))


if __name__ == '__main__':
    unittest.main()
