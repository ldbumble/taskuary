"""Continue (A19, the owner, 2026-09-25): a pill on work an agent left - stopped, saved by you, or paused when
Taskuary stopped - for coding and non-coding agents alike, with what to tell it as it picks up."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import buttons, concierge, messengers, remote_assistant as ra, server
from taskuary.store import MemoryStore

JID = '15550001234@s.whatsapp.net'


class PillTests(unittest.TestCase):
    def test_it_leads_on_stopped_saved_and_paused_work(self):
        s = MemoryStore()
        for extra in ({'lane': 'stopped'}, {'lane': 'saved'}, {'lane': 'blocked', 'paused': True, 'kind': 'agent'}):
            item = {'key': 'k', 'kind': 'todo', 'tid': 7, 'ref': 'TQ-0007', **extra}
            self.assertEqual(concierge.chips_for(s, item)[0]['label'], 'Continue', extra)
        self.assertNotIn('continue', [c['verb'] for c in concierge.chips_for(s, {'key': 'k', 'kind': 'todo', 'tid': 7, 'lane': 'yours'})])

    def test_finished_work_is_closed_or_opened_not_continued(self):
        """An agent that reported done, its session still on file: the row offered Continue after its close (the owner, 2026-10-18:
        "no keep going if finished") - more for it is said in the task's own box."""
        s = MemoryStore()
        with mock.patch.object(s, 'resumable_session', return_value={'ExtId': 'thread-1'}):
            verbs = [c['verb'] for c in concierge.chips_for(s, {'key': 'k', 'kind': 'agentdone', 'tid': 7, 'ref': 'TQ-0007', 'lane': 'report'})]
        self.assertNotIn('continue', verbs); self.assertTrue(verbs, 'it still has moves to offer')

    def test_a_general_agent_is_continued_in_its_chat_so_there_is_no_pill(self):
        """Its card's own chat box is the way on (the owner, 2026-09-29), so the row draws no Continue - and the Advisor, offered
        one, picked it: its line was hidden as a move the row could not make, and the owner got no next step at all (2026-10-15)."""
        s = MemoryStore()
        tid = s.create_task({'Title': 'Look into the census dip', 'Kind': 'general', 'Status': 'in_progress'}, 'o')
        for lane in ('stopped', 'saved'):
            verbs = [c['verb'] for c in concierge.chips_for(s, {'key': 'k', 'kind': 'todo', 'tid': tid, 'lane': lane})]
            self.assertNotIn('continue', verbs, lane); self.assertTrue(verbs, 'it still has moves to offer')


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

    def test_a_general_continue_says_a_turn_is_coming_until_its_thread_has_run(self):
        """The page reloads /assistant as soon as /continue-work answers - before the thread has a session - and polls only while
        it reads busy or `starting`: unmarked, it never saw the continued turn (the agents walk, 2026-10-26)."""
        from taskuary import general
        s = MemoryStore()
        tid = s.create_task({'Title': 'Compare payroll vendors', 'Kind': 'general', 'Status': 'open'}, 'o')
        held = []
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True),              mock.patch('taskuary.general.provider_options', return_value=['x']),              mock.patch('taskuary.general.start_session', return_value=mock.Mock()),              mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=lambda: held.append(target))):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'one more thing'})
            self.assertIn(tid, general.OPENING, 'starting from the answer on')
            held[0]()
        self.assertNotIn(tid, general.OPENING, 'and no longer once the turn has run')

    def test_a_coding_agent_reopens_its_own_session_or_a_fresh_one(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(server, '_resumable', return_value=({'Agent': 'coding'}, '')), \
             mock.patch.object(server, 'continue_session', return_value={'session': 'sid'}) as reopen:
            out = TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'run the tests first'}).json()
        self.assertTrue(out['resumed']); self.assertEqual(reopen.call_args[0][1].instruction, 'run the tests first')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(server, '_resumable', return_value=(None, 'no saved session')), \
             mock.patch.object(server, 'continue_task', return_value={'session': 'sid'}) as fresh:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
        fresh.assert_called_once()

    def test_continue_stays_on_the_cli_that_made_the_conversation_even_when_it_cannot_reopen(self):
        """TQ-0887 shape: codex made the conversation, codex could not reopen it - the way on is a fresh CODEX session with the
        handover, never the default CLI (the owner, 2026-09-30: "it should start as codex if i hit continue of course")."""
        from fastapi import HTTPException
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(server, '_resumable', return_value=({'Agent': 'coding', 'Brain': 'codex'}, '')), \
             mock.patch.object(server, 'continue_session', side_effect=HTTPException(422, 'codex is out of sessions')), \
             mock.patch.object(server, 'continue_task', return_value={'session': 'sid'}) as fresh:
            out = TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'check the E09 mails'}).json()
        self.assertFalse(out['resumed'])
        self.assertEqual(fresh.call_args[0][1].brain, 'codex')
        self.assertIn('check the E09 mails', fresh.call_args[0][1].instruction)
        self.assertIn('fresh codex session', s.list_comments(tid)[-1]['Body'])


