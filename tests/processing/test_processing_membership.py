"""PW-101/102/103/106/109 canonical identity reconciliation gates."""
import contextlib
import json

import pytest

from taskuary import processing_membership
from taskuary.store import PROCESSING_DIRTY_TABLES, SQLiteStore


NOW = '2026-09-06 12:00:00'
LATER = '2026-09-06 12:01:00'


def add_message(store, *, task=None, subject='Synthetic message', body='Complete body',
                channel='email', brief=None):
    return store.add_message({
        'TaskId': task, 'ExternalId': f'synthetic:{subject}', 'Channel': channel,
        'SourceName': 'fixture-account', 'Subject': subject, 'BodyText': body,
        'SentAt': NOW, 'Status': 'filed', 'Brief': brief,
    })


def active_item(store, entity_kind, local_id):
    row = store.cx.execute('''SELECT ItemId FROM processing_member
        WHERE EntityKind=? AND LocalId=? AND RetiredAt IS NULL''',
        (entity_kind, str(local_id))).fetchone()
    return store._processing_follow(store.cx.cursor(), row['ItemId']) if row else None


def raw_owner_tables(store):
    tables = [row[0] for row in store.cx.execute('''SELECT name FROM sqlite_master
        WHERE type='table' AND name NOT LIKE 'sqlite_%'
          AND name NOT LIKE 'processing_%' ORDER BY name''')]
    return {name: [tuple(row) for row in store.cx.execute(f'SELECT * FROM "{name}"')]
            for name in tables}


def test_constructor_is_schema_only_and_uncapped_reconcile_bootstraps_507_items(tmp_path):
    path = tmp_path / 'uncapped-membership.db'
    store = SQLiteStore(str(path))
    with store.lock:
        store.cx.executemany('''INSERT INTO message
            (ExternalId,Channel,SourceName,Subject,SentAt,BodyText,Status,CreatedAt)
            VALUES (?,?,?,?,?,?,?,?)''', [
                (f'bulk:{i}', 'email', 'fixture-account', f'Bulk {i}', NOW,
                 f'full body {i}', 'filed', NOW) for i in range(507)
            ])
        store.cx.commit()

    assert store.cx.execute('SELECT COUNT(*) FROM processing_item').fetchone()[0] == 0
    assert store.processing_reconcile_status()['pending'] is True
    result = store.reconcile_processing_membership(fixed_now=NOW)
    assert result['status'] == 'complete'
    assert result['created_items'] == 507
    assert store.cx.execute('SELECT COUNT(*) FROM processing_item').fetchone()[0] == 507
    assert store.cx.execute('''SELECT COUNT(*) FROM processing_member
        WHERE EntityKind='message' AND RetiredAt IS NULL''').fetchone()[0] == 507
    first_ids = [row[0] for row in store.cx.execute(
        'SELECT ItemId FROM processing_item ORDER BY ItemId')]
    assert store.reconcile_processing_membership(fixed_now=LATER)['status'] == 'already_current'
    store.cx.close()

    reopened = SQLiteStore(str(path))
    assert reopened.processing_reconcile_status()['pending'] is False
    assert [row[0] for row in reopened.cx.execute(
        'SELECT ItemId FROM processing_item ORDER BY ItemId')] == first_ids
    reopened.cx.close()


