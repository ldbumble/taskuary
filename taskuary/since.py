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


def summary(store, now: datetime = None) -> dict:
    return {'overnight': overnight(store, now), 'learned': learned(store, now)}
