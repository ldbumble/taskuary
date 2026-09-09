"""PW-101/PW-103/PW-106/PW-109 non-activating processing inventory gates."""
import contextlib
import threading
from unittest import mock

from taskuary.store import SQLiteStore


NOW = '2026-09-06 12:00:00'


def add_message(store, *, task=None, subject='Inventory fixture', body=None):
    return store.add_message({
        'TaskId': task, 'Channel': 'email', 'SourceName': 'fixture-account',
        'Subject': subject, 'BodyText': body or f'Full body for {subject}',
        'SentAt': NOW, 'Status': 'filed',
    })


def legacy_stub(row, states, *, now, funnel_hours=12):
    key = f"msg:{row['MessageId']}"
    state = states.get(key) or {}
    return {
        'selected_key': key,
        'observed_unread': state.get('Status') not in ('done', 'surfaced'),
        'permanent_read': state.get('Status') in ('done', 'surfaced'),
        'reasons': [state['Status']] if state.get('Status') else [],
        'deferral': None,
        'raw_evidence': {'selected_state': state, 'fixed_now': now, 'funnel_hours': funnel_hours},
    }


def seed_four_entity_kinds(store):
    task_id = store.create_task({'Title': 'Uncatalogued task'}, 'fixture')
    message_id = add_message(store, task=task_id, subject='Uncatalogued message')
    review_id = store.add_review({
        'TaskId': task_id, 'MessageId': message_id, 'Kind': 'reply',
        'DraftText': 'Owner draft', 'Status': 'pending',
    })
    idea = store.upsert_idea({
        'key': 'uncatalogued-idea', 'text': 'Uncatalogued idea', 'kind': 'followup',
    }, NOW)
    return task_id, message_id, review_id, idea['IdeaId']


def dump_owner_tables(store):
    tables = [r[0] for r in store.cx.execute('''SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%' ORDER BY name''')]
    return {table: [tuple(row) for row in store.cx.execute(f'SELECT * FROM "{table}"')]
            for table in tables}


def test_empty_inventory_reports_uncatalogued_raw_entities_without_allocating(tmp_path):
    store = SQLiteStore(str(tmp_path / 'empty-gaps.db'))
    seed_four_entity_kinds(store)
    before = dump_owner_tables(store)

    picture = store.processing_inventory_snapshot(fixed_now=NOW)

    assert picture['schema_version'] == 'taskuary.processing.inventory.v1'
    assert picture['as_of'] == NOW
    assert picture['items'] == []
    reconciliation = store.processing_reconcile_status()
    assert reconciliation['pending'] is True
    assert reconciliation['dirty_generation'] > 0
    assert reconciliation['attempted_generation'] == reconciliation['reconciled_generation'] == 0
    assert reconciliation['conflicts'] == []
    assert picture['coverage'] == {
        'canonical_item_count': 0,
        'visible_item_count': 0,
        'tombstone_item_count': 0,
        'member_count': 0,
        'uncatalogued': {'message': 1, 'task': 1, 'review': 1, 'idea': 1},
        'completed_baselines': [],
        'unsupported': ['attachment_only_items', 'calendar', 'comment_only_items', 'task_artifact_only_items',
                        'waitroom', 'worker_questions'],
        'processing_reconciliation': reconciliation,
    }
    assert picture['worker_attention_available'] is False
    assert len(picture['worker_input_revision']) == 64
    assert len(picture['snapshot_revision']) == 64
    assert picture == store.processing_inventory_snapshot(fixed_now=NOW)
    assert picture['snapshot_revision'] != store.processing_inventory_snapshot(
        fixed_now='2026-09-06 12:00:01')['snapshot_revision']
    assert dump_owner_tables(store) == before
    store.cx.close()


