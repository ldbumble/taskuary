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
import hashlib, json, time
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
    from .selfclose import asked_inline, without_summary
    t = str(text or ''); out = asked_inline(without_summary(t))[0].strip()
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
        for k, r in refs:
            n += store.cx.execute('INSERT OR IGNORE INTO heard (TaskId,Kind,Ref,At,Grp,Seq,Sid) VALUES (?,?,?,?,?,?,?)', (tid, k, r, now, grp, seq, sid or '')).rowcount
        store.cx.commit()
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
    for s in out: s.pop('open', None); s.pop('mid', None)
    return out


# ── the list ─────────────────────────────────────────────────────────────────────────────────────
def _session_steps(store, tid: int) -> list:
    "Every coding session of the task, oldest first: (sid, live, its steps in the one shape, each with `T`)."
    from . import codingchat
    out = []
    for s in codingchat.owned(store, tid, codingchat.sessions(store, tid, local=False)):
        steps, t = acp_steps(s['updates']) if s.get('source') == 'acp' else [dict(x) for x in s.get('steps') or []], ep(s.get('at'))
        for x in steps: t = x['T'] = max(t, ep(x.get('at')))          # a record reads in its own order: a step with no time is at the one before it
        out.append((s['sid'], bool(s.get('live')), steps))
    return out


