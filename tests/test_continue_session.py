"""Continue (A19, the owner, 2026-09-25): a pill on work an agent left - stopped, saved by you, or paused when
Taskuary stopped - for coding and non-coding agents alike, with what to tell it as it picks up."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import buttons, concierge, continuity, messengers, remote_assistant as ra, server
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
            verbs = [c['verb'] for c in concierge.chips_for(s, {'key': 'k', 'kind': 'agentdone', 'tid': 7, 'ref': 'TQ-0007', 'lane': 'yours'})]
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
        """A note is a line the owner typed, and takes the one road every typed line takes (general.take_line, 2026-11-10): kept as his, then
        his conversation's next turn - the mail since and the Assistant's words ride as Taskuary's, never in his line."""
        from taskuary import general
        s = MemoryStore()
        tid = s.create_task({'Title': 'Draft the vendor letter', 'Kind': 'general', 'Status': 'open'}, 'o')
        session = mock.Mock(alive=True)
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), \
             mock.patch('taskuary.general.start_session', return_value=session), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)):
            out = TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'use the new letterhead'}).json()
        self.assertEqual(out['kind'], 'general')
        args, kw = session.send_prompt.call_args
        self.assertEqual(args[0], 'use the new letterhead')
        self.assertEqual(kw['waiting'], general.waiting_lines(s, tid)[0]['id'], 'the line it kept, which the turn takes')

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

    def test_a_general_continue_writes_the_owners_note_before_it_answers(self):
        """The page reads the conversation the moment /continue-work answers: the note written by the turn, once its CLI had started,
        was missed, and showed seconds later under an agent already "working" (the owner, 0.3.9.51). Kept once, by the one road, before it answers."""
        from taskuary import general
        s = MemoryStore()
        tid = s.create_task({'Title': 'Compare payroll vendors', 'Kind': 'general', 'Status': 'open'}, 'o')
        session, held = mock.Mock(alive=True), []
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), \
             mock.patch('taskuary.general.start_session', return_value=session), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=lambda: held.append(target))):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'look at the south office first'})
            self.assertEqual([w['text'] for w in general.waiting_lines(s, tid)], ['look at the south office first'], 'kept before the turn runs')
            self.assertTrue(general.line_state(s, tid)['working'], 'and at work from the answer on')
            held[0]()
        self.assertIsNotNone(session.send_prompt.call_args.kwargs['waiting'], 'and the turn does not write it a second time')
        general.OPENING.discard(tid)

    def test_a_picture_with_no_note_is_his_line_too(self):
        """The attach stress round, 2026-11-18: Continue's box lets a picture go with no words ("(images)", the page says), and the server took the
        line road only for a note - the picture was dropped and the agent carried on as if nothing was sent. What he attached is a line of his."""
        from taskuary import config, general, outputs
        s = MemoryStore()
        tid = s.create_task({'Title': 'Draft the vendor letter', 'Kind': 'general', 'Status': 'open'}, 'o')
        up = config.home() / 'attachments' / 'prompt' / '209901' / '20991231-235959-abc123-letterhead.png'
        up.parent.mkdir(parents=True, exist_ok=True); up.write_bytes(b'\x89PNG letterhead'); self.addCleanup(up.unlink, missing_ok=True)
        session = mock.Mock(alive=True)
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), \
             mock.patch('taskuary.general.start_session', return_value=session), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': None, 'images': [str(up)]}).json()
        args, kw = session.send_prompt.call_args
        self.assertEqual((args[0], args[1]), ('', [str(outputs.folder(tid) / 'letterhead.png')]))
        self.assertEqual(kw['waiting'], general.waiting_lines(s, tid)[0]['id'], 'his line, kept with its picture')
        general.answered(tid, every=True)

    def test_continue_on_a_session_that_just_ended_goes_to_a_fresh_one(self):
        """The Continue round, 2026-11-18, recorded: a general agent's CLI died mid-turn, and Continue (Try again) was pressed while that session was
        still closing. The press answered "continued", the turn met "this assistant session has ended", and that was logged and said nowhere -
        nothing ran, nothing lit. A typed line in the same spot is handed once to a fresh session (say_line); Continue takes that road too."""
        from taskuary import general
        s = MemoryStore()
        tid = s.create_task({'Title': 'Compare payroll vendors', 'Kind': 'general', 'Status': 'open'}, 'o')
        dying, fresh = mock.Mock(alive=False), mock.Mock(alive=True)
        dying.send_prompt.side_effect = general.Ended()
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), \
             mock.patch('taskuary.general.start_session', side_effect=[dying, fresh]), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)):
            out = TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={}).json()
        self.assertTrue(out['continued'])
        args, kw = fresh.send_prompt.call_args
        self.assertTrue(args[0].endswith(continuity.RESUME_PROMPT)); self.assertEqual((kw['brief'], kw['kept']), (True, True))
        self.assertNotIn(tid, general.OPENING)

    def test_a_coding_agent_reopens_its_own_session_or_a_fresh_one(self):
        from taskuary import general, ingest, terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(ingest, '_resumable_coding', return_value=({'Agent': 'coding', 'Cwd': '/w', 'ExtId': 'conv-1'}, '')), \
             mock.patch.object(server, '_brainless', return_value=''), mock.patch.object(server, '_refresh_chat_context', return_value={}), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)), \
             mock.patch.object(terminal, 'start_on_task', return_value={'sid': 'sid'}) as reopen:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'run the tests first'}).json()
        self.assertEqual(reopen.call_args.kwargs['resume'], 'conv-1'); self.assertIn('run the tests first', reopen.call_args.kwargs['instruction'])
        general.answered(tid, every=True)
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(server, '_resumable', return_value=(None, 'no saved session')), \
             mock.patch.object(server, 'continue_task', return_value={'session': 'sid'}) as fresh:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
        fresh.assert_called_once()

    def test_a_coding_continue_with_only_a_picture_hands_the_picture_over(self):
        """Continue on a coding task with a screenshot and no words: the coding branch never looked at the pictures, so the session
        reopened on the resume prompt alone and what he attached was lost. It is a line like any other (take_line), its file the task's."""
        from taskuary import config, general, ingest, outputs, terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        shot = config.home() / 'attachments' / 'prompt' / '202611' / '20261118-101500-abc123-broken-header.png'
        shot.parent.mkdir(parents=True, exist_ok=True); shot.write_bytes(b'\x89PNG-shot')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(ingest, '_resumable_coding', return_value=({'Agent': 'coding', 'Cwd': '/w', 'ExtId': 'conv-1'}, '')), \
             mock.patch.object(server, '_brainless', return_value=''), mock.patch.object(server, '_refresh_chat_context', return_value={}), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)), \
             mock.patch.object(terminal, 'start_on_task', return_value={'sid': 'sid'}) as reopen:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'images': [str(shot)]}).json()
        self.assertIn(str(outputs.folder(tid) / 'broken-header.png'), reopen.call_args.kwargs['instruction'])
        general.answered(tid, every=True)

    def test_continue_stays_on_the_cli_that_made_the_conversation_even_when_it_cannot_reopen(self):
        """TQ-0887 shape: codex made the conversation, codex could not reopen it - the way on is a fresh CODEX session with the
        handover, never the default CLI (the owner, 2026-09-30: "it should start as codex if i hit continue of course")."""
        from taskuary import general, ingest, terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(ingest, '_resumable_coding', return_value=({'Agent': 'coding', 'Brain': 'codex', 'Cwd': '/w', 'ExtId': 'conv-1'}, '')), \
             mock.patch.object(server, '_brainless', return_value=''), mock.patch.object(server, '_refresh_chat_context', return_value={}), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)), \
             mock.patch.object(terminal, 'start_on_task', side_effect=[ValueError('codex is out of sessions'), {'sid': 'sid'}]) as start:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'check the E09 mails'}).json()
        fresh = start.call_args_list[-1].kwargs
        self.assertEqual(fresh['brain'], 'codex'); self.assertNotIn('resume', fresh)
        self.assertIn('check the E09 mails', fresh['instruction'])
        self.assertTrue(any('fresh codex session' in c['Body'] for c in s.list_comments(tid)))
        general.answered(tid, every=True)


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
    def test_a_note_held_behind_trust_is_said_as_held_never_as_continuing(self):
        """The Continue round, 2026-11-18: Continue from the phone on a stranger's task. The note was kept by the box behind Trust - nothing went
        to an agent - and the phone said "Continuing TQ-0001 with your note - it picks up where it left off". It says what happened: kept, and why."""
        from taskuary import general, origin
        s = MemoryStore()
        tid = s.create_task({'Title': 'Quote request', 'Kind': 'general', 'Status': 'done'}, 'o')
        line = 'You have not trusted Pat Lee (pat@vendor.example) yet - nothing goes to an agent until you do.'
        with mock.patch.object(server, 'store', s), mock.patch.object(origin, 'hold', return_value={'line': line}), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), mock.patch.object(server, '_brainless', return_value=''):
            said = ra._continue(s, str(tid), 'send them our price list')
        self.assertNotIn('Continuing', said); self.assertNotIn('picks up', said)
        self.assertIn('Your note waits on TQ-0001', said); self.assertIn(line, said)
        self.assertEqual([w['text'] for w in general.waiting_lines(s, tid)], ['send them our price list'])

    def test_the_assistant_says_a_held_note_as_held_too(self):
        "The same press from the Assistant's chat said \"Picked up TQ-0001 again with your note\" - one sentence for both (general.kept_held)."
        from taskuary import general, origin
        s = MemoryStore()
        tid = s.create_task({'Title': 'Quote request', 'Kind': 'general', 'Status': 'done'}, 'o')
        dock = s.create_task({'Title': 'Assistant', 'Kind': 'general', 'Status': 'open'}, 'o')
        line = 'You have not trusted Pat Lee (pat@vendor.example) yet - nothing goes to an agent until you do.'
        with mock.patch.object(server, 'store', s), mock.patch.object(origin, 'hold', return_value={'line': line}), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), mock.patch.object(server, '_brainless', return_value=''), \
             mock.patch.object(concierge, 'continuable', return_value=True):
            out = concierge._task_writes(s, dock, 'agent.continue', tid, {'note': 'send them our price list'}, 'TQ-0001', 'owner',
                                         said='send them our price list')
        self.assertEqual(out['say'], f'Your note waits on TQ-0001 - {line}')

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
