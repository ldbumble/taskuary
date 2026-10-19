"""The outcome ledger (spec 2026-10-12, build step 2).

Every store that remembers is written from the owner's click at the moment of the click. Nothing recorded what the
owner did NEXT (Continue, "merge it") or what the world did AFTER (the thread died, the task reopened, the PR
held, Ray delivered on day 9). This table does: one row per action, filled in two halves - the action when it happens
(record), the outcome days later by a sweep that reads facts already in the store (resolve). No model runs here:
what the facts MEAN is reflection's (learn.gather reads evidence()), and the Advisor's (build step 3).
"""
import json
from datetime import datetime, timedelta
from loguru import logger

KINDS = ('reply.sent', 'task.closed', 'agent.stopped', 'agent.continued', 'pr.merged', 'promise.made', 'sender.ignored',
         'chase.let_go', 'chase.elsewhere')          # the slipped card's answers (spec 2026-10-12, build step 4)
WINDOW = {'reply.sent': 7, 'task.closed': 7, 'agent.stopped': 2, 'pr.merged': 14, 'sender.ignored': 60, 'promise.made': 7}
SWEPT_KEY = 'outcomes_swept_on'
def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def _dt(s):
    try: return datetime.strptime(str(s)[:19].replace('T', ' '), '%Y-%m-%d %H:%M:%S')
    except (TypeError, ValueError): return None


def record(store, kind: str, target_kind: str, target_id, actor: str = 'owner', facts: dict = None, next_move: str = None, at: str = None) -> int:
    """One row for an action just taken. A storage failure is logged and returns 0: the ledger rides along on a send, a close,
    a hook - none of which may fail for it. An unknown kind is a programming error and raises."""
    if kind not in KINDS: raise ValueError(f'not an outcome kind: {kind}')
    try:
        return store._exec('INSERT INTO outcome (Kind,TargetKind,TargetId,Actor,At,FactsJson,NextMove,NextAt) VALUES (?,?,?,?,?,?,?,?)',
                           (kind, target_kind, int(target_id or 0), actor, at or _now(), json.dumps(facts or {}),
                            '' if next_move is None else str(next_move)[:300], _now() if next_move is not None else None))
    except Exception as e:
        logger.warning(f'outcome {kind} on {target_kind} {target_id} not recorded: {e}'); return 0


def open_stop(store, tid) -> dict | None:
    return store._one("SELECT * FROM outcome WHERE Kind='agent.stopped' AND TargetKind='task' AND TargetId=? AND ResolvedAt IS NULL ORDER BY Id DESC LIMIT 1", (int(tid),))
def stopped(store, tid, actor: str, facts: dict = None) -> int:
    """A stop is ONE row per stretch of waiting, not one per turn: the Stop hook fires at every response's end, and a session
    the owner is typing into ends thirty of them. The row opens at the first stop and closes at the owner's next move."""
    return 0 if open_stop(store, tid) else record(store, 'agent.stopped', 'task', tid, actor, facts=facts)
def owner_words(text: str) -> str:
    """What the owner typed, without what Taskuary typed around it: a Resume arrives as "FROM THE OWNER: <words> <the resume
    handover>", and the whole of it sat in the ledger as the owner's words - the Advisor read our own instructions back as theirs
    (2026-10-13)."""
    from .continuity import RESUME_PROMPT
    t = ' '.join(str(text or '').split())
    t = t.split(' '.join(RESUME_PROMPT.split()[:5]))[0].strip()
    return t[len('FROM THE OWNER:'):].strip() if t.upper().startswith('FROM THE OWNER:') else t
