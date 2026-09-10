"""Email checkpoints preserve concurrent owner edits and fail atomically."""
from concurrent.futures import ThreadPoolExecutor
import json
import sqlite3
import threading

import pytest

from taskuary.store import SQLiteStore


@pytest.fixture(params=['source', 'connector'])
def checkpoint(tmp_path, request):
    path = str(tmp_path / 'mail-checkpoint.db')
    db = SQLiteStore(path)
    kind = request.param
    config = {'address': 'synthetic@example.invalid', 'folders': ['inbox'],
              'owner': {'custom': ['keep', 'exactly']}, 'cursor': {'uid': 25}}
    if kind == 'source':
        row_id = db.save_source({'Channel': 'email', 'Address': config['address'], 'Active': 1,
                                 'ConfigJson': json.dumps(config)}, 'fixture')
        patch, get, key = db.patch_source_poll_state, db.get_source, 'SourceId'
    else:
        row_id = db.get_connector_by_type('imap')['ConnectorId']
        db.set_connector_config(row_id, config)
        patch, get, key = db.patch_connector_poll_state, db.get_connector, 'ConnectorId'
    try:
        yield db, path, kind, row_id, patch, get, key
    finally:
        db.cx.close()


def test_checkpoint_merges_latest_owner_config_across_connections(checkpoint):
    db, path, kind, row_id, patch, get, key = checkpoint
    owner = sqlite3.connect(path)
    entered = threading.Event()
    try:
        owner.execute('BEGIN IMMEDIATE')
        cfg = json.loads(get(row_id)['ConfigJson'])
        cfg['owner']['custom'].append('owner edit while poll fetched')
        owner.execute(f'UPDATE {kind} SET ConfigJson=? WHERE {key}=?', (json.dumps(cfg), row_id))

        updates = {'cursor': {'uid': 50}}
        db.cx.set_trace_callback(lambda sql: entered.set() if sql == 'BEGIN IMMEDIATE' else None)
        def write_checkpoint():
            return patch(row_id, config_set=updates,
                         expect_config={'address': 'synthetic@example.invalid'})

        with ThreadPoolExecutor(max_workers=1) as pool:
            future = pool.submit(write_checkpoint)
            try:
                assert entered.wait(3)
                assert not future.done(), 'checkpoint must wait for the owner transaction'
                updates['cursor']['uid'] = 999  # caller mutation after the helper captured its patch
            finally:
                owner.commit()
            assert future.result(timeout=5)
        saved = json.loads(get(row_id)['ConfigJson'])
        assert saved == {**cfg, 'cursor': {'uid': 50}}
    finally:
        db.cx.set_trace_callback(None)
        owner.close()


def test_stale_or_missing_checkpoint_performs_zero_writes(checkpoint):
    db, _, _, row_id, patch, get, _ = checkpoint
    before = get(row_id)
    changes, writes = db.cx.total_changes, db._writes
    assert patch(row_id, config_set={'cursor': 99}, expect_config={'folders': ['sentitems']}) is False
    assert patch(row_id, config_remove=['owner'], expect_fields={'Active': 999}) is False
    assert patch(-999, config_set={'cursor': 99}) is False
    assert get(row_id) == before
    assert db.cx.total_changes == changes
    assert db._writes == writes


@pytest.mark.parametrize('invalid', ['not json', '[]', 'null', '"text"'])
def test_invalid_owner_config_is_preserved(checkpoint, invalid):
    db, _, kind, row_id, patch, get, key = checkpoint
    db._exec(f'UPDATE {kind} SET ConfigJson=? WHERE {key}=?', (invalid, row_id))
    changes = db.cx.total_changes
    with pytest.raises(ValueError): patch(row_id, config_set={'cursor': 99})
    assert get(row_id)['ConfigJson'] == invalid
    assert db.cx.total_changes == changes
    assert not db.cx.in_transaction


def test_failed_update_rolls_back_entire_checkpoint_and_connection_is_reusable(checkpoint):
    db, _, kind, row_id, patch, get, _ = checkpoint
    before = get(row_id)
    db.cx.execute(f"CREATE TRIGGER reject_checkpoint BEFORE UPDATE ON {kind} "
                  "BEGIN SELECT RAISE(ABORT, 'synthetic disk failure'); END")
    db.cx.commit()
    extra = {'last_polled_at': '2026-09-06 14:00:00'} if kind == 'source' else {}
    with pytest.raises(sqlite3.IntegrityError, match='synthetic disk failure'):
        patch(row_id, config_set={'epoch': 8, 'cursor': 0}, config_remove=['owner'], **extra)
    assert get(row_id) == before
    assert not db.cx.in_transaction
    db.cx.execute('DROP TRIGGER reject_checkpoint')
    db.cx.commit()
    assert patch(row_id, config_set={'epoch': 8, 'cursor': 0}, **extra)
    saved = get(row_id)
    assert json.loads(saved['ConfigJson'])['epoch'] == 8
    assert json.loads(saved['ConfigJson'])['cursor'] == 0
    if kind == 'source': assert saved['LastPolledAt'] == extra['last_polled_at']


def test_patch_does_not_mutate_inputs_and_none_expectation_accepts_missing_or_null(checkpoint):
    _, _, _, row_id, patch, get, _ = checkpoint
    updates = {'epoch': {'uid': 8}, 'nullable': None}
    expected = {'missing': None}
    assert patch(row_id, config_set=updates, config_remove=['cursor'], expect_config=expected)
    updates['epoch']['uid'] = 99
    assert json.loads(get(row_id)['ConfigJson'])['epoch'] == {'uid': 8}
    assert expected == {'missing': None}
    assert patch(row_id, expect_config={'nullable': None})
    assert 'cursor' not in json.loads(get(row_id)['ConfigJson'])


def test_source_cutoff_and_cursor_cleanup_are_one_conditional_checkpoint(tmp_path):
    db = SQLiteStore(str(tmp_path / 'source-cutoff.db'))
    try:
        sid = db.save_source({'Channel': 'email', 'Address': 'synthetic@example.invalid',
                              'ConfigJson': '{"folders":["inbox"],"mail_cursor":{"inbox":"old"}}'}, 'fixture')
        cutoff = '2026-09-06 14:00:00'
        assert db.patch_source_poll_state(sid, last_polled_at=cutoff,
                                          config_remove=['mail_cursor'],
                                          expect_fields={'LastPolledAt': None},
                                          expect_config={'folders': ['inbox']})
        assert db.get_source(sid)['LastPolledAt'] == cutoff
        assert 'mail_cursor' not in json.loads(db.get_source(sid)['ConfigJson'])
        assert db.patch_source_poll_state(sid, config_set={'mail_cursor': {'inbox': 'progress'}})
        assert db.get_source(sid)['LastPolledAt'] == cutoff, 'omitted watermark must stay unchanged'
        db.rewind_source(sid)
        before = db.get_source(sid)
        assert db.patch_source_poll_state(sid, last_polled_at='2026-09-06 15:00:00',
                                          config_remove=['mail_cursor'],
                                          expect_fields={'LastPolledAt': cutoff}) is False
        assert db.get_source(sid) == before, 'stale completion must not undo an owner rewind'
        assert db.patch_source_poll_state(sid, last_polled_at=cutoff)
        assert db.patch_source_poll_state(sid, last_polled_at=None)
        assert db.get_source(sid)['LastPolledAt'] is None
    finally:
        db.cx.close()
