"""A TASK'S CHAT IS ONE LIST, AND THE SERVER OWNS IT (the owner, 2026-11-11: "this needs a rebuild with one pass robust code, with shared
code for general and coding agents ... just make it general how a chat works"). `items(store, tid)` is that list for every kind of task and
every road an agent runs on; the page draws it and decides nothing.

THE HEARD RULE ("where the agent listens to it is where it shows on the canvas"). Every input - a line he typed, a press, a message that came
in on the task - is PENDING (accepted, not yet handed to the agent) or HEARD. Heard is a fact written at the hand-over, by the one function
every road calls (`hear`): a row of the `heard` ledger, once per input (its UNIQUE key is what makes "told twice" impossible). A heard input
stands in the list at the moment it was heard - the agent's work before it above, its work after it below; a pending one is in `pending`,
drawn by the box, and moves once. An input no ledger row names (a task from before the ledger, a message on a task no agent works) stands at
its own time, after the turn it came in under - never inside one.

One item: {id, kind, at, ...}
  arrival  m:<MessageId>            who, channel, words, files, own (his own reply on the channel)
  line     <the page's LineId> | c:<CommentId>      text, files
  press    p:<audit id>             text - his press, in his voice (general.PRESSES)
  note     n:<...>                  text - one quiet sentence
  turn     t:<the input before it>:<n>   state starting|working|done|stopped|failed, steps, text, cards (last), started, ended, fail
  card     r:<ReviewId>             an action outside any turn
Ids never change once given, so the page keys by them and a turn that ends, or a line that is heard, redraws in place."""
import functools, hashlib, json, math, re, threading, time
from datetime import datetime
from pathlib import Path

INF = float('inf')


def ep(at) -> float:
    "A stamp as epoch seconds: the store's local 'YYYY-MM-DD HH:MM:SS', a CLI log's ISO with its zone, or a number already."
    if isinstance(at, (int, float)): return float(at)
    s = str(at or '').strip()
    if not s: return 0.
    try: return datetime.fromisoformat(s.replace('Z', '+00:00').replace(' ', 'T', 1)).timestamp()
    except ValueError: return 0.
def stamp(ts) -> str: return datetime.fromtimestamp(ts).isoformat(sep=' ', timespec='seconds') if ts and ts < INF else ''
def _flat(s) -> str: return ' '.join(str(s or '').split())


# ...each text cleaned once (a long session's every step was cleaned again on every poll - seconds a call): the words decide it alone
@functools.lru_cache(maxsize=50000)
def _clean(t: str) -> str: return _cleaned(t)
def clean(text) -> str: return _clean(str(text or ''))


def _cleaned(text) -> str:
    """THE AGENT'S WORDS, WITHOUT WHAT IT WROTE FOR THE APP - one function for every road's turn (a chat's answer, a quick answer, a coding
    session's words, the turn at work): the summary block it is asked to end on (selfclose.SUMMARY_OPEN), closed or not - an opening marker
    with no close goes to the end of the text - and the marker of a question. A turn that said nothing but the block says the block's own
    sentence, once."""
    from .selfclose import asked_inline, signin_marker, turn_marker, without_summary
    # ...and the sign-in's and the hand-over's markers, which the app acts on and never draws (the recorded coding walk, 2026-11-12: a coding
    # turn's words over ACP and in the terminal drew "[[TASKUARY-SIGNIN: localhost:18451]]" in the chat)
    t = str(text or ''); out = asked_inline(turn_marker(signin_marker(without_summary(t))[0])[0])[0].strip()
    if out or not t.strip(): return out
    try: j = json.loads(t[t.index('{'):t.rindex('}') + 1])
    except ValueError: return ''
    return str(j.get('did') or j.get('about') or '').strip() if isinstance(j, dict) else ''
# ...A CLI'S OWN PLUMBING IS NO STEP, by the one list the page reads too (the walks, 2026-11-17: a stopped turn whose only step was ToolSearch
# was kept here for that step and drawn as nothing there - a "1 step" trail for 100 ms, then head and trail gone)
_KINDS = json.loads(Path(__file__).with_name('stepkinds.json').read_text(encoding='utf-8'))
MACHINERY, _OWN_LINE = frozenset(_KINDS['machinery']), re.compile(_KINDS['commands'], re.I)
def machinery(s: dict) -> bool:
    a = s.get('args') if isinstance(s.get('args'), dict) else {}
    return s.get('k') == 'tool' and (re.sub(r'[^a-z0-9]', '', str(s.get('name') or '').split('__')[-1].lower()) in MACHINERY
                                     or bool(_OWN_LINE.search(str(a.get('command') or a.get('cmd') or ''))))


def _said(steps: list, body: str = '') -> list:
    "A turn's steps with its words cleaned (clean) - and a step that says only what the turn's answer says, or nothing, or is machinery, left out."
    from .chatformat import plain_text
    out = []
    for s in steps:
        if machinery(s): continue
        # ...a thought is one plain row: the same cleaner, and its markup said as words ("**Replacing the pending draft**" stood raw)
        if s.get('k') == 'thought' and (w := plain_text(clean(s.get('text'))) or clean(s.get('text'))): out.append({**s, 'text': w}); continue
        if s.get('k') != 'said': out.append(s); continue
        w = clean(s.get('text'))
        if w and w != body.strip(): out.append({**s, 'text': w})
    return out


# ── the ledger ───────────────────────────────────────────────────────────────────────────────────
def _mail(store, tid: int) -> list:
    "Every message on the task's thread the chat draws (general.JOINED, and his own lines filed elsewhere), each with `T`: when it joined."
    from . import general
    rows = [*store._rows(general.JOINED, (tid,)), *general.room_own(store, tid)]
    return sorted(({**x, 'T': ep((x.get('SentAt') if x.get('Own') else None) or x.get('JoinedAt') or x.get('CreatedAt'))} for x in rows),
                  key=lambda x: (x['T'], x['MessageId']))


def _since(store, tid: int) -> float:
    """From when the ledger answers for this task: its FIRST row, else (a task from before it) its last answer or session. Everything that
    came in or was pressed from then on is in the ledger or still unheard - so a hand-over takes ALL of it, whatever was heard a moment
    before (the recorded flood, 2026-11-11: the lines' own hear, a millisecond earlier, made ten waiting mails "older than the last hand-over";
    they were never heard, entered above the turn that was at work, and got a turn of their own)."""
    r = store._one('SELECT MIN(At) AS a FROM heard WHERE TaskId=?', (tid,))
    if r and r['a']: return r['a']
    from .general import ASSISTANT_TYPE
    c = store._one('SELECT MAX(CreatedAt) AS a FROM comment WHERE TaskId=? AND ActorType=?', (tid, ASSISTANT_TYPE))
    s = store._one('SELECT MAX(CreatedAt) AS a FROM transcript WHERE TaskId=?', (tid,))
    return max(ep((c or {}).get('a')), ep((s or {}).get('a')))


def _after(body) -> float:
    "The newest message the store held when a kept line was typed (general.wait_line) - a line from before that was written is after all of its second."
    try: return float(json.loads(body or '{}').get('after'))
    except (ValueError, TypeError, AttributeError): return INF
def came(x: dict) -> tuple:
    """WHEN AN INPUT CAME - one key for a message and a line of his alike: its second (a stamp is no finer), then inside it the order the store
    took them in - a message by its id, a line after the newest message there when it was typed (_after). A message by when it CAME - the
    store took it, or he sent his own - never its sender's clock, nor when triage put it here, which a flood finishes out of order."""
    if 'MessageId' in x: return (int(ep((x.get('SentAt') if x.get('Own') else None) or x.get('CreatedAt')) or x.get('T') or 0), x['MessageId'], 0, x['MessageId'])
    return (int(ep(x.get('CreatedAt'))), _after(x.get('Body')), 1, x['CommentId'])


def hear(store, tid: int, lines=(), turn: bool = False, sid: str = '', standing: bool = False) -> int:
    """THE ONE HAND-OVER. Called ONCE at the moment a road gives the agent its input: `lines` - his lines it takes now, as they waited
    (store.take_lines' rows), or the name (LineId) of one sent this moment; `turn` - a turn begins, and with it the agent is told everything
    that came in or was pressed since its last one (general.turn_facts), so those are heard here too, and the turn's own start is marked.
    `standing`: a line that begins a turn at the press - what already stood in the chat unheard is heard with it, before it, so nothing
    drawn moves under his line. Each input once, whoever calls and however often. -> how many were new.
    WHAT ONE HAND-OVER TAKES STANDS IN THE ORDER IT CAME (the recorded flood, 2026-11-11: his lines were written down first, then his own
    replies, then the sender's mail in the order triage got through them - "34, 31, 46"): by each one's own time, and inside one second - a
    stamp is no finer - by the order the store took them in: a line knows the newest message that was there when it was typed (came).
    ...AND NEVER ABOVE WHAT WAS DRAWN: what was on the task before his oldest waiting line was typed stood in the chat already - from that
    line on, what comes in waits by the box with it (items) - so those keep the order they stood in, ahead of the rest."""
    from . import general
    tid, now = int(tid), time.time()
    rows = [x for x in lines if isinstance(x, dict)]
    first = min((_after(x.get('Body')) for x in rows), default=INF)
    # (where, kind, name) - where: (0, when it joined, id) it stood drawn | (1, its second, the newest message before it, kind, place) | (2, n) sent now
    refs = []
    if turn or standing:
        since = _since(store, tid) - 1
        # ...a mail by when it CAME (came): a mail held up on its way was placed by its Date, above the line he typed before it came
        refs += [((0, x['T'], x['MessageId']) if x['MessageId'] <= first else (1, *came(x)), 'mail', str(x['MessageId'])) for x in _mail(store, tid) if x['T'] >= since]
        # ...a press stands where he made it (his stop is drawn the moment it is pressed): the lines that waited enter under it
        refs += [((0, ep(p[1]), i), 'press', str(p[0])) for i, p in enumerate(general.presses(store, tid)) if ep(p[1]) >= since]
    refs += [((1, *came(x)), 'line', str(x.get('LineId') or '')) if isinstance(x, dict) else ((2, i), 'line', str(x))
             for i, x in enumerate(lines) if x]
    refs = [(k, r) for _, k, r in sorted(refs, key=lambda x: x[0]) if r]
    if turn: refs.append(('turn', str(time.time_ns())))
    if not refs: return 0
    n = 0
    with store.lock:
        seq = (store.cx.execute('SELECT MAX(CommentId) AS m FROM comment WHERE TaskId=?', (tid,)).fetchone()['m'] or 0)
        grp = (store.cx.execute('SELECT MAX(HId) AS m FROM heard').fetchone()['m'] or 0) + 1
        new = []
        for k, r in refs:
            if (c := store.cx.execute('INSERT OR IGNORE INTO heard (TaskId,Kind,Ref,At,Grp,Seq,Sid) VALUES (?,?,?,?,?,?,?)', (tid, k, r, now, grp, seq, sid or '')).rowcount): new.append((k, r))
            n += c
        store.cx.commit()
    # ...a line of his, or a message, heard is the conversation moving past any reply draft that waited above it (proposals.set_aside_drafts):
    # the turn that hears it drafts again under it where a reply is still owed (the rail walk, 2026-11-12: the sender wrote again, and the
    # draft to refresh stood above her new mail)
    # ...a draft written after that message is its answer, never set aside by it: older than the input, by the input's own time
    # ...and a letter Taskuary sent on his press, come back from his Sent folder, is no input at all (the owner, 2026-11-13: two letters
    # waited, he sent one, and its copy coming back set the other aside - "how am i supposed to send 2 messages then")
    mine = general.went_from_here(store, tid)
    joined = {str(x['MessageId']): x['T'] for x in _mail(store, tid) if not (x.get('Own') and mine(x))} if any(k == 'mail' for k, _ in new) else {}
    if (at := max([now for k, _ in new if k == 'line'] + [joined.get(r, 0) for k, r in new if k == 'mail'], default=0)):
        from . import proposals
        proposals.set_aside_drafts(store, tid, at, actions=now if any(k == 'line' for k, _ in new) else 0)
    if n: store._poke('task-changed', task_id=tid)
    return n


def heard(store, tid: int, kind: str, refs) -> bool:
    "Has the agent been handed every one of these (`refs` of one kind) already?"
    refs = list({str(r) for r in refs or [] if r})
    return bool(refs) and store._one(f"SELECT COUNT(*) AS n FROM heard WHERE TaskId=? AND Kind=? AND Ref IN ({','.join('?' * len(refs))})", (int(tid), kind, *refs))['n'] == len(refs)


