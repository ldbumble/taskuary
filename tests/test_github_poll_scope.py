"""A repo picker belongs to one card, and never enables its unconfigured neighbours."""
import json
from unittest import mock

import pytest

from taskuary import channels
from taskuary.store import MemoryStore


def card(store, roles='tool'):
    return store.save_connector({'Type': 'github', 'Name': 'Test GitHub', 'Roles': roles,
                                 'Active': 1, 'Secret': 'test-token'}, 'test')


def repo(store, cid, address, modes=None, active=1):
    return store.save_source({'Channel': 'github', 'Address': address, 'ConnectorId': cid,
                              'Active': active, 'ConfigJson': json.dumps(modes or {})}, 'test')


def test_picker_does_not_enable_another_tool_only_card():
    store = MemoryStore()
    trigger, tool = card(store, 'trigger,tool'), card(store)
    repo(store, trigger, 'northwind/ledger', {'prs': 'tasks'})
    sid = repo(store, tool, 'northwind/portal')
    with mock.patch('taskuary.github.list_items', return_value=[]) as read:
        channels.poll_channels(store)
    assert [call.args[1] for call in read.call_args_list] == ['northwind/ledger']
    assert store.get_source(sid)['LastPolledAt'] is None


def test_picker_does_not_enable_other_repos_on_the_same_tool_card():
    store = MemoryStore(); cid = card(store)
    live = repo(store, cid, 'northwind/ledger', {'prs': 'tasks'})
    off = repo(store, cid, 'northwind/portal')
    with mock.patch('taskuary.github.list_items', return_value=[]) as read:
        channels.poll_channels(store)
    assert [call.args[1] for call in read.call_args_list] == ['northwind/ledger']
    assert store.get_source(live)['LastPolledAt'] is not None
    assert store.get_source(off)['LastPolledAt'] is None


def test_inactive_and_unowned_pickers_do_not_enable_a_card():
    store = MemoryStore(); cid = card(store)
    repo(store, cid, 'northwind/ledger', {'prs': 'tasks'}, active=0)
    repo(store, None, 'northwind/portal', {'issues': 'feed'})
    assert channels._poll_jobs(store) == []


@pytest.mark.parametrize('roles, expected', [('trigger,tool', 'tasks'), ('feed,tool', 'feed'),
                                            ('tool', 'off')])
def test_unconfigured_issues_follow_their_own_card_role(roles, expected):
    store = MemoryStore(); cid = card(store, roles)
    repo(store, cid, 'northwind/ledger', {'prs': 'tasks'})
    common = {'body': 'Synthetic request', 'updated_at': '2026-10-01T10:00:00Z',
              'user': {'login': 'alex'}, 'author_association': 'MEMBER'}
    items = [{**common, 'number': 1, 'title': 'Import issue'},
             {**common, 'number': 2, 'title': 'Import fix', 'pull_request': {}}]
    llm = lambda *a, **kw: '{"intent":"task","why":"synthetic test"}'
    with mock.patch('taskuary.github.list_items', return_value=items), \
         mock.patch('taskuary.llm.build_llm', return_value=llm):
        channels.poll_channels(store)
    messages = store.scan_messages()
    issue = next((m for m in messages if '#1 ' in m['Subject']), None)
    if expected == 'off': assert issue is None
    elif expected == 'feed': assert issue['Status'] == 'feed' and issue['TaskId'] is None
    else: assert issue['TaskId'] is not None
    pr = next(m for m in messages if '#2 ' in m['Subject'])
    assert pr['TaskId'] is not None                  # explicit PR tasks still override every role


def test_explicit_issue_modes_override_tool_and_feed_roles():
    for mode in ('tasks', 'feed', 'replies', 'off'):
        for roles in ({'tool'}, {'feed', 'tool'}):
            assert channels.gh_modes({'ConfigJson': json.dumps({'issues': mode})}, True, roles) == (mode, 'off')
