"""Real-store lifecycle gates for the canonical All consumer."""
import asyncio
import copy
import json
import threading
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import processing_all, server
from taskuary.store import SQLiteStore


NOW = '2026-09-06 12:00:00'


def _message(store, text, *, task=None, body=None):
    mid = store.add_message({
        'TaskId': task, 'ExternalId': f'lifecycle:{text}', 'Channel': 'email',
        'SourceName': 'fixture@example.test', 'Subject': text,
        'BodyText': body or f'{text} full body', 'SentAt': NOW, 'Status': 'filed',
    })
    store._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (NOW, mid))
    return mid


def _item_for_member(store, member_id, *, live_state=None):
    page = processing_all.AllInventory().page(store, fixed_now=NOW, live_state=live_state)
    return next(row for row in page['items'] if member_id in row['member_ids'])


def test_pending_membership_rejects_detail_before_a_moved_message_can_show_old_task(tmp_path):
    store = SQLiteStore(str(tmp_path / 'pending-detail.db'))
    try:
        first = store.create_task({'Title': 'First task', 'Status': 'open'}, 'fixture')
        second = store.create_task({'Title': 'Second task', 'Status': 'open'}, 'fixture')
        mid = _message(store, 'Move between tasks', task=first)
        store.reconcile_processing_membership(fixed_now=NOW)
        selected = _item_for_member(store, f'message:{mid}')

        store._exec('UPDATE message SET TaskId=? WHERE MessageId=?', (second, mid))
        state = store.processing_reconcile_status()
        assert state['pending'] is True
        assert state['dirty_generation'] > state['reconciled_generation']

        with mock.patch.object(server, 'store', store), \
             mock.patch.object(server, '_processing_live', return_value=[]):
            client = TestClient(server.app)
            response = client.get(
                f"/api/processing/items/{selected['item_id']}/detail",
                params={'kind': 'message', 'id': mid,
                        'view_revision': selected['view_revision']})
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'processing_coverage_pending'
        assert store.get_message(mid)['TaskId'] == second

        store.reconcile_processing_membership(fixed_now='2026-09-06 12:01:00')
        with mock.patch.object(server, 'store', store), \
             mock.patch.object(server, '_processing_live', return_value=[]):
            response = TestClient(server.app).get(
                f"/api/processing/items/{selected['item_id']}/detail",
                params={'kind': 'message', 'id': mid})
        assert response.status_code == 409
        assert response.json()['detail']['code'] == 'processing_target_moved'
    finally:
        store.cx.close()


def test_membership_worker_observes_external_sqlite_write_notifies_and_recovers(tmp_path):
    path = tmp_path / 'external-worker.db'
    store = SQLiteStore(str(path))
    peer = None
    worker = None
    try:
        mid = _message(store, 'External mutation', body='before external write')
        store.reconcile_processing_membership(fixed_now=NOW)
        peer = SQLiteStore(str(path))
        peer._exec('UPDATE message SET BodyText=? WHERE MessageId=?',
                   ('after external write', mid))
        assert store.processing_reconcile_status()['pending'] is True

        notified = threading.Event()
        reports = []

        def notify(result):
            reports.append(result)
            notified.set()

        worker = processing_all.MembershipWorker(store, interval=0.01, notify=notify)
        worker.start()
        assert notified.wait(3), 'membership worker did not observe committed peer write'
        worker.close()
        worker = None

        assert reports[-1]['status'] == 'complete'
        assert reports[-1]['pending'] is False
        assert store.processing_reconcile_status()['pending'] is False
        selected = _item_for_member(store, f'message:{mid}')
        detail = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])
        assert detail['row']['BodyText'] == 'after external write'
    finally:
        if worker is not None:
            worker.close()
        if peer is not None:
            peer.cx.close()
        store.cx.close()