def test_display_history_filters_before_projection_and_caches_until_a_write(tmp_path):
    store = SQLiteStore(str(tmp_path / 'display-window.db'))
    recent = add_message(store, subject='Recent')
    old = add_message(store, subject='Old')
    source = store.save_source({'Channel': 'email', 'Address': 'fixture-account', 'Active': 1}, 'fixture')
    store._exec("UPDATE message SET CreatedAt='2020-01-01 12:00:00',SentAt='2020-01-01 12:00:00' WHERE MessageId=?", (old,))
    store.reconcile_processing_membership()

    complete = store.processing_inventory_snapshot(fixed_now=NOW, live_state=[], display_only=True)
    assert {mid for item in complete['items'] for mid in item['member_ids']} == {
        f'message:{recent}', f'message:{old}'}

    store._processing_display_cache = {}
    with mock.patch.object(store, '_processing_snapshot_cursor', wraps=store._processing_snapshot_cursor) as projection:
        first = store.processing_inventory_snapshot(
            fixed_now=NOW, live_state=[], display_only=True, history_days=14)
        calls = projection.call_count
        assert [mid for item in first['items'] for mid in item['member_ids']] == [f'message:{recent}']
        second = store.processing_inventory_snapshot(
            fixed_now='2026-09-06 12:00:01', live_state=[], display_only=True, history_days=14)
        assert projection.call_count == calls
        assert second['items'] == first['items']
        assert second['snapshot_revision'] != first['snapshot_revision']

        store.touch_source(source)
        store.patch_source_poll_state(source, config_set={'watermark': 'next'}, last_polled_at=NOW)
        store.processing_inventory_snapshot(
            fixed_now='2026-09-06 12:00:01', live_state=[], display_only=True, history_days=14)
        assert projection.call_count == calls

        store.set_setting('owner_name', 'Cache invalidation', 'fixture')
        store.processing_inventory_snapshot(
            fixed_now='2026-09-06 12:00:02', live_state=[], display_only=True, history_days=14)
        assert projection.call_count > calls
    store.cx.close()


def test_cached_display_read_does_not_wait_for_the_writer_connection_lock(tmp_path):
    store = SQLiteStore(str(tmp_path / 'display-cache-lock.db'))
    add_message(store, subject='Cached while syncing')
    store.reconcile_processing_membership()
    store.processing_inventory_snapshot(
        fixed_now=NOW, live_state=[], display_only=True, history_days=14)
    finished = threading.Event()
    failures = []

    def read_cached():
        try:
            store.processing_inventory_snapshot(
                fixed_now=NOW, live_state=[], display_only=True, history_days=14)
        except BaseException as error:
            failures.append(error)
        finally:
            finished.set()

    with store.lock:  # stand in for a poll currently writing through the shared connection
        thread = threading.Thread(target=read_cached)
        thread.start()
        assert finished.wait(0.5)
    thread.join()
    assert failures == []
    store.cx.close()


def test_display_cache_ignores_terminal_tail_ticks_but_not_waiting_transitions(tmp_path):
    store = SQLiteStore(str(tmp_path / 'display-worker-cache.db'))
    task = store.create_task({'Title': 'Live worker'}, 'fixture')
    add_message(store, task=task, subject='Live worker message')
    store.reconcile_processing_membership()
    first_worker = [{'taskId': task, 'agent': 'coder', 'waiting': False,
                     'tail': ['first frame'], 'phase': 'working'}]
    next_frame = [{'taskId': task, 'agent': 'coder', 'waiting': False,
                   'tail': ['different frame'], 'phase': 'working'}]
    waiting = [{'taskId': task, 'agent': 'coder', 'waiting': True,
                'tail': ['different frame'], 'phase': 'waiting'}]

    with mock.patch.object(store, '_processing_snapshot_cursor', wraps=store._processing_snapshot_cursor) as projection:
        store.processing_inventory_snapshot(
            fixed_now=NOW, live_state=first_worker, display_only=True, history_days=14)
        calls = projection.call_count
        store.processing_inventory_snapshot(
            fixed_now=NOW, live_state=next_frame, display_only=True, history_days=14)
        assert projection.call_count == calls
        first_waiting = store.processing_inventory_snapshot(
            fixed_now=NOW, live_state=waiting, display_only=True, history_days=14)
        assert projection.call_count == calls
        assert first_waiting['worker_input_revision'] != store.processing_inventory_snapshot(
            fixed_now=NOW, live_state=next_frame, display_only=True, history_days=14)['worker_input_revision']
    store.cx.close()


