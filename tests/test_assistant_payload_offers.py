"""What the conversation offers under an answer is decided by what PRODUCED it (the owner, 2026-10-21): a playbook drafted in the chat
is approved in the chat, and "Make recurring report" stands only under an answer that reading data produced - never by its words."""
import json
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, proposals, server, sessionrecord
from taskuary.store import MemoryStore

PB = '# Send our W-9\nwhen: a customer asks for our W-9\nuses: files\nsteps: attach it\nalone: all\nask first: bank details\ndone when: sent\n'


def payload(s, tid):
    with mock.patch.object(server, 'store', s):
        return TestClient(server.app).get(f'/api/tasks/{tid}/assistant').json()


def chat(s, **task):
    tid = s.create_task({'Title': 'A question', 'Kind': 'general', **task}, 't')
    s.add_comment(tid, 'owner', general.USER_TYPE, 'How did vendor spend move?')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'It rose 8% on July.')
    return tid


def test_an_answer_no_data_produced_offers_no_recurring_report_whatever_it_says():
    s = MemoryStore(); tid = chat(s)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Here is your weekly report of the numbers, run it every Monday.')
    assert payload(s, tid)['reportLike'] is False


def test_a_workflow_or_report_run_and_a_look_up_through_the_tool_door_do():
    s = MemoryStore()
    assert payload(s, chat(s, Source='workflow'))['reportLike'] is True
    assert payload(s, chat(s, Source='report'))['reportLike'] is True
    tid = chat(s)
    reply = [c for c in s.list_comments(tid) if c['ActorType'] == general.ASSISTANT_TYPE][-1]['CommentId']
    sessionrecord.keep_turn(tid, reply, [{'type': 'tool_call', 'name': 'Bash', 'detail': {'args': {
        'command': 'curl -s -X POST "$TASKUARY_URL/api/tools/run" -d \'{"type": "mssql", "query": "select 1"}\'',
        'description': 'Read vendor spend from SQL Server'}}}])
    assert payload(s, tid)['reportLike'] is True


def test_a_playbook_drafted_in_the_chat_is_handed_to_the_chat_with_its_approve():
    s = MemoryStore(); tid = chat(s, SourceRef='assistant:playbook')
    made = proposals.queue(s, tid, {'action': 'write_playbook', 'slug': 'new', 'text': PB}, 'assistant')
    p = payload(s, tid)
    assert [r['ReviewId'] for r in p['playbookDrafts']] == [made['reviewId']]
    assert json.loads(p['playbookDrafts'][0]['DraftText'])['action'] == 'write_playbook'
    s.decide_review(made['reviewId'], 'rejected', None, 'owner', '')
    assert payload(s, tid)['playbookDrafts'] == []
