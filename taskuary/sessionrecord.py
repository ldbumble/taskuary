"""What an agent did and thought, in one shape whoever the agent was (the owner, 2026-10-10: "unify what gets saved and
show as much information about what gets saved ... different cli tools, general agent vs regular ... the agent work
section carries enough info to let user know everything the agent did and thought about").

A session's record was whatever its road happened to leave: a coding pane left a 12k tail of rendered SCREEN and a
three-field report; a general chat left its turns and threw its tool calls away with the next turn; nobody kept the
thinking. Every CLI already writes the whole account to disk - claude's project .jsonl, codex's rollout, copilot's
events.jsonl, gemini's chat file - addressed by the conversation id we already file (transcript.ExtId). This reads
that account into one list of steps, and keeps a copy beside the task's artifacts when the session is saved, so a CLI
pruning its logs next month does not take the record with it.

A step is {k, text, name?, file?, at?}: k is `you` (what the agent was told), `brief` (what Taskuary told it - keep_seed),
`thought`, `said`, `tool` (name + what it was pointed at), `plan` (its todo list) or `error`. Tool OUTPUT is left out on purpose - it is the noise the record
is read past, and the agent's next thought or answer says what it made of it."""
import json
import re
from datetime import datetime
from pathlib import Path

from loguru import logger

from . import session_artifacts
from .wrapup import REPORTS

THOUGHT_N, SAID_N, YOU_N, TARGET_N = 6000, 20000, 3000, 300
MAX_STEPS = 800
NOTE_ACTOR = 'taskuary'   # who files Taskuary's own notes into a task's chat - a receipt, the Advisor's word - never an agent's turn
_FILE_TOOLS = {'Edit', 'Write', 'MultiEdit', 'NotebookEdit', 'apply_patch', 'edit', 'write', 'create', 'str_replace_editor',
               'write_file', 'replace', 'edit_file'}
_TARGET_KEYS = ('command', 'cmd', 'pattern', 'query', 'url', 'file_path', 'path', 'filePath', 'absolute_path', 'description', 'prompt')


def _home() -> Path: return Path.home()
def _cut(s, n): s = str(s or '').strip(); return s if len(s) <= n else s[:n].rstrip() + '…'


def _target(args) -> str:
    """What a tool was pointed at, in one line: the command, the file, the search - never the whole payload."""
    if isinstance(args, str):
        try: args = json.loads(args)
        except ValueError: return _cut(args.splitlines()[0] if args.strip() else '', TARGET_N)
    if not isinstance(args, dict): return ''
    v = next((args[k] for k in _TARGET_KEYS if args.get(k)), None)
    if v is None: v = next((x for x in args.values() if isinstance(x, str) and x.strip()), '')
    if (args.get('pattern') or args.get('query')) and args.get('path'): v = f"{v} in {args['path']}"     # a search says where it looked
    return _cut(' '.join(str(v).split()), TARGET_N)


def _tool(name, args, at=None) -> dict:
    s = {'k': 'tool', 'name': str(name or 'tool'), 'text': _target(args), 'at': at}
    a = args if isinstance(args, dict) else {}
    # a command the agent DESCRIBED reads as what it was for; the command itself stays one click away
    if str(a.get('description') or '').strip() and (a.get('command') or a.get('cmd')):
        s['text'], s['detail'] = _cut(a['description'], TARGET_N), _cut(a.get('command') or a.get('cmd'), 4000)
    f = a.get('file_path') or a.get('path') or a.get('filePath') or a.get('absolute_path')
    if name in _FILE_TOOLS and f: s['file'] = str(f)
    todos = a.get('todos') or a.get('plan')
    if isinstance(todos, list) and todos:
        items = [{'text': _cut(t.get('content') or t.get('step') or t.get('text') or '', 300),
                  'status': str(t.get('status') or 'pending')} for t in todos if isinstance(t, dict)]
        if items: return {'k': 'plan', 'name': str(name), 'items': items, 'at': at}
    return s


def _blocks(content):
    return content if isinstance(content, list) else [{'type': 'text', 'text': content}] if isinstance(content, str) else []


# ── each CLI's own log ───────────────────────────────────────────────────────────────────
_FOUND = {}                     # conversation id -> its file: a glob over every project folder is not paid on each read


