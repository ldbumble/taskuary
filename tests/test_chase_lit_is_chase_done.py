"""A LATE WAIT IS ITS AGENT'S TO CHASE (the owner, 2026-11-27: "side model should never work in agent canvas"). A fixed rule lit Chase on a
wait past its day and a one-shot writer drafted the nudge - while checkback.late already woke the task's agent for the same lateness. Now
that one road stands: no Chase button, no chase operation, no drafted nudge; the agent raises the nudge as its card. What a chase that
went still means to the ledger is pinned below. Invented people."""
from datetime import datetime, timedelta
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import buttons, checkback, concierge, operations, rulebook, server
from taskuary.store import MemoryStore
from taskuary.testing import Factory

RAY = 'ray.colton@northwind.example'
def at(d=0): return (datetime.now() - timedelta(days=d)).strftime('%Y-%m-%d %H:%M:%S')


def _waiting(s, days):
    f = Factory(s)
    t = f.task(title='Vendor W-9', kind='task', status='waiting'); s._exec('UPDATE task SET WaitingOn=? WHERE TaskId=?', (RAY, t))
    f.message(task_id=t, subject='W-9?', direction='out', sent_at=at(d=days))
    return t, {'key': f'task:{t}', 'kind': 'todo', 'lane': 'theirs', 'tid': t}


def test_a_late_wait_lights_no_chase_and_no_road_drafts_one():
    s = MemoryStore()
    t, it = _waiting(s, 7)
    assert rulebook.adds(s, it) == [] and not hasattr(rulebook, 'chase_thread'), 'no lit Chase on the row'
    assert 'chase' not in concierge.VERBS and 'chase' not in buttons.VERBS and 'task.chase' not in operations.KINDS
    assert 'chase' not in [c['verb'] for c in concierge.chips_for(s, {**it, 'lane': 'forgotten'})], 'nor on a slipped card'
    with mock.patch.object(server, 'store', s):
        op = TestClient(server.app).post('/api/operations', json={'kind': 'task.chase', 'target': t, 'params': {'key': it['key']}})
    assert op.status_code >= 400, op.text
    assert callable(checkback.late), "the one road left: lateness wakes the task's agent"


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
    s.close()
    s = SQLiteStore(p)
    assert [r['Origin'] for r in s._rows('SELECT Origin FROM review ORDER BY ReviewId')] == ['chase', 'triage', None]
    assert s.get_review(s.add_review({'TaskId': 1, 'Kind': 'draft', 'Status': 'pending', 'Origin': 'chase'}))['Origin'] == 'chase'
