"""AN API BRAIN WITH HANDS: Taskuary's browser and its `show`, offered to a general agent on an API card through function calling.

A general agent on an API card was one system and one user message - nothing it could DO. On an install with no CLI at all (a client
on the HIPAA AI card only: no Claude Code, no Codex) "log into the scheduling portal and look at the denials" was answered "logging in
cannot be done from here - paste the claim information" (the owner, 2026-11-09: "why is this so dumb. this is agent itself"). The
action is the goal, and the browser road already exists: agent-browser, the sign-in vault, the hold on acts that can't be undone.

So the turn is a loop of the card's own chat-completions `tools` (llm.make_llm's `chat`): the model calls a tool, the server runs
it, the answer goes back - until it answers in words, as a CLI's turn does. Nothing counts its steps (the owner, 2026-11-04: an agent
at work is never ended for running long - only finishing or Stop ends it); only steps that bring nothing new do (idle_steps). And Stop ends it AT
ONCE, mid-call or mid-tool (_await). The tools are the CLI road's own, run by the server rather than a shell:
- browser_open / browser_look / browser_click / browser_fill / browser_press / browser_screenshot - `agent-browser` in THIS task's
  named session (browserview), so the pane shows it. Every act goes through browsergate.check first, exactly as a CLI's shell
  command does through its hook: a press that can't be undone is held for the owner and the agent is told so.
- show - agenttools.show_files: a screenshot, a file, drawn in the chat (the frontend draws a `show` step's FILES_MARK rows).
- SIGNING IN is never a tool: the agent ends its turn with [[TASKUARY-SIGNIN: site]] (selfclose.signin_marker), and the turn's
  filing raises it (general._file -> signin.needs). A saved vault sign-in is typed by the server and the agent is woken
  "Signed in - continue"; with none, the owner's ask is the secure fill page, "Save to vault for next time" on it. The secret
  never reaches the model.
HIPAA: what the page shows goes to the card that runs the turn and nowhere else - the client's own chosen gateway.
"""
import json, re, shlex
from pathlib import Path
from loguru import logger
from .selfclose import SHOW_WHAT
from .browserview import SIGNUP_LINE

IDLE_STEPS = 8                 # steps in a row whose answers held nothing the turn had not read already: going in circles, not working
CAP = 12_000                  # one tool answer, as the model reads it
WAIT = 45.0                    # one browser act

_S = lambda props, need=(): {'type': 'object', 'properties': props, 'required': list(need)}
_REF = {'type': 'string', 'description': 'the element ref from browser_look, like @e12'}
FROM = {'from': {'type': 'integer', 'description': 'the character to start at, for the rest of a long answer (its cut says where)'}}
def _fn(name, desc, params): return {'type': 'function', 'function': {'name': name, 'description': desc, 'parameters': params}}

BROWSER = [
    _fn('browser_open', "Open a web address in Taskuary's browser for this task (the owner watches it beside the chat). Answers with the page's "
        'interactive elements.', _S({'url': {'type': 'string'}}, ['url'])),
    _fn('browser_look', 'Read the page the browser is on: its address and interactive elements with refs (@e1 ...); full=true for all of '
        'its text too (tables, messages).', _S({'full': {'type': 'boolean'}, **FROM})),
    _fn('browser_click', 'Click an element by its ref.', _S({'ref': _REF}, ['ref'])),
    _fn('browser_fill', 'Type text into a box by its ref (replaces what is there). Never a password: sign-ins are Taskuary\'s.',
        _S({'ref': _REF, 'text': {'type': 'string'}}, ['ref', 'text'])),
    _fn('browser_press', 'Press a key in the page, like Enter or Tab.', _S({'key': {'type': 'string'}}, ['key'])),
    _fn('browser_screenshot', 'Save a picture of the page; answers with its path, which `show` puts in the chat.', _S({})),
]
SHOW = _fn('show', f"Show the owner files in this chat - a screenshot, a file you made - by path. {SHOW_WHAT}",
           _S({'files': {'type': 'array', 'items': {'type': 'string'}}}, ['files']))

BRIEF = ('YOUR TOOLS: you drive Taskuary\'s browser for this task with browser_open, browser_look, browser_click, browser_fill, browser_press '
         'and browser_screenshot, and `show` puts a picture or file in this chat. DO the work - open the site, look, click, read - never tell '
         'the owner it "cannot be done from here" or ask them to paste what the page shows. A SIGN-IN PAGE: never type a password and never '
         'ask for one - open the site\'s sign-in page, then end your turn with a final line [[TASKUARY-SIGNIN: <the site\'s domain>]]. '
         'Taskuary signs in with the login saved in its vault and wakes you to continue; if none is saved, the owner fills it in securely '
         '(and can save it to the vault for next time). ' + SIGNUP_LINE + 'An act that can\'t be undone (submit, pay, send, delete) may be HELD for the owner: '
         'when a tool says so, stop and say what you will do once they approve. Say what you found from the page itself, and what you could not check.')
# ── PHASE 2: the rest of what a CLI's hands do (the owner, 2026-11-09: "make sure hipaa thing matches capabilities of claude cli") ──────
# Files in the task's own outputs folder (the one folder the task page serves), read with Taskuary's own readers (attachtext); a page fetched
# through the address guard every other fetch of an untrusted URL takes (webguard); a search on the owner's connected search card, run
# through run_system's own door; and a command - only ever HELD for the owner's Approve (shellgate's card), never run by the agent itself.
_PATH = {'type': 'string', 'description': "a path - relative to your working folder, or full"}
FILES = [
    _fn('files_list', 'List a folder (default: your working folder).', _S({'path': _PATH})),
    _fn('file_read', 'Read a file as text: code, text, CSV, JSON, HTML - and PDF, Word, Excel, PowerPoint through Taskuary\'s readers.',
        _S({'path': _PATH, **FROM}, ['path'])),
]
WRITE = [
    _fn('file_write', 'Write a whole file (created, or replaced). A .docx or .xlsx path writes a real Word document or Excel workbook from '
        'the text: a line a paragraph (# a heading), and `a | b | c` lines a table - in a workbook its rows, `=SUM(G2:G9)` a formula.',
        _S({'path': _PATH, 'text': {'type': 'string'}}, ['path', 'text'])),
    _fn('file_edit', 'Replace one exact piece of a file with another - `old` must occur in it exactly once. In a .docx or .xlsx it is the '
        "text as file_read shows it, and the file keeps its look; `old` a whole table row (`a | b | c`) and `new` several such lines fills one "
        "row per line - a template's line items. `save_as`: the result goes there, the file itself left as it was.",
        _S({'path': _PATH, 'old': {'type': 'string'}, 'new': {'type': 'string'}, 'save_as': _PATH}, ['path', 'old', 'new'])),
]
WEB = [
    _fn('web_search', "Search the web - the AI's own search (OpenAI's, Google's, Anthropic's), else a connected search service - and read pages "
        'it finds, with their sources.', _S({'query': {'type': 'string', 'description': 'what to find out; a URL in it is read'}}, ['query'])),
    _fn('web_fetch', 'Read one public web page or file by its address, as text (no sign-in, nothing clicked - browser_open is for that).',
        _S({'url': {'type': 'string'}, **FROM}, ['url'])),
]
# THE CALL IS THE ASK (a live turn, 2026-11-10): told its push "waits for the owner's Approve", one model never made the call - it wrote
# that the push needed approval and stopped, and the task had no button to press. The gate holds the step and files the button; words do not
ASK_BY_CALLING = ("Call it for such a step all the same: the call is what puts the Approve button on the task, and it runs once the owner "
                  "presses. Saying in words that a step needs approval puts nothing there.")