def _newest(base: Path, pattern: str):
    k = (str(base), pattern)
    if k in _FOUND and _FOUND[k].is_file(): return _FOUND[k]
    f = next(iter(sorted(base.glob(pattern), key=lambda p: -p.stat().st_mtime)), None)
    if f: _FOUND[k] = f
    return f


def _claude_file(ext: str): return _newest(_home() / '.claude' / 'projects', f'*/{ext}.jsonl')


def _claude(path: Path) -> list:
    out = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try: j = json.loads(line)
        except ValueError: continue
        if j.get('isMeta') or j.get('isSidechain') or j.get('type') not in ('user', 'assistant'): continue
        at, msg = j.get('timestamp'), j.get('message') or {}
        for b in _blocks(msg.get('content')):
            t = b.get('type')
            if j['type'] == 'user':
                # the owner's words - not a tool result coming back, not a slash command's or a hook's plumbing
                if t == 'text' and (x := str(b.get('text') or '').strip()) and not x.startswith(('<command-', '<local-command', '<system-reminder', 'Caveat:')):
                    out.append({'k': 'you', 'text': _cut(x, YOU_N), 'at': at})
            elif t == 'thinking' and str(b.get('thinking') or '').strip(): out.append({'k': 'thought', 'text': _cut(b['thinking'], THOUGHT_N), 'at': at})
            elif t == 'text' and str(b.get('text') or '').strip(): out.append({'k': 'said', 'text': _cut(b['text'], SAID_N), 'at': at})
            elif t == 'tool_use': out.append(_tool(b.get('name'), b.get('input'), at))
    return out


def _codex_file(ext: str): return _newest(_home() / '.codex' / 'sessions', f'**/rollout-*{ext}.jsonl')


def _codex(path: Path) -> list:
    out = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try: j = json.loads(line)
        except ValueError: continue
        p, at = j.get('payload') or {}, j.get('timestamp')
        if j.get('type') == 'event_msg' and p.get('type') == 'user_message' and str(p.get('message') or '').strip():
            out.append({'k': 'you', 'text': _cut(p['message'], YOU_N), 'at': at})
        if j.get('type') != 'response_item': continue
        t = p.get('type')
        if t == 'reasoning':
            # its summary when the model wrote one; the rest is encrypted and stays that way
            x = '\n\n'.join(str(s.get('text') or '') for s in p.get('summary') or [] if isinstance(s, dict)).strip()
            if x: out.append({'k': 'thought', 'text': _cut(x, THOUGHT_N), 'at': at})
        elif t == 'message' and p.get('role') == 'assistant':
            x = '\n'.join(str(c.get('text') or '') for c in p.get('content') or [] if isinstance(c, dict)).strip()
            if x: out.append({'k': 'said', 'text': _cut(x, SAID_N), 'at': at})
        elif t in ('function_call', 'custom_tool_call', 'local_shell_call'):
            args = p.get('arguments') or p.get('input') or (p.get('action') or {})
            if t == 'custom_tool_call' and p.get('name') == 'apply_patch':
                files = re.findall(r'^\*\*\* (?:Update|Add|Delete) File: (.+)$', str(args), re.M)
                out += [{'k': 'tool', 'name': 'apply_patch', 'text': _cut(f, TARGET_N), 'file': f, 'at': at} for f in files] or [_tool('apply_patch', '', at)]
            elif t == 'custom_tool_call' and (cmds := re.findall(r'\bcmd:\s*"((?:[^"\\]|\\.)*)"', str(args))):
                out += [{'k': 'tool', 'name': 'shell', 'text': _cut(c.replace('\\"', '"'), TARGET_N), 'at': at} for c in cmds]   # codex's js harness: the commands it ran
            else: out.append(_tool(p.get('name') or 'shell', args, at))
    return out


def _copilot_file(ext: str):
    p = _home() / '.copilot' / 'session-state' / ext / 'events.jsonl'
    return p if p.is_file() else None


def _copilot(path: Path) -> list:
    out = []
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try: j = json.loads(line)
        except ValueError: continue
        d, at, t = j.get('data') or {}, j.get('timestamp'), j.get('type')
        if t == 'user.message' and str(d.get('content') or '').strip(): out.append({'k': 'you', 'text': _cut(d['content'], YOU_N), 'at': at})
        elif t == 'assistant.message':
            if str(d.get('reasoningText') or '').strip(): out.append({'k': 'thought', 'text': _cut(d['reasoningText'], THOUGHT_N), 'at': at})
            if str(d.get('content') or '').strip(): out.append({'k': 'said', 'text': _cut(d['content'], SAID_N), 'at': at})
        elif t == 'tool.execution_start': out.append(_tool(d.get('toolName'), d.get('arguments'), at))
        elif t == 'tool.execution_complete' and d.get('success') is False:
            out.append({'k': 'error', 'text': _cut((d.get('error') or {}).get('message') if isinstance(d.get('error'), dict) else d.get('error') or 'a tool failed', 400), 'at': at})
    return out


