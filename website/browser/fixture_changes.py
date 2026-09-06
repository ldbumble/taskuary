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
        '/api/fixture/processing/canonical-all',
        '/api/fixture/processing/canonical-arrival',
        '/api/fixture/processing/canonical-emit',
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
