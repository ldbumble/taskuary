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
                          ('FOO=1 git push', 'push'), ('curl -X POST https://hooks.vendor.example/notify -d "{}"', 'send data to hooks.vendor.example'),
                          ('powershell -Command "Invoke-RestMethod -Method Post -Uri https://api.vendor.example/pay -Body $b"', 'send data')):
            got = sg.acts(cmd)
            self.assertTrue(got, cmd); self.assertIn(what, got[0]['what'], cmd)

    def test_looking_and_working_locally_pass(self):
        for cmd in ('git status', 'git commit -m "push the fix"', 'git log --grep push', 'gh pr view 12', 'gh api repos/northwind/ledger',
                    'echo git push', 'npm install', 'pytest -q', 'rm -rf build', 'git pull', 'git fetch origin', 'gh pr list',
                    'curl -s https://docs.northwind.example/budget', 'curl -s -X POST http://127.0.0.1:7787/api/agent/tick -d "{}"'):
            self.assertEqual(sg.acts(cmd), [], cmd)


class Holding(unittest.TestCase):
    held_dir = staticmethod(lambda p: p == r'C:\work\ledger')   # only the held folder is there: a blanket isdir would hide bash from shutil.which
    def setUp(self):
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Fix the ledger export')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: self.told.append(text))
        proposals._PRESSED.clear()       # a store's ids start at 1 again: an earlier test's press is not this one's

    def held(self, cmd='git push origin fix-export'):
        return sg.check(self.s, self.tid, 'run1', cmd, 'Bash', r'C:\work\ledger')

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))

    def heard(self):
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told

    def test_an_http_write_off_this_machine_is_held_like_a_push_on_the_hook_road(self):
        """The north-star audit, 2026-11-10: a CLI's `curl -X POST` to an outside host went out unseen on the hook road - only the ACP road
        read HTTP writes, and refused them flat. One reading of the command (shellgate.acts) now, the same Approve card a push gets."""
        cmd = 'curl -X POST https://hooks.vendor.example/notify -d "{}"'
        d = hooks.command_gate(self.s, self.tid, 'run1', cmd, 'Bash', r'C:\work\ledger')['hookSpecificOutput']
        self.assertEqual(d['permissionDecision'], 'deny'); self.assertIn('held this for the owner', d['permissionDecisionReason'])
        [rv] = self.pending(); p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['command']), ('shell_act', cmd)); self.assertIn('send data to hooks.vendor.example', p['what'])
        self.assertEqual(hooks.command_gate(self.s, self.tid, 'run1', 'curl -s -X POST http://127.0.0.1:7787/api/agent/tick -d "{}"', 'Bash', ''), {})

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
        self.assertIn(rv['ReviewId'], proposals._PRESSED, 'its told turn will not supersede it under the press')

    def test_a_step_that_fails_says_so_and_runs_nowhere_else(self):
        self.held(); [rv] = self.pending()
        calls, run = self.ran(1, 'rejected: non-fast-forward')
        with mock.patch.object(sg.os.path, 'isdir', self.held_dir), run:
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertIn('non-fast-forward', out['send_error'])
        self.assertTrue(out['send_error'].startswith('The held step failed: '), out['send_error'])
        with mock.patch.object(sg.os.path, 'isdir', return_value=False):
            self.assertRaisesRegex(RuntimeError, 'folder it was held in is gone', sg.perform, self.s, self.tid, json.loads(rv['DraftText']))

    # the owner, 2026-11-09: a held run declined in the agent's chat stood on as "Approve runs: ..." after the agent had asked something else
    # ...and the owner, 2026-11-10: "once youa re passed it, it should stay where it is with buttons grayed out" - the conversation moving on
    # passes every card of the task (proposals.move_on), whichever session held it
    def test_the_owner_speaking_to_that_session_again_settles_its_held_step(self):
        self.held(); sg.check(self.s, self.tid, 'other', 'git push origin other', 'Bash', r'C:\work\ledger')
        self.assertEqual(len(proposals.move_on(self.s, self.tid)), 2)
        self.assertEqual(self.pending(), [])
        gone = self.s._one("SELECT * FROM review WHERE TaskId=? AND Status='superseded'", (self.tid,))
        self.assertEqual(gone['DecideNote'], proposals.SET_ASIDE); self.assertTrue(proposals.passed(gone))

    def test_the_prompt_hook_moves_past_it_and_a_step_being_approved_is_not_touched(self):
        self.held(); [rv] = self.pending()
        t = SimpleNamespace(store=self.s, task_id=self.tid, sid='run1', bg={})
        with mock.patch.object(proposals, '_PRESSED', {rv['ReviewId']: time.time()}):
            hooks._events(t, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'carry on'})
            self.assertEqual(len(self.pending()), 1, 'its own Approve is telling the agent - never superseded under the press')
        hooks._events(t, {'hook_event_name': 'UserPromptSubmit', 'prompt': '<task-notification>done</task-notification>'})
        self.assertEqual(len(self.pending()), 1, 'a background wake is not the owner moving on')
        hooks._events(t, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'no, leave the checkout - is it ready to push?'})
        self.assertEqual(self.pending(), [])

    def test_the_agents_own_words_for_the_call_ride_on_the_card(self):
        sg.check(self.s, self.tid, 'run1', 'git push origin fix-export', 'Bash', r'C:\work\ledger', about='  ship the export fix  ')
        [rv] = self.pending(); self.assertEqual(json.loads(rv['DraftText'])['about'], 'ship the export fix')

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
                         'The held step failed: Windows Subsystem for Linux has no installed distributions.')
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

    def test_an_agent_with_no_terminal_is_not_said_to_have_one_asking(self):
        """Agent walk 2, 2026-11-10: "The agent asked to push ... - its terminal asks you to allow it" on a coding agent that talks ACP. It
        has no terminal: the ask goes back to Taskuary's own gate, which had answered the push with the landing card."""
        d = self.hook(self.push, acp=True)['hookSpecificOutput']
        self.assertEqual(d['permissionDecision'], 'ask', "still the CLI's ask: acpgate answers it")
        self.assertEqual([c['Body'] for c in self.s.list_comments(self.tid) if 'terminal' in c['Body']], [])
        self.assertTrue(any(a['Action'] == 'shell_act_asked' for a in self.s._rows('SELECT * FROM audit')))
        self.assertEqual(self.held(), [])

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


