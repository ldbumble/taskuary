"""Report a bug from where it happened: the facts, scrubbed, and a draft the person checks.

The tracker (`ldbumble/taskuary`) is PUBLIC, and this app reads one person's mail. So the facts are
gathered by code - where, the error, versions, the log around it, action names - never by a model
that might reach for a task title, and every string is scrubbed before the person sees the draft.
Nothing leaves from here: the popup shows the text and the person presses Submit on GitHub.
"""
import hashlib, json, os, platform, re, sys
from datetime import datetime
from pathlib import Path

from . import config

N_LOG, N_ACTIONS = 30, 5
_STAMP = re.compile(r'^(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}) ')        # logs.setup's file format
_ID = re.compile(r'^(?:\d+|[0-9a-fA-F]{32})$')
_FRAME = re.compile(r'^\s*(?:at\s|File\s|\S+@\S+:\d+)')               # Chrome, Python, Firefox


def _dockerenv(): return Path('/.dockerenv').exists()
def _source(): return (Path(__file__).resolve().parent.parent / 'pyproject.toml').exists()


def install_kind() -> str:
    from . import deps
    if deps.frozen(): return 'exe'
    if _dockerenv() or os.environ.get('TASKUARY_HOME') == '/data': return 'docker'
    return 'source' if _source() else 'pip'


def norm_route(route) -> str:
    """Ids out of a route, so two reports of the same bug on different tasks share a fingerprint."""
    path = str(route or '').split('?')[0]
    return '/'.join(':id' if _ID.match(p) else p for p in path.split('/'))


def _brain(store, slot) -> str:
    """A slot's brain as a CLI name or a connector type - never a Name, which can be an account."""
    from . import agents, llm
    v = str(store.get_setting(slot['key']) or '').strip()
    if slot['pick'] == 'agent': v = f"cli:{v or agents.default_agent(store)}" if ':' not in v else v
    st = llm.brain_status(store, v)
    if st.get('Type') != 'cli': return str(st.get('Type') or '')
    row = agents.agent_row(store, str(st.get('pick') or '')[4:]) or {}
    try: prof = json.loads(row.get('Config') or '{}')
    except (TypeError, ValueError): prof = {}
    return f"{agents.cli_of(prof if isinstance(prof, dict) else {}, row.get('Name') or '') or 'unknown'} (cli)"


def _fact(f, default='?'):
    # one unreadable fact must not cost the person the whole report
    try: return f()
    except Exception: return default


def env(store) -> str:
    from . import __version__, aidefaults
    brains = list(dict.fromkeys(b for b in (_fact(lambda s=s: _brain(store, s), '') for s in aidefaults.SLOTS) if b))
    conns = _fact(lambda: sorted({c['Type'] for c in store.list_connectors() if c.get('Active') and c.get('Type')}), [])
    v = sys.version_info
    return (f"Taskuary {__version__} ({_fact(install_kind)}) · {platform.system()} {platform.release()} · Python {v.major}.{v.minor}"
            f" · brains: {', '.join(brains) or 'none'} · connectors: {', '.join(conns) or 'none'}")


def _when(at):
    """The client's ISO time as the log's own clock: loguru stamps local time, a browser sends UTC."""
    try: t = datetime.fromisoformat(str(at).strip().replace('Z', '+00:00'))
    except ValueError: return None
    return t.astimezone().replace(tzinfo=None) if t.tzinfo else t


def log_near(at, n=N_LOG) -> str:
    """The `n` lines ending with the last record stamped at or just before `at` (a traceback rides with its
    record); the newest lines when there is no time. A missing log is '', never an error."""
    try: lines = (config.home() / 'taskuary.log').read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError: return ''
    t, end = _when(at) if at else None, len(lines)
    if t:
        # the server logs a failure before its answer reaches the page, so what the error left is at or before `at`
        cut, stamped = t.strftime('%Y-%m-%d %H:%M:%S'), [i for i, l in enumerate(lines) if _STAMP.match(l)]
        before = [i for i in stamped if _STAMP.match(lines[i]).group(1) <= cut]
        if before: end = next((i for i in stamped if i > before[-1]), len(lines))
        elif stamped: end = min(len(lines), stamped[0] + n)
    return '\n'.join(lines[max(0, end - n):end])


def _etype(err) -> str:
    first = str(err or '').strip().split('\n')[0]
    m = re.match(r'([A-Za-z_][\w.]*)\s*:', first)
    return m.group(1) if m else first[:40]


def _frame(stack) -> str:
    return next((l.strip() for l in str(stack or '').splitlines() if _FRAME.match(l)), '')


def fingerprint(err, route, stack) -> str:
    return hashlib.sha1(f'{_etype(err)}|{norm_route(route)}|{_frame(stack)}'.encode()).hexdigest()[:10]


def collect(store, client: dict) -> dict:
    """The report's facts, unscrubbed: `client` carries screen, route, error, stack, actions and at (ISO)."""
    c = client or {}
    g = lambda k: str(c.get(k) or '').strip()
    err, stack = g('error'), g('stack')
    # a browser stack repeats the message as its first line; Python's does not
    body = '\n'.join(stack.splitlines()[1:] if stack.startswith(err.split('\n')[0]) and err else stack.splitlines())
    acts = c.get('actions') if isinstance(c.get('actions'), list) else []
    return {'where': ' '.join(x for x in (g('screen'), f"({g('route')})" if g('route') else '') if x),
            'error': '\n'.join(x for x in (err, '\n'.join(body.splitlines()[:40])) if x),
            'env': env(store), 'log': log_near(g('at')),
            'actions': [str(a)[:80] for a in acts[-N_ACTIONS:]],
            'fingerprint': fingerprint(err, g('route'), stack)}