SHELL = [_fn('run_command', "Run a shell command in your working folder (PowerShell on Windows, bash elsewhere) - git, scripts, builds, "
             "tests. The same rules as a Claude Code session here: a step that leaves this computer (push, publish, send), a delete outside "
             "your folder, or a browser or desktop act that can't be undone waits for the owner's Approve; everything else runs now. "
             + ASK_BY_CALLING,
             _S({'command': {'type': 'string'}, 'why': {'type': 'string', 'description': 'what it does, in a few plain words'}}, ['command', 'why']))]
LOCAL = {t['function']['name'] for t in (*BROWSER, SHOW, *FILES, *WRITE, *WEB, *SHELL)}
# ONE LINE A TOOL (the owner, 2026-11-15: "MCP-style tools with simple JSON ... All methods can be searched later"): as agenttools.SHORT for
# Taskuary's own - the whole words of each are kept (FULL) and read with find_tools
SHORT = {'browser_open': "Open a web page in this task's browser.",
         'browser_look': 'Read the page the browser is on: its elements with refs (@e1); full=true for its text.',
         'browser_click': 'Click an element by its ref.', 'browser_fill': 'Type text into a box by its ref (never a password).',
         'browser_press': 'Press a key in the page (Enter, Tab).', 'browser_screenshot': 'Save a picture of the page; answers with its path.',
         'show': 'Show the owner files in this chat, by path.', 'files_list': 'List a folder (default: your working folder).',
         'file_read': 'Read a file as text (also PDF, Word, Excel).',
         'file_write': 'Write a whole file (.docx/.xlsx made real).',
         'file_edit': 'Replace one exact piece of a file.',
         'web_search': 'Search the web.', 'web_fetch': 'Read one public web page or file by its address.',
         'run_command': 'Run a shell command in your working folder.'}
FULL = {}
def _short(tools: list):
    "Each of `tools` (in place) listed by its line and lean parameters, its whole words kept in FULL."
    from .agenttools import lean
    for x in tools:
        f = x['function']; FULL[f['name']] = f"{f['name']}: {f['description']}\nParameters: {json.dumps(f['parameters'], ensure_ascii=False)}"
        f['description'], f['parameters'] = SHORT[f['name']], lean(f['parameters'])
_short([*BROWSER, SHOW, *FILES, *WRITE, *WEB, *SHELL])
HANDS = ('files_list', 'file_read', 'file_write', 'file_edit', 'web_fetch', 'web_search', 'run_command')
RUN_WAIT = 600                 # one command - a build, a test run
SEARCHERS = ('brave_search', 'tavily', 'exa', 'serpapi', 'serper')


TOOLS_BRIEF = ("YOUR TASKUARY TOOLS are functions you call, not commands to write out - the connected systems among them (list_systems, "
               "run_system) - and, where offered, a Claude Code session's hands: files (files_list, file_read, file_write, file_edit) "
               "anywhere you name, the web (web_search, web_fetch for one page) and run_command (git, scripts, builds), under its rules - a "
               "step that leaves this computer, a delete outside your folder or an act that can't be undone waits for the owner's Approve. "
               + ASK_BY_CALLING + " Each tool is listed by one line: find_tools with its name gives its whole instructions - read them "
               "before a first use where the line is not enough - and finds the tools not listed. " + SHOW_WHAT)
NO_BROWSER = ('THIS COMPUTER HAS NO BROWSER FOR AGENTS YET (agent-browser is not installed), so you cannot open a site this turn. Do not say '
              '"cannot be done from here" and do not ask the owner to paste the page: say in one line that the browser is not set up, and '
              'end with [[TASKUARY-ASK]] Set up the agent browser under {where} so I can do this myself?')
NO_TOOLS = ('THIS AI CANNOT DRIVE A BROWSER (its card takes no tools). If the work needs a website - signing in to a portal, reading a '
            'page - do not say "cannot be done from here" and do not ask the owner to paste it: do what you can without it, then end with '
            '[[TASKUARY-ASK]] This needs an agent with a browser - connect an AI that can use tools (or Claude Code or Codex under {where}), '
            'or switch this task to one?')


class ToolsRefused(RuntimeError): "The card's model would not take tools at all - its first call was refused."
class Lost(RuntimeError): "The conversation carried from earlier turns was turned down on this turn's first call - it is said again, whole (general)."
_REFUSED = re.compile(r' error (400|422)\b')


def can(brain) -> bool:
    "Does this brain take a tool loop - a real `chat` step (llm.make_llm), not just anything callable that answers to the name?"
    import inspect
    f = getattr(brain, 'chat', None)
    return inspect.isfunction(f) or inspect.ismethod(f)
def _where() -> str:
    from . import words
    return words.name('ai_apps')
def no_browser_line() -> str: return NO_BROWSER.format(where=_where())
def no_tools_line() -> str: return NO_TOOLS.format(where=_where())


def _cut(s, n=CAP) -> str: s = str(s or ''); return s if len(s) <= n else s[:n] + f'\n... (cut at {n:,} of {len(s):,} characters - the rest is not shown)'


# A LONG PAGE OR FILE IS READ PART BY PART (the browser-read round, 2026-11-18): cut with "look again for the rest", and no reading tool took a
# place to start, so looking again gave the same first part (and the turn served it as already read) - a payroll table's last runs were never
# reached. The reading tools take `from` (FROM), and the cut says where the next part starts.
def _part(s, a: dict) -> str:
    "One part of a reading tool's answer: CAP characters from the call's `from`, and where the cut is, where the next part starts."
    s = str(s or '')
    try: at = max(0, int(a.get('from') or 0))
    except (TypeError, ValueError): at = 0
    part = s[at:at + CAP]
    if at + CAP >= len(s): return part if part or not at else f'(nothing past character {at:,} - it has {len(s):,})'
    return part + f'\n... (characters {at:,}-{at + CAP:,} of {len(s):,}; call it again with from={at + CAP} for the rest)'


