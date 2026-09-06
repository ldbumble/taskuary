"""All and Unread share membership; display and ranking cannot create reads."""
from datetime import datetime, timedelta

import pytest

from taskuary import funnel, terminal, processing_all, processing_unread
from taskuary.funnel_selection import capture_selection
from taskuary.store import MemoryStore


@pytest.fixture
def store(monkeypatch):
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s: [])
    s.reconcile_processing_membership()
    s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[])
    funnel.invalidate()
    yield s
    funnel.invalidate()
    s.cx.close()


def add(s, title, *, tid=None, channel='email', status='filed', sent=None):
    return s.add_message({'ExternalId': title, 'ConversationId': title, 'TaskId': tid,
                          'Channel': channel, 'SourceName': 'fixture@example.test',
                          'FromName': 'Fixture', 'FromEmail': 'sender@example.test',
                          'Subject': title, 'BodyText': title, 'Status': status,
                          'SentAt': sent or datetime.now().isoformat(' ')})


def both(s):
    s.reconcile_processing_membership()
    now = datetime.now()
    snapshot = s.processing_inventory_snapshot(fixed_now=now.isoformat(), live_state=[])
    all_rows, _, _ = processing_all.compact_inventory(snapshot, processing_unread.query_for(s))
    unread = funnel.build(s, now=now, reconcile=False, live_state=[])
    return all_rows, unread


def test_uncapped_shared_inventory_keeps_categories_pending_and_old_provider_arrivals(store):
    store.set_setting('funnel_max', '3', 'test')
    store.set_setting('funnel_hours', '1', 'test')
    for index in range(505):
        add(store, f'Arrival {index:03}', status='ignored' if index % 2 else 'filed')
    add(store, 'Still triaging', status='triaging')
    old = add(store, 'Old provider date, new arrival', sent='2020-01-01 12:00:00')
    all_rows, unread = both(store)
    assert len(all_rows) == len(unread['items']) == 507
    assert {r['item_id'] for r in all_rows} == {r['processing_id'] for r in unread['items']}
    assert all(r['row']['Unread'] == 1 for r in all_rows)
    assert unread['hidden'] == 0
    assert next(r for r in unread['items'] if r['mid'] == old)['unread']
    pending = next(r for r in unread['items'] if r['title'] == 'Still triaging')
    assert pending['settling'] and not pending['actionable']
    capture = capture_selection(store)
    assert pending['key'] not in capture.member_keys
    assert len(capture.member_keys) == 4


def test_display_and_next_do_not_read_but_done_updates_shared_subset(store):
    add(store, 'First FYI')
    add(store, 'Second FYI')
    _, unread = both(store)
    first = unread['items'][0]
    funnel.settle(store, first['key'], 'surfaced', note='shown in chat')
    _, displayed = both(store)
    assert len(displayed['items']) == 2
    assert capture_selection(store).member_keys[0] == first['key']
    before = list(store.cx.iterdump())
    capture_selection(store, exclude=first['key'])
    assert list(store.cx.iterdump()) == before
    funnel.settle(store, first['key'], 'done')
    all_rows, unread = both(store)
    assert len(all_rows) == 2 and len(unread['items']) == 1
    assert {r['item_id'] for r in all_rows if r['row']['Unread']} == {r['processing_id'] for r in unread['items']}


def test_fyi_summary_survives_refresh_but_is_dropped_when_its_source_changes(store):
    mid = add(store, 'Summary subject')
    _, initial = both(store)
    key = initial['items'][0]['key']
    funnel.settle(store, key, 'surfaced', note='Summary of the original source')
    _, refreshed = both(store)
    assert refreshed['items'][0]['summary'] == 'Summary of the original source'
    assert refreshed['items'][0]['unread']
    store._exec('UPDATE message SET BodyText=? WHERE MessageId=?', ('New substantive information', mid))
    _, changed = both(store)
    assert changed['items'][0].get('summary') != 'Summary of the original source'
    assert changed['items'][0]['unread']
    assert not store.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()


def test_pre_cutover_fyi_current_resolves_its_exact_legacy_member_aliases(store):
    first = add(store, 'First preserved FYI')
    second = add(store, 'Second preserved FYI')
    both(store)
    legacy_key = f'fyis:msg:{first},msg:{second}'
    before = list(store.cx.iterdump())
    restored = funnel.next_item(store, legacy_key)
    assert restored['key'] == legacy_key
    assert [i['mid'] for i in restored['items']] == [first, second]
    assert all(i['processing_id'] for i in restored['items'])
    assert capture_selection(store, exclude=legacy_key).selected is None
    assert list(store.cx.iterdump()) == before


def test_confirmed_done_rejects_new_context_instead_of_reading_unseen_arrival(store):
    from taskuary import operations
    tid = store.create_task({'Title': 'Confirmed target', 'Status': 'open'}, 'test')
    add(store, 'Original confirmed source', tid=tid)
    _, pile = both(store)
    key = pile['items'][0]['key']
    proposal = operations.propose(store, 'item.settle', tid, {'key': key, 'verb': 'done', 'tid': tid})
    add(store, 'Unseen arrival after proposal', tid=tid)
    both(store)
    before = list(store.cx.iterdump())
    result = operations.execute(store, proposal['id'], proposal['version'],
                                lambda: pytest.fail('stale proposal cannot run its handler'))
    assert result['status'] == 'stale'
    assert list(store.cx.iterdump()) == before


