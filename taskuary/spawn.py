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
for DETACHED_PROCESS, a stronger statement of the same intent.
"""
import os
import subprocess

# defined on Windows Python 3.7+; the literal keeps this importable (and testable) anywhere
CREATE_NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0x08000000)
WINDOWS = os.name == 'nt'


def flags(**kw) -> dict:
    """The caller's keyword arguments, plus the flag that keeps the console shut on Windows.
    An explicit creationflags is kept and OR-ed, never replaced."""
    if not WINDOWS: return kw
    return {**kw, 'creationflags': kw.get('creationflags', 0) | CREATE_NO_WINDOW}


def run(*args, **kw): return subprocess.run(*args, **flags(**kw))
def popen(*args, **kw): return subprocess.Popen(*args, **flags(**kw))
