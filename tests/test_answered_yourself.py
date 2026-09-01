"""You answered it in Teams. The Timeline has to know that, or it nags you forever.

Every state the Timeline can show - waving, working, reply, todo - is about what TASKUARY did.
There was no word for the commonest ending of all: the owner read the message and answered it
themselves, in Teams or Outlook, thirty seconds later, and never came back here. Those replies
ARE ingested - channels.ingest_own_message stores them as `context` rows on the same
conversation, and its docstring has said "so the panel shows it was answered" since it was
written - but nothing ever read them. So the message stayed "on your list", permanently, and the
needs-me count was wrong by however many things you had already dealt with.
"""
import unittest

from taskuary.store import MemoryStore

CONV = 'teams:19:mindy'


def _store():
    return MemoryStore()


def _line(s, who, body, at, status='filed', conv=CONV, ext=None):
    return s.add_message({'ExternalId': ext or f'{who}:{at}', 'ConversationId': conv, 'Channel': 'teams',
                          'SourceName': 'me@ours.com', 'Subject': 'Teams chat with Mindy',
                          'FromName': who, 'SentAt': at, 'BodyText': body, 'Status': status})


def _row(s, mid):
    return {r['MessageId']: r for r in s.feed(limit=100)}[mid]


class AnsweringItYourself(unittest.TestCase):
    def setUp(self):
        self.s = _store()
        self.mid = _line(self.s, 'Mindy', 'did you send it?', '2026-08-31 12:41:00')
        tid = self.s.create_task({'Title': 'did you send it?', 'Kind': 'task', 'Status': 'open'}, 'o')
        self.s.attach_message(self.mid, tid)

    def test_before_you_answer_it_is_on_you(self):
        r = _row(self.s, self.mid)
        self.assertIsNone(r['AnsweredAt'])
        self.assertEqual(r['NeedsYou'], 1)

    def test_your_reply_in_teams_takes_it_off_your_list(self):
        _line(self.s, 'You', 'sent this morning', '2026-08-31 12:44:00', status='context')
        r = _row(self.s, self.mid)
        self.assertEqual(r['AnsweredAt'], '2026-08-31 12:44:00')
        self.assertEqual(r['NeedsYou'], 0)

    def test_a_reply_BEFORE_the_message_does_not_count(self):
        """Answering yesterday is not answering this. Only a later line closes it."""
        _line(self.s, 'You', 'unrelated earlier line', '2026-08-31 09:00:00', status='context')
        r = _row(self.s, self.mid)
        self.assertIsNone(r['AnsweredAt'])
        self.assertEqual(r['NeedsYou'], 1)

    def test_a_reply_on_another_conversation_does_not_count(self):
        _line(self.s, 'You', 'to somebody else', '2026-08-31 13:00:00', status='context', conv='teams:19:other')
        self.assertIsNone(_row(self.s, self.mid)['AnsweredAt'])

    def test_the_newest_of_several_replies_is_the_one_reported(self):
        _line(self.s, 'You', 'first', '2026-08-31 12:44:00', status='context')
        _line(self.s, 'You', 'and again', '2026-08-31 12:50:00', status='context')
        self.assertEqual(_row(self.s, self.mid)['AnsweredAt'], '2026-08-31 12:50:00')

    def test_a_pending_draft_still_outranks_it(self):
        """A decision nobody has taken is still on you, however the thread went on."""
        _line(self.s, 'You', 'sent this morning', '2026-08-31 12:44:00', status='context')
        self.s.add_review({'MessageId': self.mid, 'Kind': 'draft_reply', 'Status': 'pending'})
        self.assertEqual(_row(self.s, self.mid)['NeedsYou'], 1)

    def test_an_inbound_reply_from_them_is_not_you_answering(self):
        """Only the owner's own lines are `context`. Mindy writing again is not an answer."""
        _line(self.s, 'Mindy', 'anyone?', '2026-08-31 13:10:00')
        r = _row(self.s, self.mid)
        self.assertIsNone(r['AnsweredAt'])
        self.assertEqual(r['NeedsYou'], 1)

    def test_a_row_with_no_conversation_id_is_never_matched_by_accident(self):
        s = _store()
        mid = s.add_message({'ExternalId': 'lone', 'Channel': 'email', 'SourceName': 'me',
                             'Subject': 'x', 'FromName': 'Sam', 'SentAt': '2026-08-31 10:00:00',
                             'BodyText': 'hello', 'Status': 'filed'})
        s.add_message({'ExternalId': 'lone2', 'Channel': 'email', 'SourceName': 'me', 'Subject': 'y',
                       'FromName': 'You', 'SentAt': '2026-08-31 11:00:00', 'BodyText': 'hi',
                       'Status': 'context'})
        self.assertIsNone(_row(s, mid)['AnsweredAt'])


if __name__ == '__main__':
    unittest.main()