def _gemini_file(ext: str):
    """gemini names no file by id: the chat file that carries it (layout from its docs - sessionfiles)."""
    for p in sorted((_home() / '.gemini' / 'tmp').glob('*/chats/session-*.json*'), key=lambda p: -p.stat().st_mtime)[:200]:
        try:
            if ext in p.read_text(encoding='utf-8', errors='replace')[:4000] or p.stem.endswith(ext[:8]): return p
        except OSError: continue
    return None


def _gemini(path: Path) -> list:
    try: j = json.loads(path.read_text(encoding='utf-8', errors='replace'))
    except ValueError: return []
    out = []
    for m in (j.get('messages') if isinstance(j, dict) else j) or []:
        if not isinstance(m, dict): continue
        at, text = m.get('timestamp'), m.get('content') if isinstance(m.get('content'), str) else ' '.join(
            str(x.get('text') or '') for x in m.get('content') or [] if isinstance(x, dict))
        if m.get('type') == 'user':
            if text.strip(): out.append({'k': 'you', 'text': _cut(text, YOU_N), 'at': at})
            continue
        for th in m.get('thoughts') or []:
            x = ': '.join(str(th.get(k) or '') for k in ('subject', 'description') if th.get(k)) if isinstance(th, dict) else str(th)
            if x.strip(): out.append({'k': 'thought', 'text': _cut(x, THOUGHT_N), 'at': at})
        out += [_tool(c.get('name'), c.get('args'), at) for c in m.get('toolCalls') or [] if isinstance(c, dict)]
        if text.strip(): out.append({'k': 'said', 'text': _cut(text, SAID_N), 'at': at})
    return out


# cli name (terminal.cli_of / transcript.Brain) -> (find the file by conversation id, read it, what to call it)
READERS = {'claude': (_claude_file, _claude, 'Claude Code log'), 'codex': (_codex_file, _codex, 'Codex rollout'),
           'copilot': (_copilot_file, _copilot, 'Copilot session log'), 'gemini': (_gemini_file, _gemini, 'Gemini chat file')}


def cli_steps(cli: str, ext: str) -> tuple[list, str]:
    """(steps, source) from the CLI's own log, or ([], '') when it keeps none we can read."""
    r = READERS.get(str(cli or '').split('/')[-1].removesuffix('.exe'))
    if not (r and ext): return [], ''
    try:
        f = r[0](str(ext))
        return (r[1](f), r[2]) if f else ([], '')
    except Exception as e:
        logger.debug(f'session record: {cli} log for {ext} unreadable - {e}'); return [], ''


# WHAT A RUN COST (the owner, 2026-10-22: cost & time per run): the tokens each CLI's own log counts, from `since` - a resumed
# conversation's log holds every earlier run too. {'in': every input token, cached ones included, 'cached', 'out', 'cost'?}; a log
# that counts nothing gives {}, and only a log that prices its run gives 'cost' - an unknown cost is said by saying nothing, never $0.
def _after(at, since) -> bool: return not since or _local(at) >= since


def _claude_usage(path: Path, since: str) -> dict:
    msgs, cost = {}, 0.0
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try: j = json.loads(line)
        except ValueError: continue
        if j.get('type') != 'assistant' or j.get('isSidechain') or not _after(j.get('timestamp'), since): continue
        m = j.get('message') or {}
        if isinstance(m.get('usage'), dict): msgs[m.get('id') or len(msgs)] = m['usage']    # one message spans lines, each with its usage
        if isinstance(j.get('costUSD'), (int, float)): cost += j['costUSD']
    if not msgs: return {}
    n = lambda k: sum(int(u.get(k) or 0) for u in msgs.values())
    cached = n('cache_read_input_tokens')
    return {'in': n('input_tokens') + n('cache_creation_input_tokens') + cached, 'cached': cached, 'out': n('output_tokens'),
            **({'cost': round(cost, 4)} if cost else {})}


