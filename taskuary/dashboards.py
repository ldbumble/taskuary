"""Dashboards: a report you LOOK at. Same sources, same schedule, same rail row - no AI at run time.

A dashboard is a report source (Channel='report') whose config is {"type": "dashboard", "title", schedule keys,
"sources": [...], "filters": {...}, "components": [...]}. Its sources are the deterministic reads a report already
makes (SQL, a sheet, a file, Taskuary's own tables); its components are PRESETS from one small library
(website/src/dashboard/), each bound to one source's columns. The AI writes the spec once, at setup (compose.py
compose_dashboard), and the owner approves it rendered over real rows. A run re-reads the sources and keeps the rows;
the page slices them - the date range and the segment filter re-slice every component, a bar drills into its rows.

The rules the presets follow (docs/notes/dashboards.md): one screen, the number first, one palette in both themes,
one axis, thin marks, recessive chrome, filters in one row above everything they scope, a table behind every chart.
"""
import json, re, time
from datetime import datetime, timedelta
from loguru import logger

from .processing_order import known, level
from .store import task_ref

# kind -> (bindings it cannot draw without, the width it takes on a four-column grid)
KINDS = {'stat': ((), 1), 'progress': (('target',), 1), 'line': (('x',), 2), 'area': (('x',), 2), 'bar': (('x',), 2),
         'stacked': (('x', 'series'), 2), 'table': ((), 4), 'list': (('label',), 2)}
AGGS = ('count', 'sum', 'avg', 'median', 'min', 'max')
RANGES = (7, 30, 90, 0)            # days back; 0 is everything the sources returned
MAX_SOURCES, MAX_COMPONENTS, ROWS = 8, 20, 2000
COLUMN_KEYS = ('x', 'y', 'series', 'label', 'meta', 'value', 'date')


def is_dashboard(cfg) -> bool: return isinstance(cfg, dict) and cfg.get('type') == 'dashboard'
def cfg_of(src) -> dict:
    try: return json.loads((src or {}).get('ConfigJson') or '{}') or {}
    except ValueError: return {}


# ── Taskuary's own tables as rows (the demo's dashboard, and anybody's "how is my week going") ─────────────
def _since(days): return (datetime.now() - timedelta(days=max(1, int(days or 90)))).strftime('%Y-%m-%d %H:%M:%S')


def _tasks(store, days):
    """One row per task opened in the window or still open: when its ask arrived (its first mail, else when it was made)."""
    rows = store._rows("""SELECT t.TaskId, t.Title, t.Kind, t.Status, t.Priority, t.CreatedAt, t.ClosedAt, t.UpdatedAt,
        (SELECT MIN(m.SentAt) FROM message m WHERE m.TaskId=t.TaskId) FirstAt
        FROM task t WHERE t.ParentId IS NULL AND (t.CreatedAt>=? OR t.Status NOT IN ('done','dropped'))
        -- the Assistant's own chat records are not work (the rail and Tasks leave them out too): the owner, 2026-10-26, found a
        -- "Taskuary guide" row on the built-in dashboard that opened an empty task
        AND COALESCE(t.SourceRef,'') NOT IN ('assistant:dock','assistant:concierge')
        ORDER BY t.TaskId DESC LIMIT ?""", (_since(days), ROWS))
    return [{'task_id': r['TaskId'], 'ref': task_ref(r['TaskId']), 'title': r['Title'] or '', 'kind': r['Kind'] or 'general',
             'status': r['Status'] or 'open', 'state': 'closed' if r['Status'] in ('done', 'dropped') else 'open',
             'priority': level(r['Priority']), 'arrived': (a := str(r['FirstAt'] or r['CreatedAt'] or '')[:10]),
             # a task closed before ClosedAt was stamped on every close says when it was last touched instead
             'closed': str(r['ClosedAt'] or (r['UpdatedAt'] if r['Status'] in ('done', 'dropped') else '') or '')[:10], 'waiting': _waited(a)}
            for r in rows]


def _waited(day) -> str:
    """How long since the ask arrived, as a person says it - a list's meta line under "waiting longest"."""
    try: n = (datetime.now().date() - datetime.strptime(day, '%Y-%m-%d').date()).days
    except ValueError: return ''
    return 'today' if n <= 0 else 'yesterday' if n == 1 else f'{n} days' if n < 60 else f'{n // 30} months'


def _mail(store, days):
    """One row per message that came IN (not the reports' own rows): its day, channel and sender."""
    rows = store._rows("""SELECT MessageId, TaskId, Channel, SentAt, FromName, FromEmail, SourceName FROM message
        WHERE IFNULL(Direction,'in')='in' AND Channel<>'report' AND Status<>'context' AND SentAt>=? ORDER BY SentAt DESC LIMIT ?""",
                       (_since(days), ROWS))
    return [{'message_id': r['MessageId'], 'task_id': r['TaskId'], 'day': str(r['SentAt'] or '')[:10], 'channel': r['Channel'] or 'email',
             'sender': r['FromName'] or r['SourceName'] or r['FromEmail'] or '', 'became_task': 'yes' if r['TaskId'] else 'no'} for r in rows]


# the stages an ask passes, in order: a message is counted at every stage it reached, so the funnel's bars only ever step down
STAGES = ('Came in', 'Triaged', 'On a task', 'Task closed')
_JUDGED = """EXISTS (SELECT 1 FROM route r WHERE r.MessageId=m.MessageId AND r.ParseError IS NULL
    AND IFNULL(r.Reason,'') NOT LIKE 'awaiting AI triage%' AND IFNULL(r.Reason,'') NOT LIKE '%triage failed (%'
    AND IFNULL(r.Reason,'') NOT LIKE 'AI triage returned an answer it could not read%')"""


