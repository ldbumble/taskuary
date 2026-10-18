"""What a real AI got wrong with the Assistant's tools (2026-10-18, 54 questions, sonnet): the typed CALL road let through cards
the buttons refuse, and the cards and descriptions said things that were not so. Each case is the model's CALL, scripted."""
import unittest
from unittest import mock

from taskuary import buttons, concierge, remind, toolcatalog
from tests.test_task_tools import table


def miss(s, item, kind, **params):
    dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
    with _Raises() as r:
        concierge.call_turn(s, dock, {'kind': kind, 'params': params}, item, 'do it')
    return r.said


class _Raises:
    said = None
    def __enter__(self): return self
    def __exit__(self, t, e, tb):
        if t is None: raise AssertionError('no CallMiss - a card was offered')
        if not issubclass(t, concierge.CallMiss): return False
        self.said = str(e); return True


class TheCallRoadChecksWhatTheButtonsCheckTests(unittest.TestCase):
    def test_a_hand_off_to_someone_who_never_wrote_here_goes_back_to_the_model(self):
        s, tid, mid, item = table()
        said = miss(s, item, 'task.handoff', who='Omar Keller', ref=f'TQ-{tid}')
        self.assertIn('Nobody called Omar Keller has written here', said)
        self.assertEqual(s._rows("SELECT * FROM operation WHERE Kind='task.handoff'"), [], 'no card nobody can run')

    def test_a_hand_off_to_someone_who_wrote_is_a_card(self):
        s, tid, mid, item = table()            # Erin Blake wrote the mail on the table
        dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
        out = concierge.call_turn(s, dock, {'kind': 'task.handoff', 'params': {'who': 'Erin Blake', 'ref': f'TQ-{tid}'}}, item, 'hand it to Erin')
        self.assertEqual(out['proposal']['kind'], 'task.handoff')

    def test_stop_with_nothing_running_says_so_and_offers_nothing(self):
        s, tid, mid, item = table()
        with mock.patch.object(concierge, '_agent_running', return_value=False):
            said = miss(s, item, 'agent.stop', ref=f'TQ-{tid}')
        self.assertIn(f'No agent is running on TQ-{tid:04d}', said)
        self.assertNotIn('transcript', said)

    def test_stop_with_an_agent_running_is_a_card(self):
        s, tid, mid, item = table()
        dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
        with mock.patch.object(concierge, '_agent_running', return_value=True):
            out = concierge.call_turn(s, dock, {'kind': 'agent.stop', 'params': {'ref': f'TQ-{tid}'}}, item, 'stop it')
        self.assertEqual(out['proposal']['kind'], 'agent.stop')


class TheCardSaysWhatIsSoTests(unittest.TestCase):
    def test_a_fact_is_summed_up_by_what_it_says_never_the_tool_name(self):
        s, tid, mid, item = table()
        dock = concierge.general.dock_task(s, 'owner')[0]['TaskId']
        out = concierge.call_turn(s, dock, {'kind': 'memory.remember', 'params': {'note': 'Gail covers payroll'}}, None, 'remember Gail covers payroll')
        self.assertNotIn('memory.remember', out['say'])
        self.assertIn('Gail covers payroll', out['say'])
        out = concierge.call_turn(s, dock, {'kind': 'memory.remember', 'params': {'note': 'Ray covers AP.'}}, None, 'remember it')
        self.assertNotIn('..', out['say'])

    def test_no_card_wears_a_sentence_written_for_the_model(self):
        for kind, p in (('routing.remember', {'field': 'kind', 'value': 'coding'}), ('memory.remember', {'note': 'x'})):
            lbl = concierge.op_label(kind, p)
            self.assertNotIn('ROUTED', lbl); self.assertNotIn('`', lbl); self.assertLess(len(lbl), 40, lbl)

    def test_a_split_is_called_a_split(self):
        self.assertEqual(concierge.op_label('task.split', {'text': 'two jobs'}), buttons.label('split', 'split'))
        self.assertIn(buttons.label('split', 'split'), buttons.labels())

    def test_a_reply_on_a_closed_task_says_it_is_closed_and_stays_closed(self):
        s, tid, mid, item = table()
        s.update_task(tid, {'Status': 'done'}, 'owner')
        note = concierge.closed_note(s, item)
        self.assertIn(f'TQ-{tid:04d} is closed', note); self.assertIn(buttons.label('reopen'), note)
        s.update_task(tid, {'Status': 'open'}, 'owner')
        self.assertEqual(concierge.closed_note(s, item), '')


class TheToolsSayWhatToPassTests(unittest.TestCase):
    def test_mark_done_names_its_note(self):
        self.assertIn('`note`', toolcatalog.PURPOSE['task.complete'])
        self.assertIn('task.complete(note?)', toolcatalog.block())

    def test_after_my_meetings_is_the_token_calendar_or_not(self):
        self.assertIn('calendar or not', toolcatalog.PURPOSE['task.defer'])

    def test_with_no_calendar_after_meetings_says_there_is_no_calendar(self):
        s, tid, mid, item = table()
        s.set_setting('calendar_enabled', '1', 'test')
        with mock.patch('taskuary.remind.agenda', return_value=[]):
            with self.assertRaisesRegex(ValueError, 'no calendar is connected'): remind.set_reminder(s, tid, remind.AFTER_MEETINGS)

    def test_an_answer_with_no_agent_waits_for_the_next_one_and_never_starts_one(self):
        self.assertIn('never this', toolcatalog.PURPOSE['agent.answer'])


class TheRailSaysADraftWaitsTests(unittest.TestCase):
    def test_a_row_with_a_draft_says_one_waits(self):
        p = {'items': [{'ref': 'TQ-0004', 'who': 'Erin Blake', 'title': 'Invoice 88213', 'lane': 'approve', 'rid': 2, 'draft': 'Approved - thanks.'},
                       {'ref': 'TQ-0007', 'who': 'Ray Colton', 'title': 'Laptop', 'lane': 'approve'}]}
        rows = concierge._rail_block(p).splitlines()
        self.assertIn('a drafted reply waits for your yes', next(r for r in rows if 'TQ-0004' in r))
        self.assertNotIn('drafted reply', next(r for r in rows if 'TQ-0007' in r))