def _codex_usage(path: Path, since: str) -> dict:
    got = {'in': 0, 'cached': 0, 'out': 0}
    for line in path.read_text(encoding='utf-8', errors='replace').splitlines():
        try: j = json.loads(line)
        except ValueError: continue
        p = j.get('payload') or {}
        if j.get('type') != 'event_msg' or p.get('type') != 'token_count' or not _after(j.get('timestamp'), since): continue
        u = (p.get('info') or {}).get('last_token_usage') or {}       # each turn's own; total_token_usage runs across runs
        for k, f in (('in', 'input_tokens'), ('cached', 'cached_input_tokens'), ('out', 'output_tokens')): got[k] += int(u.get(f) or 0)
    return got if got['in'] or got['out'] else {}


def _gemini_usage(path: Path, since: str) -> dict:
    try: j = json.loads(path.read_text(encoding='utf-8', errors='replace'))
    except ValueError: return {}
    got = {'in': 0, 'cached': 0, 'out': 0}
    for m in (j.get('messages') if isinstance(j, dict) else j) or []:
        t = m.get('tokens') if isinstance(m, dict) else None
        if not isinstance(t, dict) or not _after(m.get('timestamp'), since): continue
        got['in'] += int(t.get('input') or 0); got['cached'] += int(t.get('cached') or 0)
        got['out'] += int(t.get('output') or 0) + int(t.get('thoughts') or 0)
    return got if got['in'] or got['out'] else {}


USAGE = {'claude': _claude_usage, 'codex': _codex_usage, 'gemini': _gemini_usage}


def cli_usage(cli: str, ext: str, since: str = '') -> dict:
    """What this run cost by its CLI's own count, from `since` (local time) - {} when the CLI keeps no count we can read."""
    name = str(cli or '').split('/')[-1].removesuffix('.exe')
    if not (ext and name in USAGE): return {}
    try:
        f = READERS[name][0](str(ext))
        return USAGE[name](f, since) if f else {}
    except Exception as e:
        logger.debug(f'session record: {cli} usage for {ext} unreadable - {e}'); return {}


def took(steps: list, started: str, ended: str = '') -> int | None:
    """Seconds from the run's start to the last thing it did - not to when its pane closed, which can be hours of waiting on the
    owner later. A run whose log has no times is measured to `ended`; None when the start is unknown."""
    if not started: return None
    times = [t for x in steps if x.get('at') and (t := _local(x['at'])) >= started]
    end = max(times) if times else ended
    try: return max(0, int((datetime.fromisoformat(end) - datetime.fromisoformat(started)).total_seconds())) if end else None
    except ValueError: return None


def screen_steps(text: str) -> list:
    """No readable log (cursor, devin, muse, a pane with no id yet): what was on screen is still the record."""
    return [{'k': 'screen', 'text': str(text).strip()[-SAID_N:]}] if str(text or '').strip() else []


# ── the general agent: its turns are comments, its steps were thrown away with the next turn ──
def _gen_path(tid: int) -> Path:
    d = session_artifacts.root() / str(int(tid)); d.mkdir(parents=True, exist_ok=True)
    return d / 'general-steps.jsonl'


def keep_turn(tid: int, reply_id, trace: list):
    """A general turn's tool calls and thinking, filed under the reply they led to (general.send_prompt)."""
    steps = []
    for e in trace or []:
        k, name, d = e.get('type'), e.get('name'), e.get('detail')
        if k == 'tool_call': steps.append(_tool(name, (d or {}).get('args') if isinstance(d, dict) else d))
        elif k == 'progress' and name in ('thinking', 'reasoning') and str(d or '').strip(): steps.append({'k': 'thought', 'text': _cut(d, THOUGHT_N)})
        elif k == 'progress' and name in ('text', 'agent_message') and str(d or '').strip(): steps.append({'k': 'said', 'text': _cut(d, SAID_N)})
        elif k == 'tool_result' and isinstance(d, dict) and d.get('is_error'): steps.append({'k': 'error', 'text': _cut(d.get('result'), 400)})
        elif k == 'error': steps.append({'k': 'error', 'text': _cut((d or {}).get('result') if isinstance(d, dict) else d, 400)})
    if not steps: return
    with _gen_path(tid).open('a', encoding='utf-8') as f: f.write(json.dumps({'reply': reply_id, 'steps': steps}) + '\n')