def _flow(store, days):
    """How far what came in got: one row per message per stage it reached (STAGES) - came in, triaged (a verdict, not a failure
    or a wait for an AI), on a task, its task closed. A bar over `stage` is the funnel; `channel` slices it like the mail."""
    rows = store._rows(f"""SELECT m.MessageId, m.TaskId, m.Channel, m.SentAt, t.Status TaskStatus, (m.TaskId IS NOT NULL OR {_JUDGED}) Judged
        FROM message m LEFT JOIN task t ON t.TaskId=m.TaskId
        WHERE IFNULL(m.Direction,'in')='in' AND m.Channel<>'report' AND m.Status<>'context' AND m.SentAt>=? ORDER BY m.SentAt DESC LIMIT ?""",
                       (_since(days), ROWS))
    out = []
    for r in rows:
        reached = 1 + bool(r['Judged']) + bool(r['TaskId']) + (bool(r['TaskId']) and r['TaskStatus'] in ('done', 'dropped'))
        base = {'message_id': r['MessageId'], 'task_id': r['TaskId'], 'day': str(r['SentAt'] or '')[:10], 'channel': r['Channel'] or 'email'}
        out += [{**base, 'stage': st} for st in STAGES[:reached]]
    return out


# how an agent's session ended, by its last word (workerstate.KINDS): a turn that ended with the agent at its prompt waits on the
# owner, as an open request does - only an explicit finish is "finished". The older run table's statuses read the same way.
OUTCOME = {'finished': 'finished', 'done': 'finished', 'failed': 'failed', 'stopped': 'stopped', 'disconnected': 'stopped',
           'turn_end': 'waiting on you', 'input_needed': 'waiting on you', 'approval_needed': 'waiting on you', 'stalled': 'waiting on you'}


def _agent_runs(store, days):
    """One row per agent session: the day it started, the agent, how it ended (outcome) and the minutes to its last word. A session
    is its worker events (workerstate.record - every CLI's hooks write them); the older `run` table's rows ride along."""
    since = _since(days)
    rows = store._rows("""SELECT e.TaskId, e.Sid, e.Started, l.Kind, t.Assignee,
        (SELECT tr.Agent FROM transcript tr WHERE tr.Sid=e.Sid AND IFNULL(tr.Agent,'')<>'' ORDER BY tr.TranscriptId DESC LIMIT 1) Agent,
        (julianday(l.CreatedAt)-julianday(e.Started))*1440 Mins
        FROM (SELECT TaskId, Sid, MIN(CreatedAt) Started, MAX(Id) LastId FROM worker_event WHERE CreatedAt>=? AND Kind<>'floor_denied'
              GROUP BY TaskId, Sid) e JOIN worker_event l ON l.Id=e.LastId LEFT JOIN task t ON t.TaskId=e.TaskId
        ORDER BY e.Started DESC LIMIT ?""", (since, ROWS))
    out = []
    for r in rows:
        who = r['Agent'] or (str(r['Assignee'])[6:] if str(r['Assignee'] or '').startswith('agent:') else '') or 'agent'
        end = OUTCOME.get(r['Kind'], 'working')
        out.append({'run_id': r['Sid'], 'task_id': r['TaskId'], 'ref': task_ref(r['TaskId']) if r['TaskId'] else '', 'day': str(r['Started'] or '')[:10],
                    'agent': who, 'status': r['Kind'] or 'working', 'outcome': end,
                    'minutes': round(max(0.0, r['Mins']), 1) if r['Mins'] is not None and end != 'working' else None})
    for r in store._rows("""SELECT RunId, TaskId, AgentName, Status, StartedAt, (julianday(FinishedAt)-julianday(StartedAt))*1440 Mins
                            FROM run WHERE StartedAt>=? ORDER BY RunId DESC LIMIT ?""", (since, ROWS)):
        st = r['Status'] or 'running'
        out.append({'run_id': r['RunId'], 'task_id': r['TaskId'], 'ref': task_ref(r['TaskId']) if r['TaskId'] else '', 'day': str(r['StartedAt'] or '')[:10],
                    'agent': r['AgentName'] or 'agent', 'status': st, 'outcome': OUTCOME.get(st, 'working'),
                    'minutes': round(r['Mins'], 1) if r['Mins'] is not None else None})
    return sorted(out, key=lambda x: x['day'], reverse=True)[:ROWS]


def _replies(store, days):
    """One row per reply the owner decided: how many hours from the ask arriving to the answer."""
    rows = store._rows("""SELECT r.ReviewId, r.TaskId, r.Status, r.DecidedAt, m.SentAt, m.Channel,
        (julianday(r.DecidedAt)-julianday(m.SentAt))*24 Hrs FROM review r JOIN message m ON m.MessageId=r.MessageId
        WHERE r.DecidedAt IS NOT NULL AND r.DecidedAt>=? AND r.Kind NOT IN ('action','slot','escalation') ORDER BY r.ReviewId DESC LIMIT ?""",
                       (_since(days), ROWS))
    return [{'task_id': r['TaskId'], 'day': str(r['DecidedAt'] or '')[:10], 'channel': r['Channel'] or 'email', 'status': r['Status'],
             'hours': round(max(0.0, r['Hrs']), 1) if r['Hrs'] is not None else None} for r in rows]


def _ai_usage(store, days):
    from . import aiusage
    return aiusage.dataset(store, days)


DATASETS = {'tasks': (_tasks, 'task_id, ref, title, kind, status, state (open|closed), priority (regular|important|urgent), arrived (date), closed (date), '
                             'waiting (how long since it arrived, in words)'),
            'mail': (_mail, 'message_id, task_id, day (date), channel, sender, became_task (yes|no)'),
            'flow': (_flow, 'message_id, task_id, day (date), channel, stage (Came in|Triaged|On a task|Task closed - one row per stage reached)'),
            'agent_runs': (_agent_runs, 'run_id, task_id, ref, day (date), agent, status, outcome (finished|failed|stopped|waiting on you|working), minutes'),
            'replies': (_replies, 'task_id, day (date the reply was decided), channel, status, hours (ask to answer)'),
            'ai_usage': (_ai_usage, 'day (date), task_id (agent runs only), kind (agent run|one call), job, what (the job in words), brain, model, '
                                    'tier (quick|normal|hard|as set), calls, tokens_in, cached, tokens_out, tokens (in + out), seconds, minutes')}


