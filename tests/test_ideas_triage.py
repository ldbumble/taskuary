"""Assistant ideas enter the shared triage (PW-199 to PW-202).

The assistant's post was written to the timeline with a fixed 'feed' route and its ideas surfaced
through an assistant-only lane, never judged. Now every newly said idea gets the same triage
verdict as an incoming message - with its evidence, its originating report and the state of any
task it is about - recorded on the idea. An actionable idea that is not about active work opens a
task through the shared intake (so kind defaults and startup rules apply); one about an active
task records the verdict and creates nothing; an informational one is fyi; a failure is an error
the next run retries. The pile orders ideas by that verdict, not by a second assistant ranking, and
the assistant never reads its own generated rows back in as new arrivals. Report triage stays the
opt-in it was.
"""
import json, unittest
from datetime import datetime, timedelta
from unittest import mock

from taskuary import assistant, funnel, terminal
from taskuary.store import MemoryStore

# relative, never a clock time: the pile keeps the last twelve hours, so a fixed 09:00 failed CI every evening
STAMP = (datetime.now() - timedelta(hours=1)).strftime('%Y-%m-%d %H:%M:%S')


def idea(s, key, text, action=None, kind='idea'):
    return s.upsert_idea({'key': key, 'kind': kind, 'text': text, 'sig': text[:40], 'action': dict(action or {}) | {'why': 'the assistant noticed it'}}, STAMP)


def brain(intent='task', kind='general', calls=None):
    def llm(system, user, **k):
        if calls is not None: calls.append(json.loads(user))
        j = {'intent': intent, 'why': 'judged', 'title': 'Chase the vendor about the unpaid invoice', 'checklist': ['Call the vendor']}
        if intent == 'task': j['kind'] = kind
        return json.dumps(j)
    return llm


def pile(s):
    funnel.invalidate(); funnel.forget_states()
    with mock.patch.object(terminal, 'live_sessions', return_value=[]):
        return funnel.build(s)['items']


