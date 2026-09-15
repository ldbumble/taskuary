"""Where a CLI files its own conversation, for the ones that will not hand us the id.

Three roads to a resumable session, cheapest first: claude and copilot are TOLD theirs at launch
(agents.ASSIGN_ARGS); codex streams events into a rollout we already follow (witness.RolloutTail);
and the rest leave a file behind and say nothing. This is the third road - a table of where each
one writes, how to narrow it to THIS pane, and where the id sits inside.

The layouts come from each vendor's documentation, not from a machine that ran them: gemini and
cursor were not installed where this was written. A wrong guess costs one entry in SOURCES, and
costs the owner nothing else - no id found means the Continue button simply does not appear.
"""
import hashlib
import json
import os
import re
import threading
import time
from pathlib import Path

from loguru import logger

UUID = re.compile(r'[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}', re.I)
_ID_KEYS = ('sessionId', 'session_id', 'id', 'chatId')


def _home() -> Path: return Path.home()


def _gemini_dirs(cwd: str) -> list:
    """<project_hash> is sha256 of the project ROOT - which may be this cwd, or the git root above
    it. Try both, then fall back to every project in this home: being one directory out must not
    mean no continuity at all, and `since` still keeps us to a session opened after the pane."""
    root = _home() / '.gemini' / 'tmp'
    tried = [root / hashlib.sha256(str(p).encode()).hexdigest() / 'chats'
             for p in dict.fromkeys(_roots(cwd))]
    return [d for d in tried if d.is_dir()] or sorted(root.glob('*/chats'))


def _roots(cwd: str) -> list:
    here = Path(cwd).resolve()
    out = [here]
    for p in [here, *here.parents]:
        if (p / '.git').exists(): out.append(p); break
    return out


def _id_in_file(path: Path) -> str:
    """The session's own id, as written. A file that names none still has eight characters of it
    in its NAME (session-<ts>-<id8>.json), which is what gemini's own picker shows."""
    try: text = path.read_text(encoding='utf-8', errors='replace')[:100000]
    except OSError: return ''
    try:
        j = json.loads(text.split('\n', 1)[0] if path.suffix == '.jsonl' else text)
        named = next((str(j[k]) for k in _ID_KEYS if isinstance(j, dict) and j.get(k)), '')
        if UUID.fullmatch(named or ''): return named
    except ValueError:
        pass
    found = UUID.search(text)
    if found: return found.group(0)
    tail = path.stem.rsplit('-', 1)[-1]
    return tail if re.fullmatch(r'[0-9a-f]{8}', tail, re.I) else ''


def _id_in_path(path: Path) -> str:
    """cursor keeps one store per chat: ~/.cursor/chats/**/<chat-uuid>/store.db"""
    return next((p for p in (path.parent.name, *(x.name for x in path.parents)) if UUID.fullmatch(p)), '')


SOURCES = {
    'gemini': (_gemini_dirs, 'session-*.json*', _id_in_file),
    'cursor-agent': (lambda cwd: [_home() / '.cursor' / 'chats'], '**/store.db', _id_in_path),
}


def watches(cli: str) -> bool: return cli in SOURCES


def find(cli: str, cwd: str, since: float) -> str:
    """The id of the newest session this CLI filed AFTER `since` - '' when there is none yet."""
    source = SOURCES.get(cli)
    if not source: return ''
    dirs, pattern, read = source
    newest, at = None, since
    for d in dirs(cwd):
        try: candidates = list(Path(d).glob(pattern))
        except OSError: continue
        for f in candidates:
            try: when = f.stat().st_mtime
            except OSError: continue
            if when >= at: newest, at = f, when
    return read(newest) if newest is not None else ''


class SessionWatch(threading.Thread):
    """Wait for the file this pane is about to write, then name the pane after it. Stops with it."""

    def __init__(self, term, cli):
        super().__init__(daemon=True)
        self.t, self.cli, self.t0 = term, cli, time.time() - 3

    def run(self):
        from .terminal import bind_ext
        try:
            while self.t.alive and not getattr(self.t, 'ext_id', ''):
                bind_ext(self.t, find(self.cli, self.t.cwd, self.t0))
                time.sleep(2)
        except Exception as e:
            logger.debug(f'session file watch for {getattr(self.t, "sid", "?")} ended: {e}')
