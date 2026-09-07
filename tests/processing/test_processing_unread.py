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


def test_shown_in_chat_is_read_and_leaves_unread_and_next(store):
    """The owner's rule (2026-09-06): once an item has been put in the chat it is read, period.
    Only later/skip keep it unread, until their time."""
    add(store, 'First FYI')
    add(store, 'Second FYI')
    _, unread = both(store)
    first, second = unread['items'][0], unread['items'][1]
    funnel.settle(store, first['key'], 'surfaced', read=True)
    all_rows, displayed = both(store)
    assert [i['key'] for i in displayed['items']] == [second['key']]
    assert capture_selection(store).member_keys[0] == second['key']
    assert {r['item_id']: r['row']['Unread'] for r in all_rows} == {first['processing_id']: 0, second['processing_id']: 1}
    assert [r[0] for r in store.cx.execute("SELECT DISTINCT Origin FROM processing_read_receipt")] == ['surfaced']
    # the legacy write (no read flag) still only marks: historical fixtures and direct callers are unchanged
    funnel.settle(store, second['key'], 'surfaced')
    _, still = both(store)
    assert [i['key'] for i in still['items']] == [second['key']]


def test_words_said_about_a_task_do_not_make_it_unread_again_but_an_agents_do(store):
    """Next marked the task read at 21:12:45; the assistant's mirrored introduction landed as a comment
    at 21:12:46 and the task was unread again (2026-09-06)."""
    tid = store.create_task({'Title': 'User changes'}, 'fixture')
    add(store, 'Please change the users', tid=tid, status='routed')
    _, unread = both(store)
    key = unread['items'][0]['key']
    funnel.settle(store, key, 'surfaced', read=True)
    with store.processing_own_words(tid, 'Taskuary'):
        store.add_comment(tid, 'Taskuary', 'concierge_assistant', 'Your User changes task is still open.')
    _, after = both(store)
    assert after['items'] == [], 'the assistant talking about it is not news'
    store.add_comment(tid, 'coder', 'agent', 'Finished: users changed, PR opened.')
    _, news = both(store)
    assert [i['key'] for i in news['items']] == [key], 'an agent reporting back IS news'


def test_later_keeps_it_unread_until_its_time_then_it_comes_back(store):
    add(store, 'Sleep on it')
    _, unread = both(store)
    key = unread['items'][0]['key']
    funnel.settle(store, key, 'later', hours=2)
    _, now = both(store)
    assert now['items'] == []
    later = funnel.build(store, now=datetime.now() + timedelta(hours=3), reconcile=False, live_state=[])
    assert [i['key'] for i in later['items']] == [key] and later['items'][0]['unread']
    assert not store.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()


def test_shown_approval_stays_unread_but_marked_so_next_does_not_bounce_back(store):
    tid = store.create_task({'Title': 'Waiting on a yes'}, 'fixture')
    mid = add(store, 'Please reply', tid=tid, status='routed')
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'Draft'})
    add(store, 'Plain FYI')
    _, unread = both(store)
    approve = next(i for i in unread['items'] if i.get('rid') == rid)
    assert approve['lane'] == 'approve'
    funnel.settle(store, approve['key'], 'surfaced', read=approve['lane'] not in ('approve', 'blocked'))
    _, shown = both(store)
    kept = next(i for i in shown['items'] if i.get('rid') == rid)
    assert kept['unread'] and kept['surfaced'] and kept['surfaced_at']
    assert capture_selection(store).selected['key'] != approve['key'], 'just shown: Next moves to the FYI'
    assert not store.cx.execute('SELECT 1 FROM processing_read_receipt').fetchone()


def test_assistant_digest_post_does_not_duplicate_its_own_idea(store):
    """The old funnel hid an Assistant digest whose ideas are cards of their own (the 2026-09-04
    duplicate-Assistant regression). The canonical Unread must do the same."""
    import json
    stamp = datetime.now().isoformat(' ')
    mid = add(store, 'End of day checkup fired on its own', channel='assistant', status='feed')
    idea = store.upsert_idea({'key': 'idea:eod', 'kind': 'idea', 'text': 'End of day checkup fired on its own',
                              'action': {'type': 'message', 'mid': mid, 'section': 'systems'}}, stamp)
    store.set_ideas_message([idea['IdeaId']], mid)
    store.set_brief(mid, json.dumps({'ideas': [{'id': idea['IdeaId']}]}))
    add(store, 'A plain Assistant note', channel='assistant', status='feed')
    all_rows, unread = both(store)
    # All shows one row for it too - the owner saw both there as well (2026-09-06)
    assert sorted(r['open_target']['kind'] for r in all_rows) == ['idea', 'message']
    kinds = sorted((i['kind'], i['title']) for i in unread['items'])
    assert kinds == [('fyi', 'A plain Assistant note'), ('idea', 'End of day checkup fired on its own')], kinds
    # the one row that remains says who is talking - the owner saw "unknown" on it (2026-09-06)
    assert next(i for i in unread['items'] if i['kind'] == 'idea')['who'] == 'Assistant'


