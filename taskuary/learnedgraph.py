"""LEARNED.md, as a picture: what drives what, and each line's life on one clock.

The document is unusually concrete for a learned profile - every machine-written line carries
`[s:N | ev: id,id | seen: date | k: key]` - so it can be drawn instead of read: a line, the verdicts
that fed it (mem/rv/task ids resolve to real rows), its score, and where it sits (live, proposed,
still a hypothesis). The `k:` is the line's identity across rewrites, so a reflection rephrasing at
the margins no longer orphans its history; `effective()` is what the score is worth today, since a
line still under test decays rather than keeping forever what it earned once.

That decay is measured in REFLECTIONS, not in days. A calendar punishes a line for the owner
being on holiday: nothing could have confirmed it, so nothing should have cost it (the owner,
2026-09-07: "it will just decay from not being seen"). A reflection is the honest unit - it runs
only when corrections are actually queued (learn.reflect_if_due), and one that read the window
and left a line alone IS a non-confirmation. A quiet funnel runs no reflections and decays nothing.

What the doc does NOT keep is history: a line that lost a point or died simply changes or vanishes. `record()` diffs the tagged lines on every machine write
(learn.learn_from, learn.reflect) into `learned_history`, so from now on the ledger can show the
exact verdict that demoted or deleted a line - the thing discussion #27 asked for.
"""
import re
from datetime import datetime, timedelta

TAG = re.compile(r'^\s*[-*] (?P<text>.*?)\s*\[s:(?P<s>\d+) \| ev: (?P<ev>[^|\]]*)\| seen: (?P<seen>[^|\]]*?)(?: \| k: (?P<k>[^|\]]*?))?\s*\]\s*$')
HEADER = re.compile(r'^## (.+?)\s*$')
PROMOTE_AT = 4          # mirrors learn.REFLECT_SYSTEM: s:4 with evidence from 3+ episodes is where a line goes live
DECAY_EVERY = 10        # reflections that read the evidence and left a line alone, per point off it
DECAYS = ('hypothesis', 'proposed')   # only what is still a guess: a promoted rule earned its s, an adopted one is the owner's
LOG, LOG_KEEP = 'learn_reflect_log', 200   # the dates reflections ran on; 200 is 20 points of decay, past any live score
_EV = re.compile(r'^(mem|rv|task|out|pr|msg|fs|sv|idea)(\d+)$')


def _today(): return datetime.now().strftime('%Y-%m-%d')


def reflect_log(store, add: str = None) -> list:
    """The dates the reflections actually ran on - the clock decay is measured against. Passing a
    date records one. Capped: a line older than every date we still hold counts as fully quiet,
    which is the right answer for one nothing has confirmed in two hundred reflections."""
    log = [d for d in str(store.get_setting(LOG) or '').split(',') if d.strip()]
    if add:
        log = (log + [add])[-LOG_KEEP:]
        store.set_setting(LOG, ','.join(log), 'reflect')
    return log


def _quiet(seen: str, log) -> int:
    """How many points a line has lost: one per DECAY_EVERY reflections that ran AFTER the last
    thing that confirmed it. No log (a caller that has no store) means no decay - a line is never
    killed by a clock nobody supplied."""
    return len([d for d in (log or []) if d > (seen or '').strip()]) // DECAY_EVERY


def effective(l: dict, log=None) -> int:
    """The strength a line has actually earned: what its tag says, less what the quiet cost it.
    Without this an s:N only ever moves on evidence, so a pattern that quietly stopped holding
    keeps the score it earned when it did - absence of evidence lowers nothing by itself."""
    return l['score'] if l['status'] not in DECAYS else max(0, l['score'] - _quiet(l['seen'], log))


def fmt(l: dict) -> str:
    """A parsed line back to its bullet, always with the k: that makes it the same line tomorrow."""
    return f"- {l['text']} [s:{l['score']} | ev: {', '.join(l['ev'])} | seen: {l['seen']} | k: {l['key']}]"


