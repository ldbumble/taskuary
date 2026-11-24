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
from test_freshness_walk import reads

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
                                 'Reason': 'needs a reply: question for you', 'Origin': 'triage'})
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

    def test_taskuarys_own_short_send_coming_back_with_the_thread_under_it_is_not_a_second_reply(self):
        """...and the copy that comes back carries the quoted thread under our words. Only a reply of 160 characters or more
        was recognised: a short one ("Thanks, will do") never matched its own copy, so it read "You replied from your mailbox"
        under "Sent by email" and the thread was told the owner had answered outside."""
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = self._inbound(s, status='routed')
        tid = s.create_task({'Title': 'Financial request', 'Kind': 'task', 'Status': 'open'}, 'o')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'March thru June attached.'})
        s.decide_review(rid, 'sent', 'March thru June attached.\n\nAlex Doyle', 'o')
        copy = {**self._sent(), 'body': {'contentType': 'text', 'content': 'March thru June attached.\r\n\r\nAlex Doyle\r\n\r\n'
                                         'From: Client <client@vendor.example>\r\nSent: Sunday, August 16, 2026 8:00 AM\r\nsend March thru June'}}
        ingest_outbound_mail(s, 'me@x.com', copy)
        self.assertEqual(len(s.list_messages(tid)), 2)
        self.assertFalse([c for c in s.list_comments(tid) if 'You replied' in c['Body']])
        # ...and the chat draws it once, as its card: the copy is no "You · by email" bubble under "Sent" (walk 13, every send on both roads)
        from taskuary.conversation import _mail
        self.assertEqual([x['FromName'] for x in _mail(s, tid)], ['Client'])
        # ...while the owner's own different words on the thread still are his reply
        ingest_outbound_mail(s, 'me@x.com', {**self._sent(i='sm2'), 'bodyPreview': 'March attached; June next week.'})
        self.assertTrue([c for c in s.list_comments(tid) if 'You replied' in c['Body']])
        self.assertEqual(sorted(x['FromName'] for x in _mail(s, tid)), ['Client', 'You'], 'his own outside reply still draws as his line')

    def test_a_whatsapp_reply_retires_the_unused_draft_and_says_so(self):
        """Tess answered in WhatsApp after Taskuary drafted a reply. Read against the draft, the line covers it: never leave the old
        Approve button asking the owner to send a second answer (on a chat only when it covers it - the owner, 2026-11-09)."""
        from taskuary import concierge, general
        from taskuary.channels import ingest_own_message
        s = _store()
        mid = s.add_message({'ExternalId': 'wa-in', 'ConversationId': 'whatsapp:tess',
                             'Channel': 'whatsapp', 'SourceName': 'Tess', 'Subject': 'Chat with Tess',
                             'FromName': 'Tess', 'SentAt': '2026-09-04 12:30:00',
                             'BodyText': 'Awesome. 2 pm works. Your house?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Reply to Tess', 'Kind': 'reply', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply',
                            'Status': 'pending', 'DraftText': 'Yes, my house.'})

        with reads('covered'):
            ingest_own_message(s, {'external_id': 'wa-out', 'conversation_id': 'whatsapp:tess',
                                   'channel': 'whatsapp', 'source_name': 'Tess', 'sent_at': '2026-09-04 12:36:00',
                                   'body': 'yes'}, 'your line in this chat - kept for context')

        self.assertEqual(s.get_review(rid)['Status'], 'superseded')
        self.assertEqual(s.get_task(tid)['Status'], 'open')             # answered, and open for Mark done (2026-10-18)
        self.assertEqual(_row(s, mid)['NeedsYou'], 0)
        # ...said on the task it settled, never in the Assistant's conversation (the owner, 2026-10-06: the task being
        # worked is the main thing there, nothing else)
        # ...one line, never quoting the owner's words again - their line stands on the chat's left (the owner, 2026-11-09)
        self.assertIn('You answered Tess yourself - no new response needed.', [c['Body'] for c in s.list_comments(tid)])
        dock, _ = general.dock_task(s)
        self.assertFalse([m for m in concierge.history(s, dock['TaskId']) if 'no new response needed' in (m.get('text') or '')])

    def test_a_draft_his_mailbox_reply_retired_stays_greyed_in_its_place_saying_he_answered(self):
        """The stress round, 2026-11-18 (invented people): a reply to Erin waited; the owner answered her from his mailbox. The sync retired
        the draft as `superseded` under a note of its own that no surface knew: the chat drew it with no words and the page had no card for
        it, so the draft he had seen waiting went from the chat. It is a card the thread moved past - greyed where it stood, its words kept,
        saying what happened - and a stale Send on it is refused in that same sentence."""
        from taskuary import conversation, proposals
        from taskuary.channels import ingest_own_message
        s = _store()
        mid = s.add_message({'ExternalId': 'in-1', 'ConversationId': 'conv-venue', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                             'Subject': 'Offsite venue', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                             'SentAt': '2026-11-10 09:00:00', 'BodyText': 'Which venue did we pick?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Erin asks for the venue', 'Kind': 'task', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'We picked the Harbor Hall.'})
        s._exec("UPDATE message SET CreatedAt='2026-11-10 09:00:05' WHERE MessageId=?", (mid,))         # ...it came in that morning,
        s._exec("UPDATE review SET CreatedAt='2026-11-10 09:05:00' WHERE ReviewId=?", (rid,))           # ...drafted a few minutes on
        ingest_own_message(s, {'external_id': 'out-1', 'conversation_id': 'conv-venue', 'channel': 'email', 'source_name': 'alex@northwind.example',
                               'sent_at': '2026-11-10 09:20:00',
                               'body': 'Harbor Hall - booked it this morning.'}, 'your reply')
        self.assertTrue(proposals.passed(s.get_review(rid)))
        card = next(c for x in conversation.items(s, tid)['items'] for c in ([x] if x['kind'] == 'card' else x.get('cards') or []) if c.get('review') == rid)
        self.assertEqual((card['status'], card['was']['text']), ('passed', 'We picked the Harbor Hall.'))
        self.assertEqual(card['why'], 'Not sent - you answered Erin Blake yourself')
        self.assertEqual(proposals.passed_why(s, s.get_review(rid)), card['why'])

    def test_an_earlier_owner_line_does_not_retire_a_later_ask(self):
        from taskuary.channels import ingest_own_message
        s = _store()
        mid = s.add_message({'ExternalId': 'wa-new-ask', 'ConversationId': 'whatsapp:tess',
                             'Channel': 'whatsapp', 'SourceName': 'Tess', 'FromName': 'Tess',
                             'SentAt': '2026-09-04 12:30:00', 'BodyText': 'Your house?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Reply to Tess', 'Kind': 'reply', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply',
                            'Status': 'pending', 'DraftText': 'Yes.'})
        ingest_own_message(s, {'external_id': 'wa-old-out', 'conversation_id': 'whatsapp:tess',
                               'channel': 'whatsapp', 'source_name': 'Tess', 'sent_at': '2026-09-04 12:20:00',
                               'body': 'Earlier answer'}, 'your line in this chat - kept for context')
        self.assertEqual(s.get_review(rid)['Status'], 'pending')


