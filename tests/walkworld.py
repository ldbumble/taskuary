"""THE WALK TABLE'S WORLD (docs/superpowers/specs/2026-10-30-walk-one-owner-design.md, 6.1): the demo world, its rail cleared and laid
out again as the table names it - so the Python runner (tests/test_walk_table.py) and the browser runner (website/browser/walk-table)
walk the same rows. Rows are named by symbol and resolved to keys by what they were made from (a task, a message, a meeting), never by
a key written into the table. Everyone here is invented (CLAUDE.md): Northwind, Erin Blake, Gail Moreno, Paula Vance, *.example.

    Tasks:      T1 (task, oldest)  T2 (urgent ask)  T3 (agent working)  T4 (draft ready, Erin Blake)  T5 (task)  M1 (meeting, in 10 min)
    For later:  L1 (reminded task)
    Reports:    R1 (report)  R2 (agent-finished task)  R3 (dashboard)
    Ideas:      I1 (Advisor idea)
    FYI:        F1 .. F7   (fyi_batch 4, set by the owner: B1 = F1-F4, B2 = F5-F7)
    Off rail:   C1 (closed task, arrived between T2 and T3)
"""
import json
from datetime import datetime, timedelta

ORDER = ('T1', 'T2', 'T3', 'T4', 'T5', 'M1', 'L1', 'R1', 'R2', 'R3', 'I1', 'F1', 'F2', 'F3', 'F4', 'F5', 'F6', 'F7')
LINE = tuple(s for s in ORDER if s != 'L1')
MEETING = 'Northwind cutover check-in'


def _stamp(t: datetime) -> str: return t.strftime('%Y-%m-%d %H:%M:%S')


def clear(store):
    """Every row the demo put on the rail is closed or read - by the owner, as a person clearing their desk would."""
    from taskuary import funnel
    for t in store.list_tasks():
        if t.get('Status') in ('done', 'dropped'): continue
        for r in store._rows("SELECT ReviewId FROM review WHERE TaskId=? AND Status IN ('pending','held')", (t['TaskId'],)):
            store.decide_review(r['ReviewId'], 'no_reply', None, 'owner', note='the walk table clears the demo')
        store.update_task(t['TaskId'], {'Status': 'done'}, 'owner')
    store._exec("UPDATE run SET Status='done' WHERE Status='running'")
    reconcile(store)
    for i in funnel.pile(store, force=True)['items']:
        # ...and what a closed task still leaves there - an agent's result unread, a mail on it - read too, so a world laid out twice is one world
        if not str(i['key']).startswith('meeting:'): funnel.settle(store, i['key'], 'done', 'owner')
    reconcile(store)


def reconcile(store):
    from taskuary import funnel
    if getattr(store, 'processing_reads_active', lambda: False)():
        from taskuary import processing_all
        processing_all.wait_settled(store)
        store.reconcile_processing_membership()
    funnel.invalidate()


def meeting(store, minutes: int = 10):
    """M1 on the calendar, `minutes` from now: the agenda cache the rail reads, held fresh so no refresh replaces it."""
    from taskuary import assistant
    start = datetime.now().replace(second=0, microsecond=0) + timedelta(minutes=minutes)
    ev = {'start': start.strftime('%Y-%m-%d %H:%M'), 'end': (start + timedelta(minutes=30)).strftime('%Y-%m-%d %H:%M'), 'subject': MEETING,
          'all_day': False, 'status': 'busy', 'where': '', 'mailbox': 'demo', 'organizer': 'Gail Moreno', 'who': ['Gail Moreno'],
          'about': '', 'join': '', 'link': ''}
    assistant._AGENDA.update(days=7, at=datetime.now().timestamp() + 10 ** 9, events=[ev])
    return ev


