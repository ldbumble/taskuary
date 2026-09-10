"""A per-item history read must not rescan the complete migration archive."""
from taskuary.store import MemoryStore, SQLiteStore
from taskuary import processing_all
import sqlite3


def test_canonical_history_lookups_do_not_scan_unrelated_items():
    store = MemoryStore()
    try:
        for table, clause, params in (
            ('processing_legacy_evidence', 'ItemId=? ORDER BY EvidenceId', ('absent',)),
            ('processing_legacy_evidence', 'EntityKind=? AND LocalId=? ORDER BY EvidenceId', ('message', 'absent')),
            ('processing_context_snapshot', 'ItemId=? ORDER BY MigrationVersion,ItemId', ('absent',)),
        ):
            plan = [row[3] for row in store.cx.execute('EXPLAIN QUERY PLAN SELECT * FROM '+table+' WHERE '+clause, params)]
            assert any('SEARCH '+table in step for step in plan), plan
            assert not any('SCAN '+table in step for step in plan), plan
    finally:
        store.cx.close()


def test_runtime_cache_keeps_inventory_and_detects_local_and_external_changes(tmp_path):
    path = tmp_path / 'cache.db'
    store = SQLiteStore(str(path))
    try:
        mid = store.add_message({'Channel': 'email', 'ExternalId': 'cache-fixture',
            'Subject': 'Original source', 'BodyText': 'Original body', 'Status': 'filed'})
        store.reconcile_processing_membership()
        now = '2026-09-06 18:00:00'
        full = store.processing_inventory_snapshot(fixed_now=now, live_state=[])
        lean = store.processing_inventory_snapshot(fixed_now=now, live_state=[], include_history=False)
        query = processing_all.normalize_query(days=36500)
        assert processing_all.compact_inventory(full, query) == processing_all.compact_inventory(lean, query)
        assert 'context_history' in full['items'][0] and 'context_history' not in lean['items'][0]
        statements = []
        store.cx.set_trace_callback(statements.append)
        cached = store.processing_inventory_snapshot(fixed_now=now, live_state=[], include_history=False)
        store.cx.set_trace_callback(None)
        assert cached == lean
        assert not any('FROM message' in sql or 'FROM processing_member' in sql for sql in statements)
        cached['items'][0]['view']['messages'][0]['BodyText'] = 'caller mutation'
        assert store.processing_inventory_snapshot(fixed_now=now, live_state=[], include_history=False) == lean
        later = store.processing_inventory_snapshot(fixed_now='2026-09-07 18:00:00', live_state=[], include_history=False)
        assert later['as_of'] != lean['as_of'] and later['snapshot_revision'] != lean['snapshot_revision']
        store._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('Local change', mid))
        local = store.processing_inventory_snapshot(fixed_now=now, live_state=[], include_history=False)
        assert local['items'][0]['context_revision'] != lean['items'][0]['context_revision']
        peer = sqlite3.connect(path)
        try:
            peer.execute('UPDATE message SET BodyText=? WHERE MessageId=?', ('External change', mid))
            peer.commit()
        finally:
            peer.close()
        external = store.processing_inventory_snapshot(fixed_now=now, live_state=[], include_history=False)
        assert external['items'][0]['context_revision'] != local['items'][0]['context_revision']
    finally:
        store.cx.close()
