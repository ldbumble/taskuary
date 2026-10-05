"""A general agent can do what the CLI agent can, unless the owner narrows it (the owner, 2026-10-05: "they should be
like any agent that can do things ... permissions should be the same as cli agent by default unless edited").

It was born read-only by inheritance - the mail classifier's lockdown, loosened once to a research grant - so it was
told to use the owner's connections (/api/tools/run) while holding no tool that could POST to them. The connection's
own Authority is the dial for what an agent may change there; SQL at 'read' now really is read.
"""
import json
import unittest
from unittest import mock

from fastapi.testclient import TestClient

from taskuary import config, general, reports, server, terminal
from taskuary.store import MemoryStore


def task(store): return store.create_task({'Title': 'Fix his access', 'Kind': 'general', 'Status': 'open'}, 'owner')


def a_claude(store):
    store.upsert_agent('my-claude', 'coding', 'cli', json.dumps({'cmd': 'claude', 'args': ['-p', '--dangerously-skip-permissions']}))


def turn(store, tid, reply='ok', hands=None):
    if hands: store.set_setting('general_agent_hands', hands, 'test')
    seen = {}
    def run_cli(profile, prompt, trace, resume=None, **kwargs):
        args = list(profile.get('args') or [])
        flag = next((f for f in ('--append-system-prompt-file', '--system-prompt-file') if f in args), None)
        system = open(args[args.index(flag) + 1], encoding='utf-8').read() if flag else ''
        seen.update(profile=profile, prompt=f'{system}\n\n{prompt}', env={**(profile.get('env') or {}), **(kwargs.get('extra_env') or {})})
        return reply, None, None
    with mock.patch.dict(terminal.SESSIONS, {}, clear=True), mock.patch('taskuary.agents.run_cli', side_effect=run_cli):
        s = general.start_session(store, tid, pick='cli:my-claude')
        s.send_prompt('Grant him the Financial role', pick='cli:my-claude')
    return seen


class TheDefaultIsTheCliAgentsOwnHandsTests(unittest.TestCase):
    def test_by_default_a_general_agent_keeps_the_cli_profiles_permissions(self):
        store = MemoryStore(); a_claude(store)
        args = turn(store, task(store))['profile']['args']
        self.assertIn('--dangerously-skip-permissions', args)
        self.assertNotIn('--allowedTools', args)

    def test_it_works_in_a_folder_of_its_own_and_knows_who_it_is(self):
        store = MemoryStore(); a_claude(store)
        seen = turn(store, task(store))
        self.assertTrue(seen['profile'].get('cwd'))
        self.assertEqual(seen['env'].get('TASKUARY_TOKEN'), config.load()['server'].get('agent_token'))
        self.assertTrue(seen['env'].get('TASKUARY_URL'))

    def test_it_is_told_which_systems_it_may_use_and_how(self):
        store = MemoryStore(); a_claude(store)
        store.save_connector({'Type': 'mssql', 'Name': 'SQL Server', 'Active': 1, 'Roles': 'report,tool'}, 'test')
        prompt = turn(store, task(store))['prompt']
        self.assertIn('SQL Server', prompt); self.assertIn('/api/tools/run', prompt)
        self.assertIn('authority read', prompt)          # so a write is proposed rather than attempted

    def test_look_only_takes_the_hands_away(self):
        store = MemoryStore(); a_claude(store)
        args = turn(store, task(store), hands='look')['profile']['args']
        self.assertNotIn('--dangerously-skip-permissions', args)


class AChatCanProposeTests(unittest.TestCase):
    def test_a_proposal_in_the_chats_reply_is_queued_for_the_owner(self):
        store = MemoryStore(); a_claude(store); tid = task(store)
        turn(store, tid, reply='I need your yes for the grant.\nTASKUARY-PROPOSE {"action": "run_tool", "type": "mssql", '
                                '"query": "INSERT INTO dbo.UserRoles VALUES (1, 2)"}')
        waiting = store._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (tid,))
        self.assertEqual(len(waiting), 1)


class FakeCursor:
    def __init__(self, cx): self.cx, self.description = cx, [('n',)]
    def execute(self, q): self.cx.ran.append(q); return self
    def fetchmany(self, n): return [(1,)]


class FakeCx:
    def __init__(self): self.ran, self.committed, self.rolled = [], 0, 0
    def cursor(self): return FakeCursor(self)
    def commit(self): self.committed += 1
    def rollback(self): self.rolled += 1
    def __enter__(self): return self
    def close(self): pass
    def __exit__(self, *a):
        if not a[0]: self.commit()                    # pyodbc commits on a clean exit - which was the hole


class SqlReadIsReadTests(unittest.TestCase):
    def run_tool(self, store, body, scope=None):
        cid = store.save_connector({'Type': 'mssql', 'Name': 'SQL Server', 'Active': 1, 'Roles': 'report,tool',
                                    'ConfigJson': json.dumps({'server': 'db.example', 'database': 'UserDb'}),
                                    **({'Scope': scope} if scope else {})}, 'test')
        cx = FakeCx()
        with mock.patch.object(server, 'store', store), mock.patch('taskuary.mssql._connect', return_value=cx):
            out = TestClient(server.app).post('/api/tools/run', json={'type': 'mssql', 'connector_id': cid, **body}).json()
        return out, cx

    def test_at_read_a_batch_that_writes_is_rolled_back(self):
        out, cx = self.run_tool(MemoryStore(), {'query': 'INSERT INTO t VALUES (1); SELECT 1 AS n'})
        self.assertTrue(out['ok'], out); self.assertGreaterEqual(cx.rolled, 1)
        self.assertEqual(cx.committed, 0, 'a read-level connection committed a write')

    def test_the_caller_cannot_ask_for_a_commit(self):
        out, cx = self.run_tool(MemoryStore(), {'query': 'INSERT INTO t VALUES (1); SELECT 1 AS n', '_write': True, 'write': True})
        self.assertEqual(cx.committed, 0)

    def test_at_write_the_owner_raised_it_commits(self):
        out, cx = self.run_tool(MemoryStore(), {'query': 'INSERT INTO t VALUES (1); SELECT 1 AS n'}, scope='write')
        self.assertTrue(out['ok'], out); self.assertEqual(cx.committed, 1)

    def test_a_report_never_writes(self):
        cx = FakeCx()
        with mock.patch('taskuary.mssql._connect', return_value=cx):
            reports.run_mssql({'server': 'db.example', 'database': 'UserDb', 'query': 'SELECT 1 AS n'})
        self.assertEqual(cx.committed, 0)
