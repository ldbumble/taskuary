"""Child processes that do not open a console window.

Taskuary ships as a WINDOWED app - `taskuary.spec` builds Taskuary.exe with `console=False`, and
the desktop launcher is a pywebview window. On Windows a process with no console of its own gives
every child it starts a BRAND NEW one: a black window that pops up, flashes, and sometimes stays.
Nothing was wrong with the work being done; it was `git status`, a PowerShell report, a headless
agent run, each politely allocating a terminal nobody asked for. ("It keeps on opening terminal
windows which doesn't happen on this machine" - the owner, 2026-09-02, on a machine running the
exe. The machine where it never happened launches from a terminal, whose console the children
quietly inherit, which is exactly why this went unnoticed for so long.)

CREATE_NO_WINDOW says "run, but allocate no console". It is Windows-only and a no-op elsewhere.

What must NOT come through here: the interactive pty sessions. ConPTY (pywinpty) manages its own
hidden console and the flag has no business there - and the WhatsApp bridge, which already asks
for DETACHED_PROCESS, a stronger statement of the same intent. Those take `bare` / `guard`: all of
the below about the one-file exe, without the console flag.

NOTHING WE START MAY HOLD THE EXE'S UNPACK FOLDER. Taskuary.exe is a PyInstaller one-file build: it
unpacks into %TEMP%\\_MEIxxxx, and when it exits its bootloader deletes that folder - and when it
cannot, because a child still has something in it, it retries for fifteen seconds and then puts up
"Failed to remove temporary directory" in a dialog (owners met it after pressing Update, 2026-10-22).
A child holds the folder three ways, and `guard` + `clean_dll_dir` close all three:
  - its working directory is inside it (a cwd taken from a path under the package);
  - it LOADED A DLL from it: the bootloader points the process's DLL directory at the folder
    (SetDllDirectory), every child inherits that, and it is searched BEFORE System32 - so a
    long-lived child built on the MSVC runtime (a Rust daemon, say) maps the bundled VCRUNTIME140.dll
    and keeps it mapped. PyInstaller's own advice is to clear it for children;
  - it IS Taskuary.exe, started with our environment: PyInstaller >= 6.9 reads that as "a worker of
    my parent" and runs out of the parent's folder (the trap update.py's helper fell into, 2026-09-24).
And no child inherits our handles (close_fds): a child keeping one of our open files keeps it open.
"""
import os, subprocess, sys, threading
from contextlib import contextmanager

# defined on Windows Python 3.7+; the literal keeps this importable (and testable) anywhere
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
WINDOWS = os.name == 'nt'


def meipass() -> str:
    """The one-file exe's unpack folder, or '' when this is not a frozen build."""
    m = getattr(sys, '_MEIPASS', None) if getattr(sys, 'frozen', False) else None
    return os.path.realpath(m) if m else ''


def onedir() -> bool:
    """The installed build (TaskuarySetup.exe, taskuary.spec's one-folder mode): its bundle is the _internal folder beside
    Taskuary.exe, never unpacked to %TEMP% - so there is no bootloader parent and no unpack folder to sweep."""
    m = meipass()
    return bool(m) and os.path.normcase(os.path.dirname(m)) == os.path.normcase(os.path.dirname(os.path.realpath(sys.executable)))


def inside(path, root) -> bool:
    if not (path and root): return False
    a,b = os.path.normcase(os.path.realpath(path)),os.path.normcase(os.path.realpath(root))
    try: return os.path.commonpath([a, b]) == b
    except ValueError: return False             # another drive


def cwd_for(cwd=None):
    """The folder a child starts in: as asked, unless that is inside the unpack folder - then the Taskuary home."""
    m = meipass()
    if not m or not inside(cwd or os.getcwd(), m): return cwd
    from . import config
    return str(config.home())


def env_for(env=None):
    """The child's environment with nothing tying it to our unpack folder: PyInstaller's markers gone,
    PYINSTALLER_RESET_ENVIRONMENT set (a Taskuary.exe started from here unpacks for itself), and no PATH
    entry inside the folder. On an ordinary install it comes back as given - None still means inherit."""
    m = meipass()
    if not m: return env
    e = {k: v for k, v in (os.environ if env is None else env).items() if not k.upper().startswith(('_PYI_', '_MEIPASS'))}
    e['PYINSTALLER_RESET_ENVIRONMENT'] = '1'
    for k in [k for k in e if k.upper() == 'PATH']: e[k] = os.pathsep.join(p for p in e[k].split(os.pathsep) if not inside(p, m))
    return e


