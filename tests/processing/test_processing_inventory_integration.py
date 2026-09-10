"""Inventory seams: frozen SQLite reads, revision-bound pages and truthful coverage."""
import json
import copy

import pytest

from taskuary import processing_projection
from taskuary.processing_inventory import processing_inventory_page
from taskuary.store import SQLiteStore


NOW = '2026-09-06T12:00:00Z'


def seed(path):
    db = SQLiteStore(str(path))
    tid = db.create_task({'Title': 'Synthetic inventory task', 'Priority': 'normal'}, 'fixture')
    mid = db.add_message({'TaskId': tid, 'Channel': 'email', 'SentAt': '2020-01-01T08:00:00Z',
                          'BodyText': 'Old provider timestamp, complete synthetic body.'})
    other = db.add_message({'Channel': 'report', 'SentAt': '2026-09-06T10:00:00Z',
                            'BodyText': 'Independent synthetic report.'})
    rid = db.add_review({'MessageId': mid, 'TaskId': tid, 'Status': 'pending',
                         'Kind': 'reply', 'DraftText': 'Original draft'})
    db.backfill_processing('inventory-seam-v1', fixed_now='2026-09-06 12:00:00')
    return db, tid, mid, other, rid


def item_for(snapshot, member):
    return next(item for item in snapshot['items'] if member in item['member_ids'])


def test_external_merge_between_enumeration_and_projection_is_one_snapshot(tmp_path, monkeypatch):
    path = tmp_path / 'inventory-wal.db'
    db, _, mid, other, _ = seed(path)
    writer = SQLiteStore(str(path))
    try:
        initial = db.processing_inventory_snapshot(fixed_now=NOW, live_state=[])
        source = item_for(initial, f'message:{other}')['item_id']
        target = item_for(initial, f'message:{mid}')['item_id']
        original = processing_projection.processing_projection
        merged = False

        def merge_before_projection(cur, item_id, **kwargs):
            nonlocal merged
            if not merged:
                merged = True
                writer.merge_processing_items(source, target, fixed_now=NOW)
            return original(cur, item_id, **kwargs)

        monkeypatch.setattr(processing_projection, 'processing_projection', merge_before_projection)
        during = db.processing_inventory_snapshot(fixed_now=NOW, live_state=[])
        assert merged
        assert during == initial
        assert not db.cx.in_transaction
        after = db.processing_inventory_snapshot(fixed_now=NOW, live_state=[])
        assert after['snapshot_revision'] != initial['snapshot_revision']
        assert source not in {item['item_id'] for item in after['items']}
        assert item_for(after, f'message:{other}')['item_id'] == target
    finally:
        writer.cx.close()
        db.cx.close()


