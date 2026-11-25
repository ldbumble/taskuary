"""Agent execution: any CLI is an agent. A profile ({cmd, args, resume_args, timeout, cwd,
cwd_map}) turns Claude Code, Codex, or your own wrapper into a Taskuary teammate: prompt
over STDIN (argv length limits are real on Windows), JSON output parsed when available
(Claude-style {result, session_id} -> resumable sessions), git diff captured around the
run so code changes are first-class, every run traced + audited.
"""
import atexit, contextlib, contextvars, hashlib, json, os, re, shutil, subprocess, threading, time
from datetime import datetime
from pathlib import Path
from loguru import logger

from . import acp as acp_mod, acpadapter, aiusage, pathcache, redact, spawn
from . import clis as clis_mod
from .store import task_ref
from .timewords import clock
from .clis import preset_args
from .clipool import LIMITS, MID_TURN, Cancelled, PartWay, TimedOut, Unfinished, ended_early
from .selfclose import without_summary

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
        node = pathcache.which('node')
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


_FOUND, GONE_TRIES, GONE_WAIT = set(), 5, 1.0        # the CLIs this process has found; how long one of them may be gone before it is said so
def _resolve_cmd(name: str) -> list:
    """Windows can't CreateProcess a bare 'claude': npm installs it as claude.cmd, which only
    PATH-resolves via which(). Reaching THROUGH the shim beats running it under cmd /c - see
    _shim_target for why that difference decides whether a prompt arrives whole."""
    path = pathcache.which(name) or pathcache.which(name, path=_fresh_path())
    if not path and re.search(r'[\\/]', str(name)):
        # A saved ABSOLUTE path that has moved. codex installs itself into
        # ...\Codex\bin\<version hash>\codex.exe, so a profile pinned to one of those breaks on
        # the next update and reads as "the CLI is gone". The NAME is the durable half: ask PATH
        # again for it, which is what the owner would have done by hand.
        base = re.split(r'[\\/]', str(name))[-1]
        path = pathcache.which(base) or pathcache.which(base, path=_fresh_path())
        if path: logger.info(f'{name} has moved; using {path} instead')
    # A CLI THAT WAS HERE A MOMENT AGO IS UPDATING ITSELF (recorded on the real CLI, 2026-11-13: claude swapped its own binary between two
    # turns, and the line that waited by the box began its turn in that second - "'claude' not found on PATH - is the CLI installed?" in
    # the chat, on a machine that had just answered with it): one found earlier in this process is looked for again for a few seconds
    # before it is said to be gone. One never found fails at once, as before - a check for what is installed never waits
    # ...(while shutil.which is a test's double its answer is the answer, as pathcache holds: nothing is waited for)
    if not path and name in _FOUND and shutil.which is pathcache._ORIG:
        for _ in range(GONE_TRIES):
            time.sleep(GONE_WAIT); pathcache.forget()
            if (path := pathcache.which(name)): break
        if not path: _FOUND.discard(name)
    if not path:
        raise FileNotFoundError(f"'{name}' not found on PATH - is the CLI installed?")
    _FOUND.add(name)
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


# THE OWNER'S OWN SECRETS IN THE SERVER'S ENVIRONMENT ARE NO SESSION'S (red team #2, T3): a trusted session inherited every variable the app
# was started with - a vendor's API key, a database password, a package registry's token - for its agent to print. By the variable's name, its
# grammar: one that names a credential goes, unless it is how an AI or the code host its work pushes to signs in (the CLI, git, gh) or Taskuary's own
_SECRET_ENV = re.compile(r'(TOKEN|SECRET|PASSWORD|PASSWD|PASSPHRASE|APIKEY|_KEY|CREDENTIALS?|_PAT|_AUTH)$', re.I)
_SIGN_IN_ENV = re.compile(r'^(ANTHROPIC|CLAUDE|OPENAI|CODEX|GEMINI|GOOGLE|AWS|AZURE|VERTEX|CLOUD_ML|COPILOT|GH|GITHUB|GITLAB|GLAB|TASKUARY)_', re.I)
def ambient(base) -> dict: return {k: v for k, v in dict(base).items() if not _SECRET_ENV.search(k) or _SIGN_IN_ENV.match(k)}


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
    env = ambient(os.environ) if base is None else dict(base)       # ...the profile's own variables (spawn_env) stay as he set them
    # ...and NO CLI KEEPS A MEMORY OF ITS OWN (the recorded walk, 2026-11-11: an agent saved a "playbook" into Claude Code's memory folder,
    # where no card held it and no other agent reads it). It was switched off for chat agents only; a coding agent in a pane, over ACP, or a
    # one-shot with tools still wrote there. Every CLI Taskuary starts takes its environment from here, so here it is off for all of them
    from .clis import NO_MEMORY
    env.update(NO_MEMORY)
    env['PYTHONUTF8'] = '1'          # ...and a Python it runs reads and writes UTF-8, never the code page (shellgate.PS_UTF8 says what broke)
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


def _fmt_input(inp, name: str = '') -> str:
    """The one field a human wants to see per tool call - command, path, pattern… - and a draft by what it is, never its body
    (sessionrecord.hide_draft: a login the thread asked for goes in the draft, not on the pane)."""
    from .sessionrecord import DRAFT_SHOWN, drafting
    if drafting(name, inp): return DRAFT_SHOWN
    if not isinstance(inp, dict): return str(inp)[:140]
    for k in ('command', 'file_path', 'path', 'pattern', 'url', 'query', 'description', 'prompt'):
        if inp.get(k): return str(inp[k])[:140]
    return json.dumps(inp)[:140]


def _result_text(c) -> str:
    """A tool_result's content is a string or a list of {type: text} blocks."""
    v = c.get('content')
    if isinstance(v, list): v = ' '.join(str(b.get('text') or '') for b in v if isinstance(b, dict))
    from .agenttools import LINE_MARK                    # ...the one mark for a break (nextstep.json): the page reads it as one
    return re.sub(r'\s*\n\s*', LINE_MARK, str(v or '').strip())


_DOC_CREATES = {}                                    # tool_use id -> a Claude Docs create's input, until its result


def _published(j, trace):
    """A page the CLI published with its Artifact tool, said to the caller as its own trace event - the
    caller knows the task it belongs to (general.send_prompt keeps it there, claude_artifacts)."""
    from . import claude_artifacts
    if j.get('type') == 'assistant':                # a Claude Docs create: its answer does not say which tool it was
        for c in (j.get('message') or {}).get('content') or []:
            if isinstance(c, dict) and c.get('type') == 'tool_use' and claude_artifacts.is_doc_create(c.get('name'), c.get('input')):
                _DOC_CREATES[c.get('id')] = c['input']
                while len(_DOC_CREATES) > 64: _DOC_CREATES.pop(next(iter(_DOC_CREATES)))
        return
    info = claude_artifacts.from_stream(j)
    if info: trace('artifact', 'claude', info)
    for c in (j.get('message') or {}).get('content') or []:
        inp = _DOC_CREATES.pop(c.get('tool_use_id'), None) if isinstance(c, dict) and c.get('type') == 'tool_result' else None
        doc = inp and claude_artifacts.doc_made(inp, c.get('content'))
        if doc: trace('artifact', 'claude', doc)


class ClaudeSteps:
    """One claude stream-json turn as the trace events every road speaks (tool_call, tool_result, progress text and thinking, a published
    page). The one-shot run and the kept conversation each make one per turn and feed it every event. A call the CLI gave no id is numbered
    here, once per turn (`tool-0`, `tool-1`), and a result with no id closes the oldest such call still open - so on both roads every
    step is its own and every one closes (agentSteps.js and sessionrecord.trace_steps pair them by id)."""
    def __init__(self, trace): self.trace, self.n, self.open = trace, 0, []

    def __call__(self, j: dict):
        kind = j.get('type')
        if kind not in ('assistant', 'user'): return
        for c in (j.get('message') or {}).get('content') or []:
            if not isinstance(c, dict): continue
            if kind == 'assistant' and c.get('type') == 'tool_use':
                iid = c.get('id') or f'tool-{self.n}'
                if not c.get('id'): self.n += 1; self.open.append(iid)
                self.trace('tool_call', c.get('name') or 'tool', {'tool_call_id': iid, 'args': c.get('input') or {},
                                                                 **({'parent': j['parent_tool_use_id']} if j.get('parent_tool_use_id') else {})})
            elif kind == 'assistant' and c.get('type') == 'text' and str(c.get('text') or '').strip(): self.trace('progress', 'text', str(c['text']).strip())
            elif kind == 'assistant' and c.get('type') == 'thinking' and str(c.get('thinking') or '').strip():
                self.trace('progress', 'thinking', str(c['thinking']).strip())     # what it thought is part of the record
            elif kind == 'user' and c.get('type') == 'tool_result':
                iid = c.get('tool_use_id') or (self.open.pop(0) if self.open else 'tool')
                if iid in self.open: self.open.remove(iid)
                self.trace('tool_result', iid, {'result': _result_text(c), 'is_error': bool(c.get('is_error'))})
        _published(j, self.trace)


def failure_of(name: str, said: str, cmd0: str = '', resume=None, raw=None, err: str = '') -> Exception | None:
    """WHAT A FAILED TURN IS, read one way on every road - the one-shot run, the kept conversation, ACP's chat and coding sessions: its usage
    allowance (the CLI's own event, or its notice in words, as Codex and the ACP adapters say it), its sign-in, a conversation it no longer
    has - else None. `raw` is what else it printed; `err` its stderr, read for a sign-in as `said` is."""
    from .failures import cli_quota
    raw = raw if raw is not None else [said]
    if limit := rate_limited(raw) or rate_limited(said): return RateLimited(rate_limit_msg(name, limit), limit)
    if notice := cli_quota(said) or cli_quota(err): return RateLimited(notice)
    if _SIGNED_OUT.search(f'{said}\n{err}'): return RuntimeError(signed_out_msg(name, said, cmd0))
    if resume and gone('\n'.join(map(str, raw)) or said): return Gone(resume)
    return None


def prompt_failure(name: str, e, cmd0: str = '', sid=None) -> Exception | None:
    """WHAT AN ACP TURN'S ERROR IS, on the chat and the coding road alike: what failure_of reads (a limit, a sign-in) - else, where its agent
    answered the prompt itself with an error that names no provider's status or refusal, the turn stopped part-way (MID_TURN), its text the
    log's. Walk 16: a Codex adapter whose app-server died answered with that server's stderr, and its first line - a deprecation warning the
    run had gone on past - stood on the rail as the cause. None: none of these."""
    from . import say
    from .failures import refused
    if f := failure_of(name, str(e), cmd0): return f
    if getattr(e, 'method', '') != 'session/prompt' or say.provider_said(str(e)) or refused(str(e)): return None
    logger.warning(f'acp: {name} answered its turn with an error - {str(e)[:600]}')
    return acp_mod.DiedMidTurn(MID_TURN, sid)


def raise_failure(name: str, said: str, cmd0: str = '', resume=None, raw=None, part_way=None):
    """THE ONE WAY A TURN THAT DID NOT FINISH IS REPORTED, on every road that reads a CLI's own account of it (the kept conversation, ACP,
    the one-shot run's death with no words): what it is (failure_of) - else its own words. `part_way` is (sentence, conversation id) where the
    road knows the turn ended part-way (it died mid-turn, or ended early (a refusal, a limit), before a word or after some): raised as
    clipool.PartWay in that sentence alone."""
    if e := failure_of(name, said, cmd0, resume, raw):
        if part_way: raise e from Unfinished(said, part_way[1])        # ...its conversation kept for the try again (run_acp)
        raise e
    # ...no process name before it and no "(the CLI exited (3))" or stop code after it (the overnight walk, 2026-11-11) - those are the log's
    if part_way: logger.warning(f'{name}: {said[:500]}'); raise PartWay(*part_way)
    raise RuntimeError(f'{name}: {said[:500]}')


def _live_line(j):
    """One readable console line per claude stream-json event; None = not worth showing.
    Tool RESULTS stream too (trimmed), so the console reads like the terminal you'd see
    if you ran the CLI yourself - not just the commands it fired."""
    t = j.get('type')
    if t == 'system':
        # only the real session init is news; the other system events (hooks, compaction,
        # subagent starts) repeated 'session started' forever and said nothing
        # ...except Claude's own retries when it cannot reach its servers (the desktop run, 2026-11-04: the network down, the pane said
        # "Starting Taskuary on Claude Code… 3m" for the ten tries it made before it gave up, and nothing said why it was slow)
        if j.get('subtype') == 'api_retry':
            n, of = j.get('attempt'), j.get('max_retries')
            return f"Can't reach Claude's servers right now - trying again" + (f' ({n} of {of})' if n and of else '')
        if j.get('subtype') not in (None, 'init'): return None
        m = j.get('model') or (j.get('modelInfo') or {}).get('name') or ''
        return 'session started' + (f' · model {m}' if m else '')
    if t == 'assistant':
        out = []
        for c in (j.get('message') or {}).get('content') or []:
            if c.get('type') == 'tool_use': out.append(f"→ {c.get('name')}: {_fmt_input(c.get('input'), c.get('name'))}")
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
# ...and Gemini's and Qwen's own words for it (2026-10-25): "API key is missing or not configured", "Please set an Auth method",
# "Authentication required: Use Qwen Code CLI to authenticate first" reached the task page as an app bug with Report this bug
_SIGNED_OUT = re.compile(r'OAuth session expired|Failed to authenticate|not logged in|Not logged in|please (?:run )?[`\']?(?:claude )?/?login|codex login|401 Unauthorized'
                         r'|API key is missing|set an Auth method|Authentication required|to authenticate first', re.I)
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

    The name that arrives here is the PROFILE's - every install ships one called `coding` - so the
    CLI is read off the command it runs, which is the rule cliinstall.recipe_for exists for. Told
    the profile name, _LOGIN_HOW.get('coding') missed every time and always had."""
    from . import cliinstall, words
    cli = cliinstall.recipe_for(cmd) or name
    why = re.sub(r'^\s*session/\w+:\s*', '', str(why or ''))        # the protocol's method name is ours, not the owner's to read
    how =_LOGIN_HOW.get(cli, f"run `{cli}` and sign in again")
    # named by the AI, not the profile: "coding isn't signed in" says nothing about which sign-in to do
    return (f"{cli} isn't signed in on this machine ({why.strip()[:160]}). Press Set it up on "
            f"{words.name('ai_apps')} and sign in there in the pane that opens - or {how} in a terminal.")


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


def limit_resets(info: dict):
    "When a refused allowance comes back, as the CLI said it (a datetime), or None when it did not say."
    when = (info or {}).get('resetsAt') or (((info or {}).get('unifiedWindows') or {}).get((info or {}).get('rateLimitType')) or {}).get('resetsAt')
    try: return datetime.fromtimestamp(int(when))
    except (TypeError, ValueError, OSError, OverflowError): return None


class RateLimited(RuntimeError):
    """A CLI that refused on its usage allowance. `until` is when it comes back, or None - the router rests the brain till then
    (brainroute.cool) instead of handing it the next call to refuse."""
    def __init__(self, msg: str, info: dict = None): super().__init__(msg); self.until = limit_resets(info)


def rate_limit_msg(name: str, info: dict) -> str:
    """What the owner needs: which allowance, when it comes back, and that nothing is broken."""
    window = _LIMIT_WINDOW.get(str(info.get('rateLimitType') or ''), str(info.get('rateLimitType') or '')).strip()
    when = info.get('resetsAt') or ((info.get('unifiedWindows') or {}).get(info.get('rateLimitType')) or {}).get('resetsAt')
    at = ''
    try:
        t = datetime.fromtimestamp(int(when))
        day = '' if t.date() == datetime.now().date() else (' tomorrow' if (t.date() - datetime.now().date()).days == 1
                                                            else t.strftime(' on %a %d %b'))
        at = f" It comes back at {clock(t)}{day}."
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
    # ...and a bare error object with no event type ({"error": {"code": 401, "message": "API key not valid ..."}}): its own words
    if 'type' not in j and j.get('error'):
        e = j['error']
        return _said(e.get('message') if isinstance(e, dict) else e)
    # ...and claude's own result for a turn that failed: its words (a credit refusal), else its `errors` beside a bare subtype (error_max_turns)
    if j.get('type') == 'result' and (j.get('is_error') or str(j.get('subtype') or '').startswith('error')):
        errs = j.get('errors') if isinstance(j.get('errors'), list) else []
        return _said(j.get('result')) or '; '.join(map(str, errs)).strip() or str(j.get('subtype') or '').replace('_', ' ')
    item = j.get('item') if isinstance(j.get('item'), dict) else {}
    return _said(item.get('message')) if item.get('type') == 'error' else ''


def _is_event(line) -> bool:
    "One of a CLI's structured event lines (a JSON object), as opposed to words it printed - a dict's repr or a stack dump in braces is words."
    try: return isinstance(json.loads(str(line)), dict)
    except ValueError: return False


def _events(raw) -> list:
    """Which of the run's stdout lines are its events: each that is a JSON object - and, in a stream of nothing but events, a LAST line cut off
    as its process was killed (`{"type": "res`): it opens as one (`{"`) and never closed. Any other line is words the CLI printed."""
    raw = [str(x) for x in raw or []]
    ev = [_is_event(x) for x in raw]
    if raw and not ev[-1] and all(ev[:-1]) and raw[-1].lstrip().startswith('{"'): ev[-1] = True
    return ev


def cli_failure(raw, err: str = '') -> str:
    """Why the run failed: the CLI's own newest error event, else what it put on stderr.

    The newest wins because an earlier one is usually a warning the run carried on past - codex
    grumbles about unknown model metadata and then fails on the refusal that actually stopped it.
    """
    for line in reversed(list(raw or [])):
        said = _event_error(str(line))
        if said: return said
    clean = _said_err(err)
    # ...and never the events themselves: their JSON is no reason (a stream cut mid-line read "claude exit 137: {"type": "system", ...}")
    return clean or '\n'.join([ln for ln, e in zip(raw or [], _events(raw)) if not e][-5:]) or ('no reason given' if raw else 'no output')


def _said_err(err: str) -> str:
    "What a CLI said on stderr, without its own notices (_NOISE: \"Reading prompt from stdin...\")."
    return '\n'.join(ln for ln in str(err or '').splitlines() if ln.strip() and not _NOISE.match(ln)).strip()


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


def resume_argv(profile: dict, sid: str, store=None) -> list:
    """How this CLI is told to pick its OWN conversation back up - empty when it cannot, which is
    the honest answer for gemini, cursor and devin until each one can also be told WHICH session it
    had. A profile's own resume_args wins: the owner configured it for a CLI we do not ship."""
    if not sid: return []
    args = profile.get('resume_args') or RESUME_ARGS.get(_cli_name(with_cmd(profile, store)['cmd']))
    return _with_id(list(args), sid) if args else []


