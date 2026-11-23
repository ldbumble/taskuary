"""What the conversation offers under an answer is decided by what PRODUCED it (the owner, 2026-10-21): a playbook drafted in the chat
is approved in the chat."""
import json
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, proposals, server
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


def test_a_playbook_drafted_in_the_chat_is_handed_to_the_chat_with_its_approve():
    s = MemoryStore(); tid = chat(s, SourceRef='assistant:playbook')
    made = proposals.queue(s, tid, {'action': 'write_playbook', 'slug': 'new', 'text': PB}, 'assistant')
    p = payload(s, tid)
    assert [r['ReviewId'] for r in p['playbookDrafts']] == [made['reviewId']]
    assert json.loads(p['playbookDrafts'][0]['DraftText'])['action'] == 'write_playbook'
    s.decide_review(made['reviewId'], 'rejected', None, 'owner', '')
    assert payload(s, tid)['playbookDrafts'] == []


def test_an_agent_asking_from_a_terminal_on_a_general_task_has_its_question_in_the_canvas():
    """W6 (the UI audit, 2026-10-21): "Agent asked you something" over an empty canvas - the snapshot read the question off the task's
    conversation session only, and an agent asking from a terminal on the task had none, so its question lived in the rail's hover."""
    from taskuary import terminal, workerstate
    s = MemoryStore(); tid = s.create_task({'Title': 'Reconcile the export', 'Kind': 'general', 'Status': 'in_progress'}, 't')
    workerstate.record(s, tid, 'p1', 'working')
    workerstate.record(s, tid, 'p1', 'input_needed', text='Keep the inter-company rows, or drop them?', choices=['Keep', 'Drop'])
    pty = mock.Mock(task_id=tid, sid='p1', alive=True, mode='terminal')
    with mock.patch.dict(terminal.SESSIONS, {'p1': pty}):
        asked = payload(s, tid)['asking']
    assert asked['text'] == 'Keep the inter-company rows, or drop them?' and asked['choices'] == ['Keep', 'Drop'] and asked['sid'] == 'p1'
    # ...and it stays asked once the terminal is gone: an open question is kept with the task until it is answered (the owner, 2026-11-07:
    # "of course it should be saved") - the agent idling out or its pane closing never answers it
    assert (payload(s, tid)['asking'] or {}).get('text') == 'Keep the inter-company rows, or drop them?'


def test_a_held_browser_step_behind_the_front_is_on_no_view_and_the_detail_names_the_line():
    """ONE ACTION BOX AT A TIME (cardqueue; the owner's live task, 2026-11-19): two browser steps held on one task - the second waits its turn,
    and the browser view listed it beside the front, a second Approve. The view gets the front alone; the task's own read names the line."""
    s = MemoryStore(); tid = chat(s, Status='in_progress')
    act = lambda what: s.add_review({'TaskId': tid, 'Kind': 'action', 'Status': 'pending', 'Origin': 'agent', 'Reason': f'held before it ran: {what}',
                                     'DraftText': json.dumps({'action': 'browser_act', 'sid': 'fx', 'site': 'portal.vendor.example', 'what': what, 'command': what})})
    front, behind = act("Send Gail's invite on the vendor portal"), act("Save the portal's new settings")
    assert [r['ReviewId'] for r in payload(s, tid)['browserActs']] == [front]
    with mock.patch.object(server, 'store', s):
        d = TestClient(server.app).get(f'/api/tasks/{tid}').json()
    assert d['queue'] == {'live': [front], 'held': [behind], 'closes': "Save the portal's new settings"}
