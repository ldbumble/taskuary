"""THE OWNER'S OWN HISTORY, FOR AN AGENT: Taskuary's mail and messages, searched by sender, subject, words and date - read-only.

A researcher asked to read a colleague's email about a meeting topic had no way into the history Taskuary already holds, so it wrote
code of its own to go and find the mail (the owner, 2026-10-21: it should look in Taskuary's own history first). This is that way in,
behind `taskuary --search` / `--message` (cli.py) and GET /api/agent/messages (server.py): a session reads it on its OWN task
(guard.owns_task), and a stranger's session never (guard.stranger_denied refuses it, and its brief does not name it).
"""
import re
from .routing import tokens
from .store import task_ref

SNIP = 240


def _who(r: dict) -> str:
    name, mail = str(r.get('FromName') or '').strip(), str(r.get('FromEmail') or '').strip()
    return f'{name} <{mail}>' if name and mail and name != mail else name or mail or '?'


def _hit(r: dict) -> dict:
    body = ' '.join(str(r.get('Preview') or r.get('BodyText') or '').split())
    return {'id': r['MessageId'], 'when': str(r.get('SentAt') or ''), 'from': _who(r), 'subject': str(r.get('Subject') or ''),
            'snippet': body[:SNIP] + ('…' if len(body) > SNIP else ''), 'thread': str(r.get('ConversationId') or ''),
            'channel': str(r.get('Channel') or ''), 'task': task_ref(r['TaskId']) if r.get('TaskId') else ''}


def search(store, sender: str = '', subject: str = '', words: str = '', since: str = '', until: str = '', limit: int = 20) -> list:
    """Messages matching every filter given, best match first when there are words, else newest first. `since`/`until` are dates
    (YYYY-MM-DD) on when it was SENT, `until` inclusive. The Assistant's own chat is not mail and is never a hit."""
    who, subj = str(sender or '').strip().lower(), str(subject or '').strip().lower()
    want = tokens(f'{subject or ""} {words or ""}')
    lo, hi = str(since or '').strip()[:10], str(until or '').strip()[:10]
    limit = max(1, min(int(limit or 20), 100))
    ids = store.message_search(want, who, 3650) if (want or who) else None
    if ids is None:                                  # no index (or nothing to match on): the newest, scanned
        from .concierge import newest_rows
        rows = newest_rows(store, 3650)
    else:
        rank = {i: n for n, i in enumerate(ids)}
        rows = sorted(store.feed(limit=len(ids) or 1, days=3650, ids=ids, live_state=()), key=lambda r: rank[r['MessageId']])
    out = []
    for r in rows:
        if r.get('Channel') == 'assistant': continue
        if who and who not in f"{r.get('FromName') or ''} {r.get('FromEmail') or ''}".lower(): continue
        if subj and subj not in str(r.get('Subject') or '').lower(): continue
        if ids is None and want and not set(want) <= set(tokens(f"{r.get('Subject') or ''} {r.get('Preview') or ''} {_who(r)}")): continue
        sent = str(r.get('SentAt') or '')[:10]
        if (lo and sent < lo) or (hi and sent > hi): continue
        out.append(_hit(r))
        if len(out) >= limit: break
    return out


def message_id(x) -> int:
    """A message's id as Taskuary writes it anywhere an agent reads one: 1073, '1073', 'm1073' (the Assistant's and the brief's own
    spelling), '[1073]' or '#1073'. The agent was handed "message m1073" and read_message and `--message` both refused it as no number,
    twice each, before it gave up on the mail (2026-10-28). Structure only - an id, never words."""
    if isinstance(x, bool): raise ValueError(f'{x!r} is not a message id - one looks like m1073 or 1073')
    if isinstance(x, int): return x
    m = re.fullmatch(r'\s*[\[#(]?\s*[mM]?\s*(\d+)\s*[\])]?\s*', str(x if x is not None else ''))
    if not m: raise ValueError(f'{str(x)[:40]!r} is not a message id - one looks like m1073 or 1073 (search_messages lists them)')
    return int(m.group(1))


def message(store, mid) -> dict | None:
    """One message in full, with the thread it is on (oldest first, the owner's own replies included) - None when there is none."""
    m = store.get_message(message_id(mid))
    if not m or m.get('Channel') == 'assistant': return None
    thread = store.thread_messages(m.get('ConversationId'), m.get('Subject'), 40) or [m]
    return {**_hit(m), 'body': str(m.get('BodyText') or ''), 'to': str(m.get('RecipientsJson') or ''),
            'messages': [_hit(x) for x in thread if x.get('Channel') != 'assistant']}


def says(hits: list) -> str:
    """The hits as an agent reads them at its prompt: one block each, the id first - what `taskuary --message ID` opens."""
    if not hits: return 'No message in Taskuary matches that. Try fewer words, only --from, or a wider date range.'
    return '\n\n'.join(f"[{h['id']}] {h['when']} - {h['from']}\n{h['subject']}" + (f"  ({h['task']})" if h['task'] else '')
                       + (f"\nthread {h['thread']}" if h['thread'] else '') + (f"\n{h['snippet']}" if h['snippet'] else '') for h in hits)


def meeting_reads(store, who: list, subject: str, per: int = 3, cap: int = 12) -> list:
    """What the saved mail already says about a meeting's people and its subject - the opening reads of Prepare (the owner,
    2026-10-25: "an agent to research about person and topic through your mails"). Handed to the agent in its brief, so a brain
    with no shell starts from the same history a CLI would search; the agent searches on from there."""
    out, seen = [], set()
    asks = [{'sender': w} for w in (who or [])[:6] if str(w or '').strip()] + ([{'words': subject}] if str(subject or '').strip() else [])
    for q in asks:
        try: hits = search(store, limit=per if 'sender' in q else per + 2, **q)
        except Exception: hits = []
        for h in hits:
            if h['id'] in seen: continue
            seen.add(h['id']); out.append(h)
    return out[:cap]
