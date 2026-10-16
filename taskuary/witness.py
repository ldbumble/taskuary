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
        self.turn_at, self.said_at, self.seq = None, None, 0      # turn_at/said_at: the note's place in order, not its clock

    def note(self, n: dict):
        """A parsed observation: {k: tool|file|todos|done|turn|say, ...}."""
        at = n.get('at') or _now()
        with self.lock:
            k = n.get('k'); self.seq += 1
            if k == 'tool': self.tool = {'name': n.get('name') or '', 'target': str(n.get('target') or '')[:160], 'at': at, **({'error': str(n['error'])[:200]} if n.get('error') else {})}
            elif k == 'file':
                f = self.files.setdefault(n['path'], {'n': 0, 'first': at, 'last': at})
                f['n'] += 1; f['last'] = at
            elif k == 'todos': self.todos = [{'text': str(t.get('text') or '')[:140], 'status': _STATUS.get(str(t.get('status') or 'todo').lower(), 'todo')} for t in (n.get('items') or [])][:40]
            elif k == 'done':                                # a Stop with no words keeps only words said in THIS turn
                kept = self.said if self.turn_at is None or (self.said_at or 0) > self.turn_at else ''
                self.done_at, self.said, self.turn_at, self.said_at = at, str(n.get('text') or kept), None, self.seq
            elif k == 'turn': self.done_at = None; self.turn_at = self.seq   # a new prompt: writes from here are not "after done"
            elif k == 'say': self.said = str(n.get('text') or ''); self.said_at = self.seq
            if n.get('source'): self.source = n['source']

    # THE LAST WORD BELONGS TO ITS TURN (TQ-1112 shape): `said` outlives the prompt after it, so a session closed while it worked
    # on "merge it please" was filed with the turn before - "I recommend merging ... waiting on you" - as its ending.
    def cut_off(self) -> bool:
        "A turn began and has not ended: whatever it says now is not its final word."
        with self.lock: return self.turn_at is not None and self.done_at is None

    def said_now(self) -> str:
        "What the agent said in its CURRENT turn, or its last finished one - never a turn the owner has since moved past."
        with self.lock:
            stale = self.turn_at is not None and (self.said_at is None or self.said_at < self.turn_at)
            return '' if stale else self.said

    def snapshot(self, git_files=None, cwd: str = '', last_line: str = '') -> dict:
        """The card's view. git_files (terminal.Term.files) are the DID truth even when the CLI told
        us nothing; witness counts and times enrich them."""
        with self.lock:
            files = {_rel(p, cwd): dict(v) for p, v in self.files.items()}
            for p in (git_files or []):
                files.setdefault(_rel(p, cwd), {'n': 0, 'first': None, 'last': None})
            todos = [dict(t) for t in self.todos]; tool = dict(self.tool) if self.tool else None
            done_at, said, source = self.done_at, self.said, self.source
        # NO "STRAY" FLAG (2026-10-11, "everything should be ai"): a file was marked "touched but not in the list" when its
        # name was not a substring of the todo text - "wire the card" against website/src/Card.jsx read as stray, and
        # "fix the server" against taskuary/server.py did not. Whether a file belongs to an item is meaning, not a fact
        # the hooks gave us. What stays is a fact: written after the agent said it was done.
        rows = [{'path': p, 'n': v['n'], 'last': v['last'],
                 'late': bool(done_at and v['last'] and v['last'] > done_at)} for p, v in files.items()]
        rows.sort(key=lambda r: (r['last'] or '', r['n']), reverse=True)
        flags = []
        for r in rows:
            if r['late']: flags.append({'level': 'check', 'text': f"{r['path'].rsplit('/', 1)[-1]} written after the agent said done"})
        rung = 'tool' if tool else 'line' if last_line else 'files'
        return {'source': source, 'rung': rung, 'tool': tool, 'todos': todos, 'files': rows[:30], 'done_at': done_at,
                'said': said[:300], 'last_line': (last_line or '')[:200], 'flags': flags[:3],
                'n_done': sum(t['status'] == 'done' for t in todos), 'n_todos': len(todos)}


