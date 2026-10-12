"""The Advisor's event path (spec 2026-10-12, build step 3): one small judgement per item per revision, a pill that
presses the card's own button, and a rail that never reads any of it."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
import pytest
from taskuary import advisor, funnel, outcomes, processing_unread, terminal
from taskuary.store import MemoryStore


class RowTests(unittest.TestCase):
    def test_a_row_is_keyed_by_target_and_revision_and_read_back(self):
        s = MemoryStore(); t = s.create_task({'Title': 'Export job'}, 'owner')
        rev = advisor.revision(s, 'task', t)
        self.assertEqual(len(rev), 16)
        i = advisor._write(s, target_kind='task', target_id=t, key='task:%d' % t, event='agent.stopped', revision=rev, tier=1,
                           line='You usually merge it here.', verb='continue', label='Continue session', count=(8, 8), evidence=['out3'], model='haiku')
        r = advisor.row(s, 'task', t, rev)
        self.assertEqual((r['Id'], r['Verb'], json.loads(r['CountJson']), json.loads(r['EvidenceJson'])), (i, 'continue', [8, 8], ['out3']))
        self.assertIsNone(advisor.row(s, 'task', t, 'other'))
        self.assertEqual([x['Id'] for x in advisor.rows(s, 'task', t)], [i])

    def test_the_revision_moves_with_the_task_and_its_agent_events(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')
        a = advisor.revision(s, 'task', t)
        s.update_task(t, {'Status': 'in_progress'}, 'owner'); b = advisor.revision(s, 'task', t)
        ws.record(s, t, 'run1', 'turn_end', text='done'); c = advisor.revision(s, 'task', t)
        self.assertEqual(len({a, b, c}), 3)
        self.assertEqual(c, advisor.revision(s, 'task', t))                             # stable while nothing changes

    def test_keys_round_trip(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        self.assertEqual(advisor.key_of('task', t), f'task:{t}')
        self.assertEqual(advisor.target_of(s, f'task:{t}'), ('task', t))
        self.assertEqual(advisor.target_of(s, 'agent:7'), ('task', 7))
        self.assertEqual(advisor.target_of(s, 'msg:9'), ('message', 9))
        self.assertIsNone(advisor.target_of(s, 'conn:3'))


@pytest.fixture
def rail(monkeypatch):
    s = MemoryStore()
    s.set_setting('calendar_enabled', '0', 'test')
    monkeypatch.setattr(terminal, 'live_sessions', lambda tail=0: [])
    monkeypatch.setattr(funnel, '_agenda', lambda _s, **kw: [])
    for n in range(5):
        t = s.create_task({'Title': f'Arrival {n}', 'Status': 'open'}, 'owner')
        s.add_message({'ConversationId': f'c{n}', 'Channel': 'email', 'Subject': f'Arrival {n}', 'FromEmail': f'p{n}@vendor.example',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
    s.reconcile_processing_membership()
    s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[])
    funnel.invalidate(); yield s; funnel.invalidate(); s.cx.close()


def order(s):
    s.reconcile_processing_membership(); funnel.invalidate()
    return [c['key'] for c in processing_unread.build(s, live_state=[], include_read=True)['items']]


def test_the_rail_is_the_same_with_and_without_advice(rail):
    before = order(rail)
    assert len(before) >= 5
    for t in rail._rows('SELECT TaskId FROM task'):
        advisor._write(rail, target_kind='task', target_id=t['TaskId'], key=f"task:{t['TaskId']}", event='task.closed',
                       revision=advisor.revision(rail, 'task', t['TaskId']), tier=1, line='Close it.', verb='close', label='Mark done',
                       count=(3, 3), evidence=[], model='haiku')
    assert order(rail) == before
