"""THE MEMORY IS LEARNED.md (the owner, 2026-10-27: "everything that learns about the user should be saved in memory" - and of the Settings
notes page, "probably garbage, remove it").

Every verdict the owner gives - Not ours, Not a task, Not for the agent, a road or a kind corrected, a filed mail made a task - and every fact
they type is a line in LEARNED.md, under the section it is about, in their own hand (untagged: the reflection keeps it byte-for-byte). It
used to be a row in the memory table that triage, the Advisor and agents read only when a word matched, shown on a page of its own.

A line about one sender, their domain, a topic or a mailbox says so at its end - `(about: gail@northwind.example)`, `(about: anyone at
vendor.example)`, `(about: the topic "resident refund request")`, `(about: mail arriving on "AP inbox")` - so the readers that want the lines
bearing on one message (ingest.applicable_notes) find them by what they say, and a newer verdict on the same thing REPLACES the older one
instead of piling up beside it. A line with no `about` is general: every reader of its section has it (learned_cut).

The memory table stays the RECORD of each verdict - the ids the reflection cites as evidence (mem12), what an Undo switches off - but no
decision reads it any more."""
import re
from . import learned_cut as lc

ABOUT = re.compile(r'\s*\(about: (?P<a>[^()]+)\)\s*$')
# a verdict line names its verdict in capitals ("- NOT OURS:", "- FILE IT:", "- A CONVERSATION, not a project"): the newest one on the same
# thing stands; a ROUTING line is one per field
LABEL = re.compile(r" - (?P<l>[A-Z][A-Z' ()]{3,}?)[:,]")
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}:\s*')
APPLIED = 'notes_in_learned'           # the highest memory row already written into LEARNED.md (migrate)


def about(scope: str, key: str = None) -> str:
    """The `about` a line ends with, for a scope and its key - '' for everyone."""
    k = ' '.join(str(key or '').replace('(', ' ').replace(')', ' ').split())
    if not k or scope == 'global': return ''
    return {'sender': k.lower(), 'sender_domain': f'anyone at {k.lower()}', 'subject': f'the topic "{k}"',
            'source': f'mail arriving on "{k}"'}.get(scope, '')


def scope_of(raw: str) -> tuple:
    """(scope, key) a line is about - ('global', None) for a general line."""
    m = ABOUT.search(str(raw or ''))
    if not m: return 'global', None
    a = m.group('a').strip()
    for pre, scope in (('anyone at ', 'sender_domain'), ('the topic "', 'subject'), ('mail arriving on "', 'source')):
        if a.startswith(pre): return scope, a[len(pre):].rstrip('"')
    return ('sender', a.lower()) if '@' in a else ('global', None)


def family(raw: str) -> str:
    """Which lines a line replaces: '' (none - the owner's own words), 'verdict' (any sorting verdict on the same thing), 'routing kind'..."""
    m = LABEL.search(str(raw or ''))
    if not m: return ''
    l = m.group('l').strip()
    return l.lower() if l.startswith('ROUTING') else 'verdict'


def text_of(raw: str) -> str: return str(raw or '').strip().lstrip('-* ').strip()


def line(text: str, scope: str = 'global', key: str = None) -> str:
    """`- text (about: ...)` - the line as LEARNED.md holds it."""
    from .concierge import redact               # a token typed into a fact never lands in the memory every prompt reads
    t = redact(' '.join(_DATE.sub('', ' '.join(str(text or '').split())).split()))
    a = about(scope, key)
    return f'- {t}' + (f' (about: {a})' if a else '')


def section_for(text: str, scope: str, verdict: bool) -> str:
    """Where a line belongs: a verdict on whether mail is work is What you care about; a fact the owner typed about one person is theirs."""
    if verdict: return 'care'
    return 'people' if scope == 'sender' or lc.subject_of(text) else 'care'


def keep(store, text: str, scope: str = 'global', key: str = None, section: str = None, verdict: bool = True) -> str:
    """Write one line into LEARNED.md (owner's hand), replacing the older line of its family about the same thing. Returns the raw line, ''
    when there was nothing to write. Never raises: the verdict itself has already happened."""
    from . import memoryedit
    try:
        old = store.get_doc(memoryedit.DOC) or ''
        doc, raw = put(old, text, scope, key, section, verdict)
        if doc != old: memoryedit._save(store, old, doc)
        return raw
    except Exception as e:
        from loguru import logger
        logger.warning(f'the memory line was not written: {e}')
        return ''


def put(doc: str, text: str, scope: str = 'global', key: str = None, section: str = None, verdict: bool = True) -> tuple:
    """(the document with the line in it, the raw line) - `keep` without the save, so a migration writes once."""
    raw = line(text, scope, key)
    if not text_of(raw): return doc, ''
    slug = section if section in lc.SECTIONS else section_for(raw, scope, verdict)
    fam, sk = family(raw), scope_of(raw)
    if fam and sk[0] != 'global':
        from .memoryedit import _without
        for r, _k in lc.lines(doc, lc.SECTIONS[slug]):
            if r.strip() != raw and family(r) == fam and scope_of(r) == sk: doc = _without(doc, r)
    if raw not in doc.splitlines():
        from .learn import _under
        doc = _under(doc, lc.SECTIONS[slug], raw)
    return doc, raw


