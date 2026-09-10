"""PW-101/PW-104 additive canonical identity and legacy-baseline storage gates."""
import json
import sqlite3
import threading
from concurrent.futures import ThreadPoolExecutor

import pytest

from taskuary.store import SQLiteStore


NOW = '2026-09-06 12:00:00'


def legacy_stub(row, states, *, now, funnel_hours=12):
    """Small contract fake: production equivalence belongs to processing.py's focused tests."""
    required = {'MessageId', 'IngestedAt', 'Preview', 'MsgStatus', 'TaskStatus', 'ReviewId',
                'ReviewStatus', 'AnsweredAt', 'Working', 'AgentWaiting', 'LinkedIdeas', 'Category'}
    assert required <= set(row)
    open_ideas = [i for i in row['LinkedIdeas'] if i.get('Status') == 'open']
    if open_ideas: key = f"idea:{open_ideas[0]['IdeaId']}"
    elif row['ReviewStatus'] == 'pending' and row['ReviewId']: key = f"review:{row['ReviewId']}"
    elif row['Working'] and row['TaskId']: key = f"agent:{row['TaskId']}"
    elif row['Channel'] == 'report': key = f"report:{row['MessageId']}"
    else: key = f"msg:{row['MessageId']}"
    state = states.get(key) or {}
    status = state.get('Status')
    deferred = status in ('later', 'skip') and (not state.get('Until') or state['Until'] > now)
    permanent = status in ('surfaced', 'done')
    handled = permanent or deferred or row['TaskStatus'] in ('done', 'dropped') or bool(row['AnsweredAt'])
    if row['Working'] and not row['AgentWaiting'] and row['TaskStatus'] not in ('done', 'dropped'):
        handled = False
    return {'selected_key': key, 'observed_unread': not handled, 'permanent_read': permanent,
            'reasons': [status] if status else [],
            'deferral': {'status': status, 'until': state.get('Until')} if deferred else None,
            'raw_evidence': {'selected_state': state, 'linked_ideas': [i['IdeaId'] for i in open_ideas]}}


def add_message(store, *, task=None, channel='email', status='filed', subject='Synthetic', external=None,
                source='fixture-account', brief=None):
    return store.add_message({'TaskId': task, 'Channel': channel, 'Status': status,
                              'Subject': subject, 'BodyText': f'Complete body for {subject}',
                              'SentAt': NOW, 'ExternalId': external, 'SourceName': source,
                              'Brief': brief})


def test_constructor_is_additive_schema_only_and_preserves_legacy_rows(tmp_path):
    path = tmp_path / 'additive.db'
    store = SQLiteStore(str(path))
    mid = add_message(store, subject='Owner history')
    store.set_setting('fixture-owner-setting', 'unchanged', 'owner')
    store.save_doc('counsel', 'Owner custom COUNSEL', 'owner')
    before = (dict(store.cx.execute('SELECT * FROM message WHERE MessageId=?', (mid,)).fetchone()),
              store.get_doc('counsel'), store.get_settings()['fixture-owner-setting'])
    assert store.cx.execute('SELECT COUNT(*) FROM processing_item').fetchone()[0] == 0
    assert store.cx.execute('SELECT COUNT(*) FROM processing_migration').fetchone()[0] == 0
    store.cx.close()

    reopened = SQLiteStore(str(path))
    try:
        after = (dict(reopened.cx.execute('SELECT * FROM message WHERE MessageId=?', (mid,)).fetchone()),
                 reopened.get_doc('counsel'), reopened.get_settings()['fixture-owner-setting'])
        assert after == before
        assert reopened.cx.execute('SELECT COUNT(*) FROM processing_item').fetchone()[0] == 0
    finally: reopened.cx.close()


