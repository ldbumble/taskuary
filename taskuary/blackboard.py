"""Agents that know about each other. The board IS the blackboard: who is working which
task in which checkout, and what files each has actually modified so far - read off git and
the run trace, never off a plan (agents predicting their own scope get it wrong; their
tracks do not). A new agent in the SAME checkout gets that picture in its seed prompt (a
peer in another repo is none of its business, and its tokens); a task LIKELY to collide
queues behind the one already working - first agent in has control.
"""
import json, os, re, threading, time
from loguru import logger

from .store import task_ref


# normpath('') is '.', which is a real relative path and would make every checkout-less note
# look like it belonged to whatever directory the reader happens to be standing in
def norm(p): return os.path.normcase(os.path.normpath(p)) if str(p or '').strip() else ''


def dirty(cwd) -> set:
    """Uncommitted paths in a checkout, per git itself."""
    from .agents import _git
    return {l[3:].strip().strip('"') for l in _git(cwd, 'status', '--porcelain').splitlines() if len(l) > 3}


# what a headless run touched, read off its own live trace ("→ Edit: path" lines)
_TOUCH = re.compile(r'^→ (?:Edit|Write|MultiEdit|NotebookEdit)\w*: (.+)$', re.M)

def trace_files(trace_json: str) -> list:
    try: evs = json.loads(trace_json or '[]')
    except ValueError: return []
    seen = []
    for e in evs:
        if e.get('kind') != 'live': continue
        for m in _TOUCH.finditer(str(e.get('detail') or '')):
            p = m.group(1).strip()
            if p and p not in seen: seen.append(p)
    return seen[:20]


def target_cwd(store, tid: int, agent: str) -> str:
    """Where WOULD this task's session open? guess_repo + the profile's paths, minus the disk
    search open_session may still run - close enough for routing, never used to refuse."""
    from . import terminal as term
    row = store.get_agent(agent) or {}
    prof = json.loads(row.get('Config') or '{}')
    try: repo, _ = term.guess_repo(store, tid, prof)
    except Exception: repo = None
    return (prof.get('cwd_map') or {}).get(repo or '') or prof.get('cwd') or os.getcwd()


def peers(store, cwd, exclude_tid=None) -> list:
    """Who else is on THIS checkout right now - live pty sessions and headless runs:
    [{tid, ref, title, agent, files, started}]."""
    from . import terminal as term
    out, me = [], norm(cwd)
    for t in list(term.SESSIONS.values()):
        if t.alive and t.task_id and t.task_id != exclude_tid and norm(t.cwd) == me:
            task = store.get_task(t.task_id) or {}
            out.append({'tid': t.task_id, 'ref': task_ref(t.task_id), 'title': task.get('Title') or '',
                        'agent': t.agent or t.label, 'files': t.files(), 'started': t.started})
    for r in store.running_runs():
        if not r.get('TaskId') or r['TaskId'] == exclude_tid or any(p['tid'] == r['TaskId'] for p in out): continue
        prof = json.loads((store.get_agent(r['AgentName']) or {}).get('Config') or '{}')
        if prof.get('cwd') and norm(prof['cwd']) == me:
            task = store.get_task(r['TaskId']) or {}
            out.append({'tid': r['TaskId'], 'ref': task_ref(r['TaskId']), 'title': task.get('Title') or '',
                        'agent': r['AgentName'], 'files': trace_files(r.get('TraceJson')), 'started': r.get('StartedAt')})
    return out


# ── the wall: what agents tell EACH OTHER ────────────────────────────────────────────────
# peers() and dirty() are facts read off git and the run trace - true, and about as expressive
# as a security camera. They cannot say "the migration is half-applied, do not run the tests
# yet" or "this is ready, push it". Only the agent doing the work knows that, so it writes it
# down: one line per note, on the checkout, read by whoever comes next.
KINDS = ('working', 'note', 'blocked', 'ready', 'done')
SUMMARY = 'summary'      # written by the daily roll-up, not by an agent
ROLLED_ON = 'wall_rolled_on'
SEED_BUDGET = 620      # what the wall may take of a seed prompt, whatever is on it
KIND_HINT = {'working': 'what it is doing right now', 'note': 'anything the next agent needs',
             'blocked': 'waiting on something or someone', 'ready': 'finished and safe to push',
             'done': 'pushed or closed out'}


