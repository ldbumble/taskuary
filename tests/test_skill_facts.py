"""Work facts into the skill they belong to, as a proposal (spec 2026-10-12, build step 5)."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import card, outcomes, skill_facts, skills, proposals
from taskuary.store import MemoryStore

def ago(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

def closed_task(s, slug, asked, reopened):
    t = s.create_task({'Title': 'Vendor onboarding', 'Tags': skills.tag(slug), 'Status': 'open'}, 'owner')
    mid = s.add_message({'ConversationId': f'c{t}', 'Channel': 'email', 'Subject': 'Onboarding', 'FromEmail': 'billing@vendor.example', 'SentAt': ago(10),
                         'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
    s.add_route(mid, t, 'create', 1.0, 'x', [], 'triage', verdict={'intent': 'task' if asked else 'fyi'})
    s.update_task(t, {'Status': 'done'}, 'owner')
    r = outcomes.rows_for(s, 'task', t)[0]
    outcomes.settle(s, r['Id'], 'x', 'reopened' if reopened else 'held')
    return t

PAGE = '# Vendor onboarding\nwhen: a new vendor writes\n'


class WorkFactsTests(unittest.TestCase):
    def setUp(self): self.s = MemoryStore(); self.s.set_setting('playbooks_enabled', '1', 'test')
    def five(self):
        for asked, reopened in ((True, True), (True, True), (True, False), (False, False), (False, False)): closed_task(self.s, 'vendor-onboarding', asked, reopened)

    def test_the_close_carries_the_skill_and_whether_it_asked(self):
        t = closed_task(self.s, 'vendor-onboarding', True, False)
        f = json.loads(outcomes.rows_for(self.s, 'task', t)[0]['FactsJson'])
        self.assertEqual((f['skill'], f['asked']), ('vendor-onboarding', True))

    def test_work_facts_count_reopens_after_an_open_question(self):
        self.five()
        self.assertEqual(outcomes.work_facts(self.s, 'vendor-onboarding'), {'closes': 5, 'reopened': 2, 'closed_with_open_question': 3, 'reopened_after_open_question': 2})

    def test_closes_the_ledger_counted_when_skills_were_playbooks_still_count(self):
        """The ledger wrote the kind of work as `playbook` before the name changed: those closes are the same skill's, and reflection's
        five-close bar is not started again by an update."""
        self.five()
        self.s._exec("UPDATE outcome SET FactsJson=REPLACE(FactsJson, '\"skill\"', '\"playbook\"') WHERE Kind='task.closed'")
        self.assertNotIn('"skill"', outcomes.rows_for(self.s, 'task', 1)[0]['FactsJson'])
        self.assertEqual(outcomes.work_facts(self.s, 'vendor-onboarding')['closes'], 5)
        with mock.patch.object(skills, 'read', return_value=PAGE):
            self.assertEqual(skill_facts.refresh(self.s, llm=lambda *a, **k: '- ask first [ev: out1]'), ['vendor-onboarding'])

    def test_compile_files_a_task_less_proposal_for_the_owners_yes(self):
        self.five()
        with mock.patch.object(skills, 'read', return_value=PAGE):
            rid = skill_facts.compile(self.s, 'vendor-onboarding', llm=lambda sys_, user, **kw: '- closing with an open question reopened 2 of 3 times; ask first [ev: out1, out2]')
        rv = self.s.get_review(rid)
        self.assertIsNone(rv['TaskId']); self.assertEqual((rv['Kind'], rv['Status']), ('action', 'pending'))
        p = json.loads(rv['DraftText']); self.assertEqual(p['action'], 'save_skill'); self.assertIn('ask first', p['text']); self.assertIn('when: a new vendor writes', p['text'])
        self.assertTrue(proposals.validate(self.s, p)[0])

    def test_one_open_proposal_per_skill(self):
        self.five()
        with mock.patch.object(skills, 'read', return_value=PAGE):
            a = skill_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- a fact [ev: out1]')
            self.assertIsNone(skill_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- another [ev: out2]'))
        self.assertTrue(a)

    def test_approving_it_writes_the_skill(self):
        self.five()
        with mock.patch.object(skills, 'read', return_value=PAGE):
            rid = skill_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- ask first [ev: out1]')
        with mock.patch.object(skills, 'write', return_value='vendor-onboarding') as w:
            out = proposals.execute(self.s, self.s.get_review(rid))
        self.assertEqual(out['skill'], 'vendor-onboarding'); self.assertIn('ask first', w.call_args[0][1])

    def test_the_proposal_has_no_task_and_blocks_nothing(self):
        t = closed_task(self.s, 'vendor-onboarding', True, True)
        with mock.patch.object(skills, 'read', return_value='# Vendor onboarding\nwhen: x\n'):
            skill_facts.compile(self.s, 'vendor-onboarding', llm=lambda sys_, user, **kw: '- a fact [ev: out1]')
        self.assertFalse(card.pending(self.s, t, 'closeout')); self.assertFalse(proposals.owed(self.s, t))

    def test_refresh_needs_five_closes_and_silence_files_nothing(self):
        for _ in range(4): closed_task(self.s, 'vendor-onboarding', False, False)
        self.assertEqual(skill_facts.refresh(self.s, llm=lambda *a, **k: '- x [ev: out1]'), [])
        closed_task(self.s, 'vendor-onboarding', False, False)
        with mock.patch.object(skills, 'read', return_value='# V\nwhen: x\n'):
            self.assertEqual(skill_facts.refresh(self.s, llm=lambda *a, **k: ''), [])
            self.assertEqual(skill_facts.refresh(self.s, llm=lambda *a, **k: '- a fact [ev: out1]'), ['vendor-onboarding'])

    def test_a_skill_that_is_gone_gets_no_proposal(self):
        self.five()
        with mock.patch.object(skills, 'read', return_value=None):
            self.assertIsNone(skill_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- a fact [ev: out1]'))

    def test_approving_keeps_edits_made_to_the_skill_since(self):
        """review: the proposal carried the whole page as it was; approved weeks later it put back an older page"""
        self.five()
        with mock.patch.object(skills, 'read', return_value=PAGE):
            rid = skill_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- ask first [ev: out1]')
        later = PAGE + '\n- the owner added this later\n'
        with mock.patch.object(skills, 'read', return_value=later), mock.patch.object(skills, 'write', return_value='vendor-onboarding') as w:
            proposals.execute(self.s, self.s.get_review(rid))
        self.assertIn('the owner added this later', w.call_args[0][1]); self.assertIn('ask first', w.call_args[0][1])

    def test_a_question_the_owner_answered_is_not_left_open(self):
        """review: `asked` read the last inbound alone, so a task whose opening mail asked counted open even after the reply"""
        t = self.s.create_task({'Title': 'Vendor onboarding', 'Tags': skills.tag('vendor-onboarding'), 'Status': 'open'}, 'owner')
        mid = self.s.add_message({'ConversationId': 'cx', 'Channel': 'email', 'Subject': 'Onboarding', 'FromEmail': 'billing@vendor.example', 'SentAt': ago(10),
                                  'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
        self.s.add_route(mid, t, 'create', 1.0, 'x', [], 'triage', verdict={'intent': 'task'})
        self.s.add_message({'ConversationId': 'cx', 'Channel': 'email', 'Subject': 'Re: Onboarding', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(9),
                            'BodyText': 'done', 'Status': 'context', 'Direction': 'out', 'TaskId': t})
        self.s.update_task(t, {'Status': 'done'}, 'owner')
        self.assertFalse(json.loads(outcomes.rows_for(self.s, 'task', t)[0]['FactsJson'])['asked'])


if __name__ == '__main__': unittest.main()


SKILL_MD = '---\nname: vendor-onboarding\ndescription: Onboard a new vendor. Use when a new vendor writes.\n---\n# Vendor onboarding\n\nAsk for the W-9, then set them up.\n'
DRAFT = 'Hi Erin,\n\nThank you so much for reaching out! We would be delighted to onboard Payworth. Could you kindly send a W-9?\n\nBest regards,\nAlex Doyle'
SENT = 'Erin - send the W-9 and a voided check and we will set Payworth up this week.\n\nAlex'


class HisEditsTeachTheSkill(unittest.TestCase):
    """The owner, 2026-11-26: when he edits an agent's draft before sending it, that says how he wants this kind of job written. It
    goes into the reflection the skill already has, and comes back as ONE card to update the skill - never a silent change."""
    def setUp(self):
        import shutil
        if skills.folder().is_dir(): shutil.rmtree(skills.folder())
        self.s = MemoryStore(); self.s.set_setting('playbooks_enabled', '1', 'test')
        skills.write('vendor-onboarding', SKILL_MD)

    def letter(self, draft, final, slug='vendor-onboarding', went=True):
        t = self.s.create_task({'Title': 'Onboard Payworth', 'Tags': skills.tag(slug) if slug else '', 'Status': 'open'}, 'owner')
        rid = self.s.add_review({'TaskId': t, 'Kind': 'draft_reply', 'Status': 'sent' if went else 'pending', 'DraftText': draft, 'FinalText': final if went else None})
        if went: self.s._exec("UPDATE review SET DeliveryState='sent' WHERE ReviewId=?", (rid,))
        return rid

    def test_an_edit_is_a_letter_that_went_with_other_words_on_a_task_worked_from_the_skill(self):
        mine = self.letter(DRAFT, SENT)
        self.letter(DRAFT, DRAFT)                                   # sent as drafted: nothing of his to learn from
        self.letter(DRAFT, DRAFT.replace('\n\n', '\n \n'))            # ...nor a change of spacing alone
        self.letter(DRAFT, SENT, went=False)                        # ...nor one that never went
        self.letter(DRAFT, SENT, slug='')                           # ...nor a letter on a task no skill was used for
        self.letter(DRAFT, SENT, slug='vendor-onboarding-old')      # ...nor another skill's, whatever its name starts with
        self.assertEqual(skill_facts.edits(self.s, 'vendor-onboarding'), [{'rid': mine, 'draft': DRAFT, 'sent': SENT}])

    def test_one_edit_reaches_reflection_and_comes_back_as_a_card_never_a_silent_change(self):
        rid = self.letter(DRAFT, SENT); seen = []
        def brain(system, user, **k): seen.append((system, user)); return f'- Write to a vendor in two plain lines, no pleasantries [ev: rv{rid}]'
        before = skills.read('vendor-onboarding')
        self.assertEqual(skill_facts.refresh(self.s, llm=brain), ['vendor-onboarding'])           # no five closes needed: his edit is the evidence
        (system, user), = seen
        self.assertIn('HIS EDITS', user); self.assertIn('THE AGENT DRAFTED:\n' + DRAFT, user); self.assertIn('HE SENT:\n' + SENT, user)
        self.assertIn('what he changed in an agent\'s draft', system)
        self.assertEqual(skills.read('vendor-onboarding'), before)                                 # nothing changed without his press
        rv, = self.s.list_reviews('pending'); p = json.loads(rv['DraftText'])
        self.assertEqual((card.sort_of(rv), p['action'], p['slug']), ('skill', 'save_skill', 'vendor-onboarding'))
        self.assertIn('two plain lines', p['block']); self.assertIn('what you changed in drafts before sending them', p['block'])
        self.assertIn('Ask for the W-9, then set them up.', p['text'])                             # his own lines stand in what the card shows
        proposals.execute(self.s, rv)
        now = skills.read('vendor-onboarding')
        self.assertIn('two plain lines', now); self.assertIn('Ask for the W-9, then set them up.', now)

    def test_an_edit_is_put_to_him_once(self):
        self.letter(DRAFT, SENT); calls = []
        brain = lambda *a, **k: calls.append(1) or '- Two plain lines [ev: rv1]'
        skill_facts.refresh(self.s, llm=brain)
        rv, = self.s.list_reviews('pending')
        self.s.decide_review(rv['ReviewId'], 'rejected', None, 'owner')
        self.assertEqual(skill_facts.refresh(self.s, llm=brain), [])                               # his no stands: the same edit is not put again
        self.assertEqual(len(calls), 1)
        self.letter(DRAFT, SENT.replace('this week', 'by Friday'))                                 # ...a new edit is new evidence
        self.assertEqual(skill_facts.refresh(self.s, llm=brain), ['vendor-onboarding']); self.assertEqual(len(calls), 2)

    def test_no_edit_and_too_few_closes_asks_no_model(self):
        self.letter(DRAFT, DRAFT)
        self.assertEqual(skill_facts.refresh(self.s, llm=lambda *a, **k: 1 / 0), [])
