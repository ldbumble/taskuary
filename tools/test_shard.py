"""Print one part of the pytest files, balanced by size, for CI to run the suite in parallel halves.
Windows took 20-24 of its 35 minutes in one job, and a slow runner ran out of time with no test failing (2026-11-09)."""
import sys
from pathlib import Path

# ...but a small file can be a long run: the audit corpus drives every scenario on every agent backend (about 9 minutes) - weighed as that
# share of the suite's ~45 minutes, so it gets a part to itself rather than doubling one (2026-11-10)
# ...and so can five more (Windows part 3, 2026-11-26: the split is by size, a file grew, and all five fell into one part - 34 minutes at 84%
# when the job's 35 ran out, no test hanging). Each by its measured share of the Windows run, so no part can draw them all
SHARE = {'test_audit_scenarios.py': 0.2, 'test_assistant_queries.py': 0.08, 'test_landing.py': 0.04, 'test_line_road.py': 0.035,
         'test_every_card_kind.py': 0.03, 'test_app_own_screens.py': 0.025}

def shard(part: int, of: int, root='tests') -> list[str]:
    all_ = list(Path(root).rglob('test_*.py')); total = sum(p.stat().st_size for p in all_)
    size = lambda p: int(total * SHARE[p.name]) if p.name in SHARE else p.stat().st_size
    fs = sorted(all_, key=lambda p: (-size(p), str(p)))
    bins = [[0, []] for _ in range(of)]
    for f in fs: b = min(bins, key=lambda x: x[0]); b[0] += size(f); b[1].append(f.as_posix())
    return sorted(bins[part - 1][1])

if __name__ == '__main__': print('\n'.join(shard(int(sys.argv[1]), int(sys.argv[2]))))
