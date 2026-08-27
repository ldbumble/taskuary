"""One word per message (categories.py): the Timeline chip, and the info / automated / promo
split behind it - a colleague's FYI and a vendor's newsletter are both 'nothing to do' and
must not wear the same tag."""
import unittest

from taskuary.categories import category_of, sender_class, team_domains_of
from taskuary.store import MemoryStore

TEAM = {'mfaheritage.net'}
def fyi(**k): return {'MsgStatus': 'filed', 'RouteReason': 'triage: fyi - informational', 'Channel': 'email', **k}


class SenderTests(unittest.TestCase):
    def test_a_colleague_is_a_person(self):
        self.assertEqual(sender_class({'FromEmail': 'leah@mfaheritage.net', 'Preview': 'It can be looked up by GL expense.'}, TEAM), 'person')

    def test_a_vendor_newsletter_is_promo(self):
        self.assertEqual(sender_class({'FromEmail': 'team@anthropic.com', 'Preview': 'Two new ways to browse... Unsubscribe | Manage preferences'}, TEAM), 'promo')
        self.assertEqual(sender_class({'FromEmail': 'noreply@vendor.com', 'Preview': 'Big news! You are receiving this because you signed up.'}, TEAM), 'promo')

    def test_a_robot_is_automated_even_inside_the_team(self):
        self.assertEqual(sender_class({'FromEmail': 'noreply-securityapp@mfaheritage.net', 'Preview': 'Vendor Create'}, TEAM), 'automated')
        self.assertEqual(sender_class({'FromEmail': 'notifications@github.com', 'Preview': 'Run failed... or unsubscribe.'}, TEAM), 'automated')

    def test_chat_is_always_a_person(self):
        self.assertEqual(sender_class({'Channel': 'teams', 'FromEmail': 'noreply@x.com', 'Preview': 'unsubscribe'}, TEAM), 'person')

    def test_an_unknown_human_sender_is_a_person(self):
        self.assertEqual(sender_class({'FromEmail': 'mindy@partnerfirm.com', 'Preview': 'Re: PCC - WHT, see attached'}, TEAM), 'person')


class CategoryTests(unittest.TestCase):
    def test_the_verdict_and_the_sender_make_the_word(self):
        cases = [
            (fyi(FromEmail='leah@mfaheritage.net', Preview='It can be looked up by gl expense.'), 'info'),
            (fyi(FromEmail='team@anthropic.com', Preview='New features. Unsubscribe'), 'promo'),
            (fyi(FromEmail='reports@hrtgcs.com', Preview='MFA Financial Report attached'), 'automated'),
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

    def test_the_feed_carries_the_category(self):
        s = MemoryStore(); s.set_setting('owner_email', 'uri@mfaheritage.net', 't')
        mid = s.add_message({'Channel': 'email', 'Subject': 'RE: Stampli Approvers', 'FromEmail': 'leah@mfaheritage.net',
                             'BodyText': 'It can be looked up by gl expense.', 'Status': 'filed'})
        s.add_route(mid, None, 'file', None, 'triage: fyi - Sender provided informational clarification', [], 'triage')
        mid2 = s.add_message({'Channel': 'email', 'Subject': 'Two new ways to browse the web', 'FromEmail': 'team@claude.com',
                              'BodyText': 'Cowork... Unsubscribe from these emails.', 'Status': 'filed'})
        s.add_route(mid2, None, 'file', None, 'triage: fyi - product announcement', [], 'triage')
        cats = {r['Subject']: r['Category'] for r in s.feed()}
        self.assertEqual(cats, {'RE: Stampli Approvers': 'info', 'Two new ways to browse the web': 'promo'})

    def test_team_domains_come_from_the_owner_and_the_setting(self):
        self.assertEqual(team_domains_of({'owner_email': 'uri@mfaheritage.net', 'team_domains': 'Hrtgcs.com, mfa.org'}),
                         {'mfaheritage.net', 'hrtgcs.com', 'mfa.org'})


if __name__ == '__main__': unittest.main()
