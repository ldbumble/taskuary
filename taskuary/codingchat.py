"""A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-06: "combine the close out action in the coding cli as well. basically making general
and coding agent more similar. i do like you can review the code diffs if you want... i like the editor that you can see the code").

Nothing new is recorded for it. The chat is read off what Taskuary already keeps of a coding session:
- each session's steps - the CLI's own log (sessionrecord.cli_steps: Claude, Codex, Copilot, Gemini), else the copy kept when it was saved;
- the mail that came in, in its sender's words (general.JOINED - the general chat's own shown_history reads the same rows);
- and the live session: is its CLI running, and is its screen asking something only the terminal answers (a login, a permission prompt).
The page maps the steps into chat rows with the general chat's own step lines (chatStream.js -> agentSteps.js).

THE ACP SEAM. A coding session run over ACP (step 1: acp.py) has no CLI log to read - its session/update notifications ARE the record.
`record_update` keeps each one beside the task as it arrives; `chat` hands a session's kept updates to the page as `updates`, and
chatStream.stepsFromAcp maps them into the very step shape a log gives, so both roads draw one row shape. A coding session over ACP
(acpcoding.ACPCoding) calls `record_update(tid, sid, update)` for every update it gets, and for every prompt it sends."""
import json, re
from datetime import datetime
from pathlib import Path

from loguru import logger

from . import outputs, session_artifacts, sessionrecord

ACP_KEEP = 20000                  # the newest updates kept per session: message chunks arrive a token at a time
MAIL_N = 3000


def _acp_path(tid: int, sid: str) -> Path:
    d = session_artifacts.root() / str(int(tid)); d.mkdir(parents=True, exist_ok=True)
    return d / f"acp-{re.sub(r'[^A-Za-z0-9._-]+', '-', str(sid))[:80]}.jsonl"


def record_update(tid: int, sid: str, update: dict) -> None:
    """THE SEAM: one ACP session/update of a coding session, kept as it arrives. Never raises - a lost line costs a chat row, not the session.
    ACP never echoes the prompt it was sent, so the prompt goes in here too, as the update a replayed session would carry:
    {'sessionUpdate': 'user_message_chunk', 'content': {'type': 'text', 'text': prompt}} - with '_meta': {'taskuary': 'brief'} when it is
    Taskuary's own seed or brief rather than the owner's words (the chat never draws a brief; it draws the mail that caused it)."""
    if not isinstance(update, dict) or not sid: return
    # ...stamped as it arrives (`_at`, the server's own zone): ACP updates carry no time, and a turn read as one stamp under every mail
    update = {**update, '_at': update.get('_at') or datetime.now().isoformat(sep=' ', timespec='milliseconds')}
    try:
        with _acp_path(tid, sid).open('a', encoding='utf-8') as f: f.write(json.dumps(update, ensure_ascii=False) + '\n')
    except (OSError, TypeError, ValueError) as e: logger.debug(f'coding chat: ACP update for task {tid} not kept - {e}')


def acp_updates(tid: int, sid: str) -> list:
    p = _acp_path(tid, sid)
    if not p.is_file(): return []
    out = []
    for line in p.read_text(encoding='utf-8', errors='replace').splitlines()[-ACP_KEEP:]:
        try: out.append(json.loads(line))
        except ValueError: continue
    return out


def mails(store, tid: int) -> list:
    "What came in on the task, each in its sender's words - the shape the general chat draws (general.shown_history `mail`)."
    from .general import JOINED, mail_row
    return [{**mail_row(store, x, MAIL_N), 'joined': x.get('JoinedAt') or x.get('CreatedAt')} for x in store._rows(JOINED, (int(tid),))]


def _live(tid: int):
    "The coding CLI running on this task now, if one is - a general agent's own chat session is not one."
    from . import terminal as term
    return next((t for t in list(term.SESSIONS.values()) if t.task_id == tid and t.alive and getattr(t, 'mode', '') != 'assistant'), None)


