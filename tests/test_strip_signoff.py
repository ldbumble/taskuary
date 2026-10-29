"""A chat reply carries no sign-off - the writer is told so (CHAT, EMAIL), and what it signed anyway is taken off only where it is
KNOWN to be a signature: the owner's own name, or the lines of their saved signature. No closing-word list decides what a last line
means (the owner, 2026-10-28): "Friday works." was once cut as a name, and "Thank you!" kept behind an eaten word boundary."""
import unittest

from taskuary import responder

OWN = ['Alex Doyle', 'Alex']


class StripSignoffTests(unittest.TestCase):
    def test_the_owners_own_name_goes(self):
        self.assertEqual(responder.strip_signoff('Friday works.\n\nAlex', OWN), 'Friday works.')
        self.assertEqual(responder.strip_signoff('Friday works.\n\nAlex Doyle.', OWN), 'Friday works.')
        self.assertEqual(responder.strip_signoff('Got it.\nFriday works.\n\n-- alex', OWN), 'Got it.\nFriday works.')

    def test_a_signature_line_goes(self):
        sig = 'Alex Doyle\nController, Northwind'
        self.assertEqual(responder.strip_signoff('Friday works.\n\nAlex Doyle\nController, Northwind', sig.splitlines()), 'Friday works.')

    def test_a_closing_above_a_cut_name_goes_by_its_shape(self):
        self.assertEqual(responder.strip_signoff('Friday works.\n\nWarmly,\nAlex', OWN), 'Friday works.')
        self.assertEqual(responder.strip_signoff('Friday works,', OWN), 'Friday works,')

    def test_no_word_list_decides_what_a_line_means(self):
        for text in ('Sounds good.', 'Friday works.\n\nThanks!', 'Thanks for sending the totals over, they match ours.', 'Erin'):
            self.assertEqual(responder.strip_signoff(text, OWN), text)
        self.assertFalse(hasattr(responder, '_SIGNOFF'))

    def test_signed_swaps_the_writers_signature_for_the_saved_one(self):
        self.assertEqual(responder.signed('Friday works.\n\nAlex Doyle', 'Alex Doyle\nController'), 'Friday works.\n\nAlex Doyle\nController')


if __name__ == '__main__':
    unittest.main()
