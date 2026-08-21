"""Scheduled report connections: pull from the systems you already have, drop informational
rows on the timeline (never tasks). A report source = a source row with Channel='report'
and ConfigJson {"type", "title", "every_minutes"/"daily_at", ...executor keys}.

REGISTRY: type -> executor(config) -> (headline, summary). Implemented: sqlite, rest, rss
(mssql with the [mssql] extra). Planned types fail loudly so a misconfig is visible on the
timeline instead of silently absent. Adding a type = one ~15-line function + a REGISTRY
entry - PRs welcome.
"""
import json, re, sqlite3
from datetime import datetime
from loguru import logger

PLANNED = ['postgres', 'mysql', 'snowflake', 'sharepoint_list', 'google_sheets', 's3_object',
           'graphql', 'smb_file', 'prometheus', 'jira']

MAX_ROWS, BODY_CHARS, AI_CHARS = 200, 20000, 12000     # per report; override with cfg['max_rows']
SUMMARY_TOKENS = 1500     # a report summary is prose, not a triage verdict - give it room


def row_limit(cfg):
    """(limit, is it YOURS). The default is a safety net, not a number anybody chose - and
    the headline has to say which one it was, or "capped at 200" points the owner at a
    setting they never made and cannot find."""
    n = cfg.get('max_rows')
    return (max(1, int(n)), True) if n else (MAX_ROWS, False)


def rows_out(rows, limit, unit='rows', mine=True):
    """(headline, body) from executor rows, SAYING SO when the result was cut. A silent cap
    made the AI describe 20 rows of a TOP 500 query as 'all of them' - fetch one extra row
    and the headline can tell the truth instead."""
    more = len(rows) > limit
    rows = rows[:limit]
    why = (f'capped at {limit}' if mine else f'capped at the default {limit}') + ' — set "max rows" on this source to see more'
    head = f'{len(rows)} rows' + (f' ({why})' if more else '')
    return head.replace('rows', unit, 1), '\n'.join(json.dumps(r, default=str) for r in rows)[:BODY_CHARS]


def run_sqlite(cfg):
    """{"db": "path.db", "query": "SELECT ...", "max_rows": 200} - the local-first database report."""
    cx = sqlite3.connect(cfg['db']); cx.row_factory = sqlite3.Row
    lim, mine = row_limit(cfg)
    rows = [dict(r) for r in cx.execute(cfg['query']).fetchmany(lim + 1)]
    cx.close()
    return rows_out(rows, lim, mine=mine)


def run_mssql(cfg):
    """{"server", "database", "auth", "username", "password", "driver", "query", "max_rows"} -
    see mssql.py. Configure the connection entirely from the Connectors tab."""
    from .mssql import run_report
    return run_report(cfg)


def run_rest(cfg):
    """{"url", "headers", "path": "a.b"} - GET a JSON endpoint, dot-path into it."""
    import requests
    r = requests.get(cfg['url'], headers=cfg.get('headers') or {}, timeout=30)
    r.raise_for_status()
    data = r.json()
    for k in (cfg.get('path') or '').split('.'):
        if k: data = data[int(k)] if isinstance(data, list) else data.get(k)
    return (f'{len(data)} items' if isinstance(data, list) else 'ok'), json.dumps(data, indent=1, default=str)[:BODY_CHARS]


def run_rss(cfg):
    """{"url"} - latest titles from an RSS/Atom feed."""
    import requests
    xml = requests.get(cfg['url'], timeout=30).text
    titles = re.findall(r'<title>(?:<!\[CDATA\[)?(.*?)(?:\]\]>)?</title>', xml)[1:11]
    return f'{len(titles)} new items', '\n'.join(f'- {t}' for t in titles)[:4000]


def run_winrm(cfg):
    """{"host", "script"} - run PowerShell ON a remote Windows box (WinRM / PS remoting,
    your current Windows credentials) and report its output. A box you can RDP into is
    usually domain-joined and WinRM-reachable already; if not, run Enable-PSRemoting on
    it once (elevated)."""
    import subprocess
    host, script = cfg['host'], cfg['script']
    p = subprocess.run(['powershell', '-NoProfile', '-NonInteractive', '-Command',
                        f'Invoke-Command -ComputerName {host} -ScriptBlock {{ {script} }}'],
                       capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=180)
    if p.returncode != 0: raise RuntimeError((p.stderr or p.stdout or 'remote run failed')[:500])
    out = (p.stdout or '').strip()
    return f'{len(out.splitlines())} lines from {host}', out[:BODY_CHARS]


def run_mcp(cfg):
    """{"cmd", "args", "tool", "tool_args"} - call any MCP server's tool. See mcp.py."""
    from .mcp import run_report
    return run_report(cfg)


def run_digest(cfg):
    """{"days": 3} - Taskuary's own activity as the data: open work, finished work, pending
    reviews, fresh verdicts, who wrote how often. The Morning digest ships as a report ON
    PURPOSE: the brief lands on the Timeline like any report, its prompt is edited on the
    Reports tab, deleting the source turns it off - and it demonstrates how reports work
    using data every install already has. `store` arrives via resolve_cfg, never persisted."""
    from .digest import gather
    days = int(cfg.get('days') or 3)
    return f'the last {days} days, distilled', gather(cfg['store'], days)


