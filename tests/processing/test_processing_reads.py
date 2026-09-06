"""Real-SQLite cutover and receipt preservation; no runtime activation or connectors."""
from datetime import datetime, timedelta
import json

import pytest

from taskuary import processing_reads
from taskuary.store import SQLiteStore


NOW = datetime.now().replace(microsecond=0).isoformat(sep=' ')
FUTURE = (datetime.fromisoformat(NOW) + timedelta(days=1)).isoformat(sep=' ')


@pytest.fixture
def db(tmp_path):
    store = SQLiteStore(str(tmp_path / 'reads.db'))
    yield store
    store.cx.close()


def message(db, name='source', task=None):
    return db.add_message(dict(TaskId=task, Channel='email', SourceName='synthetic@example.test',
        FromEmail='sender@example.test', Subject=name, BodyText='Complete source ' + name,
        SentAt=NOW, Status='filed'))


def item_id(db, mid):
    return db.resolve_processing_target('legacy_funnel', f'msg:{mid}')['item_id']


def picture(db, mid):
    return db.processing_snapshot(item_id(db, mid))


def activate(db):
    db.reconcile_processing_membership(fixed_now=NOW)
    return db.activate_processing_reads(fixed_now=NOW, live_state=[])


def owned_rows(db):
    names = [r[0] for r in db.cx.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'processing_%'")]
    return {name: [tuple(r) for r in db.cx.execute(f'SELECT * FROM "{name}"')] for name in names}


def test_activation_uses_fresh_uncapped_baseline_and_reopen_is_idempotent(db):
    ids = [message(db, str(n)) for n in range(507)]
    db.backfill_processing('old-foundation', fixed_now=NOW)
    db.set_funnel_state(f'msg:{ids[-1]}', 'surfaced')
    before = owned_rows(db)
    result = activate(db)
    assert result['version'] != 'old-foundation'
    assert db.processing_reads_active()
    assert owned_rows(db) == before
    assert len(db.processing_legacy_evidence(result['version'], entity_kind='message')) == 507
    assert processing_reads.state(picture(db, ids[-1]), NOW)['unread'] is False
    assert processing_reads.state(picture(db, ids[0]), NOW)['unread'] is True
    records = [tuple(r) for r in db.cx.execute('SELECT * FROM processing_read_receipt')]
    again = db.activate_processing_reads(fixed_now=FUTURE, live_state=[])
    assert again['version'] == result['version']
    assert again['status'] == 'already_active'
    assert [tuple(r) for r in db.cx.execute('SELECT * FROM processing_read_receipt')] == records
    peer = SQLiteStore(db.cx.execute('PRAGMA database_list').fetchone()[2])
    try:
        assert peer.processing_reads_active()
        assert processing_reads.state(picture(peer, ids[-1]), NOW)['unread'] is False
    finally:
        peer.cx.close()


def test_display_ack_and_clearing_legacy_rows_never_create_or_erase_receipts(db):
    old, fresh = message(db, 'old'), message(db, 'fresh')
    db.set_funnel_state(f'msg:{old}', 'surfaced')
    activate(db)
    for status in ('surfaced', 'ack'):
        db.set_funnel_state('processing:' + item_id(db, fresh), status)
        assert processing_reads.state(picture(db, fresh), NOW)['unread']
    db.clear_funnel_state(f'msg:{old}')
    db.clear_funnel_states(('surfaced', 'ack', 'done'))
    assert not processing_reads.state(picture(db, old), NOW)['unread']
    assert processing_reads.state(picture(db, fresh), NOW)['unread']


def test_done_records_current_members_and_new_activity_reopens_exact_content(db):
    tid = db.create_task({'Title': 'Synthetic grouped task'}, 'fixture')
    first = message(db, task=tid)
    rid = db.add_review(dict(TaskId=tid, MessageId=first, Kind='reply', DraftText='Draft'))
    activate(db)
    key = 'processing:' + item_id(db, first)
    db.set_funnel_state(key, 'done')
    initial = picture(db, first)
    assert not processing_reads.state(initial, NOW)['unread']
    assert {u['entity_kind'] for u in initial['view']['processing_read']['units']} == {'task', 'message', 'review'}
    db._exec('UPDATE review SET DraftText=? WHERE ReviewId=?', ('Refreshed unsent draft', rid))
    db._exec('UPDATE task SET Priority=? WHERE TaskId=?', ('urgent', tid))
    assert not processing_reads.state(picture(db, first), NOW)['unread']
    second = message(db, 'new arrival', task=tid)
    db.reconcile_processing_membership(fixed_now=NOW)
    assert item_id(db, second) == item_id(db, first)
    assert processing_reads.state(picture(db, first), NOW)['unread']
    db.set_funnel_state(key, 'done')
    db._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('New full source content', first))
    assert processing_reads.state(picture(db, first), NOW)['unread']