def test_detail_preserves_unavailable_empty_and_supplied_native_session_states(tmp_path):
    store = SQLiteStore(str(tmp_path / 'native-session.db'))
    try:
        task = store.create_task({'Title': 'Worker task', 'Status': 'in_progress'}, 'fixture')
        mid = _message(store, 'Worker-backed message', task=task)
        store.reconcile_processing_membership(fixed_now=NOW)
        selected = _item_for_member(store, f'message:{mid}', live_state=[])

        unavailable = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid)
        observed_empty = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])
        session = {'taskId': task, 'sid': 'fixture-session', 'agent': 'coder',
                   'waiting': True, 'question': {'text': 'Choose a safe path'}}
        supplied = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid,
            live_state=[session])

        assert unavailable['detail']['session_available'] is False
        assert unavailable['detail']['session'] is None
        assert observed_empty['detail']['session_available'] is True
        assert observed_empty['detail']['session'] is None
        assert supplied['detail']['session_available'] is True
        assert supplied['detail']['session'] == session
        assert len({unavailable['view_revision'], observed_empty['view_revision'],
                    supplied['view_revision']}) == 3
    finally:
        store.cx.close()


def test_dangling_message_task_is_truthfully_hydrated_as_standalone(tmp_path):
    store = SQLiteStore(str(tmp_path / 'dangling-task.db'))
    try:
        mid = _message(store, 'Dangling task message', task=999999,
                       body='Complete standalone body survives')
        reconciled = store.reconcile_processing_membership(fixed_now=NOW)
        assert reconciled['status'] == 'complete'
        assert any(row['code'] == 'dangling_message_task'
                   for row in reconciled['diagnostics'])
        selected = _item_for_member(store, f'message:{mid}', live_state=[])

        detail = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])

        assert detail['row']['BodyText'] == 'Complete standalone body survives'
        assert detail['detail']['task'] is None
        assert detail['detail']['messages'][0]['MessageId'] == mid
        assert detail['detail']['comments'] == []
        assert detail['detail']['runs'] == []
    finally:
        store.cx.close()


def test_native_session_generator_is_consumed_once_and_detached_from_caller(tmp_path):
    store = SQLiteStore(str(tmp_path / 'native-generator.db'))
    try:
        task = store.create_task({'Title': 'Generator task', 'Status': 'in_progress'}, 'fixture')
        mid = _message(store, 'Generator-backed message', task=task)
        store.reconcile_processing_membership(fixed_now=NOW)
        selected = _item_for_member(store, f'message:{mid}', live_state=[])
        original = {'taskId': task, 'sid': 'one-shot', 'agent': 'coder', 'waiting': True,
                    'question': {'text': 'Original nested question'}}
        consumed = 0

        def one_shot():
            nonlocal consumed
            consumed += 1
            if consumed > 1:
                raise AssertionError('native generator was consumed more than once')
            yield original

        generated = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid,
            live_state=one_shot())
        expected = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid,
            live_state=[copy.deepcopy(original)])
        original['question']['text'] = 'Caller mutated after hydration'

        assert consumed == 1
        assert generated['view_revision'] == expected['view_revision']
        assert generated['detail']['session']['question']['text'] == 'Original nested question'
        assert generated['detail']['session_available'] is True
    finally:
        store.cx.close()


def test_membership_lifecycle_yields_before_initial_work_and_joins_when_cancelled(monkeypatch):
    entered = threading.Event()
    release = threading.Event()
    close_entered = threading.Event()
    reconcile_threads = []

    class HeldStore:
        def processing_reconcile_status(self):
            reconcile_threads.append(threading.current_thread().name)
            entered.set()
            assert release.wait(3), 'test did not release initial reconciliation'
            return {'dirty_generation': 1, 'attempted_generation': 0}

        def reconcile_processing_membership(self):
            return {'status': 'complete'}

    real_worker = processing_all.MembershipWorker

    class ObservedWorker(real_worker):
        def close(self):
            close_entered.set()
            return super().close()

    monkeypatch.setattr(processing_all, 'MembershipWorker', ObservedWorker)
    monkeypatch.setattr('taskuary.live.emit', mock.Mock())

    async def exercise():
        yielded = asyncio.Event()

        async def use_lifecycle():
            async with processing_all.membership_lifecycle(HeldStore()):
                yielded.set()
                await asyncio.Event().wait()

        task = asyncio.create_task(use_lifecycle())
        await yielded.wait()
        assert await asyncio.to_thread(entered.wait, 2)
        assert reconcile_threads == ['processing-membership']
        task.cancel()
        assert await asyncio.to_thread(close_entered.wait, 2)
        assert not task.done(), 'cancelled lifecycle abandoned its owned reconciliation thread'
        release.set()
        try:
            await task
        except asyncio.CancelledError:
            pass
        else:
            raise AssertionError('lifecycle cancellation was swallowed')

    asyncio.run(exercise())


