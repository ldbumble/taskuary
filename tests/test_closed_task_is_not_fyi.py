"""A closed task's mail is not "just for your information".

The shape: a colleague wrote twice with new work on a closed task's thread, triage judged it work, the task
reopened, the owner replied and closed it. Opened again later, the assistant described that mail as "I read it
as just for your information - attached: same conversation thread" - borrowed from the fyi face, which claims a
verdict triage never gave and hides that the owner had already answered. It says what happened instead.
"""
import unittest

from taskuary import concierge, funnel
from taskuary.store import MemoryStore

CID = 'conv-closed-1'


def _mail(s, tid, frm, sent, body, status='routed', direction='in'):
    return s.add_message({'ExternalId': f'x:{frm}:{sent}', 'Channel': 'email', 'Subject': 'RE: Expense export',
                         'FromName': frm.split('@')[0].title(), 'FromEmail': frm, 'SentAt': sent, 'ConversationId': CID,
                         'BodyText': body, 'Status': status, 'Direction': direction, 'TaskId': tid})


class ClosedTaskIsNotFyiTests(unittest.TestCase):
    def setUp(self, reply=True, status='done'):
        s = self.s = MemoryStore()
        self.tid = s.create_task({'Title': 'Export still includes paid items', 'Source': 'email', 'Kind': 'coding'}, 'router')
        _mail(s, self.tid, 'gail@northwind.example', '2026-10-21 06:41:00', 'Was this fixed? It pulled everything again.')
        self.mid = _mail(s, self.tid, 'gail@northwind.example', '2026-10-21 06:49:00', 'Also, paid amounts come back too.')
        s.add_route(self.mid, self.tid, 'attach', 1.0, 'attached: same conversation thread', [])
        if reply: _mail(s, self.tid, 'alex@northwind.example', '2026-10-21 09:33:00', 'Found it, fixed now.', status='context', direction='out')
        s.update_task(self.tid, {'Status': status}, 'owner')

    def _item(self):
        row = next(iter(self.s.feed(limit=1, days=3650, ids=[self.mid])))
        return funnel.from_feed(self.s, [row], canonical=True)[0]

    def test_the_item_says_it_was_handled_not_fyi(self):
        it = self._item()
        self.assertTrue(it.get('closed'))
        self.assertIn('you replied', it['why'])
        self.assertIn('09:33', it['why'])

    def test_the_assistant_says_handled_and_closed(self):
        said = concierge.fallback(self._item(), opening=True, store=self.s)
        self.assertNotIn('just for your information', said)
        self.assertNotIn('same conversation thread', said)
        self.assertIn('Handled - you replied', said)
        self.assertIn('closed', said)

    def test_closed_with_no_reply_says_closed(self):
        self.setUp(reply=False, status='dropped')
        said = concierge.fallback(self._item(), opening=True, store=self.s)
        self.assertNotIn('just for your information', said)
        self.assertIn('closed', said); self.assertNotIn('you replied', said)


if __name__ == '__main__': unittest.main()
