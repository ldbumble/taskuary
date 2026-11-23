"""A new task started from the owner's own words is its own thing - not the item on the table (2026-10-01).

Typed while one task was open on the table ("stop sending me the vendor-create mails" over the GL task), the assistant rightly
started a NEW task - and its card, both receipts and the settle named the task on the table. And the new task wore the Advisor's
mark on the rail though the owner had asked for it."""
import contextlib, importlib.util, json, unittest
from unittest import mock

from taskuary import concierge, general, ingest, processing_all
from taskuary.store import MemoryStore


@contextlib.contextmanager
def triage_reads(same_as, seen=None):
    "Triage's verdict on words that start work (ingest.same_work - the one join decider): an open task they already are, or none."
    def judge(store, msg, llm, *a, **k):
        if seen is not None: seen.append(msg)
        return {'intent': 'task', 'same_as': same_as}, {}
    with mock.patch('taskuary.llm.build_llm', return_value=lambda *a, **k: ''), mock.patch.object(ingest, 'judge', judge): yield


class NewTaskFromWordsTests(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore()
        self.dock = general.dock_task(self.s)[0]['TaskId']
        self.table_tid = self.s.create_task({'Title': 'Build the GL version', 'Kind': 'coding', 'Status': 'open'}, 'owner')
        self.table = {'key': f'task:{self.table_tid}', 'kind': 'task', 'lane': 'asked', 'title': 'Build the GL version',
                      'tid': self.table_tid, 'ref': 'TQ-%04d' % self.table_tid}

    def propose(self, text, d_text=''):
        with mock.patch('taskuary.terminal.known_repo', return_value=None), mock.patch('taskuary.terminal.known_repos', return_value=[]):
            return concierge.propose_for(self.s, self.dock, {'verb': 'coding_agent', 'text': d_text}, self.table, text)

    def test_words_make_a_proposal_that_names_none_of_the_table(self):
        p = self.propose('Stop sending me the vendor-create mails unless there is an error')
        self.assertEqual(p['kind'], 'task.create_from_text')
        self.assertEqual((p['key'], p['ref'], p['tid'], p['settles']), (None, None, None, False))
        self.assertNotIn(self.table['ref'], p['say'])
        self.assertNotIn('Build the GL version', p['summary'])

    def test_a_button_with_no_words_still_hands_on_the_item_itself(self):
        p = self.propose('')
        self.assertEqual((p['key'], p['tid']), (self.table['key'], self.table_tid))
        self.assertIn('Build the GL version', p['params']['text'])


class NewsBoxIsTheOneStartTests(unittest.TestCase):
    """F1, the walks 2026-11-18: New's box went through the Assistant's model, which picked a form - "send me this every Monday" with a CSV
    attached landed on an empty SQL "New report" form, his words and his file gone - and refused a code fix "No coding tool is connected"
    behind Developer mode. His words and files go to the one start (POST /api/start -> concierge.handoff_task); the agent does the kind."""
    def setUp(self):
        from fastapi.testclient import TestClient
        from taskuary import config, server
        self.s = MemoryStore()
        for p in (mock.patch.object(server, 'store', self.s), mock.patch.object(general, 'start_session'),
                  mock.patch('taskuary.concierge.brain', return_value=None), mock.patch.object(ingest, 'judge', side_effect=RuntimeError('no triage here'))):
            p.start(); self.addCleanup(p.stop)
        self.c, self.up = TestClient(server.app), config.home() / 'attachments' / 'new-box' / 'october-spend.csv'
        self.up.parent.mkdir(parents=True, exist_ok=True); self.up.write_text('vendor,amount' + chr(10) + 'Payworth,1200' + chr(10), encoding='utf-8')

    def start(self, text, ai=True, **kw):
        with mock.patch('taskuary.capabilities.has_ai', return_value=ai):
            return self.c.post('/api/start', json={'text': text, **kw})

    def test_a_weekly_summary_with_a_csv_is_a_task_with_his_words_and_his_file_its_agent_at_work(self):
        ask = 'Send me the vendor spend summary from this every Monday morning'
        r = self.start(ask, images=[str(self.up)])
        self.assertEqual(r.status_code, 200, r.text)
        t = self.s.get_task(r.json()['taskId'])
        self.assertEqual((t['Kind'], t['Summary']), ('general', ask), "his words alone: the file is the task's Files field")
        from taskuary import outputs, store
        self.assertEqual(store.files_of(t), [str(outputs.folder(t['TaskId']) / 'october-spend.csv')])
        self.assertTrue(r.json()['started']); general.start_session.assert_called_once()
        self.assertNotIn('the Assistant chat', ' '.join(str(c.get('Body')) for c in self.s.list_comments(t['TaskId'], internal=True)))

    def test_a_code_fix_starts_its_agent_whatever_developer_mode_says(self):
        r = self.start('Fix the rounding bug in the ledger totals, checkout at C:/work/ledger')
        self.assertEqual(r.status_code, 200, r.text); self.assertTrue(r.json()['started'])

    def test_a_fix_in_the_folder_he_names_is_made_tested_and_committed_by_the_general_agent(self):
        """Design round 3, 2026-11-18: "Fix the rounding bug in the ledger totals - my checkout is at <path>" from New was refused on every AI
        ("this general task has no way to switch to coding", "add your checkout as a repository"). Developer mode off, the general agent with
        a shell is told what it can do here, reads and changes the folder he named, runs its test and commits there - his words the go-ahead."""
        import os, subprocess, sys
        from pathlib import Path
        from taskuary import apiagent, browserview as bv, capabilities, llm, readgate
        repo = Path.home() / 'work' / 'ledger'; repo.mkdir(parents=True, exist_ok=True)     # ...his own folder, outside every one the task owns
        (repo / 'totals.py').write_text('def total(xs): return int(sum(xs))' + chr(10), encoding='utf-8')
        (repo / 'test_totals.py').write_text(chr(10).join(['import os, sys', 'sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))',
                                                           'from totals import total', 'assert total([1.25, 1.30]) == 2.55, total([1.25, 1.30])', '']), encoding='utf-8')
        who = {**os.environ, 'GIT_AUTHOR_NAME': 'Alex Doyle', 'GIT_AUTHOR_EMAIL': 'alex@northwind.example', 'GIT_COMMITTER_NAME': 'Alex Doyle',
               'GIT_COMMITTER_EMAIL': 'alex@northwind.example'}
        git = lambda *a: subprocess.run(['git', *a], cwd=repo, capture_output=True, text=True, env=who)
        git('init', '-q'); git('add', '.'); git('commit', '-qm', 'totals')
        test = lambda: subprocess.run([sys.executable, '-I', str(repo / 'test_totals.py')], capture_output=True)
        self.assertNotEqual(test().returncode, 0, 'the test fails first')
        r = self.start(f'Fix the rounding bug in the ledger totals that is failing CI. My checkout is at {repo}')
        tid = r.json()['taskId']
        go = f"Set-Location -LiteralPath '{repo}'; " if os.name == 'nt' else f'cd "{repo}" && '
        steps = [('file_read', {'path': str(repo / 'totals.py')}),
                 ('file_edit', {'path': str(repo / 'totals.py'), 'old': 'int(sum(xs))', 'new': 'round(sum(xs), 2)'}),
                 ('run_command', {'command': go + 'python test_totals.py', 'why': 'run the test'}),
                 ('run_command', {'command': go + 'git commit -qam "Round totals to cents"', 'why': 'commit'})]
        seen, said = [], []
        class Card:
            def chat(self, msgs, tools, max_tokens, **kw):
                seen.append((msgs[0]['content'] + str(msgs[1]['content']), [t['function']['name'] for t in tools]))
                said.extend(m['content'] for m in msgs[len(said) and 0:] if m.get('role') == 'tool' and m['content'] not in said)
                if not steps: return {'content': 'Fixed: totals round to cents, the test passes, committed.'}
                name, a = steps.pop(0)
                return {'content': '', 'tool_calls': [{'id': f'c{len(steps)}', 'type': 'function', 'function': {'name': name, 'arguments': json.dumps(a)}}]}
        class Shell:                       # ...the stand-in world's shell: the gate in front of it is the real one (hooks.command_gate)
            pid = 4242
            def __init__(self, argv, **kw):
                line = ' '.join(map(str, argv))
                ran = test() if 'test_totals.py' in line else git('commit', '-qam', 'Round totals to cents') if 'commit' in line else None
                self.returncode, self.out = (ran.returncode, (ran.stdout or b'') if isinstance(ran.stdout, bytes) else str(ran.stdout or '').encode()) if ran else (1, b'?')
            def communicate(self, timeout=None): return self.out, b''
        session = general.GeneralSession(self.s, tid)
        session.pick, session.provider, session.model = 'connector:1', 'Northwind AI', ''
        with mock.patch.object(llm, 'build_llm', return_value=Card()), mock.patch.object(bv, 'installed', return_value=False), \
             mock.patch.object(bv, 'can_set_up', return_value=False), mock.patch.object(apiagent, 'taskuary_tools', return_value=[]), \
             mock.patch('taskuary.spawn.popen', side_effect=Shell):
            session.send_prompt(self.s.get_task(tid)['Summary'], brief=True)
        prompt, tools = seen[0]
        self.assertIn(str(repo), prompt); self.assertIn(capabilities.HANDS['all'], prompt)
        self.assertNotIn('non-coding', prompt)
        self.assertTrue({'file_edit', 'run_command'} <= set(tools))
        self.assertIn('def total', said[0], 'his folder is read at once, never held for a press')
        self.assertEqual(test().returncode, 0, said)
        self.assertIn('Round totals to cents', git('log', '-1', '--format=%s').stdout, said)

    def test_a_file_attached_in_new_is_named_in_the_first_turn_under_his_own_ask(self):
        """Walk 9, 2026-11-23: five asks with a file attached in New - "make a chart of monthly spend from this" + budget.csv - and the agent's
        first turn named no file ("your request came through with no figures or attachment"), while the same file on a chat line was read.
        His ask was headed "TASKUARY'S WORDS ON THIS TURN - not the owner's", and triage's reading ("the message has no body or attached data")
        replaced his words as the task's summary that my_task hands the agent."""
        from taskuary import apiagent, browserview as bv, llm, outputs, agenttools
        seen = []
        class Card:
            def chat(self, msgs, tools, max_tokens, **kw): seen.append(msgs[0]['content'] + str(msgs[1]['content'])); return {'content': 'Done.'}
        def opened(store, tid, **kw):
            s_ = general.GeneralSession(store, tid); s_.pick, s_.provider, s_.model = 'connector:1', 'Northwind AI', ''
            return s_
        general.start_session.side_effect = opened
        class Now:                         # ...the first turn, run where it is started
            def __init__(self, target, args=(), **kw): self.target, self.args = target, args
            def start(self): self.target(*self.args)
        ask = 'Make a chart of monthly spend from this.'
        with mock.patch.object(llm, 'build_llm', return_value=Card()), mock.patch.object(bv, 'installed', return_value=False), \
             mock.patch.object(bv, 'can_set_up', return_value=False), mock.patch.object(apiagent, 'taskuary_tools', return_value=[]), \
             mock.patch('taskuary.capabilities.has_ai', return_value=True), mock.patch('taskuary.concierge.threading', mock.Mock(Thread=Now)), mock.patch('taskuary.ingest.threading', mock.Mock(Thread=Now)):
            tid = concierge.handoff_task(self.s, ask, 'general', 'owner', said=ask, files=[str(self.up)], door='New')['taskId']
        self.assertTrue(seen, 'the first turn ran')
        self.assertIn(str(outputs.folder(tid) / 'october-spend.csv'), seen[0])
        self.assertNotIn("TASKUARY'S WORDS", seen[0])
        mine = agenttools.call(self.s, tid, 'my_task', {}, {})
        self.assertNotIn('no attached data', mine); self.assertIn('october-spend.csv', mine)

    def test_with_no_ai_nothing_is_made_and_the_line_carries_its_way_past(self):
        r = self.start('Find three caterers near the office', ai=False)
        self.assertEqual(r.status_code, 422); self.assertEqual(self.s.list_tasks(None), [])
        self.assertIn('No AI is connected', r.json()['detail']); self.assertEqual(r.json()['fix']['label'], 'Connect an AI')

    def test_an_ask_from_new_is_a_new_task_at_once_never_read_by_triage_first(self):
        # the owner, 2026-11-22: "it should not go through triage, no one asked for that. It should create new task right away"
        there = self.s.create_task({'Title': 'Find caterers for the offsite', 'Kind': 'general', 'Status': 'open'}, 'owner')
        seen, asked = [], []
        with triage_reads(there, seen), mock.patch.object(general, 'take_line') as told, \
             mock.patch('taskuary.triage.classify_intent', side_effect=lambda *a, **k: asked.append(a) or {}):
            r = self.start('Find three caterers near the office for the offsite')
        self.assertNotEqual(r.json()['taskId'], there); self.assertFalse(r.json().get('joined'))
        self.assertEqual((seen, asked), ([], []), 'no triage reading, before the task stands or after'); told.assert_not_called()
        # ...HIS WORDS STAY HIS (2026-11-23): no summary, no to-dos read out of them - the one box is his ask as typed; its agent reads it
        t, ask = self.s.get_task(r.json()['taskId']), 'Find three caterers near the office for the offsite'
        self.assertEqual((t['Summary'], [i['text'] for i in self.s.task_checklist(t['TaskId'])]), (ask, [ask]))

    def test_his_ask_through_the_assistant_never_passes_triage_either(self):
        """Every door his own ask comes by - New, the phone, the Assistant's hand-off - is the one start (handoff_task), and none of them
        asks triage whether it is open work, how hard it is, or what its steps are: it is a task of its own, its agent at work on his words."""
        there = self.s.create_task({'Title': 'Find caterers for the offsite', 'Kind': 'general', 'Status': 'open'}, 'owner')
        seen, asked = [], []
        with triage_reads(there, seen), mock.patch('taskuary.triage.classify_intent', side_effect=lambda *a, **k: asked.append(a) or {}), \
             mock.patch.object(concierge, '_handoff_brief', return_value='Find three caterers near the office'), \
             mock.patch.object(concierge, 'start_refusal', return_value=''):
            made = concierge.handoff_task(self.s, 'Find three caterers near the office', 'general', 'owner')
        self.assertNotEqual(made['taskId'], there); self.assertFalse(made.get('joined'))
        self.assertEqual((seen, asked), ([], []))
        self.assertIsNone(self.s.task_judged(made['taskId']).get('Difficulty'), 'nothing judged how hard it is')


class AgentsNewTaskIsTheSameRoadTests(unittest.TestCase):
    """The owner's live app, 2026-11-18: an agent on one task started "the bed board" as a new task while a chat's task for the same work was
    open - two tasks, one job. The new_task tool asks the model first, as every start does (samework): the same work hears it there."""
    def test_the_same_work_open_already_is_told_and_nothing_is_made(self):
        from taskuary import server
        s = MemoryStore()
        there = s.create_task({'Title': 'Add a daily rate to the bed boards', 'Kind': 'coding', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        here = s.create_task({'Title': 'Weekly census review', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        body = server.AgentNewTaskBody(task_id=here, title='Bed board daily rate', ask='Add the daily rate column to the bed board', kind='coding')
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only'), triage_reads(there),              mock.patch.object(general, 'to_agent') as told, mock.patch.object(server, '_start_new_task') as started:
            out = server.agent_new_task(body, None)
        self.assertEqual((out['task'], out['already']), ('TQ-%04d' % there, True)); self.assertEqual(len(s.list_tasks(None)), 2)
        started.assert_not_called(); self.assertEqual(told.call_args.args[1], there)

    def test_an_open_task_no_agent_ever_worked_starts_its_agent_with_the_ask(self):
        """A dead end (rule 4): general.to_agent hands nothing to a task no agent ever worked, and the joined ask vanished. That task's agent is
        started by the dispatch door with the ask as its opening Taskuary note."""
        from taskuary import server
        s = MemoryStore()
        there = s.create_task({'Title': 'Add a daily rate to the bed boards', 'Kind': 'coding', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        here = s.create_task({'Title': 'Weekly census review', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        body = server.AgentNewTaskBody(task_id=here, title='Bed board daily rate', ask='Add the daily rate column to the bed board', kind='coding')
        seen = []
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only'), triage_reads(there),              mock.patch.object(server, 'dispatch_task', side_effect=lambda tid, b, bg: seen.append((tid, b)) or {'started': True, 'taskId': tid}):
            out = server.agent_new_task(body, None)
        self.assertEqual(out['task'], 'TQ-%04d' % there); self.assertEqual(len(s.list_tasks(None)), 2)
        (tid, b), = seen
        self.assertEqual((tid, b.kind, b.app_words), (there, 'coding', True))
        self.assertIn('Add the daily rate column to the bed board', b.instruction)


class AdvisorMarkTests(unittest.TestCase):
    def test_only_an_advisor_idea_wears_the_advisor_mark(self):
        idea = {'Source': 'assistant', 'SourceRef': 'assistant:idea:42'}
        self.assertTrue(processing_all.advisor_task(idea))
        for ref in ('assistant:handoff', 'assistant:agent', 'assistant:setup', 'assistant:playbook'):
            self.assertFalse(processing_all.advisor_task({'Source': 'assistant', 'SourceRef': ref}), ref)
        self.assertEqual(processing_all.task_mark([idea]), 'assistant')
        self.assertIsNone(processing_all.task_mark([{'Source': 'assistant', 'SourceRef': 'assistant:handoff'}]))
        self.assertEqual(processing_all.task_mark([{'Source': 'email'}]), 'email')


if __name__ == '__main__':
    unittest.main()


class SameWorkIsTriagesDecisionTests(unittest.TestCase):
    """ONE JOIN DECIDER (one road per decision, #2): whether words that start work are an open task's was asked of a model of its own (samework),
    beside triage's same_as for every message - two deciders of one question. Triage reads both now: the same open work, the same verdict."""
    def test_his_words_are_read_by_triage_as_a_message_is_and_samework_is_gone(self):
        s = MemoryStore()
        fix = s.create_task({'Title': 'Fix the ledger rounding bug', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        words = 'The northwind/ledger totals are a cent off at month end again - fix the rounding'
        seen = []
        with triage_reads(fix, seen): self.assertEqual(ingest.same_work(s, words), fix)
        [msg] = seen                                     # one triage reading of them, as of any message - its same_as is the join
        self.assertEqual((msg['body'], msg['from_name'], msg['channel']), (words, ingest.OWNER_WORDS, ingest.WORDS_CHANNEL))
        self.assertIsNone(importlib.util.find_spec('taskuary.samework'), 'the second decider is gone')

    def test_new_and_an_agents_new_task_join_by_the_same_reading(self):
        """Two doors, one question: his words in New and an agent's new_task ask triage alike, and land on the same open task."""
        from taskuary import server
        s = MemoryStore()
        there = s.create_task({'Title': 'Fix the ledger rounding bug', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        here = s.create_task({'Title': 'Month-end close', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        seen = []
        with triage_reads(there, seen), mock.patch.object(general, 'take_line'), mock.patch.object(general, 'to_agent', return_value='told') as told,                 mock.patch('taskuary.capabilities.has_ai', return_value=True):
            with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only'):
                agents = server.agent_new_task(server.AgentNewTaskBody(task_id=here, title='Ledger rounding', ask='Fix the ledger rounding at month end'), None)
        # ...an agent's new_task asks whether the work is open already (New does not - the owner, 2026-11-22)
        self.assertEqual(agents['task'], 'TQ-%04d' % there)
        self.assertEqual([m['channel'] for m in seen], [ingest.WORDS_CHANNEL])
        self.assertEqual([c.kwargs['frm'] for c in told.call_args_list], ['taskuary'], "the agent's words as Taskuary's")

    def test_who_asks_skip_and_a_closed_task_are_kept(self):
        s = MemoryStore()
        fix = s.create_task({'Title': 'Fix the ledger rounding bug', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        seen = []
        with triage_reads(fix, seen):
            self.assertIsNone(ingest.same_work(s, 'Fix the ledger rounding', skip={fix}))          # never the task that asks
            self.assertEqual(ingest.same_work(s, 'Fix the ledger rounding', who='Erin Blake on Teams'), fix)
            s.update_task(fix, {'Status': 'done'}, 'owner')
            self.assertIsNone(ingest.same_work(s, 'Fix the ledger rounding'), 'a closed task is no join for new work')
        self.assertEqual(seen[-2]['from_name'], 'Erin Blake on Teams')
        with mock.patch('taskuary.llm.build_llm', return_value=None):
            self.assertIsNone(ingest.same_work(s, 'Fix the ledger rounding'), 'no triage brain: new work')


def test_a_task_its_agent_finished_is_never_the_work_new_words_join():
    """Round 4, 2026-11-22: an ask to get a course approved joined the open task that had only kept a fact - its turn said nothing was left.
    The owner: "a new job is a new job"."""
    import json as _json
    s = MemoryStore()
    done = s.create_task({'Title': 'Remember who signs training', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
    s.add_comment(done, 'assistant', general.SUMMARY_TYPE, _json.dumps({'did': 'Kept it.', 'nothing_left': True}))
    with triage_reads(done): assert ingest.same_work(s, 'Get the Trainly course approved') is None
    s.add_comment(done, 'assistant', general.SUMMARY_TYPE, _json.dumps({'did': 'Started.', 'on_you': ['Pick a vendor']}))
    with triage_reads(done): assert ingest.same_work(s, 'Get the Trainly course approved') == done
