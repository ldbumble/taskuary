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

    def test_the_models_order_is_the_rank_and_the_floor_only_breaks_a_fall(self):
        """It used to be half the floor and half the model, which let a handful of deterministic
        signals outvote the judgement. What deserves attention IS a judgement (the owner,
        2026-09-18: "rank has to be ai") - so the model's position is the value, and the floor is
        kept only as what answers when there is no brain to ask."""
        s = MemoryStore()
        a, b = (s.create_task({'Title': t, 'Kind': 'coding', 'Status': 'open'}, 't') for t in ('alpha', 'beta'))
        s.enqueue_dispatch(a, None, 'coder', 'ranked', value=0.9, why='to you'); s.enqueue_dispatch(b, None, 'coder', 'ranked', value=0.3, why='cc')
        llm = lambda sys_, usr_, **k: json.dumps({'order': [{'ref': f'TQ-{b:04d}', 'why': 'CFO is asking'}, {'ref': f'TQ-{a:04d}', 'why': 'routine'}]})
        with mock.patch('taskuary.llm.build_llm', return_value=llm):
            self.assertEqual(rank.rerank(s, force=True), 2)
        qa, qb = (next(q for q in s.queued_dispatches() if q['TaskId'] == t) for t in (a, b))
        # beta was put first by the model and outranks alpha, whose floor was three times higher
        self.assertAlmostEqual(qb['Value'], 1.0); self.assertAlmostEqual(qa['Value'], 0.0)
        self.assertEqual((qa['Floor'], qb['Floor']), (0.9, 0.3))     # kept: it is what answers with no AI
        self.assertIn('CFO is asking', qb['Why']); self.assertTrue(qb['Why'].startswith('cc'))

    def test_with_no_brain_the_floor_still_orders_the_dispatch_queue(self):
        s = MemoryStore()
        a, b = (s.create_task({'Title': t, 'Kind': 'coding', 'Status': 'open'}, 't') for t in ('alpha', 'beta'))
        s.enqueue_dispatch(a, None, 'coder', 'ranked', value=0.9, why='to you'); s.enqueue_dispatch(b, None, 'coder', 'ranked', value=0.3, why='cc')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertEqual(rank.rerank(s, force=True), 0)
        qa, qb = (next(q for q in s.queued_dispatches() if q['TaskId'] == t) for t in (a, b))
        self.assertAlmostEqual(qa['Value'], 0.9); self.assertAlmostEqual(qb['Value'], 0.3)


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


def pending(s, subject, who='Asker', channel='email', body='', when='2026-08-27 09:00:00'):
    """An arrival as it sits BEFORE triage: Status='triaging', no task, no title but its own subject."""
    return s.add_message({'ExternalId': f'p-{subject}', 'ConversationId': f'c-{subject}', 'Channel': channel,
                          'Subject': subject, 'FromName': who, 'FromEmail': f'{who.lower()}@x.com',
                          'SentAt': when, 'BodyText': body, 'Status': 'triaging'})


def judging(store, judged):
    """A stand-in for triage that also CONSUMES the arrival - a real judgement takes the row out of
    the pending pool, and a mock that does not makes the queue look infinite."""
    def go(s, m, **k):
        judged.append(m['_mid'])
        s.place_message(m['_mid'], None, 'filed')
    return go


