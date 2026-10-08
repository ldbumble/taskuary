"""What happened while you were away, and what was learned this week - two lines under the opening screen's tiles.

The tiles say what WAITS on you; nothing said what already happened without you - the mail that was read and filed, the
reports that ran, the agents that finished - so a quiet morning looked like nothing had been done (the row-bot comparison,
2026-10-07: their Overview's "Since yesterday evening" and "Learned this week"). Counted straight from the store: no model,
so the opening screen never waits on one.
"""
from datetime import datetime, timedelta

EVENING = 18          # "last night" starts at six the evening before


def _start(now: datetime) -> datetime:
    return (now - timedelta(days=1)).replace(hour=EVENING, minute=0, second=0, microsecond=0)


def _n(store, q, p): return int((store._one(q, p) or {}).get('n') or 0)


def _plural(n, one, many=None): return f"{n} {one if n == 1 else (many or one + 's')}"


def overnight(store, now: datetime = None) -> dict:
    """{line, mail, reports, closed, sessions} since six last evening. line is '' when nothing happened."""
    since = _start(now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
    mail = _n(store, "SELECT COUNT(*) n FROM message WHERE CreatedAt>=? AND IFNULL(Direction,'in')!='out' "
                     "AND IFNULL(Channel,'') NOT IN ('report','assistant')", (since,))
    reports = _n(store, "SELECT COUNT(*) n FROM message WHERE CreatedAt>=? AND Channel='report'", (since,))
    closed = _n(store, "SELECT COUNT(*) n FROM task WHERE ClosedAt>=? AND Status='done'", (since,))
    sessions = _n(store, 'SELECT COUNT(*) n FROM transcript WHERE CreatedAt>=?', (since,))
    parts = [p for n, p in ((mail, _plural(mail, 'message') + ' read'), (reports, _plural(reports, 'report') + ' ran'),
                            (sessions, _plural(sessions, 'agent session') + ' finished'), (closed, _plural(closed, 'task') + ' closed')) if n]
    return {'line': ('Since last night: ' + ', '.join(parts) + '.') if parts else '',
            'mail': mail, 'reports': reports, 'closed': closed, 'sessions': sessions}


def learned(store, now: datetime = None) -> dict:
    """{line, n, latest} - what LEARNED.md took in over the last seven days: new guesses and new rules."""
    since = ((now or datetime.now()) - timedelta(days=7)).strftime('%Y-%m-%d')
    rows = store._rows("SELECT Text, Action FROM learned_history WHERE At>=? AND Action IN ('born','promoted') ORDER BY Id DESC", (since,))
    n = len(rows)
    return {'line': f"Learned this week: {_plural(n, 'new thing')} about how you work." if n else '', 'n': n,
            'latest': rows[0]['Text'] if rows else ''}


CARDS = 3


def cards(store, now: datetime = None) -> list:
    """What CHANGED while you were away, as up to three cards above what waits (the owner picked "A +", 2026-10-08): agents that
    finished, then the reports that ran with something in them, then what was learned. Each names the row it opens."""
    from .store import task_ref
    since = _start(now or datetime.now()).strftime('%Y-%m-%d %H:%M:%S')
    out = []
    for r in store._rows("SELECT EntityId, MAX(CreatedAt) at FROM audit WHERE EntityType='task' AND Action='self_close' AND CreatedAt>=? "
                         "GROUP BY EntityId ORDER BY at DESC LIMIT 2", (since,)):
        t = store.get_task(int(r['EntityId'])) or {}
        if t: out.append({'kind': 'agent', 'label': f"Agent finished · {task_ref(t['TaskId'])}", 'text': t.get('Title') or '',
                          'key': f"task:{t['TaskId']}", 'at': r['at']})
    # a report that SAID something - one with a row to open; the digest is not a card, it is the line under them
    for r in store._rows("SELECT SourceId, MAX(RunId) rid FROM report_run WHERE At>=? AND MessageId IS NOT NULL AND IFNULL(Type,'')!='digest' "
                         "GROUP BY SourceId ORDER BY rid DESC", (since,)):
        if len(out) >= CARDS: break
        run = store.get_report_run(int(r['rid'])) or {}
        title, subj = run.get('title') or 'Report', str(run.get('subject') or '')
        said = subj.split(' — ', 1)[1] if ' — ' in subj else subj.split(' - ', 1)[1] if subj.startswith(f'{title} - ') else subj
        out.append({'kind': 'report', 'label': f"{'Report failed' if run.get('failed') else 'Report ran'} · {str(run.get('at') or '')[11:16]}",
                    'text': f"{title}: {said}" if said and said != title else title, 'key': f"report:{run['messageId']}", 'at': run.get('at')})
    got = learned(store, now)
    if got['n'] and len(out) < CARDS:
        out.append({'kind': 'learned', 'label': 'Learned this week', 'text': f"{_plural(got['n'], 'new thing')}" + (f" · {got['latest']}" if got['latest'] else ''),
                    'link': 'settings=docs&doc=learned&view=changes'})
    return out[:CARDS]


def digest(store) -> dict:
    """The newest Morning digest, whole, and when it was written - shown folded on the opening screen, opened in place; `source_id`
    is what "Write a fresh one" reruns (reports.run_one through /api/reports/{sid}/rerun)."""
    import json
    src = next((r for r in store._rows("SELECT SourceId, ConfigJson FROM source WHERE Channel='report' AND Active=1")
                if (lambda c: c.get('type') == 'digest' or 'digest' in {x.get('type') for x in c.get('sources') or []})(
                    (lambda t: json.loads(t) if t else {})(r.get('ConfigJson') or ''))), None)
    if not src: return {}
    run = next((r for r in store.report_runs(src['SourceId'], 5) if not r.get('failed') and r.get('messageId')), None)
    if not run: return {'source_id': src['SourceId'], 'at': None, 'text': ''}
    m = store.get_message(run['messageId']) or {}
    return {'source_id': src['SourceId'], 'at': run.get('at'), 'text': str(m.get('BodyText') or '').strip()}


def summary(store, now: datetime = None) -> dict:
    return {'overnight': overnight(store, now), 'learned': learned(store, now), 'cards': cards(store, now), 'digest': digest(store)}