def assign_argv(profile: dict, sid: str, store=None) -> list:
    """The argv tail that NAMES a new conversation - empty when this CLI names its own."""
    args = ASSIGN_ARGS.get(_cli_name(with_cmd(profile, store)['cmd'])) if sid else None
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


def coding_ready(store) -> bool:
    """CODING EXISTS ONLY WHERE A CODING TOOL CAN START (the owner, 2026-10-16: "if no cli tool like cloud api tools no coding"):
    a connected CLI whose command runs on this computer. A ChatGPT sign-in or an API card - HIPAA AI included - is no coding tool.
    ...and ONLY IN DEVELOPER MODE (the owner, 2026-11-02: "for regular people everything should be a general agent, not coding"):
    off, every job is a general agent's whatever CLI is connected - triage, the pickers and the Assistant all read this one answer."""
    return developer_mode(store) and cli_ready(store)


def cli_ready(store) -> bool:
    "A connected CLI that starts on this computer - what a coding agent runs on, developer mode or not (a task already coding keeps it)."
    return any(runs_here(conn) for _key, conn in connection_brains(store))


DEV_MODE = 'developer_mode'

def developer_mode(store) -> bool:
    "The owner's Developer mode switch (Settings, setup). Off on a fresh install; an upgraded home that used coding was turned on (devmode.py)."
    try: return store is not None and str(store.get_setting(DEV_MODE) or '').strip().lower() in ('1', 'true', 'on')
    except Exception: return False


def no_coding_why(store) -> str:
    "Why there is no coding agent here, in one plain clause - the switch when it is off, else the missing tool."
    return 'Developer mode is off (Settings, Developer mode)' if not developer_mode(store) else 'No coding tool is connected'
def no_coding_fix(store) -> dict:
    """...and the button that lifts it, {label, href}: the switch that refused, never a place it is not (the walks, 2026-11-18: "No coding tool
    is connected" over a connected Codex, its button to Connections, while the block was Developer mode)."""
    from . import words
    if not developer_mode(store):
        from .settings_schema import href
        return {'label': 'Turn on Developer mode', 'href': href('developer_mode')}
    return {'label': 'Connect a coding tool', 'href': words.href('ai_apps')}


def runs_here(profile: dict) -> bool:
    """Does this profile's command resolve to something we can start? A profile naming no command names no CLI: it used to be
    read as claude, so a role row synced before any brain was chosen "ran here" on a machine where only Codex was set up."""
    cmd = (profile or {}).get('cmd')
    if not cmd: return False
    from . import demo
    if demo.enabled(): return demo.here(cmd)                  # the demo's invented machine, never the visitor's PATH
    try: return bool(_resolve_cmd(cmd))
    except (FileNotFoundError, OSError): return False


# WHICH CONNECTED CLI PASSED ITS TEST: {key: true|false}, written by the owner's own Test and by setup's pick (firstrun.choose_cli).
# A fallback brain - one nobody chose - is only ever one that starts here and did not FAIL its last test, a passed one ahead of an
# untested one: a claude left connected by a sign-in that never finished started every researcher task signed out, beside the
# Codex the person had actually set up (2026-10-21).
CLI_TESTS = 'cli_tests'

def cli_tests(store) -> dict:
    try: out = json.loads(store.get_setting(CLI_TESTS) or '{}')
    except (TypeError, ValueError): out = {}
    return out if isinstance(out, dict) else {}

def record_cli_test(store, key: str, ok: bool):
    if key: store.set_setting(CLI_TESTS, json.dumps({**cli_tests(store), str(key): bool(ok)}), 'system')

def answered(store, pick: str):
    """A FAILED TEST IS OVER THE MOMENT THE CLI ANSWERS WORK (the owner, 2026-11-11: "it says codex not claude why?"): the mark was
    cleared only by pressing Test again, so a CLI whose one test failed - pressed while it rested on its usage limit, say - stayed
    out of every list of what can take work while it ran reports and sessions all day."""
    k = str(pick or '')[4:] if str(pick or '').startswith('cli:') else ''
    if k and cli_tests(store).get(k) is False: record_cli_test(store, k, True)

# THE BRAIN SETTINGS A START READS, and who wrote each: 'owner' is the person's own pick (setup, Settings, the Assistant tab);
# anything else - 'migration' from adopt_brain_setting and migrate_brain_settings, blank - was saved FOR them.
HEALED = ('default_brain', 'triage_ai', 'concierge_ai', 'assistant_ai', 'judge_ai')

def picked(store, name: str) -> bool: return store.setting_writer(name) == 'owner'

def _cli_in(name: str, value) -> str:
    "The CLI key one brain setting names - `codex` from default_brain's `codex` or a slot's `cli:codex` - else ''."
    v = str(value or '').strip()
    if name == 'default_brain': return '' if is_card(v) else v
    return v[4:] if v.startswith('cli:') and ',' not in v else ''

def is_card(v) -> bool:
    "Does a brain setting name an AI card (`connector:<id>`, or an old bare id) rather than a CLI? default_brain may hold one."
    v = str(v or '').strip(); return v.startswith('connector:') or v.isdigit()

def stale(store, name: str) -> bool:
    "A brain saved for the person - never picked by them - that is not ready here (ready_brains): it must not keep winning."
    k = _cli_in(name, store.get_setting(name))
    return bool(k) and not picked(store, name) and k not in ready_brains(store)

def owners_pick(store, pick: str) -> bool:
    "Is this `cli:` pick one the person chose themselves, in a brain setting?"
    k = str(pick or '')[4:] if str(pick or '').startswith('cli:') else ''
    return bool(k) and any(picked(store, n) and _cli_in(n, store.get_setting(n)) == k for n in HEALED)

def heal_brains(store, probe: bool = True) -> list:
    """An upgrade must HEAL a machine an older start already pinned: adopt_brain_setting saved the first connected CLI - a claude
    never signed in, beside the Codex the person had set up - and every general task kept starting on it (2026-10-21). A brain saved
    FOR the person that is not ready is cleared, so a start falls back by ready_brains; one the person PICKED stays, and its own
    failure says so. `probe` asks a saved-for-them CLI with no test on record whether it is signed in (clisetup.signed_in, its own
    status command) - once: the answer is recorded. Returns the settings cleared."""
    if probe:
        from . import clisetup
        from .cli_connections import cli_key
        conns = dict(connection_brains(store))
        for n in HEALED:
            k = _cli_in(n, store.get_setting(n))
            if not k or picked(store, n) or k in cli_tests(store) or k not in conns: continue
            ok = clisetup.signed_in(cli_key(conns[k].get('cmd')) or k)
            if ok is not None: record_cli_test(store, k, ok)
    gone = [n for n in HEALED if stale(store, n)]
    for n in gone: store.set_setting(n, '', 'migration')
    if gone: logger.info(f"cleared brains saved for the person that do not run here: {', '.join(gone)} - a start falls back to a ready one")
    return gone


# ONE ANSWER TO "WHICH AI RUNS THIS" when a run names none (the owner, 2026-10-21: "check everywhere in the codebase where claude
# is default. It should never be that way"). In order: (1) the brain set in Settings for this kind of run, (2) a CLI that is
# connected, starts here and did not fail its test (ready_brains), (3) a connected API connector, where the run can use one -
# (4) else nothing, and the run says "No AI is connected". Every launch road that used to read a missing command as claude asks here.
NO_AI = 'No AI is connected'
NEEDS_CLI = 'needs a coding tool - connect one'
BRAIN_SETTING = {'coding': 'default_brain', 'general': 'assistant_ai', 'triage': 'triage_ai', 'assistant': 'concierge_ai'}

class NoAI(ValueError): "Nothing connected can run this - the reason a start shows, naming no AI the person does not have."


def role_brain(store, role: str) -> str:
    """The CLI key set for one profile's work (profile_brains) - his own taken at its word, as resolve_brain takes a card's; one an update
    moved there only while it is connected. '' when none."""
    try: over = json.loads(store.get_setting('profile_brains') or '{}')
    except (TypeError, ValueError): over = {}
    k = str(over.get(str(role or '')) or '').strip() if role and isinstance(over, dict) else ''
    return k if k and (picked(store, 'profile_brains') or k in dict(connection_brains(store))) else ''


def resolve_brain(store, kind: str = 'general', cli_only: bool = False, role: str = None) -> str:
    """'cli:<key>', 'connector:<id>' or '' - see above. `cli_only` for a run that cannot exist without a terminal; `role` a profile
    whose own brain (profile_brains) the owner set. THE PICK EVERY ROAD READS: triage's (llm.effective_pick), the Assistant's
    (concierge.default_pick), the general agent's (general._selected), a coding pane's (brain_for, brain_chain, cli_connections.brain_of)
    and the router's fixed answer (brainroute._fixed) - two of them read a blank slot two ways, and a job ran on a CLI Settings did not name."""
    if role and (r := role_brain(store, role)): return f'cli:{r}'
    name = BRAIN_SETTING.get(kind, 'assistant_ai')
    v = '' if stale(store, name) else str(store.get_setting(name) or '').strip()
    # ...a CLI's key, or an AI card the owner chose for coding (the owner, 2026-11-09: "coding tasks should run on hipaa, why not")
    if v and name == 'default_brain' and not is_card(v): v = f'cli:{v}'
    if v.isdigit(): v = f'connector:{v}'
    if ',' in v and not cli_only: return v              # a slot naming its own failover order (triage) is taken as written
    # the person's own pick is taken at its word - one that does not start says so when it is started, never swapped behind them
    if v.startswith('cli:') and (picked(store, name) or v[4:] in dict(connection_brains(store))): return v
    if v.startswith('connector:') and not cli_only: return v
    # BLANK MEANS THE DEFAULT BRAIN (default_pick: the Coding agent card's CLI when it is his or ready, else a ready one) - this took the
    # first ready CLI while triage and the general agent took the default, so one blank read two ways
    d = default_pick(store)
    if d.startswith('cli:'): return d
    # ...a run that needs a terminal takes any ready CLI over none (default_pick gave way to a card, or names one not connected)
    if cli_only: return next((f'cli:{k}' for k in ready_brains(store)), '')
    # no CLI here: a job with no pick of its own runs on the AI card the general agent is SET to (a gateway-only home's coding task)
    if name != 'assistant_ai' and (g := str(store.get_setting('assistant_ai') or '').strip()).startswith('connector:'): return g
    c = ready_connector(store)
    return f"connector:{c['ConnectorId']}" if c else ''


def resolved_command(store, kind: str = 'coding') -> dict:
    "The command fields of the CLI resolve_brain names for a run that needs one - {} when none is connected."
    p = resolve_brain(store, kind, cli_only=True)
    return brain_command(store, '', want=p[4:]) if p else {}


def with_cmd(profile: dict, store=None, kind: str = 'coding') -> dict:
    """The profile with the command it runs: its own, else the resolver's (`store` needed for that). A launch with no CLI is a bug
    upstream - it raises NoAI, never runs claude."""
    profile = dict(profile or {})
    if profile.get('cmd'): return profile
    from .cli_connections import COMMAND_FIELDS
    fill = resolved_command(store, kind) if store is not None else {}
    if not fill.get('cmd'): raise NoAI(f'{NO_AI} - this run {NEEDS_CLI}')
    return {**{k: v for k, v in profile.items() if k not in COMMAND_FIELDS}, **fill}


def ready_brains(store) -> list:
    """The connected CLIs a brain nobody chose may fall back to: starts here, last test not failed; passed ones first."""
    tests = cli_tests(store)
    keys = [k for k, c in connection_brains(store) if tests.get(k) is not False and runs_here(c)]
    return sorted(keys, key=lambda k: tests.get(k) is not True)


def agent_row(store, name: str, model: str = None) -> dict | None:
    """The row a `cli:<name>` pick runs. A BRAIN IS A CLI TOOL OR AN AI CONNECTION, NEVER A PROFILE (the owner, 2026-10-15:
    "there is no such profile or brain.. it's models or cli tools only"): `cli:claude` is the Claude Code connection, whatever
    profiles exist. A profile name here is a pick saved before brains named tools (`cli:<profile>`) - still run, by its row, so an
    old chat keeps working until migrate_brain_settings rewrites it."""
    if not name: return None
    from . import config, harness
    if harness.card_id(name) is not None: return harness.row(store, name, model or '')     # an API card's agent, on its harness CLI (harness.py)
    from .cli_connections import with_defaults
    conn = (config.load().get('cli_connections') or {}).get(str(name))
    if conn: return {'Name': name, 'Kind': 'general', 'Runner': 'cli', 'Config': json.dumps(with_defaults(conn))}
    return store.get_agent(name)


def connection_brains(store, cfg: dict = None) -> list[tuple[str, dict]]:
    """(key, command) for every connected CLI - the CLI brains, one per tool. Installed or not: the pickers decide whether
    that matters. Profiles are not here: a profile is instructions layered on whichever brain runs it."""
    from . import config
    from .cli_connections import with_defaults
    return [(key, with_defaults(conn)) for key, conn in ((config.load() if cfg is None else cfg).get('cli_connections') or {}).items()]


