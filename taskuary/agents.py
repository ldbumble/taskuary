"""Agent execution: any CLI is an agent. A profile ({cmd, args, resume_args, timeout, cwd,
cwd_map}) turns Claude Code, Codex, or your own wrapper into a Taskuary teammate: prompt
over STDIN (argv length limits are real on Windows), JSON output parsed when available
(Claude-style {result, session_id} -> resumable sessions), git diff captured around the
run so code changes are first-class, every run traced + audited.
"""
import json, os, re, shutil, subprocess, threading, time
from datetime import datetime
from pathlib import Path
from loguru import logger

from . import acp as acp_mod, redact, spawn
from .store import task_ref
from .clis import preset_args

_CLI_CHILDREN = set()
_CLI_CHILDREN_LOCK = threading.Lock()


def shutdown_cli_children():
    """Stop headless CLI calls that are still running when Taskuary shuts down.

    Normal calls remove themselves when their one-shot process exits. Keeping the live Popen
    objects here gives the application lifespan a deterministic cleanup road instead of leaving
    an invisible Claude/Codex process behind after the server is gone.
    """
    with _CLI_CHILDREN_LOCK:
        children = list(_CLI_CHILDREN)
        _CLI_CHILDREN.clear()
    for child in children:
        try:
            if child.poll() is None: child.kill()
        except Exception:
            pass
    return len(children)


def _git(cwd, *args):
    try:
        p = spawn.run(['git', '-C', cwd or os.getcwd(), *args], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=30)
        return p.stdout.strip() if p.returncode == 0 else ''
    except Exception:
        return ''


def _git_rc(cwd, *args, timeout=30):
    """(exit code, stdout+stderr) - for the git calls whose FAILURE is the information. _git()
    answers '' for both 'nothing to say' and 'refused', which is how a rejected push was filed as
    pushed (audit 2026-09-02); git also writes push output to stderr, which _git never read."""
    try:
        p = spawn.run(['git', '-C', cwd or os.getcwd(), *args], capture_output=True, text=True,
                           encoding='utf-8', errors='replace', timeout=timeout)
        return p.returncode, ((p.stdout or '') + (p.stderr or '')).strip()
    except Exception as e:
        return 1, str(e)


def parse_cli_json(stdout: str):
    """Claude-style single JSON object -> (result, session_id); plain text falls through."""
    try:
        j = json.loads((stdout or '').strip())
        return (j.get('result') or '').strip(), j.get('session_id')
    except (ValueError, AttributeError):
        return (stdout or '').strip(), None


def _fresh_path() -> str:
    """PATH as it is NOW, not as it was when Taskuary started. A process keeps the environment
    it was born with, so a CLI installed while the app was running said "command not found"
    until a restart - the one thing the error told you to do that you should not have to.
    Windows keeps the live value in the registry; elsewhere the inherited PATH is all there is."""
    if os.name != 'nt': return os.environ.get('PATH', '')
    import winreg
    parts = [os.environ.get('PATH', '')]
    for hive, key in ((winreg.HKEY_CURRENT_USER, 'Environment'),
                      (winreg.HKEY_LOCAL_MACHINE, r'SYSTEM\CurrentControlSet\Control\Session Manager\Environment')):
        try:
            with winreg.OpenKey(hive, key) as k:
                parts.append(os.path.expandvars(winreg.QueryValueEx(k, 'Path')[0]))
        except OSError:
            pass
    return os.pathsep.join(p for p in parts if p)


def _shim_target(path: str) -> list:
    r"""What an npm .CMD shim actually runs. The shim is four lines of batch around one real
    program - claude.CMD ends with "%dp0%\node_modules\@anthropic-ai\claude-code\bin\claude.exe" %* -
    and going through cmd /c to reach it is what costs us the prompt: cmd.exe owns & | < > and
    stray quotes, so the first prompt cannot be passed as an ARGUMENT and has to be TYPED into
    the TUI instead, in 160-char bites that a busy input loop drops. Spawn the target directly
    and the prompt travels as argv - atomically, or not at all. [] = could not tell, use cmd."""
    try: txt = open(path, encoding='utf-8', errors='replace').read()
    except OSError: return []
    here = os.path.dirname(path)
    found = []
    for tok in re.findall(r'"([^"]+)"', txt):
        # a batch file always writes \ - a separator on Windows, an ordinary character
        # everywhere else. Translating it means this parser can be exercised by CI on
        # Linux and macOS too, rather than only on the platform that has the bug.
        real = os.path.normpath(tok.replace('%dp0%', here).replace('%~dp0', here).replace(chr(92), os.sep))
        if os.path.isfile(real) and real.lower().endswith(('.exe', '.js')): found.append(real)
    exe = next((f for f in found if f.lower().endswith('.exe')), None)
    js = next((f for f in found if f.lower().endswith('.js')), None)
    if exe and js: return [exe, js]          # node.exe + the cli script
    if exe: return [exe]
    if js:
        node = shutil.which('node')
        return [node, js] if node else []
    return []


def _programs_copy(base: str) -> str:
    """The ordinary per-user install of a CLI that is ALSO published as a Store app - codex ships
    both. which() returns whichever comes first on PATH, and on some machines that is a stub this
    account may not execute at all."""
    root = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Programs')
    want = base.lower()
    for dirpath, dirs, files in os.walk(root):       # a missing root simply yields nothing
        for f in files:
            if f.lower() == want: return os.path.join(dirpath, f)
        if dirpath.count(os.sep) - root.count(os.sep) >= 3: dirs.clear()   # vendor/app/bin is deep enough
    return ''


def _resolve_cmd(name: str) -> list:
    """Windows can't CreateProcess a bare 'claude': npm installs it as claude.cmd, which only
    PATH-resolves via which(). Reaching THROUGH the shim beats running it under cmd /c - see
    _shim_target for why that difference decides whether a prompt arrives whole."""
    path = shutil.which(name) or shutil.which(name, path=_fresh_path())
    if not path and re.search(r'[\\/]', str(name)):
        # A saved ABSOLUTE path that has moved. codex installs itself into
        # ...\Codex\bin\<version hash>\codex.exe, so a profile pinned to one of those breaks on
        # the next update and reads as "the CLI is gone". The NAME is the durable half: ask PATH
        # again for it, which is what the owner would have done by hand.
        base = re.split(r'[\\/]', str(name))[-1]
        path = shutil.which(base) or shutil.which(base, path=_fresh_path())
        if path: logger.info(f'{name} has moved; using {path} instead')
    if not path:
        raise FileNotFoundError(f"'{name}' not found on PATH - is the CLI installed?")
    if os.name == 'nt' and path.lower().endswith(('.cmd', '.bat')):
        return _shim_target(path) or ['cmd', '/c', path]
    if os.name == 'nt' and '\\windowsapps\\' in path.lower():
        # which() walked into C:\Program Files\WindowsApps\<package>\...\codex.EXE - a Store package
        # folder, which CreateProcess is refused ([WinError 5] Access is denied). The runnable
        # thing is the execution ALIAS in the user's own WindowsApps folder; fall back to the
        # shell, which resolves aliases the way a typed command does.
        import ntpath   # a Windows path, split as one wherever this runs (CI is Linux and macOS)
        base = ntpath.basename(path)
        # An ordinary install beats either stub: the alias itself answers "Access is denied." when
        # the package is not registered for this account, and cmd only forwards that refusal.
        real = _programs_copy(base)
        if real: return [real]
        if '\\microsoft\\windowsapps\\' in path.lower(): return [path]     # the alias, and nothing better
        alias = os.path.join(os.environ.get('LOCALAPPDATA', ''), 'Microsoft', 'WindowsApps', base)
        return [alias] if os.path.exists(alias) else ['cmd', '/c', name]
    return [path]


