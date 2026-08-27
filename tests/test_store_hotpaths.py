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


class TimelineIndexTests(unittest.TestCase):
    def test_feed_order_and_window_use_time_indexes(self):
        s, _ = _file_store()
        s.add_message({'ExternalId': 'f1', 'Channel': 'email', 'FromEmail': 'a@b.com',
                       'SentAt': '2026-08-20 10:00:00', 'Status': 'filed'})
        self.assertIn('idx_message_sent', _plan(s, 'SELECT * FROM message ORDER BY SentAt DESC, MessageId DESC LIMIT 100'))
        self.assertIn('idx_message_created', _plan(s, "SELECT * FROM message WHERE CreatedAt >= datetime('now', 'localtime', '-14 days')"))
        s.cx.close()

    def test_known_sender_uses_the_from_index(self):
        s, _ = _file_store()
        s.add_message({'ExternalId': 's1', 'Channel': 'email', 'FromEmail': 'pat@corp.example', 'Status': 'filed'})
        plan = _plan(s, 'SELECT 1 x FROM message WHERE FromEmail=? LIMIT 1', ('pat@corp.example',))
        self.assertIn('idx_message_from', plan)
        self.assertTrue(s.known_sender('pat@corp.example'))
        self.assertFalse(s.known_sender('nobody@corp.example'))
        s.cx.close()


class RelatedIndexTests(unittest.TestCase):
    """feed() and list_tasks() look up the latest route/review/run per row. Without
    these indexes each Timeline load is N times a table scan."""

    def test_indexes_exist(self):
        s, _ = _file_store()
        names = _index_names(s)
        for ix in ('idx_route_message', 'idx_review_message', 'idx_review_task',
                   'idx_run_task', 'idx_attachment_message', 'idx_comment_task',
                   'idx_audit_entity', 'idx_dispatchq_task', 'idx_waitroom_task'):
            self.assertIn(ix, names, ix)
        s.cx.close()

    def test_latest_route_and_review_lookups_use_them(self):
        s, _ = _file_store()
        mid = s.add_message({'ExternalId': 'r1', 'Channel': 'email', 'Status': 'filed'})
        s.add_route(mid, None, 'file', None, 'fyi', [], 'triage')
        tid = s.create_task({'Title': 't'}, 't')
        s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending'})
        s.start_run(tid, 'coder', 'go', 't')
        s.add_attachment({'MessageId': mid, 'Name': 'a.png', 'ContentType': 'image/png'})
        self.assertIn('idx_route_message', _plan(s, 'SELECT * FROM route WHERE MessageId=?', (mid,)))
        self.assertIn('idx_review_message', _plan(s, 'SELECT * FROM review WHERE MessageId=?', (mid,)))
        self.assertIn('idx_run_task', _plan(s, "SELECT * FROM run WHERE TaskId=? AND Status='running'", (tid,)))
        self.assertIn('idx_attachment_message', _plan(s, 'SELECT * FROM attachment WHERE MessageId=?', (mid,)))
        row = s.feed(limit=5)[0]
        self.assertEqual(row['Decision'], 'file')
        self.assertEqual(row['ReviewStatus'], 'pending')
        self.assertEqual(row['Attachments'], 1)
        s.cx.close()


class SnapshotJoinTests(unittest.TestCase):
    def test_one_row_per_open_task_including_ones_with_no_mail(self):
        s = MemoryStore()
        empty = s.create_task({'Title': 'typed in by hand'}, 't')
        mailed = s.create_task({'Title': 'from mail'}, 't')
        s.create_task({'Title': 'finished', 'Status': 'done'}, 't')
        s.add_message({'TaskId': mailed, 'Channel': 'email', 'Subject': 'PTO file',
                       'FromEmail': 'gw@corp.example', 'ConversationId': 'c-pto',
                       'BodyText': 'Do you have the July file?', 'Status': 'routed'})
        by = {x['task_id']: x for x in s.snapshots()}
        self.assertEqual(set(by), {empty, mailed})
        self.assertEqual(by[empty]['text'], 'typed in by hand')
        self.assertEqual(by[empty]['subjects'], [])
        self.assertEqual(by[mailed]['subjects'], ['PTO file'])
        self.assertEqual(by[mailed]['senders'], ['gw@corp.example'])
        self.assertEqual(by[mailed]['conversation_ids'], ['c-pto'])
        self.assertIn('Do you have the July file?', by[mailed]['text'])
        self.assertTrue(by[mailed]['text'].startswith('from mail'))

    def test_a_follow_up_still_attaches_to_the_open_task(self):
        """The JOIN must not drop conversation_ids or routing would open a second task."""
        from taskuary.ingest import ingest_message
        llm = lambda sys, usr: '{"intent": "task", "why": "t"}'
        s = MemoryStore()
        a = ingest_message(s, {'external_id': 'm1', 'channel': 'api', 'subject': 's',
                               'body': 'please add the new user to the system',
                               'from_email': 'a@b.com', 'conversation_id': 'c1'}, llm=llm)
        b = ingest_message(s, {'external_id': 'm2', 'channel': 'api', 'subject': 's',
                               'body': 'and one more thing', 'from_email': 'a@b.com',
                               'conversation_id': 'c1'}, llm=llm)
        self.assertEqual((b['status'], b['task_id']), ('attached', a['task_id']))


class SnapshotFreezeTests(unittest.TestCase):
    FYI = {'channel': 'api', 'subject': 'notice', 'body': 'this is an automated summary, no action needed'}

    def test_filed_mail_reuses_the_frozen_snapshot(self):
        """A catch-up of newsletters does not change the open-task picture, so rebuild once."""
        from taskuary.ingest import ingest_message
        s = MemoryStore()
        n = {'n': 0}
        real = s._load_snapshots
        s._load_snapshots = lambda: n.__setitem__('n', n['n'] + 1) or real()
        with s.freeze_snapshots():
            ingest_message(s, {**self.FYI, 'external_id': 'f1'})
            ingest_message(s, {**self.FYI, 'external_id': 'f2'})
        self.assertEqual(n['n'], 1)

    def test_opening_a_task_drops_the_cache_so_the_next_on_the_thread_attaches(self):
        from taskuary.ingest import ingest_message, drain, deferred
        llm = lambda sys, usr: '{"intent": "task", "why": "t"}'
        s = MemoryStore()
        with deferred():
            ingest_message(s, {'external_id': 'd1', 'channel': 'api', 'subject': 's',
                               'body': 'please add the new user to the system',
                               'from_email': 'a@b.com', 'conversation_id': 'c-drain'}, llm=llm)
            ingest_message(s, {'external_id': 'd2', 'channel': 'api', 'subject': 's',
                               'body': 'and one more thing', 'from_email': 'a@b.com',
                               'conversation_id': 'c-drain'}, llm=llm)
        self.assertEqual(len(s.pending_triage()), 2)
        drain(s, llm=llm)
        tasks = s.list_tasks()
        self.assertEqual(len(tasks), 1)
        self.assertEqual(len(s.list_messages(tasks[0]['TaskId'])), 2)
