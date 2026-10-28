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
continue typed in the pane) until the item's next decision or two days; else it was walked past.
  right    the owner pressed the lit button (or its twin: Let go is Mark done, Try again is Continue); a reply sent as drafted agrees with
           Send, and with Reply when no draft was on the row yet; one sent in the owner's own words agrees with either
  wrong    the owner did something else - Next counts only when Next was lit
  unclear  walked past with nothing done, a press with no other button to choose
Agreement is right / (right + wrong). A decision nothing was pressed on at all is not in the log, so it is not counted.
A decision whose lit button was GREYED at a press (drawn, but disabled - press log Greyed, since 2026-10-28) is flagged apart: the Advisor
pointed at a button the owner could not press.
"""
import argparse, json, os, sqlite3, sys, tempfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta
from pathlib import Path

TWIN = {'let_go': 'close', 'done': 'close', 'try_again': 'continue'}
NOT_ANSWERS = {'back', 'reopen'}                    # moving about, never a move on the item's decision
OWNER = ('owner', 'you')
ACT = {'task.closed': 'close', 'reply.sent': 'approve', 'agent.continued': 'continue'}   # outcome kinds that are the owner's own acts
HORIZON_H, LOOKBACK_H = 48, 1 / 6
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


def decisions(cx, since: str, until: str = '9999') -> list:
    """The decisions pressed on from `since` to before `until`, oldest first: {key, target, rev, lit, by, state, kind, at, live, presses,
    action, via, ids}. `live` is every button the item's row had (the press log keeps the others; the pressed one is added back)."""
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
        # ...the same answer pressed again on the same screen (a press that seemed not to take) is the same decision
        p = last.get(d['key'])
        if p and d['rev'] and (p['lit'], p['rev'], p['action']) == (d['lit'], d['rev'], d['action']): p['ids'] += d['ids']; return
        out.append(d); last[d['key']] = d
    for p in ps:
        lit = (p.get('Lit') if p.get('Surface') else p.get('Advised')) or ''      # a row before 2026-10-23 is a desk press under a line
        got, key = p['Pressed'], p['Key']
        d = open_.get(key)
        if got in NOT_ANSWERS:
            if d: d['ids'].append(p['Id'])
            continue
        if d and _v(d['lit']) != _v(lit): close(d, 'next', 'walked past', p['CreatedAt'])
        if not lit: continue                                              # nothing lit: no decision of the Advisor's to score
        if key not in open_:
            open_[key] = {'key': key, 'target': (p['TargetKind'], p['TargetId']), 'rev': p.get('Revision') or '', 'lit': lit, 'kind': p.get('ItemKind') or '',
                          'at': p['CreatedAt'], 'live': [], 'greyed': [], 'choice': p.get('Choice') is None or bool(p['Choice']), 'ids': [], 'presses': [],
                          'kept': (p.get('State'), p.get('By'))}        # the decision as kept at the press (since 2026-10-28)
        d = open_[key]
        try: live = json.loads(p.get('Live') or '[]') or []
        except ValueError: live = []
        try: grey = json.loads(p.get('Greyed') or '[]') or []
        except ValueError: grey = []
        d['live'] = list(dict.fromkeys(d['live'] + live + [got]))
        d['greyed'] = list(dict.fromkeys(d['greyed'] + grey))
        d['ids'].append(p['Id']); d['presses'].append(got)
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
        m = None if by else model_row(cx, *d['target'], d['rev'], d['lit'])
        d['by'] = by or ('model' if m and m.get('Model') else 'rule')
        d['state'] = st or _state(cx, d)
    return sorted(out, key=lambda d: (d['at'], d['ids'][0]))


def score(d: dict, lit: str = 'lit') -> str:
    """right, wrong or unclear for one decision, judged by its `lit` field ('lit' as shown, 'today' as replayed)."""
    v, action = _v(d[lit]), d['action']
    if not d.get('choice', True): return 'unclear'      # only one button there: pressing it says nothing
    if action == 'edited': return 'right' if v in ('reply', 'approve') else 'wrong'
    if action == 'sent': return 'right' if v == 'approve' or (v == 'reply' and 'approve' not in d.get('live', ())) else 'wrong'
    if v == _v(action): return 'right'
    return 'unclear' if action == 'next' else 'wrong'