def _act(store, tid, sid, args: list) -> str:
    "One agent-browser command in this task's browser - held for the owner first where it can't be undone (browsergate.check)."
    from . import browsergate as bg
    held = bg.check(store, tid, sid, shlex.join([bg.EXE, *args]))
    if held: return (held.get('hookSpecificOutput') or {}).get('permissionDecisionReason') or f'{bg.HELD}.'
    rc, said = bg._run(sid, args, WAIT, 'api')
    if rc != 0: raise ValueError(said.strip()[-400:] or f'agent-browser {args[0]} failed')
    return said.strip() or 'Done.'


def _url(u) -> str:
    u = str(u or '').strip()
    if not u: raise ValueError('no address given')
    if re.match(r'^[a-z][a-z0-9+.-]*:', u, re.I) and not re.match(r'^https?://', u, re.I): raise ValueError('only http(s) addresses open here')
    return u if re.match(r'^https?://', u, re.I) else 'https://' + u


# ── TASKUARY'S OWN TOOLS, the CLI's toolbox ────────────────────────────────────────────────────────────────────────────────────────────
# The same server a Claude or Codex session reaches over MCP (/api/mcp, agenttools), with the same token and task proof a session's
# environment carries (terminal.session_env) - so every gate is the CLI's own: owns_task, the owner-history check, a stranger's task
# served STRANGER_TOOLS alone, sends that only ever propose, the reply tools left out where nobody waits on one. Nothing is re-decided here.
MCP_WAIT = 300.0

def _mcp(tid: int, sid: str, method: str, params: dict = None, stranger: bool = False, post=None) -> dict:
    import requests
    from . import agenttools, guard, terminal
    env = terminal.session_env('assistant', tid, sid=sid, stranger=stranger)
    h = {'X-Taskuary-Token': env.get(guard.AGENT_ENV, ''), **({guard.TASK_HDR: env[guard.TASK_ENV]} if env.get(guard.TASK_ENV) else {})}
    r = (post or requests.post)(agenttools.url(tid), json={'jsonrpc': '2.0', 'id': 1, 'method': method, 'params': params or {}}, headers=h,
                                timeout=MCP_WAIT)
    if r.status_code != 200: raise RuntimeError(f'Taskuary tools answered {r.status_code}')
    got = r.json()
    if got.get('error'): raise ValueError(got['error'].get('message') or 'refused')
    return got.get('result') or {}


_DROP = ('$schema', 'additionalProperties', 'default', 'examples', 'title')       # keys a gateway's Gemini refuses in a function schema
def _clean(x):
    "A schema with those keys taken out - never a PROPERTY of that name: a tool's `title` field is its own (a gateway refused one taken, 2026-11-09)."
    if isinstance(x, list): return [_clean(v) for v in x]
    if not isinstance(x, dict): return x
    return {k: ({p: _clean(s) for p, s in v.items()} if k in ('properties', '$defs', 'definitions') and isinstance(v, dict) else _clean(v))
            for k, v in x.items() if k not in _DROP}


def taskuary_tools(tid: int, sid: str, stranger: bool = False, post=None) -> list:
    "The session's own Taskuary tools in the function-calling schema - [] when the server cannot be reached (the turn goes on without them)."
    try: listed = _mcp(tid, sid, 'tools/list', stranger=stranger, post=post).get('tools') or []
    except Exception as e:
        logger.warning(f'apiagent: task {tid} gets no Taskuary tools - {e}'); return []
    # ...and which only read Taskuary's own records, by the catalogue's own marks (agenttools.ANNOTATIONS): a repeat is answered from the turn
    READS[(tid, sid)] = {t['name'] for t in listed if (a := t.get('annotations') or {}).get('readOnlyHint') is True and a.get('openWorldHint') is False}
    return [_fn(t['name'], str(t.get('description') or '')[:1024], _clean(t.get('inputSchema') or _S({}))) for t in listed if t.get('name')]


def call_taskuary(tid: int, sid: str, name: str, a: dict, stranger: bool = False, post=None) -> str:
    r = _mcp(tid, sid, 'tools/call', {'name': name, 'arguments': a}, stranger=stranger, post=post)
    said = '\n'.join(str(c.get('text') or '') for c in r.get('content') or [] if isinstance(c, dict))
    if r.get('isError'): raise ValueError(said or f'{name} failed')
    return said


# ── THE WORKING FOLDER, the CLI's: a general task's agent works where a general CLI does (llm.make_cli_llm: Taskuary's scratch folder),
# a coding task's in the checkout its agent works in (agentchannels.cwd_of), else that task's own folder until a checkout is chosen
def workdir(store, tid: int) -> str:
    from . import config
    from .general import GENERAL_KINDS
    task = store.get_task(tid) or {}
    if task.get('Kind') not in GENERAL_KINDS:
        from . import agentchannels, repochoice
        d = agentchannels.cwd_of(store, tid) or str(repochoice.scratch(tid))
    else: d = str(config.home() / 'scratch')
    Path(d).mkdir(parents=True, exist_ok=True)
    return d


def _path(store, tid: int, raw) -> Path:
    raw = str(raw or '').strip().strip('"' + "'")
    if not raw: raise ValueError('no path given')
    p = Path(raw).expanduser()
    return (p if p.is_absolute() else Path(workdir(store, tid)) / p).resolve()


def where_line(store, tid: int) -> str:
    from . import outputs
    return f'YOUR WORKING FOLDER is {workdir(store, tid)}. Files you make for the owner go in {outputs.folder(tid)}.'


def env_of(store, tid: int, sid: str) -> dict:
    "What a command runs with: the session's own environment, as a CLI's (terminal.session_env), its browser session named (browserview.env)."
    import os
    from . import browserview, terminal
    from .clis import HEADLESS_ENV
    return {**os.environ, **terminal.session_env('assistant', tid, sid=sid), **browserview.env(sid), **HEADLESS_ENV}


SAY = {}                       # (tid, sid) -> how this turn says a step of Taskuary's own (the browser being set up) in the chat
STOPS = {}                     # (tid, sid) -> this turn's Stop switch: a command under way is killed by it (_hands)
BRAINS = {}                    # (tid, sid) -> the brain this turn runs on: web_search asks it, with its own search on


