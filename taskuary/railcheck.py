"""ONE THING, ONE PLACE: a checker for the rail (the owner, 2026-10-28: "if the advisor idea belongs in the tasks why is the email
in fyi??"). A message, a task, a draft or an idea is drawn on exactly one row; a row's line about another row's mail is that mail
twice; a lane's count is the rows in it. `collisions` reads a built rail (funnel.pile's items, or the build with read rows kept)
and names every place that breaks, by SHAPE - lanes, kinds, entity kinds and ids - never by what a row says, so its report can be
pasted into an issue (tools/rail_dupes.py runs it over a home; tests/test_railcheck.py pins it over an invented world)."""
import json, re
from collections import Counter, defaultdict

_REF = re.compile(r'\bTQ-0*(\d+)\b, which was closed')


def _where(i) -> str: return f"{i.get('lane')}/{i.get('kind')}" + (f"/{i['idea_kind']}" if i.get('idea_kind') else '')
def _shape(rows) -> str: return ' + '.join(w + (f' x{n}' if n > 1 else '') for w, n in sorted(Counter(map(_where, rows)).items()))


def _idea_subject(store, iid) -> set:
    """The members an idea is ABOUT: the mail it was said over and the task or mail its action opens."""
    r = store._one("SELECT MessageId, ActionJson FROM idea WHERE IdeaId=?", (iid,)) if store is not None and iid else None
    if not r: return set()
    try: a = json.loads(r.get('ActionJson') or 'null') or {}
    except ValueError: a = {}
    a = a if isinstance(a, dict) else {}
    return ({f"message:{m}" for m in (r.get('MessageId'), a.get('mid')) if m} | ({f"task:{a['tid']}"} if a.get('tid') else set()))


def collisions(items: list, store=None, lanes: list = None, threads: bool = False, ideas: bool = True) -> list:
    """[{check, shape, ids, keys}] - every way the rows break one-thing-one-place. `threads` also reports two rows on one
    conversation (an owner call more than a bug: a thread can carry two tasks). `lanes` is the pile's own lane counts. `ideas`
    reads an idea row against the rows of the mail or task it is about - the rail's question; over a build with read rows kept, a
    line the daily check raised about a mail read and let go sits beside that mail's read row by design (sweep.run)."""
    out = []
    def add(check, rows, ids): out.append({'check': check, 'shape': _shape(rows), 'ids': sorted(map(str, ids)), 'keys': [i['key'] for i in rows]})
    # the same member (message, task, review, idea) inside two rows - an idea row's mid is what it is ABOUT, read below
    by = defaultdict(list)
    for i in items:
        own = set(i.get('member_ids') or ()) | ({f"task:{i['tid']}"} if i.get('tid') else set())
        for m in own | ({f"message:{i['mid']}"} if i.get('mid') and i.get('kind') != 'idea' else set()): by[m].append(i)
    seen = set()
    for m, rows in by.items():
        if len({id(r) for r in rows}) < 2: continue
        sig = tuple(sorted(r['key'] for r in rows))
        if (m.split(':')[0], sig) in seen: continue
        seen.add((m.split(':')[0], sig)); add(f"member:{m.split(':')[0]}", rows, [m])
    # a key one row answers to that another also answers to: Next, Done and a press resolve keys through aliases
    names = defaultdict(list)
    for i in items:
        for k in {i['key'], *(i.get('aliases') or ())}: names[k].append(i)
    for k, rows in names.items():
        if len({id(r) for r in rows}) > 1 and not any(c['check'].startswith('member') and set(c['keys']) == {r['key'] for r in rows} for c in out):
            add('alias', rows, [k])
    # an idea row about a mail or task another row already draws
    for i in items:
        if not ideas or i.get('kind') != 'idea' or not i.get('idea'): continue
        about = _idea_subject(store, i['idea']) | ({f"message:{i['mid']}"} if i.get('mid') else set())
        hit = [(m, r) for m in about for r in by.get(m, ()) if r is not i]
        if hit: add('idea_subject', [i, *{id(r): r for _, r in hit}.values()], {m for m, _ in hit})
    # two rows on one conversation
    if threads:
        cids = defaultdict(list)
        for i in items:
            if i.get('cid') and not str(i['cid']).startswith('own:'): cids[i['cid']].append(i)
        for c, rows in cids.items():
            if len(rows) > 1: add('thread', rows, sorted({f"thread:{r.get('channel')}" for r in rows}))
    # a row still saying it joined a closed task, when it has no task or that task is not closed any more
    for i in items:
        m = _REF.search(str(i.get('why') or ''))
        if not m: continue
        n = int(m.group(1)); t = (store.get_task(n) if store is not None else None) or {}
        if i.get('tid') != n or t.get('Status') != 'done': add('stale_reason', [i], [f"task:{n}:{t.get('Status') or 'gone'}"])
    # a lane's count is its rows
    for l in lanes or ():
        n = sum(i.get('lane') == l['lane'] for i in items)
        if l.get('n') != n: out.append({'check': 'count', 'shape': l['lane'], 'ids': [f"said {l.get('n')}", f"rows {n}"], 'keys': []})
    return out


def summary(found: list) -> dict:
    """{check: {shape: n}} - what a report says about a home without a word of its mail."""
    out = defaultdict(lambda: defaultdict(int))
    for c in found: out[c['check']][c['shape']] += 1
    return {k: dict(v) for k, v in out.items()}
