"""Guarded Next rejects stale selection before effects and binds the accepted turn."""
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
import asyncio
import json
import threading
import time

import pytest
from fastapi.testclient import TestClient

from taskuary import concierge, funnel, general, processing_navigation as navigation, server, terminal
from taskuary.store import SQLiteStore


@pytest.fixture
def nav_api(tmp_path, monkeypatch):
    db = SQLiteStore(str(tmp_path / 'navigation.db'))
    monkeypatch.setattr(server, 'store', db)
    monkeypatch.setattr(terminal, 'live_sessions', lambda **kwargs: [])
    monkeypatch.setattr(funnel, 'announce', lambda store: [])
    monkeypatch.setattr(funnel, 'alerts', lambda *args: [])
    monkeypatch.setattr(concierge, 'INTRO_AI', False)
    funnel.invalidate()
    tid = db.create_task({'Title': 'Synthetic selection', 'Status': 'open'}, 'fixture')
    mid = db.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'filed',
                          'Subject': 'Synthetic source', 'BodyText': 'Initial body',
                          'SentAt': datetime.now().isoformat(sep=' ')})
    rid = db.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply',
                         'Status': 'pending', 'DraftText': 'Initial draft'})
    client = TestClient(server.app)
    before = set(threading.enumerate())
    try:
        yield db, client, mid, rid
    finally:
        client.close()
        # the streamed Next answers from a daemon thread that goes on to build the rail (_with_pile), and that
        # thread starts another as it ends (refresh-after); closing the database under either was a native
        # access violation that took the whole run down on Windows now and then. Let every thread this test
        # started - and every thread THEY started - finish before the close.
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline:
            left = [t for t in threading.enumerate() if t not in before and t.daemon and t.is_alive()]
            if not left: break
            for t in left: t.join(timeout=max(0.1, deadline - time.monotonic()))
        funnel.invalidate()
        db.cx.close()


def binding(client, **scope):
    response = client.get('/api/funnel/pile', params={'force': True, **scope})
    assert response.status_code == 200, response.text
    data = response.json()
    return {key: data[key] for key in ('selection_revision', 'expected_next_key', 'expected_next_members')}


def dump(db):
    return list(db.cx.iterdump())


def _another(db, n=2):
    tid = db.create_task({'Title': f'Synthetic selection {n}', 'Status': 'open'}, 'fixture')
    mid = db.add_message({'TaskId': tid, 'Channel': 'email', 'Status': 'filed', 'Subject': f'Synthetic source {n}',
                          'BodyText': 'Another body', 'SentAt': datetime.now().isoformat(sep=' ')})
    return db.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'reply', 'Status': 'pending', 'DraftText': 'Another draft'})


@pytest.mark.parametrize('route', ['next', 'stream'])
@pytest.mark.parametrize('change', ['gone', 'replaced'])
def test_initial_stale_is_http_409_before_any_effect(nav_api, monkeypatch, route, change):
    """Stale is the PICK moving: the item the page shows as next is no longer what the rail hands
    over (it was settled; or settled and another stands in its place). Not a refusal to be taken
    lightly - and not one for anything else, see the fresh-content test below."""
    db, client, mid, rid = nav_api
    payload = binding(client)
    funnel.settle(db, f'review:{rid}', 'done', 'owner')
    if change == 'replaced': _another(db)
    before, writes = dump(db), db.cx.total_changes

    def forbidden(*args, **kwargs):
        pytest.fail('stale admission reached an effect boundary')

    for module, name in ((general, 'dock_task'), (concierge, 'surface'),
                         (server, '_refresh_chat_key'), (funnel, 'announce'),
                         (funnel, 'settle'), (concierge, 'record')):
        monkeypatch.setattr(module, name, forbidden)
    response = client.post(f'/api/concierge/{route}', json={'mode': 'next', **payload})
    assert response.status_code == 409, response.text
    assert response.json()['detail']['code'] == 'selection_stale'
    assert db.cx.total_changes == writes
    assert dump(db) == before