def build(store, now: datetime = None) -> dict:
    """Clear the demo's rail and lay out the table's world. Returns the symbols' sources: {symbol: {'tid'|'mid'|'meeting': ...}}."""
    from taskuary.testing import Factory
    now = now or datetime.now()
    clear(store)
    f = Factory(store); f.actor = 'triage'
    at = lambda minutes: _stamp(now - timedelta(minutes=minutes))
    src = {}

    def task(sym, title, minutes, who=('Gail Moreno', 'gail@northwind.example'), status='open', kind='general', **kw):
        tid = f.task(title=title, status=status, kind=kind, **kw)
        mid = f.message(task_id=tid, subject=title, from_name=who[0], from_email=who[1], sent_at=at(minutes),
                        body=f'{title} - please take a look.', conversation_id=f'walkworld:{sym}')
        f.route(mid, tid, 'create', 'real work')
        store._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (at(minutes), tid))
        src[sym] = {'tid': tid, 'mid': mid}
        return tid, mid

    task('T1', 'Northwind ledger close - the June variance', 600)
    task('T2', 'Payworth payroll file rejected - resend today', 540, Priority='urgent')
    store._exec("UPDATE task SET Priority='urgent' WHERE TaskId=?", (src['T2']['tid'],))
    c1, _ = task('C1', 'Trainly seats renewed for the floor team', 500)
    store.update_task(c1, {'Status': 'done'}, 'owner')
    t3, _ = task('T3', 'Reconcile the Spendly card feed', 480, status='in_progress')
    f.run(t3, agent='general')
    t4, m4 = task('T4', 'PhishGuard training dates for the floor', 420, who=('Erin Blake', 'erin@vendor.example'), kind='reply')
    src['T4']['rid'] = f.review(t4, m4, draft='Tuesday and Thursday both work for the floor team.')
    task('T5', 'Order badges for the two new starters', 360)
    meeting(store, 10)
    src['M1'] = {'meeting': MEETING}
    l1, _ = task('L1', 'Check the portal export after the upgrade', 560)
    store._exec('UPDATE task SET RemindAt=? WHERE TaskId=?', (_stamp(now + timedelta(days=2)), l1))
    # Reports: a report run, an agent's finished task, a dashboard landing - oldest first
    r1 = f.report_row(title='Northwind headcount by site')
    store._exec('UPDATE message SET SentAt=? WHERE MessageId=?', (at(300), r1.mid))
    src['R1'] = {'mid': r1.mid}
    r2, _ = task('R2', 'Find why the nightly ledger export was empty', 280, kind='general', status='in_progress')
    store.add_comment(r2, 'coding', 'agent', 'The agent closed this itself: the export ran before the bank feed landed; moved it to 02:00.')
    store.update_task(r2, {'Status': 'done'}, 'coding')
    r3 = f.report_row(title='Northwind desk')
    store._exec('UPDATE message SET SentAt=? WHERE MessageId=?', (at(260), r3.mid))
    src['R3'] = {'mid': r3.mid}
    # Ideas: one Advisor idea of its own, with no task under it
    idea = store.upsert_idea({'key': 'idea:walkworld-vendor-terms', 'kind': 'idea', 'sig': 'walkworld-vendor-terms',
                              'text': 'Payworth renews in three weeks and nobody has asked for the new terms yet.',
                              'action': {'type': 'note', 'whose': 'the owner', 'suggest': 'Ask Payworth for the renewal terms.'}}, at(200))
    store._exec('UPDATE idea SET FirstSeen=?, LastSaid=? WHERE IdeaId=?', (at(200), at(200), idea['IdeaId']))
    # ...judged already, as the Advisor's own pass leaves it: unjudged, a running app's triage pass marks it pending - "being read", off the line
    store.set_idea_action(idea['IdeaId'], {'type': 'note', 'whose': 'the owner', 'suggest': 'Ask Payworth for the renewal terms.',
                                           'triage': {'intent': 'fyi', 'kind': None, 'why': 'a note for you', 'sig': idea.get('Sig') or '',
                                                      'at': at(200), 'linked_task': None, 'error': None}})
    src['I1'] = {'idea': idea['IdeaId']}
    # FYI: seven filed mails, one thread each, ten minutes apart
    for n in range(1, 8):
        mid = f.message(task_id=None, status='filed', subject=f'Northwind floor notice {n}', from_name='Paula Vance',
                        from_email='paula@northwind.example', sent_at=at(180 - n * 10), body=f'Floor notice {n}: nothing to do.',
                        conversation_id=f'walkworld:F{n}')
        f.route(mid, None, 'file', 'information, nothing to do')
        src[f'F{n}'] = {'mid': mid}
    store.set_setting('fyi_batch', '4', 'owner')
    reconcile(store)
    return src


