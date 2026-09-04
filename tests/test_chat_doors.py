"""Every door that should open a conversation opens the SAME one, and it closes properly.

There are three ways to start a chat and one way to start a coding session, and until now nobody
had walked any of them end to end - the routes were tested for what they CREATE, not for whether
the thing they create is a working conversation that closes and reports back.

The doors:
  + New -> "Just talk it through"   POST /api/tasks  {Kind: general, Tags: ask:assistant}
  a Timeline row -> "Talk it through"   POST /api/messages/{id}/chat
  an invite -> "Prepare me for it"      POST /api/calendar/prep
  a Timeline row -> "Send it to a coding agent"   POST /api/messages/{id}/dispatch

and the thing they must NOT open: a plain `task`, which is yours and has no agent behind it.
"""
import unittest
from unittest import mock

from fastapi.testclient import TestClient
from fastapi import HTTPException

from taskuary import coder, general, selfclose, server
from taskuary.store import MemoryStore

c = TestClient(server.app)
ASK = 'ask:assistant'
EVENT = {'subject': 'Reimbursement app review', 'start': '2026-09-02T13:00:00',
         'end': '2026-09-02T14:00:00', 'who': ['dana@ours.com'], 'about': 'ESS link'}


def _msg(subject='Which vendor should we pick?', body='Two quotes, both fine. Thoughts?'):
    return server.store.add_message({'ExternalId': f'door:{subject}:{body}'[:80], 'Channel': 'email',
                                     'SourceName': 'me@ours.com', 'Subject': subject,
                                     'FromName': 'Dana', 'FromEmail': 'dana@vendor.example',
                                     'SentAt': '2026-09-01 09:00:00', 'BodyText': body,
                                     'Status': 'filed'})


def _task(tid):
    r = c.get(f'/api/tasks/{tid}').json()
    return r.get('task', r)


class EveryDoorOpensTheSameChat(unittest.TestCase):
    """Same Kind, same tag, same workspace - whichever button was pressed."""

    def _assert_is_a_chat(self, tid, where):
        t = _task(tid)
        self.assertEqual(t['Kind'], 'general', where)
        self.assertIn(ASK, t.get('Tags') or '', where)
        self.assertTrue(general.handles(t), where)
        # ...and the workspace actually accepts it, which is the thing a Kind alone does not prove
        self.assertEqual(c.get(f'/api/tasks/{tid}/assistant').status_code, 200, where)

    def test_new_sheet_just_talk_it_through(self):
        tid = c.post('/api/tasks', json={'Title': 'which vendor', 'Summary': 'Two quotes. Thoughts?',
                                         'Kind': 'general', 'Tags': ASK}).json()['taskId']
        self._assert_is_a_chat(tid, '+ New')

    def test_a_timeline_row_talk_it_through(self):
        d = c.post(f'/api/messages/{_msg()}/chat', json={}).json()
        self._assert_is_a_chat(d['taskId'], '/messages/:id/chat')
        self.assertTrue(d['chat'])

    def test_an_invite_prepare_me_for_it(self):
        d = c.post('/api/calendar/prep', json=EVENT).json()
        self._assert_is_a_chat(d['taskId'], '/calendar/prep')

    def test_the_chat_door_is_idempotent_on_the_same_message(self):
        """Pressing it twice must not make a second task for the same row."""
        mid = _msg('asked twice', 'body')
        first = c.post(f'/api/messages/{mid}/chat', json={}).json()['taskId']
        second = c.post(f'/api/messages/{mid}/chat', json={}).json()['taskId']
        self.assertEqual(first, second)


