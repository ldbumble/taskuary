"""One live Taskuary per data folder (the owner, 2026-10-14: "there should not be allowed 2 taskuarys in one machine").

The port was the only check, and a port is not the data: a second start whose port was taken by something else moved
to a free one and opened the SAME home - two pollers, two schedulers, two writers on one SQLite file, each launching its
own agents. An OS lock on <home>/taskuary.lock is what decides it now. The OS lets go when the process dies, however it
dies, so a crash never leaves a stale lock to clear by hand; instance.json beside it says where the holder serves, so a
second start can open that one instead.

A test or a demo has its own home, so it never meets the owner's lock - and its hooks are its own (hooks.user_wide)."""
import json, os
from pathlib import Path
from loguru import logger

_HELD = {}          # normalised home -> the open, locked file: kept for the life of the process


def _key(home) -> str: return os.path.normcase(os.path.realpath(str(home)))


def _lock(f) -> bool:
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_NBLCK, 1)       # one byte, past the end is fine: a marker, not data
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        return True
    except OSError: return False


def _unlock(f) -> None:
    try:
        if os.name == 'nt':
            import msvcrt
            f.seek(0); msvcrt.locking(f.fileno(), msvcrt.LK_UNLCK, 1)
        else:
            import fcntl
            fcntl.flock(f.fileno(), fcntl.LOCK_UN)
    except OSError: pass


def claim(url: str = '', home=None) -> bool:
    """Take this data folder for this process. True = it is ours (already, or now); False = another live process holds it."""
    from . import config
    home = Path(home or config.home())
    k = _key(home)
    if k in _HELD:
        if url: _say(home, url)
        return True
    try: f = open(home / 'taskuary.lock', 'a+b')
    except OSError as e:
        logger.warning(f'instance lock not opened ({e}) - starting without it'); return True       # a read-only home is not a second instance
    import time
    # a few tries: another start's holder() takes the lock for an instant to see whether it is free
    for i in range(5):
        if _lock(f): break
        if i == 4: f.close(); return False
        time.sleep(0.1)
    _HELD[k] = f
    _say(home, url)
    return True


def _say(home: Path, url: str) -> None:
    try: (home / 'instance.json').write_text(json.dumps({'pid': os.getpid(), 'url': url}), encoding='utf-8')
    except OSError as e: logger.debug(f'instance.json not written: {e}')


def holder(home=None) -> dict:
    """The process holding this data folder, as it said ({'pid', 'url'}) - {} when nobody does, or it is us."""
    from . import config
    home = Path(home or config.home())
    if _key(home) in _HELD: return {}
    try: f = open(home / 'taskuary.lock', 'a+b')
    except OSError: return {}
    try:
        if _lock(f): _unlock(f); return {}      # free: nobody holds it
    finally: f.close()
    try: d = json.loads((home / 'instance.json').read_text(encoding='utf-8'))
    except (OSError, ValueError): d = {}
    return d if isinstance(d, dict) and d else {'pid': None, 'url': ''}


def release(home=None) -> None:
    "Let the folder go (tests; a process exit does it anyway)."
    from . import config
    f = _HELD.pop(_key(home or config.home()), None)
    if f: f.close()