def live_of(t) -> dict | None:
    """What the chat needs of a running CLI: which, since when, and whether its SCREEN asks something (a chooser, a permission prompt, a
    sign-in) - then the Terminal opens by itself, as nothing typed in the chat's box can answer a chooser."""
    if not t: return None
    from . import terminal as term
    try: asking = bool(term.screen_asking(t))
    except Exception: asking = False
    try: phase = t.phase()
    except Exception: phase = 'unknown'
    acp = term.is_acp(t)
    # ...over ACP (acpcoding.py) there is no screen to ask from, and its terminal is its commands' output: none yet is no Terminal toggle
    # ...and WHEN THE TURN AT WORK BEGAN, its clock (the owner's live coding task, 2026-11-08: "Working on this… 2947m 55s"): the chat counted from
    # the owner's last line it draws, two days back - a resumed session's first turn is Taskuary's brief, drawn as no line. Never before this run
    began = getattr(t, 'turn_at', 0) or getattr(t, 'started_ts', 0) or _epoch(t.started)
    return {'sid': t.sid, 'cli': getattr(t, 'cli', '') or term.cli_of(getattr(t, 'argv', None) or []), 'started': t.started,
            'asking': asking, 'working': phase == 'working', 'promptPending': bool(term.prompt_pending(t)),
            'turnStarted': max(began, _epoch(t.started)) if began else None,
            'transport': 'acp' if acp else 'pty', 'terminal': bool(getattr(t, 'has_output', False)) if acp else True}


