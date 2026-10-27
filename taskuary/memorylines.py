"""THE MEMORY IS LEARNED.md (the owner, 2026-10-27: "everything that learns about the user should be saved in memory" - and of the Settings
notes page, "probably garbage, remove it"; of the notes table itself, "we don't need it").

Every fact the owner types, and every verdict they give that teaches something about them, is a line in LEARNED.md under the section it
is about, in their own hand (untagged: the reflection keeps it byte-for-byte). There is no second store: the memory table that used to
hold each verdict - read only when a word matched, shown on a page of its own - is drained into lines once and dropped (migrate).

A line about one sender, their domain, a topic or a mailbox says so at its end - `(about: gail@northwind.example)`, `(about: anyone at
vendor.example)`, `(about: the topic "resident refund request")`, `(about: mail arriving on "AP inbox")` - so the readers that want the lines
bearing on one message (ingest.applicable_notes) find them by what they say. A line with no `about` is general: every reader of its
section has it (learned_cut).

A VERDICT TEACHES IN WORDS, OR NOT AT ALL (the owner, 2026-10-27: "just 'this not for agent' doesn't add to understanding of the user";
of an Advisor idea taken up or turned down, a line "if it adds to understanding of the user - as long as it's not bloat"). `teach` asks
the model what the verdict says about the owner - the kind of work and why - against the lines already there: nothing when it is said
already or nothing general can be said, a line that REPLACES an older one when it sharpens it. The line's history row (learned_history,
Action 'said', Actor 'verdict:<kind>') carries the id of what the verdict was given on - msg12, task7, idea3 - which is the evidence the
reflection cites and what an Undo finds the line by (`untaught`)."""
import re
from . import learned_cut as lc

