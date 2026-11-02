"""The Advisor's "Report this?" - Taskuary ITSELF failing the same way, counted, and offered as a report for its public tracker.

The owner, 2026-11-01: "can the advisor/assistant create bug report for you to send ... yes the advisor can suggest fixes/features".
So when the app's own machinery breaks the same way again and again - an agent run failing with one error on several tasks, a failure
that began with this version, the in-chat troubleshooter giving up on the same connection - the Advisor raises one idea whose move opens
the Report popup (bugreport.draft: scrubbed, shown whole, the owner's own Submit on GitHub files it). Nothing is filed from here.

Counted, never thought: quiet unless sure. A failure the owner fixes (a refused sign-in) is theirs, not a bug; a stranger's task is never
read; and each problem is raised once - its key is the failure, its sig fixed, so a No sticks (assistant.fresh).
A WISH said again and again is not counted here: telling two wishes apart is reading, and the Assistant drafts one when it is said.
"""
import hashlib, json, re
from datetime import datetime, timedelta

from . import bugreport
from .timewords import plural

DAYS, AFTER_DAYS, BEFORE_DAYS = 7, 14, 30   # the window counted; how long after an update a new failure is "since the update"; before it
N_SAME, N_TASKS, N_SINCE, N_GAVE_UP = 3, 2, 2, 2
VERSIONS = 'report_ideas:versions'          # {version: when this home first ran it} - the app keeps no history of its own updates
SIG = 'once'                                # one idea per problem, whatever its count does next


def _stamp(t: datetime) -> str: return t.strftime('%Y-%m-%d %H:%M:%S')
def _shape(err) -> str:
    "One failure however often it happened: its first line, numbers read as one, the user's folder out."
    first = next((l.strip() for l in str(err or '').splitlines() if l.strip()), '')
    return re.sub(r'\d+', '#', bugreport.to_home(first))[:160]
def _key(*parts) -> str: return 'report:' + hashlib.sha1('|'.join(parts).encode()).hexdigest()[:12]


def updated_at(store, now: datetime) -> str:
    """When this home first ran the version it runs now - written the first time it is asked."""
    from . import __version__
    try: seen = json.loads(store.get_setting(VERSIONS) or '{}') or {}
    except (TypeError, ValueError): seen = {}
    if __version__ not in seen:
        seen[__version__] = _stamp(now)
        store.set_setting(VERSIONS, json.dumps(seen), 'assistant')
    return seen[__version__]


def _cli(store, name) -> str:
    """An agent by its CLI, never its profile's name - a name can be an account (bugreport._brain's rule)."""
    from . import agents
    row = agents.agent_row(store, name) or {}
    try: prof = json.loads(row.get('Config') or '{}')
    except (TypeError, ValueError): prof = {}
    return agents.cli_of(prof if isinstance(prof, dict) else {}, '') or ''


def _owners(store, tid) -> bool:
    """A task whose words the owner vouches for. A stranger's - or one that cannot be read - is never counted toward a report."""
    from . import origin
    if not tid: return True
    try: return origin.of_task(store, int(tid))[0] != 'stranger'
    except Exception: return False


def _idea(key, text, why, report) -> dict:
    return {'key': key, 'kind': 'report', 'sig': SIG, 'block': 'health', 'text': text,
            'action': {'type': 'report', 'report': {'kind': 'bug', 'screen': 'Advisor', **report}, 'why': why}}


