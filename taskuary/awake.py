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
    return ' and '.join(x for x in (agents and plural(agents, 'running agent'), flows and plural(flows, 'routine run')) if x)


def running(store) -> str:
    """What is live, in words - '' when nothing is, or when it cannot be read (a count never holds an update back for good)."""
    try: return said(*live(store))
    except Exception as e: logger.warning(f'awake: could not count live work - {e}'); return ''


# AN UPDATE WAITS ONLY FOR WORK IN FLIGHT (TQ-1237, 2026-10-29): an agent parked at its prompt is waiting on the owner, so it never
# "finishes" by itself - an update held for one waited an hour and a half, and the card never said which task it was. The swap closes
# a parked session the way Quit does (its task stays open), so the update waits for agents mid-turn and workflow runs, and names them.
def _parked(t) -> bool:
    try: return t.waiting() is True
    except Exception: return False

def holding(store) -> tuple:
    """(agent task ids mid-turn, workflow run task ids) - what an update must not cut off. A task with any session still working, or a
    headless run, is mid-turn; one whose every live session is parked is not."""
    from . import terminal, welcome, workflows
    ss = [t for t in list(terminal.SESSIONS.values()) if getattr(t, 'alive', False)]
    parked = {t.task_id for t in ss if _parked(t)} - {t.task_id for t in ss if not _parked(t)}
    try: parked -= {r.get('TaskId') for r in store.running_runs()}
    except Exception: pass
    agents = sorted(t['TaskId'] for t in welcome.working(store) if t['TaskId'] not in parked)
    with workflows._LOCK: flows = sorted(set(workflows._STARTING) - set(agents) - parked)
    return agents, flows

def update_waits_for(store) -> str:
    """'1 running agent (TQ-0012)' - what an update waits for, named so the owner can find it; '' when nothing in flight."""
    from .store import task_ref
    try:
        agents, flows = holding(store)
        s = said(len(agents), len(flows))
        return s and f"{s} ({', '.join(task_ref(i) for i in agents + flows)})"
    except Exception as e: logger.warning(f'awake: could not count work in flight - {e}'); return ''


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
