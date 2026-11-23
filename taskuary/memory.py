"""THE OWNER'S MEMORY: THREE STORES, ONE ROAD IN AND ONE ROAD OUT (the memory redesign, r10, 2026-11-23).

It was fourteen modules - sections, tags, strength gates, a Watching area - and the walks found its seams: a rule about his meeting
hours filed under Your people reached no agent, a correction left both lines standing, one press taught a general rule as his word,
and his sign-off lived in two homes. Now there are three stores, told apart by WHOSE word a line is:

  fact      what is simply so about a person or a system: someone's place on his org chart, a promise in his sent mail, a sender his
            rule skips - read live from where it is kept (and from the ledger, `_ledger`, once redesign/r1-ledger lands), never copied
  said      what HE said, in his words: his rules, his hours, who handles what now. One line per SUBJECT - a correction on the same
            subject replaces the line before it (the subject the model names, never a match of the words). In use at once, everywhere
  inferred  what was learned from what he DID - a verdict, a reflection over his episodes - with its evidence and how often it was seen.
            Never shown or used as his word. It goes into use BY ITSELF once his own acts bear it out - AUTO_AT distinct episodes, or a
            press "like this, from now on" - and never by asking him (the owner, 2026-11-23: "we don't want to have to confirm manually").
            Wrong or Forget takes it down at once; an act that goes against it weakens it (`weaken`)

Memory is SHORT - conclusions (how he works, who handles what, his rules, his preferences), never records: those are the ledger's and
the Hub's. A learned line is one sentence (MAX_WORDS); at most PER_ABOUT are kept about one person or topic and CAP in use in all, LEARNING
still being seen - past them the line least recently borne out falls out first (`_trim`).

How he writes is read from his sent mail (STYLE.md, learning.style_ws) and from what he said; his signature has ONE home, the
`email_signature` setting (signatures.keep writes it, the Memory page shows it among what he said).

Out: `for_task` is what rides into an agent's or a draft's context - everything he said that bears on it (every general line, every line
about the people on it), the facts about those people, and the inferred lines he confirmed. `whole` is the same for a reader that decides
on all of it (triage, the routing judge, the Assistant). `lookup` and `remember` are the agent's two tools. `page` is the Memory page.
LEARNED.md is the stores' readable face (`render`), written from them. Nothing here calls a model."""
import json, re
from datetime import datetime, timedelta
from loguru import logger

DOC, BACKUP = 'learned', 'learned-before-r10'       # LEARNED.md, the stores' face; and the document as it stood before them, kept whole
FACT, SAID, INFERRED = 'fact', 'said', 'inferred'
LIVE, DOWN = 'live', ('replaced', 'wrong', 'forgotten', 'closed', 'dropped')
WHOLE_CAP = 60_000            # ~15k tokens: past it the learned lines about one sender or topic go first, oldest first
TASK_CAP = 6_000              # the confirmed learned lines a task's context carries; what he said rides whole
MIGRATED = 'memory_r10'       # the setting that says LEARNED.md was read into the stores
IN_USE_FIX = 'memory_r10_in_use'   # ...and that the lines in use before r10 were put back in use (its first cut left them waiting on a press)
AUTO_AT = 3                   # distinct episodes of his own acts that put a learned line in use - LEARNED.md's bar from the beginning
CAP, LEARNING, PER_ABOUT = 60, 30, 6    # learned lines in use (about what LEARNED.md held), still being seen, and about one person or topic
MAX_WORDS = 30                # a conclusion is one sentence; a longer line is a record, and records are the ledger's
_ADDR = re.compile(r'[\w.+-]+@[\w-]+(?:\.[\w-]+)+')
SCOPE_SAYS = {'sender': '{}', 'sender_domain': 'anyone at {}', 'subject': 'the topic "{}"', 'source': 'mail arriving on "{}"'}
YOURS = "That line is yours - you said it, so it is not something Taskuary learned wrong. Forget takes it out."
GONE = 'That line changed since this page was drawn - it is shown again as it is now.'


def _now(): return datetime.now().strftime('%Y-%m-%d %H:%M:%S')
def subject_of(s) -> str:
    "What a line is about, as one key: case, spacing and punctuation apart - the model names it, this only makes two spellings one."
    return ' '.join(re.findall(r"[a-z0-9@.'+-]+", str(s or '').lower())).strip(" .'-")
def names(text) -> set: return {a.lower() for a in _ADDR.findall(str(text or ''))}
def cite_of(key) -> str: return f'lrn{key}'          # the id triage.note_id reads back
def _key(text: str) -> str:
    "A subject for a line that came with none (LEARNED.md's own lines, read in once): its first eight significant words."
    return ' '.join([w for w in re.findall(r'[a-z0-9]+', str(text or '').lower()) if len(w) > 3][:8])


def people_of(msg: dict) -> set:
    """Everyone on a mail: its sender and its To and Cc, lowercased (an ingest dict or a message row)."""
    m, rec = msg or {}, (msg or {}).get('RecipientsJson')
    try: rec = json.loads(rec) if isinstance(rec, str) else rec
    except ValueError: rec = None
    to, cc = (m.get('to') or (rec or {}).get('to') or []), (m.get('cc') or (rec or {}).get('cc') or [])
    return {str(a).strip().lower() for a in [m.get('from_email') or m.get('FromEmail'), *to, *cc] if a and '@' in str(a)}


# ── the rows ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _row(r: dict) -> dict:
    r = dict(r)
    r['people'] = [p for p in str(r.get('People') or '').split(',') if p]
    r['ev'] = [e for e in str(r.get('Ev') or '').split(',') if e]
    r['key'] = str(r['Id'])
    return r


def rows(store, kind: str = None, live: bool = True) -> list:
    """The store's lines, oldest first. `store.memory_until` (an evaluation's view of the past, evalset._AsOf) hides the later ones."""
    q, a = 'SELECT * FROM memory_line WHERE 1=1', []
    if kind: q += ' AND Kind=?'; a.append(kind)
    if live: q += " AND Status='live'"
    if (until := getattr(store, 'memory_until', None)): q += ' AND At<?'; a.append(until)
    return [_row(r) for r in store._rows(q + ' ORDER BY Id', tuple(a))]