def test_historical_group_shells_preserve_message_verdicts(db):
    tid = db.create_task({'Title': 'Historical pending reply'}, 'fixture')
    mid = message(db, task=tid)
    rid = db.add_review(dict(TaskId=tid, MessageId=mid, Kind='reply', DraftText='Unsent'))
    db.set_funnel_state(f'review:{rid}', 'surfaced')
    activate(db)
    read = picture(db, mid)['view']['processing_read']
    assert len(read['units']) == 3
    assert all(u['read'] for u in read['units'])
    assert not processing_reads.state(picture(db, mid), NOW)['unread']


def test_active_deferral_survives_display_clear_and_new_member_then_expires(db):
    tid = db.create_task({'Title': 'Deferred'}, 'fixture')
    mid = message(db, task=tid)
    db.set_funnel_state(f'msg:{mid}', 'later', until=FUTURE)
    activate(db)
    key = 'processing:' + item_id(db, mid)
    db.set_funnel_state(key, 'surfaced')
    db.set_funnel_state(f'msg:{mid}', 'ack')
    db.clear_funnel_state(f'msg:{mid}')
    message(db, 'new deferred activity', task=tid)
    db.reconcile_processing_membership(fixed_now=NOW)
    value = processing_reads.state(picture(db, mid), NOW)
    assert value == dict(unread=True, deferred=True, defer_until=FUTURE)
    assert processing_reads.state(picture(db, mid), FUTURE) == dict(unread=True, deferred=False, defer_until=None)


def test_new_canonical_deferral_is_not_overwritten_by_surfaced(db):
    mid = message(db)
    activate(db)
    key = 'processing:' + item_id(db, mid)
    db.set_funnel_state(key, 'skip', until=FUTURE)
    db.set_funnel_state(key, 'surfaced')
    assert processing_reads.state(picture(db, mid), NOW) == dict(unread=True, deferred=True, defer_until=FUTURE)


def test_read_receipts_follow_exact_member_split_without_reading_its_new_neighbors(db):
    a = db.create_task({'Title': 'A'}, 'fixture')
    b = db.create_task({'Title': 'B'}, 'fixture')
    first, stay, other = message(db, 'move', a), message(db, 'stay', a), message(db, 'other', b)
    activate(db)
    old_root = item_id(db, first)
    db.set_funnel_state('processing:' + old_root, 'done')
    db._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (b, first))
    db.reconcile_processing_membership(fixed_now=NOW)
    assert item_id(db, first) != old_root == item_id(db, stay)
    moved = picture(db, first)['view']['processing_read']['units']
    assert next(u for u in moved if u['entity_kind'] == 'message' and u['local_id'] == str(first))['read']
    assert not next(u for u in moved if u['entity_kind'] == 'message' and u['local_id'] == str(other))['read']