def _search(store, tid: int, sid: str, q: str) -> str:
    "The model's OWN web search (llm `search`, each provider's own); a connected search card where the card has none or refuses it."
    brain = BRAINS.get((tid, sid))
    if callable(getattr(brain, 'search', None)):
        try: return _cut(brain.search(q))
        except Exception as e: logger.info(f'apiagent: task {tid} native search refused, trying a search card - {e}')
    cards = [c for c in store.list_connectors() if c['Type'] in SEARCHERS and c['Active'] and c.get('HasSecret')]
    if not cards: raise ValueError('this AI could not search the web, and no search service is connected - web_fetch a page you know, '
                                   'or browser_open a search page')
    c = cards[0]
    return call_taskuary(tid, sid, 'run_system', {'type': c['Type'], 'connector_id': c['ConnectorId'], 'query': q}, stranger=(tid, sid) in STRANGERS)


def _hands(store, tid: int, sid: str, name: str, a: dict) -> str:
    "A CLI's own hands, run by the server: files, the web, and commands under the ONE gate a CLI's commands pass (hooks.command_gate)."
    import os
    if name in ('files_list', 'file_read'):
        # ...a read outside the task's own folders waits for the owner, as a CLI's does (readgate.py)
        from . import readgate, shellgate
        cwd = workdir(store, tid)
        held, never = readgate.judge(store, tid, [_path(store, tid, a.get('path') or '.')], cwd)
        if never: raise ValueError(never)
        if held: return (shellgate.check(store, tid, sid, '', cwd=cwd, reads=held).get('hookSpecificOutput') or {}).get('permissionDecisionReason') or shellgate.HELD
    if name == 'files_list':
        d = _path(store, tid, a.get('path') or '.')
        if not d.is_dir(): raise ValueError(f'{d} is not a folder')
        kids = sorted(d.iterdir(), key=lambda k: (not k.is_dir(), k.name.lower()))[:500]
        return f'{d}' + chr(10) + (chr(10).join(f"{k.name}{'/' if k.is_dir() else ''}" for k in kids) or '(empty)')
    if name == 'file_read':
        from . import attachtext
        p = _path(store, tid, a.get('path'))
        if not p.is_file(): raise ValueError(f'no file at {p}')
        if p.suffix.lower() in ('.pdf', '.docx', '.xlsx', '.pptx'):
            got = attachtext.read(p.name, p.read_bytes())
            return _part(got.get('text') or f"{p.name}: {got.get('note') or 'nothing in it to read'}", a)
        return _part(p.read_text(encoding='utf-8', errors='replace'), a)
    if name in ('file_write', 'file_edit'):
        # A WORD OR EXCEL FILE IS MADE, NOT SPELLED OUT (officefiles): written as text it was a file no one could open, and the agent went on
        # to build one by hand in PowerShell - a script of output a step, for as long as it took
        from . import officefiles as of
        p = _path(store, tid, a.get('path')); to = _path(store, tid, a['save_as']) if a.get('save_as') else p
        to.parent.mkdir(parents=True, exist_ok=True)
        if name == 'file_edit':
            if not p.is_file(): raise ValueError(f'no file at {p}')
            if of.is_office(p): return f'Edited {to} ({of.edit(p, str(a.get("old") or ""), str(a.get("new") or ""), to)}).'
            text, old = p.read_text(encoding='utf-8'), str(a.get('old') or '')
            if not old or text.count(old) != 1: raise ValueError(f'`old` occurs {text.count(old) if old else 0} times in {p.name} - it must be exactly once')
            to.write_text(text.replace(old, str(a.get('new') or '')), encoding='utf-8')
        elif of.is_office(p): return f'Wrote {p}: {of.write(p, str(a.get("text") or ""))} ({p.stat().st_size} bytes).'
        else: p.write_text(str(a.get('text') or ''), encoding='utf-8')
        return f'{"Edited" if name == "file_edit" else "Wrote"} {to} ({to.stat().st_size} bytes).'
    if name == 'web_fetch':
        # ...BY THE ROAD A LINKED DOCUMENT TAKES (linkdocs): a page in its own charset, a sheet as its rows, a Google or SharePoint file
        # through the card that reaches it - not every answer decoded as UTF-8 text, which read a workbook as its zip bytes
        from . import linkdocs
        u = _url(a.get('url'))
        d = linkdocs.classify(u)
        if not d: raise ValueError(f'{u} is not a page or document that reads as text (a picture, a script) - browser_open it to see it')
        got = linkdocs.read(store, d, auto=False, full=True)
        if 'note' in got: raise ValueError(f"{u} was not read: {got['note']}. If it needs a sign-in or a click, browser_open it instead")
        head = ' - '.join(x for x in (f'PAGE {u}', str(got.get('title') or '').strip(), str(got.get('more') or '')) if x)
        return _part(head + chr(10) + str(got.get('text') or '').strip(), a)
    if name == 'web_search': return _search(store, tid, sid, str(a.get('query') or ''))
    if name == 'run_command':
        from . import hooks, shellgate, spawn
        cmd, why = str(a.get('command') or '').strip(), ' '.join(str(a.get('why') or '').split())[:300]
        if not cmd: raise ValueError('no command given')
        cwd, shell = workdir(store, tid), 'PowerShell' if os.name == 'nt' else 'Bash'
        held = hooks.command_gate(store, tid, sid, cmd, shell, cwd, ask=False, about=why)
        if held: return (held.get('hookSpecificOutput') or {}).get('permissionDecisionReason') or f'{shellgate.HELD}.'
        import subprocess, time
        # ...its own process group off Windows, so the whole of it can be ended (_kill)
        p = spawn.popen(shellgate._argv(shell, cmd), cwd=cwd, env=env_of(store, tid, sid), stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                        stdin=subprocess.DEVNULL, start_new_session=True)
        stop, end = STOPS.get((tid, sid)), time.monotonic() + RUN_WAIT
        while True:
            try: out, errs = p.communicate(timeout=0.5); break
            except subprocess.TimeoutExpired:
                # STOP ENDS THE COMMAND TOO, and what it started: a build went on for its ten minutes under a turn the owner had stopped
                if stop is not None and stop.is_set(): _kill(p); raise RuntimeError('stopped')
                if time.monotonic() > end: _kill(p); raise ValueError(f'it ran past {RUN_WAIT // 60} minutes and was stopped')
        said = (shellgate.text(out) + shellgate.text(errs)).strip()
        return _cut(f'exit {p.returncode} in {cwd}' + chr(10) + (said or '(no output)'))
    raise ValueError(f'no tool named {name}')


