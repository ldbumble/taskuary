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

CONV = 'teams:19:priya'


def _store():
    return MemoryStore()


def _line(s, who, body, at, status='filed', conv=CONV, ext=None):
    return s.add_message({'ExternalId': ext or f'{who}:{at}', 'ConversationId': conv, 'Channel': 'teams',
                          'SourceName': 'me@ours.com', 'Subject': 'Teams chat with Priya',
                          'FromName': who, 'SentAt': at, 'BodyText': body, 'Status': status})


def _row(s, mid):
    return {r['MessageId']: r for r in s.feed(limit=100)}[mid]


class AnsweringItYourself(unittest.TestCase):
    def setUp(self):
        self.s = _store()
        self.mid = _line(self.s, 'Priya', 'did you send it?', '2026-08-31 12:41:00')
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

    def test_a_draft_created_after_sync_still_notices_you_already_answered(self):
        """Worker ordering cannot resurrect a draft after the real-world reply already landed."""
        _line(self.s, 'You', 'sent this morning', '2026-08-31 12:44:00', status='context')
        rid = self.s.add_review({'MessageId': self.mid, 'Kind': 'draft', 'Status': 'pending',
                                 'Reason': 'needs a reply: question for you'})
        self.assertEqual(self.s.get_review(rid)['Status'], 'superseded')
        self.assertEqual(_row(self.s, self.mid)['NeedsYou'], 0)

    def test_an_inbound_reply_from_them_is_not_you_answering(self):
        """Only the owner's own lines are `context`. Priya writing again is not an answer."""
        _line(self.s, 'Priya', 'anyone?', '2026-08-31 13:10:00')
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


class TheReplyHasToSurviveTheTrip(unittest.TestCase):
    """...which it did not. Reading the Sent folder was only ever half of it: the reply was then
    matched against OPEN tasks and DROPPED when none claimed it. So the two commonest endings -
    you answer a mail Taskuary filed with no task, and you answer a thread whose task closed -
    stored nothing at all, and the row went on saying nothing had happened (owner, 2026-09-02).
    """
    def _sent(self, conv='c9', i='sm1', body='March thru June attached.'):
        return {'id': i, 'subject': 'RE: Financial request', 'conversationId': conv,
                'bodyPreview': body, 'sentDateTime': '2026-08-17T15:00:00Z'}

    def _inbound(self, s, conv='c9', status='filed'):
        return s.add_message({'ExternalId': 'in1', 'ConversationId': conv, 'Channel': 'email',
                              'SourceName': 'me@x.com', 'Subject': 'Financial request', 'FromName': 'Client',
                              'FromEmail': 'client@y.com', 'SentAt': '2026-08-16 08:00:00',
                              'BodyText': 'send March thru June', 'Status': status})

    def test_a_mail_with_no_task_still_learns_that_you_answered_it(self):
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = self._inbound(s)
        ingest_outbound_mail(s, 'me@x.com', self._sent())
        # the stamp is the sent mail's own, in local time - the point is that there IS one
        self.assertEqual(_row(s, mid)['AnsweredAt'], s.thread_messages('c9')[-1]['SentAt'])

    def test_a_reply_after_the_task_closed_lands_on_that_task(self):
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = self._inbound(s, status='routed')
        tid = s.create_task({'Title': 'Financial request', 'Kind': 'task', 'Status': 'open'}, 'o')
        s.attach_message(mid, tid)
        s.update_task(tid, {'Status': 'done'}, 'o')
        ingest_outbound_mail(s, 'me@x.com', self._sent())
        self.assertEqual([m['FromName'] for m in s.list_messages(tid)], ['Client', 'You'])
        self.assertTrue(any('You replied from your mailbox' in c['Body'] for c in s.list_comments(tid)))

    def test_taskuarys_own_send_coming_back_is_not_a_second_reply(self):
        """The Sent folder hands back what we sent ourselves. The timeline already says 'Sent by
        email to...'; a 'You replied' under it read as the owner having answered twice."""
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = self._inbound(s, status='routed')
        tid = s.create_task({'Title': 'Financial request', 'Kind': 'task', 'Status': 'open'}, 'o')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending',
                            'DraftText': 'March thru June attached.'})
        s.decide_review(rid, 'sent', 'March thru June attached.', 'o')
        ingest_outbound_mail(s, 'me@x.com', self._sent())
        self.assertEqual(len(s.list_messages(tid)), 2)                        # still on the thread
        self.assertFalse([c for c in s.list_comments(tid) if 'You replied' in c['Body']])

    def test_a_whatsapp_reply_retires_the_unused_draft_and_says_so(self):
        """Gabi answered in WhatsApp after Taskuary drafted a reply. The sync is the verdict:
        never leave the old Approve button asking the owner to send a second answer."""
        from taskuary import concierge, general
        from taskuary.channels import ingest_own_message
        s = _store()
        mid = s.add_message({'ExternalId': 'wa-in', 'ConversationId': 'whatsapp:gabi',
                             'Channel': 'whatsapp', 'SourceName': 'Gabi', 'Subject': 'Chat with Gabi',
                             'FromName': 'Gabi', 'SentAt': '2026-09-04 12:30:00',
                             'BodyText': 'Awesome. 2 pm works. Your house?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Reply to Gabi', 'Kind': 'reply', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply',
                            'Status': 'pending', 'DraftText': 'Yes, my house.'})

        ingest_own_message(s, {'external_id': 'wa-out', 'conversation_id': 'whatsapp:gabi',
                               'channel': 'whatsapp', 'source_name': 'Gabi', 'sent_at': '2026-09-04 12:36:00',
                               'body': 'yes'}, 'your line in this chat - kept for context')

        self.assertEqual(s.get_review(rid)['Status'], 'superseded')
        self.assertEqual(s.get_task(tid)['Status'], 'done')
        self.assertEqual(_row(s, mid)['NeedsYou'], 0)
        dock, _ = general.dock_task(s)
        said = [m['text'] for m in concierge.history(s, dock['TaskId'])]
        self.assertTrue(any('replied in WhatsApp' in x and 'reply was taken care of' in x for x in said))

    def test_an_earlier_owner_line_does_not_retire_a_later_ask(self):
        from taskuary.channels import ingest_own_message
        s = _store()
        mid = s.add_message({'ExternalId': 'wa-new-ask', 'ConversationId': 'whatsapp:gabi',
                             'Channel': 'whatsapp', 'SourceName': 'Gabi', 'FromName': 'Gabi',
                             'SentAt': '2026-09-04 12:30:00', 'BodyText': 'Your house?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Reply to Gabi', 'Kind': 'reply', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply',
                            'Status': 'pending', 'DraftText': 'Yes.'})
        ingest_own_message(s, {'external_id': 'wa-old-out', 'conversation_id': 'whatsapp:gabi',
                               'channel': 'whatsapp', 'source_name': 'Gabi', 'sent_at': '2026-09-04 12:20:00',
                               'body': 'Earlier answer'}, 'your line in this chat - kept for context')
        self.assertEqual(s.get_review(rid)['Status'], 'pending')