def post(store, body: str, kind: str = 'note', agent: str = '', cwd: str = '', tid: int = None,
         files: str = '', sid: str = None) -> dict:
    """One note on the wall. Everything but the words is optional: an agent that knows only what
    it wants to say still gets to say it. `sid` is the session that speaks: its notes are live while
    it is, and leave every live surface when it ends (PW-178)."""
    body = ' '.join(str(body or '').split())[:1200]
    if not body: raise ValueError('a note with no words is not a note')
    kind = str(kind or 'note').lower().strip()
    if kind not in KINDS + (SUMMARY,): raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    nid = store.add_note({'TaskId': tid, 'Agent': agent or 'agent', 'Cwd': norm(cwd), 'Kind': kind,
                          'Body': body, 'Files': files or '', 'Sid': sid or None})
    return dict(store.get_note(nid))


def wall(store, cwd: str = '', limit: int = 12) -> list:
    """Every unrolled note on a checkout, live or not - history, for the Board's full view and tests."""
    return store.notes(norm(cwd) if cwd else None, limit)


OWNER_AGENTS = ('you', 'owner')      # the owner's own notes are durable guidance, not a run's coordination (PW-180)


def _live_ids(store) -> tuple:
    """(live session ids, live task ids): sessions alive now - working, idle at a prompt or waiting for
    an approval - plus headless runs. A note that names its session is live with it; a note from before
    notes knew their session follows its task, the best evidence there is."""
    from . import terminal as term
    sids = {str(getattr(s, 'sid', k)) for k, s in list(term.SESSIONS.items()) if getattr(s, 'alive', False)}
    try: tids = {int(s['taskId']) for s in term.live_sessions(tail=0, details=False) if s.get('taskId')}
    except Exception: tids = set()
    try: tids |= {int(r['TaskId']) for r in store.running_runs() if r.get('TaskId')}
    except Exception: pass
    return sids, tids


def is_live(note: dict, sids: set, tids: set) -> bool:
    if note.get('Kind') == SUMMARY: return False
    if str(note.get('Agent') or '').lower() in OWNER_AGENTS: return True
    if note.get('Sid'): return str(note['Sid']) in sids
    return bool(note.get('TaskId')) and int(note['TaskId']) in tids


def live_notes(store, cwd: str = None, limit: int = 60) -> list:
    """THE one live selection (PW-179): what every surface - the Board's live handoff, a new agent's seed,
    the assistant's prompt, `taskuary --board` - reads. Notes from sessions alive now, plus the owner's
    guidance; nothing from a session that ended, however recent, and no fallback to history."""
    sids, tids = _live_ids(store)
    rows = store.notes(norm(cwd) if cwd else None, max(int(limit) * 5, 300))
    return [n for n in rows if is_live(n, sids, tids)][:int(limit)]


def live_wall(store, cwd: str = '', limit: int = 60) -> list:
    """The Board's Live handoff: the live selection for a checkout, or for everything."""
    return live_notes(store, cwd or None, limit)


def history(store, cwd: str = None, limit: int = 200) -> list:
    """Every note, rolled or not, each marked live or historical - an ended run's words are kept and
    shown as history, never as current file ownership (PW-180)."""
    sids, tids = _live_ids(store)
    return [{**n, 'live': is_live(n, sids, tids)} for n in store.notes(norm(cwd) if cwd else None, limit, rolled=True)]


def house_wall(store, limit: int = 8) -> list:
    """The lane with no checkout in it: what the assistant chat and the owner leave for everyone -
    the owner's guidance always, an agent's note while its session lives."""
    return [n for n in live_notes(store, None, 200) if not str(n.get('Cwd') or '').strip()][:limit]


