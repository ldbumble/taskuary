"""LEARNED.md - the profile the funnel infers from the owner's verdicts, written by itself.

SOUL.md is what the owner SAYS; LEARNED.md is what they DO. Every explicit correction - a
draft edited before sending, a reply rejected, a task reclassified, a filed message promoted
by hand - carries a general lesson about how this person works: what they are responsible
for, how they write, what deserves a task, who matters. Nobody types those in, so the system
distills them itself. The design follows where the experience-learning literature agrees:
ExpeL's counted insights (arxiv 2308.10144), PRELUDE's infer-the-preference-from-the-edit
(arxiv 2404.15269), Generative Agents' batched reflection with cited evidence (2304.03442).

Two write paths, deliberately different speeds:
- HOT (learn_from): one cheap LLM call per correction turns the single event into a
  hypothesis, visible in the doc seconds after the verdict that taught it - explicit
  corrections are the high-signal minority and deserve immediate weight;
- REFLECTION (reflect / reflect_if_due): batched and debounced, rewrites the whole doc -
  only a batch can see cross-episode patterns, promote hypotheses that kept holding, and
  kill the ones that did not. Implicit signals (drafts approved untouched) are counted
  ONLY here: individually they are noise, in aggregate they are confirmation.

Both write paths end in settle(), which does in code the bookkeeping a model does badly: it keys
every line so a rephrase cannot orphan its history, merges the near-duplicates the hot pass was
asked (and often failed) to avoid, and ages out the untested lines that enough reflections have
now passed over without confirming - because an s:N that only ever moves on evidence never falls
when a pattern quietly stops being true. The clock there counts REFLECTIONS, never days: a
calendar would charge a line for a quiet fortnight in which nothing could have confirmed it.

Hypotheses are never injected into prompts: a pattern seen once is a guess, and a guess in
a system prompt is a rule. Only promoted sections travel (injectable()) - and rules whose
effect is to HIDE mail never promote themselves at all: they wait in 'Proposed' for the
owner, because a wrong ignore-rule silences the very corrections that would revoke it.
"""
import re
from datetime import datetime, timedelta
from loguru import logger

DOC = 'learned'
# ONE SECTION PER READER (the owner, 2026-10-23: "why would we want button presses to do with triage"): triage reads the first and
# nothing else, the Advisor the second and nothing else (learned_cut.READS); how the owner writes lives in STYLE.md (byrecipient.py)
from .learned_cut import SORT, NEXT
WATCH_HEADER = '## Watching — not read by anyone yet'
REFLECT_AT = 3           # corrections that trigger a reflection; fewer still reflect daily
DAYS = 14                # the fallback event window when no reflection has ever run
HYP_START, HYP_END = '<!-- hypotheses:start -->', '<!-- hypotheses:end -->'
PROP_START, PROP_END = '<!-- proposed:start -->', '<!-- proposed:end -->'
VERD_START, VERD_END = '<!-- verdicts:start -->', '<!-- verdicts:end -->'
# A gated section is its heading, whatever prose introduces it, and the marked block - and the
# prose is the part this used to miss. The pattern wanted the marker directly under the heading,
# but the shipped document explains each section first ("every verdict you give, dated, with the
# sender and subject..."), so the heading and its explainer rode into every triage prompt while
# the content underneath was correctly stripped: a section header describing what was not sent.
_GATED = re.compile(r'\n## [^\n]*\n(?:(?!##)[^\n]*\n)*?<!-- (hypotheses|proposed|verdicts):start -->'
                    r'.*?<!-- \1:end -->\n?', re.S)
VERD_HEADER = '## Verdicts - the evidence'
VERD_KEEP = 60           # the most recent verdict lines the doc shows; the table keeps them all

LESSON_SYSTEM = (
    'You maintain the Watching section of LEARNED.md: patterns Taskuary is testing about how '
    'its owner works, distilled from their verdicts. You get the current section and ONE new '
    'event. Return the updated section: markdown bullets only - no headers, no fences, no preamble.\n'
    '- Infer the GENERAL preference the event reveals: what they are responsible for, who matters to '
    'them, what deserves a task, how they write. Never a one-sender rule (standing notes '
    'handle those) and never a mere restatement of the event.\n'
    "- Leave every line whose evidence is pr ids exactly as it is.\n"
    "- Every bullet ends with a tag: [s:N | ev: id,id | seen: date]. A new hypothesis starts at "
    "s:2 with this event's id as ev. If a bullet already says the same thing, raise its s by 1, "
    'append the id, update seen - never duplicate. If the event contradicts one, lower its s by 1; '
    'delete any bullet at s:0.\n'
    '- Refer to the owner as {{owner_first}} - a placeholder the app fills in.\n'
    '- A routine event with nothing general in it: return the section unchanged.\n'
    '- At most 20 bullets, each under 25 words before the tag; drop the weakest first.')

