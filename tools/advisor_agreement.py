"""HOW OFTEN THE LIT BUTTON WAS THE ONE THE OWNER WANTED (the owner, 2026-10-28: "Trust is the product... measure that agreement rate after each
release and treat it as the number that matters"). Read-only: the home's database is opened `mode=ro`, and a replay works on a backup copy.

    python tools/advisor_agreement.py                       # the live home (TASKUARY_HOME, else ~/.taskuary), the last 7 days
    python tools/advisor_agreement.py --since "2026-10-28 07:03" --home <dir>
    python tools/advisor_agreement.py --replay              # ...and what today's Advisor code would have lit on the same items
    python tools/advisor_agreement.py --line                # one line, for tools/release.sh

A DECISION is what one item had lit while the owner was on it, read from the press log (advice_press: every press, on every surface,
keeps what that surface had lit - presses.py). Presses on one item under the same lit button are one decision: Next walks past it and
leaves it open, the first other press is the owner's answer. A reply that went while it was open is the answer (Send in the draft, then
Mark done). A decision nobody pressed an answer to takes the owner's own act on the item from the outcome ledger (a close, a send, a
continue typed in the pane) until the item's next decision or two days; else it was walked past. The row's pickers (priority, kind, who,
the code's place, a split) answer nothing; the same act pressed again within SAME_M minutes, and a Stop then Mark done within them, are
one decision (a Mark done); a Stop on a task already closed is not counted (the 2026-11-02 audit).
  right    the owner pressed the lit button (or its twin: Let go is Mark done, Try again is Continue); a reply sent as drafted agrees with
           Send, and with Reply when no draft was on the row yet; one sent in the owner's own words agrees with either
  wrong    the owner did something else - Next counts only when Next was lit
  unclear  walked past with nothing done, a press with no other button to choose
Agreement is right / (right + wrong). A decision nothing was pressed on at all is not in the log, so it is not counted.
A decision whose lit button was GREYED at a press (drawn, but disabled - press log Greyed, since 2026-10-28) is flagged apart: the Advisor
pointed at a button the owner could not press.

PRECISION, COVERAGE AND DROPPED BALLS (the design rev 2, 2026-10-28: NO DEFAULT VERB - when unsure, nothing is lit). Silence is neither right
nor wrong, so three numbers say how the Advisor did:
  precision  agreement on the decisions where something WAS lit - split by who lit it: the finish check (By 'check', or its agent.check
             row) and the rest
  silent     the share of decisions where nothing was lit (an item pressed on with no lit button is a decision too, the same way)
  dropped    a silent decision the owner answered with Redraft, Stop or Continue while no Advisor row had lit anything on that item in the
             hour before: a ball it should have flagged. Falling week on week is the target, with precision at 80% or more.
"""
import argparse, json, os, sqlite3, sys, tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

TWIN = {'let_go': 'close', 'done': 'close', 'try_again': 'continue', 'remove': 'close'}   # Remove puts the item down, as Mark done does
# moving about, and the row's pickers (advisor.NOT_MOVES: who does it, priority, its kind, the code's place, a split) - a field set, never a
# move on the item's decision, so neither right nor wrong (the 2026-11-02 audit: they were counted as the owner overruling the light)
NOT_ANSWERS = {'back', 'reopen', 'priority', 'change_kind', 'assign', 'owner', 'pick_repo', 'split', 'attach', 'close_note'}
OWNER = ('owner', 'you')
ACT = {'task.closed': 'close', 'reply.sent': 'approve', 'agent.continued': 'continue'}   # outcome kinds that are the owner's own acts
HORIZON_H, LOOKBACK_H = 48, 1 / 6
CHECK = 'agent.check'                               # the finish check's advice rows (advisor.CHECK)
DROPPED = {'redraft', 'stop_agent', 'continue'}     # a press that picks up a ball something dropped
FIRED_H = 1                                         # ...unflagged: no Advisor row lit anything on the item this long before it
STEER_H = 12                                        # a Continue within this long of the owner's own Continue on the item is steering
REOPEN_H = 2                                        # ...and a Continue this soon after the owner's own reopen of it
SAME_M = 10                                         # minutes: the same act pressed again, or a Stop then Mark done, is one decision
def _v(v): return TWIN.get(v or '', v or '')
def _in(xs): return ','.join('?' * len(xs))


