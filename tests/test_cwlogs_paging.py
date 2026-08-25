""""Only showing me 9 or so rows?"

FilterLogEvents pages, and its pages are not full ones: it scans log streams and returns
whatever that pass found, with a nextToken. A lambda makes one stream per invocation, so a
single call answered with nine events while the rest of the day sat behind the token - and
"9 events" read as "a quiet day", which for a report asked to find ERRORS is the worst
available way to be wrong.
"""
import unittest
from unittest import mock

from taskuary import aws


def _ev(i, msg=None):
    return {'timestamp': 1700000000000 + i * 1000, 'logStreamName': f'stream-{i % 3}',
            'message': msg or f'message {i}'}


class Fake:
    """A log group that answers in small pages, as AWS actually does."""
    def __init__(self, pages):
        self.pages, self.calls = pages, 0

    def filter_log_events(self, **kw):
        self.kw = kw
        page = self.pages[min(self.calls, len(self.pages) - 1)]
        self.calls += 1
        return page


def _run(pages, **cfg):
    f = Fake(pages)
    with mock.patch.object(aws, 'client', lambda *a, **k: f):
        head, body = aws.run_cloudwatch_logs({'log_group': '/aws/lambda/x', 'region': 'us-east-1', **cfg})
    return head, body, f


class ItKeepsAskingTests(unittest.TestCase):
    def test_it_follows_the_token_instead_of_believing_the_first_page(self):
        pages = [{'events': [_ev(i) for i in range(k * 9, k * 9 + 9)], 'nextToken': 't'} for k in range(30)]
        head, body, f = _run(pages)
        self.assertGreater(f.calls, 1, 'one call and it believed a nine-event page')
        self.assertEqual(len(body.splitlines()), 9 * aws.LOG_PAGE_CAP)
        self.assertEqual(f.calls, aws.LOG_PAGE_CAP)          # bounded, not unbounded

    def test_a_scan_that_stopped_early_says_so(self):
        """The difference that matters: nine because that is all there was, or nine because we
        stopped looking. The first is an answer; the second is a report that lies quietly."""
        pages = [{'events': [_ev(i)], 'nextToken': 'more'} for i in range(30)]
        head, _body, _f = _run(pages)
        self.assertIn('may be more', head)
        self.assertIn('filter pattern', head)                # and what to do about it

    def test_a_genuinely_quiet_group_is_one_call_and_no_warning(self):
        head, body, f = _run([{'events': [_ev(i) for i in range(9)]}], hours=6)
        self.assertEqual(f.calls, 1)
        self.assertEqual(head, '9 events in the last 6h')     # the window, so "only 9?" is answered
        self.assertNotIn('may be more', head)
        self.assertEqual(len(body.splitlines()), 9)

    def test_no_events_at_all_still_names_the_window(self):
        head, _b, _f = _run([{'events': []}], hours=1)
        self.assertEqual(head, '0 events in the last 1h')

    def test_it_stops_as_soon_as_it_has_more_than_the_cap(self):
        """Paging past the cap is wasted calls: rows_out only needs one extra to know it cut."""
        pages = [{'events': [_ev(i) for i in range(k * 100, k * 100 + 100)], 'nextToken': 't'} for k in range(10)]
        _head, _body, f = _run(pages, max_rows=150)
        self.assertEqual(f.calls, 2)


class WhichEventsSurviveTheCapTests(unittest.TestCase):
    def test_the_newest_are_kept_because_aws_hands_them_over_oldest_first(self):
        """Capping the raw order kept the OLDEST events in the window - the wrong half of a
        'what happened today' report, and the half least likely to hold the error."""
        head, body, _f = _run([{'events': [_ev(i) for i in range(500)]}], max_rows=5)
        self.assertIn('capped at 5', head)
        lines = body.splitlines()
        self.assertIn('message 499', lines[0])
        self.assertIn('message 495', lines[-1])
        self.assertNotIn('message 0', body)

    def test_the_window_and_the_cap_are_both_said_at_once(self):
        head, _b, _f = _run([{'events': [_ev(i) for i in range(500)]}], max_rows=5, hours=48)
        self.assertIn('events in the last 48h', head)
        self.assertIn('capped at 5', head)


class TheRegionErrorStillWorksTests(unittest.TestCase):
    def test_a_missing_group_is_still_reported_as_a_region_problem(self):
        """Paging wraps the same call the region message came from - it must survive that."""
        err = type('ResourceNotFoundException', (Exception,), {})
        class Boom:
            def filter_log_events(self, **kw): raise err('The specified log group does not exist.')
        with mock.patch.object(aws, 'client', lambda *a, **k: Boom()), self.assertRaises(RuntimeError) as e:
            aws.run_cloudwatch_logs({'log_group': '/x', 'region': 'us-west-2'})
        self.assertIn('us-west-2', str(e.exception))
        self.assertIn('belongs to ONE region', str(e.exception))


if __name__ == '__main__':
    unittest.main()
