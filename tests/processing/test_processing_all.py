import copy
import json
from datetime import datetime, timedelta
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import processing_all, server
from taskuary.store import SQLiteStore


NOW = '2026-09-06 12:00:00'


def _snapshot(count=507):
    items = []
    for i in range(count):
        mid = i + 1
        stamp = (datetime.fromisoformat(NOW) - timedelta(seconds=i)).isoformat(' ')
        message = {'MessageId': mid, 'TaskId': None, 'Channel': 'email', 'SourceName': 'fixture@example.test',
                   'Subject': f'Item {mid}', 'SentAt': stamp, 'CreatedAt': NOW,
                   'Status': 'filed', 'BodyText': 'source body ' + 'x' * 5000 + ' FULL BODY SENTINEL'}
        items.append({'item_id': f'item-{mid:04}', 'member_ids': [f'message:{mid}'],
                      'context_revision': f'context-{mid}', 'view_revision': f'view-{mid}',
                      'view': {'messages': [message], 'tasks': [], 'reviews': [], 'routes': [], 'settings': {}}})
    return {'as_of': NOW, 'snapshot_revision': 'snapshot-original', 'items': items,
            'coverage': {'canonical_item_count': count, 'uncatalogued': {'message': 0, 'task': 0, 'review': 0, 'idea': 0},
                         'processing_reconciliation': {'pending': False, 'status': 'complete'}}}


class _SnapshotStore:
    def __init__(self, snapshot):
        self.snapshot, self.captures = snapshot, 0

    def processing_inventory_snapshot(self, **_kwargs):
        self.captures += 1
        return copy.deepcopy(self.snapshot)


def test_pages_are_compact_frozen_and_complete_across_507_roots_and_arrivals():
    store = _SnapshotStore(_snapshot())
    service = processing_all.AllInventory()
    first = service.page(store, limit=100)
    ids = [r['item_id'] for r in first['items']]
    assert first['counts']['total'] == 507
    assert 'FULL BODY SENTINEL' not in json.dumps(first)
    assert 'BodyText' not in json.dumps(service._stores[store])
    first['items'][0]['row']['Subject'] = 'caller mutation'
    store.snapshot = _snapshot(508)
    store.snapshot['snapshot_revision'] = 'snapshot-new'
    cursor = first['next_cursor']
    while cursor:
        page = service.page(store, cursor=cursor, limit=100)
        assert page['snapshot_revision'] == 'snapshot-original'
        ids.extend(r['item_id'] for r in page['items'])
        cursor = page['next_cursor']
    assert ids == [f'item-{i:04}' for i in range(1, 508)]
    assert store.captures == 1
    fresh = service.page(store)
    assert fresh['counts']['total'] == 508
    assert fresh['items'][0]['row']['Subject'] == 'Item 1'


def test_expiry_query_binding_tampering_and_store_isolation():
    clock = [0.0]
    service = processing_all.AllInventory(ttl=10, max_leases=1, clock=lambda: clock[0])
    store = _SnapshotStore(_snapshot(3))
    first = service.page(store, limit=1, channel='email')
    for changes in ({'source': 'another'}, {'days': 15}, {'channel': 'own'}):
        with pytest.raises(processing_all.AllError) as caught:
            service.page(store, cursor=first['next_cursor'], **{'channel': 'email', **changes})
        assert caught.value.status == 422
    with pytest.raises(processing_all.AllError) as caught:
        service.page(_SnapshotStore(_snapshot(3)), cursor=first['next_cursor'], channel='email')
    assert caught.value.detail['code'] == 'processing_snapshot_expired'
    clock[0] = 10
    with pytest.raises(processing_all.AllError) as caught:
        service.page(store, cursor=first['next_cursor'], channel='email')
    assert caught.value.detail['code'] == 'processing_snapshot_expired'
    for malformed in ('not-base64!', 'W10', 'e30'):
        with pytest.raises(processing_all.AllError) as caught:
            service.page(store, cursor=malformed)
        assert caught.value.status == 422


