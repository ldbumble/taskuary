"""THE OWNER'S HAND ON THE MEMORY - Keep, Wrong, Forget, a fact said, a fact that stopped being true, and who someone is to them.

One road for every surface that corrects what Taskuary knows about how the owner works: Settings' What changed and Visualize (slice 6
of the memory redesign, the owner's ruling 2 of 2026-10-23: "Keep / Wrong / Forget on See what changed") and the Assistant's memory
tools (slice 7: "Gail moved to Ops", "forget that Ray does payroll", "who's Gail to me" - all approved by the owner, 2026-10-25).

    keep     a learned line is the owner's now: in use, in their words, never reworded or decayed by a machine write
    wrong    a learned line was never true: out of the document, a tombstone no reflection writes back (learnedlines.guard)
    forget   out of the document; it comes back only if its evidence grows GROW-fold (the owner said "not now", not "never")
    remember a fact in the owner's own words, an untagged line in its section - in use at once, as anything they type there is
    close    a fact that STOPPED being true: kept as history with the day it ended (ValidTo), never deleted, never written back
    about    every line that names a person - by address, or by the name the line or the org chart gives them

Every write goes through store.save_doc('learned', ..., 'owner'), so learnedlines.sync records it as the owner's hand. Nothing here
calls a model: it works with no AI connected."""
import re
from datetime import datetime
from . import learned_cut as lc
from .learnedgraph import TAG, fmt, lines as tagged, walk

DOC, HOW = 'learned', ('keep', 'wrong', 'forget')
YOURS = "That line is yours - you wrote it, so it is not something Taskuary learned wrong. Forget takes it out."
KEPT = 'That line is already yours - it stays as you wrote it.'
GONE = 'That line changed since this page was drawn - it is shown again as it is now.'


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def _bare(raw: str) -> str: t = raw.strip(); return t[2:].strip() if t.startswith(('- ', '* ')) else t


def find(doc: str, key: str) -> tuple:
    """(raw line, parsed line, the owner's own?) for `key` - a tagged line anywhere, else an untagged line of the owner's in one of the
    five sections; (None, None, False) when the document has neither."""
    for raw, l in walk(doc):
        if l and l['key'] == key: return raw, l, False
    for slug, head in lc.SECTIONS.items():
        for raw, k in lc.lines(doc, head):
            if k == key and not TAG.match(raw): return raw, {'key': k, 'text': _bare(raw), 'section': head[3:], 'ev': [], 'status': 'live'}, True
    return None, None, False


def _without(doc: str, raw: str) -> str: return doc.replace(raw + '\n', '', 1) if raw + '\n' in doc else doc.replace(raw, '', 1)


def _save(store, old: str, new: str):
    from .learnedgraph import record
    store.save_doc(DOC, new, 'owner'); record(store, old, new, 'owner')


def _row(store, key: str) -> dict: return store._one('SELECT * FROM learned_line WHERE Key=?', (key,)) or {}


