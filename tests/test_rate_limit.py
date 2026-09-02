"""A usage limit is a wait, not a fault.

From the owner's Failing-right-now bell, 2026-09-02: a whole rate_limit_event JSON blob sitting
red all day for an allowance that had already reset. The CLI exits 1 and says it in JSON, so the
JSON became the error text.
"""
import json, unittest
from datetime import datetime, timedelta

from taskuary import agents

# the event exactly as claude emitted it on the owner's machine
BLOB = json.dumps({'type': 'rate_limit_event', 'uuid': '4013c24c-1809-4570-938',
                   'rate_limit_info': {'status': 'rejected', 'resetsAt': 1788364200,
                                       'rateLimitType': 'five_hour', 'overageStatus': 'rejected',
                                       'overageDisabledReason': 'org_level_disabled', 'isUsingOverage': False,
                                       'unifiedWindows': {'five_hour': {'utilization': 1.09, 'resetsAt': 1788364200},
                                                          'seven_day': {'utilization': 0.13, 'resetsAt': 1788933600}}}})


class RecogniseTests(unittest.TestCase):
    def test_the_event_is_found_in_the_run_output(self):
        for raw in ([BLOB], [f'{{"type":"system"}}', BLOB], BLOB, 'noise\n' + BLOB):
            self.assertEqual(agents.rate_limited(raw).get('rateLimitType'), 'five_hour')

    def test_anything_else_is_not_a_rate_limit(self):
        """It must not swallow real failures - a crash has to stay a crash."""
        for raw in (None, '', 'boom', ['{"type":"result","is_error":true}'], ['not json at all'],
                    [json.dumps({'rate_limit_info': {'status': 'allowed', 'rateLimitType': 'five_hour'}})]):
            self.assertEqual(agents.rate_limited(raw), {})


class WordingTests(unittest.TestCase):
    def test_it_says_which_allowance_when_it_returns_and_that_nothing_is_broken(self):
        msg = agents.rate_limit_msg('claude', agents.rate_limited([BLOB]))
        self.assertNotIn('{', msg)                       # no JSON reaches the owner
        self.assertIn('five-hour usage limit', msg)
        self.assertIn('comes back at', msg)
        self.assertIn('Nothing is wrong with this report', msg)
        self.assertIn('turned off for this account', msg)   # overage rejected: it waits, not costs

    def test_a_reset_further_out_carries_its_day(self):
        soon = datetime.now() + timedelta(days=6)
        msg = agents.rate_limit_msg('codex', {'status': 'rejected', 'rateLimitType': 'seven_day',
                                              'resetsAt': int(soon.timestamp())})
        self.assertIn('seven-day usage limit', msg)
        self.assertIn(soon.strftime('%a %d %b'), msg)

    def test_tomorrow_is_said_as_tomorrow(self):
        t = datetime.now().replace(hour=9, minute=30) + timedelta(days=1)
        msg = agents.rate_limit_msg('claude', {'status': 'rejected', 'resetsAt': int(t.timestamp())})
        self.assertIn('tomorrow', msg)

    def test_a_missing_or_broken_timestamp_still_gives_a_sentence(self):
        for info in ({'status': 'rejected'}, {'status': 'rejected', 'resetsAt': 'soon'},
                     {'status': 'rejected', 'resetsAt': 99999999999999}):
            msg = agents.rate_limit_msg('claude', info)
            self.assertIn('usage limit', msg)
            self.assertNotIn('comes back at', msg)

    def test_the_window_falls_back_to_whatever_the_cli_called_it(self):
        msg = agents.rate_limit_msg('claude', {'status': 'rejected', 'rateLimitType': 'monthly'})
        self.assertIn('its monthly usage limit', msg)


if __name__ == '__main__':
    unittest.main()
