"""A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-25: "it should be exactly the same, only difference is what level of feedback it
shows by default"). Its chat is the task's one log (chatlog.py), drawn by the same page as every task's; its cards stand where that log puts
them. What is kept here is only what a coding session has and a chat agent has not:
- each session's steps - the CLI's own log (sessionrecord.cli_steps: Claude, Codex, Copilot, Gemini), else the copy kept when it was saved,
  written into the log as they come (chatlog.logged);
- the live CLI: is it running, and is its screen asking something only the terminal answers (live_of).

THE ACP SEAM. A coding session run over ACP (acp.py) has no CLI log to read - its session/update notifications ARE the record.
`record_update` keeps each one beside the task as it arrives (acpcoding.ACPCoding calls it for every update it gets, and for every prompt it
sends); the landing card and the agent's own history read it back (acp_updates)."""
import collections, json, os, re, threading, time
from datetime import datetime
from pathlib import Path

from loguru import logger

from . import session_artifacts, sessionrecord

ACP_KEEP = 20000                  # the newest updates kept per session: message chunks arrive a token at a time
OUT_KEEP = 8000                   # the characters of one tool's output kept: the page shows 1,500 of it (agentSteps.detailOf)


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
    # ...and `_t`, the same moment to the clock's full grain: the ledger's hand-overs are time.time(), and a step and a press in one millisecond
    # must read in the order they happened (conversation.acp_steps)
    now = time.time()
    _append(_acp_path(tid, sid), tid, {**update, '_at': update.get('_at') or datetime.fromtimestamp(now).isoformat(sep=' ', timespec='milliseconds'),
                                     '_t': update.get('_t') or now})


def _append(p: Path, tid, update: dict) -> None:
    try:
        with p.open('a', encoding='utf-8') as f: f.write(json.dumps(slim(update), ensure_ascii=False) + '\n')
    except (OSError, TypeError, ValueError) as e: logger.debug(f'chat record: an update for task {tid} not kept - {e}')


def record_general(tid: int, sid: str, update: dict) -> None:
    """A GENERAL AGENT'S TURN KEPT AS THE SAME RECORD (the owner, 2026-11-23: one record shape for every road): each ACP update - its CLI's own
    over ACP, or a trace road's said as one (conversation.acp_of_trace) - appended beside the task as a coding session's is. Apart from the
    coding sessions' (general-acp-*.jsonl, never listed as one); never raises."""
    if not isinstance(update, dict) or not sid or not tid: return
    p = _acp_path(tid, sid); _append(p.with_name('general-' + p.name), tid, {**update, '_t': update.get('_t') or time.time()})


def _capped(o):
    h = OUT_KEEP // 2                                                     # ...its head and its tail: a test run's verdict is at its end
    if isinstance(o, str): return o if len(o) <= OUT_KEEP else f'{o[:h]}\n... ({len(o) - 2 * h} characters not kept) ...\n{o[-h:]}'
    if isinstance(o, list): return [_capped(x) for x in o]
    return {k: _capped(v) for k, v in o.items()} if isinstance(o, dict) else o


def slim(u: dict) -> dict:
    """An update as it is kept and read: a tool's output to its head, and the CLI's own copy of what it read (`toolResponse`) not at all. The
    owner's live app, 2026-11-19: one session reading files kept every file whole three times over, 587 MB, read whole on every poll."""
    if not isinstance(u, dict) or u.get('sessionUpdate') not in ('tool_call', 'tool_call_update'): return u
    u = {**u, **({'rawOutput': _capped(u['rawOutput'])} if 'rawOutput' in u else {}),
         **({'content': [c if isinstance(c, dict) and c.get('type') == 'diff' else _capped(c) for c in u['content']]} if isinstance(u.get('content'), list) else {})}
    if isinstance(cc := (u.get('_meta') or {}).get('claudeCode'), dict) and 'toolResponse' in cc:
        u['_meta'] = {**u['_meta'], 'claudeCode': {k: v for k, v in cc.items() if k != 'toolResponse'}}
    return u


_FOLLOWED, _FOLLOWED_LOCK = {}, threading.Lock()


def follow(p: Path, fold, start, read):
    """`read(state)` of what `fold(state, update)` made of an ACP record so far, from `start()` - reading only what was appended since the last
    read (the record only grows: record_update appends). Read whole on every poll, one chat read took 17 s and the rail 56 s behind it (the
    owner's live app, 2026-11-19). A record that shrank or was made again is read from its start. Each update read as it is kept (slim)."""
    with _FOLLOWED_LOCK: e = _FOLLOWED.setdefault((str(p), fold), {'lock': threading.Lock(), 'id': None, 'off': 0, 'tail': b'', 'state': None})
    with e['lock']:
        try:
            with open(p, 'rb') as f:
                st = os.fstat(f.fileno())
                f.seek(e['off'] - len(e['tail']))                         # ...the end of what was read still there: else the record was made again
                if e['state'] is None or e['id'] != (st.st_dev, st.st_ino) or st.st_size < e['off'] or f.read(len(e['tail'])) != e['tail']:
                    e.update(id=(st.st_dev, st.st_ino), off=0, tail=b'', state=start()); f.seek(0)
                got = f.read(max(0, st.st_size - e['off']))
        except OSError: return read(start())
        # ...a last line still being written is read whole on the next read - one whole without its newline now
        if (end := got[got.rfind(b'\n') + 1:]):
            try: json.loads(end)
            except ValueError: got = got[:len(got) - len(end)]
        if got: e['off'] += len(got); e['tail'] = got[-256:]
        for line in got.splitlines():
            try: u = json.loads(line)
            except ValueError: continue
            if isinstance(u, dict): fold(e['state'], slim(u))
        return read(e['state'])