def brain_key(store, pick: str, cfg: dict = None) -> str:
    """The CLI tool a `cli:` pick names - the connection key. A legacy pick naming a profile (`cli:<profile>`) is read as the tool
    that profile ran on, so nothing saved before brains named tools is lost."""
    name = str(pick or '')[4:] if str(pick or '').startswith('cli:') else str(pick or '')
    from . import config
    from .cli_connections import cli_key
    cfg = config.load() if cfg is None else cfg
    if not name or name in (cfg.get('cli_connections') or {}): return name
    prof = (cfg.get('agents') or {}).get(name)
    if prof is None:
        row = store.get_agent(name)
        try: prof = json.loads(row.get('Config') or '{}') if row else None
        except ValueError: prof = {}
    if prof is None: return name
    provider = str(prof.get('provider') or '')
    return provider[4:] if provider.startswith('cli:') else cli_key(prof.get('cmd') or '') or name


def availability_failure(error) -> bool:
    """Can the same untouched work safely be retried on a backup provider?"""
    from .failures import cli_quota
    text = str(error or '')
    # ...and an AI card resting on its spent budget (llm.BudgetSpent) says so itself
    if getattr(error, 'unavailable', False) is True: return True
    return isinstance(error, (FileNotFoundError, PermissionError)) or bool(
        cli_quota(text) or _UNAVAILABLE.search(text) or _SIGNED_OUT.search(text) or _DENIED.search(text) or _NO_HOME.search(text))


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
    """The CLI brains a picker offers: one per connected CLI tool, its value the tool's own key (`claude`, `codex`) - never a
    profile, which is instructions and runs on whichever brain is chosen (the owner, 2026-10-15). `preferred` keys lead;
    `coding_only` is kept for its callers - every CLI tool can code."""
    order = {str(k): i for i, k in enumerate(preferred or ()) if k}
    rows = sorted(connection_brains(store), key=lambda kc: (order.get(kc[0], len(order)), ))
    return [{'value': key, 'label': key, 'cli': key, 'ready': runs_here(conn)} for key, conn in rows]


def coding_options(store) -> list[dict]:
    """EVERY AI THAT CAN RUN A CODING TASK, as the pickers offer it (the owner, 2026-11-09: "fix the picker ... it should choose the
    correct one"): each connected CLI, then each active AI card - a card runs coding through general.on_card, in the checkout a CLI
    would open. `value` is the pick resolve_brain answers in (`cli:<key>` / `connector:<id>`), so the current one is found by equality."""
    from .llm import AI_TYPES
    out = [{'value': f'cli:{k}', 'key': k, 'kind': 'cli', 'ready': runs_here(c), 'label': clis_mod.name_of(cli_of(c, k) or k)}
           for k, c in connection_brains(store)]
    for c in store.list_connectors():
        if c['Type'] not in AI_TYPES or not c['Active'] or not (c['HasSecret'] or c['Type'] == 'ollama'): continue
        try: cfg = json.loads(c.get('ConfigJson') or '{}')
        except ValueError: cfg = {}
        model = str(cfg.get('model') or cfg.get('deployment') or '')
        out.append({'value': f"connector:{c['ConnectorId']}", 'connector': c['ConnectorId'], 'kind': 'card', 'ready': True,
                    'label': ' · '.join(x for x in (c.get('Name') or c['Type'], model) if x)})
    return out


def drop_cli_clones(cfg: dict, store) -> list:
    """Remove the coding workers named after a CLI - codex, copilot, devin, opencode... - leaving
    the one coding profile. Returns the names dropped, so the caller knows whether to save.

    There is ONE coding profile and one rules document; a brain is chosen per session from the CLI
    connections. An older setup minted a coding worker per installed CLI, each pointing at the shared
    document and differing only in which CLI ran it. That minting stopped on 2026-09-14 (adopt_installed's
    docstring), but the rows it had already written stayed on the page that listed them - five
    profiles for one document (the owner, 2026-09-17: one coding document for every CLI).

    Only a row that IS such a clone goes: coding kind, named after a known CLI, using the shared
    document. A coding profile with its own name or its own rules document is the owner's and stays.
    A clone's cwd_map (repository -> checkout) is folded into the coding profile's so no path mapping is lost."""
    from .clis import KNOWN
    from .cli_connections import cli_key
    clis = {k['name'] for k in KNOWN} | {cli_key(k['cmd']) for k in KNOWN}
    have = cfg.get('agents') or {}
    shared = ('coding', 'coder')                       # the shared document, by its name now and before
    def is_clone(name, prof):
        if name not in clis: return False
        if str(prof.get('kind') or 'coding').lower() not in CODING_KINDS: return False
        return str(prof.get('rules_doc') or 'coding') in shared
    rows = {a['Name']: a for a in store.list_agents(active_only=False)}
    home = next((n for n, p in have.items() if not is_clone(n, p) and str(p.get('kind') or 'coding').lower() in CODING_KINDS), None)
    gone = []
    for name in sorted(set(have) | set(rows)):
        prof = have.get(name)
        if prof is None:
            try: prof = json.loads(rows[name].get('Config') or '{}')
            except ValueError: prof = {}
            prof.setdefault('kind', rows[name].get('Kind') or 'coding')
        if not is_clone(name, prof): continue
        if prof.get('cwd_map') and home:
            have[home]['cwd_map'] = {**prof['cwd_map'], **(have[home].get('cwd_map') or {})}
        have.pop(name, None)
        if name in rows: store.delete_agent(name)
        gone.append(name)
    return gone


# The kinds that mean "works a repository". `cli` is the legacy spelling older databases use.
CODING_KINDS = ('coding', 'cli')
# Work that can still be dispatched. An allowlist rather than a list of endings, so a status added
# later cannot quietly make a repair start rewriting finished tasks (the store also has `dropped`).
LIVE_STATUSES = ('open', 'in_progress')


def ensure_coding(cfg: dict) -> bool:
    """The coding agent's row - where its checkouts are kept (cwd_map) - is always there: nothing on screen makes or removes one.
    True when it had to be added, so the caller saves config.toml."""
    have = cfg.setdefault('agents', {})
    if any(str(p.get('kind') or 'coding').lower() in CODING_KINDS for p in have.values()): return False
    have['coding'] = {'kind': 'coding'}
    return True


def coding_role(store) -> str:
    """The profile a coding task runs under: the one whose KIND is coding, found by its kind and never by a name (the owner,
    2026-10-15: "in triage if task is coding then map to profile coding"; a coding profile is just a profile). Triage does
    not choose it - `kind: coding` names the job. With several, the shipped `coding`, else the first by name; '' with none, and a session then runs on the brain with the base rules alone. Which CLI runs it is the brain's question (default_brain)."""
    rows = sorted((a for a in store.list_agents() if str(a.get('Kind') or '').lower() in CODING_KINDS and a.get('Active', 1)),
                  key=lambda a: (a['Name'] != 'coding', a['Name']))
    return rows[0]['Name'] if rows else ''


def default_agent(store) -> str:
    """The profile a task runs under when nobody picked one - the coding profile (coding_role). Kept as a name for its callers;
    it no longer reads a setting, and never answers with a brain."""
    return coding_role(store)


def default_brain(store) -> str:
    """The CLI every worker session runs on - coding and general alike (the owner, 2026-09-16:
    "general agents use the same brain on high level like coding by default").

    Blank falls back to the CLI behind the legacy `default_agent` profile, so an install that has
    not been migrated keeps running exactly what it ran yesterday."""
    key = str(store.get_setting('default_brain') or '').strip()
    # ...an AI card chosen for coding is no CLI: everything that reads this as a command key gets the CLI it would otherwise run
    if key and not is_card(key): return key
    legacy = str(store.get_setting('default_agent') or '').strip()       # an install from before brains named tools
    return brain_key(store, f'cli:{legacy}') if legacy else next(iter(ready_brains(store)), '')


def brain_ready(store, key: str) -> bool:
    """Does the CLI brain `key` actually start on this machine - the readiness the pickers show."""
    conn = dict(connection_brains(store)).get(key)
    return bool(conn) and runs_here(conn)


# a gateway card answers only a job set to it in Settings (the owner, 2026-11-09: "it should not be used unless set in settings") -
# a blank slot fell to it whenever no CLI was ready; a gateway-only install still gets every job named by first-run setup
PICKED_ONLY = ('hipaa_ai',)
def ready_connector(store) -> dict | None:
    """The first AI connector that can answer right now - what llm._build_llm runs for an empty pick. Never a PICKED_ONLY card."""
    from .llm import AI_TYPES
    return next((c for c in store.list_connectors() if c['Type'] in AI_TYPES and c['Type'] not in PICKED_ONLY
                 and c['Active'] and (c['HasSecret'] or c['Type'] == 'ollama')), None)


def default_pick(store) -> str:
    """What a BLANK brain setting means - triage, the Assistant, general work: the default brain, as a
    `cli:<worker>` pick on its light gear. It used to mean "the first active AI connector", so which brain
    read the mail depended on which connector happened to be added first (the owner, 2026-09-24: "first
    connected should not matter").

    ...but only a brain that RUNS here. A fresh install was pinned to claude whether or not Claude Code was
    installed, so a Docker image given an Anthropic key per the docs filed every message "AI triage failed
    ('claude' not found on PATH)" while the checklist said it ran on the key. So: a default brain the OWNER
    chose is taken at its word even when it does not start (the checklist says so - it is not swapped behind
    their back); one nobody chose - blank, or written by the startup migration - is used only when it starts,
    and otherwise gives way to an AI connector that can answer. '' when there is neither: no brain yet."""
    saved = str(store.get_setting('default_brain') or '').strip()
    saved = '' if is_card(saved) else saved          # an AI card chosen for CODING says nothing of what a blank light job runs on
    key = saved or default_brain(store)
    brains = dict(connection_brains(store))
    conn = brains.get(key) if key else None
    pick = f'cli:{key}' if conn else ''
    # a default the OWNER named is taken at its word, connected or not; one nobody chose only when it is ready (ready_brains)
    chosen = bool(saved) and store.setting_writer('default_brain') != 'migration'
    if pick and chosen: return pick
    ready = ready_brains(store)
    if pick and key in ready: return pick
    # ...any OTHER connected CLI that is ready: an install with only Codex (or Gemini) read "no brain" over a CLI that worked -
    # every mail awaited triage (a first-run log, 2026-10-14)
    other = '' if chosen else next((f'cli:{k}' for k in ready), '')
    if other: return other
    c = ready_connector(store)
    return f"connector:{c['ConnectorId']}" if c else ''


def brain_for(store, role: str) -> str:
    """The CLI that runs one role's coding pane - the one resolver's (resolve_brain), the role's own brain (profile_brains) first. A
    profile never PINS a brain: this is a setting keyed BY a profile, and what it names is a brain - never a model, never an effort."""
    return resolve_brain(store, 'coding', cli_only=True, role=role)[4:]


def brain_chain(store, first: str = None, cfg: dict = None) -> list:
    """The brains to try, in order: the chosen one, then the configured backups.

    A chain of BRAINS needs no dedupe. `agent_chain` had to skip candidates whose `cli_of` it had
    already seen, because a list of roles was really a list of brains and trying claude three times
    under coding/researcher/analyst is not failover. Brains are distinct by construction.

    `backup_brains=*` is the resilient default: every other configured connection, in the owner's
    own order. A CSV narrows and orders it explicitly."""
    from . import config
    cfg = config.load() if cfg is None else cfg
    known = list(cfg.get('cli_connections') or {})
    head = str(first or resolve_brain(store, 'coding', cli_only=True)[4:] or '').strip()
    setting = str(store.get_setting('backup_brains') or '').strip()
    # ...but never one whose own test FAILED: a CLI the person never got signed in is no backup for anything
    backups = [k for k in known if cli_tests(store).get(k) is not False] if setting == '*' else [x.strip() for x in setting.split(',') if x.strip()]
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
    if str(store.get_setting('default_brain') or '').strip(): return False
    key = default_brain(store)
    # a brain that does not start here is not what it "ran yesterday": persisting one pinned every blank
    # brain setting to a missing CLI. Left blank, the next start adopts it once it is installed.
    if not key or not brain_ready(store, key): return False
    store.set_setting('default_brain', key, 'migration')
    return True


def default_ask(store) -> dict:
    """THE DEFAULT AI IS NEVER CHOSEN SILENTLY (the owner, 2026-11-11: "never change from what's in settings"). A start names the
    brain an install runs on (above) - with one CLI that is no choice at all; with several it took the first that was ready, and
    a day of work ran on a tool nobody picked. So while more than one CLI runs here and the default is nobody's own - blank, or
    written by a start - the one question is owed: {'runs': what work is on meanwhile, 'options': the CLIs}. {} once the owner
    chose (the setting's writer is theirs), and with a single CLI. It asks; it never writes."""
    ready = ready_brains(store)
    v = str(store.get_setting('default_brain') or '').strip()
    if len(ready) < 2 or (v and store.setting_writer('default_brain') != 'migration'): return {}
    from .brainroute import _and, _said, cooldowns
    name = lambda k: _said(store, f'cli:{k}')
    # every CLI that can take work, one resting on its limit with the time it is back - and one left out says why, with its way back
    cold, tests = cooldowns(store), cli_tests(store)
    names = [name(k) + (f" (resting until {clock(cold[f'cli:{k}'])})" if f'cli:{k}' in cold else '') for k in ready]
    out = [name(k) for k, c in connection_brains(store) if tests.get(k) is False and runs_here(c)]
    one, runs = len(out) == 1, default_brain(store)
    # ...and where the one it took is itself resting, the work is on it only once it is back: the card's RUNS line names what has it now
    facts = (f"{_and(names)} are {'both' if len(names) == 2 else 'all'} connected and you have not chosen between them, so work runs on "
             f"{name(runs)}, the first one ready{', once it is back' if f'cli:{runs}' in cold else ''}."
             + (f" {_and(out)} {'is' if one else 'are'} left out: {'its' if one else 'their'} last test failed - press Test on "
                f"{'it' if one else 'them'} under Connections." if out else ''))
    # one set of facts for the bell and the Settings card; each ends with the move where it is read (`detail` the bell's, `note` the card's)
    return {'runs': runs, 'options': ready, 'title': 'Choose your default AI', 'detail': f'{facts} Choose one in Settings, on the {ASK_CARD} card.',
            'note': f'{facts} Choose one in the list above - choosing {name(runs)} again counts.'}


ASK_CARD = 'Coding agent'      # the card that holds default_brain (aidefaults.SLOTS)


BRAIN_SETTINGS = ('triage_ai', 'triage_backup_ai', 'concierge_ai', 'assistant_ai', 'judge_ai')


def migrate_brain_settings(store, cfg: dict = None) -> int:
    """EVERY SAVED BRAIN NAMES A TOOL (the owner, 2026-10-15: no profile is a brain - "it's models or cli tools only").
    A pick saved as `cli:<profile>` - the Assistant's old pick named the coding profile - becomes the tool that profile
    ran on, `cli:claude`; a blank coding brain takes the one the legacy `default_agent` profile ran; and each saved chat's pick
    follows, with its context key, so a chat that could resume still does. Returns how many it rewrote; a second run, none."""
    from . import config, continuity
    cfg = config.load() if cfg is None else cfg
    conns = cfg.get('cli_connections') or {}
    def fix(v):
        out = []
        for p in str(v or '').split(','):
            k = brain_key(store, p.strip(), cfg) if p.strip().startswith('cli:') else ''
            out.append(f'cli:{k}' if k in conns and p.strip()[4:] not in conns else p)
        return ','.join(out)
    n = 0
    for k in BRAIN_SETTINGS:
        v = str(store.get_setting(k) or '')
        if v and (new := fix(v)) != v: store.set_setting(k, new, 'migration'); n += 1
    if not str(store.get_setting('default_brain') or '').strip() and (key := default_brain(store)) in conns:
        store.set_setting('default_brain', key, 'migration'); n += 1
    for row in store._rows("SELECT * FROM session_resume WHERE Pick LIKE 'cli:%'"):
        new = fix(row['Pick'])
        if new == row['Pick']: continue
        live = row['ContextKey'] == continuity.context_key(store, row['Pick'], row['Model'])
        store.save_session(row['TaskId'], new, row['Model'], row['NativeId'],
                           continuity.context_key(store, new, row['Model']) if live else row['ContextKey'])
        n += 1
    return n


