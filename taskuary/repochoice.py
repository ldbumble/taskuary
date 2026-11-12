"""THE CODING AGENT PICKS ITS REPOSITORY (the owner, 2026-11-06: "let's take repo decision out of the triage - remove it completely and
then the use_repo tool to figure it out or check out folders").

Triage says a job IS coding and nothing about where. A structural fact still places it without asking anyone (terminal.guess_repo): a
GitHub or GitLab item's own repository, the one the owner set with Change, a workflow's cwd, a continued session's cwd. Otherwise the
session opens in the task's own folder (outputs.folder - where the general agent works too) with the REPOSITORIES block in its first
prompt, and the agent chooses:
- `use_repo` checks the folder is a git checkout the agent may work in (a known repository's, or under FOLDERS_KEY), records it on the
  task (AGENT_TAG, the wall, the landing start) and points the live session there. A PTY CLI cannot be moved by its parent, and a CLI's
  resume is keyed by the folder it started in (`claude --resume` looks the id up under that folder), so the session keeps running and
  its cwd is recorded - the agent is told to `cd` into the checkout on every command, which every CLI here can do;
- `find_repos` lists the git checkouts under the folders the owner lets agents look in, with their remotes and last commit.
An agent that has picked nothing has no checkout - its folder is its own task's - so it collides with nobody on the blackboard."""
import os, re, time
from pathlib import Path
from loguru import logger

from . import words

AGENT_TAG = 'agent-repo:'                    # the agent's pick; the owner's `repo:` (Change) outranks it, and a structural fact does too
FOLDERS_KEY = 'code_folders'                 # Settings -> Agents: "Folders agents may look in for code", one a line; blank = HOMES that exist
HOMES = ('Documents', 'source/repos', 'repos', 'projects', 'code', 'src')
SKIP = {'node_modules', 'venv', '.venv', '__pycache__', 'dist', 'build', 'bin', 'obj', 'appdata', 'site-packages', 'windows',
        'program files', 'program files (x86)'}
DEPTH, BUDGET, SECONDS, CACHE_S, LISTED, ABOUT = 3, 4000, 4.0, 90, 40, 160
_found: dict = {}                            # tuple(folders) -> (at, rows)


def norm(p) -> str: return os.path.normcase(os.path.normpath(os.path.abspath(os.path.expanduser(str(p))))) if str(p or '').strip() else ''
def inside(p, root) -> bool:
    a, b = norm(p), norm(root)
    return bool(a and b) and (a == b or a.startswith(b.rstrip('\\/') + os.sep))
def is_checkout(p) -> bool: return bool(p) and os.path.isdir(p) and os.path.exists(os.path.join(p, '.git'))


def default_folders() -> list:
    h = Path.home()
    return [str(h / d) for d in HOMES if (h / d).is_dir()]


def folders(store) -> list:
    "The folders the owner lets agents look in for code: their list, one a line, else the usual homes for code that exist here."
    got = [x.strip().strip('"') for x in str(store.get_setting(FOLDERS_KEY) or '').replace(';', '\n').splitlines() if x.strip()]
    return [os.path.expanduser(x) for x in got] or default_folders()


def scratch(tid) -> str:
    "The task's own folder - the neutral place a coding session opens in until it picks a checkout."
    from . import outputs
    d = outputs.folder(int(tid)); d.mkdir(parents=True, exist_ok=True)
    return str(d)


def is_scratch(tid, cwd) -> bool:
    from . import outputs
    return bool(tid and cwd) and norm(cwd) == norm(outputs.folder(int(tid)))


def _profile(store) -> dict:
    import json
    from .agents import coding_role
    try: p = json.loads((store.get_agent(coding_role(store)) or {}).get('Config') or '{}')
    except (TypeError, ValueError): p = {}
    return p if isinstance(p, dict) else {}


def _paths(store, profile: dict = None) -> dict:
    "{repo: local path} from every profile's checkouts - the coding profile's own winning."
    import json
    out = {}
    for a in store.list_agents():
        try: out.update({k: v for k, v in (json.loads(a.get('Config') or '{}').get('cwd_map') or {}).items() if v and k not in out})
        except (TypeError, ValueError, AttributeError): continue
    return {**out, **{k: v for k, v in ((profile or {}).get('cwd_map') or {}).items() if v}}


def known(store, profile: dict = None) -> list:
    """[{repo, path, about}]: the SOUL.md project map, the repositories the project graph learned, and every checkout a profile has a
    path for - what a coding agent may name to use_repo. `path` is '' where none is known yet."""
    from .projects import REPO_KIND
    from .terminal import repo_map
    paths, about, soul = _paths(store, profile if profile is not None else _profile(store)), {}, repo_map(store)
    try:
        for l in store.project_links(kind=REPO_KIND):
            r, n = str(l.get('Value') or '').strip(), str(l.get('ProjectName') or '').strip()
            # a discovered repository's project is named after the repository itself: no description at all, not its name again
            if r and not about.get(r): about[r] = str(l.get('ProjectDescription') or '').strip() or ('' if n.lower() == r.lower() else n)
    except Exception as e: logger.debug(f'repochoice: project repositories unavailable - {e}')
    for r, a in soul.items():
        if not about.get(r): about[r] = a
    return [{'repo': r, 'path': paths.get(r) or '', 'about': about.get(r, '')} for r in dict.fromkeys([*soul, *paths, *about])]


