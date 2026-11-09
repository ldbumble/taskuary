"""A task an agent is working takes only its own follow-ups (the owner, 2026-11-02: "if new tasks come in and it's not the exact same
thing you are working on, put another agent on it"). A budget task with a coding agent on it took in a different person's question about
another line, and a second thread, at the combine level's "close to its subject" - and the replies got mixed. Evidence and the guide,
never a rule: every task triage may join now carries the agent on it (agent_on_it - working or waiting, what it was put to, its latest
line) and its open to-dos, the guide says a different ask is its own task whatever the level, and a task opened that way dispatches by
the one road every new task takes - another agent in the same checkout does not hold it back."""
import hashlib, json, tempfile, unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

from taskuary import context, general, histgen, ingest, senders, terminal, triage
from taskuary.store import MemoryStore, SQLiteStore
from tests.test_combine_level import ROOM, say

ASK = 'Alex, the rent line in northwind/ledger double counts March - can you fix the budget rollup?'
TODOS = ['Fix the March rent double count', 'Re-run the Q3 budget rollup']


def brain(seen, **extra):
    def llm(system, user, **k):
        seen.append((system, json.loads(user)))
        return json.dumps({'intent': 'task', 'kind': 'coding', 'why': 'scripted', 'title': 'Fix the rent double count', 'summary': 'Gail asks for the fix.',
                           'repository': 'northwind/ledger', 'checklist': TODOS, **extra})
    return llm


def mail(s, ext, body, llm, at='2026-11-02 09:00:00', frm='gail@northwind.example', name='Gail Moreno', conv='AAQk-budget', spawn=None):
    with mock.patch.object(ingest, '_spawn', spawn or mock.Mock()):
        return ingest.ingest_message(s, {'external_id': ext, 'channel': 'email', 'from_email': frm, 'from_name': name, 'conversation_id': conv,
                                         'subject': 'Re: Q3 budget', 'body': body, 'sent_at': at}, llm=llm)


def working(tid, waiting=False):
    "A live coding session on `tid`, as terminal.SESSIONS holds one."
    return mock.patch.dict(terminal.SESSIONS, {'sid1': SimpleNamespace(task_id=tid, alive=True, waiting=lambda: waiting)})