def test_activation_rejects_dirty_generation_without_any_migration_or_receipt(db):
    mid = message(db)
    db.reconcile_processing_membership(fixed_now=NOW)
    peer = SQLiteStore(db.cx.execute('PRAGMA database_list').fetchone()[2])
    try:
        peer.set_funnel_state(f'msg:{mid}', 'surfaced')
        with pytest.raises(ValueError, match='reconciled'):
            db.activate_processing_reads(fixed_now=NOW, live_state=[])
        assert not db.processing_reads_active()
        assert not db.cx.execute('SELECT 1 FROM processing_migration').fetchone()
        activate(db)
        assert not processing_reads.state(picture(db, mid), NOW)['unread']
    finally:
        peer.cx.close()


def test_activation_failure_rolls_back_receipts_baseline_and_marker_then_retries(db, monkeypatch):
    mid = message(db)
    db.set_funnel_state(f'msg:{mid}', 'surfaced')
    db.reconcile_processing_membership(fixed_now=NOW)
    original = processing_reads.capture_legacy

    def fail_after_receipt(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('synthetic failure after receipt')

    with monkeypatch.context() as patch:
        patch.setattr(processing_reads, 'capture_legacy', fail_after_receipt)
        with pytest.raises(RuntimeError, match='after receipt'):
            db.activate_processing_reads(fixed_now=NOW, live_state=[])
    for table in ('processing_read_receipt', 'processing_read_activation', 'processing_migration',
                  'processing_legacy_evidence', 'processing_context_snapshot'):
        assert not db.cx.execute(f'SELECT 1 FROM {table}').fetchone()
    activate(db)
    assert not processing_reads.state(picture(db, mid), NOW)['unread']


def test_done_transaction_rolls_back_legacy_state_when_receipt_write_fails(db, monkeypatch):
    mid = message(db)
    activate(db)
    key = 'processing:' + item_id(db, mid)
    original = processing_reads.record

    def fail_after_record(*args, **kwargs):
        original(*args, **kwargs)
        raise RuntimeError('synthetic receipt failure')

    monkeypatch.setattr(processing_reads, 'record', fail_after_record)
    with pytest.raises(RuntimeError, match='receipt failure'):
        db.set_funnel_state(key, 'done')
    assert key not in db.funnel_states()
    assert not db.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()


def test_getters_do_not_write_or_change_content_revision_when_receipt_changes(db):
    mid = message(db)
    activate(db)
    before = picture(db, mid)
    writes = db.cx.total_changes
    assert processing_reads.state(before, NOW)['unread']
    assert picture(db, mid) == before
    assert db.cx.total_changes == writes
    db.set_funnel_state(f'msg:{mid}', 'done')
    after = picture(db, mid)
    assert after['context_revision'] == before['context_revision']
    assert after['view_revision'] != before['view_revision']
    assert not processing_reads.state(after, NOW)['unread']


def test_standalone_idea_task_review_historical_receipts_and_snooze(db):
    tid = db.create_task({'Title': 'Standalone task'}, 'fixture')
    rid = db.add_review(dict(Kind='action', DraftText='{"proposed":"value"}'))
    idea = db.upsert_idea({'key': 'synthetic-open', 'text': 'Own idea'}, NOW)
    snoozed = db.upsert_idea({'key': 'synthetic-snoozed', 'text': 'Later idea'}, NOW)
    db.set_funnel_state(f'agent:{tid}', 'surfaced')
    db.set_funnel_state(f'review:{rid}', 'done')
    db.set_funnel_state(f"idea:{idea['IdeaId']}", 'surfaced')
    db.set_idea_status(snoozed['IdeaId'], 'snoozed', 'owner', FUTURE)
    activate(db)
    for key in (f'agent:{tid}', f'review:{rid}', f"idea:{idea['IdeaId']}"):
        target = db.resolve_processing_target('legacy_funnel', key)['item_id']
        assert not processing_reads.state(db.processing_snapshot(target), NOW)['unread']
    target = db.resolve_processing_target('legacy_funnel', f"idea:{snoozed['IdeaId']}")['item_id']
    assert processing_reads.state(db.processing_snapshot(target), NOW) == dict(unread=True, deferred=True, defer_until=FUTURE)


def test_legacy_assistant_wrapper_deferral_is_retained_without_permanent_receipt(db):
    mid = db.add_message(dict(Channel='assistant', Subject='Synthetic suggestion',
                             BodyText='Full source', SentAt=NOW, Status='filed'))
    idea = db.upsert_idea({'key': 'deferred-wrapper', 'text': 'Independent idea'}, NOW)
    db.set_ideas_message([idea['IdeaId']], mid)
    db.set_brief(mid, json.dumps({'ideas': [{'id': idea['IdeaId']}]}))
    db.set_funnel_state(f"idea:{idea['IdeaId']}", 'later', until=FUTURE)
    activate(db)
    assert processing_reads.state(picture(db, mid), NOW) == dict(unread=True, deferred=True, defer_until=FUTURE)
    assert not db.cx.execute("SELECT 1 FROM processing_read_receipt WHERE EntityKind='message'").fetchone()


def test_working_receipt_retained_and_completed_run_content_is_new_activity(db):
    tid = db.create_task({'Title': 'Active worker'}, 'fixture')
    mid = message(db, task=tid)
    run = db.start_run(tid, 'synthetic-worker', 'Synthetic instruction', 'test')
    db.set_funnel_state(f'agent:{tid}', 'surfaced')
    db.reconcile_processing_membership(fixed_now=NOW)
    result = db.activate_processing_reads(fixed_now=NOW,
        live_state=[{'taskId': tid, 'agent': 'synthetic-worker', 'waiting': False}])
    evidence = db.processing_legacy_evidence(result['version'], entity_kind='message', local_id=mid)[0]
    assert evidence['observed_unread'] and evidence['permanent_read']
    assert not processing_reads.state(picture(db, mid), NOW)['unread']
    db._exec('UPDATE run SET Status=?,Result=? WHERE RunId=?', ('done', 'New completed result', run))
    assert processing_reads.state(picture(db, mid), NOW)['unread']


def test_unreconciled_legacy_target_cannot_succeed_without_a_receipt(db):
    activate(db)
    mid = message(db)
    with pytest.raises(ValueError, match='unavailable'):
        db.set_funnel_state(f'msg:{mid}', 'done')
    assert f'msg:{mid}' not in db.funnel_states()


def test_serial_store_writer_is_fenced_by_activation_without_reusing_legacy_display(db):
    mid = message(db)
    activate(db)
    peer = SQLiteStore(db.cx.execute('PRAGMA database_list').fetchone()[2])
    try:
        peer.set_funnel_state(f'msg:{mid}', 'surfaced')
        assert processing_reads.state(picture(db, mid), NOW)['unread']
        assert not db.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()
    finally:
        peer.cx.close()


def test_own_display_clear_and_done_keep_clean_census_but_never_clear_peer_dirt(db):
    mid = message(db)
    activate(db)
    key = 'processing:' + item_id(db, mid)
    db.set_funnel_state(key, 'surfaced')
    assert not db.processing_reconcile_status()['pending']
    db.clear_funnel_states(('surfaced',))
    assert not db.processing_reconcile_status()['pending']
    db.set_funnel_state(key, 'done')
    assert not db.processing_reconcile_status()['pending']
    assert not processing_reads.state(picture(db, mid), NOW)['unread']
    peer = SQLiteStore(db.cx.execute('PRAGMA database_list').fetchone()[2])
    try:
        peer._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('External changed source', mid))
        newcomer = message(peer, 'External new member')
        db.set_funnel_state(key, 'surfaced')
        db.clear_funnel_state(key)
        assert db.processing_reconcile_status()['pending']
        with pytest.raises(ValueError, match='reconciled'):
            db.set_funnel_state(key, 'done')
        assert db.resolve_processing_target('legacy_funnel', f'msg:{newcomer}') is None
        assert not db.cx.execute('''SELECT 1 FROM processing_member
            WHERE EntityKind='message' AND LocalId=?''', (str(newcomer),)).fetchone()
        assert processing_reads.state(picture(db, mid), NOW)['unread']
    finally:
        peer.cx.close()


