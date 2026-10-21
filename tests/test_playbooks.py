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

    def test_the_words_of_its_steps_never_make_a_playbook_about_code(self):
        """Only `uses:` decides (2026-10-11, "everything should be ai"): a bookkeeping job that visits the branch office and
        commits a journal entry is not a code change, and its agent must not be told the repository rules outrank it."""
        pb = playbooks.parse("""# Close the month for the branch office
when:      the branch office mails its month-end pack
uses:      quickbooks (write: journal entries)
steps:     check out the pack from the branch office → commit the journal entry → reconcile the repository of receipts
alone:     nothing
ask first: everything
done when: the journal entry is posted
""")
        self.assertFalse(playbooks.about_code(pb))
        self.assertFalse(hasattr(playbooks, 'CODE_WORDS'))

    def test_write_list_read_delete(self):
        self.assertEqual(playbooks.list_all(), [])
        slug = playbooks.write('new', BILL)                                   # 'new' files it under its title
        self.assertEqual(slug, 'post-a-card-transaction-as-an-ap-bill')
        playbooks.write('onboard', ONBOARD)
        books = playbooks.list_all()
        # oldest-first by mtime; two writes in the same second are unordered (Windows CI)
        self.assertCountEqual([b['slug'] for b in books], [slug, 'onboard'])
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

    def test_one_switched_off_is_kept_but_never_offered_and_the_global_switch_stops_them_all(self):
        """Delete was the only way to stop a playbook matching, and playbooks_enabled ("follow") stopped none (the owner, 2026-10-21)."""
        playbooks.write('bill', BILL); playbooks.write('onboard', ONBOARD)
        playbooks.set_on('bill', False)
        self.assertEqual([(b['slug'], b['enabled']) for b in playbooks.list_all()], [('bill', False), ('onboard', True)])
        self.assertNotIn('- bill:', playbooks.menu()); self.assertIn('- onboard:', playbooks.menu())
        self.assertIsNotNone(playbooks.read('bill'))                         # kept for later
        playbooks.set_on('bill', True); self.assertIn('- bill:', playbooks.menu())
        s = MemoryStore(); s.set_setting('playbooks_enabled', '0', 'owner')
        self.assertEqual(playbooks.menu(store=s), '')
        s.set_setting('playbooks_enabled', '1', 'owner'); self.assertIn('- onboard:', playbooks.menu(store=s))
        playbooks.set_on('bill', False); playbooks.delete('bill', now=0)
        self.assertIn('bill', playbooks.off())                              # kept while Restore can still bring it back...
        playbooks.purge()
        self.assertNotIn('bill', playbooks.off())                           # ...and a purged one leaves no stale switch behind

    def test_a_slug_never_ends_in_a_hyphen_after_the_cut(self):
        self.assertEqual(playbooks.slugify('x' * 59 + ' onboarding'), 'x' * 59)
        self.assertEqual(playbooks.slugify('  Post a card: transaction!  '), 'post-a-card-transaction')
        self.assertEqual(playbooks.slugify('---'), 'playbook')
        self.assertEqual(len(playbooks.slugify('word ' * 40)), 59)

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

    def test_the_menu_rides_and_the_slug_comes_back_with_the_models_own_kind(self):
        llm, seen = _llm_saying({'intent': 'task', 'kind': 'task', 'why': 'a card line', 'playbook': 'bill'})
        out = triage.classify_intent(self.msg, llm=llm, playbooks=playbooks.menu())
        self.assertIn('PLAYBOOKS', seen['system']); self.assertIn('- bill: ', seen['system'])
        # PW-205 (2026-09-06): the procedure says how the job is done, not who does it - it no longer forces coding
        self.assertEqual((out['playbook'], out['kind']), ('bill', 'task'))

    def test_a_slug_the_menu_never_offered_is_ignored(self):
        llm, _ = _llm_saying({'intent': 'task', 'kind': 'coding', 'why': 'x', 'playbook': 'made-up'})
        self.assertNotIn('playbook', triage.classify_intent(self.msg, llm=llm, playbooks=playbooks.menu()))

    def test_no_playbooks_no_paragraph(self):
        llm, seen = _llm_saying({'intent': 'fyi', 'why': 'x'})
        triage.classify_intent(self.msg, llm=llm, playbooks='')
        self.assertNotIn("PLAYBOOKS - the owner's written procedures", seen['system'])   # the guide names playbooks; the menu label is absent

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
        s = MemoryStore(); s.save_doc('coding', '# Coding rules\n- ZZMARKCODINGZZ', 'owner')
        s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude'}))     # the profile a coding task runs under, by its kind
        seed = terminal.seed_text(s, self._task(s))
        self.assertIn('PLAYBOOK "Post a card transaction as an AP bill"', seed)
        self.assertIn('ASK FIRST: a new vendor', seed)
        self.assertIn('ZZMARKPLAYBOOKZZ', seed)
        self.assertIn('NOT A CODE CHANGE', seed)
        self.assertIn('ZZMARKCODINGZZ', seed)          # the closing-out and wall rules still ride
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
        """wrapup.wrap is the one on-close road; the draft rides in its `proposed` list."""
        from taskuary import wrapup
        s = MemoryStore(); tid = self._task(s)
        with mock.patch('taskuary.terminal.transcript_for', return_value=(SESSION, 'coding', None)),              mock.patch.object(wrapup, 'report_from_transcript', return_value={'summary': 'posted the bill', 'resolution': 'done'}),              mock.patch.object(wrapup, 'resolution_text', return_value='posted the bill'),              mock.patch('taskuary.handbook.enabled', return_value=False),              mock.patch('taskuary.llm.build_llm', return_value=_llm_saying({'playbook': {'slug': 'card-bill', 'text': BILL}})[0]):
            out = wrapup.wrap(s, tid, close=False, actor='owner')
        self.assertIn('write_playbook', [p['action'] for p in out['proposed']])

    def _chat(self, s, **task):
        """A general-work job as it really arrives: a mail, triage's one-line title as the opening turn, and a crisp answer - the
        chat alone is under playbooks.MIN_SESSION, so the mail has to be read with it."""
        from taskuary import general
        from taskuary.testing import Factory
        tid = s.create_task({'Title': 'Reconcile the October cash shortfall', 'Kind': 'general', **task}, 't')
        Factory(s).message(task_id=tid, subject='October cash shortfall - bank does not tie', from_name='Erin Blake',
                           body='The October bank balance does not tie to the ledger - we are $412.50 short. Can you reconcile it and '
                                'tell me what the adjusting entries are? We close the month on Friday and the auditors ask for this. '
                                'Last quarter the same gap turned out to be card fees, so start there. Thanks, Erin')
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Reconcile the October cash shortfall.')
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Matched every statement line to the register: two card fees sat in '
                      'the wrong period and one deposit is in transit. Three adjusting entries are listed for your yes: '
                      'move the two September card fees ($37.50) into October, and hold the $375.00 deposit until it clears.')
        return tid

    def test_a_general_conversation_is_asked_too(self):
        """The jobs playbooks are FOR are general work - a bill, a W-9, a reconciliation - and only the coding ending asked
        (walk 2026-10-21: a month-end reconciliation closed itself with no proposal; no brain call was even made)."""
        from taskuary import wrapup
        s = MemoryStore(); tid = self._chat(s)
        llm, seen = _llm_saying({'playbook': {'slug': 'reconcile-cash', 'text': ONBOARD.replace('# Onboard a new hire in the directory',
                                                                                              '# Reconcile a month-end cash shortfall')}})
        with mock.patch('taskuary.llm.build_llm', return_value=llm), mock.patch('taskuary.handbook.enabled', return_value=False):
            out = wrapup.wrap(s, tid, close=True, actor='assistant')
        self.assertEqual([p['action'] for p in out['proposed']], ['write_playbook'])
        self.assertIn('two card fees', seen['user'])                       # drafted from the conversation itself...
        self.assertIn('does not tie to the ledger', seen['user'])          # ...and the mail that started it - the playbook's `when`
        self.assertIsNotNone(proposals.playbook_pending(s, tid))

    def test_a_proposal_on_a_task_that_closed_itself_is_kept_in_sight(self):
        """With nobody to answer, the task closed as done and its pending proposal was shown nowhere (store._VISIBLE_PENDING).
        It waits for the proposal instead, and closes again once the owner answers it (the owner, 2026-10-21)."""
        from taskuary import general, wrapup
        s = MemoryStore()
        tid = s.create_task({'Title': 'Weekly vendor check', 'Kind': 'general'}, 't')
        s.add_comment(tid, 'owner', general.USER_TYPE, 'Check every vendor billed this week for a W-9 and a matching remit-to. ' * 6)
        s.add_comment(tid, 'assistant', general.ASSISTANT_TYPE, 'Checked Payworth, Spendly and Trainly: all on file, all matching. ' * 6)
        llm, _ = _llm_saying({'playbook': {'slug': 'vendor-check', 'text': ONBOARD}})
        with mock.patch('taskuary.llm.build_llm', return_value=llm), mock.patch('taskuary.handbook.enabled', return_value=False):
            wrapup.wrap(s, tid, close=True, actor='assistant')
        t = s.get_task(tid)
        self.assertEqual(t['Status'], 'waiting'); self.assertIn(proposals.HELD, t['Tags'])
        rv = next(r for r in s.list_reviews('pending') if r['TaskId'] == tid)      # the rail and the task page both read this
        verdicts.decide(s, rv, 'reject', None, None, 'owner')
        t = s.get_task(tid)
        self.assertEqual(t['Status'], 'done'); self.assertNotIn(proposals.HELD, t['Tags'] or '')

    def test_a_workflow_run_is_not_asked(self):
        """A workflow is a job already written down; its run proposing a playbook for itself would be the same job twice."""
        s = MemoryStore(); tid = self._chat(s, Source='workflow')
        self.assertIsNone(playbooks.draft(s, tid, SESSION, llm=lambda *a, **k: 1 / 0))

    def test_a_playbook_setup_conversation_is_not_asked_again(self):
        from taskuary import wrapup
        s = MemoryStore(); tid = self._chat(s, SourceRef='assistant:playbook')
        with mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: 1 / 0), mock.patch('taskuary.handbook.enabled', return_value=False):
            out = wrapup.wrap(s, tid, close=True, actor='owner')
        self.assertEqual(out['proposed'], [])


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
        self.assertEqual(c.put(f"/api/playbooks/{r['slug']}/enabled", json={'on': False}).json()['enabled'], False)
        self.assertEqual(c.get('/api/playbooks').json()['data'][0]['enabled'], False)
        self.assertEqual(c.put('/api/playbooks/nope/enabled', json={'on': False}).status_code, 404)
        c.put(f"/api/playbooks/{r['slug']}/enabled", json={'on': True})
        self.assertEqual(c.put('/api/playbooks/x', json={'content': 'nothing'}).status_code, 400)
        rows = c.get('/api/playbooks').json()['data']
        self.assertEqual([(b['slug'], b['uses']) for b in rows], [(r['slug'], ['quickbooks', 'teller'])])
        self.assertNotIn('text', rows[0])                                  # the shelf is titles; the page is fetched on open
        self.assertIn('ZZMARKPLAYBOOKZZ', c.get(f"/api/playbooks/{r['slug']}").json()['content'])
        # agents read playbooks (they ride in the seed anyway) and never write them: they propose
        self.assertTrue(guard.denied('PUT', '/api/playbooks/bill'))
        self.assertTrue(guard.denied('DELETE', '/api/playbooks/bill'))
        self.assertTrue(guard.denied('PUT', '/api/doc/coding'))            # the old pattern named /api/docs/, the Swagger path
        self.assertFalse(guard.denied('GET', '/api/playbooks'))
        self.assertEqual(c.delete(f"/api/playbooks/{r['slug']}").json(), {'ok': True})
        self.assertEqual(c.get(f"/api/playbooks/{r['slug']}").status_code, 404)
        shelf = c.get('/api/playbooks').json()
        self.assertEqual(shelf['data'], []); self.assertEqual(shelf['keep_days'], 30)
        self.assertEqual([(d['slug'], d['days_left']) for d in shelf['deleted']], [(r['slug'], 29)])
        self.assertTrue(guard.denied('POST', f"/api/playbooks/{r['slug']}/restore"))
        self.assertEqual(c.post(f"/api/playbooks/{r['slug']}/restore").json(), {'ok': True, 'slug': r['slug']})
        self.assertEqual(c.post(f"/api/playbooks/{r['slug']}/restore").status_code, 404)  # nothing deleted to restore
        shelf = c.get('/api/playbooks').json()
        self.assertEqual(([b['slug'] for b in shelf['data']], shelf['deleted']), ([r['slug']], []))