# ── WHAT TODAY'S CODE WOULD HAVE LIT (replay) ─────────────────────────────────────────────────────────────────────────────────────────
# No model is called. Where the item has not changed since (its revision now is the one pressed on), today's advisor.decide runs on a copy
# of the store and reads the recorded model rows at that revision - an exact replay. Elsewhere the store has moved on, so each of today's
# fixes is replayed from what was recorded at the time (the 2026-10-28 audit commit):
#   draft   Reply lit while Send was on the row, its reason anything but a caution about the draft -> Send         (advisor.checked)
#   done    Continue lit on a stopped agent that had left a result or a done note by then -> Mark done           (rulebook.stopped_done)
#   silent  the model's Remind me, or its Reply over Send, with no line -> the rule's button, read off the row    (advisor.decide)
# Not replayable without a model call: the memory budget (How you work read in full) and the hollow-line check change what the model
# READS and which of its lines show; the verbs it would pick with them are unknown. Those decisions are counted unchanged.
def left_result_at(cx, tid, at) -> bool:
    """rulebook.left_result as it stood at `at`: a done note newer than any ready note, a finished event with words no later working event
    took up, or a run that kept a result and was over."""
    n = cx.execute("SELECT Kind FROM boardnote WHERE TaskId=? AND Kind IN ('ready','done') AND CreatedAt<=? ORDER BY NoteId DESC LIMIT 1", (tid, at)).fetchone()
    if n and n['Kind'] == 'done': return True
    def ev(k): return cx.execute("SELECT Id, Text FROM worker_event WHERE TaskId=? AND Kind=? AND CreatedAt<=? ORDER BY Id DESC LIMIT 1", (tid, k, at)).fetchone()
    fin = ev('finished'); work = fin and ev('working')
    if fin and str(fin['Text'] or '').strip() and (not work or work['Id'] < fin['Id']): return True
    r = cx.execute("SELECT Result, Status FROM run WHERE TaskId=? AND IFNULL(StartedAt,'')<=? ORDER BY RunId DESC LIMIT 1", (tid, at)).fetchone()
    return bool(r) and bool(str(r['Result'] or '').strip()) and r['Status'] not in ('failed', 'error', 'running')


def failed_at(cx, tid, at) -> bool:
    r = cx.execute("SELECT Kind FROM worker_event WHERE TaskId=? AND Kind IN ('failed','finished','stopped','working') AND CreatedAt<=? ORDER BY Id DESC LIMIT 1",
                   (tid, at)).fetchone()
    return bool(r) and r['Kind'] == 'failed'


def _rule_verb(d) -> str:
    """The rule's lit button under a model's override, read off the row it was on: Send over a draft, Take it on an idea, Reply to an ask."""
    live = set(d['live'])
    if 'approve' in live: return 'approve'
    if d['kind'] == 'idea' and 'mine' in live: return 'mine'
    if d['kind'] in ('fyi', 'report'): return 'next'
    return 'reply' if 'reply' in live else 'next'


def mirror(cx, d) -> tuple:
    """(the verb today's code lights, the fix that moved it or '') from what was recorded at the decision."""
    lit, (tk, ti), live = d['lit'], d['target'], set(d['live'])
    m = model_row(cx, tk, ti, d['rev'], lit) if d['by'] == 'model' else None
    silent = bool(m) and not str(m.get('Line') or '').strip()
    if lit == 'reply' and 'approve' in live and (not m or m.get('Kind') != 'draft_caution' or silent): return 'approve', 'draft'
    if lit == 'continue' and tk == 'task' and not failed_at(cx, ti, d['at']) and left_result_at(cx, ti, d['at']):
        return ('close' if 'close' in live or not live else 'continue'), 'done'
    if lit == 'defer' and silent: return _rule_verb(d), 'silent'
    return lit, ''


