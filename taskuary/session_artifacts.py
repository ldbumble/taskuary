"""Durable, human-readable records of task agent sessions."""
import re
from datetime import datetime
from pathlib import Path

from . import config
from .store import task_ref


def _safe(value: str) -> str:
    value = re.sub(r'[^A-Za-z0-9._-]+', '-', str(value or '').strip()).strip('-._')
    return (value or 'session')[:70]


def root() -> Path:
    path = config.home() / 'artifacts'
    path.mkdir(parents=True, exist_ok=True)
    return path


def _write(store, tid: int, label: str, body: str, kind: str, actor: str) -> dict:
    task = store.get_task(tid)
    if not task: raise ValueError('task not found')
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    folder = root() / str(int(tid)); folder.mkdir(parents=True, exist_ok=True)
    name = f'{task_ref(tid)}-{_safe(label)}-{stamp}.md'
    path = folder / name
    text = str(body or '').strip() + '\n'
    path.write_text(text, encoding='utf-8')
    aid = store.add_task_artifact({'TaskId': tid, 'Name': name, 'ContentType': 'text/markdown',
                                   'Size': path.stat().st_size, 'Path': str(path),
                                   'Kind': kind, 'CreatedBy': actor})
    store.audit('task_artifact', aid, 'create', actor, detail={'task_id': tid, 'kind': kind, 'chars': len(text)})
    return store.get_task_artifact(aid)


def coding(store, tid: int, report: str, transcript: str, actor='coder', final_message: str = '') -> dict:
    """Save the useful outcome, not a repaint-heavy copy of the terminal scrollback."""
    task = store.get_task(tid) or {}
    ans = answer_since(store, tid)
    body = (f'# {task_ref(tid)} — {task.get("Title") or "Agent session"}\n\n'
            + (f"## The agent's answer\n\n{ans}\n\n" if ans else '') +
            f'## Session result\n\n{str(report or "(no compact result)").strip()}\n\n'
            + (f'## Final agent response\n\n{str(final_message).strip()}\n\n'
               if str(final_message or '').strip() else ''))
    return _write(store, tid, 'agent-session', body, 'coding_session', actor)


def result(store, tid: int, text: str, actor='agent') -> dict:
    """What the agent answered on work nobody emailed in: there is no one to reply to, so the answer IS the result."""
    task = store.get_task(tid) or {}
    return _write(store, tid, 'agent-result', f'# {task_ref(tid)} — {task.get("Title") or "Agent result"}\n\n{str(text).strip()}', 'agent_result', actor)


# what a chat may put in front of the owner (selfclose.SHOW_LINE): pictures, pages and tables
SHOWN_TYPES = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.gif': 'image/gif', '.webp': 'image/webp',
               '.svg': 'image/svg+xml', '.html': 'text/html', '.htm': 'text/html', '.md': 'text/markdown', '.csv': 'text/csv'}
SHOWN_MAX = 16 * 1024 * 1024


def shown(store, tid: int, src: Path, actor='assistant') -> dict:
    """Copy a file the agent chose to show onto the task - its own copy, so the chat keeps it after the scratch folder is cleared."""
    kind = SHOWN_TYPES.get(src.suffix.lower())
    if not kind: raise ValueError(f'{src.suffix or "a file with no extension"} cannot be shown - only {" ".join(sorted(SHOWN_TYPES))}')
    if src.stat().st_size > SHOWN_MAX: raise ValueError('it is over 16 MB')
    folder = root() / str(int(tid)); folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"shown-{datetime.now().strftime('%Y%m%d-%H%M%S-%f')}-{_safe(src.stem)}{src.suffix.lower()}"
    path.write_bytes(src.read_bytes())
    aid = store.add_task_artifact({'TaskId': tid, 'Name': src.name, 'ContentType': kind, 'Size': path.stat().st_size,
                                   'Path': str(path), 'Kind': 'shown', 'CreatedBy': actor})
    store.audit('task_artifact', aid, 'create', actor, detail={'task_id': tid, 'kind': 'shown', 'type': kind})
    return store.get_task_artifact(aid)


def answer_since(store, tid: int) -> str:
    """The newest answer the agent saved since the last session record, so a run's record carries what it answered."""
    arts = store.list_task_artifacts(tid)
    last = max((str(a.get('CreatedAt') or '') for a in arts if a.get('Kind') == 'coding_session'), default='')
    ans = [a for a in arts if a.get('Kind') == 'agent_result' and str(a.get('CreatedAt') or '') >= last]
    if not ans: return ''
    path = confined(max(ans, key=lambda a: (str(a.get('CreatedAt') or ''), int(a.get('ArtifactId') or 0))).get('Path'))
    if not path: return ''
    body = path.read_text(encoding='utf-8')
    return re.sub(r'^# .*\n+', '', body, count=1).strip()


def confined(raw: str):
    """Return a stored artifact only when it stays below Taskuary's artifact directory."""
    if not raw: return None
    try:
        path, base = Path(raw).resolve(), root().resolve()
        return path if path.is_relative_to(base) and path.is_file() else None
    except (OSError, ValueError):
        return None