REFLECT_SYSTEM = (
    'You are the reflection pass over LEARNED.md, the profile Taskuary maintains of how its owner '
    'works, learned from their verdicts. Rewrite the WHOLE document and return nothing else - no '
    'fences, no commentary. Rules:\n'
    '- Lines without a [s:...] tag were written by the owner: keep them byte-for-byte, where they are.\n'
    '- Apply the evidence: a hypothesis the events confirm gains 1 strength per distinct episode '
    '(append its ev id); a contradicted one loses 1; s:0 means delete the line.\n'
    '- Promote a hypothesis into the matching section above only at s:4+ with evidence from 3+ '
    'episodes across 2+ different people or threads - one hot thread proves nothing general. What deserves a task, what the owner '
    'is responsible for and who matters go into "## How you sort mail" (triage reads it and nothing else); how the owner WRITES goes '
    'into "## Voice" (the app moves it to STYLE.md, where the drafter reads it).\n'
    '- "## How you sort mail" is learned ONLY from sorting verdicts: mem ids, rv rejections and no-replies, task ids. A line resting '
    'only on presses (pr ids) or the outcome ledger (out ids) never goes there - the app moves it back to Watching.\n'
    '- EXCEPTION: a rule whose effect is to hide or auto-file things ("treat X as fyi", "never a '
    'task") promotes only into "Proposed rules" - hiding is the owner\'s call to approve - UNLESS two or '
    'more of its evidence ids are the owner\'s own explicit verdicts (mem ids whose notes say NOT OURS or '
    'NOT A TASK): then the owner has already said it, and it goes straight into the matching section.\n'
    '- Add new hypotheses only for patterns 2+ episodes support; singles stay unwritten.\n'
    '- Never contradict SOUL.md (it outranks this file); never invent facts beyond the events.\n'
    '- Lines from the outcome ledger (out123) are evidence of HABITS and of what WORKED: a move the owner makes every '
    'time an agent stops the same way is a habit, and a habit belongs under "## What you do next" (the Advisor reads it), never '
    'under "## How you sort mail". Cite their ids like any other.\n'
    '- Lines whose evidence is pr ids (presses: what the owner pressed) are counted by the app from the press log - under '
    '"## What you do next" and in Watching. Keep them byte-for-byte, where they are.\n'
    "- Keep each line's k: byte-for-byte - it is how a line is recognised across rewrites, and a "
    'changed one orphans its evidence and its history. A line you add fresh needs none.\n'
    '- Keep the section headers, all four <!-- --> marker lines, and every {{owner}}-style '
    'placeholder exactly as they are; keep the whole file under 120 lines.\n'
    '- End with a footer: _last reflection: date - what changed in a few words_ (replace any old one).')


def _today(): return datetime.now().strftime('%Y-%m-%d')
def _block(doc, a, b): return doc.split(a, 1)[1].split(b, 1)[0].strip() if (a in doc and b in doc) else None
def _put_block(doc, a, b, body):
    head, rest = doc.split(a, 1)
    return f'{head}{a}\n{body.strip()}\n{b}' + rest.split(b, 1)[1]
def _unfence(s): return re.sub(r'^```\w*\s*$|^```\s*$', '', (s or '').strip(), flags=re.M).strip()


def settle(store, old_doc: str, doc: str, today: str = None) -> str:
    """The bookkeeping no longer asked of the model, after every machine write.

    Each tagged line gets a `k:` - its identity from then on, so the reflection rephrasing at the
    margins stops orphaning a line's history and its evidence; lines that share one are merged
    rather than left to coexist as near-duplicates (the one thing LESSON_SYSTEM asks for that a
    model reliably gets wrong); evidence that grew restarts the line's clock; and a line still
    under test that has gone quiet through enough reflections to decay to nothing
    (learnedgraph.effective) is dropped. Untagged lines are the owner's and come through
    byte-for-byte."""
    from . import learnedgraph as lg
    today, log = today or _today(), lg.reflect_log(store)
    was = {l['key']: l for l in lg.lines(old_doc)}
    out, kept = [], {}
    for raw, l in lg.walk(doc):
        if not l: out.append(raw); continue
        prev = kept.get(l['key'])
        if prev is None:
            kept[l['key']] = dict(l, _at=len(out)); out.append(raw); continue
        # ...and the merge is SAID, in the history the owner can read (What changed): a line that vanished into another
        # was invisible there, since its key lived on (the row-bot comparison, 2026-10-07)
        if l['text'] != prev['text']:
            try: store.add_learned_event(l['key'], l['text'], l['status'], l['score'], ','.join(l['ev']), 'merged', 'settle')
            except Exception as e: logger.debug(f'learn: the merge went unrecorded - {e}')
        prev['score'] = max(prev['score'], l['score'])                    # the stronger of two claims about one pattern
        prev['ev'] += [e for e in l['ev'] if e not in prev['ev']]
        prev['seen'] = max(prev['seen'], l['seen'])
    for l in kept.values():
        o = was.get(l['key'])
        if o and set(l['ev']) - set(o['ev']): l['seen'] = today           # something new confirmed it: the clock restarts here
        out[l.pop('_at')] = lg.fmt(l) if lg.effective(l, log) > 0 else None
    from .learnedlines import guard
    return guard(store, _sort_is_verdicts('\n'.join(r for r in out if r is not None)))


SORTING = ('mem', 'rv', 'task')       # the evidence a sorting line may rest on: verdict notes, review verdicts, task corrections


def _sort_is_verdicts(doc: str) -> str:
    """PRESS HABITS NEVER REACH TRIAGE (the owner, 2026-10-23): a line under "How you sort mail" that rests only on presses or the
    outcome ledger goes back to Watching, whatever the model meant by putting it there. Triage learns from sorting verdicts."""
    from . import learnedgraph as lg
    bad = [raw for raw, l in lg.walk(doc) if l and f"## {l['section']}" == SORT and l['ev']
           and not any(e.startswith(SORTING) for e in l['ev'])]
    if not bad or HYP_START not in doc: return doc
    for raw in bad: doc = doc.replace(raw + '\n', '', 1).replace(raw, '', 1)
    return _put_block(doc, HYP_START, HYP_END, '\n'.join(filter(None, [_block(doc, HYP_START, HYP_END)] + [r.strip() for r in bad])))


def injectable(text: str) -> str:
    """The doc as prompts should read it: active sections only. Hypotheses and proposed rules
    are gated out - a tested pattern is knowledge, an untested one is noise in a system prompt -
    and so is the verdicts block: those lines reach a prompt by RELEVANCE (ingest.relevant_notes
    pulls the ones about this sender or topic), never all at once."""
    if not text: return ''
    out = _GATED.sub('\n', text)
    for a, b in ((HYP_START, HYP_END), (PROP_START, PROP_END), (VERD_START, VERD_END)):   # blocks whose header was hand-edited away
        if a in out and b in out:
            head, rest = out.split(a, 1)
            out = head + rest.split(b, 1)[1]
    return _without_preamble(out).strip()