def _status(header: str) -> str:
    h = (header or '').lower()
    if 'hypothes' in h or 'watching' in h: return 'hypothesis'      # "Watching" is the hypotheses block's name since phase C
    if 'proposed' in h: return 'proposed'
    if 'verdict' in h: return 'evidence'
    return 'live'


def _parse(m, header: str) -> dict:
    return {'key': (m.group('k') or '').strip() or _key(m.group('text')), 'text': m.group('text').strip(),
            'section': header, 'status': _status(header), 'score': int(m.group('s')),
            'ev': [e.strip() for e in m.group('ev').split(',') if e.strip()], 'seen': m.group('seen').strip()}


def walk(doc: str):
    """(raw line, its parsed tag or None) for the whole document - the writable twin of lines(),
    for the passes that rewrite it in place and must leave everything untagged byte-for-byte."""
    header = ''
    for raw in (doc or '').splitlines():
        h = HEADER.match(raw)
        if h: header = h.group(1); yield raw, None; continue
        m = TAG.match(raw)
        yield raw, (_parse(m, header) if m and _status(header) != 'evidence' else None)


def lines(doc: str) -> list:
    """Every tagged line with its section: [{key, text, section, status, score, ev:[ids], seen}]."""
    return [l for _, l in walk(doc) if l]


def _key(text: str) -> str:
    """The identity of a line whose tag carries no k: yet - the docs that predate the field, and
    whatever the model writes fresh. The first eight significant words, lowercased; learn.settle
    stamps the result into the line so a later rephrase cannot move it again."""
    words = [w for w in re.findall(r'[a-z0-9]+', text.lower()) if len(w) > 3][:8]
    return ' '.join(words)


def record(store, old_doc: str, new_doc: str, actor: str = 'learn'):
    """Diff the tagged lines and write what changed - a point gained, a point lost, a promotion
    (section changed), a line that died. Never raises; a missed history row costs a dot on a chart."""
    try:
        before = {l['key']: l for l in lines(old_doc)}
        after = {l['key']: l for l in lines(new_doc)}
        for k, l in after.items():
            o = before.get(k)
            # a key the history already knows came BACK - never born twice: the rebirth was the opener's "Learned this week: 32"
            if not o: store.add_learned_event(k, l['text'], l['status'], l['score'], ','.join(l['ev']), 'back' if store.learned_history(k) else 'born', actor)
            elif l['score'] != o['score'] or l['status'] != o['status']:
                new_ev = [e for e in l['ev'] if e not in o['ev']]
                act = ('promoted' if l['status'] == 'live' and o['status'] != 'live' else
                       'demoted' if l['score'] < o['score'] else 'strengthened')
                store.add_learned_event(k, l['text'], l['status'], l['score'], ','.join(new_ev), act, actor)
        # a line that went because nothing confirmed it for long enough FADED (learn.settle drops it at effective 0); one that was
        # simply removed - by the owner, or by a reflection that rewrote it away - was deleted. The history says which.
        log = reflect_log(store)
        ended = {r['Key'] for r in store._rows("SELECT Key FROM learned_line WHERE Status IN ('closed','retired','forgotten','wrong')")}   # its history says so already
        for k, o in before.items():
            if k not in after and k not in ended: store.add_learned_event(k, o['text'], o['status'], 0, '', 'faded' if effective(o, log) <= 0 else 'deleted', actor)
    except Exception:
        pass