class DeletedIsRecoverable(unittest.TestCase):
    """Delete is at once - no "are you sure" (the owner, 2026-10-21) - so it has to be undoable: Recently deleted for 30 days."""
    def setUp(self): _clean()

    def test_delete_hides_it_from_the_shelf_the_cards_and_the_seed(self):
        playbooks.write('bill', BILL); playbooks.write('onboard', ONBOARD)
        self.assertTrue(playbooks.delete('bill')); self.assertFalse(playbooks.delete('bill'))
        self.assertFalse(playbooks.delete('nope'))
        self.assertEqual([b['slug'] for b in playbooks.list_all()], ['onboard'])
        self.assertEqual(playbooks.for_connector('quickbooks'), [])
        self.assertIsNone(playbooks.read('bill')); self.assertIn('ZZMARKPLAYBOOKZZ', playbooks.read('bill', deleted=True))
        self.assertIsNone(playbooks.for_task({'Tags': 'playbook:bill'}))
        self.assertEqual(playbooks.seed_block({'Tags': 'playbook:bill'}), '')
        self.assertEqual([d['slug'] for d in playbooks.recently_deleted()], ['bill'])

    def test_triage_never_matches_a_deleted_one(self):
        playbooks.write('bill', BILL); playbooks.write('onboard', ONBOARD)
        playbooks.delete('bill')
        m = playbooks.menu()
        self.assertNotIn('- bill:', m); self.assertIn('- onboard:', m)
        s = MemoryStore()
        llm, seen = _llm_saying({'intent': 'task', 'kind': 'task', 'why': 'a card line', 'playbook': 'bill'})
        out = ingest.ingest_message(s, {'channel': 'email', 'external_id': 'pbdel1', 'from_email': 'alerts@card.example',
                                        'subject': 'Transaction: 12.00', 'body': 'A new transaction posted.'}, llm=llm)
        self.assertNotIn('- bill: ', seen['system']); self.assertIn('- onboard: ', seen['system'])
        self.assertIsNone(playbooks.of_task(s.get_task(out['task_id'])))  # the model named it anyway: never offered, never tagged

    def test_restore_brings_back_its_words_its_switch_and_its_place(self):
        playbooks.write('bill', BILL); playbooks.write('onboard', ONBOARD)
        playbooks.set_on('bill', False)
        before = playbooks.list_all()
        playbooks.delete('bill')
        self.assertTrue(playbooks.restore('bill')); self.assertFalse(playbooks.restore('bill'))
        self.assertEqual(playbooks.list_all(), before)                     # words, enabled=False and the mtime order, exactly
        self.assertEqual(playbooks.recently_deleted(), [])
        self.assertNotIn('- bill:', playbooks.menu())                       # it was off when deleted, and is off again

    def test_purge_after_thirty_days_and_not_before(self):
        playbooks.write('bill', BILL); playbooks.write('onboard', ONBOARD)
        day = 86400
        playbooks.delete('bill', now=1000 * day); playbooks.delete('onboard', now=1020 * day)
        self.assertEqual(playbooks.purge(now=1029 * day), [])
        self.assertEqual(playbooks.recently_deleted(now=1029 * day)[1]['days_left'], 1)
        self.assertEqual(playbooks.purge(now=1030 * day), ['bill'])
        self.assertFalse((playbooks.folder() / 'bill.md').exists())
        self.assertFalse(playbooks.restore('bill'))
        self.assertEqual(list(playbooks.deleted_at()), ['onboard'])
        self.assertTrue((playbooks.folder() / 'onboard.md').exists())

    def test_a_new_one_under_a_deleted_name_starts_fresh_and_on(self):
        playbooks.write('bill', BILL); playbooks.set_on('bill', False); playbooks.delete('bill')
        playbooks.write('bill', BILL.replace('ZZMARKPLAYBOOKZZ', 'ZZNEWZZ'))
        (b,) = playbooks.list_all()
        self.assertTrue(b['enabled']); self.assertIn('ZZNEWZZ', b['text']); self.assertEqual(playbooks.recently_deleted(), [])


if __name__ == '__main__':
    unittest.main()