def with_turn(store, tid: int) -> list:
    """The messages (ids) the turn that just began heard: everything heard since the turn before it began. [] for a task's first turn - its
    prompt carries the thread. What `hear` writes down as heard, the turn's own words must carry (general.came_in): never heard and not told."""
    m = store._rows("SELECT HId FROM heard WHERE TaskId=? AND Kind='turn' ORDER BY HId DESC LIMIT 2", (int(tid),))
    if len(m) < 2: return []
    return [int(r['Ref']) for r in store._rows("SELECT Ref FROM heard WHERE TaskId=? AND Kind='mail' AND HId>? AND HId<? ORDER BY HId", (int(tid), m[1]['HId'], m[0]['HId']))]


def unheard(store, tid: int) -> set:
    """The messages (ids) on the task that came in after the newest turn began and no hand-over took: the NEXT turn's to hear, so nothing a
    turn is told names them (general.newest_message) - told there and again when heard, an input reached the agent twice."""
    m = store._one("SELECT MAX(At) AS a FROM heard WHERE TaskId=? AND Kind='turn'", (int(tid),))
    if not (m and m['a']): return set()
    led = {r['Ref'] for r in store._rows("SELECT Ref FROM heard WHERE TaskId=? AND Kind='mail'", (int(tid),))}
    return {x['MessageId'] for x in _mail(store, tid) if str(x['MessageId']) not in led and x['T'] + 1 > m['a']}


START_BY_WRITING = 'Write to the agent below and it starts.'
# ...AND A LINE THAT CANNOT REACH THE TURN AT WORK SAYS SO (design round 3, 2026-11-18: "sign up yourself" sat 13 minutes behind a turn, unsaid)
LATER = 'This agent takes no words while it works - it reads this when its turn ends.'
TOOK_BACK = 'Asked for the sign-in details, then took that back: a sign-in is done on the page, never in the chat.'
def take_back(store, tid: int, said: str = None, why: str = '', since: float = 0., ahead: bool = False) -> None:
    """AN ANSWER THAT WAS ONLY A STEP ON THE WAY IS A STEP OF THE WORK, NEVER AN ANSWER (the recorded sign-in walks, 2026-11-11): one its agent
    is made to take back - it asked him for the password, was woken to open the sign-in page instead, and the ask stood in the chat above the
    page it opened - and one that only handed Taskuary a sign-in the saved one then did ("once you have signed in..." over a sign-in nobody
    was asked for; `why`: the line that says what happened instead, `since`: only an answer filed from then on). Marked by the answer's own
    row - or, read before that row is filed, as the next answer after the newest row - and drawn by `items` as that turn's work with one
    line in place of the words, the turn that goes on under it.
    `ahead`: the answer filed from `since` on is taken back even where it is not filed yet (the next one to be), and a later call says how
    it ended in the same line - a saved sign-in takes seconds to type, and all that time the answer that only handed it over stood in the
    chat as the agent's answer ("I have no saved sign-in for it ...", recorded 2026-11-14)."""
    from .general import ASSISTANT_TYPE
    rows = store.list_comments(int(tid), internal=True)
    c = next((c for c in reversed(rows) if c.get('ActorType') == ASSISTANT_TYPE), None)
    nxt = f">{max((r['CommentId'] for r in rows), default=0)}"
    if said is None:
        filed = bool(c) and ep(c['CreatedAt']) >= since - 1
        if not filed and not ahead: return
        ref = str(c['CommentId']) if filed else nxt
    else: ref = str(c['CommentId']) if c and str(c.get('Body') or '')[:4000] == said[:4000] else nxt
    store._exec('INSERT OR IGNORE INTO heard (TaskId,Kind,Ref,At,Grp,Seq,Sid) VALUES (?,?,?,?,?,?,?)', (int(tid), 'back', ref, time.time(), 0, 0, why))
    if ahead and why: store._exec("UPDATE heard SET Sid=? WHERE TaskId=? AND Kind='back' AND (Ref=? OR (Ref LIKE '>%' AND At>=?))", (why, int(tid), ref, since - 1))
    store._poke('task-changed', task_id=int(tid))


def hear_press(store, tid: int, action: str) -> None:
    """A PRESS ITS AGENT HEARS THE MOMENT IT IS MADE - his answer to a call the turn is stopped at (permissions.ask): heard there, so it
    stands where he pressed with the turn going on under it. Left for the next hand-over, it waited by the box while the turn it had just
    let go worked on, and then entered above work already drawn (the recorded hold, 2026-11-11)."""
    r = store._one("SELECT MAX(Id) AS i FROM audit WHERE EntityType='task' AND EntityId=? AND Action=?", (int(tid), action))
    if not (r and r['i']): return
    store._exec('INSERT OR IGNORE INTO heard (TaskId,Kind,Ref,At,Grp,Seq,Sid) VALUES (?,?,?,?,?,?,?)', (int(tid), 'press', str(r['i']), time.time(), 0, 0, ''))
    store._poke('task-changed', task_id=int(tid))


def handed_since(store, tid: int, at) -> bool:
    "Was anything handed to the agent - a line of his, a turn's start - more than a second after `at`: what a session gone since never answered."
    r = store._one("SELECT MAX(At) AS a FROM heard WHERE TaskId=? AND Kind IN ('line','turn')", (int(tid),))
    return bool(r and r['a'] and r['a'] > ep(at) + 1)


def unhear(store, tid: int, lines) -> None:
    "A start that was refused took nothing: its lines are pending again (general._start_line), never drawn as heard by nobody."
    for x in lines or []: store._exec("DELETE FROM heard WHERE TaskId=? AND Kind='line' AND Ref=?", (int(tid), str(x)))


def counts(store, tid: int) -> dict:
    "The flood's check: how many of each kind the agent heard, and how many of his lines still wait."
    from .general import WAITING_TYPE
    by = {r['Kind']: r['n'] for r in store._rows('SELECT Kind, COUNT(*) AS n FROM heard WHERE TaskId=? GROUP BY Kind', (int(tid),))}
    led = {r['Ref'] for r in store._rows("SELECT Ref FROM heard WHERE TaskId=? AND Kind='line'", (int(tid),))}
    kept = [c for c in store.list_comments(int(tid), internal=True) if c.get('ActorType') == WAITING_TYPE]
    return {**by, 'pending': sum((c.get('LineId') or '') not in led for c in kept)}


# ── an ACP session's updates -> the log's step shape (one shape for every road) ─────────────────────
_ACP_TOOL = {'read': 'Read', 'edit': 'Edit', 'delete': 'Delete', 'move': 'Move', 'search': 'Grep', 'execute': 'Bash', 'fetch': 'WebFetch', 'think': 'Think'}
_ARGS = ('command', 'cmd', 'pattern', 'query', 'url', 'file_path', 'path', 'filePath', 'absolute_path', 'description', 'prompt', 'glob', 'title', 'subagent_type', 'agentPath')
_PATHS = ('path', 'file_path', 'filePath', 'absolute_path')
def _text(c) -> str:
    if isinstance(c, str): return c
    if isinstance(c, list): return ''.join(map(_text, c))
    if isinstance(c, dict): return c.get('text') or '' if c.get('type') == 'text' else _text(c['content']) if c.get('content') else ''
    return ''
def _unfence(s: str) -> str:
    s = str(s or ''); b = s.strip()
    return b.split('\n', 1)[1].rsplit('```', 1)[0].rstrip('\n') if b.startswith('```') and b.endswith('```') and '\n' in b else s
def _out(u) -> str:
    got = '\n'.join(_unfence(_text(c.get('content'))) for c in u.get('content') or [] if isinstance(c, dict) and c.get('type') == 'content')
    raw = u.get('rawOutput')
    return got or (raw if isinstance(raw, str) else next((raw[k] for k in ('formatted_output', 'output', 'stdout') if raw.get(k)), '') if isinstance(raw, dict) else '')
def _meta(u, *ks):
    m = u.get('_meta') or {}
    for k in ks: m = m.get(k) if isinstance(m, dict) else None
    return m


def acp_steps(updates: list) -> list:
    "An ACP session's kept updates (codingchat.record_update) as steps - {k, text|name+args, at} - with each step's place (`n`) and its `line`."
    out, by, compacts = [], {}, {}
    def chunk(k, t, at, **x):
        if not t: return
        # ...ONE MESSAGE IS ONE STEP: the adapter names the message each chunk is of (`messageId`), and two messages said back to back in one
        # turn ran together as one sentence (the recorded walk, 2026-11-11: '...`plus tax`."""The reply to Gail went out')
        if out and out[-1]['k'] == k and out[-1].get('open') and not x.get('line') and not out[-1].get('line') and out[-1].get('mid') == x.get('mid'): out[-1]['text'] += t
        else: out.append({'k': k, 'text': t, 'open': True, 'at': at, **x})
    for u in updates or []:
        n0 = len(out)
        kind, at = u.get('sessionUpdate'), u.get('_at') or ''
        said = {'mid': u['messageId']} if u.get('messageId') else {}
        if kind == 'user_message_chunk':
            who = _meta(u, 'taskuary')
            chunk('said' if who == 'agent' else 'brief' if who == 'brief' else 'you', _text(u.get('content')), at, **({'line': l} if (l := _meta(u, 'line')) else {}))
        elif kind == 'agent_message_chunk': chunk('said', _text(u.get('content')), at, **said)
        elif kind == 'agent_thought_chunk': chunk('thought', _text(u.get('content')), at, **said)
        elif kind == 'error' and _meta(u, 'taskuary') == 'error': out.append({'k': 'error', 'text': _text(u.get('content')), 'at': at})
        elif kind == 'compaction_update' or (kind in ('tool_call', 'tool_call_update') and (_meta(u, 'claudeCode', 'toolName') == 'compact' or str(u.get('toolCallId')) in compacts)):
            cid = str(u.get('compactionId') if kind == 'compaction_update' else u.get('toolCallId'))
            if cid not in compacts: compacts[cid] = {'k': 'compact', 'id': cid, 'at': at}; out.append(compacts[cid])
            if u.get('status'): compacts[cid]['status'] = u['status']
        elif kind == 'plan': out.append({'k': 'plan', 'at': at, 'items': [{'text': str(e.get('content') or ''), 'status': e.get('status') or 'pending'} for e in u.get('entries') or [] if isinstance(e, dict)]})
        elif kind in ('tool_call', 'tool_call_update'):
            s = by.get(u.get('toolCallId'))
            if not s:
                if kind == 'tool_call_update' and not (u.get('rawInput') or u.get('title') or u.get('kind')): continue
                s = by[u.get('toolCallId')] = {'k': 'tool', 'id': str(u.get('toolCallId') or ''), 'at': at, 'args': {},
                                               'name': _meta(u, 'claudeCode', 'toolName') or _ACP_TOOL.get(u.get('kind')) or u.get('title') or u.get('kind') or 'tool'}
                out.append(s)
            if (par := _meta(u, 'claudeCode', 'parentToolUseId') or _meta(u, 'parentToolUseId') or _meta(u, 'parentToolCallId')): s['parent'] = str(par)
            if isinstance(u.get('rawInput'), dict): s['args'].update({k: v for k, v in u['rawInput'].items() if k in _ARGS and isinstance(v, str) and v.strip()})
            if u.get('status'): s['status'] = u['status']
            if (d := _meta(u, 'terminal_output_delta', 'data')): s['out'] = s.get('out', '') + d
            elif not s.get('out') and u.get('status') in ('completed', 'failed') and (o := _out(u)): s['output'] = o
            loc = next((l['path'] for l in u.get('locations') or [] if isinstance(l, dict) and l.get('path')), '')
            if loc and not any(s['args'].get(k) for k in _PATHS): s['args']['file_path'] = loc
            if (diffs := [c for c in u.get('content') or [] if isinstance(c, dict) and c.get('type') == 'diff']):
                s['edit'] = {'whole': True, 'parts': [{'old': d.get('oldText') or '', 'new': d.get('newText') or ''} for d in diffs]}; s['file'] = diffs[0].get('path') or loc
        # ...each new step keeps its update's exact clock (`_t`, record_update): a stamp to the millisecond put the words said right after his
        # press, in the press's own millisecond, ABOVE it - the ledger's hand-over time is finer (a CI runner, 2026-11-12)
        if u.get('_t'): [x.setdefault('_t', u['_t']) for x in out[n0:]]
    for s in out: s.pop('open', None); s.pop('mid', None)
    return out


