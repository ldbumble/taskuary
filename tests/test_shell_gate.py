"""A SHELL STEP THAT LEAVES THE MACHINE WAITS FOR THE OWNER'S PRESS (shellgate.py; the Advisor design rev 2, the owner's ruling 2026-10-28:
hold risky steps on the existing proposal card). A push, a merge, a public post, a publish or a mail an agent runs from its shell is read by
each tool's own grammar, refused to the agent and put on the task with Approve and Dismiss; Approve runs that exact command in the folder it
was held in and tells the agent; Dismiss tells it no. Everything else passes at once. Invented Northwind repositories only (CLAUDE.md)."""
import json, time, unittest
from types import SimpleNamespace
from unittest import mock

from taskuary import hooks, proposals, shellgate as sg, verdicts
from taskuary.store import MemoryStore
from taskuary.testing import Factory


class Reading(unittest.TestCase):
    def test_each_tools_own_words_for_going_out_are_held(self):
        for cmd, what in (('git push origin main', 'push'), ('git -C C:/work/ledger push --force', 'push'), ('cd ledger && git push', 'push'),
                          ('git push --delete origin old-branch', 'push'), ('gh pr merge 12 --squash', 'merge a pull request'),
                          ('gh pr create --fill', 'open a pull request'), ('gh issue comment 7 --body "fixed"', 'public comment'),
                          ('gh api -X DELETE repos/northwind/ledger/releases/3', 'API'), ('gh api repos/northwind/ledger/issues -f title=Bug', 'API'),
                          ('gh release delete v1.2', 'delete a release'), ('glab mr merge 4', 'merge a merge request'), ('npm publish', 'publish'),
                          ('twine upload dist/*', 'publish'), ('docker push northwind/portal:1.0', 'publish'),
                          ('Send-MailMessage -To erin@northwind.example -Subject x', 'email'), ('bash -c "git push origin main"', 'push'),
                          ('FOO=1 git push', 'push')):
            got = sg.acts(cmd)
            self.assertTrue(got, cmd); self.assertIn(what, got[0]['what'], cmd)

    def test_looking_and_working_locally_pass(self):
        for cmd in ('git status', 'git commit -m "push the fix"', 'git log --grep push', 'gh pr view 12', 'gh api repos/northwind/ledger',
                    'echo git push', 'npm install', 'pytest -q', 'rm -rf build', 'git pull', 'git fetch origin', 'gh pr list'):
            self.assertEqual(sg.acts(cmd), [], cmd)


