"""Print one part of the pytest files, balanced by size, for CI to run the suite in parallel halves.
Windows took 20-24 of its 35 minutes in one job, and a slow runner ran out of time with no test failing (2026-11-09)."""
import sys
from pathlib import Path

def shard(part: int, of: int, root='tests') -> list[str]:
    fs = sorted(Path(root).rglob('test_*.py'), key=lambda p: (-p.stat().st_size, str(p)))
    bins = [[0, []] for _ in range(of)]
    for f in fs: b = min(bins, key=lambda x: x[0]); b[0] += f.stat().st_size; b[1].append(f.as_posix())
    return sorted(bins[part - 1][1])

if __name__ == '__main__': print('\n'.join(shard(int(sys.argv[1]), int(sys.argv[2]))))
