"""A test run can never reach the owner's real data, whichever way it was started.

tests/conftest.py points TASKUARY_HOME at a temp dir before anything of ours is imported, which
works for `pytest`. It does NOT work for `python tests/test_terminal.py` - every test file here
ends in unittest.main(), and running one directly loads no conftest at all.

That door was open and something went through it: two copies of test_terminal's fixture task
("payroll adjustments post to the wrong month") and its graph:E2E message turned up in the
owner's live database on 2026-09-01, one of them while they were looking at the screen. The same
class of accident on 2026-08-27 cost SOUL.md and left 140 fixture tasks on the board.

So the guard belongs where the decision is made - config.home() - not in a file that only one
entry point loads.
"""
import os
import unittest
from pathlib import Path

from taskuary import config


class TheOwnersDataIsOffLimits(unittest.TestCase):
    def test_a_test_run_never_lands_on_the_real_home(self):
        real = Path.home() / '.taskuary'
        self.assertNotEqual(config.home().resolve(), real.resolve())

    def test_it_is_detected_from_the_interpreter_not_from_conftest(self):
        """unittest or pytest being imported IS the signal - no cooperation required."""
        self.assertTrue(config._under_test())

    def test_an_explicit_home_is_still_honoured(self):
        """The suite sets one; a developer pointing at a scratch dir must still get it."""
        keep = os.environ.get('TASKUARY_HOME')
        try:
            os.environ['TASKUARY_HOME'] = str(Path(keep or '.').resolve())
            self.assertEqual(config.home().resolve(), Path(keep or '.').resolve())
        finally:
            if keep is None: os.environ.pop('TASKUARY_HOME', None)
            else: os.environ['TASKUARY_HOME'] = keep

    def test_the_escape_hatch_exists_and_is_explicit(self):
        """A test that genuinely means the real home has to say so by name."""
        keep_h, keep_a = os.environ.pop('TASKUARY_HOME', None), os.environ.get('TASKUARY_ALLOW_TEST_HOME')
        try:
            os.environ['TASKUARY_ALLOW_TEST_HOME'] = '1'
            self.assertFalse(config._under_test())
        finally:
            if keep_a is None: os.environ.pop('TASKUARY_ALLOW_TEST_HOME', None)
            else: os.environ['TASKUARY_ALLOW_TEST_HOME'] = keep_a
            if keep_h is not None: os.environ['TASKUARY_HOME'] = keep_h

    def test_the_app_itself_is_not_affected(self):
        """Nothing here may change where a real run keeps its data - only a test run is redirected."""
        import inspect
        src = inspect.getsource(config.home)
        self.assertIn('_under_test()', src)
        self.assertIn("os.getenv('TASKUARY_HOME')", src)


if __name__ == '__main__':
    unittest.main()