# ── the list ─────────────────────────────────────────────────────────────────────────────────────
def _session_steps(store, tid: int) -> list:
    "Every coding session of the task, oldest first: (sid, live, its steps in the one shape, each with `T`)."
    from . import codingchat, permissions
    out, asked = [], permissions.calls(store, tid)
    for s in codingchat.owned(store, tid, codingchat.sessions(store, tid, local=False)):
        steps, t = acp_steps(s['updates']) if s.get('source') == 'acp' else [dict(x) for x in s.get('steps') or []], ep(s.get('at'))
        # ...a call put to the owner reads as he left it: waiting on him, or never run - never "Deleted ledger-archive" (permissions.calls)
        for x in steps:
            if x.get('k') == 'tool' and x.get('status') != 'completed' and (was := asked.get(str(x.get('id') or ''))): x['status'] = was
        # ...A SESSION'S `at` IS ITS START WHILE IT LIVES AND ITS END ONCE IT CLOSED (the filing of its transcript): read from there, every
        # step of a closed session stood at its close - his lines first, then all its turns (recorded 2026-11-12, a coding task opened
        # again after Send and close). Never later than its own first dated step
        t = min(t, min((ep(x['at']) for x in steps if x.get('at')), default=t))
        for x in steps: t = x['T'] = max(t, x.pop('_t', None) or ep(x.get('at')))          # a record reads in its own order: a step with no time is at the one before it
        out.append((s['sid'], bool(s.get('live')), steps))
    return out


def _card(r) -> dict:
    # ...one an earlier build set aside on his next line (proposals.passed) says so by its own name: read as `superseded` - a draft a later
    # turn rewrote - the page drew "Earlier draft" where it stood and the card itself again under everything, below the live one
    # ...and a step he approved that then failed is a card HE PRESSED (`failed`), so it stays under the answer he pressed it under: settled
    # as `superseded` it read as a rewritten draft and went back to the turn that first raised it - nothing stood where he had pressed
    # (the recorded held step, 2026-11-11)
    from .proposals import passed
    from .shellgate import FAILED, NOT_RUN
    from .wrapup import WITHDRAWN
    failed = r['Status'] == 'superseded' and (r.get('DecideNote') in (FAILED, NOT_RUN) or bool(r.get('ActError')))   # ...any act's press that failed
    # ...A DRAFT ITS AGENT TOOK BACK STAYS WHERE IT STOOD, greyed, with its words (the owner's live task, 2026-11-12: he wrote again, the agent
    # withdrew its reply in the turn that answered him, and the card went from the chat - no page draws a draft "closed unsent")
    # ...and one set aside as he wrote past it (proposals.set_aside_drafts) the same way: a draft is its words, which the page draws greyed
    words = str(r.get('DraftText') or '').strip() if r['Kind'] in (*DRAFTS, 'slot') else ''
    # ...and an action's is what it would do (its proposal's own words) - so one he wrote past is drawn greyed with them, in the frame he wrote
    if r['Kind'] == 'action':
        try: d = json.loads(r.get('DraftText') or '{}') or {}
        except (TypeError, ValueError): d = {}
        words = ' '.join(str((d.get('what') or d.get('command') or r.get('Reason') or '') if isinstance(d, dict) else r.get('Reason') or '').split())[:300]
        # ...but an act a connector declares a card for (a post, a tracker comment) is drawn by that card (ActionCard) with its own words,
        # dismissed too: handed `was`, the page swapped it for "Not sent" over the agent's reason a beat after it said "dismissed" (2026-11-18)
        from .connectorcatalog import action_for
        if r['Status'] == 'rejected' and isinstance(d, dict) and d.get('action') == 'run_tool' and action_for(d.get('type')): words = ''
    gone = r['Status'] == 'closed_unsent' and str(r.get('DecideNote') or '').startswith(WITHDRAWN) and words
    # ...AND ONE HE SAID NO TO STAYS TOO, its words under "not sent" (the real-CLI walk, 2026-11-16: Don't send took the card off the chat, and
    # only "You dropped the email" was left - the basic flow's "no card gone from the canvas")
    st = 'passed' if passed(r) else 'failed' if failed else 'withdrawn' if gone else r['Status']
    return {'id': f"r:{r['ReviewId']}", 'kind': 'card', 'review': r['ReviewId'], 'what': r['Kind'], 'status': st,
            'at': r['CreatedAt'], 'decided': r.get('DecidedAt'), **({'was': {'text': words if r['Kind'] == 'action' else r['DraftText']}} if words and st in ('passed', 'withdrawn', 'pending', 'rejected') else {})}
DRAFTS = ('draft_reply', 'draft')

def unwritten(r: dict) -> bool:
    """A REPLY OWED THAT NOBODY HAS WRITTEN, AND NOBODY SAID WHY, IS NO CARD (the owner, 2026-11-13: "why would you have empty write a reply box,
    unless the agent said i'm not sure what to respond, feel free to respond here"): the agent drafts it, and its draft is the card. An empty
    one is drawn only where its own record says why it is empty - the drafter said what it needs (DraftNeeds), it failed (DraftError), or the
    agent filed it so (DraftBy) - and then in the turn that said so. The page reads the same three (sendState.draftState: not `undrafted`)."""
    from .wrapup import AGENT_DRAFT
    return (r.get('Kind') in DRAFTS and r.get('Status') == 'pending' and not str(r.get('DraftText') or '').strip()
            and not (r.get('DraftError') or r.get('DraftNeeds') or str(r.get('DraftBy') or '').startswith(AGENT_DRAFT)))


def served_back(store, tid: int, out: list, was: dict, waiting: set) -> list:
    """AN ITEM ONCE DRAWN IS IN EVERY READ AFTER (the basic flow's check on the release run, 2026-11-12: a turn at work whose session was
    dropped under it left the chat with what it had done): an arrival and a turn at work are kept as drawn (the `shown` ledger's Host), and
    one the facts no longer give is drawn from there - a turn that was at work as stopped where it stood."""
    have = {x.get('id') for x in out}
    for k, host in was.items():
        if k in have or k in waiting or not host or not host.startswith('{'): continue
        try: x = json.loads(host)
        except ValueError: continue
        if x.get('kind') == 'turn': out.append({**x, 'state': 'stopped' if x.get('state') in LIVE else x.get('state'), 'cards': [], 'ended': x.get('ended') or x.get('started')})
        elif x.get('kind') == 'arrival': out.append(x)
    return out


def keep_shown(store, tid: int, out: list, was: dict) -> None:
    "What served_back draws an item from: an arrival as first drawn, a turn at work as it stands - written after `served` gave each its place."
    for x in out:
        if x['kind'] == 'arrival' and not was.get(x['id']) or x['kind'] == 'turn' and x.get('state') in LIVE and (x.get('text') or x.get('steps')):
            if (snap := json.dumps(x, default=str)) != was.get(x['id']): store._exec('UPDATE shown SET Host=? WHERE TaskId=? AND Key=?', (snap, int(tid), x['id']))


def served(store, tid: int, out: list) -> list:
    """THE CHAT ONLY EVER GROWS AT ITS FOOT (the owner, 2026-11-12: "have you ever seen a chat that you type something new and the past agent
    turn changes. of course not"): each item keeps the place it was first served in (the `shown` ledger) - a reload, a reopen, a restart draw
    the same order - and an item never served before goes under all of them, in the order this read made. Only an item's state changes."""
    known = {r['Key']: r['Seq'] for r in store._rows('SELECT Key, Seq FROM shown WHERE TaskId=?', (int(tid),))}
    new = [x for x in out if x['id'] not in known]
    if new:
        n = max(known.values(), default=0)
        with store.lock:
            store.cx.executemany('INSERT OR IGNORE INTO shown (TaskId, Key, Seq) VALUES (?,?,?)', [(int(tid), x['id'], n + i + 1) for i, x in enumerate(new)])
            store.cx.commit()
    return sorted((x for x in out if x['id'] in known), key=lambda x: known[x['id']]) + new


# ONE BUILD OF A TASK'S CONVERSATION AT A TIME (the owner's live app, 2026-11-16: a working coding agent's chat took 25-40 s a call, and the
# page's polls, the task's read and the rail's ran their builds side by side, each slowing the others): a call while one is building waits for
# it and takes its result - the same list, built once
_BUILDS, _BUILDS_LOCK = {}, threading.Lock()


# ONE CLOCK FOR A TURN (the owner, 2026-11-16: a reply turn read "working 1m 39s" while it ran and "ran 1m 27s" once it was done): it starts
# at the FIRST hand-over after the answer before it - his line or press, a mail it woke for - live and finished alike. The latest one, read
# for the finished turn, was an input heard mid-way, and the turn he had watched for 1m 39s "ran" 12 seconds less
# ...AND A STOP ENDS A TURN AS AN ANSWER DOES (the real-CLI walk, 2026-11-17: a turn he stopped files no answer, so the 12 s turn after it
# counted from the stopped one's start and "ran 37s"): `stops`, when each of his stops was heard - the turn begins after the last one
def turn_start(marks, after: float, before: float = float('inf'), stops=()) -> float:
    "When the turn after answer `after` and before `before` began: its first hand-over from `after` on, and from his last stop (0. with none)."
    ms = [m['At'] for m in marks if after <= m['Seq'] < before]
    cut = max((s for s in stops if ms and s <= max(ms)), default=0.)
    return min((a for a in ms if a >= cut), default=0.)


def items(store, tid: int) -> dict:
    "The task's conversation: {rev, items, pending, working, started} - see the module's head. One build per task at a time (_BUILDS)."
    key = (id(store), int(tid))
    with _BUILDS_LOCK:
        b, mine = _BUILDS.get(key), False
        if b is None: b, mine = _BUILDS.setdefault(key, {'done': threading.Event(), 'got': None, 'err': None, 'by': threading.get_ident()}), True
    # ...a build that asks for its own task's list from inside it is that build: read straight, never waiting on itself
    if not mine and b['by'] == threading.get_ident(): return _items(store, tid)
    if not mine:
        b['done'].wait()
        if b['err'] is not None: raise b['err']
        return b['got']
    try: b['got'] = _items(store, tid)
    except BaseException as e: b['err'] = e; raise
    finally:
        with _BUILDS_LOCK: _BUILDS.pop(key, None)
        b['done'].set()
    return b['got']


