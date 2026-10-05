"""Changing data in the owner's own systems is coding; looking at it is not (the owner, 2026-10-05: "data is coding i assume").

The 2026-09-25 rule called anything but a code change not-coding - "checking or confirming a value, granting a permission" - after
sixteen look-ups went to the coding agent. A payroll lead's request to correct people's facility in the T&E system then sat between
that rule and the triage document ("a query against one of their databases") and was judged general once. The line is now where
the work changes something: code or data in a system this install holds the code or credentials for is coding; reading is not.
"""
import unittest

from taskuary import triage


def kind_rule():
    seen = {}
    def llm(system, user, **kw): seen['system'] = system; return '{"intent": "task", "kind": "coding", "why": "x"}'
    triage.classify_intent({'from_email': 'erin@northwind.example', 'subject': 'Facility', 'body': 'Can we update the facility?'},
                           llm=llm, system='My own rules. Answer JSON only.')
    s = seen['system']
    return s[s.index('KIND, DECIDED FIRST'):].split('\n\n')[0]


class DataIsCodingTests(unittest.TestCase):
    def test_a_data_change_in_the_owners_systems_is_coding(self):
        rule = kind_rule()
        self.assertIn('data changed', rule)
        self.assertIn('a record corrected', rule)

    def test_reading_and_checking_stay_off_the_coding_agent(self):
        rule = kind_rule()
        self.assertIn('changes nothing', rule)
        self.assertIn('is not coding', rule)
        self.assertIn('never a reason to call it coding', rule)
