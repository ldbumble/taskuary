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
           s:<TaskId>               head, channel report|dashboard|routine, words - the start nobody typed (started_by)
  line     <the page's LineId> | c:<CommentId>      text, files
  press    p:<audit id>             text - his press, in his voice (general.PRESSES)
  note     n:<...>                  text - one quiet sentence
  turn     t:<the input before it>:<n>   state starting|working|done|stopped|failed, steps, text, cards (last), started, ended, fail
  card     r:<ReviewId>             an action outside any turn
Ids never change once given, so the page keys by them and a turn that ends, or a line that is heard, redraws in place."""
import contextlib, functools, json, re, threading, time
from datetime import datetime
from pathlib import Path

INF = float('inf')


def ep(at) -> float:
    "A stamp as epoch seconds: the store's local 'YYYY-MM-DD HH:MM:SS', a CLI log's ISO with its zone, or a number already."
    if isinstance(at, (int, float)): return float(at)
    s = str(at or '').strip()
    if not s: return 0.
    try: return datetime.fromisoformat(s.replace('Z', '+00:00').replace(' ', 'T', 1)).timestamp()
    except (ValueError, OSError, OverflowError): return 0.      # ...a stamp before the epoch on Windows raises OSError
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
    from .selfclose import asked_inline, for_screen, without_summary
    # ...ONE CLEANER FOR EVERY SURFACE (the agent audit, 2026-11-22: this one left a done line, a show and a tick line and a whole reply block on
    # screen - a coding turn's steps drew "[[TASKUARY-DONE]] Fixed the build" and the letter above its own card - where for_screen took them
    # out): what of an agent's text the owner reads is selfclose.for_screen's - every marker out, a question kept as its words
    # ...the question first made its plain words (asked_inline), so the marker's own line is never wiped with the question on it
    t = str(text or ''); out = for_screen(asked_inline(without_summary(t))[0]).strip()
    if out or not t.strip(): return out
    try: j = json.loads(t[t.index('{'):t.rindex('}') + 1])
    except ValueError: return ''
    return str(j.get('did') or j.get('about') or '').strip() if isinstance(j, dict) else ''
# ...A CLI'S OWN PLUMBING IS NO STEP, by the one list the page reads too (the walks, 2026-11-17: a stopped turn whose only step was ToolSearch
# was kept here for that step and drawn as nothing there - a "1 step" trail for 100 ms, then head and trail gone)
_KINDS = json.loads(Path(__file__).with_name('stepkinds.json').read_text(encoding='utf-8'))
MACHINERY, _OWN_LINE = frozenset(_KINDS['machinery']), re.compile(_KINDS['commands'], re.I)
def _line(x) -> str: return ' '.join(map(str, x)) if isinstance(x, list) else str(x or '')
def machinery(s: dict) -> bool:
    a = s.get('args') if isinstance(s.get('args'), dict) else {}
    # ...and its refusal too (design round 5, 2026-11-19: a tick refused for a missing argument stood in the chat as its schema dump)
    return s.get('k') in ('tool', 'error') and (re.sub(r'[^a-z0-9]', '', str(s.get('name') or '').split('__')[-1].lower()) in MACHINERY
                                     or bool(_OWN_LINE.search(_line(a.get('command') or a.get('cmd')))))


# ...A SENTENCE A TURN ALREADY SAID IS NOT SAID AGAIN AS THE NEXT MESSAGE'S OPENER (design round 5, I3: on Codex every follow-up turn read
# "Paula says the meeting moved up. I'll update the draft..." and then "Paula says the meeting moved up. The summary is ready." - the model
# opens each message of a turn with the same sentence, and both were drawn). Structure, not meaning: the same first sentence, word for word
# ...a sentence ends where the next begins with a capital or the text ends: "at 2 p.m. works." is one (walk 18: cut at "p.m.", its "works." was left)
_LEAD = re.compile(r"""\s*(.+?[.!?])(?=\s+["'(\[*_]*[A-Z]|\s*$)""", re.S)
def _lead(t: str) -> tuple:
    "(its first sentence with its spaces made one, where that sentence ends) - ('', 0) where it has none."
    m = _LEAD.match(t or '')
    # ...and a sentence has words: a list's "1." is none (the goal walk, 2026-11-22: a turn's second message opened "1." as its first had, the
    # "1." was cut as said already, and the list drew as one run-on paragraph - Markdown starts no list at "2.")
    return (' '.join(m.group(1).split()), m.end()) if m and re.search(r'[^\W\d_]{2}', m.group(1)) else ('', 0)
def said_once(t: str, seen: set) -> str:
    """`t` without its opening sentence where `seen` holds it already - and that sentence added to `seen`. A message that opens with a whole
    message said before it goes on from that one's end (walk 18, Codex: one sentence, a tool call, then that sentence again with the rest)."""
    w = t.split()
    if k := max((len(x) for x in map(str.split, seen) if len(x) < len(w) and w[:len(x)] == x), default=0): t = t[re.match(r'(?:\s*\S+){%d}' % k, t).end():].strip()
    lead, end = _lead(t)
    if not lead: return t
    if lead in seen and t[end:].strip(): return t[end:].strip()
    seen.add(lead); return t


_PARA, _RUN = re.compile(r'\n\s*\n'), 40
_OPEN = re.compile(r'\[\[\s*TASKUARY[-_ ]?SUMMARY\s*\]\]', re.I)
_CLOSE = re.compile(r'\[\[\s*/\s*TASKUARY[-_ ]?SUMMARY\s*\]\]', re.I)


def _unsummarized(steps: list) -> list:
    """The said steps read as the one stream they are: a summary block that opens in one and closes in a later one is cut whole. Each step
    cleaned alone drew the block's JSON tail - '"about": ...', '_left": false}' - as the agent's words (walk 2, 2026-11-21, a Codex turn)."""
    out, inside = [], False
    for s in steps:
        if s.get('k') != 'said' or not s.get('text'): out.append(s); continue
        t, keep = str(s['text']), ''
        while t:
            if inside:
                if not (m := _CLOSE.search(t)): t = ''; break
                t, inside = t[m.end():], False
            if (m := _OPEN.search(t)): keep, t, inside = keep + t[:m.start()], t[m.end():], True
            else: keep, t = keep + t, ''
        # ...and a tag cut off at a step's end opens the block the next step goes on with
        from .selfclose import _TAG_STUB
        if not inside and (m := _TAG_STUB.search(keep)): keep, inside = keep[:m.start()], True
        if keep.strip(): out.append({**s, 'text': keep})
    return out


def unsaid(text: str, steps: list) -> str:
    """What of a turn's answer its said steps did not say already - '' when the words it streamed were all of it, the answer whole when they
    said none of it (a road that streams no words). The answer is what is de-duplicated, never the stream (the owner, 2026-11-23)."""
    # ...A FILE IS ITS NAME ON BOTH SIDES (the HIPAA walk, 2026-11-21): the answer names a file it made by its name, the words it streamed by its
    # full path in the task's folder - compared as they stood, every answer that named a file was drawn twice
    named = lambda t: _PATHED.sub(r'\1', _flat(t))
    said = named(' '.join(clean(s.get('text')) for s in steps or [] if s.get('k') == 'said'))
    if not said: return text
    all_ = [p for p in _PARA.split(clean(text)) if _flat(p)]
    ps = [p for p in all_ if named(p) not in said]
    return text if len(ps) == len(all_) else '\n\n'.join(ps)
_PATHED = re.compile(r'(?:[A-Za-z]:)?(?:[\\/][^\s\\/`\'"*()]+)+[\\/]([^\s\\/`\'"*()]+)')      # a path by its grammar: a root, its folders, its last name


def _said(steps: list, body: str = '', seen: set = None) -> list:
    """A turn's steps with its words cleaned (clean) - and a step that says only what the turn's answer says, or nothing, or is machinery, left
    out; each message's opener once (said_once, `seen`: the openers the turn has said - the answer's own read against them after)."""
    out, seen = [], set() if seen is None else seen
    steps = _unsummarized(steps)
    ps, fb = {_flat(p) for p in _PARA.split(body)}, _flat(body)
    for s in steps:
        if machinery(s): continue
        # ...A MODEL'S PRIVATE REASONING IS NO STEP (the owner, 2026-11-23: "it has to say what is actually going on" - "Locating account menu",
        # "Awaiting final approval" stood in italics among what it did): the chat shows what happened and what the agent said; its own notes stay in
        # its record (sessionrecord), and the one being written is the working line's while it is the newest thing (chatlog._now `thinking`)
        if s.get('k') == 'thought': continue
        if s.get('k') != 'said': out.append(s); continue
        # ...WHAT THE ANSWER SAYS IS THE ANSWER'S, drawn once (design round 6, D2: on the Claude CLI a turn's messages streamed as steps and the
        # answer joined them - each paragraph drawn twice, the answer's opener cut as "said already"): a paragraph of a step the answer holds
        # - one of its paragraphs, or a longer run of its words (a message cut mid-word by a line he typed) - is left out, and is no opener seen
        if not (w := '\n\n'.join(p for p in _PARA.split(clean(s.get('text'))) if (f := _flat(p)) and not (f in ps or len(f) >= _RUN and f in fb))): continue
        # ...and a message the turn already said, word for word, is drawn once (walk 11: one sentence sent as two messages around end_turn)
        if (f := ' '.join(w.split())) in seen: continue
        out.append({**s, 'text': said_once(w, seen)}); seen.add(f)
    return out


# ── the ledger ───────────────────────────────────────────────────────────────────────────────────
_ONCE = threading.local()


@contextlib.contextmanager
def mail_once():
    "Inside it, this thread reads a task's mail once (_mail): one read of the chat asked it twice, a 2,000-line chat's 2,000 rows each time."
    was = getattr(_ONCE, 'got', None); _ONCE.got = {} if was is None else was
    try: yield
    finally: _ONCE.got = was


def _mail(store, tid: int) -> list:
    "Every message on the task's thread the chat draws (general.JOINED, and his own lines filed elsewhere), each with `T`: when it joined."
    if (got := getattr(_ONCE, 'got', None)) is None: return _mail_(store, tid)
    if (k := (id(store), int(tid))) not in got: got[k] = _mail_(store, tid)
    return [dict(x) for x in got[k]]


def _mail_(store, tid: int) -> list:
    from . import general
    rows = [*store._rows(general.JOINED, (tid,)), *general.room_own(store, tid)]
    # ...BUT NEVER THE SENT-FOLDER COPY OF A LETTER TASKUARY SENT ON HIS PRESS (walk 13: every send drawn twice - the "Sent" card, then the
    # same mail again as "You · by email"): that copy IS the card's send, drawn once by the card, and no input to the agent either (events.py)
    if any(x.get('Own') for x in rows): mine = general.went_from_here(store, tid); rows = [x for x in rows if not (x.get('Own') and mine(x))]
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
# THE START NOBODY TYPED IS AN INPUT TOO (the owner, 2026-11-18 on a routine's run and 2026-11-19 on a report: the box wore "Report · ..." and the
# chat began with the agent's turn - nothing said what started it): a routine's run, a report's or a dashboard's run that started its agent,
# drawn at the top as an arrival is - where it came from, named, and what the agent was asked. Read from the task's own facts, never a model
def started_by(store, t: dict) -> dict | None:
    "{head, channel, words} for task `t` begun by a routine or a report/dashboard run - None where a person's message or his words began it."
    if not t: return None
    if t.get('Source') == 'workflow':
        from . import workflows
        src = workflows.source_of(store, t)
        d = workflows.definition(store, src) if src else {}
        name = d.get('title') or str(t.get('Title') or '').rsplit(' - ', 1)[0]
        said = d.get('objective') or (f"Run the saved skill /{d['skill']}" if d.get('skill') else '')
        return {'head': f'From the routine {name}', 'channel': 'routine', 'words': said}
    m = next((m for m in store.list_messages(t['TaskId']) if (m.get('Channel') or '') == 'report'), None) if t.get('Source') == 'report' else None
    if not m: return None
    from .dashboards import is_dashboard
    sid = str(m.get('ConversationId') or '').partition('report:')[2]
    src = store.get_source(int(sid)) if sid.isdigit() else None
    try: dash = is_dashboard(json.loads((src or {}).get('ConfigJson') or '{}'))
    except ValueError: dash = False
    kind, name = 'dashboard' if dash else 'report', str(m.get('SourceName') or m.get('Subject') or '').strip()
    # ...what it was asked: the job its start read off the run (the task's own ask), else what the run said
    said = _flat(t.get('Summary')) or _flat(m.get('Subject')) or name
    return {'head': f'From the {kind} {name}'.strip(), 'channel': kind, 'words': said}


def came(x: dict) -> tuple:
    """WHEN AN INPUT CAME - one key for a message and a line of his alike: its second (a stamp is no finer), then inside it the order the store
    took them in - a message by its id, a line after the newest message there when it was typed (_after). A message by when it CAME - the
    store took it, or he sent his own - never its sender's clock, nor when triage put it here, which a flood finishes out of order."""
    if 'MessageId' in x: return (int(ep((x.get('SentAt') if x.get('Own') else None) or x.get('CreatedAt')) or x.get('T') or 0), x['MessageId'], 0, x['MessageId'])
    return (int(ep(x.get('CreatedAt'))), _after(x.get('Body')), 1, x['CommentId'])


def hear(store, tid: int, lines=(), turn: bool = False, sid: str = '', standing: bool = False) -> int:
    """THE ONE HAND-OVER. Called ONCE at the moment a road gives the agent its input: `lines` - his lines it takes now, as they waited
    (store.take_lines' rows), or the name (LineId) of one sent this moment; `turn` - a turn begins, and with it the agent is told everything
    that came in or was pressed since its last one (its events, events.take), so those are heard here too, and the turn's own start is marked.
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
    # ...and written into the chat's log, in the order it was taken: its place there for good (chatlog.heard)
    if new:
        from . import chatlog
        chatlog.heard(store, tid, new, now)
    # ...a line of his, or a message, heard is the conversation moving past any reply draft that waited above it (proposals.set_aside_drafts):
    # the turn that hears it drafts again under it where a reply is still owed (the rail walk, 2026-11-12: the sender wrote again, and the
    # draft to refresh stood above her new mail)
    # ...a draft written after that message is its answer, never set aside by it: older than the input, by the input's own time
    # ...and a letter Taskuary sent on his press, come back from his Sent folder, is no input at all (the owner, 2026-11-13: two letters
    # waited, he sent one, and its copy coming back set the other aside - "how am i supposed to send 2 messages then")
    # ...each message greying only the cards it bears on (proposals.bears: to its sender, or on its thread); his line, every card
    joined = {str(x['MessageId']): x for x in _mail(store, tid)} if any(k == 'mail' for k, _ in new) else {}
    mails = [(joined[r]['T'], joined[r]) for k, r in new if k == 'mail' and r in joined]
    if (line := any(k == 'line' for k, _ in new)) or mails:
        from . import proposals
        proposals.set_aside_drafts(store, tid, now if line else 0., mails)
    if n: store._poke('task-changed', task_id=tid)
    return n


def heard(store, tid: int, kind: str, refs) -> bool:
    "Has the agent been handed every one of these (`refs` of one kind) already?"
    refs = list({str(r) for r in refs or [] if r})
    return bool(refs) and store._one(f"SELECT COUNT(*) AS n FROM heard WHERE TaskId=? AND Kind=? AND Ref IN ({','.join('?' * len(refs))})", (int(tid), kind, *refs))['n'] == len(refs)


def unheard(store, tid: int) -> set:
    """The messages (ids) on the task that came in after the newest turn began and no hand-over took: what a steer's hand-over takes with
    his lines (general.GeneralSession.steer), so they stand in the chat where the agent heard them."""
    m = store._one("SELECT MAX(At) AS a FROM heard WHERE TaskId=? AND Kind='turn'", (int(tid),))
    if not (m and m['a']): return set()
    led = {r['Ref'] for r in store._rows("SELECT Ref FROM heard WHERE TaskId=? AND Kind='mail'", (int(tid),))}
    return {x['MessageId'] for x in _mail(store, tid) if str(x['MessageId']) not in led and x['T'] + 1 > m['a']}


# AN AGENT ON THE TASK IS NOT THE AGENT HAVING HEARD IT (the owner's live app, 2026-11-23): a held mail reopened a finished task, Trust was
# pressed, and the press asked only whether a session existed - it opened one on the old conversation with no turn, and the mail went unheard
def not_given(store, tid: int) -> list:
    "The messages on the task no hand-over gave its agent (ids, in the order they joined) - from when the ledger answers for it (_since)."
    since, led = _since(store, int(tid)) - 1, {r['Ref'] for r in store._rows("SELECT Ref FROM heard WHERE TaskId=? AND Kind='mail'", (int(tid),))}
    return [x['MessageId'] for x in _mail(store, int(tid)) if x['T'] >= since and str(x['MessageId']) not in led]


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
    if ref[:1] != '>':                              # ...an answer already filed: its turn in the log says it in its own step, in place
        from . import chatlog
        chatlog.took_back(store, tid, int(ref), (store._one("SELECT Sid FROM heard WHERE TaskId=? AND Kind='back' AND Ref=?", (int(tid), ref)) or {}).get('Sid')
                          or TOOK_BACK)
    store._poke('task-changed', task_id=int(tid))


def hear_press(store, tid: int, action: str) -> None:
    """A PRESS ITS AGENT HEARS THE MOMENT IT IS MADE - his answer to a call the turn is stopped at (permissions.ask): heard there, so it
    stands where he pressed with the turn going on under it. Left for the next hand-over, it waited by the box while the turn it had just
    let go worked on, and then entered above work already drawn (the recorded hold, 2026-11-11)."""
    r = store._one("SELECT MAX(Id) AS i FROM audit WHERE EntityType='task' AND EntityId=? AND Action=?", (int(tid), action))
    if not (r and r['i']): return
    store._exec('INSERT OR IGNORE INTO heard (TaskId,Kind,Ref,At,Grp,Seq,Sid) VALUES (?,?,?,?,?,?,?)', (int(tid), 'press', str(r['i']), now := time.time(), 0, 0, ''))
    from . import chatlog                    # ...and it stands in the chat's log where it was heard (the one writer of what a hand-over took)
    chatlog.heard(store, tid, [('press', str(r['i']))], now)
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
# ...ITS rawOutput BY THE ONE READER OF EVERY SHAPE (agents.result_text - walk 11, 2026-11-23): this kept its own, which knew no codex-acp
# {result: CallToolResult}, so on Codex and HIPAA AI each `show` reached the page with no answer and no view was ever drawn, live or reloaded
def _out(u) -> str:
    from .agents import result_text
    got = '\n'.join(_unfence(_text(c.get('content'))) for c in u.get('content') or [] if isinstance(c, dict) and c.get('type') == 'content')
    return got or result_text(u.get('rawOutput'))
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
        # ...and a piece of a NAMED message goes on with it past a tool's update between (walk 2, 2026-11-21, Codex: a shell left running
        # posted mid-message, and one sentence stood as three rows, "...(both by filename and file contents)" / "and did not find one.")
        elif x.get('mid') and (o := next((s for s in reversed(out) if s['k'] == k), None)) and o.get('open') and o.get('mid') == x['mid'] and not x.get('line'):
            o['text'] += t
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
        # ...a failure Taskuary marked, in his words (say.owner) - the raw text stays in the agent's own record
        elif kind == 'error' and _meta(u, 'taskuary') == 'error':
            from . import say
            out.append({'k': 'error', 'text': say.owner({'kind': 'turn_failed', 'raw': _text(u.get('content'))}), 'at': at})
        elif kind == 'error' and _meta(u, 'taskuary') == 'step_error': out.append({'k': 'error', 'text': _text(u.get('content')), 'at': at})     # ...a trace road's (acp_of_trace)
        elif kind == 'compaction_update' or (kind in ('tool_call', 'tool_call_update') and (_meta(u, 'claudeCode', 'toolName') == 'compact' or str(u.get('toolCallId')) in compacts)):
            cid = str(u.get('compactionId') if kind == 'compaction_update' else u.get('toolCallId'))
            if cid not in compacts: compacts[cid] = {'k': 'compact', 'id': cid, 'at': at}; out.append(compacts[cid])
            if u.get('status'): compacts[cid]['status'] = u['status']
        # ...one plan per turn, replaced whole where it stood in it (chatlog.step `turns`): after his line the newest is a row of the new turn
        elif kind == 'plan':
            p = {'k': 'plan', 'at': at, 'items': [{'text': str(e.get('content') or ''), 'status': e.get('status') or 'pending'} for e in u.get('entries') or [] if isinstance(e, dict)]}
            was = next((i for i in range(len(out) - 1, -1, -1) if out[i]['k'] in ('plan', 'you')), None)
            if was is not None and out[was]['k'] == 'plan': out[was] = {**out[was], 'items': p['items']}
            else: out.append(p)
        elif kind in ('tool_call', 'tool_call_update'):
            s = by.get(u.get('toolCallId'))
            if not s:
                if kind == 'tool_call_update' and not (u.get('rawInput') or u.get('title') or u.get('kind')): continue
                # ...A SERVER'S TOOL AS ITSELF (the owner's live app, 2026-11-19: codex-acp sends one as kind `execute`, its input {server, tool,
                # arguments} - read as a shell with no command, the row said "Ran a command it did not show" over a reply it drafted)
                mcp = raw if isinstance(raw := u.get('rawInput'), dict) and raw.get('server') and raw.get('tool') else None
                if mcp and isinstance(mcp.get('arguments'), dict):        # ...use_tool's as the tool it ran (agenttools.as_called)
                    from .agenttools import as_called
                    tool, a = as_called(mcp['server'], mcp['tool'], mcp['arguments']); mcp = {**mcp, 'tool': tool, 'arguments': a}
                s = by[u.get('toolCallId')] = {'k': 'tool', 'id': str(u.get('toolCallId') or ''), 'at': at,
                                               'args': dict(mcp['arguments']) if mcp and isinstance(mcp.get('arguments'), dict) else {},
                                               'name': f"mcp__{mcp['server']}__{mcp['tool']}" if mcp else _meta(u, 'taskuary', 'tool') or
                                               _meta(u, 'claudeCode', 'toolName') or _ACP_TOOL.get(u.get('kind')) or u.get('title') or u.get('kind') or 'tool'}
                out.append(s)
            # ...A PERMISSION ASKED FOR IT is its update too (acp.asked_update): it fills what the call's own updates left out - never what they
            # said (Codex asks with its own kind, the command wrapped) - and the call waits on the answer with the agent's options, until it runs
            if (ask := _meta(u, 'taskuary', 'ask')) is not None:
                s['ask'] = ask
                u = {k: v for k, v in u.items() if k in ('toolCallId', 'locations', '_meta') or k == 'rawInput' and not s['args']
                     or k == 'title' and not s.get('title') or k == 'kind' and not s.get('tool_kind')}
            elif u.get('status') in ('in_progress', 'completed', 'failed'): s.pop('ask', None)
            # ...AND THE AGENT'S OWN WORDS FOR IT (the owner, 2026-11-23: adopt the open-source model): its title as it upgrades it, its kind, its
            # files - what the row says (agentSteps.stepsOf); ours only for Taskuary's own tools and a road that gives none (acp_of_trace)
            if isinstance(u.get('title'), str) and u['title'].strip(): s['title'] = u['title'].strip()[:300]
            if u.get('kind'): s['tool_kind'] = str(u['kind'])
            if (ls := [str(l['path']) for l in u.get('locations') or [] if isinstance(l, dict) and l.get('path')]): s['paths'] = ls[:8]
            if (par := _meta(u, 'claudeCode', 'parentToolUseId') or _meta(u, 'parentToolUseId') or _meta(u, 'parentToolCallId')): s['parent'] = str(par)
            # ...a command as the words it was run with too (codex-acp's ["powershell.exe", "-Command", "..."]): dropped, the row read "Ran a command"
            if isinstance(u.get('rawInput'), dict): s['args'].update({k: v for k, v in u['rawInput'].items() if k in _ARGS and (isinstance(v, str) and v.strip()
                                                                      or k == 'command' and isinstance(v, list) and v and all(isinstance(x, str) for x in v))})
            if u.get('status'): s['status'] = u['status']
            if (d := _meta(u, 'terminal_output_delta', 'data')): s['out'] = s.get('out', '') + d
            elif not s.get('out') and u.get('status') in ('completed', 'failed') and (o := _out(u)): s['output'] = o
            from .sessionrecord import did
            did(s, s.get('output') or s.get('out'))
            # ...a step that failed says why in his words (say.step_why) - its output stays for the agent and the open row
            if s.get('status') == 'failed':
                from . import say
                s['why'] = say.step_why(s.get('output') or s.get('out'))
            loc = next((l['path'] for l in u.get('locations') or [] if isinstance(l, dict) and l.get('path')), '')
            if loc and not any(s['args'].get(k) for k in _PATHS): s['args']['file_path'] = loc
            if (diffs := [c for c in u.get('content') or [] if isinstance(c, dict) and c.get('type') == 'diff']):
                s['edit'] = {'whole': True, 'parts': [{'old': d.get('oldText') or '', 'new': d.get('newText') or ''} for d in diffs]}; s['file'] = diffs[0].get('path') or loc
            elif (p := _meta(u, 'taskuary', 'patch')): s['edit'] = {'patch': p}; s['file'] = s.get('file') or loc
        # ...each new step keeps its update's exact clock (`_t`, record_update): a stamp to the millisecond put the words said right after his
        # press, in the press's own millisecond, ABOVE it - the ledger's hand-over time is finer (a CI runner, 2026-11-12)
        if u.get('_t'): [x.setdefault('_t', u['_t']) for x in out[n0:]]
    # ...AND WHAT IS SAID READS AS THE OWNER READS IT (the ACP rows, 2026-11-23: words now stream into their own row, and an agent with no
    # end_turn tool still writes Taskuary's [[TASKUARY-...]] marks into its message): the app's own marks are cut, a mark still arriving
    # is cut from its opening brackets, and a row left empty goes
    from .selfclose import for_screen
    for s in out:
        s.pop('open', None); s.pop('mid', None)
        if s['k'] == 'said' and '[[' in str(s.get('text') or ''):
            t = for_screen(s['text']); s['text'] = re.sub(r'\[\[[^\]]*$', '', t).rstrip()
    return [s for s in out if not (s['k'] == 'said' and not str(s.get('text') or '').strip())]


# EVERY ROAD WRITES THE AGENT'S OWN SHAPE (the owner, 2026-11-23: "Does this work for both ACP and HIPAA AI or any AI we use?"): a road that is
# not ACP - claude's stream-json, Codex's JSONL, the API agent's own tool loop - records its turn as the ACP updates it stands for, here, once,
# so acp_steps is the one projection and the page the one renderer. Each call keeps its id, its tool's own name and its input; an edit carries
# its diff as ACP content; a paragraph it said is a message of its own. No title: our words for a call are the page's (agentSteps.describeCall)
_OWN_EDIT = {'file_write': ('', 'text'), 'file_edit': ('old', 'new')}
def acp_of_trace(e: dict, n: int = 0) -> list:
    "A trace event (agents.py's vocabulary) as ACP session/updates; `n` numbers what has no id of its own. [] for what is no step."
    from .sessionrecord import _FILE_TOOLS, _cut, _cut_said, _edit, _parsed, hide_draft, EDIT_N, SAID_N, THOUGHT_N
    k, name, d = e.get('type'), str(e.get('name') or ''), e.get('detail')
    d = d if isinstance(d, dict) else {}
    if k == 'tool_call':
        a = hide_draft(name, _parsed(d.get('args'))); a = a if isinstance(a, dict) else {'input': str(a or '')}
        todos = a.get('todos') or a.get('plan')
        if isinstance(todos, list) and todos and all(isinstance(t, dict) for t in todos):
            return [{'sessionUpdate': 'plan', 'entries': [{'content': _cut(t.get('content') or t.get('step') or t.get('text') or '', 300),
                                                           'status': str(t.get('status') or 'pending')} for t in todos]}]
        f = next((a[x] for x in _PATHS if isinstance(a.get(x), str) and a[x]), '')
        # ...and the API agent's own file tools (apiagent.WRITE) by their own arguments: it is Taskuary's tool, its input is ours to read
        o, w = _OWN_EDIT.get(name, ('', ''))
        ed = _edit(a) if name in _FILE_TOOLS else {'parts': [{'old': str(a.get(o) or '')[:EDIT_N], 'new': a[w][:EDIT_N]}]} if w and isinstance(a.get(w), str) else None
        patch = a.get('patch') if isinstance(a.get('patch'), str) else a.get('input') if isinstance(a.get('input'), str) and re.search(r'\*\*\* (Update|Add) File|^@@', a['input'], re.M) else None
        meta = {'tool': name, **({'patch': patch[:20000]} if patch else {})}
        return [{'sessionUpdate': 'tool_call', 'toolCallId': str(d.get('tool_call_id') or f'{name}-{n}'), 'status': 'in_progress', 'rawInput': a,
                 **({'locations': [{'path': f}]} if f else {}),
                 **({'content': [{'type': 'diff', 'path': f, 'oldText': p['old'], 'newText': p['new']} for p in ed['parts']]} if ed else {}),
                 '_meta': {'taskuary': meta, **({'parentToolUseId': str(d['parent'])} if d.get('parent') else {})}}]
    if k == 'tool_result':
        bad, out = bool(d.get('is_error')), str(d.get('result') or '')
        return [{'sessionUpdate': 'tool_call_update', 'toolCallId': str(d.get('tool_call_id') or name), 'status': 'failed' if bad else 'completed',
                 **({'content': [{'type': 'content', 'content': {'type': 'text', 'text': _cut_said(out) if bad else out}}]} if out.strip() else {})}]
    t = str(e.get('detail') or '').strip() if not isinstance(e.get('detail'), dict) else ''
    if k == 'progress' and name in ('text', 'agent_message') and t:
        return [{'sessionUpdate': 'agent_message_chunk', 'messageId': f't{n}', 'content': {'type': 'text', 'text': _cut(t, SAID_N)}}]
    if k == 'progress' and name in ('thinking', 'reasoning') and t:
        return [{'sessionUpdate': 'agent_thought_chunk', 'messageId': f't{n}', 'content': {'type': 'text', 'text': _cut(t, THOUGHT_N)}}]
    if k == 'error':
        r = e['detail'].get('result') if isinstance(e.get('detail'), dict) else e.get('detail')
        return [{'sessionUpdate': 'error', 'content': {'type': 'text', 'text': _cut(r, 400)}, '_meta': {'taskuary': 'step_error'}}] if str(r or '').strip() else []
    return []


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


FAILED_TRY = 'failed'
def failed_try(store, tid: int) -> None:
    """A TRY THAT FAILED ENDS WHERE IT FAILED (design round 4, H3: after an outage a short ask read "ran 17m 18s" - the one failure line stands in
    place, so no answer came between the tries, and the turn that answered counted from the first of them). Its end is in the ledger and is a
    stop for turn_start, as his own stop is: the turn that answers counts from its own try."""
    with store.lock:
        seq = store.cx.execute('SELECT MAX(CommentId) AS m FROM comment WHERE TaskId=?', (int(tid),)).fetchone()['m'] or 0
        store.cx.execute('INSERT OR IGNORE INTO heard (TaskId,Kind,Ref,At,Grp,Seq,Sid) VALUES (?,?,?,?,?,?,?)',
                         (int(tid), FAILED_TRY, str(time.time_ns()), time.time(), 0, seq, ''))
        store.cx.commit()
    from . import chatlog
    chatlog.failed(store, tid)


def items(store, tid: int) -> dict:
    """The task's conversation, read from its one log (chatlog.serve): {rev, items, pending, working, started, asking, permissions, ...}.
    The old build that pieced it together on every read is kept only to freeze a task into the log once (conversation_legacy)."""
    from . import chatlog
    return chatlog.serve(store, tid)


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
    # ...a line of his still waiting by the box (`pending`) is drawn under the chat, the working line under it
    if his >= 0 and got.get('working') and not any(live(x) for x in xs[his + 1:]) and not any(p.get('kind') == 'line' for p in got.get('pending') or []):
        say(f"a: his newest line {ids[his]} has no turn at work under it")
    # b
    cards = [(i, c) for i, x in enumerate(xs) for c in ([x] if x['kind'] == 'card' else x.get('cards') or [] if x['kind'] == 'turn' else [])]
    lit = [(i, c) for i, c in cards if c.get('status') == 'pending']
    for r in {c['review'] for _, c in lit if [d['review'] for _, d in lit].count(c['review']) > 1}: say(f'b: review {r} stands as two live cards')
    came = max((i for i, x in enumerate(xs) if x['kind'] in ('line', 'arrival')), default=-1)
    for i, c in lit:
        if (i < came and c.get('what') in DRAFTS or i < his) and not c.get('stands'): say(f"b: the live card {c['id']} stands above a newer input {ids[came]}")
    # d
    for x in xs:
        k = x['kind']
        if (k == 'turn' and not live(x) and not (x.get('text') or x.get('steps') or x.get('cards') or x.get('fail') or x.get('summary'))
                or k == 'line' and not (str(x.get('text') or '').strip() or x.get('files'))
                or k == 'arrival' and not (str(x.get('words') or '').strip() or x.get('files') or x.get('head'))
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