def connect(home) -> sqlite3.Connection:
    """The home's database, read-only: a measurement never writes to the store it measures."""
    p = Path(home, 'taskuary.db').resolve()
    if not p.exists(): raise FileNotFoundError(p)
    cx = sqlite3.connect(p.as_uri() + '?mode=ro', uri=True); cx.row_factory = sqlite3.Row
    return cx
def _rows(cx, q, a=()): return [dict(r) for r in cx.execute(q, a)]
def _later(at, h): return (datetime.fromisoformat(str(at)[:19]) + timedelta(hours=h)).strftime('%Y-%m-%d %H:%M:%S')
def _soon(a, b): return str(b) <= _later(a, SAME_M / 60)


def closed_at(cx, target, key, at) -> bool:
    """Whether the item's task was closed at `at`: its latest close in the ledger, with no reopen press or Continue after it."""
    if target[0] != 'task': return False
    c = cx.execute("SELECT MAX(At) a FROM outcome WHERE TargetKind=? AND TargetId=? AND Kind='task.closed' AND At<=?", (*target, at)).fetchone()['a']
    if not c: return False
    if cx.execute("SELECT 1 FROM advice_press WHERE Key=? AND Pressed='reopen' AND CreatedAt>=? AND CreatedAt<=? LIMIT 1", (key, c, at)).fetchone(): return False
    return not cx.execute("SELECT 1 FROM outcome WHERE TargetKind=? AND TargetId=? AND Kind='agent.continued' AND At>? AND At<=? LIMIT 1",
                          (*target, c, at)).fetchone()


def model_row(cx, kind, tid, rev, verb=None):
    """The Advisor's own judgement at that revision (advice): the model's verb, line and the kind of fact it said - newest first."""
    if not rev: return None
    q = 'SELECT * FROM advice WHERE TargetKind=? AND TargetId=? AND Revision=? AND Verb IS NOT NULL' + (' AND Verb=?' if verb else '')
    r = cx.execute(q + ' ORDER BY Id DESC LIMIT 1', (kind, tid, rev, *([verb] if verb else []))).fetchone()
    return dict(r) if r else None


GUESS = {'approve': 'draft_ready', 'reply': 'asked', 'continue': 'stopped', 'defer': 'waiting', 'chase': 'waiting_late', 'mine': 'idea', 'fix': 'failed',
         'review_changes': 'unpushed', 'accept_invite': 'invite_free', 'propose_time': 'invite_clash', 'copy': 'unsendable', 'retriage': 'unsorted',
         'test_connection': 'connection'}
def _state(cx, d) -> str:
    """The rule state behind the decision: the kept decision when it is the same revision (advice_decision keeps only an item's latest),
    else read off the lit button and the item's kind, marked '~' as a guess."""
    r = cx.execute('SELECT Stamp, Json FROM advice_decision WHERE Key=?', (d['key'],)).fetchone()
    if r and d['rev'] and r['Stamp'] == d['rev']:
        try: return json.loads(r['Json']).get('state') or '?'
        except ValueError: pass
    k, lit = d['kind'], d['lit']
    g = {'report': 'report_ok', 'fyi': 'fyi', 'fyis': 'fyi_batch', 'meeting': 'meeting'}.get(k, 'own') if lit == 'next' else \
        ('agent_done' if k in ('agent', 'agentdone') else 'done_list') if lit == 'close' else GUESS.get(lit, lit or '?')
    return '~' + g