# The italic paragraph under the title explains the FILE to whoever opens it - what the [s:N] tag
# means, that SOUL.md outranks it, that their own lines are never touched. None of that is a thing
# triage should know, and it is 900 characters of a 1500-character budget: the document grew its
# explanation, and the learned rules were what got cut to make room (this install went from two
# rules reaching triage to one). The reader's half of the document stops at the first heading.
_PREAMBLE = re.compile(r'\A(#[^\n]*\n+)_.*?_\s*\n+(?=#)', re.S)


def _without_preamble(doc: str) -> str:
    """The doc minus the italic note addressed to its human reader; the title is kept."""
    return _PREAMBLE.sub(r'\1', doc or '')


def render_verdicts(store) -> str:
    """The evidence, as the doc shows it: one dated line per verdict the owner gave, newest
    first, straight from the memory table (which stays the record; this is its readable face)."""
    rows = [m for m in store.list_memories() if m.get('Source') == 'verdict'][:VERD_KEEP]
    if not rows: return '_(nothing yet - "Not our task" and "Not a task" write here)_'
    return '\n'.join(f"- {str(m.get('Note') or '').strip()} [mem{m['MemoryId']} · {m['Scope']}"
                     + (f": {m['ScopeKey']}" if m.get('ScopeKey') else '') + ']' for m in rows)


def note_verdicts(store):
    """Refresh LEARNED.md's evidence block after a verdict. The section is appended to a doc
    that predates it (existing installs), never overwriting anything the owner or the
    reflection wrote. Never raises - the memory row is already saved."""
    try:
        doc = store.get_doc(DOC) or ''
        if VERD_START not in doc or VERD_END not in doc:
            doc = doc.rstrip('\n') + (f'\n\n{VERD_HEADER}\n_(every verdict you give, dated, with the sender and subject '
                                      f'it was given on. Triage is shown the ones about a similar sender or topic and judges '
                                      f'how alike the new message is; the general lesson is distilled above.)_\n'
                                      f'{VERD_START}\n{VERD_END}\n')
        new = _put_block(doc, VERD_START, VERD_END, render_verdicts(store))
        if new != (store.get_doc(DOC) or ''): store.save_doc(DOC, new, 'verdicts')
    except Exception as e:
        logger.warning(f'verdict block not written: {e}')


def _without_verdicts(doc: str) -> tuple:
    """(doc minus its verdicts section, the section) - the reflection never sees the block: it
    is generated, and a model rewriting it would only lose lines."""
    if VERD_START not in doc or VERD_END not in doc: return doc, ''
    head, rest = doc.split(VERD_START, 1)
    body, tail = rest.split(VERD_END, 1)
    hdr = head.rfind(f'\n{VERD_HEADER}')
    if hdr >= 0: head, section_head = head[:hdr], head[hdr:]
    else: section_head = ''
    return head.rstrip('\n') + '\n' + tail.lstrip('\n'), section_head + VERD_START + body + VERD_END + '\n'


def learn_from(store, event: str, llm=None):
    """One explicit owner verdict -> the Hypotheses section, updated now. Never raises: a lost
    lesson costs one observation, a broken decide endpoint costs trust in the whole funnel."""
    try:
        cfg = store.get_settings()
        if cfg.get('learn_enabled', '1') != '1': return
        try: n = int(cfg.get('learn_pending') or 0) + 1
        except ValueError: n = 1
        store.set_setting('learn_pending', str(n), 'learn')       # ticks even with no AI: the first reflection catches up
        from .llm import build_llm
        llm = llm or build_llm(store, job='memory')
        doc = store.get_doc(DOC) or ''
        hyp = _block(doc, HYP_START, HYP_END)
        if llm is None or hyp is None: return
        # the press lines are counted by the app (moves), never by a model: held out of the call and put back as they were
        held = [l for l in hyp.splitlines() if _pressed(l)]
        sent = '\n'.join(l for l in hyp.splitlines() if not _pressed(l))
        out = _unfence(llm(LESSON_SYSTEM, f'(today: {_today()})\n\nCURRENT HYPOTHESES:\n{sent[:3000]}'
                                          f'\n\nNEW EVENT:\n{event[:2000]}', max_tokens=700))
        # a broken answer never lands in the doc - markers inside it would corrupt the block splice
        if not out or '<!--' in out or len(out) > 6000: return
        if out != sent:
            out = '\n'.join([l for l in out.splitlines() if not _pressed(l)] + held)
            new_doc = settle(store, doc, _put_block(doc, HYP_START, HYP_END, out))
            store.save_doc(DOC, new_doc, 'learn')
            from . import learnedgraph; learnedgraph.record(store, doc, new_doc, 'learn')
        if n >= REFLECT_AT and not _failed_today(store): reflect(store, llm)
    except Exception as e:
        logger.warning(f'learning skipped: {e}')


def _pressed(line: str) -> bool:
    from .learnedgraph import TAG
    m = TAG.match(line)
    return bool(m) and any(e.strip().startswith('pr') for e in m.group('ev').split(','))


