"""shutil.which, remembered while nothing it searched has changed.

Every setup, first-run, agents and CLI request asked PATH where each AI CLI is: ~42 lookups across 49-85 directories
times 11 PATHEXT extensions, ~13,300 stats a request, and a page load fires 4-6 of those requests at once (perf report
2.7, 2026-10-19: setup 1.1 s, a load burst 2.1-3.4 s, 85-95% of it here). The owner's rule for this work: "performance
should not affect any action" - so the answer must be the one an uncached which() would give right now.

A lookup's answer can only change when an entry appears in or leaves a directory it searched, which bumps that
directory's mtime. So an answer is kept with the mtimes of the directories it searched and reused while they all read
the same; that check is one stat per directory, shared by every lookup for SIG_TTL. A found file is re-checked on
reuse (a symlink whose target went away), and no answer outlives MAX_AGE (a chmod +x, a coarse-mtime filesystem).
Taskuary's own installs, updates, connection changes and Test call `forget()`, so what the owner just did is seen at
once. The key carries the PATH string, PATHEXT and cwd, so a changed PATH is a new question. While shutil.which is
patched (a test's double) every call goes to the patch: a stand-in is never answered from memory."""
import os, shutil, sys, threading, time

_F = os.F_OK | os.X_OK
_ORIG = _scan = shutil.which      # _ORIG: is shutil.which still the real one?  _scan: what a miss runs (tests count it)
_hits, _sigs, _miss = {}, {}, threading.Lock()
SIG_TTL = 1.0      # one PATH's directory mtimes are read at most once a second - a page's burst shares them
MAX_AGE = 30.0     # and no answer is older than this, whatever the mtimes say


def forget() -> None:
    """Drop every remembered answer: Taskuary just installed, updated or reconnected a CLI, or the owner pressed Test."""
    _hits.clear(); _sigs.clear()


def _mtime(d):
    try: return os.stat(d or os.curdir).st_mtime_ns
    except (OSError, ValueError): return None
# ...but a Windows folder's mtime does not reliably move when a file lands in it (CI, 2026-10-20: a CLI copied into a PATH folder
# after the first look was never found), so there the folder's own listing is the signature - what which() would see, read once
def _listing(d):
    try: return hash(tuple(sorted(os.listdir(d or os.curdir))))
    except (OSError, ValueError): return None
if sys.platform == 'win32': _mtime = _listing


def _sig(path: str, cwd: str) -> tuple:
    k, now = (path, cwd), time.monotonic()
    hit = _sigs.get(k)
    if hit and now - hit[0] < SIG_TTL: return hit[1]
    ds = ([os.curdir] if sys.platform == 'win32' else []) + path.split(os.pathsep)
    s = tuple(_mtime(d) for d in dict.fromkeys(ds))
    _sigs[k] = (now, s)
    return s


def _ok(fn, mode) -> bool: return os.path.exists(fn) and os.access(fn, mode) and not os.path.isdir(fn)


def which(cmd, mode=_F, path=None):
    """shutil.which(cmd, mode, path) - the same answer, from memory while nothing it searched has changed."""
    kw = {**({'mode': mode} if mode != _F else {}), **({'path': path} if path is not None else {})}
    if shutil.which is not _ORIG: return shutil.which(cmd, **kw)                 # patched: the double decides
    if not isinstance(cmd, str) or os.path.dirname(cmd): return _scan(cmd, **kw)  # a path with a directory is one stat already
    p = path if path is not None else os.environ.get('PATH')
    if p is None: return _scan(cmd, **kw)                                         # confstr/defpath: rare, not worth a key
    cwd = os.getcwd()
    k = (cmd, mode, p, os.environ.get('PATHEXT') or '', cwd)
    def fresh(hit):
        return (hit is not None and time.monotonic() - hit[0] < MAX_AGE and hit[1] == _sig(p, cwd)
                and (hit[2] is None or _ok(hit[2], mode)))
    hit = _hits.get(k)
    if fresh(hit): return hit[2]
    with _miss:                          # single flight: the 4-6 requests of one page load scan once, not 4-6 times
        hit = _hits.get(k)
        if fresh(hit): return hit[2]
        t, s = time.monotonic(), _sig(p, cwd)
        r = _scan(cmd, **kw)
        _hits[k] = (t, s, r)
    return r
