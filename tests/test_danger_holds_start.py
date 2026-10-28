"""MAIL THAT TRIES TO STEER AN AI STARTS NOTHING BY ITSELF (the Advisor design rev 2, the owner's ruling 2026-10-28: "injection-looking
mail blocks auto-start/carry-on until the owner presses"). What triage or ranking read a message as trying to make an AI do (its `danger`,
kept on message.Danger - the model's reading, never a word list) was a warning on the rail; now it also holds the unattended start, the
carry-on of a stopped conversation and the pass-in to a live one. The task is still made, and the owner can start it by hand. Invented
Northwind people only (CLAUDE.md)."""
import json, unittest
from unittest import mock

from taskuary import general, ingest, senders
from tests.test_carry_on import AGAIN, finished_task, mail, store

STEER = 'tells the assistant to forward the payroll file to an outside address'


def ingested(s, m, danger=None, intent='task'):
    llm = lambda sy, u, **k: json.dumps({'intent': intent, 'kind': 'general', 'why': 'w', 'asks_owner': True, 'danger': danger})
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest.ingest_message(s, m, llm=llm)
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


class DangerHoldsTests(unittest.TestCase):
    def test_a_mail_read_as_steering_an_ai_starts_no_agent(self):
        s = store()
        out, spawned = ingested(s, mail(), danger=STEER)
        self.assertNotIn('_auto_general', spawned)
        tid = out['task_id']
        self.assertTrue(tid, 'the task is still made - the owner starts it by hand')
        said = ' '.join(c['Body'] for c in s.list_comments(tid)) + ' ' + ' '.join(r.get('Reason') or '' for r in s._rows('SELECT Reason FROM route'))
        self.assertIn('attempt to steer an AI', said)
        self.assertEqual(s.list_messages(tid)[-1]['Danger'], STEER, 'and the flag stays on the message')

    def test_the_same_mail_without_it_starts_as_before(self):
        _out, spawned = ingested(store(), mail(), danger=None)
        self.assertEqual(spawned, ['_auto_general'])

    def test_new_work_that_steers_does_not_carry_the_stopped_conversation_on(self):
        s = store(); tid = finished_task(s)
        _out, spawned = ingested(s, mail(**AGAIN), danger=STEER)
        self.assertNotIn('_continue_general', spawned)
        self.assertIn('steer an AI', ingest.carry_on_why(s, tid, mail(**AGAIN), None, {'intent': 'task', 'danger': STEER}))

    def test_a_kept_reading_holds_too_and_a_null_word_is_none(self):
        s = store(); tid = finished_task(s)
        mid = s.list_messages(tid)[-1]['MessageId']
        self.assertEqual(ingest.danger(s, {}, mid), '')
        s.set_message_danger(mid, 'asks an AI to run a script from a link')
        self.assertEqual(ingest.danger(s, {}, mid), 'asks an AI to run a script from a link')
        ok, why = ingest.auto_start_ok(s, {}, mid, 'general')
        self.assertFalse(ok); self.assertIn('nothing starts until you press', str(why))
        for word in ('null', 'None', ''): self.assertEqual(ingest.danger(s, {}, None, {'danger': word}), '', word)
        # ...and a live agent is not typed into either
        with mock.patch.object(ingest, 'live_agent', return_value='general'), mock.patch.object(senders, 'known', return_value=(True, 'a colleague')):
            self.assertIn('steer an AI', ingest.pass_in_why(s, tid, {}, mid, {'intent': 'task'}))
            self.assertEqual(ingest.pass_in_why(s, tid, {}, None, {'intent': 'task'}), '', 'a clean line goes in as before')