def drop(store, raw: str) -> bool:
    """Take a line out (an Undo of the verdict that wrote it)."""
    from . import memoryedit
    doc = store.get_doc(memoryedit.DOC) or ''
    hit = next((r for r in doc.splitlines() if r.strip() == str(raw or '').strip()), None)
    if not hit: return False
    memoryedit._save(store, doc, memoryedit._without(doc, hit)); return True


def of_row(m: dict) -> str:
    """The line a memory row is in LEARNED.md."""
    return line(m.get('Note') or '', m.get('Scope') or 'global', m.get('ScopeKey'))


def keep_row(store, mid) -> str:
    """A verdict just recorded in the memory table (its record), written where every reader reads it."""
    m = store._one('SELECT * FROM memory WHERE MemoryId=?', (int(mid),)) if mid else None
    if not m: return ''
    # the migration's own road, so the row is marked written (a line the owner later takes out is not brought back by the next
    # startup) and any row before it that was never written goes in first
    migrate(store)
    raw = of_row(m)
    return raw if raw in (store.get_doc('learned') or '').splitlines() else ''


def drop_row(store, mid) -> bool:
    m = store._one('SELECT * FROM memory WHERE MemoryId=?', (int(mid),)) if mid else None
    return bool(m) and drop(store, of_row(m))


def notes(store, doc: str = None) -> list:
    """Every line the readers read, as the note-shaped dicts the old table's readers took: {Note, Scope, ScopeKey, Source, MemoryId,
    Key, Section}. MemoryId is the line's place in the document - a later line is the newer word, and breaks a tie the same way."""
    from .learnedgraph import TAG
    doc = store.get_doc('learned') if doc is None else doc
    out, i = [], 0
    for slug, head in lc.SECTIONS.items():
        for raw, k in lc.lines(doc or '', head):
            i += 1
            scope, key = scope_of(raw)
            own = not TAG.match(raw)
            # the note's own words, as the owner gave them - what it is about is Scope/ScopeKey, as a row's was
            out.append({'Note': ABOUT.sub('', text_of(raw)).strip(), 'Scope': scope, 'ScopeKey': key, 'Source': 'verdict' if family(raw) else 'owner' if own else 'learned',
                        'MemoryId': i, 'Key': k, 'Section': slug, 'Own': own, 'Active': 1})
    return out


def standing(store, doc: str = None) -> list:
    """The note-shaped lines a message's readers hold it against (ingest.applicable_notes): every line about one sender, domain, topic or
    mailbox, and the owner's own general lines on what they care about - what a global note was. The reflection's general lines reach
    their readers by learned_cut, not here."""
    return [n for n in notes(store, doc) if n['Scope'] != 'global' or (n['Own'] and n['Section'] == 'care')]


def migrate(store) -> int:
    """Every memory row not yet in LEARNED.md, written there once (startup): the owner's typed notes and their verdicts, global ones too -
    nothing they wrote is lost when the notes page goes. Idempotent: a row is written once (APPLIED), and a line already there is not
    written twice. A switched-off row was the owner saying "not this" - it is not brought back. Returns the lines written."""
    _mutes(store)
    try: done = int(store.get_setting(APPLIED) or 0)
    except ValueError: done = 0
    rows = sorted((m for m in store.list_memories(active_only=False) if int(m['MemoryId']) > done), key=lambda m: m['MemoryId'])
    if not rows: return 0
    from . import memoryedit
    old = doc = store.get_doc(memoryedit.DOC) or ''
    n = 0
    for m in rows:
        if m.get('Active') and m.get('Source') == 'writing':
            # ...an instruction about HOW to write is the drafter's, and the drafter reads STYLE.md's Owner notes (PW-060/061)
            from .responder import style_feedback
            note = ' '.join(str(m.get('Note') or '').split())
            if note and note[:400] not in (store.get_doc('style') or ''): style_feedback(store, note, 'memory')
        elif m.get('Active') and str(m.get('Note') or '').strip():
            had = doc.splitlines()
            doc, raw = put(doc, m['Note'], m.get('Scope') or 'global', m.get('ScopeKey'), verdict=m.get('Source') == 'verdict')
            n += bool(raw) and raw not in had
        done = max(done, int(m['MemoryId']))
    if doc != old: memoryedit._save(store, old, doc)
    store.set_setting(APPLIED, str(done), 'memory')
    return n


MUTES_DONE = 'mutes_in_learned'


def _mutes(store):
    """The owner's standing "never show me these again" rules (funnel_mutes - written by older versions; nothing writes them now), each
    said once in LEARNED.md as what it is: something they do not care to see. The funnel still applies them as it did."""
    if store.get_setting(MUTES_DONE): return
    from .funnel import mutes
    for r in mutes(store):
        what = str(r.get('why') or '').strip() or ' '.join(r.get('words') or [])
        if what: keep(store, f'Not worth showing you: {what}', 'sender' if r.get('sender') else 'global', r.get('sender'), section='care', verdict=False)
    store.set_setting(MUTES_DONE, '1', 'memory')
