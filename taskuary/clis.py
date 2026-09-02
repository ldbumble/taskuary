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
    {'name': 'aider', 'cmd': 'aider', 'label': 'Aider',
     'args': ['--yes-always', '--no-auto-commits', '--message'], 'timeout': 1500},
]


# Optional TOOLS a coding agent may use - not agents, so the wizard never offers them as one, and
# none is a pip package, so pyproject's extras cannot name them. Declared here so the app can say
# "installed / not installed - here is the one-liner" (the owner, 2026-08-30: browser use is an
# optional dependency for now; the side-by-side UI for agent + browser is a later decision).
TOOLS = [
    {'name': 'agent-browser', 'cmd': 'agent-browser', 'label': 'agent-browser (Vercel)', 'license': 'Apache-2.0',
     'install': 'npm install -g agent-browser', 'url': 'https://github.com/vercel-labs/agent-browser',
     'why': 'a local headless Chromium the coding agent drives from the terminal, shown live beside the session (browserview.py)',
     'status': 'available'},
]


def tools() -> list:
    """Every optional tool, with whether it resolves on PATH - the install hint is for the ones that do not."""
    return [{**t, 'installed': bool(shutil.which(t['cmd'])), 'path': shutil.which(t['cmd']) or ''} for t in TOOLS]


# The classifier is not the coder. When a CLI reads mail as the triage brain (llm.make_cli_llm) the
# bypass flags come OFF and its tools with them: the message it reads IS the prompt, and a sentence
# in it saying "run this" must find nothing to run (audit 2026-09-02). Per CLI: (flags to drop,
# flags to add). Gemini's default approval mode refuses tool calls headlessly, so dropping suffices.
READONLY = {'claude': (('--dangerously-skip-permissions',), ('--tools', '')),
            'codex': (('--dangerously-bypass-approvals-and-sandbox', '--full-auto'), ('--sandbox', 'read-only')),
            'gemini': (('--yolo',), ())}


def _base(cmd: str) -> str:
    import re
    # both separators on purpose: a Windows path in config.toml is still a claude on a Linux host's CI
    return re.split(r'[\\/]', str(cmd or ''))[-1].lower().rsplit('.', 1)[0]


def readonly_args(cmd: str, args: list) -> list:
    """`args` with the permission bypass removed and the CLI's own no-tools flags added."""
    drop, add = READONLY.get(_base(cmd), ((), ()))
    return [a for a in args if a not in drop] + list(add)


def preset_args(cmd: str) -> list:
    """The known CLI's headless flags, for a profile that names a cmd and nothing else. A profile
    saved as just `cmd = "claude"` used to run bare `claude -p`: no permission flag, so a
    non-interactive claude denied every tool call and a scheduled report came back as a table
    of refusals. `claude`, `C:\\...\\claude.cmd` and `claude.exe` all resolve to the same preset."""
    import re
    # both separators on purpose: a Windows path in config.toml is still a claude on a Linux host's CI
    base = re.split(r'[\\/]', str(cmd or ''))[-1].lower().rsplit('.', 1)[0]
    return next((list(k['args']) for k in KNOWN if k['cmd'] == base), [])


def store_app(path: str) -> bool:
    """Is this the Microsoft Store copy of the CLI?

    It is found by `where`, it prints its version when you type it, and it still cannot be
    launched from a background process: CreateProcess is refused inside the package folder, and
    the execution alias only runs for the account the package is registered to. What comes back
    is "Access is denied." and nothing else - so it has to be named BEFORE a scheduled run at 6am
    is the thing that finds out (an owner's machine, 2026-08-31).
    """
    return '\\windowsapps\\' in str(path or '').lower()


def runnable(cmd: str) -> tuple:
    """(what will actually run, is it the blocked Store copy). agents._resolve_cmd already
    prefers an ordinary install when both exist, so a Store path here means there is no other."""
    from .agents import _resolve_cmd
    try: resolved = _resolve_cmd(cmd)[0]
    except (FileNotFoundError, IndexError): return '', False
    return resolved, store_app(resolved)


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
        runs, blocked = runnable(k['cmd']) if found else ('', False)
        out.append({**k, 'installed': bool(found), 'path': found or '', 'runs': runs, 'store': blocked,
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
        runs, blocked = runnable(cmd) if found else ('', False)
        out.append({'name': name, 'cmd': cmd, 'label': labels.get(base) or cmd or name, 'profile': name,
                    'args': list(prof.get('args') or []), 'installed': bool(found), 'path': found or '',
                    'runs': runs, 'store': blocked, 'configured': True})
    return out
