"""EVERY AGENT'S BROWSER AND DESKTOP PRESSES ARE HELD AT THE COMMAND ITSELF, whatever AI runs it (the design round, 2026-11-18).

The hold used to live in the AI's own tool-call road: Claude's PreToolUse hook could refuse a shell line, ACP asked for some calls and
not others, and a Codex run asked for none - its agent pressed a site's final Post itself while every brief said the press was held.
So the hold moved under the road: every task session has a folder first on its PATH (terminal.session_env) holding an `agent-browser`
and an `agent-desktop` of Taskuary's own. Each runs main() here, which lets a command that only looks go straight to the real program,
and asks the server (/api/agent/gate -> judge, the very function the API agent's browser calls) about every other one BEFORE it runs:
browsergate / agentdesktop decide, and a press that can't be undone is held on the task for the owner's one press. Held, the command
prints why and exits 1 without running; Taskuary unreachable, an act fails closed the same way. Run, an act or an open is followed by
what the site did, where it is no working page (browsergate.outcome) - a load that never finished, an error status.

What this still does not cover, said plainly: an agent that reaches the real program by its full path or through `npx`, or drives
Chrome or the desktop some other way. It gates the road agents are told to take (browserview.brief), on every AI."""
import json, os, shlex, sys
from pathlib import Path

GATED = ('agent-browser', 'agent-desktop')
MARK = '/api/agent/gate'
WAIT = 150                      # a snapshot and one verdict (browsergate.JUDGE_WAIT), and a page launched for its first open
OWN_WAIT = 300                  # ...and Taskuary's own verb: a verdict, the form sent, and a code the site emails waited for (signin.CODE_INLINE)
# TASKUARY'S OWN VERBS on the browser (design round 4, 2026-11-19): done by the server in this session's browser, never by the real program - their
# result is the command's own output. `signup`: the page's sign-up form, filled but its password, sent with a password Taskuary makes and keeps
OWN = ('signup',)
_DIR: dict = {}
LAUNCHER = b'-m taskuary.gatecmd'          # ...written in every launcher folder() makes: how one is told from the real program


def is_gate(p) -> bool:
    "Is this file one of the launchers folder() writes (its own command line names this module) - never the real program."
    try: return LAUNCHER in Path(p).read_bytes()[:400]
    except OSError: return False


def folder() -> str:
    """The folder put first on a task session's PATH: one launcher per gated program, each running main() with this interpreter and
    naming its own folder, so the real program is found past it. '' where it could not be written."""
    if 'd' in _DIR: return _DIR['d']
    from loguru import logger
    from . import config
    d, py = config.home() / 'bin' / 'gate', sys.executable
    # ...THIS SERVER'S OWN CODE, wherever the agent's shell stands (round 4, 2026-11-19): `-m taskuary` from the agent's folder found whichever
    # taskuary that Python had installed - another checkout's, an older one's - and the hold that ran was not the one its server asked
    root = str(Path(__file__).resolve().parent.parent)
    try:
        d.mkdir(parents=True, exist_ok=True)
        for n in GATED:
            _write(d / f'{n}.cmd', f'@set "PYTHONPATH={root};%PYTHONPATH%"\r\n@"{py}" -m taskuary.gatecmd "%~dp0." {n} %*\r\n')
            _write(d / n, f'#!/bin/sh\nPYTHONPATH="{root.replace(chr(92), "/")}:$PYTHONPATH" exec "{py.replace(chr(92), "/")}" -m taskuary.gatecmd '
                          f'"$(dirname "$0")" {n} "$@"\n', 0o755)
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


def own(cmd: str) -> str:
    "Taskuary's own verb this agent-browser line asks for (OWN), else ''. Its grammar is the line's first word past agent-browser's options."
    from . import browsergate
    for argv in browsergate._segments(cmd) or []:
        a = browsergate._own_args(browsergate._head(argv) or [])
        if a and a[0].lower() in OWN: return a[0].lower()
    return ''


def run_own(store, tid: int, sid: str, verb: str) -> tuple:
    "(done, what the command prints) of Taskuary's own verb."
    from . import signin
    if verb == 'signup': return signin.signup(store, tid, sid)
    return False, f'agent-browser {verb} is not a command'


def ask(name: str, args: list, after: bool = False, rc: int = 0) -> str:
    """'' runs the command; else why it was not run. Asked of the server this session belongs to, as `taskuary --note` asks it: its token
    from the session (TASKUARY_TOKEN - or the app's own config where a CLI strips token-named variables from its shell, as Codex does).
    `after`: the browser command has run (exit code `rc`) - what the site did where it is no working page, and what the command did in his
    words, every browser call, a look too (browsergate.after)."""
    cmd = shlex.join([name, *args])
    act, call = asks(name, cmd)
    if not (name == 'agent-browser' if after else call): return ''
    try: return str(post(cmd, after, rc=rc).get('why') or '')
    except Exception as e:
        if not act or after: return ''
        return (f'Taskuary held this for the owner: it could not be asked whether this press may run ({str(e)[:120]}), so nothing was '
                'done. Run it again; if it is refused like this again, tell the owner in one line what you were about to do and go on with the rest of the job.')


def post(cmd: str, after: bool = False, wait: float = WAIT, rc: int = 0) -> dict:
    "The server's answer on one line of this session's (/api/agent/gate)."
    from . import config, hooks
    from .guard import TASK_ENV, TASK_HDR
    env, srv = os.environ, config.load()['server']
    body = json.dumps({'task': env.get('TASKUARY_TASK') or '', 'sid': env.get('TASKUARY_SID') or '', 'cmd': cmd, 'cwd': os.getcwd(), **({'after': True, 'rc': rc} if after else {})}).encode()
    hdr = {'Content-Type': 'application/json', **({'X-Taskuary-Token': srv['token']} if srv.get('token') else {}),
           **({TASK_HDR: env[TASK_ENV]} if env.get(TASK_ENV) else {})}
    import urllib.request
    req = urllib.request.Request((env.get('TASKUARY_URL') or hooks.base_url()) + MARK, body, hdr)
    with urllib.request.urlopen(req, timeout=wait) as r: return json.load(r)


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
    if name == 'agent-browser' and (verb := own(shlex.join([name, *args]))):
        try: r = post(shlex.join([name, *args]), wait=OWN_WAIT)
        except Exception as e: print(f'Taskuary could not be reached ({str(e)[:120]}) - nothing was done. Run it again.', file=sys.stderr); return 1
        print(r.get('said') or r.get('why') or f'{verb}: no answer'); return 0 if r.get('ok') else 1
    why = ask(name, args)
    if why: print(why, file=sys.stderr); return 1
    from . import spawn
    # ...ITS OUTPUT HANDED ON BY NAME (round 4, 2026-11-19): started with no console, a real program behind a .cmd wrote nothing to the handles it
    # only inherited - every snapshot, url and read came back empty, and the agent worked the sites with curl instead
    rc = spawn.run([exe, *args], stdin=sys.stdin, stdout=sys.stdout, stderr=sys.stderr).returncode
    if (said := ask(name, args, after=True, rc=rc)): print(said, file=sys.stderr)
    return rc


if __name__ == '__main__': sys.exit(main())