def test_grouped_root_identity_survives_review_and_new_member_activity(store):
    tid = store.create_task({'Title': 'Shared task', 'Kind': 'general', 'Status': 'open'}, 'test')
    mid = add(store, 'Original request', tid=tid, status='routed')
    _, initial = both(store)
    key = initial['items'][0]['key']
    funnel.settle(store, key, 'done')
    add(store, 'New request on same task', tid=tid, status='routed')
    _, fresh = both(store)
    assert len(fresh['items']) == 1 and fresh['items'][0]['key'] == key
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'Draft'})
    _, pending = both(store)
    assert pending['items'][0]['key'] == key
    assert pending['items'][0]['rid'] == rid and pending['items'][0]['order_band'] == 2
    assert funnel.next_item(store, f'review:{rid}')['key'] == key
    assert pending['items'][0]['mid'] == mid, 'review target remains its exact older message'
    assert capture_selection(store, exclude=f'review:{rid}').selected is None


def test_source_filter_is_shared_with_selection_and_common_history(store):
    add(store, 'Email')
    add(store, 'Chat', channel='teams')
    both(store)
    scope = 'view:{"channel":"teams"}'
    selected = capture_selection(store, only=scope)
    snapshot = store.processing_inventory_snapshot(fixed_now=datetime.now().isoformat(), live_state=[])
    rows, _, _ = processing_all.compact_inventory(snapshot, processing_unread.query_for(store, scope))
    assert {r['item_id'] for r in rows} == {r['processing_id'] for r in selected.pile['items']}
    assert selected.selected['items'][0]['title'] == 'Chat'


def test_temporary_skip_is_shared_and_expires_without_becoming_a_read(store):
    add(store, 'Deferred information')
    _, pile = both(store)
    key = pile['items'][0]['key']
    funnel.settle(store, key, 'later', hours=1)
    all_rows, pile = both(store)
    assert len(all_rows) == 1 and not all_rows[0]['row']['Unread']
    assert all_rows[0]['row']['Deferred'] and not pile['items']
    later = datetime.now() + timedelta(hours=2)
    assert processing_unread.build(store, now=later, live_state=[])['items'][0]['key'] == key


def test_standing_sender_rule_filters_members_identically_without_hiding_other_members(store):
    import json
    tid = store.create_task({'Title': 'Mixed task', 'Kind': 'general', 'Status': 'open'}, 'test')
    muted_mid = add(store, 'Muted member', tid=tid)
    other_mid = add(store, 'Other member', tid=tid)
    store._exec('UPDATE message SET FromEmail=? WHERE MessageId=?', ('different@example.test', other_mid))
    store.set_setting('funnel_mutes', json.dumps([{'sender': 'sender@example.test'}]), 'test')
    all_rows, pile = both(store)
    assert len(all_rows) == len(pile['items']) == 1
    assert all_rows[0]['row']['MessageId'] == pile['items'][0]['mid'] == other_mid
    assert f'message:{muted_mid}' in all_rows[0]['member_ids']


def test_pending_review_on_a_filtered_out_member_cannot_be_approved_from_another_source(store):
    tid = store.create_task({'Title': 'Two sources', 'Status': 'open'}, 'test')
    mid = add(store, 'Mail requiring approval', tid=tid)
    other = add(store, 'Chat on same task', tid=tid, channel='teams')
    store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'Mail draft'})
    both(store)
    scoped = processing_unread.build(store, only='view:{"channel":"teams"}', live_state=[])['items'][0]
    assert scoped['mid'] == other and scoped.get('rid') is None


@pytest.mark.parametrize('agent', ['codex', 'claude'])
def test_working_to_waiting_uses_same_root_and_never_writes_read_state(store, agent):
    tid = store.create_task({'Title': 'Worker task', 'Kind': 'general', 'Status': 'open'}, 'test')
    add(store, 'Work source', tid=tid, status='routed')
    both(store)
    worker = {'taskId': tid, 'agent': agent, 'sid': 'synthetic-worker', 'waiting': False}
    before = list(store.cx.iterdump())
    working = processing_unread.build(store, live_state=[worker])['items'][0]
    waiting = processing_unread.build(store, live_state=[{**worker, 'waiting': True}])['items'][0]
    assert working['key'] == waiting['key']
    assert working['order_band'] == 5 and not working['actionable']
    assert waiting['order_band'] == 2 and waiting['actionable']
    assert list(store.cx.iterdump()) == before


def test_startup_backup_contains_legacy_reads_and_owner_documents(tmp_path):
    import sqlite3
    from pathlib import Path
    from taskuary.store import SQLiteStore
    from taskuary.processing_startup import initialize
    s = SQLiteStore(tmp_path / 'synthetic.sqlite')
    mid = add(s, 'Historical displayed item')
    s.set_funnel_state(f'msg:{mid}', 'surfaced', note='existing historical result')
    s._exec("UPDATE doc SET Content='Owner custom text', UpdatedBy='owner' WHERE Name='counsel'")
    result = initialize(s, live_state=[])
    with sqlite3.connect(result['backup']) as backup:
        assert backup.execute('SELECT Status FROM funnel_state WHERE Key=?', (f'msg:{mid}',)).fetchone()[0] == 'surfaced'
        assert backup.execute("SELECT Content FROM doc WHERE Name='counsel'").fetchone()[0] == 'Owner custom text'
    assert Path(result['backup']).with_suffix('.attachments.json').exists()
    assert not funnel.build(s, live_state=[])['items']
    assert initialize(s, live_state=[]) == {'status': 'already_active'}
    s.cx.close()