def test_uncapped_inventory_returns_507_sorted_full_snapshots_and_evidence(tmp_path):
    store = SQLiteStore(str(tmp_path / 'uncapped.db'))
    suffix = 'THE FULL BODY SUFFIX MUST SURVIVE'
    with store.lock:
        store.cx.executemany('''INSERT INTO message
            (ExternalId,Channel,SourceName,Subject,SentAt,BodyText,Status,CreatedAt)
            VALUES (?,?,?,?,?,?,?,?)''', [
                (f'inventory:{i}', 'email', 'fixture-account', f'Row {i}', NOW,
                 (f'Body {i} ' + ('x' * 4200) + (suffix if i == 506 else '')), 'filed', NOW)
                for i in range(507)
            ])
        store.cx.commit()
    store.set_funnel_state('msg:507', 'done', note='preserve exact owner receipt')
    result = store.backfill_processing('inventory-v1', fixed_now=NOW, evaluator=legacy_stub)
    assert result['status'] == 'complete'

    picture = store.processing_inventory_snapshot(fixed_now=NOW)

    assert len(picture['items']) == 507
    assert [row['item_id'] for row in picture['items']] == sorted(
        row['item_id'] for row in picture['items'])
    assert picture['coverage']['canonical_item_count'] == 507
    assert picture['coverage']['member_count'] == 507
    assert picture['coverage']['uncatalogued'] == {
        'message': 0, 'task': 0, 'review': 0, 'idea': 0}
    assert picture['coverage']['completed_baselines'] == ['inventory-v1']
    last = next(item for item in picture['items'] if 'message:507' in item['member_ids'])
    assert last['context']['members'][1]['BodyText'].endswith(suffix)
    evidence = next(row for row in last['legacy_evidence'] if row['local_id'] == '507')
    assert evidence['permanent_read'] is True
    assert evidence['original']['source_message']['BodyText'].endswith(suffix)
    assert {'item', 'item_history', 'members', 'member_history', 'aliases', 'relations',
            'legacy_evidence', 'context_history', 'context', 'view', 'context_revision',
            'view_revision'} <= set(last)
    for forbidden in ('read', 'defer', 'actionable', 'excluded'):
        assert forbidden not in last
    store.cx.close()


def test_redirects_deduplicate_roots_and_preserve_source_history_after_reopen(tmp_path):
    path = tmp_path / 'redirect.db'
    store = SQLiteStore(str(path))
    first = add_message(store, subject='Source item evidence')
    second = add_message(store, subject='Target item evidence')
    store.set_funnel_state(f'msg:{first}', 'done', note='source receipt remains exact')
    store.backfill_processing('inventory-v1', fixed_now=NOW, evaluator=legacy_stub)
    source = store.resolve_processing_target('legacy_funnel', f'msg:{first}')['item_id']
    target = store.resolve_processing_target('legacy_funnel', f'msg:{second}')['item_id']
    store.merge_processing_items(source, target, fixed_now='2026-09-06 12:01:00')
    store.cx.close()

    reopened = SQLiteStore(str(path))
    picture = reopened.processing_inventory_snapshot(fixed_now='2026-09-06 12:02:00')
    assert len(picture['items']) == 1
    item = picture['items'][0]
    assert item['item_id'] == target
    assert {row['ItemId'] for row in item['item_history']} == {source, target}
    assert {row['local_id'] for row in item['legacy_evidence']} == {str(first), str(second)}
    old = next(row for row in item['legacy_evidence'] if row['local_id'] == str(first))
    assert old['original']['raw_evidence']['selected_state']['Note'] == 'source receipt remains exact'
    assert picture['coverage']['canonical_item_count'] == 1
    assert picture['coverage']['member_count'] == 2
    assert picture['coverage']['uncatalogued']['message'] == 0
    assert picture == reopened.processing_inventory_snapshot(fixed_now='2026-09-06 12:02:00')
    reopened.cx.close()