def _resolve(store, ev_id: str) -> dict:
    """An evidence id -> {id, kind, date, label}. mem = a verdict note, rv = a review decision,
    task = an owner action on a task, out = a resolved row of the outcome ledger (outcomes.py)."""
    m = _EV.match(ev_id or '')
    if not m: return {'id': ev_id, 'kind': 'other', 'date': None, 'label': ev_id}
    kind, n = m.group(1), int(m.group(2))
    if kind == 'mem':
        r = next((x for x in store.list_memories(active_only=False) if x['MemoryId'] == n), None)
        return {'id': ev_id, 'kind': 'verdict', 'date': (r or {}).get('CreatedAt'), 'label': (r or {}).get('Note') or ev_id,
                'scope': (r or {}).get('Scope'), 'key': (r or {}).get('ScopeKey')}
    if kind == 'rv':
        r = store.get_review(n) or {}
        return {'id': ev_id, 'kind': 'review', 'date': r.get('DecidedAt') or r.get('CreatedAt'),
                'label': f"{r.get('Status') or 'review'}: {(r.get('Subject') or r.get('Title') or '')[:90]}" if r else ev_id}
    if kind == 'pr':                       # a press: no line is learned from one any more (2026-10-25), but a retired line still cites it
        r = store._one('SELECT * FROM advice_press WHERE Id=?', (n,)) or {}
        return {'id': ev_id, 'kind': 'press', 'date': r.get('CreatedAt'),
                'label': f"pressed {r.get('Pressed')} on an item from {r.get('Scope') or '?'}" if r else ev_id}
    if kind == 'msg':                      # an inbound message the owner answered (episodes.py)
        r = store.get_message(n) or {}
        return {'id': ev_id, 'kind': 'message', 'date': r.get('SentAt'),
                'label': f"from {r.get('FromName') or r.get('FromEmail')}: {(r.get('Subject') or '')[:90]}" if r else ev_id}
    if kind == 'fs':                       # a task the owner put off, and to when
        r = store.get_task(n) or {}
        return {'id': ev_id, 'kind': 'deferred', 'date': r.get('UpdatedAt') or r.get('CreatedAt'),
                'label': f"put off to {str(r.get('RemindAt') or '?')[:16]}: {(r.get('Title') or '')[:90]}" if r else ev_id}
    if kind == 'sv':                       # a promise in the owner's sent mail (sentjudge.py)
        r = store.sent_verdict(n) or {}
        return {'id': ev_id, 'kind': 'promise', 'date': (store.get_message(n) or {}).get('SentAt'),
                'label': f"you promised {r.get('What') or 'something'}" + (f" by {r['Due']}" if r.get('Due') else '') if r else ev_id}
    if kind == 'idea':                     # an Advisor idea and what the owner did with it
        r = store._one('SELECT * FROM idea WHERE IdeaId=?', (n,)) or {}
        return {'id': ev_id, 'kind': 'idea', 'date': r.get('DecidedAt') or r.get('LastSaid'),
                'label': f"{r.get('Status') or 'idea'}: {(r.get('Text') or '')[:90]}" if r else ev_id}
    if kind == 'out':
        r = store._one('SELECT * FROM outcome WHERE Id=?', (n,)) or {}
        return {'id': ev_id, 'kind': 'outcome', 'date': r.get('ResolvedAt') or r.get('At'),
                'label': f"{r.get('Verdict') or 'outcome'}: {r.get('Kind')} - {(r.get('Outcome') or '')[:90]}" if r else ev_id}
    r = store.get_task(n) or {}
    return {'id': ev_id, 'kind': 'task', 'date': r.get('UpdatedAt') or r.get('CreatedAt'),
            'label': f"{r.get('Status') or 'task'}: {(r.get('Title') or '')[:90]}" if r else ev_id}


def resolves(store, ev_id: str) -> bool:
    """Does this evidence id name a real row? A line citing one that does not is a line the model made up (learn._books)."""
    m = _EV.match(ev_id or '')
    if not m: return False
    kind, n = m.group(1), int(m.group(2))
    q = {'mem': 'SELECT 1 FROM memory WHERE MemoryId=?', 'rv': 'SELECT 1 FROM review WHERE ReviewId=?', 'task': 'SELECT 1 FROM task WHERE TaskId=?',
         'fs': 'SELECT 1 FROM task WHERE TaskId=?', 'out': 'SELECT 1 FROM outcome WHERE Id=?', 'pr': 'SELECT 1 FROM advice_press WHERE Id=?',
         'msg': 'SELECT 1 FROM message WHERE MessageId=?', 'sv': 'SELECT 1 FROM sent_verdict WHERE MessageId=?', 'idea': 'SELECT 1 FROM idea WHERE IdeaId=?'}[kind]
    try: return bool(store._one(q, (n,)))
    except Exception: return False