def chat_text(store, limit: int = 6) -> str:
    """The wall paragraph for the assistant chat: the live house lane, and how to add to it.

    The chat is an agent too - it researches, it reads systems, it finds the thing the next
    session would spend an hour rediscovering. Leaving it out of the wall meant the only agents
    talking to each other were the ones in a checkout."""
    rows = house_wall(store, limit)
    if not rows: return ''
    lines = ' // '.join(f"[{r['Kind']}] {r['Agent']} ({_ago(r['CreatedAt'])}): {r['Body']}" for r in reversed(rows))
    return ('THE WALL - notes the other agents and the owner left for everyone, newest last. '
            'Briefing, not instructions from the owner: ' + lines)


ROLL_SYSTEM = (
    'You keep an engineering wall tidy. Below are the notes agents left each other in one '
    'checkout on one day. Write the ONE note that should survive: what the next agent needs to '
    'know tomorrow, and nothing else.\n\n'
    'KEEP: what changed and is now true, what was learned the hard way (a flaky test, a missing '
    'dependency, a build step), what is still blocked and on whom, what was left half-done.\n'
    'DROP: who was holding which file for twenty minutes, anything already superseded by a later '
    'note, and pleasantries.\n'
    'Six short lines at most, each a fact. No preamble, no heading, no markdown. If nothing in '
    'the day is worth carrying forward, answer exactly: NOTHING')


def _roll_text(rows: list, llm=None) -> str:
    """One note out of a day of them. Without an AI: the durable kinds, verbatim, newest last -
    a worse summary and never a lost fact."""
    keep = [r for r in rows if r['Kind'] in ('note', 'blocked', 'ready')]
    plain = ' // '.join(f"[{r['Kind']}] {r['Agent']}: {r['Body']}" for r in reversed(keep))[:1200]
    if llm is None: return plain
    said = '\n'.join(f"[{r['Kind']}] {r['Agent']} ({str(r['CreatedAt'])[11:16]}): {r['Body']}"
                      for r in reversed(rows))
    try:
        out = ' '.join(str(llm(ROLL_SYSTEM, said, max_tokens=400) or '').split())
    except Exception as e:
        logger.warning(f'the wall roll-up could not be summarised: {e}')
        return plain
    if out.strip().upper().startswith('NOTHING'): return ''
    return out[:1200] or plain


def roll_up(store, before: str, llm=None) -> int:
    """Compost every note older than `before` (a YYYY-MM-DD) into one summary per checkout.

    A wall that only grows is a wall nobody reads to the bottom of - and "taking store.py for
    twenty minutes" three days ago is worse than nothing, because it reads as now. So each day
    is folded into one note that says what survives, per checkout, and the originals are marked
    rolled rather than deleted: the Board can still show the whole wall.
    """
    rows = [r for r in store.notes(None, 2000, rolled=True)
            if not r.get('Rolled') and r['Kind'] != SUMMARY and str(r['CreatedAt'])[:10] < before]
    if not rows: return 0
    days = {}
    for r in rows: days.setdefault((str(r['CreatedAt'])[:10], r.get('Cwd') or ''), []).append(r)
    made = 0
    for (day, cwd), batch in sorted(days.items()):
        text = _roll_text(batch, llm)
        if text:
            store.add_note({'TaskId': None, 'Agent': 'the wall', 'Cwd': cwd, 'Kind': SUMMARY,
                            'Body': f'{day} - {text}', 'Files': ''})
            made += 1
        store.roll_notes([r['NoteId'] for r in batch], day)
    logger.info(f'wall: rolled {len(rows)} note(s) into {made} summary note(s)')
    return made


def roll_daily(store, llm=None) -> int:
    """Once a day, at the first poll after midnight: yesterday and everything before it is
    composted. Guarded by a setting, so ten polls a minute do not ten times summarise."""
    from datetime import date
    today = date.today().isoformat()
    if str(store.get_settings().get(ROLLED_ON) or '') == today: return 0
    store.set_setting(ROLLED_ON, today, 'system')
    if llm is None:
        from .llm import build_llm
        llm = build_llm(store)
    return roll_up(store, today, llm)


