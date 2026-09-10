"""LEARNED.md as a picture (learnedgraph.py) + the two verdicts that shape the default: unanimous
evidence is settled (triage._agreement) and "Not a coding task" teaches the exception."""
import unittest
from unittest import mock

from taskuary import learn, learnedgraph, triage
from taskuary.store import MemoryStore

DOC = '''# LEARNED.md — what the system has learned about {{owner_first}}

## What becomes a task
- {{owner_first}} avoids creating tasks for operational matters owned by other people. [s:16 | ev: mem23, task31, rv25 | seen: 2026-08-27]

## Proposed rules — your call
<!-- proposed:start -->
- Resident refund threads handled by facility staff are FYI only. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-08-24]
<!-- proposed:end -->

## Hypotheses — still being tested
<!-- hypotheses:start -->
- {{owner_first}} avoids personal tasks for matters that already have an assigned owner. [s:5 | ev: mem32, task56 | seen: 2026-08-27]
<!-- hypotheses:end -->

## Verdicts - the evidence
<!-- verdicts:start -->
- 2026-08-26: "x" from y - NOT OURS [mem18 · sender: y]
<!-- verdicts:end -->
'''


def seeded():
    s = MemoryStore(); s.save_doc('learned', DOC, 'reflect')
    for i in range(18, 24): s.add_memory({'Scope': 'subject', 'ScopeKey': 'resident refund request', 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner',
                                          'Note': f'2026-08-{i}: "Re: Resident Refund Request - X" - NOT OURS: other people\'s work, no task, no reply'})
    return s


class ParseTests(unittest.TestCase):
    def test_tagged_lines_carry_section_status_score_and_evidence(self):
        ls = learnedgraph.lines(DOC)
        self.assertEqual([l['status'] for l in ls], ['live', 'proposed', 'hypothesis'])
        self.assertEqual((ls[0]['score'], ls[0]['ev']), (16, ['mem23', 'task31', 'rv25']))
        self.assertNotIn('evidence', [l['status'] for l in ls])          # the verdicts block is not a rule

    def test_graph_resolves_evidence_and_reconstructs_steps(self):
        s = seeded()
        g = learnedgraph.graph(s)
        prop = next(l for l in g['lines'] if l['status'] == 'proposed')
        self.assertEqual([e['kind'] for e in prop['evidence']], ['verdict'] * 3)
        self.assertEqual([st['score'] for st in prop['steps'] if st['effect'] == 1], [2, 3, 4])   # born at 2, +1 per verdict
        self.assertEqual(prop['steps'][-1]['score'], 5)                                            # then 'now' catches the tag up
        self.assertEqual(g['promote_at'], 4)

    def test_history_records_gains_losses_and_deaths(self):
        s = seeded()
        new = (DOC.replace('[s:5 | ev: mem32, task56 | seen: 2026-08-27]', '[s:4 | ev: mem32, task56 | seen: 2026-08-27]')
                  .replace('- Resident refund threads handled by facility staff are FYI only. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-08-24]\n', ''))
        learnedgraph.record(s, DOC, new, 'reflect')
        acts = {(h['Action'], h['Score']) for h in s.learned_history()}
        self.assertIn(('demoted', 4), acts); self.assertIn(('deleted', 0), acts)
        s.save_doc('learned', new, 'reflect')
        g = learnedgraph.graph(s)
        self.assertEqual(len(g['deleted']), 1); self.assertIn('refund', g['deleted'][0]['text'])
        hyp = next(l for l in g['lines'] if l['status'] == 'hypothesis')
        self.assertTrue(any(st.get('action') == 'demoted' for st in hyp['steps']))

    def test_adopt_moves_a_proposed_rule_into_the_live_section(self):
        s = seeded()
        key = next(l['key'] for l in learnedgraph.lines(DOC) if l['status'] == 'proposed')
        out = learn.adopt(s, key, 'owner')
        self.assertIn('refund', out['text'])
        ls = learnedgraph.lines(s.get_doc('learned'))
        self.assertEqual([l['status'] for l in ls if 'refund' in l['text']], ['live'])
        self.assertIn('refund threads', learn.injectable(s.get_doc('learned')))          # rides into prompts now
        self.assertTrue(any(h['Action'] == 'promoted' for h in s.learned_history()))
        with self.assertRaises(ValueError): learn.adopt(s, key)                           # already live