class TheDraftHisAnswerRetiredStaysWhereItStood(unittest.TestCase):
    """A reply was drafted and waited; the owner answered from his mailbox instead. The draft was retired under a note of its own that no
    surface reads as "passed", so the chat dropped the card: no `was` to draw greyed, and the page draws no superseded draft without one -
    the card went from the chat (owner ruling: an answered card stays where it stood, greyed, saying why). Invented people only."""
    def _world(self):
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = s.add_message({'ExternalId': 'in-erin', 'ConversationId': 'c-erin', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                             'Subject': 'Budget numbers', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                             'SentAt': '2026-11-17 08:00:00', 'BodyText': 'Can you send the Q3 numbers?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Send the Q3 numbers', 'Kind': 'reply', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin, attached.'})
        # ...as time had it: her mail came in at 08:00, the draft was written at 08:05, he answered at 09:00
        s._exec("UPDATE message SET CreatedAt='2026-11-17 08:00:00' WHERE MessageId=?", (mid,))
        s._exec("UPDATE route SET CreatedAt='2026-11-17 08:00:00' WHERE MessageId=?", (mid,))
        s._exec("UPDATE review SET CreatedAt='2026-11-17 08:05:00' WHERE ReviewId=?", (rid,))
        ingest_outbound_mail(s, 'alex@northwind.example', {'id': 'out-1', 'subject': 'RE: Budget numbers', 'conversationId': 'c-erin',
                                                            'bodyPreview': 'Here they are.', 'sentDateTime': '2026-11-17T09:00:00'})
        return s, tid, rid

    def test_the_card_stays_greyed_with_its_words_and_says_he_answered(self):
        from taskuary import conversation
        s, tid, rid = self._world()
        card = next(c for x in conversation.items(s, tid)['items'] for c in ([x] if x['kind'] == 'card' else x.get('cards') or [])
                    if c['review'] == rid)
        self.assertEqual(card['status'], 'passed', card)
        self.assertEqual(card.get('was', {}).get('text'), 'Hi Erin, attached.')
        self.assertEqual(card.get('why'), 'Not sent - you answered Erin Blake yourself')

    def test_the_task_says_it_in_one_line_never_his_words_again_nor_a_draft_removed(self):
        """The note said "You replied from your mailbox on TQ-0001: "Here they are.". I removed the unused draft" - his words a second time
        under his own bubble, and a draft "removed" that stands greyed in the chat. One line, the one a chat answer gets (reread_draft)."""
        from taskuary.sessionrecord import NOTE_ACTOR
        s, tid, rid = self._world()
        said = [c['Body'] for c in s.list_comments(tid) if c['Actor'] == NOTE_ACTOR]
        self.assertEqual(said, ['You answered Erin Blake yourself - no new response needed.'])

    def test_mail_polled_together_after_a_restart_still_says_he_answered(self):
        """Taskuary was off overnight. Erin wrote at 08:00 and he answered from his phone at 09:00; at 10:00 the poll took her mail in, the
        draft was written, and the Sent folder's read brought his answer. His mail was placed by when he SENT it, hers by when it ARRIVED, so
        the card read "written before the agent read Erin Blake's new message" - over a draft his own answer had retired."""
        from taskuary import conversation
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = s.add_message({'ExternalId': 'in-erin2', 'ConversationId': 'c-erin2', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                             'Subject': 'Budget numbers', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                             'SentAt': '2026-11-17 08:00:00', 'BodyText': 'Can you send the Q3 numbers?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Send the Q3 numbers', 'Kind': 'reply', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin, attached.'})
        s._exec("UPDATE message SET CreatedAt='2026-11-17 10:00:00' WHERE MessageId=?", (mid,))
        s._exec("UPDATE route SET CreatedAt='2026-11-17 10:00:00' WHERE MessageId=?", (mid,))
        s._exec("UPDATE review SET CreatedAt='2026-11-17 10:00:05' WHERE ReviewId=?", (rid,))
        ingest_outbound_mail(s, 'alex@northwind.example', {'id': 'out-2', 'subject': 'RE: Budget numbers', 'conversationId': 'c-erin2',
                                                            'bodyPreview': 'Here they are.', 'sentDateTime': '2026-11-17T09:00:00'})
        s._exec("UPDATE message SET CreatedAt='2026-11-17 10:00:10' WHERE ExternalId='graph:out-2'")
        card = next(c for x in conversation.items(s, tid)['items'] for c in ([x] if x['kind'] == 'card' else x.get('cards') or [])
                    if c['review'] == rid)
        self.assertEqual(card.get('why'), 'Not sent - you answered Erin Blake yourself')


    def test_a_late_press_on_a_taskless_draft_he_answered_says_so(self):
        """A reply to filed mail has no task. Retired by his answer, a press on it from a stale page crashed reading the task it lacks."""
        from taskuary import verdicts
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = s.add_message({'ExternalId': 'in-fyi', 'ConversationId': 'c-fyi', 'Channel': 'email', 'FromName': 'Erin Blake',
                             'FromEmail': 'erin@northwind.example', 'SentAt': '2026-11-17 08:00:00', 'BodyText': 'Quick one?', 'Status': 'filed'})
        rid = s.add_review({'MessageId': mid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Yes.'})
        ingest_outbound_mail(s, 'alex@northwind.example', {'id': 'out-fyi', 'conversationId': 'c-fyi', 'bodyPreview': 'Yes, go ahead.',
                                                            'sentDateTime': '2026-11-17T09:00:00'})
        out = verdicts.decide(s, s.get_review(rid), 'approve', 'Yes.')
        self.assertFalse(out['ok'])
        self.assertEqual(out['send_error'], 'Not sent - you answered Erin Blake yourself')

class AForwardIsNotTheAnswer(unittest.TestCase):
    """Erin asked; a reply to her waited. The owner forwarded her mail to Gail from Outlook - the forward keeps the conversation. Stored with
    no recipients, it read as his answer to Erin: her draft was retired and the chat said "you answered Erin Blake yourself". His mail now
    keeps whom it went to, and only a draft to someone it reached is answered by it; the rest is the agent's to re-plan."""
    def _world(self, to, cc=()):
        from taskuary.channels import ingest_outbound_mail
        s = _store()
        mid = s.add_message({'ExternalId': 'in-fw', 'ConversationId': 'c-fw', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                             'Subject': 'Budget numbers', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                             'SentAt': '2026-11-17 08:00:00', 'BodyText': 'Can you send the Q3 numbers?', 'Status': 'routed'})
        tid = s.create_task({'Title': 'Send the Q3 numbers', 'Kind': 'reply', 'Status': 'open'}, 'router')
        s.attach_message(mid, tid)
        rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin, attached.'})
        s._exec("UPDATE message SET CreatedAt='2026-11-17 08:00:00' WHERE MessageId=?", (mid,))
        s._exec("UPDATE route SET CreatedAt='2026-11-17 08:00:00' WHERE MessageId=?", (mid,))
        s._exec("UPDATE review SET CreatedAt='2026-11-17 08:05:00' WHERE ReviewId=?", (rid,))
        rcpt = lambda xs: [{'emailAddress': {'address': a}} for a in xs]
        ingest_outbound_mail(s, 'alex@northwind.example', {'id': 'out-fw', 'subject': 'FW: Budget numbers', 'conversationId': 'c-fw',
                                                            'bodyPreview': 'Gail - can you pull these?', 'sentDateTime': '2026-11-17T09:00:00',
                                                            'toRecipients': rcpt(to), 'ccRecipients': rcpt(cc)})
        return s, tid, rid

    def test_a_forward_to_someone_else_leaves_her_draft_to_the_agent(self):
        s, tid, rid = self._world(['gail@northwind.example'])
        self.assertEqual(s.get_review(rid)['Status'], 'pending')
        self.assertFalse([c for c in s.list_comments(tid) if 'removed the unused draft' in c['Body']])
        own = s.get_message(s.thread_messages('c-fw')[-1]['MessageId'])
        self.assertIn('gail@northwind.example', own['RecipientsJson'])

    def test_her_draft_stays_where_it_stood_greyed_once_his_forward_moved_past_it(self):
        """The card stays in its place with its buttons greyed - no reason line (the owner, 2026-11-18) - never taken off the chat."""
        from taskuary import conversation
        s, tid, rid = self._world(['gail@northwind.example'])
        card = next(c for x in conversation.items(s, tid)['items'] for c in ([x] if x['kind'] == 'card' else x.get('cards') or [])
                    if c['review'] == rid)
        self.assertEqual(card['status'], 'passed')                      # greyed as every card an input moved past, until its agent hears it

    def test_with_no_agent_to_hear_it_her_reply_goes_to_an_agent_to_write(self):
        """The reply was the arrival writer's - no agent conversation on the task, so none hears his forward. Greyed as moved past (the chat
        moved on), with nothing at work and nothing lit, it was a dead end. The reply owed goes to an agent to write, as an arrival's does."""
        from unittest import mock
        from taskuary import ingest
        with mock.patch.object(ingest, '_spawn') as spawn:
            s, tid, rid = self._world(['gail@northwind.example'])
        handed = [c.args for c in spawn.call_args_list if c.args and c.args[0] is ingest.reply_to_agent]
        self.assertEqual([(a[2], a[3]) for a in handed], [(tid, rid)], spawn.call_args_list)

    def test_a_reply_to_her_with_gail_copied_still_answers_her(self):
        s, tid, rid = self._world(['Erin@northwind.example'], ['gail@northwind.example'])
        self.assertEqual(s.get_review(rid)['Status'], 'superseded')

    def test_the_agent_is_told_whom_his_mail_went_to(self):
        from taskuary import ingest
        turn = ingest.replan_turn({'channel': 'email', 'body': 'Gail - can you pull these?', 'to': ['gail@northwind.example']}, own=True)
        self.assertIn('to gail@northwind.example', turn.splitlines()[0])
        self.assertNotIn('already answered', turn.splitlines()[0])


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


def test_his_own_mail_that_is_the_drafted_letter_joins_its_task_and_stands_the_draft_down():
    """The Codex walk, 2026-11-22: the agent's new email to Gail, "Harbor signage budget", had no thread; he sent Gail that letter from his
    own mailbox, on a thread of its own - it joined no task, the draft stood "ready to send", and Gail's reply went to an older task. The
    same subject to someone the draft is to is that letter: it joins the draft's task and the draft is not sent. Another subject is not."""
    import json
    from taskuary import channels
    s = MemoryStore()
    tid = s.create_task({'Title': 'Ask Gail about the signage budget', 'Kind': 'general', 'Status': 'open'}, 'owner')
    rid = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Gail - is the signage budget approved?',
                        'Deliver': json.dumps({'channel': 'email', 'to': ['gail@northwind.example'], 'cc': [], 'subject': 'Harbor signage budget'})})
    other = s.add_review({'TaskId': tid, 'Kind': 'slot', 'Status': 'pending', 'DraftText': 'Gail - lunch Friday?',
                          'Deliver': json.dumps({'channel': 'email', 'to': ['gail@northwind.example'], 'cc': [], 'subject': 'Lunch'})})
    channels.ingest_own_message(s, {'external_id': 'sent-1', 'channel': 'email', 'conversation_id': 'thread-new', 'subject': 'Harbor signage budget',
                                    'body': 'Gail - is the Harbor signage budget approved yet? Alex', 'to': ['gail@northwind.example'],
                                    'sent_at': '2026-11-22 21:00:00'}, 'your own mail')
    sent = next(m for m in s.list_messages(tid) if m.get('ExternalId') == 'sent-1')
    assert sent['TaskId'] == tid
    assert s.get_review(rid)['Status'] != 'pending' and s.get_review(other)['Status'] == 'pending'


def test_his_answer_given_outside_answers_the_agents_question_as_his_typed_line_does():
    """Walk 15 (S7, invented people): Erin asked to move Friday's review; the task's agent asked him "Move to 2 p.m. / Keep 10 a.m.?" and he
    answered Erin from his mailbox instead. The waiting draft went grey, but the agent's question stood open - its choices live, the header
    "agent waiting on you", the rail's wave and the phone's list of questions. His own answer is him speaking: it answers the question the
    task's agent asked him, by the road his typed line takes (workerstate.line_answers) - every surface reads that one state."""
    from taskuary import taskstate, workerstate as ws
    from taskuary.channels import ingest_outbound_mail
    s = MemoryStore()
    mid = s.add_message({'ExternalId': 'in-erin3', 'ConversationId': 'c-erin3', 'Channel': 'email', 'SourceName': 'alex@northwind.example',
                         'Subject': 'Friday review', 'FromName': 'Erin Blake', 'FromEmail': 'erin@northwind.example',
                         'SentAt': '2026-11-24 08:00:00', 'BodyText': 'Can we move Friday to 2 p.m.?', 'Status': 'routed'})
    tid = s.create_task({'Title': 'Erin asks to move Friday', 'Kind': 'general', 'Status': 'open'}, 'router')
    s.attach_message(mid, tid)
    rid = s.add_review({'MessageId': mid, 'TaskId': tid, 'Kind': 'draft_reply', 'Status': 'pending', 'DraftText': 'Hi Erin, 2 p.m. is fine.'})
    ws.record(s, tid, 'run-1', 'working', text='Erin asks to move Friday')
    ws.record(s, tid, 'run-1', 'input_needed', request_id='q:0123456789:1', text='Move Friday to 2 p.m.?', choices=['Move to 2 p.m.', 'Keep 10 a.m.'])
    ws.record(s, tid, 'run-1', 'turn_end', text='I asked you about Friday.')
    assert taskstate.open_question(s, tid), 'asked'
    ingest_outbound_mail(s, 'alex@northwind.example', {'id': 'out-3', 'subject': 'RE: Friday review', 'conversationId': 'c-erin3',
                                                        'bodyPreview': '2 p.m. works - see you then.', 'sentDateTime': '2026-11-24T09:00:00'})
    assert s.get_review(rid)['Status'] == 'superseded', 'the draft went grey, as before'
    assert taskstate.open_question(s, tid) is None, 'and the question he answered is answered'
    assert not ws.status(s, tid)['requests']