def test_uncapped_backfill_reopens_and_same_version_never_recaptures(tmp_path):
    path = tmp_path / 'uncapped.db'; store = SQLiteStore(str(path))
    store.save_doc('counsel', 'Keep this exact owner document.', 'owner')
    with store.lock:
        rows = [(f'fixture:{i}', 'email', 'fixture-account', f'Row {i}', NOW,
                 f'Full synthetic body {i}', 'filed', NOW) for i in range(507)]
        store.cx.executemany('''INSERT INTO message
            (ExternalId,Channel,SourceName,Subject,SentAt,BodyText,Status,CreatedAt) VALUES (?,?,?,?,?,?,?,?)''', rows)
        store.cx.commit()
    store._exec("UPDATE message SET Status='context' WHERE MessageId=507")
    store.set_funnel_state('msg:1', 'done', note='owner chose done')
    store.set_funnel_state('orphan:old-key', 'later', until='2026-09-07 12:00:00', note='keep dangling')
    legacy_before = ([tuple(r) for r in store.cx.execute('SELECT MessageId,BodyText,Status FROM message ORDER BY MessageId')],
                     [tuple(r) for r in store.cx.execute('SELECT * FROM funnel_state ORDER BY Key')],
                     store.get_doc('counsel'))
    result = store.backfill_processing('legacy-v1', fixed_now=NOW, evaluator=legacy_stub)
    assert result['status'] == 'complete'
    assert result['input_watermark']['message']['count'] == 507
    assert result['evidence'] == 508                 # every message + one unresolved state receipt
    assert result['unresolved_keys'] == ['orphan:old-key']
    assert legacy_before == (
        [tuple(r) for r in store.cx.execute('SELECT MessageId,BodyText,Status FROM message ORDER BY MessageId')],
        [tuple(r) for r in store.cx.execute('SELECT * FROM funnel_state ORDER BY Key')],
        store.get_doc('counsel'))
    first = store.processing_legacy_evidence('legacy-v1')
    excluded = next(x for x in first if x['entity_kind'] == 'message' and x['local_id'] == '507')
    assert excluded['observed_unread'] is None
    assert excluded['original']['row']['BodyText'] == 'Full synthetic body 506'
    store.cx.close()

    reopened = SQLiteStore(str(path))
    try:
        add_message(reopened, subject='Post-baseline write')
        again = reopened.backfill_processing('legacy-v1', fixed_now='2099-01-01 00:00:00', evaluator=lambda *_a, **_k: (_ for _ in ()).throw(AssertionError('must not recapture')))
        assert again['status'] == 'already_complete'
        assert again['input_watermark'] == result['input_watermark']
        assert reopened.processing_legacy_evidence('legacy-v1') == first
    finally: reopened.cx.close()


def test_backfill_failure_rolls_back_every_foundation_write_and_retry_succeeds(tmp_path):
    store = SQLiteStore(str(tmp_path / 'rollback.db'))
    add_message(store)
    with pytest.raises(RuntimeError, match='synthetic interruption'):
        store.backfill_processing('legacy-v1', fixed_now=NOW,
                                  evaluator=lambda *_a, **_k: (_ for _ in ()).throw(RuntimeError('synthetic interruption')))
    for table in ('processing_item', 'processing_member', 'processing_alias',
                  'processing_legacy_evidence', 'processing_migration'):
        assert store.cx.execute(f'SELECT COUNT(*) FROM {table}').fetchone()[0] == 0
    assert store.backfill_processing('legacy-v1', fixed_now=NOW, evaluator=legacy_stub)['status'] == 'complete'
    store.cx.close()


def test_two_connections_serialize_one_idempotent_baseline(tmp_path):
    path = tmp_path / 'concurrent.db'; seed = SQLiteStore(str(path)); add_message(seed); seed.cx.close()
    barrier = threading.Barrier(2)

    def capture():
        store = SQLiteStore(str(path)); barrier.wait()
        try: return store.backfill_processing('legacy-v1', fixed_now=NOW, evaluator=legacy_stub)
        finally: store.cx.close()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = [future.result() for future in (pool.submit(capture), pool.submit(capture))]
    assert {r['status'] for r in results} == {'complete', 'already_complete'}
    check = sqlite3.connect(path)
    try:
        assert check.execute('SELECT COUNT(*) FROM processing_migration').fetchone()[0] == 1
        assert check.execute('SELECT COUNT(*) FROM processing_legacy_evidence').fetchone()[0] == 1
    finally: check.close()