# ── the built-in dashboard: what the End of day checkup is to reports. Every install gets it (store.SEEDED_REPORTS), and New
# dashboard offers it again in one press. It reads ONLY this app's own tables, so it draws for anybody, with nothing connected.
# ...and what the AI used (the owner, 2026-11-06: "dashboard of the taskuary thing included in current one the token usage and per
# model"): tokens per model per day, by job, an agent run's tokens and time, and how many calls were quick, normal or hard
AI_TILES = [
    {'kind': 'stacked', 'title': 'AI tokens by model, per day', 'said': 'Tokens per model per day, stacked', 'source': 'ai', 'x': 'day',
     'series': 'model', 'agg': 'sum', 'y': 'tokens', 'w': 2},
    {'kind': 'bar', 'title': 'AI tokens by job', 'said': 'Tokens by what the AI was doing, top 8 jobs', 'source': 'ai', 'x': 'what', 'agg': 'sum',
     'y': 'tokens', 'limit': 8, 'w': 2},
    {'kind': 'stat', 'title': 'Tokens per agent run', 'said': 'The median tokens one agent run uses', 'source': 'ai', 'agg': 'median', 'y': 'tokens',
     'where': {'kind': 'agent run'}, 'good': 'none'},
    {'kind': 'stat', 'title': 'Minutes per agent run', 'said': 'The median minutes one agent run takes', 'source': 'ai', 'agg': 'median', 'y': 'minutes',
     'unit': 'min', 'where': {'kind': 'agent run'}, 'good': 'none'},
    {'kind': 'bar', 'title': 'AI calls: quick, normal or hard', 'said': 'How many AI calls were quick, normal or hard, in that order', 'source': 'ai',
     'x': 'tier', 'agg': 'sum', 'y': 'calls', 'order': ['quick', 'normal', 'hard'], 'w': 1}]
# ...and the total, in the top row (the owner, 2026-11-07: "I don't see the token count?" - the AI tiles came last, below the fold).
# The ai_usage rows carry tokens and time, no price, so there is no cost to show beside it
AI_TOKENS = {'kind': 'stat', 'title': 'AI tokens', 'said': 'How many tokens the AI used', 'source': 'ai', 'agg': 'sum', 'y': 'tokens', 'good': 'none'}
AI_SOURCE_KEY = 'ai'
_own = lambda key, label, dataset, date: {'key': key, 'label': label, 'type': 'taskuary_data', 'dataset': dataset, 'days': 90, 'date': date}
_by_model, _by_job, _per_run, _run_minutes, _calls = AI_TILES
GLANCE = {'type': 'dashboard', 'title': 'Taskuary at a glance', 'daily_at': '07:00',
          'sources': [_own('mail', 'What came in', 'mail', 'day'), _own('flow', 'How far it got', 'flow', 'day'),
                      _own('tasks', 'Tasks', 'tasks', 'arrived'), _own('closed', 'Tasks closed', 'tasks', 'closed'),
                      _own('agents', 'Agent sessions', 'agent_runs', 'day'), _own('replies', 'Replies', 'replies', 'day'),
                      _own('ai', 'AI used', 'ai_usage', 'day')],
          'filters': {'range': 7, 'segment': 'channel'},
          # four columns with every row filled: a 1-wide tile is a number, a 2-wide one a chart
          'components': [
              # the numbers first: what came in, what it became, what is still open, and what the AI used
              {'kind': 'stat', 'title': 'Came in', 'said': 'How many messages came in', 'source': 'mail', 'agg': 'count'},
              {'kind': 'stat', 'title': 'New tasks', 'said': 'How many new tasks arrived', 'source': 'tasks', 'agg': 'count'},
              {'kind': 'stat', 'title': 'Open now', 'said': 'How many tasks are open right now, lower is better', 'source': 'tasks',
               'agg': 'count', 'where': {'state': 'open'}, 'range': False, 'good': 'down'},
              AI_TOKENS,
              # ...how fast the owner answers and the week's close against its target, beside the funnel (four bars: a tile's height)
              {'kind': 'stat', 'title': 'Median reply time', 'said': 'The median hours from an ask to my reply, lower is better',
               'source': 'replies', 'agg': 'median', 'y': 'hours', 'unit': 'h', 'good': 'down'},
              {'kind': 'progress', 'title': 'Closed this week', 'said': 'Tasks closed in the last 7 days, toward a target of 15',
               'source': 'closed', 'agg': 'count', 'where': {'state': 'closed'}, 'range': 7, 'target': 15},
              {'kind': 'bar', 'title': 'How far it got', 'said': 'How far what came in got, stage by stage, each as a share of what came in',
               'source': 'flow', 'x': 'stage', 'order': list(STAGES), 'share': True, 'w': 2},
              # ...then the days: what came in beside the tokens it took, what the agents did beside what the AI was doing
              {'kind': 'stacked', 'title': 'What came in, by channel', 'said': 'Messages in per day, split by channel, stacked',
               'source': 'mail', 'x': 'day', 'series': 'channel', 'w': 2},
              _by_model,
              {'kind': 'stacked', 'title': 'Agent sessions, and how they ended', 'said': 'Agent sessions per day, split by how they ended',
               'source': 'agents', 'x': 'day', 'series': 'outcome', 'w': 2},
              _by_job,
              # ...an agent's time and tokens
              {'kind': 'stat', 'title': 'Agent time per session', 'said': 'The median minutes an agent session takes',
               'source': 'agents', 'agg': 'median', 'y': 'minutes', 'unit': 'min', 'good': 'none'},
              _per_run, _run_minutes, _calls,
              # ...the rankings
              {'kind': 'bar', 'title': 'Open work by kind', 'said': 'Open tasks right now, by kind', 'source': 'tasks', 'x': 'kind',
               'where': {'state': 'open'}, 'range': False, 'w': 2},
              {'kind': 'bar', 'title': 'Who writes most', 'said': 'Who sends the most messages, top 8', 'source': 'mail', 'x': 'sender', 'limit': 8, 'w': 2},
              # ...and the detail: the asks that have waited longest on the owner, each opening its task
              {'kind': 'list', 'title': 'Waiting longest on you', 'said': 'The open tasks that have waited longest on me, with how long, at most 6',
               'source': 'tasks', 'label': 'title', 'meta': 'waiting', 'where': {'status': 'open'}, 'range': False, 'sort': 'arrived', 'limit': 6, 'w': 4}]}
