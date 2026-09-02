"""Playbooks (docs/beyond-code.md, step 2): one markdown file per kind of job, matched by triage,
seeded into the session, drafted on close as a proposal, and never filed without the owner.
"""
import json, unittest
from unittest import mock

from taskuary import context, ingest, playbooks, proposals, terminal, triage, verdicts
from taskuary.store import MemoryStore

BILL = """# Post a card transaction as an AP bill
when:      a transaction or statement line from the card feed; a mail from the card issuer with a statement
uses:      quickbooks (write: bills, vendors)  ·  teller (read)
steps:     match the merchant to a vendor → pick the expense account → create the bill dated the
           transaction date → attach the receipt
alone:     bills under $500 to a vendor seen before, in an open period
ask first: a new vendor · anything over $500 · a closed period
done when: the bill exists in QuickBooks and its DocNumber is on the task

House rule: the memo is card last-4 + transaction id. ZZMARKPLAYBOOKZZ
"""
ONBOARD = """# Onboard a new hire in the directory
when:      HR mails that somebody starts, with a start date
uses:      azure (write: users, groups) · github (write: org membership)
steps:     create the account → add to the department group → invite to the repository org
alone:     nothing - every new account is asked first
ask first: everything
done when: the account exists and the manager has the sign-in
"""


def _clean():
    import shutil
    d = playbooks.folder()
    if d.is_dir(): shutil.rmtree(d)


class ParseAndFile(unittest.TestCase):
    def setUp(self): _clean()

    def test_the_six_lines_and_the_prose_below(self):
        pb = playbooks.parse(BILL)
        self.assertEqual(pb['title'], 'Post a card transaction as an AP bill')
        self.assertTrue(pb['when'].startswith('a transaction or statement line'))
        # an indented continuation belongs to the line above it
        self.assertIn('attach the receipt', pb['steps'])
        self.assertEqual(playbooks.uses_of(pb), ['quickbooks', 'teller'])
        self.assertIn('ZZMARKPLAYBOOKZZ', pb['body'])
        self.assertFalse(playbooks.about_code(pb))
        self.assertTrue(playbooks.about_code(playbooks.parse(ONBOARD)))     # github on uses = code rules apply

    def test_write_list_read_delete(self):
        self.assertEqual(playbooks.list_all(), [])
        slug = playbooks.write('new', BILL)                                   # 'new' files it under its title
        self.assertEqual(slug, 'post-a-card-transaction-as-an-ap-bill')
        playbooks.write('onboard', ONBOARD)
        books = playbooks.list_all()
        self.assertEqual([b['slug'] for b in books], [slug, 'onboard'])
        self.assertEqual([b['slug'] for b in playbooks.for_connector('quickbooks')], [slug])
        self.assertEqual([b['slug'] for b in playbooks.for_connector('github')], ['onboard'])
        self.assertIn('ZZMARKPLAYBOOKZZ', playbooks.read(slug))
        with self.assertRaises(ValueError): playbooks.write('bad', 'no title, no when')
        self.assertTrue(playbooks.delete('onboard')); self.assertFalse(playbooks.delete('onboard'))
        self.assertEqual(len(playbooks.list_all()), 1)

    def test_the_menu_is_what_triage_sees(self):
        playbooks.write('bill', BILL)
        m = playbooks.menu()
        self.assertIn('- bill: Post a card transaction as an AP bill - when: a transaction', m)
        self.assertEqual(playbooks.menu([]), '')

    def test_the_template_is_a_valid_playbook(self):
        pb = playbooks.parse(playbooks.template())
        self.assertTrue(pb['title'] and pb['when'] and pb['done when'])
        self.assertEqual(playbooks.uses_of(pb), ['quickbooks', 'teller'])


def _llm_saying(answer):
    seen = {}
    def llm(system, user, **kw):
        seen['system'], seen['user'] = system, user
        return json.dumps(answer)
    return llm, seen