class TheDoorsThatAreNotChats(unittest.TestCase):
    def test_a_plain_task_is_not_a_conversation(self):
        """"This one is mine" is yours to do. Opening a chat workspace on it was the bug."""
        d = c.post(f'/api/messages/{_msg("sign the form", "wet signature needed")}/mine', json={}).json()
        t = _task(d['taskId'])
        self.assertEqual(t['Kind'], 'task')
        self.assertFalse(general.handles(t))
        self.assertEqual(c.get(f"/api/tasks/{d['taskId']}/assistant").status_code, 422)

    def test_send_it_to_a_coding_agent_still_makes_a_coding_task(self):
        mid = _msg('export is broken', 'the nightly export dropped a facility')
        with mock.patch('taskuary.server.start_session', return_value={'sid': 'x'}):
            d = c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'coder'}).json()
        self.assertEqual(_task(d['taskId'])['Kind'], 'coding')

    def test_explicit_coding_choice_corrects_an_existing_general_task(self):
        """The owner's button choice wins over a triage label that got the task wrong."""
        mid = _msg('review the responsibilities', 'Please read the list I sent.')
        tid = server.store.create_task({'Title': 'review it', 'Summary': 'Review this list',
                                        'Kind': 'general'}, 'router')
        server.store.attach_message(mid, tid)
        session = mock.Mock(provider='Azure OpenAI', model='gpt-test')
        session.info.return_value = {'sid': 'assistant-1', 'mode': 'assistant'}
        with mock.patch.object(general, 'start_session', return_value=session) as regular, \
             mock.patch.object(server, 'start_session', return_value={'sid': 'coding-1'}) as coding:
            d = c.post(f'/api/messages/{mid}/dispatch',
                       json={'agent': 'coder', 'kind': 'coding'}).json()
        self.assertEqual((d['dispatch'], d['taskId']), ('session', tid))
        self.assertEqual(_task(tid)['Kind'], 'coding')
        coding.assert_called_once()
        regular.assert_not_called()

    def test_send_to_agent_can_promote_a_message_to_the_regular_agent(self):
        mid = _msg('compare the options', 'Which one is better?')
        session = mock.Mock(provider='Taskuary', model='gpt-test')
        session.info.return_value = {'sid': 'assistant-2', 'mode': 'assistant'}
        with mock.patch.object(general, 'start_session', return_value=session):
            d = c.post(f'/api/messages/{mid}/dispatch', json={'kind': 'general'}).json()
        self.assertEqual(d['dispatch'], 'assistant')
        self.assertEqual(_task(d['taskId'])['Kind'], 'general')
        session.send_prompt.assert_called_once_with('Which one is better?')

    def test_explicit_regular_choice_corrects_an_existing_coding_task(self):
        mid = _msg('compare the responsibilities', 'Please review the list and explain the gaps.')
        tid = server.store.create_task({'Title': 'review it', 'Summary': 'Explain the gaps',
                                        'Kind': 'coding'}, 'router')
        server.store.attach_message(mid, tid)
        session = mock.Mock(provider='Azure OpenAI', model='gpt-test')
        session.info.return_value = {'sid': 'assistant-3', 'mode': 'assistant'}
        with mock.patch.object(general, 'start_session', return_value=session), \
             mock.patch.object(server, 'start_session') as coding:
            d = c.post(f'/api/messages/{mid}/dispatch', json={'kind': 'general'}).json()
        self.assertEqual((d['dispatch'], _task(tid)['Kind']), ('assistant', 'general'))
        coding.assert_not_called()

    def test_agent_type_cannot_change_under_a_live_session(self):
        mid = _msg('already running', 'Do the work.')
        tid = server.store.create_task({'Title': 'already running', 'Kind': 'general'}, 'router')
        server.store.attach_message(mid, tid)
        live = mock.Mock(alive=True, agent='assistant')
        with mock.patch.object(server.hub_term, 'session_for', return_value=live):
            r = c.post(f'/api/messages/{mid}/dispatch', json={'kind': 'coding'})
        self.assertEqual(r.status_code, 409)
        self.assertEqual(_task(tid)['Kind'], 'general')

    def test_unqualified_dispatch_is_rejected_instead_of_guessing_from_triage(self):
        mid = _msg('review this', 'Please review the responsibilities list.')
        r = c.post(f'/api/messages/{mid}/dispatch', json={})
        self.assertEqual(r.status_code, 422)
        self.assertIn('Choose an agent type', r.text)

    def test_an_uncertain_repo_asks_for_a_choice_and_keeps_the_new_task_id(self):
        mid = _msg('security app account', 'the login screen is empty')
        with mock.patch('taskuary.server.start_session',
                        side_effect=HTTPException(422, 'I could not tell which checkout this belongs in')):
            response = c.post(f'/api/messages/{mid}/dispatch', json={'agent': 'coder'})
        self.assertEqual(response.status_code, 200)
        d = response.json()
        self.assertEqual(d['dispatch'], 'needs_repo')
        self.assertEqual(d['agent'], 'coder')
        self.assertEqual(_task(d['taskId'])['Kind'], 'coding')
        self.assertIn('which checkout', d['reason'])