TEMPLATES = {'glance': {'title': GLANCE['title'], 'config': GLANCE,
                        'explain': 'What came in and from where, how far it got, what is still open, how fast you answer and what your '
                                   'agents did - from this app\'s own records, so there is nothing to connect.'}}


# ── A TILE IS ONE SENTENCE (the owner, 2026-11-06, of the field grid that set a component up: "it's not generalized ... maybe we
# should just use text to say what it shows"). The owner writes what a tile shows; the AI binds it to the sources' real columns once
# (compose.compose_tile) and the sentence stays on the tile as its `said`. A tile saved before then gets one written from its config.
TILE_KEYS = ('kind', 'title', 'said', 'source', 'agg', 'y', 'where', 'range', 'good', 'unit', 'target', 'x', 'series', 'limit', 'order', 'share',
             'label', 'meta', 'sort', 'columns', 'w')
_AGG_SAID = {'sum': 'the total', 'avg': 'the average', 'median': 'the median', 'min': 'the lowest', 'max': 'the highest'}
def _col(k): return str(k or '').replace('_', ' ').strip()


def describe(c: dict, spec: dict = None) -> str:
    """A plain sentence for a tile from its config alone - what a person would have written for it. No AI: deterministic."""
    srcs = {s.get('key'): s for s in (spec or {}).get('sources') or [] if isinstance(s, dict)}
    src, k, agg = _col((srcs.get(c.get('source')) or {}).get('label') or c.get('source')) or 'rows', c.get('kind'), c.get('agg') or 'count'
    src = src[:1].lower() + src[1:] if src[1:2].islower() else src           # "Tasks" reads tasks mid-sentence, "AI used" stays
    what = f'the count of {src}' if agg == 'count' else f"{_AGG_SAID.get(agg, agg)} {_col(c.get('y'))} of {src}"
    head = (f"{what} per {_col(c.get('x'))}" if k in ('line', 'area', 'bar') else
            f"{what} per {_col(c.get('x'))}, split by {_col(c.get('series'))}" if k == 'stacked' else
            f'a table of {src}' + (f": {', '.join(map(_col, c['columns']))}" if c.get('columns') else '') if k == 'table' else
            f"a list of {src}, each reading its {_col(c.get('label'))}" + (f" with its {_col(c['meta'])} under it" if c.get('meta') else '') if k == 'list'
            else what)
    if (w := c.get('where')) and isinstance(w, dict): head += ' where ' + ' and '.join(f'{_col(a)} is {b}' for a, b in w.items())
    r = c.get('range')
    if r is False: head += ' right now'
    elif isinstance(r, int) and not isinstance(r, bool): head += f' in the last {r} days'
    more, lim, srt = [], c.get('limit'), str(c.get('sort') or '')
    if k in ('line', 'area'): more.append('as a line' if k == 'line' else 'as an area')
    if k == 'stacked': more.append('stacked')
    if c.get('order'): more.append('in the order ' + ', '.join(map(str, c['order'])))
    if c.get('share'): more.append('each as a share of the first')
    if srt: more.append(f"sorted by {_col(srt.lstrip('-'))}" + (', highest first' if srt.startswith('-') else ''))
    if lim: more.append(f'top {lim}' if k == 'bar' else f'at most {lim}')
    if k == 'progress' and c.get('target') is not None: more.append(f"toward a target of {c['target']}")
    if c.get('good') in ('up', 'down'): more.append('higher is better' if c['good'] == 'up' else 'lower is better')
    t = ', '.join([head, *more])
    return t[:1].upper() + t[1:]


# the built-in tiles keep the sentences written for them by hand, matched by what they are (a saved copy's AI source may be renamed)
def _bare(c): return json.dumps({k: v for k, v in c.items() if k not in ('said', 'source')}, sort_keys=True)
_GLANCE_SAID = {_bare(c): c['said'] for c in GLANCE['components']}


def with_said(spec: dict) -> dict:
    """The spec with every tile carrying its sentence: the one it has, the built-in one's, or one described from its config."""
    if not is_dashboard(spec) or all(not isinstance(c, dict) or c.get('said') for c in spec.get('components') or []): return spec
    return {**spec, 'components': [{**c, 'said': _GLANCE_SAID.get(_bare(c)) or describe(c, spec)} if isinstance(c, dict) and not c.get('said') else c
                                   for c in spec.get('components') or []]}


def _dataset_columns(name) -> list:
    """The columns a Taskuary dataset returns, read from what DATASETS says of it - for a source that has no rows yet."""
    return [w.strip() for w in re.sub(r'\([^)]*\)', '', DATASETS[name][1]).split(',') if w.strip()] if name in DATASETS else []


