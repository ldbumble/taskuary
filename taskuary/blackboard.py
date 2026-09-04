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
         files: str = '') -> dict:
    """One note on the wall. Everything but the words is optional: an agent that knows only what
    it wants to say still gets to say it."""
    body = ' '.join(str(body or '').split())[:1200]
    if not body: raise ValueError('a note with no words is not a note')
    kind = str(kind or 'note').lower().strip()
    if kind not in KINDS + (SUMMARY,): raise ValueError(f"kind must be one of {', '.join(KINDS)}")
    nid = store.add_note({'TaskId': tid, 'Agent': agent or 'agent', 'Cwd': norm(cwd), 'Kind': kind,
                          'Body': body, 'Files': files or ''})
    return dict(store.get_note(nid))


def wall(store, cwd: str = '', limit: int = 12) -> list:
    return store.notes(norm(cwd) if cwd else None, limit)


def live_wall(store, cwd: str = '', limit: int = 60) -> list:
    """Task notes for sessions alive now, plus the shared house lane.

    Board notes are durable, but the UI calls this surface Live handoff. Filtering only at the
    daily roll-up left notes from closed sessions looking current for hours (or indefinitely).
    """
    from . import terminal as term
    try:
        live_tids = {int(s['taskId']) for s in term.live_sessions(tail=0, details=False)
                     if s.get('taskId')}
    except Exception:
        live_tids = set()
    rows = store.notes(norm(cwd) if cwd else None, max(int(limit) * 5, 300))
    return [n for n in rows if not n.get('TaskId') or int(n['TaskId']) in live_tids][:int(limit)]


def house_wall(store, limit: int = 8) -> list:
    """The lane with no checkout in it: what the assistant chat and the owner leave for
    everyone. A chat has no repository, so this is the whole of its wall."""
    return [n for n in store.notes(None, 200) if not str(n.get('Cwd') or '').strip()][:limit]


def chat_text(store, limit: int = 6) -> str:
    """The wall paragraph for the assistant chat: the house lane, and how to add to it.

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
    """The wall, for the seed prompt: a POINTER, not a transcript.

    A seed is typed into a TUI on one line, and the whole document does not belong there - the
    newest note plus the command that shows the rest is what makes an agent go and read it.
    CODER.md carries the full etiquette; this is the nudge that says there is something to read
    RIGHT NOW. Nothing at all when the wall is empty: a paragraph saying "no notes" is tokens
    spent to say nothing."""
    rows = wall(store, cwd, limit)
    if not rows: return ''
    top = rows[0]
    said = (f'THE WALL: {len(rows)} note(s) the agents before you left for this checkout - read them '
            f'before you touch anything: `taskuary --board`. Newest, {top["Agent"]} '
            f'({_ago(top["CreatedAt"])}) [{top["Kind"]}]: {top["Body"][:220]} ' + HOW_TO_POST)
    # a hard ceiling, not a hope: this shares one command line with the task, the mail that
    # started it and the operator documents, and the wall is the one part of it that grows
    # every time an agent says something
    return said[:SEED_BUDGET]


def briefing(store, cwd, exclude_tid=None) -> str:
    """The OTHER AGENTS paragraph of a new agent's prompt. Facts only - task, agent, the files
    it has modified so far - plus the one standing rule: whoever got there first has control."""
    ps = peers(store, cwd, exclude_tid)
    if not ps: return ''
    who = ' | '.join(f"{p['ref']} \"{p['title'][:80]}\" ({p['agent']}) - files it has modified so far: "
                     + (', '.join(os.path.basename(x) for x in p['files'][:10]) or 'none yet') for p in ps)
    return ('OTHER AGENTS are working in this same checkout RIGHT NOW: ' + who + '. They were here '
            'first and have control of their files: never edit, revert, stash or commit them, and '
            'never use git add -A / git commit -a - stage and commit ONLY files you yourself changed '
            '(git status before committing; uncommitted changes that are not yours are their work in '
            'progress, leave them exactly as they are).')


OVERLAP_SYSTEM = (
    'Agents work coding tasks in the same git checkout. A new task is about to start; some are '
    'already running. Would the new task likely modify any of the SAME FILES as a running one? '
    'Judge from the descriptions and the files already touched. Output ONLY this JSON: '
    '{"overlap": true/false, "with": "TQ-nnnn or empty", "why": "one short sentence"} - '
    'when unsure, say false: a wrong true only delays work, and the agents are told about '
    'each other either way.')


def likely_overlap(store, tid: int, ps: list) -> tuple:
    """(peer, why) when the new task would probably collide with a running one, else (None, '').
    Routing only - a wrong yes waits minutes, a wrong no still gets the briefing - so no AI
    configured (or a bad answer) simply starts the task."""
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
    except Exception as e:
        logger.debug(f'overlap check failed for task {tid}: {e}')
    return None, ''


_DRAINING = threading.Lock()

def drain(store):
    """A session ended (or a slot freed up): start what was queued, in arrival order. Anything
    whose blocker is still working stays put; anything whose task moved on is just cleared."""
    from . import terminal as term, rank
    from .ingest import auto_sessions
    if not _DRAINING.acquire(blocking=False): return
    try:
        qs = store.queued_dispatches()
        # a ranked row's value ages a little per day waited (rank.aged) so the bottom never starves
        qs.sort(key=lambda q: -(rank.aged(q['Value'], q.get('CreatedAt')) if q.get('Value') is not None else 0.5))
        for q in qs:
            if len([t for t in list(term.SESSIONS.values()) if t.alive]) >= auto_sessions(store): return
            b = q.get('BehindTaskId')
            if b and (term.for_task(b) or any(r['TaskId'] == b for r in store.running_runs())): continue
            t = store.get_task(q['TaskId']) or {}
            if t.get('Status') not in ('open', 'in_progress') or term.for_task(q['TaskId']):
                store.clear_dispatch(q['TaskId']); continue
            # a ranked task never had the affinity check (it queued before anything ran): give
            # it one on the way out, so two agents do not start on the same files
            if q.get('Value') is not None and not b:
                cwd = target_cwd(store, q['TaskId'], q.get('Agent') or 'coder')
                ps = peers(store, cwd, exclude_tid=q['TaskId']) if cwd else []
                hit, why = likely_overlap(store, q['TaskId'], ps) if ps else (None, '')
                if hit:
                    store._exec('UPDATE dispatchq SET BehindTaskId=?, Reason=? WHERE TaskId=?',
                                (hit['tid'], why or 'likely to touch the same files', q['TaskId']))
                    continue
            store.clear_dispatch(q['TaskId'])
            try:
                term.start_on_task(store, q['TaskId'], q.get('Agent') or 'coder', actor='router')
                store.add_comment(q['TaskId'], 'router', 'agent', 'Started from the dispatch queue - '
                                  + (f'{task_ref(b)} finished with the files it was holding.' if b else 'a session slot freed up.'))
            except Exception as e:
                logger.warning(f'queued dispatch failed for task {q["TaskId"]}: {e}')
                store.add_comment(q['TaskId'], 'router', 'agent', f'Queued start failed: {str(e)[:200]}')
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
