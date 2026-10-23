"""An agent ticks the to-dos it finishes (the owner, 2026-10-22): `taskuary --tick <id>` / `--untick <id>` from its own session.
Only the box moves, only on its own task, and never an email box or a goal's step - those tick themselves."""
import unittest
from unittest import mock
from fastapi.testclient import TestClient

from taskuary import config, general, server, terminal
from taskuary.store import MemoryStore


def _task(s):
    tid = s.create_task({'Title': 'Renew the Trainly licence', 'Kind': 'general', 'Status': 'open'}, 't')
    s.set_task_checklist(tid, ['Check the seat count', 'Ask Gail Moreno for the PO'], 't')
    s.add_checklist_items(tid, [{'text': 'Confirm the renewal with the vendor', 'out': {'to': 'sales@vendor.example'}}], 't')
    return tid, {i['text']: i['id'] for i in s.task_checklist(tid)}


class TickTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid, self.ids = _task(self.s)

    def test_the_agents_checklist_carries_the_ids_it_may_tick_and_the_owners_does_not(self):
        md = self.s.checklist_markdown(self.tid, ids=True)
        self.assertIn(f"- [ ] Check the seat count [{self.ids['Check the seat count']}]", md)
        self.assertNotIn(f"[{self.ids['Confirm the renewal with the vendor']}]", md)        # the email box: its --slot line says how
        self.assertNotIn(self.ids['Check the seat count'], self.s.checklist_markdown(self.tid))   # the Assistant's and the page's copy

    def test_both_prompts_carry_the_ids_and_the_rule(self):
        system, user = general._prompt(self.s, self.tid)
        self.assertIn(f"[{self.ids['Check the seat count']}]", user); self.assertIn('taskuary --tick <id>', system)
        seed = terminal.seed_text(self.s, self.tid, repo=None, cwd=None)
        self.assertIn(f"[{self.ids['Check the seat count']}]", seed); self.assertIn('taskuary --tick <id>', seed)

    def _post(self, item, done=True):
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, '_own_task_only', return_value=None):
            return TestClient(server.app).post('/api/agent/tick', json={'task_id': self.tid, 'item': item, 'done': done})

    def test_tick_and_untick_move_only_the_box(self):
        i = self.ids['Ask Gail Moreno for the PO']
        r = self._post(i)
        self.assertEqual(r.status_code, 200); self.assertTrue(r.json()['done'])
        box = {x['id']: x for x in self.s.task_checklist(self.tid)}[i]
        self.assertTrue(box['done']); self.assertEqual(box['text'], 'Ask Gail Moreno for the PO')
        self._post(i, done=False)
        self.assertFalse({x['id']: x for x in self.s.task_checklist(self.tid)}[i]['done'])

    def test_an_unknown_id_and_an_email_box_are_refused(self):
        self.assertEqual(self._post('nope1234').status_code, 404)
        self.assertEqual(self._post(self.ids['Confirm the renewal with the vendor']).status_code, 422)
        self.assertFalse(any(x['done'] for x in self.s.task_checklist(self.tid)))

    def test_a_session_ticks_only_its_own_task(self):
        agent = {'X-Taskuary-Token': config.load()['server']['agent_token']}
        with mock.patch.object(server, 'store', self.s):
            r = TestClient(server.app).post('/api/agent/tick', json={'task_id': self.tid, 'item': self.ids['Check the seat count']}, headers=agent)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(any(x['done'] for x in self.s.task_checklist(self.tid)))


if __name__ == '__main__':
    unittest.main()
