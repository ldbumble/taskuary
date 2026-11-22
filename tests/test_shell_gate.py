"""A SHELL STEP THAT LEAVES THE MACHINE WAITS FOR THE OWNER'S PRESS (shellgate.py; the Advisor design rev 2, the owner's ruling 2026-10-28:
hold risky steps on the existing proposal card). A push, a merge, a public post, a publish or a mail an agent runs from its shell is read by
each tool's own grammar, refused to the agent and put on the task with Approve and Dismiss; Approve runs that exact command in the folder it
was held in and tells the agent; Dismiss tells it no. Everything else passes at once. Invented Northwind repositories only (CLAUDE.md)."""
import json, os, time, unittest
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

    def test_a_payment_posted_however_the_client_spells_it_is_held(self):
        """A mail that talks the agent into paying needs only one write to a payment host. The HTTP clients' writes were read by a few
        spellings of their flags: `--request=POST`, curl's bundled `-sXPOST` / `-sd`, wget's `--method`, PowerShell's `-Method:Post` and
        httpie's own `http POST host k=v` all went out unseen. Each client's grammar, not a list of spellings, says it writes."""
        for cmd in ('curl --request=POST https://pay.vendor.example/transfer', 'curl -sXPOST https://pay.vendor.example/transfer',
                    'curl -sd amount=500 https://pay.vendor.example/transfer', 'curl -sF to=erin https://pay.vendor.example/transfer',
                    'curl --data-ascii amount=500 https://pay.vendor.example/transfer', 'curl --form-string to=erin https://pay.vendor.example/transfer',
                    'curl -K pay.cfg https://pay.vendor.example/transfer', 'wget --method=POST https://pay.vendor.example/transfer',
                    'wget --method POST --body-data amount=500 https://pay.vendor.example/transfer',
                    'Invoke-RestMethod -Method:Post -Uri https://pay.vendor.example/transfer', 'irm https://pay.vendor.example/transfer -Me Post',
                    'http POST https://pay.vendor.example/transfer amount=500', 'http pay.vendor.example/transfer amount:=500',
                    'xh post pay.vendor.example/transfer to=erin', 'http --form pay.vendor.example/transfer to=erin'):
            got = sg.acts(cmd)
            self.assertTrue(got, cmd); self.assertIn('send data to', got[0]['what'], cmd)
        self.assertIn('pay.vendor.example', sg.acts('http POST pay.vendor.example/transfer amount=500')[0]['what'])
        for cmd in ('curl -sSL https://docs.vendor.example/rates', 'curl -sH "Accept: application/json" https://docs.vendor.example/rates',
                    'http https://docs.vendor.example/rates', 'http GET docs.vendor.example/rates q==eur', 'xh :7787/api/tasks amount=1',
                    'wget -q https://docs.vendor.example/rates.csv', 'Invoke-RestMethod https://docs.vendor.example/rates'):
            self.assertEqual(sg.acts(cmd), [], cmd)

    def test_a_step_behind_a_launcher_is_read_as_its_own_tool(self):
        """`timeout 60 git push` - how agents wrap a slow step - was read as a call of `timeout` and went out unseen; so did `env`, `nice` and
        `xargs` before a push, a merge, a POST to a payment host or a delete. A launcher runs what follows it: that program is the one read."""
        for cmd, what in (('timeout 60 git push origin main', 'push'), ('env GIT_TRACE=1 git push', 'push'), ('nice -n 5 git push', 'push'),
                          ('xargs -n1 gh pr merge', 'merge a pull request'), ('sudo -u build npm publish', 'publish'),
                          ('timeout 30 curl -X POST https://pay.vendor.example/transfer', 'send data to pay.vendor.example'),
                          ('timeout 9 rm -rf /srv/northwind/ledger', 'delete ledger')):
            got = sg.acts(cmd, '/w')
            self.assertTrue(got, cmd); self.assertIn(what, got[0]['what'], cmd)
        # ...and a quote inside the tool's name is one word to the shell: `g''h` is gh, `r''m` is rm
        self.assertIn('merge a pull request', sg.acts("g''h pr merge 12", '/w')[0]['what'])
        self.assertIn('delete ledger', sg.acts("r''m -rf /srv/northwind/ledger", '/w')[0]['what'])
        for cmd in ('timeout 60 git status', 'time pytest -q', 'timeout 30 curl -s https://docs.vendor.example/rates'):
            self.assertEqual(sg.acts(cmd, '/w'), [], cmd)

    def test_looking_and_working_locally_pass(self):
        for cmd in ('git status', 'git commit -m "push the fix"', 'git log --grep push', 'gh pr view 12', 'gh api repos/northwind/ledger',
                    'echo git push', 'npm install', 'pytest -q', 'rm -rf build', 'git pull', 'git fetch origin', 'gh pr list',
                    'curl -s https://docs.northwind.example/budget', 'curl -s -X POST http://127.0.0.1:7787/api/agent/tick -d "{}"'):
            self.assertEqual(sg.acts(cmd), [], cmd)


    def test_the_call_taskuary_tells_an_agent_to_make_to_its_own_systems_passes(self):
        """docsync.agent_systems hands a session with no MCP tools `curl -s -X POST "$TASKUARY_URL/api/tools/run" ... -d ...` for a read of
        the owner's own Intacct; the gate saw no http:// in it and held it as data sent to "a web address" - an Approve card for the owner's
        own system. $TASKUARY_URL is Taskuary itself (terminal.session_env), unless the command sets it to somewhere else first."""
        from taskuary import docsync
        from taskuary.store import MemoryStore as M
        for cmd in ('curl -s -X POST "$TASKUARY_URL/api/tools/run" -H "X-Taskuary-Token: $TASKUARY_TOKEN" -d \'{"type": "intacct"}\'',
                    'curl -s -X POST "${TASKUARY_URL}/api/tools/run" -d "{}"', "curl -X POST $TASKUARY_URL/api/agent/tick -d '{}'"):
            self.assertEqual(sg.acts(cmd), [], cmd)
        for cmd in ('export TASKUARY_URL=https://hooks.vendor.example; curl -X POST "$TASKUARY_URL/x" -d @notes.txt',
                    'TASKUARY_URL=https://hooks.vendor.example bash -c \'curl -X POST "$TASKUARY_URL/x" -d @notes.txt\'',
                    'curl -X POST "$TASKUARY_URL.vendor.example/x" -d "{}"', 'curl -X POST "$OTHER_URL/x" -d "{}"'):
            self.assertTrue(sg.acts(cmd), cmd)

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

    def test_a_step_that_fails_says_so_and_runs_nowhere_else(self):
        self.held(); [rv] = self.pending()
        calls, run = self.ran(1, 'rejected: non-fast-forward')
        with mock.patch.object(sg.os.path, 'isdir', self.held_dir), run:
            out = verdicts.decide(self.s, rv, 'approve')
        self.assertFalse(out['ok']); self.assertIn('non-fast-forward', out['send_error'])
        self.assertTrue(out['send_error'].startswith("Push the agent's commits out of this computer failed: "), out['send_error'])     # what did not happen, in his words
        with mock.patch.object(sg.os.path, 'isdir', return_value=False):
            self.assertRaisesRegex(RuntimeError, 'folder it was held in is gone', sg.perform, self.s, self.tid, json.loads(rv['DraftText']))

    # the owner, 2026-11-09: a held run declined in the agent's chat stood on as "Approve runs: ..." after the agent had asked something else
    # ...and the owner, 2026-11-10: "once youa re passed it, it should stay where it is with buttons grayed out" - the conversation moving on
    # passes every card of the task (proposals.move_on), whichever session held it
    # ...REVISED 2026-11-11 (the owner: "the question has 2 approve buttons?"): his next line leaves a held step lit, and the same step run
    # again is the card that waits - one card, never a second beside it
    def test_the_owner_speaking_to_that_session_again_leaves_its_held_step_lit_and_the_step_run_again_is_that_card(self):
        self.held(); n = len(self.pending())
        self.assertEqual(proposals.move_on(self.s, self.tid), [])
        self.held()
        self.assertEqual(len(self.pending()), n)
        self.assertIsNone(self.s._one("SELECT * FROM review WHERE TaskId=? AND Status='superseded'", (self.tid,)))

    def test_the_prompt_hook_sets_a_held_step_aside_when_he_writes_never_on_a_wake(self):
        """2026-11-12, one rule for every card: a line he types past a held step greys it in its place and the agent is told so - raised again
        if still needed. A background job's wake is no line of his: the step stays lit."""
        from taskuary import proposals
        self.held(); [rv] = self.pending()
        t = SimpleNamespace(store=self.s, task_id=self.tid, sid='run1', bg={})
        hooks._events(t, {'hook_event_name': 'UserPromptSubmit', 'prompt': '<task-notification>done</task-notification>'})
        self.assertEqual([r['ReviewId'] for r in self.pending()], [rv['ReviewId']], 'a wake leaves it lit')
        told = []
        with mock.patch('taskuary.general.to_agent', lambda st, tid, note, actor='owner': told.append(note) or 'told'):
            hooks._events(t, {'hook_event_name': 'UserPromptSubmit', 'prompt': 'no, leave the checkout - is it ready to push?'})
        self.assertEqual(self.pending(), []); self.assertTrue(proposals.passed(self.s.get_review(rv['ReviewId'])))
        from taskuary import cardqueue
        self.assertTrue(told and cardqueue.SCREEN_HEAD in told[0] and f"rv{rv['ReviewId']}" in told[0].split('Greyed, will not go')[1], told)

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

    def test_a_heredoc_fed_to_a_program_is_its_data_not_shell(self):
        # the owner's live task, 2026-11-17: a coding agent wrote layout helpers with `python - <<'PY' ... PY`; lines of its Python
        # (`del cells[k]`, `if unit not in rows: remove(...)`) were read as shell deletes - "it would delete not in TQ-.., in in TQ-.., unit:",
        # and the card said "It sends or pushes"
        script = ("cd out && python - <<'PY'\nrows = {}\nfor unit in rows:\n    del rows[unit]\nif 'b' not in rows: rows.remove('b')\n"
                  "print('git push is only a word here')\nPY\necho done")
        self.assertEqual(self.held(script), [])
        self.assertEqual(sg.acts(script), [])
        self.assertEqual(self.held("cat > notes.md <<EOF\nrm -rf ~/Downloads\nEOF"), [], 'a file written from a heredoc is its words')
        # ...while the shell around it, a heredoc a SHELL runs, and a Python delete call in it are still read
        self.assertTrue(self.held(f"python - <<'PY'\nprint(1)\nPY\nrm -rf \"{self.dl}\""))
        self.assertTrue(self.held(f"bash <<'SH'\nrm -rf \"{self.dl}\"\nSH"))
        self.assertTrue(self.held("python - <<'PY'\nimport shutil; shutil.rmtree(p)\nPY"))
        self.assertTrue(sg.acts("bash <<SH\ngit push origin main\nSH"))

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