ABOUT = re.compile(r'\s*\(about: (?P<a>[^()]+)\)\s*$')
# an older verdict line names its verdict in capitals ("- NOT OURS:", "- FILE IT:", "- A CONVERSATION, not a project" - written before
# 2026-10-27's second ruling, and kept as the owner's word): the newest one on the same thing stands; a ROUTING line is one per field
LABEL = re.compile(r" - (?P<l>[A-Z][A-Z' ()]{3,}?)[:,]")
_DATE = re.compile(r'^\d{4}-\d{2}-\d{2}:\s*')
APPLIED = 'notes_in_learned'           # the highest memory row written into LEARNED.md (migrate) - and so the highest mem id that was real
VERDICT = 'verdict'


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
    when there was nothing to write. Never raises."""
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
    return _put(doc, text, scope, key, section, verdict)[:2]


def _put(doc: str, text: str, scope: str = 'global', key: str = None, section: str = None, verdict: bool = True) -> tuple:
    """(doc, raw, [the older lines it replaced])."""
    raw, gone = line(text, scope, key), []
    if not text_of(raw): return doc, '', gone
    slug = section if section in lc.SECTIONS else section_for(raw, scope, verdict)
    fam, sk = family(raw), scope_of(raw)
    if fam and sk[0] != 'global':
        from .memoryedit import _without
        for r, _k in lc.lines(doc, lc.SECTIONS[slug]):
            if r.strip() != raw and family(r) == fam and scope_of(r) == sk: doc = _without(doc, r); gone.append(r.strip())
    if raw not in doc.splitlines():
        from .learn import _under
        doc = _under(doc, lc.SECTIONS[slug], raw)
    return doc, raw, gone


def drop(store, raw: str) -> bool:
    """Take a line out."""
    from . import memoryedit
    doc = store.get_doc(memoryedit.DOC) or ''
    hit = next((r for r in doc.splitlines() if r.strip() == str(raw or '').strip()), None)
    if not hit: return False
    memoryedit._save(store, doc, memoryedit._without(doc, hit)); return True


# ── a verdict, in words ───────────────────────────────────────────────────────────────────────────────────────────────────────────────
# what each verdict was, for the model and the history - never written into a line as it stands
WORDS = {'not_ours': "Not ours - the owner said it is other people's work: no task, no reply",
         'not_a_task': 'Not a task - the owner filed it: no task, no reply',
         'not_for_agent': "Not for the agent - real work, but the owner's own: kept on their list, no agent on it",
         'made_task': 'Made a task - triage had filed it as nothing to do; the owner made it real work',
         'road_fyi': 'Nothing to do - the owner moved it to FYI', 'road_reply': 'A reply only - answering it is the work',
         'road_coding': 'Agent work - an agent should work it', 'road_general': 'A conversation with the Assistant, not a project',
         'road_task': "The owner's own task - real work, not an agent's",
         'routing': 'The owner corrected how a task was routed', 'judged': 'The owner corrected how a task was judged',
         'idea_task': 'Took up an Advisor idea - made it a task', 'idea_agent': 'Took up an Advisor idea - sent it to an agent',
         'idea_done': 'Handled an Advisor idea some other way', 'idea_dismiss': 'Turned down an Advisor idea',
         'idea_dismiss_kind': 'Turned down an Advisor idea - and no more ideas like it'}
SAID = ('not_ours', 'not_a_task', 'not_for_agent')     # the explicit put-downs: two behind a hide rule = the owner said it (learn.auto_adopt)
TEACH_SYSTEM = (
    'You keep LEARNED.md, what Taskuary knows about the person it works for (the owner). The owner just gave a verdict on one item. Say in '
    'ONE line what it teaches about the owner: what kind of work, mail or idea this is for them, and why - e.g. "You handle vendor invoice '
    'disputes yourself - not agent work", "Facilities scheduling mail is the site managers\' work, not yours".\n'
    '- Never a bare verdict ("this is not for the agent", "not a task", "turned this down"): a line that only says what was pressed '
    'teaches nothing.\n'
    "- Never one item's case details (a resident's, patient's or customer's name, an amount, a date, a ticket number).\n"
    '- Say "you" for the owner; under 25 words.\n'
    '- If an EXISTING line already says it, write nothing. If this verdict sharpens, widens or contradicts an existing line, write the new '
    'line and give the line it replaces, copied exactly. If nothing about the owner can be generalised from this one item, write nothing.\n'
    'Answer JSON only: {"line": "<the line>" or "", "replaces": "<an existing line copied exactly>" or "", "only_this": true when it holds '
    'only for mail like this one (this sender or this topic), false when it is general}')
TEACH_FIT = 6000          # the existing lines the model weighs a new one against


def _llm(store):
    from .llm import build_llm
    return build_llm(store, job='memory')


def _answer(raw) -> dict:
    import json
    t = str(raw or '').strip().removeprefix('```json').removeprefix('```').removesuffix('```').strip()
    try: o = json.loads(t)
    except ValueError:
        m = re.search(r'\{.*\}', t, re.S)
        try: o = json.loads(m.group(0)) if m else {}
        except ValueError: o = {}
    return o if isinstance(o, dict) else {}


def _existing(doc: str, slug: str, scope: str, key: str) -> list:
    """The lines a new one is weighed against: its own section first, general lines and the ones about this same thing - never the
    hundreds about someone else - up to TEACH_FIT."""
    sk, out, n = (scope, (key or '').lower() if scope == 'sender' else key), [], 0
    for s in [slug] + [x for x in lc.SECTIONS if x != slug]:
        for raw, _k in lc.lines(doc, lc.SECTIONS[s]):
            if scope_of(raw)[0] != 'global' and scope_of(raw) != sk: continue
            if n + len(raw) > TEACH_FIT: return out
            out.append(raw.strip()); n += len(raw) + 1
    return out


def _key(raw: str) -> str:
    from .learnedgraph import _key as k
    return k(str(raw or '').strip())


def teach(store, kind: str, src: str, facts: str, scope: str = 'global', key: str = None, section: str = None, llm=None, stands=None) -> str:
    """One verdict -> at most one LEARNED.md line saying what it teaches about the owner, written by the model from `facts` (the item and
    the verdict) and weighed against the lines already there. `src` is the id of what the verdict was given on (msg12, task7, idea3) -
    the line's evidence and what an Undo finds it by. `stands`: still the owner's word once the model has answered (an Undo can come
    first). No brain, no line: a bare verdict is never written in its place. Returns the raw line, ''. Never raises."""
    from . import memoryedit
    try:
        # ...a verdict counts toward the next reflection whether or not it teaches a line now (learn.learn_from's tick, which it replaces)
        try: store.set_setting('learn_pending', str(int(store.get_setting('learn_pending') or 0) + 1), 'learn')
        except ValueError: pass
        slug = section if section in lc.SECTIONS else 'care'
        llm = llm if llm is not None else _llm(store)
        if llm is None: return ''
        have = _existing(store.get_doc(memoryedit.DOC) or '', slug, scope, key)
        a = _answer(llm(TEACH_SYSTEM, f'THE VERDICT: {WORDS.get(kind, kind)}\n\nTHE ITEM:\n{str(facts or "")[:2500]}\n\n'
                                     'EXISTING LINES:\n' + ('\n'.join(have) or '(none yet)'), max_tokens=300))
        said = text_of(ABOUT.sub('', str(a.get('line') or '')).strip())
        if not said or (stands and not stands()): return ''
        doc = store.get_doc(memoryedit.DOC) or ''
        old = text_of(a.get('replaces'))
        hit = next((r for r in doc.splitlines() if old and text_of(r) == old and r.strip().startswith(('- ', '* '))), None)
        new, gone = (memoryedit._without(doc, hit), [hit.strip()]) if hit else (doc, [])
        only = a.get('only_this') is True and scope != 'global'
        new, raw, more = _put(new, said, scope if only else 'global', key if only else None, slug, True)
        if not raw or raw in doc.splitlines(): return ''
        memoryedit._save(store, doc, new)
        k = next((k for r, k in lc.lines(new, lc.SECTIONS[slug]) if r.strip() == raw), _key(raw))
        store.add_learned_event(k, raw, 'live', 0, src or '', 'said', f'{VERDICT}:{kind}')
        for g in gone + more: store.add_learned_event(_key(g), g, 'live', 0, src or '', 'replaced', f'{VERDICT}:{kind}')
        return raw
    except Exception as e:
        from loguru import logger
        logger.warning(f'the verdict taught no line: {e}'); return ''


def teach_soon(store, *a, background=None, **kw):
    """`teach` off the press: a button never waits on the model (ingest: A BUTTON NEVER WAITS ON THE AI)."""
    if background is not None: return background.add_task(teach, store, *a, **kw)
    import threading
    threading.Thread(target=teach, args=(store, *a), kwargs=kw, daemon=True).start()


def untaught(store, src: str) -> int:
    """The Undo of a verdict: the line it wrote comes out, a line it replaced goes back where it was, and what the line fed is withdrawn
    (learn.withdraw). Returns the lines taken out."""
    if not src: return 0
    from . import memoryedit
    from .learn import withdraw, _under
    rows = store._rows("SELECT * FROM learned_history WHERE Ev=? AND Action IN ('said','replaced') AND Actor LIKE ? ORDER BY Id",
                       (src, f'{VERDICT}:%'))
    doc = old = store.get_doc(memoryedit.DOC) or ''
    n = 0
    for r in rows:
        t = str(r['Text'] or '').strip()
        if r['Action'] == 'said':
            if t in [l.strip() for l in doc.splitlines()]: doc, n = memoryedit._without(doc, next(l for l in doc.splitlines() if l.strip() == t)), n + 1
            store.add_learned_event(r['Key'], t, 'live', 0, src, 'unsaid', r['Actor'])
        elif t and t not in doc.splitlines():
            doc = _under(doc, lc.SECTIONS['bring' if str(r['Actor']).startswith(f'{VERDICT}:idea_') else 'care'], t)
    if doc != old: memoryedit._save(store, old, doc)
    withdraw(store, src)
    return n


def lessons(store, since: str = '', kinds=None) -> list:
    """The verdict lines written since `since` that still stand, newest first: [{ev, kind, text, key, at}]."""
    doc = store.get_doc('learned') or ''
    now = {r.strip() for r in doc.splitlines()}
    out = []
    for r in store._rows("SELECT * FROM learned_history WHERE Action='said' AND Actor LIKE ? AND At>=? ORDER BY Id DESC",
                         (f'{VERDICT}:%', since or '')):
        kind = str(r['Actor']).split(':', 1)[1]
        if str(r['Text'] or '').strip() in now and (not kinds or kind in kinds):
            out.append({'ev': r['Ev'] or '', 'kind': kind, 'text': r['Text'], 'key': r['Key'], 'at': r['At']})
    return out


def said(store) -> set:
    """The evidence ids of the owner's explicit put-downs whose line still stands (learn.auto_adopt)."""
    return {l['ev'] for l in lessons(store, kinds=SAID) if l['ev']}


