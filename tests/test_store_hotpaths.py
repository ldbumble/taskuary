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


def _index_names(s):
    return {r['name'] for r in s._rows("SELECT name FROM sqlite_master WHERE type='index'")}


def _plan(s, sql, params=()):
    return ' '.join(r['detail'] for r in s._rows('EXPLAIN QUERY PLAN ' + sql, params)).lower()


class ExternalIdIndexTests(unittest.TestCase):
    def test_index_exists_on_a_fresh_and_a_reopened_db(self):
        s, path = _file_store()
        self.assertIn('idx_message_external', _index_names(s))
        s.cx.close()
        s2 = SQLiteStore(path)
        self.assertIn('idx_message_external', _index_names(s2))
        s2.cx.close()

    def test_dedupe_lookup_uses_the_index(self):
        """ingest_message's first line is message_exists(external_id). Without an
        index that is a full scan of every mail ever stored."""
        s, _ = _file_store()
        s.add_message({'ExternalId': 'ext-1', 'Channel': 'email', 'Status': 'filed'})
        plan = _plan(s, 'SELECT 1 x FROM message WHERE ExternalId=?', ('ext-1',))
        self.assertIn('idx_message_external', plan)
        self.assertTrue(s.message_exists('ext-1'))
        self.assertFalse(s.message_exists('no-such'))
        s.cx.close()

    def test_heals_a_db_that_was_created_before_the_index(self):
        s, path = _file_store()
        s._exec('DROP INDEX idx_message_external')
        self.assertNotIn('idx_message_external', _index_names(s))
        s.cx.close()
        s2 = SQLiteStore(path)
        self.assertIn('idx_message_external', _index_names(s2))
        s2.cx.close()


class ThreadIndexTests(unittest.TestCase):
    def test_thread_lookup_uses_the_conversation_index(self):
        s, _ = _file_store()
        s.add_message({'ExternalId': 't1', 'ConversationId': 'c-1', 'Channel': 'email',
                       'SentAt': '2026-08-20 10:00:00', 'Status': 'filed'})
        plan = _plan(s, 'SELECT * FROM message WHERE ConversationId=? ORDER BY SentAt DESC LIMIT 40', ('c-1',))
        self.assertIn('idx_message_conversation', plan)
        self.assertEqual(len(s.thread_messages('c-1')), 1)
        s.cx.close()

    def test_pending_triage_and_task_messages_use_indexes(self):
        s, _ = _file_store()
        tid = s.create_task({'Title': 'x'}, 't')
        s.add_message({'ExternalId': 'p1', 'TaskId': tid, 'Channel': 'email', 'Status': 'triaging'})
        self.assertIn('idx_message_status', _plan(s, "SELECT * FROM message WHERE Status='triaging'"))
        self.assertIn('idx_message_task', _plan(s, 'SELECT * FROM message WHERE TaskId=?', (tid,)))
        self.assertEqual(len(s.pending_triage()), 1)
        self.assertEqual(len(s.list_messages(tid)), 1)
        s.cx.close()