def arrive(store, src: dict, sym: str):
    """A row arriving now: T6 a task (newest under Tasks), F8 an FYI (newest under FYI)."""
    from taskuary.testing import Factory
    f = Factory(store); f.actor = 'triage'
    now = _stamp(datetime.now())
    if sym.startswith('T'):
        tid = f.task(title='Paula: the new starter has no badge', status='open', kind='general')
        mid = f.message(task_id=tid, subject='The new starter has no badge', from_name='Paula Vance', from_email='paula@northwind.example',
                        sent_at=now, body='Can you sort a badge today?', conversation_id=f'walkworld:{sym}')
        f.route(mid, tid, 'create', 'real work')
        store._exec('UPDATE task SET CreatedAt=? WHERE TaskId=?', (now, tid))
        src[sym] = {'tid': tid, 'mid': mid}
    else:
        mid = f.message(task_id=None, status='filed', subject='Northwind floor notice 8', from_name='Paula Vance',
                        from_email='paula@northwind.example', sent_at=now, body='Floor notice 8: nothing to do.', conversation_id=f'walkworld:{sym}')
        f.route(mid, None, 'file', 'information, nothing to do')
        src[sym] = {'mid': mid}
    reconcile(store)


def close_elsewhere(store, src: dict, sym: str):
    """Closed somewhere other than the walk - the Tasks page, the phone, a meeting that is over."""
    from taskuary import concierge, funnel
    s = src[sym]
    if 'meeting' in s:                                # a meeting is over: gone from the calendar the rail reads
        from taskuary import assistant
        assistant._AGENDA['events'] = [e for e in assistant._AGENDA.get('events') or [] if e.get('subject') != s['meeting']]
    elif 'tid' in s: concierge.close_task(store, s['tid'], 'owner')
    else:
        key = key_of(store, src, sym)
        if key: funnel.settle(store, key, 'done', 'owner')
    reconcile(store)


def agent_closes(store, src: dict, sym: str):
    """The task's agent finished it and closed it itself: its result is a row under Reports."""
    tid = src[sym]['tid']
    import time; time.sleep(1.1)                      # after the open that read it: stamps are to the second, and a close in that second reads as seen
    store._exec("UPDATE run SET Status='done' WHERE TaskId=?", (tid,))
    store.add_comment(tid, 'coding', 'agent', 'The agent closed this itself: matched every card line to the ledger.')
    store.update_task(tid, {'Status': 'done'}, 'coding')
    reconcile(store)


def rows(store, full: bool = False) -> list:
    from taskuary import funnel
    p = funnel.pile(store)
    return (funnel.full_items(store) or p['items']) if full else p['items']


def matches(row: dict, s: dict) -> bool:
    if 'meeting' in s: return row.get('kind') == 'meeting' and s['meeting'] in str(row.get('title') or '')
    if 'idea' in s: return row.get('idea') == s['idea']
    if 'tid' in s and row.get('tid') == s['tid']: return True
    mids = {str(m) for m in row.get('member_ids') or ()}
    return 'mid' in s and not s.get('tid') and (row.get('mid') == s['mid'] or f"message:{s['mid']}" in mids)


def key_of(store, src: dict, sym: str, items: list = None) -> str | None:
    """A symbol's key on the rail as it is now - or, for a task not on it, `task:<n>`."""
    s = src.get(sym)
    if not s: return None
    row = next((r for r in (items if items is not None else rows(store)) if matches(r, s)), None)
    if row: return row['key']
    return f"task:{s['tid']}" if s.get('tid') else None


def symbol_of(store, src: dict, key: str, items: list = None) -> str | None:
    """The symbol a rail key stands for (by the row it names), else None."""
    items = items if items is not None else rows(store)
    row = next((r for r in items if key == r['key'] or key in (r.get('aliases') or ())), None)
    for sym, s in src.items():
        if row and matches(row, s): return sym
        if s.get('tid') and key == f"task:{s['tid']}": return sym
    return None


def dump(store, src: dict) -> list:
    """The rail as (section, symbol or '?') - what a failing case prints."""
    from taskuary import lanes
    return [(lanes.level_of(r), symbol_of(store, src, r['key']) or f"?{r.get('kind')}") for r in rows(store)]