def verdict_ids(store) -> set:
    """Every id a verdict was given on (msg12, task7): sorting evidence, where a msg id is otherwise only a mail the owner answered."""
    return {r['Ev'] for r in store._rows("SELECT DISTINCT Ev FROM learned_history WHERE Action='said' AND Actor LIKE ? AND IFNULL(Ev,'')<>''",
                                         (f'{VERDICT}:%',))}


def given_on(store, ev: str) -> dict:
    """The newest verdict line given on `ev` (msg12, task7) - {kind, text} or {} - so its evidence reads as the verdict it was."""
    r = store._one("SELECT * FROM learned_history WHERE Ev=? AND Action='said' AND Actor LIKE ? ORDER BY Id DESC LIMIT 1", (ev, f'{VERDICT}:%'))
    return {'kind': str(r['Actor']).split(':', 1)[1], 'text': r['Text']} if r else {}


# ── the readers' view ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def notes(store, doc: str = None) -> list:
    """Every line the readers read, as note-shaped dicts: {Note, Scope, ScopeKey, Source, MemoryId, Key, Section}. MemoryId is the line's
    place in the document - a later line is the newer word, and breaks a tie the same way."""
    from .learnedgraph import TAG
    doc = store.get_doc('learned') if doc is None else doc
    out, i = [], 0
    for slug, head in lc.SECTIONS.items():
        for raw, k in lc.lines(doc or '', head):
            i += 1
            scope, key = scope_of(raw)
            own = not TAG.match(raw)
            # the note's own words, as the owner gave them - what it is about is Scope/ScopeKey
            out.append({'Note': ABOUT.sub('', text_of(raw)).strip(), 'Scope': scope, 'ScopeKey': key, 'Source': 'verdict' if family(raw) else 'owner' if own else 'learned',
                        'MemoryId': i, 'Key': k, 'Section': slug, 'Own': own, 'Active': 1})
    return out