def _planned(name):
    def _fail(cfg): raise NotImplementedError(f"connector type '{name}' is on the roadmap - not implemented yet")
    return _fail


REGISTRY = {'sqlite': run_sqlite, 'mssql': run_mssql, 'winrm': run_winrm, 'mcp': run_mcp, 'rest': run_rest,
            'rss': run_rss, 'digest': run_digest, **{n: _planned(n) for n in PLANNED}}


def mssql_connection(store) -> dict:
    """The SQL Server CONNECTION lives on the mssql connector card (set up once, tested
    there); report configs carry only query/ai_prompt/schedule and inherit it here.
    Per-report overrides still win if present."""
    c = store.get_connector_by_type('mssql', with_secret=True)
    if not c: return {}
    cfg = json.loads(c.get('ConfigJson') or '{}')
    if c.get('Secret'): cfg.setdefault('password', c['Secret'])
    return {k: v for k, v in cfg.items() if v}


def winrm_connection(store) -> dict:
    """Same connection-card pattern as mssql: the host lives on the winrm connector."""
    c = store.get_connector_by_type('winrm')
    cfg = json.loads((c or {}).get('ConfigJson') or '{}')
    return {k: v for k, v in cfg.items() if v}


def resolve_cfg(store, cfg: dict) -> dict:
    if cfg.get('type') == 'digest': return {**cfg, 'store': store}   # its data IS the store
    conn = {'mssql': mssql_connection, 'winrm': winrm_connection}.get(cfg.get('type'))
    if conn: return {**conn(store), **{k: v for k, v in cfg.items() if v not in (None, '')}}
    return cfg


AI_SYSTEM = ('You summarize scheduled report data for a busy operator. Follow the operator '
             'instruction exactly. Be concise and concrete: numbers, names, deltas. Plain text only. '
             'The data may be a CAPPED slice of a larger result (the headline says so, and the rows '
             'may be cut mid-way) - never describe a capped or truncated slice as complete, and say '
             'plainly when something the instruction asks about is not present in the rows you got.')

# The rows come back as a spreadsheet and a chart, and the model that just read every row knows
# which column is the measure better than a heuristic hunting for "all numeric" does.
CHART_SYSTEM = ('\n\nThe rows are also turned into a bar chart for the reader. If ONE column is a '
                'measure worth plotting, end your answer with a single line:\n'
                'CHART: <value column> | <label column> | <short chart title>\n'
                'Use the exact column names from the data. Omit the line entirely when the rows are '
                'not worth plotting (no measure, one row, or every value the same) - a chart of '
                'nothing is worse than no chart.')


def run_sources(store, subs: list):
    """Several sources feeding ONE report: each runs on its own connection and query, the
    bodies are stacked under labeled headers, and the AI pass downstream sees all of them
    at once. The same connection can appear twice with different queries. One source
    failing is reported in place - it never takes the whole report down."""
    heads, bodies = [], []
    for i, sub in enumerate(subs, 1):
        t = sub.get('type', 'rest')
        label = (sub.get('label') or '').strip() or f'{t} #{i}'
        try:
            head, body = REGISTRY[t](resolve_cfg(store, dict(sub)))
        except Exception as e:
            head, body = 'FAILED', f'error: {str(e)[:400]}'
            logger.warning(f'report source "{label}" failed: {e}')
        heads.append(f'{label}: {head}')
        bodies.append(f'=== {label} ({head}) ===\n{body}')
    return ' · '.join(heads)[:400], '\n\n'.join(bodies)[:BODY_CHARS]


def report_llm(store, cfg: dict, default_llm):
    """The brain THIS report asked for (cfg['ai_brain'] in /api/brains values, optional
    cfg['ai_model'] override) - a heavier model for the weekly review, the cheap tier for
    pings. Falls back to the caller's default (the triage brain) when unset or broken."""
    if not (cfg.get('ai_brain') or cfg.get('ai_model')): return default_llm
    from .llm import build_llm
    try: return build_llm(store, cfg.get('ai_brain') or None, cfg.get('ai_model') or None) or default_llm
    except Exception as e:
        logger.warning(f'report brain unavailable, using the default: {e}')
        return default_llm


