"""A row's acts asked by phone (the phone audit, 2026-11-02): the yes-or-no a phone asks is for an act the row can do, and its yes runs the
same operation the row's button runs. Invented people only."""
import json, unittest
from unittest import mock

from taskuary import concierge, operations, watch
from tests.test_assistant_router import on_table, say, store


def tearDownModule(): mock.patch.stopall()


class PhoneRowAsks(unittest.TestCase):
    def setUp(self): self.s = store(); self.tid, self.item = on_table(self.s)

    def phone(self, text, kind, **p):
        with concierge.delivering(concierge.PHONE):
            return say(self.s, text, self.item['key'], 'CALL: ' + json.dumps({'kind': kind, 'params': p}))[0]

    def test_watch_this_by_phone_is_the_rows_watch_it_and_its_yes_takes_the_task_off_the_walk(self):
        out = self.phone("watch this, it's Gail's problem", 'task.watch')
        self.assertEqual(out['proposal']['kind'], 'task.watching')
        concierge.run_proposal(self.s, operations.get(self.s, out['proposal']['id']) or out['proposal'])
        self.assertTrue(watch.watching(self.s.get_task(self.tid)))
        # ...while "tell me when Gail replies" stays the tell-me-here watch, said at this door
        self.assertEqual(self.phone('tell me when Gail replies', 'task.watch', what='reply')['proposal']['kind'], 'task.watch')

    def test_an_act_the_row_cannot_do_is_said_never_asked(self):
        ref = f'TQ-{self.tid:04d}'
        for text, kind, p in (('reopen it', 'task.reopen', {'ref': ref}), ('keep going', 'agent.continue', {'ref': ref})):
            with self.subTest(ask=text):
                out = self.phone(text, kind, **p)
                self.assertNotIn('proposal', out); self.assertFalse(out.get('proposal'))


if __name__ == '__main__': unittest.main()