class SettleTests(unittest.TestCase):
    """The bookkeeping learn.settle does in code instead of asking the model for it: a stable k:
    key, one line per key, and a point off every untested line enough reflections have passed by."""
    def doc(self, *bullets, section='## Hypotheses - still being tested'):
        return '# LEARNED.md\n\n' + section + '\n' + '\n'.join(bullets) + '\n'

    def store(self, reflections=0, since='2026-06-02'):
        """A store whose reflection log holds `reflections` runs, all after `since` - the clock
        decay is measured on. Dates need not be distinct: what counts is how many ran."""
        s = MemoryStore()
        if reflections: s.set_setting(learnedgraph.LOG, ','.join([since] * reflections), 't')
        return s

    def test_an_explicit_key_is_the_identity_and_a_line_without_one_still_parses(self):
        d = self.doc('- Uri answers vendors himself. [s:3 | ev: mem1 | seen: 2026-09-01 | k: vendor-mail]',
                     '- Uri avoids tasks other people own. [s:3 | ev: mem2 | seen: 2026-09-01]')
        ls = learnedgraph.lines(d)
        self.assertEqual(ls[0]['key'], 'vendor-mail')
        self.assertEqual(ls[1]['key'], learnedgraph._key('Uri avoids tasks other people own.'))

    def test_settle_assigns_a_key_once_and_it_survives_a_rephrase(self):
        s, d = self.store(), self.doc('- Uri answers vendors himself. [s:3 | ev: mem1 | seen: 2026-09-01]')
        keyed = learn.settle(s, d, d, today='2026-09-05')
        k = learnedgraph.lines(keyed)[0]['key']
        self.assertIn(f'| k: {k}]', keyed)
        rephrased = keyed.replace('Uri answers vendors himself.', 'Vendor mail is answered by Uri, not filed.')
        self.assertEqual(learnedgraph.lines(learn.settle(s, keyed, rephrased, today='2026-09-05'))[0]['key'], k)

    def test_two_bullets_on_one_key_merge_into_the_stronger_line(self):
        d = self.doc('- Uri answers vendors himself. [s:3 | ev: mem1 | seen: 2026-09-01 | k: vendor-mail]',
                     '- Uri replies to vendors personally. [s:5 | ev: mem2, mem3 | seen: 2026-09-04 | k: vendor-mail]')
        ls = learnedgraph.lines(learn.settle(self.store(), d, d, today='2026-09-05'))
        self.assertEqual(len(ls), 1)
        self.assertEqual(ls[0]['score'], 5)
        self.assertEqual(ls[0]['ev'], ['mem1', 'mem2', 'mem3'])
        self.assertIn('answers vendors himself', ls[0]['text'])          # the first line keeps its place and wording

    def test_new_evidence_restarts_the_clock(self):
        old = self.doc('- Uri answers vendors himself. [s:3 | ev: mem1 | seen: 2026-06-01 | k: vendor-mail]')
        new = self.doc('- Uri answers vendors himself. [s:4 | ev: mem1, mem9 | seen: 2026-06-01 | k: vendor-mail]')
        out = learn.settle(self.store(30), old, new, today='2026-09-05')
        self.assertEqual(learnedgraph.lines(out)[0]['seen'], '2026-09-05')   # and 30 reflections no longer count against it

    def test_reflections_spend_a_quiet_hypothesis_and_a_silent_funnel_spends_nothing(self):
        d = self.doc('- Uri answers vendors himself. [s:5 | ev: mem1 | seen: 2026-06-01 | k: vendor-mail]')
        l = learnedgraph.lines(d)[0]
        self.assertEqual(learnedgraph.effective(l, []), 5)                        # no reflections ran: nothing is owed
        self.assertEqual(learnedgraph.effective(l, ['2026-06-02'] * 30), 2)       # 30 reflections passed it by = 3 points
        self.assertEqual(learnedgraph.effective(l, ['2026-05-01'] * 90), 5)       # all of them BEFORE the evidence: free
        # the tag itself is never rewritten by decay - only the line's death is written down
        self.assertEqual(learnedgraph.lines(learn.settle(self.store(30), d, d, today='2026-09-05'))[0]['score'], 5)
        spent = learn.settle(self.store(50), d, d, today='2026-09-05')
        self.assertEqual(learnedgraph.lines(spent), [])
        self.assertIn('# LEARNED.md', spent)                                      # only the line goes

    def test_years_of_silence_cost_a_live_rule_and_an_owner_line_nothing(self):
        d = self.doc('- Uri answers vendors himself. [s:5 | ev: mem1 | seen: 2026-01-01 | k: vendor-mail]',
                     '- Never open a task for payroll.',
                     section='## What becomes a task')
        out = learn.settle(self.store(200), d, d, today='2027-06-01')
        self.assertEqual(learnedgraph.effective(learnedgraph.lines(d)[0], ['2026-06-02'] * 200), 5)
        self.assertIn('answers vendors himself', out)
        self.assertIn('- Never open a task for payroll.', out)          # untagged: byte-for-byte, no key added

    def test_a_reflection_records_its_own_tick_and_stale_lines_stop_being_promotable(self):
        """Same evidence, same s:5 - only the reflections that passed it by differ."""
        s = MemoryStore()
        for who in ('alice@x.com', 'bob@y.com', 'alice@x.com'):
            s.add_memory({'Scope': 'sender', 'ScopeKey': who, 'Source': 'verdict', 'Active': 1, 'CreatedBy': 'owner', 'Note': 'NOT OURS'})
        hyp = ('# LEARNED.md\n\n## Hypotheses - still being tested\n<!-- hypotheses:start -->\n'
               '- Uri leaves matters with an assigned owner alone. [s:5 | ev: mem1, mem2, mem3 | seen: 2026-04-01 | k: assigned-owner]\n'
               '<!-- hypotheses:end -->\n')
        s.save_doc('learned', hyp, 'reflect')
        fresh = learnedgraph.graph(s)['lines'][0]
        self.assertEqual((fresh['score'], fresh['effective']), (5, 5)); self.assertTrue(fresh['eligible'])
        for _ in range(20): learnedgraph.reflect_log(s, '2026-05-01')    # twenty reflections read the window, none touched it
        stale = learnedgraph.graph(s)['lines'][0]
        self.assertEqual((stale['score'], stale['effective']), (5, 3)); self.assertFalse(stale['eligible'])

    def test_the_log_is_capped_and_a_line_older_than_it_is_fully_quiet(self):
        s = MemoryStore()
        for i in range(learnedgraph.LOG_KEEP + 25): learnedgraph.reflect_log(s, '2026-%02d-01' % (1 + i % 9))
        self.assertEqual(len(learnedgraph.reflect_log(s)), learnedgraph.LOG_KEEP)


