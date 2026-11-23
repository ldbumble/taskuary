"""A reply goes to the person its agent wrote it to - never to whoever wrote last (2026-11-02).

A task began from one person's request. Later a second person's separate thread joined it, and her short "Perfect!" was the newest
mail. The session asked the first person a question with `taskuary --reply`: it was filed as a reply to the second person's
"Perfect!", Close out said "Answering" her, and the owner's Send threw the agent's words away for a fresh draft to her - nothing went
to the person the question was for. Now `--to` names the person, the draft keeps that recipient, a line on another thread neither
re-targets nor rewrites it, Send sends it to them, and two letters waiting are two drafts. Invented people throughout.
"""
import tempfile, unittest
from pathlib import Path
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import operations, server, verdicts, wrapup
from taskuary.store import MemoryStore, SQLiteStore

OWNER = 'alex@northwind.example'
ASK = 'Hi Gail,\n\nWhich room rate should I load for 2027 - the private or the semi-private one?\n\nAlex'


def mail(s, tid, ext, conv, who, addr, at, body, status='routed', subject='Budget inputs'):
    return s.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': conv, 'Channel': 'email', 'SourceName': OWNER,
                          'Subject': subject, 'FromName': who, 'FromEmail': addr, 'SentAt': at, 'BodyText': body, 'Status': status,
                          'RecipientsJson': '{"to": ["%s"], "cc": []}' % OWNER})


def world(s):
    """Gail's request opened the task; Paula's separate thread joined it, and her 'Perfect!' (filed, nothing to do) is the newest."""
    tid = s.create_task({'Title': 'Update budget inputs', 'Kind': 'coding', 'Status': 'in_progress', 'Source': 'email'}, 'router')
    gail = mail(s, tid, 'g1', 'AAQk-gail', 'Gail Moreno', 'gail@northwind.example', '2026-11-02 10:40:00', 'Can you update the budget inputs from the sheet?')
    mail(s, tid, 'p1', 'AAQk-paula', 'Paula Vance', 'paula@northwind.example', '2026-11-02 11:41:00', 'Can you add an ancillary revenue input?')
    paula = mail(s, tid, 'p2', 'AAQk-paula', 'Paula Vance', 'paula@northwind.example', '2026-11-02 12:08:00', 'Missed that. Perfect!', status='filed')
    return tid, gail, paula


def to_of(s, rid): return verdicts._envelope(s.get_review(rid)).get('to')


class NoHook(unittest.TestCase):
    def setUp(self): self._prev, wrapup.REFRESH = wrapup.REFRESH, None
    def tearDown(self): wrapup.REFRESH = self._prev


