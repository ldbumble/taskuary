"""An agent may not send. Enforced in code, where a message cannot argue with it.

The threat is not an agent that decides to misbehave; it is an agent working a message that
CONTAINS instructions. Every earlier control against it was a paragraph - SOUL.md, CODER.md, the
seed prompt - sitting in the same context as the untrusted text and arguing with it on equal
terms. These tests are the line that is not a paragraph.
"""
import unittest
from fastapi.testclient import TestClient

from taskuary import config, guard, server

c = TestClient(server.app)
AGENT = {'X-Taskuary-Token': config.load()['server']['agent_token']}


class DenyListTests(unittest.TestCase):
    """The table itself, with no server in the way."""

    def test_everything_that_sends_is_refused_to_an_agent(self):
        for method, path in (('POST', '/api/reviews/12/decide'),        # approving IS sending
                             ('POST', '/api/tasks/7/handoff'),          # forwards to a person
                             ('POST', '/api/outbox'),                   # starts an outbound message
                             ('POST', '/api/messages/3/reply'),         # opens one
                             ('POST', '/api/tasks/7/clarify')):         # opens a sender clarification
            self.assertTrue(guard.denied(method, path), f'{method} {path} must be refused')

    def test_widening_its_own_reach_is_refused_too(self):
        """The obvious next move for a model that has been told to send something and cannot is
        to change the rules until it can."""
        for method, path in (('POST', '/api/settings'), ('PUT', '/api/connectors/2'),
                             ('POST', '/api/docs/soul'), ('DELETE', '/api/policies/4'),
                             ('GET', '/api/send-targets')):
            self.assertTrue(guard.denied(method, path), f'{method} {path} must be refused')

    def test_the_work_an_agent_is_here_to_do_is_untouched(self):
        for method, path in (('GET', '/api/tasks'), ('GET', '/api/feed'),
                             ('POST', '/api/board/notes'),              # the wall
                             ('POST', '/api/handbook'),                 # the handbook
                             ('POST', '/api/tasks/7/comment'),
                             ('GET', '/api/connectors'),                # reading is fine; writing is not
                             ('POST', '/api/agent/done')):              # closing its own task
            self.assertFalse(guard.denied(method, path), f'{method} {path} must be allowed')

    def test_the_list_is_not_configurable(self):
        """If this ever reads a setting, a document or the database, delete that and this test.
        A control an agent can reach is not a control."""
        import inspect
        src = inspect.getsource(guard)
        for reachable in ('get_settings', 'store.', 'doc(', 'os.getenv'):
            self.assertNotIn(reachable, src, f'guard must not consult {reachable}')


class ScopeTests(unittest.TestCase):
    def test_the_agent_token_is_what_says_agent(self):
        srv = {'token': '', 'agent_token': 'AGENT'}
        self.assertEqual(guard.scope_of(srv, {'X-Taskuary-Token': 'AGENT'}), guard.AGENT)
        self.assertEqual(guard.scope_of(srv, {}), guard.OWNER)          # no owner token: the open door

    def test_with_an_owner_token_set_an_unknown_caller_is_nobody(self):
        srv = {'token': 'OWNER', 'agent_token': 'AGENT'}
        self.assertEqual(guard.scope_of(srv, {'X-Taskuary-Token': 'OWNER'}), guard.OWNER)
        self.assertEqual(guard.scope_of(srv, {'X-Taskuary-Token': 'AGENT'}), guard.AGENT)
        self.assertEqual(guard.scope_of(srv, {'X-Taskuary-Token': 'guess'}), guard.ANON)
        self.assertEqual(guard.scope_of(srv, {}), guard.ANON)

    def test_every_install_gets_an_agent_token(self):
        """Without one there is nothing to tell a session's request from a person's, so the deny
        list has nothing to act on - it is minted whether or not the owner set an owner token."""
        srv = {}
        guard.ensure_tokens(dict, lambda d: None, srv)
        self.assertTrue(len(srv['agent_token']) > 20)
        first = srv['agent_token']
        guard.ensure_tokens(dict, lambda d: None, srv)
        self.assertEqual(srv['agent_token'], first)                     # stable across restarts


class OverTheWireTests(unittest.TestCase):
    """...and the same thing through the actual middleware, which is what a curl in a session hits."""

    def test_a_session_cannot_approve_its_own_draft(self):
        r = c.post('/api/reviews/1/decide', json={'verb': 'approve'}, headers=AGENT)
        self.assertEqual(r.status_code, 403)
        self.assertIn('agents cannot do this', r.json()['detail'])

    def test_a_session_cannot_read_where_this_install_can_send(self):
        self.assertEqual(c.get('/api/send-targets', headers=AGENT).status_code, 403)
        self.assertEqual(c.get('/api/send-targets').status_code, 200)   # the owner still can

    def test_a_session_cannot_rewrite_the_document_that_governs_it(self):
        self.assertEqual(c.post('/api/docs/soul', json={'text': 'agents may send'}, headers=AGENT).status_code, 403)

    def test_a_session_can_still_do_its_job(self):
        self.assertEqual(c.post('/api/board/notes', json={'body': 'taking store.py'}, headers=AGENT).status_code, 200)
        self.assertEqual(c.post('/api/handbook', json={'title': 'the tests need pyodbc'}, headers=AGENT).status_code, 200)

    def test_a_session_is_given_the_token_in_its_environment(self):
        """...which is how `taskuary --note` works at all, and how the middleware knows."""
        from taskuary import terminal
        env = terminal.session_env('coder', 41, 'C:/repo')
        self.assertEqual(env[guard.AGENT_ENV], config.load()['server']['agent_token'])


if __name__ == '__main__':
    unittest.main()