def test_membership_worker_failure_uses_backoff_before_retrying():
    waits = []

    class FailingStore:
        def processing_reconcile_status(self):
            raise RuntimeError('synthetic reconciliation failure')

    class OneWait:
        def is_set(self):
            return False

        def wait(self, delay):
            waits.append(delay)
            return True

        def set(self):
            pass

    worker = processing_all.MembershipWorker(FailingStore(), interval=0.01)
    worker.stop = OneWait()
    worker.start()
    worker.thread.join(2)
    assert not worker.thread.is_alive()
    assert waits == [5.0]


def test_nullable_review_kind_and_note_time_match_legacy_display_semantics(tmp_path):
    store = SQLiteStore(str(tmp_path / 'nullable-display.db'))
    try:
        reply_task = store.create_task({
            'Title': 'Nullable approved review', 'Kind': 'reply', 'Status': 'open'}, 'fixture')
        reply_mid = _message(store, 'Nullable approved review', task=reply_task)
        store.add_review({
            'TaskId': reply_task, 'MessageId': reply_mid, 'Kind': None,
            'Status': 'approved', 'DraftText': 'Approved legacy text'})

        note_task = store.create_task({
            'Title': 'Unscheduled note', 'Kind': 'note', 'Status': 'open'}, 'fixture')
        note_mid = _message(store, 'Unscheduled note', task=note_task)
        store._exec('UPDATE message SET SentAt=NULL WHERE MessageId=?', (note_mid,))
        store.reconcile_processing_membership(fixed_now=NOW)

        legacy = {row['MessageId']: row for row in store.feed(days=36500, live_state=[])}
        page = processing_all.AllInventory().page(
            store, fixed_now=NOW, days=36500, live_state=[])
        canonical = {}
        for mid in (reply_mid, note_mid):
            item = next(row for row in page['items'] if f'message:{mid}' in row['member_ids'])
            canonical[mid] = processing_all.item_detail(
                store, item['item_id'], kind='message', local_id=mid,
                live_state=[])['row']

        for mid in (reply_mid, note_mid):
            assert {key: canonical[mid][key] for key in ('NeedsYou', 'TheirTurn', 'AnsweredAt')} == {
                key: legacy[mid][key] for key in ('NeedsYou', 'TheirTurn', 'AnsweredAt')}
        assert legacy[reply_mid]['ReviewKind'] is None
        assert canonical[reply_mid]['NeedsYou'] == 1
        assert canonical[reply_mid]['TheirTurn'] == 0
        assert canonical[note_mid]['NeedsYou'] == 0
        assert canonical[note_mid]['AnsweredAt'] is None
    finally:
        store.cx.close()


