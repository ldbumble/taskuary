"""P0-ISOLATION executable checks for the suite's fail-closed boundaries."""
import imaplib
import asyncio
import os
import smtplib
import subprocess
import sys
from pathlib import Path
from unittest import mock

import pytest
import httpx
import requests
from fastapi.testclient import TestClient

from taskuary import hooks, server, spawn, terminal


def test_taskuary_and_user_configuration_live_under_the_generated_suite_root():
    taskuary_home = Path(os.environ['TASKUARY_HOME']).resolve()
    user_home = Path.home().resolve()

    assert taskuary_home.name == 'taskuary'
    assert user_home.name == 'user'
    assert taskuary_home.parent == user_home.parent
    assert Path(os.environ['TASKUARY_TEST_HOME']).resolve() == taskuary_home
    for name in ('CODEX_HOME', 'CLAUDE_CONFIG_DIR', 'AGENT_BROWSER_HOME', 'APPDATA', 'LOCALAPPDATA'):
        assert Path(os.environ[name]).resolve().is_relative_to(taskuary_home.parent)
    assert os.environ['TASKUARY_HOST'] == '127.0.0.1'
    assert os.environ['TASKUARY_PORT'] == '0'
    assert os.environ['TASKUARY_TOKEN'] == 'pytest-owner-token'
    assert 'TASKUARY_API' not in os.environ


def test_unregistered_network_and_mail_connections_fail_closed():
    with pytest.raises(AssertionError, match='blocked unmocked HTTP request'):
        requests.get('https://connector.example.test/messages')
    with pytest.raises(AssertionError, match='blocked unmocked HTTP request'):
        requests.get('http://127.0.0.1:7787/api/settings')
    with pytest.raises(AssertionError, match='blocked unmocked IMAP connection'):
        imaplib.IMAP4_SSL('imap.example.test')
    with pytest.raises(AssertionError, match='blocked unmocked SMTP connection'):
        smtplib.SMTP_SSL('smtp.example.test')

    async def async_request():
        async with httpx.AsyncClient() as client:
            await client.get('https://async-connector.example.test/messages')
    with pytest.raises(AssertionError, match='blocked unmocked async HTTP request'):
        asyncio.run(async_request())


def test_only_disposable_python_ptys_and_mocked_headless_workers_can_launch():
    with pytest.raises(AssertionError, match='blocked unmocked subprocess'):
        spawn.popen(['fixture-agent', '--work'])
    with pytest.raises(AssertionError, match='blocked unmocked PTY worker'):
        terminal.Term(['fixture-agent'], os.getcwd(), 'fixture')
    with pytest.raises(AssertionError, match='blocked unmocked subprocess'):
        subprocess.run([sys.executable, '-c', "open('owner-file', 'w').write('escape')"])

    with mock.patch('taskuary.spawn.popen', return_value='fake-child'):
        assert spawn.popen(['fixture-agent']) == 'fake-child'


def test_git_guard_rejects_owner_config_writes_and_url_remotes(tmp_path):
    checkout = Path(__file__).resolve().parents[2]
    with pytest.raises(AssertionError, match='blocked unmocked subprocess'):
        subprocess.run(['git', 'config', 'alias.fixture-escape', '!echo unsafe'], cwd=checkout)
    with pytest.raises(AssertionError, match='blocked unmocked subprocess'):
        subprocess.run(['git', 'fetch', 'https://git.example.test/owner/repo'], cwd=tmp_path)


def test_open_session_cannot_write_claude_hooks_into_the_checkout(tmp_path):
    checkout = Path(__file__).resolve().parents[2]
    settings = checkout / '.claude' / 'settings.local.json'
    before = settings.read_bytes() if settings.exists() else None

    assert hooks.install(str(checkout), 'fixture-token') is False
    assert (settings.read_bytes() if settings.exists() else None) == before

    disposable_checkout = tmp_path / 'checkout'
    disposable_checkout.mkdir()
    assert hooks.install(str(disposable_checkout), 'fixture-token') is True
    assert (disposable_checkout / '.claude' / 'settings.local.json').exists()


def test_lifespan_records_no_op_scheduler_and_connector_boundaries(test_safety_events):
    start = len(test_safety_events)
    with TestClient(server.app) as client:
        assert client.get('/api/health').status_code == 200
    events = set(test_safety_events[start:])

    assert {('lifespan boundary', name) for name in (
        'WhatsApp bridge', 'startup catch-up', 'poll scheduler', 'waitroom watcher')} <= events


def test_fixture_subprocesses_receive_distinct_homes_and_registered_api(isolated_process_env, allow_test_port):
    with __import__('socket').socket() as sock:
        sock.bind(('127.0.0.1', 0))
        port = allow_test_port(sock.getsockname()[1])
    first = isolated_process_env(port=port)
    second = isolated_process_env(port=port)

    assert first['TASKUARY_HOME'] != second['TASKUARY_HOME']
    assert first['TASKUARY_HOME'] != os.environ['TASKUARY_HOME']
    assert first['HOME'] != second['HOME']
    assert first['AGENT_BROWSER_HOME'] != second['AGENT_BROWSER_HOME']
    assert first['TASKUARY_API'] == f'http://127.0.0.1:{port}'
    assert 'TASKUARY_ALLOW_TEST_HOME' not in first


def test_python_test_child_remains_available_for_native_pty_regressions():
    child = terminal.Term([sys.executable, '-c', "print('synthetic-child-ok')"], os.getcwd(), 'fixture')
    try:
        import time
        end = time.time() + 20
        while time.time() < end and 'synthetic-child-ok' not in child.scrollback():
            time.sleep(.05)
        assert 'synthetic-child-ok' in child.scrollback()
    finally:
        child.close()
        terminal.SESSIONS.pop(child.sid, None)
