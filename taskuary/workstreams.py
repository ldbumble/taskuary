"""WORKSTREAMS - the owner's separate bodies of work (the design 2026-11-01, docs/superpowers/specs/2026-11-01-advisor-understands-the-owner-design.md).

Someone who runs a day job, a side product with a small team and a personal life over the same apps was judged by the day job's norms
everywhere: one flat JOB.md, one title, one company, and nothing that said which hat a mail, a task, an idea or a memory line was under.

A workstream has a name, a one-line `about`, and the signals that place an item in it - the people in it, their domains, the mailboxes
and chat groups it runs on, its repositories. The list is kept in the `workstreams` setting (machine-owned: the bootstrap, the owner's
picker and the Advisor's cards write it); JOB.md carries what a model reads about each - an index and one marked section per
workstream (`<!-- ws:<slug>:start -->` ... `<!-- ws:<slug>:end -->`), the owner's own lines outside the markers surviving as always.
One workstream may be PERSONAL: it is never learned from and never raised (the owner, 2026-11-01: personal asks are FYI).

Placing an item reads the strongest signal first: the thread it is on, then the mailbox or chat group (only one that serves a single
workstream decides), the repository, the people on it, their domain - and else triage's model, which has the list and says which, or
nothing when unsure."""
import json, re
from collections import Counter

KEY = 'workstreams'
SIGNALS = ('people', 'domains', 'mailboxes', 'channels', 'repos')
INDEX_START, INDEX_END = '<!-- workstreams:start -->', '<!-- workstreams:end -->'
def start(slug): return f'<!-- ws:{slug}:start -->'
def end(slug): return f'<!-- ws:{slug}:end -->'
def slugify(name: str) -> str: return re.sub(r'[^a-z0-9]+', '-', str(name or '').lower()).strip('-')[:40] or 'work'
def _low(xs): return [str(x).strip().lower() for x in xs or () if str(x).strip()]


def _norm(w: dict) -> dict:
    name = ' '.join(str(w.get('name') or '').split()) or 'Work'
    out = {'slug': w.get('slug') or slugify(name), 'name': name, 'about': ' '.join(str(w.get('about') or '').split())[:240],
           'personal': bool(w.get('personal')), 'status': w.get('status') or 'active'}
    return out | {k: list(dict.fromkeys(_low(w.get(k)))) for k in SIGNALS}


def streams(store, every: bool = False) -> list:
    """The owner's workstreams, as kept - active and quiet ones; `every` adds the proposed ones the owner has not confirmed."""
    try: xs = json.loads(store.get_setting(KEY) or '[]') or []
    except ValueError: xs = []
    xs = [_norm(x) for x in xs if isinstance(x, dict)]
    return xs if every else [x for x in xs if x['status'] != 'proposed']


def get(store, slug: str) -> dict | None: return next((w for w in streams(store, True) if w['slug'] == slug), None)
def names(store) -> dict: return {w['slug']: w['name'] for w in streams(store, True)}
def personal(store) -> set: return {w['slug'] for w in streams(store, True) if w['personal']}


def save(store, xs: list, actor: str = 'workstreams'):
    xs = [_norm(x) for x in xs]
    seen, out = set(), []
    for w in xs:                                   # one slug, one workstream
        if w['slug'] in seen: continue
        seen.add(w['slug']); out.append(w)
    store.set_setting(KEY, json.dumps(out), actor)
    write_job(store, actor)
    return out


def upsert(store, w: dict, actor: str = 'workstreams') -> dict:
    """Add a workstream, or merge signals into the one with its slug (the owner's name and about win over a machine's)."""
    w = _norm(w)
    xs, hit = streams(store, True), None
    for x in xs:
        if x['slug'] == w['slug']:
            hit = x
            for k in SIGNALS: x[k] = list(dict.fromkeys(x[k] + w[k]))
            if w['about'] and not x['about']: x['about'] = w['about']
            if w['status'] == 'active': x['status'] = 'active'
            x['personal'] = x['personal'] or w['personal']
    if not hit: xs.append(w)
    save(store, xs, actor)
    return get(store, w['slug'])


def remove(store, slug: str, actor: str = 'owner'):
    save(store, [w for w in streams(store, True) if w['slug'] != slug], actor)


# ── PLACING AN ITEM ───────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _addresses(m: dict) -> list:
    """The people on a message other than the owner's own mailbox: who wrote it, or who it went to when the owner wrote it."""
    if (m.get('Direction') or 'in') == 'out':
        try: rs = json.loads(m.get('RecipientsJson') or '[]') or []
        except ValueError: rs = []
        return _low((r.get('email') if isinstance(r, dict) else r) for r in rs)
    return _low([m.get('FromEmail')])


