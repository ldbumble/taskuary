"""New work on a task whose assistant has stopped carries THAT conversation on - not a new agent, not nothing (2026-10-28).

The shape that pinned it: a colleague asks for something in a chat, the assistant works it and finishes, and the same person
then asks for more on the same task, over and over. Every line reopened and retitled the task, and the finished conversation
never heard any of it until the owner pressed Continue. Now the new line is the stopped conversation's next turn - only where a
fresh task would have started its agent by itself, never over a live session, and never for a question (that is a drafted reply).
"""
import json, unittest
from unittest import mock

from taskuary import continuity, general, ingest, senders
from taskuary.ingest import ingest_message
from taskuary.store import MemoryStore


def llm_says(intent='task', **extra):
    return lambda sy, u, **k: json.dumps({'intent': intent, 'kind': 'general', 'why': 'w', 'asks_owner': True, **extra})


def mail(**kw):
    base = {'external_id': 'x1', 'channel': 'email', 'subject': 'pilot plan', 'body': 'Can you draft a pilot plan for the new box?',
            'from_email': 'erin@northwind.example', 'from_name': 'Erin Blake', 'conversation_id': 'AAQk-pilot',
            'sent_at': '2026-10-27 18:00', 'source_name': 'alex@northwind.example'}
    return {**base, **kw}


def store(**settings):
    s = MemoryStore()
    s.set_setting('owner_email', 'alex@northwind.example', 't')
    for k, v in settings.items(): s.set_setting(k, v, 't')
    return s


def ingested(s, m, intent='task'):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=True), \
         mock.patch.object(general, 'provider_options', return_value=[{'pick': 'cli:claude', 'type': 'cli'}]):
        out = ingest_message(s, m, llm=llm_says(intent))
    return out, [getattr(c[0][0], '__name__', '') for c in spawn.call_args_list]


def finished_task(s):
    """A general task its assistant worked and finished: a conversation on it, the task closed."""
    out, spawned = ingested(s, mail())
    assert spawned == ['_auto_general'], spawned
    tid = out['task_id']
    s.add_comment(tid, 'owner', general.USER_TYPE, 'Can you draft a pilot plan for the new box?')
    s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Wrote the pilot plan and drafted a reply.')
    s.update_task(tid, {'Status': 'done'}, 't')
    return tid


AGAIN = dict(external_id='x2', body='Also - can you price the second site the same way?', sent_at='2026-10-28 10:00')


class CarryOnTests(unittest.TestCase):
    def test_new_work_carries_the_stopped_conversation_on(self):
        s = store(); tid = finished_task(s)
        out, spawned = ingested(s, mail(**AGAIN))
        self.assertEqual(out['task_id'], tid)
        self.assertEqual(spawned, ['_continue_general'])                     # the same conversation - no _auto_general, no second agent
        self.assertNotEqual(s.get_task(tid)['Status'], 'done')
        self.assertTrue(any('carries on its conversation here by itself' in c['Body'] for c in s.list_comments(tid)))
        self.assertTrue(any(a['Action'] == 'auto_continue' for a in s._rows('SELECT * FROM audit WHERE EntityId=?', (str(tid),))))
        self.assertIn(tid, general.OPENING); general.OPENING.discard(tid)

    def test_not_when_the_owner_switched_unattended_starts_off(self):
        s = store(); tid = finished_task(s)
        s.set_setting('general_auto_enabled', '0', 't')
        _out, spawned = ingested(s, mail(**AGAIN))
        self.assertEqual(spawned, [])
        self.assertTrue(ingest.carry_on_why(s, tid, mail(**AGAIN), None, {'intent': 'task'}))

    def test_a_question_is_a_drafted_reply_not_a_turn(self):
        s = store(); finished_task(s)
        _out, spawned = ingested(s, mail(**{**AGAIN, 'body': 'Did you get my last note?'}), intent='reply_only')
        self.assertNotIn('_continue_general', spawned)
        self.assertIn('_auto_draft', spawned)

    def test_never_over_a_live_session(self):
        s = store(); tid = finished_task(s)
        with mock.patch.object(general, 'session_for', return_value=object()):
            _out, spawned = ingested(s, mail(**AGAIN))
        self.assertNotIn('_continue_general', spawned)

    def test_a_task_with_no_conversation_is_not_carried_on(self):
        s = store()
        out, _ = ingested(s, mail())
        s.update_task(out['task_id'], {'Status': 'done'}, 't')
        _out, spawned = ingested(s, mail(**AGAIN))
        self.assertEqual(spawned, [])

    def test_a_coding_task_waits_for_the_owners_continue(self):
        s = store(); tid = finished_task(s)
        s.update_task(tid, {'Kind': 'coding'}, 't')
        self.assertEqual(ingest.carry_on_why(s, tid, mail(**AGAIN), None, {'intent': 'task'}), "not the assistant's task")

    def test_the_turn_is_continue_told_what_came_in(self):
        s = store(); tid = finished_task(s)
        ses = mock.Mock()
        with mock.patch.object(general, 'start_session', return_value=ses) as start, \
             mock.patch.object(continuity, 'news_block', return_value='NEW SINCE YOUR LAST TURN: one message'):
            general.OPENING.add(tid)
            ingest._continue_general(s, tid)
        self.assertEqual(start.call_args.kwargs.get('actor'), 'router')
        args, kw = ses.send_prompt.call_args
        self.assertEqual(args[0], continuity.RESUME_PROMPT)
        self.assertEqual((kw['as_owner'], kw['delivery_instructions']), (False, 'NEW SINCE YOUR LAST TURN: one message'))
        self.assertNotIn(tid, general.OPENING)


if __name__ == '__main__': unittest.main()