def _sent(cx, target, a, b) -> str:
    """The owner's reply that went on the target between `a` and `b`: 'sent' as drafted, 'edited' in their own words, or ''."""
    r = cx.execute(f"SELECT json_extract(FactsJson,'$.verb') v FROM outcome WHERE Kind='reply.sent' AND TargetKind=? AND TargetId=? AND At>=? AND At<=? "
                   f"AND Actor IN ({_in(OWNER)}) ORDER BY Id LIMIT 1", (*target, a, b, *OWNER)).fetchone()
    return '' if not r else 'sent' if r['v'] == 'approve' else 'edited'


def decisions(cx, since: str, until: str = '9999', silent: bool = False) -> list:
    """The decisions pressed on from `since` to before `until`, oldest first: {key, target, rev, lit, by, state, kind, at, live, presses,
    action, via, ids}. `live` is every button the item's row had (the press log keeps the others; the pressed one is added back).
    `silent`: the decisions where nothing was lit as well (lit '', by 'silent') - for coverage and dropped balls, never scored."""
    ps = _rows(cx, 'SELECT * FROM advice_press WHERE CreatedAt>=? AND CreatedAt<? ORDER BY Id', (since, until))
    out, open_, last = [], {}, {}
    def close(d, action, via, until):
        # ...a reply that went while it was open is the answer, whatever was pressed round it (Send in the draft, then Mark done). The draft's
        # own Send is not in the press log, so the item was on screen before its first logged press: LOOKBACK_H earlier, never before the
        # item's previous decision
        prev = last.get(d['key'])
        a = max(_later(d['at'], -LOOKBACK_H), _later(prev['end'], 0.0003) if prev else '')
        if _v(d['lit']) in ('reply', 'approve') and (s := _sent(cx, d['target'], a, until)): action, via = s, 'outcome'
        d['action'], d['via'], d['end'] = action, via, until; open_.pop(d['key'], None)
        # ...the same answer pressed again on the same screen (a press that seemed not to take), or the same act pressed again within minutes,
        # is the same decision; a Stop then Mark done within minutes is one Mark done - putting the work down, never a dropped ball
        p = last.get(d['key'])
        if p and d['rev'] and (p['lit'], p['rev'], p['action']) == (d['lit'], d['rev'], d['action']): p['ids'] += d['ids']; p['last'] = d['last']; return
        if p and via == 'pressed' and p['via'] == 'pressed' and _soon(p['last'], d['at']) and (
                _v(p['action']) == _v(action) or p['action'] == 'stop_agent' and _v(action) == 'close'):
            if not p['lit'] and d['lit']: p.update({k: d[k] for k in ('lit', 'rev', 'live', 'greyed', 'choice', 'kept')})   # what was lit at the answer
            p['action'], p['end'], p['last'] = action, until, d['last']; p['ids'] += d['ids']; return
        out.append(d); last[d['key']] = d
    for p in ps:
        lit = (p.get('Lit') if p.get('Surface') else p.get('Advised')) or ''      # a row before 2026-10-23 is a desk press under a line
        got, key = p['Pressed'], p['Key']
        d = open_.get(key)
        if got in NOT_ANSWERS or (got == 'stop_agent' and closed_at(cx, (p['TargetKind'], p['TargetId']), key, p['CreatedAt'])):   # a Stop on a closed task stops nothing
            if d: d['ids'].append(p['Id'])
            continue
        if d and _v(d['lit']) != _v(lit): close(d, 'next', 'walked past', p['CreatedAt'])
        if not lit and not silent: continue                               # nothing lit: no decision of the Advisor's to score
        if key not in open_:
            open_[key] = {'key': key, 'target': (p['TargetKind'], p['TargetId']), 'rev': p.get('Revision') or '', 'lit': lit, 'kind': p.get('ItemKind') or '',
                          'at': p['CreatedAt'], 'last': p['CreatedAt'], 'live': [], 'greyed': [], 'choice': p.get('Choice') is None or bool(p['Choice']), 'ids': [], 'presses': [],
                          'kept': (p.get('State'), p.get('By'))}        # the decision as kept at the press (since 2026-10-28)
        d = open_[key]
        try: live = json.loads(p.get('Live') or '[]') or []
        except ValueError: live = []
        try: grey = json.loads(p.get('Greyed') or '[]') or []
        except ValueError: grey = []
        d['live'] = list(dict.fromkeys(d['live'] + live + [got]))
        d['greyed'] = list(dict.fromkeys(d['greyed'] + grey))
        d['ids'].append(p['Id']); d['presses'].append(got); d['last'] = p['CreatedAt']
        if got != 'next': close(d, got, 'pressed', _later(p['CreatedAt'], 0.05))
    # ...a decision left open takes the owner's own act from the outcome ledger, until that item's next decision (or two days)
    starts = defaultdict(list)
    for d in out + list(open_.values()): starts[d['key']].append(d['at'])
    for d in sorted(open_.values(), key=lambda d: d['at']):
        end = min([a for a in starts[d['key']] if a > d['at']] + [_later(d['at'], HORIZON_H)])
        r = cx.execute(f"SELECT Kind FROM outcome WHERE TargetKind=? AND TargetId=? AND Actor IN ({_in(OWNER)}) AND Kind IN ({_in(ACT)}) AND At>=? AND At<? "
                       "ORDER BY Id LIMIT 1", (*d['target'], *OWNER, *ACT, d['at'], end)).fetchone()
        close(d, ACT[r['Kind']], 'outcome', end) if r else close(d, 'next', 'walked past', end)
    for d in out:
        st, by = d.pop('kept')
        if not d['lit']: d['by'], d['state'] = 'silent', st or '?'; continue
        m = None if by else model_row(cx, *d['target'], d['rev'], d['lit'])
        d['by'] = by or ('check' if m and m.get('Event') == CHECK else 'model' if m and m.get('Model') else 'rule')
        d['state'] = st or _state(cx, d)
    return sorted(out, key=lambda d: (d['at'], d['ids'][0]))