class RankBeforeTriageTests(unittest.TestCase):
    """300 pull requests must not cost 300 triage calls. In bulk mode the pool is RANKED first - by
    its own small call, not by triage's - and only the head is judged; the rest wait, already in
    order, and are judged as slots open (the owner, 2026-09-18: "the triage would process them up
    next when you read or close one of the first 4 ranked").

    Everything here is gated on the connector's bulk setting: clear mode must take none of it."""

    def setUp(self):
        self.s = MemoryStore()
        self.s.save_source({'Channel': 'email', 'Address': 'me@corp.example', 'Owner': 'me', 'Active': 1}, 't')

    def test_a_message_carries_the_rank_it_was_given(self):
        mid = pending(self.s, 'one')
        self.s.set_message_rank(mid, 0.82, 'team member \u00b7 pull request', 'rank')
        row = self.s.get_message(mid)
        self.assertEqual((row['RankValue'], row['RankWhy']), (0.82, 'team member \u00b7 pull request'))

    def test_the_untriaged_pool_can_come_back_in_rank_order(self):
        """Arrival order is what pending_triage has always used; a ranked pool answers by value, and
        anything never ranked sorts after what was, not above it."""
        a, b, c = pending(self.s, 'a'), pending(self.s, 'b'), pending(self.s, 'c')
        self.s.set_message_rank(a, 0.2, 'cc', 'rank')
        self.s.set_message_rank(b, 0.9, 'to you \u00b7 urgent', 'rank')
        self.assertEqual([r['MessageId'] for r in self.s.pending_triage(ranked=True)], [b, a, c])
        self.assertEqual([r['MessageId'] for r in self.s.pending_triage()], [a, b, c])

    def test_the_ranking_call_reads_the_raw_arrival_and_is_one_call_for_the_lot(self):
        """It runs BEFORE triage, so there is no task, no Title and no Summary to read - only what
        the arrival itself carries. And it is listwise: forty subjects in one call, never forty calls."""
        rank_mode(self.s)
        mids = [pending(self.s, f'subject {i}', who=f'Person{i}') for i in range(5)]
        seen = []
        def llm(system, user, **k):
            seen.append((system, user))
            order = [{'ref': f'm{m}', 'why': 'looks urgent'} for m in reversed(mids)]
            return json.dumps({'order': order})
        with mock.patch.object(rank, 'build_rank_llm', return_value=llm):
            n = rank.rank_pending(self.s, force=True)
        self.assertEqual(len(seen), 1, 'one listwise call, not one per item')
        self.assertEqual(n, 5)
        self.assertIn('subject 0', seen[0][1])
        self.assertNotIn('Summary', seen[0][1])
        ranked = [r['MessageId'] for r in self.s.pending_triage(ranked=True)]
        self.assertEqual(ranked, list(reversed(mids)), "the model's order is the order")

    def test_with_no_brain_the_floor_orders_it_rather_than_nothing(self):
        """A cold start, or an install with no AI configured, still gets a sane queue - the floor is
        the FALLBACK now, not half of every answer."""
        rank_mode(self.s)
        mids = [pending(self.s, f's{i}') for i in range(3)]
        with mock.patch.object(rank, 'build_rank_llm', return_value=None):
            rank.rank_pending(self.s, force=True)
        for m in mids: self.assertIsNotNone(self.s.get_message(m)['RankValue'])

    def test_clear_mode_judges_everything_exactly_as_before(self):
        judged = []
        for i in range(6): pending(self.s, f'c{i}')
        with mock.patch.object(ingest, 'ingest_message', side_effect=judging(self.s, judged)):
            ingest.drain(self.s)
        self.assertEqual(len(judged), 6, 'clear mode drains the lot, untouched')

    def test_bulk_mode_judges_only_the_head_and_leaves_the_rest_waiting(self):
        rank_mode(self.s)
        mids = [pending(self.s, f'b{i}') for i in range(10)]
        for i, m in enumerate(mids): self.s.set_message_rank(m, i / 10, 'floor', 'rank')
        judged = []
        with mock.patch.object(ingest, 'ingest_message', side_effect=judging(self.s, judged)):
            ingest.drain(self.s)
        self.assertEqual(len(judged), rank.head_size(self.s))
        self.assertEqual(judged, list(reversed(mids))[:rank.head_size(self.s)], 'the most valuable first')
        self.assertEqual(len(self.s.pending_triage()), 10 - rank.head_size(self.s), 'the rest wait, ranked')

    def test_a_slot_opening_judges_exactly_one_more(self):
        rank_mode(self.s)
        mids = [pending(self.s, f'd{i}') for i in range(10)]
        for i, m in enumerate(mids): self.s.set_message_rank(m, i / 10, 'floor', 'rank')
        judged = []
        with mock.patch.object(ingest, 'ingest_message', side_effect=judging(self.s, judged)):
            ingest.drain(self.s)
            before = len(judged)
            rank.top_up(self.s, 1)
        self.assertEqual(len(judged), before + 1)
        self.assertEqual(judged[-1], list(reversed(mids))[before])

    def test_settling_a_head_item_judges_the_next_one_and_later_counts(self):
        """`later` holds the ITEM, not the queue behind it - so it opens the slot like any other
        disposal (the owner, 2026-09-18: "later should open the slot")."""
        from taskuary import funnel
        rank_mode(self.s)
        mids = [pending(self.s, f'e{i}') for i in range(10)]
        for i, m in enumerate(mids): self.s.set_message_rank(m, i / 10, 'floor', 'rank')
        judged = []
        with mock.patch.object(ingest, 'ingest_message', side_effect=judging(self.s, judged)):
            ingest.drain(self.s)
            head = len(judged)
            for verb in ('done', 'later', 'skip'):
                rank._last['at'] = 0
                funnel.settle(self.s, f'task:{9000 + len(judged)}', verb, 'owner')
        self.assertEqual(len(judged), head + 3, 'done, later and skip each open one slot')

    def test_merely_showing_an_item_does_not_open_a_slot(self):
        """`surfaced` without read means it was put up, not dealt with - the head is still full."""
        from taskuary import funnel
        rank_mode(self.s)
        mids = [pending(self.s, f'f{i}') for i in range(10)]
        for i, m in enumerate(mids): self.s.set_message_rank(m, i / 10, 'floor', 'rank')
        judged = []
        with mock.patch.object(ingest, 'ingest_message', side_effect=judging(self.s, judged)):
            ingest.drain(self.s)
            head = len(judged)
            rank._last['at'] = 0
            funnel.settle(self.s, 'task:9999', 'surfaced', 'owner')
        self.assertEqual(len(judged), head)

    def test_how_many_still_wait_is_answerable_without_judging_any_of_them(self):
        """The rail's "296 up next" - a count and a list of subjects, costing no model call."""
        rank_mode(self.s)
        for i in range(12): pending(self.s, f'u{i}')
        waiting = rank.waiting(self.s)
        self.assertEqual(waiting['count'], 12)
        self.assertEqual(len(waiting['items']), 12)
        self.assertIn('u0', [i['subject'] for i in waiting['items']])


