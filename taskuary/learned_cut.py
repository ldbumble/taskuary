"""EACH READER THE SECTIONS THAT HELP IT, WITHIN A BUDGET (phase C 2026-10-23; one section per SUBJECT since 2026-10-25).

LEARNED.md reached every prompt whole and was cut at character 1500, 2000 or 2500 - triage's cut fell before most of the live
rules. Then it was one section per reader, and the Advisor's was a press count: "On asks from X, presses Next (1 of 1)" (the owner,
2026-10-25: a button press is not a fact about a person). Now the sections are about what the owner is like at work - their
people, what they care about, how they work, their promises, what to bring up - and each reader takes the sections that help it
(READS), its in-use lines ranked closest scope first (this sender, their domain or repository, then general), whole lines until its
budget is spent. What does not fit is recorded as over budget (OVER), never dropped without a trace, and every read leaves a
receipt (memory_use) of the lines it was given for which item."""
import json, re, zlib
from datetime import datetime
from .kinds import ASSISTANT

# the five subjects, in the document's order: slug -> heading
SECTIONS = {'people': '## Your people', 'care': '## What you care about', 'work': '## How you work', 'promises': '## Promises',
            'bring': '## What to bring up'}
PEOPLE, CARE, WORK, PROMISES, BRING = SECTIONS.values()
# who reads what (the design's reader matrix, 2026-10-25). Triage reads what the owner cares about - learned from sorting verdicts,
# so a press, a defer or a reply lag never decides whether mail is a task (ruling 11, 2026-10-23)
# ...and the people lines about whoever is on the mail, for its PRIORITY only - important is "it matters because of who" (the owner,
# 2026-10-25); the triage prompt says they never decide whether mail is a task
# ...and an agent reads ALL of it (the owner, 2026-10-27: "every part it knows about the user should be in the agents") - the people lines
# still only about the people on its own task, and nothing at all on a stranger's task (context.py)
# ...and triage, and the report's routing judge, read the WHOLE of it every time, through `whole` - not a budgeted cut (the owner,
# 2026-10-27: "triage needs the entire thing to make a decision every time"). Agents read it on demand (agenttools' owner_memory,
# `taskuary --memory`) instead of carrying it in their start prompt (2026-10-27: "progressive disclosure")
READS = {'triage': tuple(SECTIONS), 'drafter': ('people', 'work'), 'advisor': ('people', 'work', 'care', 'promises'), 'assistant': tuple(SECTIONS),
         'agents': tuple(SECTIONS)}
# who reads a section, as the owner reads it - triage takes the people lines for a task's PRIORITY only (the owner, 2026-10-25)
READER_WORDS = {'triage': 'triage', 'drafter': 'drafts', 'advisor': 'the Advisor', 'assistant': ASSISTANT, 'agents': 'agents'}


def reads_label(slug: str) -> str:
    """'read by triage (priority only) · drafts · the Advisor · the Assistant · agents' - the matrix said in words."""
    rs = [READER_WORDS[r] + (' (priority only)' if r == 'triage' and slug == 'people' else '') for r in READS if slug in READS[r]]
    return 'read by ' + ' · '.join(rs) if rs else 'read by nobody yet'