# ── Claude Code: hook payloads (hooks.py wires them, server.py receives them) ─────────────────
def turn_text(path) -> str:
    """Everything the agent SAID since the owner's last prompt, from Claude's own transcript - not only its last message.
    An agent wrote the reply, ran `taskuary --done`, then said "The reply above is ready for you to review"; the Stop hook's
    last_assistant_message is that last line alone, so the reply was drafted from a pointer to text it never saw - a
    placeholder went out for review (2026-10-13). A wake (a background job reporting) is not the owner's prompt. '' when
    the file cannot be read: the caller keeps the last message."""
    try: rows = [json.loads(l) for l in open(path, encoding='utf-8', errors='replace') if l.strip()]
    except (OSError, TypeError, ValueError): return ''
    def prompt(r):
        m = r.get('message') or {}
        if r.get('type') != 'user' or m.get('role') != 'user': return False
        c = m.get('content')
        txt = c if isinstance(c, str) else ' '.join(b.get('text') or '' for b in c or [] if isinstance(b, dict) and b.get('type') == 'text')
        return bool(txt.strip()) and not txt.lstrip().startswith(('<task-notification>', '<system_notification>'))
    start = max((i for i, r in enumerate(rows) if prompt(r)), default=-1)
    said = [b.get('text') or '' for r in rows[start + 1:] if (r.get('message') or {}).get('role') == 'assistant'
            for b in ((r.get('message') or {}).get('content') or []) if isinstance(b, dict) and b.get('type') == 'text']
    return '\n\n'.join(s.strip() for s in said if s.strip())


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
    if ev == 'PostToolUseFailure':
        # the tool itself failed: the pane shows the failure where a running tool would show its name
        return [{'k': 'tool', 'name': str(p.get('tool_name') or ''), 'target': _fmt_input(p.get('tool_input') or {}), 'at': at, 'source': 'hook',
                 'error': str(p.get('error') or p.get('error_message') or 'failed').strip()[:200]}]
    if ev == 'Stop':
        last = str(p.get('last_assistant_message') or '').strip()
        return [{'k': 'done', 'text': turn_text(p.get('transcript_path')) or last, 'at': at, 'source': 'hook'}]
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

    def _ours(self, meta: dict) -> bool:
        """Is this rollout THIS pane's? A pane that already knows its thread (resumed - Codex forks it, so the new
        rollout names the old id as forked_from_id) takes only that thread's. One that does not takes a rollout CREATED
        after the pty opened: modified-after was the test, and another codex working in the same folder - the owner's
        own - writes its rollout all the time, so it read as this pane's (2026-09-28)."""
        ids = {i for i in (getattr(self.t, 'ext_id', ''), getattr(self.t, 'resumed_from', '')) if i}
        if ids: return bool(ids & {meta.get('id'), meta.get('forked_from_id'), meta.get('session_id')})
        at = str(meta.get('timestamp') or '')
        if not at: return True                  # an older codex that does not stamp session_meta: the mtime test stands
        try: return datetime.fromisoformat(at.replace('Z', '+00:00')).timestamp() >= self.t0
        except ValueError: return True

    def _find(self):
        from .climodels import codex_home
        want = os.path.normcase(os.path.normpath(self.t.cwd))
        for f in sorted(glob.glob(str(codex_home() / 'sessions' / '*' / '*' / '*' / 'rollout-*.jsonl')), key=os.path.getmtime, reverse=True):
            if f in _BOUND or os.path.getmtime(f) < self.t0: continue
            try:
                with open(f, encoding='utf-8') as fh: first = json.loads(fh.readline() or '{}')
            except (OSError, ValueError): continue
            meta = (first.get('payload') or {}) if first.get('type') == 'session_meta' else {}
            cwd = meta.get('cwd') or ''
            if cwd and os.path.normcase(os.path.normpath(cwd)) == want and self._ours(meta):
                _BOUND.add(f)
                # the rollout names the thread codex can be told to resume; the filename carries
                # the same id for older rollouts that did not write it into session_meta
                from .terminal import bind_ext
                m = re.search(r'rollout-[\d\-T]+-(.+)\.jsonl$', os.path.basename(f))
                bind_ext(self.t, str(meta.get('id') or (m.group(1) if m else '')))
                return f
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
