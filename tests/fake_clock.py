"""A wall clock set to an hour of the test's choosing (no freezegun here): every taskuary module that imported `datetime` sees a
`datetime` whose now() starts at `at` and runs on from there. Pick a moment in the PAST - SQLite's own 'now' still reads the real
clock, and a stamp ahead of it would read as the future. Only modules ALREADY imported see it: run the code once first (a lazy
`from .testing import Factory` inside a function is imported on its first call, and would read the real clock).

    with fake_clock(datetime(2026, 10, 20, 8, 0)): ...
"""
import sys
from contextlib import contextmanager
from datetime import datetime as _real


@contextmanager
def fake_clock(at: _real):
    t0, base = _real.now(), at

    class Clock(_real):
        @classmethod
        def now(cls, tz=None):
            n = base + (_real.now() - t0)
            return n if tz is None else n.replace(tzinfo=tz)
        @classmethod
        def today(cls): return cls.now()

    swapped = []
    for name, mod in list(sys.modules.items()):
        if (name == 'taskuary' or name.startswith('taskuary.') or name.startswith('tests.')) and getattr(mod, 'datetime', None) is _real:
            swapped.append(mod); mod.datetime = Clock
    try: yield Clock
    finally:
        for mod in swapped: mod.datetime = _real
