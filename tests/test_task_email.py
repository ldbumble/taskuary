"""Email a summary, from inside a task - whoever started it (the owner, 2026-10-09: "even though i started it from the new button
i want to be able to create email to send to someone and notify it's done"; then "add from mailbox picker and teams/chat too").
It was a one-shot writer's email in the agent's place; now (the owner, 2026-11-27: "side model should never work in agent canvas")
what he fills in is his line to the task's agent, which writes it and raises its card. The send road behind that card - a task's
email (slots.py), its files, its mailbox, a chat - is what the rest pins.
"""
import json
from unittest import mock

import pytest
from fastapi.testclient import TestClient

from taskuary import buttons, general, outbound, outbox, server, session_artifacts as sa, slots, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

SENT = {'channel': 'email', 'to': ['erin@northwind.example'], 'mailbox': 'alex@northwind.example'}


@pytest.fixture
def s(): return MemoryStore()


def work(s, title='Corporate supervisor upload'):
    tid = Factory(s).task(title=title, kind='coding', source='manual')
    sa.result(s, tid, 'The supervisor template downloads from the Corporate Supervisors page; 180 tests pass.')
    return tid


def letter(s, tid, **kw):
    "The agent's own card for a task's email (slots.draft) - what his ask now brings back."
    out = slots.draft(s, tid, kw.pop('text', 'Hi Erin,\n\nThe supervisor upload is live.'), to=kw.pop('to', 'erin@northwind.example'),
                      subject=kw.pop('subject', 'Supervisor upload is live'), agent='assistant', **kw)
    assert out.get('ok'), out
    return out['review_id']


def ask(s, tid, body):
    told = []
    with mock.patch.object(server, 'store', s), mock.patch.object(general, 'to_agent', side_effect=lambda st, t, said, *a, **k: told.append((t, said, k.get('frm'))) or 'woke'), \
         mock.patch('taskuary.outbox.draft_message', side_effect=AssertionError('a side model wrote it')), \
         mock.patch('taskuary.outbox.subject_for', side_effect=AssertionError('a side model wrote its subject')):
        r = TestClient(server.app).post(f'/api/tasks/{tid}/emails', json=body)
    return r, told


def test_email_a_summary_is_his_line_to_the_tasks_agent_with_everything_he_picked(s):
    tid, other = work(s), work(s, 'Another task')
    mine = sa.result(s, tid, 'mine')['ArtifactId']
    r, told = ask(s, tid, {'to': 'erin@northwind.example', 'cc': ['gail@northwind.example'], 'mailbox': 'ops@northwind.example',
                           'about': 'tell her she can start Monday', 'attach': [{'kind': 'artifact', 'id': mine}]})
    assert r.status_code == 200 and r.json()['asked'], r.text
    [(t, said, frm)] = told
    assert (t, frm) == (tid, 'owner')
    for part in (buttons.label('share'), 'erin@northwind.example', 'cc gail@northwind.example', 'from ops@northwind.example',
                 s.get_task_artifact(mine)['Name'], 'tell her she can start Monday'):
        assert part in said, (part, said)
    assert not slots.open_(s, tid), 'no email is filed in his name - the agent raises its own card'
    # ...and only this task's files are named: the ids come from the page, and another task's file is not this one's
    theirs = sa.result(s, other, 'not this one')['ArtifactId']
    s._exec('UPDATE task_artifact SET Name=? WHERE ArtifactId=?', ('another-tasks-file.md', theirs))
    _, [(_, said, _)] = ask(s, tid, {'to': 'erin@northwind.example', 'attach': [{'kind': 'artifact', 'id': theirs}]})
    assert 'another-tasks-file.md' not in said, said


def test_a_chat_target_is_named_by_its_name_and_channel(s):
    tid = work(s)
    _, [(_, said, _)] = ask(s, tid, {'to': '19:ops@thread.v2', 'channel': 'teams', 'name': 'Ops channel'})
    assert said == f"{buttons.label('share')} to Ops channel on teams"


def test_the_writer_road_is_gone():
    assert not hasattr(outbox, 'task_email') and not hasattr(outbox, 'redraft_review')


def test_the_files_on_its_card_go_with_it_when_it_is_sent(s):
    tid = work(s)
    rid = letter(s, tid)
    verdicts.attach(s, rid, 'corporate-supervisors-template.xlsx', b'PK\x03\x04 sheet', 'owner')
    with mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch.object(outbound, 'can_reply', return_value=True), mock.patch('taskuary.learning.learn_from'):
        verdicts.decide(s, s.get_review(rid), 'approve')
    assert [f['name'] for f in sent.call_args.kwargs['attachments']] == ['corporate-supervisors-template.xlsx']
    assert s.get_task(tid)['Status'] == 'open'                                                 # sent - Mark done is the owner's (2026-10-18)


