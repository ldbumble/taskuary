"""EACH READER THE SECTIONS THAT HELP IT, WITHIN A BUDGET (phase C 2026-10-23; one section per SUBJECT since 2026-10-25).

LEARNED.md reached every prompt whole and was cut at character 1500, 2000 or 2500 - triage's cut fell before most of the live
rules. Then it was one section per reader, and the Advisor's was a press count: "On asks from X, presses Next (1 of 1)" (the owner,
2026-10-25: a button press is not a fact about a person). Now the sections are about what the owner is like at work - their
people, what they care about, how they work, their promises, what to bring up - and each reader takes the sections that help it
(READS), its in-use lines ranked closest scope first (this sender, their domain or repository, then general), whole lines until its
budget is spent. What does not fit is recorded as over budget (OVER), never dropped without a trace, and every read leaves a
receipt (memory_use) of the lines it was given for which item."""
import json, re
from datetime import datetime

# the five subjects, in the document's order: slug -> heading
SECTIONS = {'people': '## Your people', 'care': '## What you care about', 'work': '## How you work', 'promises': '## Promises',
            'bring': '## What to bring up'}
PEOPLE, CARE, WORK, PROMISES, BRING = SECTIONS.values()
# who reads what (the design's reader matrix, 2026-10-25). Triage reads what the owner cares about - learned from sorting verdicts,
# so a press, a defer or a reply lag never decides whether mail is a task (ruling 11, 2026-10-23)
# ...and the people lines about whoever is on the mail, for its PRIORITY only - important is "it matters because of who" (the owner,
# 2026-10-25); the triage prompt says they never decide whether mail is a task
READS = {'triage': ('care', 'people'), 'drafter': ('people',), 'advisor': ('people', 'care', 'work', 'promises'), 'assistant': tuple(SECTIONS),
         'agents': ('people', 'care', 'promises')}
# who reads a section, as the owner reads it - triage takes the people lines for a task's PRIORITY only (the owner, 2026-10-25)
READER_WORDS = {'triage': 'triage', 'drafter': 'drafts', 'advisor': 'the Advisor', 'assistant': 'the Assistant', 'agents': 'agents'}


def reads_label(slug: str) -> str:
    """'read by triage (priority only) · drafts · the Advisor · the Assistant · agents' - the matrix said in words."""
    rs = [READER_WORDS[r] + (' (priority only)' if r == 'triage' and slug == 'people' else '') for r in READS if slug in READS[r]]
    return 'read by ' + ' · '.join(rs) if rs else 'read by nobody yet'


TITLE = {'people': 'Your people', 'care': 'What you care about', 'work': 'How you work', 'promises': 'Promises', 'bring': 'What to bring up'}
BUDGET = {'triage': 1500, 'drafter': 600, 'agents': 2500, 'assistant': 2000, 'advisor': 2000}
OVER = 'learned_over_budget'          # {reader: [keys]} - the lines a reader's budget left out on its last read
USE_KEEP = 20_000                     # memory_use rows kept; the oldest go past it
_PLACEHOLDER = re.compile(r'_\([^)]*\)_', re.S)
_ADDR = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')


def slug_of(heading: str) -> str:
    """A section heading -> its slug ('people', 'care', ...), '' for any other heading."""
    h = '## ' + str(heading or '').lstrip('#').strip()
    return next((k for k, v in SECTIONS.items() if v == h), '')


def readers_of(slug: str) -> list:
    """The readers that take a section, in READS order."""
    return [r for r, ss in READS.items() if slug in ss]


def subject_of(text: str) -> str:
    """Whom a line is about: the first address in it, lowercased - parsing, not meaning ('' when it names none)."""
    m = _ADDR.search(str(text or ''))
    return m.group(0).lower() if m else ''


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
    """0 this sender, 1 their domain or repository, 3 general. FACTS the app keeps about the item - its sender, domain, repository -
    against the line, never a list of words."""
    t, a = f'{raw} {key}'.lower(), {k: str(v or '').lower() for k, v in (about or {}).items()}
    if a.get('sender') and a['sender'] in t: return 0
    if any(a.get(f) and a[f] in t for f in ('domain', 'repo', 'scope')): return 1
    return 3


