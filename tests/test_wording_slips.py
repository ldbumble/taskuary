"""Wording slips the email walk found (2026-10-29): sentences cut mid-word, a label with nothing after it."""
import unittest
from taskuary import blackboard


class WordingSlipTests(unittest.TestCase):
    def test_a_start_failure_reason_is_cut_on_a_word_never_mid_word(self):
        err = 'The agent could not open the checkout ' + 'because the repository folder was moved away ' * 8
        line = blackboard.failed_line(err, False)
        why = line.split(': ', 1)[1].split('. Press Start')[0]
        self.assertTrue(why.endswith('…'), why)
        self.assertTrue(err.startswith(why[:-1]) and err[len(why) - 1] == ' ', f'ends on a whole word: {why}')
        first = 'First the login failed on the allowed host because the vendor had not yet added our address to its list of callers'
        self.assertEqual(blackboard._why(f'{first}. ' + 'Then the retry timed out waiting for it ' * 6), first)    # a whole sentence
        self.assertEqual(blackboard._why('short reason.'), 'short reason')


if __name__ == '__main__': unittest.main()