def in_use(store) -> list:
    "What every reader may lean on: what he said, and what was learned that his own acts bore out."
    return [r for r in rows(store) if r['Kind'] == SAID or r['Confirmed']]


def get(store, key) -> dict:
    """One line by its key (its id) - else by its subject, else by its own words (the Assistant names a line by what it says: TQ-1251)."""
    k = str(key or '').strip()
    if k.isdigit() and (r := store._one('SELECT * FROM memory_line WHERE Id=?', (int(k),))): return _row(r)
    for r in reversed(rows(store)):
        if subject_of(r['Subject']) == subject_of(k) or _same(r['Text'], k): return r
    return {}


def _same(a, b) -> bool:
    said = lambda x: re.sub(r'\s*\([^()\s]+@[^()\s]+\)$', '', ' '.join(str(x or '').lower().split()).rstrip('.')).lstrip('-* ').rstrip('.')
    return said(a) == said(b)


def _add(store, kind, text, subject, people=(), scope='global', key='', ev=(), confirmed=False, source='', workstream='') -> int:
    return store._exec('INSERT INTO memory_line (Kind,Subject,Text,People,Scope,ScopeKey,Ev,N,Confirmed,Status,Source,Workstream,At,UpdatedAt) '
                       'VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?)',
                       (kind, subject_of(subject), text, ','.join(sorted({p for p in people if p})), scope or 'global', key or '',
                        ','.join(dict.fromkeys(ev)), max(1, len(set(ev))), int(bool(confirmed)), LIVE, source, workstream or '', _now(), _now()))


def _down(store, rid, status, by=None):
    store._exec('UPDATE memory_line SET Status=?, ReplacedBy=?, UpdatedAt=? WHERE Id=?', (status, by, _now(), int(rid)))


# ── what he said ─────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def owner_names(store) -> set:
    "The ways a line or an `about` names the owner himself: his name, his first name, his addresses (lowercased) - facts, never a guess."
    o = store.owner()
    n = ' '.join(str(o.get('owner') or '').split()).lower()
    out = {n, n.split()[0]} if n and n != 'the owner' else set()
    try:
        from .ingest import own_addresses
        out |= {a for a in own_addresses(store) if a}
    except Exception: pass
    return out | ({str(o['owner_email']).strip().lower()} if o.get('owner_email') else set())


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


def recipient(store, about: str) -> str:
    """The one address a person is kept under - an address or domain as given, else the one a name finds in their mail or the org chart.
    ValueError when the name finds none, or several (the model asks which)."""
    w = ' '.join(str(about or '').split()).lower()
    if '@' in w or re.fullmatch(r'[\w-]+(\.[\w-]+)+', w): return w
    hits = sorted(n for n in _names(store, w) if '@' in n)
    if not hits: raise ValueError(f'No address is known for {about!r} - say their address, and it is kept for them.')
    if len(hits) > 1: raise ValueError(f"{about!r} is more than one person here ({', '.join(hits[:4])}) - say which address.")
    return hits[0]


SUBJECT_WORDS = ('`subject`: what it is about, in a few words ("meeting hours", "who handles payroll questions", "Gail\'s role") - the same '
                 'subject as a line it corrects, which it then replaces; a new subject is a new line')


def remember(store, text: str, subject: str = '', about: str = '', actor: str = 'owner', signature: bool = False, doc: str = '') -> dict:
    """THE ONE ROAD FOR WHAT THE OWNER SAID - the Assistant's memory.remember, every agent's remember tool, the Memory page. His words,
    kept as said; `subject` names what it is about, and the newest word on a subject stands: the line before it on that subject - his own
    or one Taskuary learned - is replaced, kept as history. `about`: the person it is about (a name or an address); a line about the owner
    himself, or nobody, is general and rides into every task. In use at once. {ok, key, text, subject, replaced, already}.
    `signature`: the words ARE how he signs - kept in the signature's one home, the saved signature every email carries (signatures.keep;
    the walk, 2026-11-21: kept as a memory line, "Best, Alex" never reached a card). {ok, text, signature: True}.
    `doc` soul or counsel: who he IS, or how the Assistant speaks to him - appended to that document of his (told)."""
    if signature:
        from .signatures import keep
        return {'ok': True, 'text': keep(store, str(text or ''), actor), 'signature': True, 'subject': 'signature', 'replaced': None}
    from .concierge import redact               # a token typed into a fact never lands in the memory every prompt reads
    t = redact(' '.join(str(text or '').split()).lstrip('-* ').strip())
    if not t: raise ValueError('say the fact to remember')
    if doc: return told(store, doc, t, actor)
    subject = subject if subject_of(subject) else (_key(t) or t.lower())        # ...none named: a line of its own, which only its own words correct
    w = ' '.join(str(about or '').split()).lower()
    me = owner_names(store)
    who = '' if not w or w in me else w
    if who and '@' not in who:
        try: who = recipient(store, who)
        except ValueError: pass                 # ...a name no address is known for is kept as the name
    people = (names(t) - me) | ({who} if who else set())
    olds = [r for r in rows(store) if r['Kind'] in (SAID, INFERRED) and subject_of(r['Subject']) == subject_of(subject)]
    # ...SAID AGAIN IS NOT SAID TWICE (the owner, 2026-11-14: "be careful not to make the memory file too big"), whatever subject it came with
    if (same := next((r for r in rows(store, SAID) if _same(r['Text'], t)), None)):
        return {'ok': True, 'key': same['key'], 'text': t, 'subject': same['Subject'], 'already': True, 'replaced': None}
    rid = _add(store, SAID, t, subject, people, source=actor)
    for r in olds: _down(store, r['Id'], 'replaced', rid)
    render(store)
    gone = next((r['Text'] for r in reversed(olds)), None)
    return {'ok': True, 'key': str(rid), 'text': t, 'subject': subject_of(subject), 'replaced': gone, 'already': False}


