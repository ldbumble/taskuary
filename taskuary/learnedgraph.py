"""LEARNED.md, as a picture: what drives what, and each line's life on one clock.

The document is unusually concrete for a learned profile - every machine-written line carries
`[s:N | ev: id,id | seen: date]` - so it can be drawn instead of read: a line, the verdicts that
fed it (mem/rv/task ids resolve to real rows), its score, and where it sits (live, proposed,
still a hypothesis). What the doc does NOT keep is history: a line that lost a point or died
simply changes or vanishes. `record()` diffs the tagged lines on every machine write
(learn.learn_from, learn.reflect) into `learned_history`, so from now on the ledger can show the
exact verdict that demoted or deleted a line - the thing discussion #27 asked for.
"""
import re
from datetime import datetime

TAG = re.compile(r'^\s*[-*] (?P<text>.*?)\s*\[s:(?P<s>\d+) \| ev: (?P<ev>[^|\]]*)\| seen: (?P<seen>[^\]]*)\]\s*$')
HEADER = re.compile(r'^## (.+?)\s*$')
PROMOTE_AT = 4          # mirrors learn.REFLECT_SYSTEM: s:4 with evidence from 3+ episodes is where a line goes live
_EV = re.compile(r'^(mem|rv|task)(\d+)$')


def _status(header: str) -> str:
    h = (header or '').lower()
    if 'hypothes' in h: return 'hypothesis'
    if 'proposed' in h: return 'proposed'
    if 'verdict' in h: return 'evidence'
    return 'live'


def lines(doc: str) -> list:
    """Every tagged line with its section: [{key, text, section, status, score, ev:[ids], seen}]."""
    out, header = [], ''
    for raw in (doc or '').splitlines():
        h = HEADER.match(raw)
        if h: header = h.group(1); continue
        m = TAG.match(raw)
        if not m or _status(header) == 'evidence': continue
        ev = [e.strip() for e in m.group('ev').split(',') if e.strip()]
        out.append({'key': _key(m.group('text')), 'text': m.group('text').strip(), 'section': header,
                    'status': _status(header), 'score': int(m.group('s')), 'ev': ev, 'seen': m.group('seen').strip()})
    return out


def _key(text: str) -> str:
    """A line's identity across rewrites: the reflection reprases at the margins, so the key is
    the first eight significant words, lowercased."""
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
            if not o: store.add_learned_event(k, l['text'], l['status'], l['score'], ','.join(l['ev']), 'born', actor)
            elif l['score'] != o['score'] or l['status'] != o['status']:
                new_ev = [e for e in l['ev'] if e not in o['ev']]
                act = ('promoted' if l['status'] == 'live' and o['status'] != 'live' else
                       'demoted' if l['score'] < o['score'] else 'strengthened')
                store.add_learned_event(k, l['text'], l['status'], l['score'], ','.join(new_ev), act, actor)
        for k, o in before.items():
            if k not in after: store.add_learned_event(k, o['text'], o['status'], 0, '', 'deleted', actor)
    except Exception:
        pass


def _resolve(store, ev_id: str) -> dict:
    """An evidence id -> {id, kind, date, label}. mem = a verdict note, rv = a review decision,
    task = an owner action on a task."""
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
    r = store.get_task(n) or {}
    return {'id': ev_id, 'kind': 'task', 'date': r.get('UpdatedAt') or r.get('CreatedAt'),
            'label': f"{r.get('Status') or 'task'}: {(r.get('Title') or '')[:90]}" if r else ev_id}


def graph(store) -> dict:
    """What the Visualize view draws. Each line carries its resolved evidence and a step series
    (date, score) reconstructed from the evidence dates - a hypothesis is born at s:2 with its
    first event and gains one per later event - with recorded history laid over it, which is
    where demotions and deletions come from. Deleted lines come from history alone."""
    doc = store.get_doc('learned') or ''
    ls = lines(doc)
    hist = store.learned_history()
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
        out.append({**l, 'evidence': evs, 'steps': steps, 'eligible': l['status'] == 'hypothesis' and l['score'] >= PROMOTE_AT and len(dated) >= 3 and len(people) >= 2})
    live_keys = {l['key'] for l in ls}
    deleted = []
    for k, hs in by_key.items():
        if k in live_keys: continue
        last = hs[-1]
        if last['Action'] != 'deleted': continue
        contradictions = [h for h in hs if h['Action'] == 'demoted']
        deleted.append({'key': k, 'text': last['Text'], 'status': 'deleted', 'score': 0, 'deleted_at': last['At'],
                        'contradictions': [{'date': h['At'], 'ev': h['Ev']} for h in contradictions]})
    used = {e for l in ls for e in l['ev']}
    loose = [{'id': f"mem{m['MemoryId']}", 'kind': 'verdict', 'date': m.get('CreatedAt'), 'label': m.get('Note') or '', 'scope': m.get('Scope'), 'key': m.get('ScopeKey')}
             for m in store.list_memories() if m.get('Source') == 'verdict' and f"mem{m['MemoryId']}" not in used][:12]
    return {'lines': out, 'deleted': deleted, 'loose_evidence': loose, 'soul': soul_rules(store), 'promote_at': PROMOTE_AT,
            'history_since': hist[0]['At'] if hist else None}


def soul_rules(store, limit: int = 5) -> list:
    """The SOUL.md bullets a learned line might lean on or bow to - the first sections' rules."""
    out, header = [], ''
    for raw in (store.doc('soul') or '').splitlines():
        h = HEADER.match(raw)
        if h: header = h.group(1); continue
        if header.lower().startswith(('connected', 'repository')): continue
        if raw.strip().startswith('- ') and len(out) < limit: out.append({'section': header, 'text': raw.strip()[2:].strip()[:160]})
    return out
