from unittest import mock

from fastapi.testclient import TestClient

from taskuary import server
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def queued_task(store, title):
    task_id = Factory(store).task(title=title, kind='coding')
    store.enqueue_dispatch(task_id, None, 'coder', 'capacity')
    return task_id


def agent_headers():
    return {'X-Taskuary-Token': server.cfg['server']['agent_token']}


def owner_headers():
    return {'X-Taskuary-Token': server.cfg['server']['token']}


def test_agent_cannot_retry_or_cancel_a_queued_dispatch():
    store = MemoryStore()
    retry_task = queued_task(store, 'Retry must remain an owner choice')
    cancel_task = queued_task(store, 'Cancel must remain an owner choice')

    with mock.patch.object(server, 'store', store), \
         mock.patch.object(store, 'dispatch_retry', return_value=True) as retry, \
         mock.patch.object(store, 'clear_dispatch') as clear, \
         mock.patch.object(server.blackboard, 'drain') as drain:
        client = TestClient(server.app)
        retry_response = client.post(
            f'/api/tasks/{retry_task}/dispatch/retry', headers=agent_headers())
        cancel_response = client.delete(
            f'/api/tasks/{cancel_task}/dispatch', headers=agent_headers())

    assert retry_response.status_code == 403
    assert cancel_response.status_code == 403
    assert 'agents cannot do this' in retry_response.json()['detail']
    assert 'agents cannot do this' in cancel_response.json()['detail']
    retry.assert_not_called()
    clear.assert_not_called()
    drain.assert_not_called()
    assert store.get_dispatch(retry_task) is not None
    assert store.get_dispatch(cancel_task) is not None


def test_owner_can_retry_and_cancel_queued_dispatches():
    store = MemoryStore()
    retry_task = queued_task(store, 'Owner retries this start')
    cancel_task = queued_task(store, 'Owner cancels this start')

    with mock.patch.object(server, 'store', store), \
         mock.patch.object(store, 'dispatch_retry', wraps=store.dispatch_retry) as retry, \
         mock.patch.object(store, 'clear_dispatch', wraps=store.clear_dispatch) as clear, \
         mock.patch.object(server.blackboard, 'drain') as drain:
        client = TestClient(server.app)
        retry_response = client.post(
            f'/api/tasks/{retry_task}/dispatch/retry', headers=owner_headers())
        cancel_response = client.delete(
            f'/api/tasks/{cancel_task}/dispatch', headers=owner_headers())

    assert retry_response.status_code == 200
    assert cancel_response.status_code == 200
    retry.assert_called_once_with(retry_task)
    clear.assert_called_once_with(cancel_task)
    drain.assert_called_once_with(store)
    assert store.get_dispatch(retry_task)['State'] == 'waiting'
    assert store.get_dispatch(cancel_task) is None
    assert store.get_task(cancel_task)['Status'] == 'open'
