"""New work on a task whose assistant has stopped carries THAT conversation on - not a new agent, not nothing (2026-10-28).

The shape that pinned it: a colleague asks for something in a chat, the assistant works it and finishes, and the same person
then asks for more on the same task, over and over. Every line reopened and retitled the task, and the finished conversation
never heard any of it until the owner pressed Continue. Now the new line is the stopped conversation's next turn - only where a
fresh task would have started its agent by itself, never over a live session, and never for a question (that is a drafted reply).
"""
import json, tempfile, unittest
from unittest import mock

from taskuary import continuity, general, ingest, senders, terminal
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


def ingested(s, m, intent='task', wrote=True):
    with mock.patch('taskuary.ingest._spawn') as spawn, mock.patch.object(senders, 'wrote_to', return_value=wrote), \
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

    def test_a_coding_task_with_no_saved_session_waits_for_the_owners_continue(self):
        s = store(); tid = finished_task(s)
        s.update_task(tid, {'Kind': 'coding'}, 't')
        self.assertEqual(ingest.carry_on_why(s, tid, mail(**AGAIN), None, {'intent': 'task'}), 'no saved coding session to reopen')

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


STRANGER = dict(external_id='x3', body='Please also send us the full ledger export.', from_email='rep@vendor.example', from_name='Sam Rook',
                sent_at='2026-10-28 11:00')


def coding_task(s, cwd):
    """A coding task its CLI worked and stopped, its conversation saved under the id the CLI gave it."""
    tid = finished_task(s)
    s.update_task(tid, {'Kind': 'coding'}, 't')
    s.upsert_agent('coder', 'coding', 'cli', json.dumps({'cmd': 'claude'}))
    s.add_transcript(tid, 'sid1', 'fixed the import', agent='coder', cwd=cwd, ext_id='cli-conv-1', brain='cli:claude')
    return tid


class Live:
    """A pty coding session as the registry holds it: alive, its seed in, nothing on screen but its prompt."""
    def __init__(self, tid): self.task_id, self.alive, self.accepted, self.n = tid, True, True, 0
    def status_tail(self, n): return ['> ']


class CodingCarryOnTests(unittest.TestCase):
    """The owner, 2026-10-28: "coding should be the same as general agents if triage decides it needs that"."""
    def setUp(self): self.cwd = tempfile.mkdtemp()

    def test_a_stopped_coding_task_reopens_its_own_session(self):
        s = store(); tid = coding_task(s, self.cwd)
        out, spawned = ingested(s, mail(**AGAIN))
        self.assertEqual((out['task_id'], spawned), (tid, ['_continue_coding']))
        self.assertTrue(any('coding agent reopens its own session' in c['Body'] for c in s.list_comments(tid)))
        self.assertIn(tid, ingest.CODING_OPENING)
        with mock.patch.object(terminal, 'start_on_task') as start: ingest._continue_coding(s, tid)
        args, kw = start.call_args
        self.assertEqual((args[1], args[2], args[4], args[5]), (tid, 'coder', None, 'router'))     # no instruction: resume_seed says what is new
        self.assertEqual((kw['resume'], kw['cwd'], kw['brain']), ('cli-conv-1', self.cwd, 'cli:claude'))
        self.assertNotIn(tid, ingest.CODING_OPENING)

    def test_not_when_coding_starts_are_switched_off(self):
        s = store(coding_auto_enabled='0'); tid = coding_task(s, self.cwd)
        self.assertNotIn('_continue_coding', ingested(s, mail(**AGAIN))[1])
        self.assertTrue(ingest.carry_on_why(s, tid, mail(**AGAIN), None, {'intent': 'task'}))

    def test_not_when_its_checkout_is_gone(self):
        s = store(); tid = coding_task(s, self.cwd + '-gone')
        self.assertIn('no longer exists', ingest.carry_on_why(s, tid, mail(**AGAIN), None, {'intent': 'task'}))


