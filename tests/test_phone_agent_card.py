"""The phone's agent card (2026-10-06): what the agent RETURNED is shown, its question is the agent's line and not the
owner's, a task the owner asked for is never the Advisor's idea, and a receipt that says "open it" can be opened."""
import json, unittest
from unittest import mock

from taskuary import remote_assistant as ra
from taskuary.store import MemoryStore


class PhoneAgentCardTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Count the event log runs', 'Kind': 'general', 'Source': 'assistant',
                                       'SourceRef': 'assistant:agent', 'Status': 'in_progress'}, 'owner')
        self.s._exec('UPDATE task SET AskedVia=? WHERE TaskId=?', ('whatsapp:chat1', self.tid))
        self.s._exec("INSERT INTO worker_event (TaskId, Sid, Kind, Text, Source, CreatedAt) VALUES (?, 's1', 'turn_end', ?, 'api', '2026-10-06 16:06:35')",
                     (self.tid, '158 events came in today; 107 processed, 51 pending.'))
        self.item = {'kind': 'agent', 'tid': self.tid, 'ref': f'TQ-{self.tid:04d}', 'title': 'Count the event log runs', 'lane': 'blocked',
                     'asking': True, 'tail': ['Where do the run results get reported?'], 'agent': 'analyst', 'who': 'You', 'channel': 'own'}

    def test_the_result_leads_and_the_question_is_the_agents(self):
        story = ra.story_block(self.s, self.item)
        self.assertIn('158 events came in today', story)
        self.assertIn('asks: **Where do the run results get reported?**', story)
        self.assertNotIn('Advisor', story)                                   # the owner asked for it on the phone
        move = ra.move_block(self.s, self.item)
        self.assertNotIn('Where do the run results get reported?', move)       # under You: only what to do about it

    def test_a_done_receipt_that_made_a_task_offers_to_open_it(self):
        with mock.patch('taskuary.concierge.receipt', return_value='Done - Start a regular agent on it. Open it from here.'):
            text = ra.receipt_text(self.s, {'status': 'done', 'outcome': {'taskId': self.tid, 'ref': f'TQ-{self.tid:04d}'}})
        self.assertIn(f'Open TQ-{self.tid:04d}', text)