class CodexResumeModelTests(unittest.TestCase):
    """TQ-0887: codex's conversation was first opened with claude's model; `codex resume` reused it and every Continue died
    on a 400. A codex resume names codex's own model (2026-09-30)."""
    def test_a_codex_resume_names_codex_own_model(self):
        from taskuary import climodels, terminal
        with mock.patch.object(climodels, 'codex_current', return_value={'model': 'gpt-6'}):
            out = terminal.codex_resume_model(['C:/bin/codex.EXE', '--x', 'resume', 'abc'])
        self.assertEqual(out[-4:], ['resume', 'abc', '-m', 'gpt-6'])

    def test_a_model_asked_for_wins_and_one_already_named_is_left(self):
        from taskuary import terminal
        self.assertEqual(terminal.codex_resume_model(['codex', 'resume', 'abc'], 'gpt-6-mini')[-2:], ['-m', 'gpt-6-mini'])
        self.assertEqual(terminal.codex_resume_model(['codex', '-m', 'x', 'resume', 'abc']), ['codex', '-m', 'x', 'resume', 'abc'])

    def test_other_clis_are_untouched(self):
        from taskuary import terminal
        self.assertEqual(terminal.codex_resume_model(['claude', '--resume', 'abc']), ['claude', '--resume', 'abc'])


class BriefInParagraphsTests(unittest.TestCase):
    """The brief went to the CLI as one 8000-character line, which Claude showed as "(0 lines hidden)" with the task, the
    rules and the mail run together (2026-09-30). On the command line it keeps its paragraphs; typed, it is still one line."""
    def test_blocks_keep_a_blank_line_between_them_and_lose_their_inner_spacing(self):
        from taskuary import terminal
        out = terminal.paragraphs('TASK TQ-0001 - fix   the\nexport\n\n\n  RULES: stay in\n the checkout \n\nFROM Gail Moreno')
        self.assertEqual(out, 'TASK TQ-0001 - fix the export\n\nRULES: stay in the checkout\n\nFROM Gail Moreno')

    def test_typed_into_a_pane_it_is_still_one_line(self):
        from taskuary import terminal
        self.assertNotIn('\n', terminal.fit_typed('TASK one\n\nRULES two\n\nFROM three'))


class PhoneTests(unittest.TestCase):
    def test_the_pick_asks_and_the_next_typed_line_is_the_note(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        item = {'key': 'k', 'kind': 'todo', 'tid': tid, 'ref': 'TQ-0001', 'lane': 'stopped'}
        ra._ASKING.chat = {'channel': 'whatsapp', 'chat': JID, 'connector_id': None}
        try: asked = ra.run_act(s, {'t': 'verb', 'verb': 'continue', 'key': 'k'}, item)
        finally: ra._ASKING.chat = None
        self.assertIn(f"tap {buttons.label('continue')}", asked)
        with mock.patch.object(messengers, 'wa_send'), mock.patch('taskuary.general.dock_task', return_value=({'TaskId': 99}, False)), \
             mock.patch.object(concierge, 'restore_current', return_value=None), \
             mock.patch.object(concierge, 'say', side_effect=AssertionError('the note is not words for the model')), \
             mock.patch.object(ra, '_continue', return_value='Continuing') as cont:
            ra.respond(s, 'whatsapp', JID, 'run the tests first', None)
        cont.assert_called_once_with(s, str(tid), 'run the tests first')


if __name__ == '__main__': unittest.main()
