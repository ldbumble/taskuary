"""Work facts into the playbook they belong to, as a proposal (spec 2026-10-12, build step 5)."""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock
from taskuary import outcomes, playbook_facts, playbooks, proposals
from taskuary.store import MemoryStore

def ago(days=0): return (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')

def closed_task(s, slug, asked, reopened):
    t = s.create_task({'Title': 'Vendor onboarding', 'Tags': playbooks.tag(slug), 'Status': 'open'}, 'owner')
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

    def test_the_close_carries_the_playbook_and_whether_it_asked(self):
        t = closed_task(self.s, 'vendor-onboarding', True, False)
        f = json.loads(outcomes.rows_for(self.s, 'task', t)[0]['FactsJson'])
        self.assertEqual((f['playbook'], f['asked']), ('vendor-onboarding', True))

    def test_work_facts_count_reopens_after_an_open_question(self):
        self.five()
        self.assertEqual(outcomes.work_facts(self.s, 'vendor-onboarding'), {'closes': 5, 'reopened': 2, 'closed_with_open_question': 3, 'reopened_after_open_question': 2})

    def test_compile_files_a_task_less_proposal_for_the_owners_yes(self):
        self.five()
        with mock.patch.object(playbooks, 'read', return_value=PAGE):
            rid = playbook_facts.compile(self.s, 'vendor-onboarding', llm=lambda sys_, user, **kw: '- closing with an open question reopened 2 of 3 times; ask first [ev: out1, out2]')
        rv = self.s.get_review(rid)
        self.assertIsNone(rv['TaskId']); self.assertEqual((rv['Kind'], rv['Status']), ('action', 'pending'))
        p = json.loads(rv['DraftText']); self.assertEqual(p['action'], 'amend_playbook'); self.assertIn('ask first', p['text']); self.assertIn('when: a new vendor writes', p['text'])
        self.assertTrue(proposals.validate(self.s, p)[0])

    def test_one_open_proposal_per_playbook(self):
        self.five()
        with mock.patch.object(playbooks, 'read', return_value=PAGE):
            a = playbook_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- a fact [ev: out1]')
            self.assertIsNone(playbook_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- another [ev: out2]'))
        self.assertTrue(a)

    def test_approving_it_writes_the_playbook(self):
        self.five()
        with mock.patch.object(playbooks, 'read', return_value=PAGE):
            rid = playbook_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- ask first [ev: out1]')
        with mock.patch.object(playbooks, 'write', return_value='vendor-onboarding') as w:
            out = proposals.execute(self.s, self.s.get_review(rid))
        self.assertEqual(out['playbook'], 'vendor-onboarding'); self.assertIn('ask first', w.call_args[0][1])

    def test_the_proposal_has_no_task_and_blocks_nothing(self):
        t = closed_task(self.s, 'vendor-onboarding', True, True)
        with mock.patch.object(playbooks, 'read', return_value='# Vendor onboarding\nwhen: x\n'):
            playbook_facts.compile(self.s, 'vendor-onboarding', llm=lambda sys_, user, **kw: '- a fact [ev: out1]')
        self.assertFalse(proposals.closeout_pending(self.s, t)); self.assertFalse(proposals.owed(self.s, t))

    def test_refresh_needs_five_closes_and_silence_files_nothing(self):
        for _ in range(4): closed_task(self.s, 'vendor-onboarding', False, False)
        self.assertEqual(playbook_facts.refresh(self.s, llm=lambda *a, **k: '- x [ev: out1]'), [])
        closed_task(self.s, 'vendor-onboarding', False, False)
        with mock.patch.object(playbooks, 'read', return_value='# V\nwhen: x\n'):
            self.assertEqual(playbook_facts.refresh(self.s, llm=lambda *a, **k: ''), [])
            self.assertEqual(playbook_facts.refresh(self.s, llm=lambda *a, **k: '- a fact [ev: out1]'), ['vendor-onboarding'])

    def test_a_playbook_that_is_gone_gets_no_proposal(self):
        self.five()
        with mock.patch.object(playbooks, 'read', return_value=None):
            self.assertIsNone(playbook_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- a fact [ev: out1]'))

    def test_approving_keeps_edits_made_to_the_playbook_since(self):
        """review: the proposal carried the whole page as it was; approved weeks later it put back an older page"""
        self.five()
        with mock.patch.object(playbooks, 'read', return_value=PAGE):
            rid = playbook_facts.compile(self.s, 'vendor-onboarding', llm=lambda *a, **k: '- ask first [ev: out1]')
        later = PAGE + '\n- the owner added this later\n'
        with mock.patch.object(playbooks, 'read', return_value=later), mock.patch.object(playbooks, 'write', return_value='vendor-onboarding') as w:
            proposals.execute(self.s, self.s.get_review(rid))
        self.assertIn('the owner added this later', w.call_args[0][1]); self.assertIn('ask first', w.call_args[0][1])

    def test_a_question_the_owner_answered_is_not_left_open(self):
        """review: `asked` read the last inbound alone, so a task whose opening mail asked counted open even after the reply"""
        t = self.s.create_task({'Title': 'Vendor onboarding', 'Tags': playbooks.tag('vendor-onboarding'), 'Status': 'open'}, 'owner')
        mid = self.s.add_message({'ConversationId': 'cx', 'Channel': 'email', 'Subject': 'Onboarding', 'FromEmail': 'billing@vendor.example', 'SentAt': ago(10),
                                  'BodyText': 'x', 'Status': 'routed', 'TaskId': t})
        self.s.add_route(mid, t, 'create', 1.0, 'x', [], 'triage', verdict={'intent': 'task'})
        self.s.add_message({'ConversationId': 'cx', 'Channel': 'email', 'Subject': 'Re: Onboarding', 'FromEmail': 'alex@northwind.example', 'SentAt': ago(9),
                            'BodyText': 'done', 'Status': 'context', 'Direction': 'out', 'TaskId': t})
        self.s.update_task(t, {'Status': 'done'}, 'owner')
        self.assertFalse(json.loads(outcomes.rows_for(self.s, 'task', t)[0]['FactsJson'])['asked'])


if __name__ == '__main__': unittest.main()
