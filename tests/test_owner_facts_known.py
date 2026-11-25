"""What About you saved reaches the agents, and the Advisor reads the saved signature as known-true, not invented."""
import unittest
from taskuary.store import MemoryStore
from taskuary import brief


def _owner(s):
    for k, v in (('owner_name', 'Alex Doyle'), ('owner_title', 'Operations Director'), ('owner_company', 'Northwind'),
                 ('email_signature', 'Alex Doyle\\nOperations Director, Northwind')): s.set_setting(k, v, 'owner')


class OwnerFactsKnownTests(unittest.TestCase):
    def test_an_agent_reads_the_owner_title_and_company(self):
        s = MemoryStore(); _owner(s)
        bg = brief.background(s)
        self.assertIn('Job title: Operations Director', bg)
        self.assertIn('Company: Northwind', bg)

    def test_the_agent_knows_the_one_reading_its_words_is_the_owner(self):
        "The owner, 2026-11-25: an agent wrote of him in the third person to his own face - who reads it is a fact of its context."
        s = MemoryStore(); _owner(s)
        self.assertIn('the person reading your words is the owner, Alex Doyle', brief.background(s).split('\n', 1)[0])


    def test_nothing_saved_says_nothing(self):
        s = MemoryStore(); s.set_setting('email_signature_on', '0', 'owner')
        self.assertNotIn('Saved in About you', brief.background(s))


if __name__ == '__main__': unittest.main()
