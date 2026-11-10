"""The owner's own line decides whether a reply is owed, and the header says what the agent is really doing (2026-11-09).

The shape: a coding task off a group chat. The agent drafted the sender a reply, then the owner typed "is the code updated - no need to reply"
and "is it on master". The draft stood with its Send under the newest turn, and the header read "agent working" over a turn that had ended on
the owner's question - the full suite was still running in a background shell. Invented people only.
"""
import json, unittest
from unittest import mock

from taskuary import agenttools, general, terminal as term, verdicts, wrapup, workerstate as ws
import taskuary
from tests.test_hooks_events import Base
from tests.test_thread_change_replans import drafted_task, store

REP = {'determination': 'the link was dropped when the mail was read', 'actions': 'kept every link in the mail text', 'result': 'fixed'}


class OwnerSaysNoReply(unittest.TestCase):
    def tearDown(self): general.OPENING.clear()

    def test_the_agent_is_told_the_owners_line_decides_and_how_to_put_the_draft_down(self):
        line = general.action_line(store())
        self.assertIn("THE OWNER'S OWN WORDS DECIDE WHETHER A REPLY IS OWED", line)
        self.assertIn('reply_not_needed', line); self.assertIn('--reply-not-needed', line)
        from pathlib import Path
        coding = (Path(taskuary.__file__).parent / 'templates' / 'coding.md').read_text(encoding='utf-8')
        self.assertIn("in any words, no reply is needed", coding); self.assertIn('--reply-not-needed', coding)

    def test_through_the_tool_the_waiting_draft_is_retired_and_the_sessions_end_drafts_none(self):
        s = store(); tid, rid = drafted_task(s)
        self.assertEqual([d['review'] for d in general.draft_turns(s, tid)], [rid])
        doors = {'not_needed': lambda t, why: verdicts.not_needed(s, t, why, 'coding')}
        got = json.loads(agenttools.call(s, tid, 'reply_not_needed', {'why': 'Alex said no reply is needed'}, doors))
        self.assertTrue(got['ok'])
        rv = s.get_review(rid)
        self.assertEqual(rv['Status'], 'closed_unsent'); self.assertEqual(rv['NotNeeded'], 'Alex said no reply is needed')
        self.assertEqual(general.draft_turns(s, tid), [])                       # no card left to draw, on any turn
        # ...and the session ending is no new draft in its place: the report's reply would have stood with Send again
        with mock.patch.object(wrapup, 'freshen', side_effect=AssertionError('no reply to refresh')), \
             mock.patch('taskuary.responder.write_draft', side_effect=AssertionError('nothing to draft')):
            out = wrapup.finish(s, tid, REP, None, 'coding')
        self.assertFalse(out['drafting'])
        self.assertIsNone(s.pending_review(tid, 'draft_reply', live_only=False)); self.assertIsNone(s.pending_review(tid, 'draft', live_only=False))
        self.assertTrue(any('put down as not needed' in str(c.get('Body')) for c in s.list_comments(tid)))

    def test_a_new_mail_after_the_put_down_is_owed_an_answer_again(self):
        s = store(); tid, rid = drafted_task(s)
        verdicts.not_needed(s, tid, 'Alex said no reply is needed', 'coding')
        mid = s.list_messages(tid)[0]['MessageId']
        self.assertTrue(wrapup.put_down(s, tid, mid))
        s._exec("UPDATE message SET CreatedAt='2999-01-01 00:00:00' WHERE MessageId=?", (mid,))     # it came in after the put-down
        self.assertEqual(wrapup.put_down(s, tid, mid), '')


class HeaderReadsTheTurn(Base):
    """A turn whose shell is still running reads working, whatever its last words were - nothing reads the prose for a question (the
    owner, 2026-11-10). One the agent ASKED outranks the running work (bb7df739): the Stop's `background` line is no newer word."""
    def ended(self, said):
        t = self.session()
        ws.record(self.s, self.tid, 'run1', 'turn_end', text=said, source='hook')
        ws.record(self.s, self.tid, 'run1', 'background', text='1 shell still running',
                  choices=[{'id': 'b1', 'kind': 'shell', 'what': 'Run the full suite', 'until': None}], source='hook')
        return t

    def test_a_question_it_asked_with_the_suite_still_running_is_not_working(self):
        t = self.ended('It is on your local master only.')
        self.assertIs(ws.waiting_of(self.s, t), False)                          # the work in the shell reads working
        ws.record(self.s, self.tid, 'run1', 'input_needed', text='Rebase and push?', source='api')
        self.assertIs(ws.waiting_of(self.s, t), True)
        self.assertTrue(term.worker_fields(self.s, t)['waiting'])
        from taskuary import taskstate
        self.assertNotEqual(taskstate.state(self.s, self.s.get_task(self.tid), {'alive': True, **term.worker_fields(self.s, t)}), 'working')

    def test_a_turn_that_asked_nothing_reads_working_while_its_shell_runs_whatever_its_prose(self):
        t = self.ended('The suite is still running. Should I commit once it passes?')
        self.assertIs(ws.waiting_of(self.s, t), False)


if __name__ == '__main__':
    unittest.main()
