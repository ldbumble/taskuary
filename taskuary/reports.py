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


def run_sqlite(cfg):
    """{"db": "path.db", "query": "SELECT ..."} - the local-first database report."""
    cx = sqlite3.connect(cfg['db']); cx.row_factory = sqlite3.Row
    rows = [dict(r) for r in cx.execute(cfg['query']).fetchall()[:20]]
    cx.close()
    body = '\n'.join(json.dumps(r, default=str) for r in rows)
    return f'{len(rows)} rows', body[:4000]


def run_mssql(cfg):
    """{"server", "database", "auth", "username", "password", "driver", "query"} - see mssql.py.
    Configure it entirely from Settings -> Report connections in the UI."""
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
    return (f'{len(data)} items' if isinstance(data, list) else 'ok'), json.dumps(data, indent=1, default=str)[:4000]


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
    return f'{len(out.splitlines())} lines from {host}', out[:4000]


def run_mcp(cfg):
    """{"cmd", "args", "tool", "tool_args"} - call any MCP server's tool. See mcp.py."""
    from .mcp import run_report
    return run_report(cfg)


def _planned(name):
    def _fail(cfg): raise NotImplementedError(f"connector type '{name}' is on the roadmap - not implemented yet")
    return _fail


REGISTRY = {'sqlite': run_sqlite, 'mssql': run_mssql, 'winrm': run_winrm, 'mcp': run_mcp, 'rest': run_rest,
            'rss': run_rss, **{n: _planned(n) for n in PLANNED}}


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
    conn = {'mssql': mssql_connection, 'winrm': winrm_connection}.get(cfg.get('type'))
    if conn: return {**conn(store), **{k: v for k, v in cfg.items() if v not in (None, '')}}
    return cfg


AI_SYSTEM = ('You summarize scheduled report data for a busy operator. Follow the operator '
             'instruction exactly. Be concise and concrete: numbers, names, deltas. Plain text only.')


def render_report(store, cfg: dict, llm=None):
    """Run the executor, then (optionally) the AI pass: cfg['ai_prompt'] + a configured
    AI connector turn raw rows into the summary that lands on the timeline."""
    cfg = resolve_cfg(store, cfg)
    head, summary = REGISTRY[cfg.get('type', 'rest')](cfg)
    if cfg.get('ai_prompt') and llm:
        try:
            ai = llm(AI_SYSTEM, f"Instruction: {cfg['ai_prompt']}\n\nData ({head}):\n{summary[:6000]}")
            return head, f"{(ai or '').strip()}\n\n--- raw data ---\n{summary[:1500]}"
        except Exception as e:
            logger.warning(f'AI summary failed for report: {e}')
            return head, f'(AI summary failed: {str(e)[:200]})\n\n{summary}'
    if cfg.get('ai_prompt') and not llm:
        return head, f'(AI prompt set, but no active AI connector - raw data below)\n\n{summary}'
    return head, summary


def is_due(cfg: dict, last_polled) -> bool:
    now = datetime.now()
    if not last_polled: return True
    try: last = datetime.fromisoformat(str(last_polled)[:19].replace(' ', 'T'))
    except ValueError: return True
    if cfg.get('every_minutes'): return (now - last).total_seconds() >= float(cfg['every_minutes']) * 60
    if cfg.get('daily_at'):
        hh, mm = str(cfg['daily_at']).split(':')
        due = now.replace(hour=int(hh), minute=int(mm), second=0, microsecond=0)
        return now >= due and last < due
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
    mid = store.add_message({'TaskId': None, 'ExternalId': f'report:{src["SourceId"]}:{stamp}',
                             'ConversationId': f'report:{src["SourceId"]}', 'Channel': 'report',
                             'SourceName': title, 'Subject': subject, 'FromName': title,
                             'SentAt': stamp, 'BodyText': body, 'SourceLink': cfg.get('link'), 'Status': 'filed'})
    store.add_route(mid, None, 'file', None, 'scheduled report', [], 'report')
    store.audit('message', mid, 'report', 'report', 'agent', title)
    return {'message_id': mid, 'subject': subject}


def run_due_reports(store) -> int:
    from .llm import build_llm
    try: llm = build_llm(store)
    except Exception: llm = None
    n = 0
    for src in store.list_sources():
        if src['Channel'] != 'report': continue
        if is_due(json.loads(src.get('ConfigJson') or '{}'), src.get('LastPolledAt')):
            run_report_source(store, src, llm)
            store.touch_source(src['SourceId'])
            n += 1
    return n
