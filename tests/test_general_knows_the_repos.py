"""The general assistant runs in Taskuary's scratch folder, not a checkout, and was told of no repository: asked for a login
kept in a repo's .env it searched the disk for ten minutes and said it could not find the repo (the owner, 2026-10-14). Its
prompt names every repo SOUL.md maps, and where each is checked out on this machine."""
import json, unittest

from taskuary import general
from taskuary.store import MemoryStore


class ReposBlockTests(unittest.TestCase):
    def test_every_mapped_repo_is_named_with_its_checkout(self):
        s = MemoryStore()
        s.save_doc('soul', '## Repo map\n- **northwind/ledger**: the finance backend - payroll and AR jobs\n'
                           '- **northwind/portal**: the customer portal\n', 't')
        s.upsert_agent('coder', 'cli', 'claude', json.dumps({'cwd_map': {'northwind/ledger': 'C:/src/ledger'}}))
        block = general.repos_block(s)
        self.assertIn('- northwind/ledger - the finance backend - payroll and AR jobs\n  checkout on this machine: C:/src/ledger', block)
        self.assertIn('- northwind/portal - the customer portal (no local checkout)', block)
        self.assertIn('look there first, never search the disk', block)
        tid = s.create_task({'Title': 'Find the SFTP login', 'Kind': 'general', 'Status': 'open'}, 'o')
        self.assertIn('checkout on this machine: C:/src/ledger', general._prompt(s, tid)[0])

    def test_with_no_repos_known_it_says_nothing(self):
        self.assertEqual(general.repos_block(MemoryStore()), '')


if __name__ == '__main__':
    unittest.main()