class TheBallIsInTheirCourt(unittest.TestCase):
    """You answered and they have not. The row read "on your list - nobody is on this" for the
    whole of that wait, so "needs me" counted every thread the owner had just dealt with."""
    def setUp(self):
        self.s = _store()
        self.mid = _line(self.s, 'Priya', 'can you send the export?', '2026-08-31 12:41:00', status='routed')
        self.tid = self.s.create_task({'Title': 'send the export', 'Kind': 'coding', 'Status': 'open'}, 'o')
        self.s.attach_message(self.mid, self.tid)

    def test_an_open_task_with_nothing_said_back_is_on_you(self):
        r = _row(self.s, self.mid)
        self.assertEqual((r['TheirTurn'], r['NeedsYou']), (0, 1))

    def test_your_own_last_word_puts_it_in_their_court(self):
        _line(self.s, 'You', 'sent - check your inbox', '2026-08-31 12:50:00', status='context')
        r = _row(self.s, self.mid)
        self.assertEqual((r['TheirTurn'], r['NeedsYou']), (1, 0))

    def test_a_reply_taskuary_sent_counts_even_before_the_channel_echoes_it(self):
        rid = self.s.add_review({'MessageId': self.mid, 'TaskId': self.tid, 'Kind': 'draft_reply', 'Status': 'pending',
                                 'DraftText': 'sent - check your inbox'})
        self.s.decide_review(rid, 'sent', 'sent - check your inbox', 'o')
        r = _row(self.s, self.mid)
        self.assertEqual((r['TheirTurn'], r['NeedsYou']), (1, 0))

    def test_their_next_line_hands_it_back_to_you(self):
        _line(self.s, 'You', 'sent - check your inbox', '2026-08-31 12:50:00', status='context')
        _line(self.s, 'Priya', 'it is empty?', '2026-08-31 13:05:00', status='routed')
        self.assertEqual(_row(self.s, self.mid)['TheirTurn'], 0)

    def test_a_closed_task_is_nobodys_turn(self):
        _line(self.s, 'You', 'done', '2026-08-31 12:50:00', status='context')
        self.s.update_task(self.tid, {'Status': 'done'}, 'o')
        self.assertEqual(_row(self.s, self.mid)['TheirTurn'], 0)


if __name__ == '__main__':
    unittest.main()