def seen_columns(spec: dict, data: dict = None) -> dict:
    """{source key: {'columns': [...], 'values': {column: [values]}}} - what a sentence may be bound to: each source's real columns
    (the rows it returned, else what its Taskuary dataset returns), and the values a short column takes, so a "where" matches them."""
    out, got = {}, (data or {}).get('sources') or {}
    for i, s in enumerate(spec.get('sources') or [], 1):
        if not isinstance(s, dict): continue
        rows = (got.get(k := _key(s, i)) or {}).get('rows') or []
        cols = list(dict.fromkeys(c for r in rows[:200] for c in r)) or (_dataset_columns(s.get('dataset')) if s.get('type') == 'taskuary_data' else [])
        vals = {}
        for c in cols:
            vs = list(dict.fromkeys(str(r[c]) for r in rows if r.get(c) not in (None, '')))
            if vs: vals[c] = vs if len(vs) <= 12 else [*vs[:3], '...']
        out[k] = {'columns': cols, 'values': vals}
    return out


def check_tile(spec: dict, c, seen: dict = None) -> tuple:
    """(the tile, '') or (None, why): one component held to the spec's own check (validate) and, where a source's columns are known,
    bound only to columns it has. Keys no preset reads are dropped."""
    if not isinstance(c, dict): return None, 'the answer was not a tile'
    c = {k: v for k, v in c.items() if k in TILE_KEYS}
    ok, why = validate({'title': 'tile', 'sources': spec.get('sources') or [], 'components': [c]})
    if not ok: return None, why
    name = c.get('title') or c['kind']
    for k in ('target', 'limit'):
        if c.get(k) is not None and (isinstance(c[k], bool) or not isinstance(c[k], (int, float))): return None, f'{name}: "{k}" is a number'
    if c.get('w') is not None and c['w'] not in (1, 2, 3, 4): return None, f'{name}: "w" is 1 to 4 columns'
    if c.get('columns') is not None and not isinstance(c['columns'], list): return None, f'{name}: "columns" is a list'
    cols = set(((seen or {}).get(c['source']) or {}).get('columns') or [])
    if cols:
        want = [c[k] for k in COLUMN_KEYS if isinstance(c.get(k), str) and c.get(k)] + list(c.get('columns') or []) + list((c.get('where') or {}).keys())
        if c.get('sort'): want.append(str(c['sort']).lstrip('-'))
        if miss := sorted({w for w in want if w not in cols}):
            label = next((s.get('label') for s in spec.get('sources') or [] if isinstance(s, dict) and s.get('key') == c['source']), None) or c['source']
            return None, f"{name}: {label} has no column {', '.join(miss)} - it has {', '.join(sorted(cols))}"
    return c, ''


# a sentence read again and again reads the same rows: a source is run once per few minutes, not once per sentence
_PEEKED, PEEK_FOR = {}, 300


def peek(store, spec: dict) -> dict:
    """The rows a sentence is bound against (collect), kept a few minutes per set of sources."""
    sig, now = (id(store), json.dumps(spec.get('sources') or [], sort_keys=True, default=str)), time.monotonic()
    if (hit := _PEEKED.get(sig)) and now - hit[0] < PEEK_FOR: return hit[1]
    data = collect(store, {'sources': spec.get('sources') or []})
    for k in [k for k, (t, _) in _PEEKED.items() if now - t >= PEEK_FOR] + list(_PEEKED)[:max(0, len(_PEEKED) - 7)]: _PEEKED.pop(k, None)
    _PEEKED[sig] = (now, data)
    return data

def templates() -> list: return [{'key': k, 'title': t['title'], 'explain': t['explain']} for k, t in TEMPLATES.items()]
def template(key) -> dict | None: return json.loads(json.dumps(TEMPLATES[key])) if key in TEMPLATES else None      # a copy: never the shared spec


def run_taskuary_data(cfg):
    """{"dataset": "tasks|mail|flow|agent_runs|replies|ai_usage", "days": 90} - Taskuary's own tables as plain rows, no AI: tasks (task_id,
    ref, title, kind, status, state, priority, arrived, closed, waiting), mail (day, channel, sender, became_task), flow (day,
    channel, stage), agent_runs (day, agent, outcome, minutes), replies (day, channel, hours). The rows a dashboard draws from. `store` arrives via resolve_cfg."""
    from .reports import rows_out, row_limit
    name = str(cfg.get('dataset') or '').strip()
    if name not in DATASETS: raise ValueError(f"no Taskuary dataset called {name!r} - choose one of {', '.join(DATASETS)}")
    rows = DATASETS[name][0](cfg['store'], cfg.get('days') or 90)
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit=name.replace('_', ' '), mine=mine)


# A SAVED DASHBOARD SPEAKS THE THREE PRIORITIES TOO (the owner, 2026-10-25: migrate saved filters on high/normal/low): the tasks rows say
# regular / important / urgent now, so a component cut on `priority: high` would draw empty and an `order` of the old four would draw
# bars nobody has. Only Taskuary's own tasks rows are read this way - a SQL table's or a sheet's priority column is its own vocabulary.
def _own_tasks(spec) -> set: return {_key(s, i) for i, s in enumerate(spec.get('sources') or [], 1)
                                     if isinstance(s, dict) and s.get('type') == 'taskuary_data' and s.get('dataset') == 'tasks'}


def three_priorities(spec: dict) -> dict:
    """The spec with every priority it cuts or orders Taskuary's tasks on said in the three words; the same spec when nothing changed."""
    if not is_dashboard(spec) or not (own := _own_tasks(spec)): return spec
    out = json.loads(json.dumps(spec))
    for c in out.get('components') or []:
        if not isinstance(c, dict) or c.get('source') not in own: continue
        w = c.get('where')
        if isinstance(w, dict) and known(w.get('priority')): w['priority'] = level(w['priority'])
        if 'priority' in (c.get('x'), c.get('series')) and isinstance(c.get('order'), list):
            c['order'] = list(dict.fromkeys(level(v) if known(v) else v for v in c['order']))     # low and normal both land on regular
    return out


