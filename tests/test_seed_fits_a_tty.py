"""A typed seed has to fit what a tty will accept on one line, or it loses its tail.

macOS CI failed here for a day and said only "the prompt landed incomplete - clearing and
retyping", twice, then sat on a full input box with no Enter. The numbers, once the warning
carried them, were the whole story: typed 1142 chars. MAX_CANON - what a canonical-mode tty holds
on one line before it DISCARDS the rest, with no error and no signal - is 4096 on Linux and 1024
on macOS/BSD. A TUI that has not yet switched the terminal to raw mode is still canonical, which
is exactly the moment we type the first prompt into one.

So the tail went missing, and the tail is what `_echoed` checks, so a fully-typed prompt read as
eaten and got retyped until seed() gave up. Not a test artifact: any Mac user with a long seed.
"""
import unittest

from taskuary.terminal import TTY_CANON, fit_typed


class ATypedSeedFits(unittest.TestCase):
    def test_a_short_seed_is_left_exactly_alone(self):
        s = 'TASK TQ-0001 - fix the export. WHAT TO DO: work it from THIS message alone.'
        self.assertEqual(fit_typed(s), s)

    def test_a_long_seed_comes_back_under_the_limit(self):
        s = 'TASK TQ-0001 - fix it. FROM Dana on email, subject "x": ' + ('detail ' * 400)
        self.assertLessEqual(len(fit_typed(s)), TTY_CANON)

    def test_the_message_gives_and_the_ask_survives(self):
        """The same order seed_text uses against SEED_CEILING: never the rules, never the ask."""
        s = ('TASK TQ-0001 - payroll posts to the wrong month. FROM Dana on email, subject "P": '
             + ('long quoted thread ' * 200)
             + ' WHEN FINISHED: run `taskuary --done`.')
        out = fit_typed(s)
        self.assertTrue(out.startswith('TASK TQ-0001 - payroll posts to the wrong month.'))
        self.assertLessEqual(len(out), TTY_CANON)

    def test_it_says_it_cut_something(self):
        """An agent cannot ask for the rest of something it was not told was cut."""
        s = 'TASK TQ-1 - x. FROM Dana on email, subject "y": ' + ('word ' * 400)
        self.assertIn('truncated here', fit_typed(s))

    def test_a_seed_with_no_message_in_it_still_fits(self):
        """No 'FROM ' to give: it still must not exceed the line, so the whole thing is cut."""
        out = fit_typed('TASK TQ-1 - ' + ('x' * 3000))
        self.assertLessEqual(len(out), TTY_CANON)
        self.assertIn('truncated here', out)

    def test_the_limit_is_the_smallest_one_we_might_meet(self):
        """1024 is macOS/BSD; Linux is 4096. We do not know whose tty this is."""
        self.assertLessEqual(TTY_CANON, 1024)

    def test_whitespace_is_flattened_because_a_newline_submits(self):
        self.assertNotIn('\n', fit_typed('TASK TQ-1\n- do it\n\nnow'))


if __name__ == '__main__':
    unittest.main()
