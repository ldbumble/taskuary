"""Driving an agent over ACP instead of writing argv and reading stdout.

One protocol replaces a per-CLI dialect. The thing worth testing is not the happy path - it is
the half that argv never had: the agent sends requests BACK, and an unanswered one is a hang, not
an error. Every test here runs against tests/fake_acp_server.py, so no vendor CLI is installed.

Scope is the general agent's tool-using runs. A classifier call and a coding session must keep the
road they have, and the last class here pins that.
"""
import json
import sys
import unittest
from pathlib import Path
from unittest import mock

from taskuary import acp, agents, clis
from taskuary.store import MemoryStore

# the harness allows exactly [python, <one of its own fakes>] - see conftest's allowed_files
FAKE = [sys.executable, str(Path(__file__).parent / 'fake_acp_server.py')]


HERE = str(Path(__file__).parent)          # a real directory: the agent is spawned INTO its cwd


def client(**kw):
    return acp.ACPClient(FAKE[0], FAKE[1:], timeout=30, **kw)


def profile():
    return {'cmd': FAKE[0], 'args': [], 'acp': FAKE[1:], 'acp_ok': True, 'cwd': HERE}


class TheHandshakeTests(unittest.TestCase):
    def test_connecting_reports_what_the_agent_can_do(self):
        c = client()
        try:
            caps = c.connect()
            self.assertTrue(caps.get('loadSession'))
        finally:
            c.close()

    def test_we_do_not_claim_filesystem_capabilities_we_have_not_built(self):
        """Declaring fs would route the agent's file reads through Taskuary; under -p it uses its
        own. The spec is explicit that an omitted capability means UNSUPPORTED, so this is how the
        agent is told to keep its own hands."""
        sent = []
        c = client()
        try:
            with mock.patch.object(c, '_send', side_effect=lambda m: sent.append(m) or acp.ACPClient._send(c, m)):
                c.connect()
        finally:
            c.close()
        init = next(m for m in sent if m.get('method') == 'initialize')
        self.assertEqual(init['params']['clientCapabilities'].get('fs'), {'readTextFile': False, 'writeTextFile': False})


class ATurnTests(unittest.TestCase):
    def test_a_session_has_an_id_and_a_turn_returns_what_was_said(self):
        c = client()
        try:
            c.connect()
            sid = c.new_session(HERE)
            self.assertTrue(sid)
            stop, said = c.prompt('total the vendor spend')
            self.assertEqual(stop, 'end_turn')
            self.assertIn('total the vendor spend', said)
        finally:
            c.close()

    def test_progress_arrives_as_it_happens_not_at_the_end(self):
        seen = []
        c = client(on_update=lambda u: seen.append(u.get('sessionUpdate')))
        try:
            c.connect(); c.new_session(HERE); c.prompt('go')
        finally:
            c.close()
        self.assertIn('tool_call', seen); self.assertIn('agent_message_chunk', seen)

    def test_an_unanswered_permission_request_would_be_a_hang_so_we_answer_it(self):
        """The fake agent will not end its turn until the permission is answered. If this test
        ever times out rather than fails, the pump has stopped dispatching inbound requests."""
        c = client()
        try:
            c.connect(); c.new_session(HERE)
            stop, said = c.prompt('do the thing')
            self.assertEqual(stop, 'end_turn')
            self.assertIn('granted', said)          # we chose the allow option, not the first one
        finally:
            c.close()

    def test_a_resumed_session_is_loaded_rather_than_started(self):
        c = client()
        try:
            c.connect()
            self.assertEqual(c.load_session('sess_fake_1', HERE), 'sess_fake_1')
            stop, _ = c.prompt('carry on')
            self.assertEqual(stop, 'end_turn')
        finally:
            c.close()