def guard(**kw) -> dict:
    """What any child of the frozen exe starts with: a cwd and environment clear of the unpack folder, and none
    of our handles. On an ordinary install the arguments come back untouched."""
    if not meipass(): return kw
    return {**kw, 'cwd': cwd_for(kw.get('cwd')), 'env': env_for(kw.get('env')), 'close_fds': True}


_DLL = {'n': 0, 'added': None}
_DLL_LOCK = threading.Lock()
def _kernel32():
    import ctypes
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    k.SetDllDirectoryW.argtypes = [ctypes.c_wchar_p]
    return k


@contextmanager
def clean_dll_dir():
    """Start children on the default DLL search path, not the unpack folder (the module's note). Counted, so
    overlapping spawns on several threads clear it once and put it back once. While it is cleared this process
    still finds its own DLLs: the folder is also an AddDllDirectory entry, which Python's extension and ctypes
    loads search - and which, unlike SetDllDirectory, no child inherits."""
    m = meipass()
    if not (m and WINDOWS): yield; return
    k = _kernel32()
    with _DLL_LOCK:
        if _DLL['added'] is None:
            try: _DLL['added'] = os.add_dll_directory(m)
            except (OSError, AttributeError): _DLL['added'] = False
        _DLL['n'] += 1
        if _DLL['n'] == 1: k.SetDllDirectoryW(None)
    try: yield
    finally:
        with _DLL_LOCK:
            _DLL['n'] -= 1
            if not _DLL['n']: k.SetDllDirectoryW(m)


def flags(**kw) -> dict:
    """The caller's keyword arguments, plus the flag that keeps the console shut on Windows.
    An explicit creationflags is kept and OR-ed, never replaced."""
    if not WINDOWS: return kw
    return {**kw, 'creationflags': kw.get('creationflags', 0) | CREATE_NO_WINDOW}


# A PROGRAM BEING REPLACED UNDER US (walk 2, 2026-11-19): the claude CLI updated itself while two tasks started - for eight seconds its exe was
# a half-written file, Windows answered "[WinError 216] This version of %1 is not compatible...", and both starts failed for good. The image
# Windows cannot load (193, 216) or cannot open while it is being written (32) is tried again for a few seconds before it counts as a failure
SWAPPING, SWAP_WAIT = (32, 193, 216), 12.0
def _started(f, *args, **kw):
    import time
    end = time.monotonic() + SWAP_WAIT
    while True:
        try:
            with clean_dll_dir(): return f(*args, **kw)
        except OSError as e:
            if getattr(e, 'winerror', None) not in SWAPPING or time.monotonic() > end: raise
            time.sleep(1)


# AGENTS END WITH THE APP (the load test, 2026-11-24): an orderly Quit closes every session (terminal.shutdown_sessions), but a server that died any
# other way - a crash, Task Manager, a kill - left the agent CLIs and agent Chromes it started running on, and with a real AI they would spend
# tokens nobody sees. So every child started here is TIED to this process, and the tie is the operating system's, not a handler of ours:
#   - Windows: each child goes into one job object with KILL_ON_JOB_CLOSE whose only handle this process holds. However the process ends, the
#     kernel closes that handle and ends the job - the child and all it starts after (descendants inherit the job). BREAKAWAY_OK lets a child
#     that asks to (CREATE_BREAKAWAY_FROM_JOB) leave on purpose. The child is put in the job just after it starts: what it starts in its first
#     instant would be outside, and the next start's close_left is there for that.
#   - macOS and Linux: a child starts in a process group of its own, and one watchdog (`sh`, its own session) reads the groups from a pipe only
#     this process writes. At end of file - which the kernel delivers when this process ends, SIGKILL included - it ends every group listed.
#     Not PR_SET_PDEATHSIG: on Linux it fires when the starting THREAD ends, and children are started from request threads that end at once.
#     What it cannot reach: a descendant that started a session of its own (a daemon), or one left in a group whose leader was already reaped -
#     those this home's next start closes (close_left; browserview.close_orphans for the browsers).
# A child that must outlive us says so - `outlive=True`: the owner's own browser, the update helper, the relaunched app, the WhatsApp bridge.
_TIE_LOCK = threading.RLock()
_JOB = {'h': None, 'w': None}

