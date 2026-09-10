"""The assistant's answer to an agent lands on the exact outstanding request of the run that asked (PW-138); the
delivery path is the integration's own, and with no open request it falls back to the waiting room (PW-140)."""
from unittest import mock

from taskuary import server, terminal as term, workerstate as ws
from tests.test_worker_events import Base, live


class AnswerRoute(Base):
    def test_a_chat_answer_is_bound_to_the_open_request_not_typed_blind(self):
        s = live(self.tid); typed = []; s.send_prompt = lambda t: typed.append(t); term.SESSIONS['run1'] = s
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Which branch?', choices=['main', 'dev'], source='hook')
        out = ws.answer_open(self.s, self.tid, 'main', 'owner')
        self.assertTrue(out['delivered']); self.assertEqual(typed, ['main']); self.assertEqual(out['path'], 'api')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_an_approval_is_answered_before_an_ordinary_question(self):
        s = live(self.tid); typed = []; s.send_prompt = lambda t: typed.append(t); term.SESSIONS['run1'] = s
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Which branch?', source='hook')
        ws.record(self.s, self.tid, 'run1', 'approval_needed', text='Run the migration?', source='hook')
        out = ws.answer_open(self.s, self.tid, 'yes', 'owner')
        self.assertEqual(out['request_id'], ws.request_id_for('Run the migration?'))
        self.assertEqual([r['text'] for r in ws.status(self.s, self.tid)['requests']], ['Which branch?'], 'the other request stays open (PW-227)')

    def test_no_open_request_means_the_waiting_room(self):
        s = live(self.tid); term.SESSIONS['run1'] = s
        self.assertEqual(ws.answer_open(self.s, self.tid, 'carry on', 'owner')['state'], 'no_request')
        term.SESSIONS.clear()
        self.assertEqual(ws.answer_open(self.s, self.tid, 'carry on', 'owner')['state'], 'no_request')

    def test_the_delivery_path_is_the_integrations_own(self):
        pty = live(self.tid); api = live(self.tid, 'run2'); api.send_prompt = lambda t: None; dead = live(self.tid, 'run3'); dead.alive = False
        self.assertEqual((ws.delivery_path(pty), ws.delivery_path(api), ws.delivery_path(dead), ws.delivery_path(None)), ('pty', 'api', None, None))

    def test_the_operation_uses_the_request_when_there_is_one_and_the_waiting_room_otherwise(self):
        s = live(self.tid); s.send_prompt = lambda t: None; term.SESSIONS['run1'] = s
        op = {'kind': 'agent.answer', 'target': self.tid, 'params': {'text': 'yes'}}
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, 'waitroom_add', return_value={'wid': 1}) as wr:
            self.assertEqual(server._run_operation(op, None), wr.return_value)          # nothing asked: the waiting room
            ws.record(self.s, self.tid, 'run1', 'approval_needed', text='Run the migration?', source='hook')
            out = server._run_operation(op, None)
        self.assertEqual(wr.call_count, 1); self.assertTrue(out['delivered']); self.assertEqual(out['path'], 'api')
