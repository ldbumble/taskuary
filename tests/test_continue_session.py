"""Continue session (A19, the owner, 2026-09-25): a pill on work an agent left - stopped, saved by you, or paused when
Taskuary stopped - for coding and non-coding agents alike, with what to tell it as it picks up."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, messengers, remote_assistant as ra, server
from taskuary.store import MemoryStore

JID = '15550001234@s.whatsapp.net'


class PillTests(unittest.TestCase):
    def test_it_leads_on_stopped_saved_and_paused_work(self):
        s = MemoryStore()
        for extra in ({'lane': 'stopped'}, {'lane': 'saved'}, {'lane': 'blocked', 'paused': True, 'kind': 'agent'}):
            item = {'key': 'k', 'kind': 'todo', 'tid': 7, 'ref': 'TQ-0007', **extra}
            self.assertEqual(concierge.chips_for(s, item)[0]['label'], 'Continue session', extra)
        self.assertNotIn('continue', [c['verb'] for c in concierge.chips_for(s, {'key': 'k', 'kind': 'todo', 'tid': 7, 'lane': 'yours'})])


class OneRoadTests(unittest.TestCase):
    def test_a_regular_agent_resumes_its_conversation_with_the_note_first(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Draft the vendor letter', 'Kind': 'general', 'Status': 'open'}, 'o')
        session = mock.Mock()
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), \
             mock.patch('taskuary.general.start_session', return_value=session), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)):
            out = TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'use the new letterhead'}).json()
        self.assertEqual(out['kind'], 'general')
        self.assertEqual(session.send_prompt.call_args[0][0], 'use the new letterhead')

    def test_a_coding_agent_reopens_its_own_session_or_a_fresh_one(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(server, '_resumable', return_value=({'Agent': 'coder'}, '')), \
             mock.patch.object(server, 'continue_session', return_value={'session': 'sid'}) as reopen:
            out = TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'run the tests first'}).json()
        self.assertTrue(out['resumed']); self.assertEqual(reopen.call_args[0][1].instruction, 'run the tests first')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(server, '_resumable', return_value=(None, 'no saved session')), \
             mock.patch.object(server, 'continue_task', return_value={'session': 'sid'}) as fresh:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
        fresh.assert_called_once()


class PhoneTests(unittest.TestCase):
    def test_the_pick_asks_and_the_next_typed_line_is_the_note(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        item = {'key': 'k', 'kind': 'todo', 'tid': tid, 'ref': 'TQ-0001', 'lane': 'stopped'}
        ra._ASKING.chat = {'channel': 'whatsapp', 'chat': JID, 'connector_id': None}
        try: asked = ra.run_act(s, {'t': 'verb', 'verb': 'continue', 'key': 'k'}, item)
        finally: ra._ASKING.chat = None
        self.assertIn('Continue as is', asked)
        with mock.patch.object(messengers, 'wa_send'), mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 99}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=None), \
             mock.patch.object(concierge, 'say', side_effect=AssertionError('the note is not words for the model')), \
             mock.patch.object(ra, '_continue', return_value='Continuing') as cont:
            ra.respond(s, 'whatsapp', JID, 'run the tests first', None)
        cont.assert_called_once_with(s, str(tid), 'run the tests first')


if __name__ == '__main__': unittest.main()