def agent_failures(store, now: datetime) -> list:
    """An agent run failing with the same error N_SAME+ times on N_TASKS+ tasks this week - or N_SINCE+ times since an update, never
    before it. One task failing three times is that task; three tasks failing one way is the app."""
    from .outbound import auth_fix
    from .agents import _UNAVAILABLE
    since, upd = _stamp(now - timedelta(days=max(DAYS, BEFORE_DAYS))), updated_at(store, now)
    rows = store._rows("SELECT TaskId, AgentName, LastError, IFNULL(FinishedAt, IFNULL(UpdatedAt, StartedAt)) At FROM run "
                       "WHERE Status='error' AND IFNULL(LastError,'')<>'' AND IFNULL(FinishedAt, IFNULL(UpdatedAt, StartedAt))>=?", (since,))
    groups = {}
    for r in rows:
        if auth_fix(r['LastError']) or not _owners(store, r['TaskId']): continue          # a sign-in is the owner's to fix
        if _UNAVAILABLE.search(str(r['LastError'])): continue                             # ...and a usage limit is the plan's, not a bug
        groups.setdefault((_cli(store, r['AgentName']), _shape(r['LastError'])), []).append(r)
    from . import __version__
    week, fresh_update = _stamp(now - timedelta(days=DAYS)), upd >= _stamp(now - timedelta(days=AFTER_DAYS))
    out = []
    for (cli, shape), rs in groups.items():
        recent = [r for r in rs if str(r['At']) >= week]
        # ...a failure this version brought: none of its kind in the month before the update, and the update recent
        tasks, new = {r['TaskId'] for r in recent}, fresh_update and all(str(r['At']) >= upd for r in rs)
        if not shape or not (len(recent) >= N_SAME and len(tasks) >= N_TASKS or new and len(recent) >= N_SINCE): continue
        err = max(recent, key=lambda r: str(r['At']))['LastError']
        who, when = f'{cli} agent' if cli else 'agent', f' since Taskuary updated to {__version__}' if new else ' this week'
        out.append(_idea(_key('agent', cli, shape), f"{who[0].upper()}{who[1:]} runs failed the same way {len(recent)} times{when} - {shape[:80]}.",
                         f"{len(recent)} runs on {plural(len(tasks), 'task')} ended with one error"
                         + (', none before the update' if new else '') + ": the same failure on different work is Taskuary's, not the work's",
                         {'trying': f"run {'a ' + who if cli else 'an agent'} on a task", 'happened': f'the run failed the same way {len(recent)} times{when}',
                          'message': str(err)[:2000], 'route': f"agent {cli or 'run'}"}))
    return out


def gave_up(store, now: datetime) -> list:
    """The troubleshooter, in the chat, ending on Report this bug for the same connection N_GAVE_UP+ times in two weeks: nothing it can
    repair, and the owner was not asked to fix it - it is Taskuary's. Read off the chat's own lines (concierge.record keeps each answer's
    buttons on it), so nothing new is written to find it."""
    from .concierge import MARK
    rows = store._rows("SELECT Body, CreatedAt FROM comment WHERE Body LIKE ? AND Body LIKE ? AND CreatedAt>=? ORDER BY CommentId",
                       (f'%{MARK}%', '%"verb": "bug"%', _stamp(now - timedelta(days=2 * DAYS))))
    by = {}
    for r in rows:
        try: card = json.loads(str(r['Body']).split(MARK, 1)[1].rsplit(' -->', 1)[0])
        except (IndexError, ValueError): continue
        for c in card.get('chips') or []:
            rep = c.get('report') if c.get('verb') == 'bug' else None
            if isinstance(rep, dict) and not rep.get('kind') and str(rep.get('route') or '').startswith('connector '):
                by.setdefault(rep['route'], []).append(rep)
    return [_idea(_key('gave-up', route), f"The fix-it check could not repair {route[len('connector '):]} {len(reps)} times in two weeks.",
                  'it found nothing it or you could fix, each time - that is a fault in Taskuary to report',
                  {'trying': f"get {route[len('connector '):]} working again from the Assistant", 'happened': f'the check could not repair it, {len(reps)} times',
                   'message': str(reps[-1].get('message') or '')[:2000], 'route': route})
            for route, reps in by.items() if len(reps) >= N_GAVE_UP]


def ideas(store, now: datetime = None) -> list:
    """Every "Report this?" worth raising now, as Advisor lines (assistant.run raises each once - fresh). One failing source never costs
    the others."""
    now, out = now or datetime.now(), []
    for f in (agent_failures, gave_up):
        try: out += f(store, now)
        except Exception as e:
            from loguru import logger
            logger.debug(f'report ideas: {f.__name__} was skipped - {e}')
    return out
