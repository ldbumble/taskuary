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
import json
from datetime import datetime, timedelta
from loguru import logger

from .processing_order import known, level
from .store import task_ref

# kind -> (bindings it cannot draw without, the width it takes on a four-column grid)
KINDS = {'stat': ((), 1), 'progress': (('target',), 1), 'line': (('x',), 2), 'area': (('x',), 2), 'bar': (('x',), 2),
         'stacked': (('x', 'series'), 2), 'table': ((), 4), 'list': (('label',), 2)}
AGGS = ('count', 'sum', 'avg', 'median', 'min', 'max')
RANGES = (7, 30, 90, 0)            # days back; 0 is everything the sources returned
MAX_SOURCES, MAX_COMPONENTS, ROWS = 6, 12, 2000
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


DATASETS = {'tasks': (_tasks, 'task_id, ref, title, kind, status, state (open|closed), priority (regular|important|urgent), arrived (date), closed (date), '
                             'waiting (how long since it arrived, in words)'),
            'mail': (_mail, 'message_id, task_id, day (date), channel, sender, became_task (yes|no)'),
            'flow': (_flow, 'message_id, task_id, day (date), channel, stage (Came in|Triaged|On a task|Task closed - one row per stage reached)'),
            'agent_runs': (_agent_runs, 'run_id, task_id, ref, day (date), agent, status, outcome (finished|failed|stopped|waiting on you|working), minutes'),
            'replies': (_replies, 'task_id, day (date the reply was decided), channel, status, hours (ask to answer)')}


# ── the built-in dashboard: what the End of day checkup is to reports. Every install gets it (store.SEEDED_REPORTS), and New
# dashboard offers it again in one press. It reads ONLY this app's own tables, so it draws for anybody, with nothing connected.
_own = lambda key, label, dataset, date: {'key': key, 'label': label, 'type': 'taskuary_data', 'dataset': dataset, 'days': 90, 'date': date}
GLANCE = {'type': 'dashboard', 'title': 'Taskuary at a glance', 'daily_at': '07:00',
          'sources': [_own('mail', 'What came in', 'mail', 'day'), _own('flow', 'How far it got', 'flow', 'day'),
                      _own('tasks', 'Tasks', 'tasks', 'arrived'), _own('closed', 'Tasks closed', 'tasks', 'closed'),
                      _own('agents', 'Agent sessions', 'agent_runs', 'day'), _own('replies', 'Replies', 'replies', 'day')],
          'filters': {'range': 7, 'segment': 'channel'},
          'components': [
              # the numbers first: what came in, what it became, what is still open, and how fast the owner answers
              {'kind': 'stat', 'title': 'Came in', 'source': 'mail', 'agg': 'count'},
              {'kind': 'stat', 'title': 'New tasks', 'source': 'tasks', 'agg': 'count'},
              {'kind': 'stat', 'title': 'Open now', 'source': 'tasks', 'agg': 'count', 'where': {'state': 'open'}, 'range': False, 'good': 'down'},
              {'kind': 'stat', 'title': 'Median reply time', 'source': 'replies', 'agg': 'median', 'y': 'hours', 'unit': 'h', 'good': 'down'},
              # ...the week's close against its target and an agent's time, beside the funnel (four bars: a tile's height, so the row is even)
              {'kind': 'progress', 'title': 'Closed this week', 'source': 'closed', 'agg': 'count', 'where': {'state': 'closed'}, 'range': 7, 'target': 15},
              {'kind': 'stat', 'title': 'Agent time per session', 'source': 'agents', 'agg': 'median', 'y': 'minutes', 'unit': 'min', 'good': 'none'},
              {'kind': 'bar', 'title': 'How far it got', 'source': 'flow', 'x': 'stage', 'order': list(STAGES), 'share': True, 'w': 2},
              # ...then the days: what came in, and what the agents did with theirs
              {'kind': 'stacked', 'title': 'What came in, by channel', 'source': 'mail', 'x': 'day', 'series': 'channel', 'w': 2},
              {'kind': 'stacked', 'title': 'Agent sessions, and how they ended', 'source': 'agents', 'x': 'day', 'series': 'outcome', 'w': 2},
              # ...the rankings
              {'kind': 'bar', 'title': 'Open work by kind', 'source': 'tasks', 'x': 'kind', 'where': {'state': 'open'}, 'range': False, 'w': 2},
              {'kind': 'bar', 'title': 'Who writes most', 'source': 'mail', 'x': 'sender', 'limit': 8, 'w': 2},
              # ...and the detail: the asks that have waited longest on the owner, each opening its task
              {'kind': 'list', 'title': 'Waiting longest on you', 'source': 'tasks', 'label': 'title', 'meta': 'waiting',
               'where': {'status': 'open'}, 'range': False, 'sort': 'arrived', 'limit': 6, 'w': 4}]}