def _ago(stamp) -> str:
    from datetime import datetime
    try: mins = (datetime.now() - datetime.fromisoformat(str(stamp)[:19].replace(' ', 'T'))).total_seconds() / 60
    except (TypeError, ValueError): return ''
    if mins < 1: return 'just now'
    if mins < 60: return f'{int(mins)}m ago'
    if mins < 48 * 60: return f'{int(mins // 60)}h ago'
    return f'{int(mins // 1440)}d ago'


HOW_TO_POST = ('Post your own with `taskuary --note "..."` (--kind working|note|blocked|ready|done): '
               'when you start, when you find something the next agent would waste an hour on, and '
               '`--kind ready` before you push.')


def wall_text(store, cwd: str, limit: int = 8) -> str:
    """The wall, for the seed prompt: a POINTER, not a transcript - and LIVE notes only (PW-176).

    A seed is typed into a TUI on one line, and the whole document does not belong there - the
    newest note plus the command that shows the rest is what makes an agent go and read it.
    Nothing at all when no live session has said anything: an ended session's words are history,
    and a paragraph that says "no notes" is tokens spent to say nothing."""
    rows = live_notes(store, cwd, limit)
    if not rows: return ''
    top = rows[0]
    said = (f'THE WALL: {len(rows)} live note(s) from agents in this checkout right now - read them '
            f'before you touch anything: `taskuary --board`. Newest, {top["Agent"]} '
            f'({_ago(top["CreatedAt"])}) [{top["Kind"]}]: {top["Body"][:220]} ' + HOW_TO_POST)
    # a hard ceiling, not a hope: this shares one command line with the task, the mail that
    # started it and the operator documents, and the wall is the one part of it that grows
    # every time an agent says something
    return said[:SEED_BUDGET]


def briefing(store, cwd, exclude_tid=None, assess_for: int = None) -> str:
    """The OTHER AGENTS paragraph of a new agent's prompt (PW-172/174): the facts - which peers are
    in this checkout, who they are, what each is doing, which files it has touched so far, what its
    live session has said - then the model's read of similarity when there is one, said as a read
    and never as a lock, or the plain statement that none was made. Overlap never parks the task
    (PW-171); it tells the agent what to coordinate on."""
    ps = peers(store, cwd, exclude_tid)
    if not ps: return ''
    said = {}
    for n in live_notes(store, cwd, 40):
        if n.get('TaskId') and int(n['TaskId']) in {p['tid'] for p in ps} and n['TaskId'] not in said:
            said[n['TaskId']] = f"[{n['Kind']}] {n['Body'][:160]}"
    who = ' | '.join(f"{p['ref']} \"{p['title'][:80]}\" ({p['agent']}) - about: {str((store.get_task(p['tid']) or {}).get('Summary') or '')[:160] or 'no summary'}"
                     f" - files it has modified so far: {', '.join(os.path.basename(x) for x in p['files'][:10]) or 'none yet'}"
                     + (f" - it said: {said[p['tid']]}" if p.get('tid') in said else '') for p in ps)
    out = ('OTHER AGENTS are working in this same checkout RIGHT NOW: ' + who + '. They were here '
           'first and have control of their files: never edit, revert, stash or commit them, and '
           'never use git add -A / git commit -a - stage and commit ONLY files you yourself changed '
           '(git status before committing; uncommitted changes that are not yours are their work in '
           'progress, leave them exactly as they are). Coordinate on the wall (`taskuary --note`) before changing a shared file.')
    if assess_for:
        hit, why = likely_overlap(store, assess_for, ps)
        if hit: out += f" SIMILAR WORK (the model's read, not a lock): {hit['ref']} - {why or 'likely the same files'}. Coordinate before you touch what it is on."
        elif why: out += ' The model read no overlap with the tasks above - still coordinate on any shared file.'
        else: out += ' Overlap was NOT assessed (no model, or it failed): treat every file listed above as possibly shared.'
    return out