def test_canonical_done_supersedes_retained_legacy_deferral(db):
    mid = message(db)
    db.set_funnel_state(f'msg:{mid}', 'later', until=FUTURE)
    activate(db)
    db.set_funnel_state('processing:' + item_id(db, mid), 'done')
    assert processing_reads.state(picture(db, mid), NOW) == dict(unread=False, deferred=False, defer_until=None)


def test_active_concierge_done_accepts_its_own_discussion_without_expanding_members(db, monkeypatch):
    from fastapi.testclient import TestClient
    from taskuary import concierge, funnel, general, server, terminal
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda store: [])
    tid = db.create_task({'Title': 'Synthetic task', 'Kind': 'general'}, 'fixture')
    mid = message(db, task=tid)
    general.dock_task(db, 'fixture')
    activate(db)
    key = 'processing:' + item_id(db, mid)
    members = list(db.cx.execute('SELECT * FROM processing_member'))
    funnel.invalidate()
    try:
        response = concierge.say(db, 'done', key=key, actor='fixture',
                                 llm=lambda *args, **kwargs: 'I can mark it handled.\nDECIDE: done')
        proposal = response['proposal']
        assert response['decision'] is None
        assert proposal['kind'] == 'item.settle' and proposal['params']['key'] == key
        assert db.get_task(tid)['Status'] == 'open'
        assert processing_reads.state(picture(db, mid), NOW)['unread']
        assert not db.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()
        assert db.processing_reconcile_status()['pending']
        assert db.cx.execute("SELECT 1 FROM comment WHERE TaskId=? AND ActorType='concierge_user'", (tid,)).fetchone()
        monkeypatch.setattr(server, 'store', db)
        client = TestClient(server.app)
        confirmed = client.post(f"/api/operations/{proposal['id']}/execute", json={'version': proposal['version']})
        assert confirmed.status_code == 200, confirmed.text
        assert confirmed.json()['status'] == 'done'
        assert db.get_task(tid)['Status'] == 'done'
        assert not processing_reads.state(picture(db, mid), NOW)['unread']
        assert list(db.cx.execute('SELECT * FROM processing_member')) == members
        receipts = [tuple(row) for row in db.cx.execute('SELECT * FROM processing_read_receipt')]
        repeated = client.post(f"/api/operations/{proposal['id']}/execute", json={'version': proposal['version']})
        assert repeated.status_code == 200 and repeated.json()['duplicate']
        assert [tuple(row) for row in db.cx.execute('SELECT * FROM processing_read_receipt')] == receipts
    finally:
        funnel.invalidate()