def child_env(base: dict = None, home: str = None, windows: bool = None) -> dict:
    """The environment a CLI is entitled to expect.

    codex refuses to start without one: `Error finding codex home: Could not find home
    directory` (an owner's machine, 2026-08-31), and it is not a codex bug - a Taskuary
    launched from a service, a scheduled task, or a shortcut with a scrubbed environment does
    not always pass USERPROFILE down, and the Rust `dirs` crate has nothing else to go on.
    Python can answer the question, so it answers it instead of letting the CLI guess: HOME
    and USERPROFILE where they are missing, and CODEX_HOME - the variable codex checks FIRST,
    before it ever asks the OS - pointed at the same place its own installer would use.

    The three arguments exist so the Windows branch can be exercised from a Linux CI box
    without patching os.name out from under the interpreter - which is how the first version
    of this test managed to fail on the platform it was pretending to be.
    """
    import ntpath                    # a Windows path, split as one wherever this runs
    env = dict(os.environ if base is None else base)
    if home is None:
        try: home = str(Path.home())
        except (RuntimeError, OSError): return env      # nothing better to say than nothing
    env.setdefault('HOME', home)
    if (os.name == 'nt') if windows is None else windows:
        env.setdefault('USERPROFILE', home)
        drive, rest = ntpath.splitdrive(home)
        if drive: env.setdefault('HOMEDRIVE', drive); env.setdefault('HOMEPATH', rest)
        env.setdefault('CODEX_HOME', ntpath.join(home, '.codex'))
    else:
        env.setdefault('CODEX_HOME', os.path.join(home, '.codex'))
    return env


def _fmt_input(inp) -> str:
    """The one field a human wants to see per tool call - command, path, pattern…"""
    if not isinstance(inp, dict): return str(inp)[:140]
    for k in ('command', 'file_path', 'path', 'pattern', 'url', 'query', 'description', 'prompt'):
        if inp.get(k): return str(inp[k])[:140]
    return json.dumps(inp)[:140]


def _result_text(c) -> str:
    """A tool_result's content is a string or a list of {type: text} blocks."""
    v = c.get('content')
    if isinstance(v, list): v = ' '.join(str(b.get('text') or '') for b in v if isinstance(b, dict))
    return re.sub(r'\s*\n\s*', ' ⏎ ', str(v or '').strip())


def _live_line(j):
    """One readable console line per claude stream-json event; None = not worth showing.
    Tool RESULTS stream too (trimmed), so the console reads like the terminal you'd see
    if you ran the CLI yourself - not just the commands it fired."""
    t = j.get('type')
    if t == 'system':
        # only the real session init is news; the other system events (hooks, compaction,
        # subagent starts) repeated 'session started' forever and said nothing
        if j.get('subtype') not in (None, 'init'): return None
        m = j.get('model') or (j.get('modelInfo') or {}).get('name') or ''
        return 'session started' + (f' · model {m}' if m else '')
    if t == 'assistant':
        out = []
        for c in (j.get('message') or {}).get('content') or []:
            if c.get('type') == 'tool_use': out.append(f"→ {c.get('name')}: {_fmt_input(c.get('input'))}")
            elif c.get('type') == 'text' and (c.get('text') or '').strip(): out.append(c['text'].strip()[:300])
        return '\n'.join(out) or None
    if t == 'user':
        res = [c for c in (j.get('message') or {}).get('content') or []
               if isinstance(c, dict) and c.get('type') == 'tool_result']
        if not res: return None
        if any(c.get('is_error') for c in res): return f"✗ {_result_text(next(c for c in res if c.get('is_error')))[:300]}"
        txt = _result_text(res[0])
        return f'· {txt[:240]}' if txt else None
    return None


# the CLI's own login has lapsed - nothing in Taskuary can renew it, only the user at a terminal can
_SIGNED_OUT = re.compile(r'OAuth session expired|Failed to authenticate|not logged in|Not logged in|please (?:run )?[`\']?(?:claude )?/?login|codex login|401 Unauthorized', re.I)
_LOGIN_HOW = {'claude': "run `claude` and type `/login`", 'copilot': "run `copilot` and type `/login`",
              'codex': "run `codex login`", 'cursor': "run `cursor-agent login`",
              'gemini': "run `gemini` once and finish Google's sign-in",
              'qwen': "run `qwen` and use `/auth` to configure your model provider",
              'opencode': "run `opencode` and use `/connect` to configure your model provider",
              'kimi': "run `kimi` and use `/login` to configure Kimi or Moonshot",
              'muse': "run `muse` once and finish the browser sign-in at dev.meta.ai",
              'devin': "run `devin auth login` and finish the browser sign-in"}
# Provider/plan exhaustion is different from an agent failing the work. Only this availability
# class is safe to hand to another configured agent automatically: a compile error should remain
# with the agent that owns it, while "session limit; resets at 11:50" should not strand the task.
_UNAVAILABLE = re.compile(
    r'session limit|usage limit|rate limit|quota|capacity|temporarily unavailable|service unavailable|'
    r'too many requests|resource exhausted|try again (?:at|after|later)|resets? (?:at|in)', re.I)

def signed_out_msg(name: str, why: str, cmd: str = '') -> str:
    """Taskuary opens the CLI's own setup itself now (clisetup.py), so this stops sending people away.

    The name that arrives here is the PROFILE's - every install ships one called `coder` - so the
    CLI is read off the command it runs, which is the rule cliinstall.recipe_for exists for. Told
    the profile name, _LOGIN_HOW.get('coder') missed every time and always had."""
    from . import cliinstall
    cli = cliinstall.recipe_for(cmd) or name
    how = _LOGIN_HOW.get(cli, f"run `{cli}` and sign in again")
    return (f"{name} is signed out on this machine ({why.strip()[:160]}). Press Set it up on "
            f"Connections > AI CLI agents and sign in there in the pane that opens - or {how} in a terminal.")


# Windows refuses to START some installs rather than failing inside them, and says only
# "Access is denied." - which reads as an account or billing problem with the AI provider and is
# nothing of the kind: the CLI never ran. Reported on another owner's machine (2026-08-31) as
# `codex exit 1: Access is denied.` with no other output.
# A USAGE LIMIT is not a fault, and the CLI does not say so in words: it emits a rate_limit_event
# and exits 1, so the whole JSON blob landed in the error - "Report error: claude exit 1:
# {"type":"rate_limit_event","rate_limit_info":{"status":"rejected","resetsAt":1788364200,...}}" -
# on the Failing-right-now bell, all day, for something that had already reset (reported 2026-09-02).
# Nothing is broken and there is nothing to fix; there is a time to come back.
_LIMIT_WINDOW = {'five_hour': 'five-hour', 'seven_day': 'seven-day', 'opus': 'Opus'}


def rate_limited(raw) -> dict:
    """The rate_limit_info from a CLI's own event stream, if it refused for that reason."""
    for line in (raw if isinstance(raw, (list, tuple)) else str(raw or '').splitlines()):
        line = str(line).strip()
        if 'rate_limit' not in line: continue
        try: j = json.loads(line)
        except ValueError: continue
        info = (j or {}).get('rate_limit_info') or ((j or {}).get('rate_limit_info') if isinstance(j, dict) else None)
        if isinstance(info, dict) and str(info.get('status') or '').lower() in ('rejected', 'blocked', 'exceeded'):
            return info
    return {}


def rate_limit_msg(name: str, info: dict) -> str:
    """What the owner needs: which allowance, when it comes back, and that nothing is broken."""
    window = _LIMIT_WINDOW.get(str(info.get('rateLimitType') or ''), str(info.get('rateLimitType') or '')).strip()
    when = info.get('resetsAt') or ((info.get('unifiedWindows') or {}).get(info.get('rateLimitType')) or {}).get('resetsAt')
    at = ''
    try:
        t = datetime.fromtimestamp(int(when))
        day = '' if t.date() == datetime.now().date() else (' tomorrow' if (t.date() - datetime.now().date()).days == 1
                                                            else t.strftime(' on %a %d %b'))
        at = f" It comes back at {t.strftime('%I:%M %p').lstrip('0')}{day}."   # %-I is not portable
    except (TypeError, ValueError, OSError, OverflowError):
        pass
    allowance = f'its {window} usage limit' if window else 'its usage limit'
    extra = ('' if str(info.get('overageStatus') or '').lower() not in ('rejected', 'disabled')
             else ' Usage beyond the plan is turned off for this account, so it waits rather than costing more.')
    return (f'{name} has reached {allowance}, so it did not run.{at} Nothing is wrong with this '
            f'report or its setup - it will run normally once the allowance resets.{extra}')


