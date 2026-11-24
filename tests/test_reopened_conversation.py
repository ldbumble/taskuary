"""A task an agent finished, reopened by new mail on its thread (the owner, 2026-10-14). Its saved conversation is from BEFORE
that mail: the card says so instead of "paused when Taskuary stopped", Continue hands the agent the new mail first, and the
Advisor reads the whole story - what came in, and what is still to do - before it suggests anything."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import concierge, continuity, funnel, general, server
from taskuary.store import MemoryStore


def _at(table, key, rid, when, s):
    s.cx.execute(f'UPDATE {table} SET CreatedAt=? WHERE {key}=?', (when, rid)); s.cx.commit()


def reopened():
    """Finished yesterday - the assistant answered, the reply went - then two people wrote again this morning."""
    s = MemoryStore()
    tid = s.create_task({'Title': 'Check status of the ledger connector request', 'Kind': 'general', 'Status': 'open'}, 'router')
    s.cx.execute('UPDATE task SET Checklist=? WHERE TaskId=?', (json.dumps([{'id': 'a', 'text': 'Say where the request stands', 'done': True},
                 {'id': 'b', 'text': 'Scope what building the connector would take', 'done': False}]), tid))
    _at('comment', 'CommentId', s.add_comment(tid, 'assistant', 'assistant_agent', 'There is no ready-made connector; the reply is drafted.'),
        '2026-10-13 15:04:15', s)
    s.save_session(tid, 'cli:claude', '', 'native-1', 'ctx-1')
    s._exec('UPDATE task SET TrustedThrough=? WHERE TaskId=?', (10 ** 9, tid))      # a thread he trusts: an untrusted sender's task starts no agent (origin.hold)
    s.cx.execute("UPDATE session_resume SET UpdatedAt='2026-10-13 15:04:16' WHERE TaskId=?", (tid,)); s.cx.commit()
    old = s.add_message({'ExternalId': 'm0', 'Channel': 'email', 'Subject': 'Connector status?', 'FromName': 'Gail Moreno',
                         'FromEmail': 'gail@northwind.example', 'BodyText': 'Any news on the connector?', 'TaskId': tid, 'SentAt': '2026-10-13 14:00:00'})
    _at('message', 'MessageId', old, '2026-10-13 14:30:00', s)
    for n, (who, em, body) in enumerate([('Gail Moreno', 'gail@northwind.example', 'Can we just build something ourselves?'),
                                         ('Paula Vance', 'paula@northwind.example', 'What would building it take, versus the vendor gateway?')]):
        mid = s.add_message({'ExternalId': f'm{n + 1}', 'Channel': 'email', 'Subject': 'RE: Connector status?', 'FromName': who,
                             'FromEmail': em, 'BodyText': body, 'TaskId': tid, 'SentAt': f'2026-10-14 09:5{n}:00'})
        _at('message', 'MessageId', mid, f'2026-10-14 09:56:1{n}', s)
    return s, tid


class SinceTheSessionTests(unittest.TestCase):
    def test_only_the_mail_after_the_agents_last_turn_is_news(self):
        s, tid = reopened()
        self.assertEqual(continuity.last_agent_turn(s, tid), '2026-10-13 15:04:16')
        self.assertEqual([m['FromName'] for m in continuity.mail_since(s, tid)], ['Gail Moreno', 'Paula Vance'])
        block = continuity.news_block(s, tid)
        self.assertIn('NEW SINCE YOUR LAST TURN (2026-10-13 15:04:16): 2 messages', block)
        self.assertIn('versus the vendor gateway', block)
        self.assertIn('from BEFORE them', block)

    def test_the_card_says_the_conversation_is_from_before_the_mail_not_that_taskuary_stopped(self):
        s, tid = reopened()
        with mock.patch('taskuary.general.handles', return_value=True), mock.patch('taskuary.general.session_for', return_value=None):
            item = funnel.paused_conversation(s, {'key': 'msg:1', 'kind': 'todo', 'lane': 'asked', 'tid': tid, 'ref': 'TQ-0001', 'title': 't'})
        self.assertEqual(item['why'], "Gail Moreno and Paula Vance wrote again after the assistant's conversation of Oct 13"
                                      ' - continue it and it reads the new mail first')
        self.assertTrue(item['news'])
        said = concierge.fallback(item, True)
        self.assertNotIn('waiting on you', said, 'no agent asked anything')
        self.assertTrue(said.startswith('TQ-0001: Gail Moreno and Paula Vance wrote again'), said)

    def test_a_conversation_said_afresh_says_each_new_mail_once(self):
        # the CI fixer (2026-11-24): the carried-on brief quoted the two new mails, and the fresh prompt's SOURCE MATERIAL said them again
        from taskuary import ingest
        s, tid = reopened()
        s.add_comment(tid, general.BRIEF_ACTOR, general.USER_TYPE, ingest.carry_on_told(s, tid)[0])     # the brief, as send_prompt files it
        with mock.patch('taskuary.general.handles', return_value=True): user = general.prompt_parts(s, tid, turn=True)[2]
        for body in ('Can we just build something ourselves?', 'What would building it take, versus the vendor gateway?'):
            self.assertEqual(user.count(body), 1, body)
        self.assertIn('NEW SINCE YOUR LAST TURN', user)
        self.assertIn('- Paula Vance <paula@northwind.example>', user.split('SOURCE MATERIAL')[0])    # still named as new, above its material
        self.assertIn('versus the vendor gateway', continuity.news_block(s, tid), 'a conversation that goes on still hears the words')

    def test_with_nothing_new_the_card_only_says_it_is_saved(self):
        s, tid = reopened()
        s.cx.execute("UPDATE message SET CreatedAt='2026-10-13 10:00:00'"); s.cx.commit()
        self.assertEqual(continuity.since_line(s, tid, 'the assistant'), "the assistant's conversation from Oct 13 is saved; it can pick up where it left off")
        self.assertEqual(continuity.news_block(s, tid), '')


class ContinueBringsTheMailTests(unittest.TestCase):
    def test_a_regular_agent_gets_the_new_mail_with_its_turn_and_not_as_the_owners_words(self):
        s, tid = reopened()
        session = mock.Mock()
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True), \
             mock.patch('taskuary.general.provider_options', return_value=['x']), \
             mock.patch('taskuary.general.start_session', return_value=session), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
        # THE NEWS LEADS THE TURN (2026-11-03): a resumed CLI is handed the turn alone, so the mail is in it, ahead of Resume's words -
        # filed as Taskuary's brief, never as the owner's words
        args, kw = session.send_prompt.call_args
        self.assertTrue(args[0].startswith('NEW SINCE YOUR LAST TURN') and args[0].endswith(continuity.RESUME_PROMPT), args[0][:80])
        self.assertIn('What would building it take', args[0])
        self.assertEqual((kw['brief'], kw['kept'], bool(kw.get('delivery_instructions'))), (True, True, False))
        said = [(c['Actor'], c['Body']) for c in s.list_comments(tid, internal=True) if c.get('ActorType') == general.USER_TYPE]
        self.assertEqual([a for a, _ in said], [general.BRIEF_ACTOR], "shown in the chat as Taskuary's line, not the owner's")
        self.assertIn('What would building it take', said[0][1])

    def test_the_mail_leads_then_the_owners_note_then_resume(self):
        s, tid = reopened()
        session = mock.Mock()
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=True),              mock.patch('taskuary.general.provider_options', return_value=['x']),              mock.patch('taskuary.general.start_session', return_value=session),              mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)):
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'answer Paula first'})
        # ...his note is his line, taken by the one road (general.take_line, 2026-11-10); the mail since rides with it as Taskuary's
        args, kw = session.send_prompt.call_args
        self.assertEqual(args[0], 'answer Paula first')
        self.assertIn('versus the vendor gateway', kw['delivery_instructions'])
        self.assertEqual([w['text'] for w in general.waiting_lines(s, tid)], ['answer Paula first'], 'kept as his until the turn takes it')
        general.answered(tid, every=True)

    def test_a_coding_agents_instruction_is_the_owners_note_alone(self):
        from taskuary import ingest, terminal
        s, tid = reopened()
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(ingest, '_resumable_coding', return_value=({'Agent': 'coding', 'Cwd': '/w', 'ExtId': 'conv-1'}, '')), \
             mock.patch.object(server, '_brainless', return_value=''), mock.patch.object(server, '_refresh_chat_context', return_value={}), \
             mock.patch('threading.Thread', side_effect=lambda target, **k: mock.Mock(start=target)), \
             mock.patch.object(terminal, 'start_on_task', return_value={'sid': 'sid'}) as reopen:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'scope the build'})
        # the mail rode the instruction once: labelled FROM THE OWNER, clipped at the tty's ~1 KB command line, left unsent on the
        # prompt (2026-10-14). terminal.resume_seed names the new mail and the context file that holds it; the note is the owner's.
        said = reopen.call_args.kwargs['instruction']
        self.assertIn('scope the build', said); self.assertNotIn('vendor gateway', said)
        general.answered(tid, every=True)


if __name__ == '__main__':
    unittest.main()


class ClosedConversationTests(unittest.TestCase):
    """A closed task's conversation is read, not typed into; and a close says only what is true of the reply (2026-10-14)."""
    def test_a_message_to_a_closed_chat_task_reopens_it_and_carries_on(self):
        # the owner, 2026-11-05: "typing into chat should continue it or restart it ... Just type and it continues"
        s, tid = reopened()
        s.update_task(tid, {'Status': 'done'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.start_session') as start:
            start.return_value.send_prompt.return_value = 'On it.'
            TestClient(server.app).post(f'/api/tasks/{tid}/assistant/messages', json={'text': 'one more thing'})
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        start.assert_called_once()

    def test_his_line_is_the_reopen_no_press_line_is_drawn_above_it(self):
        """The Continue round, 2026-11-18, recorded: a chat marked done, then a line typed into it (Continue). His line was drawn at once, and a
        frame later "You reopened it" stood ABOVE it - the store's own reopened row, said as a press, though typing's reopen is quiet (QUIET:
        the line says it). One act, one trace: his line. A Reopen pressed as such still reads "You reopened it"."""
        s, tid = reopened()
        s.update_task(tid, {'Status': 'done'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.start_session') as start:
            start.return_value.send_prompt.return_value = 'On it.'
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'one more thing'})
        general.answered(tid, every=True)
        said = [p['content'][0]['text'] for p in general.press_lines(s, tid)]
        self.assertNotIn('You reopened it.', said)
        from taskuary import events
        self.assertNotIn('reopened it', events.take(s, tid)[0])
        s.update_task(tid, {'Status': 'done'}, 'owner'); s.update_task(tid, {'Status': 'open'}, 'owner')       # ...Reopen, pressed
        self.assertEqual([p['content'][0]['text'] for p in general.press_lines(s, tid)][-1], 'You reopened it.')
        self.assertIn('The owner reopened it.', events.take(s, tid)[0])

    def test_his_words_by_any_road_open_a_closed_task_at_once_and_say_no_press(self):
        """The redesign walk, 2026-11-19: marked done, then he wrote into it - the agent set to work while the task stayed off the rail and its
        header read Reopen for the whole turn, and later the chat said "You reopened it", a press he never made. His words reopen it the moment
        they are taken, whichever road they go: an answer to what its agent asked, words kept for its next stop (the phone), or a line."""
        from taskuary import waitroom, workerstate as ws
        for road in ({'request': 'open'}, {'wake': False}):
            s, tid = reopened()
            concierge.close_task(s, tid, 'owner')
            with mock.patch.object(ws, 'answer_open', return_value={'delivered': True, 'state': 'delivered'}),                  mock.patch.object(waitroom, 'add', return_value={'queued': True}):
                general.to_agent(s, tid, 'The checkout is under C:\work\ledger.', 'owner', frm='owner', **road)
            self.assertEqual(s.get_task(tid)['Status'], 'open', road)
            self.assertNotIn('You reopened it.', [p['content'][0]['text'] for p in general.press_lines(s, tid)], road)

    def test_a_closed_coding_task_typed_into_reopens_by_the_same_rule(self):
        """ONE ROAD (general.take_line, the owner 2026-11-10: "coding and general use the same code when it comes to interactions"): a closed
        coding task was refused "press Reopen, then Continue" while a chat task typed into opened again - now both open the same way."""
        from taskuary import waitroom
        s, tid = reopened()
        s.update_task(tid, {'Status': 'done', 'Kind': 'coding'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.start_session') as start, \
             mock.patch.object(waitroom, 'deliver', return_value={'delivered': 1, 'state': 'restarted'}):
            r = TestClient(server.app).post(f'/api/tasks/{tid}/assistant/messages', json={'text': 'one more thing'})
        self.assertEqual(r.status_code, 200, r.text)
        self.assertEqual(s.get_task(tid)['Status'], 'open')
        start.assert_not_called()
        general.answered(tid, every=True)

    def test_the_writer_is_told_what_went_back_and_who_wrote_since(self):
        s, tid = reopened()
        s.cx.execute("INSERT INTO review (TaskId, Kind, DraftText, Status, CreatedAt) VALUES (?, 'draft_reply', ?, 'pending', ?)",
                     (tid, 'No ready-made connector; we would build one.', '2026-10-13 15:00:00'))
        rid = s.cx.execute('SELECT MAX(ReviewId) FROM review').fetchone()[0]
        s.cx.execute("UPDATE review SET Status='approved', DecidedAt='2026-10-13 15:04:45' WHERE ReviewId=?", (rid,)); s.cx.commit()
        from taskuary.responder import replies_block
        block = replies_block(s, tid)
        self.assertIn('the last reply went out 2026-10-13 15:04:45: No ready-made connector', block)
        self.assertIn("0 drafted reply waiting for the owner's approval", block)
        self.assertIn('written since that reply, by: Gail Moreno, Paula Vance', block)
