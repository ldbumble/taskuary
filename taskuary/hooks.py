"""The agent tells Taskuary what it is doing - through the CLI's own hooks.

A live session is a pty: the Board sees a terminal, not tool calls. Hooks fix that without touching
the agent. Claude Code and Codex fire the same event schema; each event's JSON reaches us and becomes
a worker event (workerstate.py), so a surface reads "Edit taskuary/server.py · 4s" or "the agent is stuck -
rate limit" instead of guessing from the screen. Off with the agent_hooks setting.

TWO TRANSPORTS, measured on the owner's box 2026-09-20. Claude runs a hook's command in a shell with the
network open, so its hook POSTs the event to /api/hooks/claude. Codex runs a hook's command where no
network call succeeds - curl by name, by absolute path and wrapped in cmd all failed, with the sandbox
on AND off - while writing a file succeeds every time. So Codex's hook appends the payload to a spool
file in Taskuary's home and CodexSpool tails it. Same receiver either way.

INSTALLED ONCE, AT USER SCOPE (~/.claude/settings.json, ~/.codex/hooks.json). Set-up installs them right
after installing the CLI, before any checkout exists; a session merely refreshes them and retires the
old per-checkout entries, so no event ever fires twice (a doubled Stop is a doubled wrap-up). The owner's
own CLI in the same folder is bound apart by session id (receive). Codex runs a user-scope hook only
once it is trusted inside the TUI - which a pty never can be - so the session's argv carries
--dangerously-bypass-hook-trust (clis.py); the sandbox bypass beside it already granted more.
"""
import json, os, re, subprocess, threading, time
from pathlib import Path
from loguru import logger

HOOKED = ('claude', 'codex', 'devin', 'copilot')
MARK = '/api/hooks/claude'
# THE ASK HOOK (the owner, 2026-09-28: "hook is better if it's supported" - measured: a PreToolUse hook that returns
# updatedInput.answers answers AskUserQuestion, no form drawn). Its own mark, so the event hooks above never replace
# it; its own command, whose stdout Claude reads as the decision. A stranger's session is held up to ASK_WAIT while the
# owner answers elsewhere, then let go so the form appears in the pane; the owner's own task is never held (ask). Claude's own limit on the hook is ASK_TIMEOUT.
ASK_MARK = '/api/hooks/claude/ask'
ASK_WAIT, ASK_TIMEOUT = 540, 600
# THE REASON NETWORK HOOK (reasonnet.py): before one of our sessions uses a Reason Network tool - a message to an untrusted
# teammate is refused, a trusted one noted on the task, and ask_user is the owner's approval card instead of Reason's
# pop-up. Its own mark and command, printed back like the ask hook's; held as long as an ask.
REASON_MARK, REASON_MATCH = '/api/hooks/claude/reason', 'mcp__reason-network__.*'
# THE BROWSER HOOK (browsergate.py, 2026-10-25): every shell command a session of ours runs is read before it runs, and a browser
# act that can't be undone is held for the owner's press. Its own mark and command, its stdout the decision like the ask hook's.
BROWSER_MARK, BROWSER_MATCH = '/api/hooks/claude/browser', 'Bash|PowerShell'
# Claude's events. The last five arrived 2026-09-20 and are the ones the screen could never tell apart:
# a turn that died on a wall (StopFailure: rate_limit, max_output_tokens, overloaded, billing_error...),
# the agent asking inside its own TUI (Notification agent_needs_input / idle_prompt), the permission
# decision itself (PermissionRequest), an MCP server asking (Elicitation), and the session ending.
# SessionStart names the session id before a word is said, so the binding never has to guess.
EVENTS = ('PostToolUse', 'PostToolUseFailure', 'Stop', 'UserPromptSubmit', 'Notification',
          'StopFailure', 'PermissionRequest', 'SessionStart', 'SessionEnd', 'Elicitation', 'ElicitationResult')
# Codex's, same schema (no StopFailure and no question event: a Codex stuck alive on an error is still
# the screen's to notice). Codex clamps SessionEnd and Interrupt hook timeouts to 3 s.
CODEX_EVENTS = ('UserPromptSubmit', 'PreToolUse', 'PermissionRequest', 'PostToolUse', 'Stop', 'Interrupt',
                'SessionStart', 'SessionEnd')
CODEX_MARK = os.path.join('hooks', 'codex.jsonl')       # the spool's tail, so our entries are recognisable
# DEVIN AND COPILOT, measured 2026-10-01 with probe hooks (Devin 3000.10.21, Copilot 1.0.86). Both speak Claude's schema
# and POST like Claude does. Devin reads ~/.claude/settings.json too - and REJECTS A WHOLE hooks block that names one
# event it does not know ("unknown variant `Notification`... Using the default ({})"), so Claude's entries never ran
# there: it gets its own block in its user config, with only events from its list. Copilot runs PascalCase event
# names with Claude-shaped payloads from a file of its own in ~/.copilot/hooks.
DEVIN_EVENTS = ('PostToolUse', 'PermissionRequest', 'UserPromptSubmit', 'Stop', 'SessionStart', 'SessionEnd')
# ...but NOT PermissionRequest: Copilot runs that hook FAIL-CLOSED (its log: "execution failed (fail-closed)"), so a
# Taskuary that is down would have every permission denied. And no shell: its hook shell failed our curl line with
# code 1 where Claude's ran it, so the entry names the executable and its args (Copilot's `exec`), stdin -> body.
COPILOT_EVENTS = ('PostToolUse', 'PostToolUseFailure', 'Stop', 'UserPromptSubmit', 'Notification', 'SessionStart', 'SessionEnd')
# the CLI version the events, AskUserQuestion's tool_input and Stop's last_assistant_message were validated
# against: Claude 2.1.278 and Codex 0.154.0 (2026-09-20). Below the floor the status may be incomplete:
# installed anyway, said out loud.
MIN_VERSION = (2, 0, 0)
# a SessionEnd whose reason leaves the process alive: /clear resets the conversation, resume swaps it - and Copilot's
# `complete`, which it sends at the end of every turn (measured 2026-10-01); the pane's own exit still says disconnected
SESSION_GOES_ON = ('clear', 'resume', 'complete')


def cli_version(cmd: str) -> str | None:
    """`claude --version` -> '2.1.3'; None when the CLI is not there or will not say."""
    import shutil
    path = shutil.which(cmd) or cmd
    # an npm shim (.cmd) only runs through cmd.exe; CreateProcess on it bare raised and the log said
    # "unknown version" for a claude that was right there
    argv = ['cmd', '/c', path, '--version'] if str(path).lower().endswith(('.cmd', '.bat')) else [path, '--version']
    from . import spawn
    try: out = spawn.run(argv, capture_output=True, text=True, timeout=8).stdout
    except (OSError, subprocess.SubprocessError, ValueError): return None
    m = re.search(r'(\d+)\.(\d+)\.(\d+)', str(out or ''))
    return m.group(0) if m else None


def supported(version) -> bool:
    if not version: return False
    try: return tuple(int(x) for x in str(version).split('.')[:3]) >= MIN_VERSION
    except ValueError: return False


