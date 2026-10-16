"""One word per message (categories.py): the Timeline chip, and the info / automated / promo
split behind it - a colleague's FYI and a vendor's newsletter are both 'nothing to do' and
must not wear the same tag. WHO sent it is the triage verdict's `sender_class`, or before one
the mail's own list / auto-submission headers - never the address or a footer word (2026-10-11)."""
import email, unittest

from taskuary.categories import category_of, header_class, sender_class, team_domains_of
from taskuary.store import MemoryStore

TEAM = {'northwind.example'}
def fyi(**k): return {'MsgStatus': 'filed', 'RouteReason': 'triage: fyi - informational', 'Channel': 'email', **k}
def hdrs(text): return email.message_from_string(text + '\n\nbody')


class SenderTests(unittest.TestCase):
    def test_nothing_said_is_a_person(self):
        """No verdict, no header: a person - whatever the address or the footer reads like."""
        for em, body in (('info@vendor.example', 'Can you confirm the Q3 figures by Friday?'),
                         ('noreply-securityapp@northwind.example', 'Vendor Create'),
                         ('hello@partner.example', 'Unsubscribe | Manage preferences')):
            with self.subTest(em=em): self.assertEqual(sender_class({'FromEmail': em, 'Preview': body}, TEAM), 'person')

    def test_the_stored_class_decides(self):
        self.assertEqual(sender_class({'FromEmail': 'erin@northwind.example', 'SenderClass': 'automated'}, TEAM), 'automated')
        self.assertEqual(sender_class({'FromEmail': 'news@vendor.example', 'SenderClass': 'bulk'}, TEAM), 'bulk')
        self.assertEqual(sender_class({'FromEmail': 'info@vendor.example', 'SenderClass': 'person'}, TEAM), 'person')
        self.assertEqual(sender_class({'FromEmail': 'x@vendor.example', 'SenderClass': 'robot?'}, TEAM), 'person')   # unknown word: never a robot

    def test_chat_is_always_a_person(self):
        self.assertEqual(sender_class({'Channel': 'teams', 'FromEmail': 'noreply@vendor.example', 'SenderClass': 'bulk'}, TEAM), 'person')


class HeaderClassTests(unittest.TestCase):
    def test_list_headers_are_bulk(self):
        self.assertEqual(header_class(hdrs('List-Unsubscribe: <mailto:u@vendor.example>')), 'bulk')
        self.assertEqual(header_class(hdrs('List-Id: Deals <deals.vendor.example>')), 'bulk')
        self.assertEqual(header_class(hdrs('Precedence: bulk')), 'bulk')

    def test_auto_submission_is_automated_and_outranks_a_list(self):
        self.assertEqual(header_class(hdrs('Auto-Submitted: auto-generated')), 'automated')
        self.assertEqual(header_class(hdrs('X-Auto-Response-Suppress: All\nList-Unsubscribe: <https://ci.example/u>')), 'automated')
        self.assertEqual(header_class(hdrs('Return-Path: <>')), 'automated')

    def test_a_plain_mail_says_nothing(self):
        self.assertIsNone(header_class(hdrs('From: Erin Blake <erin@northwind.example>\nAuto-Submitted: no')))