# A CLI's REASON is on stdout, with its events; stderr is where it says it is getting started.
# Reading the reason off stderr made "codex exit 1: Reading prompt from stdin..." the whole
# account of a run that had in fact been told, in JSON on stdout, that the model in
# ~/.codex/config.toml needed a newer Codex. Thirteen hours of "Agent is working" over a two-second
# failure nobody could see (the owner, TQ-0496, 2026-09-11).
_NOISE = re.compile(r'^\s*reading prompt from stdin\.*\s*$', re.I)


def _said(msg) -> str:
    """The sentence inside an error envelope. A provider's 400 reaches the owner through two
    layers of JSON-as-a-string, and what they need out of it is the one line in English."""
    text = str(msg or '').strip()
    for _ in range(3):                                # deep enough for provider-in-CLI-in-event
        if not text.startswith('{'): break
        try: j = json.loads(text)
        except ValueError: break
        if not isinstance(j, dict): break
        inner = j.get('error') if isinstance(j.get('error'), dict) else {}
        nxt = str(inner.get('message') or j.get('message') or '').strip()
        if not nxt: break
        text = nxt
    return text


def _event_error(line: str) -> str:
    """The failure one event line reports, or '' - an ordinary event is not a fault."""
    try: j = json.loads(line)
    except ValueError: return ''
    if not isinstance(j, dict): return ''
    if j.get('type') in ('error', 'turn.failed'):
        inner = j.get('error') if isinstance(j.get('error'), dict) else {}
        return _said(inner.get('message') or j.get('message'))
    item = j.get('item') if isinstance(j.get('item'), dict) else {}
    return _said(item.get('message')) if item.get('type') == 'error' else ''


def cli_failure(raw, err: str = '') -> str:
    """Why the run failed: the CLI's own newest error event, else what it put on stderr.

    The newest wins because an earlier one is usually a warning the run carried on past - codex
    grumbles about unknown model metadata and then fails on the refusal that actually stopped it.
    """
    for line in reversed(list(raw or [])):
        said = _event_error(str(line))
        if said: return said
    clean = '\n'.join(ln for ln in str(err or '').splitlines() if ln.strip() and not _NOISE.match(ln))
    return clean.strip() or '\n'.join(list(raw or [])[-5:]) or 'no output'


_DENIED = re.compile(r'access is denied|winerror 5|permission denied|operation not permitted', re.I)
_NO_HOME = re.compile(r'could not find home directory|finding codex home|HOME.{0,20}not set', re.I)


def no_home_msg(name: str) -> str:
    return (f'{name} could not find a home directory to keep its own settings and sign-in in. '
            'Taskuary now hands every CLI a HOME, USERPROFILE and CODEX_HOME, so if this persists '
            'the account running Taskuary has no profile directory at all - which happens when it '
            'runs as a Windows service or a scheduled task under SYSTEM or a managed account. Run '
            f'Taskuary as the same user who runs `{name}` in a terminal, or set CODEX_HOME '
            'explicitly for that account, then sign in once with `codex login`.')


def denied_msg(name: str, path: str, why: str) -> str:
    where = f' ({path})' if path else ''
    return (f'Windows would not start {name}{where}: "{str(why).strip()[:120]}". The CLI never ran, so '
            f'this is not a sign-in or billing problem. Usual causes, in order: {name} came from the '
            'Microsoft Store and its app-execution alias does not work for this account (install the '
            'ordinary build instead, or reinstall it for this user); antivirus or an AppLocker policy is '
            'blocking the executable; the folder the agent works in is not readable by this account. '
            f'`where {name}` shows which copy is being found - running that exact path by hand '
            'reproduces it in one line.')


def _cli_name(cmd: str) -> str:
    """Executable name for either a bare command or a Windows/POSIX path."""
    return re.split(r'[\\/]', str(cmd or ''))[-1].lower().rsplit('.', 1)[0]


# How each CLI is told WHICH conversation. `{id}` marks where the id goes; an entry without one
# takes it as the next argument. The joined form is not decoration: copilot's --resume takes an
# OPTIONAL value, which a space-separated id is not read as. Verified 2026-09-15 from each CLI's
# own --help on this machine; a CLI not named here resumes only if its profile says how.
RESUME_ARGS = {'claude': ['--resume', '{id}'], 'codex': ['resume', '{id}'], 'copilot': ['--resume={id}'],
               # gemini and cursor were read from their docs, not from a machine that ran them:
               # each files its conversation and says nothing (sessionfiles.SOURCES finds it).
               'gemini': ['--resume', '{id}'], 'qwen': ['--resume', '{id}'], 'cursor-agent': ['--resume={id}'],
               'opencode': ['--session', '{id}'], 'kimi': ['--session', '{id}']}
# ...and the CLIs that let the CALLER name a NEW conversation, which beats learning one afterwards:
# the id exists before the CLI's first byte, so a pane killed in its first second is still
# resumable and nothing has to be guessed from a working directory (hooks.py) or a log (witness).
# claude verified by round trip - assigned, resumed, and its transcript filed under the id we gave.
ASSIGN_ARGS = {'claude': ['--session-id', '{id}'], 'copilot': ['--session-id={id}'],
               'qwen': ['--session-id', '{id}']}


def _with_id(args: list, sid: str) -> list:
    out = [str(a).replace('{id}', sid) for a in args]
    return out if any('{id}' in str(a) for a in args) else out + [sid]


def resume_argv(profile: dict, sid: str) -> list:
    """How this CLI is told to pick its OWN conversation back up - empty when it cannot, which is
    the honest answer for gemini, cursor and devin until each one can also be told WHICH session it
    had. A profile's own resume_args wins: the owner configured it for a CLI we do not ship."""
    if not sid: return []
    args = profile.get('resume_args') or RESUME_ARGS.get(_cli_name(profile.get('cmd', 'claude')))
    return _with_id(list(args), sid) if args else []


def assign_argv(profile: dict, sid: str) -> list:
    """The argv tail that NAMES a new conversation - empty when this CLI names its own."""
    args = ASSIGN_ARGS.get(_cli_name(profile.get('cmd', 'claude')))
    return _with_id(list(args), sid) if (args and sid) else []


def _codex_tool(item: dict):
    """Turn a Codex JSONL item into the common visual tool name/input contract."""
    typ = item.get('type')
    if typ == 'command_execution': return 'shell', {'command': item.get('command') or ''}
    if typ == 'file_change': return 'file change', {'changes': item.get('changes') or []}
    if typ == 'mcp_tool_call':
        return item.get('tool') or item.get('name') or 'MCP tool', item.get('arguments') or item.get('args') or {}
    if typ == 'web_search': return 'web search', {'query': item.get('query') or ''}
    return None


def runs_here(profile: dict) -> bool:
    """Does this profile's command resolve to something we can start?"""
    try: return bool(_resolve_cmd((profile or {}).get('cmd') or 'claude'))
    except (FileNotFoundError, OSError): return False


def agent_row(store, name: str) -> dict | None:
    """The row a `cli:<name>` pick runs: the worker profile of that name, else the CLI CONNECTION of
    that name. adopt_installed connects every installed CLI and mints no worker for it, so codex,
    copilot and qwen sat connected while the chat's picker - which only walked profiles - offered
    claude alone (the owner, 2026-09-24: "why only claude cli? where are the rest"). A connection
    is a brain in its own right; this is the one place a pick naming one becomes something to run."""
    row = store.get_agent(name)
    if row or not name: return row
    from . import config
    from .cli_connections import with_defaults
    conn = (config.load().get('cli_connections') or {}).get(str(name))
    return {'Name': name, 'Kind': 'general', 'Runner': 'cli', 'Config': json.dumps(with_defaults(conn))} if conn else None


def connection_brains(store) -> list[tuple[str, dict]]:
    """(key, command) for each connected CLI that no worker profile already runs - the brains
    agent_row resolves. Installed or not: the pickers decide whether that matters."""
    from . import config
    from .cli_connections import with_defaults
    covered = {cli_of(json.loads(r.get('Config') or '{}'), r['Name']) for r in store.list_agents()}
    out = []
    for key, conn in (config.load().get('cli_connections') or {}).items():
        full = with_defaults(conn)
        if store.get_agent(key) or cli_of(full, key) in covered: continue
        covered.add(cli_of(full, key)); out.append((key, full))
    return out