def test_all_raw_projection_tables_have_atomic_dirty_triggers_and_rollback_is_clean(tmp_path):
    store = SQLiteStore(str(tmp_path / 'triggers.db'))
    task = store.create_task({'Title': 'Trigger task'}, 'fixture')
    mid = add_message(store, task=task)
    with store.lock:
        store.cx.execute('''INSERT INTO review (TaskId,MessageId,Kind,Status,CreatedAt)
            VALUES (?,?,?,?,?)''', (task, mid, 'reply', 'pending', NOW))
        store.cx.execute('''INSERT INTO idea (Key,Kind,Text,Status,FirstSeen,LastSaid)
            VALUES (?,?,?,?,?,?)''', ('trigger-idea', 'followup', 'idea', 'open', NOW, NOW))
        store.cx.execute('''INSERT INTO attachment (MessageId,Name,CreatedAt)
            VALUES (?,?,?)''', (mid, 'proof.txt', NOW))
        store.cx.execute('''INSERT INTO run (TaskId,AgentName,Status,StartedAt)
            VALUES (?,?,?,?)''', (task, 'fixture-agent', 'done', NOW))
        store.cx.execute('''INSERT INTO route (MessageId,TaskId,Decision,CreatedAt)
            VALUES (?,?,?,?)''', (mid, task, 'attach', NOW))
        store.cx.execute('''INSERT INTO funnel_state (Key,Status,At)
            VALUES (?,?,?)''', (f'msg:{mid}', 'done', NOW))
        store.cx.execute('''INSERT INTO comment (TaskId,Actor,ActorType,Body,CreatedAt)
            VALUES (?,?,?,?,?)''', (task, 'owner', 'human', 'keep comment', NOW))
        store.cx.execute('''INSERT INTO task_artifact (TaskId,Name,Path,CreatedAt)
            VALUES (?,?,?,?)''', (task, 'owner.txt', '/synthetic/owner.txt', NOW))
        store.cx.commit()
    store.reconcile_processing_membership(fixed_now=NOW)
    complete = store.processing_reconcile_status()

    triggers = {row[0] for row in store.cx.execute('''SELECT name FROM sqlite_master
        WHERE type='trigger' AND name LIKE 'processing_dirty_%' ''')}
    for table in PROCESSING_DIRTY_TABLES:
        assert {f'processing_dirty_{table}_{action}' for action in ('insert', 'update', 'delete')} <= triggers

    columns = {
        'task': ('TaskId', task), 'message': ('MessageId', mid),
        'review': ('ReviewId', 1), 'idea': ('IdeaId', 1),
        'attachment': ('AttachmentId', 1), 'run': ('RunId', 1),
        'route': ('RouteId', 1), 'funnel_state': ('Key', f'msg:{mid}'),
        'comment': ('CommentId', 1), 'task_artifact': ('ArtifactId', 1),
    }
    for table, (column, value) in columns.items():
        before = store.processing_reconcile_status()['dirty_generation']
        with store.lock:
            store.cx.execute(f'UPDATE {table} SET {column}={column} WHERE {column}=?', (value,))
            store.cx.commit()
        assert store.processing_reconcile_status()['dirty_generation'] == before + 1

    before = store.processing_reconcile_status()['dirty_generation']
    with store.lock:
        store.cx.execute('BEGIN IMMEDIATE')
        store.cx.execute('UPDATE message SET BodyText=? WHERE MessageId=?', ('rolled back', mid))
        assert store.cx.execute('SELECT DirtyGeneration FROM processing_reconcile_state').fetchone()[0] == before + 1
        store.cx.rollback()
    assert store.processing_reconcile_status()['dirty_generation'] == before
    assert store.get_message(mid)['BodyText'] == 'Complete body'

    store.set_setting('owner_email', 'owner@example.test', 'fixture')
    assert store.processing_reconcile_status()['dirty_generation'] == before + 1
    store.set_setting('unrelated-processing-fixture', 'value', 'fixture')
    assert store.processing_reconcile_status()['dirty_generation'] == before + 1
    assert complete['reconciled_generation'] < store.processing_reconcile_status()['dirty_generation']
    store.cx.close()


