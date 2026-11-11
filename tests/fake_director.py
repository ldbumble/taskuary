"""A TURN SCRIPTED FROM OUTSIDE, on every agent backend (tests/audit_scenarios.py): the stand-ins (fake_claude.py, fake_acp_server.py, the API
card's model) hand each prompt they get to a folder and answer what the scenario writes back - so the scenario makes the turn's tool calls
through the real /api/mcp door WHILE the turn is at work, as a model would, and every backend's turn carries the same calls and words.

FAKE_DIRECTOR=<folder>: turn k writes <k>.in (the prompt, as the backend delivered it) and waits for <k>.out (the answer). No .out within
FAKE_DIRECTOR_WAIT seconds (default 60): it answers 'Ok.' - a scenario that stalls fails on its own checks, never hangs the suite."""
import os, time
from pathlib import Path


MARK = Path(os.environ.get('TEMP') or os.environ.get('TMPDIR') or '/tmp') / 'taskuary-fake-director.txt'


def folder_of() -> str:
    "The director's folder: FAKE_DIRECTOR, else the mark the scenario leaves in TEMP - a stranger's run gets a trimmed env (terminal.STRICT_ENV)."
    return os.environ.get('FAKE_DIRECTOR') or (MARK.read_text(encoding='utf-8').strip() if MARK.is_file() else '')


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
        if out.is_file(): return out.read_text(encoding='utf-8')          # the scenario writes it whole, by a rename
        time.sleep(0.02)
    return 'Ok.'