def with_ai_tiles(spec: dict) -> dict:
    """A saved Taskuary at a glance with the AI-use source and tiles added (2026-11-06) - the same spec when it already reads ai_usage,
    is not the built-in, or has no room under the caps."""
    if not is_dashboard(spec) or spec.get('title') != GLANCE['title']: return spec
    srcs, comps = spec.get('sources') or [], spec.get('components') or []
    if any(isinstance(s, dict) and s.get('dataset') == 'ai_usage' for s in srcs): return spec
    key = AI_SOURCE_KEY if AI_SOURCE_KEY not in {_key(s, i) for i, s in enumerate(srcs, 1) if isinstance(s, dict)} else 'ai_used'
    if len(srcs) + 1 > MAX_SOURCES or len(comps) + len(AI_TILES) > MAX_COMPONENTS: return spec
    src = {**next(s for s in GLANCE['sources'] if s['key'] == AI_SOURCE_KEY), 'key': key}
    return {**spec, 'sources': [*srcs, src], 'components': [*comps, *({**c, 'source': key} for c in AI_TILES)]}


AI_TILES_KEY = 'glance_ai_tiles_added'


def migrate_ai_tiles(store) -> int:
    """An existing install's Taskuary at a glance gets the AI-use tiles, once: an owner who removes them later is not given them again."""
    if store.get_setting(AI_TILES_KEY): return 0
    n = 0
    for src in store.list_sources(active_only=False):
        cfg = cfg_of(src)
        if src.get('Channel') == 'report' and (new := with_ai_tiles(cfg)) != cfg:
            store.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps(new)}, 'migrate'); n += 1
    store.set_setting(AI_TILES_KEY, '1', 'migrate')
    return n


# a tile matched by what it shows, whatever its sentence or its source's name (and its width, `w=False`: the AI calls bar narrowed)
def _shape(c, w=True): return json.dumps({k: v for k, v in c.items() if k not in ('said', 'source', *(() if w else ('w',)))}, sort_keys=True)


def ai_tiles_up(spec: dict) -> dict:
    """A saved Taskuary at a glance whose AI-use tiles still sit at its end (migrate_ai_tiles) with them moved up and the AI tokens total
    in its top row (2026-11-07): an unedited copy becomes today's GLANCE, an edited one keeps its own tiles in its own order with the
    total after its first three numbers and the AI tiles after the rest of them. The same spec when it is not the built-in, already
    shows the total, or its AI tiles are not where they were put (the owner moved them)."""
    if not is_dashboard(spec) or spec.get('title') != GLANCE['title']: return spec
    comps, n = spec.get('components') or [], len(AI_TILES)
    key = next((_key(s, i) for i, s in enumerate(spec.get('sources') or [], 1) if isinstance(s, dict) and s.get('dataset') == 'ai_usage'), None)
    if not key or not all(isinstance(c, dict) for c in comps) or any(_shape(c) == _shape(AI_TOKENS) for c in comps): return spec
    rest, ai = comps[:-n], comps[-n:]
    if [_shape(c, False) for c in ai] != [_shape(c, False) for c in AI_TILES]: return spec
    if sorted(map(_shape, rest)) == sorted(_shape(c) for c in GLANCE['components'] if c['source'] != AI_SOURCE_KEY):
        return {**spec, 'components': [{**c, 'source': key} if c['source'] == AI_SOURCE_KEY else c for c in GLANCE['components']]}
    top = next((i for i, c in enumerate(rest) if c.get('kind') not in ('stat', 'progress')), len(rest)); k = min(top, 3)
    total = [{**AI_TOKENS, 'source': key}] if len(comps) < MAX_COMPONENTS else []
    return {**spec, 'components': [*rest[:k], *total, *rest[k:top], *ai, *rest[top:]]}


AI_UP_KEY = 'glance_ai_tiles_up'


def migrate_ai_tiles_up(store) -> int:
    """ai_tiles_up on every saved dashboard, once: an owner who moves the tiles back down later is not overridden."""
    if store.get_setting(AI_UP_KEY): return 0
    n = 0
    for src in store.list_sources(active_only=False):
        cfg = cfg_of(src)
        if src.get('Channel') == 'report' and (new := ai_tiles_up(cfg)) != cfg:
            store.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps(new)}, 'migrate'); n += 1
    store.set_setting(AI_UP_KEY, '1', 'migrate')
    return n


def migrate_priorities(store) -> int:
    """Every saved dashboard, once each: how many changed (0 when none needed it - a second run is a no-op)."""
    n = 0
    for src in store.list_sources(active_only=False):
        cfg = cfg_of(src)
        if (new := three_priorities(cfg)) != cfg: store.save_source({'SourceId': src['SourceId'], 'ConfigJson': json.dumps(new)}, 'migrate'); n += 1
    return n


# ── the spec ────────────────────────────────────────────────────────────────────────────────
def _key(s, i): return str(s.get('key') or f's{i}').strip()


# A DASHBOARD SOURCE'S `key` IS ITS OWN NAME (what a component reads), and one executor reads a `key` of its own: an S3 source's object
# path (aws.run_s3_object). On a dashboard that path is `object_key`, handed to the executor as its `key` at run time; a report's S3
# source is untouched. A dashboard saved before this held the path in `key` itself - a key shaped like a path (a / or a .) still
# reads as one, and the names this app gives a source (s1, tasks, mail) never are.
OWN_KEYS = {'s3_object': 'object_key'}


def run_cfg(s: dict) -> dict:
    """The config a dashboard source's executor is handed: its own name dropped, a field it renamed (OWN_KEYS) put back as `key`."""
    out = {k: v for k, v in s.items() if k != 'key'}
    own = OWN_KEYS.get(s.get('type'))
    if own:
        path = out.pop(own, None) or (s.get('key') if '/' in str(s.get('key') or '') or '.' in str(s.get('key') or '') else None)
        if path: out['key'] = path
    return out


