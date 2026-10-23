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

from .store import task_ref

# kind -> (bindings it cannot draw without, the width it takes on a four-column grid)
KINDS = {'stat': ((), 1), 'progress': (('target',), 1), 'line': (('x',), 2), 'area': (('x',), 2), 'bar': (('x',), 2),
         'stacked': (('x', 'series'), 2), 'table': ((), 4), 'list': (('label',), 2)}
AGGS = ('count', 'sum', 'avg', 'min', 'max')
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
    rows = store._rows("""SELECT t.TaskId, t.Title, t.Kind, t.Status, t.Priority, t.CreatedAt, t.ClosedAt,
        (SELECT MIN(m.SentAt) FROM message m WHERE m.TaskId=t.TaskId) FirstAt
        FROM task t WHERE t.ParentId IS NULL AND (t.CreatedAt>=? OR t.Status NOT IN ('done','dropped'))
        ORDER BY t.TaskId DESC LIMIT ?""", (_since(days), ROWS))
    return [{'task_id': r['TaskId'], 'ref': task_ref(r['TaskId']), 'title': r['Title'] or '', 'kind': r['Kind'] or 'general',
             'status': r['Status'] or 'open', 'state': 'closed' if r['Status'] in ('done', 'dropped') else 'open',
             'priority': r['Priority'] or 'normal', 'arrived': str(r['FirstAt'] or r['CreatedAt'] or '')[:10],
             'closed': str(r['ClosedAt'] or '')[:10]} for r in rows]


def _mail(store, days):
    """One row per message that came IN (not the reports' own rows): its day, channel and sender."""
    rows = store._rows("""SELECT MessageId, TaskId, Channel, SentAt, FromName, SourceName FROM message
        WHERE IFNULL(Direction,'in')='in' AND Channel<>'report' AND Status<>'context' AND SentAt>=? ORDER BY SentAt DESC LIMIT ?""",
                       (_since(days), ROWS))
    return [{'message_id': r['MessageId'], 'task_id': r['TaskId'], 'day': str(r['SentAt'] or '')[:10], 'channel': r['Channel'] or 'email',
             'sender': r['FromName'] or r['SourceName'] or '', 'became_task': 'yes' if r['TaskId'] else 'no'} for r in rows]


def _agent_runs(store, days):
    """One row per agent run: the day it started, the agent, how it ended and how long it took."""
    rows = store._rows("""SELECT RunId, TaskId, AgentName, Status, StartedAt, FinishedAt,
        (julianday(FinishedAt)-julianday(StartedAt))*1440 Mins FROM run WHERE StartedAt>=? ORDER BY RunId DESC LIMIT ?""",
                       (_since(days), ROWS))
    return [{'run_id': r['RunId'], 'task_id': r['TaskId'], 'ref': task_ref(r['TaskId']) if r['TaskId'] else '', 'day': str(r['StartedAt'] or '')[:10],
             'agent': r['AgentName'] or 'agent', 'status': r['Status'] or 'running',
             'minutes': round(r['Mins'], 1) if r['Mins'] is not None else None} for r in rows]


def _replies(store, days):
    """One row per reply the owner decided: how many hours from the ask arriving to the answer."""
    rows = store._rows("""SELECT r.ReviewId, r.TaskId, r.Status, r.DecidedAt, m.SentAt, m.Channel,
        (julianday(r.DecidedAt)-julianday(m.SentAt))*24 Hrs FROM review r JOIN message m ON m.MessageId=r.MessageId
        WHERE r.DecidedAt IS NOT NULL AND r.DecidedAt>=? AND r.Kind NOT IN ('action','slot','escalation') ORDER BY r.ReviewId DESC LIMIT ?""",
                       (_since(days), ROWS))
    return [{'task_id': r['TaskId'], 'day': str(r['DecidedAt'] or '')[:10], 'channel': r['Channel'] or 'email', 'status': r['Status'],
             'hours': round(max(0.0, r['Hrs']), 1) if r['Hrs'] is not None else None} for r in rows]


DATASETS = {'tasks': (_tasks, 'task_id, ref, title, kind, status, state (open|closed), priority, arrived (date), closed (date)'),
            'mail': (_mail, 'message_id, task_id, day (date), channel, sender, became_task (yes|no)'),
            'agent_runs': (_agent_runs, 'run_id, task_id, ref, day (date), agent, status, minutes'),
            'replies': (_replies, 'task_id, day (date the reply was decided), channel, status, hours (ask to answer)')}


def run_taskuary_data(cfg):
    """{"dataset": "tasks|mail|agent_runs|replies", "days": 90} - Taskuary's own tables as plain rows, no AI: tasks (task_id,
    ref, title, kind, status, state, priority, arrived, closed), mail (day, channel, sender, became_task), agent_runs (day,
    agent, status, minutes), replies (day, channel, hours). The rows a dashboard draws from. `store` arrives via resolve_cfg."""
    from .reports import rows_out, row_limit
    name = str(cfg.get('dataset') or '').strip()
    if name not in DATASETS: raise ValueError(f"no Taskuary dataset called {name!r} - choose one of {', '.join(DATASETS)}")
    rows = DATASETS[name][0](cfg['store'], cfg.get('days') or 90)
    lim, mine = row_limit(cfg)
    return rows_out(rows, lim, unit=name.replace('_', ' '), mine=mine)


# ── the spec ────────────────────────────────────────────────────────────────────────────────
def _key(s, i): return str(s.get('key') or f's{i}').strip()


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
            ok, why = validate_source(store, s)
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
    subs = [{**s, 'max_rows': s.get('max_rows') or ROWS} for s in spec.get('sources') or []]
    with reports.wide_rows():
        parts = reports.run_source_parts(store, subs)
    out = {}
    for s, (_k, label, head, body) in zip(subs, parts):
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
    cut = ((now or datetime.now()) - timedelta(days=int(days))).strftime('%Y-%m-%d')
    return [r for r in rows if str(r.get(date_col) or '')[:10] >= cut]


def where(rows, w): return [r for r in rows if all(str(r.get(k)) == str(v) for k, v in (w or {}).items())]


def aggregate(rows, agg='count', y=None):
    if (agg or 'count') == 'count': return len(rows)
    vals = [v for v in (_num(r.get(y)) for r in rows) if v is not None]
    if not vals: return None
    return {'sum': sum(vals), 'avg': sum(vals) / len(vals), 'min': min(vals), 'max': max(vals)}[agg]


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
        rows = where(in_range(rows, (srcs.get(c['source']) or {}).get('date'), days), c.get('where'))
        out.append((c.get('title') or 'value', fmt(aggregate(rows, c.get('agg'), c.get('y')))))
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