def _job():
    "Windows: the job every tied child is put in, made once (0 where Windows refused one: children then run untied, as before)."
    if _JOB['h'] is not None: return _JOB['h']
    import ctypes, ctypes.wintypes as W
    k = ctypes.WinDLL('kernel32', use_last_error=True)
    class BASIC(ctypes.Structure):
        _fields_ = [('pt', ctypes.c_int64), ('jt', ctypes.c_int64), ('flags', W.DWORD), ('minws', ctypes.c_size_t), ('maxws', ctypes.c_size_t),
                    ('n', W.DWORD), ('aff', ctypes.c_size_t), ('prio', W.DWORD), ('sched', W.DWORD)]
    class EXT(ctypes.Structure):
        _fields_ = [('basic', BASIC), ('io', ctypes.c_uint64 * 6)] + [(n, ctypes.c_size_t) for n in ('pm', 'jm', 'ppm', 'pjm')]
    k.CreateJobObjectW.restype = W.HANDLE
    h, info = k.CreateJobObjectW(None, None), EXT()
    info.basic.flags = 0x2000 | 0x800           # KILL_ON_JOB_CLOSE | BREAKAWAY_OK
    if not (h and k.SetInformationJobObject(W.HANDLE(h), 9, ctypes.byref(info), ctypes.sizeof(info))): h = 0
    _JOB['h'] = h or 0
    return _JOB['h']

WATCH_SH = ('l=" "; while read op t; do case $op in a) l="$l$t ";; d) l=$(printf %s "$l" | sed "s/ $t / /");; esac; done; '
            'for t in $l; do kill -TERM -- "$t" 2>/dev/null; done; sleep 2; for t in $l; do kill -KILL -- "$t" 2>/dev/null; done')
def _watch(line: str):
    "POSIX: hand the watchdog one line (`a <target>` to end at our death, `d <target>` to forget), starting it on first use."
    with _TIE_LOCK:
        try:
            if _JOB['w'] is None:
                r, w = os.pipe()
                subprocess.Popen(['/bin/sh', '-c', WATCH_SH], stdin=r, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, start_new_session=True)
                os.close(r); _JOB['w'] = os.fdopen(w, 'w', buffering=1)
            _JOB['w'].write(line + '\n')
        except (OSError, ValueError): pass

def tie(pid: int = 0, handle=None) -> bool:
    "Tie process `pid` (or the process `handle`) to this one: it ends when we do, however we end (the note above). True when tied."
    if WINDOWS:
        import ctypes, ctypes.wintypes as W
        k = ctypes.WinDLL('kernel32', use_last_error=True)
        k.OpenProcess.restype = W.HANDLE
        with _TIE_LOCK: job = _job()
        if not job: return False
        handle = int(getattr(handle, 'value', handle) or 0)
        h = handle or k.OpenProcess(0x0101, False, int(pid))       # PROCESS_SET_QUOTA | PROCESS_TERMINATE
        try: return bool(h and k.AssignProcessToJobObject(W.HANDLE(job), W.HANDLE(h)))
        finally:
            if h and not handle: k.CloseHandle(W.HANDLE(h))
    try: _watch(f'a -{pid}' if os.getpgid(pid) == pid else f'a {pid}')
    except OSError: return False
    return True


def _tied(p):
    """Child `p` tied (tie) and listed (listed) - and on POSIX forgotten by the watchdog once reaped, before its pid can be reused. Only a real
    Popen: a test's stand-in carries no process to tie."""
    if not any(c.__module__ == 'subprocess' and c.__name__ == 'Popen' for c in type(p).__mro__): return p
    tie(p.pid, int(p._handle) if WINDOWS else None); listed(p.pid)
    if not WINDOWS:
        done = p._handle_exitstatus
        def reaped(sts, *a, **kw):
            done(sts, *a, **kw)
            if not os.WIFSTOPPED(sts): _watch(f'd -{p.pid}'); _watch(f'd {p.pid}')
        p._handle_exitstatus = reaped
    return p


def _popen(kw: dict):
    """How a long-lived child starts: tied unless `outlive`, and on POSIX in a group of its own unless the caller chose. The Popen is looked up
    at the call, so a test's stand-in for it still stands in."""
    if kw.pop('outlive', False): return lambda *a, **k: subprocess.Popen(*a, **k), kw
    if not WINDOWS and not {'start_new_session', 'process_group', 'preexec_fn'} & set(kw): kw['start_new_session'] = True
    return (lambda *a, **k: _tied(subprocess.Popen(*a, **k))), kw


