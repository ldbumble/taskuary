"""THE ONE FILLED BUTTON EVERY SURFACE READS (rulebook.decide): a task's own recommended move, read off its agent's turn and its facts -
never a model's. An idea row fills none (the owner, 2026-11-15: "remove the entire advisor from buttons thing"). The stamp it is decided at
(rulebook.revision) moves with every act on the item, so a button pressed on an item that moved since is refused rather than run."""
import unittest
from datetime import datetime, timedelta
from unittest import mock
from fastapi.testclient import TestClient
from taskuary import funnel, server, terminal, rulebook
from taskuary.store import MemoryStore


def _at(h=0): return (datetime.now() - timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')


class _Rail(unittest.TestCase):
    """The rail is built the way a real install builds it (processing reads on), so the card is the one the owner sees."""
    def setUp(self):
        self._p = [mock.patch.object(terminal, 'live_sessions', lambda tail=0: []), mock.patch.object(funnel, '_agenda', lambda _s, **kw: [])]
        for p in self._p: p.start()
        funnel.invalidate()
    def tearDown(self):
        for p in self._p: p.stop()
        funnel.invalidate()

    def _stopped_task(self, s):
        s.set_setting('calendar_enabled', '0', 'test')
        t = s.create_task({'Title': 'Export job', 'Status': 'in_progress', 'Kind': 'code'}, 'owner')
        s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Export job', 'FromEmail': 'gail@northwind.example', 'FromName': 'Gail Moreno',
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'Please move the export.', 'Status': 'routed', 'TaskId': t})
        rid = s.start_run(t, 'coding', 'move the export', 'owner'); s._exec("UPDATE run SET Status='stopped' WHERE RunId=?", (rid,))   # the agent left: Continue leads
        # ...with its conversation saved, so the task's row draws Continue (concierge.row_buttons)
        s._exec("INSERT INTO transcript (TaskId, Sid, Agent, Text, CreatedAt, ExtId) VALUES (?,?,?,?,?,?)", (t, 'run1', 'coding', 'x', (datetime.now() + timedelta(minutes=1)).strftime('%Y-%m-%d %H:%M:%S'), 'ext-1'))
        s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
        return t

    def _asked_task(self, s, who=('Gail Moreno', 'gail@northwind.example')):
        """Someone asked and nothing is on it: no agent took the ask, so its row fills Send to agent (rulebook.recommended)."""
        s.set_setting('calendar_enabled', '0', 'test')
        t = s.create_task({'Title': 'Export job', 'Status': 'open', 'Kind': 'task'}, 'owner')
        s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Export job', 'FromEmail': who[1], 'FromName': who[0],
                       'SentAt': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'BodyText': 'Please move the export.', 'Status': 'routed', 'TaskId': t})
        s.reconcile_processing_membership(); s.activate_processing_reads(fixed_now=datetime.now().isoformat(), live_state=[]); funnel.invalidate()
        return t