def score(d: dict, lit: str = 'lit') -> str:
    """right, wrong or unclear for one decision, judged by its `lit` field ('lit' as shown, 'today' as replayed)."""
    v, action = _v(d[lit]), d['action']
    if not v: return 'silent'                           # nothing lit: neither right nor wrong (coverage counts it)
    if not d.get('choice', True): return 'unclear'      # only one button there: pressing it says nothing
    if action == 'edited': return 'right' if v in ('reply', 'approve') else 'wrong'
    if action == 'sent': return 'right' if v == 'approve' or (v == 'reply' and 'approve' not in d.get('live', ())) else 'wrong'
    if v == _v(action): return 'right'
    return 'unclear' if action == 'next' else 'wrong'


# ── WHAT TODAY'S CODE WOULD HAVE LIT (replay) ─────────────────────────────────────────────────────────────────────────────────────────
# No model is called. Where the item has not changed since (its revision now is the one pressed on), today's advisor.decide runs on a copy
# of the store and reads the recorded model rows at that revision - an exact replay. Elsewhere the store has moved on, and since 2026-11-02
# today's code has no rule of its own to replay (the owner: "never ever use hard coded rules"): the model decides every light and code only
# refuses a button the owner could not press. A model's verb stands as it was; a rule's ('left to the rule' - no model ever read the item) is
# the model's to read today, which needs a model call - counted unchanged, named 'model' so the report says how many such decisions remain.
def mirror(cx, d) -> tuple:
    """(the verb today's code lights, how) from what was recorded at the decision."""
    return d['lit'], ('model' if d['by'] == 'rule' else '')


def replay(cx, ds, store=None) -> list:
    """Each decision with `today` (the verb today's code lights) and `how` ('exact', a fix's name, or '' for unchanged)."""
    if store is not None:
        from taskuary import advisor
    for d in ds:
        d['today'], d['how'] = mirror(cx, d)
        if store is None or not d['rev']: continue
        try:
            if advisor.revision(store, *d['target']) != d['rev']: continue
            got = advisor.decide(store, d['key'])
            if got.get('state'): d['today'], d['how'] = got.get('verb') or '', 'exact'
        except Exception as e: print(f"  (no exact replay for {d['key']}: {e})", file=sys.stderr)
    return ds


