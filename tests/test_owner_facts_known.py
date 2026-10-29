"""What About you saved reaches the agents, and the Advisor reads the saved signature as known-true, not invented."""
import unittest
from taskuary.store import MemoryStore
from taskuary import advisor, brief


def _owner(s):
    for k, v in (('owner_name', 'Alex Doyle'), ('owner_title', 'Operations Director'), ('owner_company', 'Northwind'),
                 ('email_signature', 'Alex Doyle\\nOperations Director, Northwind')): s.set_setting(k, v, 'owner')


class OwnerFactsKnownTests(unittest.TestCase):
    def test_an_agent_reads_the_owner_title_and_company(self):
        s = MemoryStore(); _owner(s)
        bg = brief.background(s)
        self.assertIn('Job title: Operations Director', bg)
        self.assertIn('Company: Northwind', bg)

    def test_the_advisor_is_told_the_signature_is_the_saved_one(self):
        s = MemoryStore(); _owner(s)
        line = advisor.known_owner_line(s)
        self.assertIn('KNOWN TRUE', line)
        self.assertIn('job title: Operations Director', line)
        self.assertIn('Alex Doyle / Operations Director, Northwind', line)

    def test_nothing_saved_says_nothing(self):
        s = MemoryStore(); s.set_setting('email_signature_on', '0', 'owner')
        self.assertNotIn('Saved in About you', brief.background(s))


if __name__ == '__main__': unittest.main()