def render_report(store, cfg: dict, llm=None):
    """Run the executor(s), then (optionally) the AI pass: cfg['ai_prompt'] + a configured
    AI connector turn raw rows into the summary that lands on the timeline. The report may
    name its own brain and model (report_llm); `llm` is the default it falls back to."""
    llm = report_llm(store, cfg, llm)
    subs = [s for s in (cfg.get('sources') or []) if s.get('type')]
    if subs:
        head, summary = run_sources(store, subs)
    else:
        cfg = resolve_cfg(store, cfg)
        head, summary = REGISTRY[cfg.get('type', 'rest')](cfg)
    if cfg.get('ai_prompt') and llm:
        try:
            data = summary[:AI_CHARS]
            if len(summary) > AI_CHARS: data += '\n…(data truncated here - later rows were NOT shown to you)'
            charts = str(store.get_settings().get('report_images_enabled') or '1') == '1'
            ai = (llm(AI_SYSTEM + (CHART_SYSTEM if charts else ''),
                      f"Instruction: {cfg['ai_prompt']}\n\nData ({head}):\n{data}",
                      max_tokens=SUMMARY_TOKENS) or '').strip()
            # an empty answer used to file as a bare '--- raw data ---' wall, which reads
            # like the prompt was never run. Say what happened instead.
            if not ai:
                ai = ('(the model returned an empty summary - it may have spent its budget thinking. '
                      'Try a shorter prompt, or a non-reasoning model for report summaries.)')
            return head, f"{ai}\n\n--- raw data ---\n{summary[:4000]}"
        except Exception as e:
            logger.warning(f'AI summary failed for report: {e}')
            return head, f'(AI summary failed: {str(e)[:200]})\n\n{summary}'
    if cfg.get('ai_prompt') and not llm:
        return head, f'(AI prompt set, but no active AI connector - raw data below)\n\n{summary}'
    return head, summary


def is_due(cfg: dict, last_polled, startup: bool = False) -> bool:
    # on_startup is local-first scheduling: the app is a window you open, so "when I open
    # it" is a real schedule. Due exactly once per launch - never on the 10-minute auto-sync,
    # and a cron time it would have missed while closed is not its problem.
    if cfg.get('on_startup'): return startup
    now = datetime.now()
    if not last_polled: return True
    try: last = datetime.fromisoformat(str(last_polled)[:19].replace(' ', 'T'))
    except ValueError: return True
    if cfg.get('every_minutes'):
        try: return (now - last).total_seconds() >= float(cfg['every_minutes']) * 60
        except (TypeError, ValueError): pass               # 'every 30' typed as words: daily default
    if cfg.get('daily_at'):
        # tolerant of what people type: '8' and '8:30' both parse; garbage falls back to the
        # daily default instead of an unpack error killing the WHOLE poll thread (it did)
        try:
            hh, mm = (str(cfg['daily_at']).strip() + ':0').split(':')[:2]
            due = now.replace(hour=int(hh), minute=int(mm or 0), second=0, microsecond=0)
            return now >= due and last < due
        except (TypeError, ValueError):
            pass
    return (now - last).total_seconds() >= 24 * 3600


def run_report_source(store, src: dict, llm=None) -> dict:
    """Execute one due report (executor + optional AI pass) and file it on the timeline.
    Errors file visibly too."""
    cfg = json.loads(src.get('ConfigJson') or '{}')
    title = cfg.get('title') or src['Address']
    logger.debug(f'report run: {title} ({cfg.get("type", "rest")}, ai={bool(cfg.get("ai_prompt"))})')
    try:
        head, summary = render_report(store, cfg, llm)
        subject, body = f'{title} — {head}', summary
    except Exception as e:
        subject, body = f'{title} — FAILED', f'Report error: {str(e)[:500]}'
        logger.warning(f'report {src["Address"]} failed: {e}')
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    # the CHART: line is an instruction to Taskuary about what to draw, not prose for the reader:
    # artifacts reads it off `body`, and what gets filed is the summary without it
    from .artifacts import strip_directive
    mid = store.add_message({'TaskId': None, 'ExternalId': f'report:{src["SourceId"]}:{stamp}',
                             'ConversationId': f'report:{src["SourceId"]}', 'Channel': 'report',
                             'SourceName': title, 'Subject': subject, 'FromName': title,
                             'SentAt': stamp, 'BodyText': strip_directive(body),
                             'SourceLink': cfg.get('link'), 'Status': 'feed'})
    store.add_route(mid, None, 'feed', None, 'scheduled report - informational, never a task', [], 'report')
    # the rows are the report: hand back the spreadsheet to open and the chart to look at, not
    # just prose about them. Prose-only reports (an AI summary, a failure) produce neither.
    try:
        from .artifacts import attach_report_output
        made = attach_report_output(store, mid, title, body)
    except Exception as e:
        made = []
        logger.warning(f'report artifacts for {title} failed: {e}')
    store.audit('message', mid, 'report', 'report', 'agent', title)
    # the digest report is ALSO what keeps DIGEST.md alive: one run, two homes - the Timeline
    # row you read in the morning, and the doc the Docs tab shows
    if 'digest' in {cfg.get('type'), *(s.get('type') for s in cfg.get('sources') or [])}:
        from .digest import HEADER
        store.save_doc('digest', f'{HEADER}_refreshed {stamp[:16]}_\n\n{strip_directive(body)}\n', 'digest')
    return {'message_id': mid, 'subject': subject, 'files': len(made)}


def run_due_reports(store, startup: bool = False) -> int:
    from .llm import build_llm
    try: llm = build_llm(store)
    except Exception: llm = None
    n = 0
    for src in store.list_sources():
        if src['Channel'] != 'report': continue
        if is_due(json.loads(src.get('ConfigJson') or '{}'), src.get('LastPolledAt'), startup):
            run_report_source(store, src, llm)
            store.touch_source(src['SourceId'])
            n += 1
    return n