def validate(spec: dict, store=None) -> tuple:
    """(ok, why). The shape only - every source a known, connected type with what it needs (compose.validate_source),
    every component a preset bound to a source the spec has. Whether the COLUMNS exist is the data's to say (problems)."""
    if not isinstance(spec, dict): return False, 'the dashboard is not a spec'
    if not str(spec.get('title') or '').strip(): return False, 'the dashboard has no title'
    srcs, comps = spec.get('sources'), spec.get('components')
    if not isinstance(srcs, list) or not srcs: return False, 'the dashboard reads no source'
    if len(srcs) > MAX_SOURCES: return False, f'at most {MAX_SOURCES} sources'
    keys = [_key(s, i) for i, s in enumerate(srcs, 1) if isinstance(s, dict)]
    if len(keys) != len(srcs) or len(set(keys)) != len(keys): return False, 'every source needs its own key'
    if store is not None:
        from .compose import validate_source
        for s in srcs:
            ok, why = validate_source(store, run_cfg(s))
            if not ok: return False, why
    if not isinstance(comps, list) or not comps: return False, 'the dashboard shows nothing - it has no components'
    if len(comps) > MAX_COMPONENTS: return False, f'at most {MAX_COMPONENTS} components - one screen'
    for n, c in enumerate(comps, 1):
        if not isinstance(c, dict): return False, f'component {n} is not a component'
        name = c.get('title') or f'component {n}'
        if c.get('kind') not in KINDS: return False, f"{name}: {c.get('kind')!r} is not a preset ({', '.join(KINDS)})"
        if c.get('source') not in keys: return False, f"{name}: it reads {c.get('source')!r}, which is not one of the sources"
        miss = [k for k in KINDS[c['kind']][0] if c.get(k) in (None, '')]
        if miss: return False, f"{name}: a {c['kind']} needs {' and '.join(miss)}"
        agg = c.get('agg') or 'count'
        if agg not in AGGS: return False, f"{name}: {agg!r} is not one of {', '.join(AGGS)}"
        if agg != 'count' and not c.get('y'): return False, f'{name}: a {agg} needs the column it adds up (y)'
        if c.get('where') is not None and not isinstance(c['where'], dict): return False, f'{name}: "where" is column: value pairs'
        r = c.get('range')
        if r is not None and r is not False and (isinstance(r, bool) or r not in RANGES[:-1]):
            return False, f'{name}: its own "range" is false (what is true now) or one of {", ".join(map(str, RANGES[:-1]))} days'
        if c.get('order') is not None and not isinstance(c['order'], list): return False, f'{name}: "order" is a list of its x values'
    rng = (spec.get('filters') or {}).get('range')
    if rng is not None and int(rng) not in RANGES: return False, f'the date range is one of {", ".join(map(str, RANGES))} days'
    return True, ''


def problems(spec: dict, data: dict) -> list:
    """What would draw empty: a component bound to a column its source never returned, or a source that failed."""
    out, srcs = [], (data or {}).get('sources') or {}
    for k, d in srcs.items():
        if d.get('failed'): out.append(f"{d.get('label') or k}: {d.get('error') or 'could not be read'}")
    for c in spec.get('components') or []:
        d = srcs.get(c.get('source')) or {}
        if d.get('failed') or not d.get('rows'): continue
        cols = set(d.get('columns') or [])
        want = [c[k] for k in COLUMN_KEYS if isinstance(c.get(k), str) and c.get(k)] + list(c.get('columns') or []) + list((c.get('where') or {}).keys())
        if (date := (next((s for s in spec.get('sources') or [] if s.get('key') == c.get('source')), {}) or {}).get('date')): want.append(date)
        miss = sorted({w for w in want if w not in cols})
        if miss: out.append(f"{c.get('title') or c['kind']}: no column {', '.join(miss)} in {d.get('label') or c['source']}")
    return out


def rows_of(body: str) -> list:
    """The rows an executor handed back as JSON lines (reports.rows_out), or one JSON list. Prose is no rows."""
    t = str(body or '').strip()
    if t.startswith('['):
        try: v = json.loads(t); return [r for r in v if isinstance(r, dict)] if isinstance(v, list) else []
        except ValueError: pass
    out = []
    for line in t.splitlines():
        line = line.strip()
        if not line.startswith('{'): continue
        try: r = json.loads(line)
        except ValueError: continue          # the last line of a cut body
        if isinstance(r, dict): out.append(r)
    return out[:ROWS]


def collect(store, spec: dict) -> dict:
    """Run every source, once, as a report would - and keep the rows. No AI. One failing source is said in place."""
    from . import reports
    srcs = spec.get('sources') or []
    subs = [{**run_cfg(s), 'max_rows': s.get('max_rows') or ROWS} for s in srcs]
    with reports.wide_rows():
        parts = reports.run_source_parts(store, subs)
    out = {}
    for s, (_k, label, head, body) in zip(srcs, parts):
        key, failed = s.get('key'), head == 'FAILED'
        rows = [] if failed else rows_of(body)
        cols = list(dict.fromkeys(c for r in rows[:200] for c in r))
        out[key] = {'label': s.get('label') or label, 'head': head, 'rows': rows, 'columns': cols, 'failed': failed,
                    **({'error': body[len('error: '):] if body.startswith('error: ') else body} if failed else {})}
    return {'at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'), 'sources': out}


# ── the one number a run says (its rail row's headline): the stat tiles, read the way the page reads them ──
def _num(v):
    try: return float(v)
    except (TypeError, ValueError): return None


def in_range(rows, date_col, days, now=None):
    if not date_col or not days: return rows
    cut = ((now or datetime.now()) - timedelta(days=int(days) - 1)).strftime('%Y-%m-%d')     # the last 7 days: today and six before
    return [r for r in rows if str(r.get(date_col) or '')[:10] >= cut]


