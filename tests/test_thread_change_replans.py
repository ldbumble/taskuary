"""Anything that changes on a task's thread wakes its agent, which re-plans the WHOLE next step (Task 4.5, the owner 2026-11-04).

The shape that pinned it: the owner was asked a question and a reply was drafted; a colleague on the thread answered it themselves,
triage read that as an fyi, and the drafted reply kept sitting there "ready to send" - nobody told the agent. Now every line that
joins a task with an agent conversation (or a pending reply) is that agent's next turn: what changed, in the sender's words, and
the question of what is left - which may be no reply at all. The agent can mark the draft not needed; it is never deleted, never
sent and the task never closed by it.
"""
import json, unittest
from unittest import mock

from taskuary import channels, general, ingest, senders, verdicts
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore

ANSWERED = {'asking': 'Erin Blake asks when the pilot box ships', 'your_part': '', 'others': [{'who': 'Gail Moreno', 'did': 'answered: it ships Friday'}],
            'asks': [], 'aside': [], 'on_you': []}


def llm_says(intent='task', **extra):
    return lambda sy, u, **k: json.dumps({'intent': intent, 'kind': 'general', 'why': 'w', 'asks_owner': True, **extra})


def mail(**kw):
    base = {'external_id': 'x1', 'channel': 'email', 'subject': 'pilot box', 'body': 'Alex, when does the pilot box ship?',
            'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake', 'conversation_id': 'AAQk-pilot',
            'sent_at': '2026-11-03 09:00', 'source_name': 'alex@northwind.example'}
    return {**base, **kw}


GAIL = dict(external_id='x2', body='Erin - it ships Friday, I booked the courier.', from_email='gail@northwind.example', from_name='Gail Moreno',
            sent_at='2026-11-03 10:00')


def store():
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    return s


def ingested(s, m, intent='task', **extra):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest_message(s, m, llm=llm_says(intent, **extra))
    return out, spawn.call_args_list


def names(calls): return [getattr(c[0][0], '__name__', '') for c in calls]


def drafted_task(s):
    """A general task its assistant worked: a conversation on it, and the reply it drafted waiting for the owner's Send."""
    out, calls = ingested(s, mail())
    tid = out['task_id']
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Can you answer Erin?')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Drafted a reply: it ships next week.')
    mid = s.list_messages(tid)[0]['MessageId']
    rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft', 'Status': 'pending', 'DraftText': 'Hi Erin - it ships next week.'})
    general.OPENING.discard(tid)
    return tid, rid