def availability_failure(error) -> bool:
    """Can the same untouched work safely be retried on a backup provider?"""
    text = str(error or '')
    return isinstance(error, (FileNotFoundError, PermissionError)) or bool(
        _UNAVAILABLE.search(text) or _SIGNED_OUT.search(text) or _DENIED.search(text) or _NO_HOME.search(text))


def profiles(store) -> dict:
    out = {}
    for a in store.list_agents():
        try: out[a['Name']] = json.loads(a.get('Config') or '{}')
        except ValueError: out[a['Name']] = {}
    return out


def cli_of(profile: dict, fallback: str = '') -> str:
    """The executable family behind a worker profile.

    Profiles say what a worker is for; this is the separate answer to which CLI
    actually runs it. Store rows are resolved execution snapshots, so ``cmd`` is
    available here even after config.toml has moved it onto a CLI connection.
    """
    from .clis import _base
    return _base((profile or {}).get('cmd') or fallback)


def cli_agent_options(store, preferred=(), coding_only: bool = False) -> list[dict]:
    """One representative worker per CLI, labelled by the CLI rather than the profile.

    Runtime APIs still carry a worker name because its model is stored on that
    profile. Pickers, however, ask which tool runs, so five profiles backed by
    Claude must be one ``claude`` choice rather than five apparent providers.
    """
    rows = list(store.list_agents())
    if coding_only:
        # ``cli`` is the legacy Kind used by older databases for coding workers.
        rows = [r for r in rows if str(r.get('Kind') or '').lower() in ('coding', 'cli')]
    order = {str(name): i for i, name in enumerate(preferred or ()) if name}
    rows.sort(key=lambda r: (order.get(str(r.get('Name')), len(order)),
                             str(r.get('Kind') or '').lower() not in ('coding', 'cli')))
    out, seen = [], set()
    for row in rows:
        name = str(row.get('Name') or '').strip()
        if not name: continue
        try: profile = json.loads(row.get('Config') or '{}')
        except ValueError: profile = {}
        cli = cli_of(profile, name)
        if cli in seen: continue
        seen.add(cli)
        out.append({'value': name, 'label': cli, 'cli': cli,
                    'ready': runs_here(profile), 'profile': name})
    return out


# The workers Taskuary ships, besides `coder`. A profile IS an agent row and its rules document is
# the `doc` row of the same name - which is what `coder` already was, so this adds no new storage and
# no migration. `purpose` is the one line triage is shown when it picks; `kind` is deliberately never
# 'coding', because that is what the coding-specific paths key on.
DEFAULT_PROFILES = {
    # researcher and analyst split on WHOSE information it is, not on how hard the question is: the
    # first pair of purpose lines both read as "find out something", and "look into last month's
    # spend" could have gone either way (the owner, 2026-09-10: "sharpen analyst vs researcher").
    'researcher': {'kind': 'research', 'purpose': 'OUTSIDE information - the web, vendors, public filings, documents, what other '
                                                  'companies do. Reads and reports with sources; queries none of our systems'},
    'analyst':    {'kind': 'analysis', 'purpose': 'OUR OWN figures - the databases, the ledger, the bank feeds, our reports. '
                                                  'Queries them, reconciles them, explains what the numbers say'},
    'coordinator': {'kind': 'coordination', 'purpose': 'meetings, chasing people, scheduling and follow-ups'},
    'marketer':   {'kind': 'marketing', 'purpose': 'copy, positioning and campaigns - drafts, never sends'},
    'trader':     {'kind': 'markets', 'purpose': 'markets and positions - proposes, never places an order'},
}


def cli_inheritance(cfg: dict) -> dict:
    """The coding agent's CLI setup - command AND flags - for a new general profile to start from.
    Empty when no coding profile has one yet. Shared by the shipped roles and an imported skill, so a
    worker made either way is runnable and editable on the Agents page the same day."""
    have = cfg.get('agents') or {}
    base = have.get('coder') or next((p for p in have.values() if p.get('kind', 'coding') == 'coding'), None)
    if not ((base or {}).get('cmd') or (base or {}).get('provider')): return {}
    return {k: v for k, v in base.items() if k in ('provider', 'cmd', 'args', 'resume', 'resume_args', 'timeout')}


def seed_profiles(cfg: dict) -> list:
    """Add any shipped profile this install does not have yet to the CONFIG, and never touch one it
    already has. Returns the names added, so the caller knows whether to save.

    It goes in config.toml rather than straight into the database because that is what the Agents page
    reads and writes (`put_agent` saves both): a profile seeded only into the database routed work and
    seeded documents while being invisible and un-editable on the page that exists to configure it.

    Each one inherits the coding agent's whole CLI setup - command AND flags - not just its name.
    `cmd` falls back to the agent's own NAME in several places, so a profile with none would try to run
    a command called `researcher`; and a claude profile without --dangerously-skip-permissions hangs
    headless, which is exactly the trap the presets exist to avoid."""
    have = cfg.setdefault('agents', {})
    keep = cli_inheritance(cfg)
    if not keep: return []
    added = []
    for name, prof in DEFAULT_PROFILES.items():
        if name in have: continue
        have[name] = {**keep, 'kind': prof['kind'], 'purpose': prof['purpose']}
        added.append(name)
    return added


def drop_cli_clones(cfg: dict, store) -> list:
    """Remove the coding workers named after a CLI - codex, copilot, devin, opencode... - leaving
    `coder`. Returns the names dropped, so the caller knows whether to save.

    There is ONE coding role and one CODER.md; a brain is chosen per session from the CLI
    connections. An older setup minted a coding worker per installed CLI, each pointing at CODER.md
    and differing only in which CLI ran it. That minting stopped on 2026-09-14 (adopt_installed's
    docstring), but the rows it had already written stayed on the Manage profiles page - five
    "coders" for one document (the owner, 2026-09-17: "there should be one coder.md for all cli's").

    Only a row that IS such a clone goes: coding kind, named after a known CLI, using the shared
    document. A coding profile with its own name or its own rules document is the owner's and stays.
    A clone's cwd_map (repository -> checkout) is folded into coder's so no path mapping is lost."""
    from .clis import KNOWN
    from .cli_connections import cli_key
    clis = {k['name'] for k in KNOWN} | {cli_key(k['cmd']) for k in KNOWN}
    have = cfg.get('agents') or {}
    def is_clone(name, prof):
        if name == 'coder' or name not in clis: return False
        if str(prof.get('kind') or 'coding').lower() not in CODING_KINDS: return False
        return str(prof.get('rules_doc') or 'coder') == 'coder'
    rows = {a['Name']: a for a in store.list_agents(active_only=False)}
    gone = []
    for name in sorted(set(have) | set(rows)):
        prof = have.get(name)
        if prof is None:
            try: prof = json.loads(rows[name].get('Config') or '{}')
            except ValueError: prof = {}
            prof.setdefault('kind', rows[name].get('Kind') or 'coding')
        if not is_clone(name, prof): continue
        if prof.get('cwd_map') and 'coder' in have:
            have['coder'].setdefault('cwd_map', {})
            have['coder']['cwd_map'] = {**prof['cwd_map'], **have['coder']['cwd_map']}
        have.pop(name, None)
        if name in rows: store.delete_agent(name)
        gone.append(name)
    if gone and str(store.get_settings().get('default_agent') or '') in gone:
        store.set_setting('default_agent', 'coder', 'system')      # the role, which is what that setting names now
    return gone


def profile_purpose(name: str, prof: dict, kind: str = 'coding') -> str:
    return str(prof.get('purpose') or DEFAULT_PROFILES.get(name, {}).get('purpose')
               or ('writes and changes code, in a repository' if kind == 'coding' else '')).strip()