def _one(hits: list) -> str:
    """The workstream most signals name, when exactly one leads; '' on a tie or nothing."""
    c = Counter(h for h in hits if h).most_common(2)
    return c[0][0] if c and (len(c) == 1 or c[0][1] > c[1][1]) else ''


def by_signals(xs: list, m: dict) -> tuple:
    """(slug, why) from the message's own signals, strongest first; ('', '') when none decides."""
    src, ch = str(m.get('SourceName') or '').strip().lower(), str(m.get('Channel') or '').strip().lower()
    def only(k, v):
        ws = [w['slug'] for w in xs if v and v in w[k]]
        return ws[0] if len(ws) == 1 else ''
    conv = str(m.get('ConversationId') or '').strip().lower()
    for k, v, why in (('channels', conv, 'chat'), ('channels', f'{ch}:{src}', 'chat group'), ('mailboxes', src, 'mailbox'), ('repos', src, 'repository')):
        if (s := only(k, v)): return s, why
    people = _addresses(m)
    if (s := _one([w['slug'] for a in people for w in xs if a in w['people']])): return s, 'people'
    if (s := _one([w['slug'] for a in people for w in xs if a.split('@')[-1] in w['domains']])): return s, 'domain'
    return '', ''


def of_message(store, m: dict) -> str:
    """The workstream of one message: its own if stamped, else the thread's, else its signals. '' when nothing decides."""
    if m.get('Workstream'): return m['Workstream']
    xs = streams(store)
    if not xs: return ''
    if m.get('ConversationId'):
        r = store._one("SELECT Workstream FROM message WHERE ConversationId=? AND IFNULL(Workstream,'')<>'' ORDER BY MessageId DESC LIMIT 1",
                       (m['ConversationId'],))
        if r and r['Workstream'] in {w['slug'] for w in xs}: return r['Workstream']
    return by_signals(xs, m)[0]


def stamp_message(store, mid: int, slug: str = None) -> str:
    """Write the message's workstream (the given one - triage's or the owner's - else its signals). Returns it."""
    m = store.get_message(mid)
    if not m: return ''
    s = slug if slug is not None else of_message(store, {**m, 'Workstream': ''})
    if s and s != (m.get('Workstream') or ''): store._exec('UPDATE message SET Workstream=? WHERE MessageId=?', (s, mid))
    return s


def of_task(store, tid: int) -> str:
    """The task's workstream: its own once set (the owner's pick always), else what its messages say - written on the task then."""
    t = store.get_task(tid)
    if not t: return ''
    if t.get('Workstream'): return t['Workstream']
    if not streams(store): return ''
    for m in store._rows('SELECT * FROM message WHERE TaskId=? ORDER BY MessageId', (tid,)):
        if (s := of_message(store, m)):
            store._exec("UPDATE task SET Workstream=? WHERE TaskId=? AND IFNULL(Workstream,'')=''", (s, tid))
            return s
    return ''


def set_task(store, tid: int, slug: str, actor: str = 'owner') -> dict:
    """The owner moves a task to a workstream (the task's picker, or Wrong here): the task, its messages and its ideas follow, and the
    people on it are placed there from now on - the correction teaches the map, never a rule about words."""
    t = store.get_task(tid)
    if not t: raise ValueError(f'no task {tid}')
    slug = slug or ''
    if slug and not get(store, slug): raise ValueError(f'no workstream {slug}')
    was = t.get('Workstream') or ''
    store._exec('UPDATE task SET Workstream=? WHERE TaskId=?', (slug, tid))
    store._exec('UPDATE message SET Workstream=? WHERE TaskId=?', (slug, tid))
    store._exec("UPDATE idea SET Workstream=? WHERE json_extract(ActionJson,'$.tid')=?", (slug, tid))
    if slug and actor == 'owner':
        people = {a for m in store._rows('SELECT * FROM message WHERE TaskId=?', (tid,)) for a in _addresses(m)} - _owner_addresses(store)
        xs = streams(store, True)
        for w in xs:
            if w['slug'] == slug: w['people'] = list(dict.fromkeys(w['people'] + sorted(people)))
            elif w['slug'] == was: w['people'] = [p for p in w['people'] if p not in people]
        save(store, xs, actor)
    store.audit('task', tid, 'set_workstream', actor, detail={'from': was, 'to': slug})
    if hasattr(store, '_poke'): store._poke('task-changed', task_id=tid)
    return {'taskId': tid, 'workstream': slug, 'was': was}


