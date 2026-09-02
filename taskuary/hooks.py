"""Claude Code tells Taskuary what it is doing - through Claude's own hooks, in the checkout.

A live session is a pty: the Board sees a terminal, not tool calls. Claude Code's hooks fix that
without touching the agent: a PostToolUse / Stop / UserPromptSubmit entry in the checkout's
.claude/settings.local.json pipes each event's JSON to POST /api/hooks/claude, and the Board card
reads "Edit taskuary/server.py · 4s" instead of guessing from the screen. Additive and local: the
file is the project-LOCAL settings Claude itself gitignores, existing hooks are kept, and only our
entries (marked by the endpoint path) are replaced. Off with the agent_hooks setting.
"""
import json, os
from pathlib import Path
from loguru import logger

MARK = '/api/hooks/claude'
EVENTS = ('PostToolUse', 'Stop', 'UserPromptSubmit')


def base_url() -> str:
    from . import config
    s = config.load()['server']
    host = s.get('host') or '127.0.0.1'
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::', '') else host}:{s.get('port') or 7787}"


def command(base: str, token: str = '') -> str:
    # curl.exe by name on Windows: in PowerShell (a hook shell there) bare `curl` is an alias for
    # Invoke-WebRequest. -m 3: a hook must never hold the agent. stdin -> body, as hooks feed it.
    # -o to the null device (not a shell redirect: PowerShell has no /dev/null) - a hook's stdout is
    # read by Claude as a decision, and our reply is not one
    curl, null = ('curl.exe', 'NUL') if os.name == 'nt' else ('curl', '/dev/null')
    tok = f' -H "X-Taskuary-Token: {token}"' if token else ''
    return f'{curl} -s -m 3 -o {null} -X POST {base}{MARK} -H "Content-Type: application/json"{tok} --data-binary @-'


def install(cwd: str, base: str = None, token: str = '') -> bool:
    """Write (or refresh) our three hook entries in cwd/.claude/settings.local.json. True = the file
    changed. Everything not ours is left exactly as it was."""
    base = base or base_url()
    p = Path(cwd) / '.claude' / 'settings.local.json'
    try: cur = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    except (OSError, ValueError): cur = {}
    if not isinstance(cur, dict): cur = {}
    hooks = cur.setdefault('hooks', {})
    if not isinstance(hooks, dict): hooks = cur['hooks'] = {}
    entry = {'type': 'command', 'command': command(base, token), 'timeout': 5}
    before = json.dumps(cur, sort_keys=True)
    for ev in EVENTS:
        lst = [g for g in (hooks.get(ev) or []) if isinstance(g, dict)
               and not any(MARK in str(h.get('command') or '') for h in (g.get('hooks') or []) if isinstance(h, dict))]
        lst.append({'hooks': [entry]})                    # no matcher = every tool, every stop
        hooks[ev] = lst
    if json.dumps(cur, sort_keys=True) == before: return False
    try:
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(cur, indent=2) + '\n', encoding='utf-8')
        logger.info(f'claude hooks -> {p}')
        return True
    except OSError as e:
        logger.warning(f'could not write claude hooks to {p}: {e}'); return False


def wanted(store, profile: dict) -> bool:
    """Claude Code, and the owner has not switched the hooks off."""
    import re
    cmd = re.split(r'[\\/]', str(profile.get('cmd') or ''))[-1].lower()
    return 'claude' in cmd and (store.get_settings().get('agent_hooks', '1') == '1')


def receive(payload: dict) -> dict:
    """A hook fired: find the session it belongs to (same checkout, Claude, most recently active
    unless already bound to this claude session id) and hand its observations to the witness."""
    from . import terminal as term, witness
    cwd = os.path.normcase(os.path.normpath(str(payload.get('cwd') or '')))
    sid = str(payload.get('session_id') or '')
    mine = [t for t in list(term.SESSIONS.values()) if t.alive and t.task_id and 'claude' in os.path.basename(str(t.argv[0])).lower()
            and os.path.normcase(os.path.normpath(t.cwd)) == cwd]
    if not mine: return {'bound': False}
    t = next((x for x in mine if getattr(x, 'ext_id', '') == sid), None)
    if not t:
        # an unbound hook may claim a session only while that session is itself unbound. The hooks
        # file is per CHECKOUT, so the owner's own claude in the same folder used to be painted
        # onto the agent's card - and its Stop judged against the agent's task (audit 2026-09-02)
        free = [x for x in mine if not getattr(x, 'ext_id', '')]
        if not free: return {'bound': False}
        t = max(free, key=lambda x: x.last); t.ext_id = sid
    for n in witness.claude_notes(payload): t.witness.note(n)
    # ...and the one hook that is not just an observation: Stop means the agent has finished
    # TALKING, which is the closest thing a pty ever gives us to "the run is over". Whether it
    # actually is over is selfclose's judgement, on its own thread - a hook has three seconds
    # and must never hold the agent (see selfclose.on_stop for the gates).
    closing, st = False, getattr(t, 'store', None)
    if str(payload.get('hook_event_name') or '') == 'Stop' and st:
        from . import selfclose
        closing = selfclose.mode(st) == 'auto'
        if closing: selfclose.spawn_on_stop(st, t, str(payload.get('last_assistant_message') or ''))
    return {'bound': True, 'sid': t.sid, 'closing': closing}
