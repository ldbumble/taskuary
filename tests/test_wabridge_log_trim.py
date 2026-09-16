"""The bridge's log is cleaned up on its own, a few days at a time.

Baileys logs every protocol frame it handles, the bridge appends that to one file, and nothing ever
rotated it: on the owner's machine wa-bridge.log had reached 205 MB (2026-09-15). The app's own log
has had rotation since logs.py was written; this is the same courtesy for the one a Node subprocess
writes, which loguru never sees.

Truncating IN PLACE is deliberate: the running bridge holds the file open in append mode, and on
Windows a held-open file cannot be renamed or deleted. An append handle always writes at the end,
so it keeps working across the truncation.
"""
import os
import unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import wabridge
from taskuary.store import MemoryStore

NOW = datetime(2026, 9, 15, 19, 0, 0)


class LogTrimTests(unittest.TestCase):
    def setUp(self):
        self.tmp = __import__('tempfile').mkdtemp(prefix='walog_')
        self.log = __import__('pathlib').Path(self.tmp) / 'wa-bridge.log'
        self.patch = mock.patch.object(wabridge, 'LOG', self.log)
        self.patch.start()
        self.addCleanup(self.patch.stop)
        self.s = MemoryStore()

    def write(self, n): self.log.write_bytes(b'x' * n)

    def test_a_log_past_the_size_cap_is_emptied(self):
        self.write(wabridge.LOG_MAX_BYTES + 1)
        out = wabridge.trim_log(self.s, NOW)
        self.assertTrue(out and out['trimmed'])
        self.assertEqual(self.log.stat().st_size, 0)

    def test_a_small_log_is_left_alone(self):
        self.write(1024)
        wabridge.trim_log(self.s, NOW)
        self.assertEqual(self.log.stat().st_size, 1024, 'nothing was wrong with it')

    def test_a_few_days_pass_and_it_is_cleaned_anyway(self):
        """Size is not the only reason - a long-running bridge should not keep a month of frames."""
        self.write(1024)
        wabridge.trim_log(self.s, NOW - timedelta(days=wabridge.LOG_KEEP_DAYS + 1))
        self.write(2048)
        out = wabridge.trim_log(self.s, NOW)
        self.assertTrue(out and out['trimmed'])
        self.assertEqual(self.log.stat().st_size, 0)

    def test_it_does_not_run_twice_in_one_day(self):
        self.write(1024)
        wabridge.trim_log(self.s, NOW)
        self.write(wabridge.LOG_MAX_BYTES + 1)
        self.assertIsNone(wabridge.trim_log(self.s, NOW + timedelta(hours=2)),
                          'the daily check already ran today')

    def test_the_running_bridge_keeps_writing_across_a_trim(self):
        """The real situation: the Node process holds it open in append mode while we truncate."""
        self.write(wabridge.LOG_MAX_BYTES + 1)
        with open(self.log, 'ab') as bridge_handle:
            wabridge.trim_log(self.s, NOW)
            bridge_handle.write(b'still connected\n')
            bridge_handle.flush()
        self.assertEqual(self.log.read_bytes(), b'still connected\n')

    def test_no_log_yet_is_not_an_error(self):
        self.assertIsNone(wabridge.trim_log(self.s, NOW))