@pytest.mark.parametrize('route', ['next', 'stream'])
@pytest.mark.parametrize('change', ['body', 'draft', 'scope', 'chat'])
def test_what_moved_around_the_same_pick_is_taken_fresh_not_refused(nav_api, route, change):
    """The page shows review:1 as next and review:1 is still the pick: the press goes through and the
    turn speaks from the rail as it is NOW - the grown body, the rewritten draft, the renewed chat.
    Refusing here failed a press with "the next item changed" when it had not (design B, 2026-09-17)."""
    db, client, mid, rid = nav_api
    payload = binding(client)
    if change == 'body': db.update_message_body(mid, 'Changed full source')
    elif change == 'draft': db.save_review_draft(rid, 'Changed draft')
    elif change == 'scope': payload['only'] = 'mail'
    elif change == 'chat': general.dock_task(db)
    response = client.post(f'/api/concierge/{route}', json={'mode': 'next', **payload})
    assert response.status_code == 200, response.text
    data = response.json() if route == 'next' else json.loads(response.text.splitlines()[-1])
    assert data['item']['key'] == f'review:{rid}'
    if change == 'body': assert data['item']['preview'] == 'Changed full source'
    states = db.funnel_states()
    assert states[f'review:{rid}']['Status'] == 'surfaced', 'the turn had its effect'


@pytest.mark.parametrize('route', ['next', 'stream'])
def test_accepted_selection_consumes_exact_capture_once(nav_api, monkeypatch, route):
    """The accepted turn takes the captured item and never selects again. It may READ the rail's
    cached pile - that is where the page's token came from, and the turn validates against it rather
    than building a second one (design B, 2026-09-17) - but it must not pick."""
    db, client, mid, rid = nav_api
    payload = binding(client)
    assert payload['expected_next_key'] == f'review:{rid}'

    def forbidden(*args, **kwargs):
        pytest.fail('accepted selection selected again')

    for name in ('next_item', 'fyi_batch'):
        monkeypatch.setattr(funnel, name, forbidden)
    response = client.post(f'/api/concierge/{route}', json={'mode': 'next', **payload})
    assert response.status_code == 200, response.text
    data = response.json() if route == 'next' else json.loads(response.text.splitlines()[-1])
    assert data['item']['key'] == payload['expected_next_key']
    # ...and the rail as the turn left it rides along, captured with the surfaced item excluded, so
    # the page holds it instead of fetching the same rows again
    assert data['pile']['expected_next_key'] != data['item']['key']
    assert set(data['pile']) >= {'selection_revision', 'expected_next_members', 'items', 'display_revision', 'generated_at'}
    before, writes = dump(db), db.cx.total_changes
    repeated = client.post(f'/api/concierge/{route}', json={'mode': 'next', **payload})
    assert repeated.status_code == 409
    assert db.cx.total_changes == writes and dump(db) == before


@pytest.mark.parametrize('missing', ['selection_revision', 'expected_next_key', 'expected_next_members'])
def test_incomplete_binding_does_not_fall_back_to_legacy(nav_api, missing):
    db, client, mid, rid = nav_api
    payload = binding(client)
    del payload[missing]
    before = dump(db)
    assert client.post('/api/concierge/next', json=payload).status_code == 422
    assert dump(db) == before


def test_concurrent_admission_has_one_owner_and_no_second_effect(nav_api, monkeypatch):
    db, client, mid, rid = nav_api
    payload = binding(client)
    entered, release = threading.Event(), threading.Event()
    original = concierge.surface

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(concierge, 'surface', held)
    with ThreadPoolExecutor(max_workers=1) as pool:
        future = pool.submit(client.post, '/api/concierge/next', json=payload)
        try:
            assert entered.wait(5)
            before = dump(db)
            duplicate = client.post('/api/concierge/next', json=payload)
            assert duplicate.status_code == 409
            assert dump(db) == before
        finally:
            release.set()
        assert future.result(timeout=10).status_code == 200


def test_new_chat_during_accepted_work_cannot_receive_old_turn(nav_api, monkeypatch):
    db, client, mid, rid = nav_api
    old, _ = general.dock_task(db)
    payload = binding(client)
    original = concierge.surface
    after_reset = []
    model_chats = []
    monkeypatch.setattr(concierge, 'INTRO_AI', True)

    def brain(store, tid, *args, **kwargs):
        model_chats.append(tid)
        return object()

    monkeypatch.setattr(concierge, '_brain_for', brain)
    monkeypatch.setattr(concierge, '_ask', lambda *args, **kwargs: ('Old accepted introduction', []))

    def reset_then_surface(*args, **kwargs):
        response = client.post('/api/assistant/dock/new')
        assert response.status_code == 200, response.text
        after_reset.extend(dump(db))
        return original(*args, **kwargs)

    monkeypatch.setattr(concierge, 'surface', reset_then_surface)
    response = client.post('/api/concierge/next', json=payload)
    assert response.status_code == 409, response.text
    assert dump(db) == after_reset
    assert model_chats == [old['TaskId']], 'accepted work must never enter the replacement chat model session'