def _items(store, tid: int) -> dict:
    from . import codingchat, funnel, general, ownwork, session_artifacts, sessionrecord, wrapup
    from .general import ASSISTANT_TYPE, FOLD_HEAD, USER_TYPE, WAITING_TYPE
    from .processing_unread import OWNER_ACTORS
    tid = int(tid)
    # ...read BEFORE the conversation: a turn that ends between the two reads is still at work in this one, its answer not yet read
    from . import origin
    hold_ = origin.hold(store, tid)
    at_work, t0 = (general.working(store, tid), general.turn_started(tid)) if not hold_ else (bool(getattr(general._live_of(tid), 'busy', False)), general.turn_started(tid))
    # ...the lines BEFORE the ledger: a line at rest is heard and then kept (general.take_line), so one read here has its hand-over in the
    # ledger read after it - never by the box for a frame, with the answer above it marked at work
    rows, kept = store.list_comments(tid, internal=True), {c['CommentId']: c for c in general.chat_rows(store, tid)}
    led = {(r['Kind'], r['Ref']): r for r in store._rows('SELECT * FROM heard WHERE TaskId=? ORDER BY HId', (tid,))}
    era = min((r['At'] for r in led.values()), default=INF)
    marks = [r for (k, _), r in led.items() if k == 'turn']; prev_answer = 0       # the answer before the turn being read (turn_start)
    # ...AND A TURN HIS LINE BEGAN STARTS AT THAT LINE (the walks, 2026-11-17): heard at his press (general.take_line), it is the first thing
    # of the turn the ledger has - the turn not yet handed over read from his press, then went back to its hand-over seconds later
    starts = [r for (k, _), r in led.items() if k in ('turn', 'line')]
    # ...his stops, where heard (else from their own second - a stamp is no finer): each ends the turn it stopped (turn_start)
    # ...and HIS CLOSE, which stops its agent as a stop does (a stress round, 2026-11-18: closed while it worked and reopened by a new mail, the
    # turn the mail began counted from the stopped one's hand-over - drawn as that old turn at work above "You marked it done", its put-down
    # card taken into it)
    ends = (general.PRESSES['stopped_turn']({}), general.PRESSES['close_from_assistant']({}))
    stops = [(h := led.get(('press', str(i)))) and h['At'] or ep(at) for i, at, w, *_ in general.presses(store, tid) if w in ends]
    backs = [int(r[1:]) for k, r in led if k == 'back' and r[:1] == '>']      # an answer taken back before its row was filed (take_back)
    back_why = lambda cid: next((w for n in sorted(backs, reverse=True) if n < cid and (w := led[('back', f'>{n}')].get('Sid'))), '')
    asked = None                                   # the task's own row: the ask that opened it, where no message did
    pend, ev = [], []                              # ev: (when, rank - an input before the work it began, order, entry)
    put = lambda t, rank, e, hid=0: ev.append((t, rank, hid, len(ev), e))        # ...and what one hand-over took, in the order it took it

    # the comments are one chain, in the order they were filed: his lines, Taskuary's briefs (never drawn - a turn begins there), the answers
    summ, steps_of, last, lines, texts = general.turn_summaries(store, tid), {}, 0., [], set()
    p = sessionrecord._gen_path(tid)
    if p.is_file():
        for l in p.read_text(encoding='utf-8', errors='replace').splitlines():
            try: j = json.loads(l); steps_of.setdefault(j.get('reply'), []).extend(j.get('steps') or [])
            except ValueError: continue
    snaps = store.draft_snapshots(tid)
    turn_of = {}                                   # an answer's CommentId -> its turn entry (a card names its turn by it)
    for c in rows:
        ty, cid = c.get('ActorType'), c['CommentId']
        # ONLY WORDS HE TYPED ARE A LINE, by who filed them here - never by the role a CLI or a runtime gave the text (the owner, 2026-11-11, of
        # Taskuary's own note to the agent drawn as his bubble: "it's not a prompt if you hit approve?"). What the app tells the agent - a
        # note, a wake, a press's result, whoever's name it is filed under - is no item at all: his press is its own quiet line (press_lines)
        if ty == WAITING_TYPE or (ty == USER_TYPE and c.get('Actor') in OWNER_ACTORS):
            body = general.his_line(c)
            it = {'id': c.get('LineId') or f'c:{cid}', 'kind': 'line', 'at': c['CreatedAt'], **body}
            h = led.get(('line', c.get('LineId') or ''))
            if not h and ty == WAITING_TYPE: pend.append({**it, '_after': _after(c['Body']), '_k': came(c)}); continue
            if h: it['_h'] = h['At']
            # ...one the ledger heard stands at its hand-over's own moment, beside what was taken with it (in the ledger's order, `put`): moved
            # a hair on for each line before it, every message of a flood stood above its second line
            last = h['At'] if h and h['At'] >= last else max(last + 1e-7, h['At'] if h else ep(c['CreatedAt']))
            put(last, 0, it, h['HId'] if h else 0); lines.append((last, _flat(body['text']), len(ev) - 1)); texts.add(_flat(body['text']))
        elif ty == USER_TYPE:
            last = max(last + 1e-7, ep(c['CreatedAt']))
            if str(c.get('Body') or '').startswith(FOLD_HEAD):
                put(last, 0, {'id': f'n:c{cid}', 'kind': 'note', 'at': c['CreatedAt'], 'text': 'Folded in ' + c['Body'][len(FOLD_HEAD):].split('\n', 1)[0]})
        elif ty == ASSISTANT_TYPE:
            body = clean(str((kept.get(cid) or c).get('Body') or ''))
            if c.get('Actor') == sessionrecord.NOTE_ACTOR:
                # ...after ALL of its own second, as a press is - its stamp is no finer: said in the second of the turn's last step (a turn cut
                # as Taskuary closed), it stood above the work it was said of
                last = max(last + 1e-7, ep(c['CreatedAt']) + 0.999); put(last, 0, {'id': f'n:c{cid}', 'kind': 'note', 'at': c['CreatedAt'], 'text': body}); continue
            began = max((m['At'] for m in marks if m['Seq'] < cid), default=0.)
            clock, prev_answer = turn_start(starts, prev_answer, cid, stops) or began, cid      # ...its clock (turn_start); `began` places it
            # ...AN ANSWER NOBODY MARKED THE START OF STANDS AT ITS OWN TIME (every task answered before hand-overs were written down - his
            # older tasks, the demo's): placed at the start of time, it stood above the mail it answered and the chat began with the agent
            last = max(last + 1e-7, began or ep(c['CreatedAt']))
            # ...ONE THAT FAILED says so where it failed, for good (general.file_turn): its closing line, after the app's own mark, is its `fail`
            body, fail = general.failed_line(body)
            st = _said(steps_of.get(cid, []), body)
            # ...one it was made to take back (take_back): its words are a step of the work that goes on under it
            # ...and its summary goes with its words (the recorded walk, 2026-11-12: the saved sign-in's folded turn still drew its summary - "Erin
            # asked Alex ...; no reference number has been read yet" - under the note that it had signed in, the owner in the third person)
            took = (('back', str(cid)) in led or any(n < cid for n in backs)) and body
            if took:
                st, body, backs = [*st, {'k': 'note', 'text': (led.get(('back', str(cid))) or {}).get('Sid') or back_why(cid) or TOOK_BACK}], '', [n for n in backs if n >= cid]
            # ...and it BEGAN at its own time too (the demo walk, 2026-11-18): with no start it counted as begun at the start of time, so a card
            # made long before it was "made in" it - a played Send's card was taken into the line said after it, and jumped down under it
            t = {'kind': 'turn', 'at': stamp(clock) or c['CreatedAt'], 'state': 'failed' if fail else 'done', 'steps': st, 'text': body, 'cards': [],
                 'started': clock or ep(c['CreatedAt']), **({'fail': fail.strip()} if fail else {}),
                 'ended': ep(c['CreatedAt']), 'answer': f'comment-{cid}', **({'summary': summ[cid]} if cid in summ and not took else {})}
            # ...and each draft this turn left that a later turn rewrote: greyed where it stood, never moved
            newest = {s['review']: k for k, ss in snaps.items() for s in ss}
            t['cards'] = [{'id': f"r:{s['review']}:c{cid}", 'kind': 'card', 'review': s['review'], 'what': 'draft_reply', 'status': 'superseded', 'at': s['at'], 'was': s}
                          for s in snaps.get(cid, []) if newest.get(s['review']) != cid]
            turn_of[cid] = t; put(last, 1, t)

    # A ROUTINE'S RUN OF STEPS IS A TURN, on the one road every turn takes (flow.turn, 2026-11-17): at work while the run has the task and no
    # agent has taken it from there - "working" is one fact, so the run's at work is the chat's
    from . import flow, workflows
    flowing = workflows.at_work(tid) and not at_work
    if (ft := flow.turn(store, tid, flowing)): put(ft['started'] or last + 1e-7, 1, ft)      # ...where the run began: an agent it hands to answers under it
    at_work = at_work or flowing

    # a chat agent's turn at work: under what it was given, its steps as they come
    ses = general.session_for(tid)
    # ...never once its answer is filed: the session reads busy for a beat after (recorded 2026-11-12: a second, empty turn spun under the
    # answer for a frame and went) - the turn at work is the one the newest hand-over began, and that one has answered
    done_ = turn_of and turn_of[max(turn_of)]['ended'] >= max((m['At'] for m in marks), default=INF) - 0.01
    if ses is not None and getattr(ses, 'busy', False) and not done_:
        answered = max(turn_of, default=0)
        began = max((m['At'] for m in marks if m['Seq'] >= answered), default=0.) or max(last + 1e-7, getattr(ses, 'last', 0) or 0)
        clock = turn_start(starts, answered, stops=stops) or general.PRESSED.get(tid) or began      # its clock, as the finished turn reads it (his press before it is written)
        # ...and never from before a stop or a close of his that no hand-over has followed yet: the work it begins is under that press (a stamp
        # is a whole second) - read from the stopped turn's hand-over, it stood as that turn, at work again above the press
        # ...only for a turn that began since (the session's own turn clock, `last`): one still letting go of the stopped turn stays above the press
        if (cut := max(stops, default=0.)) >= began and (getattr(ses, 'last', 0) or 0) > cut: began = cut + 1; clock = max(clock or 0., began)
        # ...only what came after the newest line of his it heard mid-turn (sessionrecord.since_heard): before it stands above that line
        trace = sessionrecord.since_heard(getattr(ses, 'trace', None), max((r['At'] for r in led.values()), default=0.))
        # ...and the answer it is writing, while that is the newest thing it did (agents.ACPSteps._live): the turn's line of what it is doing
        doing = (lambda e: clean(e.get('detail')) if e and e.get('type') == 'live' and e.get('name') == 'writing' else '')(trace[-1] if trace else None)
        # ...STARTING UNTIL ITS AGENT HAS THE PROMPT (recorded on the real CLI, 2026-11-16: a cold adapter took most of a minute to open, and the
        # turn read "Thinking..." over it): no word from the agent's road yet but its own start - every CLI road traces `prompt` as it hands it over
        # ...OPENING while its agent really is starting: the turn says so from its start where its CLI is not up (general.cold, 2026-11-17), and
        # the prompt its road then hands over ends it - a kept conversation is never opening
        kinds = [e.get('type') for e in trace]
        opening = 'opening' in kinds and kinds[::-1].index('opening') < (kinds[::-1].index('prompt') if 'prompt' in kinds else len(kinds))
        put(max(last + 1e-7, began), 1, {'kind': 'turn', 'at': stamp(clock), 'state': 'working', 'steps': _said(sessionrecord.trace_steps(trace)), 'text': '', 'cards': [],
                                        'started': clock, 'ended': None, 'sid': getattr(ses, 'sid', ''), **({'doing': doing} if doing else {}), **({'opening': True} if opening else {})})

    # a coding session's record: its steps, cut into turns where it was given something. What it was given is never drawn from the record -
    # his lines are the ledger's, Taskuary's briefs nobody's - but a line typed into the pane itself, or one from before the ledger, is his
    live_sid = None
    for sid, live, steps in _session_steps(store, tid) if not general.handles(store.get_task(tid) or {}) or codingchat._live(tid) else []:
        if live: live_sid = sid
        took, n = [x for x in lines], 0
        for i, s in enumerate(steps):
            k = s.get('k')
            if k in ('you', 'brief'):
                n += 1
                if k == 'brief' or s.get('line') and ('line', s['line']) in led: continue
                f = _flat(s.get('text'))
                # ...one of his the ledger already placed (heard up to the step's own time): the same words, once
                hit = next((j for j, (at, w, _) in enumerate(took) if at <= s['T'] + 2 and w and (w == f or f.startswith(w[:150]) or w.startswith(f[:150]))), None) if s['T'] >= era - 2 else None
                if hit is not None:
                    # ...and where its own record says WHEN it took the line, that is when it heard it: a pane's CLI holds a typed line until
                    # its turn ends, and the answer before it was drawn under it (the recorded walk, 2026-11-11)
                    at, _, at_ev = took.pop(hit)
                    if s['T'] > at: ev[at_ev] = (s['T'], *ev[at_ev][1:])
                    continue
                # ...and one that names his kept line is that line - by the box until its hand-over is written, then where it was heard - never
                # a second line under the record's own name: sent into a turn, it stood in the chat AND by the box until the ledger caught up,
                # and went from one name to the other (the recorded hold, 2026-11-11)
                if s.get('line'): continue
                put(s['T'], 0, {'id': f'y:{sid}:{i}', 'kind': 'line', 'at': stamp(s['T']), 'text': s.get('text') or '', 'files': []})
            else: put(s['T'], 1, {'kind': 'step', 'sid': sid, 'seg': n, 'step': {k_: v for k_, v in s.items() if k_ != 'T'}, 'T': s['T']})

    # what came in, and what he pressed: at the moment the agent heard it, else at its own time
    # ...what the chat has drawn (the `shown` ledger) - its place, and for an arrival or a turn at work what it said (Host): drawn once, an item
    # is on the canvas in every read after (served_back)
    was_shown = {r['Key']: r['Host'] for r in store._rows('SELECT Key, Host FROM shown WHERE TaskId=?', (tid,))}
    waits = min((x.pop('_after') for x in pend), default=INF)
    began = (t0 or max((r['At'] for r in led.values()), default=0.) or INF) if at_work else INF
    any_mail = False
    for x in _mail(store, tid):
        any_mail = True
        # ...the task's OWN row (ownwork.ensure: his ask, filed as its first session opens) never "came in": it is what opened the chat (below)
        if (x.get('Channel') or '') == ownwork.CHANNEL: asked = x; continue
        h, it = led.get(('mail', str(x['MessageId']))), None
        row = general.mail_row(store, x)
        it = {'id': f"m:{x['MessageId']}", 'kind': 'arrival', **row, 'joined': stamp(x['T']), **({'_hm': h['At']} if h else {})}
        # ...a stamp is a whole second: one that joined in the turn's first second came in under it (it stood ABOVE the turn at work)
        # ...and one that came in while a line of his waits by the box waits there with it: drawn at once, the line entered above it when
        # both were heard, in the order they came (the recorded flood on a pane, 2026-11-11)
        # ...and what an untrusted sender wrote on a thread an agent works: it waits, behind the Trust action (origin.hold)
        # ...and one the chat has drawn never goes back by the box (the release run on macOS, 2026-11-12: a coding turn began in the second the
        # first mail joined, and the mail left the canvas for the waiting room)
        if not h and it['id'] not in was_shown and (at_work and x['T'] + 1 > began or x['MessageId'] > waits or (hold_ and x['MessageId'] in hold_['mids'] and (turn_of or live_sid))): pend.append({**it, '_k': came(x)})
        else: put(h['At'] if h else x['T'], 0 if h else -1, it, h['HId'] if h else 0)
    # ...AND ONE THAT WAS DRAWN HERE STAYS, though it moved to a task of its own (a break-out; the basic flow's check, 2026-11-12: the second
    # matter left the chat with the turn that answered it): where it stood, saying where it went
    here = {f"m:{x['MessageId']}" for x in _mail(store, tid)}
    for r in store._rows("SELECT Key FROM shown WHERE TaskId=? AND Key LIKE 'm:%'", (tid,)):
        if r['Key'] in here or not (m := store.get_message(int(r['Key'][2:]))) or int(m.get('TaskId') or 0) == tid: continue
        h = led.get(('mail', r['Key'][2:]))
        put(h['At'] if h else ep(m.get('CreatedAt')), 0, {'id': r['Key'], 'kind': 'arrival', **general.mail_row(store, {**m, 'T': ep(m.get('CreatedAt'))}),
                                                       'moved': int(m.get('TaskId') or 0)}, h['HId'] if h else 0)
    stop =f"You {general.PRESSES['stopped_turn']({})}."
    # ...HIS CLOSE IS ONE LINE (the recorded closed task, 2026-11-12: "You marked it done" and under it the page's "Mark done 4m ago"): the
    # press that closed an open-again-never task is marked `closes`, with the note he closed it with, and the page draws no line of its own
    # ...and every close of his, which ends the turn it was pressed under as his stop does (`_shut`, below)
    closes_ = [str(r['Id']) for r in store._rows("SELECT Id FROM audit WHERE EntityType='task' AND EntityId=? AND Action='close_from_assistant' ORDER BY Id", (tid,))]
    shut = {'Id': closes_[-1]} if closes_ and (store.get_task(tid) or {}).get('Status') == 'done' else None
    for m in general.press_lines(store, tid):
        aid, text = m['id'].split('-')[1], m['content'][0]['text']
        h, closes = led.get(('press', aid)), bool(shut) and aid == str(shut['Id'])
        if closes and (note := next((c['note'] for c in reversed(store.closeouts(tid)) if c['what'] == 'closed'), '')): text = f"{text.rstrip('.')} - {note.rstrip('.')}."
        it = {'id': f'p:{aid}', 'kind': 'press' if m.get('press') else 'note', 'at': m['createdAt'], 'text': text, **({'closes': True} if closes else {}),
              **({'_shut': not h} if aid in closes_ else {}),
              **({'perm': m['perm']} if m.get('perm') else {}),
              **({'stop': True, '_hs': bool(h)} if text == stop else {})}
        # ...and one the chat has drawn never goes back by the box, as a drawn mail does not (a stress round, 2026-11-18: his Mark done, drawn,
        # left the canvas while the turn a reopening mail began was starting, and came back above that mail once it was at work) - and his
        # close never waits there at all: like his stop it ends the turn it was pressed under, it is no input for the next
        if not h and it['id'] not in was_shown and at_work and ep(m['createdAt']) + 1 > began and m.get('press') and text != stop and aid not in closes_: pend.append({**it, '_k': (int(ep(m['createdAt'])), INF, 2, int(aid))})
        # ...A PRESS NOBODY HEARD YET STANDS AFTER ALL OF ITS OWN SECOND - its stamp is no finer: a stop pressed in the second its turn's line was
        # heard sorted above that line, and the stop's mark fell on the answer before it (a same-second tie, seen as a flash and a red test)
        else: put(h['At'] if h else ep(m['createdAt']) + 0.999, 0 if h else -1, it, h['HId'] if h else 0)
    # ...AND WHAT WAITS IN THE ORDER IT CAME, on the hand-over's own key (came; a press after all of its second): gathered kind by kind, his
    # lines stood by the box above the mail between them - and a read in the beat before the hand-over served them so, a place kept for good
    # (Windows CI, 2026-11-18: a flood read every line of his, then every mail)
    pend.sort(key=lambda p: p.pop('_k'))

    # in order - and an input nobody heard never cuts a turn's work in two: it stands after the turn it came in under
    # ...A CHAT TURN'S TOO, wherever its answer was placed (the stress round, 2026-11-18): a note filed while the turn worked (his reply from
    # the mailbox put the draft down) stands at the end of its second and pushes the answer after it - past his reply, read at its own time,
    # and the finished turn was drawn under the reply as the next turn's, then gone
    spans = [(e['started'], t) for t, _, _, _, e in ev if e['kind'] == 'turn' and e.get('started')]
    # (one step past it, exactly: at an epoch's size a 1e-7 nudge is under the float's grain and leaves the tie it was to break)
    ev = [(max([t] + [math.nextafter(at, INF) for b, at in spans if b <= t <= at]) if rank == -1 else t, rank, *r) for t, rank, *r in ev]
    from .failures import cli_quota
    out, held, run = [], [], None
    def close():
        nonlocal run
        run = None; out.extend(held); held.clear()
    for t, rank, _, _, e in sorted(ev, key=lambda x: x[:4]):
        if e['kind'] == 'step':
            if run is None or run['sid'] != e['sid'] or run['seg'] != e['seg']:
                close(); run = {'kind': 'turn', 'sid': e['sid'], 'seg': e['seg'], 'at': stamp(e['T']), 'state': 'done', 'steps': [], 'text': '', 'cards': [], 'started': e['T'], 'ended': e['T']}
                out.append(run)
            step = e['step']
            if step['k'] == 'error' and (notice := cli_quota(step.get('text'))):
                run.update(state='failed', fail=notice, quota=True)
                run['steps'] = [s for s in run['steps'] if s['k'] != 'said' or str(s.get('text') or '').strip().rstrip('.') != notice]
            else: run['steps'] += _said([step])
            run['ended'] = e['T']
        elif rank == -1 and run is not None: held.append(e)
        else: close(); out.append(e)
    close()
    # THE ASK THAT OPENED THE TASK IS THE FIRST THING IN ITS CHAT, AS HIS WORDS (the owner, 2026-11-11, of a task he made with New: "i create
    # new agent it did not show the prompt i asked it to do???" - the chat held only the agent's turn at work): a task he started himself has
    # no message and, opened by its page, no typed line - its ask is the task's own (ownwork). It is the input the first turn heard, so it
    # stands above that turn, a line of his; where a line or a message already opens the chat, that is the ask
    first = next((x for x in out if x['kind'] in ('turn', 'line', 'arrival')), None)
    # ...from the moment its agent is started: its own row is filed only as the first session opens, a beat after the turn is at work. A
    # task he made and has not started says nothing yet - shown there, the title stood as his line and went when the line he typed began it
    # ...and once drawn it stays, whatever starts or stops after (the basic flow's check, 2026-11-12: it went when the turn it began ended)
    once = bool(store._one("SELECT 1 AS x FROM shown WHERE TaskId=? AND Key=?", (tid, f'a:{tid}')))
    # ...and never while a line of his begins the turn (PRESSED: his press; or heard and not yet filed): that line is the ask (CI parity, 2026-11-12: the task's title stood
    # as his line over the line he typed on one backend, from a read in that beat)
    drawn0 = {x.get('id') for x in out} | {p['id'] for p in pend}
    typed = any(k == 'line' and ref not in drawn0 for (k, ref) in led)
    if (asked or once or not any_mail and at_work and not pend and not typed and tid not in general.PRESSED) and (once or first is None or first['kind'] == 'turn') and (said := ownwork.ask(store, store.get_task(tid) or {}, asked)):
        at = asked['T'] if asked else ep((store.get_task(tid) or {}).get('CreatedAt'))
        # ...his words and his files, read as every line of his is (split_files): a file attached in New stood in his bubble as its path
        out.insert(0, {'id': f'a:{tid}', 'kind': 'line', 'at': stamp(at), **general.split_files(said), '_h': at})
    # ONE TURN AT WORK, AND IT IS THE LAST (the owner's live task, 2026-11-11: a second head spun under a later, finished answer while the task
    # read done): a turn stands where it began, so one that reads at work with a turn after it has ended - whatever its session still says
    turns_ = [x for x in out if x['kind'] == 'turn']
    for x in turns_[:-1]:
        if x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
    # the turn at work is the last thing in the list: one the agent has not yet said a word in is there too, the moment its input was heard
    # ACP keeps streaming after a permission press. Show that work below its answered card.
    tail = next((x for x in reversed(out) if x['kind'] in ('turn', 'line', 'arrival') or (live_sid and x.get('perm'))), None)
    # ...A TURN HE STOPPED IS STOPPED FROM THE PRESS (the recorded stop, 2026-11-11: its CLI took seconds to let go, and all that time the turn
    # spun above "You stopped the agent"): what is at work from there is the turn his waiting lines begin, under the press - with none
    # waiting, nothing is
    # ...UNTIL A TURN BEGINS UNDER THE STOP: one that heard his stop (its hand-over wrote the press down, `hear`) answers what the stopped
    # turn took in and never spoke to (acpcoding._unanswered) - its lines stand above the stop, so no input of its own is under it
    # ...AND HIS CLOSE, the same (a stress round, 2026-11-18): it stopped the agent, so the turn above it is over, and what works after it - a
    # mail that reopened the task - is the turn under it, never that one at work again above "You marked it done"
    # ...AND ONE STOPPED BEFORE ITS FIRST STEP IS NO ITEM YET (recorded over ACP, 2026-11-17): his line is the newest thing, and the stop under
    # it was not read as ending its turn - a new turn stood under the stop, "Waiting for the agent to start", then vanished
    shut_ = bool(tail and tail['kind'] == 'turn' and any(x.get('_shut') for x in out[out.index(tail):]))
    halted = shut_ or bool(tail and any(x.get('stop') and not x['_hs'] for x in out[out.index(tail):]))
    if halted:
        # ...and from the press too where the stopped turn owes him an answer: that turn is on its way, and nothing else says so meanwhile
        at_work = bool(pend) or not shut_ and bool(getattr(general._live_of(tid), 'owes_stop', lambda: False)())     # ...a close owes nothing
        if tail.get('state') in ('working', 'starting'): tail.update(state='done', ended=tail.get('ended') or time.time())
    # ...A TURN IS MADE ONCE, AT ITS HAND-OVER: the live session's last turn is the one at work only where its work came after the newest
    # hand-over - one that ended before it is finished, and the turn now beginning stands under it (a wake after a press marked the answer
    # above "working" again, and the card under it lost its place)
    mark = max((m['At'] for m in marks), default=0.)
    # ...AND A TURN WHOSE ANSWER IS FILED AFTER THE NEWEST HAND-OVER IS THE WORK THAT WAS AT WORK (recorded 2026-11-12: its session still read
    # busy for a beat after the answer was filed, and a second, empty turn stood "starting" under it for a frame and went): nothing new runs
    # ...BUT A HAND-OVER ON ITS WAY IS NEW WORK (the browser audit, 2026-11-15): the agent's turn ended asking for the sign-in, its answer filed,
    # and the ~3 s Taskuary typed the saved one read as nothing at work - "agent waiting on you" with nothing on him (general.starting): that
    # turn is the one at work again, its last step the sign-in going in
    if at_work and not pend and tail and tail['kind'] == 'turn' and tail['state'] == 'done' and tail.get('answer') and (tail.get('ended') or 0) >= mark - 0.01 \
            and not (t0 and t0 > (tail.get('ended') or 0)):
        if general.starting(tid): tail.update(state='working', ended=None)
        else: at_work = False
    mine =not halted and tail and tail['kind'] == 'turn' and (tail['state'] == 'working' or tail.get('sid') == live_sid and live_sid and (tail.get('ended') or INF) >= mark - 0.01)
    # ...AND NONE BEFORE THE LINE THAT BEGINS IT IS IN THE LIST (recorded 2026-11-12: a read between take_line's "at work" and its keeping the
    # line drew the new turn's dots under the old answer, his line then under them): a line heard and not yet filed is the input it waits for
    drawn = {x.get('id') for x in out}
    unfiled = any(k == 'line' and r['At'] >= mark - 0.01 and ref not in drawn and ref not in {p['id'] for p in pend} for (k, ref), r in led.items())
    # ...A TURN NOT YET HANDED OVER IS THE SAME TURN (the walks, 2026-11-17): its clock and stamp the ones it keeps once at work - the first
    # thing heard from the press that began it (`starts`) - and opening where the turn at work will be (general.cold)
    begun, opens = min((r['At'] for r in starts if t0 and r['At'] >= t0), default=0.), ({'opening': True} if general.cold(tid) else {})
    # ...AND WHAT WORKS UNDER HIS ANSWER TO A STEP COUNTS FROM IT (the owner's live app, 2026-11-18: allowed a push at 9:00 in a turn begun at
    # 8:45, the work after it read "AGENT · 8:45 PM · working 15m" under his card): never a clock from before the press it stands under
    floor = lambda upto: max((x.get('_h') or ep(x.get('at')) for x in out[:upto] if x.get('perm')), default=0.)
    if at_work and not mine and unfiled: pass
    elif at_work and not mine:
        if tail and tail.get('perm') and turns_ and turns_[-1]['state'] in LIVE:
            turns_[-1].update(state='done', ended=tail.get('_h') or ep(tail.get('at')))
        # ...AND WHAT IT WILL TAKE STANDS ABOVE IT FROM THE FIRST READ (the walks, 2026-11-17: his outside reply, handed to the agent at rest,
        # sat ~3 s as a chip by the box under the turn's bare dots, then jumped up into the chat): where no input heard since begins this turn,
        # what waits - a mail, a line of his - is its input, drawn where it will stand once heard, under its own name. Behind a Trust it waits
        if not hold_ and not (tail and tail['kind'] in ('line', 'arrival', 'press') and (tail.get('_h') or tail.get('_hm') or ('press', tail['id'][2:]) in led)):
            took = [p for p in pend if p['kind'] in ('line', 'arrival')]
            if took: out += took; pend = [p for p in pend if p not in took]; tail = took[-1]
        began_ =begun or t0 or max(mark if tail and tail['kind'] == 'turn' and mark >= (tail.get('ended') or 0) else 0., (tail or {}).get('_h') or (tail or {}).get('_hm') or 0.) or time.time()      # from its hand-over, where one is written
        if (cut := max(stops, default=0.)) >= began_: began_ = cut + 1        # ...never from before a stop or a close of his (as the turn at work, above)
        began_ = max(began_, floor(len(out)))
        out.append(tail := {'kind': 'turn', 'at': stamp(began_), 'state': 'starting', 'steps': [], 'text': '', 'cards': [], 'started': began_, 'ended': None, **opens})
    elif at_work and tail['state'] != 'working':
        b_ = max(t0 or tail['started'], floor(out.index(tail))); tail.update(state='working', ended=None, started=b_, at=stamp(b_) if b_ != tail['started'] else tail['at'])
    # ...AND NEVER ABOVE HIS NEWEST LINE (the owner's live task, 2026-11-12: the dots stood over "try now"; recorded on ACP the same day for a
    # frame - the session's record had not yet cut its turn at his line): what works now is the turn his line began, under it
    if at_work and (his := max((i for i, x in enumerate(out) if x['kind'] == 'line'), default=-1)) >= 0:
        for x in out[:his]:
            if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
        if not any(x['kind'] == 'turn' and x['state'] in ('working', 'starting') for x in out[his + 1:]):
            b_ = begun or t0 or out[his].get('_h') or time.time()
            out.append({'kind': 'turn', 'at': stamp(b_), 'state': 'starting', 'steps': [], 'text': '', 'cards': [], 'started': b_, 'ended': None, **opens})
    # ..."WORKING" IS ONE FACT, the one the task's header reads: where it is false no turn spins
    if not at_work:
        for x in out:
            if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
    # ...a turn he stopped ended there, and one that failed says so where it failed, with the way past it
    for i, x in enumerate(out):
        # ...the turn right above his stop - one stopped before it said or did anything left nothing, and the mark fell on the finished answer
        # above the line it never got to answer (the recorded stop, 2026-11-11)
        if x.get('stop') and (t := next((y for y in reversed(out[:i]) if y['kind'] in ('turn', 'line', 'arrival')), None)) and t['kind'] == 'turn' and t['state'] == 'done': t['state'] = 'stopped'
    # ...and one stopped before it said or did anything is no item: his stop's own line says it. It was drawn empty between his line and
    # the press while its session still held it, and was gone once the next turn ended (the recorded stop, 2026-11-11)
    out = [x for x in out if not (x['kind'] == 'turn' and x['state'] == 'stopped' and not (x['text'] or x['steps'] or x['cards']))]
    # ...AND STAYS THERE ONCE HE HAS MOVED ON (the Continue round, 2026-11-18): drawn only while it was the run's last word, the failure went from
    # above his line the moment he pressed Continue with a note - his first ask then stood with nothing under it. It stands under the input it
    # failed on, by its own time; the way past it (`fix`) only while it is still the run's ending
    if not at_work and (f := funnel.run_failed(store, tid, live_too=True)):
        evf = store.last_worker_event(tid, kinds=('failed',)) or {}
        t = next((y for y in reversed(out) if y['kind'] in ('turn', 'line', 'arrival')), None)
        if not (t and t['kind'] == 'turn'):
            if ep(evf.get('CreatedAt')) >= ep((t or {}).get('at')) - 1: out.append(t := {'kind': 'turn', 'at': evf.get('CreatedAt') or '', 'state': 'failed', 'steps': [], 'text': '', 'cards': [], 'started': None, 'ended': ep(evf.get('CreatedAt'))})
            else: t = None
        if t and (t.get('ended') or 0) <= ep(evf.get('CreatedAt')) + 1: t.update(state='failed', fail=f['sentence'], fix=f.get('fix'))
    # ...AND STAYS THERE ONCE HE HAS MOVED ON (the Continue round, 2026-11-18): drawn only while it was the run's last word, the failure went from
    # above his line the moment he pressed Continue with a note, and his first ask stood with nothing under it. Past, it stands under the input it
    # failed on, by its own time, without the way past it - the turn after it is that
    elif (evf := store.last_worker_event(tid, kinds=('failed',))):
        tf = ep(evf.get('CreatedAt'))
        i = next((k for k in range(len(out) - 1, -1, -1) if out[k]['kind'] in ('line', 'arrival') and ep(out[k].get('at')) <= tf), None)
        if i is not None and i + 1 < len(out):
            f, t = funnel.failure_of(evf, tid), out[i + 1]
            if not (t['kind'] == 'turn' and t['state'] != 'working' and (t.get('ended') or 0) <= tf + 1):
                out.insert(i + 1, t := {'kind': 'turn', 'at': evf.get('CreatedAt') or '', 'state': 'failed', 'steps': [], 'text': '', 'cards': [], 'started': None, 'ended': tf})
            t.update(state='failed', fail=f['sentence'], fix=None)

    # names: an input's is its own; a turn's is the input it stands under and its place after it
    seen, anchor, n = set(), f'0:{tid}', 0
    for x in out:
        if x['kind'] == 'turn':
            # ...a coding session's turn by its own record (its session, its place in it): an input that joined above it never renames it (the
            # basic flow's check, 2026-11-12: a mail placed over a closed session's turn renamed it, and the turn went and came back)
            x['_seg'] = x.pop('seg', None)
            x['id'] = f"t:{x['sid']}:{x['_seg']}" if x.get('sid') and x['_seg'] is not None else f't:{anchor}:{n}'; n += 1
        else:
            if x['kind'] in ('line', 'arrival', 'press'): anchor, n = x['id'], 0
        if x['id'] in seen: x['id'] += f":{len(seen)}"
        seen.add(x['id'])

    # A TURN'S CARDS STAND LAST IN IT: each action under the turn that set it up (the one that last left a draft as it stands), else where it was made
    # ...the turn that was at work when a thing was made: the first one that had begun (where its start is known) and had not yet ended
    # ...and a turn still at work before one that ended a moment ago (2026-11-12: a stamp is a whole second, so the turn that ended just
    # before can still read as open by it - a step held in the turn at work went up to the one before, above his line)
    def made_in(at):
        open_ = [x for x in out if x['kind'] == 'turn' and (x.get('ended') is None or x['ended'] + 1 >= at - 0.999) and (x.get('started') or 0) <= at]
        return next((x for x in open_ if x.get('ended') is None), open_[0] if open_ else None)
    # ...and each page it showed or published, by that same rule, named by its turn (`after`: the page's key for a turn); None: at the foot
    from . import outputs
    published = [{**p, 'after': (t.get('answer') or t['id']) if (t := made_in(ep(p.get('created_at')) + 0.999)) else None} for p in outputs.pages(store, tid)]
    # ...A CARD STANDS IN THE TURN IT WAS FIRST DRAWN IN, or a later one that left it again - never back up (the `shown` ledger's Host)
    hosts = {r['Key'][2:]: r['Host'] for r in store._rows("SELECT Key, Host FROM shown WHERE TaskId=? AND Key LIKE 'c:%'", (tid,))}
    # ...by name, not place: a card no turn holds is put into `out` itself, and every place after it moves down one
    turn_by = {x['id']: x for x in out if x['kind'] == 'turn'}
    turns_at = {k: i for i, k in enumerate(turn_by)}
    newest = next((x for x in reversed(out) if x['kind'] == 'turn'), None)
    from .proposals import passed as proposals_passed
    # ONE CARD AT A TIME (cardqueue): a card that waits behind another is drawn nowhere until its turn comes - and then where the chat has
    # got to, never back in the turn that raised it, above what came since: in the newest turn when nothing came in after it, else under
    # everything. One that waited and was over before it ever stood (taken back, written past) never stands at all
    from . import cardqueue
    queue = cardqueue.state(store, tid); cardqueue.mark(store, tid, queue)
    held = {x for x in queue['held'] if x != cardqueue.LAND}
    # ...and what the chat moved past is greyed where it stood from the moment the input came (proposals.written_past): an email too
    past = queue['past']
    waited = {r['Key'][2:] for r in store._rows("SELECT Key FROM shown WHERE TaskId=? AND Key LIKE 'q:%'", (tid,))}
    last_in = max((i for i, x in enumerate(out) if x['kind'] in ('line', 'arrival', 'press')), default=-1)
    ahead = newest if newest and out.index(newest) > last_in else None
    def place(card, at, cid=None):
        # ...a draft no turn has left yet is new now, whenever its row was made (the recorded walk, 2026-11-12: a reply owed since the mail came
        # was filled in the turn under his line and drawn in the turn of the mail's arrival - live, above his line): it goes in the newest turn,
        # which holds it back while it works
        fresh = card['what'] in DRAFTS and card['status'] == 'pending' and not cid
        h = hosts.get(card['id'])
        if card['id'] in waited and not h:
            # ...(where it first stood under everything it stays: '' is that place in the ledger)
            if ahead is None or h == '':
                if h is None: store._exec('INSERT OR IGNORE INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?)', (tid, f"c:{card['id']}", ''))
                out.append(card); return
            cid, fresh = None, True
        t = (turn_of.get(cid) if cid else None) or (newest if fresh and newest else made_in(at))
        # ...down only to a turn that LEFT it again (its record names that turn): a turn begun after it is not one (recorded on ACP, 2026-11-12:
        # the session went on into a second turn and the card, drawn in the first, went from the chat until the second ended)
        # ...(one with no words yet has nothing that stood anywhere: it is the newest turn's, each time, with what that turn needs for it)
        if h in turns_at and not (fresh and not card.get('was')) and (t is None or not cid or turns_at.get(t['id'], -1) < turns_at[h]): t = turn_by[h]
        elif t is not None and h != t['id'] and not (t['state'] in LIVE):
            store._exec('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host', (tid, f"c:{card['id']}", t['id']))
        if t is None:
            i = max((j for j, x in enumerate(out) if ep(x.get('started') or x.get('at')) <= at), default=-1)
            if i >= 0 and out[i]['kind'] == 'turn': t = out[i]
            else: out.insert(i + 1, card); return
        t['cards'].append(card)
    # ...a task's emails are the page's own block while they wait (`letters`, below); one he wrote past stays where it stood, greyed with
    # its words, as a reply does
    # ...AND ONE THAT WENT IS A CARD OF THE TURN IT STOOD UNDER, as a reply that went is (the audit, 2026-11-13, recorded on the real CLI: two
    # emails sent, and the list placed neither - the page drew them under everything, so they went from the chat while each later turn
    # worked and came back at its foot, under words written long after them)
    # ...A BULK CARD IS ONE CARD (bulkcard.py): its rows stand as the one card of its first, which the page draws in its bulk form
    batches = {}
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Batch IS NOT NULL ORDER BY ReviewId", (tid,)): batches.setdefault(r['Batch'], []).append(r)
    for r in store._rows("SELECT * FROM review WHERE TaskId=? ORDER BY ReviewId", (tid,)):
        if (b := r.get('Batch')):
            rs = batches.get(b) or [r]
            if r['ReviewId'] != rs[0]['ReviewId'] or r['ReviewId'] in held: continue
            # ...greyed where it stood once the chat moved past it, as any card (written_past) - and one that waited behind another and was
            # over before it ever stood never stands, as a single card's rule below
            open_ = [x for x in rs if x['Status'] == 'pending']
            gone = all(x['ReviewId'] in past for x in open_) if open_ else any(proposals_passed(x) for x in rs)
            if (f"r:{r['ReviewId']}" in waited and hosts.get(f"r:{r['ReviewId']}") is None and (gone or not open_)
                    and not any(x.get('DecidedBy') in OWNER_ACTORS for x in rs)): continue
            place({'id': f"r:{r['ReviewId']}", 'kind': 'card', 'review': r['ReviewId'], 'what': 'batch', 'batch': b, 'n': len(rs),
                   'status': 'passed' if gone else 'pending' if open_ else 'done', 'at': r['CreatedAt'], 'decided': None}, ep(r['CreatedAt']) + 0.999)
            continue
        # ...and one he said Don't send to stays too, greyed where it stood (the real-CLI walk, 2026-11-16: it went from the chat - _card)
        if r['Kind'] == 'slot' and not (str(r.get('DraftText') or '').strip() and (proposals_passed(r) or r['Status'] in (*WENT, 'rejected') or r['ReviewId'] in past)): continue
        if unwritten(r) or r['ReviewId'] in held: continue
        if cardqueue.obsolete_read(store, tid, r): continue
        # ...(one the chat moved past while it waited is over already, before its agent has heard the line that did it)
        if f"r:{r['ReviewId']}" in waited and hosts.get(f"r:{r['ReviewId']}") is None and (r['Status'] != 'pending' or r['ReviewId'] in past) and r.get('DecidedBy') not in OWNER_ACTORS: continue
        left = None if r['Kind'] == 'action' else wrapup.left_by(store, r['ReviewId'])
        place(_card(r), ep(r['CreatedAt']) + 0.999, (left or {}).get('CommentId'))

    # A CARD STANDS WHERE ITS TURN LEFT IT, FOR GOOD (the owner, 2026-11-12: "It's a chat with prompts and agent turns, nothing ever goes
    # backwards"): no card is moved under a later answer, copied there, or left behind as a ghost - he moves on past one by writing again (a
    # draft above his newer line is set aside then, `hear`), and the agent raises what is still owed as a new card in its own turn.
    # ...AND A TURN'S CARD IS DRAWN ONCE THE TURN HAS ENDED, as its last thing (the owner, 2026-11-12: "it should finish thinking and last thing
    # should be show action box" - its words landed above a card drawn while it worked): a step it is stopped at waits on him mid-turn as its
    # permission (`permissions`, drawn under the turn), never as a card in it
    # ...AND A TURN THAT GOES ON FROM THE ONE BEFORE IT, WITH NO INPUT BETWEEN, IS THE SAME WORK (the owner's live task, 2026-11-13: a turn
    # left its reply card, Taskuary woke its agent a beat later, and the woken turn's words were drawn UNDER that card - "text after the
    # action box"): what still waits for his press stands at the END of the run, under its last words - once the turn that goes on has
    # ended. WHILE IT WORKS the card stays where it stood, lit (the owner, 2026-11-13: "never close actions boxes" - a Send on one of two
    # emails woke the agent, and the other email vanished for the 15-30 s that turn ran). A card he pressed, or one set aside, stays put
    for a, b in zip(out, out[1:]):
        if a['kind'] == 'turn' and b['kind'] == 'turn' and b['state'] not in LIVE and (lit := [c for c in a['cards'] if c['status'] == 'pending']):
            a['cards'], b['cards'] = [c for c in a['cards'] if c['status'] != 'pending'], [*lit, *b['cards']]
            for c in lit:
                if hosts.get(c['id']) != b['id']:
                    store._exec('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host', (tid, f"c:{c['id']}", b['id']))
    from . import permissions
    perms = permissions.pending(tid, store)
    for x in out:
        # ...a turn at work holds back only what it has not drawn yet: a card already shown in it stays (the owner, 2026-11-13: "never close
        # actions boxes" - a Send woke the agent, the same turn went on, and the other email waiting in it vanished until the turn ended)
        if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x['cards'] = [c for c in x['cards'] if hosts.get(c['id']) == x['id']]
    # ...A REPLY DRAFT ABOVE A NEWER INPUT IS NOT THE ONE TO PRESS, from the frame that input is drawn (`hear` settles it as the turn takes the
    # input): greyed where it stood - its turn drafts again under the input where a reply is still owed
    # ...and a turn that ended having said, done and left nothing (a CLI turn that only took a line in) is no item: the page drew nothing for it
    out = [x for x in out if not (x['kind'] == 'turn' and x['state'] == 'done' and not (x['text'] or x['steps'] or x['cards'] or x.get('summary')))]
    # ...and EACH VIEW IT SHOWED IS DRAWN FROM THE TASK'S OWN COPY, on the turn's `show` step - whatever the CLI's trace kept of the call
    sessionrecord.views_onto(out, store._rows("SELECT * FROM task_artifact WHERE TaskId=? AND Kind=?", (int(tid), session_artifacts.VIEW)))

    # A CODING RUN THAT LEFT WITHOUT FINISHING SAYS SO IN ITS CHAT (decided 2026-11-12): the header chip read "agent stopped", the rail row the
    # sentence cut by its width, and the chat nothing. The task's own idle sentence (funnel.idle_state - the one the row reads) is its last line
    task_ = store.get_task(tid) or {}
    if out and not at_work and not live_sid and not general.handles(task_) and task_.get('Status') not in ('done', 'dropped'):
        from . import funnel, taskstate
        st_ = taskstate.task_state(store, tid=tid)
        if not st_.finished and (idle := funnel.idle_state(store, tid, st_))['kind'] == 'left' and idle['line']:
            out.append({'id': 'n:left', 'kind': 'note', 'at': out[-1].get('at'), 'text': idle['line']})
    # ...and once said it stays where it was said when the run is taken up again (the basic flow's check, 2026-11-12: it went from the chat)
    was_left = store._one("SELECT Host FROM shown WHERE TaskId=? AND Key='n:left'", (tid,))
    if was_left and was_left['Host'] and not any(x['id'] == 'n:left' for x in out if x.get('id')):
        out.append({'id': 'n:left', 'kind': 'note', 'at': '', 'text': was_left['Host']})
    for x in [*out, *pend]: x.pop('stop', None); x.pop('_h', None); x.pop('_hm', None); x.pop('_hs', None); x.pop('_seg', None); x.pop('_shut', None)
    out = served(store, tid, served_back(store, tid, out, was_shown, {p['id'] for p in pend})); keep_shown(store, tid, out, was_shown)
    # (the reply draft above a newer input, greyed - read in the order drawn)
    # (and any card of the agent's above his newer line - every kind, 2026-11-12 - `hear` settles it as his line is heard)
    # ...and one the thread moved past that no agent has heard yet, by the rule the header's pill and the rail read (proposals.written_past)
    from . import proposals
    last_in = max((i for i, x in enumerate(out) if x['kind'] in ('line', 'arrival')), default=-1)
    last_his = max((i for i, x in enumerate(out) if x['kind'] == 'line'), default=-1)
    for i, x in enumerate(out):
        for c in [x] if x['kind'] == 'card' else x['cards'] if x['kind'] == 'turn' else []:
            # ...a card of several emails as well: it has no words of its own to keep, and lit over his newer line it offered two Sends he had
            # just written past (the real-CLI card walk, 2026-11-18)
            set_aside = c.get('was') or c['what'] == 'batch'
            if c['status'] == 'pending' and set_aside and (c['what'] in DRAFTS and i < last_in or i < last_his or c['review'] in past): c['status'] = 'passed'
            # ...each says why in what happened (proposals.passed_why), never "you moved on" over a draft he never saw
            if c['status'] == 'passed' and (rv := store.get_review(c['review'])): c['why'] = proposals.passed_why(store, rv)
            elif c['status'] == 'pending' and set_aside: c['aside'] = proposals.WROTE_PAST      # ...and the page says it from his Enter (withMine)
    # ...and a reply with NO words yet - its card said only what its agent needed - is not the one to press above his newer line either
    # (recorded 2026-11-13: he answered the agent's question, and the empty reply box stood lit over his answer while the turn that writes it
    # worked): it has nothing to grey, so it is not drawn there; the turn his line began raises it, written, as its own last thing
    for i, x in enumerate(out[:max(last_his, 0)]):
        if x['kind'] == 'turn': x['cards'] = [c for c in x['cards'] if not (c['status'] == 'pending' and c['what'] in DRAFTS and not c.get('was'))]
    if (said_ :=next((x['text'] for x in out if x['id'] == 'n:left'), None)) and not (was_left and was_left['Host'] == said_):
        store._exec("UPDATE shown SET Host=? WHERE TaskId=? AND Key='n:left'", (said_, tid))
    # ...and what the agent waits on him for, and the CLI that runs: read by the page off this one list (the chat's own payloads are gone)
    from . import taskstate
    live = general._live_of(tid)
    ask = taskstate.asking(store, store.get_task(tid) or {'TaskId': tid}, general.session_for(tid) or (live if codingchat._live(tid) else None))
    # A QUESTION IS SAID ONCE, IN ITS TURN'S OWN WORDS, ABOVE ITS CARD (the owner, 2026-11-11; the recorded walk drew it a second time under
    # the reply card): where the newest answer already holds the ask's words the list says `said`, and the page draws no line of its own
    # A STEP THAT WAITS ON HIS ALLOW IS ONE CARD (the owner, 2026-11-11: "the question has 2 approve buttons?" - recorded on a coding agent: the
    # permission's card with Allow once / Reject, and under it the same request again as the agent's question, with the same two buttons):
    # the request a permission made is `permissions`' to draw, never the agent's question beside it
    if ask and ask.get('source') == 'permission' and perms: ask = None
    flat = lambda v: ' '.join(re.sub(r'[*_`]', '', str(v or '')).split())
    last = next((x for x in reversed(out) if x['kind'] == 'turn'), None)
    if last and last['state'] == 'failed' and (notice := cli_quota(last.get('fail'))):
        last.update(fail=notice, quota=True)
        if not at_work: ask = None
    # ...a coding turn's words are its `said` steps, its text empty: the demo's #214 drew its closing question twice
    words = last and ' '.join([str(last.get('text') or ''), *(s.get('text') or '' for s in last.get('steps') or [] if s.get('k') == 'said')])
    if ask and last and flat(ask.get('text')) and flat(ask['text']) in flat(words): ask = {**ask, 'said': True}
    # ...AND IT STANDS IN THE TURN THAT ASKED IT, NEVER AT THE CHAT'S FOOT (the owner, 2026-11-13: "never ever pin items on the bottom of the
    # chat" - recorded the same day: a question still open was drawn again under each later turn, leaving the one it had stood under): the
    # list names that turn (`turn`: the one at work when the ask was raised, else the newest) and the page draws the ask inside it, once -
    # with no line of its own where that turn's words already hold it
    if ask and last:
        said_of = lambda t: ' '.join([str(t.get('text') or ''), *(s.get('text') or '' for s in t.get('steps') or [] if s.get('k') == 'said')])
        by = (made_in(ep(ask['at']) + 0.999) if ask.get('at') else None) or last
        ask = {**ask, 'turn': by['id'], **({'said': True} if flat(ask.get('text')) and flat(ask['text']) in flat(said_of(by)) else {})}
    # ...AND IT IS THE ONE THING ASKED (the owner: a missing fact is one question in the task; recorded on the real CLI, 2026-11-15: under the
    # agent's question stood the reply it could not write yet, captioned with the same question, an empty box over a greyed Send): a reply
    # with no words is not drawn while its agent waits on his answer - the turn his answer begins writes it
    if ask:
        for x in out:
            if x['kind'] == 'turn': x['cards'] = [c for c in x['cards'] if not (c['status'] == 'pending' and c['what'] in DRAFTS and not c.get('was'))]
    # WHERE THE LETTERS THAT WAIT FOR HIS SEND ARE DRAWN: the reply and the task's emails are one block of the page (the reply's card, the
    # emails over it), and the list names its turn - `letters`: the LAST turn that left a letter still waiting, the end of its run. The page
    # hung the block on the newest reply whatever its state, so an email written turns after a reply had gone was drawn up at that reply's
    # card, above everything said since; a turn at work holds the block back as it does its cards
    order = {x['id']: i for i, x in enumerate(out)}
    def run_end(t):
        i = order.get((t or {}).get('id'), -1)
        # ...never into a turn at work (recorded on the real CLI, 2026-11-15; the owner, 2026-11-13: "never close action boxes"): he sent one of
        # two emails, the agent was woken, and for the eleven seconds its turn worked the other email was off the screen - a turn at work
        # shows no block. It keeps its place until that turn has ended, then stands under its words
        while 0 <= i < len(out) - 1 and out[i + 1]['kind'] == 'turn' and (i < 0 or out[i + 1]['state'] not in LIVE or out[i]['state'] in LIVE): i += 1
        return out[i] if i >= 0 else None
    # ...an email is written INSIDE its turn: of two turns a whole-second stamp cannot tell apart, the later one wrote it (the one before had ended)
    wrote = lambda at: next((x for x in reversed(out) if x['kind'] == 'turn' and (x.get('started') or 0) <= at and (x.get('ended') is None or x['ended'] + 1 >= at - 0.999)), None)
    spots = [x for x in out if x['kind'] == 'turn' and any(c['status'] == 'pending' and c['what'] in DRAFTS for c in x['cards'])]
    # ...one that waited its turn (cardqueue) where it came to stand: the turn it was first drawn in, else the newest one past the last input
    def spot(r):
        k = f"r:{r['ReviewId']}"
        if k not in waited: return run_end(wrote(ep(r['CreatedAt']) + 0.999))
        return turn_by.get(hosts.get(k) or (ahead or {}).get('id'))
    spots += [t for r in store._rows("SELECT ReviewId, CreatedAt, DraftText FROM review WHERE TaskId=? AND Kind='slot' AND Status='pending' AND Batch IS NULL", (tid,))
              if str(r.get('DraftText') or '').strip() and r['ReviewId'] not in held | past and (t := spot(r))]
    letters = max(spots, key=lambda t: order.get(t['id'], -1))['id'] if spots else None
    # ...and where its block stands is where each waiting email STOOD, kept as a card's place is (`shown` Host): sent, it stays there
    if letters and turn_by.get(letters, {}).get('state') not in LIVE:
        for r in store._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Kind='slot' AND Status='pending' AND Batch IS NULL", (tid,)):
            if r['ReviewId'] not in held | past and hosts.get(f"r:{r['ReviewId']}") != letters:
                store._exec('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host', (tid, f"c:r:{r['ReviewId']}", letters))
    # THE WAITING ROOM (the owner, 2026-11-12): what waits for the agent is drawn in ONE place until it is heard - his lines as rows over the
    # box, messages as counts on their sender's chip - and `now` says whether a waiting line can be handed into the turn at work at once (a
    # session that takes words mid-turn, not stopped at his Allow); `dropped`: the lines he took back, which leave no trace
    live_ = codingchat._live(tid)
    now = bool(at_work and pend and not perms and live_ is not None and getattr(live_, 'steerable', lambda: False)())
    later = LATER if at_work and any(p['kind'] == 'line' for p in pend) and not getattr(general._live_of(tid), 'hears_mid_turn', lambda: True)() else ''
    dropped = [json.loads(r['Detail'] or '{}').get('line') for r in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action='line_dropped'", (tid,))]
    # A START THAT DID NOT HAPPEN SAYS WHY, WHERE HE LOOKS (the owner's rule 4; recorded on the real CLI, 2026-11-15: the switch off, the task
    # read "waiting to start" over a chat that held only the mail). The reason was written on the task (ingest.not_started) and drawn nowhere:
    # it stands under the chat while nothing has worked the task and nothing is at work - never over a stranger's hold, which says its own.
    # Beside the list, not an item of it: a chat's items never leave it, and this line is true only until a turn begins
    idle = None
    if not at_work and not hold_ and not pend and task_.get('Status') not in ('done', 'dropped') and out and all(x['kind'] == 'arrival' for x in out):
        from .ingest import NOT_STARTED
        why = next((c for c in reversed(store.list_comments(tid, internal=True)) if str(c.get('Body') or '').startswith(NOT_STARTED)), None)
        if why: idle = f"{why['Body']} {START_BY_WRITING}"
    # ...HIS FIRST LINE ON A REPORT HE SENT ON CARRIES ITS NAME (the owner, 2026-11-17: "it says report name then your prompt"): the report is the
    # pill in his bubble, as it was on the box he typed it in - and the report itself on the task's Came from
    if (task_.get('Source') == 'report') and (first := next((x for x in out if x['kind'] == 'line'), None)):
        m = next(iter(store.list_messages(tid)), None) or {}
        if (name := str(m.get('SourceName') or m.get('Subject') or '').strip()): first['came'] = name
    body = {'items': out, 'pending': pend, 'now': now, 'later': later, 'dropped': [d for d in dropped if d], 'working': at_work, 'started': t0 if at_work else None, 'asking': ask,
            'permissions': perms, 'live': codingchat.live_of(codingchat._live(tid)),
            'letters': letters, 'idle': idle,
            # ...and the line of cards (cardqueue): which one stands, which wait behind it unseen, and what the one standing says of them
            'queue': {'live': queue['live'], 'held': queue['held'], 'line': cardqueue.line(queue)}, 'hold': hold_ and {**{k: hold_[k] for k in ('line', 'person', 'org')},
                              **({'line': origin.JOINED_LINE.format(who=hold_['who'])} if any(x['kind'] == 'turn' for x in out) else {})}, 'published': published, 'ran': bool(turn_of) or any(x['kind'] == 'turn' for x in out)}
    # ...hashed in the order it is built - the same every time - not sorted: sorting every step's keys was seconds a poll on a long session
    return {'rev': hashlib.sha1(json.dumps(body, default=str).encode()).hexdigest()[:16], **body}


LIVE = ('working', 'starting')
WENT = ('approved', 'edited', 'sent')       # a letter that left on his press
def flow_breaks(got: dict, was: dict = None) -> list:
    """THE BASIC FLOW OF A CHAT, AS INVARIANTS OVER ITS LIST (the owner, 2026-11-12: "It's a chat with prompts and agent turns, nothing ever goes
    backwards") - pure structure, no meaning judged. `got`: a list `items` served; `was`: the one served before it, for what may never change
    between two. Each break is one sentence; [] is a list a person would expect. Every corpus that builds lists runs it (tests/conftest.py).
    a his newest line has no turn at work above it, and the turn it began under it while one works
    b one live card per action, and no card above his newest line still pressable - nor a reply draft above a newer message (the owner,
      2026-11-12: the live action is always the last thing; one he wrote past greys in place and the agent raises it again if still needed)
    c nothing on the canvas goes: every item and every card of the list before is in this one
    d nothing is drawn empty
    e "working" is one fact: one turn at work, the last one, exactly when the list says working
    f nothing is drawn above what was there, and nothing that was there changes place; a past turn's words never change
    g a turn at work draws no card (its card comes when it has ended, as its last thing); a step it is stopped at is its permission
    h an input is in exactly one place: waiting (`pending`) or on the canvas, never both, and one that leaves the waiting room is on the
      canvas in the same read - unless he took it back (`dropped`)"""
    xs, out = got.get('items') or [], []
    say, ids = out.append, [x['id'] for x in xs]
    live = lambda x: x['kind'] == 'turn' and x.get('state') in LIVE
    his = max((i for i, x in enumerate(xs) if x['kind'] == 'line'), default=-1)
    # a
    for x in xs[:max(his, 0)]:
        if live(x): say(f"a: the turn at work {x['id']} stands above his newest line {ids[his]}")
    if his >= 0 and got.get('working') and not any(live(x) for x in xs[his + 1:]): say(f"a: his newest line {ids[his]} has no turn at work under it")
    # b
    cards = [(i, c) for i, x in enumerate(xs) for c in ([x] if x['kind'] == 'card' else x.get('cards') or [] if x['kind'] == 'turn' else [])]
    lit = [(i, c) for i, c in cards if c.get('status') == 'pending']
    for r in {c['review'] for _, c in lit if [d['review'] for _, d in lit].count(c['review']) > 1}: say(f'b: review {r} stands as two live cards')
    came = max((i for i, x in enumerate(xs) if x['kind'] in ('line', 'arrival')), default=-1)
    for i, c in lit:
        if i < came and c.get('what') in DRAFTS or i < his: say(f"b: the live card {c['id']} stands above a newer input {ids[came]}")
    # d
    for x in xs:
        k = x['kind']
        if (k == 'turn' and not live(x) and not (x.get('text') or x.get('steps') or x.get('cards') or x.get('fail') or x.get('summary'))
                or k == 'line' and not (str(x.get('text') or '').strip() or x.get('files'))
                or k == 'arrival' and not (str(x.get('words') or '').strip() or x.get('files'))
                or k in ('note', 'press') and not str(x.get('text') or '').strip()): say(f'd: {x["id"]} is drawn empty')
    # e
    at = [x for x in xs if live(x)]
    if len(at) > 1: say(f"e: {len(at)} turns at work: {', '.join(x['id'] for x in at)}")
    if at and not got.get('working'): say(f"e: {at[0]['id']} reads at work and the list says nothing works")
    turns = [x for x in xs if x['kind'] == 'turn']
    if got.get('working') and turns and not live(turns[-1]) and at: say(f"e: the turn at work {at[-1]['id']} is not the last turn")
    # g: a turn at work draws no NEW card - one already on the canvas before it worked stays (never closed under him, 2026-11-13)
    seen = {c['id'] for x in (was or {}).get('items') or [] for c in ([x] if x.get('kind') == 'card' else x.get('cards') or [])}
    for x in at:
        for c in x.get('cards') or []:
            if c['id'] not in seen: say(f"g: the turn at work {x['id']} draws its card {c['id']}")
    # h: ONE PLACE AT A TIME (the owner, 2026-11-12: "it does not show in 2 places"): waiting by the box or on the canvas, never both...
    for i in {p['id'] for p in got.get('pending') or []} & set(ids): say(f'h: {i} waits by the box AND stands on the canvas')
    if was is None: return out
    # ...and never neither: what left the waiting room is on the canvas in the same read, unless he took it back
    gone = {p['id'] for p in was.get('pending') or []} - {p['id'] for p in got.get('pending') or []} - set(ids) - set(got.get('dropped') or [])
    for i in sorted(gone): say(f'h: {i} left the waiting room and is nowhere')
    # c, f
    old = [x for x in was.get('items') or []]
    now, by = {x['id']: i for i, x in enumerate(xs)}, {x['id']: x for x in xs}
    for x in old:
        if x['id'] not in now and not (live(x) and not (x.get('text') or x.get('steps'))): say(f"c: {x['id']} was on the canvas and is gone")
    # ...but a card still waiting for his press that the turn now at work holds back (it goes on from the turn that left it - `items`)
    had = {c['id']: c for x in old for c in ([x] if x['kind'] == 'card' else x.get('cards') or [] if x['kind'] == 'turn' else [])}
    for c in had.keys() - {c['id'] for _, c in cards}:
        if not (at and had[c].get('status') == 'pending'): say(f'c: the card {c} was on the canvas and is gone')
    kept = [x['id'] for x in old if x['id'] in now]
    if [i for i in ids if i in set(kept)] != kept: say('f: items already drawn changed their order')
    top = max((now[i] for i in kept), default=-1)
    for x in xs[:max(top, 0)]:
        if x['id'] not in {y['id'] for y in old}: say(f"f: {x['id']} is drawn above {ids[top]}, which was already there")
    for x in old:
        y = by.get(x['id'])
        if y and x['kind'] == 'turn' and not live(x) and str(x.get('text') or '') != str(y.get('text') or ''): say(f"f: the words of the past turn {x['id']} changed")
    return out


# WHAT CODE CAN SEE OF THE AGENT'S WORDS (the owner's rule 8, 2026-11-12: "agent wording should be fixed everywhere"): structure only, never
# a word list that judges meaning - an id this app mints, the owner named to his face, and a card's own words said again above it. Read by
# the recorded walks' check and the unit test over recorded shapes; the model's meaning is the model's
MINTED = re.compile(r'\b(?:TQ-\d{3,}|rv\d+|m-?\d+)\b|\((?:review|mail|message) #?\d+\)|\b(?:mail|message|review) #\d+\b')
QUOTED_WORDS = 12                          # a run of this many of a card's words in the turn above it is the card said again
def odd_words(store, tid: int, got: dict = None) -> list:
    "[(turn id, what)] for each agent turn of task `tid`'s list that names a minted id, says the owner's name, or quotes its own card."
    from .welcome import first_name
    me = first_name(str(store.get_setting('owner_name') or '')) if hasattr(store, 'get_setting') else ''
    flat = lambda s: re.sub(r'[^\w\s]', ' ', str(s or '').lower()).split()
    out = []
    for x in (got or items(store, tid))['items']:
        if x['kind'] != 'turn' or not (said := str(x.get('text') or '')): continue
        out += [(x['id'], f'names {m.group(0)!r}') for m in MINTED.finditer(said)]
        if me and re.search(rf'\b{re.escape(me)}\b', said): out.append((x['id'], f'calls the owner {me!r} to his face'))
        w = ' '.join(flat(said))
        for c in x.get('cards') or []:
            body = flat((store.get_review(c['review']) or {}).get('DraftText')) if c.get('review') else []
            if any(' '.join(body[i:i + QUOTED_WORDS]) in w for i in range(0, max(0, len(body) - QUOTED_WORDS + 1))):
                out.append((x['id'], f"quotes its card {c['review']}"))
    return out
