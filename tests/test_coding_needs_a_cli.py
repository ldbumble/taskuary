"""CODING EXISTS ONLY WHERE A CODING TOOL IS CONNECTED (the owner, 2026-10-16: "if no cli tool like cloud api tools no coding.
hipaa ai card if they also have cli tool then they can use coding"). With nothing but a ChatGPT sign-in or an API card, triage
called work "coding", tried to start a CLI that was not there, and the task said "The coding agent couldn't start" until someone
noticed - nothing fell back to the general agent. Now triage is told, its answer cannot say coding, and a coding verdict that
slips through is the general agent's."""
import json, unittest
from unittest import mock

from taskuary import agents, triage
from taskuary.store import MemoryStore


class CodingReadyTests(unittest.TestCase):
    def test_a_connected_cli_that_starts_here_is_what_makes_coding_possible(self):
        s = MemoryStore()
        with mock.patch.object(agents, 'connection_brains', return_value=[]):
            self.assertFalse(agents.coding_ready.real(s))
        with mock.patch.object(agents, 'connection_brains', return_value=[('claude', {'cmd': 'claude'})]), \
             mock.patch.object(agents, 'runs_here', return_value=True):
            self.assertTrue(agents.coding_ready.real(s))
        with mock.patch.object(agents, 'connection_brains', return_value=[('claude', {'cmd': 'claude'})]), \
             mock.patch.object(agents, 'runs_here', return_value=False):
            self.assertFalse(agents.coding_ready.real(s), 'configured but not on this computer is not a tool that can start')


class TriageTests(unittest.TestCase):
    MSG = {'subject': 'The export script writes empty files', 'body': 'Can you fix the export script?', 'from': 'erin@northwind.example'}

    def verdict(self, coding, kind='coding'):
        seen = {}
        def brain(system, user, **kw):
            seen.update(system=system, want=kw.get('want'))
            return json.dumps({'intent': 'task', 'why': 'asks for a fix', 'kind': kind, 'title': 'Fix the export', 'summary': 's'})
        out = triage.classify_intent(self.MSG, llm=brain, coding=coding)
        return out, seen

    def test_without_a_tool_triage_is_told_and_its_answer_cannot_say_coding(self):
        out, seen = self.verdict(coding=False)
        self.assertIn('NO CODING TOOL', seen['system'])
        if seen['want']:
            self.assertNotIn('coding', json.dumps(seen['want']['schema']['properties']['kind']))
        self.assertEqual(out.get('kind'), 'general', 'a coding verdict that slips through is the general agent\'s')

    def test_with_a_tool_nothing_changes(self):
        out, seen = self.verdict(coding=True)
        self.assertNotIn('NO CODING TOOL', seen['system'])
        self.assertEqual(out.get('kind'), 'coding')


class OfferedTests(unittest.TestCase):
    def test_capabilities_say_whether_coding_exists(self):
        from fastapi.testclient import TestClient
        from taskuary import server
        s = MemoryStore()
        with mock.patch.object(server, 'store', s), mock.patch.object(agents, 'coding_ready', return_value=False):
            self.assertEqual(TestClient(server.app).get('/api/capabilities').json(), {'coding': False})


class AssistantTests(unittest.TestCase):
    def test_send_to_agent_and_its_alternatives_never_offer_a_coding_agent_without_a_tool(self):
        from taskuary import concierge
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export script', 'Kind': 'coding'}, 'test')
        with mock.patch.object(agents, 'coding_ready', return_value=False):
            self.assertEqual(concierge.triage_agent(s, {'tid': tid}), 'regular_agent')
            self.assertIn('no coding tool is connected', concierge.cannot({'tid': tid}, 'coding_agent', s))
        with mock.patch.object(agents, 'coding_ready', return_value=True):
            self.assertEqual(concierge.triage_agent(s, {'tid': tid}), 'coding_agent')