def where(rows, w): return [r for r in rows if all(str(r.get(k)) == str(v) for k, v in (w or {}).items())]


def aggregate(rows, agg='count', y=None):
    if (agg or 'count') == 'count': return len(rows)
    vals = [v for v in (_num(r.get(y)) for r in rows) if v is not None]
    if not vals: return None
    if agg == 'median': s, n = sorted(vals), len(vals); return s[n // 2] if n % 2 else (s[n // 2 - 1] + s[n // 2]) / 2
    return {'sum': sum(vals), 'avg': sum(vals) / len(vals), 'min': min(vals), 'max': max(vals)}[agg]


# a component's own window: "range": 7 is always the last week (a weekly target), whatever range the page is on
def span(c, days): return c['range'] if isinstance(c.get('range'), int) and not isinstance(c.get('range'), bool) else days


def fmt(v) -> str:
    if v is None: return '-'
    a = abs(v)
    if a >= 1e6: return f'{v / 1e6:.1f}M'
    if a >= 1e4: return f'{v / 1e3:.1f}K'
    return f'{v:,.0f}' if float(v).is_integer() else f'{v:,.1f}'


def numbers(spec: dict, data: dict) -> list:
    """[(tile, value)] for every stat tile, over the dashboard's default range - the value as counted, None where nothing was."""
    days, out = int((spec.get('filters') or {}).get('range') or 0), []
    srcs = {s.get('key'): s for s in spec.get('sources') or []}
    for c in spec.get('components') or []:
        if c.get('kind') != 'stat': continue
        rows = ((data.get('sources') or {}).get(c.get('source')) or {}).get('rows') or []
        date = None if c.get('range') is False else (srcs.get(c['source']) or {}).get('date')     # "range": false counts what is true now
        out.append((c, aggregate(where(in_range(rows, date, span(c, days)), c.get('where')), c.get('agg'), c.get('y'))))
    return out


def headline(spec: dict, data: dict, nums: list = None) -> list:
    """[(title, value)] for every stat tile, as the tile says it."""
    return [(c.get('title') or 'value', fmt(v) + (f" {c['unit']}" if c.get('unit') and v is not None else ''))
            for c, v in (numbers(spec, data) if nums is None else nums)]


# ── keeping the last result, and a run ─────────────────────────────────────────────────────────
def last(store, sid) -> dict | None:
    r = store.get_dashboard_result(sid)
    try: return json.loads(r['DataJson']) if r else None
    except ValueError: return None


def file_run(store, src: dict, cfg: dict, trigger: str = 'schedule') -> dict:
    """One run: re-read the sources, keep the rows, and put ONE row under Reports saying it is fresh (the previous run's row
    is retired, as a report's is). Nothing is triaged, summarised, sent or alerted - a dashboard is looked at."""
    from .reports import expire_previous_runs, built_from
    title = cfg.get('title') or src.get('Address') or 'Dashboard'
    data = collect(store, cfg)
    srcs = data['sources'].values()
    if srcs and all(d['failed'] for d in srcs):
        why = '; '.join(f"{d['label']}: {d.get('error') or 'could not be read'}" for d in srcs)
        return {'message_id': None, 'subject': f'{title} — FAILED', 'files': 0, 'said': 0, 'failed': True,
                'error': f'Skipped: no source could be read - {why}'[:600], 'summary': why[:2000]}
    store.save_dashboard_result(src['SourceId'], json.dumps(data, default=str))
    # NOTHING TO SHOW is not news (reports.NothingToReport): a fresh install's own tables are empty, and a row on the rail saying so
    # stood where the empty rail tells the owner what to connect. The page still draws its empty tiles; the rail gets nothing.
    # ...nor is a run whose every number is nothing: a fresh install's first sync had only the AI checks' rows, and "Came in 0 · New
    # tasks 0 · Open now 0" stood on the rail beside the tasks opened next, until the next morning's run (the bug hunt, 2026-11-12)
    nums = numbers(cfg, data)
    if srcs and (not any(d['rows'] for d in srcs) or (nums and not any(v for _, v in nums))):
        return {'message_id': None, 'subject': f'{title} — nothing to show yet', 'files': 0, 'said': 0, 'failed': False,
                'summary': 'Every source was read and none has a number yet'}
    tiles = headline(cfg, data, nums)
    bad = [d for d in srcs if d['failed']]
    note = ('Read without ' + '; '.join(f"{d['label']}: {d.get('error') or 'could not be read'}" for d in bad)) if bad else ''
    head = ' · '.join(f'{t} {v}' for t, v in tiles[:3]) or f"{sum(len(d['rows']) for d in srcs)} rows"
    text = '\n'.join([*([note] if note else []), *(f'{t}: {v}' for t, v in tiles)]) or head
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mid = store.add_message({'TaskId': None, 'ExternalId': f"report:{src['SourceId']}:{stamp}:dashboard", 'ConversationId': f"report:{src['SourceId']}",
                             'Channel': 'report', 'SourceName': title, 'Subject': f'{title} — {head}', 'FromName': title, 'SentAt': stamp,
                             'BodyText': text, 'SourceLink': f"#report={src['SourceId']}", 'Status': 'feed',
                             'MailMetaJson': json.dumps({'built_from': built_from(cfg)})})
    store.add_route(mid, None, 'feed', None, "a dashboard's run - shown, never triaged", [], 'report')   # its reason, as every arrival's (ingest.day_count)
    expire_previous_runs(store, src, cfg, mid)
    store.audit('message', mid, 'report', 'report', 'agent', title)
    logger.info(f'dashboard {title}: {head} ({trigger})')
    return {'message_id': mid, 'subject': f'{title} — {head}', 'files': 0, 'said': 0, 'summary': text, 'failed': False,
            **({'note': note} if note else {})}