def remote_of(path) -> tuple:
    "(owner/name, url) of a checkout's origin, read off its config - ('', '') when it has none."
    from . import landing
    url = landing._git(path, 'remote', 'get-url', 'origin')
    m = re.search(r'[:/]([^/:\s]+/[^/\s]+?)(?:\.git)?/?$', url or '')
    return (m.group(1) if m else '', url or '')


def _walk(roots: list) -> list:
    queue, seen, out, budget, deadline = [(Path(r), 0) for r in roots if r and os.path.isdir(r)], set(), [], BUDGET, time.time() + SECONDS
    while queue and budget > 0 and time.time() < deadline:
        d, depth = queue.pop(0)
        k = norm(d)
        if k in seen or (depth and (d.name.lower() in SKIP or d.name.startswith('.'))): continue
        seen.add(k); budget -= 1
        try: here = (d / '.git').exists()
        except OSError: continue
        if here: out.append(str(d)); continue            # a checkout: never descend into one
        if depth >= DEPTH: continue
        try: queue += [(c, depth + 1) for c in sorted(d.iterdir()) if c.is_dir()]
        except OSError: continue
    return out


def find(store, query: str = '') -> list:
    """The git checkouts under the folders agents may look in, newest commit first: [{repo, path, remote, last, known}]. Walked once per
    CACHE_S - an agent asks a few times while it looks."""
    from . import landing
    roots = tuple(folders(store))
    at, rows = _found.get(roots, (0, None))
    if rows is None or time.time() - at > CACHE_S:
        rows = []
        for p in _walk(list(roots)):
            name, url = remote_of(p)
            rows.append({'repo': name or os.path.basename(p), 'path': p, 'remote': url, 'last': landing._git(p, 'log', '-1', '--format=%cs')})
        rows.sort(key=lambda r: r['last'] or '', reverse=True)
        _found[roots] = (time.time(), rows)
    mine = {norm(k['path']) for k in known(store) if k['path']}
    q = str(query or '').strip().lower()
    return [{**r, 'known': norm(r['path']) in mine} for r in rows if not q or q in r['repo'].lower() or q in r['path'].lower()]


def says_found(rows: list, roots: list) -> str:
    if not rows: return f"no git checkout under {', '.join(roots) or 'any folder'} matches - the owner adds folders under {words.name('agents')}"
    return '\n'.join(f"- {r['repo']}: {r['path']}" + (f" (last commit {r['last']})" if r['last'] else '') + (f" - {r['remote']}" if r['remote'] else '')
                     for r in rows[:60]) + (f'\n…and {len(rows) - 60} more - narrow the query' if len(rows) > 60 else '')


def block(store, tid: int, cwd: str, profile: dict = None) -> str:
    """REPOSITORIES: what a session that opened in its task's folder is told - each known repository with its path and what it is, how
    to pick one, and what Taskuary KNOWS that bears on it (said as hints, never as the pick)."""
    from . import terminal as term
    rows = known(store, profile)
    lines = [f"- {r['repo']} ({r['path'] or 'no local path known - find_repos may find it'})" + (f": {' '.join(r['about'].split())[:ABOUT]}" if r['about'] else '')
             for r in rows[:LISTED]] + ([f'- …and {len(rows) - LISTED} more (find_repos)'] if len(rows) > LISTED else [])
    hints = []
    try:
        if own := term.our_own_repo(store, tid, [r['repo'] for r in rows]): hints.append(f"this is Taskuary's own machinery, which lives in {own}")
        from .projects import repositories_for_task
        rel, why = repositories_for_task(store, tid)
        if rel: hints.append(f"{', '.join(rel[:4])} - {why}")
    except Exception as e: logger.debug(f'repochoice: no hints for task {tid} - {e}')
    return (f"REPOSITORIES - no checkout is chosen for this task yet: you are in its own folder ({cwd}), which is not a repository. Before "
            "you read or change any code, pick the checkout this work belongs in with the use_repo tool (`path_or_name`: a name below or a "
            "folder; `why`: one line) - `taskuary --use-repo NAME_OR_PATH \"WHY\"` from a shell without it. None fits? Find it: find_repos "
            f"lists the git checkouts under the folders you may look in ({', '.join(folders(store)) or 'none set'}). Nothing fits and the "
            "work needs code of its own? Start it: a new folder, `git init`, and use_repo it. A task that needs no code is done from here, "
            "picking nothing."
            + ('\n' + '\n'.join(lines) if lines else '\nNo repository is known yet.')
            + (f"\nWhat Taskuary knows (hints, not the answer): {'; '.join(hints)}." if hints else ''))