def test_send_out_hands_the_files_to_the_mailbox_and_a_chat_refuses_them(s):
    files = [{'name': 'a.xlsx', 'path': 'x', 'size': 1}]
    with mock.patch.object(outbound, 'can_reply', return_value=True), \
         mock.patch.object(s, 'get_connector_by_type', return_value={'Active': 1}), \
         mock.patch.object(outbound, 'send_email', return_value=SENT) as mail:
        outbound.send_out(s, 'email', ['erin@northwind.example'], 'Done', 'It is live.', attachments=files)
    assert mail.call_args.kwargs['attachments'] == files
    with mock.patch.object(outbound, 'can_reply', return_value=True), pytest.raises(RuntimeError, match='cannot carry'):
        outbound.send_out(s, 'teams', ['chat-1'], 'Done', 'It is live.', attachments=files)


def two_mailboxes(s):
    a = s.save_connector({'Type': 'outlook', 'Name': 'Outlook', 'Active': 1, 'ConfigJson': json.dumps({'address': 'alex@northwind.example'})}, 't')
    b = s.save_connector({'Type': 'imap', 'Name': 'Ops IMAP', 'Active': 1, 'ConfigJson': json.dumps({'address': 'ops@northwind.example'})}, 't')
    return a, b


def test_every_connected_mailbox_is_one_from_choice(s):
    a, b = two_mailboxes(s)
    assert [(m['address'], m['connector_id']) for m in outbound.mailboxes(s)] == [('alex@northwind.example', a), ('ops@northwind.example', b)]


def test_the_mailbox_picked_is_the_one_it_is_sent_from(s):
    a, b = two_mailboxes(s)
    with mock.patch('taskuary.imapmail.send_smtp', return_value=SENT) as smtp, mock.patch.object(outbound, 'send_email') as graph:
        outbound.send_out(s, 'email', ['erin@northwind.example'], 'Done', 'It is live.', mailbox='ops@northwind.example')
    assert smtp.call_args.args[1]['ConnectorId'] == b and not graph.called
    with mock.patch.object(outbound, 'send_email', return_value=SENT) as graph:
        outbound.send_out(s, 'email', ['erin@northwind.example'], 'Done', 'It is live.', mailbox='alex@northwind.example')
    assert (graph.call_args.kwargs['mailbox'], graph.call_args.kwargs['connector_id']) == ('alex@northwind.example', a)


def test_a_chat_message_goes_to_the_chat_and_leaves_the_task_open_when_sent(s):
    tid = work(s)
    rid = letter(s, tid, to='19:ops@thread.v2', channel='teams', name='Ops channel', subject='')
    env = json.loads(s.get_review(rid)['Deliver'])
    assert (env['channel'], env['to']) == ('teams', ['19:ops@thread.v2'])
    with mock.patch('taskuary.outbound.send_out', return_value={'channel': 'teams', 'to': ['19:ops@thread.v2']}) as sent, \
         mock.patch.object(outbound, 'send_block', return_value=''), mock.patch.object(outbound, 'can_reply', return_value=True), \
         mock.patch('taskuary.learning.learn_from'):
        verdicts.decide(s, s.get_review(rid), 'approve')
    assert sent.call_args.args[1:3] == ('teams', ['19:ops@thread.v2']) and s.get_task(tid)['Status'] == 'open'


def test_it_signs_with_the_owners_own_name(s):
    s.set_setting('owner_name', 'Alex Doyle', 'test'); s.set_setting('owner_title', 'Head of Operations', 'test')
    seen = {}
    def llm(system, user, max_tokens=0):
        seen['system'] = system
        return 'Done.'
    outbox.draft_message(s, 'email', ['erin@northwind.example'], 'tell her', llm=llm)
    assert 'You ARE Alex Doyle' in seen['system']
    assert 'YOUR NAME, for any signature: Alex Doyle - Head of Operations' in seen['system']


def test_a_task_email_with_no_message_behind_it_still_offers_send(s):
    tid = work(s)
    rid = letter(s, tid)
    s.save_connector({'Type': 'outlook', 'Name': 'Work mail', 'Active': 1}, 't')
    with mock.patch.object(server, 'store', s), mock.patch.object(outbound, 'can_reply', return_value=True):
        d = TestClient(server.app).get(f'/api/tasks/{tid}').json()
    rv = next(r for r in d['reviews'] if r['ReviewId'] == rid)
    assert rv['CanSend'] is True                                             # Send, not "Copy & close - nothing arrived"


def test_a_task_email_with_no_mailbox_is_never_ready_to_send_anywhere(s):
    """The walk, 2026-11-21: with no mailbox connected the card said "No mailbox is connected" and Connect email, while its header said
    "ready to send" and the same card had offered a live Send. Whether it can leave is one answer: the card, the page's chip and the task's state."""
    from taskuary import taskstate
    tid = work(s)
    rid = letter(s, tid)
    with mock.patch.object(server, 'store', s): d = TestClient(server.app).get(f'/api/tasks/{tid}').json()
    rv = next(r for r in d['reviews'] if r['ReviewId'] == rid)
    assert rv['Connect'] and rv['CanSend'] is False, rv
    assert taskstate.status(s, s.get_task(tid))['key'] == 'unsendable'