def gather(store, since: str) -> str:
    """The verdict window, compact enough to hand an AI whole: review decisions with the
    draft-vs-sent texts (the richest style signal there is), the standing notes written in the
    window, and the owner-made corrections the audit trail carries."""
    revs = [r for r in store.list_reviews() if str(r.get('DecidedAt') or '') >= since]
    ok = [r for r in revs if r['Status'] == 'approved']
    dec = [r for r in revs if r['Status'] in ('edited', 'rejected', 'no_reply')]
    out = [f'DRAFT VERDICTS: {len(ok)} sent unchanged (each confirms the current voice), {len(dec)} corrected:']
    for r in dec[:15]:
        out.append(f"  rv{r['ReviewId']} [{r['Status']}] \"{(r.get('Subject') or r.get('Title') or '')[:70]}\" "
                   f"from {r.get('FromEmail') or '?'}"
                   + (f" - owner's note: {str(r['DecideNote'])[:120]}" if r.get('DecideNote') else ''))
        if r['Status'] == 'edited':
            out += [f"    DRAFT: {str(r.get('DraftText') or '')[:400]}",
                    f"    SENT:  {str(r.get('FinalText') or '')[:400]}"]
    mems = [m for m in store.list_memories() if str(m.get('CreatedAt') or '') >= since and m.get('Source') == 'verdict']
    if mems:
        out.append('VERDICT NOTES WRITTEN (already durable - generalize ACROSS them, never copy them):')
        out += [f"  mem{m['MemoryId']} [{m['Scope']}:{m.get('ScopeKey') or '*'}] {str(m.get('Note') or '')[:140]}" for m in mems[:12]]
    acts = ('not_a_task_delete', 'not_mine_delete', 'create_from_message', 'split', 'merge')
    aud = [a for a in store.list_audit(limit=400)
           if str(a.get('CreatedAt') or '') >= since and a['Action'] in acts and a.get('ActorType') != 'agent']
    if aud:
        out.append('OWNER CORRECTIONS (audit trail):')
        out += [f"  {a['Action']} {a['EntityType']}{a['EntityId']} {str(a.get('Detail') or '')[:120]}" for a in aud[:20]]
    # ...and NOT what the owner pressed: the presses are counted into "What you do next" by the app (moves), and a reflection that
    # read them wrote press habits into the sorting lines triage reads (the owner, 2026-10-23: press habits never reach triage)
    from . import outcomes
    led = outcomes.evidence(store, since)
    if led:
        out.append('WHAT CAME OF ACTIONS (the outcome ledger - what you did next and what followed; a habit is what you do when nothing corrected it):')
        out += [f'  {l}' for l in led]
    return '\n'.join(out)


REFLECT_FIT = 10_000     # the doc a reflection sends; under the 12k answer cap so the rewrite has room to grow
_SEEN = re.compile(r'\| seen: ([^|\]]*)')

def _fit(doc: str, cap: int = REFLECT_FIT) -> tuple:
    """(doc to send, {start marker: held lines}) - never a cut through the doc. The old `doc[:6000]`
    sliced off three of the four markers once the doc passed 6k, so every answer failed the marker
    check: a paid call that could not succeed, on every launch. Past the cap, the gated blocks lend
    their least recently seen lines instead and the answer gets them back (_restore) unjudged - a
    line the model never saw is no evidence it should go."""
    held = {}
    for a, b in ((HYP_START, HYP_END), (PROP_START, PROP_END)):
        body = _block(doc, a, b)
        if len(doc) <= cap or body is None: continue
        ls = body.splitlines()
        def seen(l): m = _SEEN.search(l); return (bool(m), m[1].strip() if m else '')
        for l in sorted(ls, key=seen):
            if len(doc) <= cap: break
            ls.remove(l); held.setdefault(a, []).append(l)
            doc = _put_block(doc, a, b, '\n'.join(ls))
    return doc, held

def _restore(doc: str, held: dict) -> str:
    for a, ls in held.items():
        b = {HYP_START: HYP_END, PROP_START: PROP_END}[a]
        doc = _put_block(doc, a, b, '\n'.join([_block(doc, a, b) or ''] + ls))
    return doc

def _failed_today(store) -> bool: return (store.get_setting('learn_reflect_failed') or '') == _today()
def _failed(store, why) -> bool:
    """A refused rewrite is refused again until the doc or the evidence moves, so the automatic doors
    (launch, the REFLECT_AT-th correction) hold off for the rest of the day instead of paying for it on
    every one. The Reflect button still runs: the owner asked."""
    store.set_setting('learn_reflect_failed', _today(), 'reflect')
    logger.warning(f'LEARNED.md reflection failed ({why}) - kept the old doc; next automatic try tomorrow')
    return False