def _kill(p):
    "The command and everything it started: ending its shell alone left the build under it running."
    import os, signal
    from . import spawn
    try:
        if os.name == 'nt': spawn.run(['taskkill', '/PID', str(p.pid), '/T', '/F'], capture_output=True, timeout=15)
        else: os.killpg(p.pid, signal.SIGKILL)
    except Exception as e: logger.info(f'apiagent: command {p.pid} not ended as a whole - {e}')
    try: p.kill(); p.communicate(timeout=5)
    except Exception: pass


def _await(f, stop):
    """f(), given up AT ONCE when the owner stops the turn. Stop was read between steps only, so it waited out whatever was under way - a
    model's answer (minutes, on a long one), a page, a command. The step runs on a thread of its own; stopped, the turn ends now and
    the step's answer is dropped when it comes (a command is killed, _hands)."""
    if stop is None: return f()
    import contextvars, threading
    box = {}
    def go():
        try: box['out'] = f()
        except BaseException as e: box['err'] = e
    t = threading.Thread(target=contextvars.copy_context().run, args=(go,), daemon=True, name='apiagent-step'); t.start()
    while t.is_alive():
        t.join(0.2)
        if stop.is_set() and t.is_alive(): raise RuntimeError('stopped')
    if 'err' in box: raise box['err']
    return box['out']


def run_tool(store, tid: int, sid: str, name: str, a: dict) -> str:
    "One tool call, run by the server. Raises ValueError with words the model can act on."
    from . import browserview as bv, browsergate as bg
    if (tid, sid) in OFFERED and name not in OFFERED[(tid, sid)]: raise ValueError(f'{name} is not one of your tools on this task')
    if SLIMMED in json.dumps(a, ensure_ascii=False, default=str):
        raise ValueError('an argument is the line that stands for text you sent on an earlier call, not the text - nothing was done; '
                         'send the full text itself (read the file again if you need it)')
    if name not in LOCAL or (name == 'show' and TOOLBOX.get((tid, sid))):
        if name not in (TOOLBOX.get((tid, sid)) or ()): raise ValueError(f'no tool named {name}')
        return call_taskuary(tid, sid, name, a, stranger=(tid, sid) in STRANGERS)
    if name.startswith('browser_') and (tid, sid) in STRANGERS: raise ValueError("a stranger's task gets no browser")
    if name == 'show':
        from . import agenttools
        return agenttools.show_files(store, tid, a.get('files') or [])
    if name in HANDS: return _hands(store, tid, sid, name, a)
    if not bv.installed():
        # NO BROWSER ON THIS COMPUTER YET: Taskuary fetches its own and the call waits for it, each step said in the turn (browserruntime)
        why = bv.set_up(SAY.get((tid, sid))) if bv.can_set_up() else 'agent-browser is not installed'
        if why: raise ValueError(f'the browser could not be set up on this computer: {why}. Tell the owner that in one plain line, in these '
                                 'words, and that asking again tries again - never send them to a settings page to install it')
    if name == 'browser_open':
        u = _url(a.get('url'))
        if not bv.state(sid, fresh=True).get('open'):
            held = bg.check(store, tid, sid, shlex.join([bg.EXE, 'open', u]))       # a magic link is judged like a click (browsergate.carries)
            if held: return (held.get('hookSpecificOutput') or {}).get('permissionDecisionReason') or bg.HELD
            if not bv.start(sid, u): raise ValueError(bv.FAILED_WHY)
        else:
            # ...A PAGE THAT CAME BUT NEVER FINISHED (an image or a tracker on it still loading) is open all the same: agent-browser's
            # "Timed out ... waiting for load state" over a page whose text was there read as a failed open (the browser-read round,
            # 2026-11-18). On that address, the agent gets the page and the line; anywhere else, the failure
            try: _act(store, tid, sid, ['open', u])
            except ValueError as e:
                if not bg._same_page(bg.address(sid), u): raise
                return f'(It had not finished loading - {str(e).strip()} - this is what has arrived.)\n' + run_tool(store, tid, sid, 'browser_look', {})
        return run_tool(store, tid, sid, 'browser_look', {})
    if name == 'browser_look':
        rc, snap = bg._run(sid, ['snapshot', '-c'] if a.get('full') else ['snapshot', '-i', '-c'], 30, 'look')
        if rc != 0: raise ValueError(snap.strip()[-300:] or 'the page could not be read')
        return _part(f'PAGE {bg.address(sid)}\n{snap.strip()}', a)
    if name == 'browser_click': return _act(store, tid, sid, ['click', str(a.get('ref') or '')])
    if name == 'browser_fill': return _act(store, tid, sid, ['fill', str(a.get('ref') or ''), str(a.get('text') or '')])
    if name == 'browser_press': return _act(store, tid, sid, ['press', str(a.get('key') or '')])
    if name == 'browser_screenshot':
        import time
        from . import outputs
        d = outputs.folder(tid); d.mkdir(parents=True, exist_ok=True)
        p = d / f'page-{time.strftime("%H%M%S")}.png'
        rc, said = bg._run(sid, ['screenshot', str(p)], 30, 'shot')
        if rc != 0 or not p.is_file(): raise ValueError(said.strip()[-300:] or 'no picture was taken')
        return f'Saved {p} - call show with it to put it in the chat.'
    raise ValueError(f'no tool named {name}')


TOOLBOX, STRANGERS, OFFERED = {}, set(), {}   # ...and OFFERED: every name a turn was offered - nothing else runs          # (tid, sid) -> the Taskuary tool names this turn was offered; the sessions on a stranger's task
READS = {}                     # (tid, sid) -> the Taskuary tools that only read its own records (taskuary_tools)


def forget(tid: int, sid: str):
    """A SESSION THAT IS GONE KEEPS NOTHING HERE. What each was offered stayed for every session there had ever been, until the app was
    closed. Asked by a session with no turn on (general: idled out, closed), never under one: `call` reads these, and every turn that
    comes after says them again first (tools_for)."""
    for d in (TOOLBOX, OFFERED, DEFERRED, READS): d.pop((tid, sid), None)
    STRANGERS.discard((tid, sid))