def people_of(msg: dict) -> set:
    """Everyone on a mail: its sender and its To and Cc, lowercased (an ingest dict or a message row)."""
    import json as _j
    m = msg or {}
    rec = m.get('RecipientsJson')
    try: rec = _j.loads(rec) if isinstance(rec, str) else rec
    except ValueError: rec = None
    to, cc = (m.get('to') or (rec or {}).get('to') or []), (m.get('cc') or (rec or {}).get('cc') or [])
    return {str(a).strip().lower() for a in [m.get('from_email') or m.get('FromEmail'), *to, *cc] if a and '@' in str(a)}


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


def receipt(store, reader: str, target: str, keys: list):
    """One memory_use row: what `reader` was given for `target`. Never raises - a lost receipt costs a "why?", not the read."""
    try:
        rid = store._exec('INSERT INTO memory_use (Reader, Target, KeysJson, At) VALUES (?,?,?,?)',
                          (reader, str(target or ''), json.dumps(keys), datetime.now().strftime('%Y-%m-%d %H:%M:%S')))
        if rid and int(rid) % 500 == 0: store._exec('DELETE FROM memory_use WHERE Id <= ?', (int(rid) - USE_KEEP,))
    except Exception: pass


def used(store, target: str = None, reader: str = None, limit: int = 20) -> list:
    """The receipts, newest first: [{reader, target, keys, at}]."""
    q, a = 'SELECT * FROM memory_use WHERE 1=1', []
    if target is not None: q += ' AND Target=?'; a.append(str(target))
    if reader: q += ' AND Reader=?'; a.append(reader)
    rows = store._rows(q + ' ORDER BY Id DESC LIMIT ?', (*a, limit))
    return [{'reader': r['Reader'], 'target': r['Target'], 'keys': json.loads(r['KeysJson'] or '[]'), 'at': r['At']} for r in rows]


def names(raw: str) -> set:
    """Every address a line names, lowercased."""
    return {a.lower() for a in _ADDR.findall(str(raw or ''))}


def for_reader(store, reader: str, about: dict = None, budget: int = None, doc: str = None, target: str = '', sections=None,
               people=None) -> str:
    """The sections `reader` reads, as its prompt block: each heading with the in-use lines of it that fit, the reader's budget
    shared across them, closest to this item first. '' when there is none - a fresh LEARNED.md is placeholders, and placeholders are
    not context. `sections` narrows the matrix (the drafter's people only); `target` names the item the receipt is for; `people`
    (addresses) keeps only the people lines about THEM - an agent reads how the owner deals with the people on its own task, never
    the owner's notes on everyone else (the owner, 2026-10-25)."""
    doc = store.doc('learned') if doc is None else doc
    want = [s for s in READS[reader] if sections is None or s in sections]
    who = None if people is None else {str(p).lower() for p in people if p}
    ls = [(raw, k, s) for s in want for raw, k in lines(doc or '', SECTIONS[s]) if s != 'people' or who is None or names(raw) & who]
    keep, over = cut([(raw, k) for raw, k, _ in ls], budget or BUDGET[reader], about)
    at = {raw: i for i, raw in enumerate(keep)}
    try: _note_over(store, reader, over)
    except Exception: pass
    got = sorted([(raw, k, s) for raw, k, s in ls if raw in at], key=lambda x: at[x[0]])      # closest to this item first, in each section
    receipt(store, reader, target, [k for _, k, _ in got])
    return '\n\n'.join(f'{SECTIONS[s]}\n' + '\n'.join(raw for raw, _, x in got if x == s) for s in want if any(x == s for *_, x in got))


def over_budget(store) -> dict:
    """{key: [readers]} - the lines a reader's budget left out on its last read (the memory list's "not read by triage: over budget")."""
    try: was = json.loads(store.get_setting(OVER) or '{}') or {}
    except ValueError: return {}
    out = {}
    for reader, keys in was.items():
        for k in keys or []: out.setdefault(k, []).append(reader)
    return out