def test_legacy_aliases_resolve_the_exact_entity_and_ideas_stay_independent(tmp_path):
    store = SQLiteStore(str(tmp_path / 'identity.db'))
    tid = store.create_task({'Title': 'Synthetic task'}, 'fixture')
    report = add_message(store, task=tid, channel='report', subject='Synthetic digest')
    review = store.add_review({'TaskId': tid, 'MessageId': report, 'Kind': 'reply', 'Status': 'pending'})
    old_wrapper = add_message(store, channel='assistant', subject='Older wrapper')
    newer_wrapper = add_message(store, channel='assistant', subject='Newer wrapper')
    one = store.upsert_idea({'key': 'fixture-one', 'text': 'Independent idea one', 'kind': 'followup'}, NOW)
    two = store.upsert_idea({'key': 'fixture-two', 'text': 'Independent idea two', 'kind': 'followup'}, NOW)
    store.set_ideas_message([one['IdeaId'], two['IdeaId']], newer_wrapper)
    store.set_brief(old_wrapper, json.dumps({'ideas': [{'id': one['IdeaId']}, {'id': two['IdeaId']}]}))
    store.set_funnel_state(f'wrap:{tid}', 'done', note='standalone wrap receipt')
    store.backfill_processing('legacy-v1', fixed_now=NOW, evaluator=legacy_stub)

    msg = store.resolve_processing_target('legacy_funnel', f'msg:{report}')
    rep = store.resolve_processing_target('legacy_funnel', f'report:{report}')
    task = store.resolve_processing_target('legacy_funnel', f'task:{tid}')
    agent = store.resolve_processing_target('legacy_funnel', f'agent:{tid}')
    rev = store.resolve_processing_target('legacy_funnel', f'review:{review}')
    assert (msg['item_id'], rep['item_id'], task['item_id'], agent['item_id']) == (task['item_id'],) * 4
    assert (msg['entity_kind'], rep['entity_kind']) == ('message', 'message')
    assert (task['entity_kind'], agent['entity_kind'], rev['entity_kind']) == ('task', 'task', 'review')
    idea_one = store.resolve_processing_target('legacy_funnel', f"idea:{one['IdeaId']}")
    idea_two = store.resolve_processing_target('legacy_funnel', f"idea:{two['IdeaId']}")
    assert idea_one['item_id'] != idea_two['item_id']
    wrapper_evidence = store.processing_legacy_evidence('legacy-v1', entity_kind='message', local_id=str(newer_wrapper))[0]
    assert wrapper_evidence['selected_key'] == f"idea:{two['IdeaId']}"  # list_ideas historically sorts DESC
    wrap_receipt = store.processing_legacy_evidence('legacy-v1', entity_kind='legacy_state', local_id=f'wrap:{tid}')[0]
    assert wrap_receipt['original']['state']['Note'] == 'standalone wrap receipt'
    relations = store.cx.execute('SELECT FromLocalId,ToLocalId FROM processing_relation ORDER BY RelationId').fetchall()
    assert (str(old_wrapper), str(one['IdeaId'])) in [tuple(r) for r in relations]
    assert (str(newer_wrapper), str(one['IdeaId'])) in [tuple(r) for r in relations]
    assert not store.cx.execute("SELECT 1 FROM processing_alias WHERE Namespace='external_id'").fetchone()
    store.cx.close()


def test_backfill_adapter_preserves_due_note_and_closed_worker_enrichment(tmp_path):
    store = SQLiteStore(str(tmp_path / 'adapter.db'))
    note = store.create_task({'Title': 'Due note', 'Kind': 'note', 'Status': 'open'}, 'fixture')
    closed = store.create_task({'Title': 'Closed work', 'Status': 'done'}, 'fixture')
    note_mid = add_message(store, task=note, subject='Due now')
    closed_mid = add_message(store, task=closed, subject='Already closed')
    seen = {}

    def capture(row, states, **kwargs):
        seen[row['MessageId']] = dict(row)
        return legacy_stub(row, states, **kwargs)

    store.backfill_processing('legacy-v1', fixed_now=NOW, evaluator=capture, live_state=[
        {'taskId': closed, 'agent': 'synthetic-worker', 'waiting': True}])
    assert seen[note_mid]['NeedsYou'] == 1
    assert seen[closed_mid]['Working'] is None
    assert seen[closed_mid]['AgentWaiting'] is False
    store.cx.close()