class TheAgentsSeamTests(unittest.TestCase):
    def test_a_run_returns_the_same_shape_as_the_argv_road(self):
        prof = profile()
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            out, sid, diff = agents.run_cli(prof, 'total the vendor spend', lambda *a, **k: None)
        self.assertIn('total the vendor spend', out); self.assertTrue(sid)

    def test_the_session_id_comes_from_the_protocol_not_from_a_file(self):
        """gemini and cursor hand out no id on the argv road - sessionfiles hashes a project root
        and reads the vendor's temp directory to find one. session/new just returns it."""
        prof = profile()
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            _out, sid, _ = agents.run_cli(prof, 'go', lambda *a, **k: None)
        self.assertEqual(sid, 'sess_fake_1')

    def test_the_work_reaches_the_board_as_trace_lines(self):
        traced, prof = [], profile()
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            agents.run_cli(prof, 'go', lambda kind, name, text='': traced.append(f'{kind}:{text}'))
        self.assertTrue(any('read the ledger' in t for t in traced))

    def test_a_credential_is_scrubbed_on_this_road_too(self):
        """run_acp must not become a door the scrub does not cover."""
        key, prof = 'AKIA' + 'IOSFODNN7EXAMPLE', profile()
        with mock.patch.object(agents, '_resolve_cmd', return_value=[FAKE[0]]):
            out, _sid, _ = agents.run_cli(prof, f'use {key} please', lambda *a, **k: None)
        self.assertNotIn(key, out); self.assertIn('[redacted:aws-key]', out)


class NothingElseChangesTests(unittest.TestCase):
    """The whole point of the gate: this is for the general agent's tool runs and nothing else."""

    def test_a_profile_without_acp_arguments_keeps_the_argv_road(self):
        with mock.patch.object(agents, 'run_acp', side_effect=AssertionError('must not take the ACP road')), \
             mock.patch.object(agents, '_resolve_cmd', return_value=['claude']), \
             mock.patch.object(agents.spawn, 'popen', side_effect=RuntimeError('stop')):
            with self.assertRaises(RuntimeError):
                agents.run_cli({'cmd': 'claude', 'args': ['-p'], 'cwd': HERE}, 'hi', lambda *a, **k: None)

    def test_a_classifier_run_keeps_the_argv_road_even_on_an_acp_capable_cli(self):
        """make_cli_llm's no-hands branch is triage and the drafter. They get one classification
        with every tool off; a session protocol has nothing to offer them."""
        from taskuary import llm
        s = MemoryStore()
        s.upsert_agent('gemini', 'coding', 'cli', json.dumps({'cmd': 'gemini', 'args': ['-p', '--yolo']}))
        brain = llm.make_cli_llm(s, 'gemini')
        seen = {}
        with mock.patch.object(agents, 'run_cli', side_effect=lambda prof, *a, **k: (seen.update(prof), ('', None, None))[1]):
            brain('sys', 'user')
        self.assertFalse(seen.get('acp_ok'))

    def test_a_general_agent_run_with_hands_is_marked_for_the_acp_road(self):
        from taskuary import llm
        s = MemoryStore()
        s.upsert_agent('gemini', 'coding', 'cli', json.dumps({'cmd': 'gemini', 'args': ['-p', '--yolo']}))
        brain = llm.make_cli_llm(s, 'gemini', cli_tools=True)
        seen = {}
        with mock.patch.object(agents, 'run_cli', side_effect=lambda prof, *a, **k: (seen.update(prof), ('', None, None))[1]):
            brain('sys', 'user')
        self.assertTrue(seen.get('acp_ok'))

    def test_an_acp_session_id_is_kept_for_a_cli_with_no_argv_resume_flag(self):
        """devin reloads its ACP sessions (loadSession) but has no --resume; the id session/new returned
        was dropped and the saved row read NativeId '' (2026-09-20)."""
        from taskuary import continuity
        s = MemoryStore()
        s.upsert_agent('deviner', 'general', 'cli', json.dumps({'cmd': 'devin', 'acp': ['acp']}))
        s.upsert_agent('devin', 'general', 'cli', json.dumps({'cmd': 'devin'}))
        self.assertTrue(continuity.can_resume(s, 'cli:deviner'))
        self.assertFalse(continuity.can_resume(s, 'cli:devin'))

    def test_only_the_clis_that_speak_it_natively_ship_with_it(self):
        by = {r['name']: r for r in clis.KNOWN}
        self.assertEqual(sorted(n for n, r in by.items() if r.get('acp')), ['copilot', 'cursor', 'devin', 'gemini', 'qwen'])   # devin acp: verified 2026-09-20
        # claude and codex are adapter-only: reachable by putting the adapter in a profile, never shipped on
        for n in ('claude', 'codex', 'muse'):
            self.assertIsNone(by[n].get('acp'))


if __name__ == '__main__':
    unittest.main()