def mark(store, key: str, how: str) -> dict:
    """Keep, Wrong or Forget one line, by its key. {ok, key, how, text}; ValueError (in plain words) when the line cannot take it."""
    from .learn import _under, PEOPLE, ADOPT_UNDER, adopt
    if how not in HOW: raise ValueError(f'say keep, wrong or forget - not {how!r}')
    doc = store.get_doc(DOC) or ''
    raw, l, own = find(doc, key)
    r = _row(store, key)
    if not raw and not r: raise LookupError(GONE)
    if own and how == 'wrong': raise ValueError(YOURS)
    if own and how == 'keep': raise ValueError(KEPT)
    text = (l or {}).get('text') or r.get('OwnerText') or r.get('Text') or ''
    if how == 'keep':
        if raw and l['status'] != 'live': adopt(store, key, 'owner'); doc = store.get_doc(DOC) or ''
        elif not raw:                                   # a line that faded or was put down, brought back as the owner's
            back = fmt({'text': text, 'score': int(r.get('Score') or 4), 'ev': [e for e in str(r.get('Ev') or '').split(',') if e],
                        'seen': _now()[:10], 'key': key})
            head = lc.SECTIONS.get(r.get('Reader')) or (PEOPLE if lc.subject_of(text) else ADOPT_UNDER)
            _save(store, doc, _under(doc, head, back)); doc = store.get_doc(DOC) or ''
        store._exec("UPDATE learned_line SET OwnerText=?, Status='in_use', InUseAt=IFNULL(InUseAt, ?), UpdatedAt=? WHERE Key=?", (text, _now(), _now(), key))
        store.add_learned_event(key, text, 'live', int(r.get('Score') or (l or {}).get('score') or 0), '', 'kept', 'owner')
    else:
        if how == 'wrong' and r: store._exec("UPDATE learned_line SET Status='wrong', UpdatedAt=? WHERE Key=?", (_now(), key))
        if raw: _save(store, doc, _without(doc, raw))
        if own:
            store.add_learned_event(key, text, 'live', 0, '', 'forgotten', 'owner')
            # ...and a verdict's line Forgotten no longer counts as the owner having said it (memorylines.lessons reads the document), and
            # what it fed is withdrawn: the id of what the verdict was given on leaves every learned line's evidence (learn.withdraw)
            from .learn import withdraw
            for h in store._rows("SELECT DISTINCT Ev FROM learned_history WHERE Action='said' AND Actor LIKE 'verdict:%' AND Text=? AND IFNULL(Ev,'')<>''",
                                 (raw.strip(),)):
                withdraw(store, h['Ev'])
        elif how == 'wrong' or not raw:
            # Wrong is final; Forget of a line already out of the document is a tombstone with its evidence counted (sync did it for one in it)
            st, ev = ('wrong', None) if how == 'wrong' else ('forgotten', len([e for e in str(r.get('Ev') or '').split(',') if e]))
            store._exec('UPDATE learned_line SET Status=?, InDoc=0, ForgotEv=IFNULL(?, ForgotEv), UpdatedAt=? WHERE Key=?', (st, ev, _now(), key))
            store.add_learned_event(key, text, (l or {}).get('status') or 'live', 0, '', 'wrong' if how == 'wrong' else 'forgotten', 'owner')
        # ...and every task whose Advisor line rested on it says so no more (the Advisor audit's judge, 2026-10-26: Wrong on "You answer
        # Erin the same day" left her task saying her usual): their decisions are re-read now, without the line
        from . import advisor
        advisor.forgot(store, lc.cite_of(key), (l or {}).get('ev') or [e for e in str(r.get('Ev') or '').split(',') if e])
    return {'ok': True, 'key': key, 'how': how, 'text': text}


STYLE = 'style'                 # memory.remember's section for a writing rule: STYLE.md, not LEARNED.md


def remember(store, text: str, about: str = '', section: str = '', replaces: str = '') -> dict:
    """A fact in the owner's own words, under the section it belongs in - `section` a slug (people, care, work, promises, bring), else
    Your people when it names someone (`about`, or an address in it) and What you care about otherwise. `replaces`: the key of a line it
    makes untrue, closed with today's date first ("Gail moved to Ops" closes "Gail runs headcount in Finance"). In use at once."""
    from .learn import _under
    from .concierge import redact               # a token typed into a fact never lands in the memory every prompt reads
    t = redact(' '.join(str(text or '').split()).lstrip('-* ').strip())
    if not t: raise ValueError('say the fact to remember')
    # a rule about HOW to write is the writing style's, not LEARNED.md's: STYLE.md's Owner notes, where an edited draft's note goes and
    # every draft reads (responder.style_feedback) - the model names the section by what the fact is (2026-10-28)
    if section == STYLE:
        from .responder import style_feedback
        style_feedback(store, t, 'owner')
        return {'ok': True, 'text': t, 'section': STYLE, 'title': 'your writing style', 'doc': 'style', 'closed': None}
    who = str(about or '').strip().lower()
    if who and '@' in who and who not in t.lower(): t = f'{t} ({who})'
    slug = section if section in lc.SECTIONS else 'people' if (who or lc.subject_of(t)) else 'care'
    closed = close(store, replaces) if replaces else None
    doc = store.get_doc(DOC) or ''
    raw = f'- {t}'
    if raw in doc.splitlines(): return {'ok': True, 'text': t, 'section': slug, 'already': True, 'closed': closed}
    _save(store, doc, _under(doc, lc.SECTIONS[slug], raw))
    store.add_learned_event(_key(t), t, 'live', 0, '', 'said', 'owner')
    return {'ok': True, 'text': t, 'section': slug, 'title': lc.TITLE[slug], 'closed': closed}


