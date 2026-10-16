"""An upstream ending is a status BESIDE the agent's write-up, never in place of it (the owner, 2026-10-12: "what happened to
the detail of what the agent did? it was there and then disappeared?"). The agent merged its own pull request; the owner
saved the session; seconds later the poll saw the merge and wrapped the session AGAIN with "was merged on GitHub" as the
agent's last message - so the card swapped the agent's account for our one-liner, and the draft it had left was retired
while the page still offered "Read the draft"."""
import json
from unittest import mock

import pytest

from taskuary import channels, github, session_artifacts, sessionrecord, terminal
from taskuary.store import MemoryStore

ENDED = 'You merged this pull request on GitHub (northwind/portal#41), so there is nothing left to do here.'
SAID = 'PR #41 is merged into main as a squash commit, pinned to the commit I reviewed. CI never ran on it; the suite passed here.'


@pytest.fixture
def home(tmp_path, monkeypatch):
    monkeypatch.setattr(sessionrecord, '_home', lambda: tmp_path)
    monkeypatch.setattr(sessionrecord, '_FOUND', {})
    (tmp_path / 'artifacts').mkdir()
    monkeypatch.setattr(session_artifacts, 'root', lambda: tmp_path / 'artifacts')
    return tmp_path


def saved_session(s, steps_at='2020-01-01T09:00:00Z'):
    """A pull-request task whose session the owner already saved: the agent merged, its write-up is filed, a reply drafted."""
    tid = s.create_task({'Title': 'Review PR for the export fix', 'Kind': 'coding', 'Status': 'open', 'Source': 'github',
                         'Assignee': 'agent:coding'}, 'router')
    mid = s.add_message({'TaskId': tid, 'ExternalId': 'gh:northwind/portal#41', 'ConversationId': 'gh:northwind/portal#41',
                         'Channel': 'github', 'Subject': 'northwind/portal#41 Fix the export', 'FromName': 'erin-blake',
                         'FromEmail': 'erin-blake@users.noreply.github.com', 'BodyText': 'Fixes the export.', 'Status': 'routed'})
    s.add_transcript(tid, 'pane1', 'merged it', agent='coding', brain='claude', ext_id='x1')
    sessionrecord._saved_path(tid, 'pane1').write_text(json.dumps({'source': 'Claude Code log', 'steps': [
        {'k': 'tool', 'name': 'Bash', 'text': 'Squash-merge PR 41', 'at': steps_at},
        {'k': 'said', 'text': SAID, 'at': steps_at}]}), encoding='utf-8')
    s.add_comment(tid, 'coding', 'agent', f'AGENT REPORT\nDetermination: merged\nActions: gh pr merge 41\nSummary: merged #41\n\nLAST MESSAGE\n{SAID}')
    s.tag_task(tid, terminal.SAVED, True, 'owner')
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Merged - thanks, Erin.'})
    return tid, rid


def test_a_saved_session_is_not_wrapped_again_when_its_pr_merges(home):
    s = MemoryStore(); tid, rid = saved_session(s)
    with mock.patch('taskuary.wrapup.wrap') as wrap:
        channels.close_upstream_ended(s, tid, ENDED, 'owner')
    wrap.assert_not_called()
    reports = [c['Body'] for c in s.list_comments(tid) if c['Body'].startswith('AGENT REPORT')]
    assert len(reports) == 1 and SAID in reports[0]
    assert s.get_task(tid)['Status'] == 'done'
    # the draft is decided, not left to be swept away: Close out still has it to read, and "not needed" is its word
    assert s.get_review(rid)['Status'] == 'no_reply'
    assert [c['Body'] for c in s.list_comments(tid) if c.get('Actor') == 'router'] == [ENDED]


def test_the_record_keeps_the_agents_words_and_adds_the_ending(home):
    s = MemoryStore(); tid, _ = saved_session(s)
    channels.close_upstream_ended(s, tid, ENDED, 'owner')
    rec = sessionrecord.record(s, tid)
    assert rec['sessions'][0]['result'] == SAID
    assert rec['ended']['text'] == ENDED and rec['ended']['at']


def test_a_rewrap_already_filed_does_not_replace_the_last_message(home):
    """Tasks the old ending already re-wrapped: the second report's "last message" was our sentence, filed after the
    session's last step. The agent's own words stay the result."""
    s = MemoryStore(); tid, _ = saved_session(s)
    s.add_comment(tid, 'router', 'agent', ENDED)
    s.add_comment(tid, 'coding', 'agent', f'AGENT REPORT\nDetermination: merged\nActions: gh pr merge 41\nSummary: merged #41\n\n'
                                          f'LAST MESSAGE\nnorthwind/portal#41 was merged on GitHub - {ENDED}')
    assert sessionrecord.record(s, tid)['sessions'][0]['result'] == SAID


