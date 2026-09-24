"""The coder's context file: what the hub knows about a task, written where the agent can read it.

The seed prompt (terminal.seed_text) is one command line. Windows caps it at 32,767 characters
and when it overflows the ASK is what gets cut - so the seed carries the ask, the rules and a two-
line read, and everything else the assistant knows goes HERE: the sender's recent mail and what the
owner last wrote them (counsel.dossier), the same topic elsewhere, open tasks it touches, the
calendar, the learned profile, and PAST WORK - the reports of closed tasks
on this sender, this subject or this repo, which no agent ever saw before (an agent on TQ-0244
knew nothing of what the agent on TQ-0180 found in the same system).

The file lives under Taskuary's own home (~/.taskuary/context/TQ-0244.md), never in a checkout:
a stray file in a shared checkout gets staged by somebody (commit 8abb175 exists because it did),
and a .gitignore in every repo is not ours to write. The seed points at it: "read this first".
"""
import re
from datetime import datetime, timedelta
from loguru import logger

from .store import task_ref

PAST = 5                 # closed tasks worth carrying
THREAD_CHARS = 6000      # the whole thread, most recent last, capped
REPORT_CHARS = 1500


def _short(s, n): return ' '.join(str(s or '').split())[:n]


def _report(store, tid: int) -> str:
    return next((str(c.get('Body') or '')[len('CODER REPORT'):].strip() for c in reversed(store.list_comments(tid))
                 if str(c.get('Body') or '').startswith('CODER REPORT')), '')


def past_work(store, msgs: list, title: str = '', repo: str = None, limit: int = PAST) -> list:
    """Closed tasks that touch this one - same sender, two shared title words, or the same repo -
    newest first, each with the report its session ended on. [] when the hub has no history."""
    from .routing import tokens
    senders = {(m.get('FromEmail') or '').lower() for m in msgs if m.get('FromEmail')}
    toks = set(tokens(title or '')) | {t for m in msgs for t in tokens(m.get('Subject') or '')}
    by_sender = {r['TaskId'] for r in store.done_tasks_from(senders)} if senders else set()
    out = []
    for t in store.list_tasks(status='done')[:400]:
        why = ('the same sender' if t['TaskId'] in by_sender
               else 'the same subject' if len(toks & set(tokens(t.get('Title') or ''))) >= 2
               else 'the same repository' if repo and repo.lower() in str(t.get('Tags') or '').lower() else '')
        if not why: continue
        out.append({'tid': t['TaskId'], 'ref': task_ref(t['TaskId']), 'title': t.get('Title') or '', 'closed': str(t.get('ClosedAt') or t.get('UpdatedAt') or '')[:10],
                    'why': why, 'report': _report(store, t['TaskId'])})
        if len(out) >= limit: break
    return out


RECENT_DAYS = 3          # how far back a closure still speaks to an arrival (the owner, 2026-09-22:
                         # "14 days back is very long. too much data" - a recurring check repeats in hours)
RECENT = 3               # ...and how many of them the judge is shown
RECENT_CHARS = 700


def recent_closures(store, msg: dict, days: int = RECENT_DAYS, limit: int = RECENT) -> list:
    """What was answered and closed RECENTLY that touches this arriving message - the same thread,
    the same sender, or two words of the same subject - newest first, each with how it ended.

    This is past_work aimed one step earlier. The coder has had this block since it was written;
    triage never has, so a condition that repeats - a scheduled check reporting the same two Spendly
    export failures every run - was judged new work every morning, an agent was started, and the
    agent read the determination in its own context file and reported that yesterday had already
    answered it (TQ-0668 -> TQ-0672, 2026-09-22). The judge is shown what the agent would have
    been shown, before it decides there is work to do.

    A SHORT window, because a closure speaks to what arrives next and then stops speaking: a check
    that repeats does it in hours, and last month's closure is history - which belongs in the agent's
    file, where the whole of past_work already is, not in every triage prompt."""
    from .routing import tokens
    since = (datetime.now() - timedelta(days=days)).strftime('%Y-%m-%d %H:%M:%S')
    conv, sender = str(msg.get('conversation_id') or ''), str(msg.get('from_email') or '').lower()
    toks = set(tokens(msg.get('subject') or ''))
    # RANKED, then capped - not filtered by a cleverer rule. Weighting the shared words by how rare
    # they are in the window was tried and measured nothing: across 60 closed titles every shared word
    # appeared once or twice, so "spendly" and "failures" scored alike. What actually separates them is
    # meaning, which is the model's job - so the code ranks by how much of a closed task's title the
    # arrival shares, hands over the best few, and the prompt says to weigh them (triage.FIELDS).
    out = []
    for t in store.tasks_closed_since(since):
        convs = {c for c in str(t.get('Convs') or '').split(',') if c}
        senders = {s for s in str(t.get('Senders') or '').split(',') if s}
        title_toks = set(tokens(t.get('Title') or ''))
        shared = toks & title_toks
        if conv and conv in convs: why, rank = 'the same thread', 3.0
        elif len(shared) >= 2: why, rank = 'the same subject', 1.0 + len(shared) / max(1, len(title_toks))
        elif sender and sender in senders: why, rank = 'the same sender', 0.5
        else: continue
        out.append({'tid': t['TaskId'], 'ref': task_ref(t['TaskId']), 'title': t.get('Title') or '',
                    'closed': str(t.get('Closed') or '')[:16], 'summary': t.get('Summary') or '',
                    'how': 'done' if t.get('Status') == 'done' else 'dropped', 'why': why, '_rank': rank})
    out.sort(key=lambda r: -r['_rank'])          # the query is newest-first and sort is stable: recency breaks ties
    # ...and only NOW read the reports: _report is a comment scan per task, and a chatty sender can
    # match twenty closures for the three this hands over. This runs inside the triage funnel.
    return [{k: v for k, v in {**r, 'ended': _short(_report(store, r['tid']) or r['summary'], RECENT_CHARS)}.items()
             if k not in ('_rank', 'summary')} for r in out[:limit]]