def test_taskless_message_to_new_task_keeps_identity_and_owner_data(tmp_path):
    store = SQLiteStore(str(tmp_path / 'fyi-task.db'))
    mid = add_message(store, subject='FYI becomes work', body='Owner original body')
    store.set_funnel_state(f'msg:{mid}', 'done', note='owner read receipt')
    store.save_doc('counsel', 'Owner custom counsel', 'owner')
    store.reconcile_processing_membership(fixed_now=NOW)
    original = active_item(store, 'message', mid)
    before_owner = raw_owner_tables(store)

    task = store.create_task({'Title': 'New work from FYI'}, 'owner')
    store._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (task, mid))
    result = store.reconcile_processing_membership(fixed_now=LATER)

    assert result['status'] == 'complete'
    assert active_item(store, 'task', task) == original
    assert active_item(store, 'message', mid) == original
    assert store.resolve_processing_target('legacy_funnel', f'msg:{mid}')['item_id'] == original
    assert store.resolve_processing_target('legacy_funnel', f'task:{task}')['item_id'] == original
    # Only the explicitly created task and its exact FK changed in owner tables.
    assert store.get_message(mid)['BodyText'] == 'Owner original body'
    assert store.funnel_states()[f'msg:{mid}']['Note'] == 'owner read receipt'
    assert store.doc('counsel') == 'Owner custom counsel'
    assert before_owner['doc'] == raw_owner_tables(store)['doc']
    store.cx.close()


def test_existing_task_root_wins_convergence_and_empty_source_redirects(tmp_path):
    store = SQLiteStore(str(tmp_path / 'task-wins.db'))
    task = store.create_task({'Title': 'Established task'}, 'fixture')
    store.reconcile_processing_membership(fixed_now=NOW)
    task_root = active_item(store, 'task', task)
    mid = add_message(store, subject='Separate FYI')
    store.reconcile_processing_membership(fixed_now='2026-09-06 12:00:30')
    fyi_root = active_item(store, 'message', mid)
    assert fyi_root != task_root

    store._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (task, mid))
    result = store.reconcile_processing_membership(fixed_now=LATER)

    assert result['redirected_items'] == 1
    assert active_item(store, 'message', mid) == task_root
    assert store._processing_follow(store.cx.cursor(), fyi_root) == task_root
    old = store.processing_snapshot(fyi_root)
    assert {row['ItemId'] for row in old['item_history']} == {fyi_root, task_root}
    assert any(row['EntityKind'] == 'message' and row['ItemId'] == fyi_root and row['RetiredAt']
               for row in old['member_history'])
    store.cx.close()


def test_task_roots_are_reserved_before_an_earlier_task_can_claim_moved_member(tmp_path):
    store = SQLiteStore(str(tmp_path / 'reserved-task-root.db'))
    earlier = store.create_task({'Title': 'Earlier unprocessed task'}, 'fixture')
    established = store.create_task({'Title': 'Established later task'}, 'fixture')
    mid = add_message(store, task=established, subject='Moves to earlier task')
    established_root = store.reconcile_processing_entities(kind='task', members=[
        {'entity_kind': 'task', 'local_id': str(established), 'role': 'primary'},
        {'entity_kind': 'message', 'local_id': str(mid)}], fixed_now=NOW)

    store._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (earlier, mid))
    store.reconcile_processing_membership(fixed_now=LATER)

    assert active_item(store, 'task', established) == established_root
    assert active_item(store, 'task', earlier) != established_root
    assert active_item(store, 'message', mid) == active_item(store, 'task', earlier)
    assert store.cx.execute('SELECT RedirectItemId FROM processing_item WHERE ItemId=?',
                            (established_root,)).fetchone()[0] is None
    store.cx.close()


def test_new_task_joining_multiple_fyis_keeps_oldest_existing_item(tmp_path):
    store = SQLiteStore(str(tmp_path / 'multiple-fyis.db'))
    first = add_message(store, subject='Older FYI')
    second = add_message(store, subject='Newer FYI')
    store.reconcile_processing_membership(fixed_now=NOW)
    first_root = active_item(store, 'message', first)
    second_root = active_item(store, 'message', second)
    task = store.create_task({'Title': 'New combined task'}, 'fixture')
    with store.lock:
        store.cx.execute('UPDATE message SET TaskId=? WHERE MessageId IN (?,?)',
                         (task, first, second))
        store.cx.commit()

    store.reconcile_processing_membership(fixed_now=LATER)

    assert active_item(store, 'task', task) == first_root
    assert active_item(store, 'message', first) == first_root
    assert active_item(store, 'message', second) == first_root
    assert store._processing_follow(store.cx.cursor(), second_root) == first_root
    store.cx.close()