def profile_document(store, name: str, prof: dict = None) -> str:
    """The job owns the instructions; changing its CLI does not create CODEX.md."""
    row = store.get_agent(name) or {}
    if prof is None:
        try: prof = json.loads(row.get('Config') or '{}')
        except ValueError: prof = {}
    explicit = str(prof.get('rules_doc') or '').strip()
    if explicit and re.fullmatch(r'[a-z0-9][a-z0-9_-]*', explicit): return explicit
    kind = prof.get('kind') or DEFAULT_PROFILES.get(name, {}).get('kind') or row.get('Kind')
    return 'coder' if kind == 'coding' else name


def profile_template(store, name: str) -> str:
    """A shipped role, or useful starter instructions for a new named worker."""
    if not re.fullmatch(r'[a-z0-9][a-z0-9_-]*', name): return ''
    folder = Path(__file__).parent / 'templates'
    source = folder / f'{name}.md'
    if source.is_file(): return source.read_text(encoding='utf-8')
    row = store.get_agent(name)
    if not row: return ''
    try: prof = json.loads(row.get('Config') or '{}')
    except ValueError: prof = {}
    purpose = profile_purpose(name, prof, row.get('Kind') or 'coding') or 'Complete the task assigned by the owner.'
    return (folder / 'profile.md').read_text(encoding='utf-8').replace('PROFILE_NAME', name.upper()).replace('PROFILE_PURPOSE', purpose)


def ensure_profile_document(store, name: str) -> str:
    doc = profile_document(store, name)
    if not str(store.get_doc(doc) or '').strip():
        starter = profile_template(store, doc)
        if starter.strip(): store.save_doc(doc, starter, 'template')
    return doc


# One worker's purpose, on the roster line. Bounded HERE, not where it is saved: the 2000-char cap
# on the whole roster (triage.py) is a budget shared by every worker in the loop, and only the code
# assembling that shared list knows how many lines are competing for it. An imported skill's raw
# `description` can be a multi-sentence folded block (skillimport.py) that would otherwise crowd
# every other worker off the end of a prompt that just truncates.
ROSTER_PURPOSE_MAX = 200

# The kinds that mean "works a repository". `cli` is the legacy spelling older databases use.
CODING_KINDS = ('coding', 'cli')
# Work that can still be dispatched. An allowlist rather than a list of endings, so a status added
# later cannot quietly make a repair start rewriting finished tasks (the store also has `dropped`).
LIVE_STATUSES = ('open', 'in_progress')


def roster(store) -> str:
    """The workers triage may choose between: one line each, name and purpose. Same shape as the
    playbook menu (playbooks.menu) because triage validates the answer against these very lines -
    the roster is DATA the owner controls, never a vocabulary baked into the prompt.

    GENERAL roles only. A coding task has exactly one role and triage does not choose it
    (routed_role), so offering the coding profiles here is what let `copilot` - a CLI, not a
    worker - be named on TQ-0588's coding work."""
    return '\n'.join(l for l, *_ in (roster_line(store, a) for a in store.list_agents()) if l)


def roster_line(store, a: dict) -> tuple:
    """(line, reason, code) for one agent row: the EXACT line triage reads for it, or '' plus why
    there is none. roster() is assembled from this and the Docs page shows it per profile, so "does
    triage see this worker" has one implementation. It used to have two - this rule here and a count
    of `triage_enabled` in JSX - and the JSX one said "on the roster" for CODER.md, which triage can
    never choose. The router reads this ONE LINE per worker; the session it picks gets the document.

    `code` is the same answer in a word a UI can switch on, because the four of these are NOT one
    situation and a chip that called them all "not routed" said the opposite of the truth for the
    commonest: every coding task goes to CODER.md, the router simply is not what sends it there
    (the owner, 2026-09-17: "why does coder.md say not routed? it is but default for coding tasks").
    Reading the prose to tell them apart would be a second implementation of this rule.
    """
    if not a.get('Active', 1): return '', 'switched off', 'off'
    if str(a.get('Kind') or '').lower() in CODING_KINDS:
        return '', 'a coding worker - coding tasks have one role and triage does not choose it', 'coding'
    try: prof = json.loads(a.get('Config') or '{}')
    except ValueError: prof = {}
    if prof.get('triage_enabled') is False:
        return '', 'not offered to the router - "Available to triage" is off', 'not_offered'
    purpose = profile_purpose(a['Name'], prof, a.get('Kind') or 'coding')
    if not purpose: return '', 'no purpose set - triage has nothing to choose it by', 'no_purpose'
    if len(purpose) > ROSTER_PURPOSE_MAX: purpose = purpose[:ROSTER_PURPOSE_MAX - 1].rstrip() + '…'
    return f"- {a['Name']}: {purpose}", '', ''


def default_agent(store) -> str:
    """Which agent a task goes to when nobody picked one.

    Availability is deliberately NOT resolved here. A PATH probe is only a hint and can change
    while Taskuary is running; using it to rewrite this answer made ``coder`` (Claude) silently
    become Copilot. The terminal's bounded failover road tries backups after the chosen CLI
    actually refuses to start, which is the only trustworthy time to switch providers."""
    return str(store.get_settings().get('default_agent') or 'coder').strip()


def default_brain(store) -> str:
    """The CLI every worker session runs on - coding and general alike (the owner, 2026-09-16:
    "general agents use the same brain on high level like coding by default").

    Blank falls back to the CLI behind the legacy `default_agent` profile, so an install that has
    not been migrated keeps running exactly what it ran yesterday."""
    key = str(store.get_settings().get('default_brain') or '').strip()
    if key: return key
    legacy = default_agent(store)
    return cli_of(profiles(store).get(legacy) or {}, legacy)


def brain_for(store, role: str) -> str:
    """The brain that runs one role. A profile never PINS a brain: this is a setting keyed BY a
    profile, and what it names is a brain - never a model, never an effort."""
    try: over = json.loads(store.get_settings().get('profile_brains') or '{}')
    except ValueError: over = {}
    key = str(over.get(str(role or '')) or '').strip() if isinstance(over, dict) else ''
    return key or default_brain(store)


def brain_chain(store, first: str = None, cfg: dict = None) -> list:
    """The brains to try, in order: the chosen one, then the configured backups.

    A chain of BRAINS needs no dedupe. `agent_chain` had to skip candidates whose `cli_of` it had
    already seen, because a list of roles was really a list of brains and trying claude three times
    under coder/researcher/analyst is not failover. Brains are distinct by construction.

    `backup_brains=*` is the resilient default: every other configured connection, in the owner's
    own order. A CSV narrows and orders it explicitly."""
    from . import config
    cfg = config.load() if cfg is None else cfg
    known = list(cfg.get('cli_connections') or {})
    head = str(first or default_brain(store) or '').strip()
    setting = str(store.get_settings().get('backup_brains') or '').strip()
    backups = known if setting == '*' else [x.strip() for x in setting.split(',') if x.strip()]
    # `*` expands from what is configured; a CSV is the owner naming brains outright, and is taken
    # at its word - one that turns out not to start just fails over like any other.
    out = []
    for key in [head, *backups]:
        if key and key not in out: out.append(key)
    return out


def adopt_brain_setting(store) -> bool:
    """Name the brain this install is already running, once.

    While `default_brain` is blank, `brain_command` stays out of the way and the profile's own
    command still decides - so this is the line that actually moves an install onto the brain
    layer, and it moves it onto exactly what it ran yesterday. Returns whether it wrote anything."""
    if str(store.get_settings().get('default_brain') or '').strip(): return False
    key = default_brain(store)
    if not key: return False
    store.set_setting('default_brain', key, 'migration')
    return True


