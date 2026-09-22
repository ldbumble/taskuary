"""A meeting invitation is a meeting to be ready for, not a job to do.

ingest has said so for a long time - an invite short-circuits to `fyi` before any AI call, because
the calendar already carries the meeting and the assistant preps it. The rule never ran: Graph types
an invitation `#microsoft.graph.eventMessageRequest`, and the check looked for a type ENDING in
"eventmessage", which that does not. So a Teams invitation for the monthly directors meeting went to
triage as ordinary mail, cost an AI call, and came back as TQ-0520 "Attend monthly directors
meeting" - an open task on the owner's list for a meeting that was already on his calendar
(2026-09-14: "it was a invite which should be in the future not a task").

Pinned here: the whole road, from what Graph actually sends to what lands on the Timeline.
"""
import unittest
from unittest import mock

from taskuary import ingest
from taskuary.counsel import is_invite
from taskuary.store import MemoryStore

# The exact shape Graph returned for the invitation that became TQ-0520, with the fields our own
# mail poll asks for (meetingMessageType is NOT among them - it belongs to the derived type and
# Graph refuses a poll that names it).
TEAMS_INVITE = {'@odata.type': '#microsoft.graph.eventMessageRequest', 'id': 'graph-inv-1',
                'subject': 'Monthly Directors Meeting',
                'bodyPreview': 'Microsoft Teams Need help? Join the meeting now Meeting ID: 255 960 655 751'}


def arrive(store, invite: bool, llm=None):
    """One mail landing, exactly as channels hands it over."""
    return ingest.ingest_message(store, {
        'external_id': 'graph:inv-1', 'channel': 'email', 'subject': TEAMS_INVITE['subject'],
        'body': TEAMS_INVITE['bodyPreview'], 'from_name': 'Gail Moreno', 'from_email': 'gmoreno@example.test',
        'to': ['owner@example.test'], 'source_name': 'owner@example.test', 'sent_at': '2026-09-14 10:59:47',
        'invite': invite}, llm=llm)


class TheFlagGetsThereTests(unittest.TestCase):
    def test_what_graph_sends_for_an_invitation_reads_as_one(self):
        self.assertTrue(is_invite(TEAMS_INVITE))

    def test_an_accept_or_a_decline_is_meeting_mail_too(self):
        self.assertTrue(is_invite({'@odata.type': '#microsoft.graph.eventMessageResponse', 'subject': 'Monthly Directors Meeting'}))


class TheRuleRunsTests(unittest.TestCase):
    def test_an_invite_files_itself_and_never_reaches_the_brain(self):
        store = MemoryStore()
        brain = mock.Mock(side_effect=AssertionError('an invite must not cost an AI call'))
        out = arrive(store, invite=True, llm=brain)
        self.assertEqual(out['status'], 'filed', 'it lands on the Timeline rather than opening work')
        self.assertIsNone(out.get('task_id'), 'a meeting on the calendar is not a task on the list')
        self.assertFalse(brain.called)
        self.assertEqual(store.get_message(out['message_id'])['Status'], 'filed')
        # ...and the record says WHY, in the words the owner would use
        said = ' '.join(str(r.get('Reason') or '') for r in store._rows(
            'SELECT * FROM route WHERE MessageId=?', (out['message_id'],)))
        self.assertIn('calendar invite', said)
        self.assertIn('not work', said)

    def test_the_same_mail_without_the_flag_is_ordinary_work_again(self):
        """The guard is the flag, not the words - so this fails loudly if the wiring is ever cut."""
        store = MemoryStore()
        out = arrive(store, invite=False, llm=None)
        said = ' '.join(str(r.get('Reason') or '') for r in store._rows(
            'SELECT * FROM route WHERE MessageId=?', (out['message_id'],)))
        self.assertNotIn('calendar invite', said)


if __name__ == '__main__':
    unittest.main()
