import os
import sys
from unittest import mock

import requests

from taskuary import blackboard, cli, terminal
from taskuary.store import MemoryStore


class Response:
    def __init__(self, data, status=200):
        self.data = data
        self.status_code = status

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f'HTTP {self.status_code}')

    def json(self):
        return self.data


def run_cli(capsys, *args):
    with mock.patch.object(sys, 'argv', ['taskuary', *args]):
        cli.main()
    return capsys.readouterr().out


def test_live_board_uses_running_server_registry_and_scoped_session_route(capsys):
    live = {'NoteId': 7, 'TaskId': 41, 'Agent': 'coder', 'Kind': 'working',
            'Body': 'active in the server-owned SID', 'CreatedAt': '2026-09-06 14:00:00',
            'Cwd': r'C:\work\taskuary', 'Sid': 'server-session'}
    env = {'TASKUARY_API': 'http://127.0.0.1:45678/',
           'TASKUARY_URL': 'http://wrong.example.test:9999',
           'TASKUARY_TOKEN': 'scoped-agent-token', 'TASKUARY_CWD': r'C:\work\taskuary'}
    with mock.patch.dict(os.environ, env, clear=False), \
         mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
         mock.patch('requests.get', return_value=Response({'data': [live]})) as get:
        output = run_cli(capsys, '--board')

    assert 'active in the server-owned SID' in output
    assert 'you are first' not in output
    get.assert_called_once_with(
        'http://127.0.0.1:45678/api/board/notes', timeout=5,
        headers={'X-Taskuary-Token': 'scoped-agent-token'},
        params={'cwd': r'C:\work\taskuary', 'limit': 20})


def test_live_board_failure_is_unavailable_and_never_history_as_live(capsys):
    store = MemoryStore()
    blackboard.post(store, 'durable history is not proof of a live SID', 'note', 'old-agent', r'C:\work\taskuary')
    with mock.patch.dict(os.environ, {'TASKUARY_API': 'http://127.0.0.1:45679',
                                      'TASKUARY_TOKEN': 'scoped-agent-token',
                                      'TASKUARY_CWD': r'C:\work\taskuary'}, clear=False), \
         mock.patch('taskuary.store.SQLiteStore', return_value=store), \
         mock.patch('requests.get', side_effect=requests.ConnectionError('server stopped')):
        output = run_cli(capsys, '--board')

    assert 'the live wall is unavailable' in output
    assert 'server stopped' in output
    assert 'durable history is not proof' not in output
    assert 'you are first' not in output


def test_board_all_remains_local_durable_history(capsys):
    store = MemoryStore()
    cwd = r'C:\work\taskuary'
    blackboard.post(store, 'durable history remains available', 'ready', 'old-agent', cwd)
    with mock.patch.dict(os.environ, {'TASKUARY_CWD': cwd}, clear=False), \
         mock.patch('taskuary.store.SQLiteStore', return_value=store), \
         mock.patch('requests.get', side_effect=AssertionError('durable history must not need the server')):
        output = run_cli(capsys, '--board', '--all')

    assert 'durable history remains available' in output
    assert 'the live wall is unavailable' not in output
