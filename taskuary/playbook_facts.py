"""Facts about a KIND of work, from the outcome ledger into the playbook it belongs to (spec 2026-10-12, build step 5). The
NUMBERS are the ledger's (outcomes.work_facts); what they mean is the model's, read at reflection. It never edits a playbook:
the block it writes reaches the page as an `amend_playbook` proposal, a review with no task, for the owner's yes."""
import json
from loguru import logger
from . import outcomes, playbooks
from .llm import build_llm
from .people_pages import splice

SYSTEM = ("You add what the outcome ledger shows about one KIND of work to the playbook the owner keeps for it. Return 3 to 6 "
          "markdown bullet lines, each one fact about how this work goes - what makes a close come open again, what to settle before "
          "closing - each ending with the evidence ids in brackets like [ev: out12, out15]. Only what the numbers and the lines support; "
          "never a number the facts do not carry. Return nothing at all when the facts say nothing yet.")


def facts_text(store, slug: str) -> str:
    f = outcomes.work_facts(store, slug)
    return (f"{f['closes']} closes; {f['reopened']} came open again\n"
            f"{f['closed_with_open_question']} closed with the last mail still asking something; {f['reopened_after_open_question']} of those came open again")


def pending(store, slug: str) -> bool:
    """One open proposal per playbook: the next reflection waits for the owner's answer on this one."""
    return any(json.loads(r.get('DraftText') or '{}').get('slug') == slug for r in
               store._rows("SELECT DraftText FROM review WHERE TaskId IS NULL AND Kind='action' AND Status='pending' AND DraftText LIKE '%amend_playbook%'"))


def compile(store, slug: str, llm=None):
    """One small call: the numbers and the ledger's lines in, bullet facts out, spliced into the playbook's marked block and filed
    as a proposal. The review id, or None when there is no brain, no playbook, an open proposal already, or nothing to say."""
    page = playbooks.read(slug)
    if not page or pending(store, slug): return None
    brain = llm or build_llm(store)
    if not brain: return None
    facts = facts_text(store, slug)
    ev = [f"out{r['Id']}: {outcomes._sentence(store, r)}" for r in store._rows(
        "SELECT * FROM outcome WHERE Kind='task.closed' AND ResolvedAt IS NOT NULL AND json_extract(FactsJson, '$.playbook')=? ORDER BY Id DESC LIMIT 20", (slug,))]
    text = str(brain(SYSTEM, f"PLAYBOOK: {slug}\n\n{page[:2000]}\n\nTHE NUMBERS:\n{facts}\n\nTHE LINES:\n" + '\n'.join(ev), max_tokens=400) or '').strip()
    lines = [l for l in text.splitlines() if l.strip().startswith('-')]
    if not lines: return None
    body = "## From the ledger\n\n_Counted by the outcome ledger; the lines are read from the numbers._\n\n" + '\n'.join(lines) + f"\n\n```\n{facts}\n```"
    # `block` is what is applied: spliced into the page AS IT IS when the owner says yes, so an edit made while this waited survives
    # (the review, 2026-10-12); `text` is the page as it would read today, for the card
    p = {'action': 'amend_playbook', 'slug': slug, 'block': body, 'text': splice(page, body), 'why': facts.replace('\n', '; ')}
    rid = store.add_review({'TaskId': None, 'Kind': 'action', 'Status': 'pending', 'DraftText': json.dumps(p), 'Reason': f"the ledger's facts about {slug}"})
    store.audit('review', rid, 'proposed', 'reflect', detail={'action': 'amend_playbook', 'slug': slug})
    return rid


def refresh(store, llm=None, limit: int = 3, min_closes: int = 5) -> list:
    """At reflection: the playbooks with `min_closes` or more resolved closes, most first, one small call each."""
    if store.get_setting('playbooks_enabled', '1') != '1': return []
    rows = store._rows("SELECT json_extract(FactsJson, '$.playbook') slug, COUNT(*) n FROM outcome WHERE Kind='task.closed' AND ResolvedAt IS NOT NULL "
                       "AND json_extract(FactsJson, '$.playbook') IS NOT NULL GROUP BY slug HAVING n>=? ORDER BY n DESC LIMIT ?", (min_closes, limit))
    out = []
    for r in rows:
        try:
            if compile(store, r['slug'], llm): out.append(r['slug'])
        except Exception as e: logger.warning(f"playbook facts for {r['slug']} skipped: {e}")
    return out
