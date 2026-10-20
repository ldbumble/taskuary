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


    # the 2026-10-19 UI walk (G9): the footer said "15 of 15" over a list cut at eight tasks
    def test_the_totals_count_past_the_caps(self):
        for i in range(search.N_TASKS + 3): self.s.create_task({'Title': f'Certificate batch {i}', 'Kind': 'general', 'Status': 'open'}, 't')
        r = search.everything(self.s, 'certificate')
        self.assertEqual(sum(h['type'] == 'task' for h in r['hits']), search.N_TASKS)
        self.assertEqual(r['totals']['task'], search.N_TASKS + 5)
        self.assertEqual(r['totals']['email'], 1); self.assertFalse(r['capped'])

    # ..."4" listed TQ-0004 fourth, behind three tasks with a 4 in their words
    def test_an_id_typed_outright_comes_first(self):
        for t in ('Close is short by 4,180', 'Year 4 audit', 'Batch 14'): self.s.create_task({'Title': t, 'Kind': 'general', 'Status': 'open'}, 't')
        four = self.s.create_task({'Title': 'Invoice past due', 'Kind': 'general', 'Status': 'done'}, 't')
        for q in (str(four), f'TQ-{four:04d}', f'tq-{four}'):
            self.assertEqual(next(h for h in self.hits(q) if h['type'] == 'task')['tid'], four, q)

    # ..."open" listed every open task: a status is a column of the Tasks tab, asked for here as status:open
    def test_a_status_is_asked_for_by_name_not_matched_as_a_word(self):
        self.assertEqual([h for h in self.hits('open') if h['type'] == 'task'], [])
        self.assertEqual([h['tid'] for h in self.hits('status:done')], [self.old])
        self.assertEqual([h['tid'] for h in self.hits('certificate status:open') if h['type'] == 'task'], [self.tid])
        # the Tasks tab still filters on the column
        self.assertIn(self.tid, [t['TaskId'] for t in self.s.list_tasks(None, q='open')])

    # ...a sender's name listed tasks with nothing on them saying why
    def test_a_task_found_through_its_mail_says_so(self):
        t = self.s.create_task({'Title': 'AP cutover date', 'Kind': 'reply', 'Status': 'open'}, 't')
        mail(self.s, 'AP cutover - Thursday?', 'Are we still on?', 'c9', who='Ray Colton', tid=t, status='routed')
        h = next(x for x in self.hits('Colton') if x['type'] == 'task')
        self.assertEqual((h['tid'], h['why']), (t, 'a mail on it is from Ray Colton'))
        self.assertEqual(next(x for x in self.hits('cutover') if x['type'] == 'task')['why'], '')     # the title shows it

    # ..."Gmail" and "model" found nothing, though a Connections card and four settings are called that
    def test_settings_and_connections_are_found_and_carry_their_link(self):
        g = next(h for h in self.hits('gmail') if h['type'] == 'connector')
        self.assertEqual((g['href'], g['sub']), ('#connector=gmail', 'not connected'))
        k = next(h for h in self.hits('semantic search') if h['type'] == 'setting')
        self.assertEqual(k['href'], '#settings=config&group=Assistant&key=kb_semantic')
        self.assertFalse(any(h['type'] == 'setting' and h['id'] == 'set:funnel_max' for h in self.hits('funnel')))

if __name__ == '__main__':
    unittest.main()
