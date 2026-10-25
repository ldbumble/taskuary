"""A page per person, derived from the outcome ledger (spec 2026-10-12, build step 4; the 2026-08-28 company-brain verdict:
compiled pages per sender, quoted as data). The NUMBERS are the ledger's (outcomes.person_facts); what they mean is the
model's, written at reflection inside a marked block so the owner's own lines on the page survive. Read by counsel.dossier,
which is how the reply drafter, triage's context, meeting prep and the Advisor's bigger read all see it."""
from datetime import datetime, timedelta
from loguru import logger
from . import outcomes
from .llm import build_llm

START, END = '<!-- ledger:start -->', '<!-- ledger:end -->'
SYSTEM = ("You write the one page Taskuary keeps about a person the owner deals with, from the outcome ledger's facts about them. "
          "Return 3 to 10 markdown bullet lines, each one fact about how this person works with the owner - how fast they answer, "
          "whether a chase is needed, who on copy moves them, what they deliver late - each ending with the evidence ids in "
          "brackets like [ev: out12, out15]. Only what the numbers and the lines support; never a number the facts do not carry; "
          "nothing about their character. Return nothing at all when the facts say nothing yet.")

def doc_name(who: str) -> str: return f"person-{str(who or '').lower()}"
def who_of(name: str) -> str: return name[7:] if str(name or '').startswith('person-') else ''


def facts_text(store, who: str) -> str:
    f = outcomes.person_facts(store, who)
    lines = [f"{f['replies']} replies sent to them; answered {f['answered']}" + (f", median {f['median_days']:.1f} days" if f['median_days'] is not None else ''),
             f"{f['chased']} were chases; {f['answered_after_chase']} of those got an answer",
             f"{f['steps']} steps they owed closed; {f['steps_late']} late", f"let go {f['let_go']} times"]
    lines += [f"copied {a}: answered {n} of {m}" for a, (n, m) in f['cc'].items()]
    return '\n'.join(lines)


def splice(doc: str, body: str) -> str:
    """The marked block replaced in place, or appended when the page has none - the owner's lines are never touched."""
    block = f"{START}\n{body.strip()}\n{END}"
    doc = doc or ''
    if START in doc and END in doc:
        head, rest = doc.split(START, 1); return f"{head}{block}{rest.split(END, 1)[1]}"
    return (doc.rstrip('\n') + '\n\n' if doc.strip() else '') + block + '\n'


def compile(store, who: str, llm=None):
    """One small call on the light brain: the numbers and the ledger's lines about them in, bullet facts out, spliced into
    the page. None when there is no brain or it had nothing to say - a page is never written empty."""
    who = str(who or '').lower()
    brain = llm or build_llm(store, job='memory')
    if not brain: return None
    facts = facts_text(store, who)
    ev = [f"out{r['Id']}: {outcomes._sentence(store, r)}" for r in outcomes._rows_who(store, who) if r.get('ResolvedAt')][-20:]
    text = str(brain(SYSTEM, f"PERSON: {who}\n\nTHE NUMBERS:\n{facts}\n\nTHE LINES:\n" + '\n'.join(ev), max_tokens=400) or '').strip()
    lines = [l for l in text.splitlines() if l.strip().startswith('-')]
    if not lines: return None
    stamp = datetime.now().strftime('%Y-%m-%d')
    body = f"_From the outcome ledger, {stamp}. The numbers are counted; the lines are read from them._\n\n" + '\n'.join(lines) + f"\n\n```\n{facts}\n```"
    name = doc_name(who)
    store.save_doc(name, splice(store.get_doc(name) or '', body), 'reflect')
    return name


def refresh(store, llm=None, limit: int = 5, days: int = 30) -> list:
    """At reflection: the people with three or more resolved rows in the window, most first, one small call each."""
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d')
    rows = store._rows("SELECT json_extract(FactsJson, '$.who') AS who, COUNT(*) AS n FROM outcome WHERE ResolvedAt IS NOT NULL AND At>=? "
                       "AND json_extract(FactsJson, '$.who') IS NOT NULL AND json_extract(FactsJson, '$.who')!='' GROUP BY who HAVING n>=3 ORDER BY n DESC LIMIT ?",
                       (since, limit))
    from .autoreply import STATUS as AUTO
    me = str(store.get_setting('owner_email', '') or '').lower()
    out = []
    for r in rows:
        # not a page about the owner, and none about a mailbox that only ever auto-replies
        if r['who'] == me or store._one('SELECT 1 x FROM message WHERE lower(FromEmail)=? AND Status=? LIMIT 1', (r['who'], AUTO)): continue
        try:
            if compile(store, r['who'], llm): out.append(r['who'])
        except Exception as e: logger.warning(f"people_pages: {r['who']} not compiled - {e}")
    return out


def pages(store) -> list:
    out = []
    for n in store.doc_names():
        w = who_of(n)
        if not w: continue
        row = store.get_doc_row(n) or {}
        out.append({'who': w, 'name': n, 'updated': row.get('UpdatedAt'), 'lines': sum(1 for l in str(row.get('Content') or '').splitlines() if l.strip().startswith('-'))})
    return sorted(out, key=lambda p: p['who'])
