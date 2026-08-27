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


def norm(p): return os.path.normcase(os.path.normpath(p or ''))


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
    for t in term.SESSIONS.values():
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
            if len([t for t in term.SESSIONS.values() if t.alive]) >= auto_sessions(store): return
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
