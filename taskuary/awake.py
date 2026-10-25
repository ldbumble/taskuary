"""Live work, counted once: what keeps the computer awake, and what an update waits for.

An agent session or a workflow run is LIVE while it works. Two things read that here (the owner, 2026-10-25): the computer is held
awake while any is live and let go the moment none is (Windows SetThreadExecutionState), and an update waits until none is,
saying what it waits for ("Update waits for 1 running agent"). One count, so the two can never disagree about what is running.
"""
import sys, threading
from loguru import logger

from .timewords import plural

ES_CONTINUOUS, ES_SYSTEM_REQUIRED = 0x80000000, 0x00000001
POLL = 20.0                 # seconds between looks - sleep is held minutes at a time, so a run that just started waits at most this long


def live(store) -> tuple:
    """(agents, workflow runs) working right now. A workflow run whose worker is already a live session counts once, as the agent."""
    from . import welcome, workflows
    agents = {t['TaskId'] for t in welcome.working(store)}
    with workflows._LOCK: flows = set(workflows._STARTING) - agents
    return len(agents), len(flows)


def said(agents: int, flows: int) -> str:
    """'1 running agent', '2 running agents and 1 workflow run', '' when nothing is live."""
    return ' and '.join(x for x in (agents and plural(agents, 'running agent'), flows and plural(flows, 'workflow run')) if x)


def running(store) -> str:
    """What is live, in words - '' when nothing is, or when it cannot be read (a count never holds an update back for good)."""
    try: return said(*live(store))
    except Exception as e: logger.warning(f'awake: could not count live work - {e}'); return ''


def _set(flags: int) -> bool:
    """The OS call; False where there is none. Windows ties the state to THIS thread, so the watcher's own thread makes every call."""
    if sys.platform != 'win32': return False
    import ctypes
    return bool(ctypes.windll.kernel32.SetThreadExecutionState(flags))


class Watch:
    """Holds the computer awake while work is live. `tick(busy)` moves the hold only when it changes - the call is cheap, but a log
    line per poll is not - and `release()` lets go whatever happens."""
    def __init__(self, setter=_set): self.set, self.held = setter, False
    def tick(self, busy: bool) -> bool:
        if busy != self.held:
            self.set(ES_CONTINUOUS | ES_SYSTEM_REQUIRED if busy else ES_CONTINUOUS); self.held = busy
            logger.info('awake: holding the computer awake while work runs' if busy else 'awake: nothing is running - sleep is allowed again')
        return self.held
    def release(self):
        if self.held: self.set(ES_CONTINUOUS); self.held = False


_STOP, _WATCH = threading.Event(), [None]


def start(store, poll: float = POLL, setter=_set) -> threading.Thread:
    """The watcher's thread, for the app's lifetime (server lifespan). The hold is the thread's own, so it ends with it as well."""
    _STOP.clear()
    w = _WATCH[0] = Watch(setter)
    def loop():
        try:
            while not _STOP.is_set():
                try: w.tick(any(live(store)))
                except Exception as e: logger.debug(f'awake: no look this time - {e}')
                _STOP.wait(poll)
        finally: w.release()
    t = threading.Thread(target=loop, name='taskuary-awake', daemon=True); t.start()
    return t


def stop(): _STOP.set()
