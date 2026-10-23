"""EACH READER ITS OWN SECTION, WITHIN A BUDGET (phase C, 2026-10-23).

LEARNED.md reached every prompt whole and was cut at character 1500, 2000 or 2500 - triage's cut fell before most of the live
rules, and the Advisor's habits rode into triage as if a button press were a sorting verdict. The owner (2026-10-23): "why would we
want button presses to do with triage" - triage reads "How you sort mail" and nothing else, the Advisor "What you do next" and
nothing else. Each reader asks for its section's in-use lines ranked closest scope first (this sender, their domain or repository,
this kind of item, then general) and takes whole lines until its budget is spent. What does not fit is recorded as over budget
(OVER), never dropped without a trace."""
import json, re

SORT, NEXT = '## How you sort mail', '## What you do next'
READS = {'triage': SORT, 'agents': SORT, 'assistant': SORT, 'advisor': NEXT}
TITLE = {SORT: 'How the owner sorts mail (learned from their own sorting verdicts)',
         NEXT: 'What the owner does next (learned from their own presses)'}
BUDGET = {'triage': 1500, 'agents': 2500, 'assistant': 2000, 'advisor': 2000}
OVER = 'learned_over_budget'          # {reader: [keys]} - the lines a reader's budget left out on its last read
_PLACEHOLDER = re.compile(r'_\([^)]*\)_', re.S)


def section(doc: str, head: str) -> str:
    """The body of one `## ` section - up to the next `## ` heading - with its italic placeholder taken out."""
    if not doc or head not in doc: return ''
    body = doc.split(head, 1)[1]
    body = body.split('\n## ', 1)[0]
    return _PLACEHOLDER.sub('', body.split('\n', 1)[1] if '\n' in body else '')


def lines(doc: str, head: str) -> list:
    """[(raw line, key)] - every line of the section a reader would read: tagged and untagged alike (an untagged line is the owner's
    own, in use from the moment they wrote it). Sub-headings are the owner's filing, not content."""
    from .learnedgraph import TAG, _key
    out = []
    for raw in section(doc, head).splitlines():
        t = raw.strip()
        if not t or t.startswith('#') or t.startswith('<!--'): continue
        m = TAG.match(raw)
        out.append((raw.rstrip(), ((m.group('k') or '').strip() or _key(m.group('text'))) if m else _key(t)))
    return out


def rank(raw: str, key: str, about: dict) -> int:
    """0 this sender, 1 their domain or repository, 2 this kind of item, 3 general. FACTS the app keeps about the item - its sender,
    domain, repository, kind - against the line, never a list of words."""
    t, a = f'{raw} {key}'.lower(), {k: str(v or '').lower() for k, v in (about or {}).items()}
    if a.get('sender') and a['sender'] in t: return 0
    if any(a.get(f) and a[f] in t for f in ('domain', 'repo', 'scope')): return 1
    if a.get('kind') and key.startswith('move ') and key.split(' ')[1:2] == [a['kind']]: return 2
    return 3


def about_mail(msg: dict) -> dict:
    """The facts a mail is ranked by: its sender and their domain (an ingest dict or a message row)."""
    em = str((msg or {}).get('from_email') or (msg or {}).get('FromEmail') or '').strip().lower()
    return {'sender': em, 'domain': em.rsplit('@', 1)[-1] if '@' in em else ''}


def cut(ls: list, budget: int, about: dict = None) -> tuple:
    """(lines that fit, keys that did not) - whole lines, closest scope first; the doc's own order breaks ties."""
    ranked = sorted(enumerate(ls), key=lambda il: (rank(il[1][0], il[1][1], about), il[0]))
    used, keep, over = 0, [], []
    for _, (raw, k) in ranked:
        if used + len(raw) + 1 > budget: over.append(k); continue
        keep.append(raw); used += len(raw) + 1
    return keep, over


def _note_over(store, reader: str, over: list):
    try: was = json.loads(store.get_setting(OVER) or '{}') or {}
    except ValueError: was = {}
    if sorted(was.get(reader) or []) == sorted(over): return
    store.set_setting(OVER, json.dumps({**was, reader: over}), 'learned_cut')


def for_reader(store, reader: str, about: dict = None, budget: int = None, doc: str = None) -> str:
    """The section `reader` reads, as its prompt block: the heading and the in-use lines that fit. '' when there is none - a fresh
    LEARNED.md is placeholders, and placeholders are not context."""
    head = READS[reader]
    doc = store.doc('learned') if doc is None else doc
    keep, over = cut(lines(doc or '', head), budget or BUDGET[reader], about)
    try: _note_over(store, reader, over)
    except Exception: pass
    return f'{head}\n' + '\n'.join(keep) if keep else ''


def over_budget(store) -> dict:
    """{key: [readers]} - the lines a reader's budget left out on its last read (the memory list's "not read by triage: over budget")."""
    try: was = json.loads(store.get_setting(OVER) or '{}') or {}
    except ValueError: return {}
    out = {}
    for reader, keys in was.items():
        for k in keys or []: out.setdefault(k, []).append(reader)
    return out