class TheConversationWorks(unittest.TestCase):
    """A door that opens onto a chat that cannot hold a turn is not wired up."""

    def _chat(self, reply='Pick the second quote - it covers install.'):
        s = MemoryStore()
        tid = s.create_task({'Title': 'which vendor', 'Kind': 'general', 'Summary': 'Two quotes.'}, 'o')
        sess = general.GeneralSession(s, tid)
        sess.pick, sess.provider, sess.model = 'cli:coder', 'coder', ''
        return s, tid, sess, mock.patch.object(general.llm_mod, 'build_llm',
                                               return_value=lambda system, user, **kw: reply)

    def test_a_turn_lands_in_the_task_and_comes_back_as_history(self):
        s, tid, sess, patched = self._chat()
        with patched:
            out = sess.send_prompt('which one should we take?')
        self.assertIn('second quote', out)
        hist = general.history(s, tid)
        self.assertEqual([m['role'] for m in hist], ['user', 'assistant'])
        self.assertIn('which one should we take?', hist[0]['content'][0]['text'])
        self.assertIn('second quote', hist[1]['content'][0]['text'])

    def test_the_conversation_is_the_tasks_own_record(self):
        """No synthetic CODER REPORT for a chat - the turns ARE the record, on the task."""
        s, tid, sess, patched = self._chat()
        with patched:
            sess.send_prompt('go on then')
        bodies = [cm['Body'] for cm in s.list_comments(tid)]
        self.assertTrue(any('go on then' in b for b in bodies))
        self.assertTrue(any('second quote' in b for b in bodies))


class ItClosesAndSaysSo(unittest.TestCase):
    def test_the_agent_can_end_it_from_inside_the_conversation(self):
        """A chat has no shell to run `taskuary --done` in, so it says it in the reply."""
        clean, said = selfclose.chat_marker(
            'Second quote, it covers install.\n[[TASKUARY-DONE]] Recommended the second quote.')
        self.assertEqual(said, 'Recommended the second quote.')
        self.assertNotIn('TASKUARY-DONE', clean)

    def test_an_ordinary_reply_never_closes_anything(self):
        """Most turns are not endings. Guessing here closes tasks out from under someone."""
        self.assertEqual(selfclose.chat_marker('Which budget is this coming from?')[1], None)

    def test_wrapping_a_chat_closes_it_and_reports_its_last_word(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'which vendor', 'Kind': 'general'}, 'o')
        sess = general.GeneralSession(s, tid)
        sess.pick, sess.provider, sess.model = 'cli:coder', 'coder', ''
        with mock.patch.object(general.llm_mod, 'build_llm',
                               return_value=lambda system, user, **kw: 'Recommended the second quote.'):
            sess.send_prompt('decide it')
        with mock.patch.object(general, 'session_for', return_value=sess), \
             mock.patch('taskuary.terminal.close'):
            out = coder.wrap(s, tid, close=True, actor='owner')
        self.assertEqual(out['wrap'], 'done')
        self.assertIn('second quote', out['report'])              # its own last word, not a summary
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertFalse(out['drafting'])                          # nobody to answer: it is your chat


if __name__ == '__main__':
    unittest.main()
