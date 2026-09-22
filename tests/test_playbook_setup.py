"""Playbook authoring starts from optional history and ends at the existing review boundary."""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import general, llm, playbooks, server, terminal
from taskuary.store import MemoryStore, SQLiteStore


def email(store, **fields):
    return store.add_message({'Channel': 'email', 'Direction': 'in', 'Subject': 'Updated item numbers',
                              'FromEmail': 'buyer@example.test', 'BodyText': 'Send the latest numbers for item X.',
                              'SentAt': '2020-01-01 12:00:00', **fields})


@pytest.mark.parametrize('on_disk', [False, True], ids=['memory', 'sqlite'])
def test_history_search_includes_old_mail_and_paginates_without_outgoing_or_chat(tmp_path, request, on_disk):
    store = SQLiteStore(tmp_path / 'playbooks.db') if on_disk else MemoryStore()
    request.addfinalizer(store.cx.close)
    mids = [email(store, Subject=f'Item {i}') for i in range(23)]
    email(store, Direction='out'); email(store, Channel='teams')
    with mock.patch.object(server, 'store', store):
        client = TestClient(server.app)
        first = client.get('/api/playbooks/examples').json()
        second = client.get('/api/playbooks/examples', params={'before': first['next']}).json()
        assert [r['MessageId'] for r in first['data'] + second['data']] == list(reversed(mids))
        assert second['next'] is None
        assert len(client.get('/api/playbooks/examples?q=buyer').json()['data']) == 20
        assert client.get('/api/playbooks/examples?q=%25').json()['data'] == []


def test_email_setup_preserves_original_and_starts_the_conversation_once():
    store = MemoryStore()
    original_task = store.create_task({'Title': 'Original request', 'Status': 'done'}, 'owner')
    mid = email(store, TaskId=original_task, Status='filed')
    original = store.get_message(mid)
    session = mock.Mock()
    def start(st, tid, **kwargs):
        assert tid in general.OPENING
        return session
    with mock.patch.object(server, 'store', store), mock.patch.object(general, 'provider_options', return_value=[{}]), \
         mock.patch.object(general, 'start_session', side_effect=start) as started:
        response = TestClient(server.app).post('/api/playbooks/setup', json={'message_id': mid, 'connector_type': 'quickbooks'})
    assert response.status_code == 200
    task = response.json()['task']
    assert task['Kind'] == 'general' and task['SourceRef'] == 'assistant:playbook'
    assert 'quickbooks' in task['Summary'] and 'item X' in task['Summary']
    assert store.get_message(mid) == original
    assert store.get_task(original_task)['Status'] == 'done'
    assert not store.list_messages(task['TaskId'])
    assert started.call_count == session.send_prompt.call_count == 1
    assert session.send_prompt.call_args.kwargs == {'as_owner': False, 'echo': False}
    assert task['TaskId'] not in general.OPENING
    assert general.history(store, task['TaskId'])[0]['role'] == 'user'


def test_invalid_setup_creates_no_task_and_unavailable_ai_explains_how_to_continue():
    store = MemoryStore()
    mid = email(store, Direction='out')
    with mock.patch.object(server, 'store', store), mock.patch.object(general, 'provider_options', return_value=[{}]), \
         mock.patch.object(general, 'start_session') as start:
        client = TestClient(server.app)
        for body in ({}, {'text': '  '}, {'message_id': mid}, {'message_id': 99999}):
            assert client.post('/api/playbooks/setup', json=body).status_code == 422
        with mock.patch.object(general, 'provider_options', return_value=[]):
            response = client.post('/api/playbooks/setup', json={'text': 'Summarize numbers'})
        assert 'Connections' in response.json()['detail']
        assert not start.called
    assert store._rows('SELECT * FROM task') == []


def test_failed_start_is_visible_in_saved_chat_and_clears_starting():
    store = MemoryStore()
    with mock.patch.object(server, 'store', store), mock.patch.object(general, 'provider_options', return_value=[{}]), \
         mock.patch.object(general, 'start_session', side_effect=RuntimeError('provider unavailable')), \
         mock.patch.object(general, 'drop_session'):
        response = TestClient(server.app).post('/api/playbooks/setup', json={'text': 'Prepare weekly numbers'})
    tid = response.json()['taskId']
    assert tid not in general.OPENING
    assert 'could not start' in general.history(store, tid)[-1]['content'][0]['text']


DRAFT = '# Item report\nwhen: new request\nuses: reporting source (read)\nsteps: read {item} and draft a summary\nalone: read\nask first: send\ndone when: owner reviews\n'


def test_api_assistant_turn_queues_a_review_without_writing_and_hides_envelope(tmp_path):
    store = MemoryStore()
    connector = store.get_connector_by_type('openai')
    store.save_connector({'ConnectorId': connector['ConnectorId'], 'Active': 1, 'Secret': 'sk-test',
                          'Name': 'Test AI', 'ConfigJson': '{"model":"test"}'}, 'owner')
    tid = playbooks.setup_task(store, 'Prepare item numbers')['taskId']
    reply = 'Here is your draft.\nTASKUARY-PROPOSE ' + json.dumps({'action': 'write_playbook', 'slug': 'new', 'text': DRAFT})
    with mock.patch.object(llm, 'build_llm', return_value=lambda *a, **k: reply), \
         mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(playbooks, 'folder', return_value=tmp_path):
        session = general.start_session(store, tid, connector_id=connector['ConnectorId'])
        visible = session.send_prompt('Prepare the draft')
        assert 'Draft ready on the task' in visible and 'TASKUARY-PROPOSE' not in visible
        assert list(tmp_path.iterdir()) == []
        session.send_prompt('Show it again')
    reviews = store.list_reviews('pending')
    assert len(reviews) == 1
    assert json.loads(reviews[0]['DraftText'])['text'] == DRAFT


def test_malformed_and_unrelated_proposals_do_not_create_reviews(tmp_path):
    store = MemoryStore(); tid = playbooks.setup_task(store, 'Prepare item numbers')['taskId']
    with mock.patch.object(playbooks, 'folder', return_value=tmp_path):
        for envelope in ('not json', '{"action":"run_tool"}', json.dumps({'action': 'write_playbook', 'text': '# Missing fields'})):
            assert 'could not be queued' in playbooks.collect_setup_draft(store, tid, 'TASKUARY-PROPOSE ' + envelope)
    assert store.list_reviews('pending') == []
