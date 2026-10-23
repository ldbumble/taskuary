"""HOW THE OWNER WRITES TO EACH PERSON - STYLE.md's "By recipient", the drafter's own memory (phase C, 2026-10-23).

What an edited draft taught about the owner's voice was learned into LEARNED.md, which the drafter never reads (PW-058: that
document is triage's) - so the lesson reached triage, where it means nothing, and never the writer. And a Redraft's typed
instruction ("shorter", "no greeting") was used once and thrown away. Both land here now: one line per lesson, scoped to an address,
a domain, or everyone; the drafter reads the lines for whoever it writes to, closest first, within a budget. The owner, 2026-10-23:
the typed instruction is stored and remembered - the second time for the same person it becomes a style line - and no chips."""
import re

HEAD = '## By recipient'
INTRO = ('<!-- how you write to each person, learned from the drafts you edited and the redrafts you asked for. The drafter reads '
         'the lines for whoever it writes to, that person first, then their domain, then everyone. Yours to edit or delete. -->')
EVERYONE = 'everyone'
INSTR_AT = 2              # the same instruction this many times for one person is how they want to be written to
BUDGET = 1200
LINE = re.compile(r'^\s*-\s*\*\*(?P<who>[^*]+)\*\*:\s*(?P<text>.+?)\s*$')


def _norm(s: str) -> str: return ' '.join(re.findall(r'[a-z0-9]+', str(s or '').lower()))


def body(doc: str) -> str:
    if HEAD not in (doc or ''): return ''
    return doc.split(HEAD, 1)[1].split('\n## ', 1)[0]


def without(doc: str) -> str:
    """STYLE.md minus this section - style_doc's whole-document read must not carry every person's lines to every reply."""
    if HEAD not in (doc or ''): return doc or ''
    head, rest = doc.split(HEAD, 1)
    return head.rstrip('\n') + ('\n\n## ' + rest.split('\n## ', 1)[1] if '\n## ' in rest else '\n')


def lines(store) -> list:
    """[(who, text)] as the section holds them."""
    return [(m['who'].strip().lower(), m['text']) for l in body(store.get_doc('style') or '').splitlines() for m in [LINE.match(l)] if m]


def add(store, who: str, text: str, actor: str = 'voice') -> bool:
    """One lesson for `who` (an address, a domain, or everyone) - once: a line it already has is not written twice."""
    who, text = (str(who or '').strip().lower() or EVERYONE), ' '.join(str(text or '').split())
    if not text or any(w == who and _norm(t) == _norm(text) for w, t in lines(store)): return False
    doc, entry = store.get_doc('style') or '', f'- **{who}**: {text[:300]}'
    if HEAD in doc:
        head, rest = doc.split(HEAD, 1)
        parts = rest.split('\n## ', 1)
        doc = head + HEAD + parts[0].rstrip('\n') + '\n' + entry + '\n' + ('\n## ' + parts[1] if len(parts) > 1 else '')
    else: doc = doc.rstrip('\n') + f'\n\n{HEAD}\n{INTRO}\n{entry}\n'
    store.save_doc('style', doc, actor)
    return True


def _rank(who: str, to: set) -> int:
    if who in to: return 0
    if who in {a.rsplit('@', 1)[-1] for a in to if '@' in a}: return 1
    return 2 if who == EVERYONE else 9


def block(store, to, budget: int = BUDGET) -> str:
    """The lines for the people a draft goes to, closest first, whole lines within `budget`. '' when there are none."""
    to = {str(a or '').strip().lower() for a in ([to] if isinstance(to, str) else to or []) if str(a or '').strip()}
    ranked = sorted(((r, i, who, t) for i, (who, t) in enumerate(lines(store)) for r in [_rank(who, to)] if r < 9))
    out, used = [], 0
    for _, _, who, t in ranked:
        l = f'- {t}' + ('' if who == EVERYONE else f' (to {who})')
        if used + len(l) > budget: continue
        out.append(l); used += len(l) + 1
    return '\n'.join(out)


def note_instruction(store, rid: int, instruction: str) -> str:
    """The owner's words for a draft are kept on its review (presses.instructions, phase B); said INSTR_AT times for one person - on
    their own drafts, any surface - they become that person's STYLE.md line, which every later draft to them reads. Returns the line
    when one was written, else ''. Never raises - the draft itself already happened."""
    try:
        from . import presses
        said, n = ' '.join(str(instruction or '').split()), _norm(instruction)
        mine = next((i for i in presses.instructions(store) if i['rid'] == int(rid)), None)
        if not said or not mine or not mine['to']: return ''
        k = len({i['rid'] for i in presses.instructions(store, to=mine['to']) if _norm(i['text']) == n})
        return said if k >= INSTR_AT and add(store, mine['to'], said) else ''
    except Exception as e:
        from loguru import logger
        logger.warning(f'the instruction did not reach STYLE.md: {e}'); return ''
