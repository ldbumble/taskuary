"""DIGEST.md - the rolling working memory, actually built.

The doc card always PROMISED "rebuilt every morning at 5:30", but no generator ever existed -
and a 5:30 schedule was the wrong shape anyway for an app that is a window you open, not a
service: at 5:30 it is closed, so the digest would simply never happen. It refreshes when the
app opens (once per day, after the startup catch-up has pulled the missed days in), so the
morning's first look already carries a synthesis of what happened while it was shut.
"""
from datetime import datetime, timedelta
from loguru import logger

DAYS = 3                 # the window the synthesis reads - matches the startup catch-up
WORDS = 350

SYSTEM = (
    "You maintain DIGEST.md: the owner's rolling morning brief. From the activity below, "
    "write what the owner, half awake, should hold in mind TODAY, "
    "in plain markdown bullets under {words} words:\n"
    "- what is in flight and who is waiting on whom (name tasks by their TQ-refs)\n"
    "- questions still unanswered, replies still unapproved\n"
    "- verdicts the owner gave recently that should keep being honored\n"
    "- patterns worth a heads-up (a sender getting louder, the same system failing twice)\n"
    "Never invent facts; omit sections with nothing to say; no preamble, no sign-off.")

HEADER = ('# DIGEST.md — your morning brief\n\n'
          '_What is in flight, distilled from recent activity when the app opens (once a day).\n'
          'For YOUR eyes - agents get their task\'s own context instead. Editable, but the next\n'
          'refresh overwrites it; durable rules belong in Agent memory (Settings) or SOUL.md._\n\n')


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


def build_digest(store, llm=None, days: int = DAYS) -> str:
    """The synthesis, or - with no AI connected - the tidy raw material itself: an empty doc
    is the one output that is never right."""
    raw = gather(store, days)
    stamp = datetime.now().strftime('%Y-%m-%d %H:%M')
    body = None
    if llm:
        try:
            body = (llm(SYSTEM.format(words=WORDS), f'Activity of the last {days} days:\n\n{raw}',
                        max_tokens=900) or '').strip()
        except Exception as e:
            logger.warning(f'digest synthesis failed: {e}')
    if not body:
        body = '_(no AI connected - the raw activity, unsynthesized)_\n\n```\n' + raw[:6000] + '\n```'
    return f'{HEADER}_refreshed {stamp}_\n\n{body}\n'


def refresh_if_stale(store) -> bool:
    """Once per day, and only when there is anything to say. The owner's hand-edits survive
    within the day; the daily refresh overwrites them by design (the card says so)."""
    row = store._one('SELECT UpdatedAt, UpdatedBy FROM doc WHERE Name=?', ('digest',)) or {}
    today = datetime.now().strftime('%Y-%m-%d')
    if str(row.get('UpdatedAt') or '').startswith(today) and row.get('UpdatedBy') == 'digest':
        return False
    from .llm import build_llm
    try: llm = build_llm(store)
    except Exception: llm = None
    store.save_doc('digest', build_digest(store, llm), 'digest')
    logger.info('DIGEST.md refreshed')
    return True