def brain_command(store, role: str, cfg: dict = None, want: str = None) -> dict:
    """The COMMAND a role's brain runs - cmd, args, resume flags, timeout, gears.

    `want` is the owner's own pick at the dialog and outranks everything below it.

    Empty unless a brain was CHOSEN - `want`, `default_brain`, or this role's override. Blank means the
    owner has not moved to the brain layer yet, and `brain_for` would then be guessing from the
    legacy `default_agent` profile; overriding an explicit profile command with a guess is how
    "start a session with codex" would have quietly run claude.

    Empty too when the chosen brain names no configured connection: a half-migrated install must
    still be able to start an agent at all."""
    from . import config
    from .cli_connections import COMMAND_FIELDS, with_defaults
    settings = store.get_settings()
    try: over = json.loads(settings.get('profile_brains') or '{}')
    except ValueError: over = {}
    # the owner picking a brain at the dialog outranks both the role's override and the default
    key = str(want or '').strip() \
        or (str(over.get(str(role or '')) or '').strip() if isinstance(over, dict) else '') \
        or str(settings.get('default_brain') or '').strip()
    if not key: return {}
    cfg = config.load() if cfg is None else cfg
    conn = (cfg.get('cli_connections') or {}).get(key)
    if not conn: return {}
    full = with_defaults(conn)
    return {k: full[k] for k in COMMAND_FIELDS if k in full}


def coding_role(store) -> str:
    """The one role a coding task takes. Triage does not choose it: `kind: coding` names the job,
    and the job names the worker. Reads `default_agent` while that setting is still a PROFILE name;
    step 2 of the spec splits it into a brain and this becomes the fixed 'coder'."""
    return default_agent(store)


def routed_role(store, kind: str, profile: str) -> str:
    """Which ROLE a verdict lands on - never which brain runs it.

    Coding has exactly one role and triage does not choose it, so whatever it named is discarded:
    TQ-0588 drew `copilot` and TQ-0586 drew `analyst`, and neither may reach a coding task. The
    role is still WRITTEN rather than left implied, because `Assignee` does a third job beyond
    naming a worker and seeding its document: an `agent:` prefix is what puts the row in the pipe's
    `queued` lane - "handed to coder, not started yet" (processing_unread, processing_all). An
    unstamped coding task reads as one that needs the owner.

    General takes the specialist triage named, if it names a general one that exists. Naming none
    is a real answer and leaves the task unassigned for the owner to pick at start. `kind: task`
    leaves the job on the owner's list, so no worker at all."""
    if str(kind or '') == 'coding': return coding_role(store)
    name = str(profile or '').strip()
    if str(kind or '') != 'general' or not name: return ''
    row = store.get_agent(name)
    # the two groups never mix: a coding role reaching general work means triage invented a name
    # the roster could not have offered, and an invented worker must not route anything
    return name if row and str(row.get('Kind') or '').lower() not in CODING_KINDS else ''


def repair_role_assignees(store) -> int:
    """Tasks routed to a BRAIN before roles and brains were separated. `Assignee` holds a role, so
    a coding task pointed at anything else is corrected to the coding role - TQ-0585 held
    `agent:copilot` and TQ-0586 held `agent:analyst` on coding work. A person owning a task
    outranks any routing (`mine` put them there) and general work keeps its specialist, so both are
    left alone. A second run corrects nothing.

    CLOSED work is history, not a routing decision to fix: `transcript.Agent` says copilot or devin
    actually worked those, and rewriting the stamp to `coder` would make the task claim otherwise.
    Only tasks still open can still be dispatched, so only they are corrected."""
    role, fixed = coding_role(store), 0
    # the six search blobs this used to opt out of are gone for everyone: search runs in SQL now,
    # so nothing builds a GROUP_CONCAT over the whole message table to be filtered in a browser
    for t in store.list_tasks():
        who = str(t.get('Assignee') or '')
        if str(t.get('Status') or '').lower() not in LIVE_STATUSES: continue
        if str(t.get('Kind') or '').lower() != 'coding' or not who.startswith('agent:'): continue
        if who == f'agent:{role}': continue
        store.update_task(t['TaskId'], {'Assignee': f'agent:{role}'}, 'migration')
        fixed += 1
    return fixed


def run_acp(profile: dict, prompt: str, trace, resume: str = None, cancel=None, extra_env: dict = None):
    """One headless turn over ACP. Returns (result, session_id, diff) - run_cli's own contract, so
    nothing upstream can tell which road a run took.

    Two things are better here than on the argv road, and they are the reason this exists. The
    session id is RETURNED by session/new rather than scraped out of a vendor's temp directory
    afterwards, and the agent's progress arrives as typed events rather than as text to parse.

    It fails loudly on purpose. There is no fallback to the argv road: a silent fallback would
    hide which of the two is broken, and this transport is new.
    """
    name = profile.get('cmd', 'claude')
    cmd = _resolve_cmd(name) + list(profile.get('acp') or [])
    if profile.get('model'):
        from .climodels import split_pick
        model, _ = split_pick(profile['model'])
        cmd += [profile.get('model_arg') or '--model', model]
    cwd = profile.get('cwd')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} over acp cwd={cwd or os.getcwd()}' + (f' resume={resume}' if resume else ''))
    head0 = _git(cwd, 'rev-parse', 'HEAD')
    env = child_env({**os.environ, **(extra_env or {})})

    def show(u):
        # the agent's words arrive one TOKEN per update ("Hello", "!", "Shell", "command") and are
        # returned whole as the result; traced one by one they buried the tool calls between them
        # (a copilot turn left 40 one-word trace lines, measured 2026-09-20). Tools and plans are the
        # progress worth a line.
        if u.get('sessionUpdate') == 'agent_message_chunk': return
        line = acp_mod.trace_line(u)
        if line: trace('live', name, line)

    try:
        client = acp_mod.ACPClient(cmd[0], cmd[1:], cwd=cwd, env=env,
                                   timeout=profile.get('timeout', 1200), on_update=show)
    except PermissionError as e:
        raise FileNotFoundError(denied_msg(name, cmd[0] if cmd else '', e)) from e
    with _CLI_CHILDREN_LOCK: _CLI_CHILDREN.add(client.p)
    watcher = None
    if cancel is not None:
        # A browser Cancel asks the agent to stop first; killing the process is the backstop for
        # an agent that does not honour session/cancel.
        def _cancel():
            cancel.wait()
            if cancel.is_set(): client.cancel(); client.close()
        watcher = threading.Thread(target=_cancel, daemon=True); watcher.start()
    try:
        caps = client.connect()
        if resume and caps.get('loadSession'): client.load_session(resume, cwd)
        else:
            if resume: trace('progress', 'acp', f'{name} cannot reload a session; starting a fresh one')
            client.new_session(cwd)
        stop, said = client.prompt(prompt)
        if stop and stop not in ('end_turn', 'cancelled'):
            trace('progress', 'acp', f'the turn ended early: {stop}')
        diff = ''
        if cwd:
            head1 = _git(cwd, 'rev-parse', 'HEAD')
            if head1 and head1 != head0: diff = _git(cwd, 'diff', f'{head0}..{head1}')
            unc = _git(cwd, 'diff', 'HEAD')
            if unc: diff = '\n'.join(x for x in (diff, unc) if x).strip()
        return said, client.session_id, (diff[:150000] or None)
    finally:
        with _CLI_CHILDREN_LOCK: _CLI_CHILDREN.discard(client.p)
        client.close()


