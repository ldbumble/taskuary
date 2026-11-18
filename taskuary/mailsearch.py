"""THE OWNER'S OWN HISTORY, FOR AN AGENT: Taskuary's mail and messages, searched by sender, subject, words and date - read-only.

A researcher asked to read a colleague's email about a meeting topic had no way into the history Taskuary already holds, so it wrote
code of its own to go and find the mail (the owner, 2026-10-21: it should look in Taskuary's own history first). This is that way in,
behind `taskuary --search` / `--message` (cli.py) and GET /api/agent/messages (server.py): a session reads it on its OWN task
(guard.owns_task), and a stranger's session never (guard.stranger_denied refuses it, and its brief does not name it).
"""
import re
from datetime import date
from .routing import tokens
from .store import task_ref
from . import textsim
from .agenttools import echo as _echo                 # a value the agent gave, bounded with its cut marked

SNIP = 240


def _who(r: dict) -> str:
    name, mail = str(r.get('FromName') or '').strip(), str(r.get('FromEmail') or '').strip()
    return f'{name} <{mail}>' if name and mail and name != mail else name or mail or '?'


def _hit(r: dict) -> dict:
    body = ' '.join(str(r.get('Preview') or r.get('BodyText') or '').split())
    return {'id': r['MessageId'], 'when': str(r.get('SentAt') or ''), 'from': _who(r), 'subject': str(r.get('Subject') or ''),
            'snippet': body[:SNIP] + ('…' if len(body) > SNIP else ''), 'thread': str(r.get('ConversationId') or ''),
            'channel': str(r.get('Channel') or ''), 'task': task_ref(r['TaskId']) if r.get('TaskId') else ''}


def _day(x, name: str) -> str:
    """A date filter as YYYY-MM-DD, '' when none is given. One it cannot read is a ValueError: compared as text, "yesterday" filtered out
    every message and the agent was told nothing matched - about the mailbox, when the trouble was the date."""
    d = str(x or '').strip()[:10]
    if not d: return ''
    try: return date.fromisoformat(d).isoformat()
    except ValueError: raise ValueError(f'{name} {_echo(x, 40)!r} is not a date - give it as YYYY-MM-DD') from None


def search(store, sender: str = '', subject: str = '', words: str = '', since: str = '', until: str = '', limit: int = 20) -> list:
    """Messages matching every filter given, best match first when there are words, else newest first. `since`/`until` are dates
    (YYYY-MM-DD) on when it was SENT, `until` inclusive. The Assistant's own chat is not mail and is never a hit."""
    who, subj = str(sender or '').strip().lower(), str(subject or '').strip().lower()
    want = tokens(f'{subject or ""} {words or ""}')
    lo, hi = _day(since, 'since'), _day(until, 'until')
    try: limit = max(1, min(int(limit or 20), 100))
    except (TypeError, ValueError): raise ValueError(f'limit {_echo(limit, 20)!r} is not a number - give how many messages, like 20') from None
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
    if not m:
        from .agenttools import refusal
        raise ValueError(refusal(f'{_echo(x, 40)!r} is not a message id - one looks like m1073 or 1073', see=('search_messages', 'lists them')))
    return int(m.group(1))


def message(store, mid) -> dict | None:
    """One message in full, with the thread it is on (oldest first, the owner's own replies included) and its attachments by the ids
    read_attachment and sign_form take, by either door - None when there is none."""
    m = store.get_message(message_id(mid))
    if not m or m.get('Channel') == 'assistant': return None
    thread = store.thread_messages(m.get('ConversationId'), m.get('Subject'), 40) or [m]
    # ...with the addresses its words carry (channels.kept_links): "pay at the link below" was read whole and still had no link in it
    from .channels import kept_links
    return {**_hit(m), 'body': str(m.get('BodyText') or ''), 'to': str(m.get('RecipientsJson') or ''), 'links': kept_links(m),
            'messages': [_hit(x) for x in thread if x.get('Channel') != 'assistant'],
            'attachments': [{'id': x['AttachmentId'], 'name': x.get('Name'), 'bytes': x.get('Size')}
                            for x in store.list_attachments(m['MessageId']) or [] if not x.get('Inline')]}


def says(hits: list, store=None) -> str:
    """The hits as an agent reads them at its prompt: one block each, the id first - what `taskuary --message ID` opens. With none,
    and the `store` to ask, how far the saved mail reaches: an empty mailbox read "try fewer words" to an agent searching mail that was
    never there, and it searched on and told the owner nothing was found."""
    if not hits:
        far = reach(store) if store is not None else ''
        return 'No message in Taskuary matches that. ' + (far if far.startswith('Taskuary holds no') else
                                                          f'{far} Try fewer words, only --from, or a wider date range.'.strip())
    return '\n\n'.join(f"[{h['id']}] {h['when']} - {h['from']}\n{h['subject']}" + (f"  ({h['task']})" if h['task'] else '')
                       + (f"\nthread {h['thread']}" if h['thread'] else '') + (f"\n{h['snippet']}" if h['snippet'] else '') for h in hits)


def reach(store) -> str:
    """How far the owner's saved mail and messages reach, in one line - or that there are none, and where a mailbox is connected."""
    from . import words
    r = store._one("SELECT COUNT(*) AS n, MIN(SentAt) AS lo, MAX(SentAt) AS hi FROM message WHERE COALESCE(Channel, '') != 'assistant'") or {}
    if not r.get('n'):
        return (f"Taskuary holds no saved mail or messages at all yet - no mailbox has been read, so searching again finds nothing. Tell "
                f"the owner, with the place a mailbox is connected: {words.link('mail')}.")
    return f"Its saved mail runs from {str(r['lo'])[:10]} to {str(r['hi'])[:10]}."


def meeting_reads(store, who: list, subject: str, per: int = 3, cap: int = 12) -> list:
    """What the saved mail already says about a meeting's people and its subject - the opening reads of Prepare (the owner,
    2026-10-25: "an agent to research about person and topic through your mails"). Handed to the agent in its brief, so a brain
    with no shell starts from the same history a CLI would search; the agent searches on from there."""
    out, seen = [], set()
    def safe(f, *a, **k):
        try: return f(*a, **k)
        except Exception: return []
    reads = [safe(search, store, sender=w, limit=per) for w in (who or [])[:6] if str(w or '').strip()] + [safe(on_subject, store, subject, per + 2)]
    for hits in reads:
        for h in hits:
            if h['id'] in seen: continue
            seen.add(h['id']); out.append(h)
    return out[:cap]


def on_subject(store, subject: str, k: int, days: int = 365, pool: int = 400) -> list:
    """Saved mail ALIKE IN MEANING to `subject` (a task's title), nearest first - textsim over the recent mail. No embedder: none, never
    a word match standing in for meaning (a title's 'brief me before the' is not what the mail is about)."""
    if not str(subject or '').strip(): return []
    from .concierge import newest_rows
    try: rows = [r for r in newest_rows(store, days, cap=pool) if r.get('Channel') != 'assistant']
    except Exception: return []
    got = textsim.rank(store, subject, [(r['MessageId'], f"{r.get('Subject') or ''}. {r.get('Preview') or ''}") for r in rows], k=k)
    by = {r['MessageId']: r for r in rows}
    return [_hit(by[i]) for i, _ in (got or []) if i in by]