def has_said(store, text: str) -> bool:
    "Whether a line he said already says `text` - the same words, whatever the case, the spacing or a closing full stop."
    return any(_same(r['Text'], text) for r in rows(store, SAID))


TOLD_DOCS, TOLD = ('soul', 'counsel'), '## Told to the Assistant'
TOLD_INTRO = '<!-- what you told the Assistant to keep here, in your words; yours to edit or delete -->'
DOC_READS = {'soul': 'read by triage · drafts · the Assistant · agents · the digest', 'counsel': 'read by the Assistant · the morning brief'}


def told(store, doc: str, text: str, actor: str = 'owner') -> dict:
    """Who the owner IS (SOUL.md) and how the Assistant speaks to him (COUNSEL.md): one line appended under TOLD, outside every generated
    block, never a rewrite - his own documents, read by their own readers. The audit row keeps the document as it was before."""
    from pathlib import Path
    if doc not in TOLD_DOCS: raise ValueError(f'the chat writes only {" or ".join(TOLD_DOCS)} - not {doc!r}')
    old = store.get_doc(doc)
    if not (old or '').strip(): old = (Path(__file__).parent / 'templates' / f'{doc}.md').read_text(encoding='utf-8')
    line = f'- {text}'
    if line in old.splitlines(): return {'ok': True, 'text': text, 'doc': doc, 'already': True, 'title': f'{doc.upper()}.md'}
    if TOLD in old:
        head, rest = old.split(TOLD, 1)
        parts = rest.split('\n## ', 1)
        new = head + TOLD + parts[0].rstrip('\n') + '\n' + line + '\n' + ('\n## ' + parts[1] if len(parts) > 1 else '')
    else: new = old.rstrip('\n') + f'\n\n{TOLD}\n{TOLD_INTRO}\n{line}\n'
    store.save_doc(doc, new, actor)
    store.audit('doc', 0, 'assistant_told', actor, detail={'doc': doc, 'line': text[:400], 'before': old})
    return {'ok': True, 'text': text, 'doc': doc, 'title': f'{doc.upper()}.md'}


# ── what was inferred ────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def infer(store, text: str, subject: str, ev=(), people=(), scope: str = 'global', key: str = '', source: str = 'learn',
          confirmed: bool = False) -> dict:
    """A line learned from what the owner did. The same subject learned again is the same line with more evidence - its newest words,
    until it is in use. In use by itself at AUTO_AT distinct episodes, or at once when `confirmed` (his press "from now on"). Never over
    what he said on that subject, never over a line he marked Wrong, never a record (past MAX_WORDS). {} when not written."""
    t = ' '.join(str(text or '').split()).lstrip('-* ').strip()
    sk, ev = subject_of(subject), [e for e in dict.fromkeys(str(e).strip() for e in ev or ()) if e]
    if not t or not sk or len(t.split()) > MAX_WORDS: return {}
    if store._one("SELECT 1 x FROM memory_line WHERE Kind=? AND Status='wrong' AND (Subject=? OR lower(Text)=?)", (INFERRED, sk, t.lower())): return {}
    if any(r['Kind'] == SAID and subject_of(r['Subject']) == sk for r in rows(store, SAID)): return {}
    ppl = set(people or ()) | names(t) | ({key.lower()} if scope == 'sender' and key else set())
    hit = next((r for r in rows(store, INFERRED) if subject_of(r['Subject']) == sk), None)
    if hit:
        more = [e for e in ev if e not in hit['ev']]
        if not more and (hit['Confirmed'] or not confirmed): return hit
        allev, used = hit['ev'] + more, hit['Confirmed'] or confirmed or hit['N'] + len(more) >= AUTO_AT
        store._exec('UPDATE memory_line SET Text=?, Ev=?, N=N+?, Confirmed=?, People=?, UpdatedAt=? WHERE Id=?',
                    (hit['Text'] if hit['Confirmed'] else t, ','.join(allev), len(more), int(bool(used)),
                     ','.join(sorted(set(hit['people']) | ppl)), _now(), hit['Id']))
        return _settled(store, hit['Id'])
    try:
        from .workstreams import of_evidence
        ws = of_evidence(store, ev)
    except Exception: ws = ''
    return _settled(store, _add(store, INFERRED, t, sk, ppl, scope, key, ev, confirmed or len(ev) >= AUTO_AT, source, ws))


def _settled(store, rid) -> dict:
    "A learned line written: the memory trimmed to its caps, LEARNED.md redrawn, and the line as it now stands ({} when it fell out)."
    _trim(store); render(store)
    r = _row(store._one('SELECT * FROM memory_line WHERE Id=?', (rid,)))
    return r if r['Status'] == LIVE else {}


def _about_of(r) -> str:
    "Whom or what a learned line is about, as one key - its scope key, else its people - '' for a general line."
    return str(r.get('ScopeKey') or '').lower() if r.get('Scope') != 'global' and r.get('ScopeKey') else ','.join(r['people'])


def _trim(store) -> int:
    """THE MEMORY STAYS SHORT (the owner, 2026-11-23: "don't write too much detail in memory, otherwise it's basically the hub"): of the
    learned lines in use at most CAP, of those still being seen LEARNING, and in each at most PER_ABOUT about one person or topic - past it
    the line least recently borne out goes first, the weaker of two seen at once. What he said is never trimmed. Returns the lines gone."""
    n = 0
    for used, cap in ((True, CAP), (False, LEARNING)):
        rs = sorted((r for r in rows(store, INFERRED) if bool(r['Confirmed']) == used), key=lambda r: (str(r['UpdatedAt']), r['N'], r['Id']))[::-1]
        per, kept = {}, 0
        for r in rs:
            a = _about_of(r)
            per[a] = per.get(a, 0) + 1
            if kept < cap and (not a or per[a] <= PER_ABOUT): kept += 1; continue
            _down(store, r['Id'], 'dropped'); n += 1
    return n


