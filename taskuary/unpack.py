"""Leaving the one-file exe's unpack folder behind - cleanly, and never with a dialog.

Taskuary.exe is a PyInstaller one-file build. Its bootloader unpacks the program into
%TEMP%\\_MEIxxxx, starts Python from there as its child, waits, and deletes the folder when the
child exits. If anything still holds a file in it, the bootloader retries for fifteen seconds and
then shows "Warning - Failed to remove temporary directory" in a dialog (2026-10-22, after Update).
While it waits it also holds Taskuary.exe itself open, which is the file an Update has to replace.

Three layers, in order:
  stop_owned   what Taskuary started is stopped before it goes: agent terminals and their browsers,
               headless CLI runs, the live CLI pool - and the WhatsApp bridge only when it runs from
               inside the unpack folder (one in the home keeps going and the next start adopts it).
  spawn.guard  what Taskuary starts never touches the folder to begin with (cwd, DLL directory, env,
               handles - spawn.py says how each one held it).
  handoff      the safety net for what neither caught - a grandchild we never saw, a browser the
               owner's link opened. PyInstaller 6 has no switch for that warning (its only knob,
               PYINSTALLER_STRICT_UNPACK_MODE, turns it into an error), and a `runtime_tmpdir` moves
               the folder without changing what happens when it cannot be deleted. So the removal is
               taken off the bootloader: a hidden sweeper is started that deletes the folder once this
               process has gone, retrying while something holds it, and the bootloader - which has
               nothing left to do but that - is ended first, so it never gets to the dialog.
And sweep_stale, at start: any of Taskuary's own old unpack folders still lying in %TEMP% (a sweeper
that ran out of retries, a crash, a build from before this) is removed once nothing uses it.
"""
import os, re, shutil, sys, time
from pathlib import Path
from loguru import logger
from . import spawn

MARK = ('taskuary', 'lanes.json')       # in every Taskuary unpack folder (taskuary.spec ships taskuary/*.json): ours, not another app's
STALE_S = 600                           # younger than this may be a copy of Taskuary still unpacking: left alone
GONE = '.taskuary-sweep'                # a folder renamed for removal; a rename only succeeds when nothing inside is in use
_NAME = re.compile(r'^_MEI[0-9A-Fa-f]+(\.taskuary-sweep)?$')
SWEEP_TRIES = 120                       # x 5s: ten minutes for a straggler to let go, then the next start's sweep_stale
WAIT_S = 120                            # how long the sweeper waits for this process before it leaves the folder alone


def stop_owned() -> dict:
    """Stop the processes Taskuary owns, each on its own existing close road. Idempotent: the lifespan's
    shutdown already did most of this on an ordinary quit, and an Update's os._exit skips that shutdown."""
    from . import agents, clipool, terminal, wabridge
    out = {}
    for k, f in (('sessions', terminal.shutdown_sessions), ('cli', agents.shutdown_cli_children),
                 ('pool', lambda: clipool.close('')), ('bridge', wabridge.stop_if_unpacked)):
        try: out[k] = f()
        except Exception as e: logger.warning(f'leaving: could not stop {k} - {e}')
    return out


def _image(pid: int) -> str:
    """The full path of the program process `pid` runs, or ''."""
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x1000, False, pid)            # PROCESS_QUERY_LIMITED_INFORMATION
    if not h: return ''
    try:
        buf, n = ctypes.create_unicode_buffer(32768), wintypes.DWORD(32768)
        return buf.value if k.QueryFullProcessImageNameW(h, 0, buf, ctypes.byref(n)) else ''
    finally: k.CloseHandle(h)


def bootloader() -> int:
    """The PID of the one-file bootloader that unpacked us - our parent, running the same Taskuary.exe - or 0."""
    if not (spawn.meipass() and spawn.WINDOWS): return 0
    try:
        ppid = os.getppid()
        img = _image(ppid)
    except Exception: return 0
    same = img and os.path.normcase(os.path.realpath(img)) == os.path.normcase(os.path.realpath(sys.executable))
    return ppid if same else 0