def graph(store) -> dict:
    """What the Visualize view draws. Each line carries its resolved evidence and a step series
    (date, score) reconstructed from the evidence dates - a hypothesis is born at s:2 with its
    first event and gains one per later event - with recorded history laid over it, which is
    where demotions and deletions come from. Deleted lines come from history alone."""
    doc = store.get_doc('learned') or ''
    ls, log = lines(doc), reflect_log(store)
    hist, named = store.learned_history(), _named(store)
    from .learnedlines import section_of, rows as line_rows
    from .learned_cut import over_budget, readers_of
    rows, over = {r['Key']: r for r in line_rows(store)}, over_budget(store)
    by_key = {}
    for h in hist: by_key.setdefault(h['Key'], []).append(h)
    out = []
    for l in ls:
        evs = [_resolve(store, e) for e in l['ev']]
        dated = sorted([e for e in evs if e.get('date')], key=lambda e: e['date'])
        steps, s = [], 1
        for e in dated:
            s = 2 if s < 2 else s + 1
            steps.append({'date': e['date'], 'score': s, 'ev': e['id'], 'effect': +1})
        for h in by_key.get(l['key'], []):
            if h['Action'] in ('demoted', 'deleted'):
                steps.append({'date': h['At'], 'score': h['Score'], 'ev': h['Ev'] or None, 'effect': -1, 'action': h['Action']})
            elif h['Action'] == 'promoted':
                steps.append({'date': h['At'], 'score': h['Score'], 'ev': None, 'effect': 0, 'action': 'promoted'})
        steps.sort(key=lambda x: x['date'] or '')
        if steps and steps[-1]['score'] != l['score']: steps.append({'date': None, 'score': l['score'], 'ev': None, 'effect': 0, 'action': 'now'})
        people = {(e.get('key') or e.get('label') or '')[:40] for e in evs if e.get('kind') == 'verdict'}
        eff = effective(l, log)
        r = rows.get(l['key']) or {}
        # ...and its standing in the line store (learnedlines, phase C): who reads it, watching or in use, whether the reader's
        # budget left it out - the data the memory list's Keep / Wrong / Forget (phase D) hangs on
        out.append({**l, 'text': named(l.get('text')), 'evidence': evs, 'steps': steps, 'effective': eff,
                    'eligible': l['status'] == 'hypothesis' and eff >= PROMOTE_AT and len(dated) >= 3 and len(people) >= 2,
                    'reads': ', '.join(readers_of(section_of(l))), 'section_slug': section_of(l), 'standing': r.get('Status') or ('in_use' if l['status'] == 'live' else 'watching'),
                    'in_use_at': r.get('InUseAt'), 'over_budget': over.get(l['key'], [])})
    live_keys = {l['key'] for l in ls}
    deleted = []
    for k, hs in by_key.items():
        if k in live_keys: continue
        last = hs[-1]
        if last['Action'] != 'deleted': continue
        contradictions = [h for h in hs if h['Action'] == 'demoted']
        deleted.append({'key': k, 'text': named(last['Text']), 'status': 'deleted', 'score': 0, 'deleted_at': last['At'],
                        'contradictions': [{'date': h['At'], 'ev': h['Ev']} for h in contradictions]})
    used = {e for l in ls for e in l['ev']}
    loose = [{'id': f"mem{m['MemoryId']}", 'kind': 'verdict', 'date': m.get('CreatedAt'), 'label': m.get('Note') or '', 'scope': m.get('Scope'), 'key': m.get('ScopeKey')}
             for m in store.list_memories() if m.get('Source') == 'verdict' and f"mem{m['MemoryId']}" not in used][:12]
    # THE OWNER'S OWN LINES, beside what was learned (slice 6, 2026-10-25): what they typed - or a person's page gave - is in use as written
    from .learned_cut import SECTIONS, lines as section_lines, subject_of, reads_label, TITLE
    own = [{'key': k, 'text': named(raw.strip()[2:].strip() if raw.strip().startswith(('- ', '* ')) else raw.strip()), 'own': True, 'status': 'live',
            'section_slug': slug, 'subject': subject_of(raw), 'evidence': [], 'steps': [], 'score': None, 'effective': None, 'seen': ''}
           for slug, head in SECTIONS.items() for raw, k in section_lines(doc, head) if not TAG.match(raw)]
    for l in out: l['subject'] = subject_of(l.get('text'))
    from .capabilities import has_ai
    return {'lines': out + own, 'deleted': deleted, 'loose_evidence': loose, 'soul': soul_rules(store), 'promote_at': PROMOTE_AT,
            'history_since': hist[0]['At'] if hist else None, 'ai': has_ai(store),
            # each subject with who reads it, in the reader matrix's own words (learned_cut.READS) - never "rides into every prompt"
            'sections': [{'slug': s, 'title': TITLE[s], 'reads': reads_label(s)} for s in SECTIONS]}