def weaken(store, subject: str, ev: str = '') -> dict:
    """An act of his that goes against a learned line (the model reads that it does, and names the line's subject): one episode less behind
    it - below AUTO_AT it is out of use until his acts bear it out again, at none it is gone. Never his own line. {} when none matched."""
    r = next((r for r in rows(store, INFERRED) if subject_of(r['Subject']) == subject_of(subject)), None)
    if not r: return {}
    if r['N'] <= 1: _down(store, r['Id'], 'dropped')
    else: store._exec('UPDATE memory_line SET N=N-1, Confirmed=? WHERE Id=?', (int(bool(r['Confirmed']) and r['N'] - 1 >= AUTO_AT), r['Id']))
    logger.info(f"memory: {ev or 'an act'} went against the learned line on {r['Subject']!r}")
    render(store)
    return _row(store._one('SELECT * FROM memory_line WHERE Id=?', (r['Id'],)))


def withdraw(store, ev: str) -> int:
    """A verdict undone, or the line it taught put down, takes back what it fed: its id leaves every learned line's evidence, a line with
    none left goes, and the correction triage reads as evidence of the same press goes with it. Returns the lines touched."""
    ev = str(ev or '').strip()
    if not ev: return 0
    if (on := re.fullmatch(r'(msg|task)(\d+)', ev)):
        store._exec(f"DELETE FROM correction WHERE {'MessageId' if on.group(1) == 'msg' else 'TaskId'}=?", (int(on.group(2)),))
    n = 0
    for r in rows(store, INFERRED):
        if ev not in r['ev']: continue
        rest = [e for e in r['ev'] if e != ev]
        if rest: store._exec('UPDATE memory_line SET Ev=?, N=MAX(1, N-1), UpdatedAt=? WHERE Id=?', (','.join(rest), _now(), r['Id']))
        else: _down(store, r['Id'], 'forgotten')
        n += 1
    if n: render(store)
    return n


def taught_on(store, src: str, kind: str = '') -> bool:
    "Whether a verdict on `src` (msg12, task7) taught a line that still stands - `kind` narrows it to one verdict."
    return any(src in r['ev'] and (not kind or r['Source'] == f'verdict:{kind}') for r in rows(store, INFERRED))


def lessons(store, since: str = '') -> list:
    "The lines the owner's verdicts taught since `since` that still stand, newest first: [{ev, kind, text, key, at}]."
    return [{'ev': (r['ev'] or [''])[0], 'kind': r['Source'].split(':', 1)[1], 'text': r['Text'], 'key': r['key'], 'at': r['At']}
            for r in reversed(rows(store, INFERRED)) if str(r['Source']).startswith('verdict:') and str(r['At']) >= (since or '')]


# ── the owner's hand: Keep, Wrong, Forget, No longer true ────────────────────────────────────────────────────────────────────────────
def mark(store, key, how: str) -> dict:
    """keep (he said a learned line is right - in use from now on; nothing asks him to), wrong (it was never true - never learned again), forget (out for now),
    ended (it was true and stopped: kept as history). His own line takes forget and ended only. ValueError in plain words; LookupError
    when the line is not there. {ok, key, how, text}."""
    how = {'confirm': 'keep', 'adopt': 'keep'}.get(how, how)
    if how not in ('keep', 'wrong', 'forget', 'ended'): raise ValueError(f'say keep, wrong, forget or ended - not {how!r}')
    if str(key) == 'signature': return _forget_signature(store, how)
    r = get(store, key)
    if not r: raise LookupError(GONE)
    if r['Kind'] == SAID and how in ('keep', 'wrong'):
        if how == 'keep': return {'ok': True, 'key': r['key'], 'how': how, 'text': r['Text'], 'already': True}
        raise ValueError(YOURS)
    if how == 'keep': store._exec('UPDATE memory_line SET Confirmed=1, UpdatedAt=? WHERE Id=?', (_now(), r['Id']))
    else:
        _down(store, r['Id'], {'wrong': 'wrong', 'forget': 'forgotten', 'ended': 'closed'}[how])
        if r['Kind'] == INFERRED and how in ('wrong', 'forget'):
            for e in r['ev']:
                if re.fullmatch(r'(msg|task)\d+', e): withdraw(store, e)
    render(store)
    return {'ok': True, 'key': r['key'], 'how': how, 'text': r['Text']}


def _forget_signature(store, how):
    if how != 'forget': raise ValueError('your signature is yours - Forget takes it off, Settings changes it')
    was = str(store.get_setting('email_signature') or '')
    store.set_setting('email_signature', '', 'owner')
    store.audit('setting', 0, 'signature_kept', 'owner', detail={'before': was, 'after': ''})
    return {'ok': True, 'key': 'signature', 'how': how, 'text': was}


# ── facts ────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────────
def _ledger(store, people) -> list:
    """THE SEAM FOR THE LEDGER (redesign/r1-ledger): what it knows about these people - a role, an address, a vendor id - as
    [{who, text, source: 'ledger'}]: the addresses he gave or mailed for them, read off the one record of what exists (ledger.rows)."""
    from . import ledger
    who = {str(p).lower() for p in people or [] if p}
    out = []
    try:
        for r in ledger.rows(store, kind='address', limit=400):
            subj, val = str(r.get('Subject') or '').lower(), str(r.get('Value') or '')
            if who and not (subj in who or val.lower() in who): continue
            out.append({'who': r.get('Subject') or val, 'text': f"{r.get('Subject') or ''} <{val}>".strip() if val else str(r.get('Subject')), 'source': 'ledger'})
    except Exception as e: logger.debug(f'memory: the ledger was not read - {e}')
    return out[:20]


PROMISE_DAYS, PROMISE_GRACE = 30, 14