class RevisionTests(unittest.TestCase):
    def test_the_revision_moves_with_the_task_and_its_agent_events(self):
        from taskuary import workerstate as ws
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')
        a = rulebook.revision(s, 'task', t)
        s.update_task(t, {'Status': 'in_progress'}, 'owner'); b = rulebook.revision(s, 'task', t)
        ws.record(s, t, 'run1', 'turn_end', text='done'); c = rulebook.revision(s, 'task', t)
        self.assertEqual(len({a, b, c}), 3)
        self.assertEqual(c, rulebook.revision(s, 'task', t))                             # stable while nothing changes

    def test_keys_round_trip(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x'}, 'owner')
        self.assertEqual(rulebook.key_of('task', t), f'task:{t}')
        self.assertEqual(rulebook.target_of(s, f'task:{t}'), ('task', t))
        self.assertEqual(rulebook.target_of(s, 'agent:7'), ('task', 7))
        self.assertEqual(rulebook.target_of(s, 'msg:9'), ('message', 9))
        self.assertIsNone(rulebook.target_of(s, 'conn:3'))

    def test_a_button_pressed_on_a_moved_item_is_refused(self):
        s = MemoryStore(); t = s.create_task({'Title': 'x', 'Status': 'open'}, 'owner')
        with mock.patch.object(server, 'store', s):
            r = TestClient(server.app).post('/api/concierge/propose', json={'verb': 'close', 'key': f'task:{t}', 'table': True, 'revision': 'stale'})
        self.assertEqual(r.status_code, 409); self.assertIn('changed', r.json()['detail'])


class StatusTests(_Rail):
    def test_nothing_is_ever_pending_and_nothing_is_lit_without_its_fact(self):
        s = MemoryStore(); t = self._asked_task(s)
        got = rulebook.status(s, f'task:{t}')
        self.assertEqual((got['verb'], got['line'], 'pending' in got), ('regular_agent', '', False))     # an ask no agent took: Send to agent (2026-11-10)

    def test_a_meeting_or_an_idea_fills_nothing(self):
        """The owner, 2026-11-15: "remove the entire advisor from buttons thing" - an Advisor idea's row is the owner's own choice, with no
        model and no rule filling one of its buttons; a meeting row has nothing to decide."""
        s = MemoryStore()
        i = s.upsert_idea({'key': 'idea:weekly-ledger', 'kind': 'idea', 'sig': 'y', 'text': 'The ledger reconciliation repeats monthly - worth automating.'}, _at())
        self.assertEqual(rulebook.status(s, 'meeting:3'), {'none': 'nothing'})
        self.assertEqual(rulebook.status(s, f"idea:{i['IdeaId']}"), {'none': 'nothing'})
        self.assertFalse(s._rows("SELECT name FROM sqlite_master WHERE name IN ('advice', 'advice_press')"), 'the judgements and the press log are gone')

    def test_the_endpoint_answers_with_the_decision(self):
        s = MemoryStore(); t = self._asked_task(s)
        with mock.patch.object(server, 'store', s):
            c = TestClient(server.app)
            got = c.get('/api/advice', params={'key': f'task:{t}'}).json()
            self.assertEqual(c.post('/api/advice/press', json={'key': f'task:{t}', 'pressed': 'close'}).status_code, 404, 'no press log')
        self.assertEqual((got['verb'], got['label'], got['line'], got['state'], got['by']), ('regular_agent', 'Send to agent', '', 'asked', 'agent'))


class AfterSendTests(_Rail):
    def _asked(self, s):
        """Erin Blake asked a question on a task; a reply is drafted for her."""
        t = s.create_task({'Title': 'August close numbers', 'Status': 'open'}, 'owner')
        m = s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'August close', 'FromEmail': 'erin@northwind.example',
                           'FromName': 'Erin Blake', 'SentAt': _at(2), 'BodyText': 'Can you confirm the August numbers before Thursday?',
                           'Status': 'routed', 'TaskId': t})
        rv = s.add_review({'TaskId': t, 'MessageId': m, 'Kind': 'reply', 'DraftText': 'Confirmed - the numbers stand.', 'Status': 'pending'})
        return t, m, rv

    def test_a_sent_reply_moves_the_revision_even_with_no_delivery_receipt(self):
        s = MemoryStore(); t, m, rv = self._asked(s)
        before = rulebook.revision(s, 'task', t)
        s._exec("UPDATE review SET Status='approved', DecidedAt=? WHERE ReviewId=?", (_at(), rv))        # DeliveryState stays NULL
        sent = rulebook.revision(s, 'task', t)
        self.assertNotEqual(before, sent, 'a decided draft is an act: the line judged before it is not read back over it')
        s._exec("UPDATE review SET DeliveryState='sent' WHERE ReviewId=?", (rv,))
        self.assertNotEqual(sent, rulebook.revision(s, 'task', t))

    def test_an_act_that_ran_moves_it_and_a_proposal_waiting_for_its_yes_does_not(self):
        s = MemoryStore(); t, m, rv = self._asked(s)
        a = rulebook.revision(s, 'task', t)
        s._exec("INSERT INTO operation (OpId, Kind, TargetKind, TargetId, Status, CreatedAt) VALUES ('op1','task.defer','task',?,'proposed',?)", (t, _at()))
        self.assertEqual(a, rulebook.revision(s, 'task', t), 'a proposal is not an act yet')
        s._exec("UPDATE operation SET Status='done' WHERE OpId='op1'")
        self.assertNotEqual(a, rulebook.revision(s, 'task', t))
