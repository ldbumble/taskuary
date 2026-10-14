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


class StrangerGetsNoBackgroundTests(unittest.TestCase):
    """Who the owner is - SOUL.md, JOB.md, the repos and their paths - is what a planted line in a stranger's mail would ask the
    agent to repeat back. A stranger's task reads none of it; the owner's own task reads all of it."""
    def _store(self, origin):
        s = MemoryStore()
        s.save_doc('job', '## The job\n- Runs month-end close for the finance team.', 't')
        s.save_doc('soul', '## Repo map\n- **northwind/ledger**: the finance backend\n', 't')
        s.upsert_agent('coder', 'cli', 'claude', json.dumps({'cwd_map': {'northwind/ledger': 'C:/src/ledger'}}))
        tid = s.create_task({'Title': 'Look at this invoice', 'Kind': 'general', 'Status': 'open'}, 'o')
        s.cx.execute('UPDATE task SET OriginBase=? WHERE TaskId=?', (origin, tid)); s.cx.commit()
        return s, tid

    def test_a_strangers_task_reads_none_of_it(self):
        from taskuary import context
        s, tid = self._store('stranger')
        system = general._prompt(s, tid)[0]
        for private in ('month-end close', 'C:/src/ledger', 'ABOUT THE OWNER'): self.assertNotIn(private, system, private)
        self.assertNotIn('month-end close', context.build(s, tid))

    def test_the_owners_own_task_reads_all_of_it(self):
        from taskuary import context
        s, tid = self._store('owner')
        system = general._prompt(s, tid)[0]
        for known in ('month-end close', 'C:/src/ledger', 'ABOUT THE OWNER'): self.assertIn(known, system, known)
        self.assertIn('month-end close', context.build(s, tid))