def facts(store, people=None) -> list:
    """[{who, text, source}] - what is simply so about these people (None: everyone): their place on his org chart, the promises his own
    sent mail made them and has not kept yet, a sender his rule skips, and what the ledger knows. Read live, never copied."""
    want = None if people is None else {str(p).lower() for p in people if p}
    hit = lambda e: want is None or str(e or '').lower() in want
    out = []
    try:
        from . import orgchart
        for p in orgchart.chart(store):
            e = str(p.get('email') or '').lower()
            if e and hit(e) and (rel := orgchart.relation_of(store, e, p.get('name') or '')):
                out.append({'who': e, 'text': f"{p.get('name') or e} ({e}): {rel}", 'source': 'org chart'})
    except Exception as e: logger.debug(f'org chart facts: {e}')
    try:
        today = datetime.now()
        since, late = (today - timedelta(days=PROMISE_DAYS)).strftime('%Y-%m-%d'), (today - timedelta(days=PROMISE_GRACE)).strftime('%Y-%m-%d')
        from .workstreams import is_personal
        for v in store._rows("SELECT v.*, m.RecipientsJson FROM sent_verdict v JOIN message m ON m.MessageId=v.MessageId "
                             "WHERE v.Promise=1 AND IFNULL(v.DeliveredBy,'')='' AND m.SentAt>=? ORDER BY m.SentAt", (since,)):
            if (v.get('Due') and str(v['Due'])[:10] < late) or is_personal(store, mid=v['MessageId']): continue
            try: to = json.loads(v.get('RecipientsJson') or '{}') or {}
            except ValueError: to = {}
            to = to.get('to') if isinstance(to, dict) else to
            who = (to or [''])[0] if to else ''
            who = str((who.get('email') if isinstance(who, dict) else who) or '').lower()
            if not hit(who): continue
            out.append({'who': who, 'source': 'your sent mail', 'text': f"You told {who or 'them'} you'd {' '.join(str(v.get('What') or 'do it').split())[:160]}"
                        + (f" by {v['Due']}" if v.get('Due') else '')})
    except Exception as e: logger.debug(f'promise facts: {e}')
    try:
        for p in store.list_policies(active_only=True):
            e = str(p.get('Pattern') or '').lower()
            if p.get('Kind') == 'sender' and p.get('Action') == 'skip' and hit(e): out.append({'who': e, 'text': f'Mail from {e} is skipped - your rule', 'source': 'your rules'})
    except Exception as e: logger.debug(f'rule facts: {e}')
    return out + _ledger(store, want)


# ── out: what a reader is given ──────────────────────────────────────────────────────────────────────────────────────────────────────
def _about_suffix(r) -> str:
    k = ' '.join(str(r.get('ScopeKey') or '').split())
    return f" (about: {SCOPE_SAYS[r['Scope']].format(k)})" if k and r.get('Scope') in SCOPE_SAYS else ''


def said_line(r, subject: bool = False) -> str:
    "A line as a reader is given it: its words, whom or what it is about, and - for what he said - the subject a correction names."
    return f"- {r['Text']}{_about_suffix(r)}" + (f" [subject: {r['Subject']}]" if subject and r['Kind'] == SAID else '')


def _bears(r, who: set, doms: set, ws: str) -> bool:
    "A line about nobody is everyone's; one about people, theirs; one learned under another workstream, not this task's."
    if r['Kind'] == INFERRED and ws and r.get('Workstream') and r['Workstream'] != ws: return False
    if r.get('Scope') == 'sender_domain': return str(r.get('ScopeKey') or '').lower() in doms
    if r.get('Scope') in ('subject', 'source'): return False
    return not r['people'] or bool(set(r['people']) & who)


SAID_HEAD, FACT_HEAD, LEARNED_HEAD = "## What the owner said", '## Facts about the people on it', '## Learned from what he did, borne out by his own acts'
NEAR = 2                      # the lines about someone NOT on the task a task still takes, when their subject is its subject
def _stems(t) -> set: return {w[:5].rstrip('s') or w[:5] for w in re.findall(r'[a-z0-9][a-z0-9-]{3,}', _ADDR.sub(' ', str(t or '').lower()))}


def _near(store, topic: str, rs: list) -> set:
    """The keys of the NEAR lines about other people whose subject is this task's ("send payroll questions to Gail now", kept about Erin,
    on a vendor's payroll question where Erin is nobody - 2026-11-14): by meaning where an embedder says, else by two words they share - a
    ranking, never a verdict."""
    if not str(topic or '').strip() or not rs: return set()
    try:
        from . import textsim
        got = textsim.rank(store, topic, [(r['key'], f"{r['Subject']}: {r['Text']}") for r in rs], least=textsim.floor(store))
    except Exception: got = None
    if got is not None: return {k for k, _ in sorted(got, key=lambda x: -x[1])[:NEAR]}
    want = _stems(topic)
    hits = sorted(((len(want & _stems(f"{r['Subject']} {r['Text']}")), r['Id'], r['key']) for r in rs), reverse=True)
    return {k for n, _, k in hits[:NEAR] if n >= 2}


def for_task(store, people=(), workstream: str = '', target: str = '', topic: str = '') -> str:
    """THE ONE BLOCK THAT RIDES INTO A TASK (an agent's brief, a draft): everything the owner said that bears on it - every line about
    nobody, every line about the people on it, by address or name, and the few about others whose subject is the task's own (`topic`) -
    with the subject each is kept under; the facts about the people on it; and the learned lines he confirmed that bear on it, within
    TASK_CAP. '' when the memory holds nothing for it."""
    who = {str(p).lower() for p in people if p}
    for p in list(who): who |= _names(store, p) if '@' in p else set()
    doms = {p.rsplit('@', 1)[1] for p in who if '@' in p}
    live = in_use(store)
    off = [r for r in live if r['people'] and r.get('Scope') not in ('subject', 'source', 'sender_domain') and not _bears(r, who, doms, workstream)]
    near = _near(store, topic, off)
    rs = [r for r in live if _bears(r, who, doms, workstream) or r['key'] in near]
    said = [said_line(r, True) for r in rs if r['Kind'] == SAID]
    fs = [f"- {f['text']}" for f in facts(store, {p for p in who if '@' in p})] if who else []
    learned, n = [], 0
    for r in reversed([r for r in rs if r['Kind'] == INFERRED]):
        l = said_line(r)
        if n + len(l) > TASK_CAP: break
        learned.append(l); n += len(l) + 1
    parts = [(SAID_HEAD, said), (FACT_HEAD, fs), (LEARNED_HEAD, learned[::-1])]
    return '\n\n'.join(f'{h}\n' + '\n'.join(ls) for h, ls in parts if ls)


