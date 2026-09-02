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


class SettledEvidenceTests(unittest.TestCase):
    def test_unanimous_verdicts_are_declared_settled(self):
        notes = ['2026-08-26: "Re: Refund - A" - NOT OURS: other people\'s work', '2026-08-25: "Refund approved" - NOT OURS: no task']
        self.assertEqual(triage._agreement(notes), ('NOT OURS', 2))
        self.assertEqual(triage._agreement(notes[:1]), ())                                # one is not a pattern
        self.assertEqual(triage._agreement(notes + ['2026-08-27: "x" - NOT A TASK: filed']), ())   # they disagree
        self.assertEqual(triage._agreement(['Priya handles AR stuff.']), ())                # free text is advice

    def test_the_prompt_says_settled(self):
        seen = {}
        def llm(sys_, usr_, **k): seen['sys'] = sys_; return '{"intent": "fyi", "why": "settled"}'
        triage.classify_intent({'from_email': 'a@b.c', 'subject': 'Re: Refund', 'body': 'thanks'}, llm=llm,
                               notes=['2026-08-26: "Refund" - NOT OURS: x', '2026-08-25: "Refund" - NOT OURS: y'])
        self.assertIn('SETTLED BY YOUR OWNER: all 2 past verdicts', seen['sys'])


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