# ...AND WHAT A RUN THAT DIED LEFT, ITS NEXT START CLOSES: the long-lived children (popen, bare, a terminal's CLI) are listed in the home with
# when they started and who started them. close_left ends those whose starter is gone and that are still the same process - a pid handed to
# something else since does not match its start time and is left alone.
def _stamp(pid: int) -> str:
    "When process `pid` started, as the OS says it - '' when no such process runs."
    try:
        if WINDOWS:
            import ctypes, ctypes.wintypes as W
            k = ctypes.WinDLL('kernel32', use_last_error=True); k.OpenProcess.restype = W.HANDLE
            h = k.OpenProcess(0x1000, False, int(pid))
            if not h: return ''
            try:
                rc, t = W.DWORD(), [W.FILETIME() for _ in range(4)]
                if not (k.GetExitCodeProcess(W.HANDLE(h), ctypes.byref(rc)) and rc.value == 259): return ''
                if not k.GetProcessTimes(W.HANDLE(h), *(ctypes.byref(x) for x in t)): return ''
                return str(t[0].dwHighDateTime << 32 | t[0].dwLowDateTime)
            finally: k.CloseHandle(W.HANDLE(h))
        if os.path.exists(f'/proc/{int(pid)}/stat'):
            with open(f'/proc/{int(pid)}/stat') as f: st = f.read().rsplit(')', 1)[1].split()
            return '' if st[0] in 'ZX' else st[19]
        return subprocess.run(['ps', '-o', 'lstart=', '-p', str(int(pid))], capture_output=True, text=True, timeout=5).stdout.strip()
    except (OSError, ValueError, IndexError, subprocess.SubprocessError): return ''

_ME = []
def _list_file():
    from . import config
    return config.home() / 'children.json'

def _read_list() -> dict:
    import json
    try: d = json.loads(_list_file().read_text(encoding='utf-8'))
    except (OSError, ValueError): return {}
    return d if isinstance(d, dict) else {}

def _write_list(d: dict):
    import json
    try: _list_file().write_text(json.dumps(d), encoding='utf-8')
    except OSError: pass

def listed(pid: int):
    "List child `pid` in the home for the next start, should this process die without closing it; entries that ended since are dropped."
    with _TIE_LOCK:
        if not _ME: _ME.extend([os.getpid(), _stamp(os.getpid())])
        try: d = {k: v for k, v in _read_list().items() if isinstance(v, list) and v and _stamp(int(k)) == v[0]}
        except (TypeError, ValueError): d = {}
        d[str(int(pid))] = [_stamp(pid), *_ME]
        _write_list(d)

def adopt(pid: int) -> bool:
    "A child started outside popen (a ConPTY session): tied and listed like one started here."
    ok = tie(pid); listed(pid); return ok

def close_left() -> int:
    """At start: end the children a run of this home that is gone left running - its agents and what they run. One whose starter still runs
    (another process of this home) is kept. Returns how many were ended."""
    import signal
    keep, gone = {}, []
    with _TIE_LOCK:
        for k, v in _read_list().items():
            try: pid, (made, by, by_made) = int(k), v
            except (TypeError, ValueError): continue
            if not made or _stamp(pid) != made: continue
            if by == os.getpid() or _stamp(by) == by_made: keep[k] = v
            else: gone.append(pid)
        _write_list(keep)
    for pid in gone:
        try:
            if WINDOWS: _end_tree(pid)
            elif os.getpgid(pid) == pid: os.killpg(pid, signal.SIGKILL)
            else: os.kill(pid, signal.SIGKILL)
        except OSError: pass
    return len(gone)

def _end_tree(pid: int):
    "Windows: end process `pid` and every process it started that still runs (a child is younger than its parent: an older one only reuses a pid)."
    import ctypes, ctypes.wintypes as W
    class PE(ctypes.Structure):
        _fields_ = [('size', W.DWORD), ('use', W.DWORD), ('pid', W.DWORD), ('heap', ctypes.c_size_t), ('mod', W.DWORD), ('n', W.DWORD),
                    ('ppid', W.DWORD), ('prio', ctypes.c_long), ('flags', W.DWORD), ('exe', ctypes.c_wchar * 260)]
    k = ctypes.WinDLL('kernel32', use_last_error=True); k.CreateToolhelp32Snapshot.restype = k.OpenProcess.restype = W.HANDLE
    snap, e, kids = k.CreateToolhelp32Snapshot(2, 0), PE(), {}
    e.size = ctypes.sizeof(PE)
    ok = k.Process32FirstW(W.HANDLE(snap), ctypes.byref(e))
    while ok: kids.setdefault(e.ppid, []).append(e.pid); ok = k.Process32NextW(W.HANDLE(snap), ctypes.byref(e))
    k.CloseHandle(W.HANDLE(snap))
    age = lambda p: int(_stamp(p) or 0)
    tree, todo = [], [int(pid)]
    while todo:
        p = todo.pop(); tree.append(p)
        todo += [c for c in kids.get(p, []) if c not in tree and age(c) >= age(p) > 0]
    for p in tree:
        if (h := k.OpenProcess(0x0001, False, p)): k.TerminateProcess(W.HANDLE(h), 1); k.CloseHandle(W.HANDLE(h))


