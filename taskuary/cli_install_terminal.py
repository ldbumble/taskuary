"""Run the closed installer recipes in an owner-visible shell, including interactive prompts."""
import os
import shlex
import threading
import time
import uuid
from pathlib import Path

from . import cliinstall, config


def ps_quote(value): return "'" + str(value).replace("'", "''") + "'"


def command_line(argv, result, windows):
    """Quote each argument independently; record completion without parsing terminal output."""
    if windows:
        command = '& ' + ' '.join(ps_quote(a) for a in argv)
        return ("$taskuaryInstallerExit = 1; $LASTEXITCODE = 0; try { " + command
                + "; if ($? -or $LASTEXITCODE -ne 0) { $taskuaryInstallerExit = $LASTEXITCODE } } catch { Write-Host $_ -ForegroundColor Red }; "
                + "[IO.File]::WriteAllText(" + ps_quote(result) + ", [string]$taskuaryInstallerExit)")
    return shlex.join(argv) + '; printf "%s" "$?" > ' + shlex.quote(str(result))


class ShellRunner:
    def __init__(self, terminal, folder, windows):
        self.term, self.folder, self.windows = terminal, folder, windows

    def ready(self):
        until = time.monotonic() + 15
        while self.term.alive and not self.term.n and time.monotonic() < until: time.sleep(.1)
        if not self.term.alive: raise RuntimeError('The installation terminal was closed')
        if not self.term.n: raise RuntimeError('The installation shell did not become ready')

    def message(self, text):
        self.ready()
        self.term.write(('Write-Host ' + ps_quote(text) if self.windows else 'printf "%s\\n" ' + shlex.quote(text)) + '\r')

    def __call__(self, cmd, timeout=900):
        self.ready()
        result = self.folder / (uuid.uuid4().hex + '.exit')
        offset = len(self.term.scrollback())
        self.term.write(command_line(cmd, result, self.windows) + '\r')
        # This is interactive: the owner may be signing in or answering the vendor wizard.
        # Closing the pane ends the wait. Do not kill the installer on the old headless timeout.
        while True:
            try:
                code = int(result.read_text(encoding='utf-8').strip())
                break
            except (FileNotFoundError, ValueError):
                if not self.term.alive: raise RuntimeError('The installation terminal was closed before the command finished')
                time.sleep(.2)
        result.unlink(missing_ok=True)
        self.term.settle(.5)  # the completion file can arrive before the pty reader drains stdout
        return code, self.term.scrollback()[offset:][-3000:]


def start(store, name, verb='install', actor='owner'):
    from . import terminal
    if verb not in ('install', 'update'): raise ValueError('Unknown installer action')
    roads = cliinstall.plan(name) if verb == 'install' else cliinstall.update_plan(name)
    if not roads: raise ValueError(cliinstall.why_not(name) or f'No {verb} available for {name}')
    if verb == 'update' and not cliinstall.find(name): raise ValueError(f'{name} is not installed yet')
    with cliinstall._LOCK:
        current = cliinstall.state()
        if current['phase'] == 'installing':
            if current['name'] != name or current.get('verb') != verb:
                raise ValueError(f'{current["name"]} is already {current.get("verb", "install")}ing')
            return current
        folder = config.home() / 'installer-sessions'
        folder.mkdir(parents=True, exist_ok=True)
        if os.name == 'nt':
            root = os.environ.get('SystemRoot') or os.environ.get('WINDIR') or 'C:/Windows'
            # PSReadLine redraws the entire line per pasted character, burying short installer
            # output under megabytes of ANSI redraws. Plain PowerShell still accepts owner input.
            argv = [str(Path(root) / 'System32/WindowsPowerShell/v1.0/powershell.exe'), '-NoLogo', '-NoProfile',
                    '-NoExit', '-Command', 'Remove-Module PSReadLine -ErrorAction SilentlyContinue']
        else: argv = ['/bin/sh', '-i']
        tid = store.create_task({'Title': f'{verb.title()} {name}', 'Kind': 'setup', 'Status': 'in_progress',
                                 'Tags': f'cli-install:{name}', 'Summary': 'CLI installer running in an interactive terminal.'}, actor)
        try:
            term = terminal.Term(argv, str(config.home()), f'{verb} {name}', tid, None, 32, 110, store)
        except Exception:
            store.update_task(tid, {'Status': 'done'}, actor)
            raise
        term.keep_transcript = False  # vendor setup may ask the owner to paste a token
        terminal.SESSIONS[term.sid] = term
        runner = ShellRunner(term, folder, os.name == 'nt')
        cliinstall._set('installing', name, f'{verb.title()} commands are running in the terminal below', verb=verb)
        cliinstall._STATE.update(sid=term.sid, taskId=tid)
        store.audit('terminal', tid, 'cli_' + verb, actor, detail={'name': name, 'sid': term.sid})
        def work():
            try:
                result = (cliinstall.install if verb == 'install' else cliinstall.update)(name, runner=runner)
            except Exception as e:
                cliinstall._set('failed', name, str(e), verb=verb)
                return
            try: runner.message(result.get('detail') or result['phase'])
            except RuntimeError: pass  # closing an already-finished pane does not undo installation
        threading.Thread(target=work, daemon=True, name=f'cli-{verb}-terminal').start()
        return cliinstall.state()
