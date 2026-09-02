"""What an agent SAID it would do and what it DID - one shape for every CLI.

The Board card used to show two raw trace lines; nobody read them. What a person checks is:
which tool is in the agent's hands right now, where it is in its own list, which files it has
written - and whether those stories agree. The DID half needs nothing from the agent: git says
what moved (terminal.Term.files). The SAID half comes from whatever the CLI emits: Claude Code's
hooks (PostToolUse / Stop / UserPromptSubmit, wired by hooks.py), Codex's rollout log under
~/.codex/sessions (FileChange, CommandExecution, AgentMessage, task_complete - tailed here). A
card always says which rung it stands on: tool line -> last screen line -> files only.

No inferred intent. A file is STRAY when no item of the agent's list names it; a write is LATE
when it lands after the agent said it was done. Both are stated as facts for the owner to look
at, never as a verdict.
"""
import glob, json, os, re, threading, time
from datetime import datetime
from loguru import logger

EDIT_TOOLS = {'edit', 'write', 'multiedit', 'notebookedit', 'apply_patch', 'file_change'}
_STATUS = {'completed': 'done', 'done': 'done', 'in_progress': 'now', 'now': 'now', 'pending': 'todo', 'todo': 'todo'}
HOT_S = 20              # a file written this recently is "under the agent's hands"


def _now(): return datetime.now().isoformat(sep=' ', timespec='seconds')


def _rel(p: str, cwd: str) -> str:
    """Repo-relative, forward slashes - the same spelling git and proof.review use."""
    p = str(p or '').replace('\\', '/')
    if cwd:
        c = os.path.normcase(os.path.normpath(cwd)).replace('\\', '/').rstrip('/') + '/'
        if os.path.normcase(p).replace('\\', '/').startswith(c): p = p[len(c):]
    return p


class Witness:
    """One agent's story: the tool in hand, its list, the files it wrote, whether it said done."""

    def __init__(self):
        self.lock = threading.Lock()
        self.tool, self.todos, self.files, self.done_at, self.said, self.source = None, [], {}, None, '', ''

    def note(self, n: dict):
        """A parsed observation: {k: tool|file|todos|done|turn|say, ...}."""
        at = n.get('at') or _now()
        with self.lock:
            k = n.get('k')
            if k == 'tool': self.tool = {'name': n.get('name') or '', 'target': str(n.get('target') or '')[:160], 'at': at}
            elif k == 'file':
                f = self.files.setdefault(n['path'], {'n': 0, 'first': at, 'last': at})
                f['n'] += 1; f['last'] = at
            elif k == 'todos': self.todos = [{'text': str(t.get('text') or '')[:140], 'status': _STATUS.get(str(t.get('status') or 'todo').lower(), 'todo')} for t in (n.get('items') or [])][:40]
            elif k == 'done': self.done_at = at; self.said = str(n.get('text') or self.said or '')
            elif k == 'turn': self.done_at = None            # a new prompt: writes from here are not "after done"
            elif k == 'say': self.said = str(n.get('text') or '')
            if n.get('source'): self.source = n['source']

    def snapshot(self, git_files=None, cwd: str = '', last_line: str = '') -> dict:
        """The card's view. git_files (terminal.Term.files) are the DID truth even when the CLI told
        us nothing; witness counts and times enrich them."""
        with self.lock:
            files = {_rel(p, cwd): dict(v) for p, v in self.files.items()}
            for p in (git_files or []):
                files.setdefault(_rel(p, cwd), {'n': 0, 'first': None, 'last': None})
            todos = [dict(t) for t in self.todos]; tool = dict(self.tool) if self.tool else None
            done_at, said, source = self.done_at, self.said, self.source
        words = ' '.join(t['text'] for t in todos).lower()
        def named(p):
            stem = re.sub(r'\.[^.]+$', '', p.rsplit('/', 1)[-1]).lower()
            parent = p.rsplit('/', 2)[-2].lower() if '/' in p else ''
            return bool(stem) and stem in words or bool(parent) and parent in words
        # "stray" only means something when the list speaks in files at all - a list of intentions
        # ("wire the card") names no file, and flagging every file against it would be noise
        speaks_files = bool(todos) and any(named(p) for p in files)
        rows = [{'path': p, 'n': v['n'], 'last': v['last'], 'stray': speaks_files and not named(p),
                 'late': bool(done_at and v['last'] and v['last'] > done_at)} for p, v in files.items()]
        rows.sort(key=lambda r: (r['last'] or '', r['n']), reverse=True)
        flags = []
        for r in rows:
            if r['late']: flags.append({'level': 'check', 'text': f"{r['path'].rsplit('/', 1)[-1]} written after the agent said done" + (' - in no item of its list' if r['stray'] else '')})
        if done_at:
            for r in rows:
                if r['stray'] and not r['late']: flags.append({'level': 'note', 'text': f"{r['path'].rsplit('/', 1)[-1]} touched but not in the list"})
        rung = 'tool' if tool else 'line' if last_line else 'files'
        return {'source': source, 'rung': rung, 'tool': tool, 'todos': todos, 'files': rows[:30], 'done_at': done_at,
                'said': said[:300], 'last_line': (last_line or '')[:200], 'flags': flags[:3],
                'n_done': sum(t['status'] == 'done' for t in todos), 'n_todos': len(todos)}