def test_a_session_that_worked_again_after_its_report_gets_its_new_last_message(home):
    """...but a session resumed and wrapped again DID speak since: its newer last message is the result."""
    s = MemoryStore(); tid, _ = saved_session(s, steps_at='2099-01-01T09:00:00Z')
    s.add_comment(tid, 'coding', 'agent', 'AGENT REPORT\nDetermination: follow-up\nActions: none\nSummary: answered\n\nLAST MESSAGE\nAlso fixed the CSV header.')
    assert sessionrecord.record(s, tid)['sessions'][0]['result'] == 'Also fixed the CSV header.'


def test_a_live_session_is_still_wrapped_with_no_words_put_in_its_mouth(home):
    s = MemoryStore(); tid, _ = saved_session(s)
    s.tag_task(tid, terminal.SAVED, False, 'owner')            # a session running on it: the normal ending
    with mock.patch('taskuary.wrapup.wrap') as wrap:
        channels.close_upstream_ended(s, tid, ENDED, 'owner')
    assert wrap.call_args.kwargs.get('close') is True and not wrap.call_args.kwargs.get('final_message')


SRC = {'Address': 'northwind/portal', 'ConfigJson': json.dumps({'issues': 'tasks', 'prs': 'tasks'})}


def test_our_comment_on_an_item_that_ended_in_the_same_poll_comes_back(home):
    """The agent commented and merged in one go: the ended item's conversation was never read again, so what it said
    upstream was nowhere on the task. Ours comes back as sent; anybody else's on a finished item does not become work."""
    s = MemoryStore(); s.set_setting('github_login', 'alex-doyle', 'test')
    tid, _ = saved_session(s)
    item = {'number': 41, 'title': 'Fix the export', 'body': 'Fixes the export.', 'state': 'closed', 'merged_at': '2026-10-12T11:44:03Z',
            'pull_request': {'merged_at': '2026-10-12T11:44:03Z'}, 'user': {'login': 'erin-blake', 'type': 'User'},
            'author_association': 'CONTRIBUTOR', 'updated_at': '2026-10-12T11:44:03Z', 'html_url': 'https://github.com/northwind/portal/pull/41'}
    said = {'id': 7, 'body': 'Merged as reviewed - thanks!', 'user': {'login': 'alex-doyle', 'type': 'User'},
            'created_at': '2026-10-12T11:43:58Z', 'html_url': 'https://github.com/northwind/portal/pull/41#c7'}
    other = {'id': 8, 'body': 'Nice one', 'user': {'login': 'ray-colton', 'type': 'User'},
             'created_at': '2026-10-12T11:45:00Z', 'html_url': 'https://github.com/northwind/portal/pull/41#c8'}
    from datetime import datetime, timedelta
    with mock.patch.object(github, 'list_items', return_value=[item]), mock.patch.object(github, 'body_images', return_value=[]), \
         mock.patch.object(github, 'closed_by', return_value='alex-doyle'), \
         mock.patch.object(github, 'issue_comments', return_value=[said, other], create=True):
        channels.ingest_github_issues(s, SRC, 'tok', datetime.now() - timedelta(hours=1))
    out = [m for m in s.task_detail(tid)['messages'] if m.get('Direction') == 'out']
    assert [m['BodyText'] for m in out] == ['Merged as reviewed - thanks!']
    assert not s.message_exists('gh:northwind/portal#41:c8')
    assert s.get_task(tid)['Status'] == 'done'


def test_an_advisor_task_about_a_pull_request_already_here_wears_the_pull_requests_mark():
    """The Advisor read a PR that had arrived and said "review it": the work came from the PR, so the row shows the PR's
    icon beside the PR's rank. Something that joined AFTER the Advisor opened the task leaves the Advisor's mark."""
    from taskuary.processing_all import task_mark
    t = {'TaskId': 9, 'Source': 'assistant', 'SourceRef': 'assistant:idea:3', 'CreatedAt': '2026-10-12 07:29:05'}
    pr = {'TaskId': 9, 'Channel': 'github', 'Direction': 'in', 'CreatedAt': '2026-10-12 07:27:28'}
    idea = {'TaskId': 9, 'Channel': 'assistant', 'Direction': 'in', 'CreatedAt': '2026-10-12 07:29:05'}
    later = {**pr, 'Channel': 'email', 'CreatedAt': '2026-10-12 09:00:00'}
    assert task_mark([t], [idea, pr]) == 'github'
    assert task_mark([t], [idea, later]) == 'assistant'
    assert task_mark([t]) == 'assistant'
    assert task_mark([{**t, 'SourceRef': 'assistant:handoff'}], [pr]) is None          # the owner's own work names no channel
    assert task_mark([{**t, 'Source': 'email', 'SourceRef': ''}], [pr]) == 'email'     # only the Advisor's mark moves