def _epoch(at) -> float:
    try: return datetime.strptime(str(at or '')[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S').timestamp()
    except ValueError: return 0.


def waiting(store, tid: int, t=None) -> list:
    """THE OWNER'S LINES NO TURN HAS TAKEN YET, on every screen (the owner, 2026-11-08: "i asked another question and the text was never sent into
    the prompt"): the waiting room's notes not yet handed over, and what a live ACP session holds for its next turn - each drawn as theirs,
    "Waiting for the agent", until a turn takes it. The general chat's own road (general.waiting_lines); [{id, text, at}], oldest first."""
    from . import general
    from .waitroom import TEAMMATE, parts
    # IN THE ORDER A LINE MOVES (general.take_line): kept, then held by the session, then drawn in its record - read in that order, so a line
    # read gone from one is already in the next, and named once by its kept row's id (`line`) wherever two reads both hold it (chat)
    kept = general.waiting_lines(store, int(tid))
    out = kept + [{'id': f"w{x['WId']}", 'text': parts(x.get('Note'))[0], 'at': x.get('CreatedAt')} for x in store.waiting_notes(int(tid))
                  if (x.get('CreatedBy') or 'owner') not in ('router', TEAMMATE)]
    held = list(getattr(t, '_q', None) or []) if t is not None else []
    # ...and the owner's words a reopening's first prompt leads with ("FROM THE OWNER: ..." - Continue): held until its adapter is up, ten seconds
    # and more, they were on no screen but the one that sent them (the owner, 2026-11-10)
    from .outcomes import owner_split
    lines = lambda text, brief, shown: shown or ([w] if brief and (w := owner_split(text)[0]) else [])
    # ...each named as the page knows it (`line`, the name it was sent under - as a kept row is named), its kept row's id beside it (`kept`): named
    # by that id, the page drew the line twice while the session held it (the browser walk, 2026-11-10)
    return out + [{'id': f'q{i}', 'text': w['text'], 'at': None, 'kept': w.get('line'), **({'line': w['name']} if w.get('name') else {})}
                  if isinstance(w, dict) else {'id': f'q{i}', 'text': w, 'at': None}
                  for i, (_t, _b, shown, _d) in enumerate(held) for w in lines(_t, _b, shown) if not (isinstance(w, dict) and w.get('drawn'))]


def _once(waiting: list, sessions: list) -> list:
    "Each owner's line once: a kept row the session holds too, or one its record already draws, is drawn there - not twice."
    drawn = {(u.get('_meta') or {}).get('line') for s in sessions for u in s.get('updates') or []} - {None}
    held = {w.get('kept') for w in waiting if str(w['id']).startswith('q')} - {None}
    return [w for w in waiting if (w.get('kept') if str(w['id']).startswith('q') else w['id']) not in drawn | (set() if str(w['id']).startswith('q') else held)]


# ...each step's time in the server's own zone, as every stamp the page reads (store.norm_stamp): a CLI log stamps UTC, and the turn read
# 3:29 PM under a mail of 10:18 AM that came in before it (the render check, 2026-11-06)
def _local(steps: list) -> list: return [{**s, 'at': sessionrecord._local(s['at'])} if s.get('at') else s for s in steps]


def _worded(ups: list) -> list:
    """Each run of the agent's words ONE update, read as a chat's answer is (selfclose.asked_inline): its [[TASKUARY-ASK]] came a token at a time,
    and the coding chat drew the bare marker where a general one draws the question (the audit, 2026-11-10)."""
    from .selfclose import asked_inline
    words = lambda u: u.get('sessionUpdate') == 'agent_message_chunk' and (u.get('content') or {}).get('type') == 'text'
    out = []
    for u in ups:
        if words(u) and out and words(out[-1]): out[-1] = {**out[-1], 'content': {'type': 'text', 'text': out[-1]['content']['text'] + str(u['content'].get('text') or '')}}
        else: out.append(u)
    return [{**u, 'content': {'type': 'text', 'text': asked_inline(u['content']['text'])[0]}} if words(u) else u for u in out]


def _session(tid: int, sid: str, cli: str, ext: str, at: str, live: bool = False, local: bool = True) -> dict:
    _local = globals()['_local'] if local else (lambda steps: steps)         # `local=False`: each step's own stamp, to the millisecond (conversation.items)
    s = {'sid': sid, 'cli': cli or '', 'at': str(at or '').replace('T', ' ')[:19], 'live': live}
    if (ups := acp_updates(tid, sid)): return {**s, 'source': 'acp', 'updates': _worded(ups)}
    saved = sessionrecord._saved_path(tid, sid)
    # a live session's log is read fresh - its saved copy, if any, is from an earlier save of the same pane
    if not live and saved.is_file():
        # ...marked again as it is read: a record saved before 2026-11-09 holds the owner's words inside Taskuary's wrapper (mark_briefs)
        try: return {**s, 'source': 'saved', 'steps': _local(sessionrecord.mark_briefs(tid, (json.loads(saved.read_text(encoding='utf-8')) or {}).get('steps') or []))}
        except (OSError, ValueError): pass
    steps, src = sessionrecord.cli_steps(cli, ext)
    return {**s, 'source': src or 'none', 'steps': _local(sessionrecord.mark_briefs(tid, steps)) if steps else []}


def sessions(store, tid: int, local: bool = True) -> list:
    """Every coding session of the task, oldest first, each with its steps (or its ACP updates). A resumed conversation writes on into
    the same CLI log, so of the sessions sharing one, only the newest is kept - it holds the earlier ones' steps too."""
    tid = int(tid)
    rows = store._rows('SELECT * FROM transcript WHERE TaskId=? ORDER BY TranscriptId', (tid,))
    t = _live(tid)
    items = [(r.get('Sid') or '', r.get('Brain') or '', r.get('ExtId') or '', r.get('CreatedAt'), False) for r in rows if (r.get('Sid') or '') != getattr(t, 'sid', None)]
    if t: items.append((t.sid, getattr(t, 'cli', '') or '', getattr(t, 'ext_id', '') or '', t.started, True))
    # ...a session run over ACP keeps its OWN updates (record_update, per Taskuary session): a resumed one holds only its new turns, so it
    # never stands in for the ones before it, and they are all kept
    acp = {sid for sid, *_ in items if _acp_path(tid, sid).is_file()}
    last = {(cli, ext): i for i, (sid, cli, ext, _, _) in enumerate(items) if ext and sid not in acp}
    return [_session(tid, sid, cli, ext, at, live, local) for i, (sid, cli, ext, at, live) in enumerate(items)
            if not ext or sid in acp or last.get((cli, ext)) == i]


def chat(store, tid: int) -> dict:
    """What the coding chat draws (GeneralWorkspace.jsx): the sessions' steps or ACP updates, the mail that came in, and the live CLI - one that
    idled out (acpcoding.idle_out) still, at rest: the chat stays as it was, and its box is the input that brings it back."""
    from . import acpcoding, general, permissions, taskstate
    t = _live(int(tid)) or (acpcoding.IDLED.get(int(tid)) if acpcoding.idled(int(tid), store) else None)
    from .landing import has_checkout
    # A LINE MOVES ONE WAY - kept, held by its session, drawn in its record - so it is read in that order: read after the sessions, a line
    # taken between the two reads was in neither (CI, 2026-11-10). One caught in two is drawn once, by its kept row's id (_once)
    was, w = general.at_work(int(tid)), waiting(store, tid, t)
    ss = owned(store, tid, sessions(store, tid))
    # ...and what the indicator and the lines read, from the one function the general chat's payload calls (general.line_state)
    return {'task': int(tid), 'sessions': ss, 'mails': mails(store, tid), 'live': live_of(t),
            'checkout': has_checkout(store, tid, getattr(t, 'cwd', '') or ''),
            **general.line_state(store, int(tid), _once(w, ss), was),
            # ...and the owner's presses, each one quiet line at its time - the general chat's own (general.press_lines): a coding task's Remind me
            # or Push left no line in its chat at all (the audit, 2026-11-10)
            'presses': general.press_lines(store, int(tid)),
            # ...and what it asks the owner, by the general chat's own read (taskstate.asking)
            'asking': taskstate.asking(store, store.get_task(int(tid)) or {'TaskId': int(tid)}, t if getattr(t, 'alive', False) else None),
            # ...and the turn each card stands in, the general payload's `turns` and `drafts` read off this record (cards)
            **cards(store, int(tid), ss),
            'permissions': permissions.pending(int(tid), store)}         # what the agent waits on the owner's button for


def owned(store, tid: int, ss: list) -> list:
    """ONLY WHAT THE OWNER TYPED IS DRAWN AS HIS (the owner's rules, part 3: "the same fact reads the same"): an ACP adapter sends user-role
    messages of its own - a slash command's output and the like - and the chat drew them in his bubble. Every line he typed is recorded
    (general.take_line; before it, the waiting room's notes), so a user-role update Taskuary did not mark and that is not one of his is the
    agent's (chatStream.stepsFromAcp draws `agent` as its words)."""
    from . import general
    from .waitroom import parts
    his = {' '.join(str(c.get('Body') or '').split()) for c in store.list_comments(int(tid), internal=True)
           if c.get('ActorType') == general.USER_TYPE and c.get('Actor') == 'owner'}
    his |= {' '.join(parts(x.get('Note'))[0].split()) for x in store.waitroom(int(tid), limit=500) if (x.get('CreatedBy') or 'owner') == 'owner'}
    mine = lambda u: ' '.join(str((u.get('content') or {}).get('text') or '').split()) in his
    sent = lambda u: (u.get('_meta') or {}).get('taskuary') == 'prompt'           # ...a prompt Taskuary sent as typed (ACPCoding._show): his words, or its own
    mark = lambda u: (u if u.get('sessionUpdate') != 'user_message_chunk' or (u.get('_meta') and not sent(u)) else
                      {**u, '_meta': {'taskuary': 'owner' if mine(u) else 'brief' if sent(u) else 'agent'}})
    return [{**s, 'updates': [mark(u) for u in s['updates']]} if s.get('updates') else s for s in ss]


def cards(store, tid: int, ss: list) -> dict:
    """WHERE EACH CARD STANDS IN THE CODING CHAT, BY ITS TURN - the general payload's `turns`, `drafts` and `published` (general.draft_turns), read off this record:
    the page compared times itself and named its turns by position, so nothing here could name one (2026-11-11). A card is of the turn whose step
    was newest when it was raised, named as the page names that step (`sid#n`, its place in what `chat` hands it - chatStream.chatRows); raised on
    arrival, or after his line before the turn's first step: none. A draft is stale once his line came after it and no step of the agent's since."""
    def whose(u):
        k, m = u.get('sessionUpdate') or u.get('k'), (u.get('_meta') or {}).get('taskuary')
        return 'his' if k == 'you' or (k == 'user_message_chunk' and m == 'owner') else '' if k in ('brief', 'user_message_chunk', 'gap', 'screen') else 'agent'
    at_ = lambda x: str(x or '').replace('T', ' ')[:19]
    steps = sorted(((at_(u.get('_at') or u.get('at') or s.get('at')), f"{s['sid']}#{i}", whose(u)) for s in ss
                    for i, u in enumerate(s.get('updates') or s.get('steps') or [])), key=lambda x: x[0])
    turn = lambda at: next((n if w == 'agent' else None for t, n, w in reversed(steps) if t <= at_(at) and w), None)
    his = lambda at: next((t for t, _, w in steps if t > at_(at) and w == 'his'), None)
    rows = store._rows("SELECT ReviewId, Kind, Status, CreatedAt, DraftText FROM review WHERE TaskId=? AND Kind<>'slot' ORDER BY ReviewId", (tid,))
    drafts = [{'review': r['ReviewId'], 'turn': turn(r['CreatedAt']), 'at': r['CreatedAt'], 'stale': stale, 'before': later if stale else None}
              for r in rows if r['Status'] == 'pending' and r['Kind'] in ('draft_reply', 'draft') and str(r.get('DraftText') or '').strip()
              for later in [his(r['CreatedAt'])] for stale in [bool(later) and not any(t > later and w == 'agent' for t, _, w in steps)]]
    # ...and each page it showed or published, in the turn that showed it as the general chat's are (outputs.pages): the coding chat drew only a
    # page whose trace carried the tool's answer, and a published one never (the overnight walk, 2026-11-11)
    return {'turns': {str(r['ReviewId']): turn(r['CreatedAt']) for r in rows}, 'drafts': drafts,
            'published': [{**p, 'after': turn(p['created_at'])} for p in outputs.pages(store, tid)]}