def test_reassignment_split_and_delete_move_only_exact_members(tmp_path):
    store = SQLiteStore(str(tmp_path / 'split.db'))
    task_a = store.create_task({'Title': 'Task A'}, 'fixture')
    task_b = store.create_task({'Title': 'Task B'}, 'fixture')
    first = add_message(store, task=task_a, subject='First A')
    second = add_message(store, task=task_a, subject='Second A')
    store.reconcile_processing_membership(fixed_now=NOW)
    root_a = active_item(store, 'task', task_a)
    root_b = active_item(store, 'task', task_b)
    with store.lock:
        store.cx.execute('''INSERT INTO processing_legacy_evidence
            (MigrationVersion,ItemId,EntityKind,LocalId,SelectedLegacyKey,ObservedUnread,
             PermanentRead,ReasonsJson,ContextFingerprint,OriginalJson,CapturedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            ('split-v1', root_a, 'message', str(second), f'msg:{second}', 0, 1,
             '["done"]', 'split-fingerprint', '{"receipt":"exact"}', NOW))
        store.cx.commit()

    store._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (task_b, second))
    store.reconcile_processing_membership(fixed_now='2026-09-06 12:01:00')
    assert active_item(store, 'task', task_a) == root_a
    assert active_item(store, 'message', first) == root_a
    assert active_item(store, 'task', task_b) == root_b
    assert active_item(store, 'message', second) == root_b
    assert store.cx.execute('SELECT RedirectItemId FROM processing_item WHERE ItemId=?',
                            (root_a,)).fetchone()[0] is None
    assert store.resolve_processing_target('legacy_funnel', f'msg:{second}')['item_id'] == root_b
    moved_snapshot = store.processing_snapshot(root_b)
    evidence = next(row for row in moved_snapshot['legacy_evidence']
                    if row['entity_kind'] == 'message' and row['local_id'] == str(second))
    assert evidence['item_id'] == root_a
    assert evidence['permanent_read'] is True
    assert evidence['original'] == {'receipt': 'exact'}

    store.delete_task(task_a)
    store.reconcile_processing_membership(fixed_now='2026-09-06 12:02:00')
    assert active_item(store, 'task', task_a) is None
    assert active_item(store, 'message', first) == root_a
    assert store.resolve_processing_target('legacy_funnel', f'task:{task_a}') is None
    assert store.resolve_processing_target('legacy_funnel', f'msg:{first}')['item_id'] == root_a

    empty_task = store.create_task({'Title': 'Delete to tombstone'}, 'fixture')
    store.reconcile_processing_membership(fixed_now='2026-09-06 12:03:00')
    empty_root = active_item(store, 'task', empty_task)
    store.delete_task(empty_task)
    store.reconcile_processing_membership(fixed_now='2026-09-06 12:04:00')
    inventory = store.processing_inventory_snapshot(fixed_now='2026-09-06 12:04:00')
    tombstone = next(item for item in inventory['items'] if item['item_id'] == empty_root)
    assert tombstone['members'] == []
    assert inventory['coverage']['tombstone_item_count'] == 1
    assert inventory['coverage']['visible_item_count'] == 2
    store.cx.close()


def test_deleting_task_splits_messages_without_redirecting_retained_root(tmp_path):
    store = SQLiteStore(str(tmp_path / 'delete-split.db'))
    task = store.create_task({'Title': 'Task with two messages'}, 'fixture')
    first = add_message(store, task=task, subject='First')
    second = add_message(store, task=task, subject='Second')
    store.reconcile_processing_membership(fixed_now=NOW)
    old_root = active_item(store, 'task', task)

    store.delete_task(task)
    store.reconcile_processing_membership(fixed_now=LATER)

    first_root = active_item(store, 'message', first)
    second_root = active_item(store, 'message', second)
    assert first_root == old_root
    assert second_root != old_root
    assert store.cx.execute('SELECT RedirectItemId FROM processing_item WHERE ItemId=?',
                            (old_root,)).fetchone()[0] is None
    assert {row['EntityKind'] for row in store.processing_members(old_root)} == {'message'}
    assert store.resolve_processing_target('legacy_funnel', f'msg:{second}')['item_id'] == second_root
    store.cx.close()


def test_review_parent_conflict_is_truthful_and_preserves_prior_identity(tmp_path):
    store = SQLiteStore(str(tmp_path / 'review-conflict.db'))
    task_a = store.create_task({'Title': 'A'}, 'fixture')
    task_b = store.create_task({'Title': 'B'}, 'fixture')
    mid = add_message(store, task=task_a, subject='A message')
    review = store.add_review({'TaskId': task_b, 'Kind': 'reply', 'Status': 'pending'})
    store.reconcile_processing_membership(fixed_now=NOW)
    review_root = active_item(store, 'review', review)
    assert review_root == active_item(store, 'task', task_b)
    last_good = store.processing_reconcile_status()['reconciled_generation']

    store._exec('UPDATE review SET MessageId=? WHERE ReviewId=?', (mid, review))
    conflicted = store.reconcile_processing_membership(fixed_now=LATER)
    assert conflicted['status'] == 'conflicted'
    assert conflicted['reconciled_generation'] == last_good
    assert conflicted['attempted_generation'] == conflicted['dirty_generation']
    assert conflicted['conflicts'][0]['code'] == 'contradictory_review_parents'
    assert active_item(store, 'review', review) == review_root
    assert store.resolve_processing_target('legacy_funnel', f'review:{review}')['item_id'] == review_root

    store._exec('UPDATE review SET TaskId=? WHERE ReviewId=?', (task_a, review))
    fixed = store.reconcile_processing_membership(fixed_now='2026-09-06 12:02:00')
    assert fixed['status'] == 'complete'
    assert active_item(store, 'review', review) == active_item(store, 'message', mid)
    store.cx.close()


def test_dangling_review_message_does_not_fall_through_to_task(tmp_path):
    store = SQLiteStore(str(tmp_path / 'review-precedence.db'))
    task = store.create_task({'Title': 'Valid task'}, 'fixture')
    with store.lock:
        rid = store.cx.execute('''INSERT INTO review
            (TaskId,MessageId,Kind,Status,CreatedAt) VALUES (?,?,?,?,?)''',
            (task, 99999, 'reply', 'pending', NOW)).lastrowid
        store.cx.commit()
    result = store.reconcile_processing_membership(fixed_now=NOW)
    assert result['status'] == 'complete'
    assert any(row['code'] == 'dangling_review_message' for row in result['diagnostics'])
    assert active_item(store, 'review', rid) != active_item(store, 'task', task)
    store.cx.close()


def test_attachments_and_runs_follow_only_valid_exact_parents(tmp_path):
    store = SQLiteStore(str(tmp_path / 'aux-members.db'))
    task = store.create_task({'Title': 'Exact parent'}, 'fixture')
    mid = add_message(store, task=task)
    with store.lock:
        attachment = store.cx.execute('''INSERT INTO attachment
            (MessageId,Name,CreatedAt) VALUES (?,?,?)''', (mid, 'valid.txt', NOW)).lastrowid
        run = store.cx.execute('''INSERT INTO run
            (TaskId,AgentName,Status,StartedAt) VALUES (?,?,?,?)''',
            (task, 'fixture-agent', 'done', NOW)).lastrowid
        dangling_attachment = store.cx.execute('''INSERT INTO attachment
            (MessageId,Name,CreatedAt) VALUES (?,?,?)''', (99991, 'dangling.txt', NOW)).lastrowid
        dangling_run = store.cx.execute('''INSERT INTO run
            (TaskId,AgentName,Status,StartedAt) VALUES (?,?,?,?)''',
            (99992, 'fixture-agent', 'done', NOW)).lastrowid
        store.cx.commit()

    result = store.reconcile_processing_membership(fixed_now=NOW)
    root = active_item(store, 'task', task)
    assert active_item(store, 'attachment', attachment) == root
    assert active_item(store, 'run', run) == root
    assert active_item(store, 'attachment', dangling_attachment) is None
    assert active_item(store, 'run', dangling_run) is None
    assert {row['code'] for row in result['diagnostics']} >= {
        'dangling_attachment_message', 'dangling_run_task'}
    # Gaps stay diagnostic. They are never promoted into independent actionable roots.
    assert result['created_items'] == 1
    store.cx.close()


def test_ideas_remain_independent_and_auxiliary_relation_errors_do_not_block(tmp_path):
    store = SQLiteStore(str(tmp_path / 'ideas.db'))
    first = store.upsert_idea({'key': 'idea-one', 'text': 'One', 'kind': 'followup'}, NOW)
    second = store.upsert_idea({'key': 'idea-two', 'text': 'Two', 'kind': 'followup'}, NOW)
    brief = json.dumps({'ideas': [{'id': first['IdeaId']}, {'id': second['IdeaId']}]})
    wrapper = add_message(store, subject='Digest wrapper', brief=brief)
    store.set_ideas_message([first['IdeaId'], second['IdeaId']], wrapper)
    result = store.reconcile_processing_membership(fixed_now=NOW)

    roots = {active_item(store, 'message', wrapper),
             active_item(store, 'idea', first['IdeaId']), active_item(store, 'idea', second['IdeaId'])}
    assert len(roots) == 3
    assert store.cx.execute('''SELECT COUNT(*) FROM processing_relation
        WHERE FromEntityKind='message' AND FromLocalId=? AND ToEntityKind='idea'
          AND RetiredAt IS NULL''', (str(wrapper),)).fetchone()[0] == 2
    first_root = active_item(store, 'idea', first['IdeaId'])

    store._exec('UPDATE message SET Brief=? WHERE MessageId=?', ('{bad json', wrapper))
    followup = store.reconcile_processing_membership(fixed_now=LATER)
    assert followup['status'] == 'complete'
    assert any(row['code'] == 'malformed_message_brief' for row in followup['diagnostics'])
    assert active_item(store, 'idea', first['IdeaId']) == first_root
    assert len({active_item(store, 'idea', first['IdeaId']),
                active_item(store, 'idea', second['IdeaId'])}) == 2
    store.cx.close()


def test_aliases_evidence_read_state_and_provider_scopes_survive_reconciliation(tmp_path):
    store = SQLiteStore(str(tmp_path / 'preservation.db'))
    mid = add_message(store, subject='Preserve everything', body='Exact owner body')
    store.set_funnel_state(f'msg:{mid}', 'later', until='2026-09-07 12:00:00',
                           note='owner deferral')
    store.save_doc('counsel', 'Exact owner counsel', 'owner')
    item = store.reconcile_processing_entities(kind='message', members=[
        {'entity_kind': 'message', 'local_id': str(mid), 'role': 'primary'}], aliases=[{
            'namespace': 'external_id', 'scope': 'connector:71', 'value': 'opaque-id',
            'entity_kind': 'message', 'local_id': str(mid), 'provenance': 'provider-receipt'}],
        fixed_now=NOW)
    with store.lock:
        store.cx.execute('''INSERT INTO processing_legacy_evidence
            (MigrationVersion,ItemId,EntityKind,LocalId,SelectedLegacyKey,ObservedUnread,
             PermanentRead,ReasonsJson,ContextFingerprint,OriginalJson,CapturedAt)
            VALUES (?,?,?,?,?,?,?,?,?,?,?)''',
            ('preserve-v1', item, 'message', str(mid), f'msg:{mid}', 0, 0,
             '["later"]', 'fingerprint', '{"owner":"exact"}', NOW))
        store.cx.commit()
    before_owner = raw_owner_tables(store)
    before_evidence = [tuple(row) for row in store.cx.execute(
        'SELECT * FROM processing_legacy_evidence')]

    store.reconcile_processing_membership(fixed_now=LATER)

    assert raw_owner_tables(store) == before_owner
    assert [tuple(row) for row in store.cx.execute(
        'SELECT * FROM processing_legacy_evidence')] == before_evidence
    provider = store.resolve_processing_target('external_id', 'opaque-id', 'connector:71')
    assert provider == {
        'item_id': item, 'entity_kind': 'message', 'local_id': str(mid),
        'namespace': 'external_id', 'scope': 'connector:71', 'value': 'opaque-id',
        'provenance': 'provider-receipt', 'redirected_from': None,
    }
    assert store.resolve_processing_target('external_id', 'opaque-id', 'connector:72') is None
    store.cx.close()


def test_reconcile_failure_rolls_back_members_aliases_relations_and_generation(tmp_path, monkeypatch):
    store = SQLiteStore(str(tmp_path / 'rollback.db'))
    mid = add_message(store, subject='Rollback membership', brief=json.dumps({'ideas': []}))
    before_status = store.processing_reconcile_status()
    before_changes = store.cx.total_changes
    real = processing_membership.reconcile_membership

    def fail_after_apply(*args, **kwargs):
        real(*args, **kwargs)
        raise RuntimeError('synthetic failure after apply')

    monkeypatch.setattr(processing_membership, 'reconcile_membership', fail_after_apply)
    with pytest.raises(RuntimeError, match='synthetic failure'):
        store.reconcile_processing_membership(fixed_now=NOW)

    assert store.cx.execute('SELECT COUNT(*) FROM processing_item').fetchone()[0] == 0
    assert store.cx.execute('SELECT COUNT(*) FROM processing_member').fetchone()[0] == 0
    assert store.cx.execute('SELECT COUNT(*) FROM processing_alias').fetchone()[0] == 0
    assert store.cx.execute('SELECT COUNT(*) FROM processing_relation').fetchone()[0] == 0
    assert store.processing_reconcile_status() == before_status
    assert store.cx.total_changes > before_changes  # SQLite counts rolled-back work; rows remain atomic.
    assert store.get_message(mid)['Subject'] == 'Rollback membership'
    store.cx.close()


def test_inventory_and_status_getters_are_read_only_and_share_one_wal_snapshot(tmp_path, monkeypatch):
    path = tmp_path / 'wal-snapshot.db'
    store = SQLiteStore(str(path))
    mid = add_message(store, subject='Before external write', body='old body')
    store.reconcile_processing_membership(fixed_now=NOW)
    peer = SQLiteStore(str(path))
    assert peer.processing_reconcile_status()['pending'] is False
    before_changes = store.cx.total_changes
    before_writes = store._writes
    entered = 0
    real_read = store._processing_read

    @contextlib.contextmanager
    def counted_read():
        nonlocal entered
        entered += 1
        with real_read() as cur:
            yield cur

    monkeypatch.setattr(store, '_processing_read', counted_read)
    real_snapshot = store._processing_snapshot_cursor
    wrote = False

    def snapshot_then_write(*args, **kwargs):
        nonlocal wrote
        result = real_snapshot(*args, **kwargs)
        if not wrote:
            wrote = True
            peer._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('new body', mid))
        return result

    monkeypatch.setattr(store, '_processing_snapshot_cursor', snapshot_then_write)
    picture = store.processing_inventory_snapshot(fixed_now=LATER)
    assert entered == 1
    assert picture['items'][0]['context']['members'][1]['BodyText'] == 'old body'
    assert picture['coverage']['processing_reconciliation']['pending'] is False
    assert store.cx.total_changes == before_changes
    assert store._writes == before_writes

    fresh = store.processing_reconcile_status()
    assert fresh['pending'] is True
    assert fresh['dirty_generation'] > fresh['reconciled_generation']
    peer.cx.close()
    store.cx.close()