def layer_profiles(cfg: dict, store) -> bool:
    """A PROFILE IS INSTRUCTIONS LAYERED ON ANY BRAIN (the owner, 2026-10-15: "profiles have nothing to do with brains. they are
    layered on top of any brain tool"; the coding profile is just a profile). Once, at start:

    - the coding brain is named outright (default_brain) from the legacy `default_agent` profile, and that setting goes;
    - a profile's own `provider` leaves it: one on another CLI than the default becomes that role's brain override
      (profile_brains), so nothing runs anywhere new, and the rest simply run on the default brain;
    - the shipped coding profile's old name becomes `coding` - its config, its row, its document (now CODING.md), the tasks and
      transcripts that name it, the settings that do. Only when no `coding` exists yet, so an owner's own is never overwritten.
    Returns whether config.toml changed (the caller saves it)."""
    agents = cfg.setdefault('agents', {})
    before = json.dumps(agents, sort_keys=True, default=str)
    migrate_brain_settings(store, cfg)          # first: a `cli:<profile>` pick is read as its tool while that profile and its provider exist
    if not str(store.get_setting('default_brain') or '').strip():
        key = default_brain(store)
        if key and key in (cfg.get('cli_connections') or {}): store.set_setting('default_brain', key, 'migration')
    if str(store.get_setting('default_agent') or '').strip(): store.set_setting('default_agent', '', 'migration')
    dflt = str(store.get_setting('default_brain') or '').strip()
    try: over = json.loads(store.get_setting('profile_brains') or '{}')
    except ValueError: over = {}
    over = over if isinstance(over, dict) else {}
    moved = dict(over)
    for name, prof in agents.items():
        provider = str(prof.pop('provider', '') or '')
        if provider.startswith('cli:') and provider[4:] != dflt and name not in moved: moved[name] = provider[4:]
    if 'coder' in agents and 'coding' not in agents:
        agents['coding'] = agents.pop('coder')
        if 'coder' in moved: moved['coding'] = moved.pop('coder')
        _rename_coding_profile(store)
    for prof in agents.values():
        if str(prof.get('rules_doc') or '') == 'coder': prof['rules_doc'] = 'coding'
    if 'coding' in agents: _retire_old_name(store)
    if moved != over: store.set_setting('profile_brains', json.dumps(moved) if moved else '', 'migration')
    return json.dumps(agents, sort_keys=True, default=str) != before


def _rename_coding_profile(store) -> None:
    """The store half of the rename to `coding`: the row, its rules document (an edited one keeps its edits), and every place that
    names the profile - task assignees, transcripts, settings. History included: a closed task read the old name on its card."""
    row = store.get_agent('coder')
    if row and not store.get_agent('coding'):
        try: conf = json.loads(row.get('Config') or '{}')
        except ValueError: conf = {}
        if conf.get('rules_doc') == 'coder': conf['rules_doc'] = 'coding'
        conf.pop('provider', None)
        store.upsert_agent('coding', row.get('Kind') or 'coding', row.get('Runner') or 'cli', json.dumps(conf))
        store._exec('UPDATE agent SET Active=? WHERE Name=?', (row.get('Active', 1), 'coding'))
    store.delete_agent('coder')
    # the store seeds an untouched CODING.md from the template when it opens - BEFORE this runs - so "already there" is not
    # the owner's; only their own edits on either side decide, and an edited CODER.md wins over a fresh template copy
    doc, now = store.get_doc_row('coder'), store.get_doc_row('coding')
    # (an untouched copy has nothing to carry: the store seeded CODING.md from the template already)
    if doc and (not now or now.get('UpdatedBy') == 'template') and doc.get('UpdatedBy') != 'template':
        store.save_doc('coding', doc['Content'], doc.get('UpdatedBy') or 'owner')
    if doc: store.delete_doc('coder')
    _retire_old_name(store)


# A profile's old name -> its name now. The notes and runs it wrote are relabelled (_retire_old_name); a read receipt hashed
# over the old label still counts (processing_reads._was), or every task the profile ever worked came back unread.
RENAMED = {'coder': 'coding'}


def _retire_old_name(store) -> None:
    """Every place that still names the coding profile by its old name. Not only on the rename: old code running beside a
    migrated store went on assigning new tasks to it, and those failed to start with "unknown agent" (2026-10-16) - so this
    runs on every start, and it is three cheap UPDATEs that touch nothing once the name is gone."""
    if store.get_agent('coder'): return                     # an owner's own profile by that name is theirs
    store._exec("UPDATE task SET Assignee='agent:coding' WHERE Assignee='agent:coder'")
    # who did what keeps its meaning under the new name - the queue, runs, notes, the wall and votes; the audit log is left as written
    for table, col in (('transcript', 'Agent'), ('dispatchq', 'Agent'), ('run', 'AgentName'), ('comment', 'Actor'),
                       ('boardnote', 'Agent'), ('outcome', 'Actor')):
        for old, new in RENAMED.items():
            try: store._exec(f"UPDATE {table} SET {col}=? WHERE {col}=?", (new, old))
            except Exception: pass                          # a table an older or in-memory store does not have
    try: store._exec("UPDATE OR IGNORE lore_vote SET Actor='coding' WHERE Actor='coder'"); store._exec("DELETE FROM lore_vote WHERE Actor='coder'")
    except Exception: pass
    # ...and a start that FAILED on the old name has no cause left once it is gone: its row kept saying "unknown agent: coder - Start
    # fails the same way until it is fixed" over a task Start would now run (2026-10-16). It goes; the task reads not started.
    try: store._exec("DELETE FROM dispatchq WHERE State='failed' AND LastError LIKE 'unknown agent: coder%'")
    except Exception: pass
    if str(store.get_setting('default_profile') or '') == 'coder': store.set_setting('default_profile', 'coding', 'migration')
    # ...and the reports that name it: one with agent `coder` failed "no CLI agent named 'coder'" after the rename, and one whose
    # brain was `cli:coder` would have too (2026-10-16). The agent becomes `coding`; the brain, the tool coding runs on.
    tool = str(store.get_setting('default_brain') or '').strip()
    for src in store.list_sources(active_only=False):
        if src.get('Channel') != 'report': continue
        try: was = json.loads(src.get('ConfigJson') or '{}')
        except ValueError: continue
        if not isinstance(was, dict): continue
        now = {**was, **({'agent': 'coding'} if was.get('agent') == 'coder' else {})}
        if tool and 'cli:coder' in str(was.get('ai_brain') or '').split(','):
            now['ai_brain'] = ','.join(f'cli:{tool}' if p == 'cli:coder' else p for p in str(was['ai_brain']).split(','))
        if now != was: store.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps(now)}, 'migration')


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


def routed_role(store, kind: str) -> str:
    """Which ROLE a verdict lands on - never which brain runs it. Coding has exactly one, the coding agent's row (coding_role): it
    is WRITTEN rather than left implied, because an `agent:` Assignee is what puts the row in the pipe's `queued` lane - "handed to an
    agent, not started yet" (processing_unread, processing_all). General work is nobody's: it runs on the assistant (general._prompt).
    `kind: task` leaves the job on the owner's list, so no worker at all."""
    return coding_role(store) if str(kind or '') == 'coding' else ''


def repair_role_assignees(store) -> int:
    """Tasks routed to a BRAIN before roles and brains were separated. `Assignee` holds a role, so
    a coding task pointed at anything else is corrected to the coding role - TQ-0585 held
    `agent:copilot` and TQ-0586 held `agent:analyst` on coding work. A person owning a task
    outranks any routing (`mine` put them there) and general work keeps its specialist, so both are
    left alone. A second run corrects nothing.

    CLOSED work is history, not a routing decision to fix: `transcript.Agent` says copilot or devin
    actually worked those, and rewriting the stamp to the coding profile would make the task claim otherwise.
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


def parent_of(u: dict) -> str:
    """The helper call an ACP tool call runs under, when its adapter says (claude-code-acp: _meta.claudeCode.parentToolUseId) - so the
    helper's own steps nest under its row instead of interleaving with the main agent's (the owner, 2026-11-06: parallel work read wrong)."""
    m = u.get('_meta') or {}
    return str((m.get('claudeCode') or {}).get('parentToolUseId') or m.get('parentToolUseId') or m.get('parentToolCallId') or '')


def result_text(raw) -> str:
    """What a tool answered, in any shape an adapter sends it as `rawOutput`: words; an MCP CallToolResult (`content` blocks, else its
    `structuredContent`); codex-acp's `{result, error}` around one; a command's `{output}`. ONE READER (the HIPAA walk, 2026-11-21): only a string
    was read, so on Codex every Taskuary tool answered nothing - a show's view, a refusal's words, a file's name - and the page drew no chart."""
    if raw is None: return ''
    if isinstance(raw, str): return raw
    if isinstance(raw, list): return chr(10).join(t for t in (result_text(x) for x in raw) if t)
    if not isinstance(raw, dict): return str(raw)
    if raw.get('type') == 'text': return str(raw.get('text') or '')
    if 'result' in raw or 'error' in raw:
        err = raw.get('error')
        return chr(10).join(t for t in (result_text(raw.get('result')), str(err.get('message') or err) if isinstance(err, dict) else str(err or '')) if t)
    if isinstance(raw.get('content'), list) and (t := result_text(raw['content'])): return t
    if raw.get('structuredContent') is not None: return json.dumps(raw['structuredContent'], ensure_ascii=False)
    for k in ('output', 'stdout', 'formatted_output', 'aggregated_output', 'text'):
        if isinstance(raw.get(k), str) and raw[k]: return raw[k]
    return ''


class ACPSteps:
    """ACP session/update as the trace events the argv road emits - tool_call with its arguments, tool_result with its output, progress for
    what it said and thought - for what reads a run's TRACE: the pane, the Board's witness, the transcript, a stopped turn's account.

    THE CHAT NEVER READS THIS (the owner, 2026-11-23: adopt the open-source model): it draws the agent's own updates, each call's row patched in
    place as they come (chatlog.feed, road 'acp'). So nothing is held back to look right there. A call is traced once, when it has ended - by
    the tool's own name (Claude's `Read`, `Bash`, `mcp__taskuary__my_task`; Codex's command) with the input it ended on, its result beside it -
    and its title, as it goes, is the run's live line. Words and thoughts arrive a token at a time and are traced as whole paragraphs. `flush`
    at the end of the turn ends whatever is still open, so nothing spins after the turn is over."""

    def __init__(self, trace, name: str, held: dict = None):
        self.trace, self.name, self.held = trace, name, held if held is not None else {}
        self.calls, self.said, self.thought, self.live_at, self.mid = {}, [], [], -1e9, None

    # ...AND WHAT IT IS THINKING IS SAID AS IT GROWS (the owner, 2026-11-16: "Thinking..." for three minutes with nothing else): about once a
    # second the newest words of the thought go out as a `live` snapshot - the working line's (chatlog._now); a thought is never a row
    LIVE_EVERY, LIVE_N = 1.0, 600
    def _live(self, name: str, parts: list):
        if (now := time.monotonic()) - self.live_at < self.LIVE_EVERY: return
        # ...the summary taken out of the whole text BEFORE the newest words are kept (2026-11-17): cut first, a block whose opening tag fell
        # off the front read as words - '..."], "nothing_left": false, "answ' on the writing line - and nothing after could tell it apart
        if (t := without_summary(''.join(parts)).strip()): self.live_at = now; self.trace('live', name, t[-self.LIVE_N:])

    # ── words ───────────────────────────────────────────────────────────────────────────────
    def _words(self):
        if self.thought:
            t = ''.join(self.thought).strip(); self.thought = []
            if t: self.trace('progress', 'thinking', t)
        if self.said:
            t = ''.join(self.said).strip(); self.said = []
            if t: self.trace('progress', 'text', t); self.trace('live', self.name, ' '.join(t.split())[:400])

    # ── tool calls ──────────────────────────────────────────────────────────────────────────
    def _merge(self, u: dict) -> dict:
        iid = str(u.get('toolCallId') or f'acp-{len(self.calls)}')
        c = self.calls.setdefault(iid, {'id': iid, 'raw': {}, 'out': [], 'done': False})
        if isinstance(u.get('rawInput'), dict) and u['rawInput']: c['raw'] = dict(u['rawInput'])
        for k in ('kind', 'name', 'status'):
            if u.get(k): c[k] = u[k]
        if u.get('title') and u['title'] != c.get('title'): c['title'] = u['title']; self.trace('live', self.name, f"→ {u['title']}"[:400])
        if (tn := ((u.get('_meta') or {}).get('claudeCode') or {}).get('toolName')): c['tool'] = tn
        if (par := parent_of(u)): c['parent'] = par
        if u.get('locations'): c['locations'] = u['locations']
        for b in u.get('content') or []:
            if isinstance(b, dict) and b.get('type') == 'content': c['text'] = acp_mod._text_of(b.get('content'))
        meta = u.get('_meta') or {}
        if (d := (meta.get('terminal_output_delta') or {}).get('data')) and sum(map(len, c['out'])) < 20000: c['out'].append(str(d))
        if 'terminal_exit' in meta: c['exit'] = (meta['terminal_exit'] or {}).get('exit_code')
        if (o := result_text(u.get('rawOutput'))): c['raw_out'] = o
        return c

    @staticmethod
    def _call(c: dict) -> tuple:
        "(the tool's name, its arguments) in the vocabulary describeCall reads - the same names stream-json and codex JSONL use."
        raw, kind = dict(c['raw']), c.get('kind') or ''
        if raw.get('type') == 'webSearch':                     # codex: one item for a search and for a page it opened
            act = raw.get('action') or {}
            if act.get('type') in ('openPage', 'findInPage'): return 'fetch', {'url': act.get('url') or raw.get('query') or ''}
            return 'web search', {'query': raw.get('query') or act.get('query') or ''}
        if raw.get('server') and raw.get('tool'):              # codex MCP: {server, tool, arguments} - use_tool's as the tool it ran
            from .agenttools import as_called
            tool, a = as_called(raw['server'], raw['tool'], dict(raw.get('arguments') or {}))
            return f"mcp__{raw['server']}__{tool}", dict(a or {})
        paths = [l.get('path') for l in c.get('locations') or [] if isinstance(l, dict) and l.get('path')]
        if paths and not any(raw.get(k) for k in ('path', 'file_path', 'absolute_path', 'filePath')): raw['path'] = paths[0]
        if len(paths) > 1 and kind == 'move': raw.setdefault('to', paths[1])
        if c.get('title'): raw.setdefault('title', c['title'])
        return c.get('tool') or c.get('name') or kind or c.get('title') or 'tool', raw

    def _finish(self, c: dict, failed: bool = None):
        if c['done']: return
        c['done'] = True
        name, args = self._call(c)
        self.trace('tool_call', name, {'tool_call_id': c['id'], 'args': args, **({'parent': c['parent']} if c.get('parent') else {})})
        out = ''.join(c['out']).strip() or c.get('text') or c.get('raw_out') or ''
        bad = (c.get('status') == 'failed' or c.get('exit') not in (None, 0)) if failed is None else failed
        if c['id'] in self.held: out, bad = self.held[c['id']], True          # Taskuary's own answer, not the adapter's "user refused"
        self.trace('tool_result', c['id'], {'result': out, 'is_error': bool(bad)})

    def asked(self, tc: dict):
        """A permission request's copy of the call (a ToolCallUpdate, the spec's): it fills what the call's own updates left out - Codex asks
        for a read it announced with no input - never what they said (it asks with its own kind, the command wrapped in powershell)."""
        if not isinstance(tc, dict) or not tc.get('toolCallId'): return
        c = self.calls.get(str(tc['toolCallId'])) or {}
        self._merge({k: v for k, v in tc.items() if k in ('toolCallId', 'locations') or (k == 'rawInput' and not c.get('raw')) or not c.get(k)})

    def __call__(self, u: dict):
        kind = u.get('sessionUpdate')
        if kind == 'agent_message_chunk':
            # ...ONE MESSAGE IS ONE STEP, as the answer (acp.prompt) and the chat (conversation.acp_steps) split them
            if self.thought or (self.said and u.get('messageId') != self.mid): self._words()
            self.mid = u.get('messageId')
            self.said.append(acp_mod._text_of(u.get('content'))); return
        if kind == 'agent_thought_chunk':
            if self.said: self._words()
            self.thought.append(acp_mod._text_of(u.get('content'))); self._live('thinking', self.thought); return
        if kind in ('tool_call', 'tool_call_update'):
            self._words()
            c = self._merge(u)
            if u.get('status') in ('completed', 'failed'): self._finish(c)
            return
        if kind == 'plan':
            self._words()
            steps = [str((e or {}).get('content') or '') for e in u.get('entries') or []]
            if any(steps):
                iid = f'plan-{sum(1 for k in self.calls if k.startswith("plan-"))}'; self.calls[iid] = {'id': iid, 'done': True}
                self.trace('tool_call', 'update_plan', {'tool_call_id': iid, 'args': {'plan': [s for s in steps if s]}})
                self.trace('tool_result', iid, {'result': ''})

    def flush(self, stop: str = None):
        "The turn is over: what it said is traced, and every call still open ends - done at a normal end, failed at any other."
        self._words()
        for c in list(self.calls.values()):
            if not c['done'] and (c['raw'] or c.get('title')): self._finish(c, failed=None if c.get('status') in ('completed', 'failed') else stop not in (None, 'end_turn'))