class Holding(unittest.TestCase):
    held_dir = staticmethod(lambda p: p == r'C:\work\ledger')   # only the held folder is there: a blanket isdir would hide bash from shutil.which
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Fix the ledger export')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: self.told.append(text))

    def held(self, cmd='git push origin fix-export'):
        return sg.check(self.s, self.tid, 'run1', cmd, 'Bash', r'C:\work\ledger')

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))

    def heard(self):
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told

    def test_a_push_is_refused_and_put_on_the_task_once(self):
        d = self.held()['hookSpecificOutput']
        self.assertEqual((d['hookEventName'], d['permissionDecision']), ('PreToolUse', 'deny'))
        self.assertIn('held this for the owner', d['permissionDecisionReason']); self.assertIn("push the agent's commits", d['permissionDecisionReason'])
        [rv] = self.pending()
        p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['sid'], p['command'], p['cwd'], p['shell']), ('shell_act', 'run1', 'git push origin fix-export', r'C:\work\ledger', 'Bash'))
        self.assertIn("held before it ran, in the agent's shell", rv['Reason'])
        self.held(); self.assertEqual(len(self.pending()), 1, 'tried again: the same card, not a second')
        self.assertEqual(self.held('git status'), {}); self.assertEqual(len(self.pending()), 1)

    def test_an_agent_cannot_propose_one_itself(self):
        self.assertEqual(proposals.parse('TASKUARY-PROPOSE {"action": "shell_act", "sid": "run1", "command": "git push"}'), [])

    def ran(self, rc, said):
        calls = []
        def run(argv, cwd=None, **kw): calls.append((argv, cwd)); return SimpleNamespace(returncode=rc, stdout=said, stderr='')
        return calls, mock.patch.object(sg.subprocess, 'run', run)

    def test_approve_runs_that_command_in_that_folder_and_tells_the_agent(self):
        self.held(); [rv] = self.pending()
        calls, run = self.ran(0, 'To northwind/ledger\n fix-export -> fix-export')
        with mock.patch('taskuary.workerstate._live', return_value=self.sess), mock.patch.object(sg.os.path, 'isdir', self.held_dir), run:
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertTrue(out['ok'], out)
        self.assertEqual(len(calls), 1); self.assertEqual((calls[0][0][-1], calls[0][1]), ('git push origin fix-export', r'C:\work\ledger'))
        self.assertIn('The owner approved it', self.heard()[0]); self.assertEqual(self.pending(), [])

    def test_a_step_that_fails_says_so_and_runs_nowhere_else(self):
        self.held(); [rv] = self.pending()
        calls, run = self.ran(1, 'rejected: non-fast-forward')
        with mock.patch.object(sg.os.path, 'isdir', self.held_dir), run:
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertIn('non-fast-forward', out['send_error'])
        self.assertTrue(out['send_error'].startswith('The held step failed: '), out['send_error'])
        with mock.patch.object(sg.os.path, 'isdir', return_value=False):
            self.assertRaisesRegex(RuntimeError, 'folder it was held in is gone', sg.perform, self.s, self.tid, json.loads(rv['DraftText']))

    def test_dismiss_tells_the_agent_it_was_not_done(self):
        self.held(); [rv] = self.pending()
        with mock.patch('taskuary.workerstate._live', return_value=self.sess):
            self.assertTrue(verdicts.decide(self.s, rv, 'reject')['ok'])
        self.assertIn('did not approve it', self.heard()[0]); self.assertIn('git push origin fix-export', self.told[0])


class Running(unittest.TestCase):
    """The owner's yes runs in the shell the agent used: Git Bash on Windows, never System32's bash.exe (WSL's launcher, which answered
    an approved push with "no distribution installed" in UTF-16, read as UTF-8 into r\\0i\\0b\\0u\\0t... under "The reply was not sent")."""
    GIT = r'C:\Program Files\Git'

    def bash(self, have, which):
        isfile = lambda p: p in have
        return (mock.patch.object(sg.os, 'name', 'nt'), mock.patch.object(sg.os.path, 'isfile', isfile),
                mock.patch.object(sg.shutil, 'which', lambda n: which.get(n)), mock.patch.dict(sg.os.environ, {'SystemRoot': r'C:\Windows'}),
                mock.patch.dict(sg.os.environ, {'CLAUDE_CODE_GIT_BASH_PATH': ''}))

    def picked(self, have, which):
        a, b, c, d, e = self.bash(have, which)
        with a, b, c, d, e: return sg.git_bash()

    def test_git_bash_beside_git_never_wsl(self):
        gb = self.GIT + r'\bin\bash.exe'
        wsl = {'git': self.GIT + r'\cmd\git.exe', 'bash': r'C:\Windows\System32\bash.exe'}
        self.assertEqual(self.picked({gb, wsl['bash']}, wsl), gb, 'the bash next to git, not the one first on PATH')
        self.assertEqual(self.picked({wsl['bash']}, {'bash': wsl['bash']}), '', "WSL's launcher is never Git Bash")
        self.assertEqual(self.picked({self.GIT + r'\usr\bin\bash.exe'}, {'git': self.GIT + r'\mingw64\bin\git.exe'}), self.GIT + r'\usr\bin\bash.exe')
        a, b, c, d, e = self.bash({wsl['bash']}, {'bash': wsl['bash']})
        with a, b, c, d, e: self.assertRaisesRegex(RuntimeError, 'no Git Bash', sg._argv, 'Bash', 'git push')
        with a, b, c, d, e: self.assertEqual(sg._argv('PowerShell', 'git push')[-2:], ['-Command', 'git push'])

    def test_output_is_read_in_its_own_encoding(self):
        wsl = 'Windows Subsystem for Linux has no installed distributions.\r\nwsl.exe --install <Distro>\r\n'
        self.assertEqual(sg.text(wsl.encode('utf-16')), wsl)                      # with its byte-order mark
        self.assertEqual(sg.text(wsl.encode('utf-16-le')), wsl)                   # without: NULs in every other place
        self.assertEqual(sg.text('To northwind/ledger — done'.encode()), 'To northwind/ledger — done')
        self.assertEqual(sg.text(b'bad \xff byte'), 'bad \ufffd byte')
        self.assertEqual(sg.failed(sg.text(wsl.encode('utf-16-le')), 1),
                         'The held step failed: Windows Subsystem for Linux has no installed distributions. / wsl.exe --install <Distro>')
        self.assertEqual(sg.failed('', 128), 'The held step failed: exit 128')