# TASKUARY'S INSTRUCTIONS ARE NOT THE OWNER'S WORDS (the owner, 2026-10-30): a coding agent's log has the prompt Taskuary typed into it
# as the first user turn, and the record showed it as "Told" beside what the owner typed into the pane. Each seed is kept here as it
# was sent (terminal.spawn), and a told step that IS one is a `brief` - drawn as one folded line, "Taskuary's instructions".
SEED_N = 160            # a typed seed is flattened and may be clipped (terminal.fit_typed): its head is what both copies share

def _seeds_path(tid: int) -> Path:
    d = session_artifacts.root() / str(int(tid)); d.mkdir(parents=True, exist_ok=True)
    return d / 'seeds.jsonl'


def _flat(s) -> str: return ' '.join(str(s or '').split()).removesuffix('…')


def keep_seed(tid: int, seed: str):
    try:
        with _seeds_path(tid).open('a', encoding='utf-8') as f: f.write(json.dumps({'seed': _flat(seed)[:SEED_N]}) + '\n')
    except OSError as e: logger.warning(f'the seed of task {tid} was not kept: {e}')


def mark_briefs(tid: int, steps: list) -> list:
    "The told steps that are a seed Taskuary sent, as `brief`."
    p = _seeds_path(tid)
    if not p.is_file(): return steps
    seeds = set()
    for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
        try: seeds.add(json.loads(line).get('seed') or '')
        except ValueError: continue
    def ours(x): a = _flat(x.get('text'))[:SEED_N]; return any(s and a and (s.startswith(a) or a.startswith(s)) and min(len(a), len(s)) >= 20 for s in seeds)
    return [{**x, 'k': 'brief'} if x.get('k') == 'you' and ours(x) else x for x in steps]


def general_steps(store, tid: int) -> list:
    from .general import ASSISTANT_TYPE, chat_rows, is_brief
    p, by = _gen_path(tid), {}
    if p.is_file():
        for line in p.read_text(encoding='utf-8', errors='replace').splitlines():
            try: j = json.loads(line); by.setdefault(j.get('reply'), []).extend(j.get('steps') or [])
            except ValueError: continue
    # TASKUARY'S OWN NOTES IN THE CHAT ARE NOT THE AGENT'S WORDS (the owner, 2026-10-27, a finished agent's Result read "You replied in WhatsApp
    # on TQ-n ... I removed the unused draft"): a receipt or a note Taskuary files there (channels, the Advisor) is a `note` step, never the
    # said step its last words are read from. One by its actor (NOTE_ACTOR); one written before that, by having no agent turn filed with it -
    # each turn's reply is audited the moment it is written (general.send_prompt) - where the task has any such audit to go by
    turns = [_when(a.get('CreatedAt')) for a in store._rows("SELECT CreatedAt FROM audit WHERE EntityType='task' AND EntityId=? AND Action='assistant_reply'", (int(tid),))]
    def turn(c) -> bool:
        if c.get('Actor') == NOTE_ACTOR: return False
        if not turns: return True
        at = _when(c.get('CreatedAt'))
        try: t0 = datetime.strptime(at, '%Y-%m-%d %H:%M:%S')
        except ValueError: return True
        return any(0 <= (datetime.strptime(t, '%Y-%m-%d %H:%M:%S') - t0).total_seconds() <= 5 for t in turns if len(t) == 19)
    out = []
    for c in chat_rows(store, tid):
        mine = c.get('ActorType') == ASSISTANT_TYPE
        # a turn's own working comes BEFORE its reply - and the reply is the said step, so a streamed copy of it is not said twice
        if mine: out += [s for s in by.get(c['CommentId'], []) if not (s['k'] == 'said' and s['text'].strip() == str(c.get('Body') or '').strip())]
        out.append({'k': ('said' if turn(c) else 'note') if mine else 'brief' if is_brief(c) else 'you', 'text': _cut(c.get('Body'), SAID_N if mine else YOU_N), 'at': c.get('CreatedAt')})
    return out


# ── the record ───────────────────────────────────────────────────────────────────────────
def _saved_path(tid: int, sid: str) -> Path:
    d = session_artifacts.root() / str(int(tid)); d.mkdir(parents=True, exist_ok=True)
    return d / f"record-{re.sub(r'[^A-Za-z0-9._-]+', '-', str(sid))[:80]}.json"


