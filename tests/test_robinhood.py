"""Robinhood over its hosted MCP: the HTTP transport, and the two gates that keep a broker safe.

The card can move money, which is new here. Two independent things stop an agent doing it:
the SCOPE ladder (the card ships at read, so robinhood_order is a proposal) and the READ GATE
(a read may only reach a tool Robinhood itself marks readOnlyHint, checked against the live
manifest and failing closed). Either alone would be enough to argue for; both is the point.
"""
import json, unittest
from unittest import mock

from taskuary import mcp, playbooks, reports, robinhood, scopes

TOOLS = [
    {'name': 'get_positions', 'description': 'current positions', 'annotations': {'readOnlyHint': True}},
    {'name': 'get_balances', 'description': 'buying power', 'annotations': {'readOnlyHint': True}},
    {'name': 'place_order', 'description': 'place an order', 'annotations': {'readOnlyHint': False}},
    {'name': 'cancel_order', 'description': 'cancel an order'},          # says nothing at all
]


class FakeSession:
    def __init__(self, tools=None, result=None):
        self._tools, self._result, self.called = tools if tools is not None else TOOLS, result, []
    def list_tools(self): return self._tools
    def call_tool(self, name, args=None):
        self.called.append((name, args))
        return self._result or {'content': [{'type': 'text', 'text': 'ok'}]}
    def close(self): pass


def _with(session):
    return mock.patch('taskuary.mcp._session', return_value=session)


CFG = {'token': 'tok'}


class ReadGateTests(unittest.TestCase):
    def test_a_read_only_tool_is_allowed(self):
        s = FakeSession()
        with _with(s):
            head, out = robinhood.run_robinhood_read({**CFG, 'tool': 'get_positions', 'args': {'account': 'agentic'}})
        self.assertEqual(s.called, [('get_positions', {'account': 'agentic'})])
        self.assertIn('get_positions', head); self.assertEqual(out, 'ok')

    def test_a_write_tool_can_never_run_as_a_read(self):
        """Without this, robinhood_read would be a read-scoped door onto every order tool."""
        s = FakeSession()
        with _with(s), self.assertRaises(PermissionError) as e:
            robinhood.run_robinhood_read({**CFG, 'tool': 'place_order', 'args': {'symbol': 'AAPL'}})
        self.assertIn('proposal', str(e.exception))
        self.assertEqual(s.called, [])                       # and nothing was sent

    def test_a_tool_that_declares_nothing_is_treated_as_a_write(self):
        """Fail closed: an unannotated tool is not evidence of safety."""
        with _with(FakeSession()), self.assertRaises(PermissionError):
            robinhood.run_robinhood_read({**CFG, 'tool': 'cancel_order'})
        self.assertFalse(mcp.read_only({'name': 'x'}))
        self.assertFalse(mcp.read_only({'name': 'x', 'annotations': {'readOnlyHint': 'yes'}}))   # not the string
        self.assertTrue(mcp.read_only({'name': 'x', 'annotations': {'readOnlyHint': True}}))

    def test_a_tool_this_account_does_not_have_is_refused(self):
        with _with(FakeSession()), self.assertRaises(ValueError):
            robinhood.run_robinhood_read({**CFG, 'tool': 'get_the_moon'})

    def test_the_order_path_does_not_apply_the_read_gate(self):
        """It is gated by SCOPE instead - that is the whole design."""
        s = FakeSession()
        with _with(s):
            robinhood.run_robinhood_order({**CFG, 'tool': 'place_order', 'args': {'symbol': 'AAPL', 'qty': 1}})
        self.assertEqual(s.called, [('place_order', {'symbol': 'AAPL', 'qty': 1})])

    def test_no_token_is_a_clear_error_not_a_401(self):
        with self.assertRaises(RuntimeError) as e: robinhood.run_robinhood_read({'tool': 'get_positions'})
        self.assertIn('connect the account', str(e.exception).lower())


class DiscoveryTests(unittest.TestCase):
    def test_the_manifest_report_says_which_tools_are_writes(self):
        with mock.patch('taskuary.mcp.list_tools', return_value=[
                {'name': 'get_positions', 'description': 'current positions', 'read_only': True},
                {'name': 'place_order', 'description': 'place an order', 'read_only': False}]):
            head, body = robinhood.run_robinhood_tools(CFG)
        self.assertIn('2 Robinhood tools', head)
        self.assertIn('get_positions  (read-only)', body)
        self.assertIn('place_order  (WRITE - proposal only)', body)