def _owner_addresses(store) -> set:
    from .ingest import own_addresses, owner_addresses
    return set(_low(own_addresses(store) | owner_addresses(store)))


# ── PERSONAL IS NEVER LEARNED FROM (the owner, 2026-10-23 and 2026-11-01: personal asks are FYI, never learned from) ─────────────────────
def is_personal(store, tid=None, mid=None, src: str = None, m: dict = None) -> bool:
    """Whether a task, a message, or an evidence id (msg12, task7, idea3, rv4, sv9, out5, fs7) is under a personal workstream."""
    ps = personal(store)
    if not ps: return False
    if src:
        hit = re.match(r'^([a-z]+)(\d+)$', str(src))
        k, n = (hit.group(1), int(hit.group(2))) if hit else ('', None)
        if k in ('msg', 'sv') and n: mid = n
        elif k in ('task', 'fs') and n: tid = n
        elif k == 'idea' and n:
            i = store._one('SELECT Workstream, ActionJson FROM idea WHERE IdeaId=?', (n,)) or {}
            if i.get('Workstream') in ps: return True
            try: a = json.loads(i.get('ActionJson') or '{}') or {}
            except ValueError: a = {}
            tid, mid = a.get('tid'), a.get('mid')
        elif k == 'rv' and n:
            r = store._one('SELECT TaskId, MessageId FROM review WHERE ReviewId=?', (n,)) or {}
            tid, mid = r.get('TaskId'), r.get('MessageId')
        elif k == 'out' and n:
            r = store._one('SELECT TargetKind, TargetId FROM outcome WHERE Id=?', (n,)) or {}
            if r.get('TargetKind') == 'task': tid = r.get('TargetId')
    if m is None and mid:
        try: m = store.get_message(int(mid))
        except (TypeError, ValueError): m = None
    if m:
        if of_message(store, m) in ps: return True
        if not tid and m.get('TaskId'): tid = m['TaskId']
    if tid:
        try: return of_task(store, int(tid)) in ps
        except (TypeError, ValueError): return False
    return False


def of_evidence(store, ids) -> str:
    """The workstream a learned line was learned under: the one most of its evidence (msg12, task7, rv4, ...) is placed in, when one
    leads; '' when the evidence is spread across hats or unplaced - such a line is everyone's."""
    if not streams(store): return ''
    hits = []
    for e in ids or ():
        m = re.match(r'^([a-z]+)(\d+)$', str(e).strip())
        if not m: continue
        k, n = m.group(1), int(m.group(2))
        try:
            if k in ('msg', 'sv'): hits.append(of_message(store, store.get_message(n) or {}))
            elif k in ('task', 'fs'): hits.append(of_task(store, n))
            elif k == 'rv': hits.append(of_task(store, (store._one('SELECT TaskId FROM review WHERE ReviewId=?', (n,)) or {}).get('TaskId') or 0))
            elif k == 'idea': hits.append((store._one('SELECT Workstream FROM idea WHERE IdeaId=?', (n,)) or {}).get('Workstream') or '')
            elif k == 'out':
                r = store._one('SELECT TargetKind, TargetId FROM outcome WHERE Id=?', (n,)) or {}
                if r.get('TargetKind') == 'task': hits.append(of_task(store, r['TargetId']))
        except Exception: continue
    return _one(hits)


def tag_lines(store) -> int:
    """Write each machine line's workstream (learned_line.Workstream) from its evidence; a people line's own subject decides first.
    Returns how many changed. Readers leave out the lines of another hat (learned_cut.for_reader)."""
    if not streams(store): return 0
    xs, n = streams(store), 0
    for r in store._rows("SELECT Key, Ev, Subject, Workstream FROM learned_line WHERE Status IN ('in_use','watching')"):
        ws = (by_signals(xs, {'FromEmail': r['Subject']})[0] if r.get('Subject') else '') or \
             of_evidence(store, [e.strip() for e in str(r.get('Ev') or '').split(',') if e.strip()])
        if ws != (r.get('Workstream') or ''):
            store._exec('UPDATE learned_line SET Workstream=? WHERE Key=?', (ws, r['Key'])); n += 1
    return n


def label(store, slug: str) -> dict | None:
    """What a screen shows beside an item: {slug, name, personal} - None when it has no workstream."""
    w = get(store, slug) if slug else None
    return {'slug': w['slug'], 'name': w['name'], 'personal': w['personal']} if w else None


# ── JOB.md: AN INDEX AND ONE SECTION PER WORKSTREAM ───────────────────────────────────────────────────────────────────────────────────
def index_text(xs: list) -> str:
    rows = [f"- **{w['name']}**" + (f" - {w['about']}" if w['about'] else '') + (' (personal: never learned from)' if w['personal'] else '')
            + (' (quiet)' if w['status'] == 'quiet' else '') for w in xs]
    return '## My workstreams\n' + ('\n'.join(rows) if rows else '- (none yet)')