# ── Claude Code: hook payloads (hooks.py wires them, server.py receives them) ─────────────────
def claude_notes(p: dict) -> list:
    from .agents import _fmt_input
    ev, at = p.get('hook_event_name') or '', _now()
    if ev == 'PostToolUse':
        name, inp = str(p.get('tool_name') or ''), p.get('tool_input') or {}
        out = [{'k': 'tool', 'name': name, 'target': _fmt_input(inp), 'at': at, 'source': 'hook'}]
        if name.lower() in EDIT_TOOLS:
            path = inp.get('file_path') or inp.get('notebook_path') or inp.get('path')
            if path: out.append({'k': 'file', 'path': str(path), 'at': at})
        if name == 'TodoWrite':
            out.append({'k': 'todos', 'items': [{'text': t.get('content') or t.get('activeForm') or '', 'status': t.get('status')} for t in (inp.get('todos') or []) if isinstance(t, dict)], 'at': at})
        return out
    if ev == 'Stop': return [{'k': 'done', 'text': str(p.get('last_assistant_message') or '').strip(), 'at': at, 'source': 'hook'}]
    if ev == 'UserPromptSubmit': return [{'k': 'turn', 'at': at, 'source': 'hook'}]
    return []


# ── Codex: the TUI writes every event to ~/.codex/sessions/Y/M/D/rollout-*.jsonl as it goes ──
_CMD = re.compile(r'"cmd"\s*:\s*"((?:[^"\\]|\\.)*)"')

def _plan_items(obj) -> list:
    """codex's update_plan: [{step, status}] - or a todo list [{text, completed}]; either becomes our items."""
    items = obj.get('plan') if isinstance(obj, dict) else None
    if not isinstance(items, list): items = obj.get('items') if isinstance(obj, dict) else None
    if not isinstance(items, list): return []
    out = []
    for it in items:
        if not isinstance(it, dict): continue
        st = it.get('status') or ('completed' if it.get('completed') else 'pending')
        out.append({'text': it.get('step') or it.get('text') or '', 'status': st})
    return out


