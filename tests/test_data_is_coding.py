"""Changing data in the owner's own systems is coding; looking at it is not (the owner, 2026-10-05: "data is coding i assume").

The 2026-09-25 rule called anything but a code change not-coding - "checking or confirming a value, granting a permission" - after
sixteen look-ups went to the coding agent. A payroll lead's request to correct people's facility in the T&E system then sat between
that rule and the triage document ("a query against one of their databases") and was judged general once. The line is now where
the work changes something: code or data in a system this install holds the code or credentials for is coding; reading is not.
"""
import unittest

from taskuary import triage


def kind_rule():
    """The kind question, as triage is told it: the guide's section 4 (it was a code-written block until 2026-10-09)."""
    return triage.shipped_section('## 4.')


class DataIsCodingTests(unittest.TestCase):
    def test_a_data_change_in_the_owners_systems_is_coding(self):
        rule = kind_rule()
        self.assertIn('data changed', rule)
        self.assertIn('a record corrected', rule)

    def test_reading_and_checking_stay_off_the_coding_agent(self):
        rule = kind_rule()
        self.assertIn('**general** - no change, but reading, checking or thinking helps', rule)
        self.assertIn('the work only reads from a system (a query, a report, a look-up)', rule)
        self.assertIn('a repository whose topic matches the message, without a change to make there', rule)