class RunEndedTests(unittest.TestCase):
    """F5: the agent's line said "is waiting on you" over a run that had failed, and a finished one read the same. The card
    reads how the run ended by its own word (workerstate.ended) - failed with its reason (owner-approved R2), or finished."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Reconcile the March ledger', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.item = {'kind': 'agent', 'tid': self.tid, 'ref': f'TQ-{self.tid:04d}', 'title': 'Reconcile the March ledger', 'lane': 'blocked',
                     'agent': 'assistant', 'who': 'Gail Moreno', 'channel': 'email'}

    def event(self, kind, text):
        self.s._exec("INSERT INTO worker_event (TaskId, Sid, Kind, Text, Source, CreatedAt) VALUES (?, 's1', ?, ?, 'api', '2026-10-21 09:00:00')",
                     (self.tid, kind, text))

    def agent_line(self):
        story = ra.story_block(self.s, self.item)
        return next(l for l in story.splitlines() if l.startswith(ra.DOT_AGENT))

    def test_a_failed_run_says_why_and_never_that_it_waits_on_you(self):
        self.event('failed', 'no AI is connected to run on')
        line = self.agent_line()
        self.assertIn('· failed - ', line)
        self.assertNotIn('waiting on you', ra.story_block(self.s, self.item))

    def test_a_finished_run_says_finished(self):
        self.event('finished', 'The ledger balances.')
        self.assertTrue(self.agent_line().endswith('· finished'), self.agent_line())

    def test_a_run_that_is_parked_still_says_it_waits_on_you(self):
        self.assertTrue(self.agent_line().endswith('· is waiting on you'), self.agent_line())

    def test_a_failed_run_with_no_row_left_comes_back_to_the_chat(self):
        import json
        from taskuary import funnel, messengers
        self.s.set_setting(ra.PROMISES_KEY, json.dumps([{'tid': self.tid, 'channel': 'whatsapp', 'chat': 'c1', 'at': __import__('time').time(),
                                                          'lane': 'working', 'ended': True}]), 't')
        ra.owner_spoke(self.s, 'whatsapp', 'c1')                      # still talking in the chat that asked
        self.event('failed', 'no AI is connected to run on')
        with mock.patch.object(funnel, 'pile', return_value={'items': [], 'alerts': []}), mock.patch.object(messengers, 'wa_send') as sent:
            self.assertEqual(ra.keep_promises(self.s, force=True), 1)
        self.assertIn(f'TQ-{self.tid:04d} is back: the agent failed - ', sent.call_args.args[2])


class HeldTaskTests(unittest.TestCase):
    """F7: an in-progress general agent on a todo task - the header read "agent working" over "No agent yet - nobody is working
    on this", and Send to agent was offered on a task an agent already held."""
    def test_header_and_body_read_the_same_session_and_no_second_hand_off(self):
        from taskuary import terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'Draft the vendor reply', 'Kind': 'general', 'Status': 'in_progress'}, 'owner')
        item = {'key': f'task:{tid}', 'kind': 'todo', 'lane': 'yours', 'tid': tid, 'ref': f'TQ-{tid:04d}', 'title': 'Draft the vendor reply',
                'who': 'owner', 'channel': 'own'}
        # a session at work says so in its own word (session.info) - the one the page and the rail read (taskstate)
        live = mock.Mock(task_id=tid, alive=True, started=1, **{'info.return_value': {'alive': True, 'waiting': False}})
        chips = [{'verb': 'close', 'label': 'Mark done'}, {'verb': 'regular_agent', 'label': 'Send to agent'}, {'verb': 'next', 'label': 'Next'}]
        with mock.patch.dict(terminal.SESSIONS, {'s1': live}):
            text = ra.turn_text({'say': 'x', 'item': item, 'chips': chips}, store=s)
        self.assertNotIn('No agent yet', text)
        self.assertIn('agent working', text.splitlines()[0])
        self.assertIn('· working', text)
        self.assertNotIn('Send to agent', text)
        self.assertIn('Mark done', text)

    def test_a_parked_session_over_a_finished_turn_is_never_working(self):
        """Walk 6 (H1): "agent working" on four finished tasks while the desktop chip said "agent done" - the phone read a session that was
        up and parked as an agent at work. It reads the task's one state (taskstate), as the chip does."""
        from taskuary import terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'Board pack for Thursday', 'Kind': 'general', 'Status': 'open'}, 'owner')
        s._exec("INSERT INTO worker_event (TaskId, Sid, Kind, Text, Source, CreatedAt) VALUES (?, 's1', 'turn_end', ?, 'api', '2026-11-23 08:40:00')",
                (tid, 'The pack is built and saved.'))
        item = {'key': f'task:{tid}', 'kind': 'todo', 'lane': 'yours', 'tid': tid, 'ref': f'TQ-{tid:04d}', 'title': 'Board pack for Thursday',
                'who': 'owner', 'channel': 'own'}
        parked = mock.Mock(task_id=tid, alive=True, started=1, sid='s1',
                           **{'info.return_value': {'alive': True, 'waiting': True, 'state': 'parked', 'sid': 's1'}})
        with mock.patch.dict(terminal.SESSIONS, {'s1': parked}), mock.patch('taskuary.workerstate.on_task', return_value=True):
            text = ra.turn_text({'say': 'x', 'item': item, 'chips': [{'verb': 'next', 'label': 'Next'}]}, store=s)
        self.assertNotIn('working', text)


