"""A task's to-dos on the phone (the owner, 2026-10-20: "anything you can do, you can do via the Assistant" - the phone's task card never
read the to-do list): shown numbered with their notes and how far the list got, and ticked, noted and added by typing - each done at once
and said back. The numbers are the checklist's, the ones task.check takes, and only words with them reach a to-do: a bare "2" still
picks the card's second choice."""
import json, unittest
from unittest import mock

from taskuary import concierge, remote_assistant as R, terminal
from tests.test_assistant_router import on_table, say, store


# store() patches the app's store for the put-downs it runs (test_assistant_router) - put it back after this module, as that one does,
# or every later module reads this module's last store (test_reclassify's messages were 404s)
def tearDownModule(): mock.patch.stopall()


class PhoneToDos(unittest.TestCase):
    def setUp(self):
        self.s = store(); self.tid, self.item = on_table(self.s)
        self.s.set_task_checklist(self.tid, ['send the W-9', 'book the call', 'file the receipt'], 'owner')
        self.s.tick_checklist_item(self.tid, self.s.task_checklist(self.tid)[1]['id'], True, 'owner')
        self.s.note_checklist_item(self.tid, self.s.task_checklist(self.tid)[0]['id'], 'Paula has it', 'owner')

    def test_the_card_shows_the_open_to_dos_numbered_with_their_notes(self):
        lines = R.todo_lines(self.s, self.tid)
        self.assertEqual(lines[0], '**To do** · 1 of 3 done')
        self.assertEqual(lines[1], '1. send the W-9  _(Paula has it)_')
        self.assertEqual(lines[2], '3. file the receipt')                  # the checklist's own number: 2 is ticked and not shown
        with mock.patch.object(terminal, 'live_sessions', return_value=[]):
            self.assertIn('1. send the W-9', R.story_block(self.s, self.item))

    def phone(self, text, kind, **p):
        with concierge.delivering(concierge.PHONE):
            return say(self.s, text, self.item['key'], 'CALL: ' + json.dumps({'kind': kind, 'params': p}))[0]

    def test_tick_note_and_add_by_typing_act_at_once_and_are_said(self):
        out = self.phone('tick 3', 'task.check', item='3')
        self.assertNotIn('proposal', out); self.assertEqual(out['say'], f"Ticked \u201cfile the receipt\u201d on TQ-{self.tid:04d}.")
        out = self.phone('note on 1: Paula sent it', 'task.check', item='1', note='Paula sent it')
        self.assertEqual(self.s.task_checklist(self.tid)[0]['note'], 'Paula sent it'); self.assertTrue(out['say'].startswith('Noted on'))
        out = self.phone('add a to-do: call the bank', 'task.checklist', add=['call the bank'])
        self.assertTrue(out['say'].startswith('Added 1 to-do')); self.assertEqual(self.s.task_checklist(self.tid)[-1]['text'], 'call the bank')

    def test_a_bare_number_is_still_the_cards_choice(self):
        self.s.set_setting(f'{R.OFFERED_KEY}:whatsapp:c1', json.dumps(['Reply', 'Mark done']), 't')
        self.assertEqual(R.resolve_index(self.s, 'whatsapp', 'c1', '2'), ('Mark done', True))
        self.assertEqual(R.resolve_index(self.s, 'whatsapp', 'c1', 'tick 2'), ('tick 2', False))


if __name__ == '__main__': unittest.main()