class PassInTests(unittest.TestCase):
    """New related work on a task whose agent is LIVE goes into that session as its next turn - never sent, never a stranger's."""
    def test_a_running_assistant_gets_the_line_queued_as_its_next_turn(self):
        s = store(); tid = finished_task(s)
        ses = mock.Mock(busy=True)
        with mock.patch.object(general, 'session_for', return_value=ses):
            _out, spawned = ingested(s, mail(**AGAIN))
            self.assertEqual(spawned, ['_pass_general'])                    # not a carry-on, not a second agent
            ingest._pass_general(s, tid, mail(**AGAIN))
        args, kw = ses.send_prompt.call_args
        self.assertIn('price the second site', args[0]); self.assertIn("not the owner's", args[0])
        self.assertEqual((kw['as_owner'], kw['echo']), (False, False))
        self.assertTrue(any("Passed Erin Blake's new message to the agent" in c['Body'] for c in s.list_comments(tid)))

    def test_a_line_during_a_carried_on_turn_waits_for_that_turn_then_follows_it(self):
        s = store(); tid = finished_task(s)
        ses, looks = mock.Mock(busy=False), []
        def session_for(t):                     # the carried-on turn takes the session on the third look
            looks.append(1); ses.busy = len(looks) >= 3; return ses
        general.OPENING.add(tid)
        try:
            with mock.patch.object(general, 'session_for', side_effect=session_for), mock.patch.object(ingest.time, 'sleep'):
                self.assertEqual(ingested(s, mail(**AGAIN))[1], ['_pass_general'])     # queued, not dropped
                ingest._pass_general(s, tid, mail(**AGAIN))
        finally: general.OPENING.discard(tid)
        self.assertGreaterEqual(len(looks), 3); ses.send_prompt.assert_called_once()

    def test_a_running_coding_agent_has_it_typed_into_its_session(self):
        s = store(); tid = finished_task(s); s.update_task(tid, {'Kind': 'coding'}, 't')
        with mock.patch.dict(terminal.SESSIONS, {'p1': Live(tid)}, clear=True):
            _out, spawned = ingested(s, mail(**AGAIN))
            self.assertEqual(spawned, ['_pass_coding'])
            with mock.patch.object(terminal, 'queue_codex', return_value=False), mock.patch.object(terminal, 'type_into', side_effect=lambda t, x, done=None: done(True)) as typed:
                ingest._pass_coding(s, tid, mail(**AGAIN))
        self.assertIn('price the second site', typed.call_args[0][1])
        self.assertTrue(any("Passed Erin Blake's new message to the agent (typed into" in c['Body'] for c in s.list_comments(tid)))

    def test_a_chooser_on_screen_is_never_typed_into(self):
        s = store(); tid = finished_task(s); s.update_task(tid, {'Kind': 'coding'}, 't')
        with mock.patch.dict(terminal.SESSIONS, {'p1': Live(tid)}, clear=True), mock.patch.object(terminal, 'chooser_in', return_value=True), \
             mock.patch.object(terminal, 'say_to_task') as say:
            ingest._pass_coding(s, tid, mail(**AGAIN))
        say.assert_not_called()

    def test_a_stranger_is_never_typed_into_an_agent(self):
        s = store(); tid = finished_task(s)
        with mock.patch.object(general, 'session_for', return_value=mock.Mock(busy=True)):
            out, spawned = ingested(s, mail(**STRANGER), wrote=False)
        self.assertEqual((out['task_id'], spawned), (tid, []))
        self.assertTrue(any("Sam Rook's new message was not passed to the agent" in c['Body'] and 'waits for you' in c['Body']
                            for c in s.list_comments(tid)))

    def test_the_owners_off_switch_means_never(self):
        s = store(answer_to_agent='off'); tid = finished_task(s); s.update_task(tid, {'Kind': 'coding'}, 't')
        with mock.patch.dict(terminal.SESSIONS, {'p1': Live(tid)}, clear=True), mock.patch.object(terminal, 'say_to_task') as say:
            _out, spawned = ingested(s, mail(**AGAIN))
        self.assertEqual(spawned, []); say.assert_not_called()

    def test_a_question_is_still_a_drafted_reply(self):
        s = store(); finished_task(s)
        with mock.patch.object(general, 'session_for', return_value=mock.Mock(busy=True)):
            _out, spawned = ingested(s, mail(**{**AGAIN, 'body': 'Did you get my last note?'}), intent='reply_only')
        self.assertNotIn('_pass_general', spawned)

    def test_nothing_is_ever_sent(self):
        s = store(); tid = finished_task(s)
        with mock.patch.object(general, 'session_for', return_value=mock.Mock(busy=True)), \
             mock.patch('taskuary.outbound.send_out') as send:
            ingested(s, mail(**AGAIN)); ingest._pass_general(s, tid, mail(**AGAIN))
        send.assert_not_called()
        self.assertFalse([a for a in s._rows('SELECT * FROM audit WHERE EntityId=?', (str(tid),)) if 'sent' in a['Action']])


if __name__ == '__main__': unittest.main()