def run_cli(profile: dict, prompt: str, trace, resume: str = None, cancel=None, extra_env: dict = None):
    """One headless invocation of the configured CLI, output STREAMED line by line into
    the run trace so the Board shows the agent working live. claude's stream-json events
    render as readable tool/text lines; any other CLI's plain stdout streams as-is.
    Returns (result, session_id, diff)."""
    # Whatever built this prompt, a credential in it would go to the CLI's provider and be filed
    # in the run's own trace two lines below. task_context() writes each message's BodyText in
    # verbatim, so mail is the likeliest way one arrives here. See redact.py.
    prompt = redact.scrub(prompt)
    # The ACP road, for the profiles marked for it: the general agent's tool-using runs on a CLI
    # that speaks the protocol natively. Everything else - triage, the drafter, coding sessions,
    # every pane - stays on the argv road below. See docs/acp-transport.md.
    if profile.get('acp') and profile.get('acp_ok'):
        return run_acp(profile, prompt, trace, resume=resume, cancel=cancel, extra_env=extra_env)
    name = profile.get('cmd', 'claude')
    family = _cli_name(name)
    args = list(profile.get('args') or preset_args(name) or ['-p'])
    # Codex's normal exec output is human prose with no boundary between commands, searches,
    # edits and the final answer. JSONL is an exec-only presentation flag, so add it here (not
    # to the saved profile, which is also used to open the interactive terminal TUI).
    is_codex = _cli_name(name) == 'codex' and bool(args) and args[0] in ('exec', 'e')
    if is_codex and '--json' not in args: args.append('--json')
    # Same reasoning for the trust check: codex refuses to start outside a git repo with "Not
    # inside a trusted directory and --skip-git-repo-check was not specified", and half of what
    # this app asks a CLI runs in ~/.taskuary/scratch on purpose - the classifier, the drafter,
    # STYLE.md generation - none of which is a checkout. Headlessly there is nobody to answer the
    # trust prompt, so every one of those died before the model was reached (issue #34). The flag
    # only relaxes WHERE codex may run; the sandbox flags decide what it may do.
    if is_codex and '--skip-git-repo-check' not in args: args.append('--skip-git-repo-check')
    cmd = _resolve_cmd(name) + args
    # which model works it: profile default, or a per-run override from the UI. The flag
    # name is configurable because every CLI spells it differently (claude/codex: --model).
    if profile.get('model'):
        # 'gpt-5.4@high' spells a codex model and its reasoning level in one pick (climodels)
        from .climodels import split_pick
        m, eff = split_pick(profile['model'])
        cmd += [profile.get('model_arg') or '--model', m]
        if eff: cmd += ['-c', f'model_reasoning_effort={eff}']
    # A CONVERSATION KEPT OPEN: the Assistant and the general agent name theirs (`keep_alive`), and claude's
    # stream-json input serves every turn from one process instead of starting the CLI per call (clipool).
    keep = profile.get('keep_alive')
    if keep and family == 'claude' and 'stream-json' in args and ('-p' in args or '--print' in args):
        return _run_live(profile, name, cmd, prompt, trace, keep, resume, cancel, extra_env)
    # Keep exec's existing sandbox/config flags, and resume the exact thread.
    if resume: cmd += resume_argv(profile, resume) + (['--json', '-'] if is_codex else [])
    # Kimi's current CLI does not read its prompt from stdin. --prompt is print mode
    # and requires a value; keep it out of the profile shared with the interactive pane.
    if family == 'kimi': cmd += ['--prompt', prompt]
    cwd = profile.get('cwd')
    head0 = _git(cwd, 'rev-parse', 'HEAD')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} cwd={cwd or os.getcwd()}' + (f' resume={resume}' if resume else ''))
    try:
        # A headless Assistant session can still own an embedded browser. Its session identity
        # rides here just as it does in a PTY; merge it over the real process environment so PATH,
        # login homes, and every configured CLI keep working.
        env = child_env({**os.environ, **(extra_env or {})})
        p = spawn.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding='utf-8', errors='replace', cwd=cwd, shell=False,
                             env=env)
        with _CLI_CHILDREN_LOCK: _CLI_CHILDREN.add(p)
    except PermissionError as e:
        # which() found something that cannot be executed from here. "Not installed" sent people
        # off to reinstall a CLI that was already there; the reason is in denied_msg.
        raise FileNotFoundError(denied_msg(name, cmd[0] if cmd else '', e)) from e
    timed = threading.Event()
    killer = threading.Timer(profile.get('timeout', 1200), lambda: (timed.set(), p.kill()))
    killer.start()
    # A browser Cancel closes the streaming response. Kill the CLI too; otherwise the UI says
    # stopped while an invisible agent keeps using tools in the background.
    if cancel is not None:
        def _cancel():
            cancel.wait()
            if cancel.is_set() and p.poll() is None:
                try: p.kill()
                except Exception: pass
        threading.Thread(target=_cancel, daemon=True).start()
    err_buf = []
    err_t = threading.Thread(target=lambda: err_buf.append(p.stderr.read()), daemon=True)
    err_t.start()
    # stdin feed on its own thread: writing a big prompt while the child is already
    # emitting output can deadlock both pipes otherwise
    def _feed():
        try:
            if family != 'kimi': p.stdin.write(prompt)
            p.stdin.close()
        except Exception: pass
    threading.Thread(target=_feed, daemon=True).start()
    raw, final, streamed_out, streamed_sid, open_tools = [], None, '', None, set()
    stream_error, structured_stream = None, False
    try:
        for line in p.stdout:
            line = line.rstrip('\n')
            if not line.strip(): continue
            raw.append(line)
            try: j = json.loads(line)
            except ValueError: trace('live', name, line[:400]); continue
            if isinstance(j, dict) and family == 'opencode':
                structured_stream = True
                streamed_sid = j.get('sessionID') or streamed_sid
                part = j.get('part') or {}
                if j.get('type') == 'text':
                    text = str(part.get('text') or '')
                    streamed_out += text
                    trace('progress', 'text', text)
                    trace('live', name, text[:400])
                elif j.get('type') == 'tool_use':
                    state = part.get('state') or {}
                    iid = part.get('callID') or part.get('id') or f'tool-{len(raw)}'
                    if iid not in open_tools:
                        trace('tool_call', part.get('tool') or 'tool', {'tool_call_id': iid, 'args': state.get('input') or {}})
                        open_tools.add(iid)
                    if state.get('status') in ('completed', 'error'):
                        trace('tool_result', iid, {'result': state.get('output') or state.get('error') or '',
                                                   'is_error': state.get('status') == 'error'})
                elif j.get('type') == 'error':
                    stream_error = json.dumps(j.get('error') or j, ensure_ascii=False)
                continue
            if isinstance(j, dict) and family == 'kimi':
                structured_stream = True
                if j.get('type') == 'session.resume_hint': streamed_sid = j.get('session_id') or streamed_sid
                if j.get('role') == 'assistant':
                    text = str(j.get('content') or '')
                    if text:
                        streamed_out = text
                        trace('progress', 'text', text)
                        trace('live', name, text[:400])
                    for call in j.get('tool_calls') or []:
                        fn = call.get('function') or {}
                        try: inputs = json.loads(fn.get('arguments') or '{}')
                        except (ValueError, TypeError): inputs = {'input': fn.get('arguments')}
                        trace('tool_call', fn.get('name') or 'tool', {'tool_call_id': call.get('id'), 'args': inputs})
                elif j.get('role') == 'tool':
                    trace('tool_result', j.get('tool_call_id') or 'tool', {'result': j.get('content') or ''})
                continue
            if isinstance(j, dict) and (j.get('type') == 'result' or ('result' in j and 'type' not in j)):
                final = j; continue
            # Preserve the CLI's structured work for visual clients. The existing readable
            # `live` line remains for Board traces and the terminal renderer.
            if isinstance(j, dict) and j.get('type') == 'assistant':
                for c in (j.get('message') or {}).get('content') or []:
                    if c.get('type') == 'tool_use':
                        trace('tool_call', c.get('name') or 'tool', {
                            'tool_call_id': c.get('id') or f'tool-{len(raw)}', 'args': c.get('input') or {}})
                    elif c.get('type') == 'text' and str(c.get('text') or '').strip():
                        trace('progress', 'text', str(c['text']).strip())
            elif isinstance(j, dict) and j.get('type') == 'user':
                for c in (j.get('message') or {}).get('content') or []:
                    if isinstance(c, dict) and c.get('type') == 'tool_result':
                        trace('tool_result', c.get('tool_use_id') or 'tool', {
                            'result': _result_text(c), 'is_error': bool(c.get('is_error'))})
            # Codex `exec --json` speaks item lifecycle events instead of Claude content blocks.
            # Normalize both into one stream so assistant-ui does not care which CLI is logged in.
            if isinstance(j, dict) and j.get('type') == 'thread.started':
                streamed_sid = j.get('thread_id') or streamed_sid
            if isinstance(j, dict) and j.get('type') in ('item.started', 'item.updated', 'item.completed'):
                item = j.get('item') or {}
                iid = item.get('id') or f"item-{len(raw)}"
                tool = _codex_tool(item)
                if tool and iid not in open_tools:
                    trace('tool_call', tool[0], {'tool_call_id': iid, 'args': tool[1]})
                    open_tools.add(iid)
                if tool and j.get('type') == 'item.completed':
                    result = item.get('aggregated_output') or item.get('output') or item.get('status') or ''
                    failed = item.get('status') == 'failed' or item.get('exit_code') not in (None, 0)
                    trace('tool_result', iid, {'result': str(result), 'is_error': failed})
                if item.get('type') in ('agent_message', 'reasoning') and str(item.get('text') or '').strip():
                    text = str(item['text']).strip()
                    trace('progress', item.get('type'), text)
                    if item.get('type') == 'agent_message': streamed_out = text
            shown = _live_line(j) if isinstance(j, dict) else None
            if shown: trace('live', name, shown)
        p.wait()
    finally:
        killer.cancel()
        with _CLI_CHILDREN_LOCK: _CLI_CHILDREN.discard(p)
    err_t.join(5)      # the exit code can land before the stderr reader has appended - 'boom' read as 'no output' on a fast CI box
    if p.returncode != 0:
        if cancel is not None and cancel.is_set(): raise RuntimeError('cancelled')
        err = ''.join(err_buf)
        said = cli_failure(raw, err)
        why = (f'timed out after {profile.get("timeout", 1200)}s' if timed.is_set() else said)[:500]
        # the CLASSIFYING patterns read both streams: a sign-in refusal or a Windows launch
        # refusal lands on stderr, while the reason the owner reads now comes off stdout
        hay = f'{said}\n{err}'
        limit = rate_limited(raw) or rate_limited(hay)
        if limit: raise RuntimeError(rate_limit_msg(name, limit))
        if _SIGNED_OUT.search(hay): raise RuntimeError(signed_out_msg(name, said, cmd[0] if cmd else ''))
        # a refusal to START, not a failed run: the CLI produced no output of its own and the
        # only thing on stderr is the refusal
        if _DENIED.search(hay) and not raw: raise RuntimeError(denied_msg(name, cmd[0] if cmd else '', said))
        if _NO_HOME.search(hay): raise RuntimeError(no_home_msg(_cli_name(name) or name))
        raise RuntimeError(f'{name} exit {p.returncode}: {why}')
    # OpenCode can report provider errors in JSON while its process exits successfully.
    if stream_error: raise RuntimeError(f'{name}: {redact.scrub(stream_error)[:500]}')
    if final is not None: out, sid = str(final.get('result') or '').strip(), final.get('session_id')
    elif streamed_out: out, sid = streamed_out, streamed_sid
    elif structured_stream: out, sid = '', streamed_sid
    else: out, sid = parse_cli_json('\n'.join(raw))
    trace('output', name, out[-1000:])
    diff = ''
    if head0:
        head1 = _git(cwd, 'rev-parse', 'HEAD')
        if head1 and head1 != head0: diff = _git(cwd, 'diff', f'{head0}..{head1}')
        unc = _git(cwd, 'diff', 'HEAD')
        if unc: diff = f'{diff}\n{unc}'.strip()
        if diff: trace('tool', 'code_changes', f'{len(diff.splitlines())} diff lines captured')
    return out, sid, (diff[:150000] or None)