def replay(cx, ds, store=None) -> list:
    """Each decision with `today` (the verb today's code lights) and `how` ('exact', a fix's name, or '' for unchanged)."""
    if store is not None:
        from taskuary import advisor
    for d in ds:
        d['today'], d['how'] = mirror(cx, d)
        if store is None or not d['rev']: continue
        try:
            if advisor.revision(store, *d['target']) != d['rev']: continue
            got = advisor.decide(store, d['key'], preread=False)
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
    return {'decisions': len(ds), 'right': r, 'wrong': w, 'unclear': c['unclear'], 'pct': round(100 * r / (r + w)) if r + w else None}


def line(t: dict, since: str, label='Advisor agreement') -> str:
    pct = f"{t['pct']}%" if t['pct'] is not None else 'n/a'
    return f"{label}: {pct} ({t['right']} right, {t['wrong']} wrong, {t['unclear']} unclear of {t['decisions']} decisions since {since})"


def misses(ds, lit='lit', n=8) -> list:
    """The commonest wrong pairs - (lit, by, state, what the owner did) - each with its decisions."""
    g = defaultdict(list)
    for d in ds:
        if score(d, lit) == 'wrong': g[(d[lit], d['by'], d['state'].lstrip('~'), d['action'])].append(d)
    return sorted(g.items(), key=lambda kv: -len(kv[1]))[:n]


def lit_greyed(ds) -> list:
    """The decisions whose lit button was greyed at one of their presses: the owner was pointed at a button they could not press."""
    return [d for d in ds if d['lit'] and (d['lit'] in d.get('greyed', ()) or _v(d['lit']) in map(_v, d.get('greyed', ())))]


def _ids(xs): return ', '.join(f"{d['target'][0]}:{d['target'][1]} #{d['ids'][0]}" for d in xs[:5])    # target ids and press ids only


def _group(ds, f) -> dict:
    g = defaultdict(list)
    for d in ds: g[f(d)].append(d)
    return g


def report(ds, since, replayed=False) -> str:
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
    out += ['', 'top misses (lit, by, state -> what the owner did; e.g. target and first press id):']
    out += [f"  {len(xs):>3}  {lit} ({who}, {st}) -> {act}   e.g. {_ids(xs)}" for (lit, who, st, act), xs in misses(ds)]
    grey = lit_greyed(ds)
    out += ['', f'lit but greyed (the lit button was disabled at a press): {len(grey)}']
    out += [f"  {len(xs):>3}  {lit} ({st})   e.g. {_ids(xs)}" for (lit, st), xs in
            sorted(_group(grey, lambda d: (d['lit'], d['state'].lstrip('~'))).items(), key=lambda kv: -len(kv[1]))]
    if replayed:
        moved = Counter(d['how'] for d in ds if d['how'] not in ('', 'exact') and d['today'] != d['lit'])
        exact = [d for d in ds if d['how'] == 'exact']
        out += ['', line(tally(ds, 'today'), since, "With today's code (replayed)"),
                f"  exact replays (item unchanged since, today's decide on a copy): {len(exact)}, {sum(d['today'] != d['lit'] for d in exact)} lit differently",
                '  moved by a fix replayed from the record: ' + (', '.join(f'{k} {v}' for k, v in sorted(moved.items())) or 'none')
                + f"; counted unchanged: {sum(1 for d in ds if not d['how'] or d['today'] == d['lit'] and d['how'] != 'exact')}",
                '  not replayable: the memory budget and the hollow-line check (they change what the model reads; no model is called)',
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
    ds = decisions(cx, since, a.until)
    if a.until != '9999': since = f'{since} until {a.until}'
    if a.line:
        g = len(lit_greyed(ds))
        print(line(tally(ds), since) + (f'; {g} lit but greyed' if g else '')); return 0
    if a.replay: replay(cx, ds, copied_store(a.home))
    print(report(ds, since, a.replay))
    return 0


if __name__ == '__main__': sys.exit(main())
