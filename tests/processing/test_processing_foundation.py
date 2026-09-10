"""Independent seams: historical evidence agrees with the unchanged legacy consumer."""
from datetime import datetime, timedelta
import json

import pytest

from taskuary import store as storage
from .test_baseline_preservation import _legacy_picture, _assert_preserved


def _database_rows(db):
    names = [row[0] for row in db.cx.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")]
    return {name: sorted((tuple(row) for row in db.cx.execute(f'SELECT * FROM "{name}"')), key=repr)
            for name in names}


def test_additive_startup_and_getters_do_not_capture_or_change_owner_state(tmp_path):
    path = tmp_path / 'frozen-legacy.db'
    expected = _legacy_picture(path)
    db = storage.SQLiteStore(str(path))
    try:
        before = _database_rows(db)
        processing = {name: rows for name, rows in before.items()
                      if name.startswith('processing_')}
        assert len(processing) >= 5
        assert len(processing['processing_reconcile_state']) == 1
        assert all(not rows for name, rows in processing.items() if name != 'processing_reconcile_state')
        status = db.processing_reconcile_status()
        assert status['pending'] is True
        assert status['attempted_generation'] == status['reconciled_generation'] == 0
        _assert_preserved(db, expected)
        assert db.resolve_processing_target('legacy_funnel', 'msg:71') is None
        assert not db.processing_members('nonexistent-synthetic-item')
        assert not db.processing_snapshot('nonexistent-synthetic-item')
        assert _database_rows(db) == before
    finally:
        db.cx.close()


@pytest.mark.parametrize('mixed', [False, True])
def test_digest_deferral_is_not_promoted_to_permanent_read(tmp_path, mixed):
    stamp = datetime.now().replace(microsecond=0).isoformat(sep=' ')
    db = storage.SQLiteStore(str(tmp_path / 'digest.db'))
    try:
        mid = db.add_message({'Channel': 'assistant', 'Subject': 'Synthetic digest',
                              'BodyText': 'Two independent invented suggestions.', 'SentAt': stamp})
        deferred = db.upsert_idea({'key': 'synthetic-deferred', 'text': 'Defer this idea.'}, stamp)
        ideas = [deferred]
        if mixed:
            ideas.append(db.upsert_idea({'key': 'synthetic-surfaced', 'text': 'Already displayed.'}, stamp))
            db.set_funnel_state(f"idea:{ideas[1]['IdeaId']}", 'surfaced')
        ids = [idea['IdeaId'] for idea in ideas]
        db.set_ideas_message(ids, mid)
        db.set_brief(mid, json.dumps({'ideas': [{'id': iid} for iid in ids]}))
        # Legacy idea filtering suppresses even expired deferrals. Preserve that
        # observed result without turning the wrapper into a permanent read receipt.
        db.set_funnel_state(f"idea:{deferred['IdeaId']}", 'later', until='2000-01-01 00:00:00')
        original_states = db.funnel_states()
        row = next(row for row in db.feed() if row['MessageId'] == mid)
        assert row['Unread'] == 0
        db.backfill_processing('digest-provenance-v1', fixed_now=stamp)
        evidence = dict(db.cx.execute('''SELECT * FROM processing_legacy_evidence
            WHERE MigrationVersion=? AND EntityKind='message' AND LocalId=?''',
            ('digest-provenance-v1', str(mid))).fetchone())
        assert evidence['ObservedUnread'] == 0
        assert evidence['PermanentRead'] == 0
        assert db.funnel_states() == original_states
        targets = [db.resolve_processing_target('legacy_funnel', f'idea:{iid}') for iid in ids]
        assert len({target['item_id'] for target in targets}) == len(ids)
    finally:
        db.cx.close()


def test_baseline_replay_and_reopen_preserve_original_owner_records(tmp_path):
    path = tmp_path / 'baseline-replay.db'
    expected = _legacy_picture(path)
    db = storage.SQLiteStore(str(path))
    identities = None
    try:
        legacy = {name: rows for name, rows in _database_rows(db).items()
                  if not name.startswith('processing_')}
        db.backfill_processing('frozen-v1', fixed_now=expected['at'])
        evidence = db.processing_legacy_evidence('frozen-v1')
        assert evidence
        identities = [db.resolve_processing_target('legacy_funnel', f'msg:{mid}') for mid in (71, 72, 73, 74)]
        assert all(identities)
        assert {name: rows for name, rows in _database_rows(db).items()
                if not name.startswith('processing_')} == legacy

        db.set_funnel_state('msg:71', 'done', note='Synthetic later owner operation')
        newcomer = db.add_message({'Channel': 'email', 'Subject': 'After baseline',
                                   'BodyText': 'Synthetic new activity', 'Status': 'filed'})
        db.backfill_processing('frozen-v1', fixed_now='2099-01-01 00:00:00')
        assert db.processing_legacy_evidence('frozen-v1') == evidence
        assert not db.processing_legacy_evidence('frozen-v1', entity_kind='message', local_id=newcomer)
        assert db.get_message(newcomer)['BodyText'] == 'Synthetic new activity'
    finally:
        db.cx.close()

    for _ in range(2):
        db = storage.SQLiteStore(str(path))
        try:
            assert db.processing_legacy_evidence('frozen-v1') == evidence
            assert [db.resolve_processing_target('legacy_funnel', f'msg:{mid}') for mid in (71, 72, 73, 74)] == identities
            assert db.funnel_states()['msg:71']['Note'] == 'Synthetic later owner operation'
            assert expected['attachment_file'].read_text(encoding='utf-8') == 'synthetic attachment bytes'
        finally:
            db.cx.close()


def test_two_open_ideas_capture_the_exact_legacy_selected_key(tmp_path):
    stamp = datetime.now().replace(microsecond=0).isoformat(sep=' ')
    db = storage.SQLiteStore(str(tmp_path / 'open-ideas.db'))
    try:
        mid = db.add_message({'Channel': 'assistant', 'Subject': 'Synthetic suggestions',
                              'BodyText': 'Both suggestions remain independent.', 'SentAt': stamp})
        ideas = [db.upsert_idea({'key': f'synthetic-open-{n}', 'text': f'Suggestion {n}'}, stamp)
                 for n in range(2)]
        ids = [idea['IdeaId'] for idea in ideas]
        db.set_ideas_message(ids, mid)
        db.set_brief(mid, json.dumps({'ideas': [{'id': iid} for iid in ids]}))
        row = next(row for row in db.feed() if row['MessageId'] == mid)
        expected_key = f'idea:{max(ids)}'
        assert row['FunnelKey'] == expected_key
        db.backfill_processing('open-ideas-v1', fixed_now=stamp)
        evidence = db.processing_legacy_evidence('open-ideas-v1', entity_kind='message', local_id=mid)
        assert len(evidence) == 1
        assert evidence[0]['selected_key'] == expected_key
        assert evidence[0]['observed_unread']
    finally:
        db.cx.close()


@pytest.mark.parametrize('getter', ['resolve', 'members', 'snapshot'])
def test_multiquery_getter_keeps_one_snapshot_during_external_merge(tmp_path, monkeypatch, getter):
    path = tmp_path / 'concurrent-read.db'
    reader = storage.SQLiteStore(str(path))
    writer = storage.SQLiteStore(str(path))
    try:
        mids = [reader.add_message({'Channel': 'email', 'BodyText': f'Synthetic body {n}'})
                for n in range(2)]
        reader.backfill_processing('reader-v1', fixed_now='2026-09-06 12:00:00')
        source, target = [reader.resolve_processing_target('legacy_funnel', f'msg:{mid}')['item_id']
                          for mid in mids]
        follow = reader._processing_follow
        merged = False

        def merge_after_first_read(cur, item_id):
            nonlocal merged
            if getter == 'resolve' and not merged:
                # Alias/member reads have established the old snapshot; following
                # the redirect must stay in that snapshot too.
                merged = True
                writer.merge_processing_items(source, target)
            result = follow(cur, item_id)
            if not merged:
                merged = True
                writer.merge_processing_items(source, target)
            return result

        monkeypatch.setattr(reader, '_processing_follow', merge_after_first_read)
        if getter == 'resolve':
            result = reader.resolve_processing_target('legacy_funnel', f'msg:{mids[0]}')
            assert result['item_id'] == source
        elif getter == 'members':
            result = reader.processing_members(source, include_retired=True)
            assert {row['ItemId'] for row in result} == {source}
            assert all(row['RetiredAt'] is None for row in result)
        else:
            result = reader.processing_snapshot(source)
            assert result['item_id'] == source
            assert result['member_ids'] == [f'message:{mids[0]}']
        assert merged and not reader.cx.in_transaction
        assert reader.resolve_processing_target('legacy_funnel', f'msg:{mids[0]}')['item_id'] == target
    finally:
        reader.cx.close()
        writer.cx.close()


def test_late_context_capture_failure_rolls_back_and_can_retry(tmp_path, monkeypatch):
    from taskuary import processing_projection as projection_module
    db = storage.SQLiteStore(str(tmp_path / 'late-capture-failure.db'))
    try:
        for n in range(2):
            db.add_message({'Channel': 'email', 'BodyText': f'Complete synthetic body {n}'})
        before = _database_rows(db)
        original = projection_module.processing_projection
        calls = 0

        def fail_second_context(*args, **kwargs):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise RuntimeError('synthetic context capture failure')
            return original(*args, **kwargs)

        monkeypatch.setattr(projection_module, 'processing_projection', fail_second_context)
        with pytest.raises(RuntimeError, match='synthetic context capture failure'):
            db.backfill_processing('late-failure-v1', fixed_now='2026-09-06 12:00:00')
        assert calls == 2
        assert _database_rows(db) == before
        assert not db.cx.in_transaction
        monkeypatch.setattr(projection_module, 'processing_projection', original)
        db.backfill_processing('late-failure-v1', fixed_now='2026-09-06 12:00:00')
        assert db.cx.execute('SELECT COUNT(*) FROM processing_context_snapshot').fetchone()[0] == 2
    finally:
        db.cx.close()


def test_worker_iterator_and_nested_payload_are_frozen_across_capture_and_getter(tmp_path):
    db = storage.SQLiteStore(str(tmp_path / 'worker-snapshots.db'))
    try:
        tasks = [db.create_task({'Title': f'Synthetic work {n}'}, 'fixture') for n in range(2)]
        for tid in tasks:
            db.add_message({'TaskId': tid, 'Channel': 'email', 'BodyText': 'Synthetic source'})
        workers = [{'taskId': tid, 'agent': 'fixture', 'waiting': True,
                    'tail': ['Original synthetic question']} for tid in tasks]
        db.backfill_processing('iterator-v1', fixed_now='2026-09-06 12:00:00', live_state=iter(workers))
        for tid in tasks:
            iid = db.resolve_processing_target('legacy_funnel', f'task:{tid}')['item_id']
            captured = json.loads(db.cx.execute('''SELECT ViewJson FROM processing_context_snapshot
                WHERE MigrationVersion=? AND ItemId=?''', ('iterator-v1', iid)).fetchone()[0])
            assert captured['worker_attention_available']
            assert captured['worker_attention'][0]['taskId'] == tid
            assert captured['worker_attention'][0]['tail'] == ['Original synthetic question']
        snapshot = db.processing_snapshot(iid, live_state=workers)
        frozen = json.dumps(snapshot, sort_keys=True)
        workers[-1]['tail'].append('Caller changed its nested list afterward')
        assert json.dumps(snapshot, sort_keys=True) == frozen
        refreshed = db.processing_snapshot(iid, live_state=workers)
        assert refreshed['context_revision'] == snapshot['context_revision']
        assert refreshed['view_revision'] != snapshot['view_revision']
        assert not db.processing_snapshot(iid)['view']['worker_attention_available']
        assert db.processing_snapshot(iid, live_state=[])['view']['worker_attention_available']
    finally:
        db.cx.close()


@pytest.mark.parametrize('case, expected_unread', [
    ('new', True), ('surfaced', False), ('done', False),
    ('deferred', False), ('expiry_equal', True), ('aged', False),
    ('cutoff_equal', True), ('closed', False), ('ignored', False),
    ('answered_pending', False), ('latest_resolved', False),
    ('null_review', True), ('empty_review', False),
    ('due_note', True),
    ('working_over_done', True), ('waiting_done', False),
])
def test_legacy_evidence_matches_actual_feed_and_fixed_expectation(
        tmp_path, monkeypatch, case, expected_unread):
    # Freeze only this synthetic store's Python clock; all records fall inside the
    # SQL inventory window. Exact cutoff/expiry expectations catch > versus >= drift.
    fixed = datetime.now().replace(microsecond=0)

    class Clock(datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed

    monkeypatch.setattr(storage, 'datetime', Clock)
    from taskuary import terminal
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    db = storage.SQLiteStore(str(tmp_path / 'differential.db'))
    try:
        stamp = fixed.isoformat(sep=' ')
        task = None
        if case in ('closed', 'working_over_done', 'waiting_done', 'due_note'):
            task = db.create_task({'Title': 'Invented task', 'Status': 'open',
                                   'Kind': 'note' if case == 'due_note' else 'general'}, 'fixture')
        mid = db.add_message({
            'TaskId': task, 'Channel': 'email', 'Subject': 'Invented mail',
            'BodyText': 'Complete synthetic source body.', 'SentAt': stamp,
            'ConversationId': 'synthetic-differential', 'Status': 'filed',
        })
        key = f'msg:{mid}'
        if case in ('surfaced', 'done'):
            db.set_funnel_state(key, case)
        if case in ('deferred', 'expiry_equal'):
            until = fixed + timedelta(hours=2) if case == 'deferred' else fixed
            db.set_funnel_state(key, 'later', until=until.isoformat(sep=' '))
        if case in ('aged', 'cutoff_equal', 'due_note'):
            age = timedelta(hours=12, seconds=0 if case == 'cutoff_equal' else 1)
            db._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?',
                     ((fixed - age).isoformat(sep=' '), mid))
        if case == 'closed':
            db.update_task(task, {'Status': 'done'}, 'fixture')
        if case == 'ignored':
            db.set_message_status(mid, 'ignored')
        if case in ('answered_pending', 'latest_resolved'):
            db.add_review({'MessageId': mid, 'Kind': 'reply', 'Status': 'pending'})
            if case == 'latest_resolved':
                db.add_review({'MessageId': mid, 'Kind': 'reply', 'Status': 'rejected'})
            else:
                db.add_message({
                    'Channel': 'email', 'Status': 'context',
                    'ConversationId': 'synthetic-differential', 'BodyText': 'Synthetic reply',
                    'SentAt': (fixed + timedelta(seconds=1)).isoformat(sep=' '),
                })
        if case in ('null_review', 'empty_review'):
            db.add_review({'MessageId': mid, 'Kind': 'reply',
                           'Status': None if case == 'null_review' else ''})
        live = []
        if case in ('working_over_done', 'waiting_done'):
            live = [{
                'taskId': task, 'agent': 'synthetic-worker',
                'waiting': case == 'waiting_done',
            }]
            monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: live)
            db.set_funnel_state(f'agent:{task}', 'done')

        rows = db.feed(limit=100, days=2)
        row = next(row for row in rows if row['MessageId'] == mid)
        db.backfill_processing('independent-differential-v1', fixed_now=stamp, live_state=live)
        evidence = dict(db.cx.execute('''SELECT * FROM processing_legacy_evidence
            WHERE MigrationVersion=? AND EntityKind='message' AND LocalId=?''',
            ('independent-differential-v1', str(mid))).fetchone())
        assert bool(row['Unread']) is expected_unread
        assert bool(evidence['ObservedUnread']) is expected_unread
        assert evidence['SelectedLegacyKey'] == row['FunnelKey']
        if case == 'deferred':
            assert not evidence['PermanentRead']
            assert evidence['TemporaryDeferJson']
    finally:
        db.cx.close()