SLIM_OVER = 20_000_000              # a record past this was kept before slim() and is written again in its form, once


def slim_kept(root: Path = None, live=None) -> list:
    """EVERY RECORD KEPT BEFORE slim() WRITTEN AGAIN IN ITS FORM (the owner, 2026-11-19: yes): one session's record was 587 MB, read in full on
    the first read after every start. Run once a start, on its own thread: each record past SLIM_OVER is read line by line into a file beside
    it and swapped in only when whole, and only if nothing was appended meanwhile - a record whose session is live is left for the next start.
    `live`: the records being written now (default: every running session's). -> [(path, bytes before, bytes after)] of what was rewritten."""
    root = Path(root) if root else session_artifacts.root()
    if live is None:
        from . import terminal as term
        live = {_acp_path(t.task_id, t.sid) for t in list(term.SESSIONS.values()) if getattr(t, 'alive', False) and t.task_id}
    live, done = {os.path.normcase(str(p)) for p in live}, []
    for p in sorted(root.glob('*/acp-*.jsonl')):
        try: st = p.stat()
        except OSError: continue
        if st.st_size <= SLIM_OVER or os.path.normcase(str(p)) in live: continue
        tmp = p.with_suffix('.slim')
        try:
            with open(p, 'rb') as f, open(tmp, 'wb') as out:
                for line in f:
                    try: u = json.loads(line)
                    except ValueError: out.write(line if line.endswith(b'\n') else line + b'\n'); continue
                    out.write(json.dumps(slim(u), ensure_ascii=False).encode('utf-8') + b'\n')
            now = p.stat()
            if (now.st_size, now.st_mtime_ns) != (st.st_size, st.st_mtime_ns): tmp.unlink(); continue      # ...written to meanwhile: next start
            os.replace(tmp, p); done.append((p, st.st_size, os.path.getsize(p)))
            logger.info(f'coding chat: {p.parent.name}/{p.name} kept in slim form - {st.st_size / 1e6:.0f} MB to {done[-1][2] / 1e6:.1f} MB')
        except OSError as e:
            logger.warning(f'coding chat: {p.name} not slimmed - {e}')
            try: tmp.unlink()
            except OSError: pass
    return done


def _keep(q, u): q.append(u)
def _kept(): return collections.deque(maxlen=ACP_KEEP)


def acp_updates(tid: int, sid: str) -> list:
    p = _acp_path(tid, sid)
    return follow(p, _keep, _kept, list) if p.is_file() else []


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
    # ...at work by the one function that says so (general._at_work): a turn that waits on his press or his sign-in is not
    from .general import _at_work
    return {'sid': t.sid, 'cli': getattr(t, 'cli', '') or term.cli_of(getattr(t, 'argv', None) or []), 'started': t.started,
            'asking': asking, 'working': phase == 'working' and _at_work(t), 'promptPending': bool(term.prompt_pending(t)),
            'turnStarted': max(began, _epoch(t.started)) if began else None,
            'transport': 'acp' if acp else 'pty', 'terminal': bool(getattr(t, 'has_output', False)) if acp else True}


def _epoch(at) -> float:
    try: return datetime.strptime(str(at or '')[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S').timestamp()
    except ValueError: return 0.


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


def _session(tid: int, sid: str, cli: str, ext: str, at: str, live: bool = False, local: bool = True, acp: bool = False) -> dict:
    _local = globals()['_local'] if local else (lambda steps: steps)         # `local=False`: each step's own stamp, to the millisecond (conversation.items)
    s = {'sid': sid, 'cli': cli or '', 'at': str(at or '').replace('T', ' ')[:19], 'live': live}
    if (ups := acp_updates(tid, sid)) or acp: return {**s, 'source': 'acp', 'updates': _worded(ups)}
    saved = sessionrecord._saved_path(tid, sid)
    # a live session's log is read fresh - its saved copy, if any, is from an earlier save of the same pane
    if not live and saved.is_file():
        # ...marked again as it is read: a record saved before 2026-11-09 holds the owner's words inside Taskuary's wrapper (mark_briefs)
        try: return {**s, 'source': 'saved', 'steps': _local(sessionrecord.mark_briefs(tid, (json.loads(saved.read_text(encoding='utf-8')) or {}).get('steps') or []))}
        except (OSError, ValueError): pass
    steps, src = sessionrecord.marked_steps(tid, cli, ext)
    return {**s, 'source': src or 'none', 'steps': _local(steps) if steps else []}


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
    # ...AND ONE OVER ACP IS SO FROM ITS START, before its first update is kept (the recorded restart, 2026-11-11: his line reopened a session
    # on its CLI's own conversation, and until that session wrote its first update it was read as a pane's - the CLI's whole log, every
    # earlier turn a second time and stamped now. One read of the chat drew all his lines first and every turn after them: one frame,
    # 370 px taller, and back)
    from . import terminal as term
    acp = {sid for sid, *_, live in items if _acp_path(tid, sid).is_file() or (live and term.is_acp(t))}
    last = {(cli, ext): i for i, (sid, cli, ext, _, _) in enumerate(items) if ext and sid not in acp}
    return [_session(tid, sid, cli, ext, at, live, local, sid in acp) for i, (sid, cli, ext, at, live) in enumerate(items)
            if not ext or sid in acp or last.get((cli, ext)) == i]


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

