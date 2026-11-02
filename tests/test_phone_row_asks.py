"""A row's acts asked by phone (the phone audit, 2026-11-02): the yes-or-no a phone asks is for an act the row can do, and its yes runs the
same operation the row's button runs. Invented people only."""
import json, unittest
from unittest import mock

from taskuary import concierge, operations, watch
from tests.test_assistant_router import on_table, say, store


def tearDownModule(): mock.patch.stopall()


class PhoneRowAsks(unittest.TestCase):
    def setUp(self): self.s = store(); self.tid, self.item = on_table(self.s)

    def phone(self, text, tool, **p):
        with concierge.delivering(concierge.PHONE):
            return say(self.s, text, self.item['key'], 'CALL: ' + json.dumps({'kind': tool, 'params': p}))[0]

    def test_watch_this_by_phone_is_the_rows_watch_it_run_at_once(self):
        out = self.phone("watch this, it's Gail's problem", 'task.watch')
        self.assertEqual((out['proposal']['kind'], out['proposal'].get('auto')), ('task.watching', True))
        concierge.run_proposal(self.s, operations.get(self.s, out['proposal']['id']) or out['proposal'])
        self.assertTrue(watch.watching(self.s.get_task(self.tid)))
        # ...and "tell me when Gail replies" is the same Watch it, as the desk lights it (the owner, 2026-11-02: "both should mean same thing")
        for p in ({'what': 'reply'}, {'what': 'done'}):
            self.assertEqual(self.phone('tell me when Gail replies', 'task.watch', **p)['proposal']['kind'], 'task.watching')
        self.assertEqual(self.phone('stop watching it', 'task.watch', what='off')['proposal']['params'], {'off': True})

    def test_a_small_change_acts_at_once_and_a_send_or_a_close_still_asks(self):
        # the owner, 2026-11-02: "yes" to "should small changes act without asking" - nothing sent, nothing closed
        for text, kind, p in (('make it high priority', 'task.update', {'priority': 'high'}), ('this is a coding task', 'task.set_kind', {'kind': 'coding'}),
                              ('remind me friday', 'task.defer', {'until': 'friday 9am'})):
            with self.subTest(ask=text): self.assertTrue(self.phone(text, kind, **p)['proposal'].get('auto'))
        # ...a kind with no kind named still asks: the picker is the question
        self.assertFalse((self.phone('change what kind it is', 'task.set_kind').get('proposal') or {}).get('auto'))
        self.assertFalse(self.phone('forward this to gail@northwind.example', 'task.handoff', who='gail@northwind.example')['proposal'].get('auto'))

    def test_an_act_the_row_cannot_do_is_said_never_asked(self):
        ref = f'TQ-{self.tid:04d}'
        for text, kind, p in (('reopen it', 'task.reopen', {'ref': ref}), ('keep going', 'agent.continue', {'ref': ref})):
            with self.subTest(ask=text):
                out = self.phone(text, kind, **p)
                self.assertNotIn('proposal', out); self.assertFalse(out.get('proposal'))


if __name__ == '__main__': unittest.main()