def copied_store(home):
    """A backup of the home's database in a scratch home, opened as a store - today's code reads it and may write to it, never the original."""
    tmp = tempfile.mkdtemp(prefix='advisor-agreement-')
    src, dst = connect(home), sqlite3.connect(os.path.join(tmp, 'taskuary.db'))
    src.backup(dst); dst.close(); src.close()
    os.environ['TASKUARY_HOME'] = tmp                          # before taskuary is imported: nothing it opens is the measured home
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
    from loguru import logger
    logger.remove()
    from taskuary import advisor
    from taskuary.store import SQLiteStore
    advisor.BACKGROUND = False                                  # no thread and no model: the recorded rows are all it reads
    return SQLiteStore(os.path.join(tmp, 'taskuary.db'))


# ── THE REPORT ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def tally(ds, lit='lit') -> dict:
    c = Counter(score(d, lit) for d in ds)
    r, w = c['right'], c['wrong']
    return {'decisions': len(ds), 'right': r, 'wrong': w, 'unclear': c['unclear'], 'pct': round(100 * r / (r + w)) if r + w else None,
            **({'silent': c['silent']} if c['silent'] else {})}


def line(t: dict, since: str, label='Advisor agreement') -> str:
    pct = f"{t['pct']}%" if t['pct'] is not None else 'n/a'
    quiet = f", {t['silent']} silent" if t.get('silent') else ''
    return f"{label}: {pct} ({t['right']} right, {t['wrong']} wrong, {t['unclear']} unclear{quiet} of {t['decisions']} decisions since {since})"


def misses(ds, lit='lit', n=8) -> list:
    """The commonest wrong pairs - (lit, by, state, what the owner did) - each with its decisions."""
    g = defaultdict(list)
    for d in ds:
        if score(d, lit) == 'wrong': g[(d[lit], d['by'], d['state'].lstrip('~'), d['action'])].append(d)
    return sorted(g.items(), key=lambda kv: -len(kv[1]))[:n]


def lit(ds) -> list: return [d for d in ds if d['lit']]


def precision(ds) -> dict:
    """Agreement on the lit decisions alone, and split by who lit them: the finish check, and the rest."""
    on = lit(ds)
    return {'all': tally(on), 'check': tally([d for d in on if d['by'] == 'check']), 'rest': tally([d for d in on if d['by'] != 'check'])}


def coverage(ds) -> dict:
    """How many decisions had nothing lit, of all of them."""
    n, quiet = len(ds), sum(1 for d in ds if not d['lit'])
    return {'decisions': n, 'silent': quiet, 'pct': round(100 * quiet / n) if n else None}


def fired(cx, d) -> bool:
    """Whether any Advisor row lit something on the decision's item in the FIRED_H hours before it."""
    a = _later(d['at'], -FIRED_H)
    return bool(cx.execute('SELECT 1 FROM advice WHERE TargetKind=? AND TargetId=? AND Verb IS NOT NULL AND CreatedAt>=? AND CreatedAt<=? LIMIT 1',
                           (*d['target'], a, d['end'] if d.get('end') else d['at'])).fetchone())


def steering(cx, d, ds) -> bool:
    """A Continue the owner presses on work they are already driving - their own Continue (a press or typed in the pane) on the same item in
    the STEER_H hours before, or their own reopen of it in the REOPEN_H before - is steering a long task, not a ball the Advisor dropped
    (the 2026-11-01 audit: 8 of 14 'dropped' were this)."""
    if _v(d['action']) != 'continue': return False
    a = _later(d['at'], -STEER_H)
    if any(o is not d and o['target'] == d['target'] and _v(o['action']) == 'continue' and a <= o['at'] < d['at'] for o in ds): return True
    # ...and the FIRST Continue on a task the owner just reopened: they are driving it (the 2026-11-02 audit)
    if cx.execute("SELECT 1 FROM advice_press WHERE Key=? AND Pressed='reopen' AND CreatedAt>=? AND CreatedAt<? LIMIT 1",
                  (d['key'], _later(d['at'], -REOPEN_H), d['at'])).fetchone(): return True
    return bool(cx.execute(f"SELECT 1 FROM outcome WHERE TargetKind=? AND TargetId=? AND Kind='agent.continued' AND Actor IN ({_in(OWNER)}) AND At>=? AND At<? LIMIT 1",
                           (*d['target'], *OWNER, a, d['at'])).fetchone())