def acp_tracer(trace, name: str, held: dict = None) -> ACPSteps: return ACPSteps(trace, name, held)


# ── the ACP road ─────────────────────────────────────────────────────────────────────────────────────────────────────────────
ACP_SETTING = 'acp_cli'
_FELL_BACK: set = set()
# THE STORE AND TASK A RUN IS FOR, beside run_cli's arguments rather than in them: the ACP road's permission answers need both
# (gate - the send filter's verdicts, a step held on this task), and run_cli's signature is the one every caller and test fake
# shares. make_cli_llm sets it around its call; a run with none reads the switch's default and holds nothing on a task.
_RUN = contextvars.ContextVar('taskuary_run', default=(None, None))


@contextlib.contextmanager
def run_context(store, task_id=None):
    tok = _RUN.set((store, task_id))
    try: yield
    finally: _RUN.reset(tok)


def acp_on(store) -> bool:
    "The owner's 'Run CLI agents over ACP' (Settings, Agents). On unless switched off; a run with no store reads the default."
    try: v = store.get_setting(ACP_SETTING) if store is not None else None
    except Exception: v = None
    return str('1' if v is None else v).strip().lower() not in ('0', 'false', 'off', 'no')


def _acp_road(profile: dict, store=None) -> bool:
    "Does this run go over ACP: a run marked for it (llm: a general agent's run with hands), the switch on, and a way to launch it."
    if not (profile.get('acp_ok') and acp_on(store if store is not None else _RUN.get()[0])): return False
    # ...never a stranger's run, whatever acp_ok says: its trimmed environment (strict_env) marks the floor argv carries (llm.make_cli_llm)
    if profile.get('strict_env'): return False
    return bool(profile.get('acp') or profile.get('acp_cmd') or clis_mod.acp_adapter(profile.get('cmd') or ''))


# A HEADLESS CLAUDE'S ARGV, AS WHAT THE ADAPTER TAKES. Everything make_cli_llm put on the command line still has to reach the run:
# Taskuary's own tools (--mcp-config), the owner's send tools left out (--disallowedTools), the agent's instructions (the system
# prompt file), the browser hold (--settings). The adapter takes them as Claude Agent SDK options in _meta.claudeCode.options;
# the ones the protocol owns itself - print mode, the output format, the bypass, the model, resume - are its, and dropped.
_CLAUDE_DROP = {'-p', '--print', '--verbose', '--dangerously-skip-permissions', '--allow-dangerously-skip-permissions', '--include-partial-messages'}
_CLAUDE_DROP_VALUED = {'--output-format', '--input-format', '--model', '--resume', '-r', '--permission-mode', '--fallback-model'}
_CODEX_DROP = {'exec', 'e', '--json', '--skip-git-repo-check', '--dangerously-bypass-approvals-and-sandbox', '--dangerously-bypass-hook-trust', '--full-auto'}
_CODEX_DROP_VALUED = {'--sandbox', '-s', '--model', '-m', '--ask-for-approval', '-a'}


def _read(path) -> str:
    try: return Path(path).read_text(encoding='utf-8')
    except OSError: return ''


def claude_acp_options(args: list) -> dict:
    """claude's -p argv -> the SDK options the claude-agent-acp adapter spreads into its query (_meta.claudeCode.options)."""
    opt, extra, it, back = {}, {}, iter(list(args or [])), []
    # ...`back`: an argument read ahead and handed back. A flag with no value read the next one to see - and then rebound `it`, which the
    # loop no longer read: every option after `--strict-mcp-config` was dropped, a chat agent's --settings (its hooks) among them
    while (a := back.pop() if back else next(it, None)) is not None:
        a = str(a)
        if a in _CLAUDE_DROP: continue
        if a in _CLAUDE_DROP_VALUED: next(it, None); continue
        if not a.startswith('-'): continue                                        # a prompt or a stray value: never an option
        if a == '--disallowedTools': opt.setdefault('disallowedTools', []).extend(x for x in str(next(it, '')).split(',') if x)
        elif a == '--allowedTools': opt.setdefault('allowedTools', []).extend(x for x in str(next(it, '')).split(',') if x)
        elif a == '--append-system-prompt-file': opt['systemPrompt'] = {'type': 'preset', 'preset': 'claude_code', 'append': _read(next(it, ''))}
        elif a == '--system-prompt-file': opt['systemPrompt'] = _read(next(it, ''))
        elif a == '--add-dir': opt.setdefault('additionalDirectories', []).append(str(next(it, '')))
        elif a == '--settings': opt['settings'] = str(next(it, ''))
        elif a == '--setting-sources': opt['settingSources'] = [x for x in str(next(it, '')).split(',') if x]
        else:
            # --mcp-config <file>, --strict-mcp-config: passed through as Claude's own flags (the SDK's extraArgs), so the CLI
            # reads the file and expands its ${TASKUARY_TOKEN} from the environment - no token is written anywhere
            nxt = next(it, None)
            if nxt is not None and not str(nxt).startswith('-'): extra[a.lstrip('-')] = str(nxt)
            else:
                extra[a.lstrip('-')] = None
                if nxt is not None: back.append(nxt)
    if extra: opt['extraArgs'] = extra
    # ...and NO PREDICTED NEXT PROMPT (claude-agent-acp turns promptSuggestions on: one more model call after every turn, for a composer's gray
    # text nothing of Taskuary draws - the speed round, 2026-11-20)
    opt['promptSuggestions'] = False
    return opt


def _toml_value(v: str):
    try: import tomllib
    except ImportError: import tomli as tomllib
    try: return tomllib.loads(f'v = {v}')['v']
    except Exception: return v                                                   # a bare word: codex reads it as a string too


def codex_acp_config(args: list) -> dict:
    """codex exec's argv -> CODEX_CONFIG, which the codex-acp adapter hands Codex as the session's config: every `-c key=value`
    (Taskuary's MCP server with its headers named by env var, the owner's send tools disabled - agenttools.codex_args,
    sendfilter.codex_args) as the same dotted key. The rest is the protocol's: the mode replaces the sandbox and approval flags."""
    cfg, it = {}, iter(list(args or []))
    for a in it:
        a = str(a)
        if a in ('-c', '--config'):
            kv = str(next(it, ''))
            if '=' in kv: k, v = kv.split('=', 1); cfg[k.strip()] = _toml_value(v.strip())
        elif a in _CODEX_DROP_VALUED: next(it, None)
        elif a not in _CODEX_DROP and a.startswith('-'): logger.debug(f'acp: codex flag {a} has no ACP spelling - left out')
    return cfg


def acp_launch(profile: dict) -> dict:
    """How this profile's CLI is started as an ACP agent: {'cmd', 'env', 'mode', 'meta', 'adapter'}.
    A native CLI is its own binary with its ACP arguments (`gemini --acp`); claude and codex are their adapter (clis.ADAPTERS)
    driving the binary the owner already has - the one _resolve_cmd finds, so it is the same login, settings and hooks."""
    name, family = profile['cmd'], _cli_name(profile['cmd'])
    ad = {} if profile.get('acp') else clis_mod.acp_adapter(name)
    if not ad:
        cmd = _resolve_cmd(name) + list(profile.get('acp') or [])
        if profile.get('model'):
            from .climodels import split_pick
            model, _ = split_pick(profile['model'])
            if model: cmd += [profile.get('model_arg') or '--model', model]
        return {'cmd': cmd, 'env': {}, 'mode': '', 'meta': None, 'adapter': ''}
    # the adapter's own command when it is installed (`npm i -g` puts it on PATH: ~2.3 s a start quicker, measured), else npx, pinned
    own = pathcache.which(ad['bin'])
    # ...but only the PINNED one (acpadapter.runs_pinned): a global left by an older release speaks what that release spoke, so npx
    # fetches the pinned version instead and the card's line offers Update
    if own and not acpadapter.runs_pinned(ad, own): own = None
    # ...else TASKUARY'S OWN PINNED COPY (acpadapter.kept), fetched once behind the first start that had none - npx only until it is there
    if not own and not profile.get('acp_cmd') and not (own := acpadapter.kept(ad)): acpadapter.keep_soon(ad)
    # ...and no npx is a start failure, not a missing CLI: the owner's claude is there, and the argv road runs it (a machine with no
    # Node on PATH answered every general turn "'npx' not found on PATH" and nothing else - 2026-11-06)
    try: cmd = list(profile.get('acp_cmd') or ([own] if own else _resolve_cmd('npx') + ['-y', ad['pkg']]))
    except FileNotFoundError as e: raise acp_mod.ACPStartError(f"{ad['pkg']} cannot launch: {e}") from e
    cli = (_resolve_cmd(name) or [name])[-1]
    env = {k: v.replace('{cli}', cli) for k, v in ad['env'].items()}
    args = _own_settings(profile, name, list(profile.get('args') or clis_mod.preset_args(name) or []))
    meta = None
    if family == 'claude':
        opts = claude_acp_options(args)
        if opts: meta = {'claudeCode': {'options': opts}}
    elif family == 'codex':
        from .harness import OWNER_CLI_OFF, OFF_KEYS          # ...his own Codex starts with ChatGPT's apps and plugins off and no bundled skills - his -c keys after
        env['CODEX_CONFIG'] = json.dumps({**{f'features.{k}': False for k in OWNER_CLI_OFF}, **OFF_KEYS, **codex_acp_config(args)})
    return {'cmd': cmd, 'env': env, 'mode': ad['mode'], 'meta': meta, 'adapter': ad['pkg'], 'unnamed_own': bool(ad.get('unnamed_own'))}


def _long(cwd):
    """The folder by its real, long name. Codex's Windows sandbox refused every command in a folder named by its 8.3 short name
    (a temp folder under a long user name) with "Access to the path is denied", and the agent asked to escalate each one (2026-11-06)."""
    return os.path.realpath(cwd) if cwd and os.path.isdir(cwd) else cwd


def _acp_sig(launch: dict, cwd, env: dict) -> tuple:
    "What a kept connection was opened with: a different command, folder, environment's names, options or mode is a new one (clipool._sig)."
    return (tuple(launch['cmd']), str(cwd or ''), hash(tuple(sorted(env))), json.dumps(launch['meta'], sort_keys=True, default=str), launch['mode'])


# ...A CONVERSATION THE CLI NO LONGER HAS IS STARTED AFRESH (the owner's coding task, 2026-11-16: after a restart cut its turn, his next line drew
# only the CLI's own "No conversation found with session ID: ..." and the turn never ran): where the caller can carry the task over to a fresh
# one (`fresh_if_gone`), a resume the agent refuses opens a new conversation, said in one plain line, and the client says so (`fresh_from`)
GONE_LINE = 'Started a fresh session - the old one was gone.'
# ...ON EVERY ROAD (the general chat's ACP and command-line turns, a coding pane's terminal): the CLI's own words for a conversation it no longer
# has - a message format, read as structure (claude 2.1.326's; codex's, out of its binary) - never shown, said instead as GONE_LINE (said_afresh)
_GONE = re.compile(r'No conversation found with session ID|No saved session found with ID|no rollout found for (?:thread|conversation) id|thread not found:', re.I)
def gone(text) -> bool: return bool(_GONE.search(str(text or '')))

class Gone(RuntimeError):
    "The CLI no longer has the conversation the turn resumed: nothing ran, and the caller carries the task over to a fresh one (general.Session)."
    def __init__(self, resume=''): super().__init__(GONE_LINE); self.resume = resume or ''

def said_afresh(store, task_id) -> None:
    "The one plain line every road says when its conversation was gone and a fresh one carries the task on - Taskuary's note, never the CLI's error."
    if not (store and task_id): return
    from . import general, sessionrecord
    try: store.add_comment(task_id, sessionrecord.NOTE_ACTOR, general.ASSISTANT_TYPE, GONE_LINE)
    except Exception as e: logger.debug(f'task {task_id}: the fresh start was not said - {e}')

# A CONNECTOR STARTED AHEAD (the speed round, 2026-11-20: every new task's agent waited ~1 s for claude's adapter to start and initialise,
# before its session even began). Claude's adapter takes a session's own environment with the session (_meta.claudeCode.options.env -
# claude-agent-acp hands it to the CLI it starts), so the adapter process itself carries nothing of any task: one is started and
# initialised ahead, the next task's session opens on it, and the next is started behind it. One per launch, never shared.
_ACP_SPARE, _ACP_SPARE_LOCK = {}, threading.Lock()


def _spare_key(cmd, env: dict, timeout=None) -> str:
    # ...by what the process IS - its command and its environment - never how long its caller will wait on it, which is set as it is taken
    return hashlib.sha1(json.dumps([list(cmd), sorted(env.items())]).encode('utf-8')).hexdigest()[:16]


def _acp_ready(cmd, env: dict, timeout) -> None:
    "Start and initialise the next connector for this launch, in the background."
    key = _spare_key(cmd, env, timeout)
    def go():
        try:
            from . import config
            c = acp_mod.ACPClient(cmd[0], cmd[1:], cwd=str(config.home()), env=env, timeout=timeout); c.connect()
        except Exception as e: logger.debug(f'acp: no connector started ahead - {e}'); return
        with _ACP_SPARE_LOCK: old = _ACP_SPARE.pop(key, None); _ACP_SPARE[key] = c
        if old: old.close()
    threading.Thread(target=go, daemon=True, name='acp-spare').start()


def _acp_spare(cmd, env: dict, timeout):
    "The connector started ahead for this launch, initialised and alive - or None."
    with _ACP_SPARE_LOCK: c = _ACP_SPARE.pop(_spare_key(cmd, env, timeout), None)
    if c is not None and not c._alive: c.close(); c = None
    if c is not None and timeout: c.timeout = timeout
    return c