def test_failed_projection_closes_read_transaction_without_partial_inventory(tmp_path, monkeypatch):
    db, _, _, _, _ = seed(tmp_path / 'failed-inventory.db')
    try:
        before = db.processing_inventory_snapshot(fixed_now=NOW)
        changes = db.cx.total_changes
        original = processing_projection.processing_projection
        calls = 0

        def fail_second(cur, item_id, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('synthetic unavailable context')
            return original(cur, item_id, **kwargs)

        monkeypatch.setattr(processing_projection, 'processing_projection', fail_second)
        with pytest.raises(RuntimeError, match='synthetic unavailable context'):
            db.processing_inventory_snapshot(fixed_now=NOW)
        assert calls == 2
        assert not db.cx.in_transaction
        assert db.cx.total_changes == changes
        monkeypatch.setattr(processing_projection, 'processing_projection', original)
        assert db.processing_inventory_snapshot(fixed_now=NOW) == before
    finally:
        db.cx.close()


@pytest.mark.parametrize('change', ['body', 'draft', 'read', 'priority', 'member', 'worker'])
def test_in_place_changes_invalidate_snapshot_cursor_without_identity_churn(tmp_path, change):
    db, tid, mid, _, rid = seed(tmp_path / f'{change}.db')
    workers = [{'taskId': tid, 'waiting': False, 'tail': ['Synthetic working state']}]
    try:
        before = db.processing_inventory_snapshot(fixed_now=NOW, live_state=workers)
        frozen = json.dumps(before, sort_keys=True)
        page = processing_inventory_page(before, limit=1)
        assert page['next_cursor']
        original = item_for(before, f'message:{mid}')
        if change == 'body':
            db.update_message_body(mid, 'Changed full synthetic body beyond any UI preview.')
        elif change == 'draft':
            db._exec('UPDATE review SET DraftText=? WHERE ReviewId=?', ('Edited draft', rid))
        elif change == 'read':
            db.set_funnel_state(f'msg:{mid}', 'done')
        elif change == 'priority':
            db.update_task(tid, {'Priority': 'high'}, 'fixture')
        elif change == 'member':
            added = db.add_message({'TaskId': tid, 'Channel': 'email', 'BodyText': 'New member'})
            db.reconcile_processing_entities(kind=original['item']['Kind'],
                members=[{'entity_kind': 'message', 'local_id': added}], item_id=original['item_id'])
        else:
            workers[0]['waiting'] = True
            workers[0]['tail'].append('Synthetic question for owner')
        after = db.processing_inventory_snapshot(fixed_now=NOW, live_state=workers)
        current = item_for(after, f'message:{mid}')
        assert current['item_id'] == original['item_id']
        assert after['snapshot_revision'] != before['snapshot_revision']
        assert current['view_revision'] != original['view_revision']
        if change not in ('body', 'member'):
            assert current['context_revision'] == original['context_revision']
        else:
            assert current['context_revision'] != original['context_revision']
        assert json.dumps(before, sort_keys=True) == frozen
        with pytest.raises(ValueError):
            processing_inventory_page(after, limit=1, cursor=page['next_cursor'])
        # An old immutable snapshot remains internally pageable, never blended with new rows.
        assert processing_inventory_page(before, limit=1, cursor=page['next_cursor'])['items']
    finally:
        db.cx.close()


def test_uncatalogued_arrival_changes_coverage_without_getter_backfill(tmp_path):
    db, _, mid, _, _ = seed(tmp_path / 'coverage.db')
    try:
        before = db.processing_inventory_snapshot(fixed_now=NOW)
        late = db.add_message({'Channel': 'email', 'SentAt': '2001-01-01T00:00:00Z',
                               'BodyText': 'Old source date, newly persisted arrival.'})
        writes = db._writes
        changes = db.cx.total_changes
        after = db.processing_inventory_snapshot(fixed_now=NOW)
        assert db._writes == writes
        assert db.cx.total_changes == changes
        assert after['coverage']['uncatalogued']['message'] == before['coverage']['uncatalogued']['message'] + 1
        assert after['snapshot_revision'] != before['snapshot_revision']
        assert item_for(after, f'message:{mid}')
        assert not any(f'message:{late}' in item['member_ids'] for item in after['items'])
        assert db.resolve_processing_target('legacy_funnel', f'msg:{late}') is None
        assert 'calendar' in after['coverage']['unsupported']
    finally:
        db.cx.close()


def test_page_facts_are_revision_bound_and_cannot_change_mid_walk(tmp_path):
    db, tid, mid, _, _ = seed(tmp_path / 'ranking-facts.db')
    try:
        snapshot = db.processing_inventory_snapshot(fixed_now=NOW, live_state=[])
        item = item_for(snapshot, f'message:{mid}')
        facts = {item['item_id']: {
            'view_revision': item['view_revision'],
            'attention': {'signals': [
                {'kind': 'owner_input', 'provenance': 'synthetic request snapshot'},
                {'kind': 'working', 'provenance': 'synthetic prior working fact'},
            ]},
        }}
        page = processing_inventory_page(snapshot, order='priority', limit=1, facts=facts)
        assert page['items'][0]['item_id'] == item['item_id']
        assert page['items'][0]['inventory_facts']['attention']['band'] == 2
        assert page['next_cursor']
        changed = copy.deepcopy(facts)
        changed[item['item_id']]['attention']['signals'] = [
            {'kind': 'working', 'provenance': 'synthetic resumed request snapshot'}]
        with pytest.raises(ValueError):
            processing_inventory_page(snapshot, order='priority', limit=1,
                                      facts=changed, cursor=page['next_cursor'])
        with pytest.raises(ValueError):
            processing_inventory_page(snapshot, order='all', limit=1,
                                      facts=facts, cursor=page['next_cursor'])
        db.update_task(tid, {'Priority': 'urgent'}, 'fixture')
        fresh = db.processing_inventory_snapshot(fixed_now=NOW, live_state=[])
        with pytest.raises(ValueError):
            processing_inventory_page(fresh, order='priority', facts=facts)
        assert facts[item['item_id']]['view_revision'] == item['view_revision']
    finally:
        db.cx.close()


def test_wrapper_and_two_ideas_stay_independently_enumerated_with_exact_relations(tmp_path):
    db = SQLiteStore(str(tmp_path / 'wrapper-inventory.db'))
    try:
        mid = db.add_message({'Channel': 'assistant', 'SentAt': NOW,
                              'BodyText': 'Two independent synthetic suggestions.'})
        ideas = [db.upsert_idea({'key': f'fixture-inventory-{n}', 'text': f'Idea {n}'},
                               '2026-09-06 12:00:00')['IdeaId'] for n in range(2)]
        db.set_ideas_message(ideas, mid)
        db.set_brief(mid, json.dumps({'ideas': [{'id': iid} for iid in ideas]}))
        db.backfill_processing('wrapper-inventory-v1', fixed_now='2026-09-06 12:00:00')
        snapshot = db.processing_inventory_snapshot(fixed_now=NOW)
        wrapper = item_for(snapshot, f'message:{mid}')
        suggestion_items = [item_for(snapshot, f'idea:{iid}') for iid in ideas]
        assert len({wrapper['item_id'], *(item['item_id'] for item in suggestion_items)}) == 3
        assert {f'idea:{iid}' for iid in ideas} <= set(wrapper['related_entity_ids'])
        assert snapshot['coverage']['uncatalogued']['idea'] == 0
        page = processing_inventory_page(snapshot)
        assert {item['item_id'] for item in page['items']} == {item['item_id'] for item in snapshot['items']}
        for item in page['items']:
            assert item['inventory_facts']['read_state'] == {'state': 'unknown'}
            assert item['inventory_facts']['actionability'] == {'state': 'unknown'}
        assert db.processing_legacy_evidence('wrapper-inventory-v1')
    finally:
        db.cx.close()
