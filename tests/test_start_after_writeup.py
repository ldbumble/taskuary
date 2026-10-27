"""A Stop and save still writing up closes its session only once the result is saved, and the page offers Continue and Run another
agent from that Result: a press in the gap waits for the write-up instead of being refused "already has a live session"
(website/browser/agent-presses)."""
import threading, time, unittest
from unittest import mock

from taskuary import server, writeup


class AfterWriteupTests(unittest.TestCase):
    def test_a_start_waits_for_the_running_writeup(self):
        done = threading.Event()
        with mock.patch.dict(writeup._JOBS, {7: done}):
            threading.Timer(0.2, done.set).start()
            t0 = time.time(); server._after_writeup(7, timeout=5)
            self.assertGreaterEqual(time.time() - t0, 0.15, 'it waited for the write-up')

    def test_no_writeup_no_wait_and_never_from_inside_one(self):
        t0 = time.time(); server._after_writeup(8, timeout=5)
        self.assertLess(time.time() - t0, 0.1)
        held = threading.Event()
        with mock.patch.dict(writeup._JOBS, {9: held}), mock.patch.object(writeup, 'in_job', return_value=True):
            t0 = time.time(); server._after_writeup(9, timeout=5)
            self.assertLess(time.time() - t0, 0.1, 'the write-up itself starting something never waits on itself')


if __name__ == '__main__':
    unittest.main()