def base_url() -> str:
    from . import config
    s = config.load()['server']
    host = s.get('host') or '127.0.0.1'
    return f"http://{'127.0.0.1' if host in ('0.0.0.0', '::', '') else host}:{s.get('port') or 7787}"


def agent_token() -> str:
    from . import config
    return str(config.load()['server'].get('agent_token') or '')


def cli_for(profile: dict) -> str | None:
    """'claude' / 'codex' for a profile whose command is that CLI, else None."""
    cmd = re.split(r'[\\/]', str((profile or {}).get('cmd') or ''))[-1].lower()
    return next((c for c in HOOKED if c in cmd), None)


def wanted(store, profile: dict) -> bool:
    """A hooked CLI, and the owner has not switched the hooks off."""
    return bool(cli_for(profile)) and store.get_setting('agent_hooks', '1') == '1'


def header_file(token: str, home: str = None) -> str:
    """The token as a header line in a file of its own, <taskuary home>/hooks/<sha>.hdr, for curl's `-H @file`. Written
    into the command, it sat in every process listing for as long as the hook ran - the ask hook for up to ten minutes,
    a stranger's permit for days - where any process of this account, a stranger's session among them, could read the
    shared agent token. The file is in Taskuary's home, which the floor refuses a stranger's session. Named by the
    token's hash, so the agent token and each stranger task's token never share one; replaced whole, so a hook firing
    while it is written never reads half."""
    import hashlib
    from . import config
    p = Path(home or config.home()) / 'hooks' / f'{hashlib.sha256(token.encode()).hexdigest()[:12]}.hdr'
    want = f'X-Taskuary-Token: {token}\n'
    try:
        if p.read_text(encoding='utf-8') == want: return p.as_posix()
    except OSError: pass
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_name(f'{p.name}.{os.getpid()}.{threading.get_ident()}.tmp')
    with os.fdopen(os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8', newline='\n') as f: f.write(want)
    os.replace(tmp, p)
    return p.as_posix()          # forward slashes: one spelling every hook shell (bash, PowerShell, cmd) passes through untouched


def token_arg(token: str, home: str = None) -> str:
    "curl's header argument for the token, quoted for a shell: the file's path, never the token itself (header_file)."
    return f' -H "@{header_file(token, home)}"' if token else ''


def command(base: str, token: str, cli: str, home: str = None) -> str:
    """Claude's hook: POST the event. curl.exe by name on Windows (bare `curl` is a PowerShell alias for
    Invoke-WebRequest there). -m 3: a hook must never hold the agent. stdin -> body. -o to the null
    device (not a shell redirect: PowerShell has no /dev/null) - a hook's stdout is read by Claude as a
    decision, and our reply is not one. `home` is Taskuary's (tests); the token rides in a file (header_file)."""
    curl, null = ('curl.exe', 'NUL') if os.name == 'nt' else ('curl', '/dev/null')
    return f'{curl} -s -m 3 -o {null} -X POST {base}/api/hooks/{cli} -H "Content-Type: application/json"{token_arg(token, home)} --data-binary @-'


def ask_command(base: str, token: str = '', home: str = None) -> str:
    """The ask hook: POST the ask and PRINT our answer (Claude reads a hook's stdout as its decision). -f prints nothing
    on an error and -m outlives the server's wait, so a failure or a timeout leaves Claude to draw its own form."""
    curl = 'curl.exe' if os.name == 'nt' else 'curl'
    return f'{curl} -s -f -m {ASK_WAIT + 30} -X POST {base}{ASK_MARK} -H "Content-Type: application/json"{token_arg(token, home)} --data-binary @-'


def reason_command(base: str, token: str = '', home: str = None) -> str:
    "The Reason Network hook: like the ask hook, its stdout is the decision; a failure prints nothing and leaves the call to Claude."
    curl = 'curl.exe' if os.name == 'nt' else 'curl'
    return f'{curl} -s -f -m {ASK_WAIT + 30} -X POST {base}{REASON_MARK} -H "Content-Type: application/json"{token_arg(token, home)} --data-binary @-'


def browser_command(base: str, token: str = '', home: str = None) -> str:
    "The browser hook: like the ask hook, its stdout is the decision; a failure prints nothing and leaves the command to Claude."
    curl = 'curl.exe' if os.name == 'nt' else 'curl'
    return f'{curl} -s -f -m {int(BROWSER_WAIT)} -X POST {base}{BROWSER_MARK} -H "Content-Type: application/json"{token_arg(token, home)} --data-binary @-'


BROWSER_WAIT = 120                  # a snapshot and one light verdict; past this curl gives up and Claude runs the command


def spool_path(home: str = None) -> str:
    """Where Codex's hooks leave their payloads: <taskuary home>/hooks/codex.jsonl."""
    if home: return os.path.join(home, CODEX_MARK)
    from . import config
    return os.path.join(str(config.home()), CODEX_MARK)


def codex_command(spool: str) -> str:
    """Codex's hook: append stdin to the spool. `findstr .` copies every non-empty line of stdin - the
    payload is one line of JSON - and needs nothing but cmd, which is exactly what ran when curl would not."""
    return f'cmd /c findstr . >> "{spool}"' if os.name == 'nt' else f'cat >> "{spool}"'


def user_wide() -> bool:
    """May THIS instance write the hooks every CLI on the machine runs? Only the owner's real one: its default data folder,
    not a demo. A demo, a test server or a second home that wrote them took every Claude event on the machine - they
    carry its URL - until the real one next launched a session (live check 2026-10-14: ~2 min of the owner's events went
    to a test server). Any other instance hands its hooks to each session it launches instead (session_hooks)."""
    from . import config
    if os.environ.get('TASKUARY_DEMO'): return False
    same = lambda a, b: os.path.normcase(os.path.realpath(str(a))) == os.path.normcase(os.path.realpath(str(b)))
    return same(config.home(), Path.home() / '.taskuary')


def session_hooks(token: str = None, base: str = None) -> dict:
    """Claude's hooks for ONE session's --settings: the events and the ask hook, for an instance that may not write them
    user-wide (user_wide). Claude ADDS a --settings file's hooks to the user's (origin.SETTINGS_HOOKS_MERGE)."""
    base, token = base or base_url(), agent_token() if token is None else token
    ev = {'type': 'command', 'command': command(base, token, 'claude'), 'timeout': 5}
    d = {e: [{'hooks': [ev]}] for e in EVENTS}
    d['PreToolUse'] = [{'matcher': 'AskUserQuestion', 'hooks': [{'type': 'command', 'command': ask_command(base, token), 'timeout': ASK_TIMEOUT}]},
                       {'matcher': REASON_MATCH, 'hooks': [{'type': 'command', 'command': reason_command(base, token), 'timeout': ASK_TIMEOUT}]},
                       {'matcher': BROWSER_MATCH, 'hooks': [{'type': 'command', 'command': browser_command(base, token), 'timeout': BROWSER_WAIT + 10}]}]
    return d


def _merge(hooks: dict, events, entry: dict, mark: str) -> None:
    """Our entry under every event, replacing only entries carrying our mark. Everything else stays."""
    for ev in events:
        lst = [g for g in (hooks.get(ev) or []) if isinstance(g, dict)
               and not any(mark in str(h.get('command') or '') for h in (g.get('hooks') or []) if isinstance(h, dict))]
        lst.append({'hooks': [entry]})                    # no matcher = every tool, every stop
        hooks[ev] = lst


def _read_json(p: Path) -> dict:
    try: cur = json.loads(p.read_text(encoding='utf-8')) if p.exists() else {}
    except (OSError, ValueError): cur = {}
    return cur if isinstance(cur, dict) else {}


def _write_json(p: Path, cur: dict) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(json.dumps(cur, indent=2) + '\n', encoding='utf-8')


def install_user(cli: str, base: str = None, token: str = None, home: str = None, cmd: str = None) -> bool:
    """Write (or refresh) our hook entries at USER scope for one CLI. True = a file changed.

    claude: ~/.claude/settings.json, entries that POST to us. codex: ~/.codex/hooks.json, entries that
    append to the spool. `home` overrides the user's home (tests). `cmd` names the CLI to read the
    version from; without it no version is read."""
    if cli not in HOOKED: return False
    if home is None and not user_wide(): return False        # not the owner's real instance: its sessions carry their own
    home = home or os.path.expanduser('~')
    th = os.path.join(home, '.taskuary') if home != os.path.expanduser('~') else None      # Taskuary's home beside a test's user home
    if cli == 'copilot': return _install_copilot(Path(home), base or base_url(), agent_token() if token is None else token, th)
    if cli == 'devin':
        # %APPDATA%\devin\config.json on Windows, ~/.config/devin/config.json elsewhere (its --help names the latter)
        roam = os.environ.get('APPDATA') if os.name == 'nt' and home == os.path.expanduser('~') else None
        p = Path(roam) / 'devin' / 'config.json' if roam else Path(home) / '.config' / 'devin' / 'config.json'
        entry = {'type': 'command', 'command': command(base or base_url(), agent_token() if token is None else token, cli, th), 'timeout': 5}
        events, mark = DEVIN_EVENTS, '/api/hooks/devin'
    elif cli == 'claude':
        p = Path(home) / '.claude' / 'settings.json'
        entry = {'type': 'command', 'command': command(base or base_url(), agent_token() if token is None else token, 'claude', home=th), 'timeout': 5}
        events, mark = EVENTS, MARK
    else:
        p = Path(home) / '.codex' / 'hooks.json'
        spool = spool_path(th)
        entry = {'type': 'command', 'command': codex_command(spool), 'timeout': 3}
        events, mark = CODEX_EVENTS, CODEX_MARK
    cur = _read_json(p)
    hooks = cur.setdefault('hooks', {})
    if not isinstance(hooks, dict): hooks = cur['hooks'] = {}
    before = json.dumps(cur, sort_keys=True)
    _merge(hooks, events, entry, mark)
    if cli == 'claude':
        ask = {'type': 'command', 'command': ask_command(base or base_url(), agent_token() if token is None else token, th), 'timeout': ASK_TIMEOUT}
        hooks['PreToolUse'] = [g for g in (hooks.get('PreToolUse') or []) if isinstance(g, dict)
                               and not any(m in str(h.get('command') or '') for m in (ASK_MARK, REASON_MARK, BROWSER_MARK)
                                           for h in (g.get('hooks') or []) if isinstance(h, dict))]
        hooks['PreToolUse'].append({'matcher': 'AskUserQuestion', 'hooks': [ask]})
        rn = reason_command(base or base_url(), agent_token() if token is None else token, th)
        hooks['PreToolUse'].append({'matcher': REASON_MATCH, 'hooks': [{**ask, 'command': rn}]})
        bw = browser_command(base or base_url(), agent_token() if token is None else token, th)
        hooks['PreToolUse'].append({'matcher': BROWSER_MATCH, 'hooks': [{'type': 'command', 'command': bw, 'timeout': BROWSER_WAIT + 10}]})
    if json.dumps(cur, sort_keys=True) == before: return False
    try: _write_json(p, cur)
    except OSError as e:
        logger.warning(f'could not write {cli} hooks to {p}: {e}'); return False
    if cmd is None: logger.info(f'{cli} hooks -> {p}'); return True
    v = cli_version(cmd)
    if supported(v): logger.info(f'{cli} hooks -> {p} ({cli} {v})')
    else: logger.warning(f'{cli} hooks -> {p} for {cli} {v or "unknown version"} - the events were validated for '
                         f'>= {".".join(map(str, MIN_VERSION))}; worker status from this session may be incomplete')
    return True


def _install_copilot(home: Path, base: str, token: str, th: str = None) -> bool:
    """Copilot's own file, wholly ours: ~/.copilot/hooks/taskuary.json (or $COPILOT_HOME/hooks). Its schema is flat - each
    event a list of entries - and `timeoutSec`."""
    curl, null = ('curl.exe', 'NUL') if os.name == 'nt' else ('curl', '/dev/null')
    args = ['-s', '-m', '3', '-o', null, '-X', 'POST', f'{base}/api/hooks/copilot', '-H', 'Content-Type: application/json',
            *(['-H', f'@{header_file(token, th)}'] if token else []), '--data-binary', '@-']      # no shell: the path is one argument
    root = Path(os.environ['COPILOT_HOME']) if os.environ.get('COPILOT_HOME') and home == Path(os.path.expanduser('~')) else home / '.copilot'
    p = root / 'hooks' / 'taskuary.json'
    want = {'version': 1, 'hooks': {ev: [{'type': 'command', 'exec': curl, 'args': args, 'timeoutSec': 5}] for ev in COPILOT_EVENTS}}
    if _read_json(p) == want: return False
    try: _write_json(p, want)
    except OSError as e:
        logger.warning(f'could not write copilot hooks to {p}: {e}'); return False
    logger.info(f'copilot hooks -> {p}'); return True


def retire_project(cwd: str) -> bool:
    """Drop OUR entries from a checkout's .claude/settings.local.json (the pre-2026-09-20 home of the
    hooks). Theirs stay. True = something was removed. With user-scope entries in place, a per-checkout
    copy would make every event fire twice."""
    p = Path(cwd) / '.claude' / 'settings.local.json'
    cur = _read_json(p)
    hooks = cur.get('hooks')
    if not isinstance(hooks, dict): return False
    before = json.dumps(cur, sort_keys=True)
    for ev in list(hooks):
        kept = [g for g in (hooks.get(ev) or []) if not (isinstance(g, dict)
                and any(MARK in str(h.get('command') or '') for h in (g.get('hooks') or []) if isinstance(h, dict)))]
        if kept: hooks[ev] = kept
        else: hooks.pop(ev)
    if not hooks: cur.pop('hooks')
    if json.dumps(cur, sort_keys=True) == before: return False
    try: _write_json(p, cur); return True
    except OSError as e:
        logger.debug(f'could not retire hooks in {p}: {e}'); return False


def install(cwd: str, base: str = None, token: str = '', cmd: str = None) -> bool:
    """The per-checkout install (cwd/.claude/settings.local.json). Kept for the road that has not moved
    to user scope; a session now calls install_user + retire_project instead."""
    base = base or base_url()
    p = Path(cwd) / '.claude' / 'settings.local.json'
    cur = _read_json(p)
    hooks = cur.setdefault('hooks', {})
    if not isinstance(hooks, dict): hooks = cur['hooks'] = {}
    before = json.dumps(cur, sort_keys=True)
    _merge(hooks, EVENTS, {'type': 'command', 'command': command(base, token, 'claude'), 'timeout': 5}, MARK)
    if json.dumps(cur, sort_keys=True) == before: return False
    try: _write_json(p, cur)
    except OSError as e:
        logger.warning(f'could not write claude hooks to {p}: {e}'); return False
    if cmd is None: logger.info(f'claude hooks -> {p}'); return True
    v = cli_version(cmd)
    if supported(v): logger.info(f'claude hooks -> {p} (claude {v})')
    else: logger.warning(f'claude hooks -> {p} for claude {v or "unknown version"} - the events were validated for '
                         f'>= {".".join(map(str, MIN_VERSION))}; worker status from this session may be incomplete')
    return True


def _describe(tool: str, inp) -> str:
    from .agents import _fmt_input
    try: what = _fmt_input(inp)
    except Exception: what = json.dumps(inp)[:200] if inp else ''
    return f'{tool} {what}'.strip() if what else tool


def _group(p: dict) -> str:
    """The id every hook of one AskUserQuestion shares: its questions themselves. Not the tool call's id - not every
    hook carries it (a PostToolUse without it named the same question differently, and an answered one stayed open);
    the same keying one question always had (request_id_for)."""
    from . import workerstate as ws
    return ws.group_key('|'.join(t for t, _ in _questions(p)))


def _questions(p: dict) -> list:
    """AskUserQuestion's questions as (text, choices) pairs, read off its tool_input."""
    out = []
    for q in (p.get('tool_input') or {}).get('questions') or []:
        text = str(q.get('question') or '').strip()
        if not text: continue
        labels = [str(o.get('label') or '') if isinstance(o, dict) else str(o) for o in (q.get('options') or [])]
        out.append((text, [l for l in labels if l.strip()]))
    return out


def _events(t, p: dict) -> None:
    """The hook as a worker event (workerstate.py). A prompt submitted is Working; a question is Input
    needed with its text; a permission is Approval needed with the action; a turn that died on a wall
    is Stalled with the error; Stop is the response ending - never a finish (PW-226) - and it clears a
    stall, because the run spoke again. Nothing here is inferred from the screen."""
    from . import workerstate as ws
    st = getattr(t, 'store', None)
    if not st or not getattr(t, 'task_id', None): return
    ev, tid, sid = str(p.get('hook_event_name') or ''), t.task_id, t.sid
    from . import background
    if not isinstance(getattr(t, 'bg', None), dict): t.bg = {}
    background.track(t.bg, p)
    def close(kinds, why):
        for r in ws.open_requests(ws.events(st, tid, sid)):
            if r['Kind'] in kinds and (r.get('Source') or 'api') != 'screen':
                ws.record(st, tid, sid, 'answered', request_id=r['RequestId'], text=why, source='hook')
    try:
        if ev == 'UserPromptSubmit':
            # ...including a turn Claude took because a background job reported. That one is marked: it is the agent
            # working again, not the owner speaking, so it must not overtake a question still open (open_requests)
            from .background import is_wake
            ws.record(st, tid, sid, 'working', text=ws.WAKE if is_wake(p.get('prompt')) else '', source='hook')
            if not is_wake(p.get('prompt')):                # ...and the owner's words are their next move after a stop (outcomes.py)
                try:
                    from . import outcomes
                    outcomes.moved_on(st, tid, p.get('prompt'))
                except Exception as e: logger.debug(f'task {tid}: the prompt was not ledgered - {e}')
        # a tool that FAILED had its permission decided too - the run went on either way - and a request left open
        # read "waiting for your approval" over an agent that kept working until its next prompt
        elif ev == 'PostToolUseFailure': close(('approval_needed',), 'decided in the pane')
        elif ev == 'PostToolUse':
            # PostToolUse fires once the tool has COMPLETED - and AskUserQuestion completes when the owner
            # has answered it in the pane. Recorded as an open request, the question said "the agent asked you
            # something" from the moment it was answered until the next prompt, while the pane plainly
            # worked on (TQ-0631, 2026-09-18: input_needed at 14:23:55, turn_end at 14:29:52, no answer
            # between). It goes on the record as what it is: asked, and answered.
            if str(p.get('tool_name') or '') == 'AskUserQuestion':
                resp = p.get('tool_response') if isinstance(p.get('tool_response'), dict) else {}
                answers = resp.get('answers') if isinstance(resp.get('answers'), dict) else {}
                g = _group(p)
                for i, (text, choices) in enumerate(_questions(p), 1):
                    rid = ws.question_id(g, i)
                    ws.record(st, tid, sid, 'input_needed', request_id=rid, text=text, choices=choices, source='hook')
                    if rid not in {e['RequestId'] for e in ws.events(st, tid, sid) if e['Kind'] == 'answered'}:
                        ws.record(st, tid, sid, 'answered', request_id=rid, text=str(answers.get(text) or 'answered in the pane'), source='hook')
            # ...and a tool that RAN had its permission. The notification's request had nothing to close it
            # once the owner clicked yes in the pane - no hook fires for that - so the card said "stopped and
            # is waiting on you" over an agent mid-search, until its next prompt.
            close(('approval_needed',), 'granted in the pane')
        elif ev == 'PermissionRequest':
            if str(p.get('tool_name') or '') == 'AskUserQuestion':
                # a QUESTION, not a permission: Claude asks leave to run the tool that asks (measured 2026-09-20),
                # so every surface read "the agent needs your approval: AskUserQuestion {json}" over a chooser of
                # two plain options, and the chat had nothing to pick from. Recorded as what it is, with its
                # choices, under the id PostToolUse closes it by once the owner has picked.
                g = _group(p)
                for i, (text, choices) in enumerate(_questions(p), 1):
                    ws.record(st, tid, sid, 'input_needed', request_id=ws.question_id(g, i), text=text, choices=choices, source='hook')
            elif getattr(t, 'mode', 'full') == 'auto': pass     # a stranger's session: the permit door (permit) owns this card
            else:
                # the decision point itself, with the tool and what it wants to do - not a sentence about it
                text = _describe(str(p.get('tool_name') or 'a tool'), p.get('tool_input'))
                ws.record(st, tid, sid, 'approval_needed', request_id=ws.request_id_for(text), text=text, source='hook')
        elif ev == 'Notification':
            kind, msg = str(p.get('notification_type') or '').lower(), str(p.get('message') or '').strip()
            if kind == 'permission_prompt' or (not kind and 'permission' in msg.lower()):
                # the generic sentence that FOLLOWS PermissionRequest's specific one, six seconds later: the
                # same stop recorded twice, and the newest won the card - "Claude needs your permission" over
                # "Edit taskuary/server.py" (measured 2026-09-20). It stands alone only when nothing else does.
                if not ws.open_requests(ws.events(st, tid, sid)):
                    text = msg or 'Claude needs your permission'
                    ws.record(st, tid, sid, 'approval_needed', request_id=ws.request_id_for(text), text=text, source='hook')
            elif kind in ('agent_needs_input', 'idle_prompt'):
                # the agent asking INSIDE its TUI - a chooser, a prompt - which no tool hook ever reports. Not the idle
                # notice a minute after a turn that left a shell running, though: Claude wakes itself when that job
                # reports, so it is waiting on its own work, not on you - and it flipped a working agent to "on you"
                # every turn (TQ-1059, 2026-10-13). A real ask (agent_needs_input) still counts.
                evs = ws.events(st, tid, sid)
                if not (kind == 'idle_prompt' and evs and ws.background_jobs(evs[-1])):
                    text = msg or 'Claude is waiting for your input'
                    ws.record(st, tid, sid, 'input_needed', request_id=ws.request_id_for(text), text=text, source='hook')
            elif kind == 'quota_auto_resume_fired': close(('stalled',), 'resumed after the limit lifted')
        elif ev == 'StopFailure':
            # THE WALL. A rate limit, a token ceiling, an overloaded API: the turn ends, the CLI sits at its
            # prompt, and on the screen that is indistinguishable from a question. Not terminal - Claude
            # can auto-resume and the owner can retry - so it is a request that stands until the run speaks.
            kind = str(p.get('error_type') or 'unknown').replace('_', ' ')
            text = f"{kind}: {str(p.get('error_message') or '').strip()}".rstrip(': ')
            ws.record(st, tid, sid, 'stalled', request_id=ws.request_id_for(text), text=text, source='hook')
        elif ev == 'Elicitation':
            text = f"{p.get('server_name') or 'an MCP server'} asks: {str(p.get('prompt') or '').strip()}"
            ws.record(st, tid, sid, 'input_needed', request_id=ws.request_id_for(text), text=text, source='hook')
        elif ev == 'ElicitationResult':
            text = f"{p.get('server_name') or 'an MCP server'} asks: {str(p.get('prompt') or '').strip()}"
            ws.record(st, tid, sid, 'answered', request_id=ws.request_id_for(text), text=str(p.get('response') or 'answered'), source='hook')
        elif ev == 'Stop':
            close(('stalled',), 'the run spoke again')
            # a CLI with no question tool (codex) asks with the marker: every line of it is a question, one group
            from . import selfclose
            said, signing = selfclose.signin_marker(str(p.get('last_assistant_message') or ''))
            said, asks = selfclose.ask_markers(said)
            ws.record(st, tid, sid, 'turn_end', text=said[:4000], source='hook')
            if signing is not None:                     # a sign-in it needs: Taskuary's to do, never the agent's (signin.py)
                from . import signin
                try: signin.needs(st, tid, sid, signing)
                except Exception as e: logger.warning(f'task {tid}: the sign-in the agent asked for was not raised - {e}')
            try:                                        # the ledger: what the owner does next after a stop (outcomes.py); never breaks a hook
                from . import advisor, ci, outcomes
                agent = getattr(t, 'agent', '') or 'agent'
                # ...and the Advisor hears of it once per stretch - unless the turn ASKED: then the ask below is the event, and a
                # stop judged here would be stale the moment the question is recorded (the review, 2026-10-12)
                if outcomes.stopped(st, tid, f'agent:{agent}', facts={'pr': bool(ci.pr_of(st, tid)), 'agent': agent}) and not asks and signing is None:
                    advisor.notice(st, 'agent.stopped', 'task', tid)
            except Exception as e: logger.debug(f'task {tid}: the stop was not ledgered - {e}')
            g = ws.group_key('|'.join(q for q, _ in asks)) if len(asks) > 1 else None
            for i, (q, choices) in enumerate(asks, 1):
                ws.record(st, tid, sid, 'input_needed', request_id=ws.question_id(g, i) if g else ws.request_id_for(q),
                          text=q, choices=choices, source='hook')
            # ...and a turn that asked only in PROSE is the model's to read, in the background - never a word list's
            if not asks and signing is None and said.strip() and not ws.open_requests(ws.events(st, tid, sid)): judge_turn(st, tid, sid, said)
            # the response ended, the WORK did not: a shell, a monitor or a subagent it left running and will be woken by
            # (background.py) - Claude's own list, else the jobs its hooks started (Copilot), else Claude's transcript.
            # Devin is not here on purpose: it does not wake for a background shell, so one left running is the owner's
            jobs = background.from_hook(p)
            if jobs is None: jobs = background.live(list(t.bg.values())) or (background.pending(p.get('transcript_path')) if 'claude' in _cli(t) else [])
            if jobs: ws.record(st, tid, sid, 'background', text=background.summary(jobs), choices=jobs, source='hook')
        elif ev == 'Interrupt': ws.record(st, tid, sid, 'turn_end', text='interrupted', source='hook')
        elif ev == 'SessionEnd':
            # the run's own ending, before the pty's EOF gets there - unless the process lives on
            if str(p.get('reason') or 'other') not in SESSION_GOES_ON:
                ws.record(st, tid, sid, 'disconnected', text=f"session ended ({p.get('reason') or 'other'})", source='hook')
    except Exception as e: logger.debug(f'worker event from hook skipped: {e}')


# DID THE TURN ASK THE OWNER? (the owner, 2026-10-11: "everything should be ai".) A question asked through the CLI's
# own tool, the [[TASKUARY-ASK]] marker or a chooser arrives as a request on its own. One asked only in the prose that
# ended the turn has no such signal, and the screen used to be read for it with a word list - "?" at a line's end,
# "should i", "do you want" - so a report closing on a rhetorical question became "asked you", and the owner's next
# note went in as its answer. The light model reads the Stop's last message instead: once per turn (cached on the
# words), on its own thread, so no hook and no button waits on it. Until it answers - or with no brain at all - the
# session is what it honestly is: parked, waiting on you.
JUDGE_SYSTEM = ('You read the last message a coding agent wrote before it stopped and handed the turn back to its owner. '
                'Decide one thing: does the agent need the owner to ANSWER something before the work can go on - a decision, '
                'a choice between options, a missing fact, a permission? A report of finished work, a rhetorical question, '
                'or an offer of optional extra help after the work is done is not that. Reply with JSON only: '
                '{"asks": true or false, "question": "the question in the agent\'s own words, one sentence; empty when asks is false"}')
JUDGE_WANT = {'type': 'object', 'properties': {'asks': {'type': 'boolean'}, 'question': {'type': 'string'}}, 'required': ['asks']}
_JUDGED, _JUDGED_MAX = {}, 256          # (sid, sha of the words) -> the question or '' - a Stop the spool replays costs nothing


def judge_turn(store, tid: int, sid: str, said: str, brain=None, wait: bool = False):
    "Read the turn's last message for a question to the owner; record it as an open request when there is one."
    import hashlib
    key = (str(sid), hashlib.sha1(said.encode('utf-8', 'replace')).hexdigest())
    def go():
        from . import workerstate as ws
        if key in _JUDGED: q = _JUDGED[key]
        else:
            try:
                from .llm import build_llm, ask_json
                b = brain or build_llm(store, job='judge')
                if not b: return
                v = ask_json(b, JUDGE_SYSTEM, f"THE AGENT'S LAST MESSAGE:\n{said[-4000:]}", want=JUDGE_WANT, need=('asks',)).data or {}
            except Exception as e: logger.debug(f'turn judge skipped for {sid}: {e}'); return
            if not isinstance(v, dict) or not isinstance(v.get('asks'), bool): return     # unreadable is no verdict, and is not cached
            q = ' '.join(str(v.get('question') or '').split())[:600] if v['asks'] else ''
            if v['asks'] and not q: q = ' '.join(said.split())[-300:]
            if len(_JUDGED) >= _JUDGED_MAX: _JUDGED.pop(next(iter(_JUDGED)))
            _JUDGED[key] = q
        if not q: return
        # ...and only while that turn is still the newest word: a prompt the owner submitted while the model read has
        # moved on past the question, and a request recorded after it would stand over the new turn
        evs = ws.events(store, tid, sid)
        if not evs or evs[-1]['Kind'] != 'turn_end' or evs[-1].get('Text') != said[:4000]: return
        ws.record(store, tid, sid, 'input_needed', request_id=ws.request_id_for(q), text=q, source='judge')
    if wait: return go()
    threading.Thread(target=go, daemon=True, name=f'turn-judge-{sid}').start()


# ...AND DID A HEADLESS TURN END SHORT? A general agent's CLI is not woken by work it left in the background, so a turn ending "I have
# the mail side - I'm waiting for the app walkthrough to finish, then I'll write the brief" was filed as its answer, and the task
# read "researcher answered · agent waiting on you" over a brief that would never come (the owner, 2026-10-21). The same judge reads
# it - the model, never a phrase list - and a turn that ended without delivering is the run FAILING, with its reason: the one state
# every surface already reads (workerstate.ended -> failed): R2's "Failed - <reason>" with Try again (funnel.run_failed). `then` ends
# the session the way a failed turn's does (general.GeneralSession.close, learn=False report=False) - conversation kept, no result filed.
ENDED_SYSTEM = ('You read the last message an agent wrote before its turn ended. Nothing will wake the agent again until its owner '
                'writes to it. Decide one thing: did it END WITHOUT DELIVERING what it was asked for, because it says it is still waiting '
                'on work of its own - something it started in the background, a sub-agent, a job still running - or promises to come '
                'back with the result later? An answer that delivers the work, a question to the owner, or a plain statement that '
                'something cannot be done is not that. Reply with JSON only: {"unfinished": true or false, "why": "what it is still '
                'waiting on, in a few plain words; empty when unfinished is false"}')
ENDED_WANT = {'type': 'object', 'properties': {'unfinished': {'type': 'boolean'}, 'why': {'type': 'string'}}, 'required': ['unfinished']}
_ENDED = {}
BACKGROUND = True          # the suite turns the read off its own thread (tests/conftest.py), as advisor.BACKGROUND; `wait` still reads


def ended_short(why: str) -> str:
    "The failure's reason, as R2's step reads it: \"Failed - It ended its turn still waiting on ...\" (funnel.run_failed), Try again under it."
    return f"it ended its turn still waiting on {why or 'work of its own'}"


def judge_ended(store, tid: int, sid: str, said: str, brain=None, wait: bool = False, then=None):
    "Read a headless turn's last message for work it left unfinished; record the run as failed, with why, when it did."
    import hashlib
    key = (str(sid), hashlib.sha1(said.encode('utf-8', 'replace')).hexdigest())
    def go():
        from . import workerstate as ws
        if key in _ENDED: why = _ENDED[key]
        else:
            try:
                from .llm import build_llm, ask_json
                b = brain or build_llm(store, job='judge')
                if not b: return
                v = ask_json(b, ENDED_SYSTEM, f"THE AGENT'S LAST MESSAGE:\n{said[-4000:]}", want=ENDED_WANT, need=('unfinished',)).data or {}
            except Exception as e: logger.debug(f'turn-end judge skipped for {sid}: {e}'); return
            if not isinstance(v, dict) or not isinstance(v.get('unfinished'), bool): return
            why = (' '.join(str(v.get('why') or '').split())[:300] or 'work of its own') if v['unfinished'] else ''
            if len(_ENDED) >= _JUDGED_MAX: _ENDED.pop(next(iter(_ENDED)))
            _ENDED[key] = why
        if not why: return
        # ...only while that turn is still the newest word, as judge_turn: the owner may have written since
        evs = [e for e in ws.events(store, tid, sid) if e['Kind'] not in ws.NOTES]
        if not evs or evs[-1]['Kind'] != 'turn_end' or evs[-1].get('Text') != said[:4000]: return
        ws.record(store, tid, sid, 'failed', text=ended_short(why), source='judge')
        if then:
            try: then()
            except Exception as e: logger.debug(f'task {tid}: the session was not ended after its short turn - {e}')
    if wait: return go()
    if BACKGROUND: threading.Thread(target=go, daemon=True, name=f'turn-end-judge-{sid}').start()


def _cli(t) -> str:
    return os.path.basename(str((getattr(t, 'argv', None) or [''])[0])).lower()


def _same_dir(a: str, b: str) -> bool:
    """Codex reports the cwd it was given, which on Windows may be the 8.3 short spelling of ours."""
    norm = lambda x: os.path.normcase(os.path.normpath(os.path.realpath(str(x or ''))))
    try: return norm(a) == norm(b)
    except OSError: return os.path.normcase(os.path.normpath(str(a or ''))) == os.path.normcase(os.path.normpath(str(b or '')))


def receive(payload: dict, cli: str) -> dict:
    """A hook fired: find the session it belongs to (same checkout, same CLI, most recently active unless
    already bound to this CLI session id) and hand its observations to the witness."""
    from . import terminal as term, witness
    cwd, sid = str(payload.get('cwd') or ''), str(payload.get('session_id') or '')
    # `t.argv` first: the assistant's conversation is registered as a session too and it is not a
    # process - no argv, no checkout - so reading argv[0] to judge it raised IndexError and took the
    # whole hook with it, costing the coding agent beside it its said-and-did (2026-09-07).
    mine = [t for t in list(term.SESSIONS.values()) if t.alive and t.task_id and getattr(t, 'argv', None)
            and cli in os.path.basename(str(t.argv[0])).lower() and _same_dir(t.cwd, cwd)]
    if not mine: return {'bound': False}
    # the pane's own id, or the one it was resumed from (Codex forks a resumed thread: terminal.open_session)
    t = next((x for x in mine if sid and sid in (getattr(x, 'ext_id', ''), getattr(x, 'resumed_from', ''))), None)
    if not t:
        # an unbound hook may claim a session only while that session is itself unbound. The hooks are
        # user-wide, so the owner's own CLI in the same folder used to be painted onto the agent's card -
        # and its Stop judged against the agent's task (audit 2026-09-02)
        free = [x for x in mine if not getattr(x, 'ext_id', '')]
        # ...and only by a session STARTING. Any event used to claim it, so another CLI already running in the folder -
        # the owner's own, or this checkout's other agents - took the pane with its next prompt or Stop and spoke for
        # the task from then on (2026-09-28: the owner's questions drawn as the agent asking). A pane's own CLI opens
        # with SessionStart; one already running never sends it. Claude panes are named at launch (terminal.
        # open_session); this is Codex's road until its rollout names the thread (witness).
        if str(payload.get('hook_event_name') or '') != 'SessionStart': return {'bound': False}
        if not free: return {'bound': False}
        t = max(free, key=lambda x: x.last); term.bind_ext(t, sid)
    if cli == 'claude':
        for n in witness.claude_notes(payload): t.witness.note(n)
        # a page the agent published is its output: keep the link (and a copy) on the task (claude_artifacts)
        if payload.get('hook_event_name') == 'PostToolUse' and payload.get('tool_name') == 'Artifact':
            from . import claude_artifacts
            res = payload.get('tool_response')
            claude_artifacts.capture(getattr(t, 'store', None), t.task_id, res if isinstance(res, dict) else None,
                                     res if isinstance(res, str) else '', by=getattr(t, 'agent', '') or 'agent')
        # ...and so is a Claude Doc it wrote with the Claude Docs connector - a different tool, a different answer (2026-10-06)
        elif payload.get('hook_event_name') == 'PostToolUse':
            from . import claude_artifacts
            if claude_artifacts.is_doc_create(payload.get('tool_name'), payload.get('tool_input')):
                claude_artifacts.capture_doc(getattr(t, 'store', None), t.task_id, payload['tool_input'], payload.get('tool_response'),
                                             by=getattr(t, 'agent', '') or 'agent')
    _events(t, payload)
    # ...and whatever Reason Network showed this agent goes on its task (reasonnet.on_hook): never a reason to fail the hook
    try:
        from . import reasonnet
        reasonnet.on_hook(getattr(t, 'store', None), t.task_id, payload)
    except Exception as e: logger.debug(f'reason network note skipped: {e}')
    # Stop is an observation like the rest: the agent finished a RESPONSE, not the task. Nothing closes
    # on it - only `taskuary --done` (selfclose.declare) or the owner ends a task (2026-09-24). The answer
    # used to carry a `closing` flag for a judge that no longer exists; nothing read it.
    return {'bound': True, 'sid': t.sid}


def _pane(payload: dict, cli: str):
    """The live pane this hook's session is BOUND to - never a free one: an ask is held only for a pane of ours."""
    from . import terminal as term
    cwd, sid = str(payload.get('cwd') or ''), str(payload.get('session_id') or '')
    return next((t for t in list(term.SESSIONS.values()) if t.alive and t.task_id and getattr(t, 'argv', None)
                 and cli in os.path.basename(str(t.argv[0])).lower() and _same_dir(t.cwd, cwd)
                 and sid and sid in (getattr(t, 'ext_id', ''), getattr(t, 'resumed_from', ''))), None)


def ask(payload: dict, wait: float = None) -> dict:
    """AskUserQuestion, before it draws its form: record the questions as one group. The owner's own task: {} at once -
    Claude draws its form and the owner answers it in the terminal. A stranger's session: HOLD while the owner answers in
    the Assistant or on the phone; answered, return the answers as the tool's input and no form is drawn. Not our
    pane, released, or out of time: {} - Claude draws its form and the terminal answers as it always did."""
    from . import workerstate as ws
    if str(payload.get('tool_name') or '') != 'AskUserQuestion': return {}
    t = _pane(payload, 'claude')            # AskUserQuestion is Claude's own tool, asked through Claude's hook
    st = getattr(t, 'store', None) if t else None
    if not t or not st: return {}
    qs, g = _questions(payload), _group(payload)
    if not qs: return {}
    rids = [ws.question_id(g, i) for i in range(1, len(qs) + 1)]
    # the questions first, then the hold: a card read between the two must never show "held" with nothing to answer
    for rid, (text, choices) in zip(rids, qs):
        ws.record(st, t.task_id, t.sid, 'input_needed', request_id=rid, text=text, choices=choices, source='hook')
    # THE OWNER'S OWN TASK IS ASKED IN ITS OWN TERMINAL (the owner, 2026-10-21: "no need to add a layer on the terminal. Just
    # show the emoji terminal stopped and that will tell the user to answer the question"). Held, the pane sat on "running
    # PreToolUse hook" looking stuck. Now Claude draws its form at once; the open request just recorded is what puts the
    # task in the waiting-on-you lane (👋 "asked you: ...") on the rail, the Board and the agent's work line, and PostToolUse
    # closes it once picked. Only a stranger's session (mode 'auto') is still held for the owner to answer outside it.
    if getattr(t, 'mode', 'full') != 'auto': return {}
    # ...and held ONLY when the page shows them. Claude sits on "running PreToolUse hook" for as long as this holds, with
    # nothing in the pane, so a hold nobody can see is the agent hung for nine minutes: a question asked again word for
    # word after it was answered (its id is the words, and that id is answered), or a card refused as another run's.
    # Not shown, not held - Claude draws its form in the pane at once.
    shown = {e['RequestId'] for e in ws.open_requests(ws.events(st, t.task_id, t.sid))}
    if not set(rids) <= shown:
        logger.info(f'task {t.task_id}: a question the page would not show was not held - the pane asks it')
        return {}
    ws.hold(t.task_id, t.sid, g, rids)
    got = ws.wait_held(g, ASK_WAIT if wait is None else wait)
    if not got: return {}
    inp = dict(payload.get('tool_input') or {})
    inp['answers'] = {text: got[rid] for rid, (text, _c) in zip(rids, qs)}
    return {'hookSpecificOutput': {'hookEventName': 'PreToolUse', 'permissionDecision': 'allow',
                                   'permissionDecisionReason': 'answered by the owner in Taskuary', 'updatedInput': inp}}


def reason(payload: dict, wait: float = None) -> dict:
    """Before one of OUR sessions uses a Reason Network tool (reasonnet.pre_tool). Not our pane, or the card off: {} - the call
    is Claude's and Reason's as it always was."""
    from . import reasonnet
    tool = str(payload.get('tool_name') or '')
    if not tool.startswith(reasonnet.TOOL): return {}
    t = _pane(payload, 'claude')            # Reason's hook is only installed for Claude (reasonnet: Claude takes its MCP, no hooks)
    st = getattr(t, 'store', None) if t else None
    if not t or not st: return {}
    return reasonnet.pre_tool(st, t.task_id, run_sid(payload, t.task_id), tool[len(reasonnet.TOOL):], payload.get('tool_input') or {}, wait)


def browser(payload: dict, brain=None) -> dict:
    """Before one of OUR sessions runs a shell command (browsergate.check): a browser act that can't be undone is refused and held
    for the owner. Not our pane, not a shell tool, nothing of agent-browser in it: {} at once - the command is Claude's."""
    from . import browsergate
    if str(payload.get('tool_name') or '') not in ('Bash', 'PowerShell'): return {}
    cmd = str((payload.get('tool_input') or {}).get('command') or '')
    if browsergate.EXE not in cmd.lower(): return {}                 # the cheap test first: this hook sees every shell command
    t = _pane(payload, 'claude')
    st = getattr(t, 'store', None) if t else None
    if not t or not st: return {}
    return browsergate.check(st, t.task_id, t.sid, cmd, brain)


def run_sid(payload: dict, tid: int) -> str:
    """The run a stranger session's hook speaks for, as workerstate keys it: Taskuary's OWN session id, never Claude's
    conversation id. Recorded under Claude's, the permit's card was discarded as another run's and the agent held for
    days with nothing to answer (task 10 live check). The pane bound to this payload, else the task's live session,
    else - a headless run, no session of ours - the CLI's id, which workerstate keeps while no live run owns the task."""
    from . import workerstate as ws
    t = _pane(payload, 'claude')            # the permit hook is Claude's (origin.session_settings)
    if t and t.task_id == tid: return str(t.sid)
    live = ws._live(tid)
    return str(live.sid) if live else str(payload.get('session_id') or '')


def permit(payload: dict, tid: int, wait: float = None, store=None) -> dict:
    """A stranger's session whose reviewer will not decide: the request is the owner's, and the agent HOLDS until they
    answer Allow or Deny - no timeout here, the hook's own 7 days is the outer edge. Released (the session ended) is a
    refusal, and so is any answer but Allow. Allow is this ONE call; it grants nothing further."""
    from . import workerstate as ws, redact
    sid, inp = run_sid(payload, tid), payload.get('tool_input')
    inp = inp if isinstance(inp, dict) else {}
    what = redact.scrub(str(inp.get('command') or inp.get('url') or inp.get('file_path') or inp))[:600]
    g = ws.group_key(f'permit:{tid}:{sid}:{time.time_ns()}')        # a new group per call, so one Allow can never cover the next
    rid = ws.question_id(g, 1)
    # the hold BEFORE the card: an answer that lands between the two would find nothing to release and the wait would never end
    ws.hold(tid, sid, g, [rid])
    try: shown = ws.record(store, tid, sid, 'approval_needed', request_id=rid, text=f"The agent wants to use {payload.get('tool_name') or 'a tool'}: {what}",
                           choices=['Allow', 'Deny'], source='hook')
    except Exception:
        with ws._HELD_LOCK: ws.HELD.pop(g, None)          # a failed card must not leak a hold nobody can release
        raise
    if not shown:
        # a card refused (another run owns the task) is a hold nobody can see or answer: the agent waited out the hook's
        # seven days on "running hook" with nothing on the page. Refused now, and the agent is told why.
        with ws._HELD_LOCK: ws.HELD.pop(g, None)
        return {'hookSpecificOutput': {'hookEventName': 'PermissionRequest', 'decision': {
            'behavior': 'deny', 'message': "Taskuary could not put this request in front of the owner (another run holds the task), so it is refused"}}}
    got = ws.wait_held(g, wait)
    # released: the card must not stay open, and a late answer must not be typed into whatever pane has the task now
    if got is None: ws.record(store, tid, sid, 'answered', request_id=rid, text='the session ended before you answered', source='hook')
    ok = bool(got) and str(got.get(rid) or '').strip().lower() == 'allow'
    dec = {'behavior': 'allow'} if ok else {'behavior': 'deny', 'message': 'the owner did not allow it' if got else
           'Taskuary closed before the owner answered' if ws.STOP.is_set() else 'the session ended before the owner answered'}
    return {'hookSpecificOutput': {'hookEventName': 'PermissionRequest', 'decision': dec}}


# ── Codex's spool: the hook appends, we tail ─────────────────────────────────────────────────────
BOM16 = b'\xff\xfe'

def decode_spool(raw: bytes) -> list:
    """The payload lines in a spool, however cmd encoded them. Under Codex, cmd's redirect wrote UTF-16
    with a byte-order mark (measured 2026-09-20); a plain shell writes UTF-8. Segments are split on the
    mark and each decoded in its own encoding, then split into lines."""
    # ...but the mark is written ONCE, at the file's start, and the tailer reads from where it left off - so every chunk after
    # the first arrived WITHOUT it, was decoded as UTF-8 with the NULs stripped, and a payload carrying one curly quote, dash
    # or bullet broke as JSON and was dropped. Codex's Stop was one: TQ-0887 sat at "agent working" over a pane that had
    # finished and asked (the owner, 2026-09-30). A segment is UTF-16 when its bytes SAY so - NULs in every other place.
    def utf16(seg: bytes) -> bytes | None:
        if len(seg) < 4: return None
        for s in (seg, seg[1:]):                      # a chunk can start one byte off the character grid
            odd = s[1::2]
            if odd and odd.count(0) > len(odd) * 0.3 and s[0::2].count(0) < len(odd) * 0.1: return s
        return None
    out = []
    for i, seg in enumerate(raw.split(BOM16)):
        if not seg: continue
        wide = seg if i > 0 else utf16(seg)
        text = wide[:len(wide) // 2 * 2].decode('utf-16-le', 'replace') if wide is not None else seg.decode('utf-8', 'replace')
        out += [l.strip() for l in text.replace('\x00', '').splitlines() if l.strip()]
    return out


class CodexSpool(threading.Thread):
    """Tail the spool and hand every payload to receive(cli='codex'). One per process."""
    def __init__(self, path: str, every: float = 0.5):
        super().__init__(daemon=True, name='codex-hooks')
        self.path, self.every, self.pos, self.stop = path, every, 0, threading.Event()

    def feed(self, raw: bytes) -> int:
        n = 0
        for line in decode_spool(raw):
            try: p = json.loads(line)
            except ValueError: continue
            if not isinstance(p, dict): continue
            try: receive(p, cli='codex'); n += 1
            except Exception as e: logger.debug(f'codex hook ignored: {e}')
        return n

    def run(self):
        while not self.stop.wait(self.every):
            try:
                if not os.path.exists(self.path): continue
                size = os.path.getsize(self.path)
                if size < self.pos: self.pos = 0                      # truncated: start over
                if size == self.pos: continue
                with open(self.path, 'rb') as f:
                    f.seek(self.pos); raw = f.read()
                # a payload mid-write ends without a newline; leave it for the next pass
                cut = max(raw.rfind(b'\n'), raw.rfind(b'\n\x00'))
                if cut < 0: continue
                self.feed(raw[:cut + 2 if raw[cut:cut + 2] == b'\n\x00' else cut + 1]); self.pos += cut + (2 if raw[cut:cut + 2] == b'\n\x00' else 1)
            except Exception as e: logger.debug(f'codex spool: {e}')


_SPOOL = None

def start_codex_spool(path: str = None) -> CodexSpool:
    """Start tailing (once). The spool is ours: it is emptied on start so yesterday's events are not replayed."""
    global _SPOOL
    if _SPOOL and _SPOOL.is_alive(): return _SPOOL
    path = path or spool_path()
    try:
        Path(path).parent.mkdir(parents=True, exist_ok=True); open(path, 'wb').close()
    except OSError as e: logger.debug(f'codex spool not reset: {e}')
    _SPOOL = CodexSpool(path); _SPOOL.start()
    return _SPOOL


def stop_codex_spool() -> None:
    global _SPOOL
    if _SPOOL: _SPOOL.stop.set(); _SPOOL = None