def _card(r) -> dict:
    return {'id': f"r:{r['ReviewId']}", 'kind': 'card', 'review': r['ReviewId'], 'what': r['Kind'], 'status': r['Status'], 'at': r['CreatedAt'], 'decided': r.get('DecidedAt')}


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
    led = {(r['Kind'], r['Ref']): r for r in store._rows('SELECT * FROM heard WHERE TaskId=? ORDER BY HId', (tid,))}
    era = min((r['At'] for r in led.values()), default=INF)
    marks = [r for (k, _), r in led.items() if k == 'turn']
    pend, ev = [], []                              # ev: (when, rank - an input before the work it began, order, entry)
    put = lambda t, rank, e, hid=0: ev.append((t, rank, hid, len(ev), e))        # ...and what one hand-over took, in the order it took it

    # the comments are one chain, in the order they were filed: his lines, Taskuary's briefs (never drawn - a turn begins there), the answers
    rows, kept = store.list_comments(tid, internal=True), {c['CommentId']: c for c in general.chat_rows(store, tid)}
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
                last = max(last + 1e-7, ep(c['CreatedAt'])); put(last, 0, {'id': f'n:c{cid}', 'kind': 'note', 'at': c['CreatedAt'], 'text': body}); continue
            began = max((m['At'] for m in marks if m['Seq'] < cid), default=0.)
            last = max(last + 1e-7, began)
            st = _said(steps_of.get(cid, []), body)
            t = {'kind': 'turn', 'at': stamp(began) or c['CreatedAt'], 'state': 'done', 'steps': st, 'text': body, 'cards': [], 'started': began or None,
                 'ended': ep(c['CreatedAt']), 'answer': f'comment-{cid}', **({'summary': summ[cid]} if cid in summ else {})}
            # ...and each draft this turn left that a later turn rewrote: greyed where it stood, never moved
            newest = {s['review']: k for k, ss in snaps.items() for s in ss}
            t['cards'] = [{'id': f"r:{s['review']}:c{cid}", 'kind': 'card', 'review': s['review'], 'what': 'draft_reply', 'status': 'superseded', 'at': s['at'], 'was': s}
                          for s in snaps.get(cid, []) if newest.get(s['review']) != cid]
            turn_of[cid] = t; put(last, 1, t)

    # a chat agent's turn at work: under what it was given, its steps as they come
    ses = general.session_for(tid)
    if ses is not None and getattr(ses, 'busy', False):
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
                put(s['T'], 0, {'id': f'y:{sid}:{i}', 'kind': 'line', 'at': stamp(s['T']), 'text': s.get('text') or '', 'files': []})
            else: put(s['T'], 1, {'kind': 'step', 'sid': sid, 'seg': n, 'step': {k_: v for k_, v in s.items() if k_ != 'T'}, 'T': s['T']})

    # what came in, and what he pressed: at the moment the agent heard it, else at its own time
    waits = min((x.pop('_after') for x in pend), default=INF)
    began = (t0 or max((r['At'] for r in led.values()), default=0.) or INF) if at_work else INF
    for x in _mail(store, tid):
        # ...the task's OWN row (ownwork.ensure: his ask, filed as the task was made) never "came in": it is drawn only where the chat has nothing else
        if (x.get('Channel') or '') == ownwork.CHANNEL and ev: continue
        h, it = led.get(('mail', str(x['MessageId']))), None
        row = general.mail_row(store, x)
        it = {'id': f"m:{x['MessageId']}", 'kind': 'arrival', **row, 'joined': stamp(x['T']), **({'_hm': h['At']} if h else {})}
        # ...a stamp is a whole second: one that joined in the turn's first second came in under it (it stood ABOVE the turn at work)
        # ...and one that came in while a line of his waits by the box waits there with it: drawn at once, the line entered above it when
        # both were heard, in the order they came (the recorded flood on a pane, 2026-11-11)
        # ...and what an untrusted sender wrote on a thread an agent works: it waits, behind the Trust action (origin.hold)
        if not h and (at_work and x['T'] + 1 > began or x['MessageId'] > waits or (hold_ and x['MessageId'] in hold_['mids'] and (turn_of or live_sid))): pend.append(it)
        else: put(h['At'] if h else x['T'], 0 if h else -1, it, h['HId'] if h else 0)
    stop = f"You {general.PRESSES['stopped_turn']({})}."
    for m in general.press_lines(store, tid):
        aid, text = m['id'].split('-')[1], m['content'][0]['text']
        h, it = led.get(('press', aid)), {'id': f'p:{aid}', 'kind': 'press' if m.get('press') else 'note', 'at': m['createdAt'], 'text': text, **({'stop': True} if text == stop else {})}
        if not h and at_work and ep(m['createdAt']) + 1 > began and m.get('press') and text != stop: pend.append(it)
        else: put(h['At'] if h else ep(m['createdAt']), 0 if h else -1, it, h['HId'] if h else 0)

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
    halted = bool(tail and tail['kind'] == 'turn' and any(x.get('stop') for x in out[out.index(tail):]))
    if halted:
        at_work = bool(pend)
        if tail['state'] in ('working', 'starting'): tail.update(state='done', ended=tail.get('ended') or time.time())
    # ...A TURN IS MADE ONCE, AT ITS HAND-OVER: the live session's last turn is the one at work only where its work came after the newest
    # hand-over - one that ended before it is finished, and the turn now beginning stands under it (a wake after a press marked the answer
    # above "working" again, and the card under it lost its place)
    mark = max((m['At'] for m in marks), default=0.)
    mine = not halted and tail and tail['kind'] == 'turn' and (tail['state'] == 'working' or tail.get('sid') == live_sid and live_sid and (tail.get('ended') or INF) >= mark - 0.01)
    if at_work and not mine:
        began_ = t0 or max(mark if tail and tail['kind'] == 'turn' and mark >= (tail.get('ended') or 0) else 0., (tail or {}).get('_h') or (tail or {}).get('_hm') or 0.) or time.time()      # from its hand-over, where one is written
        out.append(tail := {'kind': 'turn', 'at': stamp(began_), 'state': 'starting', 'steps': [], 'text': '', 'cards': [], 'started': began_, 'ended': None})
    elif at_work and tail['state'] != 'working': tail.update(state='working', ended=None, started=t0 or tail['started'])
    # ..."WORKING" IS ONE FACT, the one the task's header reads: where it is false no turn spins
    if not at_work:
        for x in out:
            if x['kind'] == 'turn' and x['state'] in ('working', 'starting'): x.update(state='done', ended=x.get('ended') or x.get('started'))
    # ...a turn he stopped ended there, and one that failed says so where it failed, with the way past it
    for i, x in enumerate(out):
        # ...the turn right above his stop - one stopped before it said or did anything left nothing, and the mark fell on the finished answer
        # above the line it never got to answer (the recorded stop, 2026-11-11)
        if x.get('stop') and (t := next((y for y in reversed(out[:i]) if y['kind'] in ('turn', 'line', 'arrival')), None)) and t['kind'] == 'turn' and t['state'] == 'done': t['state'] = 'stopped'
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
            x['id'] = f't:{anchor}:{n}'; n += 1
            for k in ('seg',): x.pop(k, None)
        else:
            if x['kind'] in ('line', 'arrival', 'press'): anchor, n = x['id'], 0
        if x['id'] in seen: x['id'] += f":{len(seen)}"
        seen.add(x['id'])

    # A TURN'S CARDS STAND LAST IN IT: each action under the turn that set it up (the one that last left a draft as it stands), else where it was made
    # ...the turn that was at work when a thing was made: the first one that had begun (where its start is known) and had not yet ended
    made_in = lambda at: next((x for x in out if x['kind'] == 'turn' and (x.get('ended') is None or x['ended'] + 1 >= at - 0.999) and (x.get('started') or 0) <= at), None)
    # ...and each page it showed or published, by that same rule, named by its turn (`after`: the page's key for a turn); None: at the foot
    from . import outputs
    published = [{**p, 'after': (t.get('answer') or t['id']) if (t := made_in(ep(p.get('created_at')) + 0.999)) else None} for p in outputs.pages(store, tid)]
    def place(card, at, cid=None):
        t = (turn_of.get(cid) if cid else None) or made_in(at)
        if t is None:
            i = max((j for j, x in enumerate(out) if ep(x.get('started') or x.get('at')) <= at), default=-1)
            if i >= 0 and out[i]['kind'] == 'turn': t = out[i]
            else: out.insert(i + 1, card); return
        t['cards'].append(card)
    for r in store._rows("SELECT * FROM review WHERE TaskId=? AND Kind<>'slot' ORDER BY ReviewId", (tid,)):
        if r['Kind'] in ('draft_reply', 'draft') and r['Status'] == 'pending' and not str(r.get('DraftText') or '').strip() and not r.get('DraftError'): continue
        left = None if r['Kind'] == 'action' else wrapup.left_by(store, r['ReviewId'])
        place(_card(r), ep(r['CreatedAt']) + 0.999, (left or {}).get('CommentId'))

    # THE NEXT THING TO PRESS IS RIGHT ABOVE THE BOX (the recorded walk, 2026-11-11: the agent said "check the card before you press Send" of a
    # card a screen above its words): an action still live after a later turn ended is one that turn KEPT - each turn is told what waits and
    # takes back what it undoes - so it stands last in the newest turn that said something, and where it stood says so, greyed
    # ...and one he pressed stays where it stood when he pressed it: under the newest answer of that moment, never back where it was first made
    said = [(i, x) for i, x in enumerate(out) if x['kind'] == 'turn' and x['state'] in ('done', 'stopped') and (x['text'] or x['steps'])]
    def under(i, card):
        "The newest answer after place `i` that had ended by the time the card was decided (now, while it waits) - None: it stands where it is."
        lim = INF if card['status'] == 'pending' else ep(card.get('decided')) if card.get('decided') else -1
        # ...a press is stamped by the whole second: an answer that ended in that second stood there, the turn the press began ends after it
        return next((t for k, t in reversed(said) if k > i and int(t.get('ended') or 0) <= lim), None)
    moves = []
    for i, x in enumerate(out):
        for card in ([x] if x['kind'] == 'card' else x['cards'] if x['kind'] == 'turn' else []):
            if card['status'] not in ('superseded',) and (t := under(i, card)): moves.append((i, x, card, t))
    for i, x, card, t in moves:
        # ...where it stood says so, greyed, under the same name: nothing drawn goes away
        if x['kind'] == 'card': out[i] = {**x, 'status': 'kept'}; t['cards'].append({**card, 'id': card['id'] + ':live'})
        else: x['cards'] = [{**c, 'id': c['id'] + ':k', 'status': 'kept'} if c is card else c for c in x['cards']]; t['cards'].append(card)

    for x in out: x.pop('stop', None); x.pop('_h', None); x.pop('_hm', None)
    # ...and what the agent waits on him for, and the CLI that runs: read by the page off this one list (the chat's own payloads are gone)
    from . import permissions, taskstate
    live = general._live_of(tid)
    body = {'items': out, 'pending': pend, 'working': at_work, 'started': t0 if at_work else None,
            'asking': taskstate.asking(store, store.get_task(tid) or {'TaskId': tid}, general.session_for(tid) or (live if codingchat._live(tid) else None)),
            'permissions': permissions.pending(tid, store), 'live': codingchat.live_of(codingchat._live(tid)),
            'hold': hold_ and {k: hold_[k] for k in ('line', 'person', 'org')}, 'published': published, 'ran': bool(turn_of) or any(x['kind'] == 'turn' for x in out)}
    return {'rev': hashlib.sha1(json.dumps(body, sort_keys=True, default=str).encode()).hexdigest()[:16], **body}