def _run_live(profile: dict, name: str, cmd: list, prompt: str, trace, keep: str, resume, cancel, extra_env):
    """run_cli's turn on a conversation's LIVE process: the same trace events, the same errors, the same
    (result, session_id, diff) - with no checkout to diff, since neither the Assistant nor a general agent
    works in one."""
    from . import clipool
    cwd = profile.get('cwd')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} cwd={cwd or os.getcwd()} live={keep}' + (f' resume={resume}' if resume else ''))
    def on(j):
        if j.get('type') == 'assistant':
            for c in (j.get('message') or {}).get('content') or []:
                if c.get('type') == 'tool_use':
                    trace('tool_call', c.get('name') or 'tool', {'tool_call_id': c.get('id') or 'tool', 'args': c.get('input') or {}})
                elif c.get('type') == 'text' and str(c.get('text') or '').strip():
                    trace('progress', 'text', str(c['text']).strip())
        elif j.get('type') == 'user':
            for c in (j.get('message') or {}).get('content') or []:
                if isinstance(c, dict) and c.get('type') == 'tool_result':
                    trace('tool_result', c.get('tool_use_id') or 'tool', {'result': _result_text(c), 'is_error': bool(c.get('is_error'))})
        shown = _live_line(j)
        if shown: trace('live', name, shown)
    try:
        final, raw = clipool.run(keep, cmd, prompt, on, cwd=cwd, env=child_env({**os.environ, **(extra_env or {})}),
                                 resume=resume, cancel=cancel, timeout=profile.get('timeout', 1200))
    except PermissionError as e:
        raise FileNotFoundError(denied_msg(name, cmd[0] if cmd else '', e)) from e
    except RuntimeError as e:
        said = str(e)
        if said == 'cancelled': raise
        limit = rate_limited(said)
        if limit: raise RuntimeError(rate_limit_msg(name, limit))
        if _SIGNED_OUT.search(said): raise RuntimeError(signed_out_msg(name, said, cmd[0] if cmd else ''))
        raise RuntimeError(f'{name}: {said[:500]}')
    if final.get('is_error'):
        said = str(final.get('result') or final.get('subtype') or 'the CLI reported an error')
        limit = rate_limited(raw) or rate_limited(said)
        if limit: raise RuntimeError(rate_limit_msg(name, limit))
        if _SIGNED_OUT.search(said): raise RuntimeError(signed_out_msg(name, said, cmd[0] if cmd else ''))
        raise RuntimeError(f'{name}: {said[:500]}')
    out = str(final.get('result') or '').strip()
    trace('output', name, out[-1000:])
    return out, final.get('session_id'), None


def task_context(store, task_id: int) -> str:
    d = store.task_detail(task_id)
    t = d['task']
    lines = [f"Task {d['ref']}: {t.get('Title')}", f"Kind: {t.get('Kind')}  Status: {t.get('Status')}",
             f"Summary: {t.get('Summary') or ''}", '', 'Messages:']
    for m in d['messages']:
        lines += [f"- [{m.get('SentAt')}] {m.get('FromName') or m.get('FromEmail')}: {m.get('Subject') or ''}",
                  f"  {str(m.get('BodyText') or '')[:1500]}"]
    lines += ['', 'Thread:'] + [f"- {c.get('Actor')}: {str(c.get('Body'))[:300]}" for c in d['comments']]
    mem = memory_block(store, d['messages'])
    if mem: lines += ['', mem]
    from . import knowledge
    kb = knowledge.block(store, ' '.join(f"{m.get('Subject') or ''} {m.get('BodyText') or ''}" for m in d['messages'])[:4000])
    if kb: lines += [kb.strip()]
    return '\n'.join(lines)


def memory_block(store, messages: list) -> str:
    """The standing notes an agent working this thread has to follow - the ones that bear on
    THIS thread, not every note on file. It used to be every match with no cap at all, which
    grows without limit as the owner keeps giving verdicts; ranking by what the thread actually
    says puts the ones that matter at the top and says how many were left out."""
    from .ingest import relevant_notes
    text = ' '.join(f"{m.get('Subject') or ''} {m.get('BodyText') or ''}" for m in messages)[:4000]
    notes, left = relevant_notes(store, [(m.get('FromEmail') or '') for m in messages], text)
    if not notes: return ''
    return ('Standing notes (learned from the owner - FOLLOW these):\n'
            + '\n'.join(f'- {n}' for n in notes)
            + (f'\n({left} more apply to this thread but did not fit - ask before assuming '
               'nothing else was said.)' if left else ''))


# dispatch() lived here: one open->close HEADLESS run on a task, the CLI working and closing
# where nobody could watch it, interrupt it or answer it. That is precisely the thing this app
# exists to replace, and every road that used it now opens a REAL session instead
# (terminal.start_on_task) or, for a two-sentence reply, asks the main AI directly
# (responder.write_draft). It is deleted rather than left dormant: a headless runner sitting
# in the module is a headless runner somebody wires back up.
#
# run_cli above STAYS, and is not the same thing: it is a one-shot "ask this CLI a question"
# used as a cheap BRAIN (llm.make_cli_llm - triage, drafts, summaries on an agent's light
# model) and by the connector test. No task, no run row, no work performed.
