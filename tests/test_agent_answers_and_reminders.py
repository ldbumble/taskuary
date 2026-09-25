"""The owner, 2026-09-25, on the agent lifecycle map: A11 a new question gets through a reminder; A12 the phone saves an
answer for an agent that stopped asking; A13 a note to a stalled agent waits until the limit lifts."""
import unittest
from unittest import mock

from taskuary import funnel, processing_unread, remind, remote_assistant as ra, terminal, waitroom, workerstate as ws
from taskuary.store import MemoryStore
from test_funnel import ago


class QuestionGetsThroughAReminderTests(unittest.TestCase):
    def test_a_waiting_agent_is_on_the_rail_whatever_the_reminder_says(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        s.add_message({'TaskId': t, 'ExternalId': 'e1', 'Channel': 'email', 'Subject': 'Export', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'SentAt': ago(1), 'BodyText': 'Is it fixed?', 'Status': 'routed'})
        remind.set_reminder(s, t, '1 week')
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        quiet = [{'taskId': t, 'agent': 'coder', 'sid': 's1', 'waiting': False, 'tail': []}]
        asking = [{'taskId': t, 'agent': 'coder', 'sid': 's1', 'waiting': True, 'state': 'asking', 'line': 'coder asked you: which branch?', 'tail': []}]
        rail = lambda live: [i['unread'] for i in processing_unread.build(s, live_state=live, include_read=True)['items'] if i.get('tid') == t]
        self.assertEqual(rail(quiet), [False], 'put away while it works quietly')
        self.assertEqual(rail(asking), [True], 'a new question gets through')


class StalledAgentHoldsNotesTests(unittest.TestCase):
    def test_a_stall_is_not_a_question(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        fake = mock.Mock(task_id=t, alive=True, sid='s1'); fake.waiting.return_value = True
        with mock.patch.dict(terminal.SESSIONS, {'s1': fake}, clear=True), \
             mock.patch.object(ws, 'asking_of', return_value={'kind': 'stalled', 'text': 'rate limit'}):
            self.assertEqual(waitroom.state(s, t)[0], 'working')
        with mock.patch.dict(terminal.SESSIONS, {'s1': fake}, clear=True), \
             mock.patch.object(ws, 'asking_of', return_value={'kind': 'input_needed', 'text': 'which branch?'}):
            self.assertEqual(waitroom.state(s, t)[0], 'asking')


class PhoneSavesALateAnswerTests(unittest.TestCase):
    def test_an_answer_to_an_agent_that_stopped_asking_is_saved_for_it(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        item = {'kind': 'agent', 'tid': t, 'agent': 'coder', 'asking': True, 'choices': ['main', 'release']}
        with mock.patch.object(ws, 'answer_open', return_value={'delivered': False, 'state': 'no_request'}), \
             mock.patch.object(waitroom, 'add', return_value={'queued': True}) as saved:
            said = ra.answer_the_agent(s, item, 'main', True)
        saved.assert_called_once_with(s, t, 'main', 'owner')
        self.assertIn('saved', said)


if __name__ == '__main__': unittest.main()