def _terminate(pid: int) -> bool:
    import ctypes
    from ctypes import wintypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.OpenProcess.restype = wintypes.HANDLE
    h = k.OpenProcess(0x0001, False, pid)            # PROCESS_TERMINATE
    if not h: return False
    try: return bool(k.TerminateProcess(h, 0))
    finally: k.CloseHandle(h)


def sweep_script(pid: int) -> str:
    """Wait for `pid` to go, then delete %TQ_UNPACK% - retrying while something still holds it - and remove
    itself. The folder rides in the environment, not the text: a batch file is read in the console's code
    page, and %TEMP% holds the owner's name, which need not be ASCII. If `pid` never goes, nothing is deleted."""
    from .update import wait_lines
    return '\r\n'.join([
        '@echo off', 'setlocal', 'set /a waited=0',
        *wait_lines([pid], 'done'),
        'set /a tries=0',
        ':sweep',
        'rmdir /s /q "%TQ_UNPACK%" >nul 2>&1',
        'if not exist "%TQ_UNPACK%\\" goto done',
        'set /a tries+=1',
        f'if %tries% geq {SWEEP_TRIES} goto done',
        'ping -n 6 127.0.0.1 >nul',
        'goto sweep',
        ':done',
        'del "%~f0"',
        'exit /b 0']) + '\r\n'


def handoff() -> bool:
    """Take the unpack folder's removal off the bootloader (the module's note). False, with the bootloader left
    to do it as it always has, on anything but a frozen one-file exe or when the sweeper cannot be started."""
    m, boot = spawn.meipass(), bootloader()
    if not (m and boot): return False
    from . import config, update
    try:
        d = config.home() / 'update'; d.mkdir(parents=True, exist_ok=True)
        script = d / f'unpack-sweep-{os.getpid()}.cmd'
        script.write_text(sweep_script(os.getpid()), encoding='utf-8')
        update._launch_swap(script, d, env={**os.environ, 'TQ_UNPACK': m})
    except Exception as e:
        logger.warning(f'leaving: no sweeper for {m} ({e}) - the bootloader removes it as before'); return False
    ok = _terminate(boot)
    logger.info(f'leaving: {m} is the sweeper\'s to remove' + ('' if ok else ' (the bootloader could not be ended - it may try too)'))
    return ok


def sweep_stale(now: float = None) -> list:
    """Remove Taskuary's own old unpack folders beside ours: not this run's, old enough not to be a copy still
    unpacking, and renamable - Windows refuses to rename a folder while anything has a file in it open, runs from
    it or works in it, so a folder some process still uses is left exactly as it is. Returns what went.
    Off Windows nothing: a rename there succeeds under a running copy, so it is no test of use, and the bootloader
    removes a folder held open without a dialog."""
    m = spawn.meipass()
    if not (m and spawn.WINDOWS): return []
    now, gone = now or time.time(), []
    try: dirs = list(Path(m).parent.iterdir())
    except OSError: return []
    for d in dirs:
        try:
            if not (_NAME.match(d.name) and d.is_dir()) or os.path.normcase(str(d.resolve())) == os.path.normcase(m): continue
            if d.name.endswith(GONE): doomed = d                                # claimed by an earlier sweep that did not finish
            else:
                if not d.joinpath(*MARK).is_file(): continue                   # another PyInstaller app's: not ours to judge
                if now - d.stat().st_mtime < STALE_S: continue
                doomed = d.rename(d.with_name(d.name + GONE))                  # the in-use test, and the claim
        except OSError: continue
        shutil.rmtree(doomed, ignore_errors=True)
        if not doomed.exists(): gone.append(d.name)
    if gone: logger.info(f'removed {len(gone)} old unpack folder(s) of Taskuary: {", ".join(gone)}')
    return gone