def test_checklist_comments_and_artifacts_refresh_detail_and_correct_revision_layer(tmp_path):
    store = SQLiteStore(str(tmp_path / 'detail-revisions.db'))
    try:
        task = store.create_task({
            'Title': 'Detail-backed task', 'Summary': 'Preserve complete task summary',
            'Status': 'open'}, 'fixture')
        mid = _message(store, 'Detail-backed message', task=task)
        store.reconcile_processing_membership(fixed_now=NOW)
        selected = _item_for_member(store, f'message:{mid}', live_state=[])
        initial = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])
        assert initial['detail']['task']['Checklist'] in (None, '')
        assert initial['detail']['comments'] == []
        assert initial['detail']['artifacts'] == []

        checklist = store.set_task_checklist(task, ['Keep the exact owner checklist'], 'owner')
        assert store.processing_reconcile_status()['pending'] is True
        store.reconcile_processing_membership(fixed_now='2026-09-06 12:01:00')
        after_checklist = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])
        assert after_checklist['detail']['checklist'] == checklist
        assert after_checklist['context_revision'] != initial['context_revision']
        assert after_checklist['view_revision'] != initial['view_revision']

        store.add_comment(task, 'owner', 'human', 'Exact owner history entry')
        store.reconcile_processing_membership(fixed_now='2026-09-06 12:02:00')
        after_comment = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])
        assert after_comment['context_revision'] == after_checklist['context_revision']
        assert after_comment['view_revision'] != after_checklist['view_revision']
        assert [row['Body'] for row in after_comment['detail']['comments']] == [
            'Exact owner history entry']

        artifact = store.add_task_artifact({
            'TaskId': task, 'Name': 'owner-proof.txt', 'ContentType': 'text/plain',
            'Size': 23, 'Path': '/synthetic/owner-proof.txt', 'Kind': 'evidence',
            'CreatedBy': 'owner'})
        store.reconcile_processing_membership(fixed_now='2026-09-06 12:03:00')
        after_artifact = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])
        assert after_artifact['context_revision'] == after_comment['context_revision']
        assert after_artifact['view_revision'] != after_comment['view_revision']
        assert [(row['ArtifactId'], row['Name'], row['Path'])
                for row in after_artifact['detail']['artifacts']] == [
                    (artifact, 'owner-proof.txt', '/synthetic/owner-proof.txt')]
        assert len({initial['detail_revision'], after_checklist['detail_revision'],
                    after_comment['detail_revision'], after_artifact['detail_revision']}) == 4
    finally:
        store.cx.close()


def test_persisted_transcript_exposes_metadata_without_full_text_and_refreshes_view(tmp_path):
    path = tmp_path / 'transcript-metadata.db'
    store = SQLiteStore(str(path))
    try:
        task = store.create_task({'Title': 'Completed worker task', 'Status': 'waiting'}, 'fixture')
        mid = _message(store, 'Completed worker message', task=task)
        store.reconcile_processing_membership(fixed_now=NOW)
        selected = _item_for_member(store, f'message:{mid}', live_state=[])
        before = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])
        assert before['detail']['transcript'] is None

        full_text = 'PRIVATE FULL TRANSCRIPT\nwith an exact second line'
        store.add_transcript(task, 'ended-session', full_text,
                             agent='coder', cwd='/synthetic/repository')
        assert store.processing_reconcile_status()['pending'] is True
        store.reconcile_processing_membership(fixed_now='2026-09-06 12:04:00')
        after = processing_all.item_detail(
            store, selected['item_id'], kind='message', local_id=mid, live_state=[])

        assert after['context_revision'] == before['context_revision']
        assert after['view_revision'] != before['view_revision']
        assert after['detail']['transcript'] == {
            'sid': 'ended-session', 'agent': 'coder', 'cwd': '/synthetic/repository',
            'at': store.last_transcript(task)['CreatedAt'], 'chars': len(full_text),
        }
        assert full_text not in json.dumps(after)
        item_id = selected['item_id']
    finally:
        store.cx.close()

    reopened = SQLiteStore(str(path))
    try:
        persisted = processing_all.item_detail(
            reopened, item_id, kind='message', local_id=mid, live_state=[])
        assert persisted['detail']['transcript']['sid'] == 'ended-session'
        assert persisted['detail']['transcript']['chars'] == len(full_text)
        assert full_text not in json.dumps(persisted)
    finally:
        reopened.cx.close()


