"""Nothing Taskuary starts may hold the one-file exe's unpack folder (%TEMP%\\_MEIxxxx), and what it owns is stopped
before it goes - or the bootloader shows "Failed to remove temporary directory" (after Update, 2026-10-22).

Frozen is faked: sys.frozen + sys._MEIPASS pointed at a temp folder, and the working directory moved INTO it, which
is the worst case - a child that inherits our cwd would then sit in the folder."""
import io, os, re, subprocess, sys, time
from pathlib import Path, PureWindowsPath
from unittest import mock

import pytest

from taskuary import spawn, unpack, update

ROOT = Path(__file__).resolve().parent.parent / 'taskuary'
REAL_POPEN = spawn.popen          # conftest swaps it for its process guard after import; these tests fake one level lower


class FakeProc:
    def __init__(self, *a, **kw):
        self.args, self.kw, self.pid, self.returncode = a, kw, 4242, None
        self.stdin, self.stdout, self.stderr = io.StringIO(), io.StringIO(''), io.StringIO('')
    def poll(self): return None
    def wait(self, timeout=None): return 0
    def kill(self): pass


@pytest.fixture
def frozen(tmp_path, monkeypatch):
    """A frozen exe whose unpack folder is <tmp>/_MEI1234 and whose cwd is inside it. Yields the folder;
    every Popen/run is captured in `frozen.calls` instead of run."""
    mei = tmp_path / '_MEI1234'; (mei / 'taskuary').mkdir(parents=True)
    monkeypatch.setattr(sys, 'frozen', True, raising=False)
    monkeypatch.setattr(sys, '_MEIPASS', str(mei), raising=False)
    monkeypatch.chdir(mei)
    monkeypatch.setenv('_PYI_APPLICATION_HOME_DIR', str(mei))
    monkeypatch.setenv('_PYI_ARCHIVE_FILE', r'C:\Apps\Taskuary.exe')
    monkeypatch.setenv('PATH', os.pathsep.join([str(mei), str(tmp_path / 'bin')]))
    calls = []
    def popen(*a, **kw): calls.append(kw); return FakeProc(*a, **kw)
    def run(*a, **kw): calls.append(kw); return subprocess.CompletedProcess(a[0] if a else kw.get('args'), 0, '', '')
    monkeypatch.setattr(subprocess, 'Popen', popen)
    monkeypatch.setattr(subprocess, 'run', run)
    monkeypatch.setattr(spawn, 'popen', REAL_POPEN)
    # the real DLL-directory switch is process-wide: count the calls instead of making them
    k = mock.Mock()
    monkeypatch.setattr(spawn, '_kernel32', lambda: k)
    monkeypatch.setattr(spawn, '_DLL', {'n': 0, 'added': False})
    class F: pass
    f = F(); f.mei, f.calls, f.k = mei, calls, k
    return f


def clear_of(f, kw):
    """The child starts outside the folder, inherits none of our handles, and carries nothing that ties it to the folder."""
    cwd = kw.get('cwd') or os.getcwd()
    assert not spawn.inside(cwd, str(f.mei)), f'child starts in the unpack folder: {cwd}'
    assert kw.get('close_fds') is True, 'child inherits our handles'
    env = kw.get('env')
    assert env is not None and not any(k.upper().startswith('_PYI_') for k in env), 'PyInstaller markers leak into the child'
    assert env.get('PYINSTALLER_RESET_ENVIRONMENT') == '1'
    path = next(v for k, v in env.items() if k.upper() == 'PATH')
    assert not any(spawn.inside(p, str(f.mei)) for p in path.split(os.pathsep) if p)