def test_unready_coverage_never_claims_empty_and_unknown_dates_are_not_silently_dropped():
    snapshot = _snapshot(2)
    snapshot['coverage']['processing_reconciliation']['pending'] = True
    with pytest.raises(processing_all.AllError) as caught:
        processing_all.AllInventory().page(_SnapshotStore(snapshot))
    assert caught.value.detail['code'] == 'processing_coverage_pending'
    snapshot['coverage']['processing_reconciliation']['pending'] = False
    snapshot['items'][0]['view']['messages'][0].update(SentAt='unknown', CreatedAt='unknown')
    page = processing_all.AllInventory().page(_SnapshotStore(snapshot))
    assert page['counts']['total'] == 2
    assert page['items'][-1]['item_id'] == 'item-0001'
    assert page['items'][-1]['activity_basis'] == 'unknown'


def _message(store, text, *, task=None, source='a@example.test', status='routed', sent=NOW):
    mid = store.add_message({'TaskId': task, 'ExternalId': f'fixture:{text}', 'Channel': 'email',
                             'SourceName': source, 'Subject': text, 'BodyText': text + ' FULL SOURCE',
                             'SentAt': sent, 'Status': status})
    store._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (NOW, mid))
    return mid


def test_real_all_filters_roots_by_matching_member_and_binds_draft_detail(tmp_path):
    store = SQLiteStore(str(tmp_path / 'all.db'))
    try:
        tid = store.create_task({'Title': 'Shared work', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
        older = _message(store, 'Older member', task=tid, sent='2025-01-01 00:00:00')
        latest = _message(store, 'Latest member', task=tid, source='b@example.test')
        r1 = store.add_review({'TaskId': tid, 'MessageId': older, 'Kind': 'draft_reply',
                               'Status': 'pending', 'DraftText': 'EXACT OLDER DRAFT'})
        store.add_review({'TaskId': tid, 'MessageId': latest, 'Kind': 'draft_reply',
                          'Status': 'pending', 'DraftText': 'DO NOT SEND SIBLING DRAFT'})
        store.reconcile_processing_membership(fixed_now=NOW)
        service = processing_all.AllInventory()
        all_page = service.page(store, fixed_now=NOW)
        assert all_page['counts']['total'] == 1
        selected = service.page(store, source='a@example.test', fixed_now=NOW)['items'][0]
        assert selected['item_id'] == all_page['items'][0]['item_id']
        assert selected['open_target'] == {'kind': 'message', 'id': older}
        assert selected['counts']['messages'] == 2
        detail = processing_all.item_detail(store, selected['item_id'], kind='message', local_id=older)
        assert detail['row']['BodyText'] == 'Older member FULL SOURCE'
        assert detail['row']['ReviewId'] == r1
        assert [r['DraftText'] for r in detail['detail']['reviews']] == ['EXACT OLDER DRAFT']
        assert 'DO NOT SEND SIBLING DRAFT' not in json.dumps(detail)
    finally:
        store.cx.close()


def test_real_generic_roots_hidden_history_tombstones_and_detail_gets_are_readonly(tmp_path):
    store = SQLiteStore(str(tmp_path / 'generic.db'))
    try:
        store.set_setting('feed_days', '36500', 'fixture')
        task = store.create_task({'Title': 'Manual task', 'Summary': 'Full manual summary', 'Status': 'open'}, 'fixture')
        store.set_task_checklist(task, ['Keep this box'], 'fixture')
        store.add_comment(task, 'fixture', 'user', 'Retain exact history')
        idea = store.upsert_idea({'key': 'fixture:idea', 'kind': 'followup', 'text': 'Full independent idea'}, NOW)
        review = store.add_review({'Kind': 'action', 'Status': 'pending', 'Reason': 'Full independent review'})
        for status in ('history', 'context', 'skipped'):
            _message(store, status, status=status)
        old = _message(store, 'Owner read', status='filed')
        store.set_funnel_state(f'msg:{old}', 'done', note='Explicit old read')
        store.save_doc('counsel', 'Exact owner custom document', 'owner')
        store.reconcile_processing_membership(fixed_now=NOW)
        writes, changes = store._writes, store.cx.total_changes
        states = store.funnel_states()
        with mock.patch.object(server, 'store', store), mock.patch.object(server, '_processing_live', return_value=[]):
            client = TestClient(server.app)
            page = client.get('/api/processing/all').json()
            kinds = {item['open_target']['kind'] for item in page['items']}
            assert kinds == {'message', 'task', 'idea', 'review'}
            assert page['counts']['total'] == 4
            for item in page['items']:
                target = item['open_target']
                response = client.get(f"/api/processing/items/{item['item_id']}/detail", params={
                    'kind': target['kind'], 'id': target['id'], 'view_revision': item['view_revision']})
                assert response.status_code == 200
                if target['kind'] == 'idea':
                    assert response.json()['detail']['body'] == 'Full independent idea'
                if target['kind'] == 'review':
                    assert response.json()['detail']['body'] == 'Full independent review'
                if target['kind'] == 'task':
                    assert response.json()['detail']['history'][0]['text'] == 'Retain exact history'
        assert store._writes == writes
        assert store.cx.total_changes == changes
        assert store.funnel_states() == states
        assert store.doc('counsel') == 'Exact owner custom document'
        assert idea['IdeaId'] and review
    finally:
        store.cx.close()


def test_detail_rejects_member_moved_to_another_task(tmp_path):
    store = SQLiteStore(str(tmp_path / 'move.db'))
    try:
        one = store.create_task({'Title': 'First', 'Status': 'open'}, 'fixture')
        two = store.create_task({'Title': 'Second', 'Status': 'open'}, 'fixture')
        mid = _message(store, 'Moving member', task=one)
        store.reconcile_processing_membership(fixed_now=NOW)
        initial = processing_all.AllInventory().page(store, fixed_now=NOW)
        item = next(row for row in initial['items'] if f'message:{mid}' in row['member_ids'])
        store._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (two, mid))
        store.reconcile_processing_membership(fixed_now=NOW)
        with pytest.raises(processing_all.AllError) as caught:
            processing_all.item_detail(store, item['item_id'], kind='message', local_id=mid)
        assert caught.value.detail['code'] == 'processing_target_moved'
    finally:
        store.cx.close()


def test_fixture_seeds_complete_real_census_and_frozen_arrival_without_notifications(tmp_path, monkeypatch):
    import importlib.util
    from pathlib import Path
    from fastapi import FastAPI
    from taskuary import calendar, live

    monkeypatch.setenv('TASKUARY_DEMO', '1')
    monkeypatch.setenv('TASKUARY_HOME', str(tmp_path))
    # Fixture installs a deterministic calendar only in its owned process.
    monkeypatch.setattr(calendar, 'today', calendar.today)
    spec = importlib.util.spec_from_file_location('canonical_fixture_test',
        Path(__file__).resolve().parents[2] / 'website/browser/fixture_canonical.py')
    fixture = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(fixture)
    store = SQLiteStore(str(tmp_path / 'census.db'))
    try:
        app = FastAPI()
        fixture.install_canonical_changes(app, store)
        client = TestClient(app)
        with mock.patch.object(live, 'emit') as emit:
            response = client.post('/api/fixture/processing/canonical-all', json={'count': 507})
            assert response.status_code == 200, response.text
            seeded = response.json()
            assert seeded['total'] == 507
            service = processing_all.AllInventory()
            page = service.page(store, limit=100)
            ids = [i['item_id'] for i in page['items']]
            early = {seeded['grouped']['item_id'], seeded['ignored_item_id'], seeded['muted_item_id'],
                     *(i['item_id'] for i in seeded['standalone'].values())}
            assert early <= set(ids)
            arrival = client.post('/api/fixture/processing/canonical-arrival', json={'emit': False}).json()
            while page['next_cursor']:
                page = service.page(store, limit=100, cursor=page['next_cursor'])
                ids.extend(i['item_id'] for i in page['items'])
            assert len(ids) == len(set(ids)) == 507
            assert arrival['item_id'] not in ids
            assert service.page(store)['counts']['total'] == 508
            emit.assert_not_called()
            assert client.post('/api/fixture/processing/canonical-emit').status_code == 200
            emit.assert_called_once_with('feed-changed')
    finally:
        store.cx.close()


def test_standalone_review_detail_preserves_owner_final_text(tmp_path):
    store = SQLiteStore(str(tmp_path / 'final-review.db'))
    try:
        rid = store.add_review({'Kind': 'draft_reply', 'Status': 'edited',
                                'DraftText': 'Superseded machine draft', 'FinalText': 'Exact owner final wording'})
        store.reconcile_processing_membership()
        item = processing_all.AllInventory().page(store)['items'][0]
        detail = processing_all.item_detail(store, item['item_id'], kind='review', local_id=rid)
        assert detail['detail']['body'] == 'Exact owner final wording'
        assert 'Superseded machine draft' not in json.dumps(detail)
    finally:
        store.cx.close()
