"""A report that fails the SAME way twice reaches the owner once (2026-09-23: "same for a failed report
run, next should dismiss it"). A different error, or a failure after a good run, is news again."""
import unittest

from taskuary import reports
from taskuary.store import MemoryStore


def run(s, sid, failed, error=None):
    s.add_report_run(sid, {'at': '2026-09-23 10:00:00', 'type': 'mssql', 'title': 'Process Error Check',
                           'ms': 10, 'subject': 'x', 'failed': failed, 'error': error})


class SameFailureTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.sid = self.s.save_source({'Channel': 'report', 'Address': 'Process Error Check', 'Active': 1,
                                       'ConfigJson': '{"type": "mssql", "title": "Process Error Check"}'}, 'o')

    def test_the_same_error_again_is_quiet_and_numbers_do_not_make_it_new(self):
        run(self.s, self.sid, True, "Report error: ('08001', 'Named Pipes Provider: error 40 at 08:43')")
        self.assertTrue(reports.same_failure_as_last(self.s, self.sid, "Report error: ('08001', 'Named Pipes Provider: error 40 at 12:10')"))
        run(self.s, self.sid, True, "('08001', 'Named Pipes Provider: error 40 at 13:00')")       # stored bare, said with the prefix
        self.assertTrue(reports.same_failure_as_last(self.s, self.sid, "Report error: ('08001', 'Named Pipes Provider: error 40 at 14:00')"))

    def test_a_different_error_or_a_failure_after_a_good_run_is_news(self):
        run(self.s, self.sid, True, 'Report error: timeout')
        self.assertFalse(reports.same_failure_as_last(self.s, self.sid, 'Report error: login failed'))
        run(self.s, self.sid, False)
        self.assertFalse(reports.same_failure_as_last(self.s, self.sid, 'Report error: timeout'))