TITLE = {'people': 'Your people', 'care': 'What you care about', 'work': 'How you work', 'promises': 'Promises', 'bring': 'What to bring up'}
# ...the Assistant's is the memory whole, short of the lines about one other sender or topic (LEARNED.md's own head says "the Assistant all
# of it"): at 4,000 it read the first forty lines of What you care about and no line of Your people - nor the fact just told it there
# (2026-11-14). Its instructions are written once per chat and cached (concierge.turn_system)
BUDGET = {'triage': 1500, 'drafter': 600, 'agents': 3500, 'assistant': 16_000, 'advisor': 6000}
# ...and the section a reader takes FIRST, after the lines about the people on the item: what the owner cares about, except the Advisor's,
# which is how they work - its 2000 characters filled with what-becomes-a-task lines and How you work never arrived (the Advisor audit,
# 2026-10-28); a line saying how the owner handles a thing is what a lit button rests on
FIRST = {'advisor': 'work'}
NEAR_PEOPLE = 2                       # the people lines about an item's SUBJECT a reader takes, beside those about the people on it
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
    from .memorylines import scope_of
    out = []
    for raw in section(doc, head).splitlines():
        t = raw.strip()
        if not t or t.startswith('#') or t.startswith('<!--'): continue
        m = TAG.match(raw)
        # ...an untagged line's key is its first eight words AND whom it is about: "Weekly digests from this sender are reading only" about
        # sixty senders was sixty lines under one key, and Forget on one took out whichever came first (the memory audit, 2026-11-12)
        sk = '' if m else scope_of(t)[1]
        out.append((raw.rstrip(), ((m.group('k') or '').strip() or _key(m.group('text'))) if m else _key(t) + (f' · {sk}' if sk else '')))
    return out


_TOPIC = re.compile(r'[a-z0-9][a-z0-9-]{3,}')
# ...a word and its plural or tense are one word here ("payroll question" and "payroll questions" shared one word, and the line about
# payroll was ranked with the lines about parking - 2026-11-14): the first five letters less a plural's s, a way of matching spellings,
# never a list of words
# ...and an address is who, not what about: every colleague's line shared "northwind" and "example" with a summary that named the company
def stems(text: str) -> set: return {w[:5].rstrip('s') or w[:5] for w in _TOPIC.findall(_ADDR.sub(' ', str(text or '').lower()))}
def rank(raw: str, key: str, about: dict) -> int:
    """0 this sender, 1 someone else on the item (by address or full name), 2 the item's own subject, 3 their domain or repository,
    4 general. FACTS the app keeps about the item - its sender, the people on it, its title, its domain or repository - against the line,
    never a list of words.
    ...WHO IS ON IT, AND WHAT IT IS ABOUT (the memory audit, 2026-10-26): ranked by domain alone, every colleague tied - one company, one
    domain - and the 2000-character budget cut the people lines in the document's order, whoever the item was about."""
    a = about or {}
    t, s = f'{raw} {key}'.lower(), {k: str(v or '').lower() for k, v in a.items() if isinstance(v, str)}
    if any(s.get(f) and s[f] in t for f in ('sender', 'sender_name')): return 0
    if any(str(p).lower() in t for p in a.get('people') or () if p): return 1
    # ...a line about one OTHER sender (memorylines' `(about: x@y)`) is theirs alone - a colleague at the same domain is not them
    from .memorylines import scope_of
    if scope_of(raw)[0] == 'sender': return 5
    # ...the subject as two of its own longer words in the line: a ranking, so a near miss costs an order, never a read
    if len(stems(s.get('topic', '')) & stems(t)) >= 2: return 2
    if any(s.get(f) and s[f] in t for f in ('domain', 'repo', 'scope')): return 3
    # ...and a line about one OTHER sender, domain or topic (memorylines' `(about: ...)` - the owner's verdicts, a line each) comes after
    # every general line: there are hundreds of them, and the one about someone else says least about this item (2026-10-27)
    from .memorylines import ABOUT
    return 5 if ABOUT.search(raw) else 4


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


# WHAT THE OWNER CARES ABOUT IS NEVER THE FIRST CUT (the owner, 2026-10-27: "if I don't care about something the system knows it"). A
# don't-care line - "the legacy export job is not mine to watch" - is general, so it ranked 4 and the document's order cut it behind every
# line about someone not on the item; and the owner's own lines sit at the END of their section, so they went before the learned ones.
# So every reader takes the care lines before lines of the same scope from other sections, and the owner's own words before the learned
# ones. The lines about the people on this very item still come first: there are few of them, and triage weighs the priority by them.