# THE FIRST START AFTER THE APP OPENS IS PAID FOR IN THE BACKGROUND (the owner, 2026-11-22: "still takes 40 seconds" under "Waiting for the agent
# to start"; timed: the first start's connect took 9.4 s, every later one under 4 s - the adapter and its CLI loading cold from disk). Each
# adapter a road here uses is started once, a while after launch, and let go once it answers: nothing is asked of it, nothing is kept
PRIME_AFTER = 20
def prime_adapters(wait: float = PRIME_AFTER) -> list:
    "Start and close each installed ACP adapter once (clis.ADAPTERS), so his first real start finds them warm. -> the ones primed."
    time.sleep(wait)
    from . import config
    done = []
    for name in clis_mod.ADAPTERS:
        try:
            if not _resolve_cmd(name): continue                  # ...a CLI this computer does not have needs no warm adapter
            # ...and one NOT YET KEPT is fetched now, not behind his first ask (timed 2026-11-22: through npx a Claude start's connect took 3-10 s,
            # from the kept copy 0.6-0.8 s); acp_launch starts that fetch, and the prime waits for it to land before warming the copy itself
            l = acp_launch({'cmd': name, 'args': clis_mod.preset_args(name) or []})
            ad = clis_mod.ADAPTERS[name]
            for _ in range(60):
                if acpadapter.kept(ad) or (pathcache.which(ad['bin']) and acpadapter.runs_pinned(ad, pathcache.which(ad['bin']))): break
                time.sleep(5)
            l = acp_launch({'cmd': name, 'args': clis_mod.preset_args(name) or []})
            # ...and where its road keeps a connector started ahead (claude's: _acp_open `spare`), the first one is that spare, with the very
            # environment a task's start asks for (spawn_env, the adapter's own) - timed 2026-11-22: the first Claude task's connect took 7.6 s
            # beside a prime that had just warmed a different process
            if name == 'claude':
                _acp_ready(l['cmd'], {**spawn_env({}), **l['env']}, 120); done.append(name)
                logger.info(f'acp: {name} connector started ahead - the first task takes it ready'); continue
            t0 = time.time(); c = acp_mod.ACPClient(l['cmd'][0], l['cmd'][1:], cwd=str(config.home()), env={**os.environ, **l['env']}, timeout=120)
            try: c.connect(); done.append(name); logger.info(f'acp: {name} adapter primed in {time.time() - t0:.1f}s - the first task start finds it warm')
            finally: c.close()
        except Exception as e: logger.debug(f'acp: {name} adapter not primed - {e}')
    return done
_prime_adapters = prime_adapters      # ...the real one, for its own test (tests/conftest.py turns priming off for every server a test starts)


@atexit.register
def _close_spares():
    with _ACP_SPARE_LOCK: gone = list(_ACP_SPARE.values()); _ACP_SPARE.clear()
    for c in gone: c.close()


def _acp_open(name: str, launch: dict, cwd, env: dict, resume, timeout, trace, fresh_if_gone: bool = False, base: dict = None):
    """A connected session, ready for a prompt: started, initialized, the conversation opened (resumed where there is one),
    its mode, model and effort set. ACPStartError for anything before the session exists - nothing has run, so run_cli takes
    the argv road instead. `base`: the environment with nothing of this task in it - given, claude's adapter runs on it (one started
    ahead where there is one) and the task's own part rides with its session."""
    # ...EACH PHASE OF A START TIMED, in the log (the owner, 2026-11-22: "still takes 40 seconds" under "Waiting for the agent to start"): spawn,
    # connect, session - so where a slow start spends its seconds is read, never guessed
    t0 = time.time(); at = {}
    spare = base is not None and bool(launch['adapter']) and _cli_name(name) == 'claude'
    if spare:
        own = {k: v for k, v in env.items() if base.get(k) != v}
        launch = {**launch, 'meta': {'claudeCode': {**((launch['meta'] or {}).get('claudeCode') or {}),
                                                    'options': {**(((launch['meta'] or {}).get('claudeCode') or {}).get('options') or {}), 'env': own}}}}
        client, env = _acp_spare(launch['cmd'], base, timeout), base
    else: client = None
    try: client = client or acp_mod.ACPClient(launch['cmd'][0], launch['cmd'][1:], cwd=cwd, env=env, timeout=timeout)
    except PermissionError as e:
        if launch['adapter']: raise acp_mod.ACPStartError(f"{launch['adapter']} was refused: {e}") from e   # the adapter, not the CLI
        raise FileNotFoundError(denied_msg(name, launch['cmd'][0], e)) from e
    at['spawn'] = time.time()
    client.unnamed_own = bool(launch.get('unnamed_own'))           # ...its adapter's own lines, told from the model's (acp.prompt)
    if spare: _acp_ready(launch['cmd'], base, timeout)              # ...the next task's, started now
    try:
        caps = client._caps if client._caps else client.connect()
        at['connect'] = time.time()
        try:
            if resume and (caps.get('loadSession') or client.can_resume()):
                try: client.load_session(resume, cwd, meta=launch['meta'])
                except acp_mod.ACPAgentError as e:
                    if not fresh_if_gone or _SIGNED_OUT.search(str(e)): raise
                    logger.info(f'acp: {name} could not reopen {resume} ({str(e)[:160]}) - a fresh conversation instead')
                    client.new_session(cwd, meta=launch['meta']); client.fresh_from = resume      # the caller says it once (said_afresh)
            else:
                if resume: trace('progress', 'acp', f'{name} cannot reload a session; starting a fresh one')
                client.new_session(cwd, meta=launch['meta'])
        except acp_mod.ACPAgentError as e:
            # a CLI that is not signed in answers session/new in its own words: said as a sign-in, not as a broken app (2026-10-25)
            if f := failure_of(name, str(e), launch['cmd'][0]): raise f from e
            raise acp_mod.ACPStartError(f'session: {e}') from e
        if launch['mode'] and not client.set_option('mode', launch['mode']):
            logger.warning(f"acp: {name} has no '{launch['mode']}' mode - it runs in {client.option('mode').get('currentValue') or 'its own'}")
        done = time.time()
        logger.info(f"acp: {name} opened in {done - t0:.1f}s - spawn {at.get('spawn', t0) - t0:.1f}s, connect {at.get('connect', t0) - at.get('spawn', t0):.1f}s, "
                    f"session {done - at.get('connect', t0):.1f}s{' (resumed)' if resume else ''}")
        return client
    except BaseException:
        client.close(); raise


# OUR MODEL ID, THE AGENT'S SPELLING (the owner's chat, 2026-11-06: "claude offers no model 'claude-opus-5-5' over ACP - it runs on opus"
# as an agent step). claude-agent-acp offers aliases - default, opus, sonnet, haiku, opus[1m] - and may offer dated ids; codex-acp offers
# Codex's own ids. Ours is matched to the closest one quietly: plumbing is a debug line, never the owner's chat. Only a model the agent
# has nothing near - one this sign-in cannot run - is said, in plain words.
_FAMILIES = ('opus', 'sonnet', 'haiku')
def _bare(v) -> str: return re.sub(r'(\[[^\]]*\]|-\d{8})$', '', str(v or '').lower())
def _parts(v) -> list: return re.split(r'[^a-z0-9]+', str(v or '').lower())


def offered_model(want: str, vals: list) -> str:
    """The value the agent offers for model `want`: the same id; else it without a date or [1m] suffix; else claude's family
    (claude-opus-5-5 -> opus, the bare alias first); else the offered id that begins `want` or that `want` begins. '' when none is near."""
    vals, w = [str(v) for v in vals or [] if v], _bare(want)
    if not (w and vals): return ''
    if (x := next((v for v in vals if v.lower() == str(want).lower()), '')): return x
    if (same := [v for v in vals if _bare(v) == w]): return min(same, key=lambda v: ('[' in v, len(v)))
    if (fam := next((f for f in _FAMILIES if f in _parts(w)), '')):
        c = [v for v in vals if fam in _parts(v)]
        return min(c, key=lambda v: (v.lower() != fam, '[' in v, len(v))) if c else ''
    near = [v for v in vals if _bare(v).startswith(w) or w.startswith(_bare(v))]
    return min(near, key=lambda v: (abs(len(_bare(v)) - len(w)), len(v))) if near else ''


def offered_effort(want: str, vals: list) -> str:
    "The offered effort nearest `want` on the one scale (brainroute.EFFORTS), a lower one on a tie - '' when it offers none we know."
    from .brainroute import EFFORTS
    vals = [str(v) for v in vals or [] if v]
    if want in vals: return want
    if want not in EFFORTS: return ''
    known = [v for v in vals if v in EFFORTS]
    return min(known, key=lambda v: (abs(EFFORTS.index(v) - EFFORTS.index(want)), EFFORTS.index(v))) if known else ''


def _acp_gears(client, profile: dict, name: str, trace):
    """The run's model and effort as session config options, each as the agent spells it (offered_model, offered_effort). A model it has
    nothing near is said to the owner; everything else is a debug line, and it runs on its own."""
    if not profile.get('model'): return
    from .climodels import split_pick
    for cat, want in zip(('model', 'thought_level'), split_pick(profile['model'])):
        if not want or not client.option(cat): continue
        vals = client.values(cat)
        to = (offered_model if cat == 'model' else offered_effort)(want, vals) if vals else want
        if to and client.set_option(cat, to):
            if to != want: logger.debug(f'acp: {name} {cat} {want!r} runs as its {to!r}')
            continue
        now = client.option(cat).get('currentValue') or 'its default'
        logger.debug(f'acp: {name} offers no {cat} near {want!r} (it offers {vals}) - it runs on {now}')
        if cat == 'model': trace('progress', 'acp', f"{want} is not available on this {_cli_name(name)} sign-in, so this ran on {now}")


STOP_GRACE = 2.0                 # seconds a stopped turn has to honour session/cancel before its process is closed
NO_GOES_ON = 8                   # turns one prompt may go on for after a no of ours ended its turn (run_acp) - a loop of nos ends, as Cancelled
NO_THEN = 'Go on with the rest of the job.'
def run_acp(profile: dict, prompt: str, trace, resume: str = None, cancel=None, extra_env: dict = None, store=None):
    """One headless turn over ACP. Returns (result, session_id, diff) - run_cli's own contract, so
    nothing upstream can tell which road a run took.

    The session id is RETURNED by session/new rather than scraped out of a vendor's temp directory, the progress arrives as typed
    events, and every tool call the agent asks to make is answered by gate - Taskuary's rules, not a bypass flag. A kept
    conversation (keep_alive: a general agent's task, the Assistant) holds its connection between turns in clipool, as the argv
    road holds its claude process, so a turn after the first pays no start-up. ACPStartError means nothing ran: run_cli falls back.
    """
    profile = with_cmd(profile, store); name = profile['cmd']
    launch, cwd, keep = acp_launch(profile), _long(profile.get('cwd')), profile.get('keep_alive')
    env, base = {**spawn_env(profile, extra_env), **launch['env']}, {**spawn_env(profile), **launch['env']}
    from . import clipool, gate as gate_
    sig = _acp_sig(launch, cwd, env)
    opener = lambda: acp_mod.Conversation(_acp_open(name, launch, cwd, env, resume, profile.get('timeout'), trace, fresh_if_gone=True, base=base), sig)
    conv = clipool.take(keep, sig, opener, resume) if keep else opener()      # ...its turn read opening from its start where none was up (general.cold)
    client = conv.client
    # ...ITS CONVERSATION WAS GONE: nothing is asked of the fresh one here - this turn's words assume what it no longer has. The caller says the
    # whole of it again (Gone), and a kept one finds this fresh conversation open and unused (clipool._stale), so no second start is paid
    if isinstance(getattr(client, 'fresh_from', None), str) and not conv.turns:
        client.fresh_from = None
        if not keep: client.close()
        raise Gone(resume)
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f"{name} over acp{' via ' + launch['adapter'] if launch['adapter'] else ''} cwd={cwd or os.getcwd()}"
                         + (f' resume={resume}' if resume else '') + (f' live={keep}' if keep else ''))
    head0 = _git(cwd, 'rev-parse', 'HEAD')
    held, asked, told = {}, threading.Event(), []            # `asked`: this turn's prompt is on its way to the agent; `told`: what each no says
    steps = ACPSteps(trace, name, held)
    ctx_store, task_id = _RUN.get()
    gstore = store if store is not None else ctx_store
    gate = gate_.answerer({'store': gstore, 'task_id': task_id, 'cli': _cli_name(name), 'cwd': cwd,
                             'sid': client.session_id}, trace, held, told)
    # ...THE AGENT'S OWN UPDATES ARE THE CHAT'S RECORD (the owner, 2026-11-23): a run for a task's chat (a trace that takes them: general's
    # `visible.acp`) hands each one in as it comes, before its trace's echo - drawn as the agent sent it, one row per call patched in place
    # ...and a permission asked is the call's own update too (its toolCall): onto its row, the agent's options with it, before the answer
    raw = getattr(trace, 'acp', None)
    def permit(params):
        steps.asked(params.get('toolCall'))
        if callable(raw) and (u := acp_mod.asked_update(params)): raw(u)
        return gate(params)
    client.on_update, client.permit = (lambda u: (raw(u), steps(u))) if callable(raw) else steps, permit
    with _CLI_CHILDREN_LOCK: _CLI_CHILDREN.add(client.p)
    over = threading.Event()             # this turn has ended, however it ended
    if cancel is not None:
        # A browser Cancel asks the agent to stop first; killing the process is the backstop for
        # an agent that does not honour session/cancel.
        # ...AND ONLY FOR THE TURN THAT WAS STOPPED (the recorded stop, 2026-11-11): the kill came two seconds after the ask whatever had
        # happened since - the stopped turn had ended at once, the lines that waited behind it had begun their turn on this same
        # conversation, and it was closed under them: "died mid-turn", nothing drawn, his lines unanswered. A turn that honoured the stop is
        # over; what runs next is never the one being stopped
        # ...AND A STOP PRESSED BEFORE ITS PROMPT WAS SENT IS STILL ITS STOP: it looked for this turn's lock, found none taken yet and was lost,
        # and the turn ran on unstopped. It is sent the moment this turn's prompt is on its way (`sent`), and never once the turn is over
        def _cancel():
            cancel.wait(); asked.wait()
            if over.is_set(): return
            client.cancel()
            if not over.wait(STOP_GRACE): clipool.drop(keep, conv) if keep else client.close()
        threading.Thread(target=_cancel, daemon=True, name='acp-stop-backstop').start()
    stop, ok = None, False               # ...set before anything can raise: the `finally` reads both, whatever ended the turn
    try:
        with conv.lock:
            if launch['adapter']: _acp_gears(client, profile, name, trace)     # a native CLI took its model on its command line
            # ...A STOP PRESSED BEFORE ITS PROMPT WAS SENT: the prompt is never sent. Sent and then cancelled, an agent quick enough did the work
            # he stopped (a call the gate allows on its own runs) and only its answer was thrown away. Nothing was asked: the conversation is sound
            if cancel is not None and cancel.is_set(): stop, ok = 'cancelled', True; raise Cancelled(client.session_id)
            since = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            stop, said = client.prompt(prompt, sent=asked.set)
            # ...A NO OF OURS IS AN ANSWER, NEVER THE END OF THE TURN (the HIPAA walk, 2026-11-21): codex-acp offers Codex's "cancel" as its only
            # reject, so every hold or refusal aborted Codex's turn - filed "Cancelled" with Try again over the live Approve card, and the agent
            # never heard why. The same conversation goes on at once, told what the step's answer would have said on an adapter that goes on
            for _ in range(NO_GOES_ON):
                if stop != 'cancelled' or (cancel is not None and cancel.is_set()) or not told: break
                words, told[:] = '\n\n'.join(t['words'] for t in told), []
                trace('progress', 'acp', 'a step it asked for was not run - it goes on, told why')
                stop, said = client.prompt(f'{words}\n\n{NO_THEN}')
            conv.turns += 1; conv.used = time.time()
        ok = True
        # WHAT THE TURN USED, onto its route row (aiusage.Metered's meter): the adapter's count, else the CLI's own log (aiusage.acp_turn)
        aiusage.note_turn(aiusage.acp_turn(_cli_name(name), client.last_turn, client.session_id, since))
        # ONE CONTRACT FOR A STOPPED TURN on every road: Cancelled, with the conversation it was on - never a blank success
        if stop == 'cancelled': raise Cancelled(client.session_id)
        if stop and stop != 'end_turn':
            trace('progress', 'acp', f'the turn ended early: {stop}')
            # ...and a turn that ended early with nothing said is a failure, as the kept road reads its CLI's own error result - never an empty reply
            # filed as done: ended part-way, in the sentence for its reason, its conversation kept for the next line
            # ...and one it ended at a refusal or a limit AFTER words is the same part-way end, its words kept in the steps - never a half answer
            # filed as done, as the kept road files claude's own error_max_turns
            if not said.strip() or stop == 'refusal' or stop in clipool.LIMITS:
                raise_failure(name, f'the turn ended early: {stop}', launch['cmd'][0], resume, part_way=(clipool.ended_early(stop), client.session_id))
        diff = ''
        if cwd:
            head1 = _git(cwd, 'rev-parse', 'HEAD')
            if head1 and head1 != head0: diff = _git(cwd, 'diff', f'{head0}..{head1}')
            unc = _git(cwd, 'diff', 'HEAD')
            if unc: diff = '\n'.join(x for x in (diff, unc) if x).strip()
        return said, client.session_id, (diff[:150000] or None)
    except acp_mod.ACPAgentError as e:
        # ...a stopped turn its agent did not end was ended by the backstop: still his stop, never a death
        if cancel is not None and cancel.is_set(): raise Cancelled(client.session_id) from e
        # ...a usage limit, a sign-in: read as every road reads them (failure_of) - an ACP limit was raw adapter text, and the router never rested it
        # ...AND A TURN THAT FAILED KEEPS THE CONVERSATION IT WAS ON (the HIPAA walk, 2026-11-21): a gateway's 429 ended a first turn, and its
        # try again opened a fresh Codex thread that learned it all again and wrote the workbook a second time. The try resumes this one
        kept = Unfinished(str(e), client.session_id); kept.__cause__ = e
        if f := prompt_failure(name, e, launch['cmd'][0], client.session_id): raise f from kept
        raise e from kept
    finally:
        over.set(); asked.set()
        # ...and a refusal's reason the turn went on past (its adapter answered the step "refused") is said by the one road, as it always was
        if gstore is not None and str(task_id or '').isdigit() and (rest := [t['words'] for t in told if t['tell']]):
            from .browsergate import _tell
            for w in rest: _tell(gstore, int(task_id), w)
        steps.flush(stop if ok else 'error')
        client.on_update, client.permit = None, None
        with _CLI_CHILDREN_LOCK: _CLI_CHILDREN.discard(client.p)
        if not keep: client.close()
        elif not ok: clipool.drop(keep, conv)          # a turn that failed part-way is never sent again on that connection (MID_TURN)