def splice(doc: str, a: str, b: str, body: str, append: bool = True) -> str:
    """`doc` with the block between markers a..b replaced by body (markers kept); appended at the end when absent and `append`."""
    block = f'{a}\n{body.strip()}\n{b}'
    if a in doc and b in doc:
        head, rest = doc.split(a, 1)
        return head + block + rest.split(b, 1)[1]
    return (doc.rstrip() + '\n\n' + block + '\n') if append else doc


def section(store, slug: str) -> str:
    """The workstream's own section of JOB.md as written (comments stripped), '' when it has none."""
    doc = store.doc('job') or ''
    if start(slug) not in doc or end(slug) not in doc: return ''
    return re.sub(r'<!--.*?-->', '', doc.split(start(slug), 1)[1].split(end(slug), 1)[0], flags=re.S).strip()


def write_section(store, slug: str, body: str, actor: str = 'workstreams'):
    """Replace one workstream's section (the bootstrap and the weekly refresh write here; the owner edits it in Docs)."""
    w = get(store, slug)
    if not w: raise ValueError(f'no workstream {slug}')
    body = body.strip()
    if not body.startswith('### '): body = f"### {w['name']}\n{body}"
    store.save_doc('job', splice(store.get_doc('job') or '', start(slug), end(slug), body), actor)


def write_job(store, actor: str = 'workstreams'):
    """The index block, and a section skeleton for every non-personal workstream that has none (never overwriting a written one)."""
    xs = streams(store)
    doc = store.get_doc('job') or ''
    new = splice(doc, INDEX_START, INDEX_END, index_text(xs))
    for w in xs:
        if w['personal'] or start(w['slug']) in new: continue
        new = splice(new, start(w['slug']), end(w['slug']), f"### {w['name']}\n" + (f"- {w['about']}" if w['about'] else '- (what this work is, and my role in it)'))
    if new != doc: store.save_doc('job', new, actor)


# ── WHAT EACH READER GETS (the design's S4: readers get the item's workstream, not the first 600 characters of everything) ─────────────
_SECTION = re.compile(r'<!-- ws:([a-z0-9-]+):start -->(.*?)<!-- ws:\1:end -->', re.S)


def _clean(t: str) -> str: return re.sub(r'\n{3,}', '\n\n', re.sub(r'<!--.*?-->', '', t, flags=re.S)).strip()


def job_view(store, keep: str = None) -> str:
    """JOB.md as an item under workstream `keep` reads it: the index, the owner's own lines, and that workstream's section - the other
    workstreams' sections left out, since a day-job colleague's norms are noise on a side product's task. `keep` None: all of it."""
    doc = store.doc('job') or ''
    if keep is not None: doc = _SECTION.sub(lambda m: m.group(0) if m.group(1) == keep else '', doc)
    return _clean(doc)


def job_brief(store, per: int = 600, limit: int = None) -> str:
    """JOB.md for a reader that serves every workstream (triage, the memory's reflection): the index and each section, cut to `per`
    characters, FIRST - so a cut at `limit` never drops a second workstream - and then the rest of the document."""
    doc = store.doc('job') or ''
    secs = [(m.group(1), _clean(m.group(2))) for m in _SECTION.finditer(doc)]
    idx = _clean(doc.split(INDEX_START, 1)[1].split(INDEX_END, 1)[0]) if INDEX_START in doc and INDEX_END in doc else ''
    rest = _SECTION.sub('', doc)
    if INDEX_START in rest and INDEX_END in rest: rest = rest.split(INDEX_START, 1)[0] + rest.split(INDEX_END, 1)[1]
    head = '\n\n'.join([idx] + [s[:per] for _, s in secs if s]) if (idx or secs) else ''
    out = '\n\n'.join(x for x in (head, _clean(rest)) if x)
    return out[:limit] if limit else out


def menu(store) -> str:
    """The workstreams as triage is shown them: one line each, its slug first - the model names one, or null."""
    return '\n'.join(f"- {w['slug']}: {w['name']}" + (f" - {w['about']}" if w['about'] else '') + (' (personal)' if w['personal'] else '')
                     for w in streams(store))


def from_menu(answer, shown: str) -> str:
    """A slug triage answered, only if it was one it was shown."""
    s = str(answer or '').strip().lower()
    return s if s and re.search(rf'^- {re.escape(s)}: ', shown or '', re.M) else ''