class Hook(unittest.TestCase):
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Fix the ledger export')
        self.push = {'tool_name': 'Bash', 'tool_input': {'command': 'git push origin main'}, 'session_id': 'c-1', 'cwd': r'C:\work'}

    def hook(self, payload, **pane):
        p = SimpleNamespace(**{'sid': 'run1', 'alive': True, 'task_id': self.tid, 'cwd': r'C:\work', 'argv': ['claude'], 'ext_id': 'c-1',
                               'resumed_from': '', 'store': self.s, 'mode': 'full', 'cli': 'claude', **pane})
        with mock.patch.dict('taskuary.terminal.SESSIONS', {'run1': p}, clear=True): return hooks.browser(payload)

    def held(self): return self.s._rows("SELECT DraftText FROM review WHERE Kind='action' AND Status='pending'")

    def test_the_owners_own_pane_asks_in_the_cli_and_holds_nothing(self):
        self.assertEqual(self.hook({**self.push, 'tool_input': {'command': 'git status'}}), {})
        self.assertEqual(self.hook({**self.push, 'session_id': 'someone-else'}), {}, "not our pane: the owner's own Claude")
        d = self.hook(self.push)['hookSpecificOutput']
        self.assertEqual((d['hookEventName'], d['permissionDecision']), ('PreToolUse', 'ask'), 'asked, never allowed')
        self.assertIn("push the agent's commits", d['permissionDecisionReason'])
        self.assertNotIn('another way', d['permissionDecisionReason']); self.assertNotIn('End your turn', d['permissionDecisionReason'])
        self.assertEqual(self.held(), [], "the CLI's prompt is the approval: no Approve card")
        self.assertTrue(any(a['Action'] == 'shell_act_asked' for a in self.s._rows('SELECT * FROM audit')))
        self.assertIn('git push origin main', self.s.list_comments(self.tid)[-1]['Body'])

    def test_where_nobody_answers_the_cli_it_is_held_for_approve(self):
        for why, pane in (("a stranger's task", {'mode': 'auto'}), ('a CLI whose hook cannot ask', {'cli': 'devin', 'argv': ['claude']})):
            self.assertEqual(self.hook(self.push, **pane)['hookSpecificOutput']['permissionDecision'], 'deny', why)
        self.s.update_task(self.tid, {'Source': 'workflow'}, 'owner')
        self.assertEqual(self.hook(self.push)['hookSpecificOutput']['permissionDecision'], 'deny', "a workflow's run")
        [rv] = self.held(); self.assertEqual(json.loads(rv['DraftText'])['cwd'], r'C:\work')

    def test_a_headless_chat_is_held(self):
        chat = SimpleNamespace(sid='g1', task_id=self.tid, mode='full')            # a general chat: no argv, no pane
        self.assertFalse(sg.asks(self.s, chat))
        self.assertEqual(sg.check(self.s, self.tid, 'g1', 'git push', ask=sg.asks(self.s, chat))['hookSpecificOutput']['permissionDecision'], 'deny')
