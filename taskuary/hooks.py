"""The agent tells Taskuary what it is doing - through the CLI's own hooks.

A live session is a pty: the Board sees a terminal, not tool calls. Hooks fix that without touching
the agent. Claude Code and Codex fire the same event schema; each event's JSON reaches us and becomes
a worker event (workerstate.py), so a surface reads "Edit taskuary/server.py · 4s" or "coder is stuck -
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

HOOKED = ('claude', 'codex')
MARK = '/api/hooks/claude'
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
# the CLI version the events, AskUserQuestion's tool_input and Stop's last_assistant_message were validated
# against: Claude 2.1.278 and Codex 0.154.0 (2026-09-20). Below the floor the status may be incomplete:
# installed anyway, said out loud.
MIN_VERSION = (2, 0, 0)
# a SessionEnd whose reason leaves the process alive: /clear resets the conversation, resume swaps it
SESSION_GOES_ON = ('clear', 'resume')


def cli_version(cmd: str = 'claude') -> str | None:
    """`claude --version` -> '2.1.3'; None when the CLI is not there or will not say."""
    try: out = subprocess.run([cmd, '--version'], capture_output=True, text=True, timeout=5).stdout
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
    return bool(cli_for(profile)) and store.get_settings().get('agent_hooks', '1') == '1'


def command(base: str, token: str = '') -> str:
    """Claude's hook: POST the event. curl.exe by name on Windows (bare `curl` is a PowerShell alias for
    Invoke-WebRequest there). -m 3: a hook must never hold the agent. stdin -> body. -o to the null
    device (not a shell redirect: PowerShell has no /dev/null) - a hook's stdout is read by Claude as a
    decision, and our reply is not one."""
    curl, null = ('curl.exe', 'NUL') if os.name == 'nt' else ('curl', '/dev/null')
    tok = f' -H "X-Taskuary-Token: {token}"' if token else ''
    return f'{curl} -s -m 3 -o {null} -X POST {base}{MARK} -H "Content-Type: application/json"{tok} --data-binary @-'


def spool_path(home: str = None) -> str:
    """Where Codex's hooks leave their payloads: <taskuary home>/hooks/codex.jsonl."""
    if home: return os.path.join(home, CODEX_MARK)
    from . import config
    return os.path.join(str(config.home()), CODEX_MARK)


def codex_command(spool: str) -> str:
    """Codex's hook: append stdin to the spool. `findstr .` copies every non-empty line of stdin - the
    payload is one line of JSON - and needs nothing but cmd, which is exactly what ran when curl would not."""
    return f'cmd /c findstr . >> "{spool}"' if os.name == 'nt' else f'cat >> "{spool}"'


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
    home = home or os.path.expanduser('~')
    if cli == 'claude':
        p = Path(home) / '.claude' / 'settings.json'
        entry = {'type': 'command', 'command': command(base or base_url(), agent_token() if token is None else token), 'timeout': 5}
        events, mark = EVENTS, MARK
    else:
        p = Path(home) / '.codex' / 'hooks.json'
        spool = spool_path(os.path.join(home, '.taskuary') if home != os.path.expanduser('~') else None)
        entry = {'type': 'command', 'command': codex_command(spool), 'timeout': 3}
        events, mark = CODEX_EVENTS, CODEX_MARK
    cur = _read_json(p)
    hooks = cur.setdefault('hooks', {})
    if not isinstance(hooks, dict): hooks = cur['hooks'] = {}
    before = json.dumps(cur, sort_keys=True)
    _merge(hooks, events, entry, mark)
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
    _merge(hooks, EVENTS, {'type': 'command', 'command': command(base, token), 'timeout': 5}, MARK)
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


