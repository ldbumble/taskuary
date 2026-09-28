"""MCP connector tests - a real stdio round-trip against tests/fake_mcp_server.py."""
import sys, unittest
from unittest import mock
from pathlib import Path
from taskuary import mcp

CFG = {'cmd': sys.executable, 'args': [str(Path(__file__).parent / 'fake_mcp_server.py')], 'timeout': 20}


class MCPTests(unittest.TestCase):
    def test_list_tools(self):
        tools = mcp.list_tools(CFG)
        self.assertEqual(tools[0]['name'], 'echo')

    def test_run_report_calls_tool(self):
        head, body = mcp.run_report({**CFG, 'tool': 'echo', 'tool_args': {'text': 'hi'}})
        self.assertEqual((head, body), ('echo ok', 'echo: hi'))

    def test_tool_args_as_json_string(self):
        _, body = mcp.run_report({**CFG, 'tool': 'echo', 'tool_args': '{"text": "s"}'})
        self.assertEqual(body, 'echo: s')

    def test_missing_cmd_fails_loudly(self):
        with self.assertRaises(ValueError): mcp.run_report({'tool': 'echo'})

    def test_a_blank_timeout_means_the_default(self):
        for cfg in ({}, {'timeout': ''}, {'timeout': None}, {'timeout': '  '}):
            self.assertEqual(mcp._timeout(cfg), 60)
        self.assertEqual(mcp._timeout({'timeout': '15'}), 15)
        with mock.patch.object(mcp.HTTPMCPClient, 'start', lambda self: self):
            self.assertEqual(mcp._session({'url': 'http://127.0.0.1:1/mcp', 'timeout': ''}).timeout, 60)
        self.assertEqual(mcp.list_tools({**CFG, 'timeout': ''})[0]['name'], 'echo')

    def test_a_timeout_that_is_not_seconds_says_so(self):
        for bad in ('slow', '-5', '0', 'inf', []):
            with self.subTest(timeout=bad), self.assertRaisesRegex(ValueError, '^timeout must be a number of seconds$'):
                mcp._session({'url': 'http://127.0.0.1:1/mcp', 'timeout': bad})

    def test_registered_in_registry(self):
        from taskuary.reports import REGISTRY
        head, _ = REGISTRY['mcp']({**CFG, 'tool': 'echo', 'tool_args': {'text': 'x'}})
        self.assertEqual(head, 'echo ok')


if __name__ == '__main__':
    unittest.main()
