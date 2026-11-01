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
    for k, v, why in (('channels', f'{ch}:{src}', 'chat group'), ('mailboxes', src, 'mailbox'), ('repos', src, 'repository')):
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


def menu(store) -> str:
    """The workstreams as triage is shown them: one line each, its slug first - the model names one, or null."""
    return '\n'.join(f"- {w['slug']}: {w['name']}" + (f" - {w['about']}" if w['about'] else '') + (' (personal)' if w['personal'] else '')
                     for w in streams(store))


def from_menu(answer, shown: str) -> str:
    """A slug triage answered, only if it was one it was shown."""
    s = str(answer or '').strip().lower()
    return s if s and re.search(rf'^- {re.escape(s)}: ', shown or '', re.M) else ''