def test_detail_collection_order_matches_legacy_and_selects_latest_work(tmp_path):
    store = SQLiteStore(str(tmp_path / 'detail-order.db'))
    try:
        task = store.create_task({'Title': 'Ordering task', 'Status': 'open'}, 'fixture')
        older = _message(store, 'Zulu older inbound', task=task)
        newer = _message(store, 'Alpha newest owner reply', task=task)
        with store.lock:
            store.cx.execute('UPDATE message SET SentAt=? WHERE MessageId=?',
                             ('2026-09-06 10:00:00', older))
            store.cx.execute('''UPDATE message SET SentAt=?,Direction='out',Status='context'
                WHERE MessageId=?''', ('2026-09-06 11:00:00', newer))
            store.cx.commit()

        old_comment = store.add_comment(
            task, 'coder', 'agent', 'CODER REPORT\nZulu older report')
        new_comment = store.add_comment(
            task, 'coder', 'agent', 'CODER REPORT\nAlpha newest report')
        old_run = store._exec('''INSERT INTO run
            (TaskId,AgentName,Status,DiffText,StartedAt) VALUES (?,?,?,?,?)''',
            (task, 'coder', 'done', 'AAA older diff', '2026-09-06 10:00:00'))
        new_run = store._exec('''INSERT INTO run
            (TaskId,AgentName,Status,DiffText,StartedAt) VALUES (?,?,?,?,?)''',
            (task, 'coder', 'done', 'ZZZ newest diff', '2026-09-06 11:00:00'))
        old_artifact = store.add_task_artifact({
            'TaskId': task, 'Name': 'zulu-old.txt', 'Path': '/synthetic/zulu-old.txt'})
        new_artifact = store.add_task_artifact({
            'TaskId': task, 'Name': 'alpha-new.txt', 'Path': '/synthetic/alpha-new.txt'})
        old_route = store.add_route(
            older, task, 'create', 0.8, 'Zulu older reason', [], 'fixture')
        new_route = store.add_route(
            older, task, 'attach', 0.9, 'Alpha newer reason', [], 'fixture')
        store.reconcile_processing_membership(fixed_now=NOW)
        selected = _item_for_member(store, f'message:{older}', live_state=[])

        # Capture the established contract outside canonical detail's read transaction.
        legacy = store.task_detail(task)
        with mock.patch.object(server, 'store', store), \
             mock.patch.object(server, '_processing_live', return_value=[]):
            response = TestClient(server.app).get(
                f"/api/processing/items/{selected['item_id']}/detail",
                params={'kind': 'message', 'id': older})
        assert response.status_code == 200
        detail = response.json()['detail']

        for collection, api_id, legacy_id in (
                ('messages', 'MessageId', 'MessageId'),
                ('comments', 'CommentId', 'CommentId'),
                ('routes', 'RouteId', 'RouteId'), ('runs', 'RunId', 'RunId'),
                ('artifacts', 'id', 'ArtifactId')):
            assert [row[api_id] for row in detail[collection]] == [
                row[legacy_id] for row in legacy[collection]]
        assert [row['MessageId'] for row in detail['messages']] == [older, newer]
        assert [row['CommentId'] for row in detail['comments']] == [old_comment, new_comment]
        assert [row['RunId'] for row in detail['runs']] == [new_run, old_run]
        assert [row['id'] for row in detail['artifacts']] == [new_artifact, old_artifact]
        assert [row['RouteId'] for row in detail['routes']] == [old_route, new_route]

        latest_report = next(row for row in reversed(detail['comments'])
                             if row['Body'].startswith('CODER REPORT'))
        latest_owner_reply = next(row for row in reversed(detail['messages'])
                                  if row['Direction'] == 'out')
        newest_diff = next(row for row in detail['runs'] if row['DiffText'])
        assert latest_report['CommentId'] == new_comment
        assert latest_owner_reply['MessageId'] == newer
        assert newest_diff['RunId'] == new_run
    finally:
        store.cx.close()