def test_late_raw_arrivals_are_reported_as_gaps_without_changing_existing_items(tmp_path):
    store = SQLiteStore(str(tmp_path / 'late.db'))
    first = add_message(store, subject='Baseline item')
    store.backfill_processing('inventory-v1', fixed_now=NOW, evaluator=legacy_stub)
    before = store.processing_inventory_snapshot(fixed_now=NOW)
    existing_ids = [row['item_id'] for row in before['items']]

    seed_four_entity_kinds(store)
    after = store.processing_inventory_snapshot(fixed_now='2026-09-06 13:00:00')

    assert after['coverage']['uncatalogued'] == {
        'message': 1, 'task': 1, 'review': 1, 'idea': 1}
    assert after['coverage']['canonical_item_count'] == 1
    assert [row['item_id'] for row in after['items']] == existing_ids
    assert store.resolve_processing_target('legacy_funnel', f'msg:{first}')['item_id'] == existing_ids[0]
    store.cx.close()


def test_inventory_uses_one_read_transaction_and_preserves_every_owner_table(tmp_path, monkeypatch):
    store = SQLiteStore(str(tmp_path / 'read-only.db'))
    task_id = store.create_task({'Title': 'Owner task', 'Summary': 'Keep summary'}, 'owner')
    message_id = add_message(store, task=task_id, subject='Owner message')
    store.add_comment(task_id, 'owner', 'human', 'Owner comment')
    store.add_task_artifact({'TaskId': task_id, 'Name': 'owner.txt',
                             'Path': '/synthetic/owner.txt', 'CreatedBy': 'owner'})
    store.save_doc('counsel', 'Owner custom counsel', 'owner')
    store.set_setting('owner-inventory-fixture', 'keep exactly', 'owner')
    store.backfill_processing('inventory-v1', fixed_now=NOW, evaluator=legacy_stub)
    item_id = store.resolve_processing_target('legacy_funnel', f'msg:{message_id}')['item_id']
    live = [{'taskId': task_id, 'agent': 'fixture-worker', 'waiting': True}]
    expected = store.processing_snapshot(item_id, live_state=live)
    before = dump_owner_tables(store)
    changes = store.cx.total_changes
    writes = store._writes
    entered = 0
    real_read = store._processing_read

    @contextlib.contextmanager
    def counted_read():
        nonlocal entered
        entered += 1
        with real_read() as cur:
            yield cur

    monkeypatch.setattr(store, '_processing_read', counted_read)
    monkeypatch.setattr(store, '_processing_item_id',
                        lambda: (_ for _ in ()).throw(AssertionError('getter allocated identity')))

    inventory = store.processing_inventory_snapshot(fixed_now=NOW, live_state=live)

    assert entered == 1
    assert inventory['items'][0] == expected
    assert store.cx.total_changes == changes
    assert store._writes == writes
    assert dump_owner_tables(store) == before
    store.cx.close()