class OwnerSaidItTests(unittest.TestCase):
    def test_a_proposed_hide_rule_backed_by_the_owners_own_verdicts_goes_live_by_itself(self):
        s = seeded()                                   # the refund rule's ev mem1..mem3 are NOT OURS verdict notes
        out = learn.auto_adopt(s)
        self.assertEqual(len(out), 1); self.assertIn('refund', out[0])
        self.assertEqual([l['status'] for l in learnedgraph.lines(s.get_doc('learned')) if 'refund' in l['text']], ['live'])

    def test_a_rule_the_model_inferred_still_waits_for_the_click(self):
        s = MemoryStore()
        s.save_doc('learned', DOC.replace('ev: mem1, mem2, mem3', 'ev: rv12, rv15, task9'), 'reflect')   # implicit signals only
        self.assertEqual(learn.auto_adopt(s), [])
        self.assertEqual([l['status'] for l in learnedgraph.lines(s.get_doc('learned')) if 'refund' in l['text']], ['proposed'])


class VerdictEvidenceTests(unittest.TestCase):
    """Unanimous verdicts used to be declared SETTLED (triage._agreement) and ordered the model's
    answer. PW-025 (2026-09-06) removed the order: the verdicts stay in the prompt as dated
    evidence, and the model weighs them against what the new message actually asks."""
    def test_the_prompt_shows_the_verdicts_and_orders_nothing(self):
        seen = {}
        def llm(sys_, usr_, **k): seen['sys'] = sys_; return '{"intent": "fyi", "why": "same refund thread"}'
        notes = ['2026-08-26: "Refund" - NOT OURS: x', '2026-08-25: "Refund" - NOT OURS: y']
        triage.classify_intent({'from_email': 'a@b.c', 'subject': 'Re: Refund', 'body': 'thanks'}, llm=llm, notes=notes)
        self.assertNotIn('SETTLED BY YOUR OWNER', seen['sys'])
        for n in notes: self.assertIn(n, seen['sys'])


class NotCodingTests(unittest.TestCase):
    def test_button_keeps_the_task_teaches_and_closes_the_agent(self):
        from fastapi.testclient import TestClient
        from taskuary import server, terminal
        s = MemoryStore()
        tid = s.create_task({'Title': 'Order new badges', 'Kind': 'coding', 'Status': 'in_progress'}, 't')
        s.add_message({'TaskId': tid, 'ExternalId': 'nc1', 'Channel': 'email', 'Subject': 'Badges for the new hires', 'FromEmail': 'hr@corp.com',
                       'SentAt': '2026-08-27 09:00:00', 'Status': 'routed'})
        closed = []
        fake = mock.Mock(alive=True, sid='s1')
        with mock.patch.object(server, 'store', s), mock.patch.object(terminal, 'session_for', return_value=fake), \
             mock.patch.object(terminal, 'close', side_effect=lambda sid: closed.append(sid)):
            out = TestClient(server.app).post(f'/api/tasks/{tid}/not-coding').json()
        self.assertEqual((out['ok'], out['kind']), (True, 'task'))
        self.assertEqual(closed, ['s1'])
        self.assertEqual(s.get_task(tid)['Kind'], 'task'); self.assertEqual(s.get_task(tid)['Status'], 'in_progress')
        note = next(m for m in s.list_memories() if 'NOT A CODING TASK' in m['Note'])
        self.assertIn('Badges for the new hires', note['Note']); self.assertEqual(note['Scope'], 'subject')


if __name__ == '__main__': unittest.main()
