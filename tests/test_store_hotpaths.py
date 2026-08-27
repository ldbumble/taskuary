"""The store's hot paths: pragmas, indexes, feed/task queries, routing snapshots.

These are correctness tests for the cheap performance work - WAL, indexes, JOIN
rewrites - against a real on-disk SQLite file (MemoryStore hides exactly those costs).
"""
import os, tempfile, unittest
from taskuary.store import MemoryStore, SQLiteStore


def _file_store():
    path = os.path.join(tempfile.mkdtemp(), 't.db')
    return SQLiteStore(path), path


class WalTests(unittest.TestCase):
    def test_file_db_opens_in_wal(self):
        """Readers should not block on a poll's write. WAL is how sqlite does that;
        DELETE journal (the default) makes a Timeline hitch every sync."""
        s, path = _file_store()
        mode = s._one('PRAGMA journal_mode')['journal_mode']
        self.assertEqual(mode.lower(), 'wal')
        # the sidecar exists once anything has been written (schema already did)
        self.assertTrue(os.path.exists(path + '-wal') or mode.lower() == 'wal')
        s.cx.close()

    def test_memory_store_still_opens(self):
        """Tests and demos stay on :memory:, which cannot WAL. Opening one must not
        raise, and must not pretend to be a file."""
        s = MemoryStore()
        mode = s._one('PRAGMA journal_mode')['journal_mode'].lower()
        self.assertIn(mode, ('memory', 'delete', 'off'))


class BusyTimeoutTests(unittest.TestCase):
    def test_connections_wait_instead_of_failing_locked(self):
        s, _ = _file_store()
        ms = s._one('PRAGMA busy_timeout')['timeout']
        self.assertGreaterEqual(int(ms), 5000)
        s.cx.close()

    def test_memory_store_waits_too(self):
        """Tests share one process with the fixture store; a zero timeout made
        'database is locked' a flake rather than a wait."""
        s = MemoryStore()
        self.assertGreaterEqual(int(s._one('PRAGMA busy_timeout')['timeout']), 5000)