def save(store, tid: int, sid: str, cli: str, ext: str, screen: str = '', started: str = '') -> dict:
    """Snapshot a session's steps beside the task (wrapup.wrap), so the record outlives the CLI's own log - with how long the run
    took and what it cost, where its start is known (`started`, local) and its CLI counts."""
    steps, source = cli_steps(cli, ext)
    steps = mark_briefs(tid, steps)
    if not steps: steps, source = screen_steps(screen), 'screen'
    rec = {'sid': sid, 'cli': cli, 'ext': ext, 'source': source, 'steps': _bound(steps)}
    if (secs := took(steps, _when(started), datetime.now().strftime('%Y-%m-%d %H:%M:%S'))) is not None: rec['took'] = secs
    if started and (use := cli_usage(cli, ext, _when(started))): rec['usage'] = use
    try: _saved_path(tid, sid).write_text(json.dumps(rec), encoding='utf-8')
    except OSError as e: logger.warning(f'session record for task {tid} not kept: {e}')
    return rec


def _bound(steps: list) -> list:
    if len(steps) <= MAX_STEPS: return steps
    keep = MAX_STEPS // 4
    return steps[:keep] + [{'k': 'gap', 'text': f'{len(steps) - MAX_STEPS} steps in the middle are not kept'}] + steps[-(MAX_STEPS - keep):]


def summarise(steps: list) -> dict:
    """What the steps add up to: the files it wrote, its last plan, how much it thought, did and said."""
    files = list(dict.fromkeys(s['file'] for s in steps if s.get('file')))
    plan = next((s['items'] for s in reversed(steps) if s['k'] == 'plan'), [])
    n = lambda k: sum(s['k'] == k for s in steps)
    return {'files': files, 'plan': plan, 'counts': {'thought': n('thought'), 'tool': n('tool'), 'said': n('said'), 'you': n('you')}}


_REPORT = re.compile(r'^(Determination|Actions|Summary):[ \t]*', re.M)


def parse_report(body: str) -> dict:
    """An AGENT REPORT comment (CODER REPORT on older rows), back into its parts: decided / changed / summary, and the session's LAST MESSAGE.
    A general chat's note is its last answer and nothing else, so it is all `last`."""
    rep, _, last = re.sub(r'^(AGENT REPORT|CODER REPORT|HANDOVER NOTE)\n?', '', str(body or '')).strip().partition('\n\nLAST MESSAGE\n')
    parts = _REPORT.split(rep)
    if len(parts) < 3: return {'last': (last or rep).strip()}
    f = dict(zip(parts[1::2], (x.strip() for x in parts[2::2])))
    return {'decided': f.get('Determination', ''), 'changed': f.get('Actions', ''), 'summary': f.get('Summary', ''), 'last': last.strip()}


def _when(s) -> str: return str(s or '').replace('T', ' ')[:19]


def _local(at) -> str:
    """A step's time as the store writes one (local, 'YYYY-MM-DD HH:MM:SS'): a CLI log stamps UTC ('...Z')."""
    s = str(at or '')
    if not re.search(r'(Z|[+-]\d\d:?\d\d)$', s): return _when(s)
    try: return datetime.fromisoformat(s.replace('Z', '+00:00')).astimezone().strftime('%Y-%m-%d %H:%M:%S')
    except ValueError: return _when(s)


def _keeps_last(s: dict, rep: dict) -> bool:
    """A second write-up of a session nothing has happened in since the first is a RE-WRAP - the same transcript read again
    with no agent left to speak - so it may not replace the agent's last message: an upstream ending filed its own sentence
    there, and the card swapped the agent's account of its merge for "was merged on GitHub" (2026-10-12)."""
    prev = s.get('report') or {}
    if not prev.get('last') or prev.get('last') == rep.get('last'): return False
    times = [_local(x['at']) for x in s['steps'] if x.get('at')]
    return bool(times) and max(times) <= _when(prev.get('at'))


def _nearest(sessions: list, at: str):
    """Which session a note belongs to: the first that ended at or after it (a report is written, then the pty closes),
    else the last one before it (a session wrapped up from its filed transcript, after the pane had gone)."""
    at = _when(at)
    return next((s for s in sessions if s['at'] >= at[:16]), None) or (sessions[-1] if sessions else None)