class TheMoreMarkerTests(unittest.TestCase):
    """The rail's "250 more" - the same pill fyi already wears, hung off the LAST ranked row rather
    than off a band, because that row is where reading stopped (the owner, 2026-09-18: "the more
    button should be on the last github item that is triaged").

    And the promise that matters most: an owner who processes one at a time never sees any of it."""

    def setUp(self):
        self.s = MemoryStore()
        self.s.save_source({'Channel': 'email', 'Address': 'me@corp.example', 'Owner': 'me', 'Active': 1}, 't')

    def _arrival(self, subject, channel='github', status='triaging'):
        return self.s.add_message({'ExternalId': f'a-{subject}', 'ConversationId': f'c-{subject}', 'Channel': channel,
                                   'Subject': subject, 'FromName': 'dev', 'FromEmail': 'dev@x.com',
                                   'SentAt': '2026-09-18 07:00:00', 'Status': status})

    def test_nothing_is_marked_when_no_connector_ranks(self):
        """A normal install must be untouched by every part of this - no marker, no count, no pill."""
        for i in range(6): self._arrival(f'pr {i}')
        self.assertEqual(rank.waiting(self.s)['count'], 0)
        self.assertEqual(rank.more_markers(self.s, [{'key': 'k1', 'channel': 'github'}]), [])

    def test_the_count_hangs_off_the_last_ranked_row(self):
        c = self.s.get_connector_by_type('github')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'bulk': 'rank'})}, 't')
        for i in range(9): self._arrival(f'pr {i}')
        rows = [{'key': 'k1', 'channel': 'github'}, {'key': 'k2', 'channel': 'email'}, {'key': 'k3', 'channel': 'github'}]
        got = rank.more_markers(self.s, rows)
        self.assertEqual(len(got), 1)
        self.assertEqual(got[0]['key'], 'k3', 'the LAST ranked row, not the last row and not the first')
        self.assertEqual(got[0]['count'], 9)

    def test_a_ranked_source_with_nothing_waiting_shows_no_pill(self):
        c = self.s.get_connector_by_type('github')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'bulk': 'rank'})}, 't')
        self.assertEqual(rank.more_markers(self.s, [{'key': 'k1', 'channel': 'github'}]), [])

    def test_with_no_ranked_row_on_screen_there_is_nowhere_to_hang_it(self):
        c = self.s.get_connector_by_type('github')
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps({'bulk': 'rank'})}, 't')
        for i in range(4): self._arrival(f'pr {i}')
        self.assertEqual(rank.more_markers(self.s, [{'key': 'k1', 'channel': 'email'}]), [])


