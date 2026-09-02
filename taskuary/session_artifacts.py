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


def coding(store, tid: int, report: str, transcript: str, actor='coder') -> dict:
    task = store.get_task(tid) or {}
    body = (f'# {task_ref(tid)} — {task.get("Title") or "Agent session"}\n\n'
            f'## Saved result\n\n{str(report or "(no compact result)").strip()}\n\n'
            f'## Full session transcript\n\n```text\n{str(transcript or "").strip()}\n```')
    return _write(store, tid, 'agent-session', body, 'coding_session', actor)


def confined(raw: str):
    """Return a stored artifact only when it stays below Taskuary's artifact directory."""
    if not raw: return None
    try:
        path, base = Path(raw).resolve(), root().resolve()
        return path if path.is_relative_to(base) and path.is_file() else None
    except (OSError, ValueError):
        return None