def whole(store, reader: str = 'triage', target: str = '', cap: int = WHOLE_CAP, people: bool = True, subject: bool = False) -> str:
    """Everything in use, in the order it was kept - for a reader that decides on all of it (triage, the routing judge, the Assistant).
    Lines about one sender or topic come too: triage weighs them for mail about that. Past `cap` the learned lines about one sender or topic
    go first, oldest first, said in the log; what he said is never left out. The same bytes for every mail while nothing changes.
    `people` False leaves out every line about someone (an evaluation's arm); `subject` names the subject of each line he said."""
    rs = [r for r in in_use(store) if people or not (r['people'] or r.get('Scope') == 'sender')]
    fs = [f"- {f['text']}" for f in facts(store)] if people else []
    used = sum(len(said_line(r)) + 1 for r in rs if r['Kind'] == SAID) + sum(len(l) + 1 for l in fs)
    scoped = lambda r: r['Kind'] == INFERRED and r.get('Scope') != 'global'
    keep, over = set(), 0
    for r in sorted((r for r in rs if r['Kind'] == INFERRED), key=lambda r: (scoped(r), -r['Id'] if scoped(r) else r['Id'])):
        n = len(said_line(r)) + 1
        if used + n > cap: over += 1; continue
        keep.add(r['Id']); used += n
    if over: logger.warning(f'{reader} read the memory without {over} learned line(s) about one sender or topic - past its {cap:,}-character cap')
    parts = [(SAID_HEAD, [said_line(r, subject) for r in rs if r['Kind'] == SAID]), ('## Facts', fs),
             (LEARNED_HEAD, [said_line(r) for r in rs if r['Id'] in keep])]
    return '\n\n'.join(f'{h}\n' + '\n'.join(ls) for h, ls in parts if ls)


def notes(store) -> list:
    """Every line in use, note-shaped for the readers that rank them against one message (ingest.relevant_notes): {Note, Scope, ScopeKey,
    Source, MemoryId, Key, Own, Active}."""
    return [{'Note': r['Text'], 'Scope': r.get('Scope') or 'global', 'ScopeKey': r.get('ScopeKey') or None, 'Own': r['Kind'] == SAID,
             'Source': 'owner' if r['Kind'] == SAID else 'verdict' if str(r['Source']).startswith('verdict:') else 'learned',
             'MemoryId': r['Id'], 'Key': r['key'], 'Active': 1, 'People': r['people']} for r in in_use(store)]


def standing(store) -> list:
    "The note-shaped lines a message is held against: every line about one sender, domain, topic or mailbox, and every general line he said."
    return [n for n in notes(store) if n['Scope'] != 'global' or n['Own']]


def bring(store) -> list:
    "What his verdicts on the Advisor's ideas taught that he confirmed - what is worth raising, and what is not."
    return [said_line(r) for r in in_use(store) if str(r['Source']).startswith('verdict:idea')]


def about(store, who: str) -> dict:
    """{who, names, relation, lines: [{key, text, kind, own, status}]}: every line that names this person, by address or name, and what the
    org chart says they are to the owner - the answer to "who's Gail to me", read, never guessed."""
    ns = _names(store, who)
    hit = lambda r: bool(set(r['people']) & ns) or any(re.search(rf'(?<![\w@.]){re.escape(n)}(?![\w@])', r['Text'].lower()) for n in ns)
    out = [{'key': r['key'], 'text': r['Text'], 'subject': r['Subject'], 'kind': r['Kind'], 'own': r['Kind'] == SAID,
            'status': 'in use' if r['Kind'] == SAID or r['Confirmed'] else 'still being learned'} for r in rows(store) if r['Kind'] != FACT and hit(r)]
    rel = ''
    try:
        from . import orgchart
        rel = next((x for n in ns if '@' in n and (x := orgchart.relation_of(store, n))), '') or ''
    except Exception: pass
    return {'who': who, 'names': sorted(ns), 'relation': rel, 'lines': out}


def lookup(store, who: str = '', target: str = '') -> str:
    """The agent's lookup: what the memory holds about one person (`who`), else every line in use - what he said first, then the facts,
    then what was learned that his acts bore out; and how many learned lines are still being seen, never their text."""
    if str(who or '').strip():
        a = about(store, who)
        out = [f"{l['text']}" + (f" [subject: {l['subject']}]" if l['own'] else '') for l in a['lines'] if l['status'] == 'in use']
        fs = [f['text'] for f in facts(store, {n for n in a['names'] if '@' in n})]
        if not (out or fs or a['relation']): return f'the memory holds nothing about {who}'
        return '\n'.join([f"ABOUT {who}" + (f" - the org chart: {a['relation']}" if a['relation'] else '')] + [f'- {x}' for x in out + fs])
    text = whole(store, 'agents', target, subject=True)
    wait = sum(1 for r in rows(store, INFERRED) if not r['Confirmed'])
    return (text or 'nothing kept about the owner yet') + (f'\n\n({wait} learned line(s) are still being learned, not used yet.)' if wait else '')


# ── the Memory page ──────────────────────────────────────────────────────────────────────────────────────────────────────────────────
SECTIONS = [{'slug': 'said', 'title': 'What you said', 'reads': 'in your words - read by triage, every task it bears on, drafts and the Assistant'},
            {'slug': 'facts', 'title': 'Facts', 'reads': 'from your org chart, your sent mail and your rules - change them there'},
            {'slug': 'confirmed', 'title': 'Learned from what you did', 'reads': 'your own actions bore these out - read like what you said'}]
_EV_KIND = {'msg': 'message', 'rv': 'review', 'task': 'task', 'fs': 'deferred', 'sv': 'promise', 'idea': 'idea', 'say': 'said', 'out': 'outcome'}


def _evidence(ev) -> list:
    return [{'id': e, 'kind': _EV_KIND.get(re.match(r'[a-z]*', e).group(0), 'other'), 'date': None, 'label': e} for e in ev]