def nearness(ls: list, about: dict = None, sims: dict = None) -> list:
    """How near each line is to the item's subject, for ordering lines of one scope - a ranking, never a verdict. By meaning where an
    embedder says (`sims`: {key: similarity}, textsim); else by the words the line shares with the item's title and summary, a rare one
    counting for more than one half the lines carry. All zero for a reader with no item."""
    import math
    if sims is not None: return [round(float(sims.get(k, 0.0)), 3) for _raw, k, *_ in ls]
    want = stems((about or {}).get('topic'))
    if not want: return [0.0] * len(ls)
    have = [stems(said(raw)) for raw, *_ in ls]
    df = {w: sum(w in h for h in have) for w in want}
    return [round(sum(math.log(1 + len(ls) / df[w]) for w in h & want), 3) for h in have]


def cut(ls: list, budget: int, about: dict = None, first: str = 'care', sims: dict = None) -> tuple:
    """(lines that fit, keys that did not) - whole lines, closest scope first. Lines may carry their section slug as a third item: then
    care lines go before others of the same scope, and the owner's own (untagged) lines before learned ones. A `first` other than care
    leads from scope 2 on: its lines go before every topic, domain and general line of the others, so the budget never fills before it
    is read.
    ...IN ONE SCOPE, THE LINE NEAREST THIS ITEM FIRST, AND THE OWNER'S NEWEST WORD BEFORE THEIR OLDER (the owner, 2026-11-14: "if the user
    tells you something, they should not have to say it again"): ties fell in the document's order, where a fact just told is the LAST
    line of its section - sixty lines in, the one about payroll was the one the budget left out, on the very task about payroll."""
    from .learnedgraph import TAG
    near = nearness(ls, about, sims)
    def key(il):
        i, (raw, k, *s) = il
        s = s[0] if s else ''
        r = rank(raw, k, about)
        if first != 'care' and r >= 2 and r != 5: r = 2 if s == first else r + 0.5
        own = not TAG.match(raw)
        return (r, -near[i], bool(s) and s != first, bool(s) and not own, -i if own else i)
    used, keep, over = 0, [], []
    for _, (raw, k, *_s) in sorted(enumerate(ls), key=key):
        n = len(said(raw)) + 1                  # ...what the reader is given, not the tag it never sees
        if used + n > budget: over.append(k); continue
        keep.append(raw); used += n
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


def said(raw: str) -> str:
    """A line as a READER gets it: its words, without the `[s:N | ev: ... | seen: ... | k: ...]` tag. The tag is the reflection's
    bookkeeping - no reader is told what it means - and its `seen` date and evidence move on every reflection, so a memory block that
    carried them was new bytes, billed whole again, each time a line was merely confirmed (2026-11-12)."""
    from .learnedgraph import TAG
    m = TAG.match(raw or '')
    return f"- {m.group('text').strip()}" if m else str(raw or '').rstrip()


def names(raw: str) -> set:
    """Every address a line names, lowercased."""
    return {a.lower() for a in _ADDR.findall(str(raw or ''))}


# A LINE THE MODEL CAN CITE (the memory audit, 2026-10-26): a line's own tag names the episodes it was learned from, and an owner's line
# has none - so nothing said which memory line an answer rested on, and the strip could not tell a memory reason from a restated fact.
# Each line the Advisor reads carries an id made from its key: stable while the line stands, gone when it is Forgotten or replaced.
def cite_of(key: str) -> str: return f'lrn{zlib.crc32(str(key or "").encode()) % 1_000_000}'


def cited(store, ids, reader: str = 'advisor', doc: str = None) -> dict:
    """{cite id: (raw line, key, section slug)} - the lines `reader` reads today that `ids` name. A Forgotten or replaced line is no
    longer in the document, so an answer judged on it rests on nothing."""
    want = {str(i) for i in ids or ()}
    if not want: return {}
    doc = store.doc('learned') if doc is None else doc
    return {c: (raw, k, s) for s in READS[reader] for raw, k in lines(doc or '', SECTIONS[s]) if (c := cite_of(k)) in want}


