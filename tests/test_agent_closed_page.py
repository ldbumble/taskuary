"""An agent that closed its own task leaves its write-up, and the task page says who closed it and why (the owner, 2026-10-21:
"when an agent closes a task and no close out is needed, I have no idea what the agent did and why it closed").

The page on the table has no list row, so it read the task's state from nothing: the agent's own close looked like "stopped
and saved", and the page opened on Close out with advice for an open task. The detail now carries the list's State and a
one-line reason."""
from unittest import mock

import pytest

from taskuary import general, selfclose, server, taskstate
from taskuary.store import MemoryStore
from taskuary.testing import Factory

ANSWER = 'The nightly run in org/app failed on a missing DEPLOY_KEY secret. I re-added it and the re-run passed.'


@pytest.fixture
def s(monkeypatch):
    s = MemoryStore(); monkeypatch.setattr(server, 'store', s); selfclose._DONE.clear()
    return s


def worked(s):
    """A general task from a scheduled run's failure notice, the agent's answer in its chat - nobody to answer back."""
    tid = Factory(s).task(title='Check the failed nightly run', kind='general', status='in_progress', source='report')
    Factory(s).message(tid, channel='report', Subject='Nightly run failed - org/app', FromName='Nightly report')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Check why the nightly run failed.')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, ANSWER)
    return tid


def agent_closes(s, tid, said='the run failed on a missing secret; re-added it and the re-run passed'):
    with mock.patch('taskuary.playbooks.draft', return_value=None):
        return selfclose.declare(s, tid, said, 'assistant')


def test_the_agents_own_ending_leaves_its_write_up_and_the_task_open(s):
    """The agent never closes a task (the owner, 2026-11-07): its ending is written up, and the close is the owner's Mark done."""
    tid = worked(s)
    out = agent_closes(s, tid)
    assert out['ended'] and not out['closed'] and s.get_task(tid)['Status'] not in ('done', 'dropped')
    reports = [c['Body'] for c in s.list_comments(tid) if str(c['Body']).startswith('AGENT REPORT')]
    assert reports == [f'AGENT REPORT\n{ANSWER}']


def test_the_page_says_what_the_agent_did_and_that_the_close_is_the_owners(s):
    tid = worked(s); agent_closes(s, tid)
    d = server.task_detail(tid)
    assert d['state'] != 'closed' and d['closedWhy'] is None                                                       # nothing closed it
    assert s.list_comments(tid)[-1]['Body'] == ('The agent says it is finished: the run failed on a missing secret; re-added it and the '
                                                 're-run passed. You can close it with Mark done.')
    assert server.task_detail(tid)['stage'] != 'closed_by_agent'


def test_with_no_done_sentence_the_reason_is_the_reports_first_line(s):
    tid = worked(s); agent_closes(s, tid, said='')
    assert s.list_comments(tid)[-1]['Body'] == f'The agent says it is finished: {ANSWER.rstrip(".")}. You can close it with Mark done.'


def test_a_task_the_owner_closed_carries_no_agent_reason(s):
    tid = worked(s)
    s.update_task(tid, {'Status': 'done'}, 'owner')
    d = server.task_detail(tid)
    assert d['state'] == 'closed' and d['closedWhy'] is None


def test_an_open_task_has_no_reason_line(s):
    tid = worked(s)
    assert taskstate.closed_why(s, s.get_task(tid)) is None