def dropped_balls(cx, ds, steer=False) -> list:
    """The silent decisions the owner answered with Redraft, Stop or Continue, where nothing of the Advisor's had fired on the item - the real
    ones; `steer` instead gives the Continues that were the owner steering work they were already driving."""
    return [d for d in ds if not d['lit'] and _v(d['action']) in DROPPED and not fired(cx, d) and steering(cx, d, ds) == steer]


def three(cx, ds) -> str:
    """precision, coverage and dropped balls, in one line (tools/release.sh prints it beside the agreement line)."""
    p, c, db = precision(ds), coverage(ds), dropped_balls(cx, ds)
    pct = lambda t: f"{t['pct']}%" if t['pct'] is not None else 'n/a'
    on = lambda t: t['right'] + t['wrong']
    return (f"precision {pct(p['all'])} on {on(p['all'])} lit (finish check {pct(p['check'])} on {on(p['check'])}, the rest {pct(p['rest'])} on "
            f"{on(p['rest'])}); silent {pct(c)} of {c['decisions']} decisions; {len(db)} dropped-ball miss{'' if len(db) == 1 else 'es'}"
            + (f" (+{n} steering)" if (n := len(dropped_balls(cx, ds, steer=True))) else ''))


def lit_greyed(ds) -> list:
    """The decisions whose lit button was greyed at one of their presses: the owner was pointed at a button they could not press."""
    return [d for d in ds if d['lit'] and (d['lit'] in d.get('greyed', ()) or _v(d['lit']) in map(_v, d.get('greyed', ())))]


def cause(cx, d) -> str:
    """Who decided a lit button and whether the owner's memory was in it: 'rule' (a state alone, nothing about the owner read), 'model+memory'
    (its line rests on a LEARNED line), 'model' (the model, with no memory line behind it), 'check' (the finish check)."""
    if d['by'] in ('rule', 'check'): return d['by']
    m = model_row(cx, *d['target'], d['rev'], d['lit'])
    return 'model+memory' if m and (m.get('MemorySays') or m.get('Kind') == 'memory') else 'model'


def workstream(cx, d) -> str:
    """The workstream of the item a decision was on (task.Workstream, since the 2026-11-01 workstream slice), '' before it or off a task."""
    if d['target'][0] != 'task': return ''
    try: r = cx.execute('SELECT Workstream FROM task WHERE TaskId=?', (d['target'][1],)).fetchone()
    except sqlite3.OperationalError: return ''
    return (r['Workstream'] if r else '') or ''


def _ids(xs): return ', '.join(f"{d['target'][0]}:{d['target'][1]} #{d['ids'][0]}" for d in xs[:5])    # target ids and press ids only


def _group(ds, f) -> dict:
    g = defaultdict(list)
    for d in ds: g[f(d)].append(d)
    return g