def test_settlement_savepoint_rejects_peer_move_and_rolls_back_identity_attempt(db):
    first_task = db.create_task({'Title': 'A'}, 'fixture')
    other_task = db.create_task({'Title': 'B'}, 'fixture')
    mid = message(db, task=first_task)
    activate(db)
    old = item_id(db, mid)
    members = [tuple(r) for r in db.cx.execute('SELECT * FROM processing_member')]
    db._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (other_task, mid))
    with pytest.raises(ValueError, match='reconciled'):
        db.set_funnel_state('processing:' + old, 'done')
    assert [tuple(r) for r in db.cx.execute('SELECT * FROM processing_member')] == members
    assert db.processing_reconcile_status()['pending']
    assert db.get_message(mid)['TaskId'] == other_task
    assert not db.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()


def test_calendar_historical_and_explicit_receipts_ignore_later_display(db):
    old, deferred, fresh = 'meeting:historical', 'meeting:deferred', 'meeting:new'
    db.set_funnel_state(old, 'surfaced')
    db.set_funnel_state(deferred, 'later', until=FUTURE)
    activate(db)
    states = db.processing_calendar_states()
    assert states[old]['read']
    assert states[deferred]['until'] == FUTURE and not states[deferred]['read']
    db.clear_funnel_states(('surfaced', 'later'))
    db.set_funnel_state(fresh, 'surfaced')
    assert fresh not in db.processing_calendar_states()
    db.set_funnel_state(fresh, 'skip', until=FUTURE)
    db.set_funnel_state(fresh, 'ack')
    assert db.processing_calendar_states()[fresh]['until'] == FUTURE
    db.set_funnel_state(fresh, 'done')
    db.set_funnel_state(fresh, 'surfaced')
    assert db.processing_calendar_states()[fresh] == {'read': True}
    assert db.processing_calendar_states()[old]['read']