def test_reconciliation_requires_provider_scope_reuses_fyi_item_and_keeps_accounts_separate(tmp_path):
    store = SQLiteStore(str(tmp_path / 'reconcile.db'))
    fyi = store.reconcile_processing_entities(kind='message', members=[
        {'entity_kind': 'message', 'local_id': 'future-message', 'role': 'primary'}], fixed_now=NOW)
    reused = store.reconcile_processing_entities(kind='task', item_id=fyi, members=[
        {'entity_kind': 'message', 'local_id': 'future-message'},
        {'entity_kind': 'task', 'local_id': 'future-task'}], fixed_now=NOW)
    assert reused == fyi
    assert {m['EntityKind'] for m in store.processing_members(fyi)} == {'message', 'task'}

    for local_id, scope in (('account-a-message', 'connector:11'), ('account-b-message', 'connector:22')):
        store.reconcile_processing_entities(kind='message', members=[
            {'entity_kind': 'message', 'local_id': local_id}], aliases=[{
                'namespace': 'external_id', 'scope': scope, 'value': 'same-provider-id',
                'entity_kind': 'message', 'local_id': local_id, 'provenance': 'connector-receipt'}])
    a = store.resolve_processing_target('external_id', 'same-provider-id', 'connector:11')
    b = store.resolve_processing_target('external_id', 'same-provider-id', 'connector:22')
    assert a['item_id'] != b['item_id']
    assert store.resolve_processing_target('external_id', 'same-provider-id') is None
    store.cx.close()


def test_later_baseline_reuses_a_sole_fyi_item_when_it_gains_a_task(tmp_path):
    store = SQLiteStore(str(tmp_path / 'later-baseline.db'))
    mid = add_message(store, subject='FYI which later became work')
    store.backfill_processing('legacy-v1', fixed_now=NOW, evaluator=legacy_stub)
    original = store.resolve_processing_target('legacy_funnel', f'msg:{mid}')['item_id']
    tid = store.create_task({'Title': 'Converted FYI'}, 'owner')
    store._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (tid, mid))

    result = store.backfill_processing('legacy-v2', fixed_now='2026-09-06 13:00:00', evaluator=legacy_stub)
    assert result['status'] == 'complete'
    assert store.resolve_processing_target('legacy_funnel', f'task:{tid}')['item_id'] == original
    assert store.resolve_processing_target('legacy_funnel', f'msg:{mid}')['item_id'] == original
    assert {e['migration_version'] for e in store.processing_snapshot(original)['legacy_evidence']} == {
        'legacy-v1', 'legacy-v2'}
    store.cx.close()


def test_explicit_merge_preserves_redirect_members_alias_receipts_and_source_evidence(tmp_path):
    store = SQLiteStore(str(tmp_path / 'merge.db'))
    mid = add_message(store, subject='Pre-merge source evidence')
    store.set_funnel_state(f'msg:{mid}', 'done', note='exact pre-merge receipt')
    store.backfill_processing('legacy-v1', fixed_now=NOW, evaluator=legacy_stub)
    source = store.resolve_processing_target('legacy_funnel', f'msg:{mid}')['item_id']
    store.reconcile_processing_entities(kind='message', item_id=source, members=[
        {'entity_kind': 'message', 'local_id': str(mid)}],
        context_revision='old-context', view_revision='old-view')
    target = store.reconcile_processing_entities(kind='task', members=[
        {'entity_kind': 'task', 'local_id': 'target', 'role': 'primary'}])
    assert store.merge_processing_items(source, target, fixed_now=NOW) == target
    resolved = store.resolve_processing_target('legacy_funnel', f'msg:{mid}')
    assert (resolved['item_id'], resolved['entity_kind'], resolved['local_id']) == (target, 'message', str(mid))
    snap = store.processing_snapshot(source)
    assert {i['ItemId'] for i in snap['item_history']} == {source, target}
    assert any(m['ItemId'] == source and m['RetiredAt'] for m in snap['member_history'])
    assert any(m['ItemId'] == target and m['EntityKind'] == 'message' for m in snap['members'])
    assert len({a['AliasId'] for a in snap['aliases']}) == len(snap['aliases'])
    assert [(e['item_id'], e['selected_key'], e['reasons']) for e in snap['legacy_evidence']] == [
        (source, f'msg:{mid}', ['done'])]
    assert store.processing_snapshot(target)['legacy_evidence'] == snap['legacy_evidence']
    assert snap['item']['ContextRevision'] is None and snap['item']['ViewRevision'] is None
    store.cx.close()