def test_failed_work_releases_but_partial_commit_consumes_reservation(nav_api):
    db, client, mid, rid = nav_api
    general.dock_task(db)
    payload = binding(client)
    first = navigation.reserve(db, **payload)
    with pytest.raises(RuntimeError):
        first.run(lambda capture, guard, dock: (_ for _ in ()).throw(RuntimeError('before effects')))
    second = navigation.reserve(db, **payload)

    def partial(capture, guard, dock):
        with guard():
            db.audit('navigation', 1, 'synthetic_partial', 'fixture')
            raise RuntimeError('after a committed write')

    with pytest.raises(RuntimeError): second.run(partial)
    with pytest.raises(navigation.NavigationStale) as error: navigation.reserve(db, **payload)
    assert error.value.detail['reason'] == 'outcome_uncertain'
    assert error.value.detail['retryable'] is False


@pytest.mark.parametrize('route', ['next', 'stream'])
def test_context_changes_during_model_work_do_not_commit_a_stale_card(nav_api, monkeypatch, route):
    db, client, mid, rid = nav_api
    general.dock_task(db)
    payload = binding(client)
    after_change = []
    monkeypatch.setattr(concierge, 'INTRO_AI', True)
    monkeypatch.setattr(concierge, '_brain_for', lambda *args, **kwargs: object())

    def changed(*args, **kwargs):
        db.save_review_draft(rid, 'Changed while model was answering')
        after_change.extend(dump(db))
        return 'Outdated introduction', []

    monkeypatch.setattr(concierge, '_ask', changed)
    response = client.post(f'/api/concierge/{route}', json={'mode': 'next', **payload})
    if route == 'next':
        assert response.status_code == 409, response.text
    else:
        assert response.status_code == 200
        event = json.loads(response.text.splitlines()[-1])
        assert event['type'] == 'error' and event['code'] == 'selection_stale'
    assert after_change and dump(db) == after_change


def test_stream_thread_start_failure_releases_without_effects(nav_api, monkeypatch):
    db, client, mid, rid = nav_api
    payload = binding(client)
    before = dump(db)
    original = threading.Thread.start

    def fail_navigation(thread):
        if getattr(getattr(thread, '_target', None), '__name__', '') == 'work':
            raise RuntimeError('synthetic thread admission failure')
        return original(thread)

    monkeypatch.setattr(threading.Thread, 'start', fail_navigation)
    with pytest.raises(RuntimeError, match='synthetic thread'):
        asyncio.run(server.concierge_stream(server.ConciergeStreamBody(mode='next', **payload)))
    assert dump(db) == before
    reservation = navigation.reserve(db, **payload)
    reservation.close()


@pytest.mark.parametrize('route', ['next', 'stream'])
def test_unavailable_native_observation_cannot_look_like_empty_next(nav_api, monkeypatch, route):
    db, client, mid, rid = nav_api
    payload = binding(client)
    before = dump(db)

    def unavailable(**kwargs):
        raise RuntimeError('synthetic native observation unavailable')

    monkeypatch.setattr(terminal, 'live_sessions', unavailable)
    response = client.post(f'/api/concierge/{route}', json={'mode': 'next', **payload})
    assert response.status_code == 503, response.text
    assert response.json()['detail']['code'] == 'selection_unavailable'
    assert dump(db) == before


def test_unconsumed_stream_response_does_not_release_running_worker(nav_api, monkeypatch):
    db, client, mid, rid = nav_api
    general.dock_task(db)
    payload = binding(client)
    entered, release = threading.Event(), threading.Event()
    original = concierge.surface

    def held(*args, **kwargs):
        entered.set()
        assert release.wait(10)
        return original(*args, **kwargs)

    monkeypatch.setattr(concierge, 'surface', held)
    # Do not consume the response body: response delivery does not own admission.
    response = asyncio.run(server.concierge_stream(server.ConciergeStreamBody(mode='next', **payload)))
    assert response.media_type == 'application/x-ndjson'
    try:
        assert entered.wait(5)
        with pytest.raises(navigation.NavigationStale) as error:
            navigation.reserve(db, **payload)
        assert error.value.detail['reason'] == 'navigation_in_progress'
    finally:
        release.set()
    deadline = time.monotonic() + 10
    while navigation._state(db).active is not None and time.monotonic() < deadline:
        time.sleep(.01)
    assert navigation._state(db).active is None
    assert navigation._state(db).consumed[payload['selection_revision']] == 'already_completed'
