"""A report's headline says what it CONCLUDED, not how many rows it read.

"Process Error Check - 2 rows" sat above a body reading "all clear" (2026-09-22). Both were
honest on their own terms - the query returned two rows, and the prompt had discounted both as
known-divested facilities - and together they contradicted each other. A row count describes the
INPUT; once a prompt has read those rows, the summary is the finding.
"""
import unittest

from taskuary.reports import headline_from


class TheHeadlineIsTheConclusion(unittest.TestCase):
    def test_a_short_verdict_becomes_the_headline(self):
        self.assertEqual(headline_from('all clear', '2 rows'), 'all clear')
        self.assertEqual(headline_from('All clear\n\nnothing needs you', '3 rows'), 'All clear')

    def test_markdown_decoration_is_not_part_of_it(self):
        self.assertEqual(headline_from('## Two exports failed', '2 rows'), 'Two exports failed')
        self.assertEqual(headline_from('**Disk is full**', '1 rows'), 'Disk is full')
        self.assertEqual(headline_from('- one vendor was rejected', '1 rows'), 'one vendor was rejected')

    def test_a_leading_blank_line_is_skipped(self):
        self.assertEqual(headline_from('\n\n   \nall clear', '2 rows'), 'all clear')

    def test_prose_keeps_the_count_instead(self):
        """A summary opening with a paragraph is not a verdict, and squeezing it into a headline
        would lose more than the count does."""
        essay = ('The export ran for 214 seconds and processed 2,262 rows across 83 facilities, '
                 'of which two did not complete for reasons described below.')
        self.assertEqual(headline_from(essay, '2 rows'), '2 rows')

    def test_an_empty_or_missing_summary_keeps_the_count(self):
        self.assertEqual(headline_from('', '0 rows'), '0 rows')
        self.assertEqual(headline_from(None, '5 rows'), '5 rows')
        self.assertEqual(headline_from('   \n  ', '5 rows'), '5 rows')

    def test_the_boundary_is_sixty_characters(self):
        self.assertEqual(headline_from('x' * 60, '2 rows'), 'x' * 60)
        self.assertEqual(headline_from('x' * 61, '2 rows'), '2 rows')


class AHeadlineThatAlreadySaysSomething(unittest.TestCase):
    """A multi-source head names which source died. A summary need never mention that, so a
    cheerful one must not be allowed to cover it."""

    def test_a_multi_source_head_is_left_alone(self):
        head = 'cash: 3 rows \u00b7 ledger: 7 rows \u00b7 the box: FAILED'
        self.assertEqual(headline_from('all good', head), head)

    def test_a_failure_is_never_papered_over(self):
        self.assertEqual(headline_from('all clear', 'the box: FAILED'), 'the box: FAILED')

    def test_only_a_bare_count_is_replaced(self):
        self.assertEqual(headline_from('all clear', '2 rows'), 'all clear')
        self.assertEqual(headline_from('all clear', 'reconciled'), 'reconciled')

if __name__ == '__main__':
    unittest.main()
