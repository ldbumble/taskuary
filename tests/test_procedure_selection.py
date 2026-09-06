"""A saved request procedure is selected in triage and delivered to whichever worker kind the
verdict names - selecting it never makes the task a coding job (PW-205, PW-206).

A playbook match used to force kind='coding' in the classifier ("an agent works a playbook, whatever
kind said"), so a PTO request whose procedure is a general job started a coding session in some
checkout. Now the procedure rides on the task as its `playbook:` tag whatever the kind, the kind is
the model's own (general by default), and the same playbook block that seeds a coding session is in
the general worker's prompt too.
"""
import json, unittest
from unittest import mock

from taskuary import general, ingest, playbooks, terminal, triage
from taskuary.store import MemoryStore

PTO = """# Handle a PTO request
when:      an employee asks for time off, or HR forwards a PTO form
uses:      hr portal (read)  ·  calendar (write: team calendar)
steps:     check the balance in the HR portal → confirm the dates do not clash with the team calendar →
           reply with approval or the clash → put the days on the team calendar
alone:     requests of five days or fewer with enough balance
ask first: anything longer, or a clash with another absence
done when: the reply went out and the days are on the calendar

Managers approve; the assistant prepares everything and asks before anything is written.
"""
MSG = {'external_id': 'pto1', 'channel': 'email', 'from_email': 'sam@ours.example', 'from_name': 'Sam', 'conversation_id': 'AAQk-pto',
       'subject': 'PTO 12-14 October', 'body': 'Hi Uri, can I take 12 to 14 October off? I have the days.', 'sent_at': '2026-09-06 09:00:00'}


class ProcedureTests(unittest.TestCase):
    def setUp(self):
        playbooks.write('pto-request', PTO)
        self.addCleanup(lambda: playbooks.delete('pto-request'))

    def test_selecting_a_procedure_leaves_the_kind_to_the_model(self):
        for kind in ('general', 'task'):
            llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': kind, 'why': 'a PTO request', 'playbook': 'pto-request'})
            out = triage.classify_intent(MSG, llm=llm, playbooks=playbooks.menu())
            self.assertEqual((out['playbook'], out['kind']), ('pto-request', kind))

    def test_a_pto_request_becomes_a_general_task_with_its_procedure_and_no_coder(self):
        s = MemoryStore(); s.set_setting('coder_auto_enabled', '1', 't'); s.upsert_agent('coder', 'coding', 'cli', '{}')
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'a PTO request', 'playbook': 'pto-request'})
        spawned = []
        with mock.patch.object(ingest, '_spawn', side_effect=lambda f, *a: spawned.append(f.__name__)):
            out = ingest.ingest_message(s, dict(MSG), llm=llm)
        t = s.get_task(out['task_id'])
        self.assertEqual(t['Kind'], 'general'); self.assertEqual(playbooks.of_task(t), 'pto-request')
        self.assertNotIn('_auto_code', spawned)

    def test_the_general_worker_gets_the_same_procedure_block_as_a_coder_would(self):
        s = MemoryStore()
        llm = lambda *a, **k: json.dumps({'intent': 'task', 'kind': 'general', 'why': 'a PTO request', 'playbook': 'pto-request'})
        with mock.patch.object(ingest, '_spawn'):
            tid = ingest.ingest_message(s, dict(MSG), llm=llm)['task_id']
        system, _user = general._prompt(s, tid)
        self.assertIn('PLAYBOOK "Handle a PTO request"', system); self.assertIn('team calendar', system)
        self.assertIn('PLAYBOOK "Handle a PTO request"', terminal.seed_text(s, tid))   # the coding brief carries the same block


if __name__ == '__main__':
    unittest.main()