def codex_notes(j: dict) -> list:
    """One rollout line -> observations. Shapes read off real rollouts (codex-cli 0.148)."""
    t, p = j.get('type'), j.get('payload') or {}
    at = str(j.get('timestamp') or '')[:19].replace('T', ' ') or _now()
    if t == 'event_msg':
        pt = p.get('type')
        if pt == 'item_completed':
            it = p.get('item') or {}; kind = it.get('type')
            if kind == 'CommandExecution':
                cmd = it.get('command'); cmd = cmd[-1] if isinstance(cmd, list) and cmd else str(cmd or '')
                return [{'k': 'tool', 'name': 'shell', 'target': cmd, 'at': at, 'source': 'rollout'}]
            if kind == 'FileChange':
                paths = list((it.get('changes') or {}).keys()) if isinstance(it.get('changes'), dict) else [c.get('path') for c in (it.get('changes') or []) if isinstance(c, dict)]
                return [{'k': 'tool', 'name': 'Edit', 'target': (paths[0] if paths else ''), 'at': at, 'source': 'rollout'}] + [{'k': 'file', 'path': x, 'at': at} for x in paths if x]
            if kind == 'AgentMessage':
                txt = ' '.join(c.get('text') or '' for c in (it.get('content') or []) if isinstance(c, dict)).strip()
                return [{'k': 'say', 'text': txt, 'at': at}] if txt else []
            items = _plan_items(it)
            return [{'k': 'todos', 'items': items, 'at': at, 'source': 'rollout'}] if items else []
        if pt == 'patch_apply_end':
            return [{'k': 'file', 'path': x, 'at': at} for x in (p.get('changes') or {}).keys()]
        if pt == 'task_started': return [{'k': 'turn', 'at': at, 'source': 'rollout'}]
        if pt == 'task_complete': return [{'k': 'done', 'text': str(p.get('last_agent_message') or '').strip(), 'at': at, 'source': 'rollout'}]
        items = _plan_items(p)
        if items: return [{'k': 'todos', 'items': items, 'at': at, 'source': 'rollout'}]
    if t == 'response_item' and p.get('type') == 'custom_tool_call' and p.get('name') == 'exec':
        m = _CMD.search(str(p.get('input') or ''))
        return [{'k': 'tool', 'name': 'shell', 'target': (m.group(1) if m else str(p.get('input') or '')[:120]), 'at': at, 'source': 'rollout'}]
    if t == 'response_item' and p.get('type') == 'function_call' and p.get('name') == 'update_plan':
        try: items = _plan_items(json.loads(p.get('arguments') or '{}'))
        except ValueError: items = []
        return [{'k': 'todos', 'items': items, 'at': at, 'source': 'rollout'}] if items else []
    return []


_BOUND = set()      # rollout files already claimed by a session

class RolloutTail(threading.Thread):
    """Follow the rollout Codex writes for THIS session: the first rollout created after the pty
    opened whose session_meta.cwd is the session's cwd. Stops with the session."""

    def __init__(self, term):
        super().__init__(daemon=True)
        self.t, self.path, self.pos, self.buf = term, None, 0, ''
        self.t0 = time.time() - 3

    def _find(self):
        from .climodels import codex_home
        want = os.path.normcase(os.path.normpath(self.t.cwd))
        for f in sorted(glob.glob(str(codex_home() / 'sessions' / '*' / '*' / '*' / 'rollout-*.jsonl')), key=os.path.getmtime, reverse=True):
            if f in _BOUND or os.path.getmtime(f) < self.t0: continue
            try:
                with open(f, encoding='utf-8') as fh: first = json.loads(fh.readline() or '{}')
            except (OSError, ValueError): continue
            cwd = ((first.get('payload') or {}).get('cwd') or '') if first.get('type') == 'session_meta' else ''
            if cwd and os.path.normcase(os.path.normpath(cwd)) == want:
                _BOUND.add(f); return f
        return None

    def _feed(self):
        with open(self.path, 'rb') as fh:
            fh.seek(self.pos); chunk = fh.read(); self.pos = fh.tell()
        self.buf += chunk.decode('utf-8', 'replace')
        *lines, self.buf = self.buf.split('\n')
        for l in lines:
            if not l.strip(): continue
            try: j = json.loads(l)
            except ValueError: continue
            for n in codex_notes(j): self.t.witness.note(n)

    def run(self):
        try:
            while self.t.alive:
                if not self.path: self.path = self._find()
                if self.path: self._feed()
                time.sleep(2)
        except Exception as e: logger.debug(f'rollout tail for {self.t.sid} ended: {e}')
