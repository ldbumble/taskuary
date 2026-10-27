"""RUN ANOTHER AGENT ON A GENERAL TASK IS A SECOND AGENT (the owner, 2026-10-27: "I hit Run another agent and it just opened the same
window instead of a new one??? does it mean Continue?"). The dispatch reused the task's one conversation: the CLI resumed its saved id,
the pane read every turn, and with nothing typed nothing was sent - the stopped agent's chat, again. `fresh` starts a new one: its own
conversation and CLI, the task as its first ask, where the earlier agent got to in its prompt, and the earlier turns kept on the task."""
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import general, server
from taskuary.store import MemoryStore

ASKED, ANSWERED = 'Find who signs the snag list on Thursday.', 'The handover sheet names Ray Colton for Thursday.'


class RunAnotherTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.tid = self.s.create_task({'Title': 'Snag list sign-off', 'Summary': 'Find out who signs the snag list', 'Kind': 'general',
                                       'Status': 'in_progress'}, 'owner')
        self.s.add_comment(self.tid, 'owner', general.USER_TYPE, ASKED)
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, ANSWERED)
        self.s.save_session(self.tid, 'cli:claude', 'opus', 'cli-conversation-1', 'key-1')
        p = mock.patch.object(server, 'store', self.s); p.start(); self.addCleanup(p.stop)
        live = mock.patch.dict(server.hub_term.SESSIONS, {}); live.start(); self.addCleanup(live.stop)
        self.c = TestClient(server.app)

    def dispatch(self, **body):
        session = mock.Mock(provider='Claude Code', model='opus')
        session.info.return_value = {'sid': 'assistant-2', 'mode': 'assistant'}
        with mock.patch.object(general, 'start_session', return_value=session) as start:
            out = self.c.post(f'/api/tasks/{self.tid}/dispatch', json={'kind': 'general', **body}).json()
        start.assert_called_once()
        return out, session

    def test_run_another_starts_a_new_conversation_and_sends_it_the_task(self):
        out, session = self.dispatch(fresh=True)
        self.assertEqual(out['dispatch'], 'assistant')
        self.assertEqual(general.history(self.s, self.tid), [], 'the new agent opens on a conversation of its own')
        self.assertEqual([m['content'][0]['text'] for m in general.earlier(self.s, self.tid)],
                         [ASKED, ANSWERED], 'the earlier agent\'s turns stay on the task')
        self.assertEqual(self.s.saved_session(self.tid)['NativeId'], '', 'the earlier CLI conversation is never resumed')
        session.send_prompt.assert_called_once_with('Find out who signs the snag list')

    def test_the_new_agents_prompt_is_its_own_with_where_the_earlier_one_got_to(self):
        self.dispatch(fresh=True)
        self.s.add_comment(self.tid, 'owner', general.USER_TYPE, 'Check the site rota too.')
        _, user = general._prompt(self.s, self.tid)
        conv = user[user.index('CONVERSATION'):]
        self.assertIn('Check the site rota too.', conv)
        self.assertNotIn(ASKED, conv, 'the earlier agent\'s chat is not this one\'s conversation')
        self.assertIn('WHERE THE EARLIER AGENT ON THIS TASK GOT TO', user)
        self.assertIn(ANSWERED, user)

    def test_the_pane_reads_the_new_conversation_and_the_earlier_one_apart(self):
        self.dispatch(fresh=True)
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Starting fresh on the snag list.')
        with mock.patch.object(general, 'session_for', return_value=None):
            data = self.c.get(f'/api/tasks/{self.tid}/assistant').json()
        self.assertEqual([m['content'][0]['text'] for m in data['messages']], ['Starting fresh on the snag list.'])
        self.assertEqual([m['content'][0]['text'] for m in data['earlier']], [ASKED, ANSWERED])

    def test_continue_still_picks_the_same_conversation_up(self):
        out, session = self.dispatch()
        self.assertEqual(len(general.history(self.s, self.tid)), 2)
        self.assertEqual(general.earlier(self.s, self.tid), [])
        self.assertEqual(self.s.saved_session(self.tid)['NativeId'], 'cli-conversation-1')
        session.send_prompt.assert_not_called()

    def test_a_first_start_with_fresh_sets_nothing_apart(self):
        tid = self.s.create_task({'Title': 'Nothing yet', 'Kind': 'general'}, 'owner')
        self.assertFalse(general.new_run(self.s, tid))
        self.assertEqual([c for c in self.s.list_comments(tid) if c['ActorType'] == general.RUN_TYPE], [])

    def test_a_third_agent_sets_the_second_apart_too(self):
        self.dispatch(fresh=True)
        self.s.add_comment(self.tid, 'assistant', general.ASSISTANT_TYPE, 'Second agent answer.')
        self.dispatch(fresh=True)
        self.assertEqual(general.history(self.s, self.tid), [])
        self.assertEqual(len(general.earlier(self.s, self.tid)), 3)
        self.assertEqual(len(general.chat_rows(self.s, self.tid)), 3, 'every turn is still on the task')


if __name__ == '__main__':
    unittest.main()
