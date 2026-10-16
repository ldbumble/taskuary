"""A task an agent finished, reopened by new mail on its thread (the owner, 2026-10-14). Its saved conversation is from BEFORE
that mail: the card says so instead of "paused when Taskuary stopped", Continue hands the agent the new mail first, and the
Advisor reads the whole story - what came in, and what is still to do - before it suggests anything."""
import json, unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import advisor, concierge, continuity, funnel, server
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
        args, kw = session.send_prompt.call_args
        self.assertEqual(args[0], continuity.RESUME_PROMPT, 'the owner said nothing - nothing is put in their mouth')
        self.assertIn('What would building it take', kw['delivery_instructions'])

    def test_a_coding_agents_instruction_is_the_owners_note_alone(self):
        s, tid = reopened()
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.handles', return_value=False), \
             mock.patch.object(server, '_resumable', return_value=({'Agent': 'coding'}, '')), \
             mock.patch.object(server, 'continue_session', return_value={'session': 'sid'}) as reopen:
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={'note': 'scope the build'})
            TestClient(server.app).post(f'/api/tasks/{tid}/continue-work', json={})
        # the mail rode the instruction once: labelled FROM THE OWNER, clipped at the tty's ~1 KB command line, left unsent on the
        # prompt (2026-10-14). terminal.resume_seed names the new mail and the context file that holds it; the note is the owner's.
        self.assertEqual([c[0][1].instruction for c in reopen.call_args_list], ['scope the build', None])


class AdvisorReadsTheStoryTests(unittest.TestCase):
    def test_the_prompt_carries_the_mail_since_and_what_is_still_to_do(self):
        s, tid = reopened()
        p = advisor._prompt(s, 'message.attached', {'ref': 'TQ-0001', 'kind': 'agent', 'tid': tid},
                            [{'verb': 'continue', 'label': 'Continue session'}], 1, 'task', tid)
        self.assertIn("NEW SINCE THE AGENT'S LAST TURN (2026-10-13 15:04:16) - its saved conversation is from BEFORE these", p)
        self.assertIn('Paula Vance', p); self.assertNotIn('Any news on the connector', p)
        self.assertIn('STILL TO DO ON THE TASK: Scope what building the connector would take', p)
        self.assertNotIn('Say where the request stands', p)


if __name__ == '__main__':
    unittest.main()


class ClosedConversationTests(unittest.TestCase):
    """A closed task's conversation is read, not typed into; and a close says only what is true of the reply (2026-10-14)."""
    def test_a_message_to_a_closed_task_is_refused_until_it_is_reopened(self):
        s, tid = reopened()
        s.update_task(tid, {'Status': 'done'}, 'owner')
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.general.start_session') as start:
            c = TestClient(server.app)
            for path in ('messages', 'stream'):
                r = c.post(f'/api/tasks/{tid}/assistant/{path}', json={'text': 'one more thing'})
                self.assertEqual((r.status_code, r.json()['detail']), (409, server.CLOSED_CHAT), path)
        start.assert_not_called()

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
