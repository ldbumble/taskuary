"""Taskuary - Automate your job: AI triage in, coding agents out, you in charge."""
# ONE place holds the version and it is pyproject.toml, because that is the one the git tag has
# to match (RELEASING.md). A second copy here said 0.2.0 through the whole of 0.2.1: the CLI
# banner, the API and the header pill all reported it, and the header's own tooltip told the
# owner to restart - which could never have helped, because restarting reloads the same
# hardcoded string.
from pathlib import Path


def _version() -> str:
    # pyproject FIRST, and only a source checkout has one sitting next to the package. It is the
    # file the number lives in, so it is right the moment you pull - whereas installed metadata
    # is frozen at `pip install` time: an editable install made at 0.2.0 keeps reporting 0.2.0
    # through every later pull, which is the exact confusion this whole function exists to end.
    try:
        for line in (Path(__file__).parent.parent / 'pyproject.toml').read_text(encoding='utf-8').splitlines():
            if line.startswith('version'): return line.split('=', 1)[1].strip().strip('"\'')
    except OSError: pass
    try:                                  # a real wheel: no pyproject beside it, metadata is the truth
        from importlib.metadata import PackageNotFoundError, version
        try: return version('taskuary')
        except PackageNotFoundError: pass
    except ImportError: pass
    return '0.0.0+unknown'                # never a stale number pretending to be a real one


__version__ = _version()