class ThreadChangeReplans(unittest.TestCase):
    def tearDown(self): general.OPENING.clear()

    def test_someone_else_answering_wakes_the_agent_once_with_the_change(self):
        s = store(); tid, rid = drafted_task(s)
        out, calls = ingested(s, mail(**GAIL), intent='fyi', thread=ANSWERED)
        self.assertEqual((out['task_id'], names(calls)), (tid, ['_replan_general']))
        turn = calls[0][0][-1]
        self.assertIn('Gail Moreno', turn); self.assertIn('it ships Friday, I booked the courier', turn)
        self.assertIn('Gail Moreno - answered: it ships Friday', turn)                    # triage's reading rides with it
        self.assertIn('WHOLE next step', turn); self.assertIn('--reply-not-needed', turn); self.assertIn('TASKUARY-SUMMARY', turn)
        self.assertIn(tid, general.OPENING)
        # the stand-in agent decides no reply is needed: the draft is put down - kept under Not sent, no card, no Send - and the task stays open
        got = verdicts.not_needed(s, tid, 'Gail Moreno answered this', 'assistant')
        self.assertTrue(got['ok'])
        rv = s.get_review(rid)
        self.assertEqual((rv['Status'], rv['NotNeeded'], rv['DecideNote']), ('closed_unsent', 'Gail Moreno answered this', 'withdrawn - Gail Moreno answered this'))
        self.assertNotIn(s.get_task(tid)['Status'], ('done', 'dropped'))
        self.assertIsNone(s.pending_review(tid, kind='draft'))

    def test_the_owners_own_teams_reply_is_context_for_the_next_turn_never_a_turn(self):
        # a line the owner said in a chat is theirs on the thread, not a prompt (the owner, 2026-11-08): no turn starts, the next one hears it
        s = store(); tid, rid = drafted_task(s)
        s.add_message({'TaskId': tid, 'ExternalId': 'tm-1', 'ConversationId': 'teams-chat-1', 'Channel': 'teams', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'SentAt': '2026-11-03 09:30', 'BodyText': 'pinged you here too', 'Status': 'routed'})
        with mock.patch('taskuary.ingest._spawn') as spawn, \
             mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
            channels.ingest_own_message(s, {'external_id': 'tm-2', 'channel': 'teams', 'conversation_id': 'teams-chat-1',
                                            'from_email': 'alex@northwind.example', 'body': 'Friday - Gail has the courier.',
                                            'sent_at': '2026-11-03 10:05'}, 'your line in the chat')
        self.assertEqual(names(spawn.call_args_list), [])
        s._exec("UPDATE comment SET CreatedAt='2026-11-03 09:00:00' WHERE TaskId=?", (tid,))
        lb = general.latest_block(s, tid)
        self.assertIn('WHAT THE OWNER REPLIED ON THE THREAD THEMSELVES', lb); self.assertIn('on Teams: "Friday - Gail has the courier."', lb)

    def test_a_second_line_while_the_turn_is_live_queues_once(self):
        s = store(); tid, rid = drafted_task(s)
        _out, first = ingested(s, mail(**GAIL), intent='fyi', thread=ANSWERED)
        _out, second = ingested(s, mail(**{**GAIL, 'external_id': 'x3', 'body': 'Thanks Gail!', 'from_name': 'Erin Blake',
                                            'from_email': 'erin@northwind.example', 'sent_at': '2026-11-03 10:10'}), intent='fyi')
        self.assertEqual((names(first), names(second)), (['_replan_general'], ['_replan_pass']))   # queued behind the live turn, no second start

    def test_a_new_question_on_a_finished_agents_task_wakes_it(self):
        # Erin writes again with a question of her own (reply_only, not an aside): the agent re-plans with her words - it was only the
        # tool-less writer that heard it, and the agent's chat never moved
        s = store(); tid, rid = drafted_task(s)
        _out, calls = ingested(s, mail(external_id='x4', body='Also - can it go to the north office instead?', sent_at='2026-11-03 11:00'), intent='reply_only')
        self.assertIn('_replan_general', names(calls))
        self.assertIn('can it go to the north office instead', calls[names(calls).index('_replan_general')][0][-1])

    def test_a_coding_task_is_not_woken(self):
        s = store(); tid, rid = drafted_task(s)
        s.update_task(tid, {'Kind': 'coding'}, 't')
        _out, calls = ingested(s, mail(**GAIL), intent='fyi', thread=ANSWERED)
        self.assertEqual(names(calls), [])

    def test_a_put_down_draft_is_not_marked_twice(self):
        s = store(); tid, rid = drafted_task(s)
        verdicts.not_needed(s, tid, 'Gail Moreno answered this', 'assistant')
        self.assertFalse(verdicts.not_needed(s, tid, 'still answered', 'assistant')['ok'])       # nothing waits any more

    def test_the_agent_marks_it_through_its_tool_or_the_cli(self):
        from taskuary import agenttools, cli, floor
        s = store(); tid, rid = drafted_task(s)
        doors = {'not_needed': lambda t, why: verdicts.not_needed(s, t, why, 'assistant')}
        self.assertTrue(json.loads(agenttools.call(s, tid, 'reply_not_needed', {'why': 'Gail Moreno answered this'}, doors))['ok'])
        self.assertEqual(s.get_review(rid)['NotNeeded'], 'Gail Moreno answered this')
        self.assertIn('--reply-not-needed', floor.TASKUARY_OK); self.assertIn('reply_not_needed', cli.STRANGER_ACTS)

    def test_no_draft_pending_is_said_not_raised(self):
        s = store(); out, _ = ingested(s, mail())
        self.assertFalse(verdicts.not_needed(s, out['task_id'], 'nothing to answer', 'assistant')['ok'])


if __name__ == '__main__': unittest.main()