def test_the_message_an_idea_rides_into_triage_on_is_never_a_row(store):
    """assistant._idea_message writes one message per idea, external id idea:<n>, so the verdict has
    something to hang off. It is a VEHICLE: showing it beside the idea it carries is one thought as
    two rows, and the one you could open said nothing (the owner, 2026-09-07: "still duplicating
    this in timeline?? and when you click on message it says nothing")."""
    stamp = datetime.now().isoformat(' ')
    source = add(store, 'FW: AI Modus', status='filed')
    idea = store.upsert_idea({'key': 'idea:empty-forward', 'kind': 'idea', 'action': {'type': 'message', 'mid': source},
                              'text': 'Hindy forwarded "FW: AI Modus" with nothing but her signature'}, stamp)
    vehicle = store.add_message({'ExternalId': f"idea:{idea['IdeaId']}", 'ConversationId': f"idea:{idea['IdeaId']}",
                                 'Channel': 'assistant', 'SourceName': 'Assistant', 'FromName': 'Assistant',
                                 'Subject': 'Assistant idea: Hindy forwarded "FW: AI Modus"',
                                 'BodyText': 'Hindy forwarded it with nothing but her signature', 'Status': 'filed',
                                 'SentAt': stamp})
    all_rows, unread = both(store)
    assert vehicle not in {r['row'].get('MessageId') for r in all_rows}, 'the vehicle is not a row in All'
    assert vehicle not in {i.get('mid') for i in unread['items']}, 'nor in work'
    # ...and what it carried still speaks, beside the mail it is about
    assert sorted(i['kind'] for i in unread['items']) == ['fyi', 'idea']
    assert next(i for i in unread['items'] if i['kind'] == 'idea')['idea'] == idea['IdeaId']


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


def test_a_confirmed_send_leaves_unread_and_stays_in_all(store):
    """PW-149: the reply really left, so the item is answered. It drops out of Unread on the same
    pass that closed its task, and All still carries it - a sent answer is history, not a hole."""
    from taskuary import verdicts
    tid = store.create_task({'Title': 'Please reply', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
    mid = add(store, 'Please reply', tid=tid, status='routed')
    rid = store.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'Draft'})
    all_rows, unread = both(store)
    assert next(i for i in unread['items'] if i.get('rid') == rid)['lane'] == 'approve'
    assert mid in {r['row']['MessageId'] for r in all_rows}
    verdicts._settle_task_after_sent_reply(store, store.get_review(rid), 'owner', True)
    store.decide_review(rid, 'approved', 'Draft', 'owner')
    assert store.get_task(tid)['Status'] == 'done'
    all_after, after = both(store)
    assert [i for i in after['items'] if i.get('mid') == mid] == [], 'a sent reply is out of Unread'
    assert mid in {r['row']['MessageId'] for r in all_after}, 'and still in All'


def test_closing_a_task_takes_its_row_out_of_unread_and_a_later_reply_brings_it_back(store):
    """The owner closed the task and its mail row stayed in the pipe as an fyi (the owner, 2026-09-07:
    "it should just go off the unread timeline"). The close is the decision; a reply after it is new."""
    from taskuary import concierge
    tid = store.create_task({'Title': 'Proof runners', 'Kind': 'coding', 'Status': 'open'}, 'fixture')
    mid = add(store, 'Proof runners', tid=tid, channel='github', status='routed')
    _, before = both(store)
    assert [i for i in before['items'] if i.get('mid') == mid], 'it starts in Unread'
    assert concierge.close_task(store, tid, 'owner')
    _, after = both(store)
    assert [i for i in after['items'] if i.get('mid') == mid] == [], 'a closed task is off the rail'
    add(store, 'Proof runners follow-up', tid=tid, channel='github', status='routed',
        sent=(datetime.now() + timedelta(minutes=1)).isoformat(' '))
    _, later = both(store)
    assert [i for i in later['items'] if i['tid'] == tid], 'but a new arrival on it is unread again'


