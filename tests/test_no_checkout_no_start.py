"""A coding task nothing places - no repository named, no path, no folder of the agent's own - never opens in the folder Taskuary
started in. On the owner's machine that is Taskuary's own checkout: a colleague's bug report about another app opened a coding agent
there by itself (the overnight QA, 2026-10-30). The start asks which code instead, and the task says it waits for that answer."""
import json
from unittest import mock
from taskuary import funnel, ingest, terminal
from taskuary.store import MemoryStore


def _store(profile: dict):
    s = MemoryStore()
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude', **profile}))
    return s


def _opened(s, tid) -> bool:
    with mock.patch.object(terminal, 'Term') as T, mock.patch('taskuary.agents._resolve_cmd', return_value=['claude']), \
         mock.patch('taskuary.origin.of_task', new=lambda *a, **k: ('owner', 'test')):
        T.return_value = mock.Mock(sid='nocheckout', cwd='x')
        try: terminal.open_session(s, 'coder', tid)
        finally: terminal.SESSIONS.pop('nocheckout', None)
        return T.called


def test_nothing_places_it_so_it_asks_which_code():
    s = _store({})
    tid = s.create_task({'Title': 'Fix the invoices page crash in the portal', 'Kind': 'coding'}, 'owner')
    try: _opened(s, tid); assert False, 'opened a session in the folder Taskuary started in'
    except ValueError as e: assert funnel.NEEDS_REPO.search(str(e)), e


def test_a_folder_of_its_own_or_no_repository_at_all_still_opens(tmp_path):
    s = _store({'cwd': str(tmp_path)})
    assert _opened(s, s.create_task({'Title': 'a fix', 'Kind': 'coding'}, 'owner'))
    s = _store({})
    assert _opened(s, s.create_task({'Title': 'what does this mean', 'Kind': 'coding', 'Tags': f'repo:{terminal.NO_REPO}'}, 'owner'))


def test_the_automatic_start_holds_for_the_owners_pick_instead_of_retrying():
    s = _store({})
    tid = s.create_task({'Title': 'Fix the invoices page crash in the portal', 'Kind': 'coding', 'Assignee': 'agent:coder'}, 'owner')
    refusal = ValueError('I could not tell which checkout this belongs in: no repository is set up for the coding agent')
    with mock.patch.object(terminal, 'start_on_task', side_effect=refusal), mock.patch('taskuary.blackboard.record_failure') as failed, \
         mock.patch('taskuary.ingest.auto_sessions', return_value=4):
        ingest._auto_code(s, tid)
    assert not failed.called
    assert funnel.held_for_repo(s.get_task(tid))
    assert any('needs a repository' in c['Body'] for c in s.list_comments(tid))
