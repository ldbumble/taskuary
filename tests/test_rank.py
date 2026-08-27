"""Bulk processing (rank.py): a connector in rank mode puts its coding tasks into one value-ordered
queue; the floor value comes from what the funnel already knows; the drain takes the most valuable
waiting task; the owner can pin or push back. All faked - no pty, no model unless stubbed."""
import json, unittest
from unittest import mock

from taskuary import blackboard, ingest, rank, terminal
from taskuary.store import MemoryStore


class FakeLive:
    """A started session as the drain sees one: alive, on a task, in a checkout."""
    def __init__(self, tid): self.task_id, self.alive, self.cwd, self.agent, self.label, self.started = tid, True, 'x', 'coder', 'coder', ''
    def files(self): return []
    def info(self, tail=0): return {'sid': f's{self.task_id}', 'taskId': self.task_id, 'alive': True, 'idle': 0, 'files': []}


def fake_start(started):
    def go(store, tid, agent='coder', *a, **k):
        started.append(tid); terminal.SESSIONS[f's{tid}'] = FakeLive(tid); return {'sid': f's{tid}'}
    return go


def rank_mode(s, ctype='outlook'):
    c = s.get_connector_by_type(ctype)
    s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'bulk': 'rank'})}, 't')


def task_with_mail(s, title, to=None, cc=None, urgent=False, conv=None, others=()):
    tid = s.create_task({'Title': title, 'Kind': 'coding', 'Status': 'open', 'Priority': 'urgent' if urgent else 'normal', 'Source': 'email'}, 't')
    for i, who in enumerate(others):
        s.add_message({'ExternalId': f'{title}-prior{i}', 'ConversationId': conv, 'Channel': 'email', 'Subject': title,
                       'FromEmail': who, 'FromName': who.split('@')[0], 'SentAt': f'2026-08-27 0{i}:00:00', 'Status': 'filed'})
    s.add_message({'TaskId': tid, 'ExternalId': f'{title}-m', 'ConversationId': conv, 'Channel': 'email', 'Subject': title,
                   'FromEmail': 'asker@x.com', 'FromName': 'Asker', 'SentAt': '2026-08-27 09:00:00', 'Status': 'routed',
                   'RecipientsJson': json.dumps({'to': to or [], 'cc': cc or []}) if (to or cc) else None})
    return tid


class FloorTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.s.save_source({'Channel': 'email', 'Address': 'me@corp.example', 'Owner': 'me', 'Active': 1}, 't')
        self.me = {'me@corp.example'}

    def _floor(self, tid): return rank.floor(self.s, self.s.get_task(tid), self.s.list_messages(tid)[0], self.me)

    def test_addressed_to_you_beats_cc_beats_a_crowd_with_a_colleague_replying(self):
        to = self._floor(task_with_mail(self.s, 'to me', to=['me@corp.example']))
        cc = self._floor(task_with_mail(self.s, 'cc me', to=['x@corp.example'], cc=['me@corp.example']))
        crowd = self._floor(task_with_mail(self.s, 'crowd', to=[f'p{i}@corp.example' for i in range(10)], cc=['me@corp.example'],
                                           conv='c1', others=('a@corp.example', 'b@corp.example')))
        self.assertGreater(to[0], cc[0]); self.assertGreater(cc[0], crowd[0])
        self.assertIn('to you', to[1]); self.assertIn('cc', cc[1])
        self.assertIn('colleague replied', crowd[1]); self.assertIn('11 people', crowd[1])

    def test_urgent_outranks_everything_ordinary(self):
        u = self._floor(task_with_mail(self.s, 'urgent one', cc=['me@corp.example'], urgent=True))
        plain = self._floor(task_with_mail(self.s, 'plain one', to=['me@corp.example']))
        self.assertGreater(u[0], plain[0]); self.assertIn('urgent', u[1])

    def test_github_author_association_counts(self):
        tid = self.s.create_task({'Title': 'pr', 'Kind': 'coding', 'Status': 'open', 'Source': 'github'}, 't')
        row = lambda a: {'Channel': 'github', 'BodyText': f'[pull request by kai - association: {a}]\nfixes'}
        team, stranger = rank.floor(self.s, self.s.get_task(tid), row('MEMBER')), rank.floor(self.s, self.s.get_task(tid), row('NONE'))
        self.assertGreater(team[0], stranger[0]); self.assertIn('team member', team[1]); self.assertIn('stranger', stranger[1])

    def test_waiting_ages_a_little_and_caps(self):
        self.assertAlmostEqual(rank.aged(0.5, '2026-08-01 09:00:00'), 0.6, places=3)     # weeks ago: capped at +0.1
        self.assertAlmostEqual(rank.aged(0.5, '2999-01-01 00:00:00'), 0.5, places=3)     # the future does not count
        self.assertEqual(rank.aged(0.5, 'garbage'), 0.5)