class ToWhom(NoHook):
    def test_reply_to_a_named_person_answers_them_not_the_newest_mail(self):
        s = MemoryStore(); tid, gail, _ = world(s)
        out = wrapup.agent_reply(s, tid, ASK, 'coding', to='Gail Moreno')
        self.assertTrue(out['ok']); self.assertEqual(out['to'], 'Gail Moreno')
        rv = s.get_review(out['review_id'])
        self.assertEqual((rv['MessageId'], rv['DraftText'], rv['DraftBy']), (gail, ASK, 'agent:coding'))
        self.assertEqual(to_of(s, rv['ReviewId']), ['gail@northwind.example'])         # To is pinned at once, to her
        self.assertEqual(wrapup.agent_reply(s, tid, ASK + ' ', 'coding', to='gail@northwind.example')['review_id'], rv['ReviewId'])

    def test_without_to_two_people_waiting_is_asked_whom_never_the_newest_row(self):
        """Walk 6 (CLI F9): with no `to`, the reply the agent wrote for Gail went "To Paula Vance" - the newest row - and it spent a call
        withdrawing it. With two people waiting, a reply says whom it answers; nothing is filed until it does."""
        s = MemoryStore(); tid, gail, paula = world(s)
        out = wrapup.agent_reply(s, tid, 'Glad it helped.', 'coding')
        self.assertFalse(out['ok']); self.assertIn('Paula Vance <paula@northwind.example>', out['why']); self.assertIn('`to`', out['why'])
        self.assertEqual([r for r in s.list_reviews('pending') if r['TaskId'] == tid], [])
        out = wrapup.agent_reply(s, tid, 'Glad it helped.', 'coding', to='Paula')
        self.assertEqual((s.get_review(out['review_id'])['MessageId'], out['to']), (paula, 'Paula Vance'))

    def test_a_name_nobody_on_the_task_has_is_refused_with_who_is(self):
        s = MemoryStore(); tid, _, _ = world(s)
        out = wrapup.agent_reply(s, tid, ASK, 'coding', to='Omar Keller')
        self.assertFalse(out['ok']); self.assertIn('Gail Moreno', out['why']); self.assertIn('--draft', out['why'])
        self.assertEqual([r for r in s.list_reviews('pending') if r['TaskId'] == tid], [])

    def test_a_reply_waiting_for_one_person_is_never_rewritten_into_one_for_another(self):
        s = MemoryStore(); tid, gail, paula = world(s)
        first = wrapup.agent_reply(s, tid, 'Glad it helped.', 'coding', to='Paula')['review_id']
        second = wrapup.agent_reply(s, tid, ASK, 'coding', to='Gail')['review_id']
        self.assertNotEqual(first, second)
        a, b = s.get_review(first), s.get_review(second)
        self.assertEqual((a['MessageId'], a['DraftText'], a['Status']), (paula, 'Glad it helped.', 'pending'))
        self.assertEqual((b['MessageId'], b['DraftText'], b['Status']), (gail, ASK, 'pending'))
        self.assertEqual((to_of(s, first), to_of(s, second)), (['paula@northwind.example'], ['gail@northwind.example']))

    def test_two_waiting_letters_survive_a_restart(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            s = SQLiteStore(str(Path(d) / 't.db')); tid, _, _ = world(s)
            ids = {wrapup.agent_reply(s, tid, 'Glad it helped.', 'coding', to='Paula')['review_id'],
                   wrapup.agent_reply(s, tid, ASK, 'coding', to='Gail')['review_id']}
            s.close()
            s = SQLiteStore(str(Path(d) / 't.db'))
            self.assertEqual({r['ReviewId'] for r in s.list_reviews('pending') if r['TaskId'] == tid}, ids)
            s.close()


class OnePersonManyShapes(NoHook):
    """Walk 6 (HIPAA H7, CLI F9): Gail asked by email for the board pack; Paula asked by chat, a name and no address. Gail's chat line came
    in while the agent wrote her reply - it was told of it seconds later - and the reply bound to that chat line: a chat card that could not
    carry its three files. "to: paula@northwind.example" found "nobody called that", and Gail was listed twice."""
    def world(self):
        from taskuary import conversation
        s = MemoryStore(); s.set_setting('owner_email', OWNER, 'test')
        mail(s, None, 'old', 'AAQk-old', 'Paula Vance', 'paula@northwind.example', '2026-10-01 09:00:00', 'Printer quote attached.', status='filed')
        tid = s.create_task({'Title': 'Board pack', 'Kind': 'general', 'Status': 'in_progress', 'Source': 'email'}, 'router')
        gail = mail(s, tid, 'g1', 'AAQk-gail', 'Gail Moreno', 'gail@northwind.example', '2026-11-23 08:10:00', 'Send me the board pack with the charts?')
        chat = lambda ext, who, at, body: s.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': 'chat-1', 'Channel': 'teams', 'FromName': who,
                                                         'SentAt': at, 'BodyText': body, 'Status': 'routed'})
        paula = chat('t1', 'Paula Vance', '2026-11-23 08:20:00', 'Who prints the pack this time?')
        conversation.hear(s, tid, turn=True)                                       # ...the agent's turn: both are told
        late = chat('t2', 'Gail Moreno', '2026-11-23 08:24:00', 'Also - the headcount is 214.')       # ...in while it writes
        return s, tid, gail, paula, late

    def test_a_reply_binds_to_the_message_its_agent_was_told_of_never_a_newer_one(self):
        s, tid, gail, paula, late = self.world()
        out = wrapup.agent_reply(s, tid, 'Gail - the pack is attached.', 'assistant', to='Gail Moreno')
        self.assertTrue(out['ok'], out); self.assertEqual(s.get_review(out['review_id'])['MessageId'], gail, 'her email, as it was told - never her untold chat line')

    def test_reply_by_email_with_the_file_is_the_same_card_to_her_email(self):
        import json
        s, tid, gail, paula, late = self.world()
        files = [{'name': 'q3_board_pack.pdf', 'size': 41000, 'path': 'pack.pdf'}]
        rid = s.add_review({'TaskId': tid, 'MessageId': late, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Gail - the pack is attached.',
                            'Deliver': json.dumps({'kind': 'reply', 'attachments': files})})
        out = wrapup.by_email(s, rid)
        self.assertTrue(out['ok'], out)
        rv = s.get_review(rid); d = json.loads(rv['Deliver'])
        self.assertEqual((rv['MessageId'], rv['DraftText'], d['to'], d['attachments']), (gail, 'Gail - the pack is attached.', ['gail@northwind.example'], files))
        only_chat = s.add_review({'TaskId': tid, 'MessageId': paula, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Paula - see the pack.'})
        no = wrapup.by_email(s, only_chat)
        self.assertFalse(no['ok']); self.assertIn('Paula Vance sent no email', no['why'])

    def test_a_person_is_found_by_any_shape_of_them_and_named_once(self):
        s, tid, gail, paula, late = self.world()
        out = wrapup.agent_reply(s, tid, 'Paula - Marcus prints it now.', 'assistant', to='paula@northwind.example')
        self.assertTrue(out['ok'], out); self.assertEqual(s.get_review(out['review_id'])['MessageId'], paula)
        self.assertEqual(sorted(wrapup.people_named(s, tid)), ['Gail Moreno <gail@northwind.example>', 'Paula Vance'], 'one person, one name')

    def test_two_conversations_waiting_ask_whom_and_the_owners_own_and_a_machine_are_nobody(self):
        s, tid, gail, paula, late = self.world()
        out = wrapup.agent_reply(s, tid, 'Thanks!', 'assistant')
        self.assertFalse(out['ok']); self.assertIn('Gail Moreno', out['why']); self.assertIn('Paula Vance', out['why'])
        mail(s, tid, 'me', 'AAQk-gail', 'Alex Doyle', OWNER, '2026-11-23 08:30:00', 'On it.')
        ci = mail(s, tid, 'ci', 'AAQk-ci', 'Builds', 'noreply@vendor.example', '2026-11-23 08:31:00', 'Build 212 passed.')
        s._exec("UPDATE message SET SenderClass='automated' WHERE MessageId=?", (ci,))
        self.assertEqual(sorted(n for n in wrapup.people_named(s, tid)), ['Gail Moreno <gail@northwind.example>', 'Paula Vance'])


class SendGoesToThem(NoHook):
    def approve(self, s, rid, text):
        with mock.patch.object(server, 'store', s), mock.patch('taskuary.responder.draft_reply', return_value='Perfect, thanks.') as redraft, \
             mock.patch('taskuary.outbound.reply_to_message', side_effect=lambda st, m, body, to=None, cc=None, attachments=None:
                        {'channel': 'email', 'to': to or [m['FromEmail']], 'cc': cc or []}) as send:
            data = TestClient(server.app).post(f'/api/reviews/{rid}/decide', json={'verb': 'approve', 'final_text': text, 'note': None}).json()
        return data, send, redraft

    def test_a_later_line_on_another_thread_does_not_stop_or_retarget_the_send(self):
        s = MemoryStore(); tid, gail, _ = world(s)
        rid = wrapup.agent_reply(s, tid, ASK, 'coding', follow_up=True, to='Gail Moreno')['review_id']
        mail(s, tid, 'p3', 'AAQk-paula', 'Paula Vance', 'paula@northwind.example', '2026-11-02 12:40:00', 'One more: the census line too?')
        data, send, redraft = self.approve(s, rid, ASK)
        self.assertTrue(data['ok'], data); send.assert_called_once(); redraft.assert_not_called()
        msg, body = send.call_args[0][1], send.call_args[0][2]
        self.assertEqual((msg['MessageId'], msg['FromEmail'], send.call_args[1]['to']), (gail, 'gail@northwind.example', ['gail@northwind.example']))
        self.assertIn('Which room rate', body)
        self.assertTrue(any('gail@northwind.example' in (c['Body'] or '') for c in s.list_comments(tid)))   # Notes say to whom it went

    def test_a_line_on_its_own_thread_interrupts_once_and_keeps_the_agents_words(self):
        s = MemoryStore(); tid, gail, _ = world(s)
        rid = wrapup.agent_reply(s, tid, ASK, 'coding', to='Gail Moreno')['review_id']
        mail(s, tid, 'g2', 'AAQk-gail', 'Gail Moreno', 'gail@northwind.example', '2026-11-02 12:40:00', 'Also - the bad debt rate is .015.')
        data, send, redraft = self.approve(s, rid, ASK)
        self.assertFalse(data['ok']); self.assertTrue(data['stale']); send.assert_not_called(); redraft.assert_not_called()
        self.assertIn('Nothing was sent', data['send_error']); self.assertEqual(data['draft'], ASK)
        rv = s.get_review(rid)
        self.assertEqual((rv['DraftText'], rv['DraftBy'], rv['MessageId'], rv['Status']), (ASK, 'agent:coding', gail, 'pending'))
        data, send, _ = self.approve(s, rid, ASK)                                            # seen now: the next press sends, to her
        self.assertTrue(data['ok'], data); self.assertEqual(send.call_args[1]['to'], ['gail@northwind.example'])

    def test_a_draft_pinned_to_an_fyi_is_not_stale_forever(self):
        # the reply answered a filed "Perfect!", which the material check skips - without a pinned revision it was never current
        s = MemoryStore(); tid, _, paula = world(s)
        rid = wrapup.agent_reply(s, tid, 'Glad it helped.', 'coding', to='Paula')['review_id']
        self.assertEqual(s.get_review(rid)['MessageId'], paula)
        self.assertEqual(verdicts.context_moved(s, s.get_review(rid))[0], False)


class OwnerStartedThread(unittest.TestCase):
    def test_the_owners_reply_stamped_ahead_of_the_mail_it_answers_did_not_start_the_thread(self):
        s = MemoryStore()
        theirs = 'Can you give me a quick call? I need an input added on the budget sheet.'
        s.add_message({'ExternalId': 'o1', 'ConversationId': 'AAQk-new', 'Channel': 'email', 'FromName': 'You', 'FromEmail': OWNER,
                       'SentAt': '2026-11-02 11:41:00', 'Direction': 'out', 'Status': 'context', 'Subject': 'RE: Budget input',
                       'BodyText': f'Send me the sheet and I will update.\n\nFrom: Paula Vance\nSubject: Budget input\n\n{theirs}'})
        s.add_message({'ExternalId': 'i1', 'ConversationId': 'AAQk-new', 'Channel': 'email', 'FromName': 'Paula Vance',
                       'FromEmail': 'paula@northwind.example', 'SentAt': '2026-11-02 11:41:14', 'Status': 'queued', 'Subject': 'Budget input',
                       'BodyText': theirs})
        self.assertIsNone(s.owner_started('AAQk-new'))

    def test_a_thread_the_owner_did_start_is_still_theirs(self):
        s = MemoryStore()
        s.add_message({'ExternalId': 'o1', 'ConversationId': 'AAQk-mine', 'Channel': 'email', 'FromName': 'You', 'FromEmail': OWNER,
                       'SentAt': '2026-11-02 09:00:00', 'Direction': 'out', 'Status': 'context', 'Subject': 'Docs', 'BodyText': 'Here are the docs.'})
        s.add_message({'ExternalId': 'i1', 'ConversationId': 'AAQk-mine', 'Channel': 'email', 'FromName': 'Erin Blake',
                       'FromEmail': 'erin@northwind.example', 'SentAt': '2026-11-02 10:15:00', 'Status': 'queued', 'Subject': 'RE: Docs',
                       'BodyText': 'Thanks - one question about page 2.'})
        self.assertEqual(s.owner_started('AAQk-mine')['ExternalId'], 'o1')


if __name__ == '__main__': unittest.main()