class SharedVerdictTests(unittest.TestCase):
    def test_an_actionable_idea_opens_work_through_the_shared_intake(self):
        s = MemoryStore(); calls = []
        row = idea(s, 'idea:vendor', 'The vendor invoice from 12 August is still unpaid and nobody has chased it.')
        assistant.triage_ideas(s, [row], brain(calls=calls))
        a = json.loads(s.get_idea(row['IdeaId'])['ActionJson'])
        self.assertEqual(a['triage']['intent'], 'task'); self.assertIsNone(a['triage'].get('error'))
        self.assertEqual(len(calls), 1); self.assertIn('idea', calls[0].get('subject', '').lower() + json.dumps(calls[0]).lower())
        tid = a.get('tid'); self.assertTrue(tid)
        t = s.get_task(tid)
        self.assertEqual(t['Kind'], 'general'); self.assertEqual(t['Title'], 'Chase the vendor about the unpaid invoice')
        self.assertEqual(s.get_task(tid)['Source'], 'assistant')
        self.assertEqual([i['text'] for i in s.task_checklist(tid)], ['Call the vendor'])

    def test_an_informational_idea_is_fyi_and_makes_no_task(self):
        s = MemoryStore()
        row = idea(s, 'idea:fyi', 'Three vendors sent price updates this week.')
        assistant.triage_ideas(s, [row], brain(intent='fyi'))
        a = json.loads(s.get_idea(row['IdeaId'])['ActionJson'])
        self.assertEqual(a['triage']['intent'], 'fyi'); self.assertFalse(a.get('tid')); self.assertEqual(s.list_tasks(), [])
        items = [i for i in pile(s) if i.get('idea') == row['IdeaId']]
        self.assertEqual([i['lane'] for i in items], ['fyi'])

    def test_an_idea_about_active_work_records_its_verdict_and_duplicates_nothing(self):
        s = MemoryStore()
        tid = s.create_task({'Title': 'Fix the export', 'Kind': 'coding', 'Status': 'in_progress'}, 'owner')
        row = idea(s, 'idea:export', 'TQ-0001 has not moved since Tuesday; the export is still failing.', {'tid': tid})
        assistant.triage_ideas(s, [row], brain())
        a = json.loads(s.get_idea(row['IdeaId'])['ActionJson'])
        self.assertEqual(a['triage']['linked_task'], tid); self.assertEqual(a['tid'], tid)
        self.assertEqual(len(s.list_tasks()), 1)
        self.assertEqual(s.get_task(tid)['Status'], 'in_progress')                # a generated claim completes nothing

    def test_an_actionable_idea_ranks_through_the_work_it_opened_not_a_second_lane(self):
        s = MemoryStore()
        row = idea(s, 'idea:vendor', 'The vendor invoice from 12 August is still unpaid and nobody has chased it.')
        with mock.patch('taskuary.ingest._spawn'):
            assistant.triage_ideas(s, [row], brain())
        tid = json.loads(s.get_idea(row['IdeaId'])['ActionJson'])['tid']
        items = pile(s)
        self.assertFalse([i for i in items if i.get('idea') == row['IdeaId']], 'no assistant-only card beside the task')
        work = [i for i in items if i.get('tid') == tid]
        self.assertTrue(work); self.assertIn(work[0]['lane'], ('asked', 'approve', 'time'))

    def test_saying_the_same_idea_again_does_not_triage_it_again(self):
        s = MemoryStore(); calls = []
        row = idea(s, 'idea:vendor', 'The vendor invoice is unpaid.')
        assistant.triage_ideas(s, [row], brain(intent='fyi', calls=calls))
        again = idea(s, 'idea:vendor', 'The vendor invoice is unpaid.')
        assistant.triage_ideas(s, [again], brain(intent='fyi', calls=calls))
        self.assertEqual(len(calls), 1)

    def test_a_failed_verdict_is_an_error_the_next_run_retries(self):
        s = MemoryStore()
        row = idea(s, 'idea:vendor', 'The vendor invoice is unpaid.')
        def boom(*a, **k): raise RuntimeError('model down')
        assistant.triage_ideas(s, [row], boom)
        a = json.loads(s.get_idea(row['IdeaId'])['ActionJson'])
        self.assertIn('model down', a['triage']['error'])
        items = [i for i in pile(s) if i.get('idea') == row['IdeaId']]
        self.assertIn('triage failed', items[0]['why'].lower())
        assistant.triage_ideas(s, [s.get_idea(row['IdeaId'])], brain(intent='fyi'))
        a = json.loads(s.get_idea(row['IdeaId'])['ActionJson'])
        self.assertEqual(a['triage']['intent'], 'fyi'); self.assertIsNone(a['triage'].get('error'))

    def test_no_brain_leaves_the_idea_pending_not_judged(self):
        s = MemoryStore()
        row = idea(s, 'idea:vendor', 'The vendor invoice is unpaid.')
        assistant.triage_ideas(s, [row], None)
        a = json.loads(s.get_idea(row['IdeaId'])['ActionJson'])
        self.assertEqual(a['triage'].get('pending'), True); self.assertEqual(s.list_tasks(), [])


class NoLoopTests(unittest.TestCase):
    def test_the_assistant_never_reads_its_own_generated_rows_as_arrivals(self):
        s = MemoryStore()
        row = idea(s, 'idea:vendor', 'The vendor invoice from 12 August is still unpaid and nobody has chased it.')
        assistant.triage_ideas(s, [row], brain())
        rows = [m for m in s.feed(limit=50) if m.get('Channel') == 'assistant']
        self.assertTrue(rows, 'the actionable idea left a source row behind its task')
        self.assertNotIn('unpaid', assistant._recent(s))                          # not an arrival to think about
        self.assertFalse([c for c in assistant.candidates(s, assistant.cfg(s)) if 'unpaid' in json.dumps(c)])


if __name__ == '__main__':
    unittest.main()
