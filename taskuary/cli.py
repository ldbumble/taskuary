"""`taskuary` - start the local server and open the app. Everything lives in ~/.taskuary."""
import argparse, os, socket, subprocess, threading, webbrowser
import uvicorn
from .timewords import plural
from . import __version__, config, launchkey
try: import tomllib
except ImportError: import tomli as tomllib  # py3.10
try: import winreg as _winreg           # here, not in open_when_ready's thread, which must import nothing
except ImportError: _winreg = None


def _session_headers(srv: dict) -> dict:
    """The token - a session's TASKUARY_TOKEN overlays it (config._env_server), so inside one this is the
    agent's - and the session's proof that the task it names is its own (guard.owns_task)."""
    import os
    from .guard import TASK_ENV, TASK_HDR
    return {**({'X-Taskuary-Token': srv['token']} if srv.get('token') else {}),
            **({TASK_HDR: os.environ[TASK_ENV]} if os.environ.get(TASK_ENV) else {})}

def _port(value):
    try: return config.port_number(value)
    except ValueError as e: raise argparse.ArgumentTypeError(str(e)) from None

def public_url(host, port) -> str:
    """0.0.0.0 / :: are bind addresses, not a place a browser can go."""
    shown = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    if ':' in shown and not shown.startswith('['): shown = f'[{shown}]'
    return f'http://{shown}:{port}'

def _busy(host, port):
    probe = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    try:
        with socket.create_connection((probe.strip('[]'), port), timeout=0.2): return True
    except OSError: return False

def _is_taskuary(url):
    try:
        import requests
        r = requests.get(f'{url}/api/health', timeout=2)
        if r.status_code == 200 and (r.json() or {}).get('ok') is True: return True
        return requests.get(f'{url}/api/settings', timeout=2).status_code in (200, 401)
    except Exception:
        return False


def open_when_ready(url: str, wait, open_it=None):
    """Open the browser once the port ANSWERS, not on a timer.

    A fixed 1.2s sleep was always a guess and had become a wrong one by 15 seconds: uvicorn.run
    is handed the app as a STRING, so uvicorn performs the ~8s cold import itself (fastapi and
    pydantic, ~600 modules) and only then runs the lifespan. The browser therefore opened on a
    dead port and the owner got their browser's own "site can't be reached" (2026-09-09) - which
    no splash of ours can replace, because that page is Chrome's, not the app's.

    `wait` arrives already imported and this thread imports NOTHING, because uvicorn is importing
    taskuary.server on the main thread at the same moment. The first version imported urllib in
    here and deadlocked against urllib3's six shim over there: the port never opened, and the app
    the owner had just started sat there dead for as long as they left it (2026-09-09).

    If it never answers the browser still opens: degrade to the old behaviour, which at least
    shows the owner something, rather than to a window that never appears.
    """
    wait(url)
    (open_it or webbrowser.open)(url)

_UC = r'Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice'

def _http_browser():
    """The registered http(s) browser's open command (Windows), or None. The file must go to THE BROWSER: handed to the
    shell, a .html opens in whatever owns that extension - an editor, on a developer's machine - and the app never opens."""
    if os.name != 'nt' or _winreg is None: return None
    try:
        with _winreg.OpenKey(_winreg.HKEY_CURRENT_USER, _UC) as k: prog = _winreg.QueryValueEx(k, 'ProgId')[0]
        with _winreg.OpenKey(_winreg.HKEY_CLASSES_ROOT, rf'{prog}\shell\open\command') as k: cmd = _winreg.QueryValueEx(k, '')[0]
    except OSError: return None
    return cmd if '%1' in str(cmd or '') else None

def _with_target(cmd: str, path: str) -> str:
    "The open command with the file in its %1 - quoted, unless the command quotes it or takes the rest as one argument."
    if '"%1"' in cmd: return cmd.replace('"%1"', f'"{path}"')
    return cmd.replace('%1', path if '--single-argument' in cmd else f'"{path}"')

