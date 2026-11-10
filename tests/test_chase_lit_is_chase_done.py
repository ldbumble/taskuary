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
    # ...on every wait with somebody to write to (whether a day is too soon is the model's to read from the days waited - no threshold here)
    t, it = _waiting(s, 1)
    assert rulebook.adds(s, it) == ['chase'] and concierge.cannot(it, 'chase', s) == '', 'a wait of a day: Chase is on the row'
    nobody = Factory(s).task(title='Lease copy', kind='task', status='waiting')
    gone = {'key': f'task:{nobody}', 'kind': 'todo', 'lane': 'theirs', 'tid': nobody}
    assert rulebook.adds(s, gone) == [] and concierge.cannot(gone, 'chase', s), 'nobody to write to: no Chase, and a typed one is refused'
    t, it = _waiting(s, 7)
    assert rulebook.chase_thread(s, it) == {'tid': t, 'who': RAY, 'mid': None}, 'nothing of theirs to answer: a new message to them'
    assert rulebook.adds(s, it) == ['chase'] and concierge.cannot(it, 'chase', s) == ''
    assert concierge.cannot(it, 'let_go', s), 'Let it go stays the slipped lane\'s'
    t, it = _waiting(s, 7, theirs=True)
    assert rulebook.chase_thread(s, it)['mid'], 'their own mail on the task is what the chase answers'


def test_a_chase_never_goes_to_a_machine_that_wrote_on_the_thread_since():
    # the stress round, 2026-11-10 (the owner the same day: "github emails are not supposed to be respodned to"): the owner asked a colleague,
    # then a signing service's "your envelope was viewed" and a list's digest were filed on the task - and Chase named the newest of them
    s = MemoryStore(); f = Factory(s)
    t = f.task(title='Signed contract', kind='task', status='waiting')
    ray = f.message(task_id=t, subject='Contract', body='I will sign it this week.', from_name='Ray Colton', from_email=RAY, sent_at=at(d=9))
    for who, cls, d in (('noreply@sign.example', 'automated', 6), ('news@list.example', 'bulk', 5)):
        mid = f.message(task_id=t, subject='Contract', body='Your envelope was viewed.', from_name='Notices', from_email=who, sent_at=at(d=d))
        s._exec("UPDATE message SET Status='filed', SenderClass=? WHERE MessageId=?", (cls, mid))
    assert rulebook.chase_thread(s, {'key': f'task:{t}', 'kind': 'todo', 'lane': 'theirs', 'tid': t}) == {'tid': t, 'who': RAY, 'mid': ray}


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
    assert rv['Status'] == 'pending' and rv['Origin'] == 'chase' and RAY in (rv.get('Deliver') or '')
    assert rv['Reason'] == 'chase: no answer yet', "the card's line is words, never the mark"
    assert not s._rows("SELECT * FROM message WHERE TaskId=? AND Direction='out' AND Status='sent' AND CreatedAt>?", (t, at(d=1)))


def test_a_sent_chase_is_a_chase_in_the_ledger_whatever_its_reason_reads_by_then():
    """The spine audit, 2026-11-09: the ledger knew a chase by the first six letters of the review's Reason - the line a redraft rewrites."""
    import json
    from taskuary import outcomes, verdicts
    s = MemoryStore(); f = Factory(s)
    t = f.task(title='Vendor W-9'); mid = f.message(task_id=t, subject='W-9?', from_name='Ray Colton', from_email=RAY)
    sent = lambda snap: {'channel': 'email', 'to': [RAY]}
    def send(origin):
        rid = s.add_review({'TaskId': t, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Any news?', **origin})
        s.update_review_reason(rid, 'shorter, as you asked')
        out = verdicts._deliver_review(s, s.get_review(rid), 'Any news?', 'approve', 'owner', send_fn=sent)
        assert out.get('ok') and not out.get('send_error'), out
        return json.loads(outcomes.rows_for(s, 'task', t)[0]['FactsJson'])['chase']
    assert send({'Origin': 'chase'}) is True
    assert send({}) is False and send({'Reason': 'chase: no answer yet'}) is False, 'never by its words'


def test_the_rows_filed_under_the_old_marks_are_marked_once(tmp_path):
    from taskuary.store import SQLiteStore
    p = str(tmp_path / 'taskuary.db'); s = SQLiteStore(p)
    old = s._one("SELECT sql FROM sqlite_master WHERE name='review'")['sql']
    assert ', Origin TEXT' in old
    with s.lock: s.cx.execute('DROP TABLE review'); s.cx.execute(old.replace(', Origin TEXT', '')); s.cx.commit()
    for why in ('chase:2 cc:omar@northwind.example', 'needs a reply: asked for the W-9', 'the agent drafted it'):
        s._exec("INSERT INTO review (TaskId, Kind, Status, Reason) VALUES (1, 'draft', 'pending', ?)", (why,))
    s.cx.close()
    s = SQLiteStore(p)
    assert [r['Origin'] for r in s._rows('SELECT Origin FROM review ORDER BY ReviewId')] == ['chase', 'triage', None]
    assert s.get_review(s.add_review({'TaskId': 1, 'Kind': 'draft', 'Status': 'pending', 'Origin': 'chase'}))['Origin'] == 'chase'