def page(store) -> dict:
    """What the Memory page draws, in the shape it reads: each line with its key, section and marks - what he said (Forget), the facts (read
    where they are kept), what his acts bore out (Wrong, Forget) - and what is still being seen (`hypothesis`: in use by itself once his
    acts bear it out; Wrong and Forget only - nothing asks him to confirm it). Within the same caps every reader has (_trim)."""
    from .capabilities import has_ai
    base = {'evidence': [], 'steps': [], 'effective': None, 'seen': '', 'over_budget': []}
    out = []
    sig = str(store.get_setting('email_signature') or '').strip()
    if sig: out.append({**base, 'key': 'signature', 'text': 'Your email signature: ' + ' / '.join(l.strip() for l in sig.splitlines() if l.strip()),
                        'status': 'live', 'section_slug': 'said', 'own': True, 'subject': ''})
    for r in rows(store):
        own = r['Kind'] == SAID
        out.append({**base, 'key': r['key'], 'text': r['Text'] + _about_suffix(r), 'status': 'live' if own or r['Confirmed'] else 'hypothesis',
                    'section_slug': 'said' if own else 'confirmed', 'own': own, 'kept': bool(r['Confirmed']), 'subject': (r['people'] or [''])[0],
                    'evidence': _evidence(r['ev']), 'score': r['N'], 'seen': r['UpdatedAt'], 'said_subject': r['Subject'],
                    **({'taught': r['At']} if str(r['Source']).startswith('verdict:') else {})})
    out += [{**base, 'key': '', 'text': f['text'], 'status': 'live', 'section_slug': 'facts', 'own': False, 'kept': True, 'subject': f['who'],
             'fact': f['source']} for f in facts(store)]
    return {'lines': out, 'deleted': [], 'loose_evidence': [], 'soul': [], 'sections': SECTIONS, 'ai': has_ai(store)}


SAYS = {'said': 'Said by you', 'born': 'Learned - still being seen in what you do', 'kept': 'In use - your own actions bore it out',
        'replaced': 'Replaced by a newer word', 'wrong': 'Wrong, you said - never learned again', 'forgotten': 'Taken out',
        'closed': 'No longer true - kept as history', 'dropped': 'Fell out - stronger lines, or your actions went against it'}


def changes(store, days: int = 30) -> list:
    """What changed in the last `days`, newest first: [{at, action, says, text, status, key, standing, newest}] - read off the lines' own rows."""
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    out = []
    for r in store._rows('SELECT * FROM memory_line WHERE UpdatedAt>=? ORDER BY UpdatedAt DESC, Id DESC', (since,)):
        r = _row(r)
        act = r['Status'] if r['Status'] != LIVE else 'said' if r['Kind'] == SAID else 'kept' if r['Confirmed'] else 'born'
        standing = r['Status'] if r['Status'] != LIVE else 'own' if r['Kind'] == SAID else 'in_use' if r['Confirmed'] else 'watching'
        out.append({'at': r['UpdatedAt'], 'action': act, 'says': SAYS[act], 'text': r['Text'], 'status': r['Kind'], 'score': r['N'],
                    'key': r['key'], 'standing': standing, 'newest': True})
    return out


def week(store, now: datetime = None) -> list:
    "The lines that went into use in the last seven days and are in use still - what he said, and what his acts bore out."
    since = ((now or datetime.now()) - timedelta(days=7)).strftime('%Y-%m-%d')
    return [r for r in in_use(store) if str(r['UpdatedAt'] if r['Kind'] == INFERRED else r['At']) >= since]


# ── LEARNED.md, the stores' face ─────────────────────────────────────────────────────────────────────────────────────────────────────
HEAD = ('# What Taskuary knows about you\n\n_(written from your memory - what you said, the facts, and what your own actions bore out of what was learned. '
        'Change a line on the Memory page; this page follows it)_\n')
READ_ONLY = 'LEARNED.md is written from your memory - change a line on the Memory page (Settings, About you, Memory) and this page follows it.'


def render(store) -> str:
    "LEARNED.md, written from the stores: every line in use, under whose word it is. Never raises - the rows are the record."
    try:
        text = HEAD + '\n' + (whole(store, 'render', cap=10 ** 9) or '_(nothing kept yet)_') + '\n'
        if (store.get_doc(DOC) or '') != text: store.save_doc(DOC, text, 'memory')
        return text
    except Exception as e:
        logger.warning(f'LEARNED.md not written from the memory: {e}'); return ''


# ── LEARNED.md, read into the stores once ────────────────────────────────────────────────────────────────────────────────────────────
_TAG = re.compile(r'^\s*[-*] (?P<text>.*?)\s*\[s:(?P<s>\d+) \| ev: (?P<ev>[^|\]]*)\| seen: (?P<seen>[^|\]]*?)(?: \| k: (?P<k>[^|\]]*?))?\s*\]\s*$')
_ABOUT = re.compile(r'\s*\(about: (?P<a>[^()]+)\)\s*$')
FOR_GOOD = ('not_ours', 'not_a_task', 'not_for_agent', 'made_task', 'idea_dismiss_kind')     # the presses that say "like this, from now on"


def _scope(text: str) -> tuple:
    "(text without its `(about: ...)`, scope, key) - the marker LEARNED.md's verdict lines were written with."
    m = _ABOUT.search(text)
    if not m: return text, 'global', ''
    a, bare = m.group('a').strip(), text[:m.start()].rstrip()
    for pre, sc in (('anyone at ', 'sender_domain'), ('the topic "', 'subject'), ('mail arriving on "', 'source')):
        if a.startswith(pre): return bare, sc, a[len(pre):].rstrip('"')
    return (bare, 'sender', a.lower()) if '@' in a else (text, 'global', '')


def _waiting(head: str) -> bool: return any(w in head for w in ('watching', 'proposed'))     # the two sections no reader read before r10


