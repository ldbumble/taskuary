"""A new task started from the owner's own words is its own thing - not the item on the table (2026-10-01).

Typed while one task was open on the table ("stop sending me the vendor-create mails" over the GL task), the assistant rightly
started a NEW task - and its card, both receipts and the settle named the task on the table. And the new task wore the Advisor's
mark on the rail though the owner had asked for it."""
import json, unittest
from unittest import mock

from taskuary import concierge, general, processing_all
from taskuary.store import MemoryStore


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
                  mock.patch('taskuary.concierge.brain', return_value=None)):
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
        self.assertEqual((t['Kind'], general.split_files(t['Summary'])['text'].strip()), ('general', ask))
        from taskuary import outputs
        self.assertTrue((outputs.folder(t['TaskId']) / 'october-spend.csv').exists() or 'october-spend.csv' in t['Summary'])
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

    def test_with_no_ai_nothing_is_made_and_the_line_carries_its_way_past(self):
        r = self.start('Find three caterers near the office', ai=False)
        self.assertEqual(r.status_code, 422); self.assertEqual(self.s.list_tasks(None), [])
        self.assertIn('No AI is connected', r.json()['detail']); self.assertEqual(r.json()['fix']['label'], 'Connect an AI')

    def test_the_same_work_open_already_hears_it_there(self):
        there = self.s.create_task({'Title': 'Find caterers for the offsite', 'Kind': 'general', 'Status': 'open'}, 'owner')
        llm = lambda system, user, **k: json.dumps({'same_as': there})
        with mock.patch('taskuary.concierge.brain', return_value=llm), mock.patch.object(general, 'take_line') as told:
            r = self.start('Find three caterers near the office for the offsite')
        self.assertEqual((r.json()['taskId'], r.json()['joined']), (there, True)); self.assertEqual(len(self.s.list_tasks(None)), 1)
        self.assertEqual(told.call_args.args[1:3], (there, 'Find three caterers near the office for the offsite'))


class AgentsNewTaskIsTheSameRoadTests(unittest.TestCase):
    """The owner's live app, 2026-11-18: an agent on one task started "the bed board" as a new task while a chat's task for the same work was
    open - two tasks, one job. The new_task tool asks the model first, as every start does (samework): the same work hears it there."""
    def test_the_same_work_open_already_is_told_and_nothing_is_made(self):
        from taskuary import server
        s = MemoryStore()
        there = s.create_task({'Title': 'Add a daily rate to the bed boards', 'Kind': 'coding', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        here = s.create_task({'Title': 'Weekly census review', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        llm = lambda system, user, **k: json.dumps({'same_as': there})
        body = server.AgentNewTaskBody(task_id=here, title='Bed board daily rate', ask='Add the daily rate column to the bed board', kind='coding')
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only'), mock.patch('taskuary.concierge.brain', return_value=llm),              mock.patch.object(general, 'tell') as told, mock.patch.object(server, '_start_new_task') as started:
            out = server.agent_new_task(body, None)
        self.assertEqual((out['task'], out['already']), ('TQ-%04d' % there, True)); self.assertEqual(len(s.list_tasks(None)), 2)
        started.assert_not_called(); self.assertEqual(told.call_args.args[1], there)

    def test_an_open_task_no_agent_ever_worked_starts_its_agent_with_the_ask(self):
        """A dead end (rule 4): general.tell hands nothing to a task no agent ever worked, and the joined ask vanished. That task's agent is
        started by the dispatch door with the ask as its opening Taskuary note."""
        from taskuary import server
        s = MemoryStore()
        there = s.create_task({'Title': 'Add a daily rate to the bed boards', 'Kind': 'coding', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        here = s.create_task({'Title': 'Weekly census review', 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        llm = lambda system, user, **k: json.dumps({'same_as': there})
        body = server.AgentNewTaskBody(task_id=here, title='Bed board daily rate', ask='Add the daily rate column to the bed board', kind='coding')
        seen = []
        with mock.patch.object(server, 'store', s), mock.patch.object(server, '_own_task_only'), mock.patch('taskuary.concierge.brain', return_value=llm),              mock.patch.object(server, 'dispatch_task', side_effect=lambda tid, b, bg: seen.append((tid, b)) or {'started': True, 'taskId': tid}):
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


class SameWorkIsTheSameJobTests(unittest.TestCase):
    """The Codex walk, 2026-11-19: a colleague's ask landed on his code fix in the same system. The check is the model's (rule 2) - it is shown
    each open task's ask in full and who asked it, and who asks the new work, so a sign-up list and a code fix on one system read as two jobs."""
    def test_the_model_reads_each_ask_in_full_and_who_asked(self):
        from taskuary import samework
        s = MemoryStore()
        long_ask = 'Fix the rounding bug in the northwind/ledger totals that makes CI fail. ' + 'The month-end entries lose a cent. ' * 8 + 'END-OF-ASK'
        fix = s.create_task({'Title': 'Fix the ledger rounding bug', 'Summary': long_ask, 'Kind': 'general', 'Status': 'open', 'OriginBase': 'owner'}, 'owner')
        seen = []
        def llm(system, user, **kw): seen.append((system, user)); return json.dumps({'same_as': None})
        got = samework.same_open_task(s, 'Sign up for a trial account on each of the 13 vendor sites on the internal list', llm=llm, who='Erin Blake on Teams')
        self.assertIsNone(got)
        system, user = seen[0]
        self.assertIn('END-OF-ASK', user)
        self.assertIn('asked by the owner himself', user); self.assertIn('THE NEW WORK (asked by Erin Blake on Teams)', user)
        self.assertIn('doing one would do the other', system)
        self.assertEqual(samework.same_open_task(s, 'Fix the ledger rounding', llm=lambda *a, **k: json.dumps({'same_as': fix})), fix)
