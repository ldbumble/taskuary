"""EVERY AGENT'S BROWSER AND DESKTOP PRESSES ARE HELD AT THE COMMAND ITSELF, whatever AI runs it (the design round, 2026-11-18).

The hold used to live in the AI's own tool-call road: Claude's PreToolUse hook could refuse a shell line, ACP asked for some calls and
not others, and a Codex run asked for none - its agent pressed a site's final Post itself while every brief said the press was held.
So the hold moved under the road: every task session has a folder first on its PATH (terminal.session_env) holding an `agent-browser`
and an `agent-desktop` of Taskuary's own. Each runs main() here, which lets a command that only looks go straight to the real program,
and asks the server (/api/agent/gate -> judge, the very function the API agent's browser calls) about every other one BEFORE it runs:
browsergate / agentdesktop decide, and a press that can't be undone is held on the task for the owner's one press. Held, the command
prints why and exits 1 without running; Taskuary unreachable, an act fails closed the same way.

What this still does not cover, said plainly: an agent that reaches the real program by its full path or through `npx`, or drives
Chrome or the desktop some other way. It gates the road agents are told to take (browserview.brief), on every AI."""
import json, os, shlex, subprocess, sys

GATED = ('agent-browser', 'agent-desktop')
MARK = '/api/agent/gate'
WAIT = 150                      # a snapshot and one verdict (browsergate.JUDGE_WAIT), and a page launched for its first open
_DIR: dict = {}


def folder() -> str:
    """The folder put first on a task session's PATH: one launcher per gated program, each running main() with this interpreter and
    naming its own folder, so the real program is found past it. '' where it could not be written."""
    if 'd' in _DIR: return _DIR['d']
    from loguru import logger
    from . import config
    d, py = config.home() / 'bin' / 'gate', sys.executable
    try:
        d.mkdir(parents=True, exist_ok=True)
        for n in GATED:
            _write(d / f'{n}.cmd', f'@"{py}" -m taskuary.gatecmd "%~dp0." {n} %*\r\n')
            _write(d / n, f'#!/bin/sh\nexec "{py.replace(chr(92), "/")}" -m taskuary.gatecmd "$(dirname "$0")" {n} "$@"\n', 0o755)
        _DIR['d'] = str(d)
    except OSError as e:
        logger.warning(f'the browser and desktop hold could not be put on the agents\' PATH - {e}'); _DIR['d'] = ''
    return _DIR['d']


def _write(p, text: str, mode: int = None):
    try:
        if p.read_text(encoding='utf-8') == text: return
    except OSError: pass
    p.write_text(text, encoding='utf-8', newline='')
    if mode: os.chmod(p, mode)


def _same(a: str, b: str) -> bool: return os.path.normcase(os.path.realpath(a or '.')) == os.path.normcase(os.path.realpath(b or '.'))


def real(name: str, gate: str) -> str:
    "The real program behind `name`, looked up on a PATH without the gate's folder (os.environ's is cut, so what it runs is cut too)."
    os.environ['PATH'] = os.pathsep.join(p for p in os.environ.get('PATH', '').split(os.pathsep) if p and not _same(p, gate))
    if name == 'agent-browser':
        from . import browserview
        return browserview.program()
    from . import agentdesktop
    return agentdesktop.path()


def asks(name: str, cmd: str) -> tuple:
    "(is it a press to judge, must the server see it at all): a look runs untouched; an open goes by the server, which brings the page up."
    from . import agentdesktop, browsergate
    if name == agentdesktop.EXE: return (bool(agentdesktop.acts(cmd)),) * 2
    act = bool(browsergate.acts(cmd))
    return act, act or bool(browsergate.opens(cmd))


def ask(name: str, args: list) -> str:
    """'' runs the command; else why it was not run. Asked of the server this session belongs to, as `taskuary --note` asks it: its token
    from the session (TASKUARY_TOKEN - or the app's own config where a CLI strips token-named variables from its shell, as Codex does)."""
    from . import config, hooks
    from .guard import TASK_ENV, TASK_HDR
    cmd = shlex.join([name, *args])
    act, call = asks(name, cmd)
    if not call: return ''
    env, srv = os.environ, config.load()['server']
    body = json.dumps({'task': env.get('TASKUARY_TASK') or '', 'sid': env.get('TASKUARY_SID') or '', 'cmd': cmd, 'cwd': os.getcwd()}).encode()
    hdr = {'Content-Type': 'application/json', **({'X-Taskuary-Token': srv['token']} if srv.get('token') else {}),
           **({TASK_HDR: env[TASK_ENV]} if env.get(TASK_ENV) else {})}
    import urllib.request
    try:
        req = urllib.request.Request((env.get('TASKUARY_URL') or hooks.base_url()) + MARK, body, hdr)
        with urllib.request.urlopen(req, timeout=WAIT) as r: return str(json.load(r).get('why') or '')
    except Exception as e:
        if not act: return ''
        return (f'Taskuary held this for the owner: it could not be asked whether this press may run ({str(e)[:120]}), so nothing was '
                'done. Run it again; if it is refused like this again, tell the owner in one line what you were about to do and end your turn.')


def judge(store, tid: int, sid: str, cmd: str, cwd: str = '', brain=None) -> str:
    """THE ONE DECISION on a browser or desktop command, made before it runs: '' lets it run; else why it waits for the owner. The
    browser comes up here, at the agent's first navigate, never before it has an address (browserview.on_demand)."""
    from loguru import logger
    from . import agentdesktop, browsergate, browserview
    if browsergate.names(cmd, agentdesktop.EXE): held = agentdesktop.check(store, tid, sid, cmd, brain)
    else:
        try: browserview.began(sid); browserview.on_demand(sid, cmd)
        except Exception as e: logger.warning(f'the browser for {sid} did not start on its first page - {e}')
        held = browsergate.check(store, tid, sid, cmd, brain, cwd)
    return (held.get('hookSpecificOutput') or {}).get('permissionDecisionReason') or browsergate.HELD if held else ''


def main(argv: list = None) -> int:
    gate, name, *args = sys.argv[1:] if argv is None else argv
    exe = real(name, gate)
    if not exe: print(f'{name} is not installed on this computer.', file=sys.stderr); return 127
    why = ask(name, args)
    if why: print(why, file=sys.stderr); return 1
    return subprocess.call([exe, *args])


if __name__ == '__main__': sys.exit(main())
