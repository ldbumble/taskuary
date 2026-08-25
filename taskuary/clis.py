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
    for name, row in have.items():
        if not any(o['name'] == name for o in out):
            out.append({'name': name, 'cmd': '', 'label': name, 'args': [],
                        'installed': True, 'path': '', 'configured': True})
    return out