def _old_lines(store, doc: str):
    """LEARNED.md's lines as the stores take them: {kind, text, subject, people, scope, key, ev, confirmed, source}. A learned line that
    stood in one of its sections was IN USE before r10 and stays in use; one in Watching or Proposed was read by nobody and waits as
    before, now for his acts to bear it out. A line he marked Wrong or Forgot is not one."""
    from .store import render_doc
    fill = lambda t: re.sub(r'\{\{[^}]*\}\}', 'you', render_doc(t, store.owner())).strip()      # {{owner_first}} as the page reads it
    has = lambda t: bool(store._one('SELECT name FROM sqlite_master WHERE type=? AND name=?', ('table', t)))
    hist = store._rows("SELECT Key, Text, Action, Actor, Ev FROM learned_history ORDER BY Id") if has('learned_history') else []
    taught = {str(h['Text'] or '').strip(): h for h in hist if h['Action'] == 'said' and str(h['Actor'] or '').startswith('verdict:')}
    yes = {h['Key'] for h in hist if h['Actor'] == 'owner' and h['Action'] in ('promoted', 'kept')}
    down = {r['Key']: r for r in store._rows("SELECT Key, Status, OwnerText FROM learned_line")} if has('learned_line') else {}
    head = ''
    for raw in doc.splitlines():
        t = raw.strip()
        if t.startswith('## '): head = t[3:].lower(); continue
        if not t.startswith(('- ', '* ')) or 'verdict' in head or any(w in head for w in ('voice', 'style')): continue
        if (m := _TAG.match(raw)):
            k = (m.group('k') or '').strip() or _key(m.group('text'))
            row = down.get(k) or {}
            if row.get('Status') in ('wrong', 'forgotten', 'closed', 'retired'): continue
            text, sc, sk = _scope(fill(row.get('OwnerText') or m.group('text').strip()))
            yield dict(kind=INFERRED, text=text, subject=k, people=names(text) | ({sk} if sc == 'sender' else set()), scope=sc, key=sk,
                       ev=[e.strip() for e in m.group('ev').split(',') if e.strip()], source='migrate',
                       confirmed=not _waiting(head) or bool(row.get('OwnerText')) or k in yes)
            continue
        text, sc, sk = _scope(fill(t[2:].strip()))
        if not text: continue
        v = taught.get(t)
        ppl, subj = names(text) | ({sk} if sc == 'sender' else set()), _key(text) + (f' · {sk}' if sk else '')
        if v: yield dict(kind=INFERRED, text=text, subject=subj, people=ppl, scope=sc, key=sk, ev=[v['Ev']] if v.get('Ev') else [],
                         confirmed=not _waiting(head) or v['Actor'].split(':', 1)[1] in FOR_GOOD, source=v['Actor'])
        else: yield dict(kind=SAID, text=text, subject=subj, people=ppl, scope=sc, key=sk, ev=[], confirmed=False, source='owner')


def migrate(store) -> int:
    """LEARNED.md read into the three stores, once, without loss (_old_lines): his own untagged lines are what he SAID; tagged lines - and
    the lines a verdict wrote in his document - are what was INFERRED, with their evidence, in use where they were in use before. The
    document as it stood is kept whole (BACKUP); LEARNED.md is then the stores' face. An older install's notes table is read in the same
    way. Idempotent. Returns the lines read in (or, on an install r10's first cut read in, put back in use). Never raises."""
    if store.get_setting(MIGRATED): return in_use_again(store)
    try:
        doc, n = store.get_doc(DOC) or '', 0
        for l in _old_lines(store, doc):
            _add(store, l['kind'], l['text'], l['subject'], l['people'], l['scope'], l['key'], l['ev'], l['confirmed'], l['source']); n += 1
        if store._one('SELECT name FROM sqlite_master WHERE type=? AND name=?', ('table', 'memory')):   # ...the notes table of before 2026-10-27
            for r in store._rows("SELECT * FROM memory WHERE IFNULL(Active,1)=1 AND IFNULL(Note,'')<>''"):
                text, sc, sk = ' '.join(str(r['Note']).split()), r.get('Scope') or 'global', str(r.get('ScopeKey') or '')
                _add(store, INFERRED if r.get('Source') == 'verdict' else SAID, text, _key(text) + (f' · {sk}' if sk else ''),
                     names(text) | ({sk.lower()} if sc == 'sender' else set()), sc, sk, confirmed=True, source='migrate'); n += 1
            store._exec('DROP TABLE IF EXISTS memory')
        if doc.strip(): store.save_doc(BACKUP, doc, 'migrate')
        store.set_setting(MIGRATED, _now(), 'migrate')
        in_use_again(store)                     # ...and what his acts already bear out goes into use, within the caps
        if n: logger.info(f'memory: {n} line(s) of LEARNED.md read into the three stores - the document as it was is kept as {BACKUP}')
        return n
    except Exception as e:
        logger.warning(f'LEARNED.md not read into the memory yet: {e}'); return 0


def in_use_again(store) -> int:
    """r10's first cut read LEARNED.md in and left the learned lines that were in use waiting on a Keep he was never going to press (the
    owner, 2026-11-23). Once, on an install it migrated: each line that stood in a section of the document as it was (BACKUP) is in use
    again, and every line his acts already bear out (AUTO_AT) goes into use. Returns the lines put back. Never raises."""
    if store.get_setting(IN_USE_FIX): return 0
    try:
        was = {subject_of(l['subject']) for l in _old_lines(store, store.get_doc(BACKUP) or '') if l['kind'] == INFERRED and l['confirmed']}
        back = [r['Id'] for r in rows(store, INFERRED) if not r['Confirmed'] and (subject_of(r['Subject']) in was or r['N'] >= AUTO_AT)]
        for rid in back: store._exec('UPDATE memory_line SET Confirmed=1 WHERE Id=?', (rid,))
        store.set_setting(IN_USE_FIX, _now(), 'migrate')
        _trim(store); render(store)
        if back: logger.info(f'memory: {len(back)} learned line(s) in use again, as they were before r10')
        return len(back)
    except Exception as e:
        logger.warning(f'the lines in use before r10 not put back yet: {e}'); return 0
