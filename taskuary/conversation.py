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
import hashlib, json, re, time
from datetime import datetime

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


def clean(text) -> str:
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
def _said(steps: list, body: str = '') -> list:
    "A turn's steps with its words cleaned (clean) - and a step that says only what the turn's answer says, or nothing, left out."
    from .chatformat import plain_text
    out = []
    for s in steps:
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


def hear(store, tid: int, lines=(), turn: bool = False, sid: str = '', standing: bool = False) -> int:
    """THE ONE HAND-OVER. Called ONCE at the moment a road gives the agent its input: `lines` - his lines it takes now, as they waited
    (store.take_lines' rows), or the name (LineId) of one sent this moment; `turn` - a turn begins, and with it the agent is told everything
    that came in or was pressed since its last one (general.turn_facts), so those are heard here too, and the turn's own start is marked.
    `standing`: a line that begins a turn at the press - what already stood in the chat unheard is heard with it, before it, so nothing
    drawn moves under his line. Each input once, whoever calls and however often. -> how many were new.
    WHAT ONE HAND-OVER TAKES STANDS IN THE ORDER IT CAME (the recorded flood, 2026-11-11: his lines were written down first, then his own
    replies, then the sender's mail in the order triage got through them - "34, 31, 46"): by each one's own time, and inside one second - a
    stamp is no finer - by the order the store took them in: a line knows the newest message that was there when it was typed.
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
        refs += [((0, x['T'], x['MessageId']) if x['MessageId'] <= first else (1, int(ep(x.get('SentAt') or x.get('CreatedAt')) or x['T']), x['MessageId'], 0, x['MessageId']),
                  'mail', str(x['MessageId'])) for x in _mail(store, tid) if x['T'] >= since]
        # ...a press stands where he made it (his stop is drawn the moment it is pressed): the lines that waited enter under it
        refs += [((0, ep(p[1]), i), 'press', str(p[0])) for i, p in enumerate(general.presses(store, tid)) if ep(p[1]) >= since]
    refs += [((1, int(ep(x.get('CreatedAt'))), _after(x.get('Body')), 1, x['CommentId']), 'line', str(x.get('LineId') or '')) if isinstance(x, dict) else ((2, i), 'line', str(x))
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
    joined = {str(x['MessageId']): x['T'] for x in _mail(store, tid)} if any(k == 'mail' for k, _ in new) else {}
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


TOOK_BACK = 'Asked for the sign-in details, then took that back: a sign-in is done on the page, never in the chat.'
def take_back(store, tid: int, said: str = None, why: str = '', since: float = 0.) -> None:
    """AN ANSWER THAT WAS ONLY A STEP ON THE WAY IS A STEP OF THE WORK, NEVER AN ANSWER (the recorded sign-in walks, 2026-11-11): one its agent
    is made to take back - it asked him for the password, was woken to open the sign-in page instead, and the ask stood in the chat above the
    page it opened - and one that only handed Taskuary a sign-in the saved one then did ("once you have signed in..." over a sign-in nobody
    was asked for; `why`: the line that says what happened instead, `since`: only an answer filed from then on). Marked by the answer's own
    row - or, read before that row is filed, as the next answer after the newest row - and drawn by `items` as that turn's work with one
    line in place of the words, the turn that goes on under it."""
    from .general import ASSISTANT_TYPE
    rows = store.list_comments(int(tid), internal=True)
    c = next((c for c in reversed(rows) if c.get('ActorType') == ASSISTANT_TYPE), None)
    if said is None:
        if not c or ep(c['CreatedAt']) < since - 1: return
        ref = str(c['CommentId'])
    else: ref = str(c['CommentId']) if c and str(c.get('Body') or '')[:4000] == said[:4000] else f">{max((r['CommentId'] for r in rows), default=0)}"
    store._exec('INSERT OR IGNORE INTO heard (TaskId,Kind,Ref,At,Grp,Seq,Sid) VALUES (?,?,?,?,?,?,?)', (int(tid), 'back', ref, time.time(), 0, 0, why))
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
_ARGS = ('command', 'cmd', 'pattern', 'query', 'url', 'file_path', 'path', 'filePath', 'absolute_path', 'description', 'prompt', 'glob', 'title', 'subagent_type')
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
    from . import codingchat
    out = []
    for s in codingchat.owned(store, tid, codingchat.sessions(store, tid, local=False)):
        steps, t = acp_steps(s['updates']) if s.get('source') == 'acp' else [dict(x) for x in s.get('steps') or []], ep(s.get('at'))
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
    failed = r['Status'] == 'superseded' and r.get('DecideNote') in (FAILED, NOT_RUN)
    # ...A DRAFT ITS AGENT TOOK BACK STAYS WHERE IT STOOD, greyed, with its words (the owner's live task, 2026-11-12: he wrote again, the agent
    # withdrew its reply in the turn that answered him, and the card went from the chat - no page draws a draft "closed unsent")
    # ...and one set aside as he wrote past it (proposals.set_aside_drafts) the same way: a draft is its words, which the page draws greyed
    words = str(r.get('DraftText') or '').strip() if r['Kind'] in DRAFTS else ''
    # ...and an action's is what it would do (its proposal's own words) - so one he wrote past is drawn greyed with them, in the frame he wrote
    if r['Kind'] == 'action':
        try: d = json.loads(r.get('DraftText') or '{}') or {}
        except (TypeError, ValueError): d = {}
        words = ' '.join(str((d.get('what') or d.get('command') or r.get('Reason') or '') if isinstance(d, dict) else r.get('Reason') or '').split())[:300]
    gone = r['Status'] == 'closed_unsent' and str(r.get('DecideNote') or '').startswith(WITHDRAWN) and words
    st = 'passed' if passed(r) else 'failed' if failed else 'withdrawn' if gone else r['Status']
    return {'id': f"r:{r['ReviewId']}", 'kind': 'card', 'review': r['ReviewId'], 'what': r['Kind'], 'status': st,
            'at': r['CreatedAt'], 'decided': r.get('DecidedAt'), **({'was': {'text': words if r['Kind'] == 'action' else r['DraftText']}} if words and st in ('passed', 'withdrawn', 'pending') else {})}
DRAFTS = ('draft_reply', 'draft')


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


def items(store, tid: int) -> dict:
    "The task's conversation: {rev, items, pending, working, started} - see the module's head."
    from . import codingchat, funnel, general, ownwork, sessionrecord, wrapup
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
    marks = [r for (k, _), r in led.items() if k == 'turn']
    backs = [int(r[1:]) for k, r in led if k == 'back' and r[:1] == '>']      # an answer taken back before its row was filed (take_back)
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
            body = general._line_of(c['Body']) if ty == WAITING_TYPE else {'text': c.get('Body') or '', 'files': []}
            it = {'id': c.get('LineId') or f'c:{cid}', 'kind': 'line', 'at': c['CreatedAt'], **body}
            h = led.get(('line', c.get('LineId') or ''))
            if not h and ty == WAITING_TYPE: pend.append({**it, '_after': _after(c['Body'])}); continue
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
            # ...AN ANSWER NOBODY MARKED THE START OF STANDS AT ITS OWN TIME (every task answered before hand-overs were written down - his
            # older tasks, the demo's): placed at the start of time, it stood above the mail it answered and the chat began with the agent
            last = max(last + 1e-7, began or ep(c['CreatedAt']))
            st = _said(steps_of.get(cid, []), body)
            # ...one it was made to take back (take_back): its words are a step of the work that goes on under it
            # ...and its summary goes with its words (the recorded walk, 2026-11-12: the saved sign-in's folded turn still drew its summary - "Erin
            # asked Alex ...; no reference number has been read yet" - under the note that it had signed in, the owner in the third person)
            took = (('back', str(cid)) in led or any(n < cid for n in backs)) and body
            if took:
                st, body, backs = [*st, {'k': 'note', 'text': (led.get(('back', str(cid))) or {}).get('Sid') or TOOK_BACK}], '', [n for n in backs if n >= cid]
            t = {'kind': 'turn', 'at': stamp(began) or c['CreatedAt'], 'state': 'done', 'steps': st, 'text': body, 'cards': [], 'started': began or None,
                 'ended': ep(c['CreatedAt']), 'answer': f'comment-{cid}', **({'summary': summ[cid]} if cid in summ and not took else {})}
            # ...and each draft this turn left that a later turn rewrote: greyed where it stood, never moved
            newest = {s['review']: k for k, ss in snaps.items() for s in ss}
            t['cards'] = [{'id': f"r:{s['review']}:c{cid}", 'kind': 'card', 'review': s['review'], 'what': 'draft_reply', 'status': 'superseded', 'at': s['at'], 'was': s}
                          for s in snaps.get(cid, []) if newest.get(s['review']) != cid]
            turn_of[cid] = t; put(last, 1, t)

    # a chat agent's turn at work: under what it was given, its steps as they come
    ses = general.session_for(tid)
    # ...never once its answer is filed: the session reads busy for a beat after (recorded 2026-11-12: a second, empty turn spun under the
    # answer for a frame and went) - the turn at work is the one the newest hand-over began, and that one has answered
    done_ = turn_of and turn_of[max(turn_of)]['ended'] >= max((m['At'] for m in marks), default=INF) - 0.01
    if ses is not None and getattr(ses, 'busy', False) and not done_:
        answered = max(turn_of, default=0)
        began = max((m['At'] for m in marks if m['Seq'] >= answered), default=0.) or max(last + 1e-7, getattr(ses, 'last', 0) or 0)
        trace = list(getattr(ses, 'trace', None) or [])
        put(max(last + 1e-7, began), 1, {'kind': 'turn', 'at': stamp(began), 'state': 'working', 'steps': _said(sessionrecord.trace_steps(trace)), 'text': '', 'cards': [],
                                        'started': general.PRESSED.get(tid) or began, 'ended': None, 'sid': getattr(ses, 'sid', '')})

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
        if not h and it['id'] not in was_shown and (at_work and x['T'] + 1 > began or x['MessageId'] > waits or (hold_ and x['MessageId'] in hold_['mids'] and (turn_of or live_sid))): pend.append(it)
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
    shut = (store._one("SELECT Id FROM audit WHERE EntityType='task' AND EntityId=? AND Action='close_from_assistant' ORDER BY Id DESC LIMIT 1", (tid,))
            if (store.get_task(tid) or {}).get('Status') == 'done' else None)
    for m in general.press_lines(store, tid):
        aid, text = m['id'].split('-')[1], m['content'][0]['text']
        h, closes = led.get(('press', aid)), bool(shut) and aid == str(shut['Id'])
        if closes and (note := next((c['note'] for c in reversed(store.closeouts(tid)) if c['what'] == 'closed'), '')): text = f"{text.rstrip('.')} - {note.rstrip('.')}."
        it = {'id': f'p:{aid}', 'kind': 'press' if m.get('press') else 'note', 'at': m['createdAt'], 'text': text, **({'closes': True} if closes else {}),
              **({'stop': True, '_hs': bool(h)} if text == stop else {})}
        if not h and at_work and ep(m['createdAt']) + 1 > began and m.get('press') and text != stop: pend.append(it)
        # ...A PRESS NOBODY HEARD YET STANDS AFTER ALL OF ITS OWN SECOND - its stamp is no finer: a stop pressed in the second its turn's line was
        # heard sorted above that line, and the stop's mark fell on the answer before it (a same-second tie, seen as a flash and a red test)
        else: put(h['At'] if h else ep(m['createdAt']) + 0.999, 0 if h else -1, it, h['HId'] if h else 0)

    # in order - and an input nobody heard never cuts a turn's work in two: it stands after the turn it came in under
    out, held, run = [], [], None
    def close():
        nonlocal run
        run = None; out.extend(held); held.clear()
    for t, rank, _, _, e in sorted(ev, key=lambda x: x[:4]):
        if e['kind'] == 'step':
            if run is None or run['sid'] != e['sid'] or run['seg'] != e['seg']:
                close(); run = {'kind': 'turn', 'sid': e['sid'], 'seg': e['seg'], 'at': stamp(e['T']), 'state': 'done', 'steps': [], 'text': '', 'cards': [], 'started': e['T'], 'ended': e['T']}
                out.append(run)
            run['steps'] += _said([e['step']]); run['ended'] = e['T']
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
        out.insert(0, {'id': f'a:{tid}', 'kind': 'line', 'at': stamp(at), 'text': said, 'files': [], '_h': at})
    # ONE TURN AT WORK, AND IT IS THE LAST (the owner's live task, 2026-11-11: a second head spun under a later, finished answer while the task
    # read done): a turn stands where it began, so one that reads at work with a turn after it has ended - whatever its session still says
    turns_ = [x for x in out if x['kind'] == 'turn']
    for x in turns_[:-1]:
        if x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
    # the turn at work is the last thing in the list: one the agent has not yet said a word in is there too, the moment its input was heard
    tail = next((x for x in reversed(out) if x['kind'] in ('turn', 'line', 'arrival')), None)
    # ...A TURN HE STOPPED IS STOPPED FROM THE PRESS (the recorded stop, 2026-11-11: its CLI took seconds to let go, and all that time the turn
    # spun above "You stopped the agent"): what is at work from there is the turn his waiting lines begin, under the press - with none
    # waiting, nothing is
    # ...UNTIL A TURN BEGINS UNDER THE STOP: one that heard his stop (its hand-over wrote the press down, `hear`) answers what the stopped
    # turn took in and never spoke to (acpcoding._unanswered) - its lines stand above the stop, so no input of its own is under it
    halted = bool(tail and tail['kind'] == 'turn' and any(x.get('stop') and not x['_hs'] for x in out[out.index(tail):]))
    if halted:
        # ...and from the press too where the stopped turn owes him an answer: that turn is on its way, and nothing else says so meanwhile
        at_work = bool(pend) or bool(getattr(general._live_of(tid), 'owes_stop', lambda: False)())
        if tail['state'] in ('working', 'starting'): tail.update(state='done', ended=tail.get('ended') or time.time())
    # ...A TURN IS MADE ONCE, AT ITS HAND-OVER: the live session's last turn is the one at work only where its work came after the newest
    # hand-over - one that ended before it is finished, and the turn now beginning stands under it (a wake after a press marked the answer
    # above "working" again, and the card under it lost its place)
    mark = max((m['At'] for m in marks), default=0.)
    # ...AND A TURN WHOSE ANSWER IS FILED AFTER THE NEWEST HAND-OVER IS THE WORK THAT WAS AT WORK (recorded 2026-11-12: its session still read
    # busy for a beat after the answer was filed, and a second, empty turn stood "starting" under it for a frame and went): nothing new runs
    if at_work and not pend and tail and tail['kind'] == 'turn' and tail['state'] == 'done' and tail.get('answer') and (tail.get('ended') or 0) >= mark - 0.01 \
            and not (t0 and t0 > (tail.get('ended') or 0)): at_work = False
    mine =not halted and tail and tail['kind'] == 'turn' and (tail['state'] == 'working' or tail.get('sid') == live_sid and live_sid and (tail.get('ended') or INF) >= mark - 0.01)
    # ...AND NONE BEFORE THE LINE THAT BEGINS IT IS IN THE LIST (recorded 2026-11-12: a read between take_line's "at work" and its keeping the
    # line drew the new turn's dots under the old answer, his line then under them): a line heard and not yet filed is the input it waits for
    drawn = {x.get('id') for x in out}
    unfiled = any(k == 'line' and r['At'] >= mark - 0.01 and ref not in drawn and ref not in {p['id'] for p in pend} for (k, ref), r in led.items())
    if at_work and not mine and unfiled: pass
    elif at_work and not mine:
        began_ =t0 or max(mark if tail and tail['kind'] == 'turn' and mark >= (tail.get('ended') or 0) else 0., (tail or {}).get('_h') or (tail or {}).get('_hm') or 0.) or time.time()      # from its hand-over, where one is written
        out.append(tail := {'kind': 'turn', 'at': stamp(began_), 'state': 'starting', 'steps': [], 'text': '', 'cards': [], 'started': began_, 'ended': None})
    elif at_work and tail['state'] != 'working': tail.update(state='working', ended=None, started=t0 or tail['started'])
    # ...AND NEVER ABOVE HIS NEWEST LINE (the owner's live task, 2026-11-12: the dots stood over "try now"; recorded on ACP the same day for a
    # frame - the session's record had not yet cut its turn at his line): what works now is the turn his line began, under it
    if at_work and (his := max((i for i, x in enumerate(out) if x['kind'] == 'line'), default=-1)) >= 0:
        for x in out[:his]:
            if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
        if not any(x['kind'] == 'turn' and x['state'] in ('working', 'starting') for x in out[his + 1:]):
            b_ = t0 or out[his].get('_h') or time.time()
            out.append({'kind': 'turn', 'at': stamp(b_), 'state': 'starting', 'steps': [], 'text': '', 'cards': [], 'started': b_, 'ended': None})
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
    if not at_work and (f := funnel.run_failed(store, tid)):
        evf = store.last_worker_event(tid, kinds=('failed',)) or {}
        t = next((y for y in reversed(out) if y['kind'] in ('turn', 'line', 'arrival')), None)
        if not (t and t['kind'] == 'turn'):
            if ep(evf.get('CreatedAt')) >= ep((t or {}).get('at')) - 1: out.append(t := {'kind': 'turn', 'at': evf.get('CreatedAt') or '', 'state': 'failed', 'steps': [], 'text': '', 'cards': [], 'started': None, 'ended': ep(evf.get('CreatedAt'))})
            else: t = None
        if t and (t.get('ended') or 0) <= ep(evf.get('CreatedAt')) + 1: t.update(state='failed', fail=f['sentence'], fix=f.get('fix'))

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
    def place(card, at, cid=None):
        # ...a draft no turn has left yet is new now, whenever its row was made (the recorded walk, 2026-11-12: a reply owed since the mail came
        # was filled in the turn under his line and drawn in the turn of the mail's arrival - live, above his line): it goes in the newest turn,
        # which holds it back while it works
        fresh = card['what'] in DRAFTS and card['status'] == 'pending' and not cid
        t = (turn_of.get(cid) if cid else None) or (newest if fresh and newest else made_in(at))
        h = hosts.get(card['id'])
        # ...down only to a turn that LEFT it again (its record names that turn): a turn begun after it is not one (recorded on ACP, 2026-11-12:
        # the session went on into a second turn and the card, drawn in the first, went from the chat until the second ended)
        if h in turns_at and (t is None or not cid or turns_at.get(t['id'], -1) < turns_at[h]): t = turn_by[h]
        elif t is not None and h != t['id'] and not (t['state'] in LIVE):
            store._exec('INSERT INTO shown (TaskId, Key, Seq, Host) VALUES (?,?,0,?) ON CONFLICT(TaskId, Key) DO UPDATE SET Host=excluded.Host', (tid, f"c:{card['id']}", t['id']))
        if t is None:
            i = max((j for j, x in enumerate(out) if ep(x.get('started') or x.get('at')) <= at), default=-1)
            if i >= 0 and out[i]['kind'] == 'turn': t = out[i]
            else: out.insert(i + 1, card); return
        t['cards'].append(card)
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind<>'slot' ORDER BY ReviewId", (tid,)):
        if r['Kind'] in ('draft_reply', 'draft') and r['Status'] == 'pending' and not str(r.get('DraftText') or '').strip() and not r.get('DraftError'): continue
        left = None if r['Kind'] == 'action' else wrapup.left_by(store, r['ReviewId'])
        place(_card(r), ep(r['CreatedAt']) + 0.999, (left or {}).get('CommentId'))

    # A CARD STANDS WHERE ITS TURN LEFT IT, FOR GOOD (the owner, 2026-11-12: "It's a chat with prompts and agent turns, nothing ever goes
    # backwards"): no card is moved under a later answer, copied there, or left behind as a ghost - he moves on past one by writing again (a
    # draft above his newer line is set aside then, `hear`), and the agent raises what is still owed as a new card in its own turn.
    # ...AND A TURN'S CARD IS DRAWN ONCE THE TURN HAS ENDED, as its last thing (the owner, 2026-11-12: "it should finish thinking and last thing
    # should be show action box" - its words landed above a card drawn while it worked): a step it is stopped at waits on him mid-turn as its
    # permission (`permissions`, drawn under the turn), never as a card in it
    from . import permissions
    perms = permissions.pending(tid, store)
    for x in out:
        if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x['cards'] = []
    # ...A REPLY DRAFT ABOVE A NEWER INPUT IS NOT THE ONE TO PRESS, from the frame that input is drawn (`hear` settles it as the turn takes the
    # input): greyed where it stood - its turn drafts again under the input where a reply is still owed
    # ...and a turn that ended having said, done and left nothing (a CLI turn that only took a line in) is no item: the page drew nothing for it
    out = [x for x in out if not (x['kind'] == 'turn' and x['state'] == 'done' and not (x['text'] or x['steps'] or x['cards'] or x.get('summary')))]

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
    for x in out: x.pop('stop', None); x.pop('_h', None); x.pop('_hm', None); x.pop('_hs', None); x.pop('_seg', None)
    out = served(store, tid, served_back(store, tid, out, was_shown, {p['id'] for p in pend})); keep_shown(store, tid, out, was_shown)
    # (the reply draft above a newer input, greyed - read in the order drawn)
    # (and any card of the agent's above his newer line - every kind, 2026-11-12 - `hear` settles it as his line is heard)
    last_in = max((i for i, x in enumerate(out) if x['kind'] in ('line', 'arrival')), default=-1)
    last_his = max((i for i, x in enumerate(out) if x['kind'] == 'line'), default=-1)
    for i, x in enumerate(out):
        for c in [x] if x['kind'] == 'card' else x['cards'] if x['kind'] == 'turn' else []:
            if c['status'] == 'pending' and c.get('was') and (c['what'] in DRAFTS and i < last_in or i < last_his): c['status'] = 'passed'
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
    # ...a coding turn's words are its `said` steps, its text empty: the demo's #214 drew its closing question twice
    words = last and ' '.join([str(last.get('text') or ''), *(s.get('text') or '' for s in last.get('steps') or [] if s.get('k') == 'said')])
    if ask and last and flat(ask.get('text')) and flat(ask['text']) in flat(words): ask = {**ask, 'said': True}
    # THE WAITING ROOM (the owner, 2026-11-12): what waits for the agent is drawn in ONE place until it is heard - his lines as rows over the
    # box, messages as counts on their sender's chip - and `now` says whether a waiting line can be handed into the turn at work at once (a
    # session that takes words mid-turn, not stopped at his Allow); `dropped`: the lines he took back, which leave no trace
    live_ = codingchat._live(tid)
    now = bool(at_work and pend and not perms and live_ is not None and getattr(live_, 'steerable', lambda: False)())
    dropped = [json.loads(r['Detail'] or '{}').get('line') for r in store._rows("SELECT Detail FROM audit WHERE EntityType='task' AND EntityId=? AND Action='line_dropped'", (tid,))]
    body = {'items': out, 'pending': pend, 'now': now, 'dropped': [d for d in dropped if d], 'working': at_work, 'started': t0 if at_work else None, 'asking': ask,
            'permissions': perms, 'live': codingchat.live_of(codingchat._live(tid)),
            'hold': hold_ and {**{k: hold_[k] for k in ('line', 'person', 'org')},
                              **({'line': origin.JOINED_LINE.format(who=hold_['who'])} if any(x['kind'] == 'turn' for x in out) else {})}, 'published': published, 'ran': bool(turn_of) or any(x['kind'] == 'turn' for x in out)}
    return {'rev': hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16], **body}


LIVE = ('working', 'starting')
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
    # g
    for x in at:
        for c in x.get('cards') or []: say(f"g: the turn at work {x['id']} draws its card {c['id']}")
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
    had = {c['id'] for x in old for c in ([x] if x['kind'] == 'card' else x.get('cards') or [] if x['kind'] == 'turn' else [])}
    for c in had - {c['id'] for _, c in cards}: say(f'c: the card {c} was on the canvas and is gone')
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