class Deleting(unittest.TestCase):
    """A DELETE ON THE OWNER'S COMPUTER WAITS (the desktop stress test, 2026-11-03): asked to remove the folder it had just unzipped into
    Downloads, a general agent ran Remove-Item -Recurse -Force at once - permanent, not in the Recycle Bin. Its own folder and temp are its."""
    def setUp(self):
        import os, tempfile
        self.os, self.home = os, tempfile.mkdtemp(dir=os.path.expanduser('~'))      # never under temp: temp is the agent's to tidy
        self.addCleanup(__import__('shutil').rmtree, self.home, True)
        self.cwd = os.path.join(self.home, '.taskuary', 'scratch'); os.makedirs(self.cwd)
        self.dl = os.path.join(self.home, 'Downloads', 'notes-unzipped')
        env = mock.patch.dict(os.environ, {'USERPROFILE': self.home, 'HOME': self.home}); env.start(); self.addCleanup(env.stop)
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Unzip the notes')

    def held(self, cmd): return sg.acts(cmd, self.cwd)

    def test_the_stress_tests_own_line_is_held_and_named(self):
        # the agent's PowerShell, in shape: the folder set in a variable on the same line, then removed
        cmd = ('$dst="$env:USERPROFILE\\Downloads\\notes-unzipped"; Remove-Item $dst -Recurse -Force -Confirm:$false; '
               '"folder exists: $(Test-Path $dst)"')
        if self.os.name != 'nt': cmd = cmd.replace('\\', '/')
        [a] = self.held(cmd)
        self.assertEqual((a['what'], a['why']), ('delete notes-unzipped in Downloads', "it can't be undone"))

    def test_a_delete_outside_its_folder_is_held_by_each_tools_name(self):
        for cmd in (f'rm -rf "{self.dl}"', 'rm -rf ~/Downloads/notes-unzipped', 'rm -r $HOME/Downloads/notes-unzipped',
                    f'Remove-Item -LiteralPath "{self.dl}" -Recurse -ErrorAction SilentlyContinue', f'if (Test-Path x) {{ Remove-Item "{self.dl}" }}',
                    f'bash -c "rm -rf {self.dl}"', f'find "{self.dl}" -name "*.txt" -delete', 'rm -rf ../../Downloads'):
            [a] = self.held(cmd)
            self.assertTrue(a['what'].startswith('delete '), cmd); self.assertEqual(a['why'], "it can't be undone", cmd)
        self.assertIn('notes-unzipped in Downloads', self.held(f'rm -rf "{self.dl}"')[0]['what'])

    def test_a_cd_first_moves_where_a_relative_delete_lands(self):
        # the stress test's second delete, word for word in shape: into Downloads, then a relative rm - it passed as the agent's own folder
        [a] = self.held('cd ~/Downloads && find notes-unzipped | sort && rm -rf notes-unzipped && ls -d notes-unzipped 2>&1; ls -l notes.zip')
        self.assertEqual(a['what'], 'delete notes-unzipped in Downloads')
        self.assertTrue(self.held(f'Set-Location "{self.home}"; Remove-Item -Recurse Downloads'))
        self.assertTrue(self.held(f'cmd /c "cd /d {self.home} && rd /s /q Downloads"'))
        self.assertTrue(self.held('cd "$somewhere" && rm -rf notes'), 'a cd it cannot follow leaves the delete unread - held')
        self.assertEqual(self.held('cd out && rm -rf old'), [], 'a cd within its own folder stays its own')

    def test_what_it_cannot_read_is_held_never_let_through(self):
        vb = 'Add-Type -AssemblyName Microsoft.VisualBasic; [Microsoft.VisualBasic.FileIO.FileSystem]::DeleteDirectory("C:\\x\\notes", \'OnlyErrorDialogs\', \'{}\')'
        for cmd in ('rm -rf "$target"', 'Get-ChildItem C:/x -Filter *.tmp | Remove-Item', 'python -c "import shutil; shutil.rmtree(p)"',
                    '[IO.Directory]::Delete($p, $true)', vb.format('DeletePermanently')):
            [a] = self.held(cmd)
            self.assertEqual(a['what'], 'delete files on this computer', cmd)
        # ...while the Recycle Bin can be undone - the agent's own pick in the stress test - and passes
        self.assertEqual(self.held(vb.format('SendToRecycleBin')), [])

    def test_its_own_folder_temp_and_other_words_pass(self):
        import tempfile
        for cmd in ('rm -rf build', 'rm -f out/report.md', f'rm -rf "{self.os.path.join(self.cwd, "tmp")}"', 'echo term; npm run format',
                    f'rm -rf "{self.os.path.join(tempfile.gettempdir(), "junk")}"', 'Remove-Item ./draft.txt', 'npm run rmdist', 'ls Downloads'):
            self.assertEqual(self.held(cmd), [], cmd)
        self.assertTrue(self.held('rm -rf .'), 'the whole folder it works in is not its to tidy')

    def test_held_on_the_task_with_its_own_reason_and_the_agent_told(self):
        d = sg.check(self.s, self.tid, 'g1', f'rm -rf "{self.dl}"', 'Bash', self.cwd)['hookSpecificOutput']
        self.assertEqual(d['permissionDecision'], 'deny')
        self.assertIn("delete notes-unzipped in Downloads (it can't be undone)", d['permissionDecisionReason'])
        [rv] = self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
        p = json.loads(rv['DraftText'])
        self.assertEqual(p['why'], "it can't be undone")
        # the card's In is the folder it aims at, never the scratch folder it ran from - which Approve still runs in
        self.assertEqual((p['where'], p['cwd']), (self.os.path.dirname(self.dl), self.cwd))
        self.assertIn("delete notes-unzipped in Downloads - it can't be undone", rv['Reason'])
        self.assertNotIn('leaves this computer', rv['Reason'])
        # ...and where the owner can answer the CLI's own prompt, it asks there, with the same words
        a = sg.check(self.s, self.tid, 'p1', f'rm -rf "{self.dl}"', 'Bash', self.cwd, ask=True)['hookSpecificOutput']
        self.assertEqual(a['permissionDecision'], 'ask'); self.assertIn("(it can't be undone)", a['permissionDecisionReason'])