# ── the rule itself ────────────────────────────────────────────────────────────────────────
def test_an_ordinary_install_spawns_exactly_as_asked(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    kw = {'cwd': None, 'stdout': subprocess.PIPE}
    assert spawn.guard(**kw) == kw and spawn.env_for(None) is None and spawn.cwd_for('x') == 'x'


def test_a_cwd_outside_the_folder_is_kept_and_one_inside_becomes_the_home(frozen, tmp_path):
    from taskuary import config
    assert spawn.cwd_for(str(tmp_path)) == str(tmp_path)
    assert spawn.cwd_for(str(frozen.mei / 'taskuary')) == str(config.home())
    assert spawn.cwd_for(None) == str(config.home())                 # inherited cwd is inside: replaced too


def test_children_get_the_default_dll_search_path_and_it_is_put_back_once(frozen):
    with spawn.clean_dll_dir():
        with spawn.clean_dll_dir(): pass                              # another thread spawning at the same time
        assert frozen.k.SetDllDirectoryW.call_args_list == [mock.call(None)]
    assert frozen.k.SetDllDirectoryW.call_args_list == [mock.call(None), mock.call(str(frozen.mei.resolve()))]


# ── every spawn site ───────────────────────────────────────────────────────────────────────
@pytest.mark.parametrize('call', [
    lambda: spawn.popen(['git', 'status']),
    lambda: spawn.run(['git', 'status'], capture_output=True),
    lambda: spawn.bare(['node', 'x.mjs'], creationflags=0),
    lambda: spawn.popen(['claude'], cwd=os.getcwd(), env={'PATH': os.environ['PATH'], '_PYI_ARCHIVE_FILE': 'x'}),
])
def test_spawn_helpers(frozen, call):
    call()
    clear_of(frozen, frozen.calls[-1])
    assert frozen.k.SetDllDirectoryW.call_args_list[0] == mock.call(None)


def test_the_update_helper(frozen):
    update._launch_swap(Path(r'C:\Apps\taskuary-update.cmd'), Path(os.getcwd()))
    clear_of(frozen, frozen.calls[-1])


def test_the_whatsapp_bridge(frozen, tmp_path, monkeypatch):
    from taskuary import wabridge
    run = tmp_path / 'wa'; (run / 'node_modules' / '@whiskeysockets').mkdir(parents=True)
    monkeypatch.setattr(wabridge, 'node', lambda: 'node')
    monkeypatch.setattr(wabridge, 'stage', lambda carry=True: run)
    monkeypatch.setattr(wabridge, 'LOG', tmp_path / 'wa.log')
    monkeypatch.setattr(wabridge, 'token', lambda: 't')
    monkeypatch.setattr(wabridge.time, 'sleep', lambda s: None)
    assert wabridge.start(wait=True)['phase'] == 'running'
    clear_of(frozen, frozen.calls[-1])


def test_the_browser_view(frozen, monkeypatch):
    from taskuary import browserview
    monkeypatch.setattr(browserview.shutil, 'which', lambda n: r'C:\bin\agent-browser.exe')
    opened = iter([False, True])
    monkeypatch.setattr(browserview, 'state', lambda sid, fresh=False: {'open': next(opened, True)})
    monkeypatch.setattr(browserview.time, 'sleep', lambda s: None)
    assert browserview.start('s1')
    clear_of(frozen, frozen.calls[-1])
    assert browserview.set_viewport('s1', 800, 600)
    clear_of(frozen, frozen.calls[-1])


def test_an_acp_client_and_a_live_cli(frozen):
    from taskuary import acp, clipool
    acp.ACPClient('agent', ['--acp'], cwd=str(frozen.mei))
    clear_of(frozen, frozen.calls[-1])
    clipool.Live('k', ['claude'], None, None, ())
    clear_of(frozen, frozen.calls[-1])


@pytest.mark.skipif(os.name != 'nt', reason='ConPTY')
def test_an_agent_terminal(frozen, monkeypatch):
    import winpty
    from taskuary import terminal
    seen = {}
    monkeypatch.setattr(winpty.PtyProcess, 'spawn', classmethod(lambda cls, argv, **kw: seen.update(kw) or FakeProc()))
    terminal._WinPty(['claude'], None, 30, 100)
    clear_of(frozen, {**seen, 'close_fds': True})                     # ConPTY passes the pty and nothing else
    assert frozen.k.SetDllDirectoryW.call_args_list[0] == mock.call(None)


# Every place that starts a process goes through spawn (or is a road no Windows exe takes). A new
# subprocess.Popen somewhere is a new child that may sit in the unpack folder - so it fails here first.
DIRECT = re.compile(r'\bsubprocess\.(Popen|run|call|check_call|check_output)\(|PtyProcess\.spawn\(|os\.(system|startfile|spawn\w*)\(|create_subprocess_')
NOT_ON_THE_EXE = {('imessage.py', "['open'"), ('imessage.py', "['osascript'"), ('wabridge.py', "['lsof'"),
                  ('terminal.py', 'subprocess.Popen(argv, cwd=cwd, stdin=slave'), ('terminal.py', 'PtyProcess.spawn(argv, cwd=spawn.cwd_for')}


def test_nothing_starts_a_process_around_spawn():
    stray = []
    for p in sorted(ROOT.rglob('*.py')):
        if p.name == 'spawn.py' or 'tests' in p.parts: continue
        for n, line in enumerate(p.read_text(encoding='utf-8').splitlines(), 1):
            code = line.split('#', 1)[0]
            if DIRECT.search(code) and not any(p.name == f and s in code for f, s in NOT_ON_THE_EXE):
                stray.append(f'{p.relative_to(ROOT)}:{n}: {line.strip()}')
    assert not stray, 'start these through spawn.popen/run/bare:\n' + '\n'.join(stray)


# ── what Taskuary owns is stopped before it goes ───────────────────────────────────────────
def test_update_stops_owned_children_before_it_exits(monkeypatch):
    order = []
    class Now:                                                        # threads run at once, so the order is the code's
        def __init__(self, target=None, daemon=None, **kw): self.t = target
        def start(self): self.t()
        def join(self, timeout=None): pass
        def is_alive(self): return False
    monkeypatch.setattr(update.threading, 'Thread', Now)
    monkeypatch.setattr(update.time, 'sleep', lambda s: None)
    monkeypatch.setattr(unpack, 'stop_owned', lambda: order.append('stop'))
    monkeypatch.setattr(unpack, 'handoff', lambda: order.append('handoff'))
    monkeypatch.setattr(update.os, '_exit', lambda c: order.append(f'exit {c}'))
    update.exit_soon(0)
    assert order == ['stop', 'handoff', 'exit 0']


def test_stop_owned_closes_terminals_cli_runs_and_the_pool(monkeypatch):
    from taskuary import agents, clipool, terminal, wabridge
    seen = []
    monkeypatch.setattr(terminal, 'shutdown_sessions', lambda: seen.append('sessions'))
    monkeypatch.setattr(agents, 'shutdown_cli_children', lambda: seen.append('cli'))
    monkeypatch.setattr(clipool, 'close', lambda prefix: seen.append(f'pool:{prefix}'))
    monkeypatch.setattr(wabridge, 'stop_if_unpacked', lambda: seen.append('bridge'))
    unpack.stop_owned()
    assert seen == ['sessions', 'cli', 'pool:', 'bridge']


def test_a_closed_session_takes_its_browser_with_it(monkeypatch):
    from taskuary import browserview, terminal
    s = mock.Mock(mode='', store=None, task_id=None)
    monkeypatch.setitem(terminal.SESSIONS, 'sx', s)
    closed = []
    monkeypatch.setattr(browserview, 'close', closed.append)
    terminal.shutdown_sessions()
    s.close.assert_called_once()
    assert closed == ['sx'] and 'sx' not in terminal.SESSIONS


def test_the_bridge_in_the_home_keeps_running_and_one_in_the_folder_is_stopped(frozen, monkeypatch):
    from taskuary import config, wabridge
    stopped = []
    monkeypatch.setattr(wabridge, 'stop', lambda hold=False: stopped.append(1))
    monkeypatch.setattr(wabridge, 'run_dir', lambda: config.home() / 'whatsapp')
    assert wabridge.stop_if_unpacked() is False and not stopped       # the next version adopts it
    monkeypatch.setattr(wabridge, 'run_dir', lambda: frozen.mei / 'taskuary' / 'whatsapp')
    assert wabridge.stop_if_unpacked() is True and stopped


# ── the safety net: nothing left over becomes a dialog ─────────────────────────────────────
def test_the_swap_also_waits_for_the_bootloader_that_holds_the_exe():
    s = update.swap_script(PureWindowsPath(r'C:\Apps\Taskuary.exe'), PureWindowsPath(r'C:\Apps\T.new.exe'), 4242, [], also=[77])
    assert 'PID eq 4242' in s and 'PID eq 77' in s and 'find " 77 "' in s
    assert s.index('PID eq 77') < s.index('move /Y')


def test_the_sweeper_waits_for_us_and_names_the_folder_only_through_the_environment():
    s = unpack.sweep_script(4242)
    assert 'PID eq 4242' in s and s.index('PID eq 4242') < s.index('rmdir /s /q "%TQ_UNPACK%"')
    assert 'goto done' in s and 'del "%~f0"' in s and s.endswith('\r\n')


def test_handoff_starts_the_sweeper_then_ends_the_bootloader(frozen, monkeypatch):
    seen = []
    monkeypatch.setattr(unpack, 'bootloader', lambda: 77)
    monkeypatch.setattr(update, '_launch_swap', lambda script, cwd, env=None: seen.append(('sweeper', Path(script).is_file(), env['TQ_UNPACK'])))
    monkeypatch.setattr(unpack, '_terminate', lambda pid: seen.append(('end', pid)) or True)
    assert unpack.handoff() is True
    assert seen == [('sweeper', True, str(frozen.mei.resolve())), ('end', 77)]


def test_no_sweeper_means_the_bootloader_is_left_to_clean_up(frozen, monkeypatch):
    monkeypatch.setattr(unpack, 'bootloader', lambda: 77)
    monkeypatch.setattr(update, '_launch_swap', mock.Mock(side_effect=OSError('refused')))
    end = mock.Mock()
    monkeypatch.setattr(unpack, '_terminate', end)
    assert unpack.handoff() is False and not end.called


def test_handoff_does_nothing_off_the_exe(monkeypatch):
    monkeypatch.setattr(sys, 'frozen', False, raising=False)
    launch = mock.Mock(); monkeypatch.setattr(update, '_launch_swap', launch)
    assert unpack.handoff() is False and not launch.called and unpack.bootloader() == 0


def test_the_bootloader_is_our_parent_only_when_it_runs_the_same_exe(frozen, monkeypatch):
    monkeypatch.setattr(spawn, 'WINDOWS', True)
    monkeypatch.setattr(unpack.os, 'getppid', lambda: 77)
    monkeypatch.setattr(unpack, '_image', lambda pid: sys.executable)
    assert unpack.bootloader() == 77
    monkeypatch.setattr(unpack, '_image', lambda pid: r'C:\Windows\explorer.exe')
    assert unpack.bootloader() == 0


def test_old_unpack_folders_of_ours_are_swept_and_nothing_else(frozen, tmp_path):
    def mk(name, mark=True, age=3600):
        d = tmp_path / name; (d / 'taskuary').mkdir(parents=True)
        if mark: (d / 'taskuary' / 'lanes.json').write_text('{}')
        t = time.time() - age; os.utime(d, (t, t)); return d
    (frozen.mei / 'taskuary' / 'lanes.json').write_text('{}'); os.utime(frozen.mei, (0, 0))
    old, other, fresh, claimed = mk('_MEI1111'), mk('_MEI2222', mark=False), mk('_MEI3333', age=5), mk('_MEI5555.taskuary-sweep', mark=False)
    busy = mk('_MEI4444'); held = open(busy / 'taskuary' / 'lanes.json')
    try: gone = unpack.sweep_stale()
    finally: held.close()
    assert sorted(gone) == ['_MEI1111', '_MEI5555.taskuary-sweep']
    assert not old.exists() and not claimed.exists() and not (tmp_path / '_MEI1111.taskuary-sweep').exists()
    assert other.exists() and fresh.exists() and frozen.mei.exists()          # another app's, one unpacking, ours
    if os.name == 'nt': assert busy.exists()                                   # in use: Windows refuses the rename