# A TEMP FOLDER IS REMOVED BY WHOEVER MADE IT, AND BY THE NEXT ONE WHEN IT CANNOT (2026-11-24: eleven thousand test homes in %TEMP% since early
# November). A process removes its own at exit - but SQLite or ConPTY can still hold a file then, and a killed run never gets there. So each
# folder names its maker (pid and start time), and the next folder made with that prefix removes every one whose maker is gone.
MARK = '.taskuary-maker'

def rmtree(d, tries: int = 5) -> bool:
    "Remove folder `d` as far as it goes: a file Windows still holds a moment is tried again, a read-only one made writable. True when gone."
    import shutil, stat, time
    def again(f, p, _):
        try: os.chmod(p, stat.S_IWRITE); f(p)
        except OSError: pass
    for i in range(tries):
        shutil.rmtree(d, **({'onexc': again} if sys.version_info >= (3, 12) else {'onerror': again}))
        if not os.path.exists(d): return True
        if i < tries - 1: time.sleep(.2 * (i + 1))
    return False

def _mark(d):
    try:
        with open(os.path.join(d, MARK), 'w', encoding='utf-8') as f: f.write(f'{os.getpid()} {_stamp(os.getpid())}')
    except OSError: pass

def drop_temp(d):
    "At exit: our folder goes - and what a held file kept of it is marked ours again, for the next run to take."
    if not rmtree(d) and os.path.isdir(d): _mark(d)

def sweep_temp(prefix: str, root: str, unmarked_age: float = 86400) -> int:
    """Remove the folders in `root` named `prefix`... whose maker no longer runs. One with no mark (an older build's) goes once it is a day old.
    Returns how many went."""
    import time
    try: ds = [e for e in os.scandir(root) if e.name.startswith(prefix) and e.is_dir(follow_symlinks=False)]
    except OSError: return 0
    n = 0
    for e in ds:
        try:
            with open(os.path.join(e.path, MARK), encoding='utf-8') as f: pid, made = f.read().split(' ', 1)
            if _stamp(int(pid)) == made: continue                       # its maker still runs
        except (OSError, ValueError):
            try:
                if time.time() - e.stat().st_mtime < unmarked_age: continue
            except OSError: continue
        n += rmtree(e.path, tries=1)
    return n

def own_temp(prefix: str, root: str = None) -> str:
    "A new temp folder of this process: marked as ours, removed at our exit, and the leftovers of its prefix swept on a thread (sweep_temp)."
    import atexit, tempfile
    d = tempfile.mkdtemp(prefix=prefix, dir=root)
    _mark(d); atexit.register(drop_temp, d)
    threading.Thread(target=sweep_temp, args=(prefix, os.path.dirname(d)), daemon=True, name='temp-sweep').start()
    return d


# run(): a child waited for, bounded by its own timeout - not tied: subprocess.run builds its Popen inside, out of reach (a crash mid-run leaves
# that one command to finish)
def run(*args, **kw): return _started(subprocess.run, *args, **flags(**guard(**kw)))
def popen(*args, **kw):
    f, kw = _popen(kw)
    return _started(f, *args, **flags(**guard(**kw)))
def output(argv, timeout: float, **kw) -> tuple:
    """(exit code, what it wrote) of a command whose output goes to a FILE, never a pipe: a helper it leaves running (agent-browser's
    daemon, agent-desktop's command host) inherits the handle, and a pipe would never end. The file has no name - it goes with its last
    handle, so a log per session no longer piles up in %TEMP%. Past `timeout` the command is ended and subprocess.TimeoutExpired raised."""
    import tempfile
    with tempfile.TemporaryFile() as f:
        p = popen(argv, stdout=f, stderr=f, stdin=subprocess.DEVNULL, **kw)
        try: rc = p.wait(timeout=timeout)
        except subprocess.TimeoutExpired: p.kill(); raise
        f.seek(0); return rc, f.read().decode('utf-8', 'replace')
def bare(*args, **kw):
    """A child that sets its own creation flags (the WhatsApp bridge, the update helper, a browser): guarded, no console flag."""
    f, kw = _popen(kw)
    with clean_dll_dir(): return f(*args, **guard(**kw))
