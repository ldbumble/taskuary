"""Narrow synthetic source edits, installed only by the disposable browser server."""
import os
from datetime import datetime, timedelta

from fastapi import HTTPException


def install_processing_changes(app, store):
    if os.environ.get('TASKUARY_DEMO') != '1' or not os.environ.get('TASKUARY_HOME'):
        raise RuntimeError('processing changes require the isolated demo fixture')
    from taskuary import demo
    refuse = demo.refuse
    fixture_paths = frozenset({
        '/api/fixture/processing/source', '/api/fixture/processing/member',
        '/api/fixture/processing/draft',
        '/api/fixture/processing/context',
        '/api/fixture/processing/background',
        '/api/fixture/processing/ordering',
        '/api/fixture/processing/unread-activate',
        '/api/fixture/processing/unread-arrivals',
        '/api/fixture/processing/sync-phase',
        '/api/fixture/processing/canonical-all',
        '/api/fixture/processing/canonical-arrival',
        '/api/fixture/processing/canonical-emit',
        '/api/fixture/processing/canonical-review-move',
    })

    def fixture_refuse(method, path):
        # Only these test-installed, bounded database edits are extra allowances.
        # Every production route retains the original demo guard and socket guard.
        if method == 'POST' and path in fixture_paths:
            return ''
        return refuse(method, path)

    demo.refuse = fixture_refuse
    from website.browser.fixture_canonical import install_canonical_changes
    install_canonical_changes(app, store)

    sync_token = [None]

    @app.post('/api/fixture/processing/sync-phase')
    def sync_phase(body: dict):
        from taskuary import server
        phases = {'fetching': 'reading synthetic sources', 'triaging': 'processing synthetic messages',
                  'checking': 'checking synthetic work', 'running_reports': 'running synthetic reports', 'idle': ''}
        if set(body) != {'phase'} or body['phase'] not in phases:
            raise HTTPException(422, 'one fixed synthetic phase is required')
        phase = body['phase']
        if phase == 'idle':
            if sync_token[0] is not None:
                server._status_end(store, sync_token[0])
                sync_token[0] = None
                server._POLL_BUSY.release()
        else:
            if sync_token[0] is None:
                if not server._POLL_BUSY.acquire(blocking=False):
                    raise HTTPException(409, 'fixture sync already owned')
                sync_token[0] = server._status_begin(store, 'full', phases[phase])
            server._status_progress(store, sync_token[0], phases[phase], phase=phase)
            store.set_setting('triage_last_error', 'Synthetic triage error remains visible', 'fixture')
        return {'phase': phase}

    @app.post('/api/fixture/processing/unread-activate')
    def activate_unread(body: dict):
        if body:
            raise HTTPException(422, 'empty fixture input required')
        from taskuary import concierge, funnel, terminal
        from taskuary.processing_startup import initialize
        result = initialize(store, live_state=terminal.live_sessions(tail=6))
        # This explicit disposable-fixture activation supplies one deterministic
        # model decision; every other prompt keeps the normal offline demo voice.
        # Exercise the real say/decision/guarded-next path without a model service.
        def fixture_brain(target_store, **kwargs):
            if target_store is not store:
                raise RuntimeError('synthetic navigation model belongs to the fixture store')
            fallback = demo.brain()

            def model(system, user, **options):
                if 'The owner says: Next' in str(user).splitlines():
                    return 'Next.\nDECIDE: next'
                return fallback(system, user, **options)

            return model

        concierge.brain = fixture_brain
        funnel.invalidate()
        return result

    @app.post('/api/fixture/processing/unread-arrivals')
    def unread_arrivals(body: dict):
        if body:
            raise HTTPException(422, 'empty fixture input required')
        if not store.processing_reads_active():
            raise HTTPException(409, 'activate synthetic read boundary first')
        from taskuary import funnel
        ids = []
        for index in range(507):
            ids.append(store.add_message({'Channel': 'email', 'SourceName': 'unread-fixture@example.test',
                'ExternalId': f'unread-arrival-{index}', 'ConversationId': f'unread-arrival-{index}',
                'FromName': 'Unread fixture', 'FromEmail': 'fixture@example.test',
                'Subject': f'Shared arrival {index:03}', 'BodyText': f'Fixture information {index:03}',
                'SentAt': '2020-01-01 12:00:00' if index == 506 else datetime.now().isoformat(' '),
                'Status': 'triaging' if index == 505 else 'ignored' if index % 2 else 'filed'}))
        store.reconcile_processing_membership()
        funnel.invalidate()
        store._poke('feed-changed')
        return {'ids': ids}

    @app.post('/api/fixture/processing/background')
    def background_card(body: dict):
        if set(body) != {'task_id'} or type(body['task_id']) is not int:
            raise HTTPException(422, 'exact task_id is required')
        from taskuary import concierge, funnel, general
        item = funnel.next_item(store, f"agent:{body['task_id']}")
        if not item or item.get('kind') != 'agent':
            raise HTTPException(404, 'synthetic agent missing')
        card = {**concierge.card_for(item), 'background_event': True}
        # The native watcher producer has separate service coverage. This fixture
        # exercises persisted passive-card ingestion and restoration in the browser.
        dock, _ = general.dock_task(store, 'fixture')
        concierge.record(store, dock['TaskId'], 'assistant', 'Synthetic passive worker notice', card)
        store._poke('feed-changed', task_id=body['task_id'])
        return {'ok': True, 'key': card['key']}

    @app.post('/api/fixture/processing/context')
    def add_context(body: dict):
        if set(body) != {'task_id', 'body'} or type(body['task_id']) is not int:
            raise HTTPException(422, 'exact task_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        if not store.get_task(body['task_id']):
            raise HTTPException(404, 'synthetic task missing')
        store.add_comment(body['task_id'], 'fixture', 'user', body['body'])
        return {'ok': True}

    @app.post('/api/fixture/processing/draft')
    def change_draft(body: dict):
        if set(body) != {'review_id', 'body'} or type(body['review_id']) is not int:
            raise HTTPException(422, 'exact review_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        review = store.get_review(body['review_id'])
        if not review or review.get('Status') not in ('pending', 'held'):
            raise HTTPException(404, 'synthetic pending review missing')
        store.save_review_draft(body['review_id'], body['body'])
        return {'ok': True, 'draft': body['body']}

    @app.post('/api/fixture/processing/source')
    def change_source(body: dict):
        if set(body) != {'message_id', 'body'} or type(body['message_id']) is not int:
            raise HTTPException(422, 'exact message_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        mid = body['message_id']
        if not store.get_message(mid):
            raise HTTPException(404, 'synthetic message missing')
        store.update_message_body(mid, body['body'])
        # Exercise the actual websocket consumer after a synthetic source update.
        store._poke('feed-changed', message_id=mid)
        return {'ok': True, 'message_id': mid}

    @app.post('/api/fixture/processing/member')
    def add_older_member(body: dict):
        if set(body) != {'message_id', 'body'} or type(body['message_id']) is not int:
            raise HTTPException(422, 'exact message_id and body are required')
        if not isinstance(body['body'], str) or len(body['body']) > 50000:
            raise HTTPException(422, 'body must be a bounded string')
        original = store.get_message(body['message_id'])
        if not original or not original.get('TaskId'):
            raise HTTPException(404, 'synthetic task member missing')
        sent = datetime.fromisoformat(original['SentAt']) - timedelta(days=1)
        mid = store.add_message({
            'TaskId': original['TaskId'], 'Channel': original['Channel'],
            'Status': 'filed', 'Subject': 'Synthetic older context member',
            'SentAt': sent.isoformat(sep=' '), 'BodyText': body['body'],
        })
        return {'ok': True, 'message_id': mid}

    @app.post('/api/fixture/processing/ordering')
    def ordering_arrivals(body: dict):
        if body:
            raise HTTPException(422, 'this fixed ordering fixture accepts only an empty object')
        from taskuary import funnel
        now = datetime.now()
        titles = {}
        for name, priority, minutes in (('urgent', 'urgent', 1), ('high', 'high', 2),
                                        ('old', 'normal', 60), ('new', 'normal', 3)):
            title = 'ORDERING ' + name.upper()
            tid = store.create_task({'Title': title, 'Kind': 'general', 'Status': 'open', 'Priority': priority}, 'fixture')
            store.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'routed',
                               'ExternalId': 'ordering:' + name, 'SourceName': 'ordering@example.test',
                               'FromEmail': 'sender@example.test', 'FromName': 'Ordering fixture',
                               'Subject': title, 'BodyText': 'Please handle this synthetic request.',
                               'SentAt': (now - timedelta(minutes=minutes)).isoformat(' ')})
            titles[name] = title
        funnel.invalidate()
        store._poke('feed-changed')
        return {'titles': titles}