def _open_private(url):
    """Open `url` in the browser - through an owner-only file when it carries a launch key, so the key is never on the
    browser's command line (launchkey.via_file), handed to the registered http browser itself.

    Residual risks: the file is readable by the owner's own account until it is spent, expired or cleared (a stranger's
    session is kept out of Taskuary's home by the floor). Where no browser can be named - off Windows, or a registry that
    says nothing usable - the keyed address goes to webbrowser.open as before, and sits on that command line for the
    seconds until the page spends it."""
    cmd = _http_browser() if '?k=' in url else None
    if not cmd: return webbrowser.open(url)
    try: subprocess.Popen(_with_target(cmd, str(launchkey.via_file(url, config.home() / 'launch'))))
    except OSError: webbrowser.open(url)          # a stale registration - the browser uninstalled: still a window, as before

def _open_keyed(url):
    "The browser this process's own server opens, with a one-time key so the page carries the owner token (launchkey, R29)."
    _open_private(launchkey.link(url))


# ── INSIDE A STRANGER'S SESSION (wave B, B1) ────────────────────────────────────────────────────────────────────────
# This process runs with the session's own rights, and every in-process road reads Taskuary's home: --prompts prints the
# owner's documents and mail, --link mints the owner's key, and config.load() falls back to config.toml's OWNER token the
# moment a session unsets its own. An owner's session already has full permissions, so this buys nothing there and stays
# as it was. A stranger's session runs only the agent commands that go over HTTP with its own task-bound token, where the
# server's STRANGER scope decides.
AGENT_ACTS = ('reply', 'reply_file', 'draft', 'draft_file', 'attach', 'item', 'done', 'note', 'board', 'learned', 'upvote', 'downvote', 'comment')
STRANGER_ACTS = AGENT_ACTS[:8]                      # ...the Hub, and the wall's other sessions' words, are not a stranger's to read or write
OWNER_ACTS = ('prompts', 'reroute_held', 'backfill_asks', 'evalset', 'demo', 'link')
NO_TOKEN = ("not sent: this session has no token of its own (TASKUARY_TOKEN) - Taskuary's own is the owner's, and a "
            "session never borrows it. Restart the session from its task.")
def _flag(a): return '--' + a.replace('_', '-')

def _stranger_task(tid: int) -> bool:
    "Fail closed: a task whose origin cannot be read counts as a stranger's."
    try:
        from . import origin
        from .store import SQLiteStore
        return origin.of_task(SQLiteStore(config.db_path()), tid)[0] == 'stranger'
    except Exception: return True

def session() -> tuple:
    """(is this an agent's session, the stranger's task it works - 0 when it names none - or None when it is the owner's).

    Any one marker Taskuary put in the environment makes it a session (launchkey.in_session). It is the OWNER's only when it
    proves so: the shared agent token, which a stranger's session never holds (R28), and a task that is not a stranger's.
    Anything less is a stranger's - a session that unset its task or its token is not taken at its word. The CLI's own
    markers (CLAUDECODE and kin) are not used: the owner's own Claude Code in a terminal sets them too."""
    import os
    from .guard import token_matches
    tok, tid = os.environ.get('TASKUARY_TOKEN') or '', os.environ.get('TASKUARY_TASK') or ''
    if m := launchkey.STRANGER_TOKEN.fullmatch(tok): return True, int(m[1])
    if not launchkey.in_session(): return False, None
    try: shared = (config._read().get('server') or {}).get('agent_token')
    except Exception: shared = None
    if token_matches(tok, shared) and (not tid or tid.isdigit() and not _stranger_task(int(tid))): return True, None
    return True, int(tid) if tid.isdigit() else 0

def _acts(args) -> list:
    return [a for a in AGENT_ACTS if (getattr(args, a) is not None if a in ('reply', 'draft', 'done') else bool(getattr(args, a)))]