def tools_for(tid: int, sid: str, browser: bool, stranger: bool = False, post=None, hands: bool = True) -> list:
    """What an API session is offered this turn: Taskuary's toolbox (the CLI's, gated as the CLI's), and the browser on the owner's own task
    where agent-browser is installed. `show` is the server's where its toolbox answered, else the local one."""
    own = taskuary_tools(tid, sid, stranger=stranger, post=post)
    TOOLBOX[(tid, sid)] = {t['function']['name'] for t in own}
    (STRANGERS.add if stranger else STRANGERS.discard)((tid, sid))
    # ...and a CLI's own hands where the owner gave them (general.full_hands: 'look things up only' reads, never writes or runs). A stranger's
    # task gets none of them: its CLI runs read-only on its words alone (origin.launch_mode 'look')
    mine = [] if stranger else [*(BROWSER if browser else []), *FILES, *WEB, *((WRITE + SHELL) if hands else [])]
    out = [t for t in own if t['function']['name'] != LOAD] + mine + ([] if 'show' in TOOLBOX[(tid, sid)] else [SHOW])
    OFFERED[(tid, sid)] = {t['function']['name'] for t in out}
    later = [t for t in out if t['function']['name'] in LATER]
    DEFERRED[(tid, sid)] = {t['function']['name']: t for t in later}
    OFFERED[(tid, sid)].add(LOAD)
    return [t for t in out if t['function']['name'] not in LATER] + [loader(later)]


# TOOLS OFFERED AS THE WORK NEEDS THEM (the owner's standing rule, 2026-11-02: "model sees all, tools progressive"; 2026-11-10: "the ai limits as
# much as possible to use ai"): the whole toolbox rode on every step of every turn. The tools a turn reaches for are offered (a line each,
# SHORT); the rest are found by find_tools - by a name or by words - which answers with the whole words of what fits
# and adds a named one's schema to the END of the list for the rest of the turn (never reordered: what goes before stays the same bytes for
# the provider's cache). Named here is every tool a measured turn did not reach for; anything not named stays in the core. ...but never
# file_write / file_edit (an invoice to fill, 2026-11-15): a model shown only their names said it had no way to make the file, and stopped.
# ...and THE BROWSER'S OTHER HANDS COME WITH ITS FIRST PAGE (browser_open loads BROWSER_MORE): a page is only ever looked at and clicked after one is open
LATER = frozenset({'read_attachment', 'search_knowledge', 'owner_memory', 'calendar', 'list_systems', 'run_system', 'remind', 'ask_stronger',
                   'note_peers', 'use_repo', 'find_repos', 'propose_land', 'withdraw_draft', 'sign_form', 'answer_invite', 'set_up_meeting', 'share',
                   'search_tasks', 'person', 'guide', 'todos', 'check_back', 'browser_look', 'browser_click', 'browser_fill', 'browser_press',
                   'browser_screenshot', 'web_fetch', 'files_list', 'reply_not_needed', 'propose', 'my_task', 'new_task'})
BROWSER_MORE = ('browser_look', 'browser_click', 'browser_fill', 'browser_press', 'browser_screenshot')
LOAD = 'find_tools'
DEFERRED = {}                  # (tid, sid) -> {name: schema} of the tools this turn named but has not loaded
def loader(later: list) -> dict:
    from .agenttools import SHORT as TOOL_LINES
    return _fn(LOAD, TOOL_LINES[LOAD], _S({'query': {'type': 'string'}}, ['query']))


def load(tid: int, sid: str, tools: list, names) -> str:
    "Add the named tools' schemas to the END of `tools` (in place): what was offered before them stays the same bytes."
    have, kept = {t['function']['name'] for t in tools}, DEFERRED.get((tid, sid)) or {}
    new = [kept[n] for n in dict.fromkeys(str(n) for n in (names or [])) if n in kept and n not in have]
    tools.extend(new)
    return f"Loaded {', '.join(t['function']['name'] for t in new)} - call them now." if new else ''


def find(tid: int, sid: str, tools: list, query) -> str:
    "find_tools: the whole words of the tools this session has that `query` names or asks for - and those not yet offered, added (load)."
    from . import agenttools as at
    mine = (OFFERED.get((tid, sid)) or {t['function']['name'] for t in tools}) - {LOAD}
    words = {n: FULL.get(n) or (at.instructions(n) if n in at.TOOLS else n) for n in mine}
    hits = at.found(query, words)
    if not hits: return f"No tool fits {str(query or '')!r} - name one, or say what it should do in other words."
    return '\n\n'.join([*(words[n] for n in hits), load(tid, sid, tools, hits)]).strip()


BUDGET = 300_000               # the conversation KEPT, in characters (~75K tokens)
DROPPED = '(dropped to save room - run it again if you need it)'
# WHAT ONE CALL SENDS (the owner, 2026-11-10: "they spent 25 dollars in one day? 32 million tokens?"): every step of a turn sent the whole
# conversation again, every earlier tool answer in full - a turn of twelve reads paid for the first page twelve times. A call now sends the
# answers of the last KEEP_STEPS steps whole and an older one as a line naming the call, which the agent can make again; the conversation
# kept is untouched. Older answers stay stubbed once stubbed, so what goes before them is the same bytes call after call (the provider's
# prompt cache), and the whole is held under the `agent_request_chars` setting.
# ...AND THE LINE MOVES IN WHOLE BLOCKS (the cache audit, 2026-11-14): stubbed per step, the line between whole and stubbed moved on every
# call, and each step from the fourth wrote the last three answers to the cache again. It moves KEEP_STEPS steps at a time now, so the calls
# between are read from the cache whole, and the newest KEEP_STEPS to 2*KEEP_STEPS-1 answers go whole.
KEEP_STEPS = 3
# ...AND THE BOUND IS THE WHOLE CALL (the gateway's own per-call log, 2026-11-15: an invoice job of 139 calls at 35-60K prompt tokens each,
# 6.4M in all): the bound counted the messages' text alone - never the tools' schemas, never the arguments of the calls the agent made - so
# every file it wrote whole rode on every later call, and 120,000 characters of "conversation" was a call of 45K tokens and more. One
# function measures a call as it goes out (size) and every call of every card is held under REQUEST_CHARS by it (sent): the system, the
# tools and the task lead (the cached prefix, ~50,000 characters on a fresh install), which leaves the working window ~30,000 - a file
# read or two and what came of them. A picture counts as IMAGE_CHARS, what a model reads of it, never its base64 bytes.
# ...and a Gemini model's THOUGHT SIGNATURES (provider_specific_fields, ~2-4,000 base64 characters a step, which it must be handed back) are
# carried but not read as tokens (live, gemini-2.5-pro: 237,000 characters sent, 29,000 tokens counted) - counted, they narrowed the window for nothing
REQUEST_CHARS, IMAGE_CHARS, OPAQUE = 80_000, 4_000, ('provider_specific_fields', 'thinking_blocks')
def _read(o):
    if isinstance(o, list): return [_read(v) for v in o]
    return {k: _read(v) for k, v in o.items() if k not in OPAQUE} if isinstance(o, dict) else o
