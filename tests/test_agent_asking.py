"""One reading of whether an agent is asking (A15), and a regular agent's question reaches you (A9) - the owner,
2026-09-25, on the agent lifecycle map."""
import types, unittest

from taskuary import funnel, general, workerstate as ws
from taskuary.store import MemoryStore


class RailReadsTheSessionTests(unittest.TestCase):
    def test_the_sessions_own_state_decides_not_a_question_mark_on_screen(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        live = [{'taskId': t, 'agent': 'coder', 'sid': 's1', 'waiting': True, 'state': 'parked',
                 'line': 'coder is waiting on you', 'tail': ['Shall I also fix the import?']}]
        card = funnel.from_agents(s, live_state=live)[0]
        self.assertFalse(card['asking'])
        self.assertEqual(card['why'], 'coder is waiting on you')


class RegularAgentQuestionTests(unittest.TestCase):
    def test_its_question_and_choices_are_the_sessions_request(self):
        s = MemoryStore()
        t = s.create_task({'Title': 'Draft the vendor letter', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        ws.record(s, t, 'g1', 'input_needed', request_id='r1', text='Which letterhead?', choices=['Old', 'New'], source='api')
        fake = types.SimpleNamespace(store=s, task_id=t, sid='g1', label='assistant', agent='assistant', mode='chat', alive=True,
                                     busy=False, started='', provider='p', model='m', pick='p', resume_notice=None, cli_sid=None,
                                     waiting=lambda: True, idle=lambda: 5, phase=lambda: 'parked', tail=lambda n=3: ['Which letterhead?'])
        info = general.GeneralSession.info(fake, details=False)
        self.assertEqual((info['request'] or {}).get('choices'), ['Old', 'New'])
        self.assertEqual(info['state'], 'asking')
        self.assertIn('Which letterhead?', info['line'])


if __name__ == '__main__': unittest.main()


class OneLaneRuleTests(unittest.TestCase):
    """A16: All and the rail read one rule from the same facts; A10: a regular-agent task nobody started waits to start."""

    def test_the_shared_facts(self):
        from taskuary import terminal
        self.assertEqual(funnel.left_by_facts(terminal.SAVED, []), 'saved')
        self.assertEqual(funnel.left_by_facts('', [{'Status': 'stopped'}]), 'stopped')
        self.assertEqual(funnel.left_by_facts(terminal.INTERRUPTED, []), 'stopped')
        self.assertEqual(funnel.left_by_facts('', [{'Status': 'done'}]), '')

    def test_all_says_what_the_rail_says(self):
        from taskuary.processing_all import row_lane
        base = {'TaskStatus': 'open', 'Assignee': 'agent:coder'}
        self.assertEqual(row_lane({**base, 'AgentLeft': 'stopped'}), 'stopped')
        self.assertEqual(row_lane({**base, 'AgentLeft': 'saved'}), 'saved')
        self.assertEqual(row_lane(base), 'queued')
        self.assertEqual(row_lane({'TaskStatus': 'open', 'GeneralNotStarted': True}), 'queued')

    def test_a_regular_agent_task_nobody_started_waits_to_start_on_the_rail(self):
        from unittest import mock
        from taskuary import processing_unread
        from test_funnel import ago
        s = MemoryStore()
        t = s.create_task({'Title': 'Draft the vendor letter', 'Kind': 'general', 'Status': 'open'}, 'triage')
        s.add_message({'TaskId': t, 'ExternalId': 'g1', 'Channel': 'email', 'Subject': 'Vendor letter', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'SentAt': ago(1), 'BodyText': 'Can you draft it?', 'Status': 'routed'})
        m = s._rows('SELECT MessageId FROM message WHERE TaskId=?', (t,))[0]['MessageId']
        s.add_route(m, t, 'route', 1.0, f'triage: task - {funnel.AUTO_OFF} general auto-start is off', [], 'triage')
        s.reconcile_processing_membership(fixed_now=ago(0)); funnel.invalidate()
        with mock.patch('taskuary.terminal.live_sessions', return_value=[]):
            lanes = [i['lane'] for i in processing_unread.build(s, live_state=[], include_read=True)['items'] if i.get('tid') == t]
        self.assertEqual(lanes, ['queued'])


class AgentFinishedTests(unittest.TestCase):
    """A17: one "agent finished". Whoever edited the task last owns the close (the owner, 2026-09-25)."""

    def _done(self, s, note, actor='coder'):
        t = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'o')
        s.add_comment(t, actor, 'agent', note)
        s.update_task(t, {'Status': 'done'}, actor)
        return t

    def test_the_agent_closing_it_keeps_its_result_with_no_time_limit(self):
        from taskuary.processing_unread import finish_evidence
        s = MemoryStore(); t = self._done(s, 'The agent closed this itself: the export is fixed.')
        s.add_comment(t, 'Taskuary', 'system', 'coder finished TQ-0001.')          # notes a day later change nothing
        self.assertEqual(finish_evidence(s, t)['summary'], 'the export is fixed.')

    def test_whoever_edited_it_last_owns_it(self):
        # the agent finished and drafted a reply; the owner's send closed the task seconds later (TQ-0726, TQ-0734)
        from taskuary.processing_unread import finish_evidence
        s = MemoryStore(); t = self._done(s, 'The agent closed this itself: the export is fixed.')
        s.add_comment(t, 'owner', 'human', 'Closed - the reply went out.')
        s.update_task(t, {'Status': 'done'}, 'owner')
        self.assertIsNone(finish_evidence(s, t))

    def test_a_merged_pull_request_is_credited_to_the_pull_request(self):
        from taskuary.processing_unread import finish_evidence
        s = MemoryStore()
        t = self._done(s, 'The pull request this task came from was merged on GitHub (northwind/ledger#12), so there is nothing left to do here.', 'router')
        self.assertEqual(finish_evidence(s, t)['who'], 'Its pull request')

    def test_the_owner_closing_it_is_not_an_agent_finish(self):
        from taskuary.processing_unread import finish_evidence
        s = MemoryStore(); t = self._done(s, 'Marked done.', 'owner')
        self.assertIsNone(finish_evidence(s, t))
