"""ONE CHAT FOR EVERY TASK (the owner, 2026-11-06: "one shared chat object for coding and regular ... diff shows up if there is branch or
checkout stuff available"). What the server hands the one chat: whether the task works in a checkout (landing.has_checkout - the header's
Changes and the landing card show then only, whatever its kind), and a helper's own calls named by the call they run under (agents.parent_of),
so they nest under its row instead of interleaving with the main agent's. Invented repo and people, a temp git folder, no network."""
import os, subprocess, tempfile, unittest

from taskuary import agents, landing
from taskuary.store import MemoryStore
from taskuary.testing import Factory


def git(cwd, *a):
    return subprocess.run(['git', '-C', cwd, '-c', 'user.name=Alex Doyle', '-c', 'user.email=alex@northwind.example', *a],
                          capture_output=True, text=True, check=True).stdout.strip()


class CheckoutTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(); self.cwd = self.tmp.name
        git(self.cwd, 'init', '-q', '-b', 'master')
        with open(os.path.join(self.cwd, 'ledger.py'), 'w', encoding='utf-8') as f: f.write('total = 0\n')
        git(self.cwd, 'add', '.'); git(self.cwd, 'commit', '-q', '-m', 'start')
        self.s = MemoryStore(); self.f = Factory(self.s)

    def tearDown(self):
        try: self.tmp.cleanup()
        except OSError: pass

    def test_a_task_works_in_a_checkout_once_its_start_is_marked_whatever_its_kind(self):
        tid = self.f.task(title='Look into the ledger total', kind='general')
        self.assertFalse(landing.has_checkout(self.s, tid))
        landing.mark_start(self.s, tid, self.cwd)
        self.assertTrue(landing.has_checkout(self.s, tid))

    def test_a_session_folder_inside_a_git_repo_is_a_checkout_and_a_plain_folder_is_not(self):
        tid = self.f.task(title='Draft the reply to Erin Blake', kind='general')
        self.assertTrue(landing.has_checkout(self.s, tid, self.cwd))
        with tempfile.TemporaryDirectory() as plain: self.assertFalse(landing.has_checkout(self.s, tid, plain))
        self.assertFalse(landing.has_checkout(self.s, tid, os.path.join(self.cwd, 'missing')))


def test_a_helpers_own_calls_name_the_call_they_run_under():
    out = []
    s = agents.ACPSteps(lambda kind, name, detail=None: out.append((kind, name, detail)), 'claude')
    s({'sessionUpdate': 'tool_call', 'toolCallId': 'h1', 'kind': 'think', 'title': 'Task', 'status': 'in_progress',
       'rawInput': {'description': 'Check the portal pages'}, '_meta': {'claudeCode': {'toolName': 'Task'}}})
    s({'sessionUpdate': 'tool_call', 'toolCallId': 'r1', 'kind': 'read', 'title': 'Read app.js', 'status': 'in_progress',
       'rawInput': {'file_path': 'portal/app.js'}, '_meta': {'claudeCode': {'toolName': 'Read', 'parentToolUseId': 'h1'}}})
    calls = {d['tool_call_id']: d for k, n, d in out if k == 'tool_call'}
    assert 'parent' not in calls['h1'] and calls['r1']['parent'] == 'h1'
    assert agents.parent_of({'_meta': {'parentToolCallId': 'x'}}) == 'x' and agents.parent_of({}) == ''
