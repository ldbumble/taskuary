"""A button never waits on the AI before the owner sees what it did (the owner, 2026-10-01: "Split, Make a task are
buttons - act instantly, triage enriches after").

Make a task, Mine, Dispatch and Split message each asked the model for the task's summary and checklist INSIDE the
request (triage.extract_ask), so the row sat on a spinner for as long as the brain took to answer. The task is made from
what is already known - the subject as the title, the sender's own words as the ask, the kind the button says - and the
summary and the to-dos land on it in place once the model has read the mail.

The brain here blocks until the test lets it go: the press must come back, task and all, while it is still blocked.
"""
import json, threading, time, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import ingest, server, terminal
from taskuary.store import MemoryStore

BODY = 'Morning - the payroll export failed again overnight. Can you look before the 10am run?'


class GatedBrain:
    """A model that answers only when the test says so."""
    def __init__(self): self.gate, self.asked = threading.Event(), threading.Event()
    def __call__(self, system, user, *a, **kw):
        self.asked.set()
        self.gate.wait(10)
        return json.dumps({'summary': 'Fix the overnight payroll export before the 10am run.',
                           'checklist': ['Find why the export failed', 'Rerun it before 10am']})


class PressNeverWaitsTests(unittest.TestCase):
    def setUp(self):
        self.s, self.brain = MemoryStore(), GatedBrain()
        self.s.upsert_agent('coder', 'coding', 'cli', '{}')
        self.addCleanup(self.brain.gate.set)                    # a failing test must not leave a thread parked
        for p in (mock.patch.object(server, 'store', self.s), mock.patch.dict(terminal.SESSIONS, {}, clear=True),
                  mock.patch.object(ingest, '_spawn'), mock.patch('taskuary.llm.build_llm', return_value=self.brain)):
            p.start(); self.addCleanup(p.stop)
        self.c = TestClient(server.app)

    def _mail(self, **kw):
        return self.s.add_message({'ExternalId': f'x:{time.time_ns()}', 'Channel': 'email', 'Subject': 'Payroll export failed',
                                   'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example', 'SentAt': '2026-10-01 08:00:00',
                                   'BodyText': BODY, 'Status': 'ignored', **kw})

    def _press(self, path, body):
        """The press, timed against a brain that has not answered: it must come back regardless."""
        out = {}
        t = threading.Thread(target=lambda: out.update(r=self.c.post(path, json=body)), daemon=True)
        t.start(); t.join(5)
        self.assertFalse(t.is_alive(), f'{path} waited on the model')
        self.assertEqual(out['r'].status_code, 200, out['r'].text)
        return out['r'].json()

    def _lands_after(self, tid):
        """...and the model's reading lands on the same task once it answers."""
        t = self.s.get_task(tid)
        self.assertEqual(t['Title'], 'Payroll export failed')               # the subject, at once
        self.assertIn('payroll export failed again', t['Summary'])          # the sender's own words, at once
        self.assertEqual(self.s.task_checklist(tid), [])
        self.assertTrue(self.brain.asked.wait(5), 'the enrichment never asked the model')
        self.brain.gate.set()
        for _ in range(250):
            if self.s.task_checklist(tid): break
            time.sleep(0.02)
        self.assertEqual([i['text'] for i in self.s.task_checklist(tid)], ['Find why the export failed', 'Rerun it before 10am'])
        self.assertEqual(self.s.get_task(tid)['Summary'], 'Fix the overnight payroll export before the 10am run.')

    def test_make_a_task_mine(self):
        mid = self._mail()
        tid = self._press(f'/api/messages/{mid}/mine', {'kind': 'task'})['taskId']
        self.assertEqual(self.s.get_message(mid)['TaskId'], tid)
        self.assertEqual(self.s.get_task(tid)['Kind'], 'task')
        self._lands_after(tid)

    def test_make_a_task_for_the_assistant(self):
        mid = self._mail()
        tid = self._press(f'/api/messages/{mid}/mine', {'kind': 'general'})['taskId']
        self.assertEqual(self.s.get_task(tid)['Kind'], 'general')
        self._lands_after(tid)

    def test_dispatch_message(self):
        mid = self._mail()
        with mock.patch.object(server, 'start_session', return_value={'sid': 's1', 'agent': 'coder'}):
            out = self._press(f'/api/messages/{mid}/dispatch', {'kind': 'coding', 'agent': 'coder'})
        self.assertEqual(self.s.get_task(out['taskId'])['Kind'], 'coding')
        self._lands_after(out['taskId'])

    def test_split_message(self):
        old = self.s.create_task({'Title': 'Payroll', 'Kind': 'task', 'Summary': 'the first ask'}, 'router')
        mid = self._mail(TaskId=old, Status='routed')
        tid = self._press(f'/api/messages/{mid}/split', {'kind': 'task'})['taskId']
        self.assertNotEqual(tid, old)
        self.assertEqual(self.s.get_message(mid)['TaskId'], tid)
        self._lands_after(tid)

    def test_the_model_never_overwrites_what_the_owner_wrote_meanwhile(self):
        """The enrichment fills in what the press left plain - an ask or a to-do list the owner wrote in the
        meantime is theirs, and a slow model must not come back over it."""
        mid = self._mail()
        tid = self._press(f'/api/messages/{mid}/mine', {'kind': 'task'})['taskId']
        self.s.update_task(tid, {'Summary': 'my own words'}, 'owner')
        self.s.set_task_checklist(tid, ['my own box'], 'owner')
        self.assertTrue(self.brain.asked.wait(5))
        self.brain.gate.set()
        for t in [t for t in threading.enumerate() if t.name == ingest.ENRICH_THREAD]: t.join(5)
        self.assertEqual(self.s.get_task(tid)['Summary'], 'my own words')
        self.assertEqual([i['text'] for i in self.s.task_checklist(tid)], ['my own box'])


if __name__ == '__main__': unittest.main()
