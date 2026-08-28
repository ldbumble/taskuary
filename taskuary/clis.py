"""Which AI CLIs are actually installed on this machine.

Most people arriving here already pay for one - Claude Code, Codex, Gemini CLI - and have no
separate API key at all. The setup wizard asked for a key and pointed everyone else at Settings,
which is the wrong way round: the thing they already have should be the first offer.

The flags are not decoration. A headless run with no permission flag waits forever for an
approval nobody can click, so an agent added without them looks installed and then hangs on first
use - the exact failure a wizard exists to prevent.
"""
import shutil

KNOWN = [
    {'name': 'claude', 'cmd': 'claude', 'label': 'Claude Code',
     # --dangerously-skip-permissions: headless claude otherwise blocks on approvals forever.
     # stream-json + --verbose is what lets the Board show a run as it happens.
     'args': ['-p', '--dangerously-skip-permissions', '--output-format', 'stream-json', '--verbose'],
     'resume_args': ['--resume'], 'timeout': 1500},
    {'name': 'codex', 'cmd': 'codex', 'label': 'OpenAI Codex CLI',
     'args': ['exec', '--dangerously-bypass-approvals-and-sandbox'], 'timeout': 1500},
    {'name': 'gemini', 'cmd': 'gemini', 'label': 'Gemini CLI',
     'args': ['-p', '--yolo'], 'timeout': 1500},
    {'name': 'opencode', 'cmd': 'opencode', 'label': 'OpenCode',
     'args': ['run'], 'timeout': 1500},
    {'name': 'aider', 'cmd': 'aider', 'label': 'Aider',
     'args': ['--yes-always', '--no-auto-commits', '--message'], 'timeout': 1500},
]


def preset_args(cmd: str) -> list:
    """The known CLI's headless flags, for a profile that names a cmd and nothing else. A profile
    saved as just `cmd = "claude"` used to run bare `claude -p`: no permission flag, so a
    non-interactive claude denied every tool call and a scheduled report came back as a table
    of refusals. `claude`, `C:\\...\\claude.cmd` and `claude.exe` all resolve to the same preset."""
    import os
    base = os.path.basename(str(cmd or '')).lower().rsplit('.', 1)[0]
    return next((list(k['args']) for k in KNOWN if k['cmd'] == base), [])


def detect(store=None) -> list:
    """Every known CLI found on PATH, plus anything already configured here.

    `installed` says it resolves on PATH; `configured` says Taskuary already has a profile for
    it. Neither means it WORKS - only a test run does, which is why the wizard runs one.
    """
    have = {a['Name']: a for a in (store.list_agents() if store else [])}
    out = []
    for k in KNOWN:
        # a fresh PATH is not read here: shutil.which sees the process's own, which is what the
        # agent runner will use too, so the two agree
        found = shutil.which(k['cmd'])
        if not found and k['name'] not in have: continue
        out.append({**k, 'installed': bool(found), 'path': found or '',
                    'configured': k['name'] in have})
    import json, os
    labels = {k['cmd']: k['label'] for k in KNOWN}
    for name, row in have.items():
        if any(o['name'] == name for o in out): continue
        try: prof = json.loads(row.get('Config') or '{}')
        except ValueError: prof = {}
        cmd = str(prof.get('cmd') or '')
        base = os.path.basename(cmd).lower().rsplit('.', 1)[0] if cmd else ''
        found = shutil.which(cmd) if cmd else None
        # the row is about the CLI, not the profile's nickname: 'coder' running claude is Claude
        # Code - and "already configured" said nothing about whether claude is even on this machine
        out.append({'name': name, 'cmd': cmd, 'label': labels.get(base) or cmd or name, 'profile': name,
                    'args': list(prof.get('args') or []), 'installed': bool(found), 'path': found or '', 'configured': True})
    return out