TEMPLATES = {'glance': {'title': GLANCE['title'], 'config': GLANCE,
                        'explain': 'What came in and from where, how far it got, what is still open, how fast you answer and what your '
                                   'agents did - from this app\'s own records, so there is nothing to connect.'}}


def templates() -> list: return [{'key': k, 'title': t['title'], 'explain': t['explain']} for k, t in TEMPLATES.items()]
def template(key) -> dict | None: return json.loads(json.dumps(TEMPLATES[key])) if key in TEMPLATES else None      # a copy: never the shared spec


def run_taskuary_data(cfg):
    """{"dataset": "tasks|mail|flow|agent_runs|replies", "days": 90} - Taskuary's own tables as plain rows, no AI: tasks (task_id,
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


def headline(spec: dict, data: dict) -> list:
    """[(title, value)] for every stat tile, over the dashboard's default range."""
    days, out = int((spec.get('filters') or {}).get('range') or 0), []
    srcs = {s.get('key'): s for s in spec.get('sources') or []}
    for c in spec.get('components') or []:
        if c.get('kind') != 'stat': continue
        rows = ((data.get('sources') or {}).get(c.get('source')) or {}).get('rows') or []
        date = None if c.get('range') is False else (srcs.get(c['source']) or {}).get('date')     # "range": false counts what is true now
        rows = where(in_range(rows, date, span(c, days)), c.get('where'))
        v = aggregate(rows, c.get('agg'), c.get('y'))
        out.append((c.get('title') or 'value', fmt(v) + (f" {c['unit']}" if c.get('unit') and v is not None else '')))
    return out


# ── keeping the last result, and a run ─────────────────────────────────────────────────────────
def last(store, sid) -> dict | None:
    r = store.get_dashboard_result(sid)
    try: return json.loads(r['DataJson']) if r else None
    except ValueError: return None


def file_run(store, src: dict, cfg: dict, trigger: str = 'schedule') -> dict:
    """One run: re-read the sources, keep the rows, and put ONE row under Reports saying it is fresh (the previous run's row
    is retired, as a report's is). Nothing is triaged, summarised, sent or alerted - a dashboard is looked at."""
    from .reports import expire_previous_runs
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
    if srcs and not any(d['rows'] for d in srcs):
        return {'message_id': None, 'subject': f'{title} — nothing to show yet', 'files': 0, 'said': 0, 'failed': False,
                'summary': 'Every source was read and none has rows yet'}
    tiles = headline(cfg, data)
    bad = [d for d in srcs if d['failed']]
    note = ('Read without ' + '; '.join(f"{d['label']}: {d.get('error') or 'could not be read'}" for d in bad)) if bad else ''
    head = ' · '.join(f'{t} {v}' for t, v in tiles[:3]) or f"{sum(len(d['rows']) for d in srcs)} rows"
    text = '\n'.join([*([note] if note else []), *(f'{t}: {v}' for t, v in tiles)]) or head
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    mid = store.add_message({'TaskId': None, 'ExternalId': f"report:{src['SourceId']}:{stamp}:dashboard", 'ConversationId': f"report:{src['SourceId']}",
                             'Channel': 'report', 'SourceName': title, 'Subject': f'{title} — {head}', 'FromName': title, 'SentAt': stamp,
                             'BodyText': text, 'SourceLink': f"#report={src['SourceId']}", 'Status': 'feed'})
    expire_previous_runs(store, src, cfg, mid)
    store.audit('message', mid, 'report', 'report', 'agent', title)
    logger.info(f'dashboard {title}: {head} ({trigger})')
    return {'message_id': mid, 'subject': f'{title} — {head}', 'files': 0, 'said': 0, 'summary': text, 'failed': False,
            **({'note': note} if note else {})}
