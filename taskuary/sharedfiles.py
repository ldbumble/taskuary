"""TASKS THAT SHARE A FILE HEAR WHEN IT CHANGES (design round 6, D7: one task's agent added a "Print vendors" sheet to the board pack another
task had made; the pack's own agent rebuilt it for a new headcount and wiped the sheet, never told it was there; the research agent then said
the files "still show 212" minutes after they showed 214 - from memory, not the file).

A task's files live in its own outputs folder (outputs.folder). Plain code, no reading of meaning: at the end of each turn, the files of
ANOTHER task's folder that the turn's tool calls name are that task's files this one uses (kept on the audit, once each); and every file a
turn changed - its own, or another task's it wrote into - is said to each other live task that uses it, and to the task it belongs to, by
the one road Taskuary's words reach an agent (general.tell). What it does about it is the agent's to judge."""
import json, re

from loguru import logger

from . import outputs
from .store import task_ref

USED = 'files_used'
_THEIRS = re.compile(r'outputs[\\/]+TQ-0*(\d+)', re.I)          # Taskuary's own folder layout (outputs.folder), never words
LIVE = ('open', 'in_progress', 'waiting')


def _text(trace: list) -> str:
    "Every tool call's arguments in a turn's trace, as one text - what the turn reached for."
    return '\n'.join(json.dumps((e.get('detail') or {}).get('args'), default=str).replace('\\\\', '\\')
                     for e in trace or [] if e.get('type') == 'tool_call' and isinstance(e.get('detail'), dict))


def named(text: str, tid: int) -> dict:
    "{task id: [paths]} - the files of other tasks' folders that `text` names, each by its path in that folder."
    out = {}
    for x in {int(m) for m in _THEIRS.findall(text or '')} - {int(tid)}:
        if (ps := [r['path'] for r in outputs.listing(x) if r['path'] in text.replace('\\', '/') or r['path'].rsplit('/', 1)[-1] in text]): out[x] = ps
    return out


def users(store, x: int, path: str) -> set:
    "The tasks that used file `path` of task `x`."
    rows = store._rows(f"SELECT EntityId, Detail FROM audit WHERE EntityType='task' AND Action=?", (USED,))
    return {int(r['EntityId']) for r in rows if (d := _d(r)).get('task') == int(x) and path in (d.get('paths') or [])}


def _d(r) -> dict:
    try: return json.loads(r.get('Detail') or '{}') or {}
    except (TypeError, ValueError): return {}


def _use(store, tid: int, x: int, paths: list):
    have = {p for r in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action=?", (int(tid), USED))
            if (d := _d(r)).get('task') == int(x) for p in d.get('paths') or []}
    if (new := [p for p in paths if p not in have]): store.audit('task', int(tid), USED, 'taskuary', 'system', {'task': int(x), 'paths': new})


def turn_ended(store, tid: int, trace: list, since: float, own: list) -> list:
    """After task `tid`'s turn (begun at `since`; `own`: the files of its own it changed - outputs.keep_turn): what it used of other tasks'
    files kept, and each file it changed said to the other live tasks that use it, and to the task the file is of. -> [(task, path)] told."""
    from . import general
    told, used = [], named(_text(trace), tid)
    changed = [(int(tid), f['path']) for f in own or []]
    for x, ps in used.items():
        _use(store, tid, x, ps)
        for p in ps:
            f = outputs.resolve(x, p)
            try:
                if f and f.stat().st_mtime >= since: changed.append((x, p))
            except OSError: pass
    by = {}                                     # ...one line to each task, naming every file of its that changed
    for x, p in changed:
        for y in ({x} | users(store, x, p)) - {int(tid)}: by.setdefault(y, []).append((x, p))
    for y, fs in sorted(by.items()):
        if (store.get_task(y) or {}).get('Status') not in LIVE: continue
        said = '; '.join(f"{p.rsplit('/', 1)[-1]} ({'this task' if x == y else task_ref(x)}'s{'' if x == y else ', which you use'})" for x, p in fs)
        line = (f"{task_ref(tid)}'s agent just changed {said}. Read it again before you say what it holds, and bring up to date anything of "
                "yours made from it - or say why it needs nothing.")
        try:
            if general.tell(store, y, line, 'router'): told += [(y, p) for _, p in fs]
        except Exception as e: logger.warning(f'{task_ref(y)}: a change by {task_ref(tid)} to a file it uses was not told - {e}')
    return told