# ...IN HIS WORDS (the owner, 2026-11-22: "what was the weird bug error"): what happened and the way on - the adapter's own words go to the log
HELD_ONLY = "{cli} couldn't start just now, so nothing ran{why}. Try again, or pick another AI for this task"


def _fell_back(name: str, why, trace):
    "An ACP start that failed: said once in the log per CLI, and on this run's launch line; the run goes on over argv."
    if name not in _FELL_BACK:
        _FELL_BACK.add(name); logger.warning(f'acp: {name} did not start over ACP ({why}) - running it on its command line instead')
    trace('tool', 'acp', f'{name} over acp did not start ({str(why)[:200]}) - this run uses the command line')


def spawn_env(profile: dict, extra_env: dict = None) -> dict:
    "A headless CLI's environment: the process's own, or - for a stranger's task (profile strict_env) - only what terminal.STRICT_ENV lets through."
    from .terminal import strict_ok          # lazy: terminal imports this module
    base = {k: v for k, v in ambient(os.environ).items() if not profile.get('strict_env') or strict_ok(k)}
    # ...and the profile's own (an API card's harness: its CODEX_HOME and its key - in the environment, never on disk; harness.row)
    return child_env({**base, **(profile.get('env') or {}), **(extra_env or {})})


def sees_images(family: str, args, resume=None) -> bool:
    """Does a one-shot run of this CLI take pictures in its input: claude printing stream-json, whose stream-json input carries image blocks,
    and a fresh `codex exec`, which attaches files by --image (codex-cli's own --help, 2026-11-09)."""
    if family == 'codex': return bool(args) and args[0] in ('exec', 'e') and not resume
    return family == 'claude' and ('-p' in args or '--print' in args) and 'stream-json' in args and '--input-format' not in args


def run_cli(profile: dict, prompt: str, trace, resume: str = None, cancel=None, extra_env: dict = None, store=None, images=None):
    """One headless invocation of the configured CLI, output STREAMED line by line into
    the run trace so the Board shows the agent working live. claude's stream-json events
    render as readable tool/text lines; any other CLI's plain stdout streams as-is.
    `images` [(media type, base64)]: shown to a one-shot claude as image blocks (sees_images); dropped elsewhere.
    Returns (result, session_id, diff)."""
    # Whatever built this prompt, a credential in it would go to the CLI's provider and be filed
    # in the run's own trace two lines below. task_context() writes each message's BodyText in
    # verbatim, so mail is the likeliest way one arrives here. See redact.py.
    prompt = redact.scrub(prompt)
    # The ACP road, for the profiles marked for it: the general agent's tool-using runs, on a CLI that speaks the protocol natively
    # or through its adapter (claude, codex), while the owner's 'Run CLI agents over ACP' is on. Triage, the drafter, coding
    # sessions and every pane stay on the argv road below - and so does a run whose agent did not start over ACP (ACPStartError:
    # nothing ran), said once in the log. See docs/acp-transport.md.
    if _acp_road(profile, store):
        try: return run_acp(profile, prompt, trace, resume=resume, cancel=cancel, extra_env=extra_env, store=store)
        except acp_mod.ACPStartError as first:
            # ...A START THAT FAILED IS TRIED AGAIN ONCE BEFORE HE HEARS OF IT (the owner's live app, 2026-11-22: "session/new: Internal error" after
            # 40 s, in the minute triage and another task's start were busy; both his cards started in 0.9 s a moment later): nothing ran, so a
            # second try costs nothing - and only a start that fails twice is his to see
            e = first
            if not (cancel is not None and getattr(cancel, 'is_set', lambda: False)()):
                logger.info(f'acp: {profile.get("cmd")} did not start ({str(first)[:160]}) - trying once more')
                try: return run_acp(profile, prompt, trace, resume=resume, cancel=cancel, extra_env=extra_env, store=store)
                except acp_mod.ACPStartError as again: e = again
            if profile.get('held_only'):
                logger.warning(f"acp: {profile.get('cmd')} did not start twice - {str(e)[:300]}")
                raise RuntimeError(HELD_ONLY.format(cli=_cli_name(str(profile.get('cmd') or '')).capitalize(), why='')) from e
            _fell_back(str(profile.get('cmd') or ''), e, trace)
    # ...a run that may only go held (llm.make_cli_llm `held_only`) never takes the command line: there it would read and act unasked
    elif profile.get('held_only'):
        raise RuntimeError(HELD_ONLY.format(cli=_cli_name(str(profile.get('cmd') or '')).capitalize(), why=" - 'Taskuary approves each step of an agent' is off in Settings"))
    profile = with_cmd(profile, store); name = profile['cmd']
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
    cmd = _resolve_cmd(name) + _own_settings(profile, name, args) + _model_args(profile, name)
    # A CONVERSATION KEPT OPEN: the Assistant and the general agent name theirs (`keep_alive`), and claude's
    # stream-json input serves every turn from one process instead of starting the CLI per call (clipool).
    keep = profile.get('keep_alive')
    if _keeps(profile, family, args):
        return _run_live(profile, name, cmd, prompt, trace, keep, resume, cancel, extra_env, images=images)
    # ...and a ONE-SHOT JUDGEMENT on a process already up (clipool.spare_turn): no tools, no conversation to resume, no picture to show
    if _spares(profile, family, args, resume, images):
        return _run_live(profile, name, cmd, prompt, trace, None, None, cancel, extra_env, spare=True)
    # A PICTURE IS SHOWN, NOT NAMED (2026-11-09): triage on claude has no tools to open a file, so a screenshot-only chat line was judged
    # blind and became its own task beside the one it was about. Claude's stream-json input takes image blocks, as the API does
    # ...and Codex's exec takes them as files: each written to a private temp file for the run and removed after it, as the devin prompt is
    pics, pic_files = sees_images(family, args, resume) and list(images or []), []
    if pics and family == 'claude': cmd += ['--input-format', 'stream-json']
    elif pics:
        import base64, tempfile
        for ct, b64 in pics:
            fd, f = tempfile.mkstemp(prefix='tq-pic-', suffix='.' + ct.split('/')[-1].replace('jpeg', 'jpg'))
            with os.fdopen(fd, 'wb') as fh: fh.write(base64.b64decode(b64))
            pic_files.append(f)
        cmd += [f'--image={f}' for f in pic_files]     # `=`: --image takes a list, and a bare path after it would swallow what follows
    # Keep exec's existing sandbox/config flags, and resume the exact thread.
    if resume: cmd += resume_argv(profile, resume) + (['--json', '-'] if is_codex else [])
    # Kimi's current CLI does not read its prompt from stdin. --prompt is print mode
    # and requires a value; keep it out of the profile shared with the interactive pane.
    if family == 'kimi': cmd += ['--prompt', prompt]
    # GEMINI'S -p TAKES A VALUE now (0.62: "Not enough arguments following: p") and appends it to stdin, so an empty one keeps the
    # prompt on stdin; DEVIN's print mode reads no stdin ("needs a prompt") and takes a file. Both read as "needs you to sign in"
    # on a real first run (2026-10-15).
    if family == 'gemini' and '-p' in cmd and (cmd.index('-p') == len(cmd) - 1 or str(cmd[cmd.index('-p') + 1]).startswith('-')):
        cmd.insert(cmd.index('-p') + 1, '')
    prompt_file = None
    if family == 'devin' and '--prompt-file' not in cmd:
        import tempfile
        fd, prompt_file = tempfile.mkstemp(prefix='tq-devin-', suffix='.txt')
        with os.fdopen(fd, 'w', encoding='utf-8') as f: f.write(prompt)
        cmd += ['--prompt-file', prompt_file]
    cwd = profile.get('cwd')
    head0 = _git(cwd, 'rev-parse', 'HEAD')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} cwd={cwd or os.getcwd()}' + (f' resume={resume}' if resume else ''))
    try:
        # A headless Assistant session can still own an embedded browser. Its session identity
        # rides here just as it does in a PTY; merge it over the real process environment so PATH,
        # login homes, and every configured CLI keep working.
        env = spawn_env(profile, extra_env)
        p = spawn.popen(cmd, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                             text=True, encoding='utf-8', errors='replace', cwd=cwd, shell=False,
                             env=env)
        with _CLI_CHILDREN_LOCK: _CLI_CHILDREN.add(p)
    except PermissionError as e:
        # which() found something that cannot be executed from here. "Not installed" sent people
        # off to reinstall a CLI that was already there; the reason is in denied_msg.
        raise FileNotFoundError(denied_msg(name, cmd[0] if cmd else '', e)) from e
    # A LEASH ONLY WHEN THE CALLER GAVE ONE (llm.make_cli_llm): a one-shot look-up has its limit; an agent run has none and ends when it
    # finishes or the owner stops it (the owner, 2026-11-04: "we can't have timeout as it's an active agent")
    timed, limit = threading.Event(), profile.get('timeout')
    killer = threading.Timer(limit or 0, lambda: (timed.set(), p.kill()))
    if limit: killer.start()
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
            if pics and family == 'claude': p.stdin.write(json.dumps({'type': 'user', 'message': {'role': 'user', 'content': [
                *({'type': 'image', 'source': {'type': 'base64', 'media_type': ct, 'data': b64}} for ct, b64 in pics), {'type': 'text', 'text': prompt}]}}) + '\n')
            elif family != 'kimi' and not prompt_file: p.stdin.write(prompt)
            p.stdin.close()
        except Exception: pass
    threading.Thread(target=_feed, daemon=True).start()
    raw, final, streamed_out, streamed_sid, open_tools = [], None, '', None, set()
    claude = ClaudeSteps(trace)
    stream_error, structured_stream, turn_error = None, False, ''
    try:
        for line in p.stdout:
            line = line.rstrip('\n')
            if not line.strip(): continue
            raw.append(line)
            try: j = json.loads(line)
            except ValueError: trace('live', name, line[:400]); continue
            # ...the error the turn ENDED on, whichever CLI says it: an answer after it (a retry that got through) clears it
            if isinstance(j, dict):
                if (e := _event_error(line)): turn_error = e
                elif (j.get('type') == 'item.completed' and (j.get('item') or {}).get('type') == 'agent_message'
                      or j.get('type') == 'result' and not j.get('is_error')): turn_error = ''
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
            if isinstance(j, dict): claude(j); streamed_sid = streamed_sid or j.get('session_id')     # claude's init names it: a stop keeps it
            # Codex `exec --json` speaks item lifecycle events instead of Claude content blocks.
            # Normalize both into one stream so assistant-ui does not care which CLI is logged in.
            if isinstance(j, dict) and j.get('type') == 'thread.started':
                streamed_sid = j.get('thread_id') or streamed_sid
            if isinstance(j, dict) and j.get('type') == 'turn.completed': aiusage.codex_turn(j.get('usage'))     # what the turn used
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
        for f in [prompt_file, *pic_files]:              # the prompt and its pictures can carry mail: never left in the temp folder
            if not f: continue
            try: os.remove(f)
            except OSError: pass
    err_t.join(5)      # the exit code can land before the stderr reader has appended - 'boom' read as 'no output' on a fast CI box
    if p.returncode != 0 and cancel is not None and cancel.is_set(): raise Cancelled(streamed_sid or (final or {}).get('session_id'))
    # A FINISHED ANSWER IS THE ANSWER, whatever the exit after it: claude printed its words and a successful result, then exited non-zero - the
    # turn was told "stopped in the middle" and its answer thrown away. It is kept and shown; the exit is the log's, and the launch line's.
    # ...only a real result event that says it succeeded: any other dict with a `result` ({"result": "partial", "error": ...}) is no finished answer.
    # A success with no words is finished too - as it is at exit 0 - never "stopped in the middle of its turn"
    if p.returncode != 0 and final is not None and final.get('type') == 'result' and not final.get('is_error') and final.get('subtype', 'success') == 'success' \
            and not timed.is_set():
        logger.warning(f'{name} exited {p.returncode} after a finished answer - the answer is kept')
        trace('tool', 'cli', f'{name} exited {p.returncode} after its answer')
    elif p.returncode != 0:
        err = ''.join(err_buf)
        said = cli_failure(raw, err)
        why = (f'timed out after {limit}s' if timed.is_set() else said)[:500]
        # the CLASSIFYING patterns read both streams: a sign-in refusal or a Windows launch
        # refusal lands on stderr, while the reason the owner reads now comes off stdout
        hay = f'{said}\n{err}'
        if f := failure_of(name, said, cmd[0] if cmd else '', resume, [*raw, err], err): raise f
        # a refusal to START, not a failed run: the CLI produced no output of its own and the
        # only thing on stderr is the refusal
        if _DENIED.search(hay) and not raw: raise RuntimeError(denied_msg(name, cmd[0] if cmd else '', said))
        if _NO_HOME.search(hay): raise RuntimeError(no_home_msg(_cli_name(name) or name))
        if timed.is_set(): raise TimedOut(f'{name} exit {p.returncode}: {why}', streamed_sid or (final or {}).get('session_id'))
        # ...A LIMIT THE TURN REACHED (claude's error_max_turns) is said in the one sentence for it on every road (clipool.ended_early), as the kept
        # road and ACP say it - never "Reached max turns (3)" or its stop code
        if final is not None and final.get('type') == 'result' and str(final.get('subtype') or '') in LIMITS:
            raise_failure(name, said, cmd[0] if cmd else '', None, raw, part_way=(ended_early(str(final['subtype'])), streamed_sid or final.get('session_id')))
        # ...DIED WITH ONLY EVENTS AND NO WORD OF WHY - no event of its own says (_event_error), nothing on stderr: the one sentence the other
        # roads say for a death part-way, never the events' JSON. Where an event does say why, its words are the reason (cli_failure)
        if raw and not _said_err(err) and all(_events(raw)) and not any(_event_error(x) for x in raw):
            raise_failure(name, f'exit {p.returncode} with no reason given', cmd[0] if cmd else '', None, raw,
                          part_way=(MID_TURN, streamed_sid or (final or {}).get('session_id')))
        raise RuntimeError(f'{name} exit {p.returncode}: {why}')
    # OpenCode can report provider errors in JSON while its process exits successfully.
    if stream_error: raise RuntimeError(f'{name}: {redact.scrub(stream_error)[:500]}')
    # ...AND A TURN ITS PROVIDER REFUSED OR FAILED WHILE THE CLI EXITED CLEAN (the owner's live task, 2026-11-18: Codex's "This request was blocked
    # by our safety systems" was filed as the agent's own words, glued to its last sentence): a turn that ended part-way, in the provider's
    # sentence and whose it is - what it said before stays its steps
    if turn_error:
        who = _cli_name(name) or name
        raise_failure(name, turn_error, cmd[0] if cmd else '', None, raw, part_way=(f'{who.capitalize()} stopped this turn: {turn_error}', streamed_sid))
    if final is not None: aiusage.claude_result(final); out, sid = str(final.get('result') or '').strip(), final.get('session_id')
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