def standing(store, doc: str = None) -> list:
    """The note-shaped lines a message's readers hold it against (ingest.applicable_notes): every line about one sender, domain, topic or
    mailbox, and the owner's own general lines on what they care about. The reflection's general lines reach their readers by
    learned_cut, not here."""
    return [n for n in notes(store, doc) if n['Scope'] != 'global' or (n['Own'] and n['Section'] == 'care')]


# ── the notes table, drained and dropped ──────────────────────────────────────────────────────────────────────────────────────────────
def _table(store) -> bool:
    return bool(store._one("SELECT 1 FROM sqlite_master WHERE type='table' AND name='memory'"))


def migrate(store) -> int:
    """Every row of the old notes table not yet in LEARNED.md, written there once - the owner's typed notes and their verdicts, global
    ones too, so nothing they wrote is lost - and then the table is dropped (the owner, 2026-10-27: "we don't need it"). Idempotent: a
    row already written (APPLIED) is not written again, a line already there is not written twice, and with the table gone there is
    nothing left to do. A switched-off row was the owner saying "not this" - it is not brought back. Returns the lines written."""
    _mutes(store)
    if not _table(store): return 0
    try: done = int(store.get_setting(APPLIED) or 0)
    except ValueError: done = 0
    rows = store._rows('SELECT * FROM memory WHERE MemoryId>? ORDER BY MemoryId', (done,))
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
    # ...the lines are saved before the table goes: a crash between the two leaves rows already marked written, never rows lost
    store._exec('DROP TABLE IF EXISTS memory')
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