class TriageNamesThePlaybook(unittest.TestCase):
    def setUp(self):
        _clean(); playbooks.write('bill', BILL)
        self.msg = {'from_email': 'alerts@card.example', 'subject': 'Transaction: 84.10 at a hardware store',
                    'body': 'A new transaction posted to card ending 4412.'}

    def test_the_menu_rides_and_the_slug_comes_back_as_a_coding_task(self):
        llm, seen = _llm_saying({'intent': 'task', 'kind': 'task', 'why': 'a card line', 'playbook': 'bill'})
        out = triage.classify_intent(self.msg, llm=llm, playbooks=playbooks.menu())
        self.assertIn('PLAYBOOKS', seen['system']); self.assertIn('- bill: ', seen['system'])
        self.assertEqual((out['playbook'], out['kind']), ('bill', 'coding'))   # an agent works a playbook, whatever kind said

    def test_a_slug_the_menu_never_offered_is_ignored(self):
        llm, _ = _llm_saying({'intent': 'task', 'kind': 'coding', 'why': 'x', 'playbook': 'made-up'})
        self.assertNotIn('playbook', triage.classify_intent(self.msg, llm=llm, playbooks=playbooks.menu()))

    def test_no_playbooks_no_paragraph(self):
        llm, seen = _llm_saying({'intent': 'fyi', 'why': 'x'})
        triage.classify_intent(self.msg, llm=llm, playbooks='')
        self.assertNotIn('PLAYBOOKS', seen['system'])

    def test_ingest_tags_the_task_and_says_so(self):
        s = MemoryStore()
        llm, seen = _llm_saying({'intent': 'task', 'kind': 'coding', 'why': 'a card line', 'playbook': 'bill'})
        out = ingest.ingest_message(s, {'channel': 'email', 'external_id': 'pb1', **self.msg}, llm=llm)
        t = s.get_task(out['task_id'])
        self.assertEqual(playbooks.of_task(t), 'bill')
        self.assertIn('- bill: ', seen['system'])
        self.assertIn('playbook bill', s.feed()[0]['RouteReason'])


class TheSessionRunsOnIt(unittest.TestCase):
    def setUp(self): _clean(); playbooks.write('bill', BILL)

    def _task(self, s, tags='playbook:bill'):
        tid = s.create_task({'Title': 'Transaction: 84.10', 'Kind': 'coding', 'Source': 'email', 'Tags': tags}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': f'm{tid}', 'Channel': 'email', 'Subject': 'Transaction',
                       'FromEmail': 'alerts@card.example', 'BodyText': 'a new transaction posted', 'Status': 'routed'})
        return tid

    def test_the_seed_carries_the_playbook_and_says_it_is_not_code(self):
        s = MemoryStore(); s.save_doc('coder', '# Coder rules\n- ZZMARKCODERZZ', 'owner')
        seed = terminal.seed_text(s, self._task(s))
        self.assertIn('PLAYBOOK "Post a card transaction as an AP bill"', seed)
        self.assertIn('ASK FIRST: a new vendor', seed)
        self.assertIn('ZZMARKPLAYBOOKZZ', seed)
        self.assertIn('NOT A CODE CHANGE', seed)
        self.assertIn('ZZMARKCODERZZ', seed)          # the closing-out and wall rules still ride
        # a task without the tag gets none of it
        self.assertNotIn('PLAYBOOK', terminal.seed_text(s, self._task(s, tags='')))

    def test_a_code_playbook_keeps_the_repository_rules_unqualified(self):
        playbooks.write('onboard', ONBOARD)
        s = MemoryStore()
        seed = terminal.seed_text(s, self._task(s, tags='playbook:onboard'))
        self.assertIn('PLAYBOOK "Onboard a new hire', seed); self.assertNotIn('NOT A CODE CHANGE', seed)

    def test_the_context_file_carries_the_whole_page(self):
        s = MemoryStore()
        text = context.build(s, self._task(s))
        self.assertIn('## The playbook for this kind of job (bill.md', text)
        self.assertIn('House rule: the memo is card last-4', text)


# a real session's worth of screen: shorter than playbooks.MIN_SESSION is judged to have done no job
SESSION = 'matched the hardware store to vendor 87, expense account 6120, created bill 1043 for 84.10. ' * 8


