"""A reply that already went is not drafted again.

The agent drafted the reply, the owner sent it, the owner pressed Continue - and the agent drafted ANOTHER reply to the same
sender, which sat in Close out waiting for approval although nothing had come from them since (the owner, 2026-10-20: "I
replied with what the agent created, then reran the agent and it recreated some reply???"). Both sides: the woken agent is
told its reply went, and the `taskuary --reply` door takes a second letter to an answered message only as a follow-up.
"""
import os, unittest
from datetime import date
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import continuity, general, server, terminal, wrapup
from taskuary.store import MemoryStore

T = date.today().isoformat()
REP = {'summary': 'fixed the export', 'outcome': 'did_work', 'determination': '', 'actions': ''}
FIRST = 'Hi Gail - the August export was dropping rows over 10k; fixed and re-run, the file is in the share now.'
AGAIN = 'Hi Gail - following up: the August export is fixed and the file is in the share.'


def world():
    s = MemoryStore()
    tid = s.create_task({'Title': 'August export', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
    mid = mail(s, tid, 'g-1', 'Could you fix the August export?', '09:00:00')
    return s, tid, mid


def mail(s, tid, ext, body, at):
    mid = s.add_message({'TaskId': tid, 'ExternalId': ext, 'ConversationId': 'AAQk-g', 'Channel': 'email',
                         'SourceName': 'alex@northwind.example', 'Subject': 'August export', 'FromName': 'Gail Moreno',
                         'FromEmail': 'gail@northwind.example', 'SentAt': f'{T} {at}', 'BodyText': body, 'Status': 'routed'})
    s._exec('UPDATE message SET CreatedAt=? WHERE MessageId=?', (f'{T} {at}', mid))
    return mid


def send(s, rid, at='17:33:00'):
    """The owner's Send, as the review records it."""
    s._exec("UPDATE review SET Status='approved', FinalText=DraftText, DecidedBy='owner', DecidedAt=? WHERE ReviewId=?", (f'{T} {at}', rid))


def pending(s, tid): return [r for r in s.list_reviews('pending') if r['TaskId'] == tid]


class Base(unittest.TestCase):
    def setUp(self):
        self._prev, wrapup.REFRESH = wrapup.REFRESH, None
        self.s, self.tid, self.mid = world()
        send(self.s, wrapup.agent_reply(self.s, self.tid, FIRST, 'coding')['review_id'])
    def tearDown(self): wrapup.REFRESH = self._prev


class TheDoor(Base):
    def test_a_second_reply_with_nothing_new_from_them_is_refused_and_says_why(self):
        out = wrapup.agent_reply(self.s, self.tid, AGAIN, 'coding')
        self.assertFalse(out['ok']); self.assertTrue(out['already_answered'])
        self.assertIn('a reply to Gail Moreno already went at 05:33 PM', out['why'])
        self.assertIn('--follow-up', out['why'])
        self.assertEqual(pending(self.s, self.tid), [], 'nothing waits in Close out')

    def test_new_mail_from_them_is_a_new_message_to_answer(self):
        new = mail(self.s, self.tid, 'g-2', 'One more - can you also add September?', '18:00:00')
        out = wrapup.agent_reply(self.s, self.tid, AGAIN, 'coding')
        self.assertTrue(out['ok']); self.assertEqual(out['message_id'], new)
        self.assertFalse(wrapup.is_follow_up(self.s.get_review(out['review_id'])), 'an answer to the new mail, not a follow-up')

    def test_the_owner_asking_for_another_is_saved_as_a_follow_up_and_finishing_keeps_saying_so(self):
        out = wrapup.agent_reply(self.s, self.tid, AGAIN, 'coding', follow_up=True)
        self.assertTrue(out['ok'])
        rv = self.s.get_review(out['review_id'])
        # ...its time, and its day when that is not today ("05:33 PM on Oct 27") - CI ran past midnight UTC and the bare time no longer matched
        self.assertRegex(rv['Reason'], r'^a follow-up to your 05:33 PM( on \w{3} \d{1,2})? reply', rv['Reason'])
        with mock.patch('taskuary.responder.write_draft') as redraft: wrapup.finish(self.s, self.tid, REP, None, 'coding')
        redraft.assert_not_called()
        [rv] = pending(self.s, self.tid)
        self.assertEqual(rv['DraftText'], AGAIN); self.assertTrue(wrapup.is_follow_up(rv), rv['Reason'])

    def test_the_owners_own_words_in_the_conversation_since_are_the_ask(self):
        cid = self.s.add_comment(self.tid, 'owner', general.USER_TYPE, 'write Gail a quick note that September is next')
        self.s._exec('UPDATE comment SET CreatedAt=? WHERE CommentId=?', (f'{T} 18:05:00', cid))
        out = wrapup.agent_reply(self.s, self.tid, AGAIN, 'assistant')
        self.assertTrue(out['ok']); self.assertTrue(wrapup.is_follow_up(self.s.get_review(out['review_id'])))

    def test_the_shell_door_carries_follow_up(self):
        with mock.patch.object(server, 'store', self.s), mock.patch.object(server, '_own_task_only', lambda *a: None):
            c = TestClient(server.app)
            self.assertFalse(c.post('/api/agent/reply', json={'task_id': self.tid, 'text': AGAIN, 'agent': 'claude'}).json()['ok'])
            self.assertTrue(c.post('/api/agent/reply', json={'task_id': self.tid, 'text': AGAIN, 'agent': 'claude', 'follow_up': True}).json()['ok'])


class AckBeforeWork(unittest.TestCase):
    def test_an_acknowledgement_sent_before_any_work_still_takes_the_result(self):
        # "looking into it" went before the agent had found anything: the answer is still owed
        s, tid, mid = world()
        rid = s.add_review({'TaskId': tid, 'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'Reason': 'triage'})
        s.update_review_draft(rid, 'Thanks Gail - looking into it.', None); send(s, rid, '09:10:00')
        out = wrapup.agent_reply(s, tid, FIRST, 'coding')
        self.assertTrue(out['ok']); self.assertFalse(wrapup.is_follow_up(s.get_review(out['review_id'])))


class TheEnding(Base):
    def test_a_continued_run_ending_with_nothing_new_drafts_no_second_reply(self):
        with mock.patch('taskuary.responder.write_draft') as redraft:
            out = wrapup.finish(self.s, self.tid, REP, None, 'coding')
        redraft.assert_not_called()
        self.assertFalse(out['drafting']); self.assertEqual(pending(self.s, self.tid), [])
        self.assertTrue(any('already went at 05:33 PM' in c['Body'] for c in self.s.list_comments(self.tid)))

    def test_with_new_mail_the_ending_drafts_as_before(self):
        mail(self.s, self.tid, 'g-2', 'One more - can you also add September?', '18:00:00')
        with mock.patch('taskuary.responder.write_draft', return_value='Sure.') as redraft:
            self.assertTrue(wrapup.finish(self.s, self.tid, REP, None, 'coding')['drafting'])
        redraft.assert_called_once()


class TheAgentIsTold(Base):
    def test_continue_tells_it_the_reply_went_and_nothing_came_since(self):
        news = continuity.news_block(self.s, self.tid)
        self.assertIn('YOUR REPLY WENT OUT: the reply to Gail Moreno was SENT at 05:33 PM', news)
        self.assertIn('nothing new has come from them since', news); self.assertIn('August export was dropping rows', news)

    def test_the_resumed_cli_hears_it_in_its_seed_and_reads_it_in_its_file(self):
        import tempfile
        with tempfile.TemporaryDirectory() as home, mock.patch.dict(os.environ, {'TASKUARY_HOME': home}):
            seed = terminal.resume_seed('', self.s, self.tid)
            from taskuary import context
            text = context.build(self.s, self.tid)
        self.assertIn('YOUR REPLY WENT OUT', seed); self.assertIn('taskuary --follow-up --reply', seed)
        self.assertLess(len(seed.encode()), 1024, 'the seed rides a tty command line')
        self.assertIn('## Replies already SENT on this task', text); self.assertIn(FIRST, text)

    def test_new_mail_since_the_send_is_news_not_a_sent_line(self):
        mail(self.s, self.tid, 'g-2', 'One more - can you also add September?', '18:00:00')
        self.assertEqual(continuity.sent_block(self.s, self.tid), '')


if __name__ == '__main__': unittest.main()
