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
from datetime import datetime
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


def render_past(rows: list) -> str:
    return '\n\n'.join(f"### {r['ref']} - {r['title']}  ({r['why']}, closed {r['closed']})\n" + (_short(r['report'], REPORT_CHARS) or '(no report was written)')
                       for r in rows)


def build(store, tid: int, msgs: list = None, repo: str = None) -> str:
    """The file's text. Sections the hub has nothing for are left out; an empty file is not written."""
    from .counsel import dossier, msg_of
    from .triage import strip_boilerplate
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
    allm = store.list_messages(tid)
    if len(allm) > 1:
        thread, used = [], 0
        for m in allm:
            who = 'THE OWNER' if m.get('Status') == 'context' else (m.get('FromName') or m.get('FromEmail') or '?')
            body = _short(strip_boilerplate(str(m.get('BodyText') or '')), 1500)
            line = f"--- {who} · {m.get('SentAt')} · {m.get('Channel')}\n{body}"
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