def size(msgs: list, tools=()) -> int:
    "One call's characters as a model reads them: every message (the calls' arguments too) and the tools' schemas."
    pics = sum(len(p['image_url'].get('url') or '') - IMAGE_CHARS for m in msgs for p in (m.get('content') if isinstance(m.get('content'), list) else ())
               if isinstance(p, dict) and isinstance(p.get('image_url'), dict))
    return len(json.dumps({'messages': _read(msgs), 'tools': list(tools or ())}, separators=(',', ':'), ensure_ascii=False, default=str)) - pics
def _whole_from(msgs: list, keep: int = KEEP_STEPS) -> int:
    "Where whole answers begin: the step at the last block boundary at least `keep` steps back (0: everything whole)."
    steps = [i for i, m in enumerate(msgs) if m.get('tool_calls')]
    return steps[(len(steps) - keep) // keep * keep] if len(steps) >= 2 * keep else 0
def _stub(name, args, n) -> str: return f'(the answer to {name}({_slim(args)[:160]}), {n:,} characters, is not repeated here - call it again if you need it)'
def _slim(args) -> str:
    "A call's arguments with each long text said by its length: the file it wrote whole is not sent again on every call after (WRITE)."
    args = args if isinstance(args, str) else json.dumps(args or {})
    try: a = json.loads(args or '{}')
    except ValueError: return args if len(args) <= STUB_AT else json.dumps({'arguments': _said(args)})
    if not isinstance(a, dict) or not any(isinstance(v, str) and len(v) > STUB_AT for v in a.values()): return args
    return json.dumps({k: _said(v) if isinstance(v, str) and len(v) > STUB_AT else v for k, v in a.items()}, ensure_ascii=False)
# ...AND A LINE IS NEVER TAKEN FOR THE TEXT (the real run on gemini-2.5-pro, 2026-11-15): shown its earlier file_edit as "(1,685 characters, not
# repeated)", the model made the same call again with that line as `new`, and it went into the invoice. The line says it is not text, and a
# call carrying it is refused before it runs (run_tool) - the agent is told to send the text itself
SLIMMED = 'characters sent here earlier - not repeated, and not text to send again'
def _said(v: str) -> str: return f'[{len(v):,} {SLIMMED}]'
STUB_AT = 300


# A READ MADE AGAIN IN ONE TURN IS ANSWERED FROM THE FIRST: a model that searched or read the same thing twice paid for the whole answer twice,
# and the server ran it twice. Only a tool that reads Taskuary's own records or the agent's files (READS, FILES) is answered so, only while
# nothing else has run since: any other call - a tick, a write, a command, a click - clears the turn's record, since it may have changed it
def _again(msgs: list, first: dict, text: str, name: str, tools=(), budget: int = REQUEST_CHARS) -> str:
    "A pointer where the first answer still goes whole with every call (sent); else that answer again, as it came, without running it."
    if first.get('content') == text and any(m.get('tool_call_id') == first.get('tool_call_id') and m.get('content') == text for m in sent(msgs, tools, budget)):
        return f'(the same as your earlier {name} call this turn, answered above - nothing since could change it)'
    return text


def _size(m: dict) -> int:
    c = m.get('content')
    said = len(c) if isinstance(c, str) else sum(len(p.get('text') or '') for p in c or [])      # a picture is not counted by its bytes
    return said + sum(len((t.get('function') or {}).get('arguments') or '') for t in m.get('tool_calls') or [])


def _fit(msgs: list, keep: int = 6, budget: int = None):
    """Under `budget` (BUDGET), in place: the oldest tool answers go first (their calls stay, so the model still sees what it did), then whole
    turns after the first, oldest first. Never the system, the first message (the task, said in full) or the newest `keep`."""
    over = sum(map(_size, msgs)) - (budget or BUDGET)
    for m in msgs[2:-keep]:
        if over <= 0: return
        if m.get('role') == 'tool' and m.get('content') != DROPPED: over -= _size(m) - len(DROPPED); m['content'] = DROPPED
    while over > 0:
        nxt = next((j for j in range(3, len(msgs) - keep) if msgs[j].get('role') == 'user'), None)
        if nxt is None: return
        over -= sum(map(_size, msgs[2:nxt])); del msgs[2:nxt]


def _stubbed(msgs: list, cut: int) -> list:
    "`msgs` with every tool answer and call argument before `cut` said as a line: copies, the conversation kept is untouched."
    calls = {c.get('id') or (c.get('function') or {}).get('name'): c.get('function') or {} for m in msgs[:cut] for c in m.get('tool_calls') or []}
    out = []
    for i, m in enumerate(msgs):
        c = m.get('content')
        if i < cut and m.get('role') == 'tool' and isinstance(c, str) and len(c) > STUB_AT:
            f = calls.get(m.get('tool_call_id')) or {}
            m = {**m, 'content': _stub(f.get('name') or 'a tool', f.get('arguments'), len(c))}
        elif i < cut and m.get('tool_calls'):
            m = {**m, 'tool_calls': [{**k, 'function': {**k['function'], 'arguments': _slim(k['function'].get('arguments'))}} if k.get('function') else k
                                     for k in m['tool_calls']]}
        out.append(dict(m))
    return out


def sent(msgs: list, tools=(), budget: int = REQUEST_CHARS, keep: int = KEEP_STEPS) -> list:
    """What one call sends of the conversation `msgs` beside `tools`, under `budget` as size() counts it: tool answers and call arguments
    before the last block of steps (_whole_from) as lines; over the bound, the whole window moves on a step at a time - never past the
    newest step, whose answers the model has not read yet - and then the oldest turns go (_fit)."""
    cut, steps = _whole_from(msgs, keep), [i for i, m in enumerate(msgs) if m.get('tool_calls')]
    out = _stubbed(msgs, cut)
    for at in (s for s in steps if s > cut):
        if size(out, tools) <= budget: break
        out = _stubbed(msgs, at)
    if (over := size(out, tools) - budget) > 0:
        _fit(out, budget=max(1, sum(map(_size, out)) - over))
        if size(out, tools) > budget: logger.info(f'apiagent: a call of {size(out, tools):,} characters goes over the {budget:,} bound - its newest step alone')
    return out


def _setting(store, key: str, default: int) -> int:
    try: return max(1, int(store.get_setting(key) or default))
    except (TypeError, ValueError, AttributeError): return default


def _settle(msgs: list):
    "Every call answered, in place: one a stopped turn never ran is told so - a call left open has the next turn's first call turned down."
    at = max((i for i, m in enumerate(msgs) if m.get('tool_calls')), default=None)
    if at is None: return
    done = {m.get('tool_call_id') for m in msgs[at + 1:] if m.get('role') == 'tool'}
    msgs.extend({'role': 'tool', 'tool_call_id': i, 'content': 'no answer - the turn ended first'}
                for c in msgs[at]['tool_calls'] if (i := c.get('id') or str((c.get('function') or {}).get('name') or '')) not in done)


def turn(brain, store, tid: int, sid: str, system: str, user: str, max_tokens: int, trace=None, cancel=None, tools=None,
         steps: int = None, images=None, history: list = None) -> str:
    """One turn of an API brain with tools: call, run, answer back, until it answers in words. `trace(kind, name, detail)` sees each
    step as a CLI's do (tool_call / tool_result), so the pane and the chat draw them the same - a `show` among them as its pictures.

    `history` IS THE CARD'S OWN CONVERSATION (the spine audit, 2026-11-09), kept by its session as a CLI keeps its own: the turn opens on
    it and leaves this turn in it - what it called, what came back, what it said, and what a stopped turn had done. Every turn used to
    be one system and one user message, so whatever the agent had read with its tools was gone by the owner's next line - only its own
    last answer came back, as chat text - and it opened the same pages and files again. Kept under BUDGET (_fit)."""
    from . import llm
    tools = list(tools) if tools is not None else [*BROWSER, SHOW]
    BRAINS[(tid, sid)] = brain
    if trace: SAY[(tid, sid)] = lambda s: trace('progress', 'browser', s)
    STOPS[(tid, sid)] = cancel
    content = ([{'type': 'image_url', 'image_url': {'url': f'data:{ct};base64,{llm.vision_safe(ct, b64)}'}} for ct, b64 in images]
               + [{'type': 'text', 'text': user}]) if images else user
    mine = {'role': 'user', 'content': content}
    msgs, begun = [{'role': 'system', 'content': system}, *(history or []), mine], False
    load(tid, sid, tools, [(c.get('function') or {}).get('name') for m in history or [] for c in m.get('tool_calls') or []])   # what it used before
    why, read, idle, seen = 'You are out of steps for this turn.', set(), 0, {}
    reads = {*READS.get((tid, sid), ()), *(t['function']['name'] for t in FILES)}
    budget, idle_n = _setting(store, 'agent_request_chars', REQUEST_CHARS), _setting(store, 'agent_idle_steps', IDLE_STEPS)
    stopped = lambda: cancel is not None and cancel.is_set()
    def said(m):
        text = llm.said_text(m)
        if text: msgs.append({'role': 'assistant', 'content': text})
        return text
    try:
        for i in (range(steps) if steps else __import__('itertools').count()):
            # ...stopped before its first answer, a conversation under way still heard the line: the next turn says only its own
            if stopped(): begun = begun or bool(history); raise RuntimeError('stopped')
            _fit(msgs)
            try: m = _await(lambda: brain.chat(sent(msgs, tools, budget), tools, max_tokens), cancel)
            except Exception as e:
                if stopped(): begun = begun or bool(history); raise
                # ...the conversation it was handed is what this call could not take (too long for the model now, or a gateway that
                # dropped it): nothing of this turn has run, so it is asked again with the conversation said whole (general)
                if i == 0 and history: raise Lost(str(e)) from e
                # a model behind a gateway that turns `tools` down on the FIRST call: the turn is asked the plain way instead (general)
                if i == 0 and isinstance(e, RuntimeError) and _REFUSED.search(str(e)): raise ToolsRefused(str(e)) from e
                raise
            begun = True
            calls = m.get('tool_calls') or []
            if not calls: return said(m)
            msgs.append({'role': 'assistant', **{k: v for k, v in m.items() if v is not None}})          # as sent: a Gemini model's thought signature rides on it
            new = False
            for c in calls:
                f = c.get('function') or {}
                name = str(f.get('name') or '')
                try: a = json.loads(f.get('arguments') or '{}') or {}
                except ValueError: a = {}
                if trace: trace('tool_call', name, {'args': a})
                if name in (DEFERRED.get((tid, sid)) or {}): load(tid, sid, tools, [name])       # called by the name it was given: loaded as it runs
                if name == 'browser_open': load(tid, sid, tools, BROWSER_MORE)
                key, again = (name, json.dumps(a, sort_keys=True, default=str)), False
                if name in reads and key in seen: out, err, again = _again(msgs, *seen[key], name, tools, budget), False, True
                else:
                    try: out, err = (find(tid, sid, tools, a.get('query') or ' '.join(map(str, a.get('names') or []))) if name == LOAD else _await(lambda: run_tool(store, tid, sid, name, a), cancel)), False
                    except Exception as e:
                        if stopped(): raise
                        out, err = f'{name} failed: {e}', True
                        logger.info(f'apiagent: task {tid} {name} failed - {e}')
                    if name not in reads and name != LOAD: seen.clear()
                if trace: trace('tool_result', name, {'result': out, 'is_error': err})
                msgs.append(ans := {'role': 'tool', 'tool_call_id': c.get('id') or name, 'content': _cut(out, CAP + 200)})   # ...a part's own line kept
                if name in reads and not err and not again: seen[key] = (ans, ans['content'])
                if again: continue                  # ...and it is nothing new read: going in circles is still counted (idle)
                # PROGRESS IS SOMETHING NEW READ (the owner, 2026-11-10: "are we leaking tokens?"): a small model calling a search again
                # with other words, or a page that failed again, is not working - a line no earlier answer of this turn held is
                lines = {' '.join(l.split()) for l in str(out).splitlines() if l.strip()} if not err else set()
                new, read = new or bool(lines - read), read | lines
            idle = 0 if new else idle + 1
            if idle >= idle_n:
                why = f'Your last {idle} steps brought nothing you had not read already.'
                logger.info(f'apiagent: task {tid} made {idle} steps with nothing new - asked for where it got')
                if trace: trace('progress', 'agent', f'Stopped after {idle} steps that found nothing new - say what to try next and it carries on.')
                break
        # going in circles (or out of a caller's own bound): one last answer in words, no more tools - where it got and what is left
        msgs.append({'role': 'user', 'content': f'{why} Say what you did, what you found, and what is left.'})
        return said(_await(lambda: brain.chat(sent(msgs, tools, budget), tools, max_tokens, tool_choice='none'), cancel))
    finally:
        # ...kept once the model has answered at all: a turn stopped or failed part-way keeps what it did, so Continue goes on from there.
        # Its pictures are not carried (the model saw them; their bytes would ride on every later call)
        if history is not None and begun: mine['content'] = user; _settle(msgs); history[:] = msgs[1:]
        # ...and what was this TURN's goes with it - its brain, its Stop switch, its way to say a step: a step still under way has read its own
        for d in (SAY, STOPS, BRAINS): d.pop((tid, sid), None)