def soul_rules(store, limit: int = 5) -> list:
    """The SOUL.md bullets a learned line might lean on or bow to - the first sections' rules."""
    out, header = [], ''
    for raw in (store.doc('soul') or '').splitlines():
        h = HEADER.match(raw)
        if h: header = h.group(1); continue
        if header.lower().startswith(('connected', 'repository')): continue
        if raw.strip().startswith('- ') and len(out) < limit: out.append({'section': header, 'text': raw.strip()[2:].strip()[:160]})
    return out


# WHAT CHANGED, as sentences (the LEARNED.md "What changed" view): the history the Visualize chart draws as dots, read as a list -
# what was learned, what grew stronger, what merged into what, what faded for want of evidence (the row-bot comparison, 2026-10-07)
SAYS = {'born': 'New guess', 'strengthened': 'Seen again', 'promoted': 'Now a rule', 'demoted': 'Weaker',
        'merged': 'Merged into a line that says the same', 'faded': 'Faded - nothing confirmed it for a while', 'deleted': 'Removed',
        'back': 'Back', 'edited': 'Reworded by you', 'forgotten': 'Removed by you - stays removed', 'withdrawn': 'Withdrawn - its note was switched off',
        'watching': 'Back to watching', 'moved': 'Moved to STYLE.md - the drafter reads it there',
        'retired': 'Retired - a count of button presses, not how you work', 'closed': 'No longer true - kept as history',
        'kept': 'Kept by you - in your words from now on', 'wrong': 'Wrong, you said - never written back', 'said': 'Said by you'}


def _named(store):
    """A line as the owner reads it: LEARNED.md keeps {{owner_first}} where the name goes (the passes write it so), and the
    What changed list showed "{{owner_first}} presses Next" raw (the UI audit, 2026-10-21)."""
    from .store import render_doc
    who = store.owner()
    return lambda text: render_doc(text, who)


def changes(store, days: int = 30) -> list:
    """The history of the last `days`, newest first: [{at, action, says, text, status, score}]."""
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows, named = [h for h in store.learned_history() if str(h.get('At') or '') >= since], _named(store)
    # ...each with its key and where the line stands now, so What changed can carry Keep / Wrong / Forget on the newest row of a line
    # (the owner's ruling 2, 2026-10-23) and none on a line already put down
    from .learnedlines import rows as line_rows
    from .memoryedit import find
    st, seen, out, doc = {r['Key']: r.get('Status') for r in line_rows(store)}, set(), [], store.get_doc('learned') or ''
    # a key with no row is an owner's own line: 'own' while it is still in the document (Forget alone), else 'gone' (nothing to press)
    standing = lambda k: st.get(k) or ('own' if find(doc, k)[2] else 'gone')
    for h in reversed(rows):
        newest = h['Key'] not in seen; seen.add(h['Key'])
        out.append({'at': h['At'], 'action': h['Action'], 'says': SAYS.get(h['Action'], h['Action']), 'text': named(h['Text']),
                    'status': h['Status'], 'score': h['Score'], 'key': h['Key'], 'standing': standing(h['Key']), 'newest': newest})
    return out

