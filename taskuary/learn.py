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

Hypotheses are never injected into prompts: a pattern seen once is a guess, and a guess in
a system prompt is a rule. Only promoted sections travel (injectable()) - and rules whose
effect is to HIDE mail never promote themselves at all: they wait in 'Proposed' for the
owner, because a wrong ignore-rule silences the very corrections that would revoke it.
"""
import re
from datetime import datetime, timedelta
from loguru import logger

DOC = 'learned'
REFLECT_AT = 3           # corrections that trigger a reflection; fewer still reflect daily
DAYS = 14                # the fallback event window when no reflection has ever run
HYP_START, HYP_END = '<!-- hypotheses:start -->', '<!-- hypotheses:end -->'
PROP_START, PROP_END = '<!-- proposed:start -->', '<!-- proposed:end -->'
VERD_START, VERD_END = '<!-- verdicts:start -->', '<!-- verdicts:end -->'
_GATED = re.compile(r'\n## [^\n]*\n+<!-- (hypotheses|proposed|verdicts):start -->.*?<!-- \1:end -->\n?', re.S)
VERD_HEADER = '## Verdicts - the evidence'
VERD_KEEP = 60           # the most recent verdict lines the doc shows; the table keeps them all

LESSON_SYSTEM = (
    'You maintain the Hypotheses section of LEARNED.md: patterns Taskuary is testing about how '
    'its owner works, distilled from their verdicts. You get the current section and ONE new '
    'event. Return the updated section: markdown bullets only - no headers, no fences, no preamble.\n'
    '- Infer the GENERAL preference the event reveals: voice and style, what they are responsible '
    'for, who matters to them, what deserves a task. Never a one-sender rule (standing notes '
    'handle those) and never a mere restatement of the event.\n'
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
    'episodes across 2+ different people or threads - one hot thread proves nothing general.\n'
    '- EXCEPTION: a rule whose effect is to hide or auto-file things ("treat X as fyi", "never a '
    'task") promotes only into "Proposed rules" - hiding is the owner\'s call to approve.\n'
    '- Add new hypotheses only for patterns 2+ episodes support; singles stay unwritten.\n'
    '- Never contradict SOUL.md (it outranks this file); never invent facts beyond the events.\n'
    '- Keep the section headers, all four <!-- --> marker lines, and every {{owner}}-style '
    'placeholder exactly as they are; keep the whole file under 120 lines.\n'
    '- End with a footer: _last reflection: date - what changed in a few words_ (replace any old one).')


def _today(): return datetime.now().strftime('%Y-%m-%d')
def _block(doc, a, b): return doc.split(a, 1)[1].split(b, 1)[0].strip() if (a in doc and b in doc) else None
def _put_block(doc, a, b, body):
    head, rest = doc.split(a, 1)
    return f'{head}{a}\n{body.strip()}\n{b}' + rest.split(b, 1)[1]
def _unfence(s): return re.sub(r'^```\w*\s*$|^```\s*$', '', (s or '').strip(), flags=re.M).strip()


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
    return out.strip()


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
        llm = llm or build_llm(store)
        doc = store.get_doc(DOC) or ''
        hyp = _block(doc, HYP_START, HYP_END)
        if llm is None or hyp is None: return
        out = _unfence(llm(LESSON_SYSTEM, f'(today: {_today()})\n\nCURRENT HYPOTHESES:\n{hyp[:3000]}'
                                          f'\n\nNEW EVENT:\n{event[:2000]}', max_tokens=700))
        # a broken answer never lands in the doc - markers inside it would corrupt the block splice
        if not out or '<!--' in out or len(out) > 6000: return
        if out != hyp: store.save_doc(DOC, _put_block(doc, HYP_START, HYP_END, out), 'learn')
        if n >= REFLECT_AT: reflect(store, llm)
    except Exception as e:
        logger.warning(f'learning skipped: {e}')


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
    return '\n'.join(out)


def reflect(store, llm=None) -> bool:
    """The consolidation: whole-doc rewrite against the event window. Modeled on digest.py's
    gather -> synthesize -> save_doc, but with NO no-AI fallback - a mechanical rewrite of a
    doc that feeds every prompt would poison them, and the old doc is always a valid answer."""
    from .llm import build_llm
    llm = llm or build_llm(store)
    doc, verdicts = _without_verdicts(store.get_doc(DOC) or '')   # RAW doc: {{owner}} tokens must survive the rewrite
    if not llm or not doc.strip(): return False
    since = (store.get_settings().get('learn_last_reflect')
             or (datetime.now() - timedelta(days=DAYS)).isoformat(sep=' ', timespec='seconds'))
    try:
        new = _unfence(llm(REFLECT_SYSTEM,
                           f'(today: {_today()})\n\nCURRENT LEARNED.md:\n{doc[:6000]}\n\n'
                           f"SOUL.md (context only - it outranks, never contradict it):\n{(store.doc('soul') or '')[:2500]}\n\n"
                           f'EVENTS SINCE {since}:\n{gather(store, since)[:5000]}', max_tokens=1800))
    except Exception as e:
        logger.warning(f'reflection failed: {e}'); return False
    # the 120-line budget in the prompt is a request; this is the law. A doc past the cap is a
    # model that ignored its instructions, and an ever-growing LEARNED.md would silently lose
    # its tail to the injection caps - the old doc is always the better answer than a bloated one.
    markers = (HYP_START, HYP_END, PROP_START, PROP_END)
    if not (new.startswith('#') and 200 < len(new) <= 12_000 and new.count('\n') <= 160
            and all(new.count(m) == 1 for m in markers)):
        logger.warning('reflection produced an unusable doc - kept the old one'); return False
    store.save_doc(DOC, new.rstrip('\n') + ('\n\n' + verdicts.strip('\n') + '\n' if verdicts else ''), 'reflect')
    store.set_setting('learn_pending', '0', 'reflect')
    store.set_setting('learn_last_reflect', datetime.now().isoformat(sep=' ', timespec='seconds'), 'reflect')
    logger.info('LEARNED.md reflected')
    return True


def reflect_if_due(store) -> bool:
    """Startup hook, digest-style: reflect when enough corrections queued (REFLECT_AT triggers
    it mid-day too, from learn_from), or once a day when at least one did - never on silence."""
    cfg = store.get_settings()
    if cfg.get('learn_enabled', '1') != '1': return False
    try: n = int(cfg.get('learn_pending') or 0)
    except ValueError: n = 0
    if n <= 0: return False
    if n < REFLECT_AT and (cfg.get('learn_last_reflect') or '').startswith(_today()): return False
    return reflect(store)
