"""The routing judge reads the report's CONCLUSION, not the rows underneath it.

The run that prompted this (SourceId 4, "Process Error Check", 2026-09-22): the query is
`WHERE error IS NOT NULL`, so every row it returns is a failure by construction. The owner's
ai_prompt then says two named facilities were divested and their 403 "Business is not open" is
expected and must NOT be reported. The summariser obeyed and wrote "all clear".

The judge was then handed `head + body`, and the body is the summary PLUS a `--- raw data ---`
block carrying `"success": "0"` and `"error": "Partial export - 2 of 83 facilities failed..."`.
So it answered yes, five runs in a row, and an all-clear check sat on the work rail every time -
the exact failure reports.py already warns about: a message that arrives whether or not anything
is wrong is a message you stop reading.

The judge cannot see the ai_prompt, so it cannot know 66/67 are expected. Re-reading the rows is
re-litigating a decision that was already made WITH that knowledge. It gets the conclusion.
"""
import unittest

from taskuary import reports


class TheJudgeReadsTheConclusion(unittest.TestCase):
    def test_the_raw_block_is_not_put_in_front_of_the_judge(self):
        res = {'head': 'Process Error Check — 2 rows',
               'body': 'all clear\n\n--- raw data ---\n'
                       '{"success": "0", "error": "Partial export - 2 of 83 facilities failed. '
                       '67: rule error. Received HTTP status code, 403. Business is not open"}'}
        state = reports.judge_state(res)
        self.assertIn('all clear', state)
        self.assertNotIn('raw data', state)
        self.assertNotIn('Partial export', state)
        self.assertNotIn('403', state)

    def test_a_report_with_no_summary_still_shows_its_rows(self):
        """Without an ai_prompt the rows ARE the conclusion - there is nothing else to judge."""
        res = {'head': 'Open incidents — 3 rows',
               'body': 'id,who,what\n1,ops,disk full\n2,ops,cert expiring\n3,ops,queue stuck'}
        state = reports.judge_state(res)
        self.assertIn('disk full', state)
        self.assertIn('queue stuck', state)

    def test_the_head_is_still_carried(self):
        res = {'head': 'Nightly check — 0 rows', 'body': 'nothing ran\n\n--- raw data ---\nx'}
        self.assertTrue(reports.judge_state(res).startswith('Nightly check'))

    def test_a_summary_that_mentions_the_phrase_is_not_truncated_early(self):
        """Only the real separator cuts - a summary discussing 'raw data' keeps its words."""
        res = {'head': 'h', 'body': 'the raw data looked wrong to me, here is why\n\n--- raw data ---\nrows'}
        state = reports.judge_state(res)
        self.assertIn('the raw data looked wrong to me, here is why', state)
        self.assertNotIn('\nrows', state)


if __name__ == '__main__':
    unittest.main()
