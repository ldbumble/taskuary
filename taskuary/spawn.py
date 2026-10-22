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


def run(*args, **kw):
    with clean_dll_dir(): return subprocess.run(*args, **flags(**guard(**kw)))
def popen(*args, **kw):
    with clean_dll_dir(): return subprocess.Popen(*args, **flags(**guard(**kw)))
def bare(*args, **kw):
    """A child that sets its own creation flags (the WhatsApp bridge, the update helper, a browser): guarded, no console flag."""
    with clean_dll_dir(): return subprocess.Popen(*args, **guard(**kw))