def reflect(store, llm=None) -> bool:
    """The consolidation: whole-doc rewrite against the event window. Modeled on digest.py's
    gather -> synthesize -> save_doc, but with NO no-AI fallback - a mechanical rewrite of a
    doc that feeds every prompt would poison them, and the old doc is always a valid answer."""
    from .llm import build_llm
    llm = llm or build_llm(store, job='memory')
    doc, verdicts = _without_verdicts(store.get_doc(DOC) or '')   # RAW doc: {{owner}} tokens must survive the rewrite
    if not llm or not doc.strip(): return False
    since = (store.get_setting('learn_last_reflect')
             or (datetime.now() - timedelta(days=DAYS)).isoformat(sep=' ', timespec='seconds'))
    sent, held = _fit(doc)
    try:
        # the answer is the whole doc again, so its budget follows the doc (~3 chars a token, plus room)
        new = _unfence(llm(REFLECT_SYSTEM,
                           f'(today: {_today()})\n\nCURRENT LEARNED.md:\n{sent}\n\n'
                           f"SOUL.md (context only - it outranks, never contradict it):\n{(store.doc('soul') or '')[:2500]}\n\n"
                           f'EVENTS SINCE {since}:\n{gather(store, since)[:5000]}', max_tokens=max(1800, len(sent) // 3 + 800)))
    except Exception as e: return _failed(store, e)
    # the 120-line budget in the prompt is a request; this is the law. A doc past the cap is a
    # model that ignored its instructions, and an ever-growing LEARNED.md would silently lose
    # its tail to the injection caps - the old doc is always the better answer than a bloated one.
    markers = (HYP_START, HYP_END, PROP_START, PROP_END)
    if not (new.startswith('#') and 200 < len(new) <= 12_000 and new.count('\n') <= 160
            and all(new.count(m) == 1 for m in markers)):
        return _failed(store, f'unusable answer: {len(new)} chars, {new.count(chr(10))} lines, '
                              f'{sum(new.count(m) == 1 for m in markers)}/4 markers')
    # ...and each reader's section is still there: a rewrite that lost "How you sort mail" lost everything triage reads
    if lost := [h for h in (SORT, NEXT) if h in doc and h not in new]: return _failed(store, f'the rewrite dropped {", ".join(lost)}')
    new = _restore(new, held)
    from . import learnedgraph
    # this reflection is itself an opportunity: it read the window, so every line it did not
    # touch has just gone one tick quieter. Recorded BEFORE settle, which measures against it.
    learnedgraph.reflect_log(store, _today())
    settled = settle(store, doc, new.rstrip('\n'))
    final = settled + ('\n\n' + verdicts.strip('\n') + '\n' if verdicts else '')
    store.save_doc(DOC, final, 'reflect')
    learnedgraph.record(store, doc, new, 'reflect')            # what the reflection itself did to the lines
    learnedgraph.record(store, new, settled, 'decay')          # and what the clock did to the ones it left alone
    voice_out(store)                               # what it learned about how the owner writes goes where the drafter reads it
    auto_adopt(store)                              # what the owner already said does not wait for a click
    moves(store, restore=True)                     # ...and the press log's counts, as written, whatever the rewrite did to them
    store.set_setting('learn_pending', '0', 'reflect')
    store.set_setting('learn_reflect_failed', '', 'reflect')
    store.set_setting('learn_last_reflect', datetime.now().isoformat(sep=' ', timespec='seconds'), 'reflect')
    logger.info('LEARNED.md reflected')
    try:                                            # ...and the people the window's outcomes name get their page (people_pages.py)
        from . import people_pages
        done = people_pages.refresh(store, llm)
        if done: logger.info(f"people pages compiled: {', '.join(done)}")
    except Exception as e: logger.warning(f'people pages skipped: {e}')
    try:                                            # ...and the playbooks the ledger has facts about get a proposal (playbook_facts.py)
        from . import playbook_facts
        done = playbook_facts.refresh(store, llm)
        if done: logger.info(f"playbook facts proposed: {', '.join(done)}")
    except Exception as e: logger.warning(f'playbook facts skipped: {e}')
    return True


ADOPT_UNDER = SORT

def adopt(store, key: str, actor: str = 'owner') -> dict:
    """The owner's click on a proposed rule or a hypothesis: the line moves into the live
    section (ADOPT_UNDER, or the first live section present) and from then on rides into every
    prompt. The one thing the reflection will never do by itself for a hide-rule."""
    from . import learnedgraph
    doc = store.get_doc(DOC) or ''
    target = next((l for l in learnedgraph.lines(doc) if l['key'] == key and l['status'] != 'live'), None)
    if not target: raise ValueError('no proposed or hypothesis line with that key')
    raw = next(r for r, l in learnedgraph.walk(doc) if l and l['key'] == key)
    rest = doc.replace(raw + '\n', '', 1).replace(raw, '', 1)
    # ...its reader's own section: a press habit is the Advisor's, everything else triage's
    from .learnedlines import reader_of
    rest = _under(rest, NEXT if reader_of(target) == 'advisor' else ADOPT_UNDER, raw.strip())
    store.save_doc(DOC, rest, actor)
    learnedgraph.record(store, doc, rest, actor)
    return {'ok': True, 'text': target['text']}


OWNER_SAID = 2      # this many of the owner's own explicit verdicts among a proposed rule's evidence = they stated it
_MARK = re.compile(r'\b(NOT OURS|NOT A TASK|NOT A CODING TASK)\b')

def _said(store) -> set:
    """The owner's own explicit verdicts that are still SWITCHED ON - a note switched off no longer says anything (phase C, 2026-10-23)."""
    return {f"mem{m['MemoryId']}" for m in store.list_memories(active_only=True) if m.get('Source') == 'verdict' and _MARK.search(m.get('Note') or '')}


def auto_adopt(store, actor: str = 'owner-verdicts') -> list:
    """The Proposed gate exists because a hide-rule the model INFERRED can silence the corrections
    that would revoke it. A hide-rule the owner has already SAID - two or more of their own explicit
    verdicts (a "Not our task" pressed on the topic, a note they typed) among its evidence - is not
    an inference, and waiting for a click on it is the owner confirming themselves. Those go live
    as soon as the reflection proposes them (the owner, 2026-08-27: "anything written in absolute rules
    should not be in proposed"). Returns the adopted lines' texts."""
    from . import learnedgraph
    said = _said(store)
    out = []
    for l in learnedgraph.lines(store.get_doc(DOC) or ''):
        if l['status'] != 'proposed' or len(said & set(l['ev'])) < OWNER_SAID: continue
        try: out.append(adopt(store, l['key'], actor)['text'])
        except ValueError: continue
    if out: logger.info(f'LEARNED.md: {len(out)} proposed rule(s) the owner had already stated went live')
    return out


def reflect_if_due(store) -> bool:
    """Startup hook, digest-style: reflect when enough corrections queued (REFLECT_AT triggers
    it mid-day too, from learn_from), or once a day when at least one did - never on silence."""
    cfg = store.get_settings()
    if cfg.get('learn_enabled', '1') != '1': return False
    try: n = int(cfg.get('learn_pending') or 0)
    except ValueError: n = 0
    # no model in it, so it never waits on one: a rule the owner already stated goes live even on a
    # day the rewrite cannot run - it did not for ten days while every reflection was refused
    try: auto_adopt(store)
    except Exception as e: logger.warning(f'auto-adopt skipped: {e}')
    if n <= 0 or _failed_today(store): return False
    if n < REFLECT_AT and (cfg.get('learn_last_reflect') or '').startswith(_today()): return False
    return reflect(store)


# ── MOVES: what the owner presses, learned from the press log (the deep dive, 2026-10-20) ─────────────────────────────────────────────
# The Advisor lit a button and nothing remembered which one the owner pressed (advisor.press keeps it now). The owner expects what is
# learned to land HERE, where they can read it and delete a line to undo it - so the press log becomes lines in this document's own
# grammar: watching, then "## What you do next" (the Advisor's section, and only the Advisor's) once it is IN USE - the one ladder of
# the phase C design (2026-10-23): 3+ episodes from 2+ people or threads at a share of at least MOVE_SHARE; two overrides in a row put
# it back to watching, under the same key. The counts are the log's, never a model's: one line per moment - a kind of item from one
# sender's domain, or one repository - and the verb pressed most there. A line the owner deletes is undone: its moment counts again
# only from presses made after the delete. The reflection never reads the presses (gather) and keeps these lines as written.
MOVES_HEADER = NEXT
MOVES_INTRO = ("_(the Advisor reads only this: what you press on each kind of item, learned from your own presses - it lights that "
               'button, never presses it; delete a line to undo it)_')
SORT_INTRO = ('_(triage reads only this: what you are responsible for and what becomes a task, learned from your sorting verdicts - '
              'Not ours, Not a task, a kind or repository you moved, rules you approved)_')
MOVES_CUT = 'learn_moves_cut'        # {key: the last press id when the owner deleted that line} - presses up to it no longer count
MOVES_MINE = 'learn_moves_written'   # {key: the last press it counted} for each line this pass wrote - one gone from the doc was deleted
MOVE_SHARE = 0.6                     # the verb must be this share of the presses on the moment to be a habit at all
IN_USE_EPISODES, IN_USE_PEOPLE = 3, 2
MOMENTS = {'review': 'drafts to', 'todo': 'asks from', 'asked': 'asks from', 'agent': "agents' stops on work from", 'agentdone': 'finished agent work for',
           'idea': "the Advisor's ideas about", 'fyi': 'notices from', 'report': 'reports from', 'wrapup': 'sent replies to', 'task': 'tasks from'}
CODE_CHANNELS = ('github', 'gitlab', 'azdo', 'bitbucket')


def moment(kind: str, channel: str, scope: str) -> str:
    """A press's moment in words: "GitHub items from northwind/ledger", "drafts to vendor.example"."""
    if channel in CODE_CHANNELS: return f"{'GitHub' if channel == 'github' else channel.title()} items from {scope}"
    if str(kind or '').startswith('goal'): return f'goals with {scope}'
    return f"{MOMENTS.get(kind, 'items from')} {scope}"


def _move_key(kind, channel, scope) -> str: return f"move {kind or 'item'} {channel or '-'} {scope}"


def _json_setting(store, key, empty):
    import json
    try: return json.loads(store.get_setting(key) or 'null') or empty
    except ValueError: return empty


def press_rows(store) -> list:
    """THE ONE READER OF THE PRESS LOG (presses.py records every press, on every surface - phase B): every press with a scope to learn
    at that was a real CHOICE, oldest first - one made with no other button there says nothing about what the owner would pick. The
    habits read the presses through here and nowhere else."""
    return store._rows("SELECT * FROM advice_press WHERE IFNULL(Stale,0)=0 AND IFNULL(Choice,1)=1 AND IFNULL(Scope,'')<>'' AND IFNULL(Pressed,'')<>'' "
                       "ORDER BY Id")


def move_rows(store) -> dict:
    """{(kind, channel, scope): [press rows]} - presses on a line still true of the item (not stale), with a scope to learn at, made
    after the owner last deleted that moment's line. Only a real choice counts (presses.py, 2026-10-23): every press is kept now, and
    one made with no other button there says nothing about what the owner would pick."""
    cut, out = _json_setting(store, MOVES_CUT, {}), {}
    for r in press_rows(store):
        g = (str(r.get('ItemKind') or ''), str(r.get('Channel') or ''), str(r['Scope']))
        if int(r['Id']) > int(cut.get(_move_key(*g)) or 0): out.setdefault(g, []).append(r)
    return out


def move_lines(store) -> list:
    """Every moment with a habit: [{key, text, score, ev, seen, live, overridden}]. One episode is one item (its last press); the score
    is 1 + the episodes that pressed the verb - the episodes that pressed another, so a habit is born at s:2 as LESSON_SYSTEM's are.
    live = in use: IN_USE_EPISODES+ episodes from IN_USE_PEOPLE+ people or threads at MOVE_SHARE+, and the last two episodes not
    both something else (`overridden` - two overrides in a row put a habit back to watching)."""
    from . import buttons
    out = []
    for (kind, channel, scope), rs in move_rows(store).items():
        last = {}
        for r in rs: last[(r['TargetKind'], r['TargetId'])] = r
        votes = {}
        for r in last.values(): votes.setdefault(r['Pressed'], []).append(r)
        verb, mine = max(votes.items(), key=lambda kv: (len(kv[1]), kv[1][-1]['Id']))
        n, m = len(mine), len(last)
        score = 1 + n - (m - n)
        if n / m < MOVE_SHARE or score < 2: continue
        who = {r.get('Sender') or r.get('Thread') or f"{r['TargetKind']}{r['TargetId']}" for r in mine}
        eps = sorted(last.values(), key=lambda r: int(r['Id']))
        overridden = len(eps) >= 2 and all(r['Pressed'] != verb for r in eps[-2:])
        out.append({'key': _move_key(kind, channel, scope), 'score': score, 'upto': max(int(r['Id']) for r in rs), 'ev': [f"pr{r['Id']}" for r in mine][-8:],
                    'live': n >= IN_USE_EPISODES and len(who) >= IN_USE_PEOPLE and not overridden, 'overridden': overridden,
                    'seen': max(str(r['CreatedAt'])[:10] for r in mine), 'verb': verb, 'n': n, 'm': m, 'moment': moment(kind, channel, scope),
                    'text': f"On {moment(kind, channel, scope)}, {{{{owner_first}}}} presses {buttons.label(verb) or verb} ({n} of {m})"})
    return out


def moves(store, restore: bool = False) -> bool:
    """Write the press log's habits into LEARNED.md: each moment's line in Watching until it is in use, then under "## What you do
    next". A key this pass wrote that is gone from the doc was deleted by the owner: it is cut, and counts only presses after now -
    unless `restore` (after a reflection, whose rewrite may have dropped it: the count is the log's, not the model's). Lines are
    rewritten in place by key; nothing else in the doc is touched. Never raises. Returns whether it saved."""
    import json
    from . import learnedgraph as lg
    from .learnedlines import guard
    try:
        if (store.get_settings() or {}).get('learn_enabled', '1') != '1': return False
        doc = store.get_doc(DOC) or ''
        if HYP_START not in doc or HYP_END not in doc: return False
        have = {l['key']: l for l in lg.lines(doc)}
        mine = _json_setting(store, MOVES_MINE, {})
        mine = mine if isinstance(mine, dict) else {}
        if not restore and (gone := {k: n for k, n in mine.items() if k not in have}):
            store.set_setting(MOVES_CUT, json.dumps({**_json_setting(store, MOVES_CUT, {}), **gone}), 'learn')
        want = {m['key']: m for m in move_lines(store)}
        new, back = doc, []
        def drop(d, k):
            raw = next((r for r, l in lg.walk(d) if l and l['key'] == k), None)
            return d if raw is None else d.replace(raw + '\n', '', 1).replace(raw, '', 1)
        for k, m in want.items():
            line = lg.fmt({'text': m['text'], 'score': m['score'], 'ev': m['ev'], 'seen': m['seen'], 'key': k})
            # a line the owner moved into the section stays in use - until they press otherwise twice in a row
            live = m['live'] or (k in have and have[k]['status'] == 'live' and not m['overridden'])
            if any(raw.strip() == line for raw, l in lg.walk(new) if l and l['key'] == k) and live == (k in have and have[k]['status'] == 'live'): continue
            if k in have and have[k]['status'] == 'live' and not live: back.append(m)
            new = drop(new, k)
            new = _under(new, NEXT, line) if live else _put_block(new, HYP_START, HYP_END, '\n'.join(filter(None, [_block(new, HYP_START, HYP_END), line])))
        for k in set(mine) & set(have) - set(want): new = drop(new, k)        # a habit that no longer holds goes; the history says so
        store.set_setting(MOVES_MINE, json.dumps({k: m['upto'] for k, m in want.items()}), 'learn')
        new = guard(store, new)
        if new == doc: return False
        store.save_doc(DOC, new, 'moves')
        lg.record(store, doc, new, 'moves')
        for m in back: store.add_learned_event(m['key'], m['text'], 'hypothesis', m['score'], '', 'watching', 'moves')
        return True
    except Exception as e:
        logger.warning(f'moves not learned: {e}'); return False


def _under(doc: str, head: str, line: str) -> str:
    """`line` at the end of the `head` section, which is made (above Proposed rules, else at the end) the first time it is needed."""
    if head not in doc:
        intro = MOVES_INTRO if head == NEXT else SORT_INTRO if head == SORT else ''
        at, sect = doc.find('\n## Proposed rules'), f'{head}\n' + (f'{intro}\n' if intro else '')
        doc = doc[:at] + '\n\n' + sect + doc[at:] if at >= 0 else doc.rstrip('\n') + '\n\n' + sect
    head_, tail = doc.split(head, 1)
    nxt = tail.find('\n## ')
    body, after = (tail, '') if nxt < 0 else (tail[:nxt], tail[nxt:])
    return head_ + head + body.rstrip('\n') + '\n' + line + '\n' + after


def _under_moves(doc: str, line: str) -> str: return _under(doc, NEXT, line)


# ── VOICE LEAVES FOR STYLE.md, NOTES SWITCHED OFF WITHDRAW, AND THE ONE-TIME MOVE TO SECTIONS (phase C, 2026-10-23) ───────────────────────
def _sections(doc: str) -> list:
    """[(heading line, body)] - the document cut at its `## ` headings; the part above the first is ('', head)."""
    parts = re.split(r'(?m)^(?=## )', doc or '')
    return [('', parts[0])] + [(p.split('\n', 1)[0].rstrip('\r'), p.split('\n', 1)[1] if '\n' in p else '') for p in parts[1:]]


def _is_voice(heading: str) -> bool: return heading.startswith('## ') and any(w in heading.lower() for w in ('voice', 'style'))


def voice_out(store, actor: str = 'voice') -> list:
    """Every line under a voice heading leaves LEARNED.md for STYLE.md's "By recipient" (as a line for everyone), where the drafter
    reads it - the drafter never read LEARNED.md, so a voice lesson learned there reached triage and not the writer. The heading goes
    with its lines. Returns the texts moved. Never raises."""
    from . import byrecipient, learnedgraph as lg
    try:
        doc = store.get_doc(DOC) or ''
        secs = _sections(doc)
        moved, keep = [], []
        for h, body in secs:
            if not _is_voice(h): keep.append((h, body)); continue
            for raw in _PH.sub('', body).splitlines():
                t = raw.strip()
                if not t.startswith(('- ', '* ')): continue
                m = lg.TAG.match(raw)
                text = (m.group('text') if m else t[2:]).strip()
                byrecipient.add(store, byrecipient.EVERYONE, text, actor)
                moved.append(text)
                k = ((m.group('k') or '').strip() or lg._key(m.group('text'))) if m else lg._key(t)
                store.add_learned_event(k, text, 'live', int(m.group('s')) if m else 0, '', 'moved', actor)
                store._exec("INSERT INTO learned_line (Key,Reader,Text,Status,InDoc,InUseAt,Source,UpdatedAt) VALUES (?,?,?,?,0,?,?,?) ON CONFLICT(Key) "
                            "DO UPDATE SET Reader='drafter', Status='in_use', InDoc=0, InUseAt=COALESCE(InUseAt, excluded.InUseAt)",
                            (k, 'drafter', text, 'in_use', '-' if actor == 'migrate' else _today(), actor, _today()))
        if len(keep) == len(secs): return []
        new = ''.join((f'{h}\n{b}' if h else b) for h, b in keep)
        store.save_doc(DOC, new, actor)
        store._exec("UPDATE learned_line SET Reader='drafter', Status='in_use' WHERE Reader='drafter'")
        return moved
    except Exception as e:
        logger.warning(f'voice lessons not moved to STYLE.md: {e}'); return []


_PH = re.compile(r'_\([^)]*\)_', re.S)


def withdraw(store, mid: int) -> list:
    """A note switched off withdraws what it fed (phase C, 2026-10-23): its id leaves every line's evidence; a rule that went live
    because the owner had said it (auto_adopt) and no longer has OWNER_SAID switched-on verdicts behind it goes back to Proposed; a
    line with no evidence left goes. Returns the texts touched. Never raises."""
    from . import learnedgraph as lg
    try:
        doc, ev, said, touched = store.get_doc(DOC) or '', f'mem{int(mid)}', _said(store), []
        new = doc
        for raw, l in lg.walk(doc):
            if not l or ev not in l['ev']: continue
            rest = [e for e in l['ev'] if e != ev]
            touched.append(l['text'])
            new = new.replace(raw + '\n', '', 1).replace(raw, '', 1)
            if not rest:
                store.add_learned_event(l['key'], l['text'], l['status'], 0, ev, 'withdrawn', 'withdraw'); continue
            line = lg.fmt({**l, 'ev': rest})
            adopted = any(h['Actor'] == 'owner-verdicts' for h in store.learned_history(l['key']))
            if l['status'] == 'live' and adopted and len(said & set(rest)) < OWNER_SAID and PROP_START in new:
                new = _put_block(new, PROP_START, PROP_END, '\n'.join(filter(None, [_block(new, PROP_START, PROP_END), line])))
            else: new = _under(new, f"## {l['section']}", line) if l['status'] == 'live' else \
                        _put_block(new, HYP_START, HYP_END, '\n'.join(filter(None, [_block(new, HYP_START, HYP_END), line])))
        if new == doc: return []
        store.save_doc(DOC, new, 'withdraw')
        lg.record(store, doc, new, 'withdraw')
        return touched
    except Exception as e:
        logger.warning(f'note {mid} not withdrawn from LEARNED.md: {e}'); return []


OLD_NEXT = ('## moves',)


def migrate(store) -> bool:
    """LEARNED.md into one section per reader, once. Every live section that is not a voice section or Moves becomes a sub-section of
    "How you sort mail" (triage read all of them before, so nothing it read is lost); Moves becomes "What you do next"; voice leaves
    for STYLE.md; Proposed, Watching and the verdicts stay as they are. A line in use before keeps the date it went into use, so the
    move itself is not counted as this week's learning. Returns whether it rewrote the document. Never raises."""
    try:
        doc = store.get_doc(DOC) or ''
        if not doc.strip() or SORT in doc or HYP_START not in doc: return False
        from pathlib import Path
        tpl = (Path(__file__).parent / 'templates' / 'learned.md').read_text(encoding='utf-8')
        sort, nxt, rest = [], [], []
        head = _sections(doc)[0][1]
        if 'Taskuary writes this document itself' in head: head = _sections(tpl)[0][1]     # the shipped explainer, now about readers
        for h, body in _sections(doc)[1:]:
            gated = any(m in body for m in (HYP_START, PROP_START, VERD_START))
            if gated:
                rest.append((WATCH_HEADER if HYP_START in body else h, body)); continue
            if _is_voice(h): rest.append((h, body)); continue        # voice_out takes it from here, below
            meat = _PH.sub('', body).strip('\n')
            if h.lower().strip() in OLD_NEXT:
                if meat.strip(): nxt.append(meat.strip('\n'))
            elif meat.strip(): sort.append(f"### {h[3:].strip()}\n{meat.strip(chr(10))}")
        out = head.rstrip('\n') + f'\n\n{SORT}\n{SORT_INTRO}\n' + ''.join(f'\n{s}\n' for s in sort) + \
              f'\n{NEXT}\n{MOVES_INTRO}\n' + ''.join(f'{s}\n' for s in nxt) + '\n' + ''.join(f'{h}\n{b}' for h, b in rest)
        store.save_doc(DOC, out, 'migrate')
        voice_out(store, 'migrate')
        # in use before the move: the date its history says it went live, else unknown ('-', never this week)
        from .learnedgraph import lines
        for k in {l['key'] for l in lines(doc) if l['status'] == 'live'}:
            store._exec("UPDATE learned_line SET InUseAt=COALESCE((SELECT MIN(h.At) FROM learned_history h WHERE h.Key=? AND h.Status='live' AND h.Action<>'moved'), '-') "
                        "WHERE Key=? AND Status='in_use'", (k, k))
        logger.info('LEARNED.md: one section per reader - How you sort mail (triage), What you do next (the Advisor)')
        return True
    except Exception as e:
        logger.warning(f'LEARNED.md not moved to reader sections: {e}'); return False