class ScopeTests(unittest.TestCase):
    def test_the_card_ships_read_so_an_order_is_only_ever_proposed(self):
        self.assertEqual(scopes.DEFAULT_SCOPE['robinhood'], 'read')
        self.assertEqual(scopes.ACTIONS['robinhood_order'], 'write')
        self.assertEqual(scopes.ACTIONS['robinhood_read'], 'read')
        self.assertEqual(scopes.ACTIONS['robinhood_tools'], 'read')

    def test_a_tool_call_cannot_redirect_the_token_at_another_host(self):
        """url and token are CONNECTION_KEYS: the card decides where the credential goes."""
        body = reports.query_only({'tool': 'get_positions', 'url': 'https://evil.example', 'token': 'stolen'})
        self.assertEqual(body, {'tool': 'get_positions'})

    def test_all_three_are_registered_and_share_the_card(self):
        for t in ('robinhood_tools', 'robinhood_read', 'robinhood_order'):
            self.assertIn(t, reports.REGISTRY, t)
            self.assertIn(t, reports.CONNECTION_OF, t)


class TransportTests(unittest.TestCase):
    """Streamable HTTP: a server may answer one JSON object or an SSE stream, per response."""

    def _resp(self, *, sse=False, payload=None, status=200, sid='s1'):
        r = mock.Mock(status_code=status, headers={'content-type': 'text/event-stream' if sse else 'application/json'})
        r.headers['mcp-session-id'] = sid
        if sse: r.iter_lines = lambda decode_unicode=True: ['', 'event: message', 'data: ' + json.dumps(payload)]
        else: r.json = lambda: payload
        r.text = ''
        return r

    def test_a_plain_json_reply_is_read(self):
        c = mcp.HTTPMCPClient('https://x/mcp', token='t')
        with mock.patch('requests.post', return_value=self._resp(payload={'jsonrpc': '2.0', 'id': 1, 'result': {'ok': 1}})):
            self.assertEqual(c.request('ping'), {'ok': 1})

    def test_an_sse_reply_is_read_and_the_session_id_is_kept(self):
        c = mcp.HTTPMCPClient('https://x/mcp', token='t')
        with mock.patch('requests.post', return_value=self._resp(sse=True, payload={'jsonrpc': '2.0', 'id': 1, 'result': {'ok': 2}})):
            self.assertEqual(c.request('ping'), {'ok': 2})
        self.assertEqual(c.session, 's1')

    def test_the_token_rides_as_a_bearer(self):
        c = mcp.HTTPMCPClient('https://x/mcp', token='secret')
        with mock.patch('requests.post', return_value=self._resp(payload={'id': 1, 'result': {}})) as post:
            c.request('ping')
        self.assertEqual(post.call_args.kwargs['headers']['Authorization'], 'Bearer secret')

    def test_a_401_says_what_to_do(self):
        c = mcp.HTTPMCPClient('https://x/mcp', token='stale')
        with mock.patch('requests.post', return_value=self._resp(status=401, payload={})):
            with self.assertRaises(RuntimeError) as e: c.request('ping')
        self.assertIn('sign in again', str(e.exception))

    def test_a_url_picks_http_and_a_cmd_still_picks_stdio(self):
        """One dispatch, both transports - the stdio servers must keep working untouched."""
        with mock.patch.object(mcp, 'HTTPMCPClient') as http, mock.patch.object(mcp, 'MCPClient') as stdio:
            mcp._session({'url': 'https://x/mcp', 'token': 't'})
            http.assert_called_once(); stdio.assert_not_called()
            self.assertEqual(http.call_args[0][:2], ('https://x/mcp', 't'))
        with mock.patch.object(mcp, 'HTTPMCPClient') as http, mock.patch.object(mcp, 'MCPClient') as stdio:
            mcp._session({'cmd': 'npx', 'args': ['a']})
            stdio.assert_called_once(); http.assert_not_called()
        with self.assertRaises(ValueError): mcp._session({})       # neither one named


class PlaybookTests(unittest.TestCase):
    def test_the_shipped_playbook_names_the_card_and_forbids_placing_a_trade(self):
        from pathlib import Path
        text = (Path(__file__).parent.parent / 'taskuary' / 'templates' / 'playbooks'
                / 'robinhood-trade.md').read_text(encoding='utf-8')
        pb = playbooks.parse(text)
        self.assertIn('robinhood', playbooks.uses_of(pb))
        self.assertIn('EVERY order', pb['ask first'])
        self.assertIn('robinhood_tools first', pb['steps'])       # the names are not documented
        # it reaches systems, not a checkout - so the seed must not send an agent hunting a repo
        self.assertFalse(playbooks.about_code(pb))


if __name__ == '__main__': unittest.main()