def record(store, tid: int) -> dict:
    """Every session this task has had, oldest first, each in the one shape the Agent work card draws:
    who ran it, its result, what it decided and changed, its plan, the files it wrote, and every step."""
    from . import general
    rows = store._rows('SELECT * FROM transcript WHERE TaskId=? ORDER BY TranscriptId', (int(tid),))
    sessions = []
    for r in rows:
        saved = _saved_path(tid, r.get('Sid') or '')
        rec = json.loads(saved.read_text(encoding='utf-8')) if saved.is_file() else None
        if not rec:
            steps, source = cli_steps(r.get('Brain'), r.get('ExtId'))
            steps = mark_briefs(tid, steps)
            rec = {'steps': _bound(steps), 'source': source} if steps else {'steps': screen_steps(r.get('Text')), 'source': 'screen'}
        sessions.append({'sid': r.get('Sid'), 'by': r.get('Agent') or 'agent', 'cli': r.get('Brain') or '', 'cwd': r.get('Cwd') or '',
                         'at': _when(r.get('CreatedAt')), 'source': rec.get('source') or '', 'steps': rec.get('steps') or [],
                         **{k: rec[k] for k in ('took', 'usage') if rec.get(k) is not None}})
    chat = general.chat_rows(store, tid)
    if chat and any(c.get('ActorType') == general.ASSISTANT_TYPE for c in chat):
        turns = []
        for a in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action='assistant_reply' ORDER BY Id", (int(tid),)):
            try: turns.append(json.loads(a.get('Detail') or '{}'))
            except ValueError: continue
        ran = turns[-1] if turns else {}
        # the conversation's time is its turns' own, summed: the gaps between them are the owner's
        spent = sum(int(x['took']) for x in turns if isinstance(x.get('took'), (int, float)))
        sessions.append({'sid': 'general', 'by': 'assistant', 'cli': ' · '.join(x for x in (ran.get('provider'), ran.get('model')) if x) or 'assistant', 'cwd': '',
                         'at': _when(chat[-1].get('CreatedAt')), 'source': 'conversation', 'steps': general_steps(store, tid),
                         **({'took': spent} if spent else {})})
    sessions.sort(key=lambda s: s['at'])
    for c in store.list_comments(tid):
        if str(c.get('Body') or '').startswith(REPORTS) and (s := _nearest(sessions, c.get('CreatedAt'))):
            rep = parse_report(c['Body'])
            if _keeps_last(s, rep): rep['last'] = s['report']['last']
            s['report'] = rep | {'by': c.get('Actor') or '', 'at': _when(c.get('CreatedAt'))}
    arts = store.list_task_artifacts(tid)
    for a in sorted((a for a in arts if a.get('Kind') == 'agent_result'), key=lambda a: str(a.get('CreatedAt') or '')):
        p = session_artifacts.confined(a.get('Path'))
        if p and (s := _nearest(sessions, a.get('CreatedAt'))):
            s['answer'] = re.sub(r'^# .*\n+', '', p.read_text(encoding='utf-8'), count=1).strip()
    # what the floor refused a stranger's session (floor.py): the agent carries on, so the worker state never shows it -
    # without this the owner saw a refusal only if the pane was open when it happened
    refused = {}
    for e in store.worker_events(int(tid)):
        if e['Kind'] == 'floor_denied': refused.setdefault(str(e['Sid']), []).append({'text': e['Text'] or '', 'at': _when(e['CreatedAt'])})
    ext = {r.get('Sid'): r.get('ExtId') for r in rows}     # a headless run's events carry the CLI's id (hooks.run_sid)
    for s in sessions:
        if (got := refused.get(str(s['sid'])) or refused.get(str(ext.get(s['sid']) or ''))): s['refused'] = got
        rep = s.get('report') or {}
        said = next((x['text'] for x in reversed(s['steps']) if x['k'] == 'said'), '')
        # THE RESULT IS ONE THING, the fullest account the session left, shown once: the answer it saved, else its last
        # message, else the last thing its own log has it saying - the agent's words beat a second model's 55-word summary,
        # which stays in the full record as the summary it is
        s['result'] = s.get('answer') or rep.get('last') or said or rep.get('summary') or ''
        s.update(summarise(s['steps']))
    # ...and what ended it upstream (a merge, a close), as a status line ADDED to the record, never in place of it
    from .channels import ended_line
    return {'sessions': sessions[::-1], 'ended': ended_line(store, tid)}