def for_reader(store, reader: str, about: dict = None, budget: int = None, doc: str = None, target: str = '', sections=None,
               people=None, cite: bool = False, own: bool = False) -> str:
    """The sections `reader` reads, as its prompt block: each heading with the in-use lines of it that fit, the reader's budget
    shared across them, closest to this item first. '' when there is none - a fresh LEARNED.md is placeholders, and placeholders are
    not context. `sections` narrows the matrix (the drafter's people only); `target` names the item the receipt is for; `people`
    (addresses) keeps only the people lines about THEM - an agent reads how the owner deals with the people on its own task, never
    the owner's notes on everyone else (the owner, 2026-10-25). `own`: of the other sections, only the lines in the owner's own words
    (untagged) - what he told an agent or the Assistant, which every agent's brief carries; what was learned stays one read away."""
    doc = store.doc('learned') if doc is None else doc
    want = [s for s in READS[reader] if sections is None or s in sections]
    who = None if people is None else {str(p).lower() for p in people if p}
    every = [(raw, k, s) for s in want for raw, k in lines(doc or '', SECTIONS[s])]
    sims = None
    if str((about or {}).get('topic') or '').strip() and every:
        try:
            from . import textsim
            got = textsim.rank(store, about['topic'], [(f'learned:{k}', said(raw)) for raw, k, _ in every], least=0.0)
            sims = None if got is None else {k[8:]: v for k, v in got}
        except Exception: sims = None
    # ...or the people lines nearest this item's own SUBJECT (NEAR_PEOPLE of them: "send payroll questions to Gail now" on a vendor's
    # payroll question, where Gail is nobody on the mail and the line reached no agent - 2026-11-14): what bears on the work, still
    # never the notes on everyone else
    # ...BY WHAT A LINE IS ABOUT, NEVER BY WHERE IT WAS FILED (walk 6, H5: "only meetings between 10am and 2pm, never on Fridays", filed under
    # Your people, named nobody on any task and reached no agent - three 2:00 PM slots were proposed, one sent): a line that names people
    # (their addresses), none of them on this item, is about everyone else; any other line is read by nearness, whichever heading it is under
    near = dict(zip((k for _, k, _ in every), nearness(every, about, sims)))
    ours = lambda raw: who is not None and bool(names(raw) & who)
    others = lambda raw: who is not None and bool(names(raw)) and not ours(raw)
    off = [(raw, k) for raw, k, s in every if who is not None and not ours(raw) and rank(raw, k, about) == 2 and near[k] > 0]
    by_subject = {k for _, k in sorted(off, key=lambda x: -near[x[1]])[:NEAR_PEOPLE]}
    # ...AND A LINE ABOUT A PERSON ON THIS ITEM, under any heading but Your people (the brief carries those - context.build), is this
    # reader's: "venue quotes from this sender go to Paula" was left out as a line about everyone else, the sender being on the task
    item = {str(p).lower() for p in (about or {}).get('people') or [] if p}
    on_item = lambda x: x[2] != 'people' and bool(names(x[0]) & item)
    ls = [(raw, k, s) for raw, k, s in every if not others(raw) or k in by_subject or on_item((raw, k, s))]
    if own:
        from .learnedgraph import TAG
        ls = [x for x in ls if ours(x[0]) or x[1] in by_subject or not TAG.match(x[0])]
    # ...and a line about one OTHER sender, domain or topic (memorylines' `(about: ...)`: a verdict, a line each) is not this reader's:
    # it reaches the readers of the mail it is about, by what it is about (ingest.applicable_notes) - hundreds of them, about everyone
    # else, would be the whole budget
    ls = [x for x in ls if on_item(x) or rank(x[0], x[1], about) != 5]
    # ...and a line learned under ANOTHER workstream is not this item's (the design's S4/S5, 2026-11-01): a habit with the side product's
    # testers is noise on a day-job ask. Lines under no workstream, and the owner's own, are everyone's
    if (ws := (about or {}).get('workstream')):
        try: other = {r['Key'] for r in store._rows("SELECT Key FROM learned_line WHERE IFNULL(Workstream,'') NOT IN ('', ?)", (ws,))}
        except Exception: other = set()
        ls = [x for x in ls if x[1] not in other]
    keep, over = cut(ls, budget or BUDGET[reader], about, FIRST.get(reader, 'care'), sims)
    at = {raw: i for i, raw in enumerate(keep)}
    try: _note_over(store, reader, over)
    except Exception: pass
    got = sorted([(raw, k, s) for raw, k, s in ls if raw in at], key=lambda x: at[x[0]])      # closest to this item first, in each section
    receipt(store, reader, target, [k for _, k, _ in got])
    say = (lambda raw, k: f'{said(raw)} (id {cite_of(k)})') if cite else (lambda raw, k: said(raw))
    return '\n\n'.join(f'{SECTIONS[s]}\n' + '\n'.join(say(raw, k) for raw, k, x in got if x == s) for s in want if any(x == s for *_, x in got))