def test_display_summary_refresh_is_bound_to_context_and_never_reads(db):
    mid = message(db)
    activate(db)
    key = 'processing:' + item_id(db, mid)
    before = picture(db, mid)
    db.set_funnel_state(key, 'surfaced', note='Synthetic model summary')
    fresh = picture(db, mid)
    expected = dict(Key=key, ContextRevision=before['context_revision'], Summary='Synthetic model summary')
    assert fresh['view']['processing_summaries'] == [expected]
    assert db.funnel_states()[key]['Note'] == expected['Summary']
    assert processing_reads.state(fresh, NOW)['unread']
    assert not db.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()
    assert fresh['context_revision'] == before['context_revision']
    assert fresh['view_revision'] != before['view_revision']
    writes = db.cx.total_changes
    assert picture(db, mid)['view']['processing_summaries'] == [expected]
    assert db.cx.total_changes == writes
    db._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('Changed substantive source', mid))
    changed = picture(db, mid)
    assert changed['view']['processing_summaries'] == [expected], 'old summary remains auditable'
    assert changed['context_revision'] != expected['ContextRevision'], 'consumer must drop stale summary'
    assert processing_reads.state(changed, NOW)['unread']


def test_display_summary_reopens_by_exact_legacy_alias_without_adding_a_receipt(db):
    mid = message(db)
    activate(db)
    key = f'msg:{mid}'
    db.set_funnel_state(key, 'surfaced', note='Alias-specific summary')
    path = db.cx.execute('PRAGMA database_list').fetchone()[2]
    peer = SQLiteStore(path)
    try:
        read = picture(peer, mid)
        assert read['view']['processing_summaries'] == [dict(Key=key,
            ContextRevision=read['context_revision'], Summary='Alias-specific summary')]
        assert processing_reads.state(read, NOW)['unread']
    finally:
        peer.cx.close()


def test_confirmation_context_is_checked_inside_receipt_writer_transaction(db):
    tid = db.create_task({'Title': 'Confirmed subject'}, 'fixture')
    mid = message(db, task=tid)
    activate(db)
    original = picture(db, mid)
    key = 'processing:' + original['item_id']
    expected = {original['item_id']: original['context_revision']}
    # The worker may have reconciled new arrivals before the old confirmation is clicked.
    second = message(db, 'Arrived after proposal', task=tid)
    db.reconcile_processing_membership(fixed_now=NOW)
    assert item_id(db, second) == original['item_id']
    with pytest.raises(ValueError, match='context changed'):
        db.set_funnel_state(key, 'done', expected_context=expected)
    assert key not in db.funnel_states()
    assert not db.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()
    current = picture(db, mid)
    db.set_funnel_state(key, 'done', expected_context={current['item_id']: current['context_revision']})
    assert not processing_reads.state(picture(db, mid), NOW)['unread']


def test_confirmation_rejects_missing_root_and_in_place_source_change_without_reading(db):
    mid = message(db)
    activate(db)
    original = picture(db, mid)
    key = 'processing:' + original['item_id']
    with pytest.raises(ValueError, match='context changed'):
        db.set_funnel_state(key, 'done', expected_context={})
    db._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('Changed after precheck', mid))
    with pytest.raises(ValueError, match='context changed'):
        db.set_funnel_state(key, 'done', expected_context={original['item_id']: original['context_revision']})
    assert db.processing_reconcile_status()['pending'], 'failed confirmation does not accept the pending census'
    assert key not in db.funnel_states()
    assert not db.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()