class WaitingCardTests(unittest.TestCase):
    """Walk 6 (H1): the email to Gail waited on the desk and the agent was told it waited; the phone's bubble showed no word of it, its poll
    had no Send, and asked for the text the phone said "I do not have the text of the message in front of me here". The card that waits is
    the task's front card (cardqueue), shown in full with its own buttons, pressed through the desk's own door."""
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Board pack for Thursday', 'Kind': 'general', 'Status': 'open'}, 'owner')
        self.s._exec("INSERT INTO worker_event (TaskId, Sid, Kind, Text, Source, CreatedAt) VALUES (?, 's1', 'turn_end', ?, 'api', '2026-11-23 08:40:00')",
                     (self.tid, 'The pack is ready; the email to Gail waits for you.'))
        self.rid = self.s.add_review({'TaskId': self.tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Hi Gail, the board pack is attached.',
                                      'Deliver': json.dumps({'channel': 'email', 'to': ['gail@northwind.example'], 'slot': 's1'})})
        # the rail's row carries no review id - the shape the phone missed
        self.item = {'kind': 'agentdone', 'tid': self.tid, 'key': f'task:{self.tid}', 'ref': f'TQ-{self.tid:04d}', 'title': 'Board pack for Thursday',
                     'who': 'You', 'channel': 'own'}

    def test_the_waiting_email_is_in_the_bubble_with_its_own_buttons(self):
        text = ra.turn_text({'say': 'x', 'item': self.item, 'chips': [{'verb': 'next', 'label': 'Next'}]}, store=self.s)
        self.assertIn('Hi Gail, the board pack is attached.', text)
        self.assertIn('gail@northwind.example', text)
        picks = text.split('Reply with one of:')[1]
        for w in ('Send', 'Edit', "Don't send", 'Next'): self.assertIn(f'· {w}\n' if w != 'Next' else f'· {w}', picks)

    def test_send_and_edit_press_the_desks_own_door(self):
        from taskuary import server
        with mock.patch.object(server, 'decide', return_value={'ok': True, 'status': 'approved'}) as door:
            said = ra.run_act(self.s, {'t': 'card', 'rid': self.rid, 'verb': 'approve'}, self.item)
        self.assertEqual((door.call_args.args[0], door.call_args.args[1].verb), (self.rid, 'approve'))
        self.assertIn('Sent the email to', said)
        with mock.patch.object(server, 'decide', return_value={'ok': True}) as door:
            out = ra.press_card(self.s, self.rid, 'edit', 'Hi Gail, the pack is attached - page 3 has the chart.')
        self.assertEqual((door.call_args.args[1].verb, door.call_args.args[1].final_text), ('edit', 'Hi Gail, the pack is attached - page 3 has the chart.'))
        self.assertIn('with your words', out)

    def test_approve_named_off_the_table_is_the_press_of_its_waiting_card(self):
        """Walk 9 (42): "approve the next card" on the phone, the email to Gail waiting on a task that was not on the table and whose row
        carried no review id - approve found "nothing to approve", so the yes went to the agent as a typed line, which greyed the very card
        he approved. Approve on a task is the press of its front card (cardqueue.front), through the desk's door (review.approve -> decide)."""
        from taskuary import cardqueue, concierge, general
        self.assertEqual(cardqueue.front(self.s, self.tid).get('ReviewId'), self.rid)
        dock = general.dock_task(self.s, 'owner-whatsapp')[0]['TaskId']
        prop = concierge.propose_for(self.s, dock, {'verb': 'approve'}, self.item, 'approve the email to Gail', elsewhere=True, table={'ref': 'TQ-0099'})
        self.assertEqual((prop['kind'], prop['target']), ('review.approve', self.rid))

    def test_a_failed_send_says_why_and_nothing_is_said_sent(self):
        from taskuary import server
        with mock.patch.object(server, 'decide', return_value={'ok': True, 'status': 'pending', 'send_error': 'No mailbox is connected'}):
            said = ra.press_card(self.s, self.rid, 'approve')
        self.assertIn('Not sent - No mailbox is connected', said)
        self.assertNotIn('Sent the', said)


if __name__ == '__main__':
    unittest.main()