def test_a_task_closed_before_this_shipped_also_leaves_unread(store):
    """The row the owner was looking at was closed by a road that wrote no read receipt, so the fix
    has to read the fact rather than wait for the next close. Mail that arrives after the close is
    still new: closing a task ends the work on it, it does not deafen the thread."""
    tid = store.create_task({'Title': 'Already closed', 'Kind': 'coding', 'Status': 'open'}, 'fixture')
    mid = add(store, 'Already closed', tid=tid, status='routed')
    both(store)
    store.update_task(tid, {'Status': 'done'}, 'owner')        # no settle: the close roads before today
    _, after = both(store)
    assert [i for i in after['items'] if i.get('mid') == mid] == []
    add(store, 'They wrote back after it closed', tid=tid, status='routed',
        sent=(datetime.now() + timedelta(minutes=1)).isoformat(' '))
    _, later = both(store)
    assert [i for i in later['items'] if i['tid'] == tid], 'a reply after the close is unread again'


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


def test_waiting_selection_ignores_idle_clock_but_retains_worker_facts(store, monkeypatch):
    tid = store.create_task({'Title': 'Stable waiting worker', 'Kind': 'general', 'Status': 'open'}, 'test')
    add(store, 'Waiting worker source', tid=tid, status='routed')
    both(store)
    now = datetime.now()
    base = {'taskId': tid, 'agent': 'codex', 'sid': 'isolated-waiter',
            'started': now.timestamp(), 'waiting': True, 'phase': 'parked',
            'idle': 100, 'tail': ['Waiting for approval'],
            'request': {'request_id': 'question-1', 'kind': 'input_needed',
                        'text': 'Approve the change?', 'choices': ['yes', 'no'], 'at': now.isoformat()}}
    worker = dict(base)
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [dict(worker)])
    monkeypatch.setattr(terminal, 'asking_lines', lambda sid, lines: [])
    before = list(store.cx.iterdump())
    initial = capture_selection(store, now=now)
    assert initial.selected['tid'] == tid and initial.selected['lane'] == 'blocked'
    worker['idle'] = 101
    elapsed = capture_selection(store, now=now)
    assert elapsed.revision == initial.revision
    assert elapsed.selected['view_revision'] == initial.selected['view_revision']
    assert elapsed.selected['presentation_revision'] == initial.selected['presentation_revision']
    for changed in ({'waiting': False}, {'phase': 'working'},
                    {'request': base['request'] | {'text': 'Approve the revised change?'}},
                    {'tail': ['Different substantive output']}, {'sid': 'replacement-session'}):
        worker.clear()
        worker.update(base | changed)
        assert capture_selection(store, now=now).revision != initial.revision, changed
    worker.clear()
    worker.update(base)
    worker.pop('waiting')
    assert capture_selection(store, now=now).revision == initial.revision
    worker['idle'] = terminal.IDLE_WAITING - 1
    working = capture_selection(store, now=now)
    assert working.selected is None and working.pending['working'] == 1
    worker['idle'] = terminal.IDLE_WAITING
    waiting = capture_selection(store, now=now)
    assert waiting.selected['key'] == initial.selected['key']
    assert waiting.revision != working.revision
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


def test_window_and_full_history_snapshots_stay_cached_side_by_side(store):
    """One click alternates the Unread window with the named-item history lookup; a single-entry
    cache made each evict the other, so every build was cold (2026-09-06: "why does this take 15 seconds")."""
    add(store, 'Recent')
    store.reconcile_processing_membership()
    now = datetime.now()
    processing_unread.build(store, now=now, live_state=[])
    processing_unread.build(store, now=now, live_state=[], include_read=True, full_history=True)
    assert len(store._processing_display_cache) == 2
    calls = []
    orig = store.processing_inventory_snapshot
    def spy(**kw):
        before = dict(store._processing_display_cache); out = orig(**kw)
        calls.append(dict(store._processing_display_cache) == before); return out
    store.processing_inventory_snapshot = spy
    processing_unread.build(store, now=now, live_state=[])
    processing_unread.build(store, now=now, live_state=[], include_read=True, full_history=True)
    assert calls == [True, True], 'both windows were served from the cache'


def test_named_lookup_reads_the_unread_window_first_and_only_then_the_whole_history(store):
    recent = add(store, 'Recent named item')
    old = add(store, 'Ancient named item', sent='2020-01-01 09:00:00')
    store._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', ('2020-01-01 09:00:00', old))
    store.reconcile_processing_membership()
    windows = []
    orig = store.processing_inventory_snapshot
    def spy(**kw): windows.append(kw.get('history_days')); return orig(**kw)
    store.processing_inventory_snapshot = spy
    item = funnel.next_item(store, f'msg:{recent}')
    assert item and item['mid'] == recent
    assert windows and all(w < 36500 for w in windows), windows
    windows.clear()
    item = funnel.next_item(store, f'msg:{old}')
    assert item and item['mid'] == old
    assert 36500 in windows
