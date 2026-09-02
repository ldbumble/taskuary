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

from . import spawn
from .store import task_ref
from .clis import preset_args


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
_LOGIN_HOW = {'claude': "run `claude`, type `/login` and finish the sign-in", 'codex': "run `codex login` and finish the sign-in"}
# Provider/plan exhaustion is different from an agent failing the work. Only this availability
# class is safe to hand to another configured agent automatically: a compile error should remain
# with the agent that owns it, while "session limit; resets at 11:50" should not strand the task.
_UNAVAILABLE = re.compile(
    r'session limit|usage limit|rate limit|quota|capacity|temporarily unavailable|service unavailable|'
    r'too many requests|resource exhausted|try again (?:at|after|later)|resets? (?:at|in)', re.I)

def signed_out_msg(name: str, why: str) -> str:
    how = _LOGIN_HOW.get(name, f"run `{name}` and sign in again")
    return f"{name} is signed out on this machine ({why.strip()[:160]}). Open a terminal, {how}, then come back here and try again."


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


def default_agent(store) -> str:
    """Which agent a task goes to when nobody picked one.

    The owner's choice wins - unless its CLI is not on this machine, in which case one that IS
    beats a name that can only fail. Taskuary ships `coder` = claude, so on a machine with only
    codex installed every dispatch died on a CLI nobody had, and the Board showed it as the
    agent's failure (an owner's machine, 2026-08-31)."""
    want = str(store.get_settings().get('default_agent') or 'coder').strip()
    profs = profiles(store)
    if want not in profs or runs_here(profs[want]): return want
    return next((n for n, prof in profs.items() if runs_here(prof)), want)


def agent_chain(store, primary: str = None) -> list[str]:
    """Primary plus ordered configured fallbacks, once each.

    `backup_agents=*` is the out-of-box resilient choice: every other roster entry, in the
    stable order the owner sees. Naming a CSV narrows and orders the chain explicitly.
    """
    names = [str(a.get('Name') or '').strip() for a in store.list_agents() if a.get('Name')]
    head = str(primary or default_agent(store) or '').strip()
    if head and head not in names: return [head]
    setting = str(store.get_settings().get('backup_agents') or '').strip()
    backups = names if setting == '*' else [x.strip() for x in setting.split(',') if x.strip()]
    out = []
    for name in [head, *backups]:
        if name and name not in out and name in names: out.append(name)
    return out


def run_cli(profile: dict, prompt: str, trace, resume: str = None, cancel=None):
    """One headless invocation of the configured CLI, output STREAMED line by line into
    the run trace so the Board shows the agent working live. claude's stream-json events
    render as readable tool/text lines; any other CLI's plain stdout streams as-is.
    Returns (result, session_id, diff)."""
    name = profile.get('cmd', 'claude')
    args = list(profile.get('args') or preset_args(name) or ['-p'])
    # Codex's normal exec output is human prose with no boundary between commands, searches,
    # edits and the final answer. JSONL is an exec-only presentation flag, so add it here (not
    # to the saved profile, which is also used to open the interactive terminal TUI).
    is_codex = _cli_name(name) == 'codex' and bool(args) and args[0] in ('exec', 'e')
    if is_codex and '--json' not in args: args.append('--json')
    cmd = _resolve_cmd(name) + args
    # which model works it: profile default, or a per-run override from the UI. The flag
    # name is configurable because every CLI spells it differently (claude/codex: --model).
    if profile.get('model'):
        # 'gpt-5.4@high' spells a codex model and its reasoning level in one pick (climodels)
        from .climodels import split_pick
        m, eff = split_pick(profile['model'])
        cmd += [profile.get('model_arg') or '--model', m]
        if eff: cmd += ['-c', f'model_reasoning_effort={eff}']
    if resume and profile.get('resume_args'): cmd += list(profile['resume_args']) + [resume]
    cwd = profile.get('cwd')
    head0 = _git(cwd, 'rev-parse', 'HEAD')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} cwd={cwd or os.getcwd()}' + (f' resume={resume}' if resume else ''))
    try:
        p = spawn.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding='utf-8', errors='replace', cwd=cwd, shell=False,
                             env=child_env())
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
        try: p.stdin.write(prompt); p.stdin.close()
        except Exception: pass
    threading.Thread(target=_feed, daemon=True).start()
    raw, final, streamed_out, streamed_sid, open_tools = [], None, '', None, set()
    try:
        for line in p.stdout:
            line = line.rstrip('\n')
            if not line.strip(): continue
            raw.append(line)
            try: j = json.loads(line)
            except ValueError: trace('live', name, line[:400]); continue
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
    err_t.join(5)      # the exit code can land before the stderr reader has appended - 'boom' read as 'no output' on a fast CI box
    if p.returncode != 0:
        if cancel is not None and cancel.is_set(): raise RuntimeError('cancelled')
        why = f'timed out after {profile.get("timeout", 1200)}s' if timed.is_set() else \
            ((err_buf[0] if err_buf else '') or '\n'.join(raw[-5:]) or 'no output')[:500]
        limit = rate_limited(raw) or rate_limited(why)
        if limit: raise RuntimeError(rate_limit_msg(name, limit))
        if _SIGNED_OUT.search(why): raise RuntimeError(signed_out_msg(name, why))
        # a refusal to START, not a failed run: the CLI produced no output of its own and the
        # only thing on stderr is the refusal
        if _DENIED.search(why) and not raw: raise RuntimeError(denied_msg(name, cmd[0] if cmd else '', why))
        if _NO_HOME.search(why): raise RuntimeError(no_home_msg(_cli_name(name) or name))
        raise RuntimeError(f'{name} exit {p.returncode}: {why}')
    if final is not None: out, sid = str(final.get('result') or '').strip(), final.get('session_id')
    elif streamed_out: out, sid = streamed_out, streamed_sid
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