class EachInputChoosesItsOwnBatchTests(unittest.TestCase):
    """How many to read at once belongs to the CONNECTOR, beside the switch that turned ranking on -
    a repo firehose and a mailbox are not the same appetite (the owner, 2026-09-18: "per connector
    input you can choose how many you want in each batch no?")."""

    def setUp(self):
        self.s = MemoryStore()
        self.s.save_source({'Channel': 'email', 'Address': 'me@corp.example', 'Owner': 'me', 'Active': 1}, 't')

    def _rank(self, ctype, head=None):
        c = self.s.get_connector_by_type(ctype)
        cfg = {'bulk': 'rank'}
        if head is not None: cfg['bulk_head'] = head
        self.s.save_connector({'ConnectorId': c['ConnectorId'], 'Active': 1, 'ConfigJson': json.dumps(cfg)}, 't')

    def test_a_connector_that_says_nothing_takes_the_default(self):
        self._rank('github')
        self.assertEqual(rank.head_size(self.s, 'github'), rank.HEAD_JUDGED)

    def test_each_input_keeps_its_own_number(self):
        self._rank('github', 10)
        self._rank('outlook', 2)
        self.assertEqual(rank.head_size(self.s, 'github'), 10)
        self.assertEqual(rank.head_size(self.s, 'email'), 2)

    def test_a_nonsense_number_is_clamped_not_obeyed(self):
        self._rank('github', 900)
        self.assertEqual(rank.head_size(self.s, 'github'), rank.HEAD_RANGE[1])
        self._rank('github', 0)
        self.assertEqual(rank.head_size(self.s, 'github'), rank.HEAD_RANGE[0])

    def test_each_ranked_input_wears_its_own_pill(self):
        """Two inputs ranking means two queues and two counts - one pill under each one's last row."""
        self._rank('github', 2)
        self._rank('outlook', 2)
        for i in range(5):
            self.s.add_message({'ExternalId': f'g{i}', 'Channel': 'github', 'Subject': f'pr {i}',
                                'FromName': 'dev', 'SentAt': '2026-09-18 07:00:00', 'Status': 'triaging'})
        for i in range(3):
            self.s.add_message({'ExternalId': f'e{i}', 'Channel': 'email', 'Subject': f'mail {i}',
                                'FromName': 'Dana', 'SentAt': '2026-09-18 07:00:00', 'Status': 'triaging'})
        rows = [{'key': 'g1', 'channel': 'github'}, {'key': 'e1', 'channel': 'email'}, {'key': 'g2', 'channel': 'github'}]
        marks = rank.more_markers(self.s, rows)
        self.assertEqual({m['key']: m['count'] for m in marks}, {'g2': 5, 'e1': 3})

    def test_an_owner_who_ranks_nothing_gets_no_markers_at_all(self):
        self.assertEqual(rank.more_markers(self.s, [{'key': 'k', 'channel': 'github'}]), [])
