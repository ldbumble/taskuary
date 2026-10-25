"""THE LINE STORE behind LEARNED.md (phase C of the Advisor and memory design, 2026-10-23).

The document was its own only record: a line the owner deleted was simply gone, so the next reflection could write it straight
back, a rephrase was a new line, and the opener counted every rebirth as something learned ("Learned this week: 32"). Now every
tagged line has a row, keyed by its `k:` - the section it sits in (Reader holds its slug: people, care, work, promises, bring, or
watching / proposed; learned_cut.READS says who reads each), whom it is about (Subject), its status on the one ladder (watching ->
in_use; wrong and forgotten are tombstones, closed a fact that stopped being true, retired a press count the redesign took out), the
owner's own wording when they changed it, and when it first went into use. LEARNED.md stays the readable, editable face of the in-use lines; this is what makes an edit
there stick (the owner, 2026-10-23: hand edits are recorded and stick, tombstones stop the reflection writing a line back).

Every write reaches here through store.save_doc('learned') - the owner's editor, the hot pass, the reflection - and guard() runs on
every machine write before it is saved (learn.settle)."""
from datetime import datetime, timedelta
from loguru import logger

# the passes that write LEARNED.md by themselves; any other actor is the owner's hand (the editor, Adopt)
MACHINE = frozenset(('learn', 'reflect', 'verdicts', 'decay', 'owner-verdicts', 'template', 'seed', 'migrate', 'withdraw',
                     'voice', 'system', 'settle'))
GROW = 3        # a line the owner removed comes back only once its evidence is this many times what it had (the design, 2.3)
STATUSES = ('watching', 'in_use', 'wrong', 'forgotten', 'closed', 'retired')


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')


def section_of(l: dict) -> str:
    """Where a line sits, as its slug: one of the five subjects (learned_cut.SECTIONS), 'watching' or 'proposed' while it waits, else
    'other' (a heading the owner made). Who reads it is the reader matrix's to say (learned_cut.readers_of), never the line's."""
    from .learned_cut import slug_of
    if l.get('status') == 'hypothesis': return 'watching'
    if l.get('status') == 'proposed': return 'proposed'
    return slug_of(l.get('section')) or 'other'


def rows(store, status: str = None) -> list:
    return store._rows('SELECT * FROM learned_line' + (' WHERE Status=?' if status else '') + ' ORDER BY Key', (status,) if status else ())


def row(store, key: str) -> dict: return store._one('SELECT * FROM learned_line WHERE Key=?', (key,)) or {}


def sync(store, old: str, new: str, actor: str):
    """Record what one save did to the lines. The owner's hand: a line they removed is a tombstone (forgotten), a line they reworded
    keeps their words, a line they moved into a reader's section is in use. A machine write: each line's status follows its place,
    and one that left the document is watching again - its key and history kept, never deleted and born again. Never raises."""
    try:
        from .learnedgraph import lines
        from .learned_cut import subject_of
        owner, now = actor not in MACHINE, _now()
        before, after = {l['key']: l for l in lines(old)}, {l['key']: l for l in lines(new)}
        have = {r['Key']: r for r in rows(store)}
        for k, l in after.items():
            r, st = have.get(k) or {}, 'in_use' if l['status'] == 'live' else 'watching'
            if r.get('Status') in ('wrong', 'retired') and not owner: continue    # guard() keeps it out; nothing a machine writes revives it
            mine = owner and k in before and before[k]['text'] != l['text']
            store._exec('INSERT INTO learned_line (Key,Reader,Text,OwnerText,Status,Score,Ev,InDoc,InUseAt,ForgotEv,Source,UpdatedAt,Subject) '
                        'VALUES (?,?,?,?,?,?,?,1,?,?,?,?,?) ON CONFLICT(Key) DO UPDATE SET Reader=excluded.Reader, Text=excluded.Text, '
                        'OwnerText=excluded.OwnerText, Status=excluded.Status, Score=excluded.Score, Ev=excluded.Ev, InDoc=1, '
                        'InUseAt=excluded.InUseAt, UpdatedAt=excluded.UpdatedAt, Subject=excluded.Subject',
                        (k, section_of(l), l['text'], l['text'] if mine else r.get('OwnerText'), st, l['score'], ','.join(l['ev']),
                         r.get('InUseAt') or (now if st == 'in_use' else None), r.get('ForgotEv'), actor, now, subject_of(l['text'])))
            if mine: store.add_learned_event(k, l['text'], l['status'], l['score'], '', 'edited', actor)
        for k, o in before.items():
            if k in after: continue
            r = have.get(k) or {}
            if owner:
                store._exec('UPDATE learned_line SET Status=?, InDoc=0, ForgotEv=?, UpdatedAt=? WHERE Key=?', ('forgotten', len(o['ev']), now, k))
                store.add_learned_event(k, o['text'], o['status'], 0, '', 'forgotten', actor)
            elif r.get('Status') not in ('wrong', 'forgotten', 'closed', 'retired'):
                store._exec("UPDATE learned_line SET Status='watching', InDoc=0, UpdatedAt=? WHERE Key=?", (now, k))
    except Exception as e:
        logger.warning(f'learned lines not recorded: {e}')


def guard(store, doc: str) -> str:
    """A machine write as it may land: no line the owner marked wrong, no press count the redesign retired, no line they removed unless
    its evidence has since grown GROW-fold, and the owner's wording wherever they reworded one."""
    rs = {r['Key']: r for r in store._rows("SELECT Key, Status, OwnerText, ForgotEv FROM learned_line WHERE Status IN ('wrong','forgotten','retired') "
                                            "OR IFNULL(OwnerText,'')<>''")}
    if not rs or not doc: return doc
    from .learnedgraph import walk, fmt
    out = []
    for raw, l in walk(doc):
        r = rs.get(l['key']) if l else None
        if r and r['Status'] in ('wrong', 'retired'): continue
        if r and r['Status'] == 'forgotten' and len(l['ev']) < GROW * max(1, int(r['ForgotEv'] or 0)): continue
        if r and r.get('OwnerText') and l['text'] != r['OwnerText']: raw = fmt({**l, 'text': r['OwnerText']})
        out.append(raw)
    return '\n'.join(out) + ('\n' if doc.endswith('\n') else '')


def in_use_since(store, since: str) -> list:
    """The lines that went into use on or after `since` and are in use now - each key once, however often it was rewritten."""
    return store._rows("SELECT * FROM learned_line WHERE Status='in_use' AND (InDoc=1 OR Reader='drafter') AND InUseAt>=? AND InUseAt<>'-' "
                       "ORDER BY InUseAt DESC", (since,))


def week(store, now: datetime = None) -> list: return in_use_since(store, ((now or datetime.now()) - timedelta(days=7)).strftime('%Y-%m-%d'))
