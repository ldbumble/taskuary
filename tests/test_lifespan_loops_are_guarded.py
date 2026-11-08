"""Every forever-loop the lifespan starts must be stopped in tests.

`doorway_forever` was added on 2026-09-15 without being added to conftest's lifespan guard, and
unlike its siblings it ticks once a SECOND against the module-global `server.store`. The suite
swaps and closes that store constantly, so the thread eventually read a connection a finished test
had already closed - and sqlite3 does not raise for that, it segfaults the interpreter. CI went red
on several unrelated commits with no failing assertion to point at, just
"Fatal Python error: Segmentation fault" partway through the run.

So the guard is derived from the code rather than kept by hand: any `threading.Thread(target=X)`
started by the lifespan has to be named in conftest's patch list.
"""
import inspect
import re

from taskuary import server


def _lifespan_threads():
    src = inspect.getsource(server._lifespan)
    return set(re.findall(r'threading\.Thread\(target=(\w+)', src))


def test_the_lifespan_starts_the_loops_we_think_it_does():
    assert _lifespan_threads() == {'poll_forever', 'reports_forever', 'quick_forever', 'doorway_forever', 'share_start', 'resume_asking', 'close_orphan_browsers'}


def test_every_lifespan_loop_is_stopped_in_tests():
    from pathlib import Path
    conftest = (Path(__file__).resolve().parent / 'conftest.py').read_text(encoding='utf-8')
    guarded = set(re.findall(r"mock\.patch\.object\(server, '(\w+)'", conftest))
    missing = _lifespan_threads() - guarded
    assert not missing, (
        f'{sorted(missing)} run for real during tests. A loop on the module-global store outlives '
        'the test that started it and segfaults the run when that store is closed - add it to '
        'safe_lifespan in conftest.py.')


def test_the_doorway_ticks_fast_enough_to_matter():
    """Why this one bit when the older loops never did."""
    assert server.DOORWAY_TICK <= 2.0
    assert server.DOORWAY_TICK < server.POLL_TICK


def test_every_module_watcher_the_lifespan_starts_is_stopped_in_tests():
    # reasonnet.watch was started by every test lifespan and never stopped: the clocks piled up across the run and spun under
    # a test that mocked time.sleep, timing out the Windows job (0.3.10.22's first CI)
    from pathlib import Path
    started = set(re.findall(r'^\s*(\w+)\.watch\(store\)', inspect.getsource(server._lifespan), re.M))
    conftest = (Path(__file__).resolve().parent / 'conftest.py').read_text(encoding='utf-8')
    missing = started - set(re.findall(r"mock\.patch\.object\((\w+), 'watch'", conftest))
    assert started and not missing, f'{sorted(missing)}.watch runs for real during tests - stub it in safe_lifespan (conftest.py)'