def moved_on(store, tid, words: str, where: str = 'pane'):
    """The owner's next move after a stop, in their words (a prompt typed into the pane): the open stop row closes now."""
    r = open_stop(store, tid)
    if not r: return
    now, at = datetime.now(), _dt(r['At']) or datetime.now()
    mins = max(0, int((now - at).total_seconds() // 60)); words = owner_words(words)[:300]
    store._exec('UPDATE outcome SET NextMove=?, NextAt=? WHERE Id=?', (words, now.strftime('%Y-%m-%d %H:%M:%S'), r['Id']))
    settle(store, r['Id'], f'continued {mins} min later in the {where}' + ('' if words else ' with no words'), 'continued')


def rows_for(store, target_kind: str, target_id) -> list:
    return store._rows('SELECT * FROM outcome WHERE TargetKind=? AND TargetId=? ORDER BY Id DESC', (target_kind, int(target_id)))
def open_rows(store) -> list: return store._rows('SELECT * FROM outcome WHERE ResolvedAt IS NULL ORDER BY Id')
def settle(store, row_id: int, outcome: str, verdict: str, now: str = None):
    store._exec('UPDATE outcome SET Outcome=?, Verdict=?, ResolvedAt=? WHERE Id=? AND ResolvedAt IS NULL', (outcome, verdict, now or _now(), row_id))
def update_facts(store, row_id: int, **more):
    """A fact the sweep learned later (how long the answer took, who gave it) joins the row's facts."""
    r = store._one('SELECT FactsJson FROM outcome WHERE Id=?', (row_id,)) or {}
    f = json.loads(r.get('FactsJson') or '{}'); f.update(more)
    store._exec('UPDATE outcome SET FactsJson=? WHERE Id=?', (json.dumps(f), row_id))


def _material_inbound_after(store, cid: str, at: str) -> list:
    """Their words on the thread after `at`: not the owner's, not an auto-reply, not a calendar response."""
    from .autoreply import is_auto
    from .counsel import is_invite
    from .ingest import is_ours                                 # the repo's one own-mail predicate: Status, Direction, FromName
    me = str(store.get_setting('owner_email', '') or '').lower()
    rows = store._rows('SELECT * FROM message WHERE ConversationId=? AND SentAt>? ORDER BY SentAt', (cid, at))
    return [r for r in rows if not is_ours(r) and (not me or str(r.get('FromEmail') or '').lower() != me) and not is_auto(r) and not is_invite(r)]


def _resolve_one(store, r: dict, now: datetime):
    kind, at, facts = r['Kind'], _dt(r['At']), json.loads(r.get('FactsJson') or '{}')
    if not at: return settle(store, r['Id'], 'no stamp', 'unknown')
    age = (now - at).days
    t = store.get_task(r['TargetId']) if r['TargetKind'] == 'task' else None
    if kind == 'reply.sent':
        if not facts.get('cid'): return settle(store, r['Id'], 'no thread to watch', 'unknown')   # new mail, no conversation: nothing to read
        if age < WINDOW[kind]: return
        later = _material_inbound_after(store, facts.get('cid') or '', r['At'])
        if later:                                   # the person facts: how long THEIR first word took, and whose it was
            update_facts(store, r['Id'], answer_days=round(max(0.0, ((_dt(later[0]['SentAt']) or now) - at).total_seconds() / 86400), 1),
                         answered_by=str(later[0].get('FromEmail') or '').lower())
        reopened = t and t.get('Status') not in ('done', 'dropped') and facts.get('closed')
        if later or reopened: return settle(store, r['Id'], f"{len(later)} more from them" + ('; the task reopened' if reopened else ''), f'unsettled: {len(later)} more')
        return settle(store, r['Id'], 'nothing more from them in the window; the task stayed as it was', 'settled')
    if kind == 'task.closed':
        if age < WINDOW[kind]: return
        back = t and t.get('Status') not in ('done', 'dropped')
        return settle(store, r['Id'], 'open again' if back else 'stayed closed', 'reopened' if back else 'held')
    if kind == 'agent.stopped':
        nxt = store._one("SELECT * FROM outcome WHERE TargetKind='task' AND TargetId=? AND Kind IN ('agent.continued','task.closed') AND Id>? ORDER BY Id LIMIT 1",
                         (r['TargetId'], r['Id']))
        if nxt:
            verdict = 'continued' if nxt['Kind'] == 'agent.continued' else 'closed'
            mins = max(0, int(((_dt(nxt['At']) or now) - at).total_seconds() // 60))
            store._exec('UPDATE outcome SET NextMove=?, NextAt=? WHERE Id=?', (nxt.get('NextMove') or '', nxt['At'], r['Id']))   # their words or none, never ours
            return settle(store, r['Id'], f'{verdict} {mins} min later' + (' with no words' if verdict == 'continued' and not nxt.get('NextMove') else ''), verdict)
        if age >= WINDOW[kind]: return settle(store, r['Id'], 'nothing for two days', 'left')
        return
    if kind == 'agent.continued': return settle(store, r['Id'], 'the owner continued it', 'continued')
    if kind == 'pr.merged':
        if age >= WINDOW[kind]: return settle(store, r['Id'], 'still merged after two weeks', 'held')
        return
    if kind == 'promise.made':
        due = _dt(f"{str((t or {}).get('DueAt') or '')[:10]} 00:00:00")
        if t and t.get('Status') == 'done':
            closed = _dt(t.get('ClosedAt')) or now
            late = due and closed.date() > due.date()
            return settle(store, r['Id'], f"delivered {closed:%Y-%m-%d}" + (f", due {due:%Y-%m-%d}" if due else ''), 'kept late' if late else 'kept')
        if due and (now - due).days >= WINDOW[kind]: return settle(store, r['Id'], f'not delivered a week past {due:%Y-%m-%d}', 'late')
        return
    if kind in ('chase.let_go', 'chase.elsewhere'):   # the owner's own answer on a slipped item: a fact the moment it is given
        return settle(store, r['Id'], 'put down' if kind == 'chase.let_go' else f"answered elsewhere: {facts.get('where') or ''}".strip(), 'closed')
    if kind == 'sender.ignored':
        if age < WINDOW[kind]: return
        who = str(facts.get('from') or '').lower()
        tasks = store.tasks_from_sender(who, r['At']) if who else []
        return settle(store, r['Id'], f'{len(tasks)} task(s) from them since' if tasks else 'nothing from them became work', 'regret' if tasks else 'no regret')


def resolve(store, now: datetime = None) -> int:
    """The sweep: every open row old enough to judge, judged from the store's own facts. Bookkeeping, no model."""
    now, n = now or datetime.now(), 0
    for r in open_rows(store):
        try:
            _resolve_one(store, r, now)
            if store._one('SELECT ResolvedAt FROM outcome WHERE Id=?', (r['Id'],))['ResolvedAt']: n += 1
        except Exception as e: logger.warning(f'outcome {r["Id"]} not resolved: {e}')
    return n


def sweep_if_due(store, now: datetime = None):
    """Once a day, from the poll's housekeeping (server._poll_reports): None when today's sweep already ran."""
    now = now or datetime.now(); today = now.strftime('%Y-%m-%d')
    if store.get_setting(SWEPT_KEY, '') == today: return None
    n = resolve(store, now)
    store.set_setting(SWEPT_KEY, today, 'outcomes')
    return n


def _sentence(store, r: dict) -> str:
    """The row as one factual sentence with the owner's words verbatim - what happened, never what it means."""
    f = json.loads(r.get('FactsJson') or '{}'); kind = r['Kind']
    ref = f"TQ-{int(r['TargetId']):04d}" if r['TargetKind'] == 'task' and r['TargetId'] else r['TargetKind']
    who = str(r.get('Actor') or '').split(':', 1)[-1]
    nxt = ('' if kind != 'agent.stopped' or r['Verdict'] != 'continued' else
           f'; you then said "{owner_words(r["NextMove"])}"' if owner_words(r.get('NextMove')) else '; you then continued it with no words')
    head = {'reply.sent': f"you sent a reply on {ref} (approved as drafted)" if f.get('verb') == 'approve' else f"you sent a reply on {ref} (edited first)",
            'task.closed': f"{ref} was closed by {who} ({f.get('how', '')})", 'agent.stopped': f"{who} stopped on {ref}" + (' (PR open)' if f.get('pr') else ''),
            'agent.continued': f'you continued {ref} with "{r.get("NextMove")}"' if r.get('NextMove') else f'you continued {ref} with no words',
            'pr.merged': f"PR #{f.get('pr')} on {ref} was merged", 'promise.made': f"you promised on {ref}" + (f" by {f.get('due')}" if f.get('due') else ''),
            'sender.ignored': f"you ignored {f.get('from')}"}.get(kind, kind)
    return f"{head}{nxt}; outcome: {r.get('Outcome') or ''} [{r.get('Verdict') or ''}]"


def evidence(store, since: str, limit: int = 40) -> list:
    """One line per resolved row, newest first, `out{id}: ...` - what reflection reads (learn.gather) and cites."""
    rows = store._rows("SELECT * FROM outcome WHERE ResolvedAt IS NOT NULL AND Verdict!='unknown' AND At>=? ORDER BY Id DESC LIMIT ?", (since, limit))
    return [f"out{r['Id']}: {_sentence(store, r)}" for r in rows]


# ── the work facts (build step 5): per playbook, no model; playbook_facts.py says what they mean ───────────────────────────
def work_facts(store, slug: str) -> dict:
    """How a KIND of work has gone: its resolved closes, how many came open again, how many closed with the last mail still
    asking something, and how many of those came open again."""
    rows = store._rows("SELECT Verdict, json_extract(FactsJson, '$.asked') asked FROM outcome WHERE Kind='task.closed' AND ResolvedAt IS NOT NULL "
                       "AND json_extract(FactsJson, '$.playbook')=?", (str(slug),))
    back, asked = [r['Verdict'] == 'reopened' for r in rows], [bool(r['asked']) for r in rows]
    return {'closes': len(rows), 'reopened': sum(back), 'closed_with_open_question': sum(asked), 'reopened_after_open_question': sum(a and b for a, b in zip(asked, back))}


# ── the person facts (build step 4): bookkeeping per address, no model; people_pages.py says what they mean ──────────
def _rows_who(store, who: str, kind: str = None) -> list:
    """Every row whose facts name this address - the person key the ledger carries (`who`), never a name."""
    q, p = "SELECT * FROM outcome WHERE json_extract(FactsJson, '$.who')=?", [str(who or '').lower()]
    if kind: q += ' AND Kind=?'; p.append(kind)
    return store._rows(q + ' ORDER BY Id', p)


def person_facts(store, who: str) -> dict:
    """What the ledger counts about one person: replies and how fast they answered, chases and whether they worked, steps
    they owed and how late, how often the owner let one go, and who on copy was there when they answered."""
    who = str(who or '').lower(); f = [(r, json.loads(r.get('FactsJson') or '{}')) for r in _rows_who(store, who)]
    replies = [x for x in f if x[0]['Kind'] == 'reply.sent' and x[0].get('ResolvedAt')]       # an answer is the sweep's to count
    answered = [x for x in replies if x[1].get('answer_days') is not None]
    days = sorted(x[1]['answer_days'] for x in answered)
    cc = {}
    for r, x in replies:
        for a in x.get('cc') or []:
            c = cc.setdefault(str(a).lower(), [0, 0]); c[1] += 1; c[0] += 1 if x.get('answer_days') is not None else 0
    steps = [x for x in f if x[0]['Kind'] == 'task.closed']
    return {'replies': len(replies), 'answered': len(answered), 'answer_days': days,
            'median_days': (days[len(days) // 2] if len(days) % 2 else (days[len(days) // 2 - 1] + days[len(days) // 2]) / 2) if days else None,
            'chased': sum(1 for _, x in replies if x.get('chase')), 'answered_after_chase': sum(1 for _, x in answered if x.get('chase')),
            'steps': len(steps), 'steps_late': sum(1 for _, x in steps if (x.get('late_days') or 0) > 0),
            'let_go': sum(1 for r, _ in f if r['Kind'] == 'chase.let_go'), 'cc': cc}
def let_go_count(store, who: str) -> int: return len(_rows_who(store, who, 'chase.let_go'))


def late_after(store, who: str, default: int = 5) -> int:
    """The day a silence is late for THIS person: half again their median answer, two at least - once three answers say
    what their median is. Fewer is no habit: the default day (Settings -> Advisor)."""
    import math
    f = person_facts(store, who)
    return max(2, math.ceil(f['median_days'] * 1.5)) if f['answered'] >= 3 and f['median_days'] is not None else int(default)


def chase_cc(store, who: str):
    """The copied address that moved this person, when the ledger has seen it move them: two or more replies with them on
    copy and most of those answered. None otherwise - a chase copies nobody on a guess."""
    best = [(a, n, m) for a, (n, m) in person_facts(store, who)['cc'].items() if m >= 2 and n / m >= 0.6]
    return max(best, key=lambda x: (x[1] / x[2], x[2]))[0] if best else None
