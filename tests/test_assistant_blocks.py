"""Every context block the Assistant reads is a declaration, and the defaults are what it read
before there were declarations (the assistant-reads-Taskuary design, 2026-09-19)."""
import unittest
from taskuary import assistantblocks as B
import tests.test_appfacts as A


class CatalogueTests(unittest.TestCase):
    def test_every_block_says_what_it_reads(self):
        self.assertGreaterEqual(len(B.CATALOGUE), 16)
        seen = set()
        for b in B.CATALOGUE:
            self.assertNotIn(b.id, seen, f'{b.id} declared twice'); seen.add(b.id)
            self.assertTrue(b.label, f'{b.id} has no label')
            self.assertEqual(bool(b.heading), not b.proposes, f'{b.id}: a context block needs a heading, a producer must not have one')
            self.assertIn(b.kind, ('query', 'view'), f'{b.id} is neither a query nor a view')
            self.assertTrue(b.tables, f'{b.id} names no table')
            self.assertTrue(callable(b.build), f'{b.id} has no builder')
            if b.kind == 'query': self.assertTrue(b.sql, f'{b.id} is a query with no SQL to show')

    def test_a_query_blocks_sql_runs(self):
        s = A.store()
        for b in B.CATALOGUE:
            if b.kind != 'query' or not b.sql: continue
            with self.subTest(block=b.id):
                text, mids = B.render(s, b, B.defaults(s, b))
                self.assertIsInstance(text, str); self.assertIsInstance(mids, list)

    def test_by_id_finds_and_misses(self):
        self.assertEqual(B.by_id('gone_quiet').label, 'Work gone quiet')
        self.assertIsNone(B.by_id('nope'))


from taskuary import assistant


class DefaultsAreTodayTests(unittest.TestCase):
    """The one test that must never be relaxed: an Assistant report that has configured nothing
    reads exactly what it read before blocks existed."""
    def test_the_default_payload_is_unchanged(self):
        s = A.store()
        cands = assistant.candidates(s, assistant.cfg(s))
        self.assertEqual(assistant.inputs(s, cands), assistant.inputs(s, cands, blocks=None))

    def test_every_default_on_block_appears_in_the_payload(self):
        s = A.store()
        text = assistant.inputs(s, [])
        for b in B.CATALOGUE:
            if not B.defaults(s, b)['on']: continue
            if not b.heading: continue                      # a producer renders under CANDIDATES, not its own head
            if not B.render(s, b, B.defaults(s, b))[0].strip(): continue   # a block with nothing to say has never printed an empty head
            head = b.heading.split('(')[0].split('{')[0].strip().rstrip(':')
            with self.subTest(block=b.id): self.assertIn(head, text, f'{b.id} is on by default and is not in the payload')


if __name__ == '__main__':
    unittest.main()
