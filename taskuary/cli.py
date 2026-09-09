"""`taskuary` - start the local server and open the app. Everything lives in ~/.taskuary."""
import argparse, socket, threading, webbrowser
import uvicorn
from . import __version__, config


def public_url(host, port) -> str:
    """0.0.0.0 / :: are bind addresses, not a place a browser can go."""
    shown = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    return f'http://{shown}:{port}'

def _busy(host, port):
    probe = '127.0.0.1' if host in ('0.0.0.0', '::') else host
    with socket.socket() as s: return s.connect_ex((probe, port)) == 0

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


def main():
    ap = argparse.ArgumentParser(prog='taskuary', description='Your work AI assistant - the local-first agent work hub.')
    ap.add_argument('--host', help='override [server].host (0.0.0.0 to listen on all interfaces)')
    ap.add_argument('--port', type=int, help='override [server].port')
    ap.add_argument('--no-browser', action='store_true')
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
    ap.add_argument('--evalset', choices=['build', 'share', 'evaluate', 'ablate'], metavar='ACTION',
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
    args = ap.parse_args()
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
    if args.done is not None:
        import os, sys, requests
        try: sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, OSError): pass
        tid = os.environ.get('TASKUARY_TASK')
        if not str(tid).isdigit():
            print('not in a Taskuary session - TASKUARY_TASK is not set, so there is no task to finish')
            return
        srv = config.load()['server']
        host = '127.0.0.1' if srv.get('host') in ('0.0.0.0', '::', '', None) else srv['host']
        base = f"http://{host}:{srv.get('port') or 7787}"
        hdr = {'X-Taskuary-Token': srv['token']} if srv.get('token') else {}
        try:
            r = requests.post(f'{base}/api/agent/done', timeout=120, headers=hdr,
                              json={'task_id': int(tid), 'summary': args.done,
                                    'agent': os.environ.get('TASKUARY_AGENT') or 'agent'})
            out = r.json() if r.headers.get('content-type', '').startswith('application/json') else {}
        except Exception as e:
            print(f'could not reach Taskuary at {base}: {e}'); return
        if out.get('closed'):
            print('task closed. Report filed from this session.'
                  + (' A reply to the sender is drafted and waiting on the owner.' if out.get('drafting')
                     else ' No reply was needed.'))
        elif out.get('held'):
            print('noted, not closed: the owner opened this session to work in, so they end it. Your summary is on '
                  'the task and they have been told; stay at the prompt in case they have more.')
        else:
            print(f"not closed: {out.get('why') or out.get('detail') or r.text[:200]}")
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
        print(f"{len(moved)} task{'s' if len(moved) != 1 else ''} moved.")
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
    cfg = config.load()
    host, port = args.host or cfg['server']['host'], args.port or cfg['server']['port']
    url = public_url(host, port)
    if _busy(host, port):
        if _is_taskuary(url):
            # don't crash into 'address already in use' - reuse the running instance
            print(f'Taskuary is already running at {url} - opening it.')
            if not args.no_browser: webbrowser.open(url)
            return
        from .desktop import free_port
        old, port = port, free_port(host)
        url = public_url(host, port)
        print(f'port {old} is in use by something else - using {port} instead')
    print(f'Taskuary {__version__} - {url}  (data: {config.db_path()})')
    # the port actually bound, for anything in the server that has to name its own address (the
    # QuickBooks redirect URI): server.py reads config, and config reads this
    import os; os.environ['TASKUARY_PORT'] = str(port)
    if not args.no_browser:
        from .desktop import serving        # on the MAIN thread, before uvicorn starts importing
        threading.Thread(target=open_when_ready, args=(url, serving), daemon=True).start()
    uvicorn.run('taskuary.server:app', host=host, port=port, log_level='warning')


if __name__ == '__main__':
    main()