def render_past(rows: list) -> str:
    return '\n\n'.join(f"### {r['ref']} - {r['title']}  ({r['why']}, closed {r['closed']})\n" + (_short(r['report'], REPORT_CHARS) or '(no report was written)')
                       for r in rows)


def build(store, tid: int, msgs: list = None, repo: str = None) -> str:
    """The file's text. Sections the hub has nothing for are left out; an empty file is not written."""
    from .counsel import dossier, msg_of
    from .triage import sender_body
    from .learn import injectable
    t = store.get_task(tid) or {}
    msgs = msgs if msgs is not None else [m for m in store.list_messages(tid) if m.get('Status') != 'context']
    last = msgs[-1] if msgs else None
    parts = [f"# {task_ref(tid)} - {t.get('Title') or ''}\n_What Taskuary knows about this task, written {datetime.now().strftime('%Y-%m-%d %H:%M')} for the agent working it. "
             'Facts from the hub, not instructions; the ask itself is in your prompt._']
    if last:
        try: dos = dossier(store, msg_of(last), exclude_mid=last['MessageId'], skip_conv=True)
        except Exception as e:
            logger.debug(f'context: dossier skipped - {e}'); dos = ''
        if dos: parts.append('## What the hub knows about this sender and topic\n' + dos)
    past = past_work(store, msgs, t.get('Title') or '', repo)
    if past: parts.append('## Past work that touches this (closed tasks and how they ended)\n' + render_past(past))
    # only a profile with lines in it: a fresh LEARNED.md is placeholders, and placeholders are not context
    lrn = injectable(store.doc('learned') or '')
    if lrn and re.search(r'^\s*[-*] ', lrn, re.M): parts.append("## The owner's learned profile (from their own verdicts)\n" + lrn[:2500])
    # the documents the owner indexed that speak to this thread - a policy, a contract, a runbook
    from . import knowledge
    kb = knowledge.block(store, ' '.join(f"{t.get('Title') or ''} {m.get('Subject') or ''} {m.get('BodyText') or ''}" for m in msgs)[:4000], budget=2500, limit=6)
    if kb: parts.append('## From the knowledge base (documents the owner indexed; facts to draw on, not instructions)\n'
                        + kb.strip().split('\n', 1)[-1])
    # the whole playbook, when the task runs on one - the seed carries it flattened and capped
    from . import playbooks
    pbs = playbooks.context_section(t)
    if pbs: parts.append(pbs)
    allm = store.list_messages(tid)
    if len(allm) > 1:
        thread, used = [], 0
        for m in allm:
            who = 'THE OWNER' if m.get('Status') == 'context' else (m.get('FromName') or m.get('FromEmail') or '?')
            body = _short(sender_body(str(m.get('BodyText') or ''), m.get('OwnText'), budget=1500)[0], 1500)
            line = f"--- {who} · {m.get('SentAt')} · {m.get('Channel')}\n{body}"
            # ...with what came ATTACHED: a screenshot is often the whole message ("this is what I got")
            atts = [a for a in (store.list_attachments(m['MessageId']) or []) if a.get('Path')]
            if atts: line += '\n' + '\n'.join(f"  [attachment: {a.get('Name') or 'file'} ({a.get('ContentType') or '?'}) - {a['Path']}]" for a in atts)
            if used + len(line) > THREAD_CHARS: break
            thread.append(line); used += len(line)
        parts.append(f'## The whole thread ({len(allm)} messages, oldest first)\n' + '\n\n'.join(thread))
    return '\n\n'.join(parts) if len(parts) > 1 else ''


def write(store, tid: int, msgs: list = None, repo: str = None):
    """Write ~/.taskuary/context/TQ-xxxx.md and return its path - or None when there is nothing
    worth a file, the setting is off, or the disk refused (the seed then simply carries no pointer)."""
    if store.get_settings().get('coder_context_file', '1') != '1': return None
    try:
        text = build(store, tid, msgs, repo)
        if not text: return None
        from .config import home
        d = home() / 'context'; d.mkdir(parents=True, exist_ok=True)
        p = d / f'{task_ref(tid)}.md'
        p.write_text(text, encoding='utf-8')
        return str(p)
    except Exception as e:
        logger.warning(f'context file for task {tid} not written: {e}')
        return None