WHOLE_CAP = 60_000         # ~15k tokens: past it a reader keeps whole sections in order, and the ones left out are logged


def whole(store, reader: str = 'triage', target: str = '', doc: str = None, cap: int = WHOLE_CAP, sections=None) -> str:
    """Every line of every section, in the document's order - the whole memory, for a reader that decides on all of it (triage, the
    routing judge) or asked for it (an agent's owner_memory). Lines about one sender or topic come too: triage weighs them for mail
    about that. Only past `cap` does anything go - a whole section at a time, said in the log and noted as over budget, never a line
    cut off midway. `sections` (slugs) narrows it. '' when there is nothing in use.
    ...PAST THE CAP, THE LINES ABOUT ONE SENDER OR TOPIC GO FIRST, the oldest of them first (the memory audit, 2026-11-12): a whole section
    went, and the one that outgrew it was What you care about - six hundred verdict lines, and triage read none of it, the owner's own
    general lines with them. Each line about one sender or topic still reaches the mail it is about, as its evidence (ingest.relevant_notes).
    What is kept depends on the document alone, so the block is the same bytes for every mail."""
    from .memorylines import ABOUT
    doc = store.doc('learned') if doc is None else doc
    every = [(head, raw, k) for s, head in SECTIONS.items() if not sections or s in sections for raw, k in lines(doc or '', head)]
    used = sum(len(h) + 3 for h in {h for h, _, _ in every})
    scoped = lambda i: bool(ABOUT.search(every[i][1]))
    keep, over = set(), []
    for i in sorted(range(len(every)), key=lambda i: (scoped(i), -i if scoped(i) else i)):
        n = len(said(every[i][1])) + 1
        if used + n > cap: over.append(every[i][2]); continue
        keep.add(i); used += n
    if over:
        from loguru import logger
        logger.warning(f'{reader} read LEARNED.md without {len(over)} line(s) about one sender or topic - past its {cap:,}-character cap; '
                       'each still reaches the mail it is about')
    out = ['\n'.join([head] + [said(raw) for i, (h, raw, _) in enumerate(every) if h == head and i in keep]) for head in SECTIONS.values()
           if any(h == head and i in keep for i, (h, _, _) in enumerate(every))]
    keys = [k for i, (_, _, k) in enumerate(every) if i in keep]
    try: _note_over(store, reader, over)
    except Exception: pass
    receipt(store, reader, target, keys)
    return '\n\n'.join(out)


def left_out(store, reader: str) -> int:
    "How many lines `reader`'s budget left out on its last read - so its block can say the rest is one read away."
    try: return len((json.loads(store.get_setting(OVER) or '{}') or {}).get(reader) or [])
    except ValueError: return 0


def over_budget(store) -> dict:
    """{key: [readers]} - the lines a reader's budget left out on its last read (the memory list's "not read by triage: over budget")."""
    try: was = json.loads(store.get_setting(OVER) or '{}') or {}
    except ValueError: return {}
    out = {}
    for reader, keys in was.items():
        for k in keys or []: out.setdefault(k, []).append(reader)
    return out
