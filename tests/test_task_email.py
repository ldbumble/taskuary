"""Email someone, from inside a task - whoever started it (the owner, 2026-10-09: "even though i started it from the new button
i want to be able to create email to send to someone and notify it's done"). The AI writes it from the owner's words and what
the work found; it waits in Close out as one of the task's emails, with any of the task's files on it; sending it closes the
task. And what rode on such an email now goes with it: a message the owner STARTED was sent without its files.
"""
import json
from unittest import mock

import pytest

from taskuary import outbound, outbox, session_artifacts as sa, slots, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory

SENT = {'channel': 'email', 'to': ['erin@northwind.example'], 'mailbox': 'alex@northwind.example'}


@pytest.fixture
def s(): return MemoryStore()


def work(s, title='Corporate supervisor upload'):
    tid = Factory(s).task(title=title, kind='coding', source='manual')
    sa.result(s, tid, 'The supervisor template downloads from the Corporate Supervisors page; 180 tests pass.')
    return tid


def email(s, tid, **kw):
    seen = {}
    def llm(system, user, max_tokens=0):
        if max_tokens <= 40: return 'Supervisor upload is live'                   # the subject line
        seen['user'] = user
        return 'Hi Erin,\n\nThe supervisor upload is live.'
    with mock.patch.object(outbound, 'can_reply', return_value=True):
        out = outbox.task_email(s, tid, kw.pop('to', 'Erin Blake <erin@northwind.example>'), kw.pop('about', 'tell her it is done'),
                                llm=llm, **kw)
    return out, seen


def test_the_ai_writes_it_from_the_words_and_the_work_and_it_waits_on_the_task(s):
    tid = work(s)
    out, seen = email(s, tid, cc=['gail@northwind.example'])
    assert 'tell her it is done' in seen['user'] and '180 tests pass' in seen['user']       # the brief AND what was found
    rv = s.get_review(out['review_id'])
    env = json.loads(rv['Deliver'])
    assert (rv['Kind'], rv['Status'], rv['DraftText']) == (slots.KIND, 'pending', 'Hi Erin,\n\nThe supervisor upload is live.')
    assert (env['to'], env['cc'], env['about']) == (['erin@northwind.example'], ['gail@northwind.example'], 'tell her it is done')
    assert [i['out']['to'] for i in slots.open_(s, tid)] == ['erin@northwind.example']
    assert s.get_task(tid)['Status'] == 'open'                                                 # nothing is sent here


def test_the_files_picked_ride_on_it_and_go_with_it_when_it_is_sent(s):
    tid = work(s)
    out, _ = email(s, tid, files=[('corporate-supervisors-template.xlsx', b'PK\x03\x04 sheet')])
    assert out['attached'] == ['corporate-supervisors-template.xlsx']
    with mock.patch('taskuary.outbound.send_out', return_value=SENT) as sent, mock.patch.object(outbound, 'send_block', return_value=''), \
         mock.patch('taskuary.learn.learn_from'):
        verdicts.decide(s, s.get_review(out['review_id']), 'approve')
    assert [f['name'] for f in sent.call_args.kwargs['attachments']] == ['corporate-supervisors-template.xlsx']
    assert s.get_task(tid)['Status'] == 'done'                                                 # sending it was the last thing owed


def test_a_bad_address_or_a_closed_task_is_refused(s):
    tid = work(s)
    with pytest.raises(ValueError, match='not a valid email'): email(s, tid, to='Erin')
    s.update_task(tid, {'Status': 'done'}, 'owner')
    with pytest.raises(ValueError, match='closed'): email(s, tid)


def test_send_out_hands_the_files_to_the_mailbox_and_a_chat_refuses_them(s):
    files = [{'name': 'a.xlsx', 'path': 'x', 'size': 1}]
    with mock.patch.object(outbound, 'can_reply', return_value=True), \
         mock.patch.object(s, 'get_connector_by_type', return_value={'Active': 1}), \
         mock.patch.object(outbound, 'send_email', return_value=SENT) as mail:
        outbound.send_out(s, 'email', ['erin@northwind.example'], 'Done', 'It is live.', attachments=files)
    assert mail.call_args.kwargs['attachments'] == files
    with mock.patch.object(outbound, 'can_reply', return_value=True), pytest.raises(RuntimeError, match='cannot carry'):
        outbound.send_out(s, 'teams', ['chat-1'], 'Done', 'It is live.', attachments=files)


def test_regenerate_writes_an_owner_started_email_again_but_never_an_agents(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    tid = work(s)
    out, _ = email(s, tid)
    theirs = slots.draft(s, tid, 'Written by the agent.', to='paula@northwind.example', subject='x', agent='coder')['review_id']
    old, server.store = server.store, s
    try:
        with mock.patch('taskuary.outbox.draft_message', return_value='Hi Erin, it is live - the template is attached.'):
            ok = TestClient(server.app).post(f"/api/reviews/{out['review_id']}/draft", json={})
            no = TestClient(server.app).post(f'/api/reviews/{theirs}/draft', json={})
    finally: server.store = old
    assert ok.status_code == 200 and s.get_review(out['review_id'])['DraftText'] == 'Hi Erin, it is live - the template is attached.'
    assert no.status_code == 422


def test_the_endpoint_sends_only_this_tasks_files(s):
    from fastapi.testclient import TestClient
    from taskuary import server
    tid, other = work(s), work(s, 'Another task')
    mine = sa.result(s, tid, 'mine')['ArtifactId']
    theirs = sa.result(s, other, 'not this one')['ArtifactId']
    old, server.store = server.store, s
    try:
        with mock.patch('taskuary.outbox.task_email', return_value={'ok': True}) as made:
            bad = TestClient(server.app).post(f'/api/tasks/{tid}/emails', json={'to': 'erin@northwind.example',
                                                                               'attach': [{'kind': 'artifact', 'id': theirs}]})
            good = TestClient(server.app).post(f'/api/tasks/{tid}/emails', json={'to': 'erin@northwind.example',
                                                                                'attach': [{'kind': 'artifact', 'id': mine}]})
    finally: server.store = old
    assert bad.status_code == 422 and good.status_code == 200
    assert [n for n, _ in made.call_args.args[6]] == [s.get_task_artifact(mine)['Name']]
