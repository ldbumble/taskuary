"""One search over everything (search.py): tasks, every arrived message whatever became of it, and the sources."""
import unittest
from taskuary import search
from taskuary.store import MemoryStore


def mail(s, subject, body, conv, channel='email', link=None, who='Erin Blake', tid=None, status='filed'):
    return s.add_message({'Channel': channel, 'Subject': subject, 'BodyText': body, 'ConversationId': conv, 'FromName': who,
                          'FromEmail': 'erin@northwind.example', 'SentAt': '2026-10-13 09:00:00', 'SourceLink': link,
                          'SourceName': 'alex@northwind.example', 'TaskId': tid, 'Status': status, 'Direction': 'in',
                          'ExternalId': f'x:{subject}:{conv}'})


class SearchTests(unittest.TestCase):
    def setUp(self):
        self.s = s = MemoryStore()
        self.tid = s.create_task({'Title': 'Renew the portal certificate', 'Summary': 'The certificate lapses in January.',
                                  'Kind': 'general', 'Status': 'open'}, 't')
        self.old = s.create_task({'Title': 'Old certificate question', 'Kind': 'general', 'Status': 'done'}, 't')
        # a forward nobody made a task of - filed, the thing the old box could not find
        self.fw = mail(s, 'Fw: your certificate order expires in 90 days', 'Is this still needed?', 'c1')
        mail(s, 'Re: your certificate order expires in 90 days', 'Also, the certificate renewal quote is attached.', 'c1')
        self.pr = mail(s, 'northwind/portal#12 renew the certificate in CI', 'Bumps the certificate pin.', 'gh:northwind/portal#12',
                       channel='github', link='https://github.example/northwind/portal/pull/12', tid=self.tid, status='routed')
        mail(s, 'northwind/portal#13 certificate warning on login', 'Users see a warning.', 'gh:northwind/portal#13',
             channel='github', link='https://github.example/northwind/portal/issues/13')
        mail(s, '', 'can you check the certificate on the portal', 'teams:1', channel='teams', who='Gail Moreno')
        s.save_source({'Channel': 'email', 'Address': 'certificates@northwind.example', 'Active': 1}, 't')

    def hits(self, q): return search.everything(self.s, q)['hits']

    def test_a_mail_no_task_holds_is_found_by_the_start_of_a_word(self):
        h = [x for x in self.hits('certif still') if x['type'] == 'email']
        self.assertEqual([x['mid'] for x in h], [self.fw])
        self.assertIn('still needed', h[0]['snippet'])

    def test_every_kind_wears_its_pill_and_a_thread_is_one_row(self):
        by = {}
        for x in self.hits('certificate'): by.setdefault(x['type'], []).append(x)
        self.assertEqual(sorted(by), ['chat', 'email', 'issue', 'pr', 'source', 'task'])
        self.assertEqual(len(by['email']), 1); self.assertEqual(by['email'][0]['more'], 1)
        self.assertEqual(by['pr'][0]['title'], '#12 renew the certificate in CI')
        self.assertEqual(by['chat'][0]['title'], 'can you check the certificate on the portal')    # no subject: its own words
        self.assertEqual(by['source'][0]['pick'], 'src:email:certificates@northwind.example')

    def test_a_message_says_the_task_it_is_on_and_open_tasks_come_first(self):
        h = self.hits('certificate')
        self.assertEqual([x['tid'] for x in h if x['type'] == 'task'], [self.tid, self.old])
        self.assertEqual(next(x for x in h if x['type'] == 'pr')['ref'], 'TQ-%04d' % self.tid)

    def test_nothing_typed_is_nothing_found(self):
        self.assertEqual(self.hits('  '), [])
        self.assertEqual(self.hits('zzzz'), [])


if __name__ == '__main__':
    unittest.main()