def _refuse_outside(args):
    "SystemExit unless every command asked for is one a stranger's session may run - and at least one is (bare `taskuary` starts the app)."
    acts = _acts(args)
    bad = [_flag(f) for f in OWNER_ACTS if getattr(args, f) not in (None, False)] + [_flag(a) for a in acts if a not in STRANGER_ACTS]
    if acts and not bad: return
    raise SystemExit(f"taskuary: {', '.join(bad) or 'starting or opening the app'} refused - this is an agent session on a "
                     f"stranger's task, which reaches only its own task. It runs {', '.join(map(_flag, STRANGER_ACTS))}; the rest is the owner's.")

def _session_srv() -> dict:
    "Where the server is, and the SESSION's own token - config.toml's is the owner's, and a stranger's session must not borrow it."
    import os
    return {**(config._read().get('server') or {}), **config._env_server(), 'token': os.environ.get('TASKUARY_TOKEN') or ''}

def _post(path: str, body: dict, stranger, timeout: int = 60, hdr: dict = None):
    """POST to the running server as this session: (response, its JSON) - or None, said, when there is no server to reach
    or (a stranger's session) no token of its own. The owner's sessions keep config's token as they always did."""
    import requests
    srv = _session_srv() if stranger is not None else config.load()['server']
    if stranger is not None and not srv['token']: print(NO_TOKEN); return None
    host = '127.0.0.1' if srv.get('host') in ('0.0.0.0', '::', '', None) else srv['host']
    base = f"http://{host}:{srv.get('port') or 7787}"
    try:
        r = requests.post(f'{base}{path}', timeout=timeout, json=body, headers=_session_headers(srv) if hdr is None else hdr(srv))
        return r, (r.json() if r.headers.get('content-type', '').startswith('application/json') else {})
    except Exception as e:
        print(f'could not reach Taskuary at {base}: {e}'); return None


