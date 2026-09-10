"""`taskuary --done "<sentence>"` saves the agent's ACTUAL final answer - the Stop hook's last message for that run -
as the Finished result; the sentence is the summary (PW-230). Codex App Server capture stays open (PW-224)."""
from unittest import mock

from taskuary import selfclose, terminal as term, workerstate as ws
from tests.test_worker_events import Base, live


def quiet_gates():
    return [mock.patch.object(selfclose, 'blocked', return_value=''), mock.patch.object(selfclose, '_mark', return_value=True),
            mock.patch.object(selfclose, 'stays_open', return_value=False), mock.patch.object(selfclose, '_wrap', return_value={'closed': True}),
            mock.patch.object(selfclose, 'mode', return_value='auto')]


class FinalAnswer(Base):
    def declare(self, sentence):
        patches = quiet_gates()
        for p in patches: p.start()
        try: return selfclose.declare(self.s, self.tid, sentence, 'coder')
        finally:
            for p in patches: p.stop()

    def test_the_finished_event_carries_the_runs_last_spoken_message(self):
        s = live(self.tid); term.SESSIONS['run1'] = s
        ws.record(self.s, self.tid, 'run1', 'turn_end', text='Earlier partial answer.', source='hook')
        ws.record(self.s, self.tid, 'run1', 'working', source='hook')
        ws.record(self.s, self.tid, 'run1', 'turn_end', text='I fixed the cron: the schedule was UTC. Tests pass.', source='hook')
        self.declare('cron fixed')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'finished'); self.assertEqual(st['result'], 'I fixed the cron: the schedule was UTC. Tests pass.')
        self.assertIn('cron fixed', self.s.list_comments(self.tid)[-1]['Body'], 'the sentence is the summary the owner reads')

    def test_another_runs_last_message_is_not_this_runs_answer(self):
        ws.record(self.s, self.tid, 'old', 'turn_end', text='The old run said this.', source='hook')
        s = live(self.tid, 'run2'); term.SESSIONS['run2'] = s
        self.declare('done now')
        self.assertEqual(ws.status(self.s, self.tid)['result'], 'done now')

    def test_with_no_spoken_message_the_sentence_is_the_result(self):
        s = live(self.tid); term.SESSIONS['run1'] = s
        self.declare('cron fixed')
        self.assertEqual(ws.status(self.s, self.tid)['result'], 'cron fixed')