class CategoryTests(unittest.TestCase):
    def test_the_verdict_and_the_sender_make_the_word(self):
        cases = [
            (fyi(FromEmail='teammate@northwind.example', Preview='It can be looked up by gl expense.'), 'info'),
            (fyi(FromEmail='info@vendor.example', Preview='New features. Unsubscribe'), 'info'),          # no class stored: a person
            (fyi(FromEmail='news@vendor.example', SenderClass='bulk'), 'promo'),
            (fyi(FromEmail='reports@northwind.example', SenderClass='automated'), 'automated'),
            ({'MsgStatus': 'filed', 'RouteReason': 'you already ruled on this conversation', 'Channel': 'email'}, 'filed'),
            ({'MsgStatus': 'ignored', 'Channel': 'email'}, 'ignored'),
            ({'MsgStatus': 'triaging', 'Channel': 'email'}, 'triaging'),
            ({'MsgStatus': 'feed', 'Channel': 'github'}, 'feed'),
            ({'Channel': 'report', 'MsgStatus': 'filed'}, 'report'),
            ({'MsgStatus': 'routed', 'TaskId': 5, 'TaskKind': 'coding', 'Channel': 'github'}, 'coding'),
            ({'MsgStatus': 'routed', 'TaskId': 5, 'TaskKind': 'reply', 'Channel': 'email'}, 'review'),
            ({'MsgStatus': 'routed', 'TaskId': 5, 'TaskKind': 'general', 'Channel': 'teams'}, 'todo'),
            ({'MsgStatus': 'context', 'Direction': 'out', 'Channel': 'email'}, 'yours'),
        ]
        for row, want in cases:
            with self.subTest(want=want): self.assertEqual(category_of(row, TEAM), want)

    def test_the_feed_carries_the_verdicts_class(self):
        s = MemoryStore(); s.set_setting('owner_email', 'alex@northwind.example', 't')
        mid = s.add_message({'Channel': 'email', 'Subject': 'RE: Approvers', 'FromEmail': 'info@northwind.example',
                             'BodyText': 'It can be looked up by gl expense. Please do not reply to this email.', 'Status': 'filed'})
        s.add_route(mid, None, 'file', None, 'triage: fyi - Sender clarified', [], 'triage', verdict={'intent': 'fyi', 'sender_class': 'person'})
        mid2 = s.add_message({'Channel': 'email', 'Subject': 'Two new ways to browse', 'FromEmail': 'erin@vendor.example',
                              'BodyText': 'Cowork...', 'Status': 'filed'})
        s.add_route(mid2, None, 'file', None, 'triage: fyi - product announcement', [], 'triage', verdict={'intent': 'fyi', 'sender_class': 'bulk'})
        cats = {r['Subject']: r['Category'] for r in s.feed()}
        self.assertEqual(cats, {'RE: Approvers': 'info', 'Two new ways to browse': 'promo'})

    def test_the_verdict_outranks_the_headers(self):
        s = MemoryStore()
        mid = s.add_message({'Channel': 'email', 'Subject': 'Board update', 'FromEmail': 'gail@northwind.example',
                             'BodyText': 'Notes from today.', 'Status': 'filed', 'SenderClass': 'bulk'})   # a list header at ingest
        s.add_route(mid, None, 'file', None, 'triage: fyi - notes', [], 'triage', verdict={'intent': 'fyi', 'sender_class': 'person'})
        self.assertEqual(s.get_message(mid)['SenderClass'], 'person')
        self.assertEqual(s.feed()[0]['Category'], 'info')

    def test_team_domains_come_from_the_owner_and_the_setting(self):
        self.assertEqual(team_domains_of({'owner_email': 'alex@northwind.example', 'team_domains': 'Northwind-corp.example, northwind.org'}),
                         {'northwind.example', 'northwind-corp.example', 'northwind.org'})


if __name__ == '__main__': unittest.main()


class RouteHeadTests(unittest.TestCase):
    """The route record leads with WHOSE the work is: "triage: task" read as "on you" on work triage handed to an agent
    (the owner, 2026-10-16). Rows written before keep the old label, and every reader goes through route_intent."""
    def test_the_head_says_whose_it_is(self):
        from taskuary.categories import route_head
        self.assertEqual(route_head('task', 'coding', 'northwind/ledger'), 'work for the coding agent in northwind/ledger')
        self.assertEqual(route_head('task', 'general', 'northwind/ledger'), 'work for the assistant')       # a repo is coding's alone
        self.assertEqual(route_head('task', 'task'), 'yours to do')
        self.assertEqual((route_head('reply_only', 'reply'), route_head('fyi')), ('needs a reply', 'nothing to do'))

    def test_both_wordings_read_back_as_the_verdict(self):
        from taskuary.categories import route_intent, route_why
        for reason, want in (('triage: work for the assistant - x', 'task'), ('triage: task - x', 'task'), ('triage: yours to do', 'task'),
                             ('triage: needs a reply - x', 'reply_only'), ('triage: reply_only - x', 'reply_only'),
                             ('triage: nothing to do - x', 'fyi'), ('triage: fyi - x', 'fyi'), ('not ours - x', '')):
            self.assertEqual(route_intent(reason), want, reason)
        self.assertEqual(route_why('triage: work for the coding agent in org/app - it breaks · new task'), 'it breaks · new task')
        self.assertEqual(category_of({'MsgStatus': 'filed', 'RouteReason': 'triage: nothing to do - a notice', 'Channel': 'email'}), 'info')
