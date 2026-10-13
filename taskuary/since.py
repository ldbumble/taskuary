"""What happened while you were away, and what was learned this week - two lines under the opening screen's tiles.

The tiles say what WAITS on you; nothing said what already happened without you - the mail that was read and filed, the
reports that ran, the agents that finished - so a quiet morning looked like nothing had been done (the row-bot comparison,
2026-10-07: their Overview's "Since yesterday evening" and "Learned this week"). Counted straight from the store: no model,
so the opening screen never waits on one.
"""
from datetime import datetime, timedelta


def _start(store, now: datetime) -> tuple:
    """(start, word) - welcome.away_window, the one "while you were away" every reader shares. A fixed six-last-evening window
    called a first install's backfill "since last night" and a week away "last night" too (B5, 2026-10-11)."""
    from .welcome import away_window
    return away_window(store, now)


def _clock(d: datetime) -> str: return f"{d.strftime('%a')} {d.hour % 12 or 12}:{d.minute:02d} {'AM' if d.hour < 12 else 'PM'}"


def _n(store, q, p): return int((store._one(q, p) or {}).get('n') or 0)


def _plural(n, one, many=None): return f"{n} {one if n == 1 else (many or one + 's')}"


def overnight(store, now: datetime = None) -> dict:
    """{line, heading, mail, reports, closed, sessions} since the owner was last here. line is '' when nothing happened. Mail is
    counted the way the greeting counts it (welcome.came_in: by when it was SENT, history and context left out), so the
    opening screen and the greeting say one number."""
    from .welcome import came_in
    now = now or datetime.now()
    start, word = _start(store, now)
    since = start.strftime('%Y-%m-%d %H:%M:%S')
    mail = came_in(store, start)
    reports = _n(store, "SELECT COUNT(*) n FROM message WHERE CreatedAt>=? AND Channel='report'", (since,))
    closed = _n(store, "SELECT COUNT(*) n FROM task WHERE ClosedAt>=? AND Status='done'", (since,))
    # FINISHED IS THE RUN SAYING SO (workerstate 'finished'), never a transcript row: one is filed the moment a hook names the CLI's
    # session id, and again when a close kills the pane - so sessions the window's X cut off read "finished" (B3, 2026-10-11).
    # The ones whose run ended any other way are said apart.
    sessions = _n(store, "SELECT COUNT(DISTINCT TaskId || ':' || Sid) n FROM worker_event WHERE Kind='finished' AND CreatedAt>=?", (since,))
    cut = _n(store, "SELECT COUNT(DISTINCT TaskId || ':' || Sid) n FROM worker_event w WHERE Kind IN ('disconnected','failed','stopped') "
                    "AND CreatedAt>=? AND NOT EXISTS (SELECT 1 FROM worker_event f WHERE f.TaskId=w.TaskId AND f.Sid=w.Sid AND f.Kind='finished')",
             (since,))
    parts = [p for n, p in ((mail, _plural(mail, 'message') + ' read'), (reports, _plural(reports, 'report') + ' ran'),
                            (sessions, _plural(sessions, 'agent session') + ' finished'), (cut, (f'{cut}' if sessions else _plural(cut, 'agent session')) + ' stopped before finishing'),
                            (closed, _plural(closed, 'task') + ' closed')) if n]
    return {'line': (f'{word}: ' + ', '.join(parts) + '.') if parts else '', 'heading': word if word.startswith('Since') else f'{word} · since {_clock(start)}',
            'mail': mail, 'reports': reports, 'closed': closed, 'sessions': sessions, 'stopped': cut}


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
    finished, then the reports that ran with something in them. Each names the row it opens."""
    from .store import task_ref
    since = _start(store, now or datetime.now())[0].strftime('%Y-%m-%d %H:%M:%S')
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
        # a subject that is only a heading ("Errors:") says nothing on a card - its first real line does
        if not said.strip() or said.rstrip().endswith(':'):
            said = next((l.strip().lstrip('-•* ').strip() for l in str(run.get('summary') or '').splitlines()
                         if l.strip() and not l.strip().endswith(':')), said)
        out.append({'kind': 'report', 'label': f"{'Report failed' if run.get('failed') else 'Report ran'} · {str(run.get('at') or '')[11:16]}",
                    'text': f"{title}: {said}" if said and said != title else title, 'key': f"report:{run['messageId']}", 'at': run.get('at')})
    # what was LEARNED is not a card: it lost its slot to agents and reports on any busy morning (the owner, 2026-10-08: "did you remove
    # the memory section?") - it is its own line on the opening card, always (summary's `learned`)
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
    # the brief, not the evidence the model was handed under it (reports.RAW_MARK): a failed run's evidence IS its body
    from .reports import RAW_MARK
    return {'source_id': src['SourceId'], 'at': run.get('at'), 'text': str(m.get('BodyText') or '').split(RAW_MARK)[0].strip()}


def summary(store, now: datetime = None) -> dict:
    return {'overnight': overnight(store, now), 'learned': learned(store, now), 'cards': cards(store, now), 'digest': digest(store)}