def main():
    ap = argparse.ArgumentParser(prog='taskuary', description='Your work manager. Locally. Securely. In control.')
    ap.add_argument('--host', help='override [server].host (0.0.0.0 to listen on all interfaces)')
    ap.add_argument('--port', type=_port, help='override [server].port')
    ap.add_argument('--no-browser', action='store_true', help="don't open a browser tab when the server starts")
    ap.add_argument('--link', action='store_true', help='print a one-time address that opens the running app signed in, for a browser you open yourself')
    ap.add_argument('--debug', action='store_true', help='verbose console logging (requests, report runs, errors)')
    ap.add_argument('--version', action='version', version=f'taskuary {__version__}')
    # "what is actually in the prompt?" had no answer short of reading the code that builds it,
    # which is not a reasonable thing to ask of the person whose judgement is being automated
    ap.add_argument('--prompts', nargs='?', const='', metavar='MESSAGE_ID',
                    help='print the triage, reply and coding-agent prompts for a real item on '
                         'this machine - every block labelled with the document or table it '
                         'came from - then exit. Optionally for one message id.')
    # "is the triage right?" is a rate, and nothing measured it: build the labelled cases out of
    # the owner's own verdicts, score the configured classifier over them, or export a set that
    # can leave the machine (people and prose removed) - see evalset.py
    # coding tasks triage could not name a repository for cannot start at all: the agent wants a
    # checkout and there is none to give it. They are the assistant's work now (ingest: no_repo), but
    # rows that arrived before that rule are still sitting on the board unstartable.
    ap.add_argument('--reroute-held', action='store_true',
                    help='move open coding tasks that have no nameable repository to the agent that '
                         'needs none, and start them; prints what moved, then exits')
    # the rows filed before triage was asked for a summary and a checklist: their ask is the raw
    # email, footer and quoted thread included, and they have no todos at all
    ap.add_argument('--backfill-asks', action='store_true',
                    help='re-derive the ask and the todos for tasks whose summary is a copy of the '
                         'email. Prints what it WOULD change and writes nothing unless --apply.')
    ap.add_argument('--apply', action='store_true', help='with --backfill-asks: actually write the changes')
    ap.add_argument('--include-closed', action='store_true', help='with --backfill-asks: closed tasks too')
    ap.add_argument('--evalset', choices=['build', 'share', 'evaluate', 'ablate', 'jev'], metavar='ACTION',
                    help='triage dataset: build (labelled cases from your verdicts -> ~/.taskuary/eval), '
                         'evaluate (score the configured AI over them), ablate (score with and without memory), '
                         'share (anonymised copy for tests/data)')
    # THE WALL (blackboard.py). An agent working in a terminal has a shell and no API token, so
    # this is how it talks to the next agent: two flags, no arguments it has to be told - the
    # session puts its own name, task and checkout in the environment.
    # try-it-out in one command: a throwaway home, a world of invented work, and every door
    # to the outside nailed shut (demo.py). This is what /demo on the website runs.
    ap.add_argument('--demo', action='store_true',
                    help='run a DEMO instance: invented data, a scripted AI, replayed coding '
                         'sessions, and nothing that can reach a real system')
    ap.add_argument('--board', action='store_true',
                    help='print the agent wall for this checkout - what the agents before you left here')
    ap.add_argument('--all', action='store_true',
                    help='with --board: the whole wall, including days already folded into a summary')
    ap.add_argument('--note', metavar='TEXT',
                    help='leave a line on the wall for the next agent (see --kind)')
    ap.add_argument('--kind', default='note', metavar='KIND',
                    help='wall: working | note | blocked | ready | done; Hub: new_idea | '
                         'technical_solve | howto | gotcha | decision | system | people')
    # ...and how a session ENDS itself. The Done button was the only way a finished task ever
    # produced its report and its reply, so an agent that finished at 2am and a person who never
    # opened the tab left the sender with nothing (selfclose.py).
    # THE HANDBOOK (handbook.py). The wall is what the next hour needs; this is what next month
    # needs - and it is the difference between a company whose know-how lives in its people and
    # one a new agent can be plugged into.
    ap.add_argument('--learned', metavar='TEXT',
                    help='write one hard-earned discovery or developed company idea into the Hub. '
                         'Use only after substantial investigation/reasoning; never routine output or '
                         'what you did. See --topic, --kind and --body.')
    ap.add_argument('--topic', default='', metavar='TOPIC',
                    help='with --learned: which shelf it goes on - a repository, a system, a part of '
                         'the business. Defaults to the checkout you are in.')
    ap.add_argument('--body', default='', metavar='TEXT',
                    help='with --learned: the two or three sentences under the title - the fact, why it '
                         'is so, and what to do about it')
    ap.add_argument('--why-earned', default='', metavar='TEXT',
                    help='with --learned: what substantial investigation, tests, comparison, or reasoning earned this Hub post')
    # ...and how agents keep it honest: agree, disagree, add. One vote per agent per entry, and an
    # entry the room votes below zero leaves the Hub and every later seed prompt.
    ap.add_argument('--upvote', type=int, metavar='ID', help='this Hub entry held up - agree with it (ids are in the FROM HUB block of your prompt)')
    ap.add_argument('--downvote', type=int, metavar='ID', help='this Hub entry is wrong or stale - say why with --body')
    ap.add_argument('--comment', type=int, metavar='ID', help='add to a Hub entry without re-posting it: the text goes in --body')
    ap.add_argument('--done', metavar='SUMMARY', nargs='?', const='',
                    help='finish the task this session is working: close it, file the report from '
                         'this transcript, and draft the reply the sender gets (you are not '
                         'sending it - the owner approves it). Give one sentence on what you did '
                         'or found. Do not run this while waiting on the owner.')
    ap.add_argument('--no-reply', action='store_true',
                    help='with --done: nobody should hear back (the owner said not to answer, or there is nothing '
                         'for the sender) - the task closes with no reply drafted, and your sentence says why'),
    ap.add_argument('--reply', metavar='TEXT',
                    help="write the reply the person who asked will get, in your own words - it becomes this "
                         "task's pending reply for the owner to approve (you are not sending it), and "
                         "finishing keeps it instead of redrafting. Use - to read it from stdin.")
    ap.add_argument('--reply-file', metavar='PATH', help='--reply, read from a file (for a long or multi-line reply)')
    ap.add_argument('--follow-up', action='store_true',
                    help='with --reply: the owner asked you for ANOTHER message after your reply already went - it is saved as a '
                         'follow-up to it. Without this, a second reply to a message already answered (nothing new from them) is refused.')
    ap.add_argument('--attach', action='append', default=[], metavar='PATH',
                    help='a file that goes with --reply or --draft (repeat for more). If your words say "attached", attach it - '
                         'otherwise the mail goes out without it. Alone, it adds the file to the reply already saved.')
    # ...and the emails that close a task (slots.py): its checklist lines marked "-> email to" name them
    ap.add_argument('--draft', metavar='TEXT', help="write one of the emails that closes this task (its checklist names them) - "
                                                    "pending for the owner to approve; use with --slot or --to. Use - for stdin.")
    ap.add_argument('--draft-file', metavar='PATH', help='--draft, read from a file')
    ap.add_argument('--slot', default='', help='the checklist slot this email fills (the id after --slot in your checklist)')
    ap.add_argument('--to', default='', help='who it goes to, when no slot names them')
    ap.add_argument('--subject', default='', help='the subject line')
    # ...and a BATCH's items (batch.py): one finding per item, as the agent finishes each
    ap.add_argument('--item', type=int, metavar='N', help='in a batch: report on item N (with --result, and --overlap/--settled)')
    ap.add_argument('--result', default='', metavar='TEXT', help="with --item: what it is, whether it is right, what you propose")
    ap.add_argument('--overlap', default='', metavar='TEXT', help='with --item: the other item it duplicates, conflicts with or needs')
    ap.add_argument('--settled', action='store_true', help='with --item: nothing is left for the owner to do on it')
    ap.add_argument('--propose', default='', choices=['', 'merge', 'close', 'changes'], help='with --item: what should happen to it')
    args = ap.parse_args()
    agent, stranger = session()
    if stranger is not None: _refuse_outside(args)
    if args.demo:
        import os, tempfile
        from . import demo
        os.environ[demo.FLAG] = '1'
        # a throwaway home, so a demo can never be pointed at somebody's real database by accident
        os.environ.setdefault('TASKUARY_HOME', tempfile.mkdtemp(prefix='taskuary-demo-'))
        print(f'demo mode: invented data in {os.environ["TASKUARY_HOME"]}, nothing can reach a real system')
    # --done goes over HTTP, unlike --note. A note is a database row and any process can write
    # one; ENDING a task needs the live session's scrollback, which exists only inside the
    # running server - this process would find no transcript and wrap an empty one.
    if args.reply is not None or args.reply_file or args.draft is not None or args.draft_file or args.attach:
        import os, sys
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        tid = os.environ.get('TASKUARY_TASK')
        if not str(tid).isdigit():
            print('not in a Taskuary session - TASKUARY_TASK is not set, so there is no task to reply on')
            return
        drafting = args.draft is not None or bool(args.draft_file)
        path, flag = (args.draft_file, args.draft) if drafting else (args.reply_file, args.reply)
        if path:
            try: text = open(path, encoding='utf-8').read()
            except (OSError, UnicodeDecodeError) as e:
                print(f'not saved: cannot read {path}: {getattr(e, "strerror", None) or e}'); return
        else: text = sys.stdin.read() if flag == '-' else flag or ''
        import base64
        files = []
        for a in args.attach:
            try: files.append({'name': os.path.basename(a), 'data': base64.b64encode(open(a, 'rb').read()).decode()})
            except OSError as e: print(f'not saved: cannot read {a}: {e.strerror or e}'); return
        who = os.environ.get('TASKUARY_AGENT') or 'agent'
        got = (_post('/api/agent/draft', {'task_id': int(tid), 'text': text, 'to': args.to, 'subject': args.subject, 'slot': args.slot,
                                          'agent': who, 'files': files}, stranger) if drafting
               else _post('/api/agent/reply', {'task_id': int(tid), 'text': text, 'agent': who, 'files': files, 'follow_up': args.follow_up}, stranger))
        if not got: return
        r, out = got
        if text or not out.get('ok'): print("saved on the task as its result - nobody is waiting on a reply, so nothing will be sent." if out.get('saved') == 'result'
                                            else f"{'email' if drafting else 'reply'} saved on the task, waiting on the owner to approve and send it." if out.get('ok')
                                            else f"not saved: {out.get('why') or out.get('detail') or r.text[:200]}")
        if out.get('attached'): print('attached: ' + ', '.join(out['attached']))
        for w in out.get('not_attached') or []: print(f'NOT attached - {w}')
        return
    if args.item is not None:
        import os, sys
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        tid = os.environ.get('TASKUARY_TASK')
        if not str(tid).isdigit(): print('not in a Taskuary session - TASKUARY_TASK is not set, so there is no batch to report on'); return
        if not args.result.strip(): print('nothing reported - say what you found with --result'); return
        got = _post('/api/agent/item', {'task_id': int(tid), 'item': args.item, 'result': args.result, 'overlap': args.overlap,
                                        'settled': bool(args.settled), 'propose': args.propose,
                                        'agent': os.environ.get('TASKUARY_AGENT') or 'agent'}, stranger)
        if not got: return
        r, out = got
        print(f"item {args.item}: {'settled' if out.get('state') == 'done' else 'waiting on the owner'}" if out.get('ok')
              else f"not saved: {out.get('why') or out.get('detail') or r.text[:200]}")
        return
    if args.done is not None:
        import os, sys
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        tid = os.environ.get('TASKUARY_TASK')
        if not str(tid).isdigit():
            print('not in a Taskuary session - TASKUARY_TASK is not set, so there is no task to finish')
            return
        got = _post('/api/agent/done', {'task_id': int(tid), 'summary': args.done, 'no_reply': bool(args.no_reply),
                                        'agent': os.environ.get('TASKUARY_AGENT') or 'agent'}, stranger, timeout=120)
        if not got: return
        r, out = got
        if out.get('closed'):
            print('task closed. Report filed from this session.'
                  + (' A reply to the sender is drafted and waiting on the owner.' if out.get('drafting')
                     else ' No reply drafted, as you said.' if args.no_reply else ' No reply was needed.'))
        elif out.get('held'):
            print('noted, not closed: the owner opened this session to work in, so they end it. Your summary is on '
                  'the task and they have been told; stay at the prompt in case they have more.')
        else:
            print(f"not closed: {out.get('why') or out.get('detail') or r.text[:200]}")
        return
    if args.note and stranger is not None:
        # a stranger's note: through the board door, which pins it to the token's own task (B2 keeps it off the others' seeds)
        import os, sys
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        got = _post('/api/board/notes', {'body': args.note, 'kind': args.kind, 'agent': os.environ.get('TASKUARY_AGENT') or 'agent',
                                         'cwd': os.environ.get('TASKUARY_CWD') or os.getcwd()}, stranger, timeout=30,
                    hdr=lambda srv: {'X-Taskuary-Token': srv['token']})
        if not got: return
        r, out = got
        print(f"posted to the wall as {out.get('Agent')} [{out.get('Kind')}]" if r.status_code == 200 and out.get('Kind')
              else f"not posted: {out.get('detail') or r.text[:200]}")
        return
    if args.board or args.note or args.learned or args.upvote or args.downvote or args.comment:
        import os, sys
        from . import blackboard as bb
        from .store import SQLiteStore, task_ref
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        store = SQLiteStore(config.db_path())
        cwd = os.environ.get('TASKUARY_CWD') or os.getcwd()
        who = os.environ.get('TASKUARY_AGENT') or 'agent'
        tid = os.environ.get('TASKUARY_TASK')
        if args.upvote or args.downvote or args.comment:
            from . import handbook
            lid = args.upvote or args.downvote or args.comment
            try:
                if args.comment:
                    if not args.body.strip(): print('nothing to add - put the text in --body'); return
                    if not store.lore_get(lid): print(f'no Hub entry #{lid}'); return
                    store.lore_comment(lid, args.body.strip()[:handbook.BODY_MAX], who)
                    print(f'added to #{lid}'); return
                p = handbook.vote(store, lid, 1 if args.upvote else -1, who)
                if args.downvote and args.body.strip(): store.lore_comment(lid, args.body.strip()[:handbook.BODY_MAX], who)
            except ValueError as e: print(str(e)); return
            print(f"#{lid} is now {p['Score']:+d}" + (' - removed from the Hub' if p['Status'] == 'downvoted' else ''))
            return
        if args.learned:
            from . import handbook
            if len(' '.join(args.why_earned.split())) < 20:
                print('not filed: --why-earned must name the substantial investigation, tests, or reasoning behind this Hub post')
                return
            try: p = handbook.post(store, args.learned, args.body, args.topic, args.kind if args.kind in handbook.KINDS else 'howto',
                                   who, int(tid) if str(tid).isdigit() else None, cwd, why_earned=args.why_earned)
            except ValueError as e: print(f'not filed: {e}'); return
            if p.get('merged'): print(f"The Hub already says this - #{p['LoreId']} upvoted, now {p['Score']:+d}: {p['Title']}")
            else: print(f"filed in the Hub under {p['Topic']} as #{p['LoreId']}: {p['Title']}")
            return
        if args.note:
            try: n = bb.post(store, args.note, args.kind, who, cwd, int(tid) if str(tid).isdigit() else None, sid=os.environ.get('TASKUARY_SID'))
            except ValueError as e: print(f'not posted: {e}'); return
            print(f"posted to the wall as {n['Agent']} [{n['Kind']}]")
            return
        if args.all:
            rows = store.notes(bb.norm(cwd), 40, rolled=True)
            if agent: rows = bb.without_strangers(store, rows)     # the history, as a session reads it: no stranger's task's words
        else:
            # Liveness belongs to the running server's terminal registry. A fresh CLI process has
            # an empty registry of its own, so reading SQLite here would mislabel active SID notes
            # as dead. Ask the same endpoint as the Board, with this session's scoped token.
            import requests
            srv = config.load()['server']
            base = os.environ.get('TASKUARY_API') or os.environ.get('TASKUARY_URL')
            if not base:
                host = '127.0.0.1' if srv.get('host') in ('0.0.0.0', '::', '', None) else srv['host']
                base = f"http://{host}:{srv.get('port') or 7787}"
            token = os.environ.get('TASKUARY_TOKEN') or srv.get('token') or ''
            try:
                response = requests.get(f'{base.rstrip("/")}/api/board/notes', timeout=5,
                                        headers={'X-Taskuary-Token': token} if token else {},
                                        params={'cwd': cwd, 'limit': 20})
                response.raise_for_status()
                payload = response.json()
                if not isinstance(payload, dict) or not isinstance(payload.get('data'), list):
                    raise ValueError('the server returned an invalid wall response')
                rows = payload['data']
            except Exception as e:
                print(f'the live wall is unavailable for {cwd}: could not reach Taskuary at {base}: {e}')
                return
        print(f'the wall - {cwd}' if rows else f'the wall is empty for {cwd} - you are first')
        if not args.all and rows: print('  (older days are folded into [summary] lines; --board --all for every note)')
        for r in reversed(rows):
            ref = f" {task_ref(r['TaskId'])}" if r.get('TaskId') else ''
            print(f"  [{r['Kind']}] {r['Agent']}{ref} {bb._ago(r['CreatedAt'])}: {r['Body']}")
        return
    if args.reroute_held:
        import sys
        from . import ingest
        from .store import SQLiteStore, task_ref
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        moved = ingest.reroute_held_no_repo(SQLiteStore(config.db_path()))
        for t in moved: print(f"{task_ref(t['TaskId'])} -> general: {t['Title']}")
        print(f"{plural(len(moved), 'task')} moved.")
        return
    if args.backfill_asks:
        import sys
        from . import ingest, llm as _llm
        from .store import SQLiteStore
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        store = SQLiteStore(config.db_path())
        brain = _llm.build_llm(store)
        if not brain:
            from . import words
            print('No AI is connected, so the summaries will only be stripped of their footers '
                  f"and no todos can be drawn. Connect one under {words.name('ai')}, then choose it under {words.name('sorting')}.")
        rows = ingest.backfill_asks(store, brain, dry_run=not args.apply, include_closed=args.include_closed)
        touched = [r for r in rows if r['action'] in ('rewrote', 'would rewrite')]
        for r in touched:
            print(f"{r['ref']} {r['title'][:60]}")
            print(f"    ask:  {(r.get('summary') or '')[:150]}")
            for i in r.get('checklist') or []: print(f"    todo: {i}")
        print(f"\n{len(touched)} of {len(rows)} task(s) {'rewritten' if args.apply else 'would be rewritten'}.")
        if touched and not args.apply: print('Nothing was written. Re-run with --apply to write it.')
        return
    if args.evalset:
        import sys
        from . import evalset
        from .store import SQLiteStore
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        evalset.run(SQLiteStore(config.db_path()), args.evalset, config.home())
        return
    if args.prompts is not None:
        import sys
        from .promptmap import render
        from .store import SQLiteStore
        # the Windows console is cp1252 and the operator documents are full of em dashes, so this
        # would die on the owner's OWN text before it printed a line of it
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        mid = int(args.prompts) if str(args.prompts).strip().isdigit() else None
        print(render(SQLiteStore(config.db_path()), message_id=mid))
        return
    from .logs import setup as setup_logs
    setup_logs(args.debug)
    try:
        cfg = config.load()
    except tomllib.TOMLDecodeError as e:
        # One typo in a hand-edited config.toml should not greet the owner with a traceback: they
        # are the only one who can fix it, and the parser's own message already carries the line
        # and column - so name the file, and say how to move on. (sys is imported here, not at the
        # top: main()'s other branches import it locally, which makes it local to this function.)
        import sys
        print(f'{config.home() / "config.toml"} is not valid TOML: {e} - fix the file, or rename it '
              f'(e.g. to config.toml.bak) to start fresh', file=sys.stderr)
        sys.exit(1)
    host, port = args.host or cfg['server']['host'], args.port or cfg['server']['port']
    url = public_url(host, port)
    if args.link:
        if _busy(host, port) and _is_taskuary(url): print(launchkey.remote_link(url, cfg['server'].get('token') or ''))
        else: print(f'Taskuary is not running at {url} - start it with `taskuary`, then ask again.')
        return
    if _busy(host, port):
        if _is_taskuary(url):
            # don't crash into 'address already in use' - reuse the running instance, signed in with a key it hands us
            print(f'Taskuary is already running at {url} - opening it.')
            if not args.no_browser: _open_private(launchkey.remote_link(url, cfg['server'].get('token') or ''))
            return
        from .desktop import free_port
        old, port = port, free_port(host)
        url = public_url(host, port)
        print(f'port {old} is in use by something else - using {port} instead')
    # ...and a port is not the data: one Taskuary per data folder, wherever it serves (instance.py)
    from . import instance
    if h := instance.holder():
        at = h.get('url') or ''
        print(f'Taskuary is already running on {config.home()}{f" at {at}" if at else ""} - ' + ('opening it.' if at else 'quit it first.'))
        if at and not args.no_browser: _open_private(launchkey.remote_link(at, cfg['server'].get('token') or ''))
        return
    instance.claim(url)
    print(f'Taskuary {__version__} - {url}  (data: {config.db_path()})')
    # the port actually bound, for anything in the server that has to name its own address (the
    # QuickBooks redirect URI): server.py reads config, and config reads this
    import os; os.environ['TASKUARY_PORT'] = str(port)
    if not args.no_browser:
        from .desktop import serving        # on the MAIN thread, before uvicorn starts importing
        threading.Thread(target=open_when_ready, args=(url, serving, _open_keyed), daemon=True).start()
    # what uvicorn.run does, on the server whose stop is bounded and lets every held permit go (desktop.Server, R26)
    from .desktop import Server, server_config
    srv = Server(server_config('taskuary.server:app', host, port))
    try: srv.run()
    except KeyboardInterrupt: pass
    if not srv.started: raise SystemExit(3)           # uvicorn's own STARTUP_FAILURE


if __name__ == '__main__':
    main()
