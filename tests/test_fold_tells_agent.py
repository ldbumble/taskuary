"""Folding a task into another hands what came over to the survivor's agent as ONE new turn (the owner, 2026-11-09).

The shape: two tasks for one job, each worked by an agent. The owner folds A into B. A's mail moved and its ask was appended, but B's
agent was never told - it kept answering as if A did not exist. Now B's agent gets one turn naming the folded task, with A's mail and A's
agent result (its summary, its draft) as plain text - never A's transcript - and A's draft is dropped, so no Send stands on a dropped task.
"""
import json, os, tempfile, unittest
from unittest import mock

os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp())
from taskuary import general, ingest, reshape
from taskuary.store import MemoryStore, task_ref


def worked(s, title, said, summary=None):
    "A general task its assistant worked and stopped: the owner's line, its answer, and the turn summary filed after it."
    tid = s.create_task({'Title': title, 'Kind': 'general', 'Summary': title}, 'owner')
    s.add_comment(tid, 'owner', general.USER_TYPE, said)
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, f'TRANSCRIPT-OF-{title}: I opened the export and walked through it step by step.')
    if summary: s.add_comment(tid, 'assistant', general.SUMMARY_TYPE, json.dumps(summary))
    return tid


class FoldTellsAgentTests(unittest.TestCase):
    def setUp(self):
        self.s = s = MemoryStore()
        s.set_setting('owner_email', 'alex@northwind.example', 't')
        self.b = worked(s, 'Payworth export for Erin', 'Find why the Payworth export is short.')
        self.a = worked(s, 'Payworth export, again', 'Look at the export Erin sent.',
                        {'did': 'Found the export drops rows with a blank cost center.', 'on_you': ['say whether to backfill'], 'about': 'export'})
        self.mid = s.add_message({'TaskId': self.a, 'Channel': 'email', 'Subject': 'export short', 'FromName': 'Erin Blake',
                                  'FromEmail': 'erin@northwind.example', 'BodyText': 'The March export is missing 14 rows.', 'SentAt': '2026-11-08 09:00'})
        self.rid = s.add_review({'TaskId': self.a, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Hi Erin - the blank cost centers drop out.'})

    def fold(self):
        with mock.patch('taskuary.ingest._spawn') as spawn, \
             mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
            out = reshape.merge_tasks(self.s, self.a, self.b)
        general.OPENING.discard(self.b)
        return out, spawn.call_args_list

    def test_a_stopped_agent_gets_one_turn_with_the_fold(self):
        out, calls = self.fold()
        self.assertTrue(out['agent_told'])
        self.assertEqual([getattr(c[0][0], '__name__', '') for c in calls], ['_replan_general'])      # one turn for the whole fold
        turn = calls[0][0][3]
        self.assertTrue(turn.startswith(f'{general.FOLD_HEAD}{task_ref(self.a)}: Payworth export, again'))
        self.assertIn('The March export is missing 14 rows.', turn)                                    # the moved mail, in its sender's words
        self.assertIn(f'From {task_ref(self.a)} (folded in): its agent last said - Found the export drops rows', turn)
        self.assertIn('say whether to backfill', turn)
        self.assertIn('Hi Erin - the blank cost centers drop out.', turn)                              # its draft, as text
        self.assertNotIn('TRANSCRIPT-OF-Payworth export, again', turn)                                                     # never A's transcript
        self.assertNotIn('TRANSCRIPT-OF-Payworth export, again', ' '.join(c['Body'] for c in self.s.list_comments(self.b, internal=True)))
        self.assertEqual(self.s.get_message(self.mid)['TaskId'], self.b)
        self.assertEqual(self.s.get_review(self.rid)['Status'], 'superseded')                          # no Send left on a dropped task

    def test_the_chat_draws_the_fold_as_an_input_with_the_mail_it_brought(self):
        self.s._exec("UPDATE comment SET CreatedAt='2026-11-08 08:00:00' WHERE TaskId=?", (self.b,))  # B's last turn, before the fold
        _out, calls = self.fold()
        self.s.add_comment(self.b, general.BRIEF_ACTOR, general.USER_TYPE, calls[0][0][3])            # the turn, as send_prompt files it
        fold = [m for m in general.shown_history(self.s, self.b) if m.get('fold')]
        self.assertEqual(len(fold), 1)
        self.assertEqual(fold[0]['fold'], f'Folded in {task_ref(self.a)}: Payworth export, again')
        self.assertEqual([x['who'] for x in fold[0]['mail']], ['Erin Blake'])

    def test_a_held_draft_is_dropped_too(self):
        self.s._exec("UPDATE review SET Status='held' WHERE ReviewId=?", (self.rid,))
        self.fold()
        self.assertEqual(self.s.get_review(self.rid)['Status'], 'superseded')

    def test_no_agent_conversation_starts_nothing(self):
        c = self.s.create_task({'Title': 'fresh', 'Kind': 'general'}, 'owner')
        with mock.patch('taskuary.ingest._spawn') as spawn: out = reshape.merge_tasks(self.s, self.a, c)
        self.assertFalse(out['agent_told']); spawn.assert_not_called()


if __name__ == '__main__': unittest.main()