class WhatTriageSees(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = mail(self.s, 'a', ASK, brain([]))['task_id']

    def test_the_threads_task_says_an_agent_is_working_it_and_its_open_to_dos(self):
        seen = []
        with working(self.tid): mail(self.s, 'b', 'Any news on the rent fix?', brain(seen, new_job=None), at='2026-11-02 10:00:00')
        tt = seen[-1][1]['thread_task']
        self.assertEqual(tt['tid'], self.tid)
        self.assertEqual((tt['agent_on_it']['state'], tt['agent_on_it']['kind']), ('working', 'coding'))
        self.assertTrue(tt['agent_on_it']['doing'], "the task's latest line says what it is doing")
        self.assertNotIn('brief', tt['agent_on_it'], 'put to the task\'s own ask, which is not said twice')
        self.assertEqual(tt['open_todos'], TODOS)

    def test_a_parked_session_reads_as_waiting_for_its_next_turn(self):
        seen = []
        with working(self.tid, waiting=True): mail(self.s, 'b', 'Any news?', brain(seen, new_job=None), at='2026-11-02 10:00:00')
        self.assertEqual(seen[-1][1]['thread_task']['agent_on_it']['state'], 'waiting for its next turn')

    def test_no_agent_means_no_agent_field_and_ticked_to_dos_drop_out(self):
        self.s.tick_checklist_item(self.tid, self.s.task_checklist(self.tid)[0]['id'], True, 'owner')
        seen = []; mail(self.s, 'b', 'Any news?', brain(seen, new_job=None), at='2026-11-02 10:00:00')
        tt = seen[-1][1]['thread_task']
        self.assertNotIn('agent_on_it', tt); self.assertEqual(tt['open_todos'], TODOS[1:])

    def test_a_general_agents_brief_is_what_it_was_put_to(self):
        brief = [{'brief': True, 'content': [{'type': 'text', 'text': 'Your Advisor raised this idea: check the March rent accrual.'}]}]
        with mock.patch.object(ingest, 'live_agent', return_value='general'), mock.patch.object(general, 'history', return_value=brief):
            w = ingest.with_agent(self.s, {'tid': self.tid, 'ask': 'Gail asks for the fix.', 'status': 'open'})
        self.assertEqual(w['agent_on_it']['brief'], 'Your Advisor raised this idea: check the March rent accrual.')

    def test_open_work_carries_it_too(self):
        other = mail(self.s, 'o', 'Please also refresh the Payworth export', brain([]), conv='AAQk-other', frm='paula@northwind.example',
                     name='Paula Vance')['task_id']
        seen = []
        hit = [{'tid': self.tid, 'ref': ingest.task_ref(self.tid), 'title': 'Fix the rent double count', 'why': 'the same topic'}]
        with working(self.tid), mock.patch.object(context, 'recent_open', return_value=hit):
            mail(self.s, 'c', 'Separately - the rates line is off too', brain(seen), conv='AAQk-new', frm='paula@northwind.example', name='Paula Vance')
        ow = {w['tid']: w for w in seen[-1][1]['open_work']}
        self.assertEqual(ow[self.tid]['agent_on_it']['state'], 'working'); self.assertNotIn(other, ow)

    def test_a_chat_rooms_tasks_carry_it(self):
        s, seen = MemoryStore(), []
        s.set_setting('owner_email', 'alex@northwind.example', 't')
        llm = lambda system, user, **k: (seen.append(json.loads(user)), json.dumps({'intent': 'task', 'kind': 'general', 'why': 's', 'title': 'Rent fix',
                                         'summary': 's', 'asks_owner': True, 'relationship': 'new'}))[1]
        tid = say(s, 'w1', 'The rent line in the budget app double counts March', '2026-11-01 08:00:00', llm)[0]['task_id']
        with working(tid): say(s, 'w2', 'Can you also add a parking line?', '2026-11-02 10:00:00', llm)
        rt = {t['tid']: t for t in seen[-1]['room_tasks']}
        self.assertEqual(rt[tid]['agent_on_it']['state'], 'working')

    def test_an_owner_written_guide_is_told_what_the_field_is(self):
        seen = []
        with working(self.tid):
            triage.classify_intent({'subject': 's', 'body': 'b', 'from_email': 'gail@northwind.example'}, llm=brain(seen, new_job=None),
                                   system='My own triage rules.', thread={'thread_task': ingest.thread_task(self.s, self.tid)})
        self.assertIn('**An agent already on it**', seen[-1][0])
        self.assertIn('open_todos, on a task', seen[-1][0])


class TheGuide(unittest.TestCase):
    def test_it_says_a_different_ask_is_its_own_task_whatever_the_level(self):
        g = triage.SHIPPED
        self.assertIn('**An agent already on it** (`agent_on_it`)', g)
        self.assertIn('A different request is its own task, with its own agent', g)
        self.assertIn("whatever `combine.level` says about closeness", g)
        self.assertIn('When unsure with an agent on the task, it is a new task.', g)
        # ...said once, where the agent is (2026-11-09): the levels section's "1 to 4 widen nothing" contradicted "IN A CHAT AT 4 TOO"
        self.assertIn('How far a level reaches on a task an agent is working is said under **An agent already on it**', g)
        # ...and at 5 the owner wants one task per subject, agent or not (2026-11-08: "mostly join them unless they are totally unrelated")
        self.assertIn('AT `combine.level` 5 ALL OF THIS GIVES WAY, AND IN A CHAT AT 4 TOO', g); self.assertIn('JOIN UNLESS IT IS TOTALLY UNRELATED', g)
        # ...a stream of issues about one product is one agent's work, and a related fyi line stays on its task (2026-11-08)
        self.assertIn("A STREAM OF ISSUES IS ONE AGENT'S WORK", g); self.assertIn('A LINE THAT IS PART OF A CONVERSATION STAYS IN IT', g)
        self.assertIn('unless an agent is on it (`agent_on_it`, above), when torn means a new one', g)
        self.assertIn('`agent_on_it`, `open_todos`', triage.shipped_section('## 6.'))
        self.assertIs(triage.INTENT_SYSTEM, triage.SHIPPED, 'the fallback is the shipped guide itself, one text')
        self.assertIn('A different request is its own task', triage.FIELDS['agent_on_it'])

    def test_an_unedited_live_triage_md_takes_it_on_restart(self):
        d = tempfile.TemporaryDirectory(ignore_cleanup_errors=True); self.addCleanup(d.cleanup); db = str(Path(d.name) / 't.db')
        old = 'Classify one inbound work message. (an earlier guide)'
        s = SQLiteStore(db)
        s._exec("UPDATE doc SET Content=?, UpdatedBy='template' WHERE Name='triage'", (old,))
        s._exec("UPDATE setting SET Value=? WHERE Name='triage_guide_sha'", (hashlib.sha256(old.encode()).hexdigest(),)); s.close()
        s = SQLiteStore(db); doc = s.doc('triage'); s.close()
        self.assertIn('**An agent already on it**', doc)


class ADifferentAskGetsItsOwnAgent(unittest.TestCase):
    """Scripted triage: with a coding agent on the budget task, a follow-up joins it; a different ask about the same repository opens
    its own task, which starts its own coding agent by the ordinary road."""
    def setUp(self):
        self.s = MemoryStore(); self.tid = mail(self.s, 'a', ASK, brain([]))['task_id']

    def test_a_follow_up_joins_the_task_the_agent_is_on(self):
        with working(self.tid), mock.patch.object(ingest, 'pass_in_why', return_value='scripted'):
            b = mail(self.s, 'b', 'Correction: it is April that double counts, not March.', brain([], new_job=None, refines=True),
                     at='2026-11-02 10:00:00')
        self.assertEqual(b['task_id'], self.tid); self.assertEqual(len(self.s.list_tasks()), 1)

    def test_a_different_ask_on_the_same_repo_opens_a_task_that_starts_its_own_agent(self):
        spawn = mock.Mock()
        with working(self.tid), mock.patch.object(ingest, 'auto_start_ok', return_value=(True, 'scripted')):
            b = mail(self.s, 'b', 'Different thing - can you add a parking line to the ledger export?',
                     brain([], new_job='a parking line in the export, not the rent double count the agent is on', title='Add a parking line'),
                     at='2026-11-02 10:00:00', frm='paula@northwind.example', name='Paula Vance', spawn=spawn)
        self.assertEqual(b['status'], 'created'); self.assertNotEqual(b['task_id'], self.tid)
        started = [(c.args[0].__name__, c.args[2]) for c in spawn.call_args_list]
        self.assertIn(('_auto_code', b['task_id']), started, 'the new task dispatches like any other new task')

    def test_another_agent_in_the_same_checkout_does_not_hold_a_start_back(self):
        new = mail(self.s, 'n', 'Can you add a parking line to the ledger export?', brain([], title='Add a parking line'), conv='AAQk-parking',
                   frm='paula@northwind.example', name='Paula Vance')['task_id']
        peer = [{'tid': self.tid, 'ref': ingest.task_ref(self.tid), 'title': 'Fix the rent double count', 'agent': 'claude', 'files': [], 'started': ''}]
        with mock.patch.object(ingest, 'has_room', return_value=True), mock.patch('taskuary.blackboard.target_cwd', return_value='/code/ledger'), \
             mock.patch('taskuary.blackboard.peers', return_value=peer), mock.patch.object(terminal, 'start_on_task') as start, \
             mock.patch('taskuary.rank.mode_for', return_value='clear'):
            ingest._auto_code(self.s, new)
        start.assert_called_once()
        self.assertTrue(any('1 other agent(s) working in the same checkout' in c['Body'] for c in self.s.list_comments(new)))


if __name__ == '__main__':
    unittest.main()