class ReadingOutside(unittest.TestCase):
    """AN AGENT ASKS BEFORE IT READS OUTSIDE ITS WORK (the owner, 2026-11-15: "for all agents they should ask before acting like all other
    actions that ask for permissions"). Its own folders run freely; a read anywhere else is the same held card a push is, and Approve lets the
    task read that folder from then on; Taskuary's home and the sign-in places are never read. The 'owner's folder' here is this test folder -
    outside the scratch home, the temp folder and the agent's working folder."""
    def setUp(self):
        import tempfile
        from pathlib import Path
        from taskuary import config
        self.s = MemoryStore(); self.tid = Factory(self.s).task('Sum the quarter from his spreadsheet')
        self.work, self.docs = tempfile.mkdtemp(), str(Path(__file__).parent)
        config.home().mkdir(parents=True, exist_ok=True); self.secret = str(config.home() / 'config.toml')
        self.told = []
        self.sess = SimpleNamespace(sid='run1', send_prompt=lambda text, as_owner=True: self.told.append(text))
        self.ctx = {'store': self.s, 'task_id': self.tid, 'cwd': self.work, 'sid': 'run1'}

    def pending(self): return self.s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action' AND Status='pending'", (self.tid,))
    def read(self, p): return {'toolCallId': 'c', 'kind': 'read', '_meta': {'claudeCode': {'toolName': 'Read'}}, 'rawInput': {'file_path': p}}

    def heard(self):
        end = time.time() + 5
        while not self.told and time.time() < end: time.sleep(.01)
        return self.told

    def test_a_shell_line_is_read_for_the_paths_it_names(self):
        from taskuary import readgate as rg
        here = os.path.join(self.docs, 'conftest.py')
        self.assertEqual(rg.command_paths(f'cat "{here}"', self.work), [here])
        self.assertEqual(rg.command_paths(f'cd "{self.docs}" && ls', self.work), [self.docs])
        self.assertEqual(rg.command_paths('cat $NOPE_NOT_SET/x.txt', self.work), [None], 'a path built from a variable it cannot read is held')
        # ...the real CLI's own shape (2026-11-16): the path kept in a variable, then read through it - it passed the gate unread
        live = f"$p='{here}'; $l=Get-Content $p; \"rows: $((Import-Csv $p).Count)\""
        self.assertTrue(rg.command_paths(live, self.work) and set(rg.command_paths(live, self.work)) == {here}, rg.command_paths(live, self.work))
        self.assertTrue(rg.of_command(self.s, self.tid, live, self.work)[0])
        for cmd in ('git status', 'for f in *.csv; do wc -l "$f"; done', 'grep -rn /api/tasks src', 'curl -s https://docs.northwind.example/a',
                    'dir /s', 'python script.py 2>/dev/null', 'cat "$TASKUARY_OUTPUTS/total.txt"'):
            self.assertEqual(rg.of_command(self.s, self.tid, cmd, self.work), ([], ''), cmd)

    def test_a_secret_is_seen_however_the_shell_line_spells_it(self):
        """Taskuary's home (its config.toml carries the owner token) is never read - but the line was split as words with their quotes
        left on, and `{`/`}` cut as blocks: a quoted variable glued to a path, `${...}`, a redirect stuck to its program and a bare `cd`
        all passed the gate unread, as if they named nothing. Each is how a shell spells the same file."""
        from pathlib import Path
        from taskuary import readgate as rg
        ssh = Path.home() / '.ssh'; ssh.mkdir(exist_ok=True); (ssh / 'id_ed25519').touch()
        for cmd in ('cat "$TASKUARY_HOME"/config.toml', 'cat ${TASKUARY_HOME}/config.toml', 'cat "${TASKUARY_HOME}/config.toml"',
                    'cat<"$TASKUARY_HOME/config.toml"', 'echo "$(<"$TASKUARY_HOME/config.toml")"', f'cat "{Path(self.secret).parent}"/config.toml',
                    f"cat '{Path(self.secret).parent}'/'config.toml'", f'cd "{Path(self.secret).parent}" && cat config.toml',
                    'cd && cat .ssh/id_ed25519', 'cd ~; base64 .ssh/id_ed25519'):
            self.assertEqual(rg.of_command(self.s, self.tid, cmd, self.work), ([], rg.NEVER), cmd)
        self.assertEqual(rg.command_paths('cat ${HOME:-/x}/.ssh/id_ed25519', self.work), [None], 'a default it cannot follow is held, never skipped')

    def test_a_sign_in_place_stays_closed_inside_a_work_folder_or_behind_a_glob(self):
        """The never-list was judged after the work area and after a glob was cut to its folder: a task whose checkout is the home folder
        (a dotfiles repository) read the sign-ins in it freely, and once the owner let a task read his home folder, `cat ~/.s*/<key>`
        ran - its glob judged only as the home it lists. A work folder inside Taskuary's home (scratch, outputs) still reads."""
        from pathlib import Path
        from taskuary import config, readgate as rg
        ssh = Path.home() / '.ssh'; ssh.mkdir(exist_ok=True); key = ssh / 'id_ed25519'; key.touch()
        self.assertEqual(rg.judge(self.s, self.tid, [str(key)], str(Path.home())), ([], rg.NEVER), 'a checkout at home')
        self.assertEqual(rg.judge(self.s, self.tid, [str(config.home() / 'scratch' / 'a.md')], str(Path.home()))[1], '')
        rg.grant(self.s, self.tid, [str(Path.home())])
        for cmd in ('cat ~/.s*/id_ed25519', 'grep -r token ~/.[a-z]*', 'cat ~/.ss?/*'):
            self.assertEqual(rg.of_command(self.s, self.tid, cmd, self.work), ([], rg.NEVER), cmd)
        self.assertEqual(rg.of_command(self.s, self.tid, 'ls ~/*', self.work), ([], ''), 'a plain * takes no dot-folder, as the shell')

    def test_work_in_its_own_folders_runs_and_a_read_outside_is_the_held_card(self):
        from taskuary import acpgate, outputs
        self.assertEqual(acpgate.decide(self.read(os.path.join(self.work, 'notes.md')), self.ctx)[0], acpgate.ALLOWED)
        self.assertEqual(acpgate.decide(self.read(str(outputs.folder(self.tid) / 'total.xlsx')), self.ctx)[0], acpgate.ALLOWED)
        got = acpgate.decide(self.read(os.path.join(self.docs, 'conftest.py')), self.ctx)
        self.assertEqual(got[0], acpgate.HELD); self.assertIn('held this for the owner', got[1])
        [rv] = self.pending(); p = json.loads(rv['DraftText'])
        self.assertEqual((p['action'], p['command'], p['why']), ('shell_act', '', "it is outside this task's own folders"))
        self.assertIn('conftest.py', p['what']); self.assertEqual(p['reads'], [os.path.realpath(self.docs)], 'the folder as he spells it, not case-folded')
        # ...the same read on the shell road, by the one gate a CLI's and the API's commands pass
        d = hooks.command_gate(self.s, self.tid, 'run1', f'Get-Content "{os.path.join(self.docs, "conftest.py")}"', 'PowerShell', self.work)
        self.assertEqual(d['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(hooks.command_gate(self.s, self.tid, 'run1', 'Get-Content notes.md', 'PowerShell', self.work), {})

    def test_codexs_powershell_call_is_read_run_and_approved_as_the_script_it_is(self):
        """The HIPAA walk, 2026-11-21: Codex reports each call as its argv joined by POSIX quoting, the script's quoting switching mid-word.
        Cut at the `;` inside its quotes, `$outDir = "<its outputs folder>"; New-Item $outDir` was held as "a path it builds from a variable"
        - the task's own folder - and Approve unquoted it by hand: PowerShell's parser failed on it. A PowerShell array of folders read as
        `", in Desktop`."""
        from taskuary import acpgate, outputs, readgate as rg
        out = str(outputs.folder(self.tid))
        script = f'$outDir = "{out}"; New-Item -ItemType Directory -Force -Path $outDir | Out-Null; py make_deck.py $outDir'
        ps = r'C:\WINDOWS\System32\WindowsPowerShell\v1.0\powershell.exe'
        head, tail = out.split('\\', 1) if '\\' in out else (out, '')
        shown = f'"{ps}" -Command \'$outDir = "{head}\'"\\{tail}"\'"; New-Item -ItemType Directory -Force -Path $outDir | Out-Null; py make_deck.py $outDir\''
        if not tail: shown = f'"{ps}" -Command \'{script}\''
        tc = {'toolCallId': 'c', 'kind': 'execute', 'title': 'Run command', 'rawInput': {'command': shown, 'cwd': self.work}}
        t = acpgate.tool_of(tc)
        self.assertEqual((t['command'], t['shell'], t['argv'][1:]), (script, 'PowerShell', ['-Command', script]))
        self.assertNotIn(None, rg.command_paths(shown, self.work, rg.env_for(self.s, self.tid, self.work)))
        self.assertEqual(acpgate.decide(tc, self.ctx)[0], acpgate.ALLOWED, "the task's own outputs folder needs no press")
        # ...and a script it writes through a here-string is that file's data, never paths read ("$60 / day" was held as one, the fix2 walk)
        here = f"$outDir = \"{out}\"\n@'\nlimits = ['meals $60 / day', 'hotels $220 / night']\nopen('/etc/x')\n'@ | Set-Content -Path make_deck.py\npy make_deck.py $outDir"
        self.assertNotIn(None, rg.command_paths(here, self.work, rg.env_for(self.s, self.tid, self.work)))
        self.assertEqual(sg.acts("@'\ngit push origin main\n'@ | Set-Content x.txt", self.work), [])
        self.assertTrue(sg.acts("@'\ngit push origin main\n'@ | iex", self.work), 'fed to a shell, it is a command')
        # ...and a held one is approved as exactly that argv
        far = f'"{ps}" -Command \'Get-ChildItem -Path @("$env:USERPROFILE\\Desktop", "$env:USERPROFILE\\Documents") -Filter notes.txt\''
        got = acpgate.decide({**tc, 'rawInput': {'command': far, 'cwd': self.work}}, self.ctx)
        self.assertEqual(got[0], acpgate.HELD)
        [rv] = self.pending(); p = json.loads(rv['DraftText'])
        self.assertEqual(p['argv'][1:], ['-Command', 'Get-ChildItem -Path @("$env:USERPROFILE\\Desktop", "$env:USERPROFILE\\Documents") -Filter notes.txt'])
        self.assertEqual(sg.replay(p)[1:], p['argv'][1:])
        self.assertNotIn('"', p['what']); self.assertIn('Desktop', p['what'])

    def test_a_program_installed_for_this_user_alone_is_nobodys_files(self):
        """The real-CLI walk, 2026-11-16: an agent looking for its python (`ls .../AppData/Local/Programs/Python`) was held as a card asking the
        owner to let it read "Python". A per-user install (%LOCALAPPDATA%\\Programs) is a program's folder, as Program Files is."""
        import pytest
        if os.name != 'nt': pytest.skip('%LOCALAPPDATA% is Windows')
        local = os.path.join(self.docs, 'AppData-Local'); os.makedirs(os.path.join(local, 'Programs', 'Python', 'Python312'), exist_ok=True)
        with mock.patch.dict(os.environ, {'LOCALAPPDATA': local}):
            self.assertEqual(hooks.command_gate(self.s, self.tid, 'run1', f'ls "{os.path.join(local, "Programs", "Python")}"', 'Bash', self.work), {})
            d = hooks.command_gate(self.s, self.tid, 'run1', f'ls "{local}"', 'Bash', self.work)          # ...the rest of AppData still asks
            self.assertEqual(d['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_a_clis_own_skills_are_read_without_asking_and_the_rest_of_its_home_still_asks(self):
        """The owner's live task, 2026-11-17: a coding agent reading one of Claude Code's own skills (~/.claude/skills/<name>/reference/...)
        stood as a card "Read craft-floor.md in reference". A CLI's skills, plugins, agents and commands are its own instructions."""
        claude = os.path.join(self.docs, 'claude-home'); os.makedirs(os.path.join(claude, 'skills', 'impeccable', 'reference'), exist_ok=True)
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': claude}):
            self.assertEqual(hooks.command_gate(self.s, self.tid, 'run1', f'cat "{os.path.join(claude, "skills", "impeccable", "reference", "craft-floor.md")}"', 'Bash', self.work), {})
            d = hooks.command_gate(self.s, self.tid, 'run1', f'cat "{os.path.join(claude, "history.jsonl")}"', 'Bash', self.work)   # ...the rest still asks
            self.assertEqual(d['hookSpecificOutput']['permissionDecision'], 'deny')

    def test_a_read_card_held_before_the_gate_opened_that_folder_leaves_the_chat(self):
        """The owner, 2026-11-17, on the same task after the fix: the old card still stood, "Read craft-floor.md in reference · Dismissed ·
        nothing was run" - "it told you to get rid of it". A held read the gate would let through now was never his to answer: it is not
        drawn, pending or answered. A read it still holds stays, and so does a card whose command holds something else."""
        from taskuary import cardqueue, conversation, proposals, taskstate
        claude = os.path.join(self.docs, 'claude-home'); ref = os.path.join(claude, 'skills', 'impeccable', 'reference'); os.makedirs(ref, exist_ok=True)
        hist = os.path.join(self.docs, 'claude-home-other')
        def held(folder, cmd='', status='rejected'):
            proposals.queue(self.s, self.tid, {'action': 'shell_act', 'sid': 'run1', 'command': cmd, 'cwd': self.work, 'what': f'read x in {os.path.basename(folder)}',
                                               'why': 'outside', 'where': folder, 'reads': [folder]}, 'agent')
            rid = self.s._rows("SELECT ReviewId FROM review WHERE TaskId=? ORDER BY ReviewId DESC LIMIT 1", (self.tid,))[0]['ReviewId']
            if status != 'pending': self.s._exec("UPDATE review SET Status=? WHERE ReviewId=?", (status, rid))
            return rid
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': claude}):
            gone, gone2, kept, both = held(ref), held(ref, status='pending'), held(hist), held(ref, cmd='git push origin main')
            self.s._exec("UPDATE review SET DecidedBy='owner' WHERE ReviewId=?", (gone,))
            allowed = held(ref, status='approved')
            cards = [c['review'] for x in conversation.items(self.s, self.tid)['items'] for c in ([x] if x['kind'] == 'card' else x.get('cards') or [])]
            queue = cardqueue.state(self.s, self.tid)
            self.assertNotIn(gone2, queue['live'] + queue['held'])
            self.assertNotIn(gone2, [r['ReviewId'] for r in self.s.waiting_reviews()])
            self.assertIsNone(self.s.waiting_on_owner(self.tid))
            self.assertFalse(taskstate.waits_press(self.s, {'TaskId': self.tid, 'ReviewStatus': 'pending', 'ReviewKind': 'action'}, row=True))
        self.assertNotIn(gone, cards); self.assertNotIn(gone2, cards)
        self.assertIn(kept, cards); self.assertIn(both, cards); self.assertIn(allowed, cards)

    def test_what_its_own_cli_downloaded_is_its_work_and_the_rest_of_that_home_still_asks(self):
        """The owner, 2026-11-16: a research turn's read-back of the PDF its own WebFetch had saved was held as a card under its finished
        answer - "files the agent's own CLI downloaded during the task count as its work area". The exact folders: Claude Code's tool-results
        for a session started in this task's folder, Codex's pictures for this task's own threads - never another session's, nor the rest of
        those homes."""
        from taskuary import acpgate, climodels, readgate
        claude = os.path.join(self.docs, 'claude-home'); codex = os.path.join(self.docs, 'codex-home')         # ...outside its work, as his own are
        with mock.patch.dict(os.environ, {'CLAUDE_CONFIG_DIR': claude, 'CODEX_HOME': codex}):
            mine = os.path.join(claude, 'projects', readgate._slug(self.work), '4efe24ce', 'tool-results', 'webfetch-17948.pdf')
            other = os.path.join(claude, 'projects', readgate._slug(self.docs), '4efe24ce', 'tool-results', 'webfetch-1.pdf')
            log = os.path.join(claude, 'projects', readgate._slug(self.work), '4efe24ce.jsonl')
            self.assertEqual(acpgate.decide(self.read(mine), self.ctx)[0], acpgate.ALLOWED, 'its own download, read back')
            self.assertEqual(acpgate.decide(self.read(other), self.ctx)[0], acpgate.HELD, "another folder's session is not its own")
            self.assertNotEqual(acpgate.decide(self.read(log), self.ctx)[0], acpgate.ALLOWED, 'its session log is no download')
            self.s.add_transcript(self.tid, 'thread-7', 'Drew the chart.', 'codex', self.work)
            self.assertTrue(readgate.fetched(readgate._n(os.path.join(codex, 'generated_images', 'thread-7', 'chart.png')), self.work, readgate._sids(self.s, self.tid)))
            self.assertFalse(readgate.fetched(readgate._n(os.path.join(codex, 'generated_images', 'thread-8', 'x.png')), self.work, readgate._sids(self.s, self.tid)))

    def test_a_checkout_of_a_repository_taskuary_has_is_every_agents_work(self):
        """The owner's live task, 2026-11-16 ("we went through this 50 times"): a general agent on a question about one app asked to "read the
        folder FanApp" - his GitHub-connected repository, whose checkout the coding agents' map names. Every checkout Taskuary has - a
        profile's map, a folder a coding session ran in - is any agent's work; the folder above it still asks."""
        from taskuary import acpgate, repochoice
        fan, ledger = os.path.join(self.docs, 'FanApp'), os.path.join(self.docs, 'ledger')
        self.s.upsert_agent('coding', 'coding', 'cli', json.dumps({'cmd': 'claude', 'cwd_map': {'northwind/fanapp': fan}}))
        self.assertEqual(acpgate.decide(self.read(os.path.join(fan, 'src', 'App.tsx')), self.ctx)[0], acpgate.ALLOWED)
        other = Factory(self.s).task('Fix the ledger rounding', kind='coding'); self.s.add_transcript(other, 'run9', 'Fixed.', 'claude', ledger)
        with mock.patch.object(repochoice, 'is_checkout', lambda p: os.path.normcase(str(p)) == os.path.normcase(ledger)):
            self.assertEqual(acpgate.decide(self.read(os.path.join(ledger, 'totals.py')), self.ctx)[0], acpgate.ALLOWED, 'a checkout a coding task ran in')
        self.assertEqual(acpgate.decide(self.read(os.path.join(self.docs, 'conftest.py')), self.ctx)[0], acpgate.HELD, 'the folder above them still asks')

    def test_a_step_held_in_a_turn_that_finished_the_job_greys_with_the_true_line(self):
        """The same walk: the PDF read was held, the turn finished the report another way and said its goal was met (nothing_left) - and the
        Approve stood live under the complete answer. Steps held in a turn that finished are over: greyed in place, with what happened."""
        from taskuary import acpgate, proposals
        acpgate.decide(self.read(os.path.join(self.docs, 'conftest.py')), self.ctx); [rv] = self.pending()
        self.assertEqual(proposals.finished_without(self.s, self.tid), [rv['ReviewId']])
        r = self.s.get_review(rv['ReviewId'])
        self.assertTrue(proposals.passed(r), 'nothing presses it')
        self.assertEqual(proposals.passed_why(self.s, r), 'Not needed - the agent finished without it')
        from taskuary import cardqueue
        self.assertIn('(Not needed - the agent finished without it)', cardqueue.screen(self.s, self.tid), 'told as what it is, never as a card he moved past')

    def test_approve_lets_the_task_read_that_folder_from_then_on_and_tells_the_agent(self):
        from taskuary import acpgate
        call = self.read(os.path.join(self.docs, 'conftest.py'))
        acpgate.decide(call, self.ctx); [rv] = self.pending()
        with mock.patch('taskuary.workerstate._live', return_value=self.sess):
            self.assertTrue(verdicts.decide(self.s, rv, 'approve')['ok'])
        self.assertIn('The owner let you read', self.heard()[0])
        # ...and his press, where it is said as a line, reads as what it did - nothing "ran" (the owner, 2026-11-16; the card: heldCard)
        from taskuary import general, readgate
        said = general.PRESSES['shell_act_done']({'what': 'read conftest.py in tests', 'reads': [self.docs]})
        self.assertIn(readgate.ALLOWED, said); self.assertNotIn('it ran', said)
        self.assertEqual(acpgate.decide(call, self.ctx)[0], acpgate.ALLOWED)
        self.assertEqual(acpgate.decide(self.read(os.path.join(self.docs, 'browser', 'x.mjs')), self.ctx)[0], acpgate.ALLOWED)
        self.assertEqual(self.pending(), [])

    def test_dismiss_tells_the_agent_whose_no_it_was(self):
        from taskuary import acpgate, browsergate
        acpgate.decide(self.read(os.path.join(self.docs, 'conftest.py')), self.ctx); [rv] = self.pending()
        with mock.patch('taskuary.workerstate._live', return_value=self.sess):
            self.assertTrue(verdicts.decide(self.s, rv, 'reject')['ok'])
        self.assertIn('did not approve it', self.heard()[0]); self.assertIn(browsergate.OWNER_NO, self.told[0])

    def test_the_context_file_taskuary_wrote_for_the_task_is_its_to_read_and_no_other_tasks(self):
        """Recorded on the real CLI, 2026-11-16: the brief points the agent at its context file in Taskuary's home, and its Read was refused
        as Taskuary's own data - the agent told the owner "the task's context file was blocked from reading". It is the task's own; another
        task's is not."""
        from taskuary import acpgate, context, readgate
        own, batch = context.files(self.tid)
        self.assertEqual(acpgate.decide(self.read(str(own)), self.ctx)[0], acpgate.ALLOWED)
        self.assertEqual(acpgate.decide(self.read(str(batch)), self.ctx)[0], acpgate.ALLOWED)
        other = context.files(self.tid + 1)[0]
        self.assertEqual(acpgate.decide(self.read(str(other)), self.ctx), (acpgate.REFUSED, readgate.NEVER))

    def test_a_search_over_the_tasks_own_mail_folders_is_its_own_work_and_no_other_messages(self):
        """Timed on a long task, 2026-11-16: a grep over the files that came on the task's mail was refused as Taskuary's own data, and the
        agent spent its turn working around it. Each of the task's messages' folders is its own; another message's is not."""
        from taskuary import acpgate, config, readgate
        mine = self.s.add_message({'TaskId': self.tid, 'ExternalId': 'g1', 'Channel': 'email', 'Subject': 'plan', 'Status': 'routed'})
        other = self.s.add_message({'ExternalId': 'g2', 'Channel': 'email', 'Subject': 'not ours', 'Status': 'routed'})
        there = (config.home() / 'attachments' / str(mine)).exists()      # ...the test home is shared: another test may have made it
        grep = lambda d: {'toolCallId': 'g', 'kind': 'search', '_meta': {'claudeCode': {'toolName': 'Grep'}}, 'rawInput': {'pattern': 'sign-off', 'path': d}}
        self.assertEqual(acpgate.decide(grep(str(config.home() / 'attachments' / str(mine))), self.ctx)[0], acpgate.ALLOWED)
        self.assertEqual(acpgate.decide(grep(str(config.home() / 'attachments' / str(other))), self.ctx), (acpgate.REFUSED, readgate.NEVER))
        self.assertEqual((config.home() / 'attachments' / str(mine)).exists(), there, 'the gate names the folder, never makes it')

    def test_taskuarys_own_home_is_never_read_not_even_on_a_yes(self):
        from taskuary import acpgate, apiagent, readgate
        self.assertEqual(acpgate.decide(self.read(self.secret), self.ctx), (acpgate.REFUSED, readgate.NEVER))
        d = hooks.command_gate(self.s, self.tid, 'run1', f'cat "{self.secret}"', 'Bash', self.work)
        self.assertEqual(d['hookSpecificOutput']['permissionDecisionReason'], readgate.NEVER)
        readgate.grant(self.s, self.tid, [os.path.dirname(self.secret)])
        self.assertEqual(acpgate.decide(self.read(self.secret), self.ctx)[0], acpgate.REFUSED)
        self.assertEqual(self.pending(), [])
        # ...and the API road's own file tools, by the same rule
        with mock.patch.object(apiagent, 'workdir', return_value=self.work):
            self.assertRaisesRegex(ValueError, 'never read by an agent', apiagent._hands, self.s, self.tid, 'run1', 'file_read', {'path': self.secret})
            self.assertIn('held this for the owner', apiagent._hands(self.s, self.tid, 'run1', 'files_list', {'path': self.docs}))

    def test_a_cli_file_tool_on_the_hook_road_is_judged_the_same(self):
        t = SimpleNamespace(store=self.s, task_id=self.tid, sid='run1', cwd=self.work)
        call = lambda p: hooks.browser({'tool_name': 'Read', 'tool_input': {'file_path': p}, 'cwd': self.work})
        with mock.patch.object(hooks, '_pane', return_value=t), mock.patch.object(sg, 'asks', return_value=''):
            self.assertEqual(call(os.path.join(self.work, 'a.md')), {})
            self.assertEqual(call(os.path.join(self.docs, 'conftest.py'))['hookSpecificOutput']['permissionDecision'], 'deny')
        self.assertEqual(len(self.pending()), 1)
        self.assertIn('Read', hooks.BROWSER_MATCH.split('|'))


class TwoGatesAtOnce(unittest.TestCase):
    def test_one_call_held_by_two_gates_at_the_same_moment_is_one_card(self):
        """Recorded on the real CLI, 2026-11-16: the hook and the ACP gate held one command in the same millisecond - two cards of it, "2 of 2
        ran", the command run twice. The look for a waiting card and the filing of one are one step."""
        import threading
        s = MemoryStore(); tid = Factory(s).task('Fill the invoice templates'); go = threading.Barrier(4)
        # ...a push: held on every OS (a C:/ path is a relative one on macOS, and its delete held nothing there - CI run 43895206403)
        with mock.patch.object(sg, 'trusted', return_value=''), mock.patch('taskuary.landing.push_asked', return_value=None):
            def hold(): go.wait(); sg.check(s, tid, 'run1', 'git push origin main', 'Bash', '')
            ts = [threading.Thread(target=hold) for _ in range(4)]
            for t in ts: t.start()
            for t in ts: t.join(10)
        self.assertEqual(len(s._rows("SELECT * FROM review WHERE TaskId=? AND Kind='action'", (tid,))), 1)


# ── AN APPROVE RUNS THE CALL AS THE AGENT'S OWN TOOL WOULD HAVE (the owner's live task, 2026-11-19): Codex reported its push as the shell it
# started on a line - `"<powershell.exe>" -Command '...'` - and Approve wrapped that line in PowerShell again, which read the quoted program and
# its -Command as one expression: every press "failed: At line:1 char:66"
def test_a_held_line_replays_in_the_shell_it_was_written_for():
    ps = '"C:\\WINDOWS\\System32\\WindowsPowerShell\\v1.0\\powershell.exe" -Command \'git push origin HEAD:refs/heads/deploy\''
    a = sg.replay({'command': ps, 'shell': 'PowerShell'})
    assert sg._name(a[0]) in ('powershell', 'pwsh') and a[1:] == ['-Command', 'git push origin HEAD:refs/heads/deploy']
    bash = 'cd ../ledger && git push origin "$(git rev-parse --abbrev-ref HEAD)"'
    with mock.patch.object(sg, 'git_bash', return_value='/usr/bin/bash'):
        assert sg.replay({'command': bash, 'shell': 'Bash'}) == ['/usr/bin/bash', '-c', bash]
        assert sg.replay({'command': "bash -lc 'git push origin main'", 'shell': 'PowerShell'}) == ['/usr/bin/bash', '-lc', 'git push origin main']
    own = 'Get-ChildItem | Remove-Item -Recurse'
    assert sg.replay({'command': own, 'shell': 'PowerShell'})[-2:] == ['-Command', own]
    # ...and the argv a brain gave as a list (Codex) is that argv, the program found where it was named
    with mock.patch.object(sg, '_shell_exe', return_value='C:/pwsh.exe'):
        assert sg.replay({'command': 'x', 'argv': ['powershell.exe', '-Command', 'git push']}) == ['C:/pwsh.exe', '-Command', 'git push']


def test_a_powershell_failure_is_said_by_its_reason_never_its_position():
    said = ("At line:1 char:66\n+ \"C:\\WINDOWS\\powershell.exe\" -Command 'git push'\n+                ~~~~~~~~\n"
            "Unexpected token '-Command' in expression or statement.\n    + CategoryInfo          : ParserError: (:) [], ParentContainsErrorRecordException\n")
    assert sg.failed(said, 1, 'push 3 commits to northwind/ledger deploy') == \
        "Push 3 commits to northwind/ledger deploy failed: Unexpected token '-Command' in expression or statement."


# A READ-ONLY LOOK AT TASKUARY'S OWN API IS NO FILE READ (the roads audit, 2026-11-19): `curl "$TASKUARY_URL/api/..."` was held as "a path it
# builds from a variable" - a card each time the agent looked
def test_a_curl_of_taskuarys_own_api_reads_no_file():
    from taskuary import readgate
    assert readgate.command_paths('curl -s "$TASKUARY_URL/api/tasks/3"', 'C:/work/ledger') == []
    assert readgate.command_paths('curl -s ${TASKUARY_URL}/api/tasks/3 | python -c "import json,sys"', 'C:/work/ledger') == []
    assert readgate.command_paths('cat "$SECRETS_DIR/x"', 'C:/work/ledger') == [None]                # a variable it cannot read is still held


def test_a_step_piped_into_a_tool_that_exits_zero_is_as_it_ended():
    # the Claude walk, 2026-11-19: `git push ... | tail -3` exited 0 and the card read "Approved · it ran" over a refused push
    s = MemoryStore(); tid = Factory(s).task('Ship the export fix')
    said = "To https://github.com/northwind/ledger.git\n ! [rejected]        main -> main (fetch first)\nerror: failed to push some refs to 'https://github.com/northwind/ledger.git'"
    with mock.patch.object(sg, '_tell'), mock.patch.object(sg.os.path, 'isdir', return_value=True):
        try: sg.perform(s, tid, {'command': 'git push origin main | tail -3', 'shell': 'Bash', 'cwd': 'C:/work/ledger', 'what': 'push 1 commit to northwind/ledger main'},
                        run=lambda argv, cwd: (0, said))
        except RuntimeError as e: assert str(e).startswith('Push 1 commit to northwind/ledger main failed: error: failed to push some refs')
        else: raise AssertionError('a refused push read as run')
