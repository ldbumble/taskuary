"""The past emails a playbook can be built from (the playbook itself is built on its page: tests/test_build.py)."""
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