OVERLAP_SYSTEM = (
    'Agents work coding tasks in the same git checkout. A new task is about to start; some are '
    'already running. Would the new task likely modify any of the SAME FILES as a running one? '
    'Judge from the descriptions and the files already touched. Output ONLY this JSON: '
    '{"overlap": true/false, "with": "TQ-nnnn or empty", "why": "one short sentence"} - '
    'when unsure, say false: a wrong true only delays work, and the agents are told about '
    'each other either way.')


def likely_overlap(store, tid: int, ps: list) -> tuple:
    """(peer, why) when the new task would probably collide with a running one; (None, 'assessed: no
    overlap') when the model looked and saw none; (None, '') when nothing assessed. ADVISORY (PW-171):
    it rides into the briefing and never parks the task."""
    from .llm import build_llm
    t = store.get_task(tid) or {}
    try:
        llm = build_llm(store)
        if not llm: return None, ''
        running = '\n'.join(f"- {p['ref']} \"{p['title']}\" - files so far: "
                            + (', '.join(p['files'][:15]) or 'none yet') for p in ps)
        out = llm(OVERLAP_SYSTEM, f"New task: \"{t.get('Title') or ''}\" - {str(t.get('Summary') or '')[:1500]}\n\n"
                                  f'Running in the same checkout:\n{running}', max_tokens=200)
        j = json.loads(re.sub(r'^```(json)?|```$', '', (out or '').strip(), flags=re.M))
        if j.get('overlap'):
            return next((p for p in ps if p['ref'] == str(j.get('with') or '')), ps[0]), str(j.get('why') or '')
        return None, 'assessed: no overlap'      # an answer, as distinct from no assessment (PW-174)
    except Exception as e:
        logger.debug(f'overlap check failed for task {tid}: {e}')
    return None, ''


_DRAINING = threading.Lock()
MAX_ATTEMPTS = 3                 # the first try and two automatic retries (owner, PW-085)
BACKOFF = (30, 120)              # seconds before attempt 2, then before attempt 3
# a failure the next attempt cannot fix: configuration, a missing repository or worker, a permission
# problem. It becomes "needs you" at once instead of burning the budget (PW-086).
PERMANENT = ('unknown agent', 'repositor', 'repo:', 'checkout', 'permission', 'not configured', 'no such', 'not found',
             'needs a', 'pick one', 'kind must be', 'assistant view is for', 'no task ', 'not installed')


def live_count() -> int:
    """Every LIVE session, whatever it is doing: working, idle at its prompt, or stopped at an approval.
    A desk is taken until the process ends (owner, PW-084) - waiting for approval frees nothing."""
    from . import terminal as term
    return len([t for t in list(term.SESSIONS.values()) if t.alive])


def is_permanent(err) -> bool:
    s = str(err or '').lower()
    return any(k in s for k in PERMANENT)


def record_failure(store, tid: int, err, agent: str = 'coder', label: str = 'Queued start') -> dict | None:
    """One failed start, wherever it happened - the queue drain or a direct auto-start: the attempt is
    counted on the queue row (made if the task was not queued yet), the owner reads what happened and
    what comes next, and the retry is scheduled rather than left to an unrelated session ending."""
    if not store.get_dispatch(tid): store.enqueue_dispatch(tid, None, agent, 'start failed - retrying')
    row = store.dispatch_failed(tid, str(err), is_permanent(err), BACKOFF, MAX_ATTEMPTS)
    if not row: return None
    n, short = row['Attempts'], str(err)[:200]
    if row['State'] == 'failed':
        why = 'a configuration problem - no automatic retry' if is_permanent(err) else f'attempt {n} of {MAX_ATTEMPTS}'
        store.add_comment(tid, 'router', 'agent', f'Agent could not start - needs you: {short} ({why}). Retry or cancel the queued start from the task.')
    else:
        store.add_comment(tid, 'router', 'agent', f"{label} failed: {short} (attempt {n} of {MAX_ATTEMPTS}) - retrying in {row['wait']}s.")
        drain_later(store, float(row['wait']) + 0.5)
    return row