def report(ds, since, replayed=False, cx=None) -> str:
    out = [line(tally(ds), since)]
    def by(f, lit='lit'):
        g = defaultdict(list)
        for d in ds: g[f(d)].append(d)
        rows = []
        for k, v in sorted(g.items(), key=lambda kv: -len(kv[1])):
            t = tally(v, lit)
            rows.append(f"  {k:<30} {'-' if t['pct'] is None else t['pct']:>4}%  {t['right']:>3} right {t['wrong']:>3} wrong {t['unclear']:>3} unclear")
        return rows
    out += ['', 'by lit button (who lit it):'] + by(lambda d: f"{d['lit']} ({d['by']})")
    out += ['', "by rule state ('~' read off the button; the kept decision is only an item's latest):"] + by(lambda d: d['state'])
    if cx is not None:
        out += ['', 'by cause (who decided, and whether a memory line was behind it):'] + by(lambda d: cause(cx, d))
        if any(workstream(cx, d) for d in ds): out += ['', 'by workstream:'] + by(lambda d: workstream(cx, d) or '(none)')
    out += ['', 'top misses (lit, by, state -> what the owner did; e.g. target and first press id):']
    out += [f"  {len(xs):>3}  {lit} ({who}, {st}) -> {act}   e.g. {_ids(xs)}" for (lit, who, st, act), xs in misses(ds)]
    grey = lit_greyed(ds)
    out += ['', f'lit but greyed (the lit button was disabled at a press): {len(grey)}']
    out += [f"  {len(xs):>3}  {lit} ({st})   e.g. {_ids(xs)}" for (lit, st), xs in
            sorted(_group(grey, lambda d: (d['lit'], d['state'].lstrip('~'))).items(), key=lambda kv: -len(kv[1]))]
    if replayed:
        moved = Counter(d['how'] for d in ds if d['how'] not in ('', 'exact', 'model') and d['today'] != d['lit'])
        exact = [d for d in ds if d['how'] == 'exact']
        out += ['', line(tally(ds, 'today'), since, "With today's code (replayed)"),
                f"  exact replays (item unchanged since, today's decide on a copy): {len(exact)}, {sum(d['today'] != d['lit'] for d in exact)} lit differently",
                '  moved by a fix replayed from the record: ' + (', '.join(f'{k} {v}' for k, v in sorted(moved.items())) or 'none')
                + f"; counted unchanged: {sum(1 for d in ds if not d['how'] or d['today'] == d['lit'] and d['how'] != 'exact')}",
                f"  left to a rule then, the model's to read now (not replayable without a model call): {sum(d['how'] == 'model' for d in ds)}",
                '', "misses left with today's code:"]
        out += [f"  {len(xs):>3}  {lit} ({who}, {st}) -> {act}   e.g. {_ids(xs)}" for (lit, who, st, act), xs in misses(ds, 'today')]
    return '\n'.join(out)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--home', default=os.environ.get('TASKUARY_HOME') or os.path.expanduser('~/.taskuary'))
    ap.add_argument('--days', type=float, default=7)
    ap.add_argument('--since', help="a timestamp, e.g. a release's ('2026-10-28 07:03'); overrides --days")
    ap.add_argument('--until', default='9999', help='only presses before this timestamp (a past window, e.g. the one an audit read)')
    ap.add_argument('--replay', action='store_true', help="also score what today's Advisor code would have lit (a backup copy, no model)")
    ap.add_argument('--line', action='store_true', help='print only the agreement line')
    a = ap.parse_args(argv)
    since = a.since or (datetime.now() - timedelta(days=a.days)).strftime('%Y-%m-%d %H:%M:%S')
    cx = connect(a.home)
    every = decisions(cx, since, a.until, silent=True)
    ds = lit(every)
    if a.until != '9999': since = f'{since} until {a.until}'
    if a.line:
        g = len(lit_greyed(ds))
        print(line(tally(ds), since) + (f'; {g} lit but greyed' if g else '') + f'; {three(cx, every)}'); return 0
    if a.replay: replay(cx, ds, copied_store(a.home))
    print(report(ds, since, a.replay, cx))
    db = dropped_balls(cx, every)
    print('\n'.join(['', f'precision, coverage, dropped balls: {three(cx, every)}']
                    + [f"  dropped: {d['target'][0]}:{d['target'][1]} #{d['ids'][0]} - nothing lit, the owner pressed {d['action']} ({d['state']})" for d in db[:8]]))
    return 0


if __name__ == '__main__': sys.exit(main())
