"""Preparing for a meeting is a conversation, not a coding session.

"Prepare me for it" on a Timeline invite used to create a `coding` task tagged repo:none and open
a CLI in the agent's own folder. There is no checkout to work in - it is reading, checking and
thinking - so it opens the assistant's chat instead, the same way the Board and + New do.
"""
import unittest
from fastapi.testclient import TestClient

from taskuary import server

c = TestClient(server.app)
EVENT = {'subject': 'Reimbursement app review', 'start': '2026-09-02T13:00:00',
         'end': '2026-09-02T14:00:00', 'where': 'Teams', 'organizer': 'dana@ours.com',
         'who': ['dana@ours.com'], 'about': 'MFA and Viventium ESS link'}


class PrepOpensTheChat(unittest.TestCase):
    def _prep(self, **extra):
        r = c.post('/api/calendar/prep', json={**EVENT, **extra})
        self.assertEqual(r.status_code, 200, r.text)
        d = r.json()
        return d, c.get(f"/api/tasks/{d['taskId']}").json()

    def test_it_is_a_general_task_carrying_the_ask_tag(self):
        d, t = self._prep(instruction='Pull last month for these facilities.')
        task = t.get('task', t)
        self.assertEqual(task['Kind'], 'general')          # -> GeneralWorkspace, not a terminal
        self.assertIn('ask:assistant', task.get('Tags') or '')
        self.assertTrue(d.get('chat'))

    def test_no_session_is_started(self):
        """The chat opens its own session when the owner lands on it - nothing spawns a pty here."""
        d, _ = self._prep()
        self.assertIsNone(d.get('session'))

    def test_the_owners_words_lead_and_the_invite_follows(self):
        d, t = self._prep(instruction='Give me three questions to ask.')
        summary = (t.get('task', t))['Summary']
        self.assertTrue(summary.startswith('Give me three questions to ask.'))
        self.assertIn('Reimbursement app review', summary)   # the invite is the context under it

    def test_with_no_instruction_it_still_asks_something(self):
        _, t = self._prep()
        self.assertIn('Get me ready', (t.get('task', t))['Summary'])

    def test_the_prep_row_belongs_to_the_invite(self):
        """Not a separate line an hour down the rail: the row carries the event's own key, which
        is how the Timeline draws it UNDER the meeting instead of beside it."""
        d, _ = self._prep()
        msgs = server.store.list_messages(d['taskId'])
        self.assertEqual(len(msgs), 1)
        self.assertEqual(msgs[0]['ConversationId'], server.prep_key(EVENT['start'], EVENT['subject']))
        self.assertEqual(msgs[0]['Channel'], 'own')

    def test_the_key_is_built_the_same_way_from_either_end(self):
        """FeedView.evKey builds this string from the event it is drawing. If they drift the prep
        floats loose again, so the shape is pinned here."""
        self.assertEqual(server.prep_key('2026-09-02T13:00:00', '  Review  '),
                         'calendar:2026-09-02T13:00:00:Review')
        self.assertEqual(server.prep_key(None, None), 'calendar::the meeting')

    def test_the_prep_row_cannot_be_replied_to(self):
        """It is on channel own - nobody sent it, so nothing drafts an answer to nobody."""
        from taskuary.outbound import can_reply
        self.assertFalse(can_reply(server.store, 'own'))

    def test_an_old_page_posting_an_agent_still_works(self):
        """The agent/model fields stayed on the body so a tab loaded before the switch does not 422."""
        r = c.post('/api/calendar/prep', json={**EVENT, 'agent': 'coder', 'model': 'whatever'})
        self.assertEqual(r.status_code, 200, r.text)


if __name__ == '__main__':
    unittest.main()