def resolve(store, target: str) -> tuple:
    "(path, known name or '') for what an agent named: a known repository (full or last part, any case) or a folder."
    want = str(target or '').strip().strip('"')
    if not want: raise ValueError('name the repository or give its folder - `path_or_name`')
    rows = known(store)
    hit = [r for r in rows if r['repo'].lower() == want.lower()] or [r for r in rows if r['repo'].split('/')[-1].lower() == want.lower()]
    if len(hit) > 1: raise ValueError(f"{want} names more than one repository ({', '.join(r['repo'] for r in hit)}) - give the full name")
    if hit:
        r = hit[0]
        if r['path']: return r['path'], r['repo']
        from .terminal import find_checkout
        found = find_checkout(r['repo'], {'cwd_map': {}})
        if found: return found, r['repo']
        raise ValueError(f"no local checkout of {r['repo']} is known - find_repos lists the checkouts here; give its folder")
    p = os.path.abspath(os.path.expanduser(want))
    if os.path.isdir(p): return p, next((r['repo'] for r in rows if r['path'] and norm(r['path']) == norm(p)), '')
    raise ValueError(f'{want} is neither a repository Taskuary knows nor a folder - find_repos lists the checkouts you may use')


def allowed(store, path: str) -> bool:
    "A known repository's own checkout, or anywhere under the folders the owner lets agents look in."
    return any(inside(path, r['path']) for r in known(store) if r['path']) or any(inside(path, f) for f in folders(store))


def use(store, tid: int, target: str, why: str = '', actor: str = 'agent') -> dict:
    """use_repo: the agent's pick of the checkout, validated, recorded on the task and taken by its live session. ValueError for a pick
    the agent can correct; PermissionError for one it may not make."""
    from . import blackboard as bb, docsync, landing, live, proof, terminal as term
    from .agents import coding_role
    t = store.get_task(int(tid))
    if not t: raise ValueError(f'no task {tid}')
    why = ' '.join(str(why or '').split())[:200] or 'it is where this work lives'
    from . import origin
    # a stranger's words never choose which of the owner's checkouts an agent works in: the owner does, with Change
    if origin.of_task(store, int(tid))[0] == 'stranger':
        raise PermissionError("a stranger's task stays in its own folder - the owner picks its code with Change where the code is")
    pinned = term.repo_tag(t)
    if pinned == term.NO_REPO: raise PermissionError('the owner marked this task as not code work - do it from your folder, or ask them')
    if pinned: raise PermissionError(f'the owner set this task\'s code to {pinned} - work there; to move it, ask them (Change where the code is)')
    path, name = resolve(store, target)
    if not is_checkout(path): raise ValueError(f'{path} is not a git checkout - pick the folder that holds .git (find_repos lists them)')
    if not allowed(store, path):
        raise PermissionError(f"{path} is outside the folders agents may look in for code ({', '.join(folders(store)) or 'none set'}) - "
                              f"the owner adds a folder under {words.name('agents')}")
    added = ''
    if not name:
        name = remote_of(path)[0] or os.path.basename(os.path.normpath(path))
        added = f'Agent added {name} (found at {path})'
        docsync.update_repo_map(store, [{'full_name': name, 'description': added}], actor='agent')
    if name not in _paths(store) and (role := coding_role(store)): term.remember_path(store, role, name, path)
    for x in re.split(r'[\s,]+', str(t.get('Tags') or '')):
        if x.startswith(AGENT_TAG) and x != AGENT_TAG + name: store.tag_task(tid, x, False, actor)
    store.tag_task(tid, AGENT_TAG + name, True, actor)
    store.tag_task(tid, 'held:repo', False, actor)           # funnel.HELD_REPO: where the code is, answered
    for mark in (landing.mark_start, proof.mark_start):
        try: mark(store, tid, path)
        except Exception as e: logger.debug(f'task {tid}: {mark.__module__} start not noted - {e}')
    s = term.session_for(int(tid))
    if s is not None and getattr(s, 'alive', False) and hasattr(s, 'cwd'):
        s.cwd = path
        try: s.dirty0, s._files = bb.dirty(path), ([], 0.0)   # its dirt is counted from here (Term.files)
        except Exception: pass
    try: bb.post(store, f'working in {name}: {why}', 'working', getattr(s, 'agent', '') or 'agent', path, int(tid), sid=getattr(s, 'sid', None))
    except Exception as e: logger.debug(f'task {tid}: no wall line for its repository - {e}')
    if added: store.add_comment(tid, actor, 'agent', added)
    store.add_comment(tid, actor, 'agent', f'Working in {name} - {why}')
    store.audit('task', int(tid), 'use_repo', actor, detail={'repo': name, 'path': path, 'added': bool(added)})
    try: live.emit('task-changed', task_id=int(tid))
    except Exception: pass
    peers = bb.briefing(store, path, exclude_tid=int(tid))
    return {'ok': True, 'repo': name, 'path': path, 'added': bool(added),
            'says': f'Working in {name} ({path}). Your session started in the task\'s folder and stays a process there: run every shell '
                    f'command as `cd "{path}" && ...` and give file tools absolute paths under it.' + (f' {peers}' if peers else '')}