class QueueTests(unittest.TestCase):
    def test_the_queue_is_in_value_order_and_unranked_rows_sit_at_base(self):
        s = MemoryStore()
        a, b, c = (s.create_task({'Title': t, 'Kind': 'coding', 'Status': 'open'}, 't') for t in 'abc')
        s.enqueue_dispatch(a, None, 'coder', 'ranked', value=0.3, why='cc')
        s.enqueue_dispatch(b, None, 'coder', 'full house')                      # clear mode, no value
        s.enqueue_dispatch(c, None, 'coder', 'ranked', value=0.9, why='to you · urgent')
        self.assertEqual([q['TaskId'] for q in s.queued_dispatches()], [c, b, a])
        s.set_dispatch_value(a, rank.PIN, 'pinned by you')
        self.assertEqual(s.queued_dispatches()[0]['TaskId'], a)
        self.assertEqual(s.queued_dispatches()[0]['Floor'], 0.3)                  # the floor survives a pin

    def test_rank_mode_enqueues_and_the_drain_starts_the_most_valuable(self):
        s = MemoryStore(); rank_mode(s)
        s.save_source({'Channel': 'email', 'Address': 'me@corp.example', 'Owner': 'me', 'Active': 1}, 't')
        s.set_setting('auto_sessions', '1', 't')
        low = task_with_mail(s, 'low', cc=['me@corp.example'], to=['x@corp.example'])
        high = task_with_mail(s, 'high', to=['me@corp.example'], urgent=True)
        started = []
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(terminal, 'start_on_task', side_effect=fake_start(started)), \
             mock.patch.object(rank, 'rerank', return_value=0), mock.patch.object(blackboard, 'peers', return_value=[]):
            ingest._auto_code(s, low)                       # first in, slot free - it starts
            self.assertEqual(started, [low])
            ingest._auto_code(s, high)                      # slot taken by 'low': it waits, ranked
            self.assertEqual(started, [low])
            self.assertEqual([q['TaskId'] for q in s.queued_dispatches()], [high])
            self.assertIn('Ranked:', s.list_comments(high)[-1]['Body'])
            s.set_setting('auto_sessions', '2', 't'); blackboard.drain(s)
            self.assertEqual(started, [low, high])

    def test_the_drain_takes_the_highest_value_first_when_several_wait(self):
        s = MemoryStore(); s.set_setting('auto_sessions', '1', 't')
        a, b = (s.create_task({'Title': t, 'Kind': 'coding', 'Status': 'open'}, 't') for t in 'ab')
        s.enqueue_dispatch(a, None, 'coder', 'ranked', value=0.2, why='cc'); s.enqueue_dispatch(b, None, 'coder', 'ranked', value=0.8, why='to you')
        started = []
        with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch.object(blackboard, 'peers', return_value=[]), \
             mock.patch.object(terminal, 'start_on_task', side_effect=fake_start(started)):
            blackboard.drain(s)
        self.assertEqual(started, [b])

    def test_rerank_blends_the_models_order_with_the_floor(self):
        s = MemoryStore()
        a, b = (s.create_task({'Title': t, 'Kind': 'coding', 'Status': 'open'}, 't') for t in ('alpha', 'beta'))
        s.enqueue_dispatch(a, None, 'coder', 'ranked', value=0.9, why='to you'); s.enqueue_dispatch(b, None, 'coder', 'ranked', value=0.3, why='cc')
        llm = lambda sys_, usr_, **k: json.dumps({'order': [{'ref': f'TQ-{b:04d}', 'why': 'CFO is asking'}, {'ref': f'TQ-{a:04d}', 'why': 'routine'}]})
        with mock.patch('taskuary.llm.build_llm', return_value=llm):
            self.assertEqual(rank.rerank(s, force=True), 2)
        qa, qb = (next(q for q in s.queued_dispatches() if q['TaskId'] == t) for t in (a, b))
        self.assertAlmostEqual(qa['Value'], 0.45); self.assertAlmostEqual(qb['Value'], 0.65)   # 0.5*floor + 0.5*position
        self.assertEqual((qa['Floor'], qb['Floor']), (0.9, 0.3))                                  # the floor is kept for the next blend
        self.assertIn('CFO is asking', qb['Why']); self.assertTrue(qb['Why'].startswith('cc'))


class ApiTests(unittest.TestCase):
    def test_funnel_pin_and_later(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore(); rank_mode(s)
        a, b = (s.create_task({'Title': t, 'Kind': 'coding', 'Status': 'open'}, 't') for t in 'ab')
        s.enqueue_dispatch(a, None, 'coder', 'ranked', value=0.7, why='to you'); s.enqueue_dispatch(b, None, 'coder', 'ranked', value=0.4, why='cc')
        with mock.patch.object(server, 'store', s), mock.patch.dict(terminal.SESSIONS, {}, clear=True), \
             mock.patch.object(blackboard, 'drain_later'):
            c = TestClient(server.app)
            f = c.get('/api/funnel').json()
            self.assertEqual((f['mode'], f['width'], [q['tid'] for q in f['queued']]), ('rank', 4, [a, b]))
            self.assertEqual(f['queued'][0]['why'], 'to you')
            c.post(f'/api/funnel/{b}/pin')
            self.assertEqual([q['tid'] for q in c.get('/api/funnel').json()['queued']], [b, a])
            c.post(f'/api/funnel/{b}/later')
            self.assertEqual([q['tid'] for q in c.get('/api/funnel').json()['queued']], [a, b])
            self.assertEqual(c.post('/api/funnel/9999/pin').status_code, 404)
            self.assertEqual(next(t for t in c.get('/api/tasks').json()['data'] if t['TaskId'] == a)['Queued']['why'], 'to you')


if __name__ == '__main__': unittest.main()