def _key(text: str) -> str:
    from .learnedgraph import _key as k
    return k(text)


def close(store, key: str) -> dict:
    """A fact that stopped being true: out of the document, its row closed with today's date - history, never a tombstone of a lie."""
    doc = store.get_doc(DOC) or ''
    raw, l, own = find(doc, key)
    r = _row(store, key)
    if not raw and not r: raise LookupError(GONE)
    text = (l or {}).get('text') or r.get('Text') or ''
    if raw: _save(store, doc, _without(doc, raw))
    today = _now()[:10]
    if r: store._exec("UPDATE learned_line SET Status='closed', ValidTo=?, InDoc=0, UpdatedAt=? WHERE Key=?", (today, _now(), key))
    store.add_learned_event(key, text, 'closed', 0, '', 'closed', 'owner')
    return {'key': key, 'text': text, 'until': today}


def _names(store, who: str) -> set:
    """The ways a line may name `who`: their address, and the name the org chart or their own mail gives them (lowercased)."""
    w = ' '.join(str(who or '').split()).lower()
    if not w: return set()
    out = {w}
    if '@' in w:
        m = store._one("SELECT FromName FROM message WHERE lower(FromEmail)=? AND IFNULL(FromName,'')<>'' ORDER BY MessageId DESC LIMIT 1", (w,))
        if m: out.add(' '.join(str(m['FromName']).split()).lower())
    else:
        for m in store._rows("SELECT DISTINCT lower(FromEmail) e FROM message WHERE lower(FromName)=? OR lower(FromName) LIKE ? LIMIT 3", (w, f'{w} %')):
            if m['e']: out.add(m['e'])
    try:
        from . import orgchart
        for p in orgchart.chart(store):
            n, e = str(p.get('name') or '').lower(), str(p.get('email') or '').lower()
            if w in (n, e) or (n and n.split()[0] == w): out |= {x for x in (n, e) if x}
    except Exception: pass
    return out


def about(store, who: str) -> dict:
    """{who, lines: [{key, text, section, own, status}], relation}: every line in use or waiting that names this person, by address or
    name, and what the org chart says they are to the owner - the answer to "who's Gail to me", read, never guessed."""
    doc, names = store.get_doc(DOC) or '', _names(store, who)
    hit = lambda t: any(re.search(rf'(?<![\w@.]){re.escape(n)}(?![\w@])', t.lower()) for n in names)
    # ...and the address a line gives a name ("Gail Moreno (gail@...)"), so her other lines are found by it too
    names |= {a for _, head in lc.SECTIONS.items() for raw, _k in lc.lines(doc, head) if hit(raw) for a in lc.names(raw)}
    out = []
    for slug, head in lc.SECTIONS.items():
        for raw, k in lc.lines(doc, head):
            m = TAG.match(raw)
            t = m.group('text').strip() if m else _bare(raw)
            if hit(t): out.append({'key': k, 'text': t, 'section': lc.TITLE[slug], 'own': not m, 'status': 'in use'})
    out += [{'key': l['key'], 'text': l['text'], 'section': 'Watching', 'own': False, 'status': 'watching'}
            for l in tagged(doc) if l['status'] == 'hypothesis' and hit(l['text'])]
    rel = ''
    try:
        from . import orgchart
        rel = next((orgchart.relation_of(store, n) for n in names if '@' in n and orgchart.relation_of(store, n)), '') or ''
    except Exception: pass
    return {'who': who, 'names': sorted(names), 'relation': rel, 'lines': out}
