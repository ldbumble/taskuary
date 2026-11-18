"""A TURN SCRIPTED FROM OUTSIDE, on every agent backend (tests/audit_scenarios.py): the stand-ins (fake_claude.py, fake_acp_server.py, the API
card's model) hand each prompt they get to a folder and answer what the scenario writes back - so the scenario makes the turn's tool calls
through the real /api/mcp door WHILE the turn is at work, as a model would, and every backend's turn carries the same calls and words.

FAKE_DIRECTOR=<folder>: turn k writes <k>.in (the prompt, as the backend delivered it) and waits for <k>.out (the answer). No .out within
FAKE_DIRECTOR_WAIT seconds (default 60): it answers 'Ok.' - a scenario that stalls fails on its own checks, never hangs the suite."""
import os, time
from pathlib import Path


def marker(home: str | Path) -> Path:
    return Path(home) / '.fake-director'


def folder_of() -> str:
    "Use the scenario's own home when a stranger's launch strips FAKE_DIRECTOR."
    if folder := os.environ.get('FAKE_DIRECTOR'): return folder
    home = os.environ.get('TASKUARY_HOME')
    mark = marker(home) if home else None
    return mark.read_text(encoding='utf-8').strip() if mark and mark.is_file() else ''


def read_when_ready(path: Path) -> str | None:
    try:
        return path.read_text(encoding='utf-8')
    except (FileNotFoundError, PermissionError):
        # Windows can briefly deny a read while the other process publishes the file.
        return None


def directed(prompt: str, folder: str = None) -> str | None:
    "The scripted answer to `prompt`, or None when no director is set."
    d = folder or folder_of()
    if not d: return None
    d = Path(d)
    for k in range(10_000):
        try: os.close(os.open(d / f'{k}.k', os.O_CREAT | os.O_EXCL | os.O_WRONLY))      # turn k is this one's
        except FileExistsError: continue
        (d / f'{k}.tmp').write_text(prompt, encoding='utf-8'); os.replace(d / f'{k}.tmp', d / f'{k}.in')    # ...seen only once whole
        break
    out, end = d / f'{k}.out', time.time() + float(os.environ.get('FAKE_DIRECTOR_WAIT') or 60)
    while time.time() < end:
        if (answer := read_when_ready(out)) is not None: return answer
        time.sleep(0.02)
    return 'Ok.'


def post(p: dict) -> str:
    """What the real agent's shell would run - `taskuary --reply ...` and kin - as the CLI sends it, on the session's own task and token
    (cli._post): {"path": "/api/agent/reply", "body": {...}}, task_id filled in. Every stand-in's scripted `post` (fake_claude, fake_acp_server)."""
    import json, urllib.request
    base = f"http://127.0.0.1:{os.environ.get('TASKUARY_PORT') or 7787}"
    body = {'task_id': int(os.environ.get('TASKUARY_TASK') or 0), **p.get('body', {})}
    hdr = {'Content-Type': 'application/json', 'X-Taskuary-Token': os.environ.get('TASKUARY_TOKEN') or '',
           **({'X-Taskuary-Task-Token': os.environ['TASKUARY_TASK_TOKEN']} if os.environ.get('TASKUARY_TASK_TOKEN') else {})}
    # ...`{task}` in the path is the session's own task: the MCP door is /api/mcp?task=<id> (browser/shown-on-its-turn)
    url = base + p['path'].replace('{task}', str(body['task_id']))
    try: return urllib.request.urlopen(urllib.request.Request(url, json.dumps(body).encode(), hdr), timeout=60).read().decode()
    except Exception as e: return f'failed: {e}'
