"""Print one part of the pytest files, balanced by size, for CI to run the suite in parallel halves.
Windows took 20-24 of its 35 minutes in one job, and a slow runner ran out of time with no test failing (2026-11-09)."""
import sys
from pathlib import Path

# ...but a small file can be a long run: the audit corpus drives every scenario on every agent backend (about 9 minutes) - weighed as that
# share of the suite's ~45 minutes, so it gets a part to itself rather than doubling one (2026-11-10)
SHARE = {'test_audit_scenarios.py': 0.2}

def shard(part: int, of: int, root='tests') -> list[str]:
    all_ = list(Path(root).rglob('test_*.py')); total = sum(p.stat().st_size for p in all_)
    size = lambda p: int(total * SHARE[p.name]) if p.name in SHARE else p.stat().st_size
    fs = sorted(all_, key=lambda p: (-size(p), str(p)))
    bins = [[0, []] for _ in range(of)]
    for f in fs: b = min(bins, key=lambda x: x[0]); b[0] += size(f); b[1].append(f.as_posix())
    return sorted(bins[part - 1][1])

if __name__ == '__main__': print('\n'.join(shard(int(sys.argv[1]), int(sys.argv[2]))))