def _events(t, p: dict) -> None:
    """The hook as a worker event (workerstate.py). A prompt submitted is Working; a question is Input
    needed with its text; a permission is Approval needed with the action; a turn that died on a wall
    is Stalled with the error; Stop is the response ending - never a finish (PW-226) - and it clears a
    stall, because the run spoke again. Nothing here is inferred from the screen."""
    from . import workerstate as ws
    st = getattr(t, 'store', None)
    if not st or not getattr(t, 'task_id', None): return
    ev, tid, sid = str(p.get('hook_event_name') or ''), t.task_id, t.sid
    def close(kinds, why):
        for r in ws.open_requests(ws.events(st, tid, sid)):
            if r['Kind'] in kinds and (r.get('Source') or 'api') != 'screen':
                ws.record(st, tid, sid, 'answered', request_id=r['RequestId'], text=why, source='hook')
    try:
        if ev == 'UserPromptSubmit': ws.record(st, tid, sid, 'working', source='hook')
        elif ev == 'PostToolUse':
            # PostToolUse fires once the tool has COMPLETED - and AskUserQuestion completes when the owner
            # has answered it in the pane. Recorded as an open request, the question said "coder asked you
            # something" from the moment it was answered until the next prompt, while the pane plainly
            # worked on (TQ-0631, 2026-09-18: input_needed at 14:23:55, turn_end at 14:29:52, no answer
            # between). It goes on the record as what it is: asked, and answered.
            if str(p.get('tool_name') or '') == 'AskUserQuestion':
                resp = p.get('tool_response') if isinstance(p.get('tool_response'), dict) else {}
                answers = resp.get('answers') if isinstance(resp.get('answers'), dict) else {}
                for q in (p.get('tool_input') or {}).get('questions') or []:
                    text = str(q.get('question') or '').strip()
                    if not text: continue
                    choices = [str(o.get('label') or o) for o in (q.get('options') or []) if str(o.get('label') if isinstance(o, dict) else o).strip()]
                    rid = ws.request_id_for(text)
                    ws.record(st, tid, sid, 'input_needed', request_id=rid, text=text, choices=choices, source='hook')
                    ws.record(st, tid, sid, 'answered', request_id=rid, text=str(answers.get(text) or 'answered in the pane'), source='hook')
            # ...and a tool that RAN had its permission. The notification's request had nothing to close it
            # once the owner clicked yes in the pane - no hook fires for that - so the card said "stopped and
            # is waiting on you" over a coder mid-search, until its next prompt.
            close(('approval_needed',), 'granted in the pane')
        elif ev == 'PermissionRequest':
            # the decision point itself, with the tool and what it wants to do - not a sentence about it
            text = _describe(str(p.get('tool_name') or 'a tool'), p.get('tool_input'))
            ws.record(st, tid, sid, 'approval_needed', request_id=ws.request_id_for(text), text=text, source='hook')
        elif ev == 'Notification':
            kind, msg = str(p.get('notification_type') or '').lower(), str(p.get('message') or '').strip()
            if kind == 'permission_prompt' or (not kind and 'permission' in msg.lower()):
                text = msg or 'Claude needs your permission'
                ws.record(st, tid, sid, 'approval_needed', request_id=ws.request_id_for(text), text=text, source='hook')
            elif kind in ('agent_needs_input', 'idle_prompt'):
                # the agent asking INSIDE its TUI - a chooser, a prompt - which no tool hook ever reports
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
            ws.record(st, tid, sid, 'turn_end', text=str(p.get('last_assistant_message') or '')[:4000], source='hook')
        elif ev == 'Interrupt': ws.record(st, tid, sid, 'turn_end', text='interrupted', source='hook')
        elif ev == 'SessionEnd':
            # the run's own ending, before the pty's EOF gets there - unless the process lives on
            if str(p.get('reason') or 'other') not in SESSION_GOES_ON:
                ws.record(st, tid, sid, 'disconnected', text=f"session ended ({p.get('reason') or 'other'})", source='hook')
    except Exception as e: logger.debug(f'worker event from hook skipped: {e}')


def _same_dir(a: str, b: str) -> bool:
    """Codex reports the cwd it was given, which on Windows may be the 8.3 short spelling of ours."""
    norm = lambda x: os.path.normcase(os.path.normpath(os.path.realpath(str(x or ''))))
    try: return norm(a) == norm(b)
    except OSError: return os.path.normcase(os.path.normpath(str(a or ''))) == os.path.normcase(os.path.normpath(str(b or '')))


def receive(payload: dict, cli: str = 'claude') -> dict:
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
    t = next((x for x in mine if getattr(x, 'ext_id', '') == sid), None)
    if not t:
        # an unbound hook may claim a session only while that session is itself unbound. The hooks are
        # user-wide, so the owner's own CLI in the same folder used to be painted onto the agent's card -
        # and its Stop judged against the agent's task (audit 2026-09-02)
        free = [x for x in mine if not getattr(x, 'ext_id', '')]
        if not free: return {'bound': False}
        t = max(free, key=lambda x: x.last); term.bind_ext(t, sid)
    if cli == 'claude':
        for n in witness.claude_notes(payload): t.witness.note(n)
    _events(t, payload)
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


# ── Codex's spool: the hook appends, we tail ─────────────────────────────────────────────────────
BOM16 = b'\xff\xfe'

def decode_spool(raw: bytes) -> list:
    """The payload lines in a spool, however cmd encoded them. Under Codex, cmd's redirect wrote UTF-16
    with a byte-order mark (measured 2026-09-20); a plain shell writes UTF-8. Segments are split on the
    mark and each decoded in its own encoding, then split into lines."""
    out = []
    for i, seg in enumerate(raw.split(BOM16)):
        if not seg: continue
        text = seg.decode('utf-16-le', 'replace') if i > 0 else seg.decode('utf-8', 'replace')
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
