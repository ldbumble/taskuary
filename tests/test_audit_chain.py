"""The tamper-evident log broke itself.

audit() read "the last row" and inserted in two separate critical sections, so the poll thread
and a click could both read the same parent and both insert - a FORK. Verification then reported
"BROKEN", which is the one thing this log must never say wrongly: a real tamper becomes
indistinguishable from the log's own noise. Found at ids 151/152 of a live database, both stamped
the same second, both carrying the same PrevHash.
"""
import threading
import unittest

from taskuary.store import GENESIS, MemoryStore, chain_hash, _audit_payload


class ConcurrentWritesCannotForkItTests(unittest.TestCase):
    def test_many_threads_auditing_at_once_leave_one_unbroken_chain(self):
        s = MemoryStore()
        def burst(n):
            for i in range(25): s.audit('task', n * 100 + i, 'raced', 'owner')
        threads = [threading.Thread(target=burst, args=(t,)) for t in range(8)]
        for t in threads: t.start()
        for t in threads: t.join()
        out = s.verify_audit_chain()
        self.assertEqual(out['rows'], 200)
        self.assertEqual(out['forked_ids'], [], 'concurrent writers forked the chain')
        self.assertEqual(out['altered_ids'], [])
        self.assertTrue(out['ok'])

    def test_every_row_links_to_the_one_before_it(self):
        """The property the log is FOR: read it back and the links are a single line."""
        s = MemoryStore()
        for i in range(20): s.audit('task', i, 'step', 'owner')
        rows = s._rows('SELECT * FROM audit ORDER BY Id')
        self.assertEqual(rows[0]['PrevHash'], GENESIS)
        for a, b in zip(rows, rows[1:]):
            self.assertEqual(b['PrevHash'], a['RowHash'])
        self.assertEqual(len({r['PrevHash'] for r in rows}), len(rows))   # no shared parent


class ItTellsTheTwoFailuresApartTests(unittest.TestCase):
    """Calling both "broken" is what cried wolf about a bug in store.py."""
    def _store(self, n=6):
        s = MemoryStore()
        for i in range(n): s.audit('task', i, 'step', 'owner')
        return s

    def test_an_edited_row_is_reported_as_ALTERED(self):
        s = self._store()
        s._exec("UPDATE audit SET Actor='somebody-else' WHERE Id=3")
        out = s.verify_audit_chain()
        self.assertEqual(out['altered_ids'], [3])       # its own hash no longer fits its contents
        self.assertFalse(out['ok'])

    def test_a_raced_row_is_reported_as_FORKED_and_not_as_tampering(self):
        s = self._store()
        # exactly what the race produced: a row whose hash is honest about its own contents, but
        # whose parent is the row before its predecessor
        two = s._one('SELECT * FROM audit WHERE Id=2')
        four = s._one('SELECT * FROM audit WHERE Id=4')
        payload = _audit_payload(four['EntityType'], four['EntityId'], four['Action'], four['Actor'],
                                 four['ActorType'], four['RunId'], four['Detail'])
        s._exec('UPDATE audit SET PrevHash=?, RowHash=? WHERE Id=4',
                (two['PrevHash'], chain_hash(two['PrevHash'], payload)))
        out = s.verify_audit_chain()
        self.assertEqual(out['altered_ids'], [], 'a write race must not be reported as tampering')
        self.assertIn(4, out['forked_ids'])

    def test_a_clean_chain_says_so(self):
        out = self._store().verify_audit_chain()
        self.assertTrue(out['ok'])
        self.assertEqual((out['altered_ids'], out['forked_ids']), ([], []))

    def test_the_old_field_still_lists_everything_that_failed(self):
        """Anything reading broken_ids keeps working."""
        s = self._store()
        s._exec("UPDATE audit SET Action='edited' WHERE Id=2")
        out = s.verify_audit_chain()
        self.assertEqual(out['broken_ids'], sorted(out['altered_ids'] + out['forked_ids']))
        self.assertIn(2, out['broken_ids'])


if __name__ == '__main__':
    unittest.main()
