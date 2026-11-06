"""A CODING TASK IS THE SAME ONE CHAT (the owner, 2026-11-06: "combine the close out action in the coding cli as well. basically making general
and coding agent more similar. i do like you can review the code diffs if you want... i like the editor that you can see the code").

Nothing new is recorded for it. The chat is read off what Taskuary already keeps of a coding session:
- each session's steps - the CLI's own log (sessionrecord.cli_steps: Claude, Codex, Copilot, Gemini), else the copy kept when it was saved;
- the mail that came in, in its sender's words (general.JOINED - the general chat's own shown_history reads the same rows);
- and the live session: is its CLI running, and is its screen asking something only the terminal answers (a login, a permission prompt).
The page maps the steps into chat rows with the general chat's own step lines (codingChat.js -> agentSteps.js).

THE ACP SEAM. A coding session run over ACP (step 1: acp.py) has no CLI log to read - its session/update notifications ARE the record.
`record_update` keeps each one beside the task as it arrives; `chat` hands a session's kept updates to the page as `updates`, and
codingChat.stepsFromAcp maps them into the very step shape a log gives, so both roads draw one row shape. A coding session over ACP
(acpcoding.ACPCoding) calls `record_update(tid, sid, update)` for every update it gets, and for every prompt it sends."""
import json, re
from datetime import datetime
from pathlib import Path

from loguru import logger

from . import session_artifacts, sessionrecord

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
    update = {**update, '_at': update.get('_at') or datetime.now().isoformat(sep=' ', timespec='seconds')}
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
    from .general import JOINED
    from .triage import own_words
    return [{'who': 'You' if x.get('Own') else x.get('FromName') or x.get('FromEmail') or '', 'own': bool(x.get('Own')),
             'channel': x.get('Channel') or '', 'at': x.get('SentAt') or x.get('CreatedAt'), 'joined': x.get('JoinedAt') or x.get('CreatedAt'),
             'words': (str(x.get('OwnText') or '').strip() or own_words(str(x.get('BodyText') or '')).strip())[:MAIL_N] or x.get('Subject') or ''}
            for x in store._rows(JOINED, (int(tid),))]


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
    return {'sid': t.sid, 'cli': getattr(t, 'cli', '') or term.cli_of(getattr(t, 'argv', None) or []), 'started': t.started,
            'asking': asking, 'working': phase == 'working', 'promptPending': bool(term.prompt_pending(t)),
            'transport': 'acp' if acp else 'pty', 'terminal': bool(getattr(t, 'has_output', False)) if acp else True}


# ...each step's time in the server's own zone, as every stamp the page reads (store.norm_stamp): a CLI log stamps UTC, and the turn read
# 3:29 PM under a mail of 10:18 AM that came in before it (the render check, 2026-11-06)
def _local(steps: list) -> list: return [{**s, 'at': sessionrecord._local(s['at'])} if s.get('at') else s for s in steps]


def _session(tid: int, sid: str, cli: str, ext: str, at: str, live: bool = False) -> dict:
    s = {'sid': sid, 'cli': cli or '', 'at': str(at or '').replace('T', ' ')[:19], 'live': live}
    if (ups := acp_updates(tid, sid)): return {**s, 'source': 'acp', 'updates': ups}
    saved = sessionrecord._saved_path(tid, sid)
    # a live session's log is read fresh - its saved copy, if any, is from an earlier save of the same pane
    if not live and saved.is_file():
        try: return {**s, 'source': 'saved', 'steps': _local((json.loads(saved.read_text(encoding='utf-8')) or {}).get('steps') or [])}
        except (OSError, ValueError): pass
    steps, src = sessionrecord.cli_steps(cli, ext)
    return {**s, 'source': src or 'none', 'steps': _local(sessionrecord.mark_briefs(tid, steps)) if steps else []}


def sessions(store, tid: int) -> list:
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
    return [_session(tid, sid, cli, ext, at, live) for i, (sid, cli, ext, at, live) in enumerate(items)
            if not ext or sid in acp or last.get((cli, ext)) == i]


def chat(store, tid: int) -> dict:
    "What the coding chat draws (CodingChat.jsx): the sessions' steps or ACP updates, the mail that came in, and the live CLI."
    from . import permissions
    return {'task': int(tid), 'sessions': sessions(store, tid), 'mails': mails(store, tid), 'live': live_of(_live(int(tid))),
            'permissions': permissions.pending(int(tid), store)}         # what the agent waits on the owner's button for
