"""A chat reply carries no sign-off. The closing-word pattern held a backspace where its word boundary was (an eaten
backslash-b, since 2026-08-20), so it never matched: only the short-line fallback stripped anything, and "Thank you!"
stayed on the end of every chat reply that closed with it (2026-10-06)."""
import unittest

from taskuary import responder


class StripSignoffTests(unittest.TestCase):
    def test_closing_words_go_whatever_punctuation_follows(self):
        for close in ('Thank you!', 'Thanks!!', 'Best regards.', 'Cheers!', 'Kind regards,', 'Sincerely'):
            self.assertEqual(responder.strip_signoff(f'Friday works.\n\n{close}'), 'Friday works.', close)

    def test_a_sentence_that_only_starts_with_one_stays(self):
        self.assertEqual(responder.strip_signoff('Thanks for sending the totals over, they match ours.'),
                         'Thanks for sending the totals over, they match ours.')

    def test_a_short_last_sentence_is_the_reply_not_a_name(self):
        self.assertEqual(responder.strip_signoff('Sounds good.'), 'Sounds good.')
        self.assertEqual(responder.strip_signoff('Got it.\nFriday works.\n\nAlex'), 'Got it.\nFriday works.')
        self.assertEqual(responder.strip_signoff('Friday works.\n\nAlex Doyle'), 'Friday works.')

    def test_the_pattern_is_a_real_word_boundary(self):
        self.assertNotIn('\x08', responder._SIGNOFF.pattern)


if __name__ == '__main__':
    unittest.main()