# where the words for the owner stop: the machine lines a turn ends on (concierge.parse_call, parse_options, recover's PICK), a code
# fence, a card marker, bare JSON - and a last line that may yet become one of them ("CAL" is held until it is not "CALL:")
_MACHINE = re.compile(r'(?:^|\n)[ \t]*(?:CALL|OPTIONS|PICK)[ \t]*:|```|<!--|(?:^|\n)[ \t]*\{', re.I)
_MARKS = ('call:', 'options:', 'pick:')


def spoken(text: str) -> str:
    """The part of a half-written answer the owner may already read."""
    s = str(text or '')
    if (m := _MACHINE.search(s)): s = s[:m.start()]
    head, _, last = s.rpartition('\n')
    tail = last.strip().lower().replace(' ', '')
    if tail and any(k.startswith(tail) for k in _MARKS): s = head
    return s.strip()


def _model_args(profile: dict, name: str) -> list:
    """Which model works it: profile default, or a per-run override from the UI. The flag
    name is configurable because every CLI spells it differently (claude/codex: --model)."""
    if not profile.get('model'): return []
    # 'gpt-5.4@high' spells a codex model and its reasoning level in one pick (climodels)
    from .climodels import split_pick, effort_args
    m, eff = split_pick(profile['model'])
    # '@high' is the CLI's own model at that effort (a workflow's effort alone, workflows.brain): no empty model flag
    return ([profile.get('model_arg') or '--model', m] if m else []) + effort_args(_cli_name(name), eff)


_FLAGS: dict = {}


def cli_has_flag(name: str, flag: str) -> bool:
    """Does this CLI's --help name `flag`? Asked once per executable and remembered; a CLI that cannot say is taken as not having it."""
    try: exe = tuple(_resolve_cmd(name))
    except Exception: return False          # not installed (CI's runners): nothing to ask, and the caller runs without the flag
    if (exe, flag) not in _FLAGS:
        try:
            r = spawn.run([*exe, '--help'], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=30,
                          stdin=subprocess.DEVNULL, env=child_env(dict(os.environ)))
            _FLAGS[(exe, flag)] = flag in (r.stdout or '') + (r.stderr or '')
        except Exception as e:
            logger.info(f'{name} --help could not be read ({e}) - running without {flag}'); _FLAGS[(exe, flag)] = False
    return _FLAGS[(exe, flag)]


ROOTS = 'sandbox_workspace_write.writable_roots'
def codex_roots(args: list, *dirs) -> list:
    "`args` with `dirs` among Codex's writable roots: one `-c` key holding them all (a second would replace the first), each once."
    args, kv = list(args), f'{ROOTS}='
    i = next((n for n, a in enumerate(args) if str(a).startswith(kv) and n and args[n - 1] in ('-c', '--config')), -1)
    had = _toml_value(str(args[i])[len(kv):]) if i >= 0 else []
    roots = list(dict.fromkeys([*(had if isinstance(had, list) else []), *(Path(d).as_posix() for d in dirs)]))
    val = f"{kv}[{','.join(repr(r) for r in roots)}]"
    if i >= 0: args[i] = val
    else: args += ['-c', val]
    return args


def _own_settings(profile: dict, name: str, args: list) -> list:
    """THE ASSISTANT READS NONE OF THE OWNER'S USER-LEVEL CLAUDE SETTINGS (the owner, 2026-10-21): their user-wide hooks POST to this app
    on every prompt and every stop - 0.3-0.5 s a turn, measured - and its headless, tool-less brain has no use for them. Only a profile
    that asks (user_settings False: the Assistant's, and every one-shot with no hands - triage, summaries, judges, reports: llm.make_cli_llm);
    coding and general agents keep theirs. `args` as they run, with that applied - on the argv road and the ACP road alike.
    ...AND NONE OF HIS OWN CLAUDE.md (walk 6, 2026-11-23: every triage call carried the laptop user's ~/.claude/CLAUDE.md, its "override any
    default behavior" and his real name among it - --setting-sources leaves that file in, and the ACP road was handed neither): kept out in
    the one --settings Claude reads (hooks.not_his), merged into one the run already carries. A claude without the flag runs as before."""
    args = list(args)
    # ...AND A CODEX SANDBOX MAY WRITE WHERE ITS BROWSER KEEPS ITS SOCKETS (his live app, 2026-11-23: after a restart every agent-browser command
    # of a Codex task failed "Socket directory ~/.agent-browser is not writable" - Codex runs commands as its own restricted user, and only a
    # daemon started before it could be reached): the folder is a writable root of every Codex run, on the argv road and the ACP road alike
    if _cli_name(name) == 'codex':
        from . import browserview
        args = codex_roots(args, browserview.home())
    if profile.get('user_settings') is not False or _cli_name(name) != 'claude': return args
    if '--setting-sources' not in args and cli_has_flag(name, '--setting-sources'): args += ['--setting-sources', 'project,local']
    from . import hooks
    i = args.index('--settings') if '--settings' in args[:-1] else -1
    f = hooks.not_his_file(args[i + 1] if i >= 0 else '')
    return (args[:i] + ['--settings', f] + args[i + 2:] if i >= 0 else args + ['--settings', f]) if f else args


def _keeps(profile: dict, family: str, args: list) -> bool:
    return bool(profile.get('keep_alive')) and family == 'claude' and 'stream-json' in args and ('-p' in args or '--print' in args)


def _spares(profile: dict, family: str, args: list, resume, images) -> bool:
    "A one-shot claude call with every tool off (`--tools ''`: triage, a summary, a judge) - one a process started ahead can answer."
    bare = '--tools' in args and args.index('--tools') + 1 < len(args) and args[args.index('--tools') + 1] == ''
    return (bare and family == 'claude' and not profile.get('keep_alive') and not resume and not images and 'stream-json' in args
            and ('-p' in args or '--print' in args) and '--input-format' not in args)


def warm_cli(profile: dict, resume: str = None, extra_env: dict = None, store=None, swap: bool = False) -> bool:
    """Start a kept conversation's process ahead of its first turn (clipool.warm) - the command run_cli's live road would
    launch for this profile, so that turn finds it running. False for a profile that keeps no conversation (a one-shot
    brain, a CLI with no stream-json input): there is nothing to have ready."""
    profile = with_cmd(profile, store); name = profile['cmd']
    args = list(profile.get('args') or preset_args(name) or ['-p'])
    if profile.get('keep_alive') and _acp_road(profile, store) and (ok := _warm_acp(profile, resume, extra_env, store, swap)) is not None: return ok
    if not _keeps(profile, _cli_name(name), args): return False
    from . import clipool
    try: return clipool.warm(profile['keep_alive'], _resolve_cmd(name) + _own_settings(profile, name, args) + _model_args(profile, name),
                             cwd=profile.get('cwd'), env=spawn_env(profile, extra_env), resume=resume, swap=swap)
    except PermissionError as e: raise FileNotFoundError(denied_msg(name, name, e)) from e


def _warm_acp(profile: dict, resume, extra_env, store, swap: bool) -> bool:
    """warm_cli for a kept conversation on the ACP road: its connection opened and its session ready before the first turn - the
    adapter's start-up (3-5 s, measured) paid while the owner reads. None for a start that fails: warm_cli warms the argv
    process instead, the one the turn will fall back to."""
    from . import clipool
    try:
        name, launch, cwd = profile['cmd'], acp_launch(profile), _long(profile.get('cwd'))
        env, base = {**spawn_env(profile, extra_env), **launch['env']}, {**spawn_env(profile), **launch['env']}
        sig = _acp_sig(launch, cwd, env)
        return clipool.warm_with(profile['keep_alive'], sig, lambda: acp_mod.Conversation(
            _acp_open(name, launch, cwd, env, resume, profile.get('timeout'), lambda *a: None, fresh_if_gone=True, base=base), sig), resume, swap=swap)
    except acp_mod.ACPStartError as e:
        logger.info(f"acp: {profile['cmd']} not warmed over ACP - {e}"); return None


def _run_live(profile: dict, name: str, cmd: list, prompt: str, trace, keep: str, resume, cancel, extra_env, spare: bool = False, images=None):
    """run_cli's turn on a conversation's LIVE process: the same trace events, the same errors, the same
    (result, session_id, diff) - with no checkout to diff, since neither the Assistant nor a general agent
    works in one. `spare`: a one-shot answer on a process started ahead for this command (clipool.spare_turn)."""
    from . import clipool
    cwd = profile.get('cwd')
    trace('prompt', 'prompt_sent_to_agent', prompt)
    trace('tool', 'cli', f'{name} cwd={cwd or os.getcwd()} live={keep or "spare"}' + (f' resume={resume}' if resume else ''))
    # THE WORDS AS THEY ARE WRITTEN, for a conversation that asked for them (--include-partial-messages: the Assistant): the page
    # draws them while the rest is still coming, instead of after the whole answer (the owner, 2026-10-20: "it should respond to
    # things quickly"). Only what the owner would read - the machine's CALL line never - and the finished answer replaces them.
    written, drawn, claude = [''], [''], ClaudeSteps(trace)
    def on(j):
        if j.get('type') == 'stream_event':
            ev = j.get('event') or {}
            if ev.get('type') == 'message_start': written[0] = ''
            d = ev.get('delta') or {}
            if ev.get('type') == 'content_block_delta' and d.get('type') == 'text_delta':
                written[0] += str(d.get('text') or '')
                now = spoken(written[0])
                if now and now != drawn[0]: drawn[0] = now; trace('words', name, now)
            return
        claude(j)
        shown = _live_line(j)
        if shown: trace('live', name, shown)
    try:
        # a CLI with its tools off (the Assistant deciding: nothing happens until the app carries the decision out) may be sent its
        # turn again after any end; one with tools may have done work mid-turn, and never is
        bare = '--tools' in cmd and cmd.index('--tools') + 1 < len(cmd) and cmd[cmd.index('--tools') + 1] == ''
        env = spawn_env(profile, extra_env)
        # ...A PICTURE WITH THE TURN IS SHOWN on the live conversation too, as image blocks of its stream-json input (the walk, 2026-11-21: the
        # floating Assistant on the CLI, its tools off, was handed a path it could not open and never saw the picture)
        shown = [*({'type': 'image', 'source': {'type': 'base64', 'media_type': ct, 'data': b64}} for ct, b64 in images), {'type': 'text', 'text': prompt}] if images else prompt
        if spare:
            # ...keyed by everything it was started with, the environment's values too: a spare is never a call's under another token
            key = 'spare:' + hashlib.sha1(json.dumps([cmd, str(cwd or ''), sorted(env.items())]).encode('utf-8')).hexdigest()[:16]
            final, raw = clipool.spare_turn(key, cmd, prompt, on, cwd=cwd, env=env, cancel=cancel, timeout=profile.get('timeout'))
        else: final, raw = clipool.run(keep, cmd, shown, on, cwd=cwd, env=env, resume=resume, cancel=cancel, timeout=profile.get('timeout'), resend=bare)
    except PermissionError as e:
        raise FileNotFoundError(denied_msg(name, cmd[0] if cmd else '', e)) from e
    except Cancelled: raise
    except RuntimeError as e:
        said = str(e)
        if isinstance(e, clipool.TimedOut): raise clipool.TimedOut(f'{name}: {said[:500]}', e.session_id) from e
        # ...a turn its CLI died in says so in the one sentence an ACP agent's death says too (acp.py), its conversation kept (clipool.PartWay)
        raise_failure(name, said, cmd[0] if cmd else '', resume, part_way=(clipool.MID_TURN, e.session_id) if isinstance(e, PartWay) else None)
    aiusage.claude_result(final)                      # a turn that failed still used what it used
    if final.get('is_error'):
        said = str(final.get('result') or final.get('subtype') or 'the CLI reported an error')
        # ...a limit the turn reached (error_max_turns) is said in the one sentence for it on every road (clipool.ended_early) - never its stop code
        sub = str(final.get('subtype') or '')
        raise_failure(name, said, cmd[0] if cmd else '', resume, raw,          # its `errors` ride in raw, beside a result that says only error_during_execution
                      part_way=(clipool.ended_early(sub), final.get('session_id') or resume) if sub in clipool.LIMITS else None)
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
    # the owner's people (orgchart.py), so "send it to whoever owns payroll" has a name - not on a stranger's task (context.build's rule)
    from . import orgchart, origin
    if (org := orgchart.block(store)) and origin.of_task(store, task_id)[0] != 'stranger': lines += ['', "The owner's people:", org]
    return '\n'.join(lines)


# A VERDICT note is written by Taskuary and quotes the mail it was given on - its subject, its sender (server._learn_promotion
# and its siblings). On a stranger's task that is the stranger's text, and under "learned from the owner - FOLLOW these" the
# reviewer and the agent read it as the owner's (task 10 live check: a stranger's subject line rode into the first prompt).
OWNER_SOURCES = ('manual', 'writing', 'owner')     # 'owner': a line the owner said (memory.notes)

def memory_block(store, messages: list, owner_only: bool = False) -> str:
    """The standing notes an agent working this thread has to follow - the ones that bear on
    THIS thread, not every note on file. It used to be every match with no cap at all, which
    grows without limit as the owner keeps giving verdicts; ranking by what the thread actually
    says puts the ones that matter at the top and says how many were left out."""
    from .ingest import relevant_notes
    text = ' '.join(f"{m.get('Subject') or ''} {m.get('BodyText') or ''}" for m in messages)[:4000]
    keep = (lambda n: n.get('Source') in OWNER_SOURCES) if owner_only else None   # a stranger's task: only notes in the owner's own words
    notes, left = relevant_notes(store, [(m.get('FromEmail') or '') for m in messages], text, keep=keep)
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
