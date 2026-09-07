"""A regular (API) worker says what it needs and when its turn ended, as events - not prose a judge reads (PW-225).

Its turn used to leave one `working` event and nothing after it, so a parked assistant read as working for ever and a
question it asked in prose was a question nobody saw. Now every reply ends the turn with `turn_end`, and a reply that
ends with the ask marker is an Input-needed request with the exact question and choices - the same request the
owner's answer is bound to (workerstate.answer)."""
import unittest
from unittest import mock

from taskuary import general, selfclose, workerstate as ws
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class AskMarker(unittest.TestCase):
    def test_the_ask_marker_parses_question_and_choices(self):
        self.assertEqual(selfclose.ask_marker('I compared them.\n[[TASKUARY-ASK]] Which vendor? | Acme | Globex'),
                         ('I compared them.', 'Which vendor?', ['Acme', 'Globex']))
        self.assertEqual(selfclose.ask_marker('[[TASKUARY-ASK]]: Go ahead?'), ('', 'Go ahead?', []))
        self.assertEqual(selfclose.ask_marker('plain reply'), ('plain reply', None, []))

    def test_the_prompt_line_teaches_the_marker_and_only_for_a_real_blocker(self):
        self.assertIn(selfclose.ASK_MARKER, selfclose.ASK_LINE); self.assertIn('real blocker', selfclose.ASK_LINE)


class ApiWorkerSignals(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.fx = Factory(self.s); self.tid = self.fx.task(title='Compare vendors', kind='general')

    def turn(self, answer, text='compare them'):
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(self.s, self.tid)
        brain = lambda system, user, **kw: answer
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain):
            return sess, sess.send_prompt(text)

    def test_a_turn_records_turn_end_and_an_ask_records_input_needed(self):
        sess, reply = self.turn('Two options.\n[[TASKUARY-ASK]] Which vendor? | Acme | Globex')
        self.assertNotIn('TASKUARY-ASK', reply)
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['state'], 'input_needed'); self.assertEqual(st['requests'][0]['choices'], ['Acme', 'Globex'])
        self.assertEqual([e['Kind'] for e in ws.events(self.s, self.tid, sess.sid)], ['working', 'turn_end', 'input_needed'])

    def test_a_plain_reply_ends_the_turn_and_is_no_hand_raise(self):
        sess, _ = self.turn('Acme is cheaper; Globex ships faster.')
        st = ws.status(self.s, self.tid)
        self.assertEqual(st['requests'], []); self.assertNotEqual(st['state'], 'input_needed')
        self.assertEqual([e['Kind'] for e in ws.events(self.s, self.tid, sess.sid)], ['working', 'turn_end'])
        self.assertIs(ws.waiting_of(self.s, sess), False, 'a parked assistant with no question raises no hand (PW-226)')

    def test_the_owners_answer_resumes_the_same_session(self):
        sess, _ = self.turn('[[TASKUARY-ASK]] Which vendor? | Acme | Globex')
        sent = []; sess.send_prompt = lambda t, **kw: sent.append(t)
        from taskuary import terminal as term
        saved = dict(term.SESSIONS); term.SESSIONS.clear(); term.SESSIONS[sess.sid] = sess
        try: out = ws.answer_open(self.s, self.tid, 'Acme', 'owner')
        finally: term.SESSIONS.clear(); term.SESSIONS.update(saved)
        self.assertTrue(out['delivered']); self.assertEqual(sent, ['Acme']); self.assertEqual(out['path'], 'api')
        self.assertEqual(ws.status(self.s, self.tid)['requests'], [])

    def test_the_system_prompt_teaches_the_marker(self):
        seen = {}
        with mock.patch.object(general, '_selected', return_value=('api:test', 'Test', 'm')):
            sess = general.GeneralSession(self.s, self.tid)
        def brain(system, user, **kw): seen['system'] = system; return 'ok'
        with mock.patch.object(general.llm_mod, 'build_llm', return_value=brain): sess.send_prompt('hi')
        self.assertIn(selfclose.ASK_MARKER, seen['system'])