def test_worker_input_is_frozen_complete_and_revisioned_without_policy_inference(tmp_path):
    store = SQLiteStore(str(tmp_path / 'worker.db'))
    first_task = store.create_task({'Title': 'First worker task'}, 'fixture')
    second_task = store.create_task({'Title': 'Second worker task'}, 'fixture')
    add_message(store, task=first_task, subject='First worker message')
    add_message(store, task=second_task, subject='Second worker message')
    store.backfill_processing('inventory-v1', fixed_now=NOW, evaluator=legacy_stub)
    live = [
        {'taskId': second_task, 'agent': 'beta', 'waiting': True, 'question': {'text': 'Choose B'}},
        {'taskId': first_task, 'agent': 'alpha', 'waiting': False, 'question': {'text': 'Choose A'}},
        {'taskId': 999999, 'agent': 'orphan', 'waiting': True, 'question': {'text': 'Uncatalogued'}},
    ]

    first = store.processing_inventory_snapshot(fixed_now=NOW, live_state=live)
    reordered = store.processing_inventory_snapshot(fixed_now=NOW, live_state=list(reversed(live)))
    assert first['worker_attention_available'] is True
    assert first['worker_input_revision'] == reordered['worker_input_revision']
    assert first['snapshot_revision'] == reordered['snapshot_revision']
    assert sum(len(item['view']['worker_attention']) for item in first['items']) == 2
    assert all('read' not in item and 'actionable' not in item for item in first['items'])

    live[0]['question']['text'] = 'Changed after the first call'
    changed = store.processing_inventory_snapshot(fixed_now=NOW, live_state=live)
    unavailable = store.processing_inventory_snapshot(fixed_now=NOW)
    supplied_empty = store.processing_inventory_snapshot(fixed_now=NOW, live_state=[])
    second = next(item for item in first['items'] if f'task:{second_task}' in item['member_ids'])
    assert second['view']['worker_attention'][0]['question']['text'] == 'Choose B'
    assert changed['worker_input_revision'] != first['worker_input_revision']
    assert changed['snapshot_revision'] != first['snapshot_revision']
    assert unavailable['worker_attention_available'] is False
    assert supplied_empty['worker_attention_available'] is True
    assert unavailable['worker_input_revision'] != supplied_empty['worker_input_revision']
    assert unavailable['snapshot_revision'] != supplied_empty['snapshot_revision']
    store.cx.close()


def test_inventory_rejects_non_json_worker_input_before_opening_a_read_transaction(tmp_path, monkeypatch):
    store = SQLiteStore(str(tmp_path / 'strict-worker.db'))
    entered = False

    @contextlib.contextmanager
    def unexpected_read():
        nonlocal entered
        entered = True
        raise AssertionError('invalid worker input reached the database transaction')
        yield

    monkeypatch.setattr(store, '_processing_read', unexpected_read)
    try:
        store.processing_inventory_snapshot(
            fixed_now=NOW, live_state=[{'taskId': 1, 'opaque': object()}])
    except TypeError:
        pass
    else:
        raise AssertionError('non-JSON worker input must be rejected')
    assert entered is False
    store.cx.close()


def test_a_mutated_snapshot_never_corrupts_the_display_cache(tmp_path):
    """The display cache hands every reader a PRIVATE copy: apply_workers overlays workers onto
    what it gets and callers set fields on it, while the cached inventory behind it has to stay
    exactly as read. That copy was 396ms of every cache HIT over a real 78MB store, so it is
    specialised to the plain JSON types a snapshot actually holds - this is the invariant the
    specialisation has to keep, whatever it is implemented with.
    """
    store = SQLiteStore(str(tmp_path / 'copy-isolation.db'))
    seed_four_entity_kinds(store)
    store.reconcile_processing_membership()
    first = store.processing_inventory_snapshot(fixed_now=NOW, live_state=[], display_only=True)
    assert first['items'], 'the fixture must produce items to mutate'
    first['items'][0]['_clobbered'] = True
    first['items'].append({'_invented': True})
    first['coverage']['_clobbered'] = True

    second = store.processing_inventory_snapshot(fixed_now=NOW, live_state=[], display_only=True)
    assert '_clobbered' not in second['items'][0]
    assert all('_invented' not in item for item in second['items'])
    assert '_clobbered' not in second['coverage']
    assert len(second['items']) == len(first['items']) - 1
