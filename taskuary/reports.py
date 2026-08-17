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


def _planned(name):
    def _fail(cfg): raise NotImplementedError(f"connector type '{name}' is on the roadmap - not implemented yet")
    return _fail


REGISTRY = {'sqlite': run_sqlite, 'mssql': run_mssql, 'rest': run_rest, 'rss': run_rss,
            **{n: _planned(n) for n in PLANNED}}


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


def run_report_source(store, src: dict) -> dict:
    """Execute one due report and file it on the timeline. Errors file visibly too."""
    cfg = json.loads(src.get('ConfigJson') or '{}')
    title = cfg.get('title') or src['Address']
    try:
        head, summary = REGISTRY[cfg.get('type', 'rest')](cfg)
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
    n = 0
    for src in store.list_sources():
        if src['Channel'] != 'report': continue
        if is_due(json.loads(src.get('ConfigJson') or '{}'), src.get('LastPolledAt')):
            run_report_source(store, src)
            store.touch_source(src['SourceId'])
            n += 1
    return n
