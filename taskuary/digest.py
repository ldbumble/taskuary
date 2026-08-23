"""The morning brief's raw material - and the Morning digest REPORT that delivers it.

The digest used to be its own once-a-day machinery writing only the DIGEST.md doc, which
nobody opened: a brief nobody reads is not a brief. It is a REPORT now (reports.run_digest,
seeded on first run): the summary lands on the Timeline where mornings actually start, the
prompt below is edited like any report's on the Reports tab, deleting the source turns the
whole thing off - and the same run keeps DIGEST.md fresh for the Docs tab.
"""
from datetime import datetime, timedelta

DAYS = 3                 # the window the synthesis reads - matches the startup catch-up                 # the window the synthesis reads - matches the startup catch-up

# The seeded report's editable instruction - "configure what goes in there" IS this text,
# on the Reports tab. reports.AI_SYSTEM wraps it; this is only the ask.
PROMPT = (
    'Write what the owner, half awake, should hold in mind TODAY, under 350 words, grouped into '
    'sections. Each section is its emoji header on its own line, then tight "- " bullets under it '
    '(one fact per bullet, tasks named by their TQ-refs), then a blank line. Use exactly these '
    'sections in this order, and OMIT any with nothing to say:\n'
    '\U0001f680 In flight — what is being worked and who is waiting on whom\n'
    '⏳ Waiting on you — questions still unanswered, replies still unapproved\n'
    '\U0001f4cc Keep honoring — verdicts you gave recently that should keep applying\n'
    '\U0001f4c8 Patterns — heads-ups (a sender getting louder, the same system failing twice)\n'
    'Never invent facts; no preamble, no sign-off, nothing outside the sections.')

# every prompt ever SHIPPED, so store.__init__ can tell "still the stock text" (upgrade it)
# from "the owner wrote this" (never touch) - same deal the template docs get
OLD_PROMPTS = (
    'Write what the owner, half awake, should hold in mind TODAY, in plain bullets under 350 words:\n'
    '- what is in flight and who is waiting on whom (name tasks by their TQ-refs)\n'
    '- questions still unanswered, replies still unapproved\n'
    '- verdicts the owner gave recently that should keep being honored\n'
    '- patterns worth a heads-up (a sender getting louder, the same system failing twice)\n'
    'Never invent facts; omit sections with nothing to say; no preamble, no sign-off.',
)

HEADER = ('# DIGEST.md — your morning brief\n\n'
          '_Written by the Morning digest report (Reports tab - its prompt decides what goes in\n'
          "here; deleting the report turns it off). For YOUR eyes - agents get their task's own\n"
          'context instead. Durable rules belong in Agent memory (Settings) or SOUL.md._\n\n')


def gather(store, days: int = DAYS) -> str:
    """The raw material, compact enough to hand an AI whole."""
    since = (datetime.now() - timedelta(days=days)).isoformat(sep=' ', timespec='seconds')
    out = []
    tasks = store.list_tasks()
    live = [t for t in tasks if t.get('Status') in ('open', 'in_progress', 'waiting')]
    out.append('OPEN WORK:')
    for t in live[:25]:
        out.append(f"  TQ-{t['TaskId']:04d} [{t['Status']}] {t.get('Title') or ''} "
                   f"(kind {t.get('Kind')}, created {t.get('CreatedAt')})")
    done = [t for t in tasks if t.get('Status') == 'done' and str(t.get('UpdatedAt') or '') >= since]
    out.append('FINISHED THIS WINDOW:')
    out += [f"  TQ-{t['TaskId']:04d} {t.get('Title') or ''}" for t in done[:20]]
    pend = store.list_reviews('pending')
    out.append('WAITING ON THE OWNER (pending reviews):')
    out += [f"  TQ-{r['TaskId']:04d} {r.get('Kind')}: {(r.get('Subject') or r.get('Title') or '')[:90]}" for r in pend[:15]]
    notes = [m for m in store.list_memories() if str(m.get('CreatedAt') or '') >= since]
    out.append('VERDICTS GIVEN THIS WINDOW (already durable in memory):')
    out += [f"  [{m.get('Scope')}:{m.get('ScopeKey') or '*'}] {(m.get('Note') or '')[:110]}" for m in notes[:12]]
    msgs = store.feed(limit=120, days=days)
    senders = {}
    for m in msgs:
        who = m.get('FromName') or m.get('FromEmail') or m.get('SourceName') or '?'
        senders[who] = senders.get(who, 0) + 1
    loud = sorted(senders.items(), key=lambda kv: -kv[1])[:8]
    out.append('WHO WROTE, HOW OFTEN:')
    out += [f'  {who}: {n}' for who, n in loud]
    return '\n'.join(out)


# build_digest / refresh_if_stale used to live here - their whole job (schedule, AI pass,
# no-AI fallback, filing) is what the reports pipeline already does, so the Morning digest
# report replaced them: reports.run_digest is the executor, run_report_source keeps the doc.