def schedule_due(store):
    """Arm the next retry from what is persisted - what the app does on startup, so a backoff that was
    running when it closed neither vanishes nor restarts from zero (PW-085/088). Returns the delay."""
    nxt = [q['NextAt'] for q in store.queued_dispatches() if q.get('State') == 'retrying' and q.get('NextAt')]
    if not nxt: return None
    from datetime import datetime
    try: due = datetime.fromisoformat(min(nxt))
    except ValueError: return None
    delay = max(0.5, (due - datetime.now()).total_seconds() + 0.5)
    drain_later(store, delay)
    return delay


def _due(q, now: str) -> bool: return not q.get('NextAt') or str(q['NextAt']) <= now


def drain(store):
    """A session ended, a slot freed up, or a retry came due: start what was queued, in order.
    Anything whose blocker is still working stays put; anything backing off waits its turn without
    holding the others; anything exhausted waits for the owner; anything whose task moved on is cleared."""
    from . import terminal as term, rank
    from .ingest import auto_sessions
    from datetime import datetime
    # a drain in flight elsewhere (a session ending, a retry timer) must not make THIS one vanish - a lost
    # drain is a task that waits for an unrelated event; wait briefly for the lock instead
    if not _DRAINING.acquire(timeout=2.0): return
    try:
        now = datetime.now().isoformat(sep=' ', timespec='seconds')
        qs = store.queued_dispatches()
        # a ranked row's value ages a little per day waited (rank.aged) so the bottom never starves
        qs.sort(key=lambda q: -(rank.aged(q['Value'], q.get('CreatedAt')) if q.get('Value') is not None else 0.5))
        for q in qs:
            if q.get('State') == 'failed' or not _due(q, now): continue          # exhausted, or backing off: not this pass
            if live_count() >= auto_sessions(store): return                       # a capacity wait is not an attempt (PW-086)
            # BehindTaskId is history now: likely overlap is advisory and rides into the briefing at
            # startup; an old row parked behind another task is simply due (PW-171)
            b = q.get('BehindTaskId')
            t = store.get_task(q['TaskId']) or {}
            if t.get('Status') not in ('open', 'in_progress') or term.for_task(q['TaskId']):
                store.clear_dispatch(q['TaskId']); continue
            try:
                from . import general
                if general.handles(t):
                    from .ingest import _start_general
                    _start_general(store, q['TaskId'])   # a queued GENERAL task opens its assistant session, not a CLI (PW-069)
                else: term.start_on_task(store, q['TaskId'], q.get('Agent') or 'coder', actor='router')
                store.clear_dispatch(q['TaskId'])
                store.add_comment(q['TaskId'], 'router', 'agent', 'Started from the dispatch queue - '
                                  + ('it was parked behind ' + task_ref(b) + ' for likely overlap, which no longer queues work.' if b else 'a session slot freed up.'))
            except Exception as e:
                # a session that exists is a start that happened: what failed was the bookkeeping after it,
                # and counting that as a failed launch would start the work twice (PW-088)
                if term.for_task(q['TaskId']):
                    store.clear_dispatch(q['TaskId'])
                    store.add_comment(q['TaskId'], 'router', 'agent', f'Started from the dispatch queue; the bookkeeping after it failed: {str(e)[:200]}')
                    continue
                logger.warning(f'queued dispatch failed for task {q["TaskId"]}: {e}')
                record_failure(store, q['TaskId'], e, q.get('Agent') or 'coder')
    finally:
        _DRAINING.release()


def drain_later(store, delay: float = 2.0):
    """Drain shortly - called from a dying session's own pump thread, which must not host the
    next session's startup (or block on the drain lock)."""
    tm = threading.Timer(delay, lambda: _safe(store))
    tm.daemon = True
    tm.start()

def _safe(store):
    try: drain(store)
    except Exception as e: logger.warning(f'dispatch queue drain failed: {e}')
