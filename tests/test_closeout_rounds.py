"""CLOSE OUT HAPPENS MORE THAN ONCE (the owner, 2026-11-01: "now that a new message can reopen close out can happen multiple times..
let's update the close out to match the agent runs"). The page stacks its rounds from the task's detail: the replies are its reviews,
and `closeouts` is every close - when, and the note it was closed with - and every reopen, new mail's and a Reopen press's alike.
Invented people; the model is a stub."""
import json, unittest
from unittest import mock

from taskuary import concierge, ingest
from taskuary.store import MemoryStore

CONV = 'fixture-rounds'


def asks(system, user, **k):
    return json.dumps({'intent': 'reply_only', 'why': 'Erin asks Alex directly', 'title': 'Erin asks about the ledger',
                       'summary': 'Erin Blake asks a follow-up about the ledger accounts.', 'asks_owner': True})


class CloseoutRounds(unittest.TestCase):
    def setUp(self):
        s = self.s = MemoryStore()
        self.tid = s.create_task({'Title': 'Missing ledger accounts', 'Kind': 'task', 'Status': 'open', 'Source': 'email'}, 'router')
        self.mid = s.add_message({'TaskId': self.tid, 'Channel': 'email', 'ExternalId': f'{CONV}-1', 'ConversationId': CONV, 'FromName': 'Erin Blake',
                                  'FromEmail': 'erin@northwind.example', 'Subject': 'Missing ledger accounts', 'BodyText': 'Some accounts are missing.',
                                  'SentAt': '2026-10-30 09:00:00', 'Status': 'routed'})

    def reply(self, mid, words):
        rid = self.s.add_review({'TaskId': self.tid, 'MessageId': mid, 'Kind': 'reply', 'DraftText': words, 'Status': 'pending'})
        self.s.decide_review(rid, 'approved', words, 'owner')
        return rid

    def test_a_reply_a_close_and_new_mail_are_two_rounds(self):
        self.reply(self.mid, 'They were folded into 4100.')
        self.assertTrue(concierge.close_task(self.s, self.tid, 'owner'))
        with mock.patch.object(ingest, '_spawn'):
            out = ingest.ingest_message(self.s, {'external_id': f'{CONV}-2', 'channel': 'email', 'from_email': 'erin@northwind.example',
                                                 'from_name': 'Erin Blake', 'conversation_id': CONV, 'subject': 'RE: Missing ledger accounts',
                                                 'body': 'Which of them moved?', 'sent_at': '2026-10-31 09:00:00'}, llm=asks)
        self.assertEqual(out.get('task_id'), self.tid)
        self.assertEqual(self.s.get_task(self.tid)['Status'], 'open')
        d = self.s.task_detail(self.tid)
        self.assertEqual([e['what'] for e in d['closeouts']], ['closed', 'reopened'], 'the door and the write say one reopen')
        self.assertEqual(d['closeouts'][0]['to'], 'done')
        self.assertLessEqual(d['closeouts'][0]['at'], d['closeouts'][1]['at'])
        sent = [r for r in d['reviews'] if r['Status'] == 'approved']
        self.assertEqual((len(sent), sent[0]['MessageId'], sent[0]['FinalText']), (1, self.mid, 'They were folded into 4100.'), 'tied to what it answered')

    def test_a_close_keeps_its_own_note_and_a_reopen_press_starts_the_next(self):
        self.s.add_comment(self.tid, 'owner', 'human', 'Closed out: called Erin, nothing to send')
        concierge.close_task(self.s, self.tid, 'owner')
        self.s.update_task(self.tid, {'Status': 'open'}, 'owner')
        concierge.close_task(self.s, self.tid, 'owner')
        ev = self.s.closeouts(self.tid)
        self.assertEqual([e['what'] for e in ev], ['closed', 'reopened', 'closed'])
        self.assertEqual(ev[0]['note'], 'called Erin, nothing to send')
        self.assertEqual(ev[2]['note'], '', 'the second close was not written with a note')

    def test_a_reopen_press_is_not_an_arrival(self):
        concierge.close_task(self.s, self.tid, 'owner')
        self.s.update_task(self.tid, {'Status': 'open'}, 'owner')
        self.assertIsNone(self.s.reopened_at(self.tid), "the rail's clock moves only for new mail (processing_unread.came_back)")

    def test_a_task_closed_before_the_ledger_keeps_its_close(self):
        self.s.update_task(self.tid, {'Status': 'done'}, 'owner')
        self.s._exec("DELETE FROM outcome WHERE TargetId=?", (self.tid,))
        ev = self.s.closeouts(self.tid)
        self.assertEqual([(e['what'], e['to']) for e in ev], [('closed', 'done')])


if __name__ == '__main__': unittest.main()
