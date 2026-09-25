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

    def test_importing_a_skill_is_hiring_and_an_agent_may_not(self):
        """/api/skills/import does exactly what the two rows above forbid - it writes an agent row
        (upsert_agent) and an operator document (save_doc) - under a third prefix. /read is the half
        of it that turns a file on this disk into the text a worker would then follow."""
        for method, path in (('POST', '/api/skills/import'), ('POST', '/api/skills/read')):
            self.assertTrue(guard.denied(method, path), f'{method} {path} must be refused')
        self.assertFalse(guard.denied('GET', '/api/skills/found'),
                         'listing what is installed writes nothing and reads nothing a session cannot')

    def test_the_work_an_agent_is_here_to_do_is_untouched(self):
        for method, path in (('GET', '/api/tasks'), ('GET', '/api/feed'),
                             ('POST', '/api/board/notes'),              # the wall
                             ('POST', '/api/handbook'),                 # the handbook
                             ('POST', '/api/tasks/7/comment'),
                             ('GET', '/api/connectors'),                # reading is fine; writing is not
                             ('POST', '/api/agent/done')):              # closing its own task
            self.assertFalse(guard.denied(method, path), f'{method} {path} must be allowed')

    def test_the_doors_the_audit_found_open_are_shut(self):
        """2026-09-02: releasing the held task of the sender the hold exists for, landing work, running
        an executor or a query with a card's credentials, rewriting the governing documents."""
        for method, path in (('POST', '/api/tasks/7/release'), ('POST', '/api/tasks/7/land'), ('POST', '/api/tasks/7/ci'),
                             ('POST', '/api/soul/interview'), ('POST', '/api/learn/reflect'), ('POST', '/api/learn/adopt'),
                             ('PUT', '/api/owner'), ('PATCH', '/api/whoami'),
                             ('POST', '/api/mssql/test'), ('POST', '/api/mcp/tools'),
                             ('POST', '/api/reports/preview'), ('POST', '/api/reports/compose'), ('POST', '/api/workflows/compose'),
                             ('POST', '/api/reports/3/invoice-batches'), ('PATCH', '/api/invoice-batches/2/items/8'),
                             ('POST', '/api/invoice-batches/2/prepare'),
                             ('POST', '/api/semantic/metrics'), ('DELETE', '/api/semantic/metrics/3'), ('POST', '/api/semantic/metrics/3/try'),
                             ('POST', '/api/terminals'), ('DELETE', '/api/terminals/abc')):
            self.assertTrue(guard.denied(method, path), f'{method} {path} must be refused')
        for method, path in (('GET', '/api/semantic/metrics'), ('GET', '/api/reports'), ('POST', '/api/tools/run'),
                             ('GET', '/api/terminals'), ('GET', '/api/terminals/abc/screen')):
            self.assertFalse(guard.denied(method, path), f'{method} {path} must be allowed')

    def test_the_list_is_not_configurable(self):
        """If this ever reads a setting, a document or the database, delete that and this test.
        A control an agent can reach is not a control."""
        import inspect
        src = inspect.getsource(guard)
        for reachable in ('get_setting', 'store.', 'doc(', 'os.getenv'):
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

    def test_a_wrong_length_token_is_just_wrong(self):
        self.assertFalse(guard.token_matches('short', 'much-longer-secret'))
        self.assertTrue(guard.token_matches('secret', 'secret'))
        self.assertFalse(guard.token_matches('secret', 'secretX'))
        self.assertTrue(guard.token_matches('agent', 'nope', 'agent'))

    def test_a_token_of_the_right_length_but_the_wrong_alphabet_is_just_wrong(self):
        """A header is decoded latin-1, so one byte >= 0x80 reaches here as a non-ASCII str.
        compare_digest refuses those outright, and the middleware answered a junk token with a
        500 and a traceback instead of a refusal (review of #47)."""
        same_length = 'abcdefg' + chr(0xFF)
        self.assertEqual(len(same_length), len('abcdefgh'))
        self.assertFalse(guard.token_matches(same_length, 'abcdefgh'))
        self.assertFalse(guard.token_matches(chr(0xFF) * 8, 'abcdefgh'))
        self.assertTrue(guard.token_matches(same_length, same_length))


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
        self.assertEqual(c.post('/api/hub', json={'title': 'the tests need pyodbc',
                                                  'why_earned': 'Repeated isolated test runs proved this native dependency was required.'},
                                headers=AGENT).status_code, 200)

    def test_a_session_is_given_the_token_in_its_environment(self):
        """...which is how `taskuary --note` works at all, and how the middleware knows."""
        from taskuary import terminal
        env = terminal.session_env('coder', 41, 'C:/repo')
        self.assertEqual(env[guard.AGENT_ENV], config.load()['server']['agent_token'])

    def test_a_session_cannot_open_or_kill_a_live_pty(self):
        self.assertEqual(c.post('/api/terminals', json={'cwd': '.'}, headers=AGENT).status_code, 403)
        self.assertEqual(c.delete('/api/terminals/nope', headers=AGENT).status_code, 403)
        self.assertEqual(c.get('/api/terminals', headers=AGENT).status_code, 200)

    def test_a_session_does_not_see_oauth_secrets_on_the_connector_list(self):
        import json
        from taskuary import server
        qb = next(x for x in server.store.list_connectors() if x['Type'] == 'quickbooks')
        before = qb.get('ConfigJson')
        server.store.save_connector({'ConnectorId': qb['ConnectorId'],
                                     'ConfigJson': json.dumps({'client_id': 'id', 'client_secret': 'super-secret-app',
                                                               'realm_id': '123'})}, 't')
        try:
            shown = next(x for x in c.get('/api/connectors').json()['data'] if x['ConnectorId'] == qb['ConnectorId'])
            self.assertIn('super-secret-app', shown['ConfigJson'])          # the card the owner edits
            hidden = next(x for x in c.get('/api/connectors', headers=AGENT).json()['data']
                          if x['ConnectorId'] == qb['ConnectorId'])
            cfg = json.loads(hidden['ConfigJson'])
            self.assertNotIn('super-secret-app', hidden['ConfigJson'])
            self.assertEqual(cfg.get('client_id'), 'id')
            self.assertEqual(cfg.get('realm_id'), '123')
            self.assertNotIn('client_secret', cfg)
        finally:
            server.store.save_connector({'ConnectorId': qb['ConnectorId'], 'ConfigJson': before or '{}'}, 't')


if __name__ == '__main__':
    unittest.main()
