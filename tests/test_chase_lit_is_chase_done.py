"""A LIT CHASE CAN BE PRESSED (the Advisor design, phase A; the owner's ruling 8, 2026-10-23: Chase lights after 3 working days). The
rule lit Chase on a wait past its day and on a late goal step, but the act behind it took only a slipped follow-up and refused the
rest ("Nothing has slipped...") - a lit button that can only be refused. Now the Chase the rule lights is the one the act runs: a reply
to their newest mail on the task, else a new message to them from it - a draft for the owner's yes, never a send. Invented people."""
from datetime import datetime, timedelta
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import concierge, funnel, rulebook, server
from taskuary.store import MemoryStore
from taskuary.testing import Factory

RAY = 'ray.colton@northwind.example'
def at(d=0): return (datetime.now() - timedelta(days=d)).strftime('%Y-%m-%d %H:%M:%S')


def _waiting(s, days, theirs=False):
    f = Factory(s)
    t = f.task(title='Vendor W-9', kind='task', status='waiting'); s._exec('UPDATE task SET WaitingOn=? WHERE TaskId=?', (RAY, t))
    f.message(task_id=t, subject='W-9?', direction='out', sent_at=at(d=days))
    if theirs: f.message(task_id=t, subject='Re: W-9?', body='Looking for it.', from_name='Ray Colton', from_email=RAY, sent_at=at(d=days + 1))
    return t, {'key': f'task:{t}', 'kind': 'todo', 'lane': 'theirs', 'tid': t}


def test_chase_is_offered_only_where_it_can_go_and_the_gate_agrees():
    s = MemoryStore()
    t, it = _waiting(s, 1)
    assert rulebook.adds(s, it) == [] and concierge.cannot(it, 'chase', s), 'a day is not late: no Chase, and a typed one is refused'
    t, it = _waiting(s, 7)
    assert rulebook.chase_thread(s, it) == {'tid': t, 'who': RAY, 'mid': None}, 'nothing of theirs to answer: a new message to them'
    assert rulebook.adds(s, it) == ['chase'] and concierge.cannot(it, 'chase', s) == ''
    assert concierge.cannot(it, 'let_go', s), 'Let it go stays the slipped lane\'s'
    t, it = _waiting(s, 7, theirs=True)
    assert rulebook.chase_thread(s, it)['mid'], 'their own mail on the task is what the chase answers'


def test_pressing_the_lit_chase_drafts_a_message_to_them_and_sends_nothing():
    s = MemoryStore()
    t, it = _waiting(s, 7)
    with mock.patch.object(server, 'store', s), mock.patch.object(funnel, 'next_item', lambda *a, **k: it),          mock.patch('taskuary.outbox.draft_message', lambda *a, **k: 'Hi Ray, any news on the W-9?'),          mock.patch('taskuary.outbox.subject_for', lambda *a, **k: 'W-9'), mock.patch('taskuary.capabilities.send_refusal', lambda *a, **k: ''):
        c = TestClient(server.app)
        op = c.post('/api/operations', json={'kind': 'task.chase', 'target': t, 'params': {'key': it['key']}}).json()
        assert 'id' in op, op
        res = c.post(f"/api/operations/{op['id']}/execute", json={'version': op['version']})
    assert res.status_code == 200, res.text
    r = res.json()['outcome']
    rv = s.get_review(int(r['reviewId']))
    assert rv['Status'] == 'pending' and rv['Reason'].startswith('chase:1') and RAY in (rv.get('Deliver') or '')
    assert not s._rows("SELECT * FROM message WHERE TaskId=? AND Direction='out' AND Status='sent' AND CreatedAt>?", (t, at(d=1)))