class DraftedOnClose(unittest.TestCase):
    def setUp(self): _clean()

    def _task(self, s, tags=''):
        return s.create_task({'Title': 'Post the hardware store charge', 'Kind': 'coding', 'Tags': tags}, 't')

    def test_a_recurring_job_becomes_a_proposal_not_a_file(self):
        s = MemoryStore(); tid = self._task(s)
        llm, seen = _llm_saying({'playbook': {'slug': 'card-bill', 'text': BILL, 'why': 'every card line needs this'}})
        made = playbooks.draft(s, tid, SESSION, llm=llm)
        self.assertEqual(made['action'], 'write_playbook')
        self.assertIn('Playbooks already on file', seen['user'])
        self.assertEqual(playbooks.list_all(), [])                        # nothing on disk yet
        rv = s.list_reviews('pending')[0]
        self.assertEqual(rv['Kind'], 'action'); self.assertIn('file a new PLAYBOOK', rv['Reason'])
        # approving files it - and an edit made in the Review box is what gets filed
        edited = BILL.replace('bills under $500', 'bills under $200')
        out = verdicts.decide(s, rv, 'approve', edited, None, 'owner')
        self.assertEqual(out['result']['playbook'], 'card-bill')
        self.assertIn('bills under $200', playbooks.read('card-bill'))

    def test_usually_nothing(self):
        s = MemoryStore(); tid = self._task(s)
        llm, _ = _llm_saying({'playbook': None})
        self.assertIsNone(playbooks.draft(s, tid, SESSION, llm=llm))
        self.assertEqual(s.list_reviews('pending'), [])
        self.assertIsNone(playbooks.draft(s, tid, 'fixed the importer', llm=lambda *a, **k: 1 / 0))   # too short: no AI call at all

    def test_the_second_run_and_a_duplicate_slug_draft_nothing(self):
        s = MemoryStore()
        llm, _ = _llm_saying({'playbook': {'slug': 'bill', 'text': BILL}})
        self.assertIsNone(playbooks.draft(s, self._task(s, tags='playbook:bill'), SESSION, llm=llm))
        playbooks.write('bill', BILL)
        self.assertIsNone(playbooks.draft(s, self._task(s), SESSION, llm=llm))

    def test_the_switch_and_the_agent_road(self):
        s = MemoryStore(); tid = self._task(s)
        # an agent may propose one itself, in the transcript; the same gate applies
        made = proposals.collect(s, tid, 'TASKUARY-PROPOSE ' + json.dumps({'action': 'write_playbook', 'slug': 'bill', 'text': BILL}))
        self.assertEqual([m['action'] for m in made], ['write_playbook'])
        s.set_setting('playbooks_enabled', '0', 'owner')
        self.assertEqual(proposals.validate(s, {'action': 'write_playbook', 'slug': 'x', 'text': BILL})[0], False)
        llm, _ = _llm_saying({'playbook': {'slug': 'other', 'text': ONBOARD}})
        self.assertIsNone(playbooks.draft(s, tid, SESSION, llm=llm))

    def test_wrap_asks_the_question(self):
        """coder.wrap is the one on-close road; the draft rides in its `proposed` list."""
        from taskuary import coder
        s = MemoryStore(); tid = self._task(s)
        with mock.patch('taskuary.terminal.transcript_for', return_value=(SESSION, 'coder', None)),              mock.patch.object(coder, 'report_from_transcript', return_value={'summary': 'posted the bill', 'resolution': 'done'}),              mock.patch.object(coder, 'resolution_text', return_value='posted the bill'),              mock.patch('taskuary.handbook.enabled', return_value=False),              mock.patch('taskuary.llm.build_llm', return_value=_llm_saying({'playbook': {'slug': 'card-bill', 'text': BILL}})[0]):
            out = coder.wrap(s, tid, close=False, actor='owner')
        self.assertIn('write_playbook', [p['action'] for p in out['proposed']])


class OverTheApi(unittest.TestCase):
    def setUp(self): _clean()

    def test_shelf_editor_and_the_agent_guard(self):
        from fastapi.testclient import TestClient
        from taskuary import server, guard
        c = TestClient(server.app)
        r = c.get('/api/playbooks').json()
        self.assertEqual(r['data'], []); self.assertIn('# Post a card transaction', r['template'])
        r = c.put('/api/playbooks/new', json={'content': BILL}).json()
        self.assertEqual(r['slug'], 'post-a-card-transaction-as-an-ap-bill')
        self.assertEqual(c.put('/api/playbooks/x', json={'content': 'nothing'}).status_code, 400)
        rows = c.get('/api/playbooks').json()['data']
        self.assertEqual([(b['slug'], b['uses']) for b in rows], [(r['slug'], ['quickbooks', 'teller'])])
        self.assertNotIn('text', rows[0])                                  # the shelf is titles; the page is fetched on open
        self.assertIn('ZZMARKPLAYBOOKZZ', c.get(f"/api/playbooks/{r['slug']}").json()['content'])
        # agents read playbooks (they ride in the seed anyway) and never write them: they propose
        self.assertTrue(guard.denied('PUT', '/api/playbooks/bill'))
        self.assertTrue(guard.denied('DELETE', '/api/playbooks/bill'))
        self.assertTrue(guard.denied('PUT', '/api/doc/coder'))            # the old pattern named /api/docs/, the Swagger path
        self.assertFalse(guard.denied('GET', '/api/playbooks'))
        self.assertEqual(c.delete(f"/api/playbooks/{r['slug']}").json(), {'ok': True})
        self.assertEqual(c.get(f"/api/playbooks/{r['slug']}").status_code, 404)


if __name__ == '__main__':
    unittest.main()
